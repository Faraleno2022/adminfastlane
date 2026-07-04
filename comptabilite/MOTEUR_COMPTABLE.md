# Moteur comptable SYSCOHADA — API interne

> **Composant stratégique gelé.** Les modules métier (Achats, Ventes, Stock,
> Paie, RH…) ne créent JAMAIS d'écriture directement : ils appellent le moteur
> via les fonctions publiques ci-dessous. Toute évolution du moteur doit passer
> la suite de tests `python manage.py test comptabilite.tests.test_moteur_comptable`.

## Architecture

```
 MODULES MÉTIER (Achats, Ventes, Caisse, Banque, Paie, Immobilisations…)
        │  événements métier (facture validée, paiement reçu, pièce de caisse…)
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  comptabilite/moteur_comptable.py                            │
 │  • Table de correspondance (schémas SYSCOHADA intégrés)      │
 │  • Règles configurables en base (RegleEcriture)              │
 │  • Résolution auto des comptes / journaux / exercices        │
 │  • Comptes auxiliaires de tiers (411xxx / 401xxx)            │
 │  • Contrôles : équilibre, doublons, exercice, montants       │
 │  • Piste d'audit                                             │
 └─────────────────────────────────────────────────────────────┘
        ▼
 EcritureComptable + LigneEcriture (validées)
        ▼
 Journaux • Grand Livre • Balance • TVA • Bilan • CR • TFT • États
```

## Fonctions publiques

### `operation_simple(entreprise, utilisateur, type_operation, date_operation, libelle, montant_ht, taux_tva=0, tiers=None, mode_paiement='banque', centre_analyse=None, piece_jointe=None) → EcritureComptable`
Traduit une opération métier en écriture équilibrée et validée.

Opérations : `vente`, `achat`, `avoir_client`, `avoir_fournisseur`,
`encaissement_client`, `paiement_fournisseur`, `entree_caisse`,
`sortie_caisse`, `salaire`, `achat_immobilisation`.

Ordre de résolution : **1)** règles `RegleEcriture` de l'entreprise,
**2)** règles globales, **3)** schéma SYSCOHADA intégré.
`mode_paiement='especes'` → caisse 5711 + journal CA ; sinon banque 5211.

```python
from comptabilite.moteur_comptable import operation_simple
ecriture = operation_simple(entreprise, user, 'vente', date.today(),
                            'Vente ordinateurs', Decimal('1000000'),
                            Decimal('18'), tiers=client)
```

