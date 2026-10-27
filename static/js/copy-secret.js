(function () {
  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", function () {
      const input = document.getElementById(button.dataset.copyTarget);
      if (!input) return;
      input.select();
      const fallback = function () {
        try {
          document.execCommand("copy");
          button.textContent = "Copiado";
          setTimeout(() => { button.textContent = "Copiar"; }, 1500);
        } catch (error) {
          // Mantém o texto original; o usuário ainda pode copiar manualmente.
        }
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(input.value).then(() => {
          button.textContent = "Copiado";
          setTimeout(() => { button.textContent = "Copiar"; }, 1500);
        }).catch(fallback);
      } else {
        fallback();
      }
    });
  });
})();
