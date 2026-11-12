(function () {
  function normalizar(value) {
    return (value || "")
      .toLocaleLowerCase("pt-BR")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  document.querySelectorAll("[data-table-toolbar]").forEach(function (toolbar) {
    const table = document.querySelector(toolbar.dataset.tableToolbar || "");
    if (!table || !table.tBodies.length) return;

    const rows = Array.from(table.tBodies[0].rows).filter(function (row) {
      return !row.hasAttribute("data-table-empty");
    });
    const search = toolbar.querySelector("[data-table-search]");
    const selects = Array.from(toolbar.querySelectorAll("[data-table-filter]"));
    const count = toolbar.querySelector("[data-table-count]");
    const clear = toolbar.querySelector("[data-table-clear]");
    const total = rows.length;

    if (!table.tHead || !table.tHead.rows.length) return;
    const colunas = table.tHead.rows[0].cells.length;
    let empty = table.querySelector("[data-table-empty]");
    if (!empty) {
      empty = document.createElement("tr");
      empty.setAttribute("data-table-empty", "");
      empty.hidden = true;
      const cell = document.createElement("td");
      cell.colSpan = colunas;
      cell.className = "empty";
      cell.textContent = "Nenhum item corresponde ao filtro.";
      empty.appendChild(cell);
      table.tBodies[0].appendChild(empty);
    }

    function aplicar() {
      const termo = normalizar(search ? search.value.trim() : "");
      const filtros = selects
        .map(function (select) {
          return {
            coluna: Number(select.dataset.column || -1),
            valor: normalizar(select.value.trim()),
          };
        })
        .filter(function (filtro) {
          return filtro.coluna >= 0 && filtro.valor;
        });

      let visiveis = 0;
      rows.forEach(function (row) {
        const texto = normalizar(row.textContent);
        const celulas = row.cells;
        const combinaTexto = !termo || texto.includes(termo);
        const combinaFiltros = filtros.every(function (filtro) {
          const celula = celulas[filtro.coluna];
          return celula && normalizar(celula.textContent).includes(filtro.valor);
        });
        const visivel = combinaTexto && combinaFiltros;
        row.hidden = !visivel;
        if (visivel) visiveis += 1;
      });

      empty.hidden = visiveis !== 0;
      if (count) count.textContent = visiveis + " de " + total;
    }

    if (search) search.addEventListener("input", aplicar);
    selects.forEach(function (select) {
      select.addEventListener("change", aplicar);
    });
    if (clear) {
      clear.addEventListener("click", function () {
        if (search) search.value = "";
        selects.forEach(function (select) {
          select.value = "";
        });
        aplicar();
      });
    }
    aplicar();
  });
})();
