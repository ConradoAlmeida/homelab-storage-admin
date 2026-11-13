(function () {
  "use strict";

  var modal = document.getElementById("django-admin-modal");
  if (!modal) return;

  var form = modal.querySelector("[data-admin-form]");
  var title = modal.querySelector("[data-admin-title]");
  var subtitle = modal.querySelector("[data-admin-subtitle]");
  var lastLogin = modal.querySelector("[data-admin-last-login]");
  var actionInput = modal.querySelector("[data-admin-acao]");
  var appInput = modal.querySelector("[data-admin-app]");
  var password = modal.querySelector("#admin-password");
  var confirmation = modal.querySelector("#admin-password2");
  var toggle = modal.querySelector("[data-admin-toggle]");
  var strength = modal.querySelector("[data-admin-strength]");
  var strengthLabel = modal.querySelector("[data-admin-strength-label]");
  var bars = modal.querySelectorAll(".admin-strength-bars span");
  var match = modal.querySelector("[data-admin-match]");
  var submit = modal.querySelector("[data-admin-submit]");

  var LABELS = ["Senha fraca", "Senha fraca", "Senha razoável", "Senha boa", "Senha forte"];

  function scorePassword(value) {
    var score = 0;
    if (value.length >= 8) score += 1;
    if (value.length >= 12) score += 1;
    var classes = 0;
    if (/[a-z]/.test(value)) classes += 1;
    if (/[A-Z]/.test(value)) classes += 1;
    if (/\d/.test(value)) classes += 1;
    if (/[^A-Za-z0-9]/.test(value)) classes += 1;
    if (classes >= 2) score += 1;
    if (classes >= 3 || value.length >= 16) score += 1;
    return Math.min(score, 4);
  }

  function updateStrength() {
    var value = password.value;
    var score = value ? scorePassword(value) : 0;
    modal.dataset.strength = String(score);
    strength.hidden = !value;
    strengthLabel.dataset.level = String(score);
    bars.forEach(function (bar, index) {
      bar.classList.toggle("is-on", index < score);
    });
    if (!value) {
      strengthLabel.textContent = "";
      return;
    }
    var minimum = value.length >= 8
      ? " · mínimo de 8 caracteres atendido"
      : " · mínimo de 8 caracteres";
    strengthLabel.textContent = LABELS[score] + minimum;
  }

  function updateMatch() {
    if (!confirmation.value) {
      match.hidden = true;
      match.classList.remove("bad");
      submit.disabled = false;
      return;
    }
    var same = password.value === confirmation.value;
    match.hidden = false;
    match.textContent = same ? "As senhas coincidem" : "As senhas não coincidem";
    match.classList.toggle("bad", !same);
    submit.disabled = !same;
  }

  function resetForm() {
    form.reset();
    modal.dataset.strength = "0";
    strength.hidden = true;
    strengthLabel.textContent = "";
    strengthLabel.dataset.level = "0";
    bars.forEach(function (bar) {
      bar.classList.remove("is-on");
    });
    match.hidden = true;
    match.classList.remove("bad");
    match.textContent = "";
    submit.disabled = false;
    password.type = "password";
    toggle.textContent = "Mostrar";
    toggle.setAttribute("aria-pressed", "false");
  }

  function closeModal() {
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  }

  function openModal(button) {
    resetForm();
    var action = button.dataset.action || "password";
    var isCreate = action === "create";
    actionInput.value = action;
    appInput.value = button.dataset.app || "";
    title.textContent = isCreate ? "Criar admin" : "Trocar senha";
    subtitle.textContent = [button.dataset.label, button.dataset.container]
      .filter(Boolean)
      .join(" · ") || "—";
    var login = button.dataset.lastLogin || "";
    lastLogin.textContent = login ? "Último login " + login : "Último login —";
    submit.textContent = isCreate ? "Criar admin" : "Salvar senha";

    if (typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
    password.focus();
  }

  document.querySelectorAll("[data-admin-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      openModal(button);
    });
  });

  modal.querySelectorAll("[data-admin-close]").forEach(function (button) {
    button.addEventListener("click", closeModal);
  });

  modal.addEventListener("click", function (event) {
    if (event.target === modal) closeModal();
  });

  toggle.addEventListener("click", function () {
    var showing = password.type === "text";
    password.type = showing ? "password" : "text";
    toggle.textContent = showing ? "Mostrar" : "Ocultar";
    toggle.setAttribute("aria-pressed", showing ? "false" : "true");
    password.focus();
  });

  password.addEventListener("input", function () {
    updateStrength();
    updateMatch();
  });

  confirmation.addEventListener("input", updateMatch);

  form.addEventListener("submit", function (event) {
    if (password.value !== confirmation.value) {
      event.preventDefault();
      updateMatch();
      confirmation.focus();
    }
  });
})();
