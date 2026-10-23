import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Entreprise, ProfilUtilisateur
from core.tenancy import pour_entreprise
from flotte.models import Chauffeur, Vehicule

from .forms import ChargementForm, ClientForm, LivraisonForm, VoyageForm
from .models import Citerne, Client, FraisVoyage, Paiement, Voyage

User = get_user_model()
D = Decimal


def _entreprise(slug):
    return Entreprise.objects.create(
        nom_entreprise=f"Entreprise {slug}", slug=slug, email=f"{slug}@example.test", type_module="all")


def _user(entreprise, nom, niveau=None, admin=False):
    profil = None
    if niveau:
        profil, _ = ProfilUtilisateur.objects.get_or_create(
            nom_profil=f"niveau{niveau}", defaults={"niveau_acces": niveau})
    return User.objects.create_user(
        username=nom, email=f"{nom}@example.test", password="Mdp-test-1234", entreprise=entreprise,
        est_admin_entreprise=admin, actif=True, profil=profil)


class CarburantBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent_a, cls.ent_b = _entreprise("alpha"), _entreprise("bravo")
        cls.admin_a = _user(cls.ent_a, "admin_a", admin=True)
        cls.saisie_a = _user(cls.ent_a, "saisie_a", niveau=2)
        cls.lecteur_a = _user(cls.ent_a, "lecteur_a", niveau=1)
        cls.admin_b = _user(cls.ent_b, "admin_b", admin=True)
        aujourdhui = timezone.localdate()
        with pour_entreprise(cls.ent_a):
            cls.chauffeur = Chauffeur.objects.create(nom_prenoms="Bah Alpha", telephone="621000000")
            cls.tracteur = Vehicule.objects.create(immatriculation="RC-1234-A", chauffeur_actuel=cls.chauffeur)
            cls.citerne = Citerne.objects.create(
                immatriculation="CIT-01", vehicule=cls.tracteur, capacite=D("40000"), nb_compartiments=4,
                expiration_barremage=aujourdhui + datetime.timedelta(days=200))
            cls.client_a = Client.objects.create(nom="Star Oil Guinée", tarif_litre=D("150"), tolerance_pct=D("0.5"))
            # Voyage livré : 40 000 L chargés, 39 700 livrés -> écart 300 L, tolérance 200 L, manquant 100 L
            cls.livre = Voyage.objects.create(
                client=cls.client_a, citerne=cls.citerne, produit="gasoil", lieu_chargement="Dépôt SGP Conakry",
                destination="Station Kindia", tarif_litre=D("150"), tolerance_pct=D("0.5"), prix_produit=D("12000"),
                date_chargement=aujourdhui, quantite_chargee=D("40000"), bon_chargement="BC-1",
                date_livraison=aujourdhui, quantite_livree=D("39700"), bon_livraison="BL-1", statut=Voyage.LIVRE)
            FraisVoyage.objects.create(voyage=cls.livre, type="gasoil_camion", montant=D("1500000"))
            FraisVoyage.objects.create(voyage=cls.livre, type="mission", montant=D("300000"))
            cls.planifie = Voyage.objects.create(
                client=cls.client_a, citerne=cls.citerne, produit="essence", lieu_chargement="Dépôt SGP Conakry",
                destination="Mine de Boké", tarif_litre=D("200"), tolerance_pct=D("0.5"))
        with pour_entreprise(cls.ent_b):
            cls.client_b = Client.objects.create(nom="Client secret B")
            cls.citerne_b = Citerne.objects.create(immatriculation="CIT-B", capacite=D("30000"))
            cls.voyage_b = Voyage.objects.create(
                client=cls.client_b, citerne=cls.citerne_b, lieu_chargement="Kamsar", destination="Boffa")


