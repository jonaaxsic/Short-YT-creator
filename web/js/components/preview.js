/** Reproductor de la muestra ligera del video fuente. */
import { state } from "../state.js";

export function mountPreview() {
  const box = document.querySelector(".preview-box");
  const video = document.querySelector("#preview-video");

  document.addEventListener("video-loaded", async () => {
    try {
      const info = await fetch("/api/state").then((r) => r.json());
      if (!info.video) return;
      video.src = `/video/source?t=${Date.now()}`;
      box.classList.add("ready");
      video.load();
    } catch {
      box.classList.remove("ready");
    }
  });

  video.addEventListener("error", () => box.classList.remove("ready"));
  if (!state.video) box.classList.remove("ready");
}
