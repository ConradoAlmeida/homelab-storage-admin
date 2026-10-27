(function () {
  const card = document.getElementById("network-metrics");
  if (!card) return;
  const endpoint = card.dataset.endpoint;
  if (!endpoint) return;
  let busy = false;

  function fmtRate(mbps) {
    if (mbps === null || mbps === undefined) return "—";
    return mbps >= 1000
      ? (mbps / 1000).toFixed(2) + " Gbps"
      : Number(mbps).toFixed(1) + " Mbps";
  }

  async function tick() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const response = await fetch(endpoint, {
        headers: {"Accept": "application/json"},
        cache: "no-store"
      });
      if (!response.ok) throw new Error("http");
      const data = await response.json();
      const net = data.active;
      if (!net) throw new Error("sem interface");
      document.getElementById("net-iface").textContent = net.name;
      document.getElementById("net-state").textContent =
        net.state + (net.ssid ? " · " + net.ssid : "");
      document.getElementById("net-rx").textContent = fmtRate(net.rx_mbps);
      document.getElementById("net-rx-sub").textContent =
        Number(net.rx_mb_s).toFixed(2) + " MB/s";
      document.getElementById("net-tx").textContent = fmtRate(net.tx_mbps);
      document.getElementById("net-tx-sub").textContent =
        Number(net.tx_mb_s).toFixed(2) + " MB/s";
      document.getElementById("net-link").textContent =
        net.speed_mbps
          ? net.speed_mbps + " Mbps"
          : net.link_rx_mbps
            ? net.link_rx_mbps + " Mbps"
            : "—";
      document.getElementById("net-signal").textContent =
        net.signal_dbm !== null && net.signal_dbm !== undefined
          ? net.signal_dbm + " dBm"
          : (net.mac || "—");
    } catch (error) {
      const state = document.getElementById("net-state");
      if (state) state.textContent = "indisponível";
    } finally {
      busy = false;
    }
  }

  tick();
  setInterval(tick, 3000);
})();
