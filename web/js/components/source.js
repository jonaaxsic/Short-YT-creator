/** Origen del video: URL, ruta local o archivo, con progreso y cancelación. */
import { api } from "../api.js";
import { state, update } from "../state.js";

const PLACEHOLDERS = {
  url: "Pega aquí el enlace de YouTube...",
  path: "C:\\Videos\\stream.mp4"
};

export function mountSource() {
  const text = document.querySelector("#source-input");
  const file = document.querySelector("#file-input");
  const quality = document.querySelector("#quality");
  const button = document.querySelector("#load-btn");
  const message = document.querySelector("#load-msg");
  const progressBox = document.querySelector("#load-progress");
  const fill = document.querySelector("#load-bar-fill");
  const progressText = document.querySelector("#load-progress-text");
  const cancelLoad = document.querySelector("#cancel-load-btn");
  let timer = null;

  for (const option of document.querySelectorAll("#src-seg [data-src]")) {
    option.addEventListener("click", () => {
      const src = option.dataset.src;
      update({ src });
      for (const el of document.querySelectorAll("#src-seg [data-src]"))
        el.classList.toggle("active", el === option);
      text.classList.toggle("hidden", src === "upload");
      file.classList.toggle("hidden", src !== "upload");
      quality.disabled = src !== "url";
      text.placeholder = PLACEHOLDERS[src] || "";
    });
  }

  async function poll() {
    try {
      const info = await api.loadProgress();
      if (!info.active) return;
      fill.style.width = `${info.percent}%`;
      progressText.textContent = info.message;
    } catch {
      /* una lectura fallida no debe romper la carga */
    }
  }

  cancelLoad.addEventListener("click", async () => {
    await api.cancelLoad();
    progressText.textContent = "Cancelando...";
  });

  button.addEventListener("click", async () => {
    message.textContent = "";
    button.disabled = true;
    progressBox.classList.remove("hidden");
    fill.style.width = "0%";
    progressText.textContent = "Preparando...";
    timer = setInterval(poll, 400);
    try {
      let data;
      if (state.src === "url") data = await api.load("url", text.value.trim(), quality.value);
      else if (state.src === "path") data = await api.load("path", text.value.trim());
      else if (file.files[0]) {
        const uploaded = await api.upload(file.files[0]);
        data = await api.load("path", uploaded.path);
      } else throw new Error("Selecciona un archivo para continuar.");
      update({ video: data });
      message.textContent = `${data.name} · ${data.quality}`;
      document.dispatchEvent(new Event("video-loaded"));
    } catch (error) {
      message.textContent = error.message;
    } finally {
      clearInterval(timer);
      timer = null;
      progressBox.classList.add("hidden");
      button.disabled = false;
    }
  });
}
