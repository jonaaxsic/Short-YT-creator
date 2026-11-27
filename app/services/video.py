"""Descarga, lectura y muestras ligeras de video."""
import contextlib, io, shutil, subprocess
from pathlib import Path
import cv2, numpy as np, yt_dlp
from .. import config as cfg

# ---------- utilidades de video ----------
def download(url, max_h=1080, on_progress=None, should_cancel=None):
    height = int(max_h) if max_h else 99999
    tag = f"q{height}" if max_h else "qbest"
    fmt = f"bv*[height<={height}]+ba/b[height<={height}]/b"

    def hook(info):
        if should_cancel and should_cancel():
            raise yt_dlp.DownloadError("La descarga fue cancelada por el usuario.")
        if on_progress:
            on_progress(info)

    opts = {"format": fmt, "merge_output_format": "mp4",
            "outtmpl": str(cfg.WORK / f"%(id)s_{tag}.%(ext)s"), "ffmpeg_location": cfg.FFMPEG,
            "noplaylist": True, "quiet": False, "no_warnings": True,
            "noprogress": False, "nooverwrites": True,
            "progress_hooks": [hook],
            # YouTube requires solving JS challenges; use Node only when it is installed
            # (Node 22+). Cloud images such as Hugging Face Spaces have no Node by default.
            "js_runtimes": {"node": {}} if shutil.which("node") else {}}
    with yt_dlp.YoutubeDL(opts) as y:
        with contextlib.redirect_stdout(io.StringIO()):
            info = y.extract_info(url, download=True)
        p = Path(y.prepare_filename(info))
    if not p.exists():
        p = p.with_suffix(".mp4")
    base = p.name.split(f"_{tag}")[0]
    for old in cfg.WORK.glob(f"{base}_q*"):
        if old != p:
            old.unlink(missing_ok=True)
    return p


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
    return cfg.WORK / f"_preview_{clip.stem}.mp4"


def clip_preview(clip):
    """Short low-res sample: st.video loads entire files into RAM, so never feed it a full clip."""
    p = preview_path(clip)
    if not p.exists() or p.stat().st_mtime < clip.stat().st_mtime:
        r = subprocess.run(
            [cfg.FFMPEG, "-y", "-ss", "2", "-i", str(clip), "-t", "6", "-vf", "scale=200:-2",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34",
             "-c:a", "aac", "-b:a", "48k", "-threads", "1",
             "-movflags", "+faststart", str(p)],
            capture_output=True)
        if r.returncode or not p.exists() or p.stat().st_size < 1024:
            return None
    return p


def source_preview(video):
    """Short low-res sample of the source, cached; playable without loading the whole file."""
    p = cfg.WORK / f"_srcpreview_{video.stem}.mp4"
    if not p.exists() or p.stat().st_mtime < video.stat().st_mtime:
        r = subprocess.run(
            [cfg.FFMPEG, "-y", "-ss", "0", "-i", str(video), "-t", "10", "-vf", "scale=-2:360",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
             "-c:a", "aac", "-b:a", "64k", "-threads", "1",
             "-movflags", "+faststart", str(p)], capture_output=True)
        if r.returncode or not p.exists() or p.stat().st_size < 1024:
            return None
    return p


def clip_thumb(clip, t=1.0, max_h=720):
    """Cached frame: decoding video on each rerun is expensive."""
    p = cfg.WORK / f"_thumb_{clip.stem}_{int(t)}_{max_h}.jpg"
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


def detect_cam_range(p, W, H, start, dur, cam_h):
    """Estima el recuadro del streamer dentro de un clip, muestreando varios fotogramas."""
    try:
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cas.empty():
            return None
        boxes = []
        for k in range(6):
            frame = frame_at(p, start + dur * (k + 0.5) / 6)
            if frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = [b for b in cas.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
                     if b[2] < W * 0.25]
            if faces:
                boxes.append(min(faces, key=lambda b: b[2]))
        if not boxes:
            return None
        x, y, w, h = np.median(np.array(boxes), axis=0)
        cw_px = w * 3.0
        cx = (x + w / 2 - cw_px / 2) / W * 100
        cy = (y + h / 2 - (cw_px * cam_h / 1080) / 2) / H * 100
        return float(max(cx, 0)), float(max(cy, 0)), float(max(5, cw_px / W * 100))
    except Exception:
        return None


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
