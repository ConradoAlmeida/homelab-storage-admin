(function () {
  document.querySelectorAll("[data-tint]").forEach(function (item) {
    const tint = (item.dataset.tint || "").trim();
    if (/^#[0-9a-fA-F]{6}$/.test(tint)) {
      item.style.setProperty("--tint", tint);
    }
  });
})();
