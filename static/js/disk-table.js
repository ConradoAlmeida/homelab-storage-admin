(function () {
  function setExpanded(root, name, open) {
    root.querySelectorAll('[data-disk-toggle="' + name + '"]').forEach(function (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    root.querySelectorAll('[data-disk-detail="' + name + '"]').forEach(function (detail) {
      detail.hidden = !open;
    });
    root.querySelectorAll('[data-disk-row="' + name + '"]').forEach(function (row) {
      row.classList.toggle("is-expanded", open);
    });
  }

  document.querySelectorAll("[data-disk-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const root = btn.closest("section.section") || document;
      const name = btn.getAttribute("data-disk-toggle");
      if (!name) {
        return;
      }
      const open = btn.getAttribute("aria-expanded") !== "true";
      setExpanded(root, name, open);
    });
  });
})();
