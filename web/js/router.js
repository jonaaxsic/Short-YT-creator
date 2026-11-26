/** Cambio de vistas sin recargar la página. */
import { update } from "./state.js";

export function mountRouter() {
  const items = document.querySelectorAll("[data-view]");
  const views = document.querySelectorAll(".view");
  for (const item of items) {
    item.addEventListener("click", () => {
      const view = item.dataset.view;
      update({ view });
      for (const el of items) el.classList.toggle("active", el === item);
      for (const el of views) {
        const visible = el.id === `view-${view}`;
        el.classList.toggle("active", visible);
        el.classList.toggle("hidden", !visible);
      }
    });
  }
}
