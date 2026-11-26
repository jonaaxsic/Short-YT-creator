"""Rutas, calidad de descarga y ajustes persistentes."""
import json, os, shutil
from pathlib import Path
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config.json"
WEB = ROOT / "web"
FFMPEG = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
WORK = (ROOT / "work").resolve(); WORK.mkdir(exist_ok=True)
OUT = (ROOT / "salida").resolve(); OUT.mkdir(exist_ok=True)
MANIFEST = OUT / ".manifest.json"
QUALITY = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360,
           "320p": 320, "best": None}
DEFAULTS = {"theme": "dark", "out_dir": str(OUT), "work_dir": str(WORK),
            "cleanup_source": False}


def load_cfg():
    try:
        return {**DEFAULTS, **json.loads(CFG.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULTS)


def save_cfg(cfg):
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_dirs(cfg):
    global WORK, OUT, MANIFEST
    for key, name in (("out_dir", "OUT"), ("work_dir", "WORK")):
        p = Path(cfg.get(key, "")).expanduser()
        if str(p) in ("", "."):
            continue
        try:
            p.mkdir(parents=True, exist_ok=True)
            globals()[name] = p.resolve()
        except Exception:
            pass
    MANIFEST = OUT / ".manifest.json"