class ModeleTests(CarburantBase):
    def test_reference_incrementale_par_entreprise(self):
        annee = timezone.localdate().year
        self.assertEqual(self.livre.reference, f"TC-{annee}-0001")
        self.assertEqual(self.planifie.reference, f"TC-{annee}-0002")
        self.assertEqual(self.voyage_b.reference, f"TC-{annee}-0001")

    def test_tracteur_et_chauffeur_repris_de_la_flotte(self):
        self.assertEqual(self.planifie.vehicule_id, self.tracteur.pk)
        self.assertEqual(self.planifie.chauffeur_id, self.chauffeur.pk)

    def test_manquant_tolerance_et_penalite(self):
        v = Voyage.objects.prefetch_related("frais").get(pk=self.livre.pk)
        self.assertEqual(v.ecart, D("300"))
        self.assertEqual(v.taux_ecart, D("0.75"))
        self.assertEqual(v.tolerance_litres, D("200"))
        self.assertEqual(v.manquant_imputable, D("100"))
        self.assertEqual(v.penalite, D("1200000"))

    def test_facturation_et_marge(self):
        v = Voyage.objects.prefetch_related("frais").get(pk=self.livre.pk)
        self.assertEqual(v.montant_transport, D("5955000"))  # 39 700 L livrés x 150
        self.assertEqual(v.montant_net, D("4755000"))
        self.assertEqual(v.total_frais, D("1800000"))
        self.assertEqual(v.marge, D("2955000"))
        v.base_facturation = Voyage.CHARGEE
        self.assertEqual(v.montant_transport, D("6000000"))
        v.base_facturation, v.forfait = Voyage.FORFAIT, D("5000000")
        self.assertEqual(v.montant_transport, D("5000000"))

    def test_gain_de_temperature_sans_penalite(self):
        v = Voyage(quantite_chargee=D("10000"), quantite_livree=D("10020"), tolerance_pct=D("0.5"),
                   prix_produit=D("12000"))
        self.assertEqual(v.ecart, D("-20"))
        self.assertEqual(v.manquant_imputable, 0)
        self.assertEqual(v.penalite, 0)

    def test_etat_barremage(self):
        aujourdhui = timezone.localdate()
        self.assertEqual(Citerne(capacite=1).etat_barremage, Citerne.INCONNU)
        self.assertEqual(Citerne(capacite=1, expiration_barremage=aujourdhui - datetime.timedelta(days=1)).etat_barremage,
                         Citerne.EXPIRE)
        self.assertEqual(Citerne(capacite=1, expiration_barremage=aujourdhui + datetime.timedelta(days=10)).etat_barremage,
                         Citerne.BIENTOT)
        self.assertEqual(self.citerne.etat_barremage, Citerne.OK)


class FormulairesTests(CarburantBase):
    def _voyage(self, **donnees):
        base = {"client": self.client_a.pk, "citerne": self.citerne.pk, "produit": "gasoil",
                "lieu_chargement": "Dépôt", "destination": "Labé", "date_prevue": "2026-10-20",
                "base_facturation": "livree", "tarif_litre": "", "tolerance_pct": "", "forfait": "", "prix_produit": ""}
        base.update(donnees)
        return VoyageForm(base)

    def test_tarif_et_tolerance_du_client_par_defaut(self):
        with pour_entreprise(self.ent_a):
            form = self._voyage()
            self.assertTrue(form.is_valid(), form.errors)
            voyage = form.save()
        self.assertEqual((voyage.tarif_litre, voyage.tolerance_pct), (D("150"), D("0.5")))

    def test_forfait_obligatoire(self):
        with pour_entreprise(self.ent_a):
            form = self._voyage(base_facturation="forfait")
            self.assertFalse(form.is_valid())
            self.assertIn("forfait", form.errors)

    def test_chargement_au_dela_de_la_capacite_refuse(self):
        with pour_entreprise(self.ent_a):
            form = ChargementForm({"date_chargement": "2026-10-20", "bon_chargement": "BC", "quantite_chargee": "45000"},
                                  instance=Voyage.objects.get(pk=self.planifie.pk))
            self.assertFalse(form.is_valid())
            self.assertIn("quantite_chargee", form.errors)

    def test_citerne_deja_en_route_refusee(self):
        with pour_entreprise(self.ent_a):
            Voyage.objects.filter(pk=self.livre.pk).update(statut=Voyage.EN_ROUTE)
            form = ChargementForm({"date_chargement": "2026-10-20", "bon_chargement": "BC", "quantite_chargee": "30000"},
                                  instance=Voyage.objects.get(pk=self.planifie.pk))
            self.assertFalse(form.is_valid())
            self.assertIn("déjà en route", str(form.non_field_errors()))

    def test_barremage_expire_bloque_le_chargement(self):
        with pour_entreprise(self.ent_a):
            Citerne.objects.filter(pk=self.citerne.pk).update(
                expiration_barremage=timezone.localdate() - datetime.timedelta(days=1))
            form = ChargementForm({"date_chargement": "2026-10-20", "bon_chargement": "BC", "quantite_chargee": "30000"},
                                  instance=Voyage.objects.get(pk=self.planifie.pk))
            self.assertFalse(form.is_valid())

    def test_livraison_avant_chargement_refusee(self):
        voyage = Voyage(date_chargement=datetime.date(2026, 10, 20))
        form = LivraisonForm({"date_livraison": "2026-10-19", "bon_livraison": "BL", "quantite_livree": "100"},
                             instance=voyage)
        self.assertFalse(form.is_valid())
        self.assertIn("date_livraison", form.errors)

    def test_tolerance_superieure_a_100_refusee(self):
        form = ClientForm({"nom": "X", "tarif_litre": "1", "tolerance_pct": "150"})
        self.assertFalse(form.is_valid())


