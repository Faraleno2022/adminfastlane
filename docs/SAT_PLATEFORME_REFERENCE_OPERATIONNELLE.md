# Plateforme SAT - Référence opérationnelle

## Source et portée

- Source : `C:\Users\LENO\Downloads\Manuel Utilisateur v330 (2).pdf`
- Version du manuel : 3.30
- Volume : 165 pages
- Plateforme utilisée : `https://plateform.satgroupe.com/live/`
- Compte observé : LOGISTIQUE FASTLANE
- Date d'intégration : 16 juillet 2026

Ce document constitue la mémoire opérationnelle locale pour les futures manipulations de la plateforme SAT. En cas d'ambiguïté, consulter le PDF source, qui reste l'autorité documentaire.

## Modules principaux et pages du manuel

| Module | Pages indicatives | Usage |
|---|---:|---|
| Tracking | 11-28 | Suivi en direct, activité du jour, historique, trajets et carte |
| Administration | 28-41 | Utilisateurs, conducteurs, véhicules, capteurs, carburant et emplacements |
| Dispatch | 41-47 | Clients, dépôts, tournées, arrêts et planning |
| Tableau de bord | 47-49 | Modèles, comparaison de véhicules et graphiques |
| Rapports | 49-80 | Rapports instantanés, précédents, planifiés et personnalisés |
| Alertes | 81-106 | Création, destinataires, planning et types d'alertes |
| Tickets et messages | 107-109 | Tickets, boîte à messages et messages d'alertes |
| Paramètres utilisateur | 109-110 | Préférences d'affichage et de suivi |
| Fonctionnalités spéciales | 110 et suivantes | Sélecteurs unités, étiquettes et conducteurs |

## Lecture correcte du suivi en direct

La vue par défaut montre l'activité du jour depuis minuit. Le filtre permet de choisir :

- Aujourd'hui ;
- Historique ;
- Par trajet ;
- groupes ou unités ;
- étiquettes ;
- recherche textuelle ;
- activité ou absence d'activité ;
- statut de mouvement ;
- statut de communication.

Le filtre mémorise les derniers critères. Toujours vérifier si le bouton indique « Filtre activé » avant de conclure sur la taille ou l'état global de la flotte.

## Signification des états visuels

- Vert : moteur allumé et véhicule en mouvement.
- Jaune : moteur allumé, véhicule immobile, donc ralenti.
- Gris : moteur arrêté et véhicule immobile, donc garé/arrêté.
- Orange : moteur arrêté mais véhicule en mouvement ; mouvement potentiellement non autorisé.

## Données essentielles d'une unité

Pour chaque véhicule, relever si disponible :

- nom ou immatriculation ;
- statut de mouvement et vitesse ;
- conducteur affecté ;
- dernière communication avec la plateforme ;
- heure du dernier point GPS valide ;
- emplacement affiché et coordonnées ;
- odomètre GPS ou heures moteur ;
- temps de conduite, ralenti et arrêt depuis minuit ;
- durée dans le statut actuel ;
- distance du jour et heure du premier départ ;
- batterie interne et externe ;
- carburant, température et autres capteurs ;
- alertes du jour.

## Communication et position GPS : distinction critique

« Dernières données reçues » correspond à la dernière communication du boîtier avec la plateforme. La date placée entre crochets correspond au dernier enregistrement GPS valide et donc à la position visible sur la carte.

Ces deux dates peuvent être différentes. Un boîtier peut transmettre un message de maintien de connexion sans envoyer une nouvelle position. Une position GPS ancienne n'indique donc pas automatiquement une panne : un véhicule immobile peut conserver le même point plusieurs jours. Il faut croiser :

1. dernière communication ;
2. dernier point GPS ;
3. statut et activité du jour ;
4. valeurs récentes des capteurs ;
5. historique ou trajets si nécessaire.

Couleur de l'indicateur de communication selon le manuel :

- noir : dernière communication depuis moins d'une heure ;
- jaune : entre une et trois heures ;
- rouge : depuis plus de trois heures.

Une unité privée temporairement de réseau peut mémoriser les données et les renvoyer au retour de la connexion, si cette fonction est supportée et configurée.

## Activité quotidienne

Les données sont calculées depuis minuit :

