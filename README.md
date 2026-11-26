---
title: Short-YT-creator
emoji: 🎬
colorFrom: blue
colorTo: indigo
sdk: streamlit
app_file: app.py
pinned: false
---

# Short YT Creator

Turn a long video into vertical 9:16 clips with animated subtitles and an optional facecam overlay. The same code runs locally on Windows and as a free Hugging Face Space.

## Using the web app

1. Open the Space URL on your phone or computer.
2. Choose **Subir** and select a video (up to 2 GB). This is the recommended option on the free Space: YouTube frequently blocks downloads coming from cloud IPs, so **URL** mode may fail there.
3. Pick a recipe, adjust the facecam frame, choose a clip mode and press **Generar clips**.
4. Each clip card has an inline playable preview and a single **Descargar** button; no second button or popup window. The preview is a short 6-second sample at low resolution, cached on disk, so playing or rerunning the app never loads the full-size clips into memory. The first view builds those samples once with visible progress; **Descargar** always streams the original full-quality clip from disk.
5. If you reload the page, click **Recuperar trabajo guardado** to restore the source video and clips without reprocessing. Clips already on disk are reused when the settings are unchanged.

For speed, enable **Modo exprés**: it skips Whisper transcription and subtitles entirely. Otherwise uncheck **Subtítulos animados** to avoid per-clip transcription. Existing clips are never re-rendered unless settings change.

The heavy work (Whisper transcription and ffmpeg rendering) runs on the server. A free Space has a modest CPU and no GPU, so processing can take several minutes; the Space may also go to sleep after inactivity and need a moment to wake up on the next visit. Transcripts are cached in `work/` while the container lives.

## Running locally

Install Python and Node.js 22+, then double-click `iniciar.bat`. The app opens at `http://localhost:8501`. `LEEME.txt` has the short Spanish guide.

## Source layout

- `app.py` — Streamlit UI, transcription, clip selection and ffmpeg rendering.
- `requirements.txt` — Python dependencies.
- `.streamlit/config.toml` — upload limit and public-app UI settings.
- `work/`, `salida/` — runtime scratch and generated clips (not committed).

This Space is public. Anyone with the URL can use its CPU, so avoid uploading private material.
