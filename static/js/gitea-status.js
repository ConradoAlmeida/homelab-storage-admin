(function () {
  var raiz = document.querySelector("[data-gitea-status]");
  if (!raiz) return;

  var endpoint = raiz.getAttribute("data-endpoint");
  var etapas = {
    queued: "na fila do systemd…",
    dump: "gerando o dump…",
    dumped: "dump pronto, preparando a cópia…",
    copy: "copiando para o USB — não desconecte",
    verify: "verificando o hash — não desconecte",
    done: "concluído"
  };
  var timer = null;

  function el(id) {
    return document.getElementById(id);
  }

  function renderDumps(dumps) {
    var corpo = el("gitea-dumps-body");
    if (!corpo) return;
    corpo.innerHTML = "";
    if (!dumps.length) {
      var vazio = document.createElement("tr");
      var celula = document.createElement("td");
      celula.colSpan = 3;
      var caixa = document.createElement("div");
      caixa.className = "empty";
      caixa.textContent = "Nenhum dump no servidor ainda.";
      celula.appendChild(caixa);
      vazio.appendChild(celula);
      corpo.appendChild(vazio);
      return;
    }
    dumps.forEach(function (item) {
      var linha = document.createElement("tr");
      var nome = document.createElement("td");
      nome.className = "mono text-12";
      nome.textContent = item.name || "";
      var criado = document.createElement("td");
      criado.className = "muted";
      criado.textContent = item.created_label || "";
      var tamanho = document.createElement("td");
      tamanho.textContent = item.size_label || "";
      linha.appendChild(nome);
      linha.appendChild(criado);
      linha.appendChild(tamanho);
      corpo.appendChild(linha);
    });
  }

  function render(dados) {
    var status = dados.status || {};
    var rodando = status.status === "running";
    var alerta = el("gitea-alert");
    var sucesso = el("gitea-success");
    var falha = el("gitea-failure");
    var spinner = el("gitea-spinner");
    var badge = el("gitea-status-badge");
    var texto = el("gitea-status-text");
    var meta = el("gitea-status-meta");
    var usb = el("gitea-usb-path");

    if (alerta) alerta.hidden = !rodando;
    if (sucesso) sucesso.hidden = !(status.status === "done" && status.usb_verified);
    if (falha) falha.hidden = status.status !== "failed";
    if (falha) {
      var motivo = el("gitea-failure-text");
      if (motivo) motivo.textContent = status.error || "";
    }
    if (spinner) spinner.hidden = !rodando;

    if (badge) {
      if (rodando) {
        badge.className = "badge live";
        badge.textContent = "em andamento";
      } else if (status.status === "done") {
        badge.className = "state-ok";
        badge.textContent = "concluído" + (status.usb_verified ? " e verificado" : "");
      } else if (status.status === "failed") {
        badge.className = "state-bad";
        badge.textContent = "falhou";
      } else {
        badge.className = "muted";
        badge.textContent = "-";
      }
    }

    if (texto) texto.textContent = rodando ? etapas[status.stage] || status.stage || "" : "";

    if (meta) {
      var partes = [];
      var quando = rodando ? status.started_at : status.finished_at || status.started_at;
      if (quando) partes.push(quando.replace("T", " "));
      if (status.size_label) partes.push(status.size_label);
      if (status.error && !falha) partes.push(status.error);
      meta.textContent = partes.join(" · ");
    }

    if (usb) {
      if (status.usb_path) {
        usb.hidden = false;
        usb.textContent =
          "Copiado para " +
          status.usb_path +
          (status.sha256 ? " · sha256 " + status.sha256.slice(0, 16) + "…" : "");
      } else {
        usb.hidden = true;
      }
    }

    document.querySelectorAll("[data-gitea-run]").forEach(function (botao) {
      var bloqueado = botao.getAttribute("data-base-disabled") === "1";
      botao.disabled = rodando || bloqueado;
    });

    renderDumps(dados.dumps || []);
    return rodando;
  }

  function consultar() {
    fetch(endpoint, { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("status");
        return resposta.json();
      })
      .then(function (dados) {
        var rodando = render(dados);
        if (rodando) {
          timer = window.setTimeout(consultar, 2000);
        }
      })
      .catch(function () {
        if (raiz.getAttribute("data-running") === "1") {
          timer = window.setTimeout(consultar, 5000);
        }
      });
  }

  window.addEventListener("beforeunload", function () {
    if (timer) window.clearTimeout(timer);
  });

  consultar();
})();
