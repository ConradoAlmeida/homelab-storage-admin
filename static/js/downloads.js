(function () {
  var filtros = document.querySelector("[data-torrent-filters]");
  var tabela = document.querySelector("[data-torrent-table]");
  var nome = document.getElementById("torrent-filtro-nome");
  var pasta = document.getElementById("torrent-filtro-pasta");
  var estado = document.getElementById("torrent-filtro-estado");
  var vazio = document.querySelector("[data-torrent-empty]");
  var contagem = document.querySelector("[data-torrent-count]");
  var chave = "torrent-tabela";
  var numericos = { progress: true, download: true, upload: true, size: true };
  var ordem = "";
  var sentido = "asc";

  function linhas() {
    if (!tabela) return [];
    return Array.prototype.slice.call(tabela.querySelectorAll("tr[data-hash]"));
  }

  function marcarOrdemInicial() {
    linhas().forEach(function (linha, indice) {
      if (!linha.hasAttribute("data-seq")) linha.setAttribute("data-seq", String(indice));
    });
  }

  function numero(linha, atributo) {
    var valor = Number(linha.getAttribute(atributo) || 0);
    return Number.isFinite(valor) ? valor : 0;
  }

  function pausado(codigo) {
    return codigo === "pausedDL" || codigo === "pausedUP" || codigo === "stoppedDL" || codigo === "stoppedUP";
  }

  function combinaEstado(linha, filtro) {
    if (!filtro) return true;
    var codigo = linha.getAttribute("data-state-code") || "";
    var progresso = numero(linha, "data-progress");
    var download = numero(linha, "data-download");
    var upload = numero(linha, "data-upload");
    if (filtro === "downloading") {
      return codigo === "downloading" || codigo === "metaDL" || codigo === "forcedDL" || codigo === "stalledDL" || codigo === "queuedDL" || codigo === "checkingDL" || codigo === "allocating";
    }
    if (filtro === "seeding") {
      return codigo === "uploading" || codigo === "forcedUP" || codigo === "stalledUP" || codigo === "queuedUP" || codigo === "checkingUP";
    }
    if (filtro === "completed") return progresso >= 100;
    if (filtro === "paused") return pausado(codigo);
    if (filtro === "resumed") return !pausado(codigo);
    if (filtro === "active") return download > 0 || upload > 0;
    if (filtro === "inactive") return download === 0 && upload === 0;
    if (filtro === "stalled") return codigo === "stalledDL" || codigo === "stalledUP";
    if (filtro === "stalled_uploading") return codigo === "stalledUP";
    if (filtro === "stalled_downloading") return codigo === "stalledDL";
    if (filtro === "checking") return codigo === "checkingDL" || codigo === "checkingUP" || codigo === "checkingResumeData";
    if (filtro === "moving") return codigo === "moving";
    if (filtro === "errored") return codigo === "error" || codigo === "missingFiles";
    return true;
  }

  function gravar() {
    try {
      window.sessionStorage.setItem(chave, JSON.stringify({
        nome: nome ? nome.value : "",
        pasta: pasta ? pasta.value : "",
        estado: estado ? estado.value : "",
        ordem: ordem,
        sentido: sentido,
      }));
    } catch (erro) {
      /* a lista segue funcionando sem memória da sessão */
    }
  }

  function restaurar() {
    var salvo = null;
    try {
      salvo = JSON.parse(window.sessionStorage.getItem(chave) || "null");
    } catch (erro) {
      salvo = null;
    }
    if (!salvo || typeof salvo !== "object") return;
    if (nome && typeof salvo.nome === "string") nome.value = salvo.nome;
    if (pasta && typeof salvo.pasta === "string") pasta.value = salvo.pasta;
    if (estado && typeof salvo.estado === "string" && estado.querySelector('option[value="' + salvo.estado + '"]')) {
      estado.value = salvo.estado;
    }
    if (typeof salvo.ordem === "string") ordem = salvo.ordem;
    if (salvo.sentido === "asc" || salvo.sentido === "desc") sentido = salvo.sentido;
  }

  function cabeçalhos() {
    if (!tabela) return;
    tabela.querySelectorAll("button.th-sort").forEach(function (botao) {
      var coluna = botao.getAttribute("data-sort");
      if (ordem && coluna === ordem) {
        botao.setAttribute("aria-sort", sentido === "desc" ? "descending" : "ascending");
      } else {
        botao.removeAttribute("aria-sort");
      }
    });
  }

  function aplicar() {
    if (!tabela) return;
    marcarOrdemInicial();
    var busca = (nome && nome.value ? nome.value : "").trim().toLocaleLowerCase("pt-BR");
    var pastaEscolhida = pasta ? pasta.value : "";
    var estadoEscolhido = estado ? estado.value : "";
    var visiveis = [];
    linhas().forEach(function (linha) {
      var nomeLinha = (linha.getAttribute("data-name") || "").toLocaleLowerCase("pt-BR");
      var pastaLinha = linha.getAttribute("data-library") || "";
      var mostra = true;
      if (busca && nomeLinha.indexOf(busca) === -1) mostra = false;
      if (pastaEscolhida && pastaLinha !== pastaEscolhida) mostra = false;
      if (!combinaEstado(linha, estadoEscolhido)) mostra = false;
      linha.hidden = !mostra;
      if (mostra) visiveis.push(linha);
    });
    var corpo = tabela.querySelector("tbody");
    var fator = sentido === "desc" ? -1 : 1;
    visiveis.sort(function (a, b) {
      if (!ordem) {
        return numero(a, "data-seq") - numero(b, "data-seq");
      }
      if (numericos[ordem]) {
        var na = numero(a, "data-" + ordem);
        var nb = numero(b, "data-" + ordem);
        if (na !== nb) return (na - nb) * fator;
      } else {
        var atributo = ordem === "state" ? "data-state-label" : "data-" + ordem;
        var cmp = (a.getAttribute(atributo) || "").localeCompare(b.getAttribute(atributo) || "", "pt-BR", { sensitivity: "base" });
        if (cmp !== 0) return cmp * fator;
      }
      return numero(a, "data-seq") - numero(b, "data-seq");
    });
    visiveis.forEach(function (linha) {
      corpo.appendChild(linha);
    });
    if (vazio) vazio.hidden = visiveis.length !== 0;
    if (contagem) {
      var total = linhas().length;
      var palavra = total === 1 ? "torrent" : "torrents";
      contagem.textContent = visiveis.length === total
        ? total + " " + palavra
        : visiveis.length + " de " + total + " " + palavra;
    }
    cabeçalhos();
  }

  if (filtros) restaurar();
  [nome, pasta, estado].forEach(function (campo) {
    if (!campo) return;
    campo.addEventListener("input", function () {
      gravar();
      aplicar();
    });
    campo.addEventListener("change", function () {
      gravar();
      aplicar();
    });
  });

  if (tabela) {
    tabela.querySelectorAll("button.th-sort").forEach(function (botao) {
      botao.addEventListener("click", function () {
        var coluna = botao.getAttribute("data-sort") || "";
        if (ordem === coluna) {
          sentido = sentido === "asc" ? "desc" : "asc";
        } else {
          ordem = coluna;
          sentido = "asc";
        }
        gravar();
        aplicar();
      });
    });
    aplicar();
  }

  var alvo = document.querySelector("[data-torrent-poll]");
  if (!alvo) return;
  var url = alvo.getAttribute("data-torrent-poll");

  function texto(linha, seletor, valor) {
    var campo = linha.querySelector(seletor);
    if (campo) campo.textContent = valor || "";
  }

  window.setInterval(function () {
    if (!alvo.getAttribute("data-torrent-poll")) return;
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("status");
        return resposta.json();
      })
      .then(function (dados) {
        var torrents = dados.torrents || [];
        var atuais = alvo.querySelectorAll("tr[data-hash]");
        if (atuais.length !== torrents.length) {
          window.location.reload();
          return;
        }
        for (var i = 0; i < torrents.length; i += 1) {
          var item = torrents[i];
          if (!/^[0-9a-f]{40,64}$/i.test(item.hash || "")) {
            window.location.reload();
            return;
          }
          var linha = alvo.querySelector('tr[data-hash="' + item.hash + '"]');
          if (!linha || (item.state || "") !== linha.getAttribute("data-state-code")) {
            window.location.reload();
            return;
          }
          linha.setAttribute("data-name", item.name || "");
          linha.setAttribute("data-state-label", item.state_label || "");
          linha.setAttribute("data-progress", String(item.progress || 0));
          linha.setAttribute("data-download", String(item.download_bps || 0));
          linha.setAttribute("data-upload", String(item.upload_bps || 0));
          linha.setAttribute("data-size", String(item.size_bytes || 0));
          texto(linha, "[data-name]", item.name);
          texto(linha, "[data-state]", item.state_label);
          texto(linha, "[data-download]", item.download_speed);
          texto(linha, "[data-upload]", item.upload_speed);
          texto(linha, "[data-percent]", item.progress_label);
          texto(linha, "[data-eta]", item.eta ? "· " + item.eta : "");
        }
        aplicar();
        if (!dados.active) alvo.removeAttribute("data-torrent-poll");
      })
      .catch(function () {});
  }, 5000);
})();
