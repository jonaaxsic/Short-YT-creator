/** Modo de clips: duración en minutos, rango personalizado y estimación previa. */
import { state } from "../state.js";

const label = document.querySelector("#clip-estimate");
const range = document.querySelector("#custom-range");
const startInput = document.querySelector("#start-min");
const endInput = document.querySelector("#end-min");

function clock(minutes) {
  const total = Math.round(minutes * 60);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function minutes() {
  return Number(document.querySelector("#clip-len").value);
}

function estimate() {
  const mode = state.settings.mode;
  const duration = Number(state.video?.dur || 0);
  const min = minutes();
  state.settings.clip_len = min;
  const lenLabel = document.querySelector("#clip-len-label");
  lenLabel.textContent = mode === "Automático" ? "Duración objetivo (min)"
    : mode === "Partes iguales" ? "Duración de cada parte (min)"
    : "Duración de cada clip (min)";

  if (!duration) {
    label.textContent = "Carga un video para calcular la cantidad de clips.";
    return;
  }
  const totalMin = duration / 60;
  let from = 0, to = totalMin;
  if (mode === "Personalizado") {
    from = Number(startInput.value);
    to = Number(endInput.value);
    state.settings.start_s = from * 60;
    state.settings.end_s = to * 60;
    if (!(from >= 0) || !(to > from) || to > totalMin) {
      label.textContent = `El rango debe ir desde 0 hasta ${clock(totalMin)} y terminar después de empezar.`;
      return;
    }
  }
  const count = Math.max(1, Math.ceil((to - from) / min));
  let message;
  if (mode === "Automático") {
    message = `Automático: se estiman hasta ${count} clips de ${min} min según la duración del video; el sistema elegirá los mejores momentos.`;
  } else if (mode === "Partes iguales") {
    message = `Se crearán ${count} clips de ${min} min en partes iguales; el último puede quedar más corto.`;
  } else if (mode === "Personalizado") {
    message = `Se crearán ${count} clips de ${min} min desde ${clock(from)} hasta ${clock(to)}.`;
  } else {
    message = `Se crearán ${count} clips de ${min} min según la duración del video.`;
  }
  label.textContent = message;
  label.classList.toggle("notice", mode === "Automático" || mode === "Partes iguales");
}

export function mountClips() {
  const select = document.querySelector("#clip-len");
  for (const option of document.querySelectorAll("#mode-seg [data-mode]")) {
    option.addEventListener("click", () => {
      state.settings.mode = option.dataset.mode;
      for (const el of document.querySelectorAll("#mode-seg [data-mode]"))
        el.classList.toggle("active", el === option);
      const custom = state.settings.mode === "Personalizado";
      range.classList.toggle("hidden", !custom);
      estimate();
    });
  }
  select.addEventListener("input", estimate);
  startInput.addEventListener("input", estimate);
  endInput.addEventListener("input", estimate);
  document.addEventListener("video-loaded", () => {
    const total = Number(state.video?.dur || 0) / 60;
    if (total) {
      startInput.max = String(Math.floor(total));
      endInput.max = String(Math.ceil(total));
      if (!state.settings.end_s) endInput.value = String(Math.floor(total));
    }
    estimate();
  });

  const bind = (id, key, read = (el) => el.value) => {
    const el = document.querySelector(`#${id}`);
    if (el) state.settings[key] = read(el);
    el?.addEventListener("input", () => { state.settings[key] = read(el); });
  };
  bind("subs", "subs", (el) => el.checked);
  bind("model", "model");
  bind("lang", "lang");
  bind("gpu", "gpu", (el) => el.checked);
  bind("translate", "translate", (el) => el.checked);
  bind("track_face", "track_face", (el) => el.checked);
  estimate();
}
