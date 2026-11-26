import hashlib, json, os, re, shutil, subprocess, time, wave
from pathlib import Path
import cv2, numpy as np, streamlit as st
import imageio_ffmpeg, yt_dlp

FFMPEG = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
WORK, OUT = Path("work").resolve(), Path("salida").resolve()
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
MANIFEST = OUT / ".manifest.json"


# ---------- persistencia de trabajo ----------
def settings_fp(o, mode, clip_len, n, start_s, custom_s, model, lang):
    raw = {k: o.get(k) for k in ("layout", "cam_top", "fit", "subs", "share", "cx", "cy", "cw")}
    raw.update(mode=mode, clip_len=clip_len, n=n, start_s=start_s,
               custom_s=custom_s, model=model, lang=lang)
    return hashlib.sha1(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]


def save_manifest(video, W, H, dur, o, clips, fp, quality=None):
    data = {"video": str(video), "W": W, "H": H, "dur": dur, "quality": quality,
            "options": o, "fp": fp,
            "clips": [{"path": str(out), "start": s0, "score": score}
                      for out, s0, score in clips]}
    try:
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def read_manifest():
    try:
        d = json.loads(MANIFEST.read_text(encoding="utf-8"))
        video = Path(d["video"])
        clips = [(Path(c["path"]), c.get("start"), c.get("score"))
                 for c in d["clips"]
                 if Path(c["path"]).exists() and Path(c["path"]).stat().st_size > 1024]
        return (d, video, clips) if video.exists() and clips else None
    except Exception:
        return None


def scan_saved_clips():
    """Recupera clips generados antes de que existiera el manifiesto."""
    groups = {}
    for f in OUT.glob("*.mp4"):
        m = re.match(r"^(.*)_clip(\d+)\.mp4$", f.name)
        if m and f.stat().st_size > 1024:
            groups.setdefault(m.group(1), []).append((int(m.group(2)), f))
    if not groups:
        return None
    stem, items = max(groups.items(), key=lambda kv: len(kv[1]))
    items.sort()
    video = next((WORK / (stem + ext) for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi")
                  if (WORK / (stem + ext)).exists()), None)
    if video is None:
        return None
    W, H, dur = vinfo(video)
    return ({"W": W, "H": H, "dur": dur, "options": {}}, video,
            [(f, None, None) for _, f in items])


# ---------- utilidades de video ----------
def download(url, max_h=1080):
    height = int(max_h) if max_h else 99999
    fmt = f"bv*[height<={height}]+ba/b[height<={height}]/b"
    opts = {"format": fmt, "merge_output_format": "mp4",
            "outtmpl": str(WORK / "%(id)s.%(ext)s"), "ffmpeg_location": FFMPEG,
            "noplaylist": True, "quiet": True, "nooverwrites": True,
            # YouTube requires solving JS challenges; use Node only when it is installed
            # (Node 22+). Cloud images such as Hugging Face Spaces have no Node by default.
            "js_runtimes": {"node": {}} if shutil.which("node") else {}}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
        p = Path(y.prepare_filename(info))
    return p if p.exists() else p.with_suffix(".mp4")


def vinfo(p):
    c = cv2.VideoCapture(str(p))
    w, h, fps, n = int(c.get(3)), int(c.get(4)), c.get(5), c.get(7)
    c.release()
    return w, h, (n / fps if fps else 0)


def frame_at(p, t):
    c = cv2.VideoCapture(str(p)); c.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, f = c.read(); c.release()
    return f if ok else None


def preview_path(clip):
    return WORK / f"_preview_{clip.stem}.mp4"


def clip_preview(clip):
    """Short low-res sample: st.video loads entire files into RAM, so never feed it a full clip."""
    p = preview_path(clip)
    if not p.exists() or p.stat().st_mtime < clip.stat().st_mtime:
        r = subprocess.run(
            [FFMPEG, "-y", "-ss", "2", "-i", str(clip), "-t", "6", "-vf", "scale=200:-2",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34",
             "-c:a", "aac", "-b:a", "48k", "-threads", "1",
             "-movflags", "+faststart", str(p)],
            capture_output=True)
        if r.returncode or not p.exists() or p.stat().st_size < 1024:
            return None
    return p


def source_preview(video):
    """Short low-res sample of the source, cached; playable without loading the whole file."""
    p = WORK / f"_srcpreview_{video.stem}.mp4"
    if not p.exists() or p.stat().st_mtime < video.stat().st_mtime:
        r = subprocess.run(
            [FFMPEG, "-y", "-ss", "0", "-i", str(video), "-t", "10", "-vf", "scale=-2:360",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
             "-c:a", "aac", "-b:a", "64k", "-threads", "1",
             "-movflags", "+faststart", str(p)], capture_output=True)
        if r.returncode or not p.exists() or p.stat().st_size < 1024:
            return None
    return p


