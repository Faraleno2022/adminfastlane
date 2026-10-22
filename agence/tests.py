import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Entreprise, ProfilUtilisateur
from core.tenancy import pour_entreprise

from .forms import PaiementClientForm, PaiementFournisseurForm
from .models import (
    Client, Dossier, Fournisseur, PaiementClient, PaiementFournisseur, Prestation, Voyageur,
)

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


class AgenceBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent_a, cls.ent_b = _entreprise("alpha"), _entreprise("bravo")
        cls.admin_a = _user(cls.ent_a, "admin_a", admin=True)
        cls.saisie_a = _user(cls.ent_a, "saisie_a", niveau=2)
        cls.lecteur_a = _user(cls.ent_a, "lecteur_a", niveau=1)
        cls.admin_b = _user(cls.ent_b, "admin_b", admin=True)
        demain = timezone.localdate() + datetime.timedelta(days=10)
        with pour_entreprise(cls.ent_a):
            cls.client_a = Client.objects.create(nom="Camara Fatoumata", telephone="620000000")
            cls.air = Fournisseur.objects.create(nom="Air Test", type=Fournisseur.COMPAGNIE)
            cls.dossier = Dossier.objects.create(
                client=cls.client_a, destination="Paris", statut=Dossier.CONFIRME, date_depart=demain,
                date_retour=demain + datetime.timedelta(days=15))
            cls.billet = Prestation.objects.create(
                dossier=cls.dossier, type=Prestation.BILLET, description="Conakry → Paris", fournisseur=cls.air,
                quantite=D("2"), prix_achat=D("4000000"), prix_vente=D("4500000"))
            cls.hotel = Prestation.objects.create(
                dossier=cls.dossier, type=Prestation.HOTEL, description="Hôtel 3 nuits",
                quantite=D("1"), prix_achat=D("1000000"), prix_vente=D("1200000"))
        with pour_entreprise(cls.ent_b):
            cls.client_b = Client.objects.create(nom="Client B")
            cls.dossier_b = Dossier.objects.create(client=cls.client_b, destination="Dakar")


class ModeleTests(AgenceBase):
    def test_reference_incrementale_par_entreprise(self):
        annee = timezone.localdate().year
        self.assertEqual(self.dossier.reference, f"DV-{annee}-0001")
        self.assertEqual(self.dossier_b.reference, f"DV-{annee}-0001")
        with pour_entreprise(self.ent_a):
            second = Dossier.objects.create(client=self.client_a, destination="Dakar")
        self.assertEqual(second.reference, f"DV-{annee}-0002")

    def test_totaux_et_marge(self):
        d = Dossier.objects.get(pk=self.dossier.pk)
        self.assertEqual(d.total_vente, D("10200000"))
        self.assertEqual(d.total_achat, D("9000000"))
        self.assertEqual(d.marge, D("1200000"))

    def test_prestation_annulee_exclue_des_totaux(self):
        Prestation.objects.filter(pk=self.hotel.pk).update(statut=Prestation.ANNULEE)
        d = Dossier.objects.get(pk=self.dossier.pk)
        self.assertEqual(d.total_vente, D("9000000"))

    def test_paiements_client_et_fournisseur(self):
        with pour_entreprise(self.ent_a):
            PaiementClient.objects.create(dossier=self.dossier, montant=D("4000000"))
            PaiementFournisseur.objects.create(prestation=self.billet, montant=D("3000000"))
            d = Dossier.objects.get(pk=self.dossier.pk)
            self.assertEqual(d.reste_a_payer, D("6200000"))
            self.assertEqual(d.dette_fournisseurs, D("6000000"))  # 8 000 000 + 1 000 000 - 3 000 000
            self.assertFalse(d.est_solde)

    def test_passeport_a_verifier(self):
        proche = self.dossier.date_retour + datetime.timedelta(days=60)
        loin = self.dossier.date_retour + datetime.timedelta(days=400)
        self.assertTrue(Voyageur(dossier=self.dossier, nom="A", passeport_expiration=proche).passeport_a_verifier)
        self.assertFalse(Voyageur(dossier=self.dossier, nom="B", passeport_expiration=loin).passeport_a_verifier)
        self.assertFalse(Voyageur(dossier=self.dossier, nom="C").passeport_a_verifier)


class FormulairesTests(AgenceBase):
    def test_encaissement_superieur_au_reste_refuse(self):
        dossier = Dossier.objects.get(pk=self.dossier.pk)
        form = PaiementClientForm({"date": "2026-10-01", "montant": "99999999", "mode": "especes"}, dossier=dossier)
        self.assertFalse(form.is_valid())
        self.assertIn("montant", form.errors)

    def test_reglement_fournisseur_superieur_au_du_refuse(self):
        form = PaiementFournisseurForm({"date": "2026-10-01", "montant": "9000000", "mode": "virement"},
                                       prestation=Prestation.objects.get(pk=self.billet.pk))
        self.assertFalse(form.is_valid())

    def test_montant_negatif_refuse(self):
        dossier = Dossier.objects.get(pk=self.dossier.pk)
        form = PaiementClientForm({"date": "2026-10-01", "montant": "-1", "mode": "especes"}, dossier=dossier)
        self.assertFalse(form.is_valid())


