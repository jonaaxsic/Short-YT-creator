---
title: Short-YT-creator
emoji: 🎬
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Short YT Creator

Standalone web frontend for turning a long video into vertical 9:16 clips. The browser owns navigation, theme and all instant interactions; Python only exposes the heavy work (download, transcription, ffmpeg rendering) as an HTTP API. This removes Streamlit reruns entirely.

## Quick path

1. Double-click `iniciar.bat`, or run `python -m app 8502`.
2. Open `http://localhost:8502`.
3. Paste a YouTube URL, choose the download quality and press **Cargar video**.
4. Adjust the facecam frame while watching the playable preview, then press **Generar Short**.
5. Play each clip card or download the original file from the results grid.

## Layout

| Area | Responsibility |
|------|----------------|
| `web/index.html` | Semantic structure only. No logic, no styling. |
| `web/css/tokens.css` | Colors, spacing, radius and light/dark tokens. |
| `web/css/app.css` | Layout and components. Reads tokens, never hardcodes colors. |
| `web/js/state.js` | Single source of truth with a tiny pub/sub. |
| `web/js/api.js` | Fetch wrappers. The only place that knows endpoint paths. |
| `web/js/router.js` | View switching without reloads. |
| `web/js/theme.js` | `color-scheme` + `localStorage`; no page reload. |
| `web/js/components/` | One module per feature: source, preview, facecam, clips, results, projects, settings. |
| `app/main.py` | Starts the single HTTP server. |
| `app/api/` | `routes.py` translates requests; `jobs.py` runs generation in background. |
| `app/services/` | Domain logic with no HTTP knowledge: video, transcription, clips, storage. |
| `app/config.py` | Paths, quality map and persisted settings. |
| `app/state.py` | In-memory current video, results and jobs. |

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/state` | Current video metadata and clip count. |
| `GET /api/settings`, `POST /api/settings` | Output folder, temporary folder, source cleanup. |
| `GET /api/projects`, `POST /api/restore` | List saved clip groups and restore one. |
| `POST /api/load`, `POST /api/upload` | Load by URL/path or upload a file. |
| `POST /api/generate`, `GET /api/job?id=` | Start generation and poll progress. |
| `GET /video/source`, `/video/preview`, `/video/clip` | Range-enabled media streaming. |

## Deploy

`Dockerfile` is single-stage: installs `requirements.txt`, copies `app` and `web`, and runs `python -m app 7860` with `HOST=0.0.0.0`. No Node, no build step, no frontend dependencies.

Clip modes are **Por duración fija** (choose 1–4 minutes, the app proposes how many clips fit the video), **Automático** (2-minute clips based on duration) and **Partes iguales** (equal parts of 1–4 minutes). The estimate appears before generating. While a job runs, **Cancelar generación** stops it so settings can be changed and the job restarted.

For speed, enable **expres** mode: it skips Whisper transcription and subtitles. Transcripts are cached and existing clips are reused when settings do not change. Audio analysis reads one second at a time and ffmpeg output is suppressed, keeping RAM use bounded on 2-core machines. The preview streams the original file with HTTP range requests instead of loading it into memory.

## Checklist

- [ ] `iniciar.bat` opens a visible console with logs and starts a clean server.
- [ ] After 10 minutes idle the service pauses; the page shows **Reactivar servicio** and the console logs the reason.
- [ ] Configuración reports temporary cache size and can clear it without touching clips or source videos.
- [ ] Navigation and theme never reload the page.
- [ ] Both themes keep text contrast readable and hover states visible.
- [ ] Clips are generated in a background job with progress.
- [ ] No push to git until explicitly requested.
