"""
Agrégations pour les tableaux de bord.

Remplace les tableaux croisés dynamiques et formules (cassées) du classeur
Excel par des calculs fiables via l'ORM Django. Les fonctions acceptent un
filtre d'année et, le cas échéant, de mois.

Classement repris de la feuille « TB_Gestion » du classeur d'origine :
- DÉPENSES  : carburant (véhicules + Poclain), entretien, autres dépenses ;
- RECETTES  : voyages des camions, montant payé du porte-char, chargements
  du Poclain ;
- RÉSULTAT  : recettes − dépenses.
"""
from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear

from .models import (
    ActiviteEngin, AutreDepense, Entretien, PleinCarburant, TrajetPorteChar, Vehicule, Voyage,
)

MOIS_FR = [
    "Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin",
    "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc.",
]
MOIS_NOMS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

_DEC = DecimalField(max_digits=16, decimal_places=2)
ZERO = Decimal("0")


def _somme(qs, champ):
    return qs.aggregate(t=Coalesce(Sum(champ), Value(ZERO), output_field=_DEC))["t"]


def annees_disponibles():
    """Liste triée des années présentes dans les données."""
    annees = set()
    for model, champ in [
        (Entretien, "date"), (PleinCarburant, "date"), (Voyage, "date"),
        (ActiviteEngin, "date"), (TrajetPorteChar, "date"), (AutreDepense, "date"),
    ]:
        annees.update(
            model.objects.annotate(a=ExtractYear(champ))
            .values_list("a", flat=True)
            .distinct()
        )
    return sorted(a for a in annees if a)


def _filtrer(qs, annee, mois=None):
    if annee:
        qs = qs.filter(date__year=annee)
    if mois:
        qs = qs.filter(date__month=mois)
    return qs


def totaux(annee=None, mois=None):
    """
    Indicateurs de gestion (logique de la feuille TB_Gestion).

    Filtre facultatif par année et par mois.
    """
    ent = _filtrer(Entretien.objects, annee, mois)
    carb = _filtrer(PleinCarburant.objects, annee, mois)
    voy = _filtrer(Voyage.objects, annee, mois)
    poc = _filtrer(ActiviteEngin.objects, annee, mois)
    pch = _filtrer(TrajetPorteChar.objects, annee, mois)
    dep = _filtrer(AutreDepense.objects, annee, mois)

    # --- Dépenses ---
    litres_vehicules = _somme(carb, "litres")
    litres_poclain = _somme(poc, "qte_carburant")
    carburant_vehicules = _somme(carb, "montant")
    carburant_poclain = _somme(poc, "montant_carburant")
    montant_entretien = _somme(ent, "montant_ttc")
    montant_autres = _somme(dep, "montant")

    depenses_carburant = carburant_vehicules + carburant_poclain
    depenses_entretien_autres = montant_entretien + montant_autres
    depenses_totales = depenses_carburant + depenses_entretien_autres

    # --- Recettes ---
    recettes_voyages = _somme(voy, "montant")
    recettes_portechar = _somme(pch, "montant_paye")
    recettes_poclain = _somme(poc, "montant_chargement")
    recettes_camions_portechar = recettes_voyages + recettes_portechar
    recettes_totales = recettes_camions_portechar + recettes_poclain

    return {
        # Dépenses
        "litres_vehicules": litres_vehicules,
        "litres_poclain": litres_poclain,
        "litres_carburant": litres_vehicules + litres_poclain,
        "carburant_vehicules": carburant_vehicules,
        "carburant_poclain": carburant_poclain,
        "depenses_carburant": depenses_carburant,
        "montant_entretien": montant_entretien,
        "montant_autres": montant_autres,
        "depenses_entretien_autres": depenses_entretien_autres,
        "depenses_totales": depenses_totales,
        # Recettes
        "recettes_voyages": recettes_voyages,
        "recettes_portechar": recettes_portechar,
        "recettes_camions_portechar": recettes_camions_portechar,
        "recettes_poclain": recettes_poclain,
        "recettes_totales": recettes_totales,
        # Résultat
        "resultat": recettes_totales - depenses_totales,
        # Activité
        "nb_voyages": voy.aggregate(t=Coalesce(Sum("nb_voyage"), 0))["t"],
        "nb_chargements": poc.aggregate(t=Coalesce(Sum("nb_chargement"), 0))["t"],
        "nb_vehicules": Vehicule.objects.count(),
    }