def clip_thumb(clip, t=1.0, max_h=720):
    """Cached frame: decoding video on each rerun is expensive."""
    p = WORK / f"_thumb_{clip.stem}_{int(t)}_{max_h}.jpg"
    if not p.exists() or p.stat().st_mtime < clip.stat().st_mtime:
        fr = frame_at(clip, t)
        if fr is None:
            return None
        if max_h and fr.shape[0] > max_h:
            w = max(int(fr.shape[1] * max_h / fr.shape[0]) // 2 * 2, 2)
            fr = cv2.resize(fr, (w, max_h))
        cv2.imwrite(str(p), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return p


def cam_rect(W, H, cx, cy, cw, cam_h):
    w = int(W * cw / 100) // 2 * 2
    h = int(w * cam_h / 1080) // 2 * 2
    if h > H:
        h = H // 2 * 2; w = int(h * 1080 / cam_h) // 2 * 2
    x = min(max(int(W * cx / 100), 0), W - w)
    y = min(max(int(H * cy / 100), 0), H - h)
    return x, y, w, h


def detect_cam(p, W, H, dur, cam_h):
    """Busca la cara del streamer (la pequeña) y propone el recuadro de la facecam."""
    try:
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cas.empty():
            return 0.0, 60.0, 28.0, False
        boxes = []
        for k in range(1, 9):
            f = frame_at(p, dur * k / 9)
            if f is None: continue
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            for (x, y, w, h) in cas.detectMultiScale(g, 1.1, 5, minSize=(40, 40)):
                if w < W * 0.25: boxes.append((x, y, w, h))
        if not boxes:
            return 0.0, 60.0, 28.0, False
        x, y, w, h = np.median(np.array(boxes), axis=0)
        cw_px = w * 3.0; ch_px = cw_px * cam_h / 1080
        cx = (x + w / 2 - cw_px / 2) / W * 100
        cy = (y + h / 2 - ch_px / 2) / H * 100
        return float(max(cx, 0)), float(max(cy, 0)), float(cw_px / W * 100), True
    except Exception:
        # Face detection is optional; never break clip generation because of it.
        return 0.0, 60.0, 28.0, False


# ---------- audio, transcripción, selección de clips ----------
def extract_audio(video):
    wav = WORK / (video.stem + ".wav")
    subprocess.run([FFMPEG, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True, capture_output=True)
    return wav


@st.cache_resource(show_spinner=False)
def get_model(size, gpu):
    from faster_whisper import WhisperModel
    return WhisperModel(size, device="cuda" if gpu else "cpu",
                        compute_type="float16" if gpu else "int8")


def transcribe(wav, size, lang, gpu):
    segs, _ = get_model(size, gpu).transcribe(
        str(wav), word_timestamps=True, vad_filter=True,
        language=None if lang == "auto" else lang)
    return [{"start": w.start, "end": w.end, "text": w.word.strip()}
            for s in segs for w in (s.words or [])]


def transcribe_clip(video, start, dur, size, lang, gpu):
    """Transcribe only one clip window; timestamps are absolute (video time)."""
    cache = WORK / f"{video.stem}_t{int(start)}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    seg_wav = WORK / f"_seg_{video.stem}_{int(start)}.wav"
    subprocess.run([FFMPEG, "-y", "-ss", str(start), "-t", str(dur), "-i", str(video),
                    "-vn", "-ac", "1", "-ar", "16000", str(seg_wav)],
                   check=True, capture_output=True)
    words = transcribe(seg_wav, size, lang, gpu)
    for w in words:
        w["start"] += start
        w["end"] += start
    try:
        cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return words


def interest_curve(wav, words, total):
    """Per-second attention score (audio energy + word density + exclamations)."""
    with wave.open(str(wav)) as wf:
        sr = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
    secs = max(int(len(data) / sr), 1)
    rms = np.sqrt((data[:secs * sr].reshape(secs, sr) ** 2).mean(1))
    wps, ex = np.zeros(secs), np.zeros(secs)
    for w in words:
        i = min(int(w["start"]), secs - 1)
        wps[i] += 1
        if "!" in w["text"] or "?" in w["text"]: ex[i] += 1
    z = lambda a: (a - a.mean()) / (a.std() + 1e-6)
    curve = z(rms) + z(wps) + 0.5 * z(ex)
    return curve, np.concatenate([[0], np.cumsum(curve)])


def load_transcript(video, wav, model, lang, gpu):
    """Cache the transcript on disk so re-runs and restarts are instant."""
    cache = WORK / f"{video.stem}.{model}.{lang}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    words = transcribe(wav, model, lang, gpu)
    try:
        cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return words


def pick_clips(wav, words, total, dur, n, cs=None):
    if cs is None:
        _, cs = interest_curve(wav, words, total)
    secs = len(cs) - 1
    if secs <= dur: return [(0.0, float(secs), 0.0)]
    cands = sorted(((cs[i + dur] - cs[i], i) for i in range(0, secs - dur, 5)), reverse=True)
    chosen = []
    for _, i in cands:
        if all(abs(i - j) >= dur for j in chosen): chosen.append(i)
        if len(chosen) == n: break
    out = []
    for s in sorted(chosen):
        nxt = [w["start"] for w in words if w["start"] >= s]
        st0 = nxt[0] if nxt else s
        a, b = min(int(st0), secs), min(int(st0) + dur, secs)
        out.append((float(st0), float(min(dur, total - st0)), float(cs[b] - cs[a])))
    return out


def plan_clips(dur, mode, n, start=0.0, custom_dur=30.0, clip_len=60):
    """Manual clip plans; returns None for automatic selection."""
    if mode == "Por duración fija":
        step = float(clip_len)
        count = max(int(dur // step), 1)
        return [(i * step, min(step, dur - i * step), 0.0) for i in range(count)]
    if mode == "Video completo":
        return [(0.0, float(dur), 0.0)]
    if mode == "Partes iguales":
        step = dur / int(n)
        return [(i * step, step, 0.0) for i in range(int(n))]
    if mode == "Personalizado":
        s = min(max(float(start), 0.0), max(dur - 1.0, 0.0))
        d = min(max(float(custom_dur), 1.0), dur - s)
        return [(s, d, 0.0)]
    return None


# ---------- subtítulos ----------
def ts(t):
    t = max(t, 0); h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def make_ass(words, start, dur, y, path):
    ws = [dict(w, start=w["start"] - start, end=w["end"] - start)
          for w in words if w["start"] >= start and w["end"] <= start + dur]
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
            "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            "Style: Default,Arial,80,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,5,40,40,0,1\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    lines = []
    for g in range(0, len(ws), 3):
        grp = ws[g:g + 3]
        for i, w in enumerate(grp):
            end = grp[i + 1]["start"] if i + 1 < len(grp) else w["end"]
            txt = " ".join(("{\\c&H00FFFF&}%s{\\c&HFFFFFF&}" if j == i else "%s") % x["text"].upper()
                           for j, x in enumerate(grp))
            lines.append(f"Dialogue: 0,{ts(w['start'])},{ts(end)},Default,,0,0,0,,{{\\pos(540,{y})}}{txt}")
    Path(path).write_text(head + "\n".join(lines), encoding="utf-8")


# ---------- render ----------
def circle_mask(size):
    """Precomputed circular alpha mask: much faster than a per-pixel geq expression."""
    p = WORK / f"_mask_{size}.png"
    if not p.exists():
        img = np.zeros((size, size), np.uint8)
        cv2.circle(img, (size // 2, size // 2), size // 2, 255, -1, lineType=cv2.LINE_AA)
        cv2.imwrite(str(p), img)
    return p


def render(video, start, dur, words, out, W, H, o):
    ass = f"{out.stem}.ass"
    extra_inputs = []
    if W > H and o.get("layout") == "overlay":  # estilo OpusClip: facecam circular flotante
        size = min(max(int(1080 * o["share"] / 100) // 2 * 2, 200), 560)
        fw = int(W * o["cw"] / 100) // 2 * 2
        fh = fw
        fx = min(max(int(W * o["cx"] / 100), 0), W - fw)
        fy = min(max(int(H * o["cy"] / 100), 0), H - fh)
        extra_inputs = ["-i", str(circle_mask(size))]
        cam = f"crop={fw}:{fh}:{fx}:{fy},scale={size}:{size},format=rgba[cam]"
        fc = ("[0:v]split=2[g][c];"
              "[g]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[game];"
              f"[c]{cam};"
              "[1:v]format=gray[mk];[cam][mk]alphamerge[camc];"
              "[game][camc]overlay=40:180[s]")
        seam = 1400
    elif W > H:  # horizontal -> pantalla dividida
        cam_h = int(1920 * o["share"] / 100) // 2 * 2; game_h = 1920 - cam_h
        x, y, w, h = cam_rect(W, H, o["cx"], o["cy"], o["cw"], cam_h)
        cam = f"crop={w}:{h}:{x}:{y},scale=1080:{cam_h}"
        if o["fit"]:
            game = (f"[b]split[b1][b2];[b1]scale=1080:{game_h}:force_original_aspect_ratio=increase,"
                    f"crop=1080:{game_h},boxblur=25:5[bg];[b2]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[game];")
            split = "split=2[a][b]"
        else:
            asp = 1080 / game_h
            gw, gh = (int(H * asp), H) if W / H > asp else (W, int(W / asp))
            gw, gh = gw // 2 * 2, gh // 2 * 2
            game = f"[b]crop={gw}:{gh}:{(W-gw)//2}:{(H-gh)//2},scale=1080:{game_h}[game];"
            split = "split=2[a][b]"
        order = "[cam][game]" if o["cam_top"] else "[game][cam]"
        seam = cam_h if o["cam_top"] else game_h
        fc = f"[0:v]{split};[a]{cam}[cam];{game}{order}vstack=inputs=2[s]"
    else:      # ya es vertical
        seam = 1400
        fc = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[s]"
    if o["subs"]:
        make_ass(words, start, dur, seam, WORK / ass)
        fc += f";[s]ass={ass}[v]"
    else:
        fc += ";[s]null[v]"
    cmd = [FFMPEG, "-y", "-ss", str(start), "-t", str(dur), "-i", str(video), *extra_inputs, "-filter_complex", fc,
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-1500:])


# ---------- interfaz ----------
from pathlib import Path as _Path

_CSS = (_Path(__file__).parent / "ui.css").read_text(encoding="utf-8")
st.html(f"<style>{_CSS}</style>")


def _svg(d):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{d}</svg>'


I = {
    "play": '<span class="ic">▶</span>',
    "link": '<span class="ic">🔗</span>',
    "folder": '<span class="ic">📁</span>',
    "upload": '<span class="ic">⬆</span>',
    "clap": '<span class="ic">🎬</span>',
    "monitor": '<span class="ic">🖥</span>',
    "grid": '<span class="ic">▦</span>',
    "resize": '<span class="ic">⤢</span>',
    "arrowH": '<span class="ic">↔</span>',
    "arrowV": '<span class="ic">↕</span>',
    "scissors": '<span class="ic">✂</span>',
    "eye": '<span class="ic">👁</span>',
    "volume": '<span class="ic">🔊</span>',
    "full": '<span class="ic">⛶</span>',
    "restart": '<span class="ic">↺</span>',
    "spark": '<span class="ic">✦</span>',
    "settings": '<span class="ic">⚙</span>',
    "info": '<span class="ic">ⓘ</span>',
    "person": '<span class="ic">👤</span>',
}


def _title(icon, text):
    st.html(f'<div class="card-title">{I[icon]}<span>{text}</span></div>')


def _slider_row(icon, label, value, key, lo, hi, step=1, fmt=".0f"):
    st.html(f'<div class="slider-row">{I[icon]}<span class="lb">{label}</span>'
            f'<span class="val">{value:{fmt}} %</span></div>')
    return st.slider(label, lo, hi, value, step=step, key=key, label_visibility="collapsed")


QUALITY = {"1080p · Full HD": 1080, "720p · HD": 720, "480p": 480,
           "360p": 360, "320p · ligero": 320, "Mejor disponible": None}

# permanent custom nav — real links, no native sidebar collapse button
_VIEW = st.query_params.get("view", "crear")
_NAV = [("crear", "clap", "Crear Short"), ("proyectos", "folder", "Mis Proyectos"),
        ("config", "settings", "Configuración"), ("acerca", "info", "Acerca de")]
_nav_html = "".join(
    f'<a class="sb-item {"active" if _VIEW == key else ""}" href="?view={key}">{I[icon]} {label}</a>'
    for key, icon, label in _NAV)
st.html(
    f'<div class="sb-custom"><div class="sb-brand">{I["play"]}<span>Generador de Shorts</span></div>'
    f'<nav class="sb-nav">{_nav_html}</nav></div>')

st.html(
    f'<div class="app-header"><div class="app-icon">{I["clap"]}</div>'
    '<div><h1>Generador de Shorts</h1>'
    '<p>Ajusta el encuadre, genera clips y crea tu Short en pocos pasos</p></div></div>')

IN_SPACE = bool(os.environ.get("SPACE_ID"))
S = st.session_state
S.setdefault("results", [])

# direct folder preferences from Configuración
if S.get("out_dir"):
    _p = Path(S["out_dir"]).expanduser()
    try: _p.mkdir(parents=True, exist_ok=True)
    except Exception: pass
    OUT = _p.resolve()
    MANIFEST = OUT / ".manifest.json"
if S.get("work_dir"):
    _p = Path(S["work_dir"]).expanduser()
    try: _p.mkdir(parents=True, exist_ok=True)
    except Exception: pass
    WORK = _p.resolve()

if S.get("theme") == "Claro":
    st.html("""<style>
:root{--bg:#f5f6fa;--nav:#ffffff;--card:#ffffff;--card2:#eef0f6;
--border:#d9dce6;--text:#1b1d29;--muted:#5c6172;--input:#f4f5f9;}
.stApp{color:var(--text)!important;}
.app-header h1,.app-header p,.card-title,.field-label,.sb-brand span,.sb-item,
.slider-row .lb,.slider-row .val,.prev-title,.player,.qbadge{color:var(--text)!important;}
.sb-item.active{color:#fff!important;}
.stMarkdown,.stMarkdown p,.stCaption,[data-testid="stWidgetLabel"],label,.stAlert{color:#242735!important;}
.stTextInput input{color:#161824!important;}
.stButton>button{color:#242735!important;}
.stButton>button[kind="primary"]{color:#fff!important;}
.stSegmentedControl [role="radio"]{color:#3a3d4d!important;}
.stSegmentedControl [role="radio"][aria-checked="true"]{color:#fff!important;}
.stButton>button:hover{background:#e6e9f1!important;border-color:#cfd3df!important;color:#242735!important;}
.stSegmentedControl [role="radio"]:hover,.stPills [role="radio"]:hover{background:#e7e9f1!important;color:#242735!important;}
</style>""")

if _VIEW == "proyectos":
    with st.container(border=True):
        _title("folder", "Mis Proyectos")
        groups = {}
        for f in OUT.glob("*.mp4"):
            m = re.match(r"^(.*)_clip(\d+)\.mp4$", f.name)
            if m and f.stat().st_size > 1024:
                groups.setdefault(m.group(1), []).append((int(m.group(2)), f))
        if not groups:
            st.caption("Aún no hay clips guardados.")
        for stem, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            items.sort()
            st.markdown(f"**{stem}** · {len(items)} clips")
            if st.button("Abrir proyecto", key="open_" + re.sub(r"\W", "", stem)[:24]):
                src = next((WORK / (stem + ext) for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi")
                            if (WORK / (stem + ext)).exists()), None)
                if src:
                    S.video = src
                    S.W, S.H, S.dur = vinfo(src)
                S.results = [(f, None, None) for _, f in items]
                st.query_params["view"] = "crear"
                st.rerun()
    st.stop()

if _VIEW == "config":
    with st.container(border=True):
        _title("settings", "Configuración")
        st.segmented_control("Tema", ["Oscuro", "Claro"], key="theme")
        st.caption("El tema se aplica al guardar. El modo claro cambia los colores de la interfaz.")
        st.text_input("Carpeta de salida (clips)", value=str(S.get("out_dir", OUT)), key="out_dir_in")
        st.text_input("Carpeta de descarga temporal", value=str(S.get("work_dir", WORK)), key="work_dir_in")
        st.checkbox("Eliminar el video fuente después de generar (quedan solo los clips)",
                    value=bool(S.get("cleanup_source", False)), key="cleanup_in")
        if st.button("Guardar ajustes", type="primary"):
            S.out_dir = st.session_state.out_dir_in
            S.work_dir = st.session_state.work_dir_in
            S.cleanup_source = st.session_state.cleanup_in
            st.success("Ajustes guardados.")
    st.stop()

if _VIEW == "acerca":
    with st.container(border=True):
        _title("info", "Acerca de")
        st.markdown("Generador de Shorts: convierte un video largo en clips verticales 9:16 con subtítulos animados y facecam opcional.")
        st.caption("La transcripción se guarda en caché y los clips ya generados se reutilizan si no cambias los ajustes.")
    st.stop()

saved = read_manifest() or scan_saved_clips()
restore_state = None
if "video" not in S and saved:
    d, saved_video, saved_clips = saved
    restore_state = (d, saved_video, saved_clips)
    if "video_quality" not in S:
        S.video_quality = d.get("quality") or f"{int(d.get('H', 0))}p"

mode = "Por duración fija"
clip_len, n, start_s, custom_s = 60, 3, 0.0, min(30.0, 60.0)
model, lang, gpu, expres = "tiny", "es", False, False
o = dict(cam_top=True, fit=False, subs=True, layout="overlay", share=45,
         cx=0.0, cy=60.0, cw=28.0)

# left column: origen -> vista previa -> clips; right column: encuadre -> acciones
col_left, col_right = st.columns([1.45, 1], gap="medium")

with col_left:
    with st.container(border=True, height=170):
        _title("link", "Origen del video")
        src_labels = {"URL": ":material/link: URL", "Archivo": ":material/folder: Archivo",
                      "Subir": ":material/upload: Subir"}
        src = st.segmented_control("Origen", ["URL", "Archivo", "Subir"],
                                   format_func=lambda x: src_labels[x],
                                   default=("Subir" if IN_SPACE else "URL"),
                                   key="src", label_visibility="collapsed")
        url = path_in = up = None
        quality = "720p · HD"
        c_in, c_qual, c_btn = st.columns([2.95, 1.1, 1.35], vertical_alignment="bottom", gap="medium")
        with c_in:
            if src == "URL":
                url = st.text_input("Enlace", placeholder="Pega aquí el enlace de YouTube...",
                                    key="url", label_visibility="collapsed", live=True)
            elif src == "Archivo":
                path_in = st.text_input("Ruta", placeholder=r"C:\Videos\stream.mp4",
                                        key="path_in", label_visibility="collapsed", live=True)
            else:
                up = st.file_uploader("Video", type=["mp4", "mov", "mkv", "webm", "avi"],
                                      label_visibility="collapsed")
        with c_qual:
            if src == "URL":
                quality = st.selectbox("Calidad", list(QUALITY), index=1, key="quality",
                                       label_visibility="collapsed",
                                       help="Calidad de descarga. Se fija al cargar y no se puede cambiar después.")
        with c_btn:
            load_clicked = st.button("Cargar video", type="primary",
                                     icon=":material/play_arrow:", key="load", width="stretch")

    # ---- vista previa reproducible ----
    if "video" in S:
        W, H, dur, p = S.W, S.H, S.dur, S.video
        with st.container(border=True):
            st.html(f'<div class="prev-head"><div class="prev-title">{I["eye"]}<span>Vista previa</span></div></div>')
            sample = source_preview(p)
            if sample is not None:
                st.video(str(sample), width="stretch", alt="Vista previa reproducible del video")
            else:
                st.caption("No se pudo generar la vista previa.")
            if S.get("curve") is not None:
                with st.expander("Análisis de interés"):
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Duración", f"{int(dur) // 60}:{int(dur) % 60:02d}")
                    k2.metric("Palabras", len(S.words or []))
                    k3.metric("Resolución", f"{W}x{H}")
                    st.line_chart({"Interés": S.curve.tolist()}, height=140,
                                  alt="Interés por segundo a lo largo del video")
    else:
        with st.container(border=True, height=120):
            _title("eye", "Vista previa")
            st.caption("Carga un video para ver el encuadre en vivo.")

    # ---- clips y modo de edición ----
    if "video" in S:
        with st.container(border=True):
            _title("scissors", "Clips y modo de edición")
            st.html('<div class="field-label">Modo</div>')
            mode = st.segmented_control("Modo",
                ["Por duración fija", "Automático", "Video completo", "Partes iguales", "Personalizado"],
                default="Por duración fija", key="mode", label_visibility="collapsed")
            clip_len, n, start_s, custom_s, fast = 60, 3, 0.0, min(30.0, dur), False
            if mode == "Automático":
                a, b = st.columns(2)
                clip_len = a.selectbox("Duración", [30, 45, 60, 90, 120], index=2, key="clip_len")
                n = b.number_input("Cantidad", 1, 20, 3, key="nclips")
                fast = st.checkbox("Modo rápido (solo transcribe los clips)", value=True, key="fast_mode")
            elif mode == "Partes iguales":
                n = st.number_input("Cantidad de partes", 1, 20, 3, key="nclips")
                st.caption(f"Cada parte: {dur / n / 60:.2f} min")
            elif mode == "Personalizado":
                a, b = st.columns(2)
                start_s = a.number_input("Inicio (s)", 0.0, float(dur), 0.0, key="start_s")
                custom_s = b.number_input("Duración (s)", 1.0, float(dur), min(30.0, dur), key="custom_s")
            dc, sc2 = st.columns([1, 1.25], vertical_alignment="bottom")
            with dc:
                st.html('<div class="field-label">Duración de cada clip (s)</div>')
                clip_len = st.selectbox("Duración", [30, 60, 90, 120],
                                        index=[30, 60, 90, 120].index(clip_len) if clip_len in (30, 60, 90, 120) else 1,
                                        key="clip_len2", label_visibility="collapsed")
            with sc2:
                o["subs"] = st.checkbox("Subtítulos animados", value=bool(S.get("subs", True)),
                                        key="subs", help="Resalta la palabra activa en amarillo.")
            with st.expander("Transcripción y rendimiento"):
                expres = st.checkbox("Modo exprés (sin transcripción, mucho más rápido)",
                                     value=False, key="expres")
                if expres: o["subs"] = False
                model = st.selectbox("Modelo Whisper", ["tiny", "base", "small", "medium"], index=0, key="model")
                lang = st.selectbox("Idioma", ["es", "en", "auto"], key="lang")
                gpu = st.checkbox("Usar GPU NVIDIA", key="gpu")
                st.caption("`tiny` es más rápido en CPU. La transcripción se guarda en caché.")

if IN_SPACE:
    st.caption("En la nube, YouTube bloquea muchas descargas: elige **Subir** y selecciona el video desde tu celular (máx. 2 GB).")

if load_clicked:
    try:
        with st.spinner("Cargando..."):
            if url: p = download(url.strip(), QUALITY[quality])
            elif path_in: p = Path(path_in.strip().strip('"'))
            elif up:
                p = WORK / up.name
                p.write_bytes(up.getbuffer())
            else: st.stop()
            W, H, dur = vinfo(p)
            S.update(video=p, W=W, H=H, dur=dur, words=None, share=45,
                     cx=0.0, cy=60.0, cw=28.0, found=False, video_quality=f"{int(H)}p",
                     curve=None, cs=None, wav=None, wmodel=None, results=[])
            MANIFEST.unlink(missing_ok=True)
            if W > H:
                S.cx, S.cy, S.cw, found = detect_cam(p, W, H, dur,
                                                     int(1920 * 45 / 100) // 2 * 2)
                S.found = found
            st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")

# right column: encuadre (tall) + acciones
if "video" in S:
    W, H, dur, p = S.W, S.H, S.dur, S.video
    with col_right:
        with st.container(border=True):
            _title("monitor", "Encuadre de la facecam")
            if W > H:
                styles = {"Facecam flotante": ":material/monitor: Facecam flotante",
                          "Pantalla dividida": ":material/grid_on: Pantalla dividida"}
                estilo = st.segmented_control("Estilo", ["Facecam flotante", "Pantalla dividida"],
                                              format_func=lambda x: styles[x], default="Facecam flotante",
                                              key="layout_style", label_visibility="collapsed")
                o["layout"] = "overlay" if estilo == "Facecam flotante" else "split"
                with st.container():
                    if o["layout"] == "split":
                        o["cam_top"] = st.selectbox("Posición",
                            ["Streamer arriba, juego abajo", "Juego arriba, streamer abajo"],
                            key="pos", label_visibility="collapsed").startswith("Streamer")
                    o["share"] = _slider_row("resize", "Tamaño de la facecam (%)",
                                             int(S.share), "share", 30, 70)
                    o["cw"] = _slider_row("arrowH", "Ancho facecam (%)",
                                          int(S.cw), "cw", 5, 100)
                    o["cx"] = _slider_row("arrowH", "Posición X (%)",
                                          float(S.cx), "cx", 0.0, 100.0, 0.01, ".2f")
                    o["cy"] = _slider_row("arrowV", "Posición Y (%)",
                                          float(S.cy), "cy", 0.0, 100.0, 0.01, ".2f")
                    if not S.get("found"):
                        st.caption("Cara no detectada: ajusta el recuadro.")
            else:
                o.update(share=45, cx=0, cy=0, cw=100, layout="none")
                st.caption("Video vertical: no necesita pantalla dividida.")

        with st.container(border=True):
            st.html('<div class="actions">')
            reset_all = st.button("Restablecer", icon=":material/restart_alt:",
                                  key="reset_all", width="stretch")
            generar = st.button("Generar Short", type="primary", icon=":material/auto_awesome:",
                                key="generate", width="stretch")
            st.html('</div>')
else:
    with col_right:
        with st.container(border=True, height=170):
            _title("monitor", "Encuadre de la facecam")
            st.caption("Carga un video para ajustar el encuadre.")
        with st.container(border=True, height=120):
            reset_all = st.button("Restablecer", icon=":material/restart_alt:",
                                  key="reset_all", width="stretch")
            generar = st.button("Generar Short", type="primary", icon=":material/auto_awesome:",
                                key="generate", disabled=True, width="stretch")

if reset_all:
    if restore_state:
        d, saved_video, saved_clips = restore_state
        opts = d.get("options") or {}
        S.update(video=saved_video, W=d["W"], H=d["H"], dur=d["dur"], results=saved_clips,
                 video_quality=d.get("quality") or f"{int(d['H'])}p",
                 words=None, wav=None, curve=None, cs=None, wmodel=None,
                 share=opts.get("share", 45), cx=opts.get("cx", 0.0), cy=opts.get("cy", 60.0),
                 cw=opts.get("cw", 28.0), found=False, subs=opts.get("subs", True),
                 fit=opts.get("fit", False),
                 pos=("Streamer arriba, juego abajo" if opts.get("cam_top", True)
                      else "Juego arriba, streamer abajo"),
                 layout_style=("Facecam flotante" if opts.get("layout", "overlay") == "overlay"
                               else "Pantalla dividida"))
    else:
        for k in ("video", "results", "words", "wav", "curve", "cs", "wmodel", "video_quality"):
            S.pop(k, None)
    st.rerun()

if generar and "video" in S:
    try:
        with st.status("Generando...", expanded=True) as stt:
            bar = st.progress(0.0, text="Preparando...")
            use_fast = (expres or mode in ("Por duración fija", "Partes iguales", "Personalizado")
                        or bool(fast and mode == "Automático"))
            if S.get("wav") is None:
                bar.progress(0.02, text="Extrayendo audio...")
                S.wav = extract_audio(p)
            if use_fast:
                S.curve, S.cs = interest_curve(S.wav, [], S.dur)
            else:
                if S.get("words") is None or S.get("wmodel") != (model, lang):
                    bar.progress(0.05, text="Transcribiendo (puede tardar varios minutos en CPU)...")
                    S.words = load_transcript(p, S.wav, model, lang, gpu)
                    S.wmodel = (model, lang)
                S.curve, S.cs = interest_curve(S.wav, S.words or [], S.dur)
            bar.progress(0.10, text="Buscando los mejores momentos...")
            if mode == "Automático":
                clips = pick_clips(S.wav, [] if use_fast else (S.words or []),
                                   dur, clip_len, int(n), S.get("cs"))
            else:
                clips = plan_clips(dur, mode, int(n), start_s, custom_s, clip_len)
            total = max(len(clips), 1)
            fp = settings_fp(o, mode, clip_len, n, start_s, custom_s, model, lang)
            old = read_manifest()
            same_settings = bool(old and old[0].get("fp") == fp)
            S.results = []
            t_render = time.perf_counter()
            reused = 0
            for i, (s0, d0, score) in enumerate(clips, 1):
                bar.progress(0.10 + 0.85 * (i - 1) / total, text=f"Clip {i} de {total}...")
                out = OUT / f"{p.stem}_clip{i}.mp4"
                if same_settings and out.exists() and out.stat().st_size > 1024:
                    reused += 1
                    st.write(f"Clip {i}: reutilizando archivo ya generado.")
                else:
                    if use_fast and o["subs"]:
                        words_i = transcribe_clip(p, s0, d0, model, lang, gpu)
                    else:
                        words_i = S.words or []
                    render(p, s0, d0, words_i, out, W, H, o)
                S.results.append((out, s0, score))
                elapsed = time.perf_counter() - t_render
                eta = (elapsed / i) * (total - i)
                bar.progress(0.10 + 0.85 * i / total,
                             text=f"Clip {i}/{total} · {elapsed:.0f}s · ~{eta:.0f}s restantes")
            save_manifest(p, W, H, dur, o, S.results, fp, S.get("video_quality"))
            if S.get("cleanup_source"):
                try: p.unlink(missing_ok=True)
                except Exception: pass
            bar.progress(1.0, text=f"Listo: {total} clips en {time.perf_counter() - t_render:.0f} s"
                         + (f" · {reused} reutilizados" if reused else ""))
            stt.update(label=f"¡Listo! {total} clips", state="complete")
    except Exception as e:
        st.error(f"Error: {e}")

# ---------- resultados ----------
if S.get("results"):
    st.subheader(f"Clips generados · {len(S.results)}")
    st.caption("Los clips quedan en `salida/`. Cada tarjeta reproduce una muestra corta y descarga el original.")
    todo = [out for out, _, _ in S.results
            if not preview_path(out).exists() or preview_path(out).stat().st_mtime < out.stat().st_mtime]
    if todo:
        with st.status(f"Preparando {len(todo)} vistas previas (solo la primera vez)...",
                       expanded=False) as stt:
            for j, out in enumerate(todo, 1):
                stt.write(f"Vista previa {j}/{len(todo)}")
                clip_preview(out)
            stt.update(label="Vistas previas listas", state="complete")
    grid = st.columns(3)
    for i, (out, s0, score) in enumerate(S.results, 1):
        with grid[(i - 1) % 3].container(border=True):
            prev = clip_preview(out)
            if prev is not None:
                st.video(str(prev), alt=f"Vista previa del clip {i}")
            else:
                thumb = clip_thumb(out)
                if thumb is not None:
                    st.image(str(thumb), alt=f"Miniatura del clip {i}", width="stretch")
            label = (f"**{i} · {int(s0 // 60):02d}:{int(s0 % 60):02d}**"
                     if s0 is not None else f"**Clip {i}**")
            st.markdown(label)
            st.caption(f"Interés {score:+.1f}" if score else "Clip personalizado")
            st.download_button("Descargar", out.read_bytes, out.name, "video/mp4",
                               key=f"dl_{i}_{out.name}", icon=":material/download:", width="stretch")
