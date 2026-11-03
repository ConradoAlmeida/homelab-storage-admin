(function () {
  var filtros = document.querySelector("[data-torrent-filters]");
  var tabela = document.querySelector("[data-torrent-table]");
  var nome = document.getElementById("torrent-filtro-nome");
  var limparNome = document.querySelector("[data-clear-nome]");
  var pastaCampo = document.getElementById("torrent-filtro-pasta");
  var limpar = document.querySelector("[data-torrent-clear]");
  var vazio = document.querySelector("[data-torrent-empty]");
  var contagem = document.querySelector("[data-torrent-count]");
  var chave = "torrent-tabela";
  var numericos = { progress: true, download: true, upload: true, size: true };
  var ordem = "";
  var sentido = "asc";
  var pasta = "";
  var estado = "";

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
    if (rotulo === "concluído" || rotulo === "enviando") return "concluido";
    if (rotulo === "baixando" || rotulo === "lendo metadados") return "baixando";
    if (rotulo === "aguardando" || rotulo === "pausado" || rotulo === "na fila") return "aguardando";
    if (rotulo === "erro" || rotulo === "arquivos ausentes") return "erro";
    return "";
  }

  function gravar() {
    try {
      window.sessionStorage.setItem(chave, JSON.stringify({
        nome: nome ? nome.value : "",
        pasta: pasta,
        estado: estado,
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
    if (salvo.estado === "" || salvo.estado === "baixando" || salvo.estado === "aguardando" || salvo.estado === "concluido" || salvo.estado === "erro") {
      estado = salvo.estado;
    }
    if (typeof salvo.ordem === "string") ordem = salvo.ordem;
    if (salvo.sentido === "asc" || salvo.sentido === "desc") sentido = salvo.sentido;
    if (pastaCampo) pastaCampo.value = pasta;
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
    var todas = linhas();
    var totais = { all: todas.length, baixando: 0, aguardando: 0, concluido: 0, erro: 0 };
    todas.forEach(function (linha) {
      var grupo = grupoEstado(linha);
      if (grupo && Object.prototype.hasOwnProperty.call(totais, grupo)) totais[grupo] += 1;
    });
    document.querySelectorAll("[data-estado-count]").forEach(function (campo) {
      var qual = campo.getAttribute("data-estado-count");
      campo.textContent = String(totais[qual] || 0);
    });
    document.querySelectorAll("[data-estado]").forEach(function (botao) {
      botao.classList.toggle("is-on", (botao.getAttribute("data-estado") || "") === estado);
    });
    var visiveis = [];
    todas.forEach(function (linha) {
      var nomeLinha = (linha.getAttribute("data-name") || "").toLocaleLowerCase("pt-BR");
      var mostra = true;
      if (busca && nomeLinha.indexOf(busca) === -1) mostra = false;
      if (pasta && (linha.getAttribute("data-library") || "") !== pasta) mostra = false;
      if (estado && grupoEstado(linha) !== estado) mostra = false;
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
    var filtrosLigados = Boolean((nome && nome.value.trim()) || pasta || estado);
    if (limpar) limpar.hidden = !filtrosLigados;
    if (limparNome) limparNome.hidden = !(nome && nome.value);
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
  if (pastaCampo) {
    pastaCampo.addEventListener("change", function () {
      pasta = pastaCampo.value || "";
      gravar();
      aplicar();
    });
  }
  document.querySelectorAll("[data-estado]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      estado = botao.getAttribute("data-estado") || "";
      gravar();
      aplicar();
    });
  });
  if (limpar) {
    limpar.addEventListener("click", function () {
      if (nome) nome.value = "";
      pasta = "";
      estado = "";
      if (pastaCampo) pastaCampo.value = "";
      gravar();
      aplicar();
    });
  }

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
          texto(linha, "[data-percent]", item.progress_label);
          texto(linha, "[data-eta]", item.eta ? "· " + item.eta : "");
          var barra = linha.querySelector("progress.torrent-meter");
          if (barra) {
            barra.value = item.progress || 0;
            barra.hidden = !item.progress || item.progress >= 100;
          }
        }
        aplicar();
        if (!dados.active) alvo.removeAttribute("data-torrent-poll");
      })
      .catch(function () {});
  }, 5000);
})();
