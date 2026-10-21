import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from . import services_dashboard as services
from .models import DocumentVehicule


def lire_periode(request, annees):
    """
    Lit ?annee= et ?mois= dans la requête.

    Par défaut : l'année courante si elle a des données, sinon la plus
    récente ; le mois courant pour l'année en cours, décembre sinon.
    """
    aujourdhui = timezone.localdate()
    a = request.GET.get("annee")
    if a and a.isdigit():
        annee = int(a)
    elif aujourdhui.year in annees or not annees:
        annee = aujourdhui.year
    else:
        annee = annees[-1]
    m = request.GET.get("mois")
    if m and m.isdigit() and 1 <= int(m) <= 12:
        mois = int(m)
    else:
        mois = aujourdhui.month if annee == aujourdhui.year else 12
    return annee, mois


@login_required
def accueil(request):
    annees = services.annees_disponibles()
    annee, mois = lire_periode(request, annees)
    if annee not in annees:
        annees = sorted(set(annees) | {annee})

    contexte = {
        "titre": "Tableau de bord",
        "annees": annees,
        "annee": annee,
        "mois": mois,
        "mois_liste": list(enumerate(services.MOIS_NOMS, start=1)),
        "kpi": services.totaux(annee),
        "gestion": services.gestion(annee, mois),
        "chart_repartition": json.dumps(services.repartition_depenses(annee)),
        "chart_recettes": json.dumps(services.repartition_recettes(annee)),
        "chart_vehicules": json.dumps(services.charges_par_vehicule(annee)),
        "chart_voyages": json.dumps(services.voyages_par_vehicule(annee)),
        "chart_mois": json.dumps(services.recettes_depenses_par_mois(annee)),
        "alertes_documents": list(DocumentVehicule.en_alerte()[:10]),
        "NB_ALERTES_DOCUMENTS": DocumentVehicule.en_alerte().count(),
    }
    return render(request, "flotte/dashboard/accueil.html", contexte)


@login_required
def analyses(request):
    annees = services.annees_disponibles()
    annee = request.GET.get("annee")
    annee = int(annee) if (annee and annee.isdigit()) else (annees[-1] if annees else None)

    lignes = services.analyse_vehicules(annee)
    contexte = {
        "titre": "Analyses par véhicule",
        "annees": annees,
        "annee": annee,
        "lignes": lignes,
        "chart_cout_km": json.dumps({
            "labels": [l["vehicule"] for l in lignes if l["cout_total_km"] is not None],
            "valeurs": [l["cout_total_km"] for l in lignes if l["cout_total_km"] is not None],
        }),
        "chart_conso": json.dumps({
            "labels": [l["vehicule"] for l in lignes if l["l_100km"] is not None],
            "valeurs": [l["l_100km"] for l in lignes if l["l_100km"] is not None],
        }),
    }
    return render(request, "flotte/dashboard/analyses.html", contexte)

