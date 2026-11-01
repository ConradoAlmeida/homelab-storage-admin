(function () {
  var filtros = document.querySelector("[data-torrent-filters]");
  var tabela = document.querySelector("[data-torrent-table]");
  var nome = document.getElementById("torrent-filtro-nome");
  var limparNome = document.querySelector("[data-clear-nome]");
  var ordemCampo = document.getElementById("torrent-ordem");
  var sentidoBotao = document.getElementById("torrent-sentido");
  var chips = document.querySelector("[data-torrent-chips]");
  var limpar = document.querySelector("[data-torrent-clear]");
  var ativos = document.querySelector("[data-torrent-active]");
  var vazio = document.querySelector("[data-torrent-empty]");
  var contagem = document.querySelector("[data-torrent-count]");
  var rotuloPasta = document.querySelector("[data-pasta-rotulo]");
  var rotuloEstado = document.querySelector("[data-estado-rotulo]");
  var chave = "torrent-tabela";
  var numericos = { progress: true, download: true, upload: true, size: true };
  var rotulosEstado = {
    "": "Todos",
    concluido: "concluído",
    baixando: "baixando",
    aguardando: "aguardando",
    pausado: "pausado",
    metadados: "lendo metadados",
    fila: "na fila",
    enviando: "enviando",
    erro: "com erro",
  };
  var ordem = "";
  var sentido = "asc";
  var pasta = "";
  var estado = "";
  var recorte = "";

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

  function grupoEstado(linha) {
    var rotulo = linha.getAttribute("data-state-label") || "";
    if (rotulo === "concluído") return "concluido";
    if (rotulo === "baixando") return "baixando";
    if (rotulo === "aguardando") return "aguardando";
    if (rotulo === "pausado") return "pausado";
    if (rotulo === "lendo metadados") return "metadados";
    if (rotulo === "na fila") return "fila";
    if (rotulo === "enviando") return "enviando";
    if (rotulo === "erro" || rotulo === "arquivos ausentes") return "erro";
    return "";
  }

  function ativo(linha) {
    var codigo = linha.getAttribute("data-state-code") || "";
    if (numero(linha, "data-download") > 0 || numero(linha, "data-upload") > 0) return true;
    return codigo === "downloading" || codigo === "metaDL" || codigo === "forcedDL" || codigo === "uploading" || codigo === "forcedUP";
  }

  function concluido(linha) {
    return numero(linha, "data-progress") >= 100;
  }

  function comErro(linha) {
    var codigo = linha.getAttribute("data-state-code") || "";
    return codigo === "error" || codigo === "missingFiles";
  }

  function gravar() {
    try {
      window.sessionStorage.setItem(chave, JSON.stringify({
        nome: nome ? nome.value : "",
        pasta: pasta,
        estado: estado,
        recorte: recorte,
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
    if (typeof salvo.pasta === "string") pasta = salvo.pasta;
    if (typeof salvo.estado === "string" && Object.prototype.hasOwnProperty.call(rotulosEstado, salvo.estado)) {
      estado = salvo.estado;
    }
    if (salvo.recorte === "active" || salvo.recorte === "completed" || salvo.recorte === "errored") {
      recorte = salvo.recorte;
    }
    if (typeof salvo.ordem === "string") ordem = salvo.ordem;
    if (salvo.sentido === "asc" || salvo.sentido === "desc") sentido = salvo.sentido;
    if (ordemCampo) ordemCampo.value = ordem;
  }

  function fecharMenus() {
    document.querySelectorAll(".torrent-pick[open]").forEach(function (menu) {
      menu.removeAttribute("open");
    });
  }

  function desenharChips() {
    if (!chips) return;
    chips.textContent = "";
    function chip(texto, aoFechar) {
      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "torrent-chip";
      botao.textContent = texto + " ×";
      botao.addEventListener("click", aoFechar);
      chips.appendChild(botao);
    }
    var quantidade = 0;
    if (nome && nome.value.trim()) {
      quantidade += 1;
      chip(nome.value.trim(), function () {
        nome.value = "";
        gravar();
        aplicar();
      });
    }
    if (pasta) {
      quantidade += 1;
      chip(pasta, function () {
        pasta = "";
        gravar();
        aplicar();
      });
    }
    if (estado) {
      quantidade += 1;
      chip(rotulosEstado[estado] || estado, function () {
        estado = "";
        gravar();
        aplicar();
      });
    }
    if (recorte) quantidade += 1;
    if (limpar) limpar.hidden = quantidade === 0;
    if (ativos) {
      ativos.hidden = quantidade === 0;
      ativos.textContent = quantidade === 1 ? "1 filtro ativo" : quantidade + " filtros ativos";
    }
    if (limparNome) limparNome.hidden = !(nome && nome.value);
    if (rotuloPasta) rotuloPasta.textContent = pasta || "Todas";
    if (rotuloEstado) rotuloEstado.textContent = rotulosEstado[estado] || "Todos";
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
    if (sentidoBotao) sentidoBotao.textContent = sentido === "desc" ? "↓" : "↑";
    if (ordemCampo && ordemCampo.value !== ordem) ordemCampo.value = ordem;
  }

  function aplicar() {
    if (!tabela) return;
    marcarOrdemInicial();
    var busca = (nome && nome.value ? nome.value : "").trim().toLocaleLowerCase("pt-BR");
    var todas = linhas();
    var totais = { all: todas.length, active: 0, completed: 0, errored: 0 };
    todas.forEach(function (linha) {
      if (ativo(linha)) totais.active += 1;
      if (concluido(linha)) totais.completed += 1;
      if (comErro(linha)) totais.errored += 1;
    });
    document.querySelectorAll("[data-stat-count]").forEach(function (campo) {
      var qual = campo.getAttribute("data-stat-count");
      campo.textContent = String(totais[qual] || 0);
    });
    document.querySelectorAll("[data-stat]").forEach(function (botao) {
      botao.classList.toggle("is-on", (botao.getAttribute("data-stat") || "") === recorte);
    });
    var visiveis = [];
    todas.forEach(function (linha) {
      var nomeLinha = (linha.getAttribute("data-name") || "").toLocaleLowerCase("pt-BR");
      var mostra = true;
      if (busca && nomeLinha.indexOf(busca) === -1) mostra = false;
      if (pasta && (linha.getAttribute("data-library") || "") !== pasta) mostra = false;
      if (estado && grupoEstado(linha) !== estado) mostra = false;
      if (recorte === "active" && !ativo(linha)) mostra = false;
      if (recorte === "completed" && !concluido(linha)) mostra = false;
      if (recorte === "errored" && !comErro(linha)) mostra = false;
      linha.hidden = !mostra;
      if (mostra) visiveis.push(linha);
    });
    var corpo = tabela.querySelector("tbody");
    var fator = sentido === "desc" ? -1 : 1;
    visiveis.sort(function (a, b) {
      if (!ordem) return numero(a, "data-seq") - numero(b, "data-seq");
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
      var total = todas.length;
      var palavra = total === 1 ? "torrent" : "torrents";
      contagem.textContent = visiveis.length === total
        ? total + " " + palavra
        : visiveis.length + " de " + total + " " + palavra;
    }
    desenharChips();
    cabeçalhos();
  }

  if (filtros) restaurar();

  if (nome) {
    nome.addEventListener("input", function () {
      gravar();
      aplicar();
    });
  }
  if (limparNome) {
    limparNome.addEventListener("click", function () {
      if (!nome) return;
      nome.value = "";
      gravar();
      aplicar();
    });
  }
  document.querySelectorAll("[data-pasta]").forEach(function (botao) {
    if (botao.tagName !== "BUTTON") return;
    botao.addEventListener("click", function () {
      pasta = botao.getAttribute("data-pasta") || "";
      fecharMenus();
      gravar();
      aplicar();
    });
  });
  document.querySelectorAll("[data-estado]").forEach(function (botao) {
    if (botao.tagName !== "BUTTON") return;
    botao.addEventListener("click", function () {
      estado = botao.getAttribute("data-estado") || "";
      fecharMenus();
      gravar();
      aplicar();
    });
  });
  document.querySelectorAll("[data-stat]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      recorte = botao.getAttribute("data-stat") || "";
      gravar();
      aplicar();
    });
  });
  if (limpar) {
    limpar.addEventListener("click", function () {
      if (nome) nome.value = "";
      pasta = "";
      estado = "";
      recorte = "";
      gravar();
      aplicar();
    });
  }
  if (ordemCampo) {
    ordemCampo.addEventListener("change", function () {
      ordem = ordemCampo.value;
      sentido = "asc";
      gravar();
      aplicar();
    });
  }
  if (sentidoBotao) {
    sentidoBotao.addEventListener("click", function () {
      sentido = sentido === "asc" ? "desc" : "asc";
      gravar();
      aplicar();
    });
  }
  document.addEventListener("click", function (evento) {
    document.querySelectorAll(".torrent-pick[open]").forEach(function (menu) {
      if (!menu.contains(evento.target)) menu.removeAttribute("open");
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
