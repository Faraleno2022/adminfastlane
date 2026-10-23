"""Vues du module Transport de carburant."""
from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ventes.exports import reponse_export

from .forms import (
    ChargementForm, CiterneForm, ClientForm, FraisForm, LivraisonForm, PaiementForm, VoyageForm,
)
from .models import PRODUITS, Citerne, Client, FraisVoyage, Paiement, Voyage, ZERO
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


def _litres(valeur):
    return f"{(valeur or 0):,.0f} L".replace(",", " ")


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


def _voyages(qs=None):
    """Voyages avec tout ce qu'il faut pour calculer les montants sans requêtes supplémentaires."""
    qs = Voyage.objects.all() if qs is None else qs
    return qs.select_related("client", "citerne", "vehicule", "chauffeur").prefetch_related("frais")


def _paginer(request, elements):
    page = Paginator(elements, PAGE).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("export", None)
    page.qs = params.urlencode()
    return page


def _formulaire(request, form, titre, retour, retour_args=(), **extra):
    return render(request, "carburant/formulaire.html", _ctx(
        request, form=form, titre=titre, retour_url=reverse(retour, args=retour_args), **extra))


def _entreprise_nom(request):
    return getattr(request.user.entreprise, "nom_entreprise", "")


def _situation(client):
    """Facturé (voyages livrés, nets des pénalités), payé et solde d'un client préchargé."""
    facture = sum((v.montant_net for v in client.voyages.all() if v.facturable), ZERO)
    paye = sum((p.montant for p in client.paiements.all()), ZERO)
    return facture, paye, facture - paye


def _clients_avec_situation(qs=None):
    qs = Client.objects.all() if qs is None else qs
    lignes = list(qs.prefetch_related("voyages", "paiements"))
    for c in lignes:
        c.facture, c.paye, c.solde = _situation(c)
    return lignes


def _totaux(voyages):
    comptes = [v for v in voyages if v.statut != Voyage.ANNULE]
    livres = [v for v in comptes if v.facturable]
    return {
        "charge": sum((v.quantite_chargee or ZERO for v in comptes), ZERO),
        "livre": sum((v.quantite_livree or ZERO for v in livres), ZERO),
        "manquant": sum((v.manquant_imputable for v in livres), ZERO),
        "penalite": sum((v.penalite for v in livres), ZERO),
        "net": sum((v.montant_net for v in livres), ZERO),
        "frais": sum((v.total_frais for v in comptes), ZERO),
        "marge": sum((v.marge for v in livres), ZERO) - sum((v.total_frais for v in comptes if not v.facturable), ZERO),
    }


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------
def tableau_de_bord(request):
    aujourdhui = timezone.localdate()
    debut_mois = aujourdhui.replace(day=1)
    en_route = list(_voyages(Voyage.objects.filter(statut=Voyage.EN_ROUTE)).order_by("date_chargement"))
    planifies = list(_voyages(Voyage.objects.filter(statut=Voyage.PLANIFIE)).order_by("date_prevue")[:10])
    livres_mois = list(_voyages(Voyage.objects.filter(statut=Voyage.LIVRE, date_livraison__gte=debut_mois)))
    clients = _clients_avec_situation()
    citernes = list(Citerne.objects.filter(active=True).select_related("vehicule"))
    occupees = {v.citerne_id for v in en_route}
    alertes = [c for c in citernes if c.etat_barremage in (Citerne.EXPIRE, Citerne.BIENTOT)]
    frais_mois = FraisVoyage.objects.filter(date__gte=debut_mois).aggregate(t=Sum("montant"))["t"] or ZERO
    encaisse_mois = Paiement.objects.filter(date__gte=debut_mois).aggregate(t=Sum("montant"))["t"] or ZERO

    return render(request, "carburant/tableau_de_bord.html", _ctx(
        request,
        en_route=en_route, planifies=planifies, nb_planifies=Voyage.objects.filter(statut=Voyage.PLANIFIE).count(),
        nb_livres_mois=len(livres_mois),
        litres_mois=sum((v.quantite_livree or ZERO for v in livres_mois), ZERO),
        ca_mois=sum((v.montant_net for v in livres_mois), ZERO),
        manquant_mois=sum((v.manquant_imputable for v in livres_mois), ZERO),
        penalites_mois=sum((v.penalite for v in livres_mois), ZERO),
        frais_mois=frais_mois, encaisse_mois=encaisse_mois,
        creances=sum((c.solde for c in clients if c.solde > 0), ZERO),
        debiteurs=sorted((c for c in clients if c.solde > 0), key=lambda c: c.solde, reverse=True)[:8],
        nb_citernes=len(citernes), nb_disponibles=sum(1 for c in citernes if c.pk not in occupees),
        alertes=alertes))


