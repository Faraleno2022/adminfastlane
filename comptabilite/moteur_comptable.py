"""
Moteur comptable central SYSCOHADA
===================================
L'utilisateur effectue des OPÉRATIONS MÉTIER (achat, vente, encaissement,
paiement, caisse, salaire…) ; le moteur traduit chaque opération en écriture
comptable équilibrée via une TABLE DE CORRESPONDANCE — jamais de saisie
manuelle de comptes.

Principes :
- Les comptes SYSCOHADA par défaut sont créés automatiquement s'ils manquent
  (plan comptable intelligent) ; le compte du tiers est utilisé s'il est défini.
- Contrôles avant validation : équilibre débit/crédit, montants positifs,
  exercice comptable ouvert (créé automatiquement si absent).
- Chaque écriture générée est validée et rattachée au document d'origine.
"""
from decimal import Decimal
from datetime import date as date_type

from django.db import transaction
from django.utils import timezone

from .models import (
    PlanComptable, Journal, ExerciceComptable, EcritureComptable, LigneEcriture,
    RegleEcriture,
)

ZERO = Decimal('0')


class ErreurComptabilisation(Exception):
    """Erreur métier levée par le moteur (message affichable à l'utilisateur)."""


# ═══════════════════════════════════════════════════════════════════════════
# TABLE DE CORRESPONDANCE — comptes SYSCOHADA par défaut
# ═══════════════════════════════════════════════════════════════════════════

COMPTES_DEFAUT = {
    'clients':            ('4111', 'Clients'),
    'fournisseurs':       ('4011', 'Fournisseurs'),
    'ventes':             ('7011', 'Ventes de marchandises'),
    'achats':             ('6011', 'Achats de marchandises'),
    'tva_collectee':      ('4431', 'TVA facturée sur ventes'),
    'tva_deductible':     ('4452', 'TVA récupérable sur achats'),
    'banque':             ('5211', 'Banque'),
    'caisse':             ('5711', 'Caisse'),
    'salaires':           ('6611', 'Appointements et salaires'),
    'personnel':          ('4221', 'Personnel, rémunérations dues'),
    'immobilisations':    ('2441', 'Matériel et outillage'),
    'frs_investissement': ('4812', 'Fournisseurs d\'investissements'),
    'produits_divers':    ('7588', 'Autres produits divers'),
    'charges_diverses':   ('6588', 'Autres charges diverses'),
}

# Journaux SYSCOHADA par type d'opération
JOURNAUX_DEFAUT = {
    'AC': 'Journal des Achats',
    'VT': 'Journal des Ventes',
    'BQ': 'Journal de Banque',
    'CA': 'Journal de Caisse',
    'OD': 'Journal des Opérations Diverses',
    'SA': 'Journal des Salaires',
}

# Table de correspondance opération → (journal, libellé) ; les lignes sont
# construites par les fonctions de schéma ci-dessous.
OPERATIONS = {
    'vente':                ('VT', 'Vente'),
    'achat':                ('AC', 'Achat'),
    'avoir_client':         ('VT', 'Avoir client'),
    'avoir_fournisseur':    ('AC', 'Avoir fournisseur'),
    'encaissement_client':  ('BQ', 'Encaissement client'),
    'paiement_fournisseur': ('BQ', 'Paiement fournisseur'),
    'entree_caisse':        ('CA', 'Entrée de caisse'),
    'sortie_caisse':        ('CA', 'Sortie de caisse'),
    'salaire':              ('SA', 'Paiement de salaires'),
    'achat_immobilisation': ('OD', 'Acquisition d\'immobilisation'),
}


# ═══════════════════════════════════════════════════════════════════════════
# RÉSOLUTION AUTOMATIQUE (comptes, journaux, exercices, numérotation)
# ═══════════════════════════════════════════════════════════════════════════

