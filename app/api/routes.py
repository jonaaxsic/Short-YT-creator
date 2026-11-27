"""Manejador HTTP: traduce peticiones a llamadas de servicios."""
import json, re, threading, uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from .. import config, state
from ..services import video
from .jobs import generate


def friendly_error(exc):
    """Errores en lenguaje del usuario, con una acción posible."""
    text = str(exc)
    low = text.lower()
    if "cancelada" in low:
        return "Descarga cancelada. Puedes reintentar cuando quieras."
    if any(k in low for k in ("unable to download", "http error", "not available", "video unavailable")):
        return "No se pudo descargar el video. Revisa el enlace o usa Subir para seleccionarlo desde tu equipo."
    if "no such file" in low or "file not found" in low:
        return "No encontré el archivo. Revisa la ruta o usa Subir."
    return text

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def _serve(self, path, ctype):
        f = config.WEB / path
        if not f.exists():
            self.send_error(404)
            return
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _video(self, path):
        if not path.exists():
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        code = 200
        if rng and rng.startswith("bytes="):
            parts = rng[6:].split("-")
            start = int(parts[0] or 0)
            if len(parts) > 1 and parts[1]:
                end = int(parts[1])
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path == "/video/source" and state.STATE["video"]:
            f = Path(state.STATE["video"])
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(f.stat().st_size))
            self.end_headers()
        else:
            self.send_error(404)

    def _activity(self, path):
        import time
        state.LAST_ACTIVITY = time.time()
        if path.startswith("/api/") and path not in ("/api/idle-status", "/api/reactivate") and state.IDLE:
            self._json({"idle": True, "message": "El servicio se detuvo por inactividad."}, 503)
            return False
        return True

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        if not self._activity(path):
            return
        if path in ("/", "/index.html"):
            return self._serve("index.html", "text/html; charset=utf-8")
        if path == "/styles.css":
            return self._serve("styles.css", "text/css; charset=utf-8")
        if path.startswith(("/css/", "/js/")):
            rel = path.lstrip("/")
            ctype = "text/css; charset=utf-8" if rel.endswith(".css") else "application/javascript; charset=utf-8"
            return self._serve(rel, ctype)
        if path == "/api/idle-status":
            return self._json({"idle": state.IDLE, "minutes": state.IDLE_MINUTES})
        if path == "/api/cache":
            files = [f for f in config.WORK.glob("_*.mp4")] + [f for f in config.WORK.glob("_*.jpg")] \
                    + [f for f in config.WORK.glob("_*.wav")]
            return self._json({"files": len(files),
                               "megabytes": round(sum(f.stat().st_size for f in files) / 1048576, 1)})
        if path == "/api/load-progress":
            return self._json(state.LOAD_PROGRESS)
        if path == "/api/state":
            return self._json({"video": bool(state.STATE["video"]), "W": state.STATE["W"],
                               "H": state.STATE["H"], "dur": state.STATE["dur"],
                               "quality": state.STATE["quality"],
                               "clips": len(state.STATE["results"])})
        if path == "/api/settings":
            return self._json(config.load_cfg())
        if path == "/api/projects":
            groups = {}
            for f in config.OUT.glob("*.mp4"):
                m = re.match(r"^(.*)_clip(\d+)\.mp4$", f.name)
                if m and f.stat().st_size > 1024:
                    groups.setdefault(m.group(1), []).append((int(m.group(2)), f.name))
            return self._json([{"stem": k, "count": len(v)} for k, v in
                               sorted(groups.items(), key=lambda kv: -len(kv[1]))])
        if path == "/api/job":
            return self._json(state.JOBS.get(q.get("id", [""])[0], {"done": False, "progress": 0, "message": ""}))
        if path == "/api/clips":
            return self._json([{"name": f.name, "start": s0} for f, s0, _ in state.STATE["results"]])
        if path == "/video/source":
            if not state.STATE["video"]:
                return self.send_error(404)
            return self._video(Path(state.STATE["video"]))
        if path == "/video/clip":
            name = q.get("name", [""])[0]
            return self._video(config.OUT / name)
        if path == "/video/preview":
            name = q.get("name", [""])[0]
            f = video.preview_path(config.OUT / name)
            return self._video(f if f.exists() else config.OUT / name)
        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        if not self._activity(path):
            return
        if path == "/api/reactivate":
            state.IDLE = False
            state.LAST_ACTIVITY = __import__("time").time()
            return self._json({"ok": True, "message": "Servidor reactivado."})
        if path == "/api/cache/clear":
            import time
            state.LAST_ACTIVITY = time.time()
            removed, freed = 0, 0
            for pattern in ("_*.mp4", "_*.jpg", "_*.wav"):
                for f in config.WORK.glob(pattern):
                    try:
                        freed += f.stat().st_size
                        f.unlink()
                        removed += 1
                    except Exception:
                        pass
            return self._json({"ok": True, "removed": removed,
                               "megabytes": round(freed / 1048576, 1)})
        if path == "/api/settings":
            cfg = config.load_cfg()
            cfg.update(self._body())
            config.save_cfg(cfg)
            config.apply_dirs(cfg)
            return self._json({"ok": True})
        if path == "/api/upload":
            name = unquote(self.headers.get("X-Filename", "upload.mp4"))
            n = int(self.headers.get("Content-Length", 0))
            f = config.WORK / name
            with open(f, "wb") as out:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    out.write(chunk)
                    left -= len(chunk)
            return self._json({"path": str(f)})
        if path == "/api/load":
            b = self._body()
            kind, value = b.get("kind", "url"), b.get("value", "")
            state.LOAD_CANCEL["requested"] = False
            state.LOAD_PROGRESS.update(active=True, percent=0,
                                       message="Resolviendo el video y eligiendo la calidad...")

            def progress(info):
                if info.get("status") == "downloading":
                    total = info.get("total_bytes") or info.get("total_bytes_estimate") or 0
                    done = info.get("downloaded_bytes") or 0
                    pct = (done / total * 100) if total else float(info.get("percent") or 0)
                    eta = info.get("eta")
                    extra = f" · {eta}s restantes" if eta else ""
                    state.LOAD_PROGRESS.update(percent=pct, message=f"Descargando {pct:.0f}%{extra}")
                elif info.get("status") == "finished":
                    state.LOAD_PROGRESS.update(percent=100, message="Uniendo video y audio...")

            try:
                if kind == "url":
                    p = video.download(value.strip(), config.QUALITY.get(b.get("quality", "720p"), 720),
                                       on_progress=progress,
                                       should_cancel=lambda: state.LOAD_CANCEL["requested"])
                elif kind == "path":
                    p = Path(value.strip().strip('"'))
                else:
                    p = config.WORK / value
                if not p.exists():
                    raise FileNotFoundError(str(p))
                W, H, dur = video.vinfo(p)
                state.STATE.update(video=str(p), W=W, H=H, dur=dur,
                             quality=f"{int(H)}p", results=[])
                state.LOAD_PROGRESS.update(active=False, percent=100, message="Listo")
                return self._json({"ok": True, "W": W, "H": H, "dur": dur,
                                   "quality": state.STATE["quality"], "name": p.name})
            except Exception as exc:
                state.LOAD_PROGRESS.update(active=False, percent=0, message="")
                return self._json({"ok": False, "error": friendly_error(exc)}, 400)
        if path == "/api/delete-clip":
            name = self._body().get("name", "")
            if Path(name).name != name:
                return self._json({"ok": False, "error": "Nombre de clip no válido"}, 400)
            target = config.OUT / name
            if not target.exists():
                return self._json({"ok": False, "error": "El clip ya no existe"}, 404)
            target.unlink(missing_ok=True)
            for f in (video.preview_path(target), config.WORK / f"_thumb_{target.stem}_1_720.jpg"):
                f.unlink(missing_ok=True)
            state.STATE["results"] = [item for item in state.STATE["results"]
                                      if item[0].name != name]
            return self._json({"ok": True})
        if path == "/api/cancel-load":
            state.LOAD_CANCEL["requested"] = True
            return self._json({"ok": True})
        if path == "/api/cancel":
            job_id = self._body().get("id", "")
            state.CANCELLED.add(job_id)
            proc = state.PROCESSES.get(job_id)
            if proc is not None and proc.poll() is None:
                proc.terminate()
            return self._json({"ok": True})
        if path == "/api/generate":
            if not state.STATE["video"]:
                return self._json({"error": "Carga un video primero"}, 400)
            job_id = uuid.uuid4().hex[:12]
            state.JOBS[job_id] = {"done": False, "progress": 0, "message": "Preparando..."}
            threading.Thread(target=generate, args=(job_id, self._body()), daemon=True).start()
            return self._json({"id": job_id})
        if path == "/api/restore":
            stem = self._body().get("stem", "")
            src = next((config.WORK / (stem + ext) for ext in
                        (".mp4", ".mkv", ".webm", ".mov", ".avi")
                        if (config.WORK / (stem + ext)).exists()), None)
            if src:
                W, H, dur = video.vinfo(src)
                state.STATE.update(video=str(src), W=W, H=H, dur=dur, quality=f"{int(H)}p")
            files = sorted(config.OUT.glob(stem + "_clip*.mp4"))
            state.STATE["results"] = [(f, None, None) for f in files]
            return self._json({"ok": True, "clips": len(files)})
        self.send_error(404)
