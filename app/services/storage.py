"""Persistencia del manifiesto y escaneo de clips en disco."""
import hashlib, json, re
from pathlib import Path
from .. import config as cfg
from .video import vinfo

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
        cfg.MANIFEST.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def read_manifest():
    try:
        d = json.loads(cfg.MANIFEST.read_text(encoding="utf-8"))
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
    for f in cfg.OUT.glob("*.mp4"):
        m = re.match(r"^(.*)_clip(\d+)\.mp4$", f.name)
        if m and f.stat().st_size > 1024:
            groups.setdefault(m.group(1), []).append((int(m.group(2)), f))
    if not groups:
        return None
    stem, items = max(groups.items(), key=lambda kv: len(kv[1]))
    items.sort()
    video = next((cfg.WORK / (stem + ext) for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi")
                  if (cfg.WORK / (stem + ext)).exists()), None)
    if video is None:
        return None
    W, H, dur = vinfo(video)
    return ({"W": W, "H": H, "dur": dur, "options": {}}, video,
            [(f, None, None) for _, f in items])
