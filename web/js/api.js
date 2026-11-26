/** Envoltorios de la API. El frontend no conoce la lógica de negocio. */
async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function json(body) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const api = {
  state: () => request("/api/state"),
  idleStatus: () => request("/api/idle-status"),
  reactivate: () => request("/api/reactivate", { method: "POST" }),
  cache: () => request("/api/cache"),
  clearCache: () => request("/api/cache/clear", { method: "POST" }),
  loadProgress: () => request("/api/load-progress"),
  cancelLoad: () => request("/api/cancel-load", { method: "POST" }),
  settings: () => request("/api/settings"),
  saveSettings: (cfg) => request("/api/settings", json(cfg)),
  projects: () => request("/api/projects"),
  restore: (stem) => request("/api/restore", json({ stem })),
  clips: () => request("/api/clips"),
  load: (kind, value, quality) => request("/api/load", json({ kind, value, quality })),
  generate: (settings) => request("/api/generate", json(settings)),
  job: (id) => request(`/api/job?id=${encodeURIComponent(id)}`),
  cancel: (id) => request("/api/cancel", json({ id })),
  upload: (file) => request("/api/upload", {
    method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file
  })
};