# --------------------------------------------------------------------------
# Voyages
# --------------------------------------------------------------------------
def voyages(request):
    q = (request.GET.get("q") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    client = (request.GET.get("client") or "").strip()
    citerne = (request.GET.get("citerne") or "").strip()
    produit = (request.GET.get("produit") or "").strip()
    filtre = (request.GET.get("filtre") or "").strip()
    debut, fin = _dates(request)
    qs = _voyages()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(client__nom__icontains=q) | Q(destination__icontains=q)
                       | Q(bon_chargement__icontains=q) | Q(bon_livraison__icontains=q)
                       | Q(lieu_chargement__icontains=q))
    if statut in dict(Voyage.STATUTS):
        qs = qs.filter(statut=statut)
    if client.isdigit():
        qs = qs.filter(client_id=int(client))
    if citerne.isdigit():
        qs = qs.filter(citerne_id=int(citerne))
    if produit in dict(PRODUITS):
        qs = qs.filter(produit=produit)
    if debut:
        qs = qs.filter(date_prevue__gte=debut)
    if fin:
        qs = qs.filter(date_prevue__lte=fin)
    lignes = list(qs)
    if filtre == "manquants":
        lignes = [v for v in lignes if v.facturable and v.manquant_imputable > 0]
    totaux = _totaux(lignes)

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[v.reference, v.date_prevue.strftime("%d/%m/%Y"), v.client.nom, v.get_produit_display(),
                    v.citerne.immatriculation, f"{v.lieu_chargement} → {v.destination}", v.get_statut_display(),
                    _litres(v.quantite_chargee), _litres(v.quantite_livree), _litres(v.manquant_imputable),
                    _gnf(v.montant_net) if v.facturable else "", _gnf(v.total_frais)] for v in lignes]
        donnees.append(["TOTAL", "", f"{len(lignes)} voyage(s)", "", "", "", "", _litres(totaux["charge"]),
                        _litres(totaux["livre"]), _litres(totaux["manquant"]), _gnf(totaux["net"]),
                        _gnf(totaux["frais"])])
        return reponse_export(
            fmt, "voyages_carburant", "Voyages de transport de carburant",
            ["Référence", "Date", "Client", "Produit", "Citerne", "Trajet", "Statut", "Chargé", "Livré",
             "Manquant", "Net facturé", "Frais"],
            donnees, sous_titre=f"{len(lignes)} voyage(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=_entreprise_nom(request))

    return render(request, "carburant/voyages.html", _ctx(
        request, page=_paginer(request, lignes), nb=len(lignes), totaux=totaux, q=q, statut=statut,
        client=client, citerne=citerne, produit=produit, filtre=filtre, statuts=Voyage.STATUTS, produits=PRODUITS,
        date_from=request.GET.get("date_from", ""), date_to=request.GET.get("date_to", ""),
        liste_clients=Client.objects.only("id", "nom"), liste_citernes=Citerne.objects.only("id", "immatriculation")))


def voyage_detail(request, pk):
    voyage = get_object_or_404(_voyages(), pk=pk)
    return render(request, "carburant/voyage_detail.html", _ctx(
        request, voyage=voyage, frais=list(voyage.frais.all())))


@saisie_requise
def voyage_nouveau(request):
    initial = {"date_prevue": timezone.localdate()}
    client_id = request.GET.get("client") or ""
    if client_id.isdigit():
        client = Client.objects.filter(pk=int(client_id)).first()
        if client:
            initial.update(client=client.pk, tarif_litre=client.tarif_litre, tolerance_pct=client.tolerance_pct)
    if (request.GET.get("citerne") or "").isdigit():
        initial["citerne"] = request.GET["citerne"]
    form = VoyageForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        voyage = form.save(commit=False)
        voyage.agent = _agent(request.user)
        voyage.save()
        messages.success(request, f"Voyage {voyage.reference} planifié.")
        return redirect("carburant:voyage_detail", pk=voyage.pk)
    return _formulaire(request, form, "Nouveau voyage", "carburant:voyages")


@saisie_requise
def voyage_modifier(request, pk):
    voyage = get_object_or_404(Voyage, pk=pk)
    form = VoyageForm(request.POST or None, instance=voyage)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Voyage mis à jour.")
        return redirect("carburant:voyage_detail", pk=voyage.pk)
    return _formulaire(request, form, f"Modifier le voyage {voyage.reference}", "carburant:voyage_detail", (voyage.pk,))


@saisie_requise
def voyage_chargement(request, pk):
    voyage = get_object_or_404(Voyage.objects.select_related("citerne"), pk=pk)
    if voyage.statut not in (Voyage.PLANIFIE, Voyage.EN_ROUTE):
        messages.error(request, "Le chargement ne peut être saisi que sur un voyage planifié ou en route.")
        return redirect("carburant:voyage_detail", pk=pk)
    initial = {} if voyage.date_chargement else {"date_chargement": timezone.localdate()}
    form = ChargementForm(request.POST or None, instance=voyage, initial=initial)
    if request.method == "POST" and form.is_valid():
        voyage = form.save(commit=False)
        voyage.statut = Voyage.EN_ROUTE
        voyage.save()
        messages.success(request, f"Chargement enregistré : {voyage.reference} est en route.")
        return redirect("carburant:voyage_detail", pk=voyage.pk)
    return _formulaire(request, form, f"Chargement au dépôt — {voyage.reference}", "carburant:voyage_detail",
                       (voyage.pk,), info=f"Citerne {voyage.citerne} — dépôt : {voyage.lieu_chargement}")


@saisie_requise
def voyage_livraison(request, pk):
    voyage = get_object_or_404(Voyage, pk=pk)
    if voyage.statut not in (Voyage.EN_ROUTE, Voyage.LIVRE):
        messages.error(request, "Enregistrez d'abord le chargement de ce voyage.")
        return redirect("carburant:voyage_detail", pk=pk)
    initial = {} if voyage.date_livraison else {"date_livraison": timezone.localdate()}
    form = LivraisonForm(request.POST or None, instance=voyage, initial=initial)
    if request.method == "POST" and form.is_valid():
        voyage = form.save(commit=False)
        voyage.statut = Voyage.LIVRE
        voyage.save()
        if voyage.manquant_imputable > 0:
            messages.warning(request, f"Livraison enregistrée avec un manquant de {_litres(voyage.manquant_imputable)} "
                                      f"au-delà de la tolérance (pénalité : {_gnf(voyage.penalite)} GNF).")
        else:
            messages.success(request, f"Livraison enregistrée : {voyage.reference} est livré.")
        return redirect("carburant:voyage_detail", pk=voyage.pk)
    return _formulaire(request, form, f"Livraison — {voyage.reference}", "carburant:voyage_detail", (voyage.pk,),
                       info=f"Chargé : {_litres(voyage.quantite_chargee)} le "
                            f"{voyage.date_chargement:%d/%m/%Y} — destination : {voyage.destination}")


@saisie_requise
@require_POST
def voyage_statut(request, pk):
    """Annuler un voyage non livré, ou remettre en planifié un voyage annulé."""
    voyage = get_object_or_404(Voyage, pk=pk)
    action = request.POST.get("action")
    if action == "annuler" and voyage.statut in (Voyage.PLANIFIE, Voyage.EN_ROUTE):
        voyage.statut = Voyage.ANNULE
        voyage.save(update_fields=["statut"])
        messages.success(request, f"Voyage {voyage.reference} annulé.")
    elif action == "replanifier" and voyage.statut == Voyage.ANNULE:
        voyage.statut = Voyage.PLANIFIE
        voyage.date_chargement = voyage.quantite_chargee = None
        voyage.bon_chargement = ""
        voyage.save(update_fields=["statut", "date_chargement", "quantite_chargee", "bon_chargement"])
        messages.success(request, f"Voyage {voyage.reference} remis en planifié.")
    else:
        messages.error(request, "Changement de statut impossible.")
    return redirect("carburant:voyage_detail", pk=voyage.pk)


@suppression_requise
@require_POST
def voyage_supprimer(request, pk):
    voyage = get_object_or_404(Voyage, pk=pk)
    if voyage.statut in (Voyage.EN_ROUTE, Voyage.LIVRE) or voyage.frais.exists():
        messages.error(request, "Ce voyage a été chargé ou porte des frais : annulez-le plutôt que de le supprimer.")
        return redirect("carburant:voyage_detail", pk=pk)
    voyage.delete()
    messages.success(request, "Voyage supprimé.")
    return redirect("carburant:voyages")


def bon(request, pk):
    """Bon de transport (lettre de voiture) imprimable."""
    voyage = get_object_or_404(_voyages(), pk=pk)
    return render(request, "carburant/bon.html", {"voyage": voyage, "entreprise": request.user.entreprise})


# --------------------------------------------------------------------------
# Frais de voyage
# --------------------------------------------------------------------------
@saisie_requise
def frais_nouveau(request, pk):
    voyage = get_object_or_404(Voyage, pk=pk)
    form = FraisForm(request.POST or None, initial={"date": voyage.date_chargement or timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        frais = form.save(commit=False)
        frais.voyage = voyage
        frais.save()
        messages.success(request, "Frais enregistré.")
        return redirect("carburant:voyage_detail", pk=voyage.pk)
    return _formulaire(request, form, f"Frais de route — {voyage.reference}", "carburant:voyage_detail", (voyage.pk,))


@suppression_requise
@require_POST
def frais_supprimer(request, pk):
    frais = get_object_or_404(FraisVoyage, pk=pk)
    voyage_id = frais.voyage_id
    frais.delete()
    messages.success(request, "Frais supprimé.")
    return redirect("carburant:voyage_detail", pk=voyage_id)


# --------------------------------------------------------------------------
# Citernes
# --------------------------------------------------------------------------
def citernes(request):
    q = (request.GET.get("q") or "").strip()
    qs = Citerne.objects.select_related("vehicule")
    if q:
        qs = qs.filter(Q(immatriculation__icontains=q) | Q(vehicule__immatriculation__icontains=q)
                       | Q(numero_barremage__icontains=q))
    lignes = list(qs)
    en_route = dict(Voyage.objects.filter(statut=Voyage.EN_ROUTE).values_list("citerne_id", "reference"))
    for c in lignes:
        c.voyage_en_cours = en_route.get(c.pk)
    return render(request, "carburant/citernes.html", _ctx(request, page=_paginer(request, lignes), q=q))


def citerne_detail(request, pk):
    citerne = get_object_or_404(Citerne.objects.select_related("vehicule"), pk=pk)
    voyages_citerne = list(_voyages(citerne.voyages.all()))
    return render(request, "carburant/citerne_detail.html", _ctx(
        request, citerne=citerne, voyages=voyages_citerne[:50], totaux=_totaux(voyages_citerne),
        nb_voyages=sum(1 for v in voyages_citerne if v.facturable)))


@saisie_requise
def citerne_nouvelle(request):
    form = CiterneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        citerne = form.save()
        messages.success(request, f"Citerne {citerne.immatriculation} enregistrée.")
        return redirect("carburant:citerne_detail", pk=citerne.pk)
    return _formulaire(request, form, "Nouvelle citerne", "carburant:citernes")


@saisie_requise
def citerne_modifier(request, pk):
    citerne = get_object_or_404(Citerne, pk=pk)
    form = CiterneForm(request.POST or None, instance=citerne)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Citerne mise à jour.")
        return redirect("carburant:citerne_detail", pk=citerne.pk)
    return _formulaire(request, form, f"Modifier la citerne {citerne.immatriculation}", "carburant:citerne_detail",
                       (citerne.pk,))


@suppression_requise
@require_POST
def citerne_supprimer(request, pk):
    citerne = get_object_or_404(Citerne, pk=pk)
    try:
        citerne.delete()
    except ProtectedError:
        messages.error(request, "Cette citerne a des voyages : mettez-la hors service plutôt que de la supprimer.")
        return redirect("carburant:citerne_detail", pk=pk)
    messages.success(request, "Citerne supprimée.")
    return redirect("carburant:citernes")


# --------------------------------------------------------------------------
# Clients, paiements, relevés
# --------------------------------------------------------------------------
def clients(request):
    q = (request.GET.get("q") or "").strip()
    qs = Client.objects.all()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(contact__icontains=q) | Q(telephone__icontains=q)
                       | Q(email__icontains=q))
    lignes = _clients_avec_situation(qs)
    return render(request, "carburant/clients.html", _ctx(
        request, page=_paginer(request, lignes), q=q, total_solde=sum((c.solde for c in lignes), ZERO)))


def client_detail(request, pk):
    client = get_object_or_404(Client.objects.prefetch_related("voyages", "paiements"), pk=pk)
    facture, paye, solde = _situation(client)
    voyages_client = list(_voyages(client.voyages.all())[:50])
    return render(request, "carburant/client_detail.html", _ctx(
        request, client=client, facture=facture, paye=paye, solde=solde, voyages=voyages_client,
        paiements=list(client.paiements.all()[:50])))


@saisie_requise
def client_nouveau(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client « {client.nom} » enregistré.")
        return redirect("carburant:client_detail", pk=client.pk)
    return _formulaire(request, form, "Nouveau client", "carburant:clients")


@saisie_requise
def client_modifier(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client mis à jour.")
        return redirect("carburant:client_detail", pk=client.pk)
    return _formulaire(request, form, f"Modifier : {client.nom}", "carburant:client_detail", (client.pk,))


@suppression_requise
@require_POST
def client_supprimer(request, pk):
    client = get_object_or_404(Client, pk=pk)
    try:
        client.delete()
    except ProtectedError:
        messages.error(request, "Ce client a des voyages ou des paiements : suppression impossible.")
        return redirect("carburant:client_detail", pk=pk)
    messages.success(request, "Client supprimé.")
    return redirect("carburant:clients")


@saisie_requise
def paiement_nouveau(request, pk):
    client = get_object_or_404(Client.objects.prefetch_related("voyages", "paiements"), pk=pk)
    solde = _situation(client)[2]
    form = PaiementForm(request.POST or None, initial={"montant": max(solde, ZERO) or None})
    if request.method == "POST" and form.is_valid():
        paiement = form.save(commit=False)
        paiement.client = client
        paiement.agent = _agent(request.user)
        paiement.save()
        messages.success(request, "Paiement enregistré.")
        return redirect("carburant:recu", pk=paiement.pk) if request.POST.get("imprimer") \
            else redirect("carburant:client_detail", pk=client.pk)
    return _formulaire(request, form, f"Encaissement — {client.nom}", "carburant:client_detail", (client.pk,),
                       imprimer=True, info=f"Solde dû par le client : {_gnf(solde)} GNF")


@suppression_requise
@require_POST
def paiement_supprimer(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)
    client_id = paiement.client_id
    paiement.delete()
    messages.success(request, "Paiement supprimé.")
    return redirect("carburant:client_detail", pk=client_id)


def recu(request, pk):
    paiement = get_object_or_404(Paiement.objects.select_related("client"), pk=pk)
    client = Client.objects.prefetch_related("voyages", "paiements").get(pk=paiement.client_id)
    return render(request, "carburant/recu.html", {
        "paiement": paiement, "client": client, "solde": _situation(client)[2],
        "entreprise": request.user.entreprise})


def releve(request, pk):
    """Relevé de compte d'un client sur une période (voyages livrés et paiements)."""
    client = get_object_or_404(Client, pk=pk)
    debut, fin = _dates(request)
    aujourdhui = timezone.localdate()
    debut = debut or aujourdhui.replace(day=1)
    fin = fin or aujourdhui
    livres = _voyages(client.voyages.filter(statut=Voyage.LIVRE))
    paiements = client.paiements.all()
    anterieur = (sum((v.montant_net for v in livres.filter(date_livraison__lt=debut)), ZERO)
                 - (paiements.filter(date__lt=debut).aggregate(t=Sum("montant"))["t"] or ZERO))
    periode_voyages = list(livres.filter(date_livraison__gte=debut, date_livraison__lte=fin)
                           .order_by("date_livraison", "id"))
    periode_paiements = list(paiements.filter(date__gte=debut, date__lte=fin).order_by("date", "id"))
    total_voyages = sum((v.montant_net for v in periode_voyages), ZERO)
    total_paiements = sum((p.montant for p in periode_paiements), ZERO)
    return render(request, "carburant/releve.html", {
        "client": client, "entreprise": request.user.entreprise, "debut": debut, "fin": fin,
        "voyages": periode_voyages, "paiements": periode_paiements, "anterieur": anterieur,
        "total_voyages": total_voyages, "total_paiements": total_paiements,
        "total_litres": sum((v.quantite_livree or ZERO for v in periode_voyages), ZERO),
        "solde_final": anterieur + total_voyages - total_paiements,
    })


# --------------------------------------------------------------------------
# Rapports
# --------------------------------------------------------------------------
def rapports(request):
    debut, fin = _dates(request)
    aujourdhui = timezone.localdate()
    debut = debut or aujourdhui.replace(day=1)
    fin = fin or aujourdhui

    livres = list(_voyages(Voyage.objects.filter(
        statut=Voyage.LIVRE, date_livraison__gte=debut, date_livraison__lte=fin)))
    par_client = defaultdict(lambda: [0, ZERO, ZERO, ZERO])
    par_citerne = defaultdict(lambda: [0, ZERO, ZERO, ZERO])
    par_produit = defaultdict(lambda: [0, ZERO, ZERO])
    libelles = dict(PRODUITS)
    for v in livres:
        for ligne in (par_client[v.client.nom], par_citerne[v.citerne.immatriculation]):
            ligne[0] += 1
            ligne[1] += v.quantite_livree or ZERO
        par_client[v.client.nom][2] += v.manquant_imputable
        par_client[v.client.nom][3] += v.montant_net
        par_citerne[v.citerne.immatriculation][2] += v.montant_net
        par_citerne[v.citerne.immatriculation][3] += v.total_frais
        produit = par_produit[libelles.get(v.produit, v.produit)]
        produit[0] += 1
        produit[1] += v.quantite_chargee or ZERO
        produit[2] += v.quantite_livree or ZERO
    lignes_client = sorted(([n, *vals] for n, vals in par_client.items()), key=lambda x: x[4], reverse=True)
    lignes_citerne = sorted(([n, nb, l, ca, fr, ca - fr] for n, (nb, l, ca, fr) in par_citerne.items()),
                            key=lambda x: x[3], reverse=True)
    lignes_produit = sorted(([n, *vals] for n, vals in par_produit.items()), key=lambda x: x[3], reverse=True)
    totaux = _totaux(livres)
    encaisse = Paiement.objects.filter(date__gte=debut, date__lte=fin).aggregate(t=Sum("montant"))["t"] or ZERO
    periode = f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[n, nb, _litres(l), _litres(m), _gnf(ca)] for n, nb, l, m, ca in lignes_client]
        donnees.append(["TOTAL", len(livres), _litres(totaux["livre"]), _litres(totaux["manquant"]), _gnf(totaux["net"])])
        return reponse_export(
            fmt, "rapport_transport_carburant", "Transport de carburant par client",
            ["Client", "Voyages", "Litres livrés", "Manquants imputables", "Net facturé"], donnees,
            sous_titre=periode, entreprise=_entreprise_nom(request))

    return render(request, "carburant/rapports.html", _ctx(
        request, date_from=debut.isoformat(), date_to=fin.isoformat(), periode=periode, nb=len(livres),
        totaux=totaux, encaisse=encaisse, lignes_client=lignes_client, lignes_citerne=lignes_citerne,
        lignes_produit=lignes_produit))