def gestion(annee, mois):
    """
    Tableau de bord de gestion : chaque indicateur en mensuel ET en annuel
    (reproduit la feuille « TB_Gestion »).
    """
    m = totaux(annee, mois)
    a = totaux(annee)
    lignes_depenses = [
        ("Carburant total consommé (L)", m["litres_carburant"], a["litres_carburant"], "litres"),
        ("Total dépenses carburant", m["depenses_carburant"], a["depenses_carburant"], "montant"),
        ("Charges d'entretien / Autres", m["depenses_entretien_autres"], a["depenses_entretien_autres"], "montant"),
        ("Montant global dépenses", m["depenses_totales"], a["depenses_totales"], "total"),
    ]
    lignes_recettes = [
        ("Recette des camions et porte-char", m["recettes_camions_portechar"], a["recettes_camions_portechar"], "montant"),
        ("Recette Poclain", m["recettes_poclain"], a["recettes_poclain"], "montant"),
        ("Recette globale", m["recettes_totales"], a["recettes_totales"], "total"),
    ]
    return {
        "annee": annee,
        "mois": mois,
        "mois_nom": MOIS_NOMS[mois - 1] if mois else "",
        "depenses": lignes_depenses,
        "recettes": lignes_recettes,
        "resultat_mensuel": m["resultat"],
        "resultat_annuel": a["resultat"],
    }


def repartition_depenses(annee=None, mois=None):
    """Montant par catégorie de dépense (camembert)."""
    t = totaux(annee, mois)
    return {
        "labels": ["Entretien", "Carburant véhicules", "Carburant Poclain", "Autres dépenses"],
        "valeurs": [
            float(t["montant_entretien"]),
            float(t["carburant_vehicules"]),
            float(t["carburant_poclain"]),
            float(t["montant_autres"]),
        ],
    }


def repartition_recettes(annee=None, mois=None):
    """Montant par source de recette (camembert)."""
    t = totaux(annee, mois)
    return {
        "labels": ["Voyages camions", "Porte-char", "Chargements Poclain"],
        "valeurs": [
            float(t["recettes_voyages"]),
            float(t["recettes_portechar"]),
            float(t["recettes_poclain"]),
        ],
    }


def serie_mensuelle(qs, champ, annee):
    """Liste des 12 sommes mensuelles d'un champ pour une année."""
    data = {i: ZERO for i in range(1, 13)}
    rows = (
        qs.filter(date__year=annee)
        .annotate(m=ExtractMonth("date"))
        .values("m")
        .annotate(t=Coalesce(Sum(champ), Value(ZERO), output_field=_DEC))
    )
    for r in rows:
        data[r["m"]] = r["t"]
    return [data[i] for i in range(1, 13)]


def recettes_depenses_par_mois(annee):
    """Recettes vs dépenses par mois pour une année (histogramme)."""
    def add(*series):
        return [sum(v) for v in zip(*series)]

    depenses = add(
        serie_mensuelle(Entretien.objects, "montant_ttc", annee),
        serie_mensuelle(PleinCarburant.objects, "montant", annee),
        serie_mensuelle(ActiviteEngin.objects, "montant_carburant", annee),
        serie_mensuelle(AutreDepense.objects, "montant", annee),
    )
    recettes = add(
        serie_mensuelle(Voyage.objects, "montant", annee),
        serie_mensuelle(TrajetPorteChar.objects, "montant_paye", annee),
        serie_mensuelle(ActiviteEngin.objects, "montant_chargement", annee),
    )
    return {
        "labels": MOIS_FR,
        "depenses": [float(v) for v in depenses],
        "recettes": [float(v) for v in recettes],
    }


def charges_par_vehicule(annee=None):
    """Charges d'entretien + carburant par véhicule (barres)."""
    resultats = {}
    ent = _filtrer(Entretien.objects, annee).values("vehicule__immatriculation").annotate(
        t=Coalesce(Sum("montant_ttc"), Value(Decimal("0")), output_field=_DEC)
    )
    carb = _filtrer(PleinCarburant.objects, annee).values("vehicule__immatriculation").annotate(
        t=Coalesce(Sum("montant"), Value(Decimal("0")), output_field=_DEC)
    )
    for r in ent:
        resultats.setdefault(r["vehicule__immatriculation"] or "—", Decimal("0"))
        resultats[r["vehicule__immatriculation"] or "—"] += r["t"]
    for r in carb:
        resultats.setdefault(r["vehicule__immatriculation"] or "—", Decimal("0"))
        resultats[r["vehicule__immatriculation"] or "—"] += r["t"]
    items = sorted(resultats.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "labels": [k for k, _ in items],
        "valeurs": [float(v) for _, v in items],
    }


