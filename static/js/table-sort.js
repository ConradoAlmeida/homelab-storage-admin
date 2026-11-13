(function () {
  function texto(value) {
    return (value || "").trim();
  }

  document.querySelectorAll("table[data-table-sortable]").forEach(function (table) {
    if (!table.tHead || !table.tBodies.length) return;
    const body = table.tBodies[0];
    const headers = Array.from(table.tHead.rows[0].cells);
    const buttons = headers
      .map(function (cell) {
        return cell.querySelector("button.th-sort");
      })
      .filter(Boolean);

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        const column = Number(button.dataset.sort);
        if (Number.isNaN(column)) return;
        const direction = button.getAttribute("aria-sort") === "ascending"
          ? "descending"
          : "ascending";

        buttons.forEach(function (other) {
          other.removeAttribute("aria-sort");
        });
        button.setAttribute("aria-sort", direction);

        const rows = Array.from(body.rows).filter(function (row) {
          return !row.hasAttribute("data-table-empty");
        });
        rows.sort(function (a, b) {
          const left = texto(a.cells[column] && a.cells[column].textContent);
          const right = texto(b.cells[column] && b.cells[column].textContent);
          const result = left.localeCompare(right, "pt-BR", {
            numeric: true,
            sensitivity: "base",
          });
          return direction === "ascending" ? result : -result;
        });
        rows.forEach(function (row) {
          body.appendChild(row);
        });
        const empty = body.querySelector("[data-table-empty]");
        if (empty) body.appendChild(empty);
      });
    });
  });
})();
