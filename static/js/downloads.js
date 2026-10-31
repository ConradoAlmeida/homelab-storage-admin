(function () {
  var alvo = document.querySelector("[data-torrent-poll]");
  if (!alvo) return;
  var url = alvo.getAttribute("data-torrent-poll");

  function texto(linha, seletor, valor) {
    var campo = linha.querySelector(seletor);
    if (campo) campo.textContent = valor || "";
  }

  var timer = window.setInterval(function () {
    if (!alvo.getAttribute("data-torrent-poll")) {
      window.clearInterval(timer);
      return;
    }
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("status");
        return resposta.json();
      })
      .then(function (dados) {
        var torrents = dados.torrents || [];
        var linhas = alvo.querySelectorAll("tr[data-hash]");
        if (linhas.length !== torrents.length) {
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
          texto(linha, "[data-state]", item.state_label);
          texto(linha, "[data-speed]", item.speed);
          texto(linha, "[data-percent]", item.progress_label);
          texto(linha, "[data-eta]", item.eta ? "· " + item.eta : "");
        }
        if (!dados.active) {
          alvo.removeAttribute("data-torrent-poll");
          window.clearInterval(timer);
        }
      })
      .catch(function () {});
  }, 5000);
})();
