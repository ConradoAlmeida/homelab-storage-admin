(function () {
  var secao = document.querySelector("[data-torrent-status]");
  var filtros = document.querySelector("[data-torrent-filters]");
  var tabela = document.querySelector("[data-torrent-table]");
  var nome = document.getElementById("torrent-filtro-nome");
  var limparNome = document.querySelector("[data-clear-nome]");
  var pastaCampo = document.getElementById("torrent-filtro-pasta");
  var limpar = document.querySelector("[data-torrent-clear]");
  var vazio = document.querySelector("[data-torrent-empty]");
  var contagem = document.querySelector("[data-torrent-count]");
  var botaoAtualizar = document.querySelector("[data-torrent-refresh]");
  var botaoAuto = document.querySelector("[data-torrent-auto]");
  var erroRefresh = document.querySelector("[data-torrent-refresh-erro]");
  var moldeLinha = document.getElementById("torrent-linha");
  var chave = "torrent-tabela";
  var chaveAuto = "torrent-auto";
  var numericos = { progress: true, download: true, upload: true, size: true };
  var ordem = "";
  var sentido = "asc";
  var pasta = "";
  var estado = "";
  var intervalo = null;
  var pedidoAberto = false;
  var hashRe = /^[0-9a-f]{40,64}$/i;

  function linhas() {
    if (!tabela) return [];
    return Array.prototype.slice.call(tabela.querySelectorAll("tr[data-hash]"));
  }

  function corpoTabela() {
    return tabela ? tabela.querySelector("tbody") : null;
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

  function selecaoNaTabela(corpo) {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !corpo) return false;
    return corpo.contains(sel.anchorNode) || corpo.contains(sel.focusNode);
  }

  function limparSelecaoIndevida(corpo, tinhaSelecao) {
    if (tinhaSelecao) return;
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !corpo) return;
    if (corpo.contains(sel.anchorNode) || corpo.contains(sel.focusNode)) sel.removeAllRanges();
  }

  function textoIgual(linha, seletor, valor) {
    var campo = linha.querySelector(seletor);
    if (!campo) return;
    var v = valor || "";
    if (campo.textContent !== v) campo.textContent = v;
  }

  function atributoIgual(linha, nomeAtributo, valor) {
    var v = valor == null ? "" : String(valor);
    if (linha.getAttribute(nomeAtributo) !== v) linha.setAttribute(nomeAtributo, v);
  }

  function classeEstado(item) {
    var state = item.state || "";
    var rotulo = item.state_label || "";
    if (state === "error" || state === "missingFiles") return "off";
    if (rotulo === "lendo metadados") return "meta";
    if (rotulo === "baixando") return "info";
    if (rotulo === "aguardando" || rotulo === "na fila" || item.can_resume) return "warn";
    if (rotulo === "concluído" || rotulo === "enviando") return "ok";
    return "";
  }

  function atualizarClasseStatus(linha, item) {
    var campo = linha.querySelector("[data-state]");
    if (!campo) return;
    var extra = classeEstado(item);
    campo.className = extra ? "status " + extra : "status";
  }

  function atualizarForms(linha, item) {
    var hash = item.hash || "";
    linha.querySelectorAll('input[name="hash"]').forEach(function (campo) {
      if (campo.value !== hash) campo.value = hash;
    });
    var pausa = linha.querySelector("[data-torrent-pause]");
    var retoma = linha.querySelector("[data-torrent-resume]");
    if (pausa) pausa.hidden = !item.can_pause;
    if (retoma) retoma.hidden = !item.can_resume;
    var apagar = item.can_delete !== false;
    linha.querySelectorAll("[data-torrent-delete]").forEach(function (form) {
      form.hidden = !apagar;
    });
    var aviso = linha.querySelector("[data-torrent-delete-msg]");
    if (aviso) {
      var texto = apagar ? "" : item.delete_blocked_message || "";
      aviso.textContent = texto;
      aviso.hidden = !texto;
    }
  }

  function preencherLinha(linha, item) {
    if (!item || !hashRe.test(item.hash || "")) return;
    atributoIgual(linha, "data-hash", item.hash);
    atributoIgual(linha, "data-state-code", item.state || "");
    atributoIgual(linha, "data-name", item.name || "");
    atributoIgual(linha, "data-library", item.library || "");
    atributoIgual(linha, "data-state-label", item.state_label || "");
    atributoIgual(linha, "data-progress", String(item.progress || 0));
    atributoIgual(linha, "data-download", String(item.download_bps || 0));
    atributoIgual(linha, "data-upload", String(item.upload_bps || 0));
    atributoIgual(linha, "data-size", String(item.size_bytes || 0));
    textoIgual(linha, "[data-name]", item.name);
    textoIgual(linha, "[data-size-label]", item.size);
    textoIgual(linha, "[data-library-label]", item.library);
    textoIgual(linha, "[data-state]", item.state_label);
    textoIgual(linha, "[data-download]", item.download_speed);
    textoIgual(linha, "[data-percent]", item.progress_label);
    textoIgual(linha, "[data-eta]", item.eta ? "· " + item.eta : "");
    atualizarClasseStatus(linha, item);
    atualizarForms(linha, item);
    var barra = linha.querySelector("progress.torrent-meter");
    if (barra) {
      var progresso = item.progress || 0;
      if (Number(barra.value) !== progresso) barra.value = progresso;
      barra.hidden = !progresso || progresso >= 100;
    }
  }

  function novaLinha(item) {
    if (!moldeLinha || !moldeLinha.content) return null;
    var no = moldeLinha.content.firstElementChild;
    if (!no) return null;
    var linha = no.cloneNode(true);
    preencherLinha(linha, item);
    return linha;
  }

  function mensagemVazia(total) {
    if (total === 0) return "Nenhum torrent nas pastas do Jellyfin.";
    var filtrosLigados = Boolean((nome && nome.value.trim()) || pasta || estado);
    return filtrosLigados ? "Nenhum torrent com esse filtro." : "Nenhum torrent nas pastas do Jellyfin.";
  }

  function aplicar(opcoes) {
    if (!tabela) return;
    var corpo = corpoTabela();
    opcoes = opcoes || {};
    var tinhaSelecao = opcoes.tinhaSelecao != null ? opcoes.tinhaSelecao : selecaoNaTabela(corpo);
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
    if (corpo) {
      visiveis.forEach(function (linha, idx) {
        var proximo = visiveis[idx + 1] || null;
        if (linha.nextElementSibling === proximo) return;
        corpo.insertBefore(linha, proximo);
      });
    }
    if (vazio) {
      vazio.hidden = visiveis.length !== 0;
      var msg = mensagemVazia(todas.length);
      if (vazio.textContent !== msg) vazio.textContent = msg;
    }
    if (contagem) {
      var total = todas.length;
      var palavra = total === 1 ? "torrent" : "torrents";
      var textoContagem = visiveis.length === total
        ? total + " " + palavra
        : visiveis.length + " de " + total + " " + palavra;
      if (contagem.textContent !== textoContagem) contagem.textContent = textoContagem;
    }
    var filtrosLigados = Boolean((nome && nome.value.trim()) || pasta || estado);
    if (limpar) limpar.hidden = !filtrosLigados;
    if (limparNome) limparNome.hidden = !(nome && nome.value);
    cabeçalhos();
    limparSelecaoIndevida(corpo, tinhaSelecao);
  }

  function sincronizarTorrents(torrents) {
    if (!tabela) return;
    var corpo = corpoTabela();
    if (!corpo) return;
    var tinhaSelecao = selecaoNaTabela(corpo);
    var mapa = {};
    linhas().forEach(function (linha) {
      mapa[linha.getAttribute("data-hash") || ""] = linha;
    });
    var vistos = {};
    torrents.forEach(function (item, indice) {
      if (!hashRe.test(item.hash || "")) return;
      vistos[item.hash] = true;
      var linha = mapa[item.hash];
      if (!linha) {
        linha = novaLinha(item);
        if (!linha) return;
        if (!linha.hasAttribute("data-seq")) linha.setAttribute("data-seq", String(indice));
        corpo.appendChild(linha);
        mapa[item.hash] = linha;
      } else {
        preencherLinha(linha, item);
      }
    });
    Object.keys(mapa).forEach(function (hash) {
      if (vistos[hash]) return;
      if (mapa[hash] && mapa[hash].parentNode) mapa[hash].parentNode.removeChild(mapa[hash]);
    });
    aplicar({ tinhaSelecao: tinhaSelecao });
  }

  function mostrarErroRefresh(mensagem) {
    if (!erroRefresh) return;
    if (mensagem) {
      erroRefresh.textContent = mensagem;
      erroRefresh.hidden = false;
    } else {
      erroRefresh.textContent = "";
      erroRefresh.hidden = true;
    }
  }

  function atualizar() {
    if (!secao || pedidoAberto) return;
    var url = secao.getAttribute("data-torrent-status");
    if (!url) return;
    pedidoAberto = true;
    secao.setAttribute("aria-busy", "true");
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("Não foi possível atualizar o andamento (HTTP " + resposta.status + ").");
        return resposta.json();
      })
      .then(function (dados) {
        mostrarErroRefresh("");
        sincronizarTorrents(dados.torrents || []);
      })
      .catch(function (erro) {
        mostrarErroRefresh(erro && erro.message ? erro.message : "Não foi possível atualizar o andamento.");
      })
      .finally(function () {
        pedidoAberto = false;
        secao.removeAttribute("aria-busy");
      });
  }

  function autoLigado() {
    return botaoAuto && botaoAuto.getAttribute("aria-pressed") === "true";
  }

  function gravarAuto(ligado) {
    try {
      window.sessionStorage.setItem(chaveAuto, ligado ? "1" : "0");
    } catch (erro) {
      /* preferência opcional */
    }
  }

  function lerAutoSalvo() {
    try {
      return window.sessionStorage.getItem(chaveAuto);
    } catch (erro) {
      return null;
    }
  }

  function definirAuto(ligado) {
    if (!botaoAuto) return;
    botaoAuto.setAttribute("aria-pressed", ligado ? "true" : "false");
    botaoAuto.classList.toggle("is-on", ligado);
    gravarAuto(ligado);
    if (intervalo) {
      window.clearInterval(intervalo);
      intervalo = null;
    }
    if (ligado) intervalo = window.setInterval(atualizar, 5000);
  }

  function autoPadrao() {
    var salvo = lerAutoSalvo();
    if (salvo === "1") return true;
    if (salvo === "0") return false;
    return Boolean(secao && secao.hasAttribute("data-torrent-active"));
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

  if (botaoAtualizar) {
    botaoAtualizar.addEventListener("click", function () {
      atualizar();
    });
  }
  if (botaoAuto) {
    botaoAuto.addEventListener("click", function () {
      definirAuto(!autoLigado());
    });
    definirAuto(autoPadrao());
  }
})();
