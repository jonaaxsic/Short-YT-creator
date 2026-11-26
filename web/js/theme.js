/** Tema controlado por color-scheme y localStorage; nunca recarga la app. */
const META = document.querySelector('meta[name="color-scheme"]');

function current() {
  return localStorage.getItem("color-scheme") || "dark";
}

function paint() {
  const value = current();
  META.content = value;
  const selected = value === "light dark" ? "system" : value;
  for (const button of document.querySelectorAll("[data-theme]")) {
    button.classList.toggle("active", button.dataset.theme === selected);
  }
}

export function mountTheme() {
  for (const button of document.querySelectorAll("[data-theme]")) {
    button.addEventListener("click", () => {
      const choice = button.dataset.theme;
      if (choice === "system") localStorage.removeItem("color-scheme");
      else localStorage.setItem("color-scheme", choice);
      paint();
    });
  }
  window.addEventListener("storage", paint);
  paint();
}
