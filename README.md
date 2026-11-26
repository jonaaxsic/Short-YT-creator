---
title: Short-YT-creator
emoji: 🎬
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

<div align="center">

# 🎬 Short YT Creator

**Turn a long video into vertical 9:16 clips with a facecam overlay — fast, lightweight, and without framework bloat.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![CSS](https://img.shields.io/badge/CSS-variables-1572B6?logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-ES_modules-F7DF1E?logo=javascript&logoColor=black)
![HTML5](https://img.shields.io/badge/HTML5-semantic-E34F26?logo=html5&logoColor=white)
![Vanilla JS](https://img.shields.io/badge/Framework-none-6c757d)
![Server](https://img.shields.io/badge/Server-Python_stdlib-3776AB)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

</div>

## See it in action

<img src="docs/screenshots/01-editor.png" width="720" alt="Editor listo para cargar un video">

<img src="docs/screenshots/02-preview.png" width="720" alt="Video cargado con el recuadro de la facecam">

<img src="docs/screenshots/03-generando.png" width="720" alt="Generación de clips con barra de progreso">

<img src="docs/screenshots/04-clips-generados.png" width="720" alt="Clip generado listo para reproducir o descargar">

## How to use

1. Paste a YouTube URL or choose **Subir**, pick the download quality, then press **Cargar video**.
2. Move the sliders to place the facecam square while watching the preview.
3. Choose a clip mode and duration (1–4 minutes), then press **Generar Short**.
4. Play or download each clip from the results grid.

## Run it

On Windows, double-click **`iniciar.bat`**. It installs dependencies on first run, starts the server, opens the browser at `http://localhost:8502`, and leaves a visible console with logs.

To stop it, close the console window. After 10 minutes without activity the service pauses and the page offers a **Reactivar servicio** button.
