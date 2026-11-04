(function () {
  var raiz = document.querySelector("[data-task-poll]");
  if (!raiz) return;
  var endpoint = raiz.getAttribute("data-endpoint");
  if (!endpoint) return;

  var rotulos = {
    recovery_password: "Senha de recuperação",
    device: "Disco",
    mountpoint: "Montagem",
    repo: "Repositório",
    uuid: "UUID",
    share: "Share",
    name: "Nome",
    paths: "Caminhos",
    archive: "Arquivo",
    security_copy: "Cópia anterior",
    size_label: "Tamanho",
    integrity: "Integridade",
    snapshots: "Snapshots",
    message: "Detalhe"
  };
  var timer = null;

  function el(nome) {
    return raiz.querySelector("[data-task-" + nome + "]");
  }

  function texto(valor) {
    if (Array.isArray(valor)) return valor.join(", ");
    if (valor === null || valor === undefined) return "";
    return String(valor);
  }

  function mostrarResultado(resultado) {
    var caixa = el("result");
    if (!caixa) return;
    caixa.textContent = "";
    var senha = resultado.recovery_password;
    if (senha) {
      var zona = document.createElement("div");
      zona.className = "danger-zone";
      var titulo = document.createElement("strong");
      titulo.textContent = "Guarde a senha de recuperação do restic agora";
      var pre = document.createElement("pre");
      pre.className = "pre";
      pre.textContent = String(senha);
      zona.appendChild(titulo);
      zona.appendChild(pre);
      caixa.appendChild(zona);
    }
    Object.keys(rotulos).forEach(function (chave) {
      if (chave === "recovery_password" || chave === "message") return;
      if (!Object.prototype.hasOwnProperty.call(resultado, chave)) return;
      var valor = texto(resultado[chave]);
      if (!valor) return;
      var linha = document.createElement("p");
      var nome = document.createElement("strong");
      nome.textContent = rotulos[chave] + ": ";
      linha.appendChild(nome);
      linha.appendChild(document.createTextNode(valor));
      caixa.appendChild(linha);
    });
  }

  function render(dados) {
    var status = dados.status || "";
    var rodando = status === "running";
    var badge = el("badge");
    var spinner = el("spinner");
    var mensagem = el("message");
    var ok = el("ok");
    var falha = el("fail");
    if (spinner) spinner.hidden = !rodando;
    if (mensagem) mensagem.hidden = !rodando;
    if (mensagem && rodando) mensagem.textContent = dados.message || "Trabalho em andamento…";
    if (badge) {
      if (rodando) {
        badge.className = "tag ok";
        badge.textContent = "em andamento";
      } else if (status === "ok") {
        badge.className = "tag ok";
        badge.textContent = "concluído";
      } else {
        badge.className = "tag off";
        badge.textContent = "falhou";
      }
    }
    if (ok) {
      ok.hidden = status !== "ok";
      ok.textContent = status === "ok" ? dados.message || "Concluído." : "";
    }
    if (falha) {
      falha.hidden = status !== "failed";
      falha.textContent = status === "failed" ? dados.message || "O trabalho falhou." : "";
    }
    if (status === "ok") mostrarResultado(dados.result || {});
    return rodando;
  }

  function consultar() {
    fetch(endpoint, { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("status");
        return resposta.json();
      })
      .then(function (dados) {
        if (render(dados)) timer = window.setTimeout(consultar, 2000);
      })
      .catch(function () {
        if (raiz.getAttribute("data-status") === "running") {
          timer = window.setTimeout(consultar, 5000);
        }
      });
  }

  window.addEventListener("beforeunload", function () {
    if (timer) window.clearTimeout(timer);
  });
  consultar();
})();
