"""Règles métier du module Ventes & caisse.

Toutes les opérations qui modifient un solde ou un stock passent par ces
fonctions, dans une transaction verrouillée par entreprise : deux saisies
simultanées ne peuvent pas dépasser un solde ni un stock.
"""
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    ClientCompte, DemandeStock, EcritureCaisse, JournalAudit, MouvementStock, Operation,
    ParametreVentes, Produit, Vente, ZERO, _agent_nom,
)


class ErreurMetier(ValueError):
    """Erreur de règle métier, affichable telle quelle à l'utilisateur."""


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def nombre(valeur, libelle="Valeur"):
    """Convertit une saisie (« 1 250,5 ») en Decimal fini."""
    if isinstance(valeur, Decimal):
        n = valeur
    else:
        texte = str(valeur if valeur is not None else "").replace(" ", "").replace("\xa0", "")
        texte = texte.replace(" ", "").replace(",", ".")
        try:
            n = Decimal(texte)
        except (InvalidOperation, ValueError):
            raise ErreurMetier(f"{libelle} : nombre invalide.")
    if not n.is_finite():
        raise ErreurMetier(f"{libelle} : nombre invalide.")
    return n


def limiter(texte, maxi, libelle):
    texte = (texte or "").strip()
    if len(texte) > maxi:
        raise ErreurMetier(f"{libelle} : {maxi} caractères maximum (saisie : {len(texte)}).")
    return texte


def fmt_gnf(valeur):
    return f"{Decimal(valeur or 0):,.0f}".replace(",", " ") + " GNF"


@contextmanager
def verrou():
    """Transaction sérialisée par entreprise (verrou sur la ligne de paramètres)."""
    with transaction.atomic():
        ParametreVentes.courant()
        ParametreVentes.objects.select_for_update().first()
        yield


def audit(user, action, target_type="", target_id="", details=""):
    JournalAudit.objects.create(
        user=user if getattr(user, "pk", None) else None,
        user_identifiant=getattr(user, "username", "") or "",
        action=action, target_type=target_type, target_id=str(target_id or ""), details=details or "",
    )


# --------------------------------------------------------------------------
# Soldes des comptes clients
# --------------------------------------------------------------------------
def solde_matricule(matricule):
    """Dépôts − retraits − ventes débitées du compte (les ventes en caisse sont exclues)."""
    matricule = (matricule or "").strip()
    ops = Operation.objects.filter(matricule=matricule, deleted=False)
    depots = ops.filter(type=Operation.DEPOT).aggregate(s=Sum("montant"))["s"] or ZERO
    retraits = ops.filter(type=Operation.RETRAIT).aggregate(s=Sum("montant"))["s"] or ZERO
    ventes = (Vente.objects.filter(matricule=matricule, deleted=False, mode_paiement=Vente.COMPTE)
              .aggregate(s=Sum("montant_total"))["s"] or ZERO)
    return depots - retraits - ventes


def soldes_clients(recherche=""):
    """Tous les comptes (fiches actives + matricules ayant des opérations) avec leur solde."""
    mouvements = defaultdict(lambda: ZERO)
    nb_ops = defaultdict(int)
    for matricule, type_, montant in Operation.objects.filter(deleted=False).values_list(
            "matricule", "type", "montant"):
        if not matricule:
            continue
        mouvements[matricule] += montant if type_ == Operation.DEPOT else -montant
        nb_ops[matricule] += 1
    for matricule, montant, mode in Vente.objects.filter(deleted=False).values_list(
            "matricule", "montant_total", "mode_paiement"):
        if not matricule:
            continue
        nb_ops[matricule] += 1
        if mode == Vente.COMPTE:
            mouvements[matricule] -= montant
    fiches = {c.matricule: c for c in ClientCompte.objects.filter(actif=True)}
    needle = (recherche or "").strip().lower()
    lignes = []
    for matricule in sorted(set(fiches) | set(nb_ops)):
        fiche = fiches.get(matricule)
        nom = fiche.nom if fiche else ""
        if needle and needle not in matricule.lower() and needle not in nom.lower():
            continue
        lignes.append({
            "matricule": matricule, "nom": nom, "telephone": fiche.telephone if fiche else "",
            "solde": mouvements[matricule], "nb_ops": nb_ops[matricule], "fiche": fiche,
        })
    return lignes


