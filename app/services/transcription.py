"""Audio, transcripción, caché y selección de momentos."""
import functools, json, subprocess, wave
from pathlib import Path
import numpy as np
from .. import config as cfg

# ---------- audio, transcripción, selección de clips ----------
def extract_audio(video):
    wav = cfg.WORK / (video.stem + ".wav")
    subprocess.run([cfg.FFMPEG, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True, capture_output=True)
    return wav


@functools.lru_cache(maxsize=2)
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
    cache = cfg.WORK / f"{video.stem}_t{int(start)}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    seg_wav = cfg.WORK / f"_seg_{video.stem}_{int(start)}.wav"
    subprocess.run([cfg.FFMPEG, "-y", "-ss", str(start), "-t", str(dur), "-i", str(video),
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
    """Per-second attention score, reading one second at a time to bound RAM."""
    with wave.open(str(wav)) as wf:
        sr = wf.getframerate()
        secs = max(int(wf.getnframes() / sr), 1)
        rms = np.zeros(secs, dtype=np.float32)
        for i in range(secs):
            block = wf.readframes(sr)
            if not block:
                break
            samples = np.frombuffer(block, dtype=np.int16).astype(np.float32)
            rms[i] = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
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
    cache = cfg.WORK / f"{video.stem}.{model}.{lang}.json"
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


def translate_words(words, target="es"):
    """Traduce el texto de las palabras al idioma destino, con fallback al original."""
    unique = list(dict.fromkeys(w["text"] for w in words if w.get("text")))
    if not unique:
        return words
    mapping = {}
    try:
        import requests
        for i in range(0, len(unique), 60):
            chunk = unique[i:i + 60]
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t",
                        "q": " | ".join(chunk)}, timeout=8)
            segments = [item[0] for item in response.json()[0] if item and item[0]]
            parts = [part.strip() for part in "".join(segments).split("|")]
            if len(parts) == len(chunk):
                for source, translated in zip(chunk, parts):
                    mapping[source] = translated
    except Exception:
        return words
    return [dict(w, text=mapping.get(w.get("text"), w.get("text", ""))) for w in words]


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
