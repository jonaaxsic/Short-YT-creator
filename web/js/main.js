/** Arranque de la interfaz: monta componentes y sondea el trabajo en curso. */
import { api } from "./api.js";
import { state, update } from "./state.js";
import { mountRouter } from "./router.js";
import { mountTheme } from "./theme.js";
import { mountSource } from "./components/source.js";
import { mountPreview } from "./components/preview.js";
import { mountFacecam } from "./components/facecam.js";
import { mountClips } from "./components/clips.js";
import { renderResults } from "./components/results.js";
import { mountProjects } from "./components/projects.js";
import { mountSettings } from "./components/settings.js";

async function watchJob(id, message, bar) {
  for (;;) {
    const job = await api.job(id);
    message.textContent = `${job.message} (${Math.round(job.progress * 100)}%)`;
    bar.style.width = `${Math.round(job.progress * 100)}%`;
    if (job.done) {
      if (job.cancelled) message.textContent = "Generación cancelada. Ajusta lo necesario y vuelve a generar.";
      else if (job.error) message.textContent = job.error;
      else {
        await renderResults();
        document.querySelector('[data-view="crear"] .btn.primary')?.blur();
      }
      update({ job: null });
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
}

function mountGenerate() {
  const button = document.querySelector("#generate-btn");
  const cancel = document.querySelector("#cancel-btn");
  const message = document.querySelector("#job-msg");
  const progress = document.querySelector("#job-progress");
  const bar = document.querySelector("#job-bar");
  button.addEventListener("click", async () => {
    button.disabled = true;
    cancel.classList.remove("hidden");
    progress.classList.remove("hidden");
    bar.style.width = "0%";
    message.textContent = "Preparando...";
    try {
      const job = await api.generate({ ...state.settings, clip_len: state.settings.clip_len * 60 });
      update({ job });
      await watchJob(job.id, message, bar);
    } catch (error) {
      message.textContent = error.message;
    } finally {
      button.disabled = false;
      cancel.classList.add("hidden");
      progress.classList.add("hidden");
    }
  });
  cancel.addEventListener("click", async () => {
    if (!state.job) return;
    await api.cancel(state.job.id);
    message.textContent = "Cancelando...";
  });
}

function mountIdle() {
  const overlay = document.querySelector("#idle-overlay");
  document.querySelector("#reactivate-btn").addEventListener("click", async () => {
    await api.reactivate();
    overlay.classList.add("hidden");
  });
  setInterval(async () => {
    try {
      const info = await api.idleStatus();
      overlay.classList.toggle("hidden", !info.idle);
    } catch {
      /* si el servidor está caído, el overlay se mantiene visible */
    }
  }, 20000);
}

function applyStoredUI() {
  for (const id of ["share", "cw", "cx", "cy"]) {
    const el = document.querySelector(`#${id}`);
    if (el && state.settings[id] !== undefined) el.value = state.settings[id];
  }
  for (const [selector, key, attr] of [
    ["#style-seg [data-style]", "layout", "style"],
    ["#mode-seg [data-mode]", "mode", "mode"]
  ]) {
    for (const el of document.querySelectorAll(selector)) {
      el.classList.toggle("active", el.dataset[attr] === state.settings[key]);
    }
  }
  const clipLen = document.querySelector("#clip-len");
  if (clipLen) clipLen.value = String(state.settings.clip_len);
  for (const [id, key] of [["subs", "subs"], ["gpu", "gpu"],
                           ["translate", "translate"], ["track_face", "track_face"]]) {
    const el = document.querySelector(`#${id}`);
    if (el) el.checked = Boolean(state.settings[key]);
  }
}

async function restoreWork() {
  const info = await api.state();
  if (info.video) {
    state.video = { name: "", W: info.W, H: info.H, dur: info.dur, quality: info.quality };
    document.dispatchEvent(new Event("video-loaded"));
  }
  if (info.clips) await renderResults();
}

async function main() {
  mountRouter();
  mountTheme();
  mountSource();
  mountPreview();
  mountFacecam();
  mountClips();
  mountGenerate();
  mountIdle();
  await mountSettings();
  await mountProjects();
  applyStoredUI();
  await restoreWork();
}

main().catch((error) => console.error(error));
