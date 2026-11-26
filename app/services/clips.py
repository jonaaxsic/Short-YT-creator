"""Planificación, subtítulos y render de clips."""
import subprocess
from pathlib import Path
import cv2, numpy as np
from .. import config as cfg
from .video import cam_rect

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
    p = cfg.WORK / f"_mask_{size}.png"
    if not p.exists():
        img = np.zeros((size, size), np.uint8)
        cv2.circle(img, (size // 2, size // 2), size // 2, 255, -1, lineType=cv2.LINE_AA)
        cv2.imwrite(str(p), img)
    return p


def render(video, start, dur, words, out, W, H, o, on_process=None):
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
        make_ass(words, start, dur, seam, cfg.WORK / ass)
        fc += f";[s]ass={ass}[v]"
    else:
        fc += ";[s]null[v]"
    cmd = [cfg.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(dur), "-i", str(video), *extra_inputs, "-filter_complex", fc,
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, cwd=cfg.WORK, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True)
    if on_process is not None:
        on_process(proc)
    _, err = proc.communicate()
    if proc.returncode:
        raise RuntimeError(err[-1500:])