# --------------------------------------------------------------------------
# Dépôts
# --------------------------------------------------------------------------
def depots_du_jour(matricule, jour=None, exclure_id=None):
    jour = jour or timezone.localdate()
    qs = Operation.objects.filter(matricule=matricule.strip(), type=Operation.DEPOT, deleted=False,
                                  created_at__date=jour)
    if exclure_id:
        qs = qs.exclude(pk=exclure_id)
    return qs.aggregate(s=Sum("montant"))["s"] or ZERO


def verifier_plafond(montant, deja_depose):
    plafond = ParametreVentes.courant().plafond_depot_journalier
    if plafond and plafond > 0 and deja_depose + montant > plafond:
        restant = max(ZERO, plafond - deja_depose)
        raise ErreurMetier(
            f"Plafond journalier de {fmt_gnf(plafond)} par matricule atteint ou dépassé. "
            f"Déjà déposé : {fmt_gnf(deja_depose)} ; restant autorisé : {fmt_gnf(restant)}.")


def creer_depot(user, matricule, telephone, montant, note=""):
    with verrou():
        matricule = limiter(matricule, 80, "Matricule")
        if not matricule:
            raise ErreurMetier("Le matricule est obligatoire.")
        telephone = limiter(telephone, 40, "Téléphone")
        note = limiter(note, 255, "Note")
        montant = nombre(montant, "Montant")
        if montant <= 0:
            raise ErreurMetier("Le montant doit être strictement positif.")
        verifier_plafond(montant, depots_du_jour(matricule))
        apres = solde_matricule(matricule) + montant
        op = Operation.objects.create(
            matricule=matricule, telephone=telephone, type=Operation.DEPOT, montant=montant,
            solde_apres=apres, agent=user, agent_nom=_agent_nom(user), note=note)
        audit(user, "depot_create", "operation", op.pk,
              f"matricule={matricule} montant={montant:.0f} solde_apres={apres:.0f}")
        return op


# --------------------------------------------------------------------------
# Retraits et ventes
# --------------------------------------------------------------------------
def _mouvement(produit, type_, quantite, stock_apres, motif, user, vente=None):
    return MouvementStock.objects.create(
        produit=produit, produit_nom=produit.nom, type=type_, quantite=quantite,
        stock_apres=stock_apres, motif=motif, vente=vente, agent=user, agent_nom=_agent_nom(user))