### `comptabiliser_facture(facture, utilisateur) → EcritureComptable`
Facture validée → écriture (vente : 411x/701+4431 ; achat : 601+4452/401x ;
avoirs inversés). Idempotente (`facture.ecriture` déjà lié → renvoyé tel quel).
Appelée automatiquement par `facture_valider` (après approbation si un seuil
`RegleValidation` s'applique).

### `comptabiliser_reglement(reglement, utilisateur) → EcritureComptable`
Encaissement client (banque/caisse ← 411x) ou paiement fournisseur
(401x ← banque/caisse). Espèces → journal CA, sinon BQ. Idempotente.

### `comptabiliser_piece_caisse(piece, utilisateur) → EcritureComptable`
Entrée : 5711 / 7588 — Sortie : 6588 / 5711, journal CA. Idempotente.

### `generer_ecriture(entreprise, utilisateur, type_journal, date_operation, libelle, lignes, centre_analyse=None, piece_jointe=None, verifier_doublon=True) → EcritureComptable`
Primitive bas niveau. `lignes = [(compte, libellé, débit, crédit), …]`.
**Contrôles bloquants** (lèvent `ErreurComptabilisation`) :
- au moins un débit et un crédit ;
- équilibre débit = crédit, montant > 0 ;
- exercice ouvert (créé automatiquement en année civile s'il n'existe pas ;
  **refus si clôturé**) ;
- anti-doublon : même journal + date + libellé + montant
  (désactivable via `verifier_doublon=False` pour les traitements de masse).
Trace chaque génération dans `PisteAudit` (module `MOTEUR_COMPTABLE`).

### Résolution automatique
- `obtenir_compte(entreprise, cle_ou_numero, intitule=None)` — clés de la table
  `COMPTES_DEFAUT` (`clients`, `fournisseurs`, `ventes`, `achats`,
  `tva_collectee`, `tva_deductible`, `banque`, `caisse`, `salaires`…) ou numéro
  brut ; `get_or_create` dans le plan comptable.
- `obtenir_compte_auxiliaire(entreprise, tiers, 'clients'|'fournisseurs')` —
  compte individuel 411xxx/401xxx créé et mémorisé sur `tiers.compte_comptable`.
- `obtenir_journal(entreprise, 'VT'|'AC'|'BQ'|'CA'|'OD'|'SA'|'AN')`.
- `obtenir_exercice(entreprise, date)` — exercice couvrant la date.

## Règles configurables (`RegleEcriture`)
Une opération = N lignes ordonnées. Champs : `operation`, `ordre`,
`sens` (débit/crédit), `role_compte` (`fixe` + numéro / `tiers` auxiliaire /
`tresorerie` banque-caisse selon paiement), `base_montant` (HT/TVA/TTC),
`journal_type`, `entreprise` (vide = globale), `est_active`.
Les règles de l'entreprise priment sur les globales, qui priment sur le schéma
intégré. **Ajouter une opération ne demande aucun code.**

## Workflow de validation (`RegleValidation`)
Seuil en GNF par type de document (`facture`, `reglement`, `piece_caisse`,
`operation`) → `DemandeApprobation` + `DecisionApprobation` (quorum
`nb_approbations`). Autorisation d'approuver :
`user.has_permission('<type>.approuver', entreprise)` — rôle via
`AccesEntreprise` (comptable, chef_comptable, daf, dg, auditeur,
administrateur), permissions par rôle dans `PermissionRole`
(seed : `python manage.py seed_permissions`), **délégations** temporaires via
`core.Delegation` (le délégataire exerce les permissions du délégant pendant
la période). Fallback : niveau d'accès du profil ≥ `niveau_acces_min`.
Au quorum atteint sur une facture : validation + comptabilisation automatiques.

## Moteur d'autorisations (`core`)
```python
user.role_dans(entreprise)                    # 'daf', 'comptable', …
user.has_permission('facture.approuver')      # rôle + délégation + superuser
```
Codes : `<domaine>.<action>` — voir `PermissionRole.DEFAUTS`.
**Ne plus tester `is_superuser` ou `niveau >= n` dans le code métier.**

## Clôtures
- **Période** (`/comptabilite/cloture-periode/`) : dotations linéaires
  automatiques (valeur/durée, plafonnées à la VNC) → écritures 6811/28xx + `Amortissement`.
- **Exercice** (`/comptabilite/cloture-exercice/`) : contrôles bloquants
  (brouillons, journaux déséquilibrés) et avertissements (comptes 47x,
  dotations manquantes) → affectation du résultat (soldes 6/7 → 131/139)
  → à-nouveaux (classes 1-5, journal AN, 1er jour N+1) → clôture + ouverture N+1.

## Garanties de conception
- `Utilisateur.entreprise` est en **SET_NULL** : supprimer une entreprise ne
  supprime jamais les comptes utilisateurs (seulement leurs accès).
- Toutes les données métier sont cloisonnées par `entreprise` (multi-sociétés).
- Chaque écriture générée est équilibrée, validée, tracée, et rattachée au
  document d'origine (`facture.ecriture`, `reglement.ecriture`, `piece.ecriture`).

## Tests
```
python manage.py test comptabilite.tests.test_moteur_comptable
```
26 tests : ventes HT/TTC, achats, avoirs, règlements banque/caisse, pièces de
caisse, contrôles (équilibre, doublon, exercice clôturé), comptes auxiliaires,
règles en base, dotations (plafond VNC), résultat de clôture, permissions par
rôle, accès expirés, délégations, quorum multiple, suppression d'entreprise
sans perte d'utilisateur, cloisonnement multi-sociétés.