def _distances_par_vehicule(annee):
    """
    Estime la distance parcourue par véhicule (km max - km min observés),
    à partir des kilométrages saisis dans pleins, entretiens et voyages.
    """
    bornes = {}  # immat -> [min, max]

    def integrer(immat, valeur):
        if immat is None or valeur in (None, 0):
            return
        b = bornes.setdefault(immat, [valeur, valeur])
        b[0] = min(b[0], valeur)
        b[1] = max(b[1], valeur)

    sources = [
        (_filtrer(PleinCarburant.objects, annee), ["kilometrage"]),
        (_filtrer(Entretien.objects, annee), ["km_depart", "km_arrivee"]),
        (_filtrer(Voyage.objects, annee), ["km_depart", "km_arrivee"]),
    ]
    for qs, champs in sources:
        vals = qs.values_list("vehicule__immatriculation", *champs)
        for row in vals:
            immat = row[0]
            for v in row[1:]:
                integrer(immat, v)

    return {immat: (b[1] - b[0]) for immat, b in bornes.items() if b[1] > b[0]}


def analyse_vehicules(annee=None):
    """
    Tableau d'analyse par véhicule : distance, litres, L/100km, coûts au km.

    Renvoie une liste de dictionnaires triée par coût total au km décroissant.
    """
    distances = _distances_par_vehicule(annee)

    litres = {
        r["vehicule__immatriculation"]: r["l"]
        for r in _filtrer(PleinCarburant.objects, annee)
        .values("vehicule__immatriculation")
        .annotate(l=Coalesce(Sum("litres"), Value(Decimal("0")), output_field=_DEC))
    }
    cout_carb = {
        r["vehicule__immatriculation"]: r["m"]
        for r in _filtrer(PleinCarburant.objects, annee)
        .values("vehicule__immatriculation")
        .annotate(m=Coalesce(Sum("montant"), Value(Decimal("0")), output_field=_DEC))
    }
    cout_ent = {
        r["vehicule__immatriculation"]: r["m"]
        for r in _filtrer(Entretien.objects, annee)
        .values("vehicule__immatriculation")
        .annotate(m=Coalesce(Sum("montant_ttc"), Value(Decimal("0")), output_field=_DEC))
    }
    nb_voy = {
        r["vehicule__immatriculation"]: r["n"]
        for r in _filtrer(Voyage.objects, annee)
        .values("vehicule__immatriculation")
        .annotate(n=Coalesce(Sum("nb_voyage"), 0))
    }

    immats = set(litres) | set(cout_carb) | set(cout_ent) | set(nb_voy) | set(distances)
    lignes = []
    for immat in immats:
        if not immat:
            continue
        dist = distances.get(immat)
        l = float(litres.get(immat, 0) or 0)
        cc = float(cout_carb.get(immat, 0) or 0)
        ce = float(cout_ent.get(immat, 0) or 0)
        total = cc + ce
        lignes.append({
            "vehicule": immat,
            "distance": dist,
            "litres": l,
            "montant_carburant": cc,
            "montant_entretien": ce,
            "montant_total": total,
            "nb_voyages": nb_voy.get(immat, 0),
            "l_100km": round(l / dist * 100, 2) if dist else None,
            "cout_carburant_km": round(cc / dist, 2) if dist else None,
            "cout_entretien_km": round(ce / dist, 2) if dist else None,
            "cout_total_km": round(total / dist, 2) if dist else None,
        })
    lignes.sort(key=lambda x: (x["cout_total_km"] or 0, x["montant_total"]), reverse=True)
    return lignes


def voyages_par_vehicule(annee=None):
    """Nombre de voyages par véhicule (barres)."""
    rows = (
        _filtrer(Voyage.objects, annee)
        .values("vehicule__immatriculation")
        .annotate(nb=Coalesce(Sum("nb_voyage"), 0))
        .order_by("-nb")
    )
    return {
        "labels": [r["vehicule__immatriculation"] or "—" for r in rows],
        "valeurs": [r["nb"] for r in rows],
    }
