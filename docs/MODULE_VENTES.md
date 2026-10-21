# Module Ventes & caisse

Intégré depuis le projet « Gestionnaire Dépôt / Retrait » (EMAB). Accessible depuis le lanceur
d'applications (tuile **Ventes & caisse**, URL `/ventes/`).

## Principe

Un client, identifié par son **matricule**, alimente un compte par des **dépôts**. Il peut ensuite
**retirer des espèces** ou **acheter des produits** : la vente débite son compte, ou elle est
**encaissée en caisse** (sans compte). Le stock, la caisse et les soldes sont tenus à jour.

Solde d'un compte = dépôts − retraits − ventes débitées du compte (les ventes encaissées en caisse
n'y comptent pas).

## Fonctions

| Menu | Contenu |
|------|---------|
| Tableau de bord | Soldes des comptes et de la caisse, dépôts / sorties / ventes du jour et du mois, valeur du stock, alertes |
| Opérations | Nouveau dépôt, retrait d'espèces ou vente de produits (une vente par produit), historique avec filtres, reçus et tickets imprimables (80 mm), exports Excel / PDF |
| Clients | Comptes avec leur solde (y compris les matricules sans fiche), fiches, export des soldes |
| Caisse | Journal d'entrées / sorties avec solde progressif, ouverture, annulation |
| Stock | Produits (catégorie, unité, prix, seuil, emplacement, article sans suivi de stock), mouvements, inventaire physique, demandes d'entrée ou de nouveau produit à valider par un administrateur |
| Rapports | Rapports par période (dépôts/retraits, ventes, caisse, stock) en PDF ou Excel, journal d'audit |
| Configuration | Plafond de dépôt, en-tête / pied des tickets, corbeille (restauration) |

## Règles métier

- **Plafond de dépôt** par matricule et par jour : 40 000 GNF par défaut, modifiable (0 = aucun plafond)
  dans *Configuration → Paramètres*.
- Un retrait sans produit est refusé si le solde est insuffisant ; une vente refuse un stock insuffisant.
- Annuler une vente rend le stock et retire son encaissement de la caisse ; la restaurer les rétablit.
  Un dépôt déjà utilisé ne peut pas être annulé ; une sortie de caisse ne peut pas dépasser le solde.
- Toutes les opérations qui touchent un solde ou un stock s'exécutent dans une transaction verrouillée
  par entreprise (pas de dépassement en cas de saisies simultanées).

## Droits (déduits des comptes existants)

- **Administrateur** (superutilisateur, administrateur d'entreprise ou niveau 5) : produits, validations,
  inventaire, paramètres, journal d'audit.
- **Responsable** (administrateur ou niveau ≥ 3) : suppression / restauration, corbeille.
- **Caissier** (niveau ≥ 2 ou groupe « caissier ») : dépôts, ventes, caisse, demandes de stock.
- **Consultation** : les autres comptes (lecture seule).

## Architecture

Application Django `ventes`. Les données sont **isolées par entreprise** grâce au mécanisme commun
`core.tenancy` (middleware + managers filtrés), partagé avec le module Flotte. Hors requête (shell,
commandes, tests), utiliser `with core.tenancy.pour_entreprise(entreprise): ...`.

## Mise en production

```bash
python manage.py migrate        # crée les tables ventes_*
```

## Non repris de l'application d'origine

- Application de bureau PySide6 et synchronisation poste ↔ serveur (appareils, jetons, réplication).
- Impression directe ESC/POS sur imprimante thermique (le ticket HTML s'imprime via le navigateur).
- Gestion des utilisateurs propre (les comptes de l'application sont utilisés), mise à jour automatique,
  recalcul / réconciliation de stock.
- Les données existantes de l'application d'origine ne sont pas importées.