def obtenir_compte(entreprise, cle_ou_numero, intitule=None):
    """Retourne le compte du plan comptable, créé automatiquement au besoin.
    Accepte une clé de la table (ex. 'clients') ou un numéro brut ('4111')."""
    if cle_ou_numero in COMPTES_DEFAUT:
        numero, intitule_defaut = COMPTES_DEFAUT[cle_ou_numero]
    else:
        numero, intitule_defaut = str(cle_ou_numero), intitule or f'Compte {cle_ou_numero}'
    compte, _ = PlanComptable.objects.get_or_create(
        entreprise=entreprise, numero_compte=numero,
        defaults={'intitule': intitule or intitule_defaut, 'classe': numero[0], 'est_actif': True})
    return compte


def obtenir_journal(entreprise, type_journal):
    """Retourne le journal du type demandé, créé automatiquement au besoin."""
    journal = Journal.objects.filter(
        entreprise=entreprise, type_journal=type_journal, est_actif=True).first()
    if journal is None:
        journal, _ = Journal.objects.get_or_create(
            entreprise=entreprise, code=type_journal,
            defaults={'libelle': JOURNAUX_DEFAUT.get(type_journal, type_journal),
                      'type_journal': type_journal, 'est_actif': True})
    return journal


def obtenir_exercice(entreprise, date_operation):
    """Retourne l'exercice ouvert couvrant la date ; créé automatiquement
    (année civile) s'il n'existe pas. Refuse un exercice clôturé."""
    exercice = ExerciceComptable.objects.filter(
        entreprise=entreprise, date_debut__lte=date_operation,
        date_fin__gte=date_operation).first()
    if exercice is not None:
        if exercice.statut != 'ouvert':
            raise ErreurComptabilisation(
                f"L'exercice {exercice.libelle} est clôturé : opération refusée au {date_operation}.")
        return exercice
    annee = date_operation.year
    exercice, _ = ExerciceComptable.objects.get_or_create(
        entreprise=entreprise, date_debut=date_type(annee, 1, 1), date_fin=date_type(annee, 12, 31),
        defaults={'libelle': f'Exercice {annee}', 'statut': 'ouvert'})
    return exercice


def _prochain_numero_ecriture(entreprise, date_operation):
    annee = date_operation.year
    base = f'ECR-{annee}-'
    derniere = (EcritureComptable.objects
                .filter(entreprise=entreprise, numero_ecriture__startswith=base)
                .order_by('-numero_ecriture').first())
    seq = 1
    if derniere:
        try:
            seq = int(derniere.numero_ecriture.split('-')[-1]) + 1
        except ValueError:
            seq = 1
    return f'{base}{seq:05d}'


# ═══════════════════════════════════════════════════════════════════════════
# GÉNÉRATION D'ÉCRITURE (cœur du moteur)
# ═══════════════════════════════════════════════════════════════════════════

def generer_ecriture(entreprise, utilisateur, type_journal, date_operation, libelle, lignes,
                     centre_analyse=None, piece_jointe=None, verifier_doublon=True):
    """Crée une écriture validée à partir de lignes [(compte, libellé, débit, crédit)].

    Contrôles automatiques : montants positifs, au moins 2 lignes,
    équilibre débit = crédit, exercice ouvert, détection de doublon.
    Journalise l'opération dans la piste d'audit.
    """
    lignes = [(c, l, d or ZERO, cr or ZERO) for c, l, d, cr in lignes if (d or ZERO) > 0 or (cr or ZERO) > 0]
    if len(lignes) < 2:
        raise ErreurComptabilisation("Écriture incomplète : au moins un débit et un crédit sont requis.")
    total_debit = sum((d for _, _, d, _ in lignes), ZERO)
    total_credit = sum((c for _, _, _, c in lignes), ZERO)
    if total_debit != total_credit:
        raise ErreurComptabilisation(
            f"Écriture déséquilibrée : débit {total_debit:,.0f} ≠ crédit {total_credit:,.0f}.")
    if total_debit <= 0:
        raise ErreurComptabilisation("Le montant de l'opération doit être supérieur à zéro.")

    exercice = obtenir_exercice(entreprise, date_operation)
    journal = obtenir_journal(entreprise, type_journal)

    # Contrôle anti-doublon : même journal, même date, même libellé, même total
    if verifier_doublon:
        doublon = (EcritureComptable.objects
                   .filter(entreprise=entreprise, journal=journal,
                           date_ecriture=date_operation, libelle=libelle[:200])
                   .filter(lignes__montant_debit=lignes[0][2] or lignes[0][3])
                   .first())
        if doublon:
            raise ErreurComptabilisation(
                f"Doublon probable : l'écriture {doublon.numero_ecriture} du "
                f"{date_operation} porte déjà le même libellé et le même montant. "
                f"Modifiez le libellé pour confirmer qu'il s'agit d'une opération distincte.")

    with transaction.atomic():
        ecriture = EcritureComptable.objects.create(
            entreprise=entreprise, exercice=exercice, journal=journal,
            numero_ecriture=_prochain_numero_ecriture(entreprise, date_operation),
            date_ecriture=date_operation, libelle=libelle[:200],
            piece_jointe=piece_jointe,
            est_validee=True, date_validation=timezone.now(), validee_par=utilisateur)
        for compte, lib_ligne, debit, credit in lignes:
            LigneEcriture.objects.create(
                ecriture=ecriture, compte=compte, libelle=(lib_ligne or libelle)[:200],
                montant_debit=debit, montant_credit=credit,
                centre_analyse=centre_analyse)
        _piste_audit(entreprise, utilisateur, ecriture, total_debit)
    return ecriture


