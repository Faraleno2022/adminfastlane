"""Vues du module Ventes & caisse."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import exports, services
from .forms import ClientForm, ParametresForm, ProduitForm
from .models import (
    ClientCompte, DemandeStock, EcritureCaisse, JournalAudit, MouvementStock, Operation,
    ParametreVentes, Produit, Vente, ZERO,
)
from .permissions import (
    admin_requis, est_admin, peut_saisir, peut_supprimer, saisie_requise, suppression_requise,
)
from .services import ErreurMetier, fmt_gnf

PAGE = 50


def _page(request, qs, par_page=PAGE):
    page = Paginator(qs, par_page).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    page.qs = params.urlencode()  # filtres à conserver dans les liens de pagination
    return page


def _periode(request):
    debut = (request.GET.get("date_from") or "").strip()
    fin = (request.GET.get("date_to") or "").strip()
    try:
        debut = date.fromisoformat(debut) if debut else None
        fin = date.fromisoformat(fin) if fin else None
    except ValueError:
        debut = fin = None
    return debut, fin


def _filtrer_dates(qs, champ, debut, fin):
    if debut:
        qs = qs.filter(**{f"{champ}__date__gte": debut})
    if fin:
        qs = qs.filter(**{f"{champ}__date__lte": fin})
    return qs


def _ctx(request, **extra):
    base = {
        "peut_saisir": peut_saisir(request.user),
        "peut_supprimer": peut_supprimer(request.user),
        "est_admin": est_admin(request.user),
    }
    base.update(extra)
    return base


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------
def tableau_de_bord(request):
    stats = services.stats_tableau_de_bord()
    return render(request, "ventes/tableau_de_bord.html", _ctx(
        request, s=stats,
        recentes=Operation.objects.filter(deleted=False)[:10],
        dernieres_ventes=Vente.objects.filter(deleted=False)[:10],
    ))


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
def clients(request):
    recherche = (request.GET.get("q") or "").strip()
    lignes = services.soldes_clients(recherche)
    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        donnees = [[l["matricule"], l["nom"], l["telephone"], fmt_gnf(l["solde"]), l["nb_ops"],
                    "Oui" if l["fiche"] else "Non"] for l in lignes]
        total = sum((l["solde"] for l in lignes), ZERO)
        donnees.append(["TOTAL", f"{len(lignes)} compte(s)", "", fmt_gnf(total), "", ""])
        return exports.reponse_export(
            fmt, "clients_soldes", "Clients et soldes",
            ["Matricule", "Nom", "Téléphone", "Solde", "Opérations", "Fiche client"], donnees,
            sous_titre=f"{len(lignes)} compte(s) — {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))
    return render(request, "ventes/clients.html", _ctx(
        request, lignes=lignes[:500], q=recherche,
        total=sum((l["solde"] for l in lignes), ZERO), nb=len(lignes)))


@saisie_requise
def client_nouveau(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        services.audit(request.user, "client_create", "client", client.pk, client.matricule)
        messages.success(request, f"Fiche client « {client.matricule} » créée.")
        return redirect("ventes:clients")
    return render(request, "ventes/formulaire.html", _ctx(request, form=form, titre="Nouveau client",
                                                          retour="ventes:clients"))


@admin_requis
def client_modifier(request, pk):
    client = get_object_or_404(ClientCompte, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        services.audit(request.user, "client_update", "client", client.pk, client.matricule)
        messages.success(request, "Fiche client mise à jour.")
        return redirect("ventes:clients")
    return render(request, "ventes/formulaire.html", _ctx(request, form=form, titre=f"Modifier {client.matricule}",
                                                          retour="ventes:clients"))


@admin_requis
@require_POST
def client_basculer(request, pk):
    client = get_object_or_404(ClientCompte, pk=pk)
    client.actif = not client.actif
    client.save()
    services.audit(request.user, "client_toggle", "client", client.pk, f"{client.matricule} actif={client.actif}")
    messages.success(request, f"Fiche « {client.matricule} » {'réactivée' if client.actif else 'envoyée à la corbeille'}.")
    return redirect("ventes:clients")


def solde_api(request):
    matricule = (request.GET.get("matricule") or "").strip()
    if not matricule:
        return JsonResponse({"ok": False, "solde": 0})
    solde = services.solde_matricule(matricule)
    fiche = ClientCompte.objects.filter(matricule=matricule, actif=True).first()
    return JsonResponse({
        "ok": True, "solde": float(solde), "solde_txt": fmt_gnf(solde),
        "nom": fiche.nom if fiche else "", "telephone": fiche.telephone if fiche else "",
        "deja_depose": float(services.depots_du_jour(matricule)),
    })


# --------------------------------------------------------------------------
# Dépôts, retraits, ventes
# --------------------------------------------------------------------------
@saisie_requise
def depot_nouveau(request):
    erreur = None
    if request.method == "POST":
        try:
            op = services.creer_depot(
                request.user, request.POST.get("matricule"), request.POST.get("telephone"),
                request.POST.get("montant"), request.POST.get("note"))
            messages.success(request, f"Dépôt de {fmt_gnf(op.montant)} enregistré pour {op.matricule}. "
                                      f"Nouveau solde : {fmt_gnf(op.solde_apres)}.")
            request.session["dernier_ticket"] = {"kind": "operation", "pk": op.pk}
            return redirect("ventes:depot_nouveau")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/depot_form.html", _ctx(
        request, erreur=erreur, ticket=request.session.get("dernier_ticket"),
        plafond=ParametreVentes.courant().plafond_depot_journalier,
        post=request.POST if erreur else {}))


@saisie_requise
def retrait_nouveau(request):
    erreur = None
    if request.method == "POST":
        try:
            if request.POST.get("confirme") != "1":
                raise ErreurMetier("Vous devez confirmer les produits et le montant avant de valider.")
            ids, qtes = request.POST.getlist("prod_id"), request.POST.getlist("prod_qte")
            if len(ids) != len(qtes):
                raise ErreurMetier("Les lignes de produits sont incomplètes.")
            genre, resultat = services.creer_retrait_ou_vente(
                request.user, request.POST.get("matricule"), request.POST.get("telephone"),
                request.POST.get("note"), request.POST.get("mode_paiement") or "compte",
                list(zip(ids, qtes)), request.POST.get("montant"))
            if genre == "vente":
                total = sum((v.montant_total for v in resultat), ZERO)
                messages.success(request, f"Vente de {fmt_gnf(total)} enregistrée"
                                          + (f" pour {resultat[0].matricule}. Nouveau solde : {fmt_gnf(resultat[-1].solde_apres)}."
                                             if resultat[0].matricule else " (encaissée en caisse)."))
                request.session["dernier_ticket"] = {"kind": "vente", "pk": resultat[0].pk,
                                                     "pks": [v.pk for v in resultat]}
            else:
                messages.success(request, f"Retrait de {fmt_gnf(resultat.montant)} enregistré pour {resultat.matricule}. "
                                          f"Nouveau solde : {fmt_gnf(resultat.solde_apres)}.")
                request.session["dernier_ticket"] = {"kind": "operation", "pk": resultat.pk}
            return redirect("ventes:retrait_nouveau")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/retrait_form.html", _ctx(
        request, erreur=erreur, ticket=request.session.get("dernier_ticket"),
        produits=Produit.objects.filter(actif=True).order_by("nom"),
        post=request.POST if erreur else {}))


def operations(request):
    qs = Operation.objects.filter(deleted=False)
    q = (request.GET.get("q") or "").strip()
    type_ = (request.GET.get("type") or "").strip()
    debut, fin = _periode(request)
    if q:
        qs = qs.filter(Q(matricule__icontains=q) | Q(note__icontains=q) | Q(agent_nom__icontains=q))
    if type_ in (Operation.DEPOT, Operation.RETRAIT):
        qs = qs.filter(type=type_)
    qs = _filtrer_dates(qs, "created_at", debut, fin)
    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        return exports.reponse_export(
            fmt, "operations", "Dépôts et retraits",
            ["Date", "Matricule", "Type", "Montant", "Solde après", "Agent", "Note"],
            [[f"{timezone.localtime(o.created_at):%d/%m/%Y %H:%M}", o.matricule, o.get_type_display(), o.montant,
              o.solde_apres, o.agent_nom, o.note] for o in qs],
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))
    return render(request, "ventes/operations.html", _ctx(
        request, page=_page(request, qs), q=q, type=type_,
        debut=debut or "", fin=fin or "",
        total_depots=qs.filter(type=Operation.DEPOT).aggregate(s=Sum("montant"))["s"] or ZERO,
        total_retraits=qs.filter(type=Operation.RETRAIT).aggregate(s=Sum("montant"))["s"] or ZERO))


@suppression_requise
@require_POST
def operation_supprimer(request, pk):
    op = get_object_or_404(Operation, pk=pk, deleted=False)
    try:
        services.supprimer_operation(request.user, op)
        messages.success(request, f"{op.get_type_display()} de {fmt_gnf(op.montant)} ({op.matricule}) envoyé à la corbeille.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:operations")


def ventes(request):
    qs = Vente.objects.filter(deleted=False)
    q = (request.GET.get("q") or "").strip()
    debut, fin = _periode(request)
    if q:
        qs = qs.filter(Q(matricule__icontains=q) | Q(produit_nom__icontains=q) | Q(agent_nom__icontains=q))
    qs = _filtrer_dates(qs, "created_at", debut, fin)
    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        return exports.reponse_export(
            fmt, "ventes", "Ventes",
            ["Date", "Matricule", "Produit", "Quantité", "Prix unitaire", "Montant", "Paiement", "Agent"],
            [[f"{timezone.localtime(v.created_at):%d/%m/%Y %H:%M}", v.matricule or "—", v.produit_nom, v.quantite,
              v.prix_unitaire, v.montant_total, v.get_mode_paiement_display(), v.agent_nom] for v in qs],
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))
    return render(request, "ventes/ventes.html", _ctx(
        request, page=_page(request, qs), q=q, debut=debut or "", fin=fin or "",
        total=qs.aggregate(s=Sum("montant_total"))["s"] or ZERO))


@suppression_requise
@require_POST
def vente_supprimer(request, pk):
    vente = get_object_or_404(Vente, pk=pk, deleted=False)
    try:
        services.supprimer_vente(request.user, vente)
        messages.success(request, f"Vente « {vente.produit_nom} » envoyée à la corbeille. Stock rendu et solde recalculé.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:ventes")


def ticket(request, kind, pk):
    """Ticket de caisse imprimable (80 mm)."""
    param = ParametreVentes.courant()
    if kind == "operation":
        obj = get_object_or_404(Operation, pk=pk)
        lignes, total, solde = [], obj.montant, obj.solde_apres
        titre = "REÇU DE DÉPÔT" if obj.type == Operation.DEPOT else "REÇU DE RETRAIT"
        ref, date_op, agent, matricule = f"OP-{obj.pk}", obj.created_at, obj.agent_nom, obj.matricule
    else:
        obj = get_object_or_404(Vente, pk=pk)
        pks = (request.session.get("dernier_ticket") or {}).get("pks") or [obj.pk]
        ventes_lot = list(Vente.objects.filter(pk__in=pks, deleted=False)) or [obj]
        lignes = [(v.produit_nom, v.quantite, v.prix_unitaire, v.montant_total) for v in ventes_lot]
        total = sum((v.montant_total for v in ventes_lot), ZERO)
        solde = ventes_lot[-1].solde_apres if obj.mode_paiement == Vente.COMPTE else None
        titre = "TICKET DE VENTE"
        ref, date_op, agent, matricule = f"V-{obj.pk}", obj.created_at, obj.agent_nom, obj.matricule
    return render(request, "ventes/ticket.html", {
        "param": param, "entreprise": request.user.entreprise, "titre": titre, "ref": ref,
        "date_op": date_op, "agent": agent, "matricule": matricule, "lignes": lignes,
        "total": total, "solde": solde, "obj": obj,
    })


# --------------------------------------------------------------------------
# Caisse
# --------------------------------------------------------------------------
def caisse(request):
    debut, fin = _periode(request)
    journal = services.journal_caisse(debut, fin)
    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        return exports.reponse_export(
            fmt, "caisse", "Caisse", ["Date", "Libellé", "Entrées", "Sorties", "Solde progressif", "Agent"],
            [[e.date.strftime("%d/%m/%Y"), e.libelle, e.entree or "", e.sortie or "", solde, e.agent_nom]
             for e, solde in journal],
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))
    return render(request, "ventes/caisse.html", _ctx(
        request, lignes=list(reversed(journal)), solde=services.solde_caisse(),
        total_entrees=sum((e.entree for e, _ in journal), ZERO),
        total_sorties=sum((e.sortie for e, _ in journal), ZERO),
        a_ouverture=EcritureCaisse.objects.filter(source=EcritureCaisse.OUVERTURE, deleted=False).exists(),
        aujourdhui=timezone.localdate(), debut=debut or "", fin=fin or ""))


@saisie_requise
@require_POST
def ecriture_nouvelle(request):
    try:
        date_saisie = request.POST.get("date") or ""
        try:
            jour = date.fromisoformat(date_saisie) if date_saisie else None
        except ValueError:
            raise ErreurMetier("Date invalide : format attendu AAAA-MM-JJ.")
        services.ecriture_caisse(request.user, request.POST.get("libelle"), request.POST.get("sens"),
                                 request.POST.get("montant"), jour)
        messages.success(request, f"Écriture enregistrée. Solde de la caisse : {fmt_gnf(services.solde_caisse())}.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:caisse")


@suppression_requise
@require_POST
def ecriture_annuler(request, pk):
    ecriture = get_object_or_404(EcritureCaisse, pk=pk, deleted=False)
    try:
        services.annuler_ecriture(request.user, ecriture)
        messages.success(request, "Écriture annulée.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:caisse")


# --------------------------------------------------------------------------
# Produits et stock
# --------------------------------------------------------------------------
def produits(request):
    q = (request.GET.get("q") or "").strip()
    qs = Produit.objects.filter(actif=True)
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(reference__icontains=q) | Q(categorie__icontains=q))
    liste = list(qs.order_by("nom"))
    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        return exports.reponse_export(
            fmt, "produits", "Produits et stock",
            ["Référence", "Produit", "Catégorie", "Prix de vente", "Stock", "Seuil", "Valeur"],
            [[p.reference, p.nom, p.categorie, p.prix_unitaire, p.quantite_stock if p.suivi_stock else "—",
              p.seuil_alerte, p.valeur_stock if p.suivi_stock else ""] for p in liste],
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))
    return render(request, "ventes/produits.html", _ctx(
        request, produits=liste, q=q, demandes=DemandeStock.objects.filter(statut=DemandeStock.EN_ATTENTE).count()))


@admin_requis
def produit_nouveau(request):
    form = ProduitForm(request.POST or None)
    erreur = None
    if request.method == "POST" and form.is_valid():
        try:
            stock_initial = services.nombre(request.POST.get("stock_initial") or 0, "Stock initial")
            if stock_initial < 0:
                raise ErreurMetier("Le stock initial ne peut pas être négatif.")
            with services.verrou():
                produit = form.save()
                if stock_initial > 0 and produit.suivi_stock:
                    services.ajuster_stock(request.user, produit, MouvementStock.ENTREE, stock_initial, "Stock initial")
            services.audit(request.user, "product_create", "produit", produit.pk, produit.nom)
            messages.success(request, f"Produit « {produit.nom} » créé.")
            return redirect("ventes:produits")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/produit_form.html", _ctx(request, form=form, titre="Nouveau produit",
                                                            erreur=erreur, creation=True))


@admin_requis
def produit_modifier(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    form = ProduitForm(request.POST or None, instance=produit)
    if request.method == "POST" and form.is_valid():
        form.save()
        services.audit(request.user, "product_update", "produit", produit.pk, produit.nom)
        messages.success(request, "Produit mis à jour.")
        return redirect("ventes:produits")
    return render(request, "ventes/produit_form.html", _ctx(request, form=form, titre=f"Modifier {produit.nom}"))


@admin_requis
@require_POST
def produit_basculer(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    produit.actif = not produit.actif
    produit.save()
    services.audit(request.user, "product_toggle", "produit", produit.pk, f"{produit.nom} actif={produit.actif}")
    messages.success(request, f"Produit « {produit.nom} » {'réactivé' if produit.actif else 'envoyé à la corbeille'}.")
    return redirect("ventes:produits")


def produit_recherche_api(request):
    q = (request.GET.get("q") or "").strip()
    qs = Produit.objects.filter(actif=True)
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(reference__icontains=q))
    return JsonResponse({"produits": [
        {"id": p.pk, "nom": p.nom, "reference": p.reference, "prix": float(p.prix_unitaire),
         "stock": float(p.quantite_stock), "suivi": p.suivi_stock}
        for p in qs.order_by("nom")[:30]]})


@admin_requis
def stock_ajuster(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    erreur = None
    if request.method == "POST":
        try:
            mv = services.ajuster_stock(request.user, produit, request.POST.get("type"),
                                        request.POST.get("quantite"), request.POST.get("motif"))
            messages.success(request, f"{mv.get_type_display()} de {mv.quantite:g} enregistrée pour « {produit.nom} ». "
                                      f"Stock : {mv.stock_apres:g}.")
            return redirect("ventes:produits")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/stock_form.html", _ctx(request, produit=produit, erreur=erreur))


@saisie_requise
def demande_entree(request, pk):
    produit = get_object_or_404(Produit, pk=pk, actif=True)
    erreur = None
    if request.method == "POST":
        try:
            services.creer_demande_entree(request.user, produit, request.POST.get("quantite"), request.POST.get("motif"))
            messages.success(request, "Demande d'entrée envoyée : elle sera appliquée après validation d'un administrateur.")
            return redirect("ventes:produits")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/demande_form.html", _ctx(request, produit=produit, erreur=erreur, nouveau=False))


@saisie_requise
def demande_produit(request):
    erreur = None
    if request.method == "POST":
        try:
            services.creer_demande_produit(
                request.user, request.POST.get("nom"), request.POST.get("reference"), request.POST.get("prix"),
                request.POST.get("seuil"), request.POST.get("description"), request.POST.get("quantite"),
                request.POST.get("motif"))
            messages.success(request, "Proposition envoyée : le produit sera créé après validation d'un administrateur.")
            return redirect("ventes:produits")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/demande_form.html", _ctx(request, erreur=erreur, nouveau=True,
                                                            post=request.POST if erreur else {}))


@admin_requis
def validations(request):
    return render(request, "ventes/validations.html", _ctx(
        request, en_attente=DemandeStock.objects.filter(statut=DemandeStock.EN_ATTENTE),
        traitees=DemandeStock.objects.exclude(statut=DemandeStock.EN_ATTENTE)[:30]))


@admin_requis
@require_POST
def demande_valider(request, pk):
    demande = get_object_or_404(DemandeStock, pk=pk)
    try:
        _, produit = services.valider_demande(request.user, demande)
        messages.success(request, f"Demande validée pour « {produit.nom} ». Stock réel : {produit.quantite_stock:g}.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:validations")


@admin_requis
@require_POST
def demande_rejeter(request, pk):
    demande = get_object_or_404(DemandeStock, pk=pk)
    try:
        services.rejeter_demande(request.user, demande, request.POST.get("motif"))
        messages.info(request, f"Demande pour « {demande.produit_nom} » rejetée. Le stock n'a pas été modifié.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:validations")


def mouvements(request):
    qs = MouvementStock.objects.filter(deleted=False).select_related("produit")
    q = (request.GET.get("q") or "").strip()
    debut, fin = _periode(request)
    if q:
        qs = qs.filter(Q(produit_nom__icontains=q) | Q(motif__icontains=q) | Q(agent_nom__icontains=q))
    qs = _filtrer_dates(qs, "created_at", debut, fin)
    return render(request, "ventes/mouvements.html", _ctx(request, page=_page(request, qs), q=q,
                                                          debut=debut or "", fin=fin or ""))


@admin_requis
def inventaire(request):
    liste = list(Produit.objects.filter(actif=True, suivi_stock=True).order_by("nom"))
    erreur = None
    fmt = request.GET.get("export")
    if fmt in ("xlsx", "pdf"):
        return exports.reponse_export(
            fmt, "inventaire", "Feuille d'inventaire",
            ["Référence", "Produit", "Prix", "Stock théorique", "Stock compté", "Écart", "Valeur"],
            [[p.reference, p.nom, p.prix_unitaire, p.quantite_stock, "", "", p.valeur_stock] for p in liste],
            sous_titre=f"Au {timezone.localtime():%d/%m/%Y %H:%M}",
            entreprise=getattr(request.user.entreprise, "nom_entreprise", ""))
    if request.method == "POST":
        try:
            comptages = {p.pk: request.POST.get(f"count_{p.pk}") for p in liste}
            ajustements = services.compter_inventaire(request.user, comptages, request.POST.get("motif"))
            if ajustements:
                messages.success(request, f"Inventaire enregistré : {len(ajustements)} produit(s) compté(s).")
            else:
                messages.info(request, "Aucune quantité comptée saisie : aucun stock modifié.")
            return redirect("ventes:inventaire")
        except ErreurMetier as exc:
            erreur = str(exc)
    return render(request, "ventes/inventaire.html", _ctx(
        request, produits=liste, erreur=erreur,
        total_valeur=sum((p.valeur_stock for p in liste), ZERO),
        total_unites=sum((p.quantite_stock for p in liste), ZERO)))


# --------------------------------------------------------------------------
# Corbeille
# --------------------------------------------------------------------------
@suppression_requise
def corbeille(request):
    return render(request, "ventes/corbeille.html", _ctx(
        request,
        operations=Operation.objects.filter(deleted=True)[:100],
        ventes=Vente.objects.filter(deleted=True)[:100],
        produits=Produit.objects.filter(actif=False).order_by("nom")[:100],
        clients=ClientCompte.objects.filter(actif=False).order_by("matricule")[:100]))


@suppression_requise
@require_POST
def operation_restaurer(request, pk):
    try:
        services.restaurer_operation(request.user, get_object_or_404(Operation, pk=pk, deleted=True))
        messages.success(request, "Opération restaurée.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:corbeille")


@suppression_requise
@require_POST
def vente_restaurer(request, pk):
    try:
        services.restaurer_vente(request.user, get_object_or_404(Vente, pk=pk, deleted=True))
        messages.success(request, "Vente restaurée.")
    except ErreurMetier as exc:
        messages.error(request, str(exc))
    return redirect("ventes:corbeille")


@suppression_requise
@require_POST
def produit_restaurer(request, pk):
    produit = get_object_or_404(Produit, pk=pk, actif=False)
    produit.actif = True
    produit.save()
    services.audit(request.user, "product_restore", "produit", produit.pk, produit.nom)
    messages.success(request, f"Produit « {produit.nom} » restauré.")
    return redirect("ventes:corbeille")


@suppression_requise
@require_POST
def client_restaurer(request, pk):
    client = get_object_or_404(ClientCompte, pk=pk, actif=False)
    client.actif = True
    client.save()
    services.audit(request.user, "client_restore", "client", client.pk, client.matricule)
    messages.success(request, f"Fiche client « {client.matricule} » restaurée.")
    return redirect("ventes:corbeille")


# --------------------------------------------------------------------------
# Rapports, journal, paramètres
# --------------------------------------------------------------------------
def rapports(request):
    aujourdhui = timezone.localdate()
    if request.method == "POST":
        jeu = request.POST.get("dataset") or "operations"
        genre = request.POST.get("kind") or "custom"
        fmt = request.POST.get("format") if request.POST.get("format") in ("xlsx", "pdf") else "pdf"
        try:
            debut = date.fromisoformat(request.POST.get("date_from") or aujourdhui.replace(day=1).isoformat())
            fin = date.fromisoformat(request.POST.get("date_to") or aujourdhui.isoformat())
        except ValueError:
            messages.error(request, "Dates invalides.")
            return redirect("ventes:rapports")
        if genre == "daily":
            debut = fin = aujourdhui
        elif genre == "monthly":
            debut, fin = aujourdhui.replace(day=1), aujourdhui
        elif genre == "annual":
            debut, fin = aujourdhui.replace(month=1, day=1), aujourdhui
        elif genre == "all":
            debut, fin = date(2000, 1, 1), date(2100, 12, 31)
        sous = f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"
        entreprise = getattr(request.user.entreprise, "nom_entreprise", "")
        if jeu == "ventes":
            qs = _filtrer_dates(Vente.objects.filter(deleted=False), "created_at", debut, fin)
            entetes = ["Date", "Matricule", "Produit", "Qté", "Prix unit.", "Montant", "Paiement", "Agent"]
            lignes = [[f"{timezone.localtime(v.created_at):%d/%m/%Y %H:%M}", v.matricule or "—", v.produit_nom, v.quantite,
                       v.prix_unitaire, v.montant_total, v.get_mode_paiement_display(), v.agent_nom] for v in qs]
            titre = "Rapport des ventes"
        elif jeu == "caisse":
            journal = services.journal_caisse(debut, fin)
            entetes = ["Date", "Libellé", "Entrées", "Sorties", "Solde progressif", "Agent"]
            lignes = [[e.date.strftime("%d/%m/%Y"), e.libelle, e.entree or "", e.sortie or "", s, e.agent_nom]
                      for e, s in journal]
            titre = "Rapport de caisse"
        elif jeu == "stock":
            qs = _filtrer_dates(MouvementStock.objects.filter(deleted=False), "created_at", debut, fin)
            entetes = ["Date", "Produit", "Type", "Quantité", "Stock après", "Motif", "Agent"]
            lignes = [[f"{timezone.localtime(m.created_at):%d/%m/%Y %H:%M}", m.produit_nom, m.get_type_display(),
                       m.quantite, m.stock_apres, m.motif, m.agent_nom] for m in qs]
            titre = "Rapport des mouvements de stock"
        else:
            qs = _filtrer_dates(Operation.objects.filter(deleted=False), "created_at", debut, fin)
            entetes = ["Date", "Matricule", "Type", "Montant", "Solde après", "Agent", "Note"]
            lignes = [[f"{timezone.localtime(o.created_at):%d/%m/%Y %H:%M}", o.matricule, o.get_type_display(),
                       o.montant, o.solde_apres, o.agent_nom, o.note] for o in qs]
            titre = "Rapport des dépôts et retraits"
        services.audit(request.user, "report_generate", "rapport", jeu, f"format={fmt} {sous}")
        return exports.reponse_export(fmt, f"rapport_{jeu}", titre, entetes, lignes, sous, entreprise)

    debut_mois, debut_annee = aujourdhui.replace(day=1), aujourdhui.replace(month=1, day=1)
    ops = Operation.objects.filter(deleted=False)

    def somme(qs, type_):
        return qs.filter(type=type_).aggregate(s=Sum("montant"))["s"] or ZERO

    stats = {
        "jour": (somme(ops.filter(created_at__date=aujourdhui), "depot"), somme(ops.filter(created_at__date=aujourdhui), "retrait")),
        "mois": (somme(ops.filter(created_at__date__gte=debut_mois), "depot"), somme(ops.filter(created_at__date__gte=debut_mois), "retrait")),
        "annee": (somme(ops.filter(created_at__date__gte=debut_annee), "depot"), somme(ops.filter(created_at__date__gte=debut_annee), "retrait")),
    }
    return render(request, "ventes/rapports.html", _ctx(
        request, stats=stats, debut_defaut=debut_mois, fin_defaut=aujourdhui))


@admin_requis
def journal(request):
    qs = JournalAudit.objects.all()
    u, a = (request.GET.get("user") or "").strip(), (request.GET.get("action") or "").strip()
    debut, fin = _periode(request)
    if u:
        qs = qs.filter(user_identifiant__icontains=u)
    if a:
        qs = qs.filter(action__icontains=a)
    qs = _filtrer_dates(qs, "created_at", debut, fin)
    return render(request, "ventes/journal.html", _ctx(request, page=_page(request, qs), u=u, a=a,
                                                       debut=debut or "", fin=fin or ""))


@admin_requis
def parametres(request):
    param = ParametreVentes.courant()
    form = ParametresForm(request.POST or None, instance=param)
    if request.method == "POST" and form.is_valid():
        form.save()
        services.audit(request.user, "settings_update", "parametres", param.pk, "")
        messages.success(request, "Paramètres enregistrés.")
        return redirect("ventes:parametres")
    return render(request, "ventes/formulaire.html", _ctx(request, form=form, titre="Paramètres des ventes",
                                                          retour="ventes:tableau_de_bord"))
