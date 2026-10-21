// Graphiques de la page Analyses par véhicule.
(function () {
  var A = window.ANALYSE || {};
  function ctx(id) { var e = document.getElementById(id); return e ? e.getContext("2d") : null; }

  if (A.coutKm && ctx("c-cout-km")) {
    new Chart(ctx("c-cout-km"), {
      type: "bar",
      data: { labels: A.coutKm.labels,
        datasets: [{ label: "Coût total / km", data: A.coutKm.valeurs, backgroundColor: "#dc3545" }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } } },
    });
  }
  if (A.conso && ctx("c-conso")) {
    new Chart(ctx("c-conso"), {
      type: "bar",
      data: { labels: A.conso.labels,
        datasets: [{ label: "L/100 km", data: A.conso.valeurs, backgroundColor: "#0d6efd" }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } } },
    });
  }
})();