def _piste_audit(entreprise, utilisateur, ecriture, montant):
    """Trace la génération d'écriture dans la piste d'audit (non bloquant)."""
    try:
        from .models import PisteAudit
        PisteAudit.objects.create(
            entreprise=entreprise, utilisateur=utilisateur,
            action='GENERATION_AUTO', module='MOTEUR_COMPTABLE',
            type_objet='EcritureComptable', id_objet=str(ecriture.pk),
            donnees_nouvelles=f"{ecriture.numero_ecriture} | {ecriture.journal.code} | "
                              f"{ecriture.date_ecriture} | {ecriture.libelle} | "
                              f"{montant:,.0f} GNF")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# COMPTES AUXILIAIRES DE TIERS (411001 Orange, 401002 SONAP…)
# ═══════════════════════════════════════════════════════════════════════════

def obtenir_compte_auxiliaire(entreprise, tiers, categorie):
    """Retourne (et crée au besoin) le compte auxiliaire individuel du tiers :
    clients → 411xxx, fournisseurs → 401xxx. Mémorisé sur le tiers."""
    if tiers is None:
        return obtenir_compte(entreprise, categorie)
    if tiers.compte_comptable_id:
        return tiers.compte_comptable
    racine = '411' if categorie == 'clients' else '401'
    dernier = (PlanComptable.objects
               .filter(entreprise=entreprise, numero_compte__startswith=racine)
               .exclude(numero_compte__in=[racine + '1'])
               .order_by('-numero_compte').first())
    seq = 1
    if dernier and len(dernier.numero_compte) >= 6:
        try:
            seq = int(dernier.numero_compte[3:]) + 1
        except ValueError:
            seq = 1
    numero = f"{racine}{seq:03d}"
    compte, _ = PlanComptable.objects.get_or_create(
        entreprise=entreprise, numero_compte=numero,
        defaults={'intitule': tiers.raison_sociale[:200], 'classe': '4', 'est_actif': True})
    tiers.compte_comptable = compte
    tiers.save(update_fields=['compte_comptable'])
    return compte


# ═══════════════════════════════════════════════════════════════════════════
# RÈGLES CONFIGURABLES (table de correspondance en base)
# ═══════════════════════════════════════════════════════════════════════════

def _regles_pour(entreprise, type_operation):
    """Règles actives : celles de l'entreprise en priorité, sinon les globales."""
    regles = list(RegleEcriture.objects.filter(
        entreprise=entreprise, operation=type_operation, est_active=True).order_by('ordre'))
    if not regles:
        regles = list(RegleEcriture.objects.filter(
            entreprise__isnull=True, operation=type_operation, est_active=True).order_by('ordre'))
    return regles