class VuesTests(CarburantBase):
    def test_pages_accessibles(self):
        with pour_entreprise(self.ent_a):
            paiement = Paiement.objects.create(client=self.client_a, montant=D("1000000"))
        self.client.force_login(self.admin_a)
        pages = [
            ("tableau_de_bord", []), ("voyages", []), ("voyage_nouveau", []), ("voyage_detail", [self.livre.pk]),
            ("voyage_detail", [self.planifie.pk]), ("voyage_modifier", [self.livre.pk]),
            ("voyage_chargement", [self.planifie.pk]), ("voyage_livraison", [self.livre.pk]), ("bon", [self.livre.pk]),
            ("frais_nouveau", [self.livre.pk]), ("citernes", []), ("citerne_nouvelle", []),
            ("citerne_detail", [self.citerne.pk]), ("citerne_modifier", [self.citerne.pk]), ("clients", []),
            ("client_nouveau", []), ("client_detail", [self.client_a.pk]), ("client_modifier", [self.client_a.pk]),
            ("releve", [self.client_a.pk]), ("paiement_nouveau", [self.client_a.pk]), ("recu", [paiement.pk]),
            ("rapports", []),
        ]
        for nom, args in pages:
            rep = self.client.get(reverse(f"carburant:{nom}", args=args))
            self.assertEqual(rep.status_code, 200, nom)

    def test_isolation_entre_entreprises(self):
        self.client.force_login(self.admin_a)
        self.assertNotContains(self.client.get(reverse("carburant:clients")), "Client secret B")
        self.assertNotContains(self.client.get(reverse("carburant:citernes")), "CIT-B")
        self.assertEqual(self.client.get(reverse("carburant:voyage_detail", args=[self.voyage_b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("carburant:bon", args=[self.voyage_b.pk])).status_code, 404)

    def test_citerne_d_une_autre_entreprise_refusee(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("carburant:voyage_nouveau"), {
            "client": self.client_a.pk, "citerne": self.citerne_b.pk, "produit": "gasoil", "lieu_chargement": "X",
            "destination": "Pirate", "date_prevue": "2026-10-20", "base_facturation": "livree", "tarif_litre": "100"})
        self.assertEqual(rep.status_code, 200)
        with pour_entreprise(self.ent_a):
            self.assertFalse(Voyage.objects.filter(destination="Pirate").exists())

    def test_cycle_complet_planifie_charge_livre(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("carburant:voyage_chargement", args=[self.planifie.pk]), {
            "date_chargement": "2026-10-20", "bon_chargement": "BC-77", "quantite_chargee": "30000"})
        self.assertEqual(rep.status_code, 302)
        self.planifie.refresh_from_db()
        self.assertEqual(self.planifie.statut, Voyage.EN_ROUTE)
        rep = self.client.post(reverse("carburant:voyage_livraison", args=[self.planifie.pk]), {
            "date_livraison": "2026-10-21", "bon_livraison": "BL-77", "quantite_livree": "29900"})
        self.assertEqual(rep.status_code, 302)
        self.planifie.refresh_from_db()
        self.assertEqual(self.planifie.statut, Voyage.LIVRE)
        self.assertEqual(self.planifie.montant_net, D("5980000"))  # 29 900 x 200, écart dans la tolérance

    def test_livraison_impossible_avant_chargement(self):
        self.client.force_login(self.saisie_a)
        self.client.post(reverse("carburant:voyage_livraison", args=[self.planifie.pk]), {
            "date_livraison": "2026-10-21", "quantite_livree": "100"})
        self.planifie.refresh_from_db()
        self.assertEqual(self.planifie.statut, Voyage.PLANIFIE)

    def test_solde_client_et_releve(self):
        with pour_entreprise(self.ent_a):
            Paiement.objects.create(client=self.client_a, montant=D("4000000"))
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("carburant:client_detail", args=[self.client_a.pk]))
        self.assertEqual(rep.context["solde"], D("755000"))
        jour = timezone.localdate().isoformat()
        rep = self.client.get(reverse("carburant:releve", args=[self.client_a.pk]), {"date_from": jour, "date_to": jour})
        self.assertEqual(rep.context["solde_final"], D("755000"))
        self.assertContains(rep, self.livre.reference)

    def test_encaissement(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("carburant:paiement_nouveau", args=[self.client_a.pk]), {
            "date": "2026-10-22", "montant": "2000000", "mode": "virement", "imprimer": "1"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            self.assertEqual(Paiement.objects.get().agent, "saisie_a")
        self.assertEqual(self.client.get(rep["Location"]).status_code, 200)

    def test_annuler_puis_replanifier(self):
        self.client.force_login(self.saisie_a)
        self.client.post(reverse("carburant:voyage_statut", args=[self.planifie.pk]), {"action": "annuler"})
        self.planifie.refresh_from_db()
        self.assertEqual(self.planifie.statut, Voyage.ANNULE)
        self.client.post(reverse("carburant:voyage_statut", args=[self.planifie.pk]), {"action": "replanifier"})
        self.planifie.refresh_from_db()
        self.assertEqual(self.planifie.statut, Voyage.PLANIFIE)
        # Un voyage livré ne s'annule pas
        self.client.post(reverse("carburant:voyage_statut", args=[self.livre.pk]), {"action": "annuler"})
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.statut, Voyage.LIVRE)

    def test_lecteur_en_lecture_seule(self):
        self.client.force_login(self.lecteur_a)
        self.assertEqual(self.client.get(reverse("carburant:voyages")).status_code, 200)
        self.assertEqual(self.client.get(reverse("carburant:voyage_nouveau")).status_code, 403)
        self.assertEqual(self.client.get(reverse("carburant:voyage_chargement", args=[self.planifie.pk])).status_code, 403)

    def test_suppressions_protegees(self):
        self.client.force_login(self.saisie_a)
        self.assertEqual(self.client.post(reverse("carburant:voyage_supprimer", args=[self.planifie.pk])).status_code, 403)
        self.client.force_login(self.admin_a)
        self.client.post(reverse("carburant:voyage_supprimer", args=[self.livre.pk]))
        self.client.post(reverse("carburant:client_supprimer", args=[self.client_a.pk]))
        self.client.post(reverse("carburant:citerne_supprimer", args=[self.citerne.pk]))
        with pour_entreprise(self.ent_a):
            self.assertTrue(Voyage.objects.filter(pk=self.livre.pk).exists())
            self.assertTrue(Client.objects.filter(pk=self.client_a.pk).exists())
            self.assertTrue(Citerne.objects.filter(pk=self.citerne.pk).exists())
        self.client.post(reverse("carburant:voyage_supprimer", args=[self.planifie.pk]))
        with pour_entreprise(self.ent_a):
            self.assertFalse(Voyage.objects.filter(pk=self.planifie.pk).exists())

    def test_filtres_et_exports(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("carburant:voyages"), {"filtre": "manquants"})
        self.assertContains(rep, self.livre.reference)
        self.assertNotContains(rep, self.planifie.reference)
        rep = self.client.get(reverse("carburant:voyages"), {"export": "xlsx"})
        self.assertIn("spreadsheetml", rep["Content-Type"])
        rep = self.client.get(reverse("carburant:rapports"), {"export": "pdf"})
        self.assertEqual(rep["Content-Type"], "application/pdf")

    def test_rapport(self):
        self.client.force_login(self.admin_a)
        jour = timezone.localdate().isoformat()
        rep = self.client.get(reverse("carburant:rapports"), {"date_from": jour, "date_to": jour})
        self.assertContains(rep, "Star Oil Guinée")
        self.assertContains(rep, "CIT-01")
        self.assertEqual(rep.context["totaux"]["manquant"], D("100"))

    def test_menu_application_carburant(self):
        from core.odoo_menu import APPS
        self.assertIn("carburant", [a["key"] for a in APPS])
