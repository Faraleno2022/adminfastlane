// Rendu des graphiques du tableau de bord (Chart.js, vendorisé en local).
(function () {
  var D = window.DASH || {};
  var paletteDep = ["#dc3545", "#fd7e14", "#ffc107", "#6c757d"];
  var paletteRec = ["#198754", "#20c997", "#0dcaf0"];

  function ctx(id) {
    var el = document.getElementById(id);
    return el ? el.getContext("2d") : null;
  }
  function vide(serie) {
    return !serie || !serie.valeurs || serie.valeurs.every(function (v) { return !v; });
  }
  function camembert(id, serie, palette) {
    if (!serie || !ctx(id)) return;
    new Chart(ctx(id), {
      type: "doughnut",
      data: {
        labels: serie.labels,
        datasets: [{ data: serie.valeurs, backgroundColor: palette }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
          title: { display: vide(serie), text: "Aucune donnée sur la période" },
        },
      },
    });
  }

  camembert("c-repartition", D.repartition, paletteDep);
  camembert("c-recettes", D.recettes, paletteRec);

  // Barres : charges par véhicule
  if (D.vehicules && ctx("c-vehicules")) {
    new Chart(ctx("c-vehicules"), {
      type: "bar",
      data: {
        labels: D.vehicules.labels,
        datasets: [{ label: "Charges", data: D.vehicules.valeurs, backgroundColor: "#dc3545" }],
      },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } } },
    });
  }

  // Barres : voyages par véhicule
  if (D.voyages && ctx("c-voyages")) {
    new Chart(ctx("c-voyages"), {
      type: "bar",
      data: {
        labels: D.voyages.labels,
        datasets: [{ label: "Voyages", data: D.voyages.valeurs, backgroundColor: "#198754" }],
      },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } } },
    });
  }

  // Histogramme mensuel : recettes vs dépenses
  if (D.mois && ctx("c-mois")) {
    new Chart(ctx("c-mois"), {
      type: "bar",
      data: {
        labels: D.mois.labels,
        datasets: [
          { label: "Recettes", data: D.mois.recettes, backgroundColor: "#198754" },
          { label: "Dépenses", data: D.mois.depenses, backgroundColor: "#dc3545" },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } } },
    });
  }
})();
