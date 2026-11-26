/** Listado de proyectos guardados y restauración sin reprocesar. */
import { api } from "../api.js";
import { renderResults } from "./results.js";

export async function mountProjects() {
  const list = document.querySelector("#projects-list");
  const projects = await api.projects();
  list.replaceChildren();
  if (!projects.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Aún no hay clips guardados.";
    list.append(empty);
    return;
  }
  for (const project of projects) {
    const row = document.createElement("div");
    row.className = "project-row";
    const label = document.createElement("span");
    label.textContent = `${project.stem} · ${project.count} clips`;
    const button = document.createElement("button");
    button.className = "btn";
    button.textContent = "Abrir proyecto";
    button.addEventListener("click", async () => {
      await api.restore(project.stem);
      await renderResults();
      document.dispatchEvent(new Event("video-loaded"));
      document.querySelector('[data-view="crear"]').click();
    });
    row.append(label, button);
    list.append(row);
  }
}
