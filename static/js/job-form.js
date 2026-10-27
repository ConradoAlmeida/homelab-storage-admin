(function () {
  const button = document.getElementById("restore-excludes");
  const textarea = document.getElementById("excludes");
  const defaults = document.getElementById("default-excludes");
  if (!button || !textarea || !defaults) return;
  button.addEventListener("click", function () {
    textarea.value = defaults.value;
  });
})();
