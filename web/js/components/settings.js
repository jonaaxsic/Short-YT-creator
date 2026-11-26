/** Ajustes persistentes: carpetas y limpieza del video fuente. */
import { api } from "../api.js";

export async function mountSettings() {
  const outDir = document.querySelector("#out-dir");
  const workDir = document.querySelector("#work-dir");
  const cleanup = document.querySelector("#cleanup");
  const message = document.querySelector("#settings-msg");

  const cfg = await api.settings();
  outDir.value = cfg.out_dir;
  workDir.value = cfg.work_dir;
  cleanup.checked = Boolean(cfg.cleanup_source);

  const cacheInfo = document.querySelector("#cache-info");
  async function refreshCache() {
    try {
      const info = await api.cache();
      cacheInfo.textContent = `${info.files} archivos temporales · ${info.megabytes} MB`;
    } catch {
      cacheInfo.textContent = "No se pudo leer la caché.";
    }
  }
  document.querySelector("#clear-cache").addEventListener("click", async () => {
    const info = await api.clearCache();
    cacheInfo.textContent = `Se eliminaron ${info.removed} archivos (${info.megabytes} MB).`;
  });
  await refreshCache();

  document.querySelector("#save-settings").addEventListener("click", async () => {
    try {
      await api.saveSettings({
        out_dir: outDir.value.trim(), work_dir: workDir.value.trim(),
        cleanup_source: cleanup.checked
      });
      message.textContent = "Ajustes guardados.";
    } catch (error) {
      message.textContent = error.message;
    }
  });
}
