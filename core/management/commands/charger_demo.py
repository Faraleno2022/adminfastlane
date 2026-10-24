"""Données de démonstration réalistes (fictives) pour présenter AdminFastlane.

    python manage.py charger_demo --utilisateur Myschool                      # grand volume (12 mois)
    python manage.py charger_demo --utilisateur Myschool --volume standard    # jeu réduit (3 mois)
    python manage.py charger_demo --utilisateur Myschool --supprimer

Les données sont rattachées à l'entreprise de l'utilisateur indiqué : structure,
employés et bulletins de paie, flotte, transport de carburant, projets, agence de
voyage, ventes (comptes prépayés), prêts et comptabilité (capital, factures de vente
et d'achat avec TVA, règlements, salaires et charges sociales, caisse). Les noms de
personnes et de sociétés sont inventés. Chaque objet créé, y compris par les services
et signaux de l'application, est noté dans core.DonneeDemo : l'option --supprimer
retire toute la démonstration sans toucher aux autres données.
"""
import random
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_save
from django.utils import timezone

from core.models import DonneeDemo, Etablissement, Poste, Service, Societe, Utilisateur
from core.tenancy import pour_entreprise

D = Decimal
ZERO = D(0)

VOLUMES = {
    "standard": {"mois": 3, "employes": 0, "vehicules": 4, "citernes": 3, "clients": 3, "voyages": 4, "projets": 3,
                 "dossiers": 4, "produits": 6, "comptes": 4, "ventes_caisse": 1, "prets": 3},
    "grand": {"mois": 12, "employes": 36, "vehicules": 12, "citernes": 8, "clients": 8, "voyages": 14, "projets": 10,
              "dossiers": 40, "produits": 24, "comptes": 60, "ventes_caisse": 30, "prets": 15},
}


def _mois_precedents(nombre):
    """(année, mois) des ``nombre`` mois révolus avant le mois courant, du plus ancien au plus récent."""
    annee, mois = timezone.localdate().year, timezone.localdate().month
    resultat = []
    for _ in range(nombre):
        mois -= 1
        if mois == 0:
            annee, mois = annee - 1, 12
        resultat.append((annee, mois))
    return list(reversed(resultat))


def _fin_de_mois(annee, mois):
    suivant = date(annee + (mois == 12), mois % 12 + 1, 1)
    return suivant - timedelta(days=1)


MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre",
           "Octobre", "Novembre", "Décembre"]

# Employés fixes (vérifiés à la main dans les tests) : (civilité, nom, prénoms, sexe, naissance, contrat,
# embauche, situation, enfants, service, poste, salaire de base, transport, logement, prime, paiement)
EMPLOYES = [
    ("M.", "CAMARA", "Ibrahima Sory", "M", date(1974, 2, 11), "CDI", date(2012, 3, 1), "marie", 4,
     "DIR", "DG", 9000000, 800000, 1500000, 1000000, "virement"),
    ("Mme", "BAH", "Mariama Dian", "F", date(1983, 6, 25), "CDI", date(2015, 9, 1), "marie", 2,
     "FIN", "RAF", 5500000, 500000, 800000, 0, "virement"),
    ("M.", "SYLLA", "Mohamed Lamine", "M", date(1986, 10, 3), "CDI", date(2017, 1, 16), "marie", 3,
     "LOG", "CLOG", 4200000, 400000, 0, 300000, "virement"),
    ("Mme", "KEITA", "Hawa", "F", date(1990, 4, 14), "CDI", date(2019, 5, 2), "celibataire", 0,
     "FIN", "CPT", 3000000, 300000, 300000, 0, "virement"),
    ("Mlle", "CONDE", "Aïssatou", "F", date(1995, 8, 30), "CDD", date(2023, 2, 1), "celibataire", 0,
     "COM", "COMM", 2500000, 250000, 0, 400000, "mobile_money"),
    ("M.", "TOURE", "Abdoulaye", "M", date(1982, 12, 9), "CDI", date(2016, 7, 4), "marie", 5,
     "LOG", "CHPL", 1800000, 200000, 0, 150000, "mobile_money"),
    ("Mme", "SOUMAH", "Fanta", "F", date(1992, 3, 21), "CDI", date(2020, 10, 1), "marie", 1,
     "DIR", "ASS", 1500000, 200000, 500000, 0, "mobile_money"),
    ("M.", "DOUMBOUYA", "Sékou", "M", date(1997, 1, 5), "CDD", date(2024, 4, 15), "celibataire", 0,
     "LOG", "MAG", 1100000, 150000, 0, 0, "especes"),
    ("Mlle", "KOUROUMA", "Nènè", "F", date(2003, 9, 12), "stage", None, "celibataire", 0,
     "COM", "STG", 800000, 100000, 0, 0, "mobile_money"),
]

SERVICES = [("DIR", "Direction générale"), ("FIN", "Administration & finances"), ("COM", "Commercial"),
            ("LOG", "Logistique & transport")]
POSTES = [("DG", "Directeur général", "DIR"), ("RAF", "Responsable administratif et financier", "FIN"),
          ("CLOG", "Chef logistique", "LOG"), ("CPT", "Comptable", "FIN"), ("COMM", "Chargée commerciale", "COM"),
          ("CHPL", "Chauffeur poids lourd", "LOG"), ("ASS", "Assistante de direction", "DIR"),
          ("MAG", "Magasinier", "LOG"), ("STG", "Stagiaire commerciale", "COM"),
          ("COND", "Conducteur de citerne", "LOG"), ("MECA", "Mécanicien", "LOG"), ("AGC", "Agent commercial", "COM"),
          ("CAIS", "Caissière", "FIN"), ("ACPT", "Aide-comptable", "FIN"), ("SECU", "Agent de sécurité", "DIR"),
          ("ALOG", "Agent logistique", "LOG")]
# Postes des employés générés : (code, salaire de base mini, maxi)
POSTES_GENERES = [("COND", 1600000, 2400000), ("COND", 1600000, 2400000), ("MECA", 1800000, 2800000),
                  ("AGC", 1500000, 2500000), ("CAIS", 1200000, 1800000), ("ACPT", 2000000, 3000000),
                  ("SECU", 900000, 1300000), ("ALOG", 1300000, 2000000)]

PRENOMS_H = ["Mamadou", "Alpha", "Ibrahima", "Ousmane", "Sékou", "Mohamed", "Abdoulaye", "Thierno", "Lansana",
             "Facinet", "Moussa", "Amadou", "Souleymane", "Boubacar", "Karamo", "Fodé", "Aboubacar", "Saliou"]
PRENOMS_F = ["Mariama", "Fatoumata", "Aïssatou", "Kadiatou", "Hawa", "Fanta", "Djénabou", "Aminata", "Mabinty",
             "Nènè", "Ramatoulaye", "Sira", "Oumou", "Kadija", "M'Balia", "Hadja"]
NOMS = ["DIALLO", "BARRY", "SOW", "BALDE", "FOFANA", "CISSE", "BANGOURA", "KABA", "KANTE", "TRAORE", "SAMPIL",
        "LAMAH", "HABA", "GUILAVOGUI", "MILLIMONO", "KOIVOGUI", "YANSANE", "SANOH", "KONATE", "DRAME", "CONTE",
        "TOUNKARA", "MAGASSOUBA", "CHERIF"]
VILLES = ["Kindia", "Mamou", "Labé", "Boké", "Kankan", "Faranah", "Siguiri", "Kissidougou", "Nzérékoré", "Dubréka",
          "Coyah", "Fria", "Boffa", "Pita", "Dalaba"]


