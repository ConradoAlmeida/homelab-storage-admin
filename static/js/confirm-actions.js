(function () {
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });
})();
