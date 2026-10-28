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