def creer_retrait_ou_vente(user, matricule, telephone, note, mode, lignes, montant_manuel=None):
    """Retrait d'espèces (sans produit) ou vente de produits.

    ``lignes`` : liste de ``(produit_id, quantité)``. Avec des produits, une vente est
    créée par produit (débit du compte ou encaissement en caisse + sortie de stock) ;
    sans produit, c'est un retrait d'espèces du compte.
    Retourne ``("vente", [ventes])`` ou ``("retrait", operation)``.
    """
    if mode not in (Vente.COMPTE, Vente.CAISSE):
        raise ErreurMetier("Mode de paiement inconnu.")
    encaisse = mode == Vente.CAISSE
    with verrou():
        matricule = "" if encaisse else limiter(matricule, 80, "Matricule")
        if not encaisse and not matricule:
            raise ErreurMetier("Le matricule est obligatoire.")
        telephone = "" if encaisse else limiter(telephone, 40, "Téléphone")
        note = limiter(note, 255, "Note")

        quantites = {}
        for pid, q in lignes:
            if not str(pid or "").strip():
                continue
            qte = nombre(q, "Quantité")
            if qte <= 0:
                raise ErreurMetier("La quantité d'un produit doit être strictement positive.")
            quantites[int(pid)] = quantites.get(int(pid), ZERO) + qte

        details, total_produits = [], ZERO
        for pid, qte in sorted(quantites.items()):
            produit = Produit.objects.select_for_update().filter(pk=pid, actif=True).first()
            if produit is None:
                raise ErreurMetier("Un produit sélectionné est invalide ou inactif.")
            if produit.suivi_stock and qte > produit.quantite_stock:
                raise ErreurMetier(
                    f"Stock insuffisant pour « {produit.nom} » : {produit.quantite_stock:g} "
                    f"disponible, {qte:g} demandé.")
            if produit.prix_unitaire < 0:
                raise ErreurMetier("Le prix du produit ne peut pas être négatif.")
            ligne_total = (produit.prix_unitaire * qte).quantize(Decimal("0.01"))
            total_produits += ligne_total
            details.append((produit, qte, ligne_total))

        if details:
            montant = total_produits
        else:
            montant = nombre(montant_manuel, "Montant") if str(montant_manuel or "").strip() else ZERO
        if montant <= 0:
            raise ErreurMetier("Ajoutez au moins un produit ou saisissez un montant positif.")
        if encaisse and not details:
            raise ErreurMetier("Une vente encaissée doit porter sur au moins un produit.")

        courant = ZERO if encaisse else solde_matricule(matricule)
        if not encaisse and not details and montant > courant:
            raise ErreurMetier(f"Solde insuffisant : disponible {fmt_gnf(courant)}, demande {fmt_gnf(montant)}.")

        if details:
            ventes, running = [], courant
            for produit, qte, ligne_total in details:
                running = ZERO if encaisse else running - ligne_total
                vente = Vente.objects.create(
                    matricule=matricule, telephone=telephone, produit=produit, produit_nom=produit.nom,
                    quantite=qte, prix_unitaire=produit.prix_unitaire, montant_total=ligne_total,
                    solde_apres=running, mode_paiement=mode, agent=user, agent_nom=_agent_nom(user), note=note)
                if encaisse:
                    EcritureCaisse.objects.create(
                        date=timezone.localdate(), libelle=limiter(f"Vente — {produit.nom} x{qte:g}", 255, "Libellé"),
                        entree=ligne_total, source=EcritureCaisse.VENTE, vente=vente,
                        agent=user, agent_nom=_agent_nom(user))
                if produit.suivi_stock:
                    produit.quantite_stock -= qte
                    produit.save()
                    _mouvement(produit, MouvementStock.SORTIE, qte, produit.quantite_stock,
                               f"Vente {matricule or 'caisse'}", user, vente)
                ventes.append(vente)
            detail = ", ".join(f"{p.nom} x{q:g}" for p, q, _ in details)
            audit(user, "sale_create", "vente", ventes[0].pk,
                  f"matricule={matricule} montant={montant:.0f} produits=[{detail}]")
            return "vente", ventes

        op = Operation.objects.create(
            matricule=matricule, telephone=telephone, type=Operation.RETRAIT, montant=montant,
            solde_apres=courant - montant, agent=user, agent_nom=_agent_nom(user), note=note)
        audit(user, "retrait_create", "operation", op.pk, f"matricule={matricule} montant={montant:.0f}")
        return "retrait", op


# --------------------------------------------------------------------------
# Corbeille : suppression / restauration
# --------------------------------------------------------------------------
def supprimer_operation(user, op):
    with verrou():
        op = Operation.objects.select_for_update().get(pk=op.pk)
        if op.deleted:
            return op
        if op.type == Operation.DEPOT and op.montant > solde_matricule(op.matricule):
            raise ErreurMetier("Ce dépôt a déjà été utilisé : son annulation rendrait le solde négatif.")
        op.deleted = True
        op.save()
        audit(user, "transaction_delete", "operation", op.pk,
              f"{op.type} matricule={op.matricule} montant={op.montant:.0f}")
        return op


