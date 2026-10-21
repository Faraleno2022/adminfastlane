import datetime
import io

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from . import excel, pdf
from . import services_dashboard as dash
from . import services_rapports as services
from .models import Vehicule
from .views_dashboard import lire_periode


def _periode(request):
    annees = dash.annees_disponibles()
    annee, mois = lire_periode(request, annees)
    if annee not in annees:
        annees = sorted(set(annees) | {annee})
    return annees, annee, mois


def _ctx_periode(annees, annee, mois, **extra):
    ctx = {
        "annees": annees,
        "annee": annee,
        "mois": mois,
        "mois_liste": list(enumerate(dash.MOIS_NOMS, start=1)),
        "mois_nom": dash.MOIS_NOMS[mois - 1],
    }
    ctx.update(extra)
    return ctx


@login_required
def rapport_mensuel(request):
    """Feuille « Rapport » : tonnage et carburant par camion (mois + jour)."""
    annees, annee, mois = _periode(request)
    try:
        jour = datetime.date.fromisoformat(request.GET.get("jour", ""))
    except ValueError:
        jour = services.jour_par_defaut(annee, mois)
    contexte = _ctx_periode(
        annees, annee, mois,
        titre="Rapport mensuel d'activités",
        jour=jour,
        r=services.rapport_mensuel(annee, mois, jour),
        aujourdhui=datetime.date.today(),
    )
    return render(request, "flotte/rapports/mensuel.html", contexte)


@login_required
def charges_entretien(request):
    """Feuille « Charges Entretient » : charges par véhicule et par mois."""
    annees, annee, mois = _periode(request)
    vehicule_id = request.GET.get("vehicule") or None
    contexte = _ctx_periode(
        annees, annee, mois,
        titre="Charges d'entretien",
        vehicules=Vehicule.objects.all(),
        vehicule_id=vehicule_id,
        m=services.charges_entretien(annee, vehicule_id),
    )
    return render(request, "flotte/rapports/charges_entretien.html", contexte)


@login_required
def consommation_carburant(request):
    """Feuille « Consommation Carburant » : carburant par période."""
    annees, annee, mois = _periode(request)
    unite = "montant" if request.GET.get("unite") == "montant" else "litres"
    contexte = _ctx_periode(
        annees, annee, mois,
        titre="Consommation de carburant",
        unite=unite,
        m=services.consommation_carburant(annee, unite),
    )
    return render(request, "flotte/rapports/carburant.html", contexte)


@login_required
def analyse_poclain(request):
    """Feuille « Analyse des données du Poclain »."""
    annees, annee, mois = _periode(request)
    contexte = _ctx_periode(
        annees, annee, mois,
        titre="Analyse du Poclain",
        p=services.analyse_poclain(annee, mois),
    )
    return render(request, "flotte/rapports/poclain.html", contexte)


def _annee(request):
    a = request.GET.get("annee")
    return int(a) if (a and a.isdigit()) else None


@login_required
def export_excel(request):
    annee = _annee(request)
    wb = excel.construire(annee)
    flux = io.BytesIO()
    wb.save(flux)
    flux.seek(0)
    nom = f"flotte_cab_{annee or 'global'}.xlsx"
    resp = HttpResponse(
        flux.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{nom}"'
    return resp


@login_required
def export_pdf(request):
    annee = _annee(request)
    contenu = pdf.construire(annee)
    nom = f"flotte_cab_{annee or 'global'}.pdf"
    resp = HttpResponse(contenu, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{nom}"'
    return resp