def _appliquer_regles(entreprise, regles, montants, tiers, tresorerie, lib, categorie_tiers):
    """Construit les lignes d'écriture depuis les règles configurées.
    montants = {'ht': …, 'tva': …, 'ttc': …}."""
    lignes = []
    journal = None
    for regle in regles:
        montant = montants.get(regle.base_montant, ZERO)
        if montant <= 0 and regle.ignorer_si_nul:
            continue
        if regle.role_compte == 'tiers':
            compte = obtenir_compte_auxiliaire(entreprise, tiers, categorie_tiers)
        elif regle.role_compte == 'tresorerie':
            compte = tresorerie
        else:
            if not regle.compte_numero:
                raise ErreurComptabilisation(
                    f"Règle {regle} : aucun numéro de compte configuré.")
            compte = obtenir_compte(entreprise, regle.compte_numero,
                                    regle.compte_intitule or None)
        debit = montant if regle.sens == 'debit' else ZERO
        credit = montant if regle.sens == 'credit' else ZERO
        lignes.append((compte, lib, debit, credit))
        if regle.journal_type:
            journal = regle.journal_type
    return lignes, journal


def _compte_tiers(entreprise, tiers, cle_defaut):
    """Compte auxiliaire individuel du tiers (créé automatiquement : 411xxx
    clients / 401xxx fournisseurs), sinon compte collectif par défaut."""
    if tiers is not None:
        return obtenir_compte_auxiliaire(entreprise, tiers, cle_defaut)
    return obtenir_compte(entreprise, cle_defaut)


def _compte_tresorerie(entreprise, mode_paiement):
    """Caisse pour les espèces, banque pour tout le reste."""
    if str(mode_paiement or '').lower() in ('especes', 'espèces', 'cash', 'caisse'):
        return obtenir_compte(entreprise, 'caisse')
    return obtenir_compte(entreprise, 'banque')


# ═══════════════════════════════════════════════════════════════════════════
# SCHÉMAS D'OPÉRATIONS MÉTIER
# ═══════════════════════════════════════════════════════════════════════════

def comptabiliser_facture(facture, utilisateur):
    """Facture validée → écriture automatique selon la table :
    vente  : Client (D, TTC) / Ventes (C, HT) + TVA facturée (C)
    achat  : Achats (D, HT) + TVA récupérable (D) / Fournisseur (C, TTC)
    avoirs : écritures inverses."""
    if facture.ecriture_id:
        return facture.ecriture
    e = facture.entreprise
    ht, tva, ttc = facture.montant_ht or ZERO, facture.montant_tva or ZERO, facture.montant_ttc or ZERO
    if ttc <= 0:
        raise ErreurComptabilisation("La facture n'a pas de montant : écriture non générée.")
    lib = f"{facture.get_type_facture_display()} {facture.numero} - {facture.tiers.raison_sociale}"

    if facture.type_facture in ('vente', 'acompte'):
        lignes = [
            (_compte_tiers(e, facture.tiers, 'clients'), lib, ttc, ZERO),
            (obtenir_compte(e, 'ventes'), lib, ZERO, ht),
        ]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_collectee'), lib, ZERO, tva))
        ecriture = generer_ecriture(e, utilisateur, 'VT', facture.date_facture, lib, lignes)
    elif facture.type_facture == 'achat':
        lignes = [
            (obtenir_compte(e, 'achats'), lib, ht, ZERO),
        ]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_deductible'), lib, tva, ZERO))
        lignes.append((_compte_tiers(e, facture.tiers, 'fournisseurs'), lib, ZERO, ttc))
        ecriture = generer_ecriture(e, utilisateur, 'AC', facture.date_facture, lib, lignes)
    elif facture.type_facture == 'avoir_client':
        lignes = [
            (obtenir_compte(e, 'ventes'), lib, ht, ZERO),
        ]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_collectee'), lib, tva, ZERO))
        lignes.append((_compte_tiers(e, facture.tiers, 'clients'), lib, ZERO, ttc))
        ecriture = generer_ecriture(e, utilisateur, 'VT', facture.date_facture, lib, lignes)
    elif facture.type_facture == 'avoir_fournisseur':
        lignes = [
            (_compte_tiers(e, facture.tiers, 'fournisseurs'), lib, ttc, ZERO),
            (obtenir_compte(e, 'achats'), lib, ZERO, ht),
        ]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_deductible'), lib, ZERO, tva))
        ecriture = generer_ecriture(e, utilisateur, 'AC', facture.date_facture, lib, lignes)
    else:
        raise ErreurComptabilisation(f"Type de facture non géré : {facture.type_facture}.")

    facture.ecriture = ecriture
    facture.save(update_fields=['ecriture'])
    return ecriture


