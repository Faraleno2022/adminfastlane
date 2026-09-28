# 📚 Cahier d'exercices — Formation RH & Paie
## GestionnaireRH Guinée — Exercices pratiques sur données fictives

> **Public** : gestionnaires RH, comptables, assistants de direction
> **Durée conseillée** : 2 journées de formation (Module 1-5 : jour 1 · Module 6-10 : jour 2)
> **Méthode** : chaque exercice se fait D'ABORD à la main (calculatrice), PUIS dans l'application pour vérifier. C'est ainsi qu'on apprend à repérer une erreur de saisie.

---

## 🏢 L'entreprise fictive de la formation

Toute la formation utilise la société suivante (à créer dans l'application) :

| Élément | Valeur |
|---|---|
| Raison sociale | **SOGUIMEX SARL** (Société Guinéenne d'Import-Export) |
| Adresse | Quartier Almamya, Kaloum — Conakry |
| NIF | 123456789A (fictif) |
| Effectif | **12 salariés** (⚠️ moins de 30 → Taxe d'Apprentissage 2 %) |
| Activité | Import-export de produits alimentaires |

**Variante « SOGUIMEX-GRANDE »** utilisée au Module 8 : même société avec **35 salariés** (≥ 30 → ONFPP 1,5 % au lieu de TA 2 %).

### 👥 Les 5 employés fictifs à créer

| Matricule | Nom | Poste | Service | Embauche | Salaire évoqué |
|---|---|---|---|---|---|
| FORM-001 | **Mamadou DIALLO** | Magasinier | Logistique | 01/03/2026 | 1 500 000 brut |
| FORM-002 | **Aissatou BARRY** | Comptable | Finance | 15/01/2026 | 3 000 000 brut |
| FORM-003 | **Sékou CONDÉ** | Directeur commercial | Commercial | 01/01/2025 | net convenu 10 000 000 |
| FORM-004 | **Fatoumata CAMARA** | Assistante RH | RH | 01/06/2026 | net convenu 1 000 000 |
| FORM-005 | **Ibrahima SOW** | Chauffeur | Logistique | 01/02/2026 | 1 733 300 base (CDD 12 mois) |

### 📐 Rappel des paramètres légaux utilisés par l'application

| Paramètre | Valeur |
|---|---|
| CNSS salarié | 5 % — plancher 550 000, **plafond 2 500 000** (max 125 000 GNF) |
| CNSS employeur | 18 % — même assiette plafonnée (max 450 000 GNF) |
| Barème RTS (6 tranches) | 0→1M : 0 % · 1→3M : 5 % · 3→5M : 8 % · 5→10M : 10 % · 10→20M : 15 % · +20M : 20 % |
| Exonération indemnités forfaitaires | plafonnée à **25 % du brut** — **s'applique à la RTS UNIQUEMENT** |
| Versement Forfaitaire (VF) | **6 % du brut intégral** (pas de réduction de 25 %) |
| TA (moins de 30 salariés) | 2 % du brut |
| ONFPP (30 salariés et plus) | 1,5 % du brut |
| Congés payés | **2,5 jours ouvrables par mois** (30 j/an) |
| Heures supplémentaires | 4 premières : +30 % · au-delà : +60 % · nuit : +20 % · dimanche/férié : +60 % · férié de nuit : +100 % |
| Base horaire mensuelle | 173,33 h |

---

# JOUR 1 — Prise en main et paie de base

---

## Module 1 · Créer l'entreprise et les employés

### Exercice 1.1 — Mise en place
**🖥️ Dans l'application :**
1. Créez les services : *Logistique, Finance, Commercial, RH*.
2. Créez les 5 employés du tableau ci-dessus (menu **Employés → Nouveau**) avec leurs matricules FORM-xxx.
3. Vérifiez dans la liste des employés que les 5 apparaissent avec le bon service.

**✅ Auto-contrôle :** le tableau de bord RH doit afficher 5 employés actifs. Si un employé n'apparaît pas, vérifiez le champ *statut* (actif).

### Exercice 1.2 — Question de réflexion
SOGUIMEX compte 12 salariés. Laquelle des deux contributions s'applique : **TA 2 %** ou **ONFPP 1,5 %** ? À partir de quel effectif bascule-t-on ?

**✅ Corrigé :** TA 2 % (effectif < 30). La bascule vers l'ONFPP 1,5 % se fait à partir de **30 salariés**. L'application choisit automatiquement selon l'effectif actif.

---

## Module 2 · Bulletin simple — Mamadou DIALLO (le cas fondamental)

### Exercice 2.1 — Calcul à la main
Mamadou DIALLO gagne **1 500 000 GNF brut**, 100 % en salaire de base (aucune indemnité). Calculez : CNSS salarié, base RTS, RTS, net à payer.

**✅ Corrigé pas à pas :**
```
CNSS salarié = 1 500 000 × 5 %                    =    75 000
Base RTS     = 1 500 000 − 75 000                 = 1 425 000
RTS :  tranche 0 → 1 000 000        : 0 %         =         0
       tranche 1 000 000 → 1 425 000 : 425 000×5 % =    21 250
NET À PAYER  = 1 500 000 − 75 000 − 21 250        = 1 403 750 GNF
```

### Exercice 2.2 — Côté employeur
Toujours pour DIALLO, calculez les charges patronales et le coût total employeur.

**✅ Corrigé :**
```
CNSS employeur = 1 500 000 × 18 %  = 270 000
VF             = 1 500 000 × 6 %   =  90 000   ← sur le brut INTÉGRAL
TA (12 sal.)   = 1 500 000 × 2 %   =  30 000
Charges patronales                  = 390 000
COÛT TOTAL EMPLOYEUR = 1 500 000 + 390 000 = 1 890 000 GNF
```

### Exercice 2.3 — Vérification dans l'application
1. Menu **Paie → Éléments de salaire** de DIALLO : créez un élément *Salaire de base* de 1 500 000 (récurrent, actif).
2. Créez la période de paie du mois en cours et **calculez le bulletin**.
3. Comparez chaque ligne du bulletin avec vos calculs de 2.1 et 2.2.

**✅ Auto-contrôle :** le net doit afficher **1 403 750**. Si le RTS diffère, vérifiez que l'élément de salaire est bien imposable et qu'aucune indemnité parasite n'existe.

---

## Module 3 · Structuration salariale — Aissatou BARRY (le cœur de l'outil)

### Exercice 3.1 — Répartir un brut en composantes
Aissatou BARRY est embauchée à **3 000 000 GNF brut**. Utilisez la **Structuration salariale intelligente** (page Éléments de salaire de BARRY) :
1. Saisissez le brut 3 000 000 et choisissez le mode **« Base 75 % / Indemnités 25 % (max exonération CGI) »**.
2. Relevez la répartition proposée et vérifiez que le total fait exactement 100 %.

**✅ Corrigé :**
```
Salaire de base  75 % = 2 250 000
Transport        10 % =   300 000
Logement         10 % =   300 000
Cherté de vie     5 % =   150 000
TOTAL           100 % = 3 000 000  ✔
Indemnités = 750 000 = exactement 25 % du brut (plafond CGI atteint)
```

### Exercice 3.2 — Effet des indemnités sur la RTS (à la main)
Avec cette structure, calculez CNSS, base RTS, RTS et net.

**✅ Corrigé pas à pas :**
```
Assiette CNSS  = min(3 000 000 ; plafond 2 500 000)     = 2 500 000
CNSS salarié   = 2 500 000 × 5 %                        =   125 000  ← PLAFONNÉE
Exonération    = min(750 000 ; 25 % × 3 000 000)        =   750 000
Base RTS       = 3 000 000 − 125 000 − 750 000          = 2 125 000
RTS : 1M→2,125M = 1 125 000 × 5 %                       =    56 250
NET            = 3 000 000 − 125 000 − 56 250           = 2 818 750 GNF
```
💡 **Comparez avec un brut 100 % base** : la RTS serait de 93 750 au lieu de 56 250. **Gain pour la salariée : 37 500 GNF/mois**, en toute légalité.

### Exercice 3.3 — ⚠️ Le piège à connaître : VF et ONFPP
Question : l'exonération de 25 % réduit-elle aussi le VF de 6 % ?

**✅ Corrigé :** **NON.** C'est l'erreur classique. L'exonération plafonnée à 25 % ne concerne **que la RTS** (impôt du salarié). Le VF 6 % et la TA/ONFPP se calculent sur le **brut intégral** :
```
VF = 3 000 000 × 6 %   = 180 000   (et non 6 % × 2 250 000 = 135 000 ✗)
TA = 3 000 000 × 2 %   =  60 000
CNSS employeur 18 %     = 450 000   (assiette plafonnée à 2 500 000)
Charges patronales      = 690 000
```
L'application applique cette règle automatiquement — mais vous devez savoir la vérifier sur les déclarations.

### Exercice 3.4 — Créer les éléments en lot
Dans la structuration de BARRY, cliquez **« Créer en lot »** : vérifiez que 4 éléments actifs sont créés (base + 3 indemnités) et que l'en-tête « Gains » affiche **4 actifs**.

---

## Module 4 · Rétro-paie — partir du NET convenu

### Exercice 4.1 — Fatoumata CAMARA : « je veux 1 000 000 net »
Fatoumata a négocié un **net de 1 000 000 GNF**. Utilisez la **Proposition automatique complète** (Net cible → Structure optimale) :
1. Saisissez net cible = 1 000 000, taux max 25 %.
2. Relevez : brut calculé, CNSS, RTS, taux optimal retenu, décision du moteur.

**✅ Corrigé et interprétation :**
```
Brut calculé = 1 052 632
CNSS 5 %     =    52 632
Base RTS     = 1 000 000  → RTS = 0 (≤ 1 000 000, tranche à 0 %)
NET          = 1 000 000  exact ✔
Taux optimal = 0 % → structure 100 % salaire de base
```
💡 **Pourquoi 0 % d'indemnités ?** Le moteur affiche *« Aucune optimisation nécessaire »* : à ce niveau, la RTS est déjà nulle — les indemnités n'apporteraient **aucun** gain. C'est la preuve que l'outil n'optimise pas « bêtement ».

### Exercice 4.2 — Sékou CONDÉ : « je veux 10 000 000 net »
Même exercice avec net cible = **10 000 000** (utilisez la variante SOGUIMEX-GRANDE, 35 salariés, pour ce cas).

**✅ Corrigé :**
```
Brut calculé      = 10 672 973
Structure retenue = base 8 004 730 · transport 1 067 297 · logement 1 067 297 · cherté 533 649
CNSS (plafonnée)  = 5 % × 2 500 000                      =    125 000
Plafond exo 25 %  = 2 668 243 → indemnités = 2 668 243 → exonération totale
Base RTS          = 10 672 973 − 125 000 − 2 668 243     =  7 879 730
RTS : 1→3M : 100 000 · 3→5M : 160 000 · 5→7,879M : 287 973 = 547 973
NET               = 10 672 973 − 125 000 − 547 973       = 10 000 000 ✔
— Employeur (35 salariés → ONFPP) —
CNSS employeur (plafonnée)  = 450 000
VF  = 6 %  × 10 672 973     = 640 378   ← brut intégral
ONFPP = 1,5 % × 10 672 973  = 160 095
Charges patronales          = 1 250 473
```
**Points remarquables** : CNSS plafonnée (brut > 2,5 M), plafond d'exonération exactement atteint (« Optimisation parfaite »), ONFPP au lieu de TA (effectif ≥ 30).

---

## Module 5 · Heures supplémentaires — Ibrahima SOW

### Exercice 5.1 — Calcul à la main
Ibrahima SOW (base **1 733 300**) a effectué en une semaine : **6 heures supplémentaires de jour** + **2 heures un dimanche**.

**✅ Corrigé :**
```
Taux horaire = 1 733 300 ÷ 173,33 = 10 000 GNF/h
4 premières HS jour  : 4 × 10 000 × 1,30 = 52 000
2 HS jour au-delà    : 2 × 10 000 × 1,60 = 32 000
2 HS dimanche        : 2 × 10 000 × 1,60 = 32 000
TOTAL HS = 116 000 GNF (à ajouter au brut du mois)
```

### Exercice 5.2 — Dans l'application
1. Menu **Temps de travail → Heures supplémentaires** : saisissez les HS de SOW avec les bons types (jour +30 %, jour +60 %, dimanche +60 %).
2. Recalculez son bulletin et vérifiez la ligne HS = 116 000.

**⚠️ Piège pédagogique :** si vous choisissez un mauvais type d'HS, le montant sera faux. Les types affichés correspondent aux taux du Code du travail (30/60, nuit 20, férié 60, férié nuit 100).

---

# JOUR 2 — Temps de travail, congés, déclarations et départs

---

## Module 6 · Congés payés

### Exercice 6.1 — Acquisition progressive
Mamadou DIALLO est embauché le **01/03/2026**. Combien de jours de congés a-t-il acquis au **31/08/2026** ? Peut-il prendre 20 jours ?

**✅ Corrigé :** 6 mois × 2,5 = **15 jours acquis**. Une demande de 20 jours doit être **refusée par l'application** (solde insuffisant) — testez-le !

### Exercice 6.2 — Circuit de demande via le portail
1. Faites soumettre par DIALLO (portail employé) une demande de **10 jours** de congé annuel.
2. Côté RH : validez la demande.
3. Vérifiez le nouveau solde.

**✅ Auto-contrôle :** solde après validation = 15 − 10 = **5 jours**. Statuts attendus : *soumise → validée* (un refus donne *rejetée* — testez aussi le refus avec motif).

---

## Module 7 · Pointages et feuille de présence

### Exercice 7.1 — Saisir une semaine type
Pour la semaine du lundi au samedi, pointez Fatoumata CAMARA ainsi :
lundi *présent*, mardi *présent AM* (matin seul), mercredi *malade*, jeudi *présent*, vendredi *absence justifiée*, samedi *présent PM*.

### Exercice 7.2 — Lire la feuille de présence
Générez le rapport **Feuille de présence** du mois (menu Paie → Rapports) et vérifiez les compteurs de CAMARA.

**✅ Auto-contrôle :** P = 2 · AM = 1 · PM = 1 · M = 1 · AJ = 1. Les codes du rapport : P (présent), AM/PM (demi-journées), A (absent), R (retard), AJ (absence justifiée), M (malade).

---

## Module 8 · Déclarations sociales (CNSS + DMU)

### Exercice 8.1 — Déclaration mensuelle de SOGUIMEX (12 salariés)
Après avoir calculé les bulletins de DIALLO (1 500 000) et BARRY (3 000 000), générez la déclaration sociale du mois et vérifiez à la main :

**✅ Corrigé (2 bulletins) :**
```
Masse brute            = 4 500 000
CNSS salariés  (5 %)   =   200 000   (75 000 + 125 000 plafonnée)
CNSS employeur (18 %)  =   720 000   (270 000 + 450 000 plafonnée)
VF   (6 % × brut)      =   270 000   (90 000 + 180 000)
TA   (2 % × brut)      =    90 000   (30 000 + 60 000)   ← 12 salariés
DMU totale             = CNSS emp. + VF + TA
```

### Exercice 8.2 — Contrôle de conformité (esprit critique)
Un stagiaire vous présente une DMU où le VF vaut `6 % × (brut − 25 %)`. Que répondez-vous ?

**✅ Corrigé :** C'est **faux** : la déduction de 25 % ne s'applique qu'à la RTS. Le VF se calcule sur le brut intégral (CGI art. 201). Une DMU calculée sur base réduite **sous-déclare** les impôts — l'application signale d'ailleurs les anciens bulletins à base réduite comme non conformes. En cas de doute sur un document ancien : **recalculer le bulletin puis régénérer la déclaration**.

---

## Module 9 · Fin de contrat — Solde de tout compte

### Exercice 9.1 — Fin du CDD d'Ibrahima SOW
Le CDD de 12 mois de SOW arrive à terme. Dans le module **Contrats → Solde de tout compte** :
1. Générez le STC de SOW.
2. Identifiez les composantes : salaire du dernier mois au prorata, **congés non pris payés**, indemnité de fin de CDD.
3. Vérifiez que la rémunération totale de référence provient des **bulletins réellement validés/payés** (pas d'une simple multiplication salaire × mois).

**✅ Points de contrôle :**
- Les congés restants sont valorisés sur la base du salaire.
- Un contrat de 11 mois et 29 jours est proratisé (les mois partiels comptent).
- La CNSS du STC suit les mêmes plancher/plafond/taux que la paie normale.

---

## Module 10 · Cas de synthèse — « La nouvelle recrue » (évaluation finale)

**📝 Énoncé complet (45 min, sans aide) :**
SOGUIMEX embauche **Mariama SYLLA**, cheffe comptable, au 1er du mois prochain, avec un **net convenu de 3 000 000 GNF**.

1. Créez l'employée (matricule FORM-006, service Finance).
2. Utilisez la **proposition automatique** pour trouver le brut et la structure optimale ; relevez la « Décision du moteur ».
3. Créez les éléments de salaire en lot.
4. Saisissez 3 HS de jour dans son premier mois.
5. Calculez son premier bulletin et contrôlez à la main : CNSS, base RTS, RTS, net.
6. Elle pose 2 jours de congé le mois suivant : que répond l'application et pourquoi ?
7. Générez la déclaration sociale et vérifiez que le VF est bien 6 % × brut intégral.

**✅ Grille de correction (formateur) :**
- Brut calculé ≈ **3 188 312** ; structure 75/10/10/5 ; taux optimal 25 % (« Optimisation maximale ») ;
- CNSS = 125 000 (assiette plafonnée à 2 500 000) · exonération = 797 078 (25 % pile) · base RTS = 2 266 234 · RTS = 63 312 · **net = 3 000 000 exact** (l'application garantit le net au franc près — les montants exacts peuvent varier de ±quelques GNF selon les arrondis affichés) ;
- Congés : 2,5 j acquis après 1 mois → demande de 2 j **acceptée**, solde 0,5 j ;
- VF = 6 % × 3 188 312 ≈ 191 299 (jamais sur base réduite).

---

## 📎 Annexe formateur

### Erreurs volontaires à faire commettre (apprentissage par l'erreur)
1. Créer une indemnité transport de 40 % du brut → observer l'alerte de dépassement du plafond 25 % et la proposition de correction.
2. Saisir une demande de congé supérieure au solde → refus automatique.
3. Choisir un mauvais type d'heure supplémentaire → montant incorrect visible au bulletin.
4. Tenter de valider un besoin/une écriture sans lignes (modules Stock/Compta) → blocage.

### Barème de certification interne suggéré
| Score au cas de synthèse | Niveau |
|---|---|
| 7/7 étapes justes | Autonome — peut former d'autres utilisateurs |
| 5-6 | Opérationnel — supervision légère le 1er mois |
| < 5 | Reprendre les modules 2-4 |

### Rappels de prudence
- Les données de formation (SOGUIMEX, FORM-xxx) doivent être créées dans une **base d'essai/démo**, jamais dans la base de production d'un client.
- Après toute mise à jour de l'application, refaire l'exercice 2.1 (cas DIALLO) : c'est le « cas témoin » le plus rapide pour vérifier que le moteur calcule juste.