def restaurer_operation(user, op):
    with verrou():
        op = Operation.objects.select_for_update().get(pk=op.pk)
        if not op.deleted:
            return op
        if op.type == Operation.DEPOT:
            verifier_plafond(op.montant, depots_du_jour(op.matricule, op.created_at.date(), exclure_id=op.pk))
        elif op.montant > solde_matricule(op.matricule):
            raise ErreurMetier("Solde insuffisant pour restaurer ce retrait.")
        op.deleted = False
        op.save()
        audit(user, "transaction_restore", "operation", op.pk,
              f"{op.type} matricule={op.matricule} montant={op.montant:.0f}")
        return op


def supprimer_vente(user, vente):
    with verrou():
        vente = Vente.objects.select_for_update().get(pk=vente.pk)
        if vente.deleted:
            return vente
        vente.deleted = True
        vente.save()
        # L'encaissement suit sa vente : il sort de la caisse avec elle.
        EcritureCaisse.objects.filter(vente=vente, source=EcritureCaisse.VENTE, deleted=False).update(deleted=True)
        produit = Produit.objects.select_for_update().filter(pk=vente.produit_id).first()
        if produit and produit.suivi_stock:
            produit.quantite_stock += vente.quantite
            produit.save()
            _mouvement(produit, MouvementStock.ENTREE, vente.quantite, produit.quantite_stock,
                       f"Annulation vente N°{vente.pk} ({vente.matricule or 'caisse'})", user, vente)
        audit(user, "sale_delete", "vente", vente.pk,
              f"{vente.produit_nom} x{vente.quantite:g} matricule={vente.matricule} montant={vente.montant_total:.0f}")
        return vente


def restaurer_vente(user, vente):
    with verrou():
        vente = Vente.objects.select_for_update().get(pk=vente.pk)
        if not vente.deleted:
            return vente
        produit = Produit.objects.select_for_update().filter(pk=vente.produit_id).first()
        if produit is None:
            raise ErreurMetier("Produit introuvable : la vente ne peut pas être restaurée.")
        if produit.suivi_stock and vente.quantite > produit.quantite_stock:
            raise ErreurMetier("Stock insuffisant pour restaurer cette vente.")
        vente.deleted = False
        vente.save()
        EcritureCaisse.objects.filter(vente=vente, source=EcritureCaisse.VENTE, deleted=True).update(deleted=False)
        if produit.suivi_stock:
            produit.quantite_stock -= vente.quantite
            produit.save()
            _mouvement(produit, MouvementStock.SORTIE, vente.quantite, produit.quantite_stock,
                       f"Rétablissement vente N°{vente.pk} ({vente.matricule or 'caisse'})", user, vente)
        audit(user, "sale_restore", "vente", vente.pk, f"{vente.produit_nom} x{vente.quantite:g}")
        return vente


# --------------------------------------------------------------------------
# Stock
# --------------------------------------------------------------------------
def ajuster_stock(user, produit, type_, quantite, motif=""):
    with verrou():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        if not produit.suivi_stock:
            raise ErreurMetier(f"« {produit.nom} » est vendu sans suivi de stock : aucun mouvement possible.")
        if type_ not in (MouvementStock.ENTREE, MouvementStock.SORTIE):
            raise ErreurMetier("Type de mouvement invalide.")
        quantite = nombre(quantite, "Quantité")
        if quantite <= 0:
            raise ErreurMetier("La quantité doit être strictement positive.")
        motif = limiter(motif, 255, "Motif")
        if type_ == MouvementStock.ENTREE:
            nouveau = produit.quantite_stock + quantite
        else:
            if quantite > produit.quantite_stock:
                raise ErreurMetier(
                    f"Stock insuffisant : {produit.quantite_stock:g} disponible, sortie demandée {quantite:g}.")
            nouveau = produit.quantite_stock - quantite
        produit.quantite_stock = nouveau
        produit.save()
        mv = _mouvement(produit, type_, quantite, nouveau, motif, user)
        audit(user, f"stock_{type_}", "produit", produit.pk,
              f"{produit.nom} : {type_} {quantite:g} → {nouveau:g}" + (f" — {motif}" if motif else ""))
        return mv


