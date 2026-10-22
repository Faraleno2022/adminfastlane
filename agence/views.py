"""Vues du module Agence de voyage."""
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ventes.exports import reponse_export

from .forms import (
    ClientForm, DossierForm, FournisseurForm, PaiementClientForm, PaiementFournisseurForm, PrestationForm,
    VoyageurForm,
)
from .models import (
    Client, Dossier, Fournisseur, PaiementClient, PaiementFournisseur, Prestation, Voyageur, ZERO,
)
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


def _agent(user):
    return (user.get_full_name() or user.get_username() or "").strip()


def _dates(request):
    try:
        debut = date.fromisoformat((request.GET.get("date_from") or "").strip() or "x")
    except ValueError:
        debut = None
    try:
        fin = date.fromisoformat((request.GET.get("date_to") or "").strip() or "x")
    except ValueError:
        fin = None
    return debut, fin


def _dossiers(qs=None):
    """Dossiers avec tout ce qu'il faut pour calculer les totaux sans requêtes supplémentaires."""
    qs = Dossier.objects.all() if qs is None else qs
    return qs.select_related("client").prefetch_related("prestations__paiements", "paiements")


def _paginer(request, elements):
    page = Paginator(elements, PAGE).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("export", None)
    page.qs = params.urlencode()
    return page


def _formulaire(request, form, titre, retour, retour_args=()):
    return render(request, "agence/formulaire.html", _ctx(
        request, form=form, titre=titre, retour_url=reverse(retour, args=retour_args)))


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------
def tableau_de_bord(request):
    aujourdhui = timezone.localdate()
    dossiers = list(_dossiers())
    actifs = [d for d in dossiers if d.statut in Dossier.STATUTS_ACTIFS]
    debut_mois = aujourdhui.replace(day=1)

    ca = sum((d.total_vente for d in actifs), ZERO)
    marge = sum((d.marge for d in actifs), ZERO)
    impayes = sorted((d for d in actifs if d.reste_a_payer > 0), key=lambda d: d.reste_a_payer, reverse=True)
    departs = sorted((d for d in dossiers if d.statut == Dossier.CONFIRME and d.date_depart
                      and aujourdhui <= d.date_depart <= aujourdhui + timedelta(days=30)),
                     key=lambda d: d.date_depart)
    voyageurs = Voyageur.objects.filter(
        dossier__statut=Dossier.CONFIRME, dossier__date_depart__gte=aujourdhui).select_related("dossier")
    passeports = [v for v in voyageurs if v.passeport_a_verifier]

    mois = PaiementClient.objects.filter(date__gte=debut_mois).aggregate(t=Sum("montant"))["t"] or ZERO
    return render(request, "agence/tableau_de_bord.html", _ctx(
        request,
        nb_devis=sum(1 for d in dossiers if d.statut == Dossier.DEVIS),
        nb_confirmes=sum(1 for d in dossiers if d.statut == Dossier.CONFIRME),
        nb_termines=sum(1 for d in dossiers if d.statut == Dossier.TERMINE),
        nb_clients=Client.objects.count(),
        ca=ca, marge=marge, encaisse=sum((d.total_paye for d in actifs), ZERO), encaisse_mois=mois,
        total_impayes=sum((d.reste_a_payer for d in impayes), ZERO), impayes=impayes[:8],
        dettes=sum((d.dette_fournisseurs for d in actifs), ZERO),
        departs=departs[:8], passeports=passeports[:10], nb_passeports=len(passeports),
        recents=dossiers[:8]))


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
def clients(request):
    q = (request.GET.get("q") or "").strip()
    qs = Client.objects.prefetch_related("dossiers")
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(telephone__icontains=q) | Q(passeport_numero__icontains=q)
                       | Q(email__icontains=q))
    return render(request, "agence/clients.html", _ctx(request, page=_paginer(request, list(qs)), q=q))


def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    dossiers = list(_dossiers(client.dossiers.all()))
    return render(request, "agence/client_detail.html", _ctx(
        request, client=client, dossiers=dossiers,
        total=sum((d.total_vente for d in dossiers if d.statut in Dossier.STATUTS_ACTIFS), ZERO),
        reste=sum((d.reste_a_payer for d in dossiers if d.statut in Dossier.STATUTS_ACTIFS), ZERO)))


