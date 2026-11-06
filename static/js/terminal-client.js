/**
 * Terminal no navegador. O xterm trata backspace, setas e o eco do PTY.
 * Cada tecla sai na hora; a leitura seguinte não espera um intervalo fixo.
 */
(function () {
  var root = document.querySelector("[data-terminal-app]");
  if (!root || typeof Terminal === "undefined") return;

  var tela = root.querySelector("[data-terminal-screen]");
  var status = root.querySelector("[data-terminal-status]");
  var form = root.querySelector("[data-terminal-unlock]");
  var sessao = root.querySelector("[data-terminal-session]");
  var endpoint = root.getAttribute("data-endpoint");
  if (!tela || !form || !endpoint) return;

  var sessionId = "";
  var pending = "";
  var ocupado = false;
  var encerrado = false;
  var term = null;

  function setStatus(t) {
    if (status) status.textContent = t || "";
  }

  function getCookie(name) {
    var v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  function postJson(body) {
    return fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify(body),
      credentials: "same-origin",
    }).then(function (r) {
      return r.json();
    });
  }

  function encodeTexto(str) {
    var bytes = new TextEncoder().encode(str);
    var bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }

  function decodeSaida(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }

  function falhou(msg) {
    encerrado = true;
    sessionId = "";
    setStatus(msg || "Sessão encerrada ou agente indisponível.");
  }

  function bombear() {
    if (!sessionId || ocupado || encerrado) return;
    ocupado = true;
    var enviar = pending;
    pending = "";
    postJson({
      op: "io",
      session_id: sessionId,
      input_b64: enviar ? encodeTexto(enviar) : "",
    })
      .then(function (res) {
        ocupado = false;
        if (!sessionId || encerrado) return;
        if (!res.ok) throw new Error(res.error || "io");
        var b64 = res.data && res.data.output_b64;
        if (b64 && term) term.write(decodeSaida(b64));
        if (pending) bombear();
        else window.setTimeout(bombear, b64 ? 16 : 40);
      })
      .catch(function () {
        ocupado = false;
        falhou();
      });
  }

  function openSession(usuario, senha) {
    setStatus("Conferindo a senha sudo…");
    if (!term) {
      term = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        theme: { background: "#0b0f14", foreground: "#e6edf3", cursor: "#e6edf3" },
      });
      term.open(tela);
      term.onData(function (data) {
        if (!sessionId) return;
        pending += data;
        bombear();
      });
    }
    postJson({
      op: "open",
      cols: term.cols || 100,
      rows: term.rows || 28,
      user: usuario,
      password: senha,
    })
      .then(function (res) {
        if (!res.ok) throw new Error(res.error || "open");
        sessionId = res.data.session_id || "";
        if (!sessionId) throw new Error("sem id");
        encerrado = false;
        form.hidden = true;
        if (sessao) sessao.hidden = false;
        setStatus("Conectado como " + usuario + ". Inatividade encerra em 15 minutos.");
        term.focus();
        bombear();
      })
      .catch(function (e) {
        setStatus("Não foi possível abrir: " + (e.message || e));
      });
  }

  window.addEventListener("pagehide", function () {
    if (!sessionId) return;
    var sid = sessionId;
    sessionId = "";
    encerrado = true;
    try {
      fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ op: "close", session_id: sid }),
        keepalive: true,
        credentials: "same-origin",
      });
    } catch (e) {
      /* ignore */
    }
  });

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var usuario = (form.querySelector("[name=user]").value || "").trim();
    var campo = form.querySelector("[name=password]");
    var senha = campo.value || "";
    campo.value = "";
    if (!usuario || !senha) {
      setStatus("Informe o usuário Linux e a senha sudo.");
      return;
    }
    openSession(usuario, senha);
  });
})();