def compter_inventaire(user, comptages, motif=""):
    """``comptages`` : dict ``{produit_id: quantité comptée}`` ; crée les écarts de stock."""
    with verrou():
        motif = limiter(motif, 255, "Motif") or "Inventaire physique"
        ajustements = []
        for produit in Produit.objects.select_for_update().filter(actif=True, suivi_stock=True).order_by("pk"):
            brut = comptages.get(produit.pk)
            if brut is None or str(brut).strip() == "":
                continue
            compte = nombre(brut, f"Quantité comptée pour « {produit.nom} »")
            if compte < 0:
                raise ErreurMetier(f"Quantité comptée invalide pour « {produit.nom} ».")
            theorique = produit.quantite_stock
            ecart = compte - theorique
            _mouvement(produit, MouvementStock.ENTREE if ecart > 0 else MouvementStock.SORTIE,
                       abs(ecart), compte, motif, user)
            produit.quantite_stock = compte
            produit.save()
            ajustements.append((produit.nom, theorique, compte, ecart))
        if ajustements:
            detail = "; ".join(f"{n}: {t:g}→{c:g} ({'+' if e > 0 else ''}{e:g})" for n, t, c, e in ajustements)
            audit(user, "inventory_adjust", "stock", "", f"motif={motif} | {detail}")
        return ajustements


def _normaliser(nom):
    return " ".join((nom or "").lower().split())


def produit_en_double(nom, reference=""):
    norm, ref = _normaliser(nom), (reference or "").strip().lower()
    for p in Produit.objects.filter(actif=True):
        if _normaliser(p.nom) == norm or (ref and (p.reference or "").strip().lower() == ref):
            return p
    return None


def creer_demande_entree(user, produit, quantite, motif=""):
    quantite = nombre(quantite, "Quantité")
    if quantite <= 0:
        raise ErreurMetier("La quantité doit être strictement positive.")
    demande = DemandeStock.objects.create(
        kind=DemandeStock.ENTREE, produit=produit, produit_nom=produit.nom, quantite=quantite,
        motif=limiter(motif, 255, "Motif"), demandeur=user, demandeur_nom=_agent_nom(user))
    audit(user, "stock_entry_request", "produit", produit.pk, f"{produit.nom} : +{quantite:g} demandé")
    return demande


def creer_demande_produit(user, nom, reference, prix, seuil, description, quantite, motif=""):
    nom = limiter(nom, 200, "Nom")
    if not nom:
        raise ErreurMetier("Le nom du produit est obligatoire.")
    if produit_en_double(nom, reference):
        raise ErreurMetier(f"Un produit « {nom} » existe déjà : faites plutôt une demande d'entrée.")
    prix, seuil = nombre(prix or 0, "Prix"), nombre(seuil or 0, "Seuil")
    quantite = nombre(quantite or 0, "Quantité")
    if prix < 0 or seuil < 0 or quantite < 0:
        raise ErreurMetier("Prix, seuil et quantité doivent être positifs ou nuls.")
    demande = DemandeStock.objects.create(
        kind=DemandeStock.NOUVEAU, produit_nom=nom, quantite=quantite, motif=limiter(motif, 255, "Motif"),
        new_reference=limiter(reference, 80, "Référence"), new_prix_unitaire=prix, new_seuil_alerte=seuil,
        new_description=description or "", demandeur=user, demandeur_nom=_agent_nom(user))
    audit(user, "product_request", "produit", "", f"Nouveau produit proposé : {nom}")
    return demande


