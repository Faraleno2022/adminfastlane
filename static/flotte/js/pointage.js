// Enregistrement AJAX des cellules de pointage + mise à jour des totaux.
(function () {
  var url = window.PTG_URL, csrf = window.PTG_CSRF;
  if (!url) return;

  function colorerCellule(cell, statut) {
    cell.className = cell.className.replace(/\bst-\w*\b/g, "").trim();
    cell.classList.add("cell");
    if (cell.dataset.weekend === "1") cell.classList.add("weekend");
    cell.classList.add("st-" + statut);
  }

  function majTotaux(tr, d) {
    var set = function (sel, val) {
      var el = tr.querySelector(sel);
      if (el) el.textContent = val;
    };
    set(".tot-presence", d.nb_presence);
    set(".tot-absence", d.nb_absence);
    set(".tot-conge", d.nb_conge);
    set(".tot-mission", d.nb_mission);
    set(".tot-repos", d.nb_repos);
    set(".tot-maladie", d.nb_maladie);
    set(".tot-retard", d.nb_retard);
    set(".tot-sanction", d.nb_sanction);
  }

  document.querySelectorAll(".ptg-select").forEach(function (sel) {
    // Mémorise le week-end pour recolorer correctement.
    var td = sel.closest("td");
    if (td.classList.contains("weekend")) td.dataset.weekend = "1";

    sel.addEventListener("change", function () {
      var tr = sel.closest("tr");
      var employe = tr.dataset.employe;
      var date = sel.dataset.date;
      var statut = sel.value;
      var td = sel.closest("td");
      sel.disabled = true;

      var body = new URLSearchParams();
      body.append("employe", employe);
      body.append("date", date);
      body.append("statut", statut);

      fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          sel.disabled = false;
          if (!res.ok || !res.j.ok) {
            alert("Enregistrement impossible : " + (res.j.erreur || "erreur"));
            return;
          }
          colorerCellule(td, statut);
          majTotaux(tr, res.j);
        })
        .catch(function () {
          sel.disabled = false;
          // Hors-ligne : la saisie locale reste possible côté client Django ;
          // ici (serveur distant) on prévient simplement.
          alert("Réseau indisponible. Réessayez quand la connexion revient.");
        });
    });
  });
})();
