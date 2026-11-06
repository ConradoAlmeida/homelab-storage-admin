/**
 * Cliente mínimo para o terminal via /sistema/terminal/io/ (JSON + base64).
 * Remove sequências ANSI comuns para exibir texto em um <pre>.
 */
(function () {
  var root = document.querySelector("[data-terminal-app]");
  if (!root) return;

  var pre = root.querySelector("[data-terminal-screen]");
  var status = root.querySelector("[data-terminal-status]");
  var endpoint = root.getAttribute("data-endpoint");
  if (!pre || !endpoint) return;

  var sessionId = "";
  var pollTimer = null;
  var pendingInput = new Uint8Array(0);

  function setStatus(t) {
    if (status) status.textContent = t || "";
  }

  function stripAnsi(bytes) {
    var t = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    t = t.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "");
    t = t.replace(/\x1b\][^\x07]*\x07/g, "");
    return t;
  }

  function appendOutput(b64) {
    if (!b64) return;
    try {
      var bin = atob(b64);
      var bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      var texto = stripAnsi(bytes);
      pre.textContent += texto;
      pre.scrollTop = pre.scrollHeight;
    } catch (e) {
      /* ignore */
    }
  }

  function getCookie(name) {
    var v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  function mergePending(extra) {
    if (!extra.length) return;
    var out = new Uint8Array(pendingInput.length + extra.length);
    out.set(pendingInput, 0);
    out.set(extra, pendingInput.length);
    pendingInput = out;
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

  function encodeB64(u8) {
    var bin = "";
    for (var i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
    return btoa(bin);
  }

  function ioLoop() {
    if (!sessionId) return;
    var enviar = pendingInput;
    pendingInput = new Uint8Array(0);
    postJson({
      op: "io",
      session_id: sessionId,
      input_b64: enviar.length ? encodeB64(enviar) : "",
    })
      .then(function (res) {
        if (!res.ok) throw new Error(res.error || "io");
        appendOutput(res.data && res.data.output_b64);
      })
      .catch(function () {
        setStatus("Sessão encerrada ou agente indisponível.");
        sessionId = "";
        if (pollTimer) clearInterval(pollTimer);
      });
  }

  function openSession() {
    setStatus("Abrindo sessão…");
    postJson({ op: "open", cols: 100, rows: 28 })
      .then(function (res) {
        if (!res.ok) throw new Error(res.error || "open");
        sessionId = res.data.session_id || "";
        if (!sessionId) throw new Error("sem id");
        setStatus("Conectado. Inatividade encerra em 15 minutos.");
        pollTimer = window.setInterval(ioLoop, 300);
        ioLoop();
      })
      .catch(function (e) {
        setStatus("Não foi possível abrir: " + (e.message || e));
      });
  }

  pre.tabIndex = 0;
  pre.addEventListener("keydown", function (ev) {
    if (!sessionId) return;
    var extra;
    if (ev.key === "Enter") extra = new Uint8Array([13]);
    else if (ev.key === "Backspace") extra = new Uint8Array([127]);
    else if (ev.key === "Tab") extra = new Uint8Array([9]);
    else if (ev.key.length === 1) {
      extra = new TextEncoder().encode(ev.key);
    } else if (ev.key === "ArrowUp") extra = new TextEncoder().encode("\x1b[A");
    else if (ev.key === "ArrowDown") extra = new TextEncoder().encode("\x1b[B");
    else if (ev.key === "ArrowRight") extra = new TextEncoder().encode("\x1b[C");
    else if (ev.key === "ArrowLeft") extra = new TextEncoder().encode("\x1b[D");
    else return;
    ev.preventDefault();
    mergePending(extra);
  });

  window.addEventListener("beforeunload", function () {
    if (pollTimer) clearInterval(pollTimer);
  });

  window.addEventListener("pagehide", function () {
    if (!sessionId) return;
    try {
      fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ op: "close", session_id: sessionId }),
        keepalive: true,
        credentials: "same-origin",
      });
    } catch (e) {
      /* ignore */
    }
  });

  openSession();
})();