class VuesTests(AgenceBase):
    def test_pages_accessibles(self):
        self.client.force_login(self.admin_a)
        pages = [
            ("tableau_de_bord", []), ("clients", []), ("client_nouveau", []), ("client_detail", [self.client_a.pk]),
            ("client_modifier", [self.client_a.pk]), ("fournisseurs", []), ("fournisseur_nouveau", []),
            ("fournisseur_detail", [self.air.pk]), ("dossiers", []), ("dossier_nouveau", []),
            ("dossier_detail", [self.dossier.pk]), ("dossier_modifier", [self.dossier.pk]),
            ("document", [self.dossier.pk]), ("prestation_nouvelle", [self.dossier.pk]),
            ("prestation_modifier", [self.billet.pk]), ("paiement_fournisseur_nouveau", [self.billet.pk]),
            ("voyageur_nouveau", [self.dossier.pk]), ("paiement_nouveau", [self.dossier.pk]), ("rapports", []),
        ]
        for nom, args in pages:
            rep = self.client.get(reverse(f"agence:{nom}", args=args))
            self.assertEqual(rep.status_code, 200, nom)

    def test_isolation_entre_entreprises(self):
        self.client.force_login(self.admin_a)
        self.assertNotContains(self.client.get(reverse("agence:clients")), "Client B")
        self.assertEqual(self.client.get(reverse("agence:dossier_detail", args=[self.dossier_b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("agence:client_detail", args=[self.client_b.pk])).status_code, 404)

    def test_creation_dossier_renseigne_agent_et_reference(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("agence:dossier_nouveau"), {
            "client": self.client_a.pk, "destination": "Istanbul", "nb_voyageurs": 2, "statut": "devis"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            d = Dossier.objects.get(destination="Istanbul")
        self.assertTrue(d.reference.startswith("DV-"))
        self.assertEqual(d.agent, "saisie_a")

    def test_client_d_une_autre_entreprise_refuse(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("agence:dossier_nouveau"), {
            "client": self.client_b.pk, "destination": "Pirate", "nb_voyageurs": 1, "statut": "devis"})
        self.assertEqual(rep.status_code, 200)  # formulaire réaffiché avec une erreur
        with pour_entreprise(self.ent_a):
            self.assertFalse(Dossier.objects.filter(destination="Pirate").exists())

    def test_encaissement_via_la_vue(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("agence:paiement_nouveau", args=[self.dossier.pk]), {
            "date": "2026-10-05", "montant": "2000000", "mode": "mobile_money", "imprimer": "1"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            paiement = PaiementClient.objects.get()
        self.assertEqual(paiement.agent, "saisie_a")
        self.assertEqual(self.client.get(rep["Location"]).status_code, 200)  # reçu

    def test_lecteur_en_lecture_seule(self):
        self.client.force_login(self.lecteur_a)
        self.assertEqual(self.client.get(reverse("agence:dossiers")).status_code, 200)
        self.assertEqual(self.client.get(reverse("agence:dossier_nouveau")).status_code, 403)
        self.assertEqual(self.client.post(reverse("agence:dossier_statut", args=[self.dossier.pk]),
                                          {"statut": "annule"}).status_code, 403)

    def test_changement_de_statut(self):
        self.client.force_login(self.saisie_a)
        self.client.post(reverse("agence:dossier_statut", args=[self.dossier.pk]), {"statut": "termine"})
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.statut, Dossier.TERMINE)

    def test_suppression_dossier_avec_paiement_refusee(self):
        with pour_entreprise(self.ent_a):
            PaiementClient.objects.create(dossier=self.dossier, montant=D("1"))
        self.client.force_login(self.admin_a)
        self.client.post(reverse("agence:dossier_supprimer", args=[self.dossier.pk]))
        with pour_entreprise(self.ent_a):
            self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())

    def test_suppression_client_avec_dossiers_refusee(self):
        self.client.force_login(self.admin_a)
        self.client.post(reverse("agence:client_supprimer", args=[self.client_a.pk]))
        with pour_entreprise(self.ent_a):
            self.assertTrue(Client.objects.filter(pk=self.client_a.pk).exists())

    def test_suppression_reservee_aux_responsables(self):
        self.client.force_login(self.saisie_a)
        self.assertEqual(self.client.post(reverse("agence:prestation_supprimer", args=[self.hotel.pk])).status_code, 403)

    def test_documents_devis_et_facture(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("agence:document", args=[self.dossier.pk]))
        self.assertContains(rep, "FACTURE")
        Dossier.objects.filter(pk=self.dossier.pk).update(statut=Dossier.DEVIS)
        self.assertContains(self.client.get(reverse("agence:document", args=[self.dossier.pk])), "DEVIS")

    def test_filtres_et_exports(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("agence:dossiers"), {"filtre": "impayes"})
        self.assertContains(rep, self.dossier.reference)
        rep = self.client.get(reverse("agence:dossiers"), {"statut": "annule"})
        self.assertNotContains(rep, self.dossier.reference)
        rep = self.client.get(reverse("agence:dossiers"), {"export": "xlsx"})
        self.assertIn("spreadsheetml", rep["Content-Type"])
        rep = self.client.get(reverse("agence:rapports"), {"export": "pdf"})
        self.assertEqual(rep["Content-Type"], "application/pdf")

    def test_rapport_par_type(self):
        self.client.force_login(self.admin_a)
        jour = timezone.localdate().isoformat()
        rep = self.client.get(reverse("agence:rapports"), {"date_from": jour, "date_to": jour})
        self.assertContains(rep, "Billet d&#x27;avion")
        self.assertContains(rep, "Paris")

    def test_menu_application_agence(self):
        from core.odoo_menu import APPS
        self.assertIn("agence", [a["key"] for a in APPS])