- temps de conduite ;
- temps au ralenti ;
- temps à l'arrêt ;
- durée dans le statut actuel ;
- distance parcourue ;
- heure du premier départ.

L'odomètre GPS est une estimation cumulative basée sur les points GPS. Il ne doit pas être traité comme aussi précis que le compteur physique du véhicule.

## Détail d'un véhicule

Cliquer sur le nom ouvre notamment :

- Trajets : trajets de la période, durée, distance, carburant, score, départ et arrivée ;
- Activité : état courant des informations et capteurs ;
- Alertes : alertes générées pendant la période ;
- Médias : photos ou vidéos disponibles ;
- Suivre : centre la carte sur l'unité et maintient le suivi ;
- barre d'activité : chronologie conduite, ralenti et arrêt.

## Capteurs et anomalies

La valeur affichée est la dernière valeur transmise, pas nécessairement une mesure prise au moment de la consultation. Toujours relever l'horodatage associé au capteur.

Une valeur physiquement incohérente, par exemple une température de `-128 °C`, doit être signalée comme anomalie probable de sonde, de configuration ou de transmission, et non comme température réelle sans vérification.

## Rapports recommandés selon le besoin

### Situation journalière de flotte

- Activité quotidienne : résumé par jour et par véhicule/conducteur.
- Liste des véhicules : groupe, dernier emplacement, odomètre, champs personnalisés et capteurs choisis.
- Résumé trajet : détails de chaque trajet, avec option d'inclure les véhicules sans trajet.

### Exploitation et productivité

- Résumé trajet ;
- résumé trajet + coûts ;
- coût détaillé du trajet ;
- visites POI et visites client ;
- analyse d'emplacement ;
- temps de fonctionnement du moteur ;
- ICP véhicule/conducteur.

### Carburant

- Consommation de carburant ;
- ravitaillement ;
- diminution soudaine ;
- rapport Carburant, qui repose sur les transactions saisies dans le journal carburant.

### Sécurité et maintenance

- Excès de vitesse ;
- marche au ralenti ;
- arrêt ;
- géoclôture et zone interdite ;
- utilisation ou mouvement non autorisé ;
- DTC pour les codes de diagnostic ;
- données et intervalles des capteurs.

## Alertes disponibles

Les catégories principales sont :

- activité : vitesse, ralenti, arrêt, odomètre, temps moteur, batterie, température, carburant, heures et pauses de conduite, seuils de consommables ;
- productivité : visites POI, non-entrée, trajet emplacement, entrée/sortie et dates importantes ;
- sécurité : géoclôture, zone interdite, mouvement non autorisé, intervalle de données et intervalle capteur ;
- dispatch : arrivée/départ tardif, non-arrivée/non-départ, durée et visites client ;
- alertes composées : combinaison de plusieurs critères.

## Procédure standard pour un rapport global quotidien

1. Ouvrir Tracking et confirmer que le filtre est désactivé ou couvre toute la flotte.
2. Vérifier la date et l'heure de la plateforme.
3. Compter les unités par statut : mouvement, ralenti, arrêté et état anormal.
4. Relever l'activité depuis minuit : conduite, ralenti, arrêt et distance.
5. Distinguer fraîcheur de communication et fraîcheur GPS.
6. Regrouper les véhicules par zone géographique.
7. Identifier les absences de communication, positions anciennes et capteurs incohérents.
8. Contrôler les alertes du jour ; ne pas confondre « alertes non lues » et nombre total d'alertes.
9. Pour une validation officielle, générer le rapport Activité quotidienne ou Liste des véhicules depuis le module Rapports.
10. Présenter les conclusions, anomalies et actions recommandées sans surinterpréter les données anciennes.

## Précautions avant toute action

- La consultation, le filtrage et la génération d'un aperçu sont des opérations de lecture.
- L'envoi de commandes à un véhicule, notamment l'immobilisation à distance, nécessite une confirmation explicite au moment de l'action.
- La création ou modification d'utilisateurs, véhicules, alertes, géoclôtures, plannings et destinataires produit des changements persistants ; demander confirmation si l'instruction ne les autorise pas clairement.
- Vérifier les véhicules et la période sélectionnés avant de générer ou planifier un rapport.