def valider_demande(user, demande):
    with verrou():
        demande = DemandeStock.objects.select_for_update().get(pk=demande.pk)
        if demande.statut != DemandeStock.EN_ATTENTE:
            raise ErreurMetier("Cette demande a déjà été traitée.")
        entree = demande.quantite
        if entree < 0 or (demande.kind != DemandeStock.NOUVEAU and entree == 0):
            raise ErreurMetier("La quantité demandée est invalide.")
        if demande.kind == DemandeStock.NOUVEAU:
            if produit_en_double(demande.produit_nom, demande.new_reference):
                raise ErreurMetier(
                    f"Un produit « {demande.produit_nom} » existe déjà : rejetez cette proposition "
                    "et faites une entrée sur le produit existant.")
            produit = Produit.objects.create(
                reference=demande.new_reference, nom=demande.produit_nom, description=demande.new_description,
                prix_unitaire=demande.new_prix_unitaire, seuil_alerte=demande.new_seuil_alerte)
        else:
            produit = Produit.objects.select_for_update().filter(pk=demande.produit_id).first()
            if produit is None:
                raise ErreurMetier("Produit introuvable pour cette demande.")
        mouvement = None
        if entree > 0:
            produit.quantite_stock += entree
            produit.save()
            mouvement = _mouvement(
                produit, MouvementStock.ENTREE, entree, produit.quantite_stock,
                demande.motif or ("Stock initial (nouveau produit)" if demande.kind == DemandeStock.NOUVEAU
                                  else "Entrée validée"), None)
            mouvement.agent, mouvement.agent_nom = demande.demandeur, demande.demandeur_nom or "—"
            mouvement.save()
        demande.statut = DemandeStock.VALIDE
        demande.produit = produit
        demande.decide_par_nom, demande.decide_le = _agent_nom(user), timezone.now()
        demande.mouvement = mouvement
        demande.save()
        audit(user, "stock_entry_validate", "produit", produit.pk,
              f"{produit.nom} : entrée validée {entree:g} → {produit.quantite_stock:g}")
        return demande, produit


def rejeter_demande(user, demande, motif=""):
    with verrou():
        demande = DemandeStock.objects.select_for_update().get(pk=demande.pk)
        if demande.statut != DemandeStock.EN_ATTENTE:
            raise ErreurMetier("Cette demande a déjà été traitée.")
        demande.statut = DemandeStock.REJETE
        demande.decision_motif = limiter(motif, 255, "Motif")
        demande.decide_par_nom, demande.decide_le = _agent_nom(user), timezone.now()
        demande.save()
        audit(user, "stock_entry_reject", "produit", demande.produit_id or "",
              f"{demande.produit_nom} : demande refusée {demande.quantite:g}")
        return demande


# --------------------------------------------------------------------------
# Caisse
# --------------------------------------------------------------------------
def journal_caisse(date_debut=None, date_fin=None):
    """Écritures actives avec solde progressif : liste de ``(écriture, solde)``."""
    total, lignes = ZERO, []
    for e in EcritureCaisse.objects.filter(deleted=False).order_by("date", "created_at", "id"):
        total += e.entree - e.sortie
        if (date_debut and e.date < date_debut) or (date_fin and e.date > date_fin):
            continue
        lignes.append((e, total))
    return lignes


def solde_caisse():
    agg = EcritureCaisse.objects.filter(deleted=False).aggregate(e=Sum("entree"), s=Sum("sortie"))
    return (agg["e"] or ZERO) - (agg["s"] or ZERO)


