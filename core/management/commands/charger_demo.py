"""Données de démonstration réalistes (fictives) pour présenter AdminFastlane.

    python manage.py charger_demo --utilisateur Myschool
    python manage.py charger_demo --utilisateur Myschool --supprimer

Les données sont rattachées à l'entreprise de l'utilisateur indiqué : structure,
employés et bulletins de paie des derniers mois, flotte, transport de carburant,
projets, agence de voyage, ventes (comptes prépayés) et prêts. Les noms de
personnes et de sociétés sont inventés. Chaque objet créé, y compris par les
services et signaux de l'application, est noté dans core.DonneeDemo : l'option
--supprimer retire toute la démonstration sans toucher aux autres données.
"""
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.signals import post_save
from django.utils import timezone

from core.models import DonneeDemo, Etablissement, Poste, Service, Societe, Utilisateur
from core.tenancy import pour_entreprise

D = Decimal


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

# Employés fictifs : (civilité, nom, prénoms, sexe, naissance, contrat, embauche, situation, enfants,
#                     service, poste, salaire de base, transport, logement, prime, paiement)
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
          ("MAG", "Magasinier", "LOG"), ("STG", "Stagiaire commerciale", "COM")]


class Command(BaseCommand):
    help = "Charge (ou supprime) des données de démonstration fictives dans l'entreprise d'un utilisateur."

    def add_arguments(self, parser):
        parser.add_argument("--utilisateur", required=True, help="Identifiant de connexion d'un utilisateur de l'entreprise.")
        parser.add_argument("--mois", type=int, default=3, help="Nombre de mois de paie et d'activité (défaut : 3).")
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
        if not 1 <= options["mois"] <= 12:
            raise CommandError("--mois doit être compris entre 1 et 12.")

        self.user, self.entreprise = user, entreprise
        self.suffixe = entreprise.pk.hex[:4].upper()
        self.mois = _mois_precedents(options["mois"])
        self.aujourdhui = timezone.localdate()
        self.resume = []

        with transaction.atomic(), pour_entreprise(entreprise):
            with self._enregistrer() as crees:
                employes = self._rh()
                self._paie(employes)
                vehicules, chauffeurs = self._flotte()
                self._carburant(vehicules)
                self._projets()
                self._agence()
                self._ventes()
                self._prets()
            DonneeDemo.objects.bulk_create([
                DonneeDemo(entreprise=entreprise, content_type=ContentType.objects.get_for_model(modele),
                           object_id=str(pk))
                for modele, pk in crees
            ])

        self.stdout.write(self.style.SUCCESS(
            f"Démonstration chargée pour « {entreprise.nom_entreprise} » ({len(crees)} enregistrements)."))
        for ligne in self.resume:
            self.stdout.write(ligne)
        self.stdout.write("Pour tout retirer : python manage.py charger_demo --utilisateur "
                          f"{user.username} --supprimer")

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
        debut_paie = date(*self.mois[0], 1)
        employes = []
        for i, (civ, nom, prenoms, sexe, naissance, contrat, embauche, situation, enfants, service, poste,
                base, transport, logement, prime, paiement) in enumerate(EMPLOYES, start=1):
            embauche = embauche or debut_paie  # stagiaire : stage commencé avec la période de démonstration
            initiales = f"{prenoms[0]}.{nom.lower()}"
            employe = Employe.objects.create(
                entreprise=self.entreprise, matricule=f"D{self.suffixe}-{i:03d}", civilite=civ, nom=nom,
                prenoms=prenoms, sexe=sexe, date_naissance=naissance, lieu_naissance="Conakry",
                type_contrat=contrat, date_embauche=embauche, date_debut_contrat=embauche,
                situation_matrimoniale=situation, nombre_enfants=enfants, etablissement=etablissement,
                service=services[service], poste=postes[poste], statut_employe="actif",
                telephone_principal=f"+224 62{i} {10 + i * 7:02d} {20 + i * 3:02d} {30 + i:02d}",
                email_professionnel=f"{initiales.lower()}@exemple-demo.gn", mode_paiement=paiement,
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

        bulletins = []
        for annee, mois in self.mois:
            periode, cree = PeriodePaie.objects.get_or_create(
                entreprise=self.entreprise, annee=annee, mois=mois,
                defaults={"libelle": f"{MOIS_FR[mois]} {annee}", "date_debut": date(annee, mois, 1),
                          "date_fin": _fin_de_mois(annee, mois), "statut_periode": "ouverte"})
            if not cree and periode.statut_periode != "ouverte":
                self.resume.append(f"  Paie {MOIS_FR[mois]} {annee} : période déjà {periode.statut_periode}, ignorée")
                continue
            for employe in employes:
                bulletins.append(MoteurCalculPaie(employe, periode).generer_bulletin(self.user))
        if bulletins:
            dernier = [b for b in bulletins if (b.annee_paie, b.mois_paie) == self.mois[-1]]
            self.resume.append(f"  Paie : {len(bulletins)} bulletins sur {len(self.mois)} mois ; "
                               f"{MOIS_FR[self.mois[-1][1]]} {self.mois[-1][0]} :")
            for b in dernier:
                self.resume.append(
                    f"    {b.employe.nom:<10} brut {b.salaire_brut:>12,.0f}  CNSS {b.cnss_employe:>9,.0f}  "
                    f"RTS {b.irg:>9,.0f}  net {b.net_a_payer:>12,.0f}".replace(",", " "))

    # ------------------------------------------------------------------
    # Flotte
    # ------------------------------------------------------------------
    def _flotte(self):
        from flotte.models import Chauffeur, Entretien, Marque, PleinCarburant, Vehicule

        chauffeurs = [Chauffeur.objects.create(nom_prenoms=n, telephone=t) for n, t in (
            ("Abdoulaye Touré", "+224 621 45 12 78"), ("Mamadou Saliou Diallo", "+224 622 33 90 14"),
            ("Ousmane Camara", "+224 624 08 51 66"), ("Lansana Kaba", "+224 625 70 22 39"))]
        marques = [Marque.objects.get_or_create(nom=n)[0] for n in ("Renault Trucks", "Mercedes-Benz", "Volvo")]
        vehicules = []
        for i, (immat, marque, type_v) in enumerate((
                ("RC-4581-AB", 0, "Tracteur routier"), ("RC-7720-AC", 1, "Tracteur routier"),
                ("RC-1934-AD", 2, "Tracteur routier"), ("RC-3307-AE", 1, "Pick-up de liaison"))):
            vehicules.append(Vehicule.objects.create(
                immatriculation=immat, marque=marques[marque], type_vehicule=type_v,
                chauffeur_actuel=chauffeurs[i], actif=True))
        pleins = entretiens = 0
        for n, (annee, mois) in enumerate(self.mois):
            for i, vehicule in enumerate(vehicules):
                for jour in (6, 20):
                    PleinCarburant.objects.create(
                        date=date(annee, mois, jour), vehicule=vehicule, chauffeur=vehicule.chauffeur_actuel,
                        litres=D(80 if i == 3 else 350), prix_litre=D(12000), kilometrage=48000 + 3200 * n + i * 9000 + jour * 40,
                        n_bon=f"BC-{annee}{mois:02d}{jour:02d}-{i + 1}")
                    pleins += 1
            vehicule = vehicules[n % len(vehicules)]
            Entretien.objects.create(
                date=date(annee, mois, 14), vehicule=vehicule, chauffeur=vehicule.chauffeur_actuel,
                n_facture=f"FG-{annee}{mois:02d}-{n + 1:02d}", garage="Garage central de Matoto",
                nature_operations="Vidange moteur, filtres à huile et à gasoil, contrôle des freins",
                montant_ttc=D(2750000 + 350000 * n))
            entretiens += 1
        self.resume.append(f"  Flotte : {len(vehicules)} véhicules, {len(chauffeurs)} chauffeurs, "
                           f"{pleins} pleins, {entretiens} entretiens")
        return vehicules, chauffeurs

    # ------------------------------------------------------------------
    # Transport de carburant
    # ------------------------------------------------------------------
    def _carburant(self, vehicules):
        from carburant.models import Citerne, Client, FraisVoyage, Paiement, Voyage

        clients = [
            Client.objects.create(nom="Kaloum Énergie SARL", contact="Service approvisionnement",
                                  telephone="+224 628 10 20 30", tarif_litre=D(150), tolerance_pct=D("0.5")),
            Client.objects.create(nom="Bauxite Rive Ouest SA", contact="Responsable carburant",
                                  telephone="+224 629 44 55 66", tarif_litre=D(220), tolerance_pct=D("0.3")),
            Client.objects.create(nom="Réseau Stations du Fouta", contact="Gérant réseau",
                                  telephone="+224 620 77 88 99", tarif_litre=D(180), tolerance_pct=D("0.5")),
        ]
        citernes = [
            Citerne.objects.create(immatriculation="CIT-01", vehicule=vehicules[0], capacite=D(40000), nb_compartiments=4,
                                   numero_barremage="BAR-2025-118", expiration_barremage=self.aujourdhui + timedelta(days=210)),
            Citerne.objects.create(immatriculation="CIT-02", vehicule=vehicules[1], capacite=D(36000), nb_compartiments=3,
                                   numero_barremage="BAR-2025-131", expiration_barremage=self.aujourdhui + timedelta(days=20)),
            Citerne.objects.create(immatriculation="CIT-03", vehicule=vehicules[2], capacite=D(33000), nb_compartiments=3,
                                   numero_barremage="BAR-2026-007", expiration_barremage=self.aujourdhui + timedelta(days=320)),
        ]
        trajets = [("Dépôt pétrolier de Conakry", "Station Kaloum Énergie — Dixinn", 0, "gasoil"),
                   ("Dépôt pétrolier de Conakry", "Site minier — Boffa", 1, "gasoil"),
                   ("Dépôt pétrolier de Conakry", "Station du Fouta — Labé", 2, "essence"),
                   ("Dépôt pétrolier de Conakry", "Station du Fouta — Mamou", 2, "gasoil")]
        ecarts = [D(40), D(130), D(260), D(90)]  # litres manquants à la livraison
        livres = 0
        for n, (annee, mois) in enumerate(self.mois):
            for k, (depart, arrivee, ic, produit) in enumerate(trajets):
                citerne = citernes[k % 3]
                charge = citerne.capacite - D(500 * k)
                jour = 3 + k * 6
                v = Voyage.objects.create(
                    client=clients[ic], citerne=citerne, produit=produit, lieu_chargement=depart, destination=arrivee,
                    date_prevue=date(annee, mois, jour), date_chargement=date(annee, mois, jour),
                    bon_chargement=f"BCH-{annee}{mois:02d}-{k + 1:02d}", quantite_chargee=charge,
                    date_livraison=date(annee, mois, jour + 1), bon_livraison=f"BL-{annee}{mois:02d}-{k + 1:02d}",
                    quantite_livree=charge - ecarts[(k + n) % 4], tarif_litre=clients[ic].tarif_litre,
                    tolerance_pct=clients[ic].tolerance_pct, prix_produit=D(12000), statut=Voyage.LIVRE,
                    agent=self._agent())
                for type_frais, montant in (("gasoil_camion", 1200000 + 150000 * (ic == 1)), ("mission", 300000),
                                            ("peage", 100000)):
                    FraisVoyage.objects.create(voyage=v, type=type_frais, date=v.date_chargement, montant=D(montant))
                livres += 1
        # Activité du mois en cours : deux citernes en route, un voyage planifié, un annulé
        debut = self.aujourdhui.replace(day=1)
        for k, ic in ((0, 0), (1, 1)):
            Voyage.objects.create(
                client=clients[ic], citerne=citernes[k], produit="gasoil", lieu_chargement=trajets[ic][0],
                destination=trajets[ic][1], date_prevue=debut, date_chargement=debut, bon_chargement=f"BCH-EN-{k + 1}",
                quantite_chargee=citernes[k].capacite, tarif_litre=clients[ic].tarif_litre,
                tolerance_pct=clients[ic].tolerance_pct, prix_produit=D(12000), statut=Voyage.EN_ROUTE, agent=self._agent())
        Voyage.objects.create(
            client=clients[2], citerne=citernes[2], produit="essence", lieu_chargement=trajets[2][0],
            destination=trajets[2][1], date_prevue=self.aujourdhui + timedelta(days=2), tarif_litre=clients[2].tarif_litre,
            tolerance_pct=clients[2].tolerance_pct, prix_produit=D(12000), agent=self._agent())
        Voyage.objects.create(
            client=clients[0], citerne=citernes[2], produit="gasoil", lieu_chargement=trajets[0][0],
            destination=trajets[0][1], date_prevue=debut, statut=Voyage.ANNULE, tarif_litre=clients[0].tarif_litre,
            tolerance_pct=clients[0].tolerance_pct, note="Commande annulée par le client", agent=self._agent())
        # Paiements : le client principal a tout réglé sauf le dernier mois, les autres partiellement
        for client, part in ((clients[0], D("0.70")), (clients[1], D("0.50")), (clients[2], D("0.85"))):
            facture = sum((v.montant_net for v in client.voyages.filter(statut=Voyage.LIVRE)), D(0))
            Paiement.objects.create(client=client, date=self.aujourdhui - timedelta(days=10),
                                    montant=(facture * part).quantize(D(1000)), mode="virement",
                                    reference=f"VIR-{client.pk:04d}", agent=self._agent())
        self.resume.append(f"  Transport de carburant : {len(clients)} clients, {len(citernes)} citernes, "
                           f"{livres} voyages livrés, 2 en route, 1 planifié, 1 annulé")

    # ------------------------------------------------------------------
    # Gestion de projet
    # ------------------------------------------------------------------
    def _projets(self):
        from projets.models import Client, Membre, Mouvement, Projet, Tache

        debut = date(*self.mois[0], 1)
        c1 = Client.objects.create(nom="Coopérative des Transporteurs de Kindia", contact="M. Fofana",
                                   telephone="+224 627 11 22 33")
        c2 = Client.objects.create(nom="Groupe scolaire Les Palmiers", contact="Mme Sow",
                                   telephone="+224 626 44 55 66")
        projets = [
            (Projet.objects.create(nom="Construction d'un entrepôt logistique à Kagbelen", client=c1,
                                   responsable="Mohamed Lamine Sylla", budget=D(450000000), date_debut=debut,
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
                                   budget=D(45000000), date_debut=debut, date_fin_prevue=self.aujourdhui - timedelta(days=6),
                                   statut=Projet.EN_COURS, lieu="Ratoma", ville="Conakry", cree_par=self._agent()),
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
        for projet, taches, mouvements in projets:
            for ordre, (titre, progression, statut, echeance) in enumerate(taches, start=1):
                Tache.objects.create(projet=projet, titre=titre, responsable=projet.responsable, ordre=ordre,
                                     date_debut=projet.date_debut, statut=statut, progression=progression,
                                     date_fin_prevue=self.aujourdhui + timedelta(days=echeance),
                                     priorite=Tache.HAUTE if statut == Tache.BLOQUEE else Tache.MOYENNE)
            for type_m, categorie, montant, libelle, jours in mouvements:
                Mouvement.objects.create(projet=projet, type=type_m, categorie=categorie or "", montant=D(montant),
                                         libelle=libelle, date=self.aujourdhui + timedelta(days=jours),
                                         mode="virement", saisi_par=self._agent())
        for nom, role in (("Mohamed Lamine Sylla", "Chef de chantier"), ("Abdoulaye Touré", "Conducteur d'engins"),
                          ("Ousmane Camara", "Chef d'équipe maçons")):
            Membre.objects.create(projet=projets[0][0], nom=nom, role=role, date_debut=debut)
        self.resume.append("  Projets : 3 projets (dont 1 en retard et 1 au budget dépassé), 10 tâches, 10 mouvements")

    # ------------------------------------------------------------------
    # Agence de voyage
    # ------------------------------------------------------------------
    def _agence(self):
        from agence.models import Client, Dossier, Fournisseur, PaiementClient, PaiementFournisseur, Prestation, Voyageur

        f_air = Fournisseur.objects.create(nom="Air Côte Ouest", type=Fournisseur.COMPAGNIE, telephone="+224 620 10 10 10")
        f_hotel = Fournisseur.objects.create(nom="Hôtel Les Palmiers — Dakar", type=Fournisseur.HOTEL)
        f_visa = Fournisseur.objects.create(nom="Service consulaire (visas)", type=Fournisseur.VISA)
        f_assur = Fournisseur.objects.create(nom="Assurance Voyage Plus", type=Fournisseur.ASSURANCE)
        clients = [Client.objects.create(nom=n, telephone=t, nationalite="Guinéenne", passeport_numero=p,
                                         passeport_expiration=self.aujourdhui + timedelta(days=e))
                   for n, t, p, e in (("Alpha Oumar Diallo", "+224 628 51 62 73", "R0451287", 900),
                                      ("Kadiatou Barry", "+224 629 84 95 06", "R0773019", 120),
                                      ("Famille Kaba", "+224 620 17 28 39", "R0928364", 1500),
                                      ("Thierno Sow", "+224 621 40 51 62", "R0112045", 700))]
        dossiers = [
            (clients[0], "Paris", "Affaires", 18, 9, Dossier.TERMINE,
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
        for client, destination, objet, dans, duree, statut, prestations, part in dossiers:
            depart = self.aujourdhui + timedelta(days=dans if statut != Dossier.TERMINE else -dans)
            dossier = Dossier.objects.create(
                client=client, destination=destination, objet=objet, date_depart=depart,
                date_retour=depart + timedelta(days=duree) if duree else None,
                nb_voyageurs=prestations[0][3], statut=statut, agent=self._agent())
            for type_p, description, fournisseur, qte, achat, vente in prestations:
                p = Prestation.objects.create(
                    dossier=dossier, type=type_p, description=description, fournisseur=fournisseur,
                    quantite=D(qte), prix_achat=D(achat), prix_vente=D(vente), date_debut=depart,
                    statut=Prestation.CONFIRMEE if statut != Dossier.DEVIS else Prestation.ATTENTE)
                if statut == Dossier.TERMINE:
                    PaiementFournisseur.objects.create(prestation=p, montant=p.total_achat, mode="virement")
            Voyageur.objects.create(dossier=dossier, nom=client.nom, nationalite="Guinéenne",
                                    passeport_numero=client.passeport_numero,
                                    passeport_expiration=client.passeport_expiration)
            total = sum((D(q) * D(v) for _, _, _, q, _, v in prestations), D(0))
            if part:
                PaiementClient.objects.create(dossier=dossier, montant=(total * D(str(part))).quantize(D(1000)),
                                              mode="especes" if part < 1 else "virement", agent=self._agent())
        self.resume.append(f"  Agence de voyage : {len(clients)} clients, 4 fournisseurs, {len(dossiers)} dossiers")

    # ------------------------------------------------------------------
    # Ventes (comptes prépayés et caisse)
    # ------------------------------------------------------------------
    def _ventes(self):
        from ventes import services
        from ventes.models import ClientCompte, MouvementStock, Produit, Vente

        produits = [Produit.objects.create(nom=n, reference=r, categorie=c, unite=u, prix_unitaire=D(pv),
                                           prix_achat=D(pa), seuil_alerte=D(s))
                    for n, r, c, u, pv, pa, s in (
                        ("Sandwich poulet", "SNK-01", "Restauration", "pièce", 10000, 6500, 10),
                        ("Pain au chocolat", "SNK-02", "Restauration", "pièce", 3000, 1800, 20),
                        ("Jus de bissap 33 cl", "BOI-01", "Boissons", "bouteille", 5000, 3000, 24),
                        ("Eau minérale 50 cl", "BOI-02", "Boissons", "bouteille", 2000, 1100, 24),
                        ("Cahier 200 pages", "FOU-01", "Fournitures", "pièce", 10000, 6000, 15),
                        ("Stylo à bille (lot de 4)", "FOU-02", "Fournitures", "lot", 4000, 2200, 15))]
        for produit, quantite in zip(produits, (60, 120, 96, 144, 80, 60)):
            services.ajuster_stock(self.user, produit, MouvementStock.ENTREE, quantite, "Stock initial de démonstration")
        comptes = [ClientCompte.objects.create(matricule=f"ELV-{self.suffixe}-{i:03d}", nom=n, telephone=t)
                   for i, (n, t) in enumerate((("Mariam Cissé", "+224 620 30 40 50"), ("Ibrahim Fofana", "+224 621 31 41 51"),
                                                ("Djénabou Sow", "+224 622 32 42 52"), ("Moussa Kanté", "+224 623 33 43 53")),
                                               start=1)]
        for compte, depot in zip(comptes, (40000, 35000, 30000, 25000)):
            services.creer_depot(self.user, compte.matricule, compte.telephone, depot, "Dépôt des parents")
        par_id = {p.reference: p.pk for p in produits}
        achats = [(comptes[0], [("SNK-01", 1), ("BOI-01", 2)]), (comptes[1], [("SNK-02", 3), ("BOI-02", 2)]),
                  (comptes[2], [("FOU-01", 1), ("FOU-02", 2)]), (comptes[3], [("SNK-01", 1), ("BOI-02", 1)])]
        for compte, lignes in achats:
            services.creer_retrait_ou_vente(self.user, compte.matricule, compte.telephone, "", Vente.COMPTE,
                                            [(par_id[r], q) for r, q in lignes])
        services.creer_retrait_ou_vente(self.user, "", "", "Vente au comptoir", Vente.CAISSE,
                                        [(par_id["SNK-01"], 6), (par_id["BOI-01"], 8), (par_id["SNK-02"], 10)])
        self.resume.append(f"  Ventes : {len(produits)} produits en stock, {len(comptes)} comptes prépayés, "
                           "dépôts, achats sur compte et ventes en caisse")

    # ------------------------------------------------------------------
    # Prêts
    # ------------------------------------------------------------------
    def _prets(self):
        from prets.models import Pret, Remboursement

        debut = date(*self.mois[0], 1)
        p1 = Pret.objects.create(designation="Prêt d'équipement — Atelier de couture Kaba", montant_pret=D(15000000),
                                 montant_a_recouvrer=D(16500000), valeur_interet=D(1500000), date_debut=debut,
                                 date_fin=self.aujourdhui + timedelta(days=90))
        p2 = Pret.objects.create(designation="Avance de trésorerie — Boutique Diallo & Fils", montant_pret=D(5000000),
                                 montant_a_recouvrer=D(5400000), valeur_interet=D(400000), date_debut=debut,
                                 date_fin=self.aujourdhui - timedelta(days=15))
        p3 = Pret.objects.create(designation="Prêt scolaire — Famille Bangoura", montant_pret=D(2000000),
                                 montant_a_recouvrer=D(2100000), valeur_interet=D(100000), date_debut=debut,
                                 date_fin=self.aujourdhui - timedelta(days=5))
        for n, (annee, mois) in enumerate(self.mois):
            Remboursement.objects.create(pret=p1, date=date(annee, mois, 28), montant=D(4000000))
            Remboursement.objects.create(pret=p3, date=date(annee, mois, 28), montant=D(700000))
        Remboursement.objects.create(pret=p2, date=date(*self.mois[0], 28), montant=D(2000000))
        for pret in (p1, p2, p3):
            pret.synchroniser_statut()
        self.resume.append("  Prêts : 3 prêts (1 remboursé, 1 en cours, 1 échu non soldé)")

    def _agent(self):
        return (self.user.get_full_name() or self.user.get_username()).strip()