class Command(BaseCommand):
    help = "Charge (ou supprime) des données de démonstration fictives dans l'entreprise d'un utilisateur."

    def add_arguments(self, parser):
        parser.add_argument("--utilisateur", required=True, help="Identifiant de connexion d'un utilisateur de l'entreprise.")
        parser.add_argument("--volume", choices=sorted(VOLUMES), default="grand",
                            help="grand (12 mois, défaut) ou standard (jeu réduit de 3 mois).")
        parser.add_argument("--mois", type=int, help="Nombre de mois d'activité (remplace celui du volume).")
        parser.add_argument("--supprimer", action="store_true", help="Supprime la démonstration chargée.")

    def handle(self, *args, **options):
        user = Utilisateur.objects.filter(username__iexact=options["utilisateur"]).select_related("entreprise").first()
        if user is None or user.entreprise is None:
            raise CommandError(f"Utilisateur « {options['utilisateur']} » introuvable ou sans entreprise.")
        entreprise = user.entreprise
        if options["supprimer"]:
            self._supprimer(entreprise)
            return
        if DonneeDemo.objects.filter(entreprise=entreprise).exists():
            raise CommandError("Une démonstration est déjà chargée pour cette entreprise : "
                               "lancez d'abord la commande avec --supprimer.")
        self.v = dict(VOLUMES[options["volume"]])
        if options["mois"] is not None:
            if not 1 <= options["mois"] <= 24:
                raise CommandError("--mois doit être compris entre 1 et 24.")
            self.v["mois"] = options["mois"]

        self.user, self.entreprise = user, entreprise
        self.suffixe = entreprise.pk.hex[:4].upper()
        self.mois = _mois_precedents(self.v["mois"])
        self.aujourdhui = timezone.localdate()
        self.debut = date(*self.mois[0], 1)
        self.rng = random.Random(f"demo-{entreprise.pk}")
        self.resume = []

        from comptabilite.moteur_comptable import ErreurComptabilisation
        try:
            crees = self._charger(entreprise)
        except ErreurComptabilisation as exc:
            raise CommandError(f"Comptabilité : {exc}") from exc

        self.stdout.write(self.style.SUCCESS(
            f"Démonstration chargée pour « {entreprise.nom_entreprise} » ({len(crees)} enregistrements)."))
        for ligne in self.resume:
            self.stdout.write(ligne)
        self.stdout.write("Pour tout retirer : python manage.py charger_demo --utilisateur "
                          f"{user.username} --supprimer")

    def _charger(self, entreprise):
        with transaction.atomic(), pour_entreprise(entreprise):
            with self._enregistrer() as crees:
                employes = self._rh()
                bulletins = self._paie(employes)
                vehicules = self._flotte()
                voyages = self._carburant(vehicules)
                self._projets()
                self._agence()
                self._ventes()
                self._prets()
                self._comptabilite(bulletins, voyages)
            DonneeDemo.objects.bulk_create([
                DonneeDemo(entreprise=entreprise, content_type=ContentType.objects.get_for_model(modele),
                           object_id=str(pk))
                for modele, pk in crees
            ], batch_size=1000)
        return crees

    # ------------------------------------------------------------------
    # Registre des objets créés
    # ------------------------------------------------------------------
    @contextmanager
    def _enregistrer(self):
        crees = []

        def recepteur(sender, instance, created, raw=False, **kwargs):
            if created and not raw and sender is not DonneeDemo:
                crees.append((sender, instance.pk))

        post_save.connect(recepteur, weak=False, dispatch_uid="charger_demo")
        try:
            yield crees
        finally:
            post_save.disconnect(dispatch_uid="charger_demo")

    def _supprimer(self, entreprise):
        lignes = list(DonneeDemo.objects.filter(entreprise=entreprise).select_related("content_type").order_by("-id"))
        if not lignes:
            self.stdout.write("Aucune démonstration à supprimer.")
            return
        supprimes = 0
        with transaction.atomic(), pour_entreprise(entreprise):
            for ligne in lignes:  # ordre inverse de création : les dépendances partent d'abord
                modele = ligne.content_type.model_class()
                obj = modele._base_manager.filter(pk=ligne.object_id).first() if modele else None
                if obj is None:  # déjà supprimé en cascade
                    continue
                if hasattr(obj, "hard_delete"):  # Flotte : suppression logique par défaut
                    obj.hard_delete()
                else:
                    obj.delete()
                supprimes += 1
            DonneeDemo.objects.filter(entreprise=entreprise).delete()
        self.stdout.write(self.style.SUCCESS(f"Démonstration supprimée ({supprimes} enregistrements)."))

    # ------------------------------------------------------------------
    # Aides
    # ------------------------------------------------------------------
    def _agent(self):
        return (self.user.get_full_name() or self.user.get_username()).strip()

    def _personne(self, femme=None):
        femme = self.rng.random() < 0.4 if femme is None else femme
        prenom = self.rng.choice(PRENOMS_F if femme else PRENOMS_H)
        return femme, prenom, self.rng.choice(NOMS)

    def _telephone(self):
        return f"+224 6{self.rng.choice('2256')}{self.rng.randint(0, 9)} {self.rng.randint(10, 99)} " \
               f"{self.rng.randint(10, 99)} {self.rng.randint(10, 99)}"

    def _jour(self, annee, mois, jour):
        return min(date(annee, mois, min(jour, _fin_de_mois(annee, mois).day)), self.aujourdhui)

    # ------------------------------------------------------------------
    # Structure et employés
    # ------------------------------------------------------------------
    def _rh(self):
        from employes.models import Employe
        from paie.models import ElementSalaire

        societe = Societe.objects.filter(entreprise=self.entreprise).first() or Societe.objects.create(
            entreprise=self.entreprise, raison_sociale=self.entreprise.nom_entreprise, ville="Conakry")
        etablissement = Etablissement.objects.filter(societe=societe).first() or Etablissement.objects.create(
            societe=societe, code_etablissement=f"SIEGE-{self.suffixe}", nom_etablissement="Siège — Kaloum",
            type_etablissement="siege", ville="Conakry")
        services = {}
        for code, nom in SERVICES:
            services[code], _ = Service.objects.get_or_create(
                entreprise=self.entreprise, code_service=f"D-{code}",
                defaults={"nom_service": nom, "etablissement": etablissement})
        postes = {}
        for code, intitule, service in POSTES:
            postes[code], _ = Poste.objects.get_or_create(
                entreprise=self.entreprise, code_poste=f"D-{code}",
                defaults={"intitule_poste": intitule, "service": services[service]})
        self.rubriques = self._rubriques()

        profils = list(EMPLOYES)
        for n in range(self.v["employes"]):
            code, mini, maxi = POSTES_GENERES[n % len(POSTES_GENERES)]
            femme, prenom, nom = self._personne(femme=True if code == "CAIS" else (False if code in ("COND", "MECA") else None))
            service = next(s for c, _, s in POSTES if c == code)
            base = self.rng.randrange(mini, maxi + 1, 50000)
            transport = self.rng.randrange(150000, 400001, 50000)
            logement = self.rng.choice([0, 0, 200000, 300000])
            prime = self.rng.choice([0, 0, 100000, 150000, 250000])
            naissance = date(self.rng.randint(1975, 2000), self.rng.randint(1, 12), self.rng.randint(1, 28))
            embauche = date(self.rng.randint(2014, self.debut.year - 1), self.rng.randint(1, 12), 1)
            profils.append(("Mme" if femme else "M.", nom, prenom, "F" if femme else "M", naissance,
                            self.rng.choice(["CDI", "CDI", "CDI", "CDD"]), embauche,
                            self.rng.choice(["marie", "celibataire"]), self.rng.randint(0, 5), service, code,
                            base, transport, logement, prime, self.rng.choice(["virement", "mobile_money"])))

        employes = []
        for i, (civ, nom, prenoms, sexe, naissance, contrat, embauche, situation, enfants, service, poste,
                base, transport, logement, prime, paiement) in enumerate(profils, start=1):
            embauche = embauche or self.debut  # stagiaire : stage commencé avec la démonstration
            employe = Employe.objects.create(
                entreprise=self.entreprise, matricule=f"D{self.suffixe}-{i:03d}", civilite=civ, nom=nom,
                prenoms=prenoms, sexe=sexe, date_naissance=naissance, lieu_naissance=self.rng.choice(["Conakry"] + VILLES),
                type_contrat=contrat, date_embauche=embauche, date_debut_contrat=embauche,
                situation_matrimoniale=situation, nombre_enfants=enfants, etablissement=etablissement,
                service=services[service], poste=postes[poste], statut_employe="actif",
                telephone_principal=self._telephone(),
                email_professionnel=f"{prenoms[0].lower()}.{nom.lower()}{i}@exemple-demo.gn", mode_paiement=paiement,
                nom_banque="Banque de démonstration" if paiement == "virement" else None,
                operateur_mobile_money="Orange Money" if paiement == "mobile_money" else None,
                utilisateur_creation=self.user)
            ElementSalaire.objects.filter(employe=employe).delete()  # élément créé par signal, remplacé ci-dessous
            for cle, montant in (("base", base), ("transport", transport), ("logement", logement), ("prime", prime)):
                if montant:
                    ElementSalaire.objects.create(
                        employe=employe, rubrique=self.rubriques[cle], montant=D(montant),
                        date_debut=embauche, actif=True, recurrent=True)
            employes.append(employe)
        self.resume.append(f"  Employés : {len(employes)} (services, postes et éléments de salaire)")
        return employes

    def _rubriques(self):
        from paie.models import RubriquePaie

        def rubrique(code, libelle, categorie, soumis, ordre):
            obj, _ = RubriquePaie.objects.get_or_create(
                entreprise=self.entreprise, code_rubrique=code,
                defaults={"libelle_rubrique": libelle, "type_rubrique": "gain", "categorie_rubrique": categorie,
                          "soumis_cnss": soumis, "soumis_irg": soumis, "ordre_calcul": ordre,
                          "ordre_affichage": ordre, "actif": True})
            return obj

        return {
            "base": rubrique("SAL_BASE", "Salaire de base", "salaire_base", True, 10),
            "transport": rubrique("IND_TRANSPORT", "Indemnité de transport", "indemnite", False, 20),
            "logement": rubrique("IND_LOGEMENT", "Indemnité de logement", "indemnite", False, 21),
            "prime": rubrique("PRIME_RESP", "Prime de responsabilité", "prime", True, 30),
        }

    # ------------------------------------------------------------------
    # Paie
    # ------------------------------------------------------------------
    def _paie(self, employes):
        from paie.models import PeriodePaie
        from paie.services import MoteurCalculPaie

        par_mois = {}
        for annee, mois in self.mois:
            periode, cree = PeriodePaie.objects.get_or_create(
                entreprise=self.entreprise, annee=annee, mois=mois,
                defaults={"libelle": f"{MOIS_FR[mois]} {annee}", "date_debut": date(annee, mois, 1),
                          "date_fin": _fin_de_mois(annee, mois), "statut_periode": "ouverte"})
            if not cree and periode.statut_periode != "ouverte":
                self.resume.append(f"  Paie {MOIS_FR[mois]} {annee} : période déjà {periode.statut_periode}, ignorée")
                continue
            par_mois[(annee, mois)] = [MoteurCalculPaie(e, periode).generer_bulletin(self.user) for e in employes]
        nb = sum(len(b) for b in par_mois.values())
        if nb:
            dernier = par_mois.get(self.mois[-1], [])
            self.resume.append(f"  Paie : {nb} bulletins sur {len(par_mois)} mois ; "
                               f"{MOIS_FR[self.mois[-1][1]]} {self.mois[-1][0]} (premiers employés) :")
            for b in dernier[:len(EMPLOYES)]:
                self.resume.append(
                    f"    {b.employe.nom:<10} brut {b.salaire_brut:>12,.0f}  CNSS {b.cnss_employe:>9,.0f}  "
                    f"RTS {b.irg:>9,.0f}  net {b.net_a_payer:>12,.0f}".replace(",", " "))
            masse = sum((b.salaire_brut for b in dernier), ZERO)
            self.resume.append(f"    Masse salariale brute du mois : {masse:,.0f} GNF".replace(",", " "))
        return par_mois

    # ------------------------------------------------------------------
    # Flotte
    # ------------------------------------------------------------------
    def _flotte(self):
        from flotte.models import Chauffeur, Entretien, Marque, PleinCarburant, Vehicule, Voyage

        noms = ["Abdoulaye Touré", "Mamadou Saliou Diallo", "Ousmane Camara", "Lansana Kaba"]
        while len(noms) < self.v["vehicules"]:
            _, prenom, nom = self._personne(femme=False)
            noms.append(f"{prenom} {nom.title()}")
        chauffeurs = [Chauffeur.objects.create(nom_prenoms=n, telephone=self._telephone()) for n in noms]
        marques = [Marque.objects.get_or_create(nom=n)[0] for n in ("Renault Trucks", "Mercedes-Benz", "Volvo", "MAN")]
        vehicules = []
        for i in range(self.v["vehicules"]):
            pick_up = i % 4 == 3
            vehicules.append(Vehicule.objects.create(
                immatriculation=f"RC-{1000 + (i * 2731) % 9000}-{chr(65 + i % 26)}{chr(66 + (i * 7) % 25)}",
                marque=marques[i % len(marques)], type_vehicule="Pick-up de liaison" if pick_up else "Tracteur routier",
                chauffeur_actuel=chauffeurs[i], actif=True))
        self.entretiens = defaultdict(list)
        pleins = entretiens = activites = 0
        for n, (annee, mois) in enumerate(self.mois):
            for i, vehicule in enumerate(vehicules):
                pick_up = vehicule.type_vehicule.startswith("Pick-up")
                for jour in (6, 20):
                    PleinCarburant.objects.create(
                        date=self._jour(annee, mois, jour), vehicule=vehicule, chauffeur=vehicule.chauffeur_actuel,
                        litres=D(self.rng.choice([60, 70, 80]) if pick_up else self.rng.choice([300, 350, 400])),
                        prix_litre=D(12000), kilometrage=48000 + 3200 * n + i * 9000 + jour * 40,
                        n_bon=f"BC-{annee}{mois:02d}{jour:02d}-{i + 1}")
                    pleins += 1
                if not pick_up and self.v["vehicules"] > 4:
                    Voyage.objects.create(date=self._jour(annee, mois, 25), vehicule=vehicule,
                                          chauffeur=vehicule.chauffeur_actuel, n_bon=f"AV-{annee}{mois:02d}-{i + 1}",
                                          nb_voyage=self.rng.randint(3, 8), pu_voyage=D(1500000))
                    activites += 1
            # Entretiens : montant TTC = HT × 1,18 (facture du garage reprise en comptabilité)
            for vehicule in vehicules[n % 3::3] if self.v["vehicules"] > 4 else [vehicules[n % len(vehicules)]]:
                ht = D(2500000 + 300000 * (n % 4))
                Entretien.objects.create(
                    date=self._jour(annee, mois, 14), vehicule=vehicule, chauffeur=vehicule.chauffeur_actuel,
                    n_facture=f"FG-{annee}{mois:02d}-{entretiens + 1:03d}", garage="Garage central de Matoto",
                    nature_operations="Vidange moteur, filtres à huile et à gasoil, contrôle des freins",
                    montant_ttc=ht * D("1.18"))
                self.entretiens[(annee, mois)].append(ht)
                entretiens += 1
        self.pleins_par_mois = {
            (a, m): sum((p.montant for p in PleinCarburant.objects.filter(date__year=a, date__month=m,
                                                                          vehicule__in=vehicules)), ZERO)
            for a, m in self.mois}
        self.resume.append(f"  Flotte : {len(vehicules)} véhicules, {len(chauffeurs)} chauffeurs, {pleins} pleins, "
                           f"{entretiens} entretiens" + (f", {activites} relevés d'activité" if activites else ""))
        return vehicules

    # ------------------------------------------------------------------
    # Transport de carburant
    # ------------------------------------------------------------------
    def _carburant(self, vehicules):
        from carburant.models import Citerne, Client, FraisVoyage, Paiement, Voyage

        bases = [("Kaloum Énergie SARL", 150, D("0.5"), "Station Kaloum Énergie — Dixinn"),
                 ("Bauxite Rive Ouest SA", 220, D("0.3"), "Site minier — Boffa"),
                 ("Réseau Stations du Fouta", 180, D("0.5"), "Station du Fouta — Labé")]
        for n in range(self.v["clients"] - len(bases)):
            ville = VILLES[n % len(VILLES)]
            nom = [f"Station Service {ville}", f"Mines et Carrières de {ville}", f"Transports {ville} Express",
                   f"Centrale électrique de {ville}"][n % 4]
            bases.append((nom, self.rng.choice([150, 160, 180, 200, 220]), D("0.5"), f"{nom} — {ville}"))
        clients = [Client.objects.create(nom=nom, contact="Service approvisionnement", telephone=self._telephone(),
                                         tarif_litre=D(tarif), tolerance_pct=tol)
                   for nom, tarif, tol, _ in bases[:self.v["clients"]]]
        destinations = {c.pk: bases[i][3] for i, c in enumerate(clients)}
        capacites = [40000, 36000, 33000, 40000, 36000, 30000, 40000, 33000]
        tracteurs = [v for v in vehicules if not v.type_vehicule.startswith("Pick-up")]
        citernes = []
        for i in range(self.v["citernes"]):
            citernes.append(Citerne.objects.create(
                immatriculation=f"CIT-{i + 1:02d}", vehicule=tracteurs[i % len(tracteurs)], capacite=D(capacites[i % 8]),
                nb_compartiments=4 if capacites[i % 8] >= 40000 else 3, numero_barremage=f"BAR-2026-{100 + i}",
                expiration_barremage=self.aujourdhui + timedelta(days=20 if i == 1 else 150 + 40 * i)))
        ecarts = [D(40), D(130), D(260), D(90), D(0), D(180), D(310), D(60)]
        livres = []
        for n, (annee, mois) in enumerate(self.mois):
            for k in range(self.v["voyages"]):
                client = clients[k % len(clients)]
                citerne = citernes[(k + n) % len(citernes)]
                charge = citerne.capacite - D(500 * (k % 3))
                jour = 2 + (k * 27) // max(self.v["voyages"], 1)
                produit = "essence" if k % 5 == 2 else "gasoil"
                v = Voyage.objects.create(
                    client=client, citerne=citerne, produit=produit, lieu_chargement="Dépôt pétrolier de Conakry",
                    destination=destinations[client.pk], date_prevue=self._jour(annee, mois, jour),
                    date_chargement=self._jour(annee, mois, jour), bon_chargement=f"BCH-{annee}{mois:02d}-{k + 1:02d}",
                    quantite_chargee=charge, date_livraison=self._jour(annee, mois, jour + 1),
                    bon_livraison=f"BL-{annee}{mois:02d}-{k + 1:02d}", quantite_livree=charge - ecarts[(k + n) % 8],
                    tarif_litre=client.tarif_litre, tolerance_pct=client.tolerance_pct, prix_produit=D(12000),
                    statut=Voyage.LIVRE, agent=self._agent())
                for type_frais, montant in (("gasoil_camion", 1200000 + 150000 * (k % 3)), ("mission", 300000),
                                            ("peage", 100000)):
                    FraisVoyage.objects.create(voyage=v, type=type_frais, date=v.date_chargement, montant=D(montant))
                livres.append(v)
        # Activité du mois en cours : citernes en route (une seule par citerne), voyages planifiés, un annulé
        debut_mois = self.aujourdhui.replace(day=1)
        for k in range(min(2, len(citernes))):
            client = clients[k % len(clients)]
            Voyage.objects.create(
                client=client, citerne=citernes[k], produit="gasoil", lieu_chargement="Dépôt pétrolier de Conakry",
                destination=destinations[client.pk], date_prevue=debut_mois, date_chargement=debut_mois,
                bon_chargement=f"BCH-EN-{k + 1}", quantite_chargee=citernes[k].capacite, tarif_litre=client.tarif_litre,
                tolerance_pct=client.tolerance_pct, prix_produit=D(12000), statut=Voyage.EN_ROUTE, agent=self._agent())
        for k in range(1 if len(citernes) <= 3 else 3):
            client = clients[(k + 2) % len(clients)]
            Voyage.objects.create(
                client=client, citerne=citernes[(k + 2) % len(citernes)], produit="essence",
                lieu_chargement="Dépôt pétrolier de Conakry", destination=destinations[client.pk],
                date_prevue=self.aujourdhui + timedelta(days=2 + k), tarif_litre=client.tarif_litre,
                tolerance_pct=client.tolerance_pct, prix_produit=D(12000), agent=self._agent())
        Voyage.objects.create(
            client=clients[0], citerne=citernes[-1], produit="gasoil", lieu_chargement="Dépôt pétrolier de Conakry",
            destination=destinations[clients[0].pk], date_prevue=debut_mois, statut=Voyage.ANNULE,
            tarif_litre=clients[0].tarif_litre, tolerance_pct=clients[0].tolerance_pct,
            note="Commande annulée par le client", agent=self._agent())
        # Encaissements directs du module (hors comptabilité) : part du facturé selon le client
        for i, client in enumerate(clients):
            facture = sum((v.montant_net for v in livres if v.client_id == client.pk), ZERO)
            part = [D("0.70"), D("0.50"), D("0.85"), D("0.95"), D("0.60")][i % 5]
            Paiement.objects.create(client=client, date=self.aujourdhui - timedelta(days=10),
                                    montant=(facture * part).quantize(D(1000)), mode="virement",
                                    reference=f"VIR-{client.pk:04d}", agent=self._agent())
        self.resume.append(f"  Transport de carburant : {len(clients)} clients, {len(citernes)} citernes, "
                           f"{len(livres)} voyages livrés, 2 en route, planifiés et annulé")
        return livres

    # ------------------------------------------------------------------
    # Gestion de projet
    # ------------------------------------------------------------------
    def _projets(self):
        from projets.models import Client, Membre, Mouvement, Projet, Tache

        c1 = Client.objects.create(nom="Coopérative des Transporteurs de Kindia", contact="M. Fofana",
                                   telephone=self._telephone())
        c2 = Client.objects.create(nom="Groupe scolaire Les Palmiers", contact="Mme Sow", telephone=self._telephone())
        clients = [c1, c2] + [Client.objects.create(nom=n, contact="Direction", telephone=self._telephone())
                              for n in ("Commune de Matoto", "Clinique Sainte-Espérance", "Association des Femmes de Coyah")]
        projets = [
            (Projet.objects.create(nom="Construction d'un entrepôt logistique à Kagbelen", client=c1,
                                   responsable="Mohamed Lamine Sylla", budget=D(450000000), date_debut=self.debut,
                                   date_fin_prevue=self.aujourdhui + timedelta(days=60), statut=Projet.EN_COURS,
                                   lieu="Kagbelen, Dubréka", ville="Dubréka", cree_par=self._agent()),
             [("Études et plans", 100, Tache.TERMINEE, -80), ("Terrassement et fondations", 100, Tache.TERMINEE, -45),
              ("Élévation des murs", 60, Tache.EN_COURS, -5), ("Charpente et toiture", 0, Tache.A_FAIRE, 25),
              ("Électricité et réception", 0, Tache.A_FAIRE, 55)],
             [(Mouvement.DEPOT, None, 150000000, "Avance au démarrage", -85),
              (Mouvement.DEPENSE, "etudes", 18000000, "Honoraires du bureau d'études", -78),
              (Mouvement.DEPENSE, "materiaux", 96500000, "Ciment, fer à béton et agrégats", -50),
              (Mouvement.DEPENSE, "main_oeuvre", 42000000, "Paie de l'équipe de maçons", -30),
              (Mouvement.DEPOT, None, 120000000, "Deuxième tranche client", -20),
              (Mouvement.DEPENSE, "equipement", 15500000, "Location de bétonnière et d'échafaudages", -12)]),
            (Projet.objects.create(nom="Rénovation des salles de classe", client=c2, responsable="Mariama Dian Bah",
                                   budget=D(45000000), date_debut=self.debut,
                                   date_fin_prevue=self.aujourdhui - timedelta(days=6), statut=Projet.EN_COURS,
                                   lieu="Ratoma", ville="Conakry", cree_par=self._agent()),
             [("Peinture des classes", 100, Tache.TERMINEE, -30), ("Remplacement des tables-bancs", 70, Tache.EN_COURS, -6),
              ("Installation électrique", 30, Tache.BLOQUEE, -2)],
             [(Mouvement.DEPOT, None, 40000000, "Acompte de l'école", -60),
              (Mouvement.DEPENSE, "materiaux", 52000000, "Peinture, tables-bancs et câblage", -35),
              (Mouvement.DEPENSE, "main_oeuvre", 38000000, "Menuisiers et électriciens", -15)]),
            (Projet.objects.create(nom="Installation d'une station-service à Coyah", client=c1,
                                   responsable="Ibrahima Sory Camara", budget=D(1200000000),
                                   date_debut=self.aujourdhui + timedelta(days=20),
                                   date_fin_prevue=self.aujourdhui + timedelta(days=200), statut=Projet.PLANIFIE,
                                   lieu="Route nationale 1, Coyah", ville="Coyah", cree_par=self._agent()),
             [("Autorisations administratives", 20, Tache.EN_COURS, 15), ("Appel d'offres des cuves", 0, Tache.A_FAIRE, 40)],
             [(Mouvement.DEPOT, None, 200000000, "Apport initial", -3)]),
        ]
        noms = ["Réfection de la piste d'accès au dépôt", "Clôture et gardiennage du parc à camions",
                "Construction d'un atelier mécanique", "Extension des bureaux du siège", "Forage et château d'eau",
                "Aménagement d'une aire de lavage", "Installation de panneaux solaires", "Réhabilitation d'un centre de santé",
                "Construction d'un hangar de stockage", "Mise en place d'un réseau informatique"]
        etapes = ["Études et devis", "Préparation du site", "Gros œuvre", "Second œuvre", "Finitions", "Réception"]
        for n in range(self.v["projets"] - len(projets)):
            budget = D(self.rng.randrange(60, 900, 20) * 1000000)
            demarre = self.debut + timedelta(days=self.rng.randint(0, max(1, (self.aujourdhui - self.debut).days - 60)))
            duree = self.rng.randint(90, 300)
            fin = demarre + timedelta(days=duree)
            statut = Projet.TERMINE if fin < self.aujourdhui - timedelta(days=10) and n % 3 == 0 else Projet.EN_COURS
            projet = Projet.objects.create(
                nom=noms[n % len(noms)], client=clients[n % len(clients)], budget=budget, date_debut=demarre,
                date_fin_prevue=fin, date_fin_reelle=fin if statut == Projet.TERMINE else None, statut=statut,
                responsable=f"{self._personne()[1]} {self._personne()[2].title()}", ville=self.rng.choice(VILLES),
                lieu="Chantier", cree_par=self._agent())
            ecoule = max(0, min(100, int((self.aujourdhui - demarre).days * 100 / duree)))
            taches = []
            for k, etape in enumerate(etapes):
                seuil = (k + 1) * 100 // len(etapes)
                progression = 100 if statut == Projet.TERMINE or ecoule >= seuil else max(0, ecoule - k * 100 // len(etapes)) * len(etapes)
                progression = min(progression, 100)
                tache_statut = Tache.TERMINEE if progression == 100 else (Tache.EN_COURS if progression > 0 else Tache.A_FAIRE)
                taches.append((etape, progression, tache_statut, (demarre - self.aujourdhui).days + (k + 1) * duree // len(etapes)))
            mouvements = [(Mouvement.DEPOT, None, int(budget * D("0.4")), "Avance du client", (demarre - self.aujourdhui).days + 2)]
            for k, categorie in enumerate(["etudes", "materiaux", "main_oeuvre", "equipement", "transport", "materiaux"]):
                jour = (demarre - self.aujourdhui).days + 10 + k * duree // 7
                if jour < 0:
                    mouvements.append((Mouvement.DEPENSE, categorie, int(budget * D(self.rng.choice(["0.08", "0.12", "0.15", "0.20"]))),
                                       f"Dépense {dict(Mouvement.CATEGORIES)[categorie].lower()} — lot {k + 1}", jour))
            if (self.aujourdhui - demarre).days > duree // 2:
                mouvements.append((Mouvement.DEPOT, None, int(budget * D("0.3")), "Deuxième tranche client",
                                   (demarre - self.aujourdhui).days + duree // 2))
            projets.append((projet, taches, mouvements))
        nb_taches = nb_mouvements = 0
        for projet, taches, mouvements in projets:
            for ordre, (titre, progression, statut, echeance) in enumerate(taches, start=1):
                Tache.objects.create(projet=projet, titre=titre, responsable=projet.responsable, ordre=ordre,
                                     date_debut=projet.date_debut, statut=statut, progression=progression,
                                     date_fin_prevue=self.aujourdhui + timedelta(days=echeance),
                                     priorite=Tache.HAUTE if statut == Tache.BLOQUEE else Tache.MOYENNE)
                nb_taches += 1
            for type_m, categorie, montant, libelle, jours in mouvements:
                Mouvement.objects.create(projet=projet, type=type_m, categorie=categorie or "", montant=D(montant),
                                         libelle=libelle, date=self.aujourdhui + timedelta(days=jours),
                                         mode="virement", saisi_par=self._agent())
                nb_mouvements += 1
        for nom, role in (("Mohamed Lamine Sylla", "Chef de chantier"), ("Abdoulaye Touré", "Conducteur d'engins"),
                          ("Ousmane Camara", "Chef d'équipe maçons")):
            Membre.objects.create(projet=projets[0][0], nom=nom, role=role, date_debut=self.debut)
        self.resume.append(f"  Projets : {len(projets)} projets (dont 1 en retard et 1 au budget dépassé), "
                           f"{nb_taches} tâches, {nb_mouvements} mouvements")

    # ------------------------------------------------------------------
    # Agence de voyage
    # ------------------------------------------------------------------
    def _agence(self):
        from agence.models import Client, Dossier, Fournisseur, PaiementClient, PaiementFournisseur, Prestation, Voyageur

        f_air = Fournisseur.objects.create(nom="Air Côte Ouest", type=Fournisseur.COMPAGNIE, telephone="+224 620 10 10 10")
        f_hotel = Fournisseur.objects.create(nom="Hôtel Les Palmiers — Dakar", type=Fournisseur.HOTEL)
        f_visa = Fournisseur.objects.create(nom="Service consulaire (visas)", type=Fournisseur.VISA)
        f_assur = Fournisseur.objects.create(nom="Assurance Voyage Plus", type=Fournisseur.ASSURANCE)
        f_air2 = Fournisseur.objects.create(nom="Sahel Airways", type=Fournisseur.COMPAGNIE)
        f_hotel2 = Fournisseur.objects.create(nom="Résidence Atlantique — Casablanca", type=Fournisseur.HOTEL)
        clients = [Client.objects.create(nom=n, telephone=self._telephone(), nationalite="Guinéenne", passeport_numero=p,
                                         passeport_expiration=self.aujourdhui + timedelta(days=e))
                   for n, p, e in (("Alpha Oumar Diallo", "R0451287", 900), ("Kadiatou Barry", "R0773019", 120),
                                   ("Famille Kaba", "R0928364", 1500), ("Thierno Sow", "R0112045", 700))]
        for n in range(max(0, self.v["dossiers"] // 2 - len(clients))):
            femme, prenom, nom = self._personne()
            clients.append(Client.objects.create(
                nom=f"{prenom} {nom.title()}", telephone=self._telephone(), nationalite="Guinéenne",
                passeport_numero=f"R0{self.rng.randint(100000, 999999)}",
                passeport_expiration=self.aujourdhui + timedelta(days=self.rng.choice([90, 400, 900, 1500]))))
        dossiers = [
            (clients[0], "Paris", "Affaires", -18, 9, Dossier.TERMINE,
             [(Prestation.BILLET, "Conakry → Paris → Conakry, classe économique", f_air, 1, 7800000, 8600000),
              (Prestation.ASSURANCE, "Assurance voyage 10 jours", f_assur, 1, 350000, 500000)], 1.0),
            (clients[1], "Dakar", "Tourisme", 25, 5, Dossier.CONFIRME,
             [(Prestation.BILLET, "Conakry → Dakar → Conakry", f_air, 1, 3200000, 3700000),
              (Prestation.HOTEL, "Hôtel 4 nuits, petit-déjeuner inclus", f_hotel, 4, 650000, 800000)], 0.5),
            (clients[2], "Djeddah", "Pèlerinage (Oumra)", 40, 14, Dossier.CONFIRME,
             [(Prestation.BILLET, "Conakry → Djeddah → Conakry", f_air, 3, 9500000, 10500000),
              (Prestation.VISA, "Visa Oumra", f_visa, 3, 1800000, 2200000),
              (Prestation.HOTEL, "Hébergement 12 nuits", f_hotel, 3, 4200000, 5000000)], 0.6),
            (clients[3], "Casablanca", "Études", 12, 0, Dossier.DEVIS,
             [(Prestation.BILLET, "Conakry → Casablanca, aller simple", f_air, 1, 4100000, 4600000)], 0.0),
        ]
        catalogue = [("Paris", "Affaires", f_air, 7800000, 8600000, f_hotel2, 900000, 1100000),
                     ("Dakar", "Tourisme", f_air2, 3200000, 3700000, f_hotel, 650000, 800000),
                     ("Abidjan", "Affaires", f_air2, 3600000, 4100000, f_hotel, 700000, 850000),
                     ("Casablanca", "Études", f_air, 4100000, 4600000, f_hotel2, 600000, 750000),
                     ("Istanbul", "Commerce", f_air, 6900000, 7700000, f_hotel2, 800000, 950000),
                     ("Dubaï", "Commerce", f_air, 8200000, 9100000, f_hotel2, 1200000, 1450000)]
        for n in range(self.v["dossiers"] - len(dossiers)):
            ville, objet, compagnie, achat, vente, hotel, h_achat, h_vente = catalogue[n % len(catalogue)]
            decalage = self.rng.randint(-(self.aujourdhui - self.debut).days, 60)
            nb = self.rng.choice([1, 1, 2, 3])
            nuits = self.rng.choice([0, 3, 5, 7])
            statut = (Dossier.TERMINE if decalage < -15 else Dossier.CONFIRME) if n % 9 else \
                self.rng.choice([Dossier.DEVIS, Dossier.ANNULE])
            prestations = [(Prestation.BILLET, f"Conakry → {ville} → Conakry", compagnie, nb, achat, vente),
                           (Prestation.ASSURANCE, "Assurance voyage", f_assur, nb, 350000, 500000)]
            if nuits:
                prestations.append((Prestation.HOTEL, f"Hôtel {nuits} nuits", hotel, nb * nuits, h_achat, h_vente))
            part = 1.0 if statut == Dossier.TERMINE else (0.0 if statut in (Dossier.DEVIS, Dossier.ANNULE)
                                                          else self.rng.choice([0.3, 0.5, 1.0]))
            dossiers.append((clients[(n + 4) % len(clients)], ville, objet, decalage, nuits or 5, statut, prestations, part))
        for client, destination, objet, dans, duree, statut, prestations, part in dossiers:
            depart = self.aujourdhui + timedelta(days=dans)
            cree = min(depart - timedelta(days=20), self.aujourdhui)
            dossier = Dossier.objects.create(
                client=client, destination=destination, objet=objet, date_depart=depart,
                date_retour=depart + timedelta(days=duree) if duree else None, nb_voyageurs=prestations[0][3],
                statut=statut, agent=self._agent(), created_at=timezone.make_aware(datetime.combine(cree, time(10))))
            for type_p, description, fournisseur, qte, achat, vente in prestations:
                p = Prestation.objects.create(
                    dossier=dossier, type=type_p, description=description, fournisseur=fournisseur,
                    quantite=D(qte), prix_achat=D(achat), prix_vente=D(vente), date_debut=depart,
                    statut=Prestation.CONFIRMEE if statut not in (Dossier.DEVIS, Dossier.ANNULE) else Prestation.ATTENTE)
                if statut == Dossier.TERMINE:
                    PaiementFournisseur.objects.create(prestation=p, montant=p.total_achat, mode="virement")
            Voyageur.objects.create(dossier=dossier, nom=client.nom, nationalite="Guinéenne",
                                    passeport_numero=client.passeport_numero,
                                    passeport_expiration=client.passeport_expiration)
            total = sum((D(q) * D(v) for _, _, _, q, _, v in prestations), ZERO)
            if part:
                PaiementClient.objects.create(dossier=dossier, montant=(total * D(str(part))).quantize(D(1000)),
                                              date=cree, mode="especes" if part < 1 else "virement", agent=self._agent())
        self.resume.append(f"  Agence de voyage : {len(clients)} clients, 6 fournisseurs, {len(dossiers)} dossiers")

    # ------------------------------------------------------------------
    # Ventes (comptes prépayés et caisse)
    # ------------------------------------------------------------------
    def _ventes(self):
        from ventes import services
        from ventes.models import ClientCompte, MouvementStock, Produit, Vente

        catalogue = [("Sandwich poulet", "SNK-01", "Restauration", "pièce", 10000, 6500, 60),
                     ("Pain au chocolat", "SNK-02", "Restauration", "pièce", 3000, 1800, 120),
                     ("Jus de bissap 33 cl", "BOI-01", "Boissons", "bouteille", 5000, 3000, 96),
                     ("Eau minérale 50 cl", "BOI-02", "Boissons", "bouteille", 2000, 1100, 144),
                     ("Cahier 200 pages", "FOU-01", "Fournitures", "pièce", 10000, 6000, 80),
                     ("Stylo à bille (lot de 4)", "FOU-02", "Fournitures", "lot", 4000, 2200, 60),
                     ("Riz gras au poisson", "SNK-03", "Restauration", "assiette", 15000, 9000, 80),
                     ("Beignets (sachet)", "SNK-04", "Restauration", "sachet", 2000, 1000, 150),
                     ("Yaourt sucré", "BOI-03", "Boissons", "pot", 3000, 1800, 90),
                     ("Jus de gingembre", "BOI-04", "Boissons", "bouteille", 5000, 2800, 80),
                     ("Soda 33 cl", "BOI-05", "Boissons", "canette", 6000, 4000, 120),
                     ("Cahier 100 pages", "FOU-03", "Fournitures", "pièce", 6000, 3500, 100),
                     ("Règle 30 cm", "FOU-04", "Fournitures", "pièce", 3000, 1500, 60),
                     ("Calculatrice scientifique", "FOU-05", "Fournitures", "pièce", 85000, 60000, 20),
                     ("Ardoise et craie", "FOU-06", "Fournitures", "lot", 8000, 4500, 40),
                     ("Trousse", "FOU-07", "Fournitures", "pièce", 12000, 7000, 40),
                     ("Clé USB 16 Go", "INF-01", "Informatique", "pièce", 60000, 42000, 25),
                     ("Ramette papier A4", "FOU-08", "Fournitures", "ramette", 45000, 32000, 30),
                     ("Tee-shirt de l'école", "UNI-01", "Uniformes", "pièce", 50000, 30000, 50),
                     ("Badge et cordon", "UNI-02", "Uniformes", "pièce", 15000, 8000, 80),
                     ("Brioche", "SNK-05", "Restauration", "pièce", 3000, 1700, 100),
                     ("Fataya à la viande", "SNK-06", "Restauration", "pièce", 4000, 2300, 100),
                     ("Lait caillé", "BOI-06", "Boissons", "pot", 4000, 2400, 60),
                     ("Dictionnaire de poche", "FOU-09", "Fournitures", "pièce", 70000, 50000, 15)]
        produits = []
        for nom, ref, cat, unite, pv, pa, stock in catalogue[:self.v["produits"]]:
            produit = Produit.objects.create(nom=nom, reference=ref, categorie=cat, unite=unite, prix_unitaire=D(pv),
                                             prix_achat=D(pa), seuil_alerte=D(max(5, stock // 8)))
            services.ajuster_stock(self.user, produit, MouvementStock.ENTREE, stock, "Stock initial de démonstration")
            produits.append(produit)
        comptes = [ClientCompte.objects.create(matricule=f"ELV-{self.suffixe}-{i:03d}", nom=n, telephone=t)
                   for i, (n, t) in enumerate((("Mariam Cissé", "+224 620 30 40 50"), ("Ibrahim Fofana", "+224 621 31 41 51"),
                                                ("Djénabou Sow", "+224 622 32 42 52"), ("Moussa Kanté", "+224 623 33 43 53")),
                                               start=1)]
        for i in range(len(comptes) + 1, self.v["comptes"] + 1):
            _, prenom, nom = self._personne()
            comptes.append(ClientCompte.objects.create(matricule=f"ELV-{self.suffixe}-{i:03d}",
                                                       nom=f"{prenom} {nom.title()}", telephone=self._telephone()))
        depots = [40000, 35000, 30000, 25000]
        par_ref = {p.reference: p for p in produits}
        achats_fixes = {0: [("SNK-01", 1), ("BOI-01", 2)], 1: [("SNK-02", 3), ("BOI-02", 2)],
                        2: [("FOU-01", 1), ("FOU-02", 2)], 3: [("SNK-01", 1), ("BOI-02", 1)]}
        nb_ventes = 0
        for i, compte in enumerate(comptes):
            depot = depots[i] if i < 4 else self.rng.choice([20000, 25000, 30000, 35000, 40000])
            services.creer_depot(self.user, compte.matricule, compte.telephone, depot, "Dépôt des parents")
            if i in achats_fixes:
                lignes = achats_fixes[i]
            else:
                lignes, total = [], 0
                for _ in range(self.rng.randint(1, 3)):  # achats dans la limite du dépôt
                    p = self.rng.choice([p for p in produits if p.prix_unitaire <= 15000])
                    if total + p.prix_unitaire <= depot:
                        lignes.append((p.reference, 1))
                        total += p.prix_unitaire
            if lignes:
                services.creer_retrait_ou_vente(self.user, compte.matricule, compte.telephone, "", Vente.COMPTE,
                                                [(par_ref[r].pk, q) for r, q in lignes])
                nb_ventes += len(lignes)
        services.creer_retrait_ou_vente(self.user, "", "", "Vente au comptoir", Vente.CAISSE,
                                        [(par_ref["SNK-01"].pk, 6), (par_ref["BOI-01"].pk, 8), (par_ref["SNK-02"].pk, 10)])
        for _ in range(self.v["ventes_caisse"] - 1):
            choix = self.rng.sample(produits, 2)
            lignes = [(p.pk, self.rng.randint(1, 3)) for p in choix
                      if Produit.objects.get(pk=p.pk).quantite_stock >= 3]
            if lignes:
                services.creer_retrait_ou_vente(self.user, "", "", "Vente au comptoir", Vente.CAISSE, lignes)
        self.resume.append(f"  Ventes : {len(produits)} produits en stock, {len(comptes)} comptes prépayés, "
                           f"dépôts, {nb_ventes} achats sur compte et {self.v['ventes_caisse']} ventes en caisse")

    # ------------------------------------------------------------------
    # Prêts
    # ------------------------------------------------------------------
    def _prets(self):
        from prets.models import Pret, Remboursement

        prets = [
            (Pret.objects.create(designation="Prêt d'équipement — Atelier de couture Kaba", montant_pret=D(15000000),
                                 montant_a_recouvrer=D(16500000), valeur_interet=D(1500000), date_debut=self.debut,
                                 date_fin=self.aujourdhui + timedelta(days=90)), 4000000, 3),
            (Pret.objects.create(designation="Avance de trésorerie — Boutique Diallo & Fils", montant_pret=D(5000000),
                                 montant_a_recouvrer=D(5400000), valeur_interet=D(400000), date_debut=self.debut,
                                 date_fin=self.aujourdhui - timedelta(days=15)), 2000000, 1),
            (Pret.objects.create(designation="Prêt scolaire — Famille Bangoura", montant_pret=D(2000000),
                                 montant_a_recouvrer=D(2100000), valeur_interet=D(100000), date_debut=self.debut,
                                 date_fin=self.aujourdhui - timedelta(days=5)), 700000, 3),
        ]
        objets = ["Fonds de roulement", "Achat de marchandises", "Équipement agricole", "Moto-taxi", "Matériel de soudure",
                  "Congélateur pour boutique", "Frais de scolarité", "Rénovation de boutique"]
        for n in range(self.v["prets"] - len(prets)):
            montant = D(self.rng.randrange(1000000, 20000001, 500000))
            interet = (montant * D(self.rng.choice(["0.05", "0.08", "0.10"]))).quantize(D(1000))
            debut = self.debut + timedelta(days=self.rng.randint(0, 120))
            duree = self.rng.choice([90, 180, 270, 360])
            _, prenom, nom = self._personne()
            pret = Pret.objects.create(designation=f"{objets[n % len(objets)]} — {prenom} {nom.title()}",
                                       montant_pret=montant, montant_a_recouvrer=montant + interet, valeur_interet=interet,
                                       date_debut=debut, date_fin=debut + timedelta(days=duree))
            echeances = max(1, duree // 30)
            mensualite = ((montant + interet) / echeances).quantize(D(1000))
            payees = min(echeances, max(0, (self.aujourdhui - debut).days // 30) - (1 if n % 4 == 0 else 0))
            prets.append((pret, mensualite, payees))
        for pret, mensualite, payees in prets:
            for k in range(payees):
                jour = min(pret.date_debut + timedelta(days=30 * (k + 1)), self.aujourdhui)
                reste = pret.montant_a_recouvrer - (pret.remboursements.aggregate(t=Sum("montant"))["t"] or ZERO)
                montant = min(D(mensualite), reste)
                if montant > 0:
                    Remboursement.objects.create(pret=pret, date=jour, montant=montant)
            pret.synchroniser_statut()
        self.resume.append(f"  Prêts : {len(prets)} prêts avec leurs remboursements (remboursés, en cours, échus)")

    # ------------------------------------------------------------------
    # Comptabilité (SYSCOHADA) : écritures générées par le moteur comptable
    # ------------------------------------------------------------------
    def _comptabilite(self, bulletins_par_mois, voyages):
        from comptabilite import moteur_comptable as mc
        from comptabilite.models import Facture, LigneFacture, Reglement, Tiers

        e, u = self.entreprise, self.user
        compte = lambda numero, intitule=None: mc.obtenir_compte(e, numero, intitule)  # noqa: E731
        banque, caisse = compte("banque"), compte("caisse")
        capital = D(5000000000 if self.v["mois"] > 3 else 1000000000)
        lib = "Apport en capital (démonstration)"
        mc.generer_ecriture(e, u, "OD", self.debut, lib, [
            (banque, lib, capital, ZERO), (compte("1013", "Capital souscrit, appelé, versé"), lib, ZERO, capital)])

        compteur = defaultdict(int)

        def numero(prefixe, annee, mois):
            compteur[prefixe] += 1
            return f"{prefixe}-{annee}{mois:02d}-{compteur[prefixe]:04d}"

        def facture(type_f, tiers, jour, lignes):
            f = Facture.objects.create(entreprise=e, numero=numero("FV" if type_f == "vente" else "FA", jour.year, jour.month),
                                       type_facture=type_f, tiers=tiers, date_facture=jour,
                                       date_echeance=jour + timedelta(days=30))
            for designation, quantite, prix, taux in lignes:
                LigneFacture.objects.create(facture=f, designation=designation[:200], quantite=D(quantite),
                                            prix_unitaire=D(prix), taux_tva=D(taux))
            f.refresh_from_db()
            f.statut = "validee"
            f.save()
            mc.comptabiliser_facture(f, u)
            return f

        def regler(f, montant, jour, mode):
            r = Reglement.objects.create(entreprise=e, numero=numero("RG", jour.year, jour.month), facture=f,
                                         date_reglement=jour, montant=montant, mode_paiement=mode)
            f.montant_paye = sum((x.montant for x in f.reglements.all()), ZERO)
            f.statut = "payee" if f.montant_paye >= f.montant_ttc else "validee"
            f.save(update_fields=["montant_paye", "statut"])
            mc.comptabiliser_reglement(r, u)

        # Tiers : clients du transport de carburant, fournisseurs habituels
        clients = {}
        for i, nom in enumerate(sorted({v.client.nom for v in voyages}), start=1):
            clients[nom] = Tiers.objects.create(entreprise=e, code=f"DEMO-C{i:02d}", raison_sociale=nom, type_tiers="client")
        fournisseurs = {cle: Tiers.objects.create(entreprise=e, code=f"DEMO-F{i:02d}", raison_sociale=nom, type_tiers="fournisseur")
                        for i, (cle, nom) in enumerate((("carburant", "Pétro-Distribution du Port"),
                                                        ("garage", "Garage central de Matoto"),
                                                        ("bureau", "Fournitures Bureau Plus"),
                                                        ("loyer", "SCI Immeuble Kaloum")), start=1)}
        voyages_par_mois = defaultdict(lambda: defaultdict(list))
        for v in voyages:
            voyages_par_mois[(v.date_livraison.year, v.date_livraison.month)][v.client.nom].append(v)

        nb_factures = nb_ecritures_paie = 0
        for n, (annee, mois) in enumerate(self.mois):
            fin = self._jour(annee, mois, 31)
            suivant = lambda jours: min(fin + timedelta(days=jours), self.aujourdhui)  # noqa: E731
            dernier_mois = n == len(self.mois) - 1
            # Ventes : une facture mensuelle par client, une ligne par voyage livré (TVA 18 %)
            for rang, (nom, liste) in enumerate(sorted(voyages_par_mois[(annee, mois)].items())):
                f = facture("vente", clients[nom], fin, [
                    (f"Transport {v.reference} — {v.quantite_livree:,.0f} L de {v.get_produit_display().lower()}"
                     .replace(",", " "), 1, v.montant_net, 18) for v in liste])
                nb_factures += 1
                if not dernier_mois:
                    regler(f, f.montant_ttc, suivant(12), "virement")
                elif rang % 2:
                    regler(f, (f.montant_ttc / 2).quantize(D(1)), suivant(5), "cheque")
            # Achats : carburant de la flotte, entretiens du garage, fournitures, loyer
            achats = [("carburant", [("Carburant de la flotte (bons du mois)", 1, self.pleins_par_mois[(annee, mois)], 0)]),
                      ("garage", [(f"Entretien véhicule — facture garage {k + 1}", 1, ht, 18)
                                  for k, ht in enumerate(self.entretiens[(annee, mois)])]),
                      ("bureau", [("Ramettes, cartouches et petites fournitures", 1, 1800000 + 100000 * (n % 5), 18)]),
                      ("loyer", [(f"Loyer du siège — {MOIS_FR[mois]} {annee}", 1, 12000000, 0)])]
            for cle, lignes in achats:
                lignes = [l for l in lignes if l[2] > 0]
                if not lignes:
                    continue
                f = facture("achat", fournisseurs[cle], self._jour(annee, mois, 15), lignes)
                nb_factures += 1
                if not (dernier_mois and cle == "garage"):
                    regler(f, f.montant_ttc, suivant(5), "especes" if cle == "bureau" else "virement")
            # Paie : constatation des salaires et des charges, paiement des nets, versements à la CNSS et à l'État
            bulletins = bulletins_par_mois.get((annee, mois), [])
            if bulletins:
                somme = lambda champ: sum((getattr(b, champ) or ZERO for b in bulletins), ZERO)  # noqa: E731
                brut, net, rts = somme("salaire_brut"), somme("net_a_payer"), somme("irg")
                cnss_s, cnss_p = somme("cnss_employe"), somme("cnss_employeur")
                taxes = somme("versement_forfaitaire") + somme("taxe_apprentissage") + somme("contribution_onfpp")
                autres = brut - cnss_s - rts - net
                libelle = f"Salaires {MOIS_FR[mois]} {annee}"
                lignes = [(compte("6611", "Appointements et salaires"), "Salaires bruts", brut, ZERO),
                          (compte("6641", "Charges sociales patronales (CNSS)"), "CNSS employeur", cnss_p, ZERO),
                          (compte("6413", "Taxes sur appointements et salaires (VF, TA, ONFPP)"), "VF, TA, ONFPP", taxes, ZERO),
                          (compte("4311", "Sécurité sociale (CNSS)"), "CNSS salariale et patronale", ZERO, cnss_s + cnss_p),
                          (compte("4472", "État, impôt retenu à la source (RTS)"), "RTS retenue", ZERO, rts),
                          (compte("4478", "État, taxes sur salaires à payer"), "VF, TA, ONFPP à payer", ZERO, taxes),
                          (compte("personnel"), "Salaires nets à payer", ZERO, net)]
                if autres:
                    lignes.append((compte("4228", "Autres retenues sur salaires"), "Autres retenues", ZERO, autres))
                mc.generer_ecriture(e, u, "SA", fin, libelle, lignes)
                lib = f"Paiement des salaires nets {MOIS_FR[mois]} {annee}"
                mc.generer_ecriture(e, u, "BQ", fin, lib, [(compte("personnel"), lib, net, ZERO), (banque, lib, ZERO, net)])
                nb_ecritures_paie += 2
                if fin + timedelta(days=15) <= self.aujourdhui:
                    lib = f"Versement CNSS, RTS et taxes sur salaires {MOIS_FR[mois]} {annee}"
                    mc.generer_ecriture(e, u, "BQ", fin + timedelta(days=15), lib, [
                        (compte("4311"), lib, cnss_s + cnss_p, ZERO), (compte("4472"), lib, rts, ZERO),
                        (compte("4478"), lib, taxes, ZERO), (banque, lib, ZERO, cnss_s + cnss_p + rts + taxes)])
                    nb_ecritures_paie += 1
            # Caisse : alimentation et petites dépenses
            jour = self._jour(annee, mois, 3)
            lib = f"Alimentation de la caisse {MOIS_FR[mois]} {annee}"
            mc.generer_ecriture(e, u, "CA", jour, lib, [(caisse, lib, D(5000000), ZERO), (banque, lib, ZERO, D(5000000))])
            for k, (objet, montant) in enumerate((("Carburant groupe électrogène", 650000), ("Frais de mission Kindia", 400000),
                                                  ("Achat d'eau et de collations", 250000))):
                mc.operation_simple(e, u, "sortie_caisse", self._jour(annee, mois, 8 + 7 * k),
                                    f"{objet} — {MOIS_FR[mois]} {annee}", montant, mode_paiement="especes")
        capital_txt = f"{capital:,.0f}".replace(",", " ")
        self.resume.append(f"  Comptabilité : capital de {capital_txt} GNF, {len(clients)} clients et "
                           f"{len(fournisseurs)} fournisseurs, {nb_factures} factures (TVA 18 %) avec leurs règlements, "
                           f"{nb_ecritures_paie} écritures de paie, opérations de caisse")
