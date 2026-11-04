(function () {
  const marker = document.querySelector("[data-share-sizes-endpoint]");
  if (!marker) return;
  const endpoint = marker.dataset.shareSizesEndpoint;
  if (!endpoint) return;

  function fmtBytes(bytes) {
    if (bytes === null || bytes === undefined) return "—";
    let value = Number(bytes);
    if (!Number.isFinite(value)) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    return value.toFixed(index > 1 ? 1 : 0) + " " + units[index];
  }

  function stopSpinners() {
    document.querySelectorAll("[data-size], [data-snap-size], [data-total] strong").forEach((cell) => {
      if (cell.querySelector(".spinner")) cell.textContent = "—";
    });
  }

  let stopped = false;
  window.addEventListener("pagehide", function () {
    stopped = true;
  });

  function paint(data) {
    const byName = new Map((data.shares || []).map((item) => [item.name, item]));
    let snapTotal = 0;
    let sawSnap = false;
    document.querySelectorAll("[data-share]").forEach((row) => {
      const item = byName.get(row.dataset.share);
      if (!item) return;
      const size = row.matches("[data-size]") ? row : row.querySelector("[data-size]");
      const snapSize = row.matches("[data-snap-size]") ? row : row.querySelector("[data-snap-size]");
      const total = row.querySelector("[data-total] strong");
      if (size) size.textContent = fmtBytes(item.size);
      if (snapSize) {
        snapSize.textContent = fmtBytes(item.size_snapshots);
        if (Number.isFinite(Number(item.size_snapshots))) {
          snapTotal += Number(item.size_snapshots);
          sawSnap = true;
        }
      }
      if (total) total.textContent = fmtBytes(item.size_total);
    });
    const totalNode = document.querySelector("[data-snap-total]");
    if (totalNode && sawSnap) totalNode.textContent = fmtBytes(snapTotal);
  }

  async function loadSizes() {
    if (stopped) return;
    try {
      const response = await fetch(endpoint, {
        headers: {"Accept": "application/json"},
        cache: "no-store"
      });
      if (!response.ok) {
        stopSpinners();
        return;
      }
      const data = await response.json();
      if (data.shares && data.shares.length) paint(data);
      if (data.pending) {
        window.setTimeout(loadSizes, 2000);
        return;
      }
      if (data.error) stopSpinners();
    } catch (error) {
      if (!stopped) stopSpinners();
    }
  }

  loadSizes();
})();