def comptabiliser_reglement(reglement, utilisateur):
    """Règlement → encaissement (facture de vente) ou paiement (facture d'achat) :
    encaissement : Banque/Caisse (D) / Client (C)
    paiement     : Fournisseur (D) / Banque/Caisse (C)."""
    if reglement.ecriture_id:
        return reglement.ecriture
    e = reglement.entreprise
    facture = reglement.facture
    montant = reglement.montant or ZERO
    if montant <= 0:
        raise ErreurComptabilisation("Le règlement n'a pas de montant : écriture non générée.")
    tresorerie = _compte_tresorerie(e, reglement.mode_paiement)
    journal = 'CA' if tresorerie.numero_compte.startswith('57') else 'BQ'
    lib = f"Règlement {reglement.numero} - Facture {facture.numero} - {facture.tiers.raison_sociale}"

    if facture.type_facture in ('vente', 'acompte', 'avoir_fournisseur'):
        lignes = [
            (tresorerie, lib, montant, ZERO),
            (_compte_tiers(e, facture.tiers, 'clients'), lib, ZERO, montant),
        ]
    else:
        lignes = [
            (_compte_tiers(e, facture.tiers, 'fournisseurs'), lib, montant, ZERO),
            (tresorerie, lib, ZERO, montant),
        ]
    ecriture = generer_ecriture(e, utilisateur, journal, reglement.date_reglement, lib, lignes)
    reglement.ecriture = ecriture
    reglement.save(update_fields=['ecriture'])
    return ecriture


def comptabiliser_piece_caisse(piece, utilisateur):
    """Pièce de caisse → écriture au journal de caisse :
    entrée : Caisse (D) / Produits divers (C)
    sortie : Charges diverses (D) / Caisse (C)."""
    if piece.ecriture_id:
        return piece.ecriture
    e = piece.entreprise
    caisse = obtenir_compte(e, 'caisse')
    lib = f"Pièce {piece.numero} - {piece.libelle}"
    if piece.type_piece == 'entree':
        contrepartie = obtenir_compte(e, 'produits_divers')
        lignes = [(caisse, lib, piece.montant, ZERO), (contrepartie, lib, ZERO, piece.montant)]
    else:
        contrepartie = obtenir_compte(e, 'charges_diverses')
        lignes = [(contrepartie, lib, piece.montant, ZERO), (caisse, lib, ZERO, piece.montant)]
    ecriture = generer_ecriture(e, utilisateur, 'CA', piece.date_operation, lib, lignes)
    piece.ecriture = ecriture
    piece.save(update_fields=['ecriture'])
    return ecriture


