"""Vues du module Suivi des prêts."""
from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ventes.exports import reponse_export

from .forms import PretForm, RemboursementForm
from .models import Pret, Remboursement, ZERO
from .permissions import est_admin, peut_saisir, peut_supprimer, saisie_requise, suppression_requise

PAGE = 50


def _ctx(request, **extra):
    base = {
        "peut_saisir": peut_saisir(request.user),
        "peut_supprimer": peut_supprimer(request.user),
        "est_admin": est_admin(request.user),
    }
    base.update(extra)
    return base


def _gnf(valeur):
    return f"{(valeur or 0):,.0f}".replace(",", " ")


def _dates(request):
    debut = (request.GET.get("date_from") or "").strip()
    fin = (request.GET.get("date_to") or "").strip()
    try:
        debut = date.fromisoformat(debut) if debut else None
        fin = date.fromisoformat(fin) if fin else None
    except ValueError:
        debut = fin = None
    return debut, fin


def _remboursements_par_pret():
    """{id du prêt: total remboursé} pour l'entreprise courante, en une seule requête."""
    groupes = Remboursement.objects.order_by().values("pret_id").annotate(t=Sum("montant"))
    return {g["pret_id"]: g["t"] for g in groupes}


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------
def tableau_de_bord(request):
    aujourdhui = timezone.localdate()
    prets = list(Pret.objects.all())
    rembourse = _remboursements_par_pret()
    total_pret = sum((p.montant_pret for p in prets), ZERO)
    total_recouvrer = sum((p.montant_a_recouvrer for p in prets), ZERO)
    total_interet = sum((p.valeur_interet for p in prets), ZERO)
    total_rembourse = sum((rembourse.get(p.pk, ZERO) for p in prets), ZERO)
    reste = sum((max(p.montant_a_recouvrer - rembourse.get(p.pk, ZERO), ZERO)
                 for p in prets if p.observation != Pret.PAYE), ZERO)
    echus = [p for p in prets if p.observation != Pret.PAYE and p.date_fin < aujourdhui]
    bientot = [p for p in prets if p.observation != Pret.PAYE
               and aujourdhui <= p.date_fin <= aujourdhui + timedelta(days=30)]
    par_statut = {code: sum(1 for p in prets if p.observation == code) for code, _ in Pret.STATUTS}
    return render(request, "prets/tableau_de_bord.html", _ctx(
        request,
        nb=len(prets), total_pret=total_pret, total_recouvrer=total_recouvrer,
        total_interet=total_interet, total_rembourse=total_rembourse, reste=reste,
        echus=sorted(echus, key=lambda p: p.date_fin)[:10], nb_echus=len(echus),
        bientot=sorted(bientot, key=lambda p: p.date_fin)[:10], par_statut=par_statut,
        recents=prets[:8]))


