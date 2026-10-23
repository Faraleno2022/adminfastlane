"""Vues du module Gestion de projet."""
import os
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ventes.exports import reponse_export

from .forms import ClientForm, MembreForm, MouvementForm, ProjetForm, TacheForm
from .models import Client, Membre, Mouvement, Projet, Tache, ZERO
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


def _projets(qs=None):
    """Projets avec tout ce qu'il faut pour calculer les totaux sans requêtes supplémentaires."""
    qs = Projet.objects.all() if qs is None else qs
    return qs.select_related("client").prefetch_related("mouvements", "taches")


def _paginer(request, elements):
    page = Paginator(elements, PAGE).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("export", None)
    page.qs = params.urlencode()
    return page


def _formulaire(request, form, titre, retour, retour_args=(), **extra):
    return render(request, "projets/formulaire.html", _ctx(
        request, form=form, titre=titre, retour_url=reverse(retour, args=retour_args), **extra))


def _entreprise_nom(request):
    return getattr(request.user.entreprise, "nom_entreprise", "")


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------
def tableau_de_bord(request):
    aujourdhui = timezone.localdate()
    projets = list(_projets())
    ouverts = [p for p in projets if p.statut in Projet.STATUTS_OUVERTS]
    en_cours = [p for p in projets if p.statut == Projet.EN_COURS]
    taches = Tache.objects.filter(statut__in=Tache.STATUTS_OUVERTS, projet__statut__in=Projet.STATUTS_OUVERTS)
    taches_retard = list(taches.filter(date_fin_prevue__lt=aujourdhui).select_related("projet")
                         .order_by("date_fin_prevue")[:10])
    echeances = list(taches.filter(date_fin_prevue__gte=aujourdhui, date_fin_prevue__lte=aujourdhui + timedelta(days=14))
                     .select_related("projet").order_by("date_fin_prevue")[:10])
    debut_mois = aujourdhui.replace(day=1)
    du_mois = Mouvement.objects.filter(date__gte=debut_mois).exclude(projet__statut=Projet.ANNULE)

    return render(request, "projets/tableau_de_bord.html", _ctx(
        request,
        nb_projets=len(projets), nb_ouverts=len(ouverts), nb_en_cours=len(en_cours),
        nb_termines=sum(1 for p in projets if p.statut == Projet.TERMINE),
        nb_clients=Client.objects.count(),
        budget=sum((p.budget for p in ouverts), ZERO),
        depenses=sum((p.total_depenses for p in ouverts), ZERO),
        solde=sum((p.solde_disponible for p in ouverts), ZERO),
        depenses_mois=du_mois.filter(type=Mouvement.DEPENSE).aggregate(t=Sum("montant"))["t"] or ZERO,
        depots_mois=du_mois.filter(type=Mouvement.DEPOT).aggregate(t=Sum("montant"))["t"] or ZERO,
        projets_retard=[p for p in ouverts if p.en_retard][:8],
        projets_depasses=[p for p in ouverts if p.budget_depasse][:8],
        taches_retard=taches_retard, nb_taches_retard=taches.filter(date_fin_prevue__lt=aujourdhui).count(),
        echeances=echeances, en_cours=en_cours[:10]))


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
def clients(request):
    q = (request.GET.get("q") or "").strip()
    qs = Client.objects.prefetch_related("projets")
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(contact__icontains=q) | Q(telephone__icontains=q)
                       | Q(email__icontains=q))
    return render(request, "projets/clients.html", _ctx(request, page=_paginer(request, list(qs)), q=q))


def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    projets = list(_projets(client.projets.all()))
    return render(request, "projets/client_detail.html", _ctx(
        request, client=client, projets=projets,
        budget=sum((p.budget for p in projets if p.statut != Projet.ANNULE), ZERO),
        depots=sum((p.total_depots for p in projets if p.statut != Projet.ANNULE), ZERO)))


