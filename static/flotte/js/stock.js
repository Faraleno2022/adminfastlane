// Graphique de répartition du stock par catégorie.
(function () {
  var D = window.STOCK_CAT;
  var el = document.getElementById("c-cat");
  if (!D || !el) return;
  var palette = ["#0d6efd", "#198754", "#ffc107", "#dc3545", "#6c757d",
                 "#0dcaf0", "#6610f2", "#fd7e14", "#20c997", "#d63384"];
  new Chart(el.getContext("2d"), {
    type: "bar",
    data: { labels: D.labels,
      datasets: [{ label: "Quantité", data: D.valeurs, backgroundColor: palette }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } } },
  });
})();