# --------------------------------------------------------------------------
# Prêts
# --------------------------------------------------------------------------
def prets(request):
    q = (request.GET.get("q") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    debut, fin = _dates(request)
    qs = Pret.objects.all()
    if q:
        qs = qs.filter(Q(designation__icontains=q) | Q(note__icontains=q))
    if statut == "echu":
        qs = qs.exclude(observation=Pret.PAYE).filter(date_fin__lt=timezone.localdate())
    elif statut in dict(Pret.STATUTS):
        qs = qs.filter(observation=statut)
    if debut:
        qs = qs.filter(date_debut__gte=debut)
    if fin:
        qs = qs.filter(date_debut__lte=fin)
    qs = qs.order_by("date_debut", "id")

    rembourse = _remboursements_par_pret()
    lignes = list(qs)
    for p in lignes:
        p.rembourse = rembourse.get(p.pk, ZERO)
        p.reste = max(p.montant_a_recouvrer - p.rembourse, ZERO)
    totaux = {
        "pret": sum((p.montant_pret for p in lignes), ZERO),
        "recouvrer": sum((p.montant_a_recouvrer for p in lignes), ZERO),
        "interet": sum((p.valeur_interet for p in lignes), ZERO),
        "rembourse": sum((p.rembourse for p in lignes), ZERO),
        "reste": sum((p.reste for p in lignes), ZERO),
    }

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[i, p.designation, _gnf(p.montant_pret), _gnf(p.montant_a_recouvrer), _gnf(p.valeur_interet),
                    p.date_debut.strftime("%d/%m/%Y"), p.date_fin.strftime("%d/%m/%Y"), f"{p.duree_jours} jours",
                    p.get_observation_display()] for i, p in enumerate(lignes, 1)]
        donnees.append(["", "TOTAL", _gnf(totaux["pret"]), _gnf(totaux["recouvrer"]), _gnf(totaux["interet"]),
                        "", "", "", ""])
        return reponse_export(
            fmt, "suivi_prets", "Suivi des montants de prêts",
            ["N°", "Désignation", "Montant de prêt", "Montant global à recouvrer", "Valeur d'intérêt",
             "Début", "Fin", "Durée", "Observation"], donnees,
            sous_titre=f"{len(lignes)} prêt(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))

    page = Paginator(lignes, PAGE).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("export", None)
    page.qs = params.urlencode()
    return render(request, "prets/liste.html", _ctx(
        request, page=page, totaux=totaux, nb=len(lignes), q=q, statut=statut,
        date_from=request.GET.get("date_from", ""), date_to=request.GET.get("date_to", ""),
        statuts=Pret.STATUTS, qs_export=page.qs))


def pret_detail(request, pk):
    pret = get_object_or_404(Pret, pk=pk)
    form = None
    if peut_saisir(request.user):
        form = RemboursementForm(initial={"date": timezone.localdate()})
    return render(request, "prets/detail.html", _ctx(
        request, pret=pret, remboursements=pret.remboursements.all(), form=form,
        rembourse=pret.total_rembourse, reste=pret.reste_a_recouvrer))


@saisie_requise
def pret_nouveau(request):
    form = PretForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pret = form.save()
        messages.success(request, f"Prêt « {pret.designation} » enregistré.")
        return redirect("prets:detail", pk=pret.pk)
    return render(request, "prets/formulaire.html", _ctx(request, form=form, titre="Nouveau prêt",
                                                         retour="prets:liste"))


@saisie_requise
def pret_modifier(request, pk):
    pret = get_object_or_404(Pret, pk=pk)
    form = PretForm(request.POST or None, instance=pret)
    if request.method == "POST" and form.is_valid():
        pret = form.save()
        pret.synchroniser_statut()
        messages.success(request, "Prêt mis à jour.")
        return redirect("prets:detail", pk=pret.pk)
    return render(request, "prets/formulaire.html", _ctx(request, form=form, titre=f"Modifier : {pret.designation}",
                                                         retour="prets:liste"))


@suppression_requise
@require_POST
def pret_supprimer(request, pk):
    pret = get_object_or_404(Pret, pk=pk)
    nom = pret.designation
    pret.delete()
    messages.success(request, f"Prêt « {nom} » supprimé.")
    return redirect("prets:liste")


# --------------------------------------------------------------------------
# Remboursements
# --------------------------------------------------------------------------
@saisie_requise
@require_POST
def remboursement_ajouter(request, pk):
    pret = get_object_or_404(Pret, pk=pk)
    form = RemboursementForm(request.POST)
    if form.is_valid():
        remb = form.save(commit=False)
        remb.pret = pret
        remb.save()
        pret.synchroniser_statut()
        messages.success(request, "Remboursement enregistré.")
    else:
        messages.error(request, "Remboursement refusé : " + " ".join(
            e for erreurs in form.errors.values() for e in erreurs))
    return redirect("prets:detail", pk=pret.pk)


@suppression_requise
@require_POST
def remboursement_supprimer(request, pk):
    remb = get_object_or_404(Remboursement, pk=pk)
    pret = remb.pret
    remb.delete()
    messages.success(request, "Remboursement supprimé.")
    return redirect("prets:detail", pk=pret.pk)
