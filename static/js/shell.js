(function () {
  const toggle = document.querySelector("[data-nav-toggle]");
  if (!toggle) return;
  toggle.addEventListener("click", function () {
    document.body.classList.toggle("nav-open");
  });
  document.addEventListener("click", function (event) {
    if (!document.body.classList.contains("nav-open")) return;
    if (event.target.closest(".sidebar") || event.target.closest("[data-nav-toggle]")) return;
    document.body.classList.remove("nav-open");
  });
})();

(function () {
  function place(menu) {
    const panel = menu.querySelector(".action-menu-panel, .restore-form");
    if (!panel) return;
    if (!menu.open) {
      panel.style.position = "";
      panel.style.top = "";
      panel.style.left = "";
      panel.style.right = "";
      return;
    }
    panel.style.position = "fixed";
    panel.style.right = "auto";
    const rect = menu.getBoundingClientRect();
    const width = panel.offsetWidth;
    const height = panel.offsetHeight;
    const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    let top = rect.bottom + 6;
    if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6);
    panel.style.left = left + "px";
    panel.style.top = top + "px";
  }
  document.addEventListener("toggle", function (event) {
    const menu = event.target;
    if (!(menu instanceof HTMLDetailsElement)) return;
    if (!menu.classList.contains("action-menu") && !menu.classList.contains("restore-details")) return;
    requestAnimationFrame(function () { place(menu); });
  }, true);
})();
