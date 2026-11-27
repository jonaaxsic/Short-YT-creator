/** Tarjetas de clips: muestra reproducible y descarga del original. */
import { api } from "../api.js";

export async function renderResults() {
  const section = document.querySelector("#results");
  const grid = document.querySelector("#results-grid");
  const clips = await api.clips();
  grid.replaceChildren();
  for (const clip of clips) {
    const card = document.createElement("article");
    card.className = "result";
    const player = document.createElement("video");
    player.src = `/video/preview?name=${encodeURIComponent(clip.name)}`;
    player.controls = true;
    player.preload = "metadata";
    const label = document.createElement("p");
    label.className = "muted";
    label.textContent = clip.name.replace(/\.mp4$/, "");
    const actions = document.createElement("div");
    actions.className = "result-actions";
    const link = document.createElement("a");
    link.className = "btn";
    link.href = `/video/clip?name=${encodeURIComponent(clip.name)}`;
    link.download = clip.name;
    link.textContent = "Descargar";
    const remove = document.createElement("button");
    remove.className = "btn danger";
    remove.textContent = "Eliminar";
    remove.addEventListener("click", async () => {
      if (!confirm("¿Eliminar este clip?")) return;
      await api.deleteClip(clip.name);
      await renderResults();
    });
    actions.append(link, remove);
    card.append(player, label, actions);
    grid.append(card);
  }
  section.classList.toggle("hidden", clips.length === 0);
}
