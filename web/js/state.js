/** Única fuente de verdad del frontend y suscripción ligera. */
const listeners = new Set();

export const state = {
  src: "url",
  video: null,
  job: null,
  settings: {
    mode: "Por duración fija", clip_len: 2, subs: true,
    fast: false, gpu: false, model: "tiny", lang: "es",
    layout: "overlay", share: 45, cx: 0, cy: 60, cw: 28
  }
};

export function subscribe(listener) {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

export function update(patch) {
  Object.assign(state, patch);
  for (const listener of listeners) listener(state);
}
