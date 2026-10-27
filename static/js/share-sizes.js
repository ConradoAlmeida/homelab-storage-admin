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

  async function loadSizes() {
    try {
      const response = await fetch(endpoint, {
        headers: {"Accept": "application/json"},
        cache: "no-store"
      });
      if (!response.ok) return;
      const data = await response.json();
      const byName = new Map((data.shares || []).map((item) => [item.name, item]));
      document.querySelectorAll("tr[data-share]").forEach((row) => {
        const item = byName.get(row.dataset.share);
        if (!item) return;
        const size = row.querySelector("[data-size]");
        const snapSize = row.querySelector("[data-snap-size]");
        const total = row.querySelector("[data-total] strong");
        if (size) size.textContent = fmtBytes(item.size);
        if (snapSize) snapSize.textContent = fmtBytes(item.size_snapshots);
        if (total) total.textContent = fmtBytes(item.size_total);
      });
    } catch (error) {
      // Mantem os placeholders; o dashboard continua utilizavel.
    }
  }

  loadSizes();
})();
