"""
Calculs des rapports issus du classeur d'origine.

- rapport_mensuel        -> feuille « Rapport »
- charges_entretien      -> feuille « Charges Entretient »
- consommation_carburant -> feuille « Consommation Carburant »
- analyse_poclain        -> feuille « Analyse des données du Poclain »
"""
import datetime
from decimal import Decimal

from django.db.models import Sum

from .models import (
    ActiviteEngin, CategorieRoues, Engin, Entretien, PleinCarburant, Vehicule, Voyage,
)
from .services_dashboard import MOIS_FR, ZERO, serie_mensuelle


def _somme(qs, champ):
    return qs.aggregate(t=Sum(champ))["t"] or ZERO


# ------------------------------------------------------------------ Rapport
def rapport_mensuel(annee, mois, jour):
    """
    Tonnage (nb de voyages) et consommation de carburant par camion, pour le
    mois choisi et pour une journée donnée (feuille « Rapport »).
    """
    vehicules = Vehicule.objects.filter(actif=True).select_related("chauffeur_actuel", "chauffeur_secondaire")

    voyages, carburant = [], []
    for v in vehicules:
        voy_mois = Voyage.objects.filter(vehicule=v, date__year=annee, date__month=mois)
        pleins_mois = PleinCarburant.objects.filter(vehicule=v, date__year=annee, date__month=mois)
        chauffeur = v.noms_chauffeurs()
        voyages.append({
            "chauffeur": chauffeur,
            "immatriculation": v.immatriculation,
            "mois": voy_mois.aggregate(t=Sum("nb_voyage"))["t"] or 0,
            "jour": Voyage.objects.filter(vehicule=v, date=jour).aggregate(t=Sum("nb_voyage"))["t"] or 0,
        })
        carburant.append({
            "chauffeur": chauffeur,
            "immatriculation": v.immatriculation,
            "mois": _somme(pleins_mois, "litres"),
            "jour": _somme(PleinCarburant.objects.filter(vehicule=v, date=jour), "litres"),
        })

    # Les engins (Poclain…) consomment aussi du carburant.
    for e in Engin.objects.filter(actif=True):
        acts = ActiviteEngin.objects.filter(engin=e)
        litres_mois = _somme(acts.filter(date__year=annee, date__month=mois), "qte_carburant")
        litres_jour = _somme(acts.filter(date=jour), "qte_carburant")
        if litres_mois or litres_jour:
            carburant.append({
                "chauffeur": "(engin)",
                "immatriculation": e.nom,
                "mois": litres_mois,
                "jour": litres_jour,
            })

    # Statistiques journalières des voyages sur le mois (date × camion).
    stats = (
        Voyage.objects.filter(date__year=annee, date__month=mois)
        .values("date", "vehicule__immatriculation")
        .annotate(nb=Sum("nb_voyage"))
        .order_by("date", "vehicule__immatriculation")
    )
    return {
        "voyages": voyages,
        "carburant": carburant,
        "stats_journalieres": list(stats),
        "total_voyages_mois": sum(l["mois"] for l in voyages),
        "total_voyages_jour": sum(l["jour"] for l in voyages),
        "total_litres_mois": sum((l["mois"] for l in carburant), ZERO),
        "total_litres_jour": sum((l["jour"] for l in carburant), ZERO),
    }


# -------------------------------------------------------- Matrices mensuelles
def _matrice(lignes_source, annee):
    """
    lignes_source : liste de (libellé, queryset, champ).
    Retourne lignes (libellé, 12 valeurs, total) + ligne de totaux par mois.
    """
    lignes = []
    totaux = [ZERO] * 12
    for libelle, qs, champ in lignes_source:
        valeurs = serie_mensuelle(qs, champ, annee)
        total = sum(valeurs, ZERO)
        if not total:
            continue
        lignes.append({"libelle": libelle, "valeurs": valeurs, "total": total})
        totaux = [a + b for a, b in zip(totaux, valeurs)]
    return {
        "mois": MOIS_FR,
        "lignes": lignes,
        "totaux": totaux,
        "total_general": sum(totaux, ZERO),
    }


def charges_entretien(annee, vehicule_id=None):
    """Charges d'entretien (Montant TTC) par véhicule et par mois."""
    vehicules = Vehicule.objects.all()
    if vehicule_id:
        vehicules = vehicules.filter(pk=vehicule_id)
    source = [
        (v.immatriculation, Entretien.objects.filter(vehicule=v), "montant_ttc")
        for v in vehicules
    ]
    return _matrice(source, annee)


def consommation_carburant(annee, unite="litres"):
    """
    Carburant par véhicule / engin et par mois.
    unite = "litres" (quantité) ou "montant" (dépense).
    """
    champ_v = "litres" if unite == "litres" else "montant"
    champ_e = "qte_carburant" if unite == "litres" else "montant_carburant"
    source = [
        (v.immatriculation, PleinCarburant.objects.filter(vehicule=v), champ_v)
        for v in Vehicule.objects.all()
    ]
    source += [
        (f"{e.nom} (engin)", ActiviteEngin.objects.filter(engin=e), champ_e)
        for e in Engin.objects.all()
    ]
    return _matrice(source, annee)


# ---------------------------------------------------------------- Poclain
def analyse_poclain(annee, mois):
    """Reproduit la feuille « Analyse des données du Poclain »."""
    base = ActiviteEngin.objects.all()
    du_mois = base.filter(date__year=annee, date__month=mois)
    de_l_annee = base.filter(date__year=annee)

    par_roues = []
    categories = list(CategorieRoues.objects.all()) + [None]
    for cat in categories:
        m = du_mois.filter(categorie_roues=cat)
        a = de_l_annee.filter(categorie_roues=cat)
        ligne = {
            "libelle": cat.libelle if cat else "Non précisé",
            "chargements_mois": m.aggregate(t=Sum("nb_chargement"))["t"] or 0,
            "chargements_annee": a.aggregate(t=Sum("nb_chargement"))["t"] or 0,
            "montant_mois": _somme(m, "montant_chargement"),
            "montant_annee": _somme(a, "montant_chargement"),
        }
        # On masque la ligne « Non précisé » si elle est vide.
        if cat is None and not ligne["chargements_annee"] and not ligne["montant_annee"]:
            continue
        par_roues.append(ligne)

    journalier = (
        du_mois.values("date")
        .annotate(
            chargements=Sum("nb_chargement"),
            recette=Sum("montant_chargement"),
            litres=Sum("qte_carburant"),
            depense_carburant=Sum("montant_carburant"),
        )
        .order_by("date")
    )
    return {
        "par_roues": par_roues,
        "carburant": {
            "litres_mois": _somme(du_mois, "qte_carburant"),
            "litres_annee": _somme(de_l_annee, "qte_carburant"),
            "montant_mois": _somme(du_mois, "montant_carburant"),
            "montant_annee": _somme(de_l_annee, "montant_carburant"),
        },
        "journalier": list(journalier),
        "total_chargements_mois": sum(l["chargements_mois"] for l in par_roues),
        "total_recette_mois": sum((l["montant_mois"] for l in par_roues), ZERO),
    }


def jour_par_defaut(annee, mois):
    """Aujourd'hui si on est dans le mois choisi, sinon le dernier jour du mois."""
    aujourdhui = datetime.date.today()
    if aujourdhui.year == annee and aujourdhui.month == mois:
        return aujourdhui
    if mois == 12:
        return datetime.date(annee, 12, 31)
    return datetime.date(annee, mois + 1, 1) - datetime.timedelta(days=1)