@saisie_requise
def client_nouveau(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client « {client.nom} » enregistré.")
        return redirect("projets:client_detail", pk=client.pk)
    return _formulaire(request, form, "Nouveau client", "projets:clients")


@saisie_requise
def client_modifier(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client mis à jour.")
        return redirect("projets:client_detail", pk=client.pk)
    return _formulaire(request, form, f"Modifier : {client.nom}", "projets:client_detail", (client.pk,))


@suppression_requise
@require_POST
def client_supprimer(request, pk):
    client = get_object_or_404(Client, pk=pk)
    try:
        client.delete()
    except ProtectedError:
        messages.error(request, "Ce client a des projets : suppression impossible.")
        return redirect("projets:client_detail", pk=pk)
    messages.success(request, "Client supprimé.")
    return redirect("projets:clients")


# --------------------------------------------------------------------------
# Projets
# --------------------------------------------------------------------------
def projets(request):
    q = (request.GET.get("q") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    filtre = (request.GET.get("filtre") or "").strip()
    qs = _projets()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(nom__icontains=q) | Q(client__nom__icontains=q)
                       | Q(responsable__icontains=q) | Q(ville__icontains=q))
    if statut in dict(Projet.STATUTS):
        qs = qs.filter(statut=statut)
    lignes = list(qs)
    if filtre == "retard":
        lignes = [p for p in lignes if p.en_retard]
    elif filtre == "depasse":
        lignes = [p for p in lignes if p.budget_depasse and p.statut != Projet.ANNULE]

    comptes = [p for p in lignes if p.statut != Projet.ANNULE]
    totaux = {
        "budget": sum((p.budget for p in comptes), ZERO),
        "depots": sum((p.total_depots for p in comptes), ZERO),
        "depenses": sum((p.total_depenses for p in comptes), ZERO),
        "solde": sum((p.solde_disponible for p in comptes), ZERO),
    }

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[p.reference, p.nom, p.client.nom if p.client else "", p.responsable, p.get_statut_display(),
                    p.date_debut.strftime("%d/%m/%Y") if p.date_debut else "",
                    p.date_fin_prevue.strftime("%d/%m/%Y") if p.date_fin_prevue else "", f"{p.progression} %",
                    _gnf(p.budget), _gnf(p.total_depots), _gnf(p.total_depenses), _gnf(p.solde_disponible)]
                   for p in lignes]
        donnees.append(["TOTAL", f"{len(lignes)} projet(s)", "", "", "", "", "", "", _gnf(totaux["budget"]),
                        _gnf(totaux["depots"]), _gnf(totaux["depenses"]), _gnf(totaux["solde"])])
        return reponse_export(
            fmt, "projets", "Liste des projets",
            ["Code", "Projet", "Client", "Chef de projet", "Statut", "Début", "Fin prévue", "Avancement",
             "Budget", "Dépôts", "Dépenses", "Solde"],
            donnees, sous_titre=f"{len(lignes)} projet(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=_entreprise_nom(request))

    return render(request, "projets/projets.html", _ctx(
        request, page=_paginer(request, lignes), nb=len(lignes), totaux=totaux, q=q, statut=statut, filtre=filtre,
        statuts=Projet.STATUTS))


def projet_detail(request, pk):
    projet = get_object_or_404(_projets().prefetch_related("membres"), pk=pk)
    mouvements = list(projet.mouvements.all())
    par_categorie = defaultdict(lambda: ZERO)
    libelles = dict(Mouvement.CATEGORIES)
    for m in mouvements:
        if m.type == Mouvement.DEPENSE:
            par_categorie[libelles.get(m.categorie, "Autre")] += m.montant
    return render(request, "projets/projet_detail.html", _ctx(
        request, projet=projet, taches=list(projet.taches.all()), membres=list(projet.membres.all()),
        mouvements=mouvements, statuts=Projet.STATUTS,
        par_categorie=sorted(par_categorie.items(), key=lambda x: x[1], reverse=True)))


@saisie_requise
def projet_nouveau(request):
    initial = {}
    if request.GET.get("client"):
        initial["client"] = request.GET["client"]
    form = ProjetForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        projet = form.save(commit=False)
        projet.cree_par = _agent(request.user)
        projet.save()
        messages.success(request, f"Projet {projet.reference} créé.")
        return redirect("projets:projet_detail", pk=projet.pk)
    return _formulaire(request, form, "Nouveau projet", "projets:projets")


@saisie_requise
def projet_modifier(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    form = ProjetForm(request.POST or None, instance=projet)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Projet mis à jour.")
        return redirect("projets:projet_detail", pk=projet.pk)
    return _formulaire(request, form, f"Modifier le projet {projet.reference}", "projets:projet_detail", (projet.pk,))


@saisie_requise
@require_POST
def projet_statut(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    nouveau = request.POST.get("statut")
    if nouveau in dict(Projet.STATUTS):
        projet.statut = nouveau
        projet.save(update_fields=["statut", "date_fin_reelle"])
        messages.success(request, f"Projet {projet.reference} : {projet.get_statut_display().lower()}.")
    return redirect("projets:projet_detail", pk=projet.pk)


@suppression_requise
@require_POST
def projet_supprimer(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    if projet.mouvements.exists():
        messages.error(request, "Des mouvements financiers sont enregistrés : annulez le projet plutôt que de le supprimer.")
        return redirect("projets:projet_detail", pk=pk)
    projet.delete()
    messages.success(request, "Projet supprimé.")
    return redirect("projets:projets")


def fiche(request, pk):
    """Fiche de synthèse du projet, imprimable."""
    projet = get_object_or_404(_projets().prefetch_related("membres"), pk=pk)
    return render(request, "projets/fiche.html", {
        "projet": projet, "entreprise": request.user.entreprise, "taches": list(projet.taches.all()),
        "membres": [m for m in projet.membres.all() if m.actif], "mouvements": list(projet.mouvements.all()),
        "imprime_le": timezone.localtime(),
    })


# --------------------------------------------------------------------------
# Tâches
# --------------------------------------------------------------------------
def taches(request):
    """Planning : toutes les tâches, tous projets confondus."""
    q = (request.GET.get("q") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    priorite = (request.GET.get("priorite") or "").strip()
    projet = (request.GET.get("projet") or "").strip()
    filtre = (request.GET.get("filtre") or "").strip()
    aujourdhui = timezone.localdate()
    qs = Tache.objects.select_related("projet").order_by("date_fin_prevue", "ordre", "id")
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(responsable__icontains=q) | Q(projet__nom__icontains=q)
                       | Q(projet__reference__icontains=q))
    if statut in dict(Tache.STATUTS):
        qs = qs.filter(statut=statut)
    elif statut == "ouvertes":
        qs = qs.filter(statut__in=Tache.STATUTS_OUVERTS)
    if priorite in dict(Tache.PRIORITES):
        qs = qs.filter(priorite=priorite)
    if projet.isdigit():
        qs = qs.filter(projet_id=int(projet))
    if filtre == "retard":
        qs = qs.filter(statut__in=Tache.STATUTS_OUVERTS, date_fin_prevue__lt=aujourdhui)
    elif filtre == "semaine":
        qs = qs.filter(statut__in=Tache.STATUTS_OUVERTS, date_fin_prevue__gte=aujourdhui,
                       date_fin_prevue__lte=aujourdhui + timedelta(days=7))
    lignes = list(qs)

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[t.projet.reference, t.titre, t.responsable, t.get_priorite_display(), t.get_statut_display(),
                    t.date_debut.strftime("%d/%m/%Y") if t.date_debut else "",
                    t.date_fin_prevue.strftime("%d/%m/%Y") if t.date_fin_prevue else "", f"{t.progression} %",
                    f"{t.jours_retard} j" if t.en_retard else ""] for t in lignes]
        return reponse_export(
            fmt, "taches_projets", "Planning des tâches",
            ["Projet", "Tâche", "Responsable", "Priorité", "Statut", "Début", "Échéance", "Progression", "Retard"],
            donnees, sous_titre=f"{len(lignes)} tâche(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=_entreprise_nom(request))

    return render(request, "projets/taches.html", _ctx(
        request, page=_paginer(request, lignes), nb=len(lignes), q=q, statut=statut, priorite=priorite,
        projet=projet, filtre=filtre, statuts=Tache.STATUTS, priorites=Tache.PRIORITES,
        liste_projets=Projet.objects.only("id", "reference", "nom")))


def _retour_tache(request, tache):
    if request.POST.get("retour") == "planning" or request.GET.get("retour") == "planning":
        return redirect("projets:taches")
    return redirect("projets:projet_detail", pk=tache.projet_id)


@saisie_requise
def tache_nouvelle(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    form = TacheForm(request.POST or None, initial={
        "date_debut": projet.date_debut or timezone.localdate(), "ordre": projet.taches.count() + 1})
    if request.method == "POST" and form.is_valid():
        tache = form.save(commit=False)
        tache.projet = projet
        tache.save()
        messages.success(request, "Tâche ajoutée.")
        return redirect("projets:projet_detail", pk=projet.pk)
    return _formulaire(request, form, f"Nouvelle tâche — {projet.reference}", "projets:projet_detail", (projet.pk,))


@saisie_requise
def tache_modifier(request, pk):
    tache = get_object_or_404(Tache, pk=pk)
    form = TacheForm(request.POST or None, instance=tache)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tâche mise à jour.")
        return _retour_tache(request, tache)
    return _formulaire(request, form, f"Modifier la tâche : {tache.titre}", "projets:projet_detail", (tache.projet_id,))


@saisie_requise
@require_POST
def tache_statut(request, pk):
    tache = get_object_or_404(Tache, pk=pk)
    nouveau = request.POST.get("statut")
    if nouveau in dict(Tache.STATUTS):
        tache.statut = nouveau
        if nouveau == Tache.EN_COURS and not tache.progression:
            tache.progression = 10
        tache.save()
        messages.success(request, f"Tâche « {tache.titre} » : {tache.get_statut_display().lower()}.")
    return _retour_tache(request, tache)


@suppression_requise
@require_POST
def tache_supprimer(request, pk):
    tache = get_object_or_404(Tache, pk=pk)
    tache.delete()
    messages.success(request, "Tâche supprimée.")
    return _retour_tache(request, tache)


# --------------------------------------------------------------------------
# Équipe
# --------------------------------------------------------------------------
@saisie_requise
def membre_nouveau(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    form = MembreForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        membre = form.save(commit=False)
        membre.projet = projet
        membre.save()
        messages.success(request, f"{membre.nom} ajouté(e) à l'équipe.")
        return redirect("projets:projet_detail", pk=projet.pk)
    return _formulaire(request, form, f"Affecter une personne — {projet.reference}", "projets:projet_detail", (projet.pk,))


@saisie_requise
def membre_modifier(request, pk):
    membre = get_object_or_404(Membre, pk=pk)
    form = MembreForm(request.POST or None, instance=membre)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Affectation mise à jour.")
        return redirect("projets:projet_detail", pk=membre.projet_id)
    return _formulaire(request, form, f"Modifier : {membre.nom}", "projets:projet_detail", (membre.projet_id,))


@suppression_requise
@require_POST
def membre_supprimer(request, pk):
    membre = get_object_or_404(Membre, pk=pk)
    projet_id = membre.projet_id
    membre.delete()
    messages.success(request, "Personne retirée de l'équipe.")
    return redirect("projets:projet_detail", pk=projet_id)


# --------------------------------------------------------------------------
# Mouvements financiers
# --------------------------------------------------------------------------
def _info_solde(projet):
    projet = _projets().get(pk=projet.pk)
    return f"Solde disponible du projet : {_gnf(projet.solde_disponible)} GNF"


@saisie_requise
def mouvement_nouveau(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    type_initial = request.GET.get("type") if request.GET.get("type") in dict(Mouvement.TYPES) else Mouvement.DEPENSE
    form = MouvementForm(request.POST or None, request.FILES or None, initial={"type": type_initial})
    if request.method == "POST" and form.is_valid():
        mouvement = form.save(commit=False)
        mouvement.projet = projet
        mouvement.saisi_par = _agent(request.user)
        mouvement.save()
        messages.success(request, f"{mouvement.get_type_display().split(' (')[0]} enregistré(e).")
        return redirect("projets:projet_detail", pk=projet.pk)
    return _formulaire(request, form, f"Mouvement financier — {projet.reference}", "projets:projet_detail",
                       (projet.pk,), info=_info_solde(projet), fichiers=True)


@saisie_requise
def mouvement_modifier(request, pk):
    mouvement = get_object_or_404(Mouvement, pk=pk)
    form = MouvementForm(request.POST or None, request.FILES or None, instance=mouvement)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mouvement mis à jour.")
        return redirect("projets:projet_detail", pk=mouvement.projet_id)
    return _formulaire(request, form, f"Modifier : {mouvement.libelle}", "projets:projet_detail",
                       (mouvement.projet_id,), fichiers=True)


@suppression_requise
@require_POST
def mouvement_supprimer(request, pk):
    mouvement = get_object_or_404(Mouvement, pk=pk)
    projet_id = mouvement.projet_id
    if mouvement.piece:
        mouvement.piece.delete(save=False)
    mouvement.delete()
    messages.success(request, "Mouvement supprimé.")
    return redirect("projets:projet_detail", pk=projet_id)


def mouvement_piece(request, pk):
    """Sert la pièce justificative après contrôle de l'entreprise (pas de lien /media/ direct)."""
    mouvement = get_object_or_404(Mouvement, pk=pk)
    if not mouvement.piece:
        raise Http404
    try:
        fichier = mouvement.piece.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    return FileResponse(fichier, filename=os.path.basename(mouvement.piece.name))


def mouvements(request):
    """Journal de tous les mouvements financiers."""
    q = (request.GET.get("q") or "").strip()
    type_ = (request.GET.get("type") or "").strip()
    categorie = (request.GET.get("categorie") or "").strip()
    projet = (request.GET.get("projet") or "").strip()
    debut, fin = _dates(request)
    qs = Mouvement.objects.select_related("projet")
    if q:
        qs = qs.filter(Q(libelle__icontains=q) | Q(beneficiaire__icontains=q) | Q(reference__icontains=q)
                       | Q(projet__reference__icontains=q) | Q(projet__nom__icontains=q))
    if type_ in dict(Mouvement.TYPES):
        qs = qs.filter(type=type_)
    if categorie in dict(Mouvement.CATEGORIES):
        qs = qs.filter(categorie=categorie)
    if projet.isdigit():
        qs = qs.filter(projet_id=int(projet))
    if debut:
        qs = qs.filter(date__gte=debut)
    if fin:
        qs = qs.filter(date__lte=fin)
    lignes = list(qs)
    totaux = {t: sum((m.montant for m in lignes if m.type == t), ZERO) for t in dict(Mouvement.TYPES)}

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[m.date.strftime("%d/%m/%Y"), m.projet.reference, m.get_type_display(),
                    m.get_categorie_display() if m.categorie else "", m.libelle, m.beneficiaire,
                    m.get_mode_display(), m.reference, _gnf(m.montant)] for m in lignes]
        for code, libelle in Mouvement.TYPES:
            donnees.append([f"TOTAL {libelle.upper()}", "", "", "", "", "", "", "", _gnf(totaux[code])])
        return reponse_export(
            fmt, "mouvements_projets", "Mouvements financiers des projets",
            ["Date", "Projet", "Type", "Catégorie", "Libellé", "Bénéficiaire", "Mode", "Référence", "Montant"],
            donnees, sous_titre=f"{len(lignes)} mouvement(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=_entreprise_nom(request))

    return render(request, "projets/mouvements.html", _ctx(
        request, page=_paginer(request, lignes), nb=len(lignes), totaux=totaux, q=q, type=type_,
        categorie=categorie, projet=projet, types=Mouvement.TYPES, categories=Mouvement.CATEGORIES,
        date_from=request.GET.get("date_from", ""), date_to=request.GET.get("date_to", ""),
        liste_projets=Projet.objects.only("id", "reference", "nom")))


# --------------------------------------------------------------------------
# Rapports
# --------------------------------------------------------------------------
def rapports(request):
    debut, fin = _dates(request)
    aujourdhui = timezone.localdate()
    debut = debut or aujourdhui.replace(day=1)
    fin = fin or aujourdhui

    mouvements_periode = list(Mouvement.objects.filter(date__gte=debut, date__lte=fin).select_related("projet"))
    libelles = dict(Mouvement.CATEGORIES)
    par_categorie = defaultdict(lambda: ZERO)
    par_projet = defaultdict(lambda: [ZERO, ZERO, ZERO])
    for m in mouvements_periode:
        ligne = par_projet[m.projet]
        if m.type == Mouvement.DEPOT:
            ligne[0] += m.montant
        elif m.type == Mouvement.RETRAIT:
            ligne[1] += m.montant
        else:
            ligne[2] += m.montant
            par_categorie[libelles.get(m.categorie, "Autre")] += m.montant
    lignes_categorie = sorted(par_categorie.items(), key=lambda x: x[1], reverse=True)
    lignes_projet = sorted(([p, d, r, dep] for p, (d, r, dep) in par_projet.items()), key=lambda x: x[3], reverse=True)
    total_depots = sum((l[1] for l in lignes_projet), ZERO)
    total_retraits = sum((l[2] for l in lignes_projet), ZERO)
    total_depenses = sum((l[3] for l in lignes_projet), ZERO)
    periode = f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"

    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[p.reference, p.nom, _gnf(d), _gnf(r), _gnf(dep)] for p, d, r, dep in lignes_projet]
        donnees.append(["TOTAL", "", _gnf(total_depots), _gnf(total_retraits), _gnf(total_depenses)])
        return reponse_export(
            fmt, "rapport_projets", "Mouvements financiers par projet",
            ["Code", "Projet", "Dépôts", "Retraits", "Dépenses"], donnees, sous_titre=periode,
            entreprise=_entreprise_nom(request))

    termines = Projet.objects.filter(statut=Projet.TERMINE, date_fin_reelle__gte=debut, date_fin_reelle__lte=fin).count()
    return render(request, "projets/rapports.html", _ctx(
        request, date_from=debut.isoformat(), date_to=fin.isoformat(), periode=periode,
        total_depots=total_depots, total_retraits=total_retraits, total_depenses=total_depenses,
        nb_termines=termines, lignes_categorie=lignes_categorie, lignes_projet=lignes_projet))
