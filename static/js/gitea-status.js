(function () {
  if (!document.querySelector("[data-gitea-running]")) return;
  window.setTimeout(function () {
    window.location.reload();
  }, 5000);
})();
