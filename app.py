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


def save_manifest(video, W, H, dur, o, clips, fp):
    data = {"video": str(video), "W": W, "H": H, "dur": dur, "options": o, "fp": fp,
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
def download(url):
    opts = {"format": "bv*[height<=1080]+ba/b[height<=1080]/b", "merge_output_format": "mp4",
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
st.set_page_config(page_title="Generador de Shorts", layout="wide")
st.title("Generador de shorts")
IN_SPACE = bool(os.environ.get("SPACE_ID"))
st.caption("Carga un video, ajusta el encuadre y genera clips verticales. "
           + ("Todo se procesa en la nube: tu equipo no se traba."
              if IN_SPACE else "Todo se procesa en tu PC."))
S = st.session_state
S.setdefault("results", [])

saved = read_manifest() or scan_saved_clips()
if "video" not in S and saved:
    d, saved_video, saved_clips = saved
    st.info(f"Trabajo guardado: **{saved_video.name}** · {len(saved_clips)} clips listos.")
    if st.button("Recuperar trabajo guardado", icon=":material/restore:", key="restore"):
        opts = d.get("options") or {}
        S.update(video=saved_video, W=d["W"], H=d["H"], dur=d["dur"], results=saved_clips,
                 words=None, wav=None, curve=None, cs=None, wmodel=None,
                 share=opts.get("share", 45), cx=opts.get("cx", 0.0), cy=opts.get("cy", 60.0),
                 cw=opts.get("cw", 28.0), found=False, subs=opts.get("subs", True),
                 fit=opts.get("fit", False),
                 pos=("Streamer arriba, juego abajo" if opts.get("cam_top", True)
                      else "Juego arriba, streamer abajo"),
                 layout_style=("Facecam flotante" if opts.get("layout", "overlay") == "overlay"
                               else "Pantalla dividida"))
        st.rerun()


def apply_preset():
    p = S.get("preset")
    if p == "Streams de gaming":
        S["pos"] = "Streamer arriba, juego abajo"; S["fit"] = False; S["subs"] = True
        S["layout_style"] = "Facecam flotante"
    elif p == "Vídeos largos":
        S["subs"] = True
    elif p == "Subtítulos":
        S["subs"] = True
    elif p == "Reencuadre":
        S["fit"] = True; S["subs"] = True


with st.container(border=True):
    c1, c2, c3 = st.columns([2, 4, 1], vertical_alignment="bottom")
    src = c1.segmented_control("Origen", ["URL", "Archivo", "Subir"],
                               default=("Subir" if IN_SPACE else "URL"), key="src", width="stretch")
    url = path_in = up = None
    if src == "URL": url = c2.text_input("Pega la URL", placeholder="https://youtube.com/watch?v=...", key="url", label_visibility="collapsed")
    elif src == "Archivo": path_in = c2.text_input(r"Ruta del video", placeholder=r"C:\Videos\stream.mp4", key="path_in", label_visibility="collapsed")
    else: up = c2.file_uploader("Video", type=["mp4", "mov", "mkv", "webm", "avi"], label_visibility="collapsed")
    load_clicked = c3.button("Cargar video", type="primary", icon=":material/upload:", key="load", width="stretch")

if IN_SPACE:
    st.caption("En la nube, YouTube bloquea muchas descargas: elige **Subir** y selecciona el video desde tu celular (máx. 2 GB).")

if load_clicked:
    try:
        with st.spinner("Cargando..."):
            if url: p = download(url.strip())
            elif path_in: p = Path(path_in.strip().strip('"'))
            elif up:
                p = WORK / up.name; p.write_bytes(up.getbuffer())
            else: st.stop()
            W, H, dur = vinfo(p)
            S.update(video=p, W=W, H=H, dur=dur, words=None, share=45,
                     cx=0.0, cy=60.0, cw=28.0, found=False,
                     curve=None, cs=None, wav=None, wmodel=None, results=[])
            MANIFEST.unlink(missing_ok=True)
            cam_h = int(1920 * 45 / 100) // 2 * 2
            if W > H:
                S.cx, S.cy, S.cw, found = detect_cam(p, W, H, dur, cam_h)
                S.found = found
            st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")

if "video" in S:
    W, H, dur, p = S.W, S.H, S.dur, S.video
    st.caption(f"{p.name} · {W}x{H} · {dur/60:.1f} min · "
               + ("horizontal → pantalla dividida" if W > H else "vertical → se usa tal cual"))

    st.pills("Receta rápida", ["Streams de gaming", "Vídeos largos", "Subtítulos", "Reencuadre"],
             default="Streams de gaming", key="preset", on_change=apply_preset)

    tab_ctrl, tab_prev = st.tabs(["⚙️ Controles", "👁️ Vista previa"])
    o = {"cam_top": True, "fit": False, "subs": True}
    with tab_ctrl:
        with st.container(border=True):
            st.markdown("**Encuadre de la facecam**")
            if W > H:
                estilo = st.segmented_control("Estilo", ["Facecam flotante", "Pantalla dividida"],
                                              default="Facecam flotante", key="layout_style")
                o["layout"] = "overlay" if estilo == "Facecam flotante" else "split"
                c1, c2 = st.columns(2)
                if o["layout"] == "split":
                    o["cam_top"] = c1.selectbox("Posición", ["Streamer arriba, juego abajo", "Juego arriba, streamer abajo"], key="pos") \
                        .startswith("Streamer")
                else:
                    o["cam_top"] = True
                    c1.caption("Juego a pantalla completa")
                o["fit"] = c2.checkbox("Fondo borroso", key="fit")
                o["share"] = st.slider("Tamaño de la facecam (%)", 30, 70, key="share")
                if not S.get("found"): st.caption("Cara no detectada: ajusta el recuadro.")
                o["cw"] = st.slider("Ancho facecam (%)", 5, 100, int(min(max(S.cw, 5), 100)), key="cw")
                o["cx"] = st.slider("Posición X (%)", 0.0, 100.0, float(min(S.cx, 100)), key="cx")
                o["cy"] = st.slider("Posición Y (%)", 0.0, 100.0, float(min(S.cy, 100)), key="cy")
                cam_h = int(1920 * o["share"] / 100) // 2 * 2
            else:
                o.update(share=45, cx=0, cy=0, cw=100, layout="none")
                cam_h = 1400
                st.caption("Video vertical: no necesita pantalla dividida.")
        with st.container(border=True):
            st.markdown("**Clips**")
            mode = st.segmented_control("Modo", ["Por duración fija", "Automático", "Video completo", "Partes iguales", "Personalizado"],
                                        default="Por duración fija", key="mode")
            clip_len, n, start_s, custom_s, fast = 60, 3, 0.0, min(30.0, dur), False
            if mode == "Por duración fija":
                clip_len = st.selectbox("Duración de cada clip", [30, 60, 90, 120], index=1, key="clip_len")
                st.caption(f"Se generarán **{max(int(dur // clip_len), 1)} clips** de {clip_len} s (el último puede ser más corto).")
            if mode == "Automático":
                a, b = st.columns(2)
                clip_len = a.selectbox("Duración", [30, 45, 60, 90, 120], index=2, key="clip_len")
                n = b.number_input("Cantidad", 1, 20, 3, key="nclips")
                fast = st.checkbox("Modo rápido (solo transcribe los clips)", value=True, key="fast_mode")
                st.caption("Con 2 CPUs, transcribir 24 min tarda ~50 min. El modo rápido elige por audio y transcribe solo los clips.")
            elif mode == "Partes iguales":
                n = st.number_input("Cantidad de partes", 1, 20, 3, key="nclips")
                st.caption(f"Cada parte: {dur / n / 60:.2f} min")
            elif mode == "Personalizado":
                a, b = st.columns(2)
                start_s = a.number_input("Inicio (s)", 0.0, float(dur), 0.0, key="start_s")
                custom_s = b.number_input("Duración (s)", 1.0, float(dur), min(30.0, dur), key="custom_s")
            expres = st.checkbox("Modo exprés (sin transcripción, mucho más rápido)",
                                 value=False, key="expres")
            o["subs"] = st.checkbox("Subtítulos animados", value=bool(S.get("subs", True)),
                                    key="subs", disabled=expres)
            if expres:
                o["subs"] = False
            with st.expander("Transcripción"):
                model = st.selectbox("Modelo Whisper", ["tiny", "base", "small", "medium"], index=0, key="model")
                lang = st.selectbox("Idioma", ["es", "en", "auto"], key="lang")
                gpu = st.checkbox("Usar GPU NVIDIA", key="gpu")
                st.caption("`tiny` es mucho más rápido en CPU. La transcripción se guarda en caché: la segunda vez es instantánea.")
            if st.button("Analizar", icon=":material/analytics:", key="analyze", width="stretch"):
                try:
                    with st.status("Analizando...", expanded=True) as stt:
                        st.write("Extrayendo audio...")
                        S.wav = extract_audio(p)
                        st.write("Transcribiendo (puede tardar varios minutos en CPU)...")
                        S.words = load_transcript(p, S.wav, model, lang, gpu)
                        S.curve, S.cs = interest_curve(S.wav, S.words, S.dur)
                        S.wmodel = (model, lang)
                        stt.update(label="Análisis listo", state="complete")
                except Exception as e:
                    st.error(f"Error: {e}")
            if st.button("Generar clips", type="primary", icon=":material/movie:", key="generate", width="stretch"):
                try:
                    t0 = time.perf_counter()
                    with st.status("Generando...", expanded=True) as stt:
                        bar = st.progress(0.0, text="Preparando...")
                        use_fast = (expres or mode in ("Por duración fija", "Partes iguales", "Personalizado")
                                    or bool(fast and mode == "Automático"))
                        if S.get("wav") is None:
                            bar.progress(0.02, text="Extrayendo audio...")
                            S.wav = extract_audio(p)
                        if use_fast:
                            st.write("Modo rápido: analizando energía del audio (sin transcripción completa)...")
                            S.curve, S.cs = interest_curve(S.wav, [], S.dur)
                        else:
                            if S.get("words") is None or S.get("wmodel") != (model, lang):
                                bar.progress(0.05, text="Transcribiendo (puede tardar varios minutos en CPU)...")
                                st.write("Transcribiendo audio...")
                                S.words = load_transcript(p, S.wav, model, lang, gpu)
                                S.wmodel = (model, lang)
                                st.write(f"Análisis completado en {time.perf_counter() - t0:.0f} s")
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
                            bar.progress(0.10 + 0.85 * (i - 1) / total,
                                         text=f"Clip {i} de {total}...")
                            out = OUT / f"{p.stem}_clip{i}.mp4"
                            if same_settings and out.exists() and out.stat().st_size > 1024:
                                reused += 1
                                st.write(f"Clip {i}: reutilizando archivo ya generado.")
                            else:
                                if use_fast and o["subs"]:
                                    st.write(f"Transcribiendo clip {i}...")
                                    words_i = transcribe_clip(p, s0, d0, model, lang, gpu)
                                else:
                                    words_i = S.words or []
                                render(p, s0, d0, words_i, out, W, H, o)
                            S.results.append((out, s0, score))
                            elapsed = time.perf_counter() - t_render
                            eta = (elapsed / i) * (total - i)
                            bar.progress(0.10 + 0.85 * i / total,
                                         text=f"Clip {i}/{total} · {elapsed:.0f}s transcurridos · ~{eta:.0f}s restantes")
                        save_manifest(p, W, H, dur, o, S.results, fp)
                        bar.progress(1.0, text=f"Listo: {total} clips en {time.perf_counter() - t_render:.0f} s"
                                     + (f" · {reused} reutilizados" if reused else ""))
                        stt.update(label=f"¡Listo! {total} clips", state="complete")
                except Exception as e:
                    st.error(f"Error: {e}")
    with tab_prev:
        with st.container(border=True):
            st.markdown("**Vista previa**")
            fr = frame_at(p, dur / 2)
            if fr is not None:
                if W > H and o.get("layout") == "overlay":
                    fw = int(W * o["cw"] / 100) // 2 * 2
                    fx = min(max(int(W * o["cx"] / 100), 0), W - fw)
                    fy = min(max(int(H * o["cy"] / 100), 0), H - fw)
                    cv2.circle(fr, (fx + fw // 2, fy + fw // 2), fw // 2, (0, 255, 0), max(3, W // 300))
                elif W > H:
                    x, y, w, h = cam_rect(W, H, o["cx"], o["cy"], o["cw"], cam_h)
                    cv2.rectangle(fr, (x, y), (x + w, y + h), (0, 255, 0), max(3, W // 300))
                st.image(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB),
                         caption="Círculo verde = facecam" if W > H and o.get("layout") == "overlay"
                         else ("Recuadro verde = facecam" if W > H else "Video vertical"),
                         alt="Vista previa del encuadre", width="stretch")
            if S.get("curve") is not None:
                k1, k2, k3 = st.columns(3)
                k1.metric("Duración", f"{int(dur) // 60}:{int(dur) % 60:02d}")
                k2.metric("Palabras", len(S.words or []))
                k3.metric("Resolución", f"{W}x{H}")
                st.line_chart({"Interés": S.curve.tolist()}, height=160,
                              alt="Interés por segundo a lo largo del video")

    if S.get("results"):
        st.subheader(f"Clips generados · {len(S.results)}")
        st.caption("Los clips quedan en `salida/`. Si recargas la página, usa **Recuperar trabajo guardado**.")
        grid = st.columns(3)
        for i, (out, s0, score) in enumerate(S.results, 1):
            with grid[(i - 1) % 3].container(border=True):
                fr = frame_at(out, 1)
                if fr is not None:
                    st.image(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB), alt=f"Miniatura del clip {i}", width="stretch")
                label = (f"**{i} · {int(s0 // 60):02d}:{int(s0 % 60):02d}**"
                         if s0 is not None else f"**Clip {i}**")
                st.markdown(label)
                st.caption(f"Interés {score:+.1f}" if score else "Clip personalizado")
                # Pass the bound read_bytes callable: Streamlit reads the file only on click,
                # instead of loading every clip into RAM on each rerun.
                st.download_button("Descargar", out.read_bytes, out.name, "video/mp4",
                                   key=f"dl_{i}_{out.name}", icon=":material/download:", width="stretch")
                with st.expander("Vista previa"):
                    st.video(str(out), alt=f"Vista previa del clip {i}")
