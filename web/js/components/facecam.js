/** Sliders del encuadre y superposición visual sobre el video. */
import { state } from "../state.js";

const IDS = ["share", "cw", "cx", "cy"];

export function mountFacecam() {
  const overlay = document.querySelector("#facecam-overlay");
  const face = overlay.querySelector(".cam-face");
  const rect = overlay.querySelector(".cam-rect");

  for (const style of document.querySelectorAll("#style-seg [data-style]")) {
    style.addEventListener("click", () => {
      state.settings.layout = style.dataset.style;
      for (const el of document.querySelectorAll("#style-seg [data-style]"))
        el.classList.toggle("active", el === style);
      paint();
    });
  }

  for (const id of IDS) {
    const slider = document.querySelector(`#${id}`);
    const output = slider.closest(".slider").querySelector("output");
    slider.style.setProperty("--attr-min", slider.min);
    slider.style.setProperty("--attr-max", slider.max);
    const sync = () => {
      slider.style.setProperty("--control-value", slider.value);
      const value = Number(slider.value);
      state.settings[id] = value;
      output.textContent = `${id === "cx" || id === "cy" ? value.toFixed(2) : value} %`;
      paint();
    };
    slider.addEventListener("input", sync);
    sync();
  }

  document.addEventListener("video-loaded", paint);

  function paint() {
    const { cx, cy, cw, share } = state.settings;
    const horizontal = Boolean(state.video && state.video.W > state.video.H);
    // El lado del cuadrado responde a "Ancho" y a "Tamaño" para que ambos sliders
    // tengan efecto visible sin dejar de ser un cuadrado.
    const side = Math.max(6, Math.min(100, cw * (share / 45)));
    const left = Math.max(0, Math.min(100 - side, cx));
    const top = Math.max(0, Math.min(100 - side, cy));
    face.style.display = horizontal ? "block" : "none";
    rect.style.display = "none";
    face.style.left = `${left}%`;
    face.style.top = `${top}%`;
    face.style.width = `${side}%`;
    face.style.height = "auto";
    face.style.aspectRatio = "1";
  }
}
