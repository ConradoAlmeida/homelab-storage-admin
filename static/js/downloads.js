(function () {
  var filtros = document.querySelector("[data-torrent-filters]");
  var tabela = document.querySelector("[data-torrent-table]");
  var nome = document.getElementById("torrent-filtro-nome");
  var pasta = document.getElementById("torrent-filtro-pasta");
  var estado = document.getElementById("torrent-filtro-estado");
  var ordem = document.getElementById("torrent-ordem");
  var sentido = document.getElementById("torrent-sentido");
  var vazio = document.querySelector("[data-torrent-empty]");
  var contagem = document.querySelector("[data-torrent-count]");
  var chave = "torrent-tabela";
  var numericos = { progress: true, download: true, upload: true, size: true };
  var grupos = {
    baixando: {
      downloading: true,
      forcedDL: true,
      metaDL: true,
      stalledDL: true,
      checkingDL: true,
      allocating: true,
      moving: true,
    },
    fila: { queuedDL: true },
    pausado: { pausedDL: true, stoppedDL: true },
    concluido: {
      uploading: true,
      forcedUP: true,
      stalledUP: true,
      pausedUP: true,
      stoppedUP: true,
      queuedUP: true,
      checkingUP: true,
    },
    erro: { error: true, missingFiles: true },
  };

  function linhas() {
    if (!tabela) return [];
    return Array.prototype.slice.call(tabela.querySelectorAll("tr[data-hash]"));
  }

  function marcarOrdemInicial() {
    linhas().forEach(function (linha, indice) {
      if (!linha.hasAttribute("data-seq")) linha.setAttribute("data-seq", String(indice));
    });
  }

  function ler() {
    return {
      nome: nome ? nome.value : "",
      pasta: pasta ? pasta.value : "",
      estado: estado ? estado.value : "",
      ordem: ordem ? ordem.value : "",
      sentido: sentido && sentido.value === "desc" ? "desc" : "asc",
    };
  }

  function gravar() {
    try {
      window.sessionStorage.setItem(chave, JSON.stringify(ler()));
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
    if (estado && typeof salvo.estado === "string") estado.value = salvo.estado;
    if (ordem && typeof salvo.ordem === "string") ordem.value = salvo.ordem;
    if (sentido && (salvo.sentido === "asc" || salvo.sentido === "desc")) {
      sentido.value = salvo.sentido;
    }
  }

  function cabeçalhos() {
    var escolha = ler();
    if (!tabela) return;
    tabela.querySelectorAll("button.th-sort").forEach(function (botao) {
      var coluna = botao.getAttribute("data-sort");
      if (escolha.ordem && coluna === escolha.ordem) {
        botao.setAttribute("aria-sort", escolha.sentido === "desc" ? "descending" : "ascending");
      } else {
        botao.removeAttribute("aria-sort");
      }
    });
  }

  function aplicar() {
    if (!tabela) return;
    marcarOrdemInicial();
    var escolha = ler();
    var busca = (escolha.nome || "").trim().toLocaleLowerCase("pt-BR");
    var grupo = grupos[escolha.estado] || null;
    var visiveis = [];
    linhas().forEach(function (linha) {
      var nomeLinha = (linha.getAttribute("data-name") || "").toLocaleLowerCase("pt-BR");
      var pastaLinha = linha.getAttribute("data-library") || "";
      var codigo = linha.getAttribute("data-state-code") || "";
      var mostra = true;
      if (busca && nomeLinha.indexOf(busca) === -1) mostra = false;
      if (escolha.pasta && pastaLinha !== escolha.pasta) mostra = false;
      if (grupo && !grupo[codigo]) mostra = false;
      linha.hidden = !mostra;
      if (mostra) visiveis.push(linha);
    });
    var corpo = tabela.querySelector("tbody");
    var fator = escolha.sentido === "desc" ? -1 : 1;
    visiveis.sort(function (a, b) {
      if (!escolha.ordem) {
        return Number(a.getAttribute("data-seq")) - Number(b.getAttribute("data-seq"));
      }
      if (numericos[escolha.ordem]) {
        var na = Number(a.getAttribute("data-" + escolha.ordem) || 0);
        var nb = Number(b.getAttribute("data-" + escolha.ordem) || 0);
        if (na !== nb) return (na - nb) * fator;
      } else {
        var ta = (a.getAttribute("data-" + (escolha.ordem === "state" ? "state-label" : escolha.ordem)) || "");
        var tb = (b.getAttribute("data-" + (escolha.ordem === "state" ? "state-label" : escolha.ordem)) || "");
        var cmp = ta.localeCompare(tb, "pt-BR", { sensitivity: "base" });
        if (cmp !== 0) return cmp * fator;
      }
      return Number(a.getAttribute("data-seq")) - Number(b.getAttribute("data-seq"));
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

  function sentidoPadrao(coluna) {
    return numericos[coluna] ? "desc" : "asc";
  }

  if (filtros) {
    restaurar();
    [nome, pasta, estado, ordem, sentido].forEach(function (campo) {
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
    if (ordem) {
      ordem.addEventListener("change", function () {
        if (sentido && ordem.value) sentido.value = sentidoPadrao(ordem.value);
        gravar();
        aplicar();
      });
    }
  }

  if (tabela) {
    tabela.querySelectorAll("button.th-sort").forEach(function (botao) {
      botao.addEventListener("click", function () {
        var coluna = botao.getAttribute("data-sort") || "";
        if (!ordem || !sentido) return;
        if (ordem.value === coluna) {
          sentido.value = sentido.value === "desc" ? "asc" : "desc";
        } else {
          ordem.value = coluna;
          sentido.value = sentidoPadrao(coluna);
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
