(function () {
  const form = document.getElementById("disk-setup-form");
  const overlay = document.getElementById("busy-overlay");
  const button = document.getElementById("disk-setup-submit");
  if (!form || !overlay) return;
  form.addEventListener("submit", function () {
    overlay.hidden = false;
    if (button) {
      button.disabled = true;
      button.textContent = "Preparando...";
    }
  });
})();