def operation_simple(entreprise, utilisateur, type_operation, date_operation, libelle,
                     montant_ht, taux_tva=ZERO, tiers=None, mode_paiement='banque',
                     centre_analyse=None, piece_jointe=None):
    """Assistant : traduit une opération métier en écriture. Les règles
    configurées en base (RegleEcriture) priment ; sinon le schéma SYSCOHADA
    intégré s'applique. Retourne l'écriture générée."""
    montant_ht = Decimal(montant_ht or 0)
    if montant_ht <= 0:
        raise ErreurComptabilisation("Le montant doit être supérieur à zéro.")
    tva = (montant_ht * Decimal(taux_tva or 0) / Decimal('100')).quantize(Decimal('1'))
    ttc = montant_ht + tva
    e = entreprise
    tresorerie = _compte_tresorerie(e, mode_paiement)

    # 1) Règles configurables en base (table de correspondance modifiable)
    regles = _regles_pour(e, type_operation)
    if regles:
        journal_defaut = OPERATIONS.get(type_operation, ('OD', type_operation))[0]
        lib_defaut = OPERATIONS.get(type_operation, ('OD', type_operation.title()))[1]
        lib = libelle or (f"{lib_defaut}" + (f" - {tiers.raison_sociale}" if tiers else ''))
        categorie_tiers = 'clients' if 'client' in type_operation or type_operation == 'vente' else 'fournisseurs'
        lignes, journal_regle = _appliquer_regles(
            e, regles, {'ht': montant_ht, 'tva': tva, 'ttc': ttc},
            tiers, tresorerie, lib, categorie_tiers)
        return generer_ecriture(e, utilisateur, journal_regle or journal_defaut,
                                date_operation, lib, lignes,
                                centre_analyse=centre_analyse, piece_jointe=piece_jointe)

    # 2) Schémas SYSCOHADA intégrés
    if type_operation not in OPERATIONS:
        raise ErreurComptabilisation(
            f"Opération inconnue : {type_operation}. Créez des règles d'écriture "
            f"pour cette opération dans la configuration du moteur comptable.")
    journal, lib_defaut = OPERATIONS[type_operation]
    lib = libelle or (f"{lib_defaut}" + (f" - {tiers.raison_sociale}" if tiers else ''))
    if type_operation in ('encaissement_client', 'paiement_fournisseur', 'salaire',
                          'entree_caisse', 'sortie_caisse'):
        journal = 'CA' if tresorerie.numero_compte.startswith('57') else journal

    if type_operation == 'vente':
        lignes = [(_compte_tiers(e, tiers, 'clients'), lib, ttc, ZERO),
                  (obtenir_compte(e, 'ventes'), lib, ZERO, montant_ht)]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_collectee'), lib, ZERO, tva))
    elif type_operation == 'achat':
        lignes = [(obtenir_compte(e, 'achats'), lib, montant_ht, ZERO)]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_deductible'), lib, tva, ZERO))
        lignes.append((_compte_tiers(e, tiers, 'fournisseurs'), lib, ZERO, ttc))
    elif type_operation == 'avoir_client':
        lignes = [(obtenir_compte(e, 'ventes'), lib, montant_ht, ZERO)]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_collectee'), lib, tva, ZERO))
        lignes.append((_compte_tiers(e, tiers, 'clients'), lib, ZERO, ttc))
    elif type_operation == 'avoir_fournisseur':
        lignes = [(_compte_tiers(e, tiers, 'fournisseurs'), lib, ttc, ZERO),
                  (obtenir_compte(e, 'achats'), lib, ZERO, montant_ht)]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_deductible'), lib, ZERO, tva))
    elif type_operation == 'encaissement_client':
        lignes = [(tresorerie, lib, ttc, ZERO),
                  (_compte_tiers(e, tiers, 'clients'), lib, ZERO, ttc)]
    elif type_operation == 'paiement_fournisseur':
        lignes = [(_compte_tiers(e, tiers, 'fournisseurs'), lib, ttc, ZERO),
                  (tresorerie, lib, ZERO, ttc)]
    elif type_operation == 'entree_caisse':
        lignes = [(obtenir_compte(e, 'caisse'), lib, ttc, ZERO),
                  (obtenir_compte(e, 'produits_divers'), lib, ZERO, ttc)]
        journal = 'CA'
    elif type_operation == 'sortie_caisse':
        lignes = [(obtenir_compte(e, 'charges_diverses'), lib, ttc, ZERO),
                  (obtenir_compte(e, 'caisse'), lib, ZERO, ttc)]
        journal = 'CA'
    elif type_operation == 'salaire':
        lignes = [(obtenir_compte(e, 'salaires'), lib, ttc, ZERO),
                  (tresorerie, lib, ZERO, ttc)]
    elif type_operation == 'achat_immobilisation':
        lignes = [(obtenir_compte(e, 'immobilisations'), lib, montant_ht, ZERO)]
        if tva > 0:
            lignes.append((obtenir_compte(e, 'tva_deductible'), lib, tva, ZERO))
        if tiers is not None:
            lignes.append((obtenir_compte(e, 'frs_investissement'), lib, ZERO, ttc))
        else:
            lignes.append((tresorerie, lib, ZERO, ttc))

    return generer_ecriture(e, utilisateur, journal, date_operation, lib, lignes)
