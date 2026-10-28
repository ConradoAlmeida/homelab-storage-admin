(function () {
  var alvo = document.querySelector("[data-auto-refresh]");
  if (!alvo || alvo.getAttribute("data-status") !== "running") return;
  window.setTimeout(function () {
    window.location.reload();
  }, 5000);
})();
