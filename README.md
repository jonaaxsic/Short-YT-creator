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
2. Choose **URL** and paste a YouTube link, or choose **Subir** and select a video (up to 2 GB). In URL mode pick the download quality (320p, 360p, 480p, 720p, 1080p or best available) before loading; it is fixed at download time and shown read-only in the preview. Uploaded files auto-detect their resolution. **Subir** is recommended on the free Space: YouTube often blocks downloads from cloud IPs.
3. Adjust the facecam frame while watching the live preview, choose a clip mode and press **Generar Short** in the bottom bar.
4. Each clip card has an inline playable preview and a single **Descargar** button; no second button or popup window. The preview is a short 6-second sample at low resolution, cached on disk, so playing or rerunning the app never loads the full-size clips into memory. **Descargar** always streams the original clip from disk.
5. If you reload the page, press **Restablecer** in the bottom bar to restore saved work. Clips already on disk are reused when the settings are unchanged.

The left menu opens **Mis Proyectos** (restore saved clip sets), **Configuración** (light/dark theme, output folder, temporary download folder, and optional source cleanup after generating) and **Acerca de**. The preview card plays a short cached sample of the source before any clip is rendered.

For speed, enable **Modo exprés**: it skips Whisper transcription and subtitles entirely. Otherwise uncheck **Subtítulos animados** to avoid per-clip transcription. Existing clips are never re-rendered unless settings change.

The heavy work (Whisper transcription and ffmpeg rendering) runs on the server. A free Space has a modest CPU and no GPU, so processing can take several minutes; the Space may also go to sleep after inactivity and need a moment to wake up on the next visit. Transcripts are cached in `work/` while the container lives.

## Running locally

Install Python and Node.js 22+, then double-click `iniciar.bat`. The app opens at `http://localhost:8501`. `LEEME.txt` has the short Spanish guide.

## Source layout

- `app.py` — Streamlit UI, transcription, clip selection and ffmpeg rendering.
- `ui.css` — compact dark workspace styling (sidebar, cards, controls and preview).
- `requirements.txt` — Python dependencies.
- `.streamlit/config.toml` — upload limit and public-app UI settings.
- `work/`, `salida/` — runtime scratch and generated clips (not committed).

This Space is public. Anyone with the URL can use its CPU, so avoid uploading private material.
