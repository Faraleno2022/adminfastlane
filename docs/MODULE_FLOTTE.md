# Module Gestion de flotte

Intégré depuis le projet autonome « GESTIONNAIRE DE FLOTTE » (Fastlane Logistic).
Accessible depuis le lanceur d'applications (tuile **Flotte**, URL `/flotte/`).

## Contenu

| Menu | Fonctions |
|------|-----------|
| Tableau de bord | Dépenses / recettes / résultat (mensuel et annuel), graphiques, alertes de documents |
| Saisie | Entretien & réparations, carburant, voyages, Poclain, porte-char, autres dépenses |
| Pointage | Grille mensuelle de présence (8 statuts), employés de la flotte |
| Stock | Inventaire (OK / alerte / rupture), mouvements, synthèse |
| Rapports | Analyses par véhicule (L/100 km, coût au km), rapport mensuel imprimable, charges d'entretien, consommation, analyse Poclain, export Excel et PDF |
| Référentiel | Véhicules, documents (carte grise, assurance… avec alertes d'expiration), marques, chauffeurs, catégories de roues, engins |

## Architecture

- Une seule application Django `flotte` (modèles, vues, services, gabarits `templates/flotte/`).
- **Isolation par entreprise** : chaque modèle porte une clé `entreprise`. Un middleware
  (`flotte.middleware.FlotteEntrepriseMiddleware`) mémorise l'entreprise de l'utilisateur
  pour la requête et les managers filtrent automatiquement dessus (lecture, listes déroulantes
  des formulaires, rapports, exports). Hors requête (shell, commandes, tests), utiliser
  `with flotte.scope.pour_entreprise(entreprise): ...`.
- **Suppression logique** : `delete()` marque l'enregistrement ; `Modele.all_objects` voit tout.
- **Droits** (`flotte/permissions.py`) : administrateur (superutilisateur, administrateur
  d'entreprise, niveau 5 ou groupe « admin ») = tout ; saisie (niveau ≥ 2 ou groupe « saisie ») =
  écritures sans le référentiel ; sinon lecture seule.
- **Pièces jointes** des véhicules : stockées dans `private_media/flotte/` (hors `/media/`,
  non servies publiquement) et délivrées uniquement par une vue authentifiée et filtrée par entreprise.

## Réglages (variables d'environnement)

`DOCUMENTS_TAILLE_MAX_MO` (10), `DOCUMENTS_DELAI_ALERTE_JOURS` (30), `RAPPORT_LIEU`,
`RAPPORT_SIGNATAIRE_TITRE`, `RAPPORT_SIGNATAIRE_NOM` (signature du rapport mensuel imprimé).

## Mise en production

```bash
python manage.py migrate        # crée les tables flotte_*
```

## Non repris du projet d'origine

- Synchronisation hors connexion (serveur central, postes nomades, jetons, `/api/sync/`).
- Commandes `import_excel` / `import_stock` (import du classeur Excel) et `init_roles`.
