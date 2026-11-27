"""Ejecución en segundo plano y progreso de generación."""
import math, time
from pathlib import Path
from .. import config, state
from ..services import transcription as tr, clips as cl, storage as st, video as vid


def job_update(job_id, progress, message):
    state.JOBS[job_id] = {"progress": progress, "message": message, "done": False}


def generate(job_id, s):
    try:
        p = Path(state.STATE["video"])
        W, H, dur = state.STATE["W"], state.STATE["H"], state.STATE["dur"]
        job_update(job_id, 0.02, "Extrayendo audio...")
        wav = tr.extract_audio(p)
        mode = s.get("mode", "Por duración fija")
        fast_mode = s.get("fast", False)
        use_fast = bool(s.get("expres") or fast_mode or
                        mode in ("Por duración fija", "Partes iguales", "Personalizado"))
        if use_fast:
            curve, cs = tr.interest_curve(wav, [], dur)
        else:
            model, lang, gpu = s.get("model", "tiny"), s.get("lang", "es"), s.get("gpu", False)
            words = tr.load_transcript(p, wav, model, lang, gpu)
            curve, cs = tr.interest_curve(wav, words, dur)
        state.STATE["curve"] = curve
        job_update(job_id, 0.10, "Buscando los mejores momentos...")
        clip_len = int(s.get("clip_len", 60))
        n = int(s.get("n", 3))
        if mode == "Automático":
            clips = tr.pick_clips(wav, [], dur, clip_len, n, cs)
        elif mode == "Personalizado":
            start = max(0.0, float(s.get("start_s", 0)))
            end = min(float(s.get("end_s", dur)), dur)
            if end <= start:
                raise ValueError("El rango personalizado termina antes de empezar.")
            clips = []
            t = start
            while t < end - 1:
                clips.append((t, min(float(clip_len), end - t), 0.0))
                t += clip_len
        else:
            if mode == "Partes iguales":
                n = max(1, math.ceil(dur / clip_len))
            clips = cl.plan_clips(dur, mode, n, float(s.get("start_s", 0)),
                                    float(s.get("custom_s", 30)), clip_len)
        total = max(len(clips), 1)
        o = {"layout": s.get("layout", "overlay"), "cam_top": bool(s.get("cam_top", True)),
             "fit": bool(s.get("fit", False)), "subs": bool(s.get("subs", True)) and not s.get("expres"),
             "share": int(s.get("share", 45)), "cx": float(s.get("cx", 0)),
             "cy": float(s.get("cy", 60)), "cw": int(s.get("cw", 28))}
        model, lang, gpu = s.get("model", "tiny"), s.get("lang", "es"), s.get("gpu", False)
        fp = st.settings_fp(o, mode, clip_len, n, float(s.get("start_s", 0)),
                              float(s.get("custom_s", 30)), model, lang)
        old = st.read_manifest()
        same = bool(old and old[0].get("fp") == fp)
        results = []
        t0 = time.perf_counter()
        for i, (s0, d0, score) in enumerate(clips, 1):
            if job_id in state.CANCELLED:
                state.CANCELLED.discard(job_id)
                state.PROCESSES.pop(job_id, None)
                state.JOBS[job_id] = {"done": True, "cancelled": True,
                                      "progress": 0, "message": "Generación cancelada"}
                return
            job_update(job_id, 0.10 + 0.85 * (i - 1) / total, f"Clip {i} de {total}...")
            out = config.OUT / f"{p.stem}_clip{i}.mp4"
            if same and out.exists() and out.stat().st_size > 1024:
                pass
            else:
                words_i = (tr.transcribe_clip(p, s0, d0, model, lang, gpu)
                           if use_fast and o["subs"] else [])
                if words_i and s.get("translate"):
                    words_i = tr.translate_words(words_i)
                clip_o = o
                if W > H and s.get("track_face", True):
                    detected = vid.detect_cam_range(
                        p, W, H, s0, d0, int(1920 * o["share"] / 100) // 2 * 2)
                    if detected:
                        clip_o = dict(o, cx=detected[0], cy=detected[1], cw=detected[2])
                try:
                    cl.render(p, s0, d0, words_i, out, W, H, clip_o,
                              on_process=lambda proc: state.PROCESSES.__setitem__(job_id, proc))
                except Exception:
                    state.PROCESSES.pop(job_id, None)
                    if job_id in state.CANCELLED:
                        state.CANCELLED.discard(job_id)
                        out.unlink(missing_ok=True)
                        state.JOBS[job_id] = {"done": True, "cancelled": True,
                                              "progress": 0, "message": "Generación cancelada"}
                        return
                    raise
            results.append((out, s0, score))
            vid.clip_preview(out)
            elapsed = time.perf_counter() - t0
            job_update(job_id, 0.10 + 0.85 * i / total,
                       f"Clip {i}/{total} · {elapsed:.0f}s")
        st.save_manifest(p, W, H, dur, o, results, fp, state.STATE["quality"])
        state.STATE["results"] = results
        cfg = config.load_cfg()
        if cfg.get("cleanup_source"):
            try: p.unlink(missing_ok=True)
            except Exception: pass
        job_update(job_id, 1.0, f"Listo: {total} clips")
        state.PROCESSES.pop(job_id, None)
        state.JOBS[job_id]["done"] = True
    except Exception as exc:
        state.JOBS[job_id] = {"done": True, "error": str(exc), "progress": 1, "message": "Error"}
