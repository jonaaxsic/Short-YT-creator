/** Única fuente de verdad del frontend, con ajustes persistidos en localStorage. */
const listeners = new Set();
const KEY = "shorts-settings";

function stored() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

const saved = stored();

export const state = {
  src: "url",
  video: null,
  job: null,
  settings: {
    mode: "Por duración fija", clip_len: 2, subs: true,
    fast: false, gpu: false, model: "tiny", lang: "auto", translate: false, track_face: true,
    layout: "overlay", share: 45, cx: 0, cy: 60, cw: 28,
    start_s: 0, end_s: 0,
    ...(saved.settings || {}),
    mode: "Por duración fija"
  }
};

export function subscribe(listener) {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

export function update(patch) {
  Object.assign(state, patch);
  try {
    localStorage.setItem(KEY, JSON.stringify({ settings: state.settings }));
  } catch {
    /* almacenamiento bloqueado: la app sigue funcionando */
  }
  for (const listener of listeners) listener(state);
}