@saisie_requise
def client_nouveau(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client « {client.nom} » enregistré.")
        return redirect("agence:client_detail", pk=client.pk)
    return _formulaire(request, form, "Nouveau client", "agence:clients")


@saisie_requise
def client_modifier(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client mis à jour.")
        return redirect("agence:client_detail", pk=client.pk)
    return _formulaire(request, form, f"Modifier : {client.nom}", "agence:client_detail", (client.pk,))


@suppression_requise
@require_POST
def client_supprimer(request, pk):
    client = get_object_or_404(Client, pk=pk)
    try:
        client.delete()
    except ProtectedError:
        messages.error(request, "Ce client a des dossiers de voyage : suppression impossible.")
        return redirect("agence:client_detail", pk=pk)
    messages.success(request, "Client supprimé.")
    return redirect("agence:clients")


# --------------------------------------------------------------------------
# Fournisseurs
# --------------------------------------------------------------------------
def _dette_fournisseur(fournisseur):
    return sum((p.reste_fournisseur for p in fournisseur.prestations.all()
                if p.statut != Prestation.ANNULEE and p.dossier.statut != Dossier.ANNULE), ZERO)


def fournisseurs(request):
    q = (request.GET.get("q") or "").strip()
    qs = Fournisseur.objects.prefetch_related("prestations__paiements", "prestations__dossier")
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(contact__icontains=q))
    lignes = list(qs)
    for f in lignes:
        f.dette = _dette_fournisseur(f)
    return render(request, "agence/fournisseurs.html", _ctx(
        request, page=_paginer(request, lignes), q=q, total_dette=sum((f.dette for f in lignes), ZERO)))


def fournisseur_detail(request, pk):
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    prestations = list(fournisseur.prestations.select_related("dossier__client").prefetch_related("paiements")
                       .order_by("-created_at"))
    return render(request, "agence/fournisseur_detail.html", _ctx(
        request, fournisseur=fournisseur, prestations=prestations,
        dette=sum((p.reste_fournisseur for p in prestations
                   if p.statut != Prestation.ANNULEE and p.dossier.statut != Dossier.ANNULE), ZERO)))


@saisie_requise
def fournisseur_nouveau(request):
    form = FournisseurForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fournisseur = form.save()
        messages.success(request, f"Fournisseur « {fournisseur.nom} » enregistré.")
        return redirect("agence:fournisseurs")
    return _formulaire(request, form, "Nouveau fournisseur", "agence:fournisseurs")


@saisie_requise
def fournisseur_modifier(request, pk):
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    form = FournisseurForm(request.POST or None, instance=fournisseur)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fournisseur mis à jour.")
        return redirect("agence:fournisseur_detail", pk=fournisseur.pk)
    return _formulaire(request, form, f"Modifier : {fournisseur.nom}", "agence:fournisseur_detail", (fournisseur.pk,))


@suppression_requise
@require_POST
def fournisseur_supprimer(request, pk):
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    fournisseur.delete()  # les prestations conservent leur libellé, seul le lien est retiré
    messages.success(request, "Fournisseur supprimé.")
    return redirect("agence:fournisseurs")


# --------------------------------------------------------------------------
# Dossiers de voyage
# --------------------------------------------------------------------------
def dossiers(request):
    q = (request.GET.get("q") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    filtre = (request.GET.get("filtre") or "").strip()
    debut, fin = _dates(request)
    qs = _dossiers()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(client__nom__icontains=q) | Q(destination__icontains=q))
    if statut in dict(Dossier.STATUTS):
        qs = qs.filter(statut=statut)
    if debut:
        qs = qs.filter(created_at__date__gte=debut)
    if fin:
        qs = qs.filter(created_at__date__lte=fin)
    aujourdhui = timezone.localdate()
    if filtre == "departs":
        qs = qs.filter(date_depart__gte=aujourdhui, date_depart__lte=aujourdhui + timedelta(days=30))
    lignes = list(qs)
    if filtre == "impayes":
        lignes = [d for d in lignes if d.statut in Dossier.STATUTS_ACTIFS and d.reste_a_payer > 0]

    totaux = {
        "vente": sum((d.total_vente for d in lignes if d.statut != Dossier.ANNULE), ZERO),
        "paye": sum((d.total_paye for d in lignes if d.statut != Dossier.ANNULE), ZERO),
        "marge": sum((d.marge for d in lignes if d.statut != Dossier.ANNULE), ZERO),
    }
    totaux["reste"] = totaux["vente"] - totaux["paye"]

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[d.reference, d.created_at.strftime("%d/%m/%Y"), d.client.nom, d.destination,
                    d.date_depart.strftime("%d/%m/%Y") if d.date_depart else "", d.get_statut_display(),
                    _gnf(d.total_vente), _gnf(d.total_paye), _gnf(d.reste_a_payer), _gnf(d.marge)] for d in lignes]
        donnees.append(["TOTAL", "", f"{len(lignes)} dossier(s)", "", "", "", _gnf(totaux["vente"]),
                        _gnf(totaux["paye"]), _gnf(totaux["reste"]), _gnf(totaux["marge"])])
        return reponse_export(
            fmt, "dossiers_voyage", "Dossiers de voyage",
            ["Référence", "Créé le", "Client", "Destination", "Départ", "Statut", "Total", "Payé", "Reste", "Marge"],
            donnees, sous_titre=f"{len(lignes)} dossier(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))

    return render(request, "agence/dossiers.html", _ctx(
        request, page=_paginer(request, lignes), nb=len(lignes), totaux=totaux, q=q, statut=statut, filtre=filtre,
        date_from=request.GET.get("date_from", ""), date_to=request.GET.get("date_to", ""),
        statuts=Dossier.STATUTS))


def dossier_detail(request, pk):
    dossier = get_object_or_404(_dossiers(), pk=pk)
    return render(request, "agence/dossier_detail.html", _ctx(
        request, dossier=dossier, prestations=list(dossier.prestations.all()),
        voyageurs=dossier.voyageurs.all(), paiements=list(dossier.paiements.all()), statuts=Dossier.STATUTS))


@saisie_requise
def dossier_nouveau(request):
    initial = {}
    if request.GET.get("client"):
        initial["client"] = request.GET["client"]
    form = DossierForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        dossier = form.save(commit=False)
        dossier.agent = _agent(request.user)
        dossier.save()
        messages.success(request, f"Dossier {dossier.reference} ouvert.")
        return redirect("agence:dossier_detail", pk=dossier.pk)
    return _formulaire(request, form, "Nouveau dossier de voyage", "agence:dossiers")


@saisie_requise
def dossier_modifier(request, pk):
    dossier = get_object_or_404(Dossier, pk=pk)
    form = DossierForm(request.POST or None, instance=dossier)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dossier mis à jour.")
        return redirect("agence:dossier_detail", pk=dossier.pk)
    return _formulaire(request, form, f"Modifier le dossier {dossier.reference}", "agence:dossier_detail", (dossier.pk,))


@saisie_requise
@require_POST
def dossier_statut(request, pk):
    dossier = get_object_or_404(Dossier, pk=pk)
    nouveau = request.POST.get("statut")
    if nouveau in dict(Dossier.STATUTS):
        dossier.statut = nouveau
        dossier.save(update_fields=["statut"])
        messages.success(request, f"Dossier {dossier.reference} : {dossier.get_statut_display().lower()}.")
    return redirect("agence:dossier_detail", pk=dossier.pk)


@suppression_requise
@require_POST
def dossier_supprimer(request, pk):
    dossier = get_object_or_404(Dossier, pk=pk)
    if dossier.paiements.exists():
        messages.error(request, "Des paiements sont enregistrés : annulez le dossier plutôt que de le supprimer.")
        return redirect("agence:dossier_detail", pk=pk)
    dossier.delete()
    messages.success(request, "Dossier supprimé.")
    return redirect("agence:dossiers")


def document(request, pk):
    """Devis (dossier en devis) ou facture, imprimable."""
    dossier = get_object_or_404(_dossiers(), pk=pk)
    return render(request, "agence/document.html", {
        "dossier": dossier, "entreprise": request.user.entreprise,
        "prestations": [p for p in dossier.prestations.all() if p.statut != Prestation.ANNULEE],
        "titre": "DEVIS" if dossier.statut == Dossier.DEVIS else "FACTURE", "paiements": list(dossier.paiements.all()),
    })


# --------------------------------------------------------------------------
# Prestations d'un dossier
# --------------------------------------------------------------------------
@saisie_requise
def prestation_nouvelle(request, pk):
    dossier = get_object_or_404(Dossier, pk=pk)
    form = PrestationForm(request.POST or None, initial={"date_debut": dossier.date_depart, "date_fin": dossier.date_retour})
    if request.method == "POST" and form.is_valid():
        prestation = form.save(commit=False)
        prestation.dossier = dossier
        prestation.save()
        messages.success(request, "Prestation ajoutée.")
        return redirect("agence:dossier_detail", pk=dossier.pk)
    return _formulaire(request, form, f"Nouvelle prestation — {dossier.reference}", "agence:dossier_detail", (dossier.pk,))


@saisie_requise
def prestation_modifier(request, pk):
    prestation = get_object_or_404(Prestation, pk=pk)
    form = PrestationForm(request.POST or None, instance=prestation)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Prestation mise à jour.")
        return redirect("agence:dossier_detail", pk=prestation.dossier_id)
    return _formulaire(request, form, "Modifier la prestation", "agence:dossier_detail", (prestation.dossier_id,))


@suppression_requise
@require_POST
def prestation_supprimer(request, pk):
    prestation = get_object_or_404(Prestation, pk=pk)
    dossier_id = prestation.dossier_id
    if prestation.paiements.exists():
        messages.error(request, "Des règlements fournisseur existent : passez la prestation en « Annulée ».")
    else:
        prestation.delete()
        messages.success(request, "Prestation supprimée.")
    return redirect("agence:dossier_detail", pk=dossier_id)


@saisie_requise
def paiement_fournisseur_nouveau(request, pk):
    prestation = get_object_or_404(Prestation.objects.prefetch_related("paiements"), pk=pk)
    form = PaiementFournisseurForm(request.POST or None, prestation=prestation,
                                   initial={"montant": prestation.reste_fournisseur})
    if request.method == "POST" and form.is_valid():
        paiement = form.save(commit=False)
        paiement.prestation = prestation
        paiement.save()
        messages.success(request, "Règlement fournisseur enregistré.")
        return redirect("agence:dossier_detail", pk=prestation.dossier_id)
    return _formulaire(request, form, f"Règlement fournisseur — {prestation.description}",
                       "agence:dossier_detail", (prestation.dossier_id,))


@suppression_requise
@require_POST
def paiement_fournisseur_supprimer(request, pk):
    paiement = get_object_or_404(PaiementFournisseur, pk=pk)
    dossier_id = paiement.prestation.dossier_id
    paiement.delete()
    messages.success(request, "Règlement supprimé.")
    return redirect("agence:dossier_detail", pk=dossier_id)


# --------------------------------------------------------------------------
# Voyageurs
# --------------------------------------------------------------------------
@saisie_requise
def voyageur_nouveau(request, pk):
    dossier = get_object_or_404(Dossier, pk=pk)
    initial = {}
    if request.GET.get("depuis_client"):
        c = dossier.client
        initial = {"nom": c.nom, "date_naissance": c.date_naissance, "nationalite": c.nationalite,
                   "passeport_numero": c.passeport_numero, "passeport_expiration": c.passeport_expiration}
    form = VoyageurForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        voyageur = form.save(commit=False)
        voyageur.dossier = dossier
        voyageur.save()
        messages.success(request, "Voyageur ajouté.")
        return redirect("agence:dossier_detail", pk=dossier.pk)
    return _formulaire(request, form, f"Nouveau voyageur — {dossier.reference}", "agence:dossier_detail", (dossier.pk,))


@saisie_requise
def voyageur_modifier(request, pk):
    voyageur = get_object_or_404(Voyageur, pk=pk)
    form = VoyageurForm(request.POST or None, instance=voyageur)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Voyageur mis à jour.")
        return redirect("agence:dossier_detail", pk=voyageur.dossier_id)
    return _formulaire(request, form, f"Modifier : {voyageur.nom}", "agence:dossier_detail", (voyageur.dossier_id,))


@suppression_requise
@require_POST
def voyageur_supprimer(request, pk):
    voyageur = get_object_or_404(Voyageur, pk=pk)
    dossier_id = voyageur.dossier_id
    voyageur.delete()
    messages.success(request, "Voyageur supprimé.")
    return redirect("agence:dossier_detail", pk=dossier_id)


# --------------------------------------------------------------------------
# Paiements des clients
# --------------------------------------------------------------------------
@saisie_requise
def paiement_nouveau(request, pk):
    dossier = get_object_or_404(_dossiers(), pk=pk)
    form = PaiementClientForm(request.POST or None, dossier=dossier, initial={"montant": max(dossier.reste_a_payer, ZERO)})
    if request.method == "POST" and form.is_valid():
        paiement = form.save(commit=False)
        paiement.dossier = dossier
        paiement.agent = _agent(request.user)
        paiement.save()
        messages.success(request, "Paiement enregistré.")
        return redirect("agence:recu", pk=paiement.pk) if request.POST.get("imprimer") \
            else redirect("agence:dossier_detail", pk=dossier.pk)
    return render(request, "agence/formulaire.html", _ctx(
        request, form=form, titre=f"Encaissement — {dossier.reference}",
        retour_url=reverse("agence:dossier_detail", args=(dossier.pk,)), imprimer=True,
        info=f"Reste à payer : {_gnf(dossier.reste_a_payer)} GNF"))


@suppression_requise
@require_POST
def paiement_supprimer(request, pk):
    paiement = get_object_or_404(PaiementClient, pk=pk)
    dossier_id = paiement.dossier_id
    paiement.delete()
    messages.success(request, "Paiement supprimé.")
    return redirect("agence:dossier_detail", pk=dossier_id)


def recu(request, pk):
    paiement = get_object_or_404(PaiementClient.objects.select_related("dossier__client"), pk=pk)
    dossier = _dossiers().get(pk=paiement.dossier_id)
    return render(request, "agence/recu.html", {
        "paiement": paiement, "dossier": dossier, "entreprise": request.user.entreprise})


# --------------------------------------------------------------------------
# Rapports
# --------------------------------------------------------------------------
def rapports(request):
    debut, fin = _dates(request)
    aujourdhui = timezone.localdate()
    debut = debut or aujourdhui.replace(day=1)
    fin = fin or aujourdhui

    actifs = [d for d in _dossiers(Dossier.objects.filter(
        statut__in=Dossier.STATUTS_ACTIFS, created_at__date__gte=debut, created_at__date__lte=fin))]
    par_type = defaultdict(lambda: [ZERO, ZERO])
    par_destination = defaultdict(lambda: [0, ZERO, ZERO])
    libelles = dict(Prestation.TYPES)
    for d in actifs:
        for p in d.prestations.all():
            if p.statut == Prestation.ANNULEE:
                continue
            par_type[libelles[p.type]][0] += p.total_vente
            par_type[libelles[p.type]][1] += p.total_achat
        ligne = par_destination[d.destination.strip().title() or "—"]
        ligne[0] += 1
        ligne[1] += d.total_vente
        ligne[2] += d.marge
    lignes_type = sorted(([nom, v, a, v - a] for nom, (v, a) in par_type.items()), key=lambda x: x[1], reverse=True)
    lignes_dest = sorted(([nom, n, v, m] for nom, (n, v, m) in par_destination.items()), key=lambda x: x[2], reverse=True)

    encaisse = PaiementClient.objects.filter(date__gte=debut, date__lte=fin).aggregate(t=Sum("montant"))["t"] or ZERO
    decaisse = PaiementFournisseur.objects.filter(date__gte=debut, date__lte=fin).aggregate(t=Sum("montant"))["t"] or ZERO
    periode = f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[nom, _gnf(v), _gnf(a), _gnf(m)] for nom, v, a, m in lignes_type]
        donnees.append(["TOTAL", _gnf(sum(l[1] for l in lignes_type)), _gnf(sum(l[2] for l in lignes_type)),
                        _gnf(sum(l[3] for l in lignes_type))])
        return reponse_export(
            fmt, "rapport_agence", "Chiffre d'affaires par type de prestation",
            ["Type de prestation", "Ventes", "Achats", "Marge"], donnees, sous_titre=periode,
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))

    return render(request, "agence/rapports.html", _ctx(
        request, date_from=debut.isoformat(), date_to=fin.isoformat(), periode=periode, nb=len(actifs),
        ca=sum((d.total_vente for d in actifs), ZERO), marge=sum((d.marge for d in actifs), ZERO),
        encaisse=encaisse, decaisse=decaisse, lignes_type=lignes_type, lignes_dest=lignes_dest[:10]))