def ecriture_caisse(user, libelle, sens, montant, date=None):
    with verrou():
        libelle = limiter(libelle, 255, "Libellé")
        if not libelle:
            raise ErreurMetier("Le libellé est obligatoire.")
        if sens not in ("entree", "sortie", "ouverture"):
            raise ErreurMetier("Précisez une entrée, une sortie ou une ouverture.")
        montant = nombre(montant, "Montant")
        if montant <= 0:
            raise ErreurMetier("Le montant doit être strictement positif.")
        if sens == "ouverture":
            if EcritureCaisse.objects.filter(source=EcritureCaisse.OUVERTURE, deleted=False).exists():
                raise ErreurMetier("La caisse a déjà une écriture d'ouverture.")
        elif sens == "sortie" and montant > solde_caisse():
            raise ErreurMetier(
                f"Solde de caisse insuffisant : disponible {fmt_gnf(solde_caisse())}, sortie demandée {fmt_gnf(montant)}.")
        e = EcritureCaisse.objects.create(
            date=date or timezone.localdate(), libelle=libelle,
            entree=montant if sens != "sortie" else ZERO, sortie=montant if sens == "sortie" else ZERO,
            source=EcritureCaisse.OUVERTURE if sens == "ouverture" else EcritureCaisse.MANUEL,
            agent=user, agent_nom=_agent_nom(user))
        audit(user, "cash_entry_create", "caisse", e.pk, f"{libelle} {sens}={montant:.0f}")
        return e


def annuler_ecriture(user, ecriture):
    with verrou():
        ecriture = EcritureCaisse.objects.select_for_update().get(pk=ecriture.pk)
        if ecriture.source == EcritureCaisse.VENTE:
            raise ErreurMetier("Cet encaissement suit sa vente : annulez la vente pour le retirer.")
        if ecriture.entree > 0 and ecriture.entree > solde_caisse():
            raise ErreurMetier("Annuler cette entrée rendrait le solde de caisse négatif.")
        ecriture.deleted = True
        ecriture.save()
        audit(user, "cash_entry_delete", "caisse", ecriture.pk, ecriture.libelle)
        return ecriture


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------
def stats_tableau_de_bord():
    aujourdhui = timezone.localdate()
    debut_mois = aujourdhui.replace(day=1)
    ops = Operation.objects.filter(deleted=False)
    ventes = Vente.objects.filter(deleted=False)

    def somme(qs, champ="montant"):
        return qs.aggregate(s=Sum(champ))["s"] or ZERO

    depots = somme(ops.filter(type=Operation.DEPOT))
    retraits = somme(ops.filter(type=Operation.RETRAIT))
    ventes_compte = somme(ventes.filter(mode_paiement=Vente.COMPTE), "montant_total")
    jour, mois = ops.filter(created_at__date=aujourdhui), ops.filter(created_at__date__gte=debut_mois)
    v_jour, v_mois = ventes.filter(created_at__date=aujourdhui), ventes.filter(created_at__date__gte=debut_mois)
    produits = list(Produit.objects.filter(actif=True))
    return {
        "solde_comptes": depots - retraits - ventes_compte,
        "solde_caisse": solde_caisse(),
        "depots_jour": somme(jour.filter(type=Operation.DEPOT)),
        "depots_mois": somme(mois.filter(type=Operation.DEPOT)),
        "sorties_jour": somme(jour.filter(type=Operation.RETRAIT)) + somme(v_jour, "montant_total"),
        "sorties_mois": somme(mois.filter(type=Operation.RETRAIT)) + somme(v_mois, "montant_total"),
        "ventes_jour": somme(v_jour, "montant_total"), "nb_ventes_jour": v_jour.count(),
        "ventes_mois": somme(v_mois, "montant_total"),
        "nb_produits": len(produits),
        "valeur_stock": sum((p.valeur_stock for p in produits if p.suivi_stock), ZERO),
        "nb_stock_bas": sum(1 for p in produits if p.etat_stock in ("rupture", "bas")),
        "nb_clients": ClientCompte.objects.filter(actif=True).count(),
        "nb_demandes": DemandeStock.objects.filter(statut=DemandeStock.EN_ATTENTE).count(),
    }
