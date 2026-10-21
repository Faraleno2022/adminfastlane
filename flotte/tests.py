import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Entreprise

from . import services_dashboard
from .models import (
    ActiviteEngin, Article, AutreDepense, Chauffeur, DocumentVehicule, Engin, EmployeFlotte,
    Entretien, Marque, MouvementStock, PleinCarburant, Pointage, TrajetPorteChar, Vehicule, Voyage,
)
from .permissions import peut_gerer_referentiel, peut_saisir
from .scope import pour_entreprise

User = get_user_model()


def _entreprise(slug):
    return Entreprise.objects.create(
        nom_entreprise=f"Entreprise {slug}", slug=slug, email=f"{slug}@example.test",
        type_module="all",
    )


def _utilisateur(entreprise, nom, admin=False):
    return User.objects.create_user(
        username=nom, email=f"{nom}@example.test", password="Mdp-test-1234", entreprise=entreprise,
        est_admin_entreprise=admin, actif=True,
    )


class FlotteBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent_a = _entreprise("alpha")
        cls.ent_b = _entreprise("bravo")
        cls.admin_a = _utilisateur(cls.ent_a, "admin_a", admin=True)
        cls.lecteur_a = _utilisateur(cls.ent_a, "lecteur_a")
        cls.admin_b = _utilisateur(cls.ent_b, "admin_b", admin=True)

        with pour_entreprise(cls.ent_a):
            cls.marque_a = Marque.objects.create(nom="HOWO")
            cls.chauffeur_a = Chauffeur.objects.create(nom_prenoms="Camara Moussa")
            cls.vehicule_a = Vehicule.objects.create(
                immatriculation="RC-1234-A", marque=cls.marque_a, chauffeur_actuel=cls.chauffeur_a,
            )
            cls.engin_a = Engin.objects.create(nom="Poclain 1", type_engin="poclain")
            jour = datetime.date(2026, 3, 10)
            cls.entretien_a = Entretien.objects.create(
                date=jour, vehicule=cls.vehicule_a, montant_ttc=Decimal("500000"))
            PleinCarburant.objects.create(
                date=jour, vehicule=cls.vehicule_a, litres=Decimal("100"), prix_litre=Decimal("12000"),
                kilometrage=1000)
            Voyage.objects.create(
                date=jour, vehicule=cls.vehicule_a, nb_voyage=3, pu_voyage=Decimal("200000"),
                km_depart=1000, km_arrivee=1300)
            ActiviteEngin.objects.create(
                date=jour, engin=cls.engin_a, nb_chargement=5, pu_chargement=Decimal("100000"),
                qte_carburant=Decimal("50"), prix_litre=Decimal("12000"))
            TrajetPorteChar.objects.create(
                date=jour, engin=cls.engin_a, point_depart="A", point_arrivee="B",
                montant_paye=Decimal("300000"))
            AutreDepense.objects.create(
                date=jour, designation="Pièces", prix_unitaire=Decimal("1000"), quantite=Decimal("2"))
            cls.employe_a = EmployeFlotte.objects.create(nom_complet="Diallo Alpha", matricule="E1")
            cls.article_a = Article.objects.create(
                code="A1", designation="Clé à molette", stock_initial=Decimal("10"),
                seuil_mini=Decimal("2"))
            MouvementStock.objects.create(
                article=cls.article_a, date=jour, type=MouvementStock.SORTIE, quantite=Decimal("4"))

        with pour_entreprise(cls.ent_b):
            cls.vehicule_b = Vehicule.objects.create(immatriculation="RC-9999-B")
            Entretien.objects.create(
                date=datetime.date(2026, 3, 11), vehicule=cls.vehicule_b, montant_ttc=Decimal("777"))


class IsolationTests(FlotteBase):
    def test_manager_filtre_sur_l_entreprise_courante(self):
        with pour_entreprise(self.ent_a):
            self.assertEqual(list(Vehicule.objects.values_list("immatriculation", flat=True)), ["RC-1234-A"])
        with pour_entreprise(self.ent_b):
            self.assertEqual(list(Vehicule.objects.values_list("immatriculation", flat=True)), ["RC-9999-B"])

    def test_utilisateur_sans_entreprise_ne_voit_rien(self):
        with pour_entreprise(None):
            self.assertEqual(Vehicule.objects.count(), 0)

    def test_suppression_logique(self):
        with pour_entreprise(self.ent_a):
            v = Vehicule.objects.create(immatriculation="TMP-1")
            v.delete()
            self.assertFalse(Vehicule.objects.filter(pk=v.pk).exists())
            self.assertTrue(Vehicule.all_objects.filter(pk=v.pk).exists())

    def test_la_liste_n_affiche_que_les_vehicules_de_l_entreprise(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("flotte:vehicule_liste"))
        self.assertContains(rep, "RC-1234-A")
        self.assertNotContains(rep, "RC-9999-B")

    def test_acces_direct_a_un_objet_d_une_autre_entreprise_refuse(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("flotte:vehicule_modifier", args=[self.vehicule_b.pk]))
        self.assertEqual(rep.status_code, 404)
        rep = self.client.post(reverse("flotte:vehicule_supprimer", args=[self.vehicule_b.pk]))
        self.assertEqual(rep.status_code, 404)
        with pour_entreprise(self.ent_b):
            self.assertTrue(Vehicule.objects.filter(pk=self.vehicule_b.pk).exists())

    def test_creation_rattachee_a_l_entreprise_de_l_utilisateur(self):
        self.client.force_login(self.admin_a)
        rep = self.client.post(reverse("flotte:marque_creer"), {"nom": "foton"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            self.assertTrue(Marque.objects.filter(nom="FOTON").exists())
        with pour_entreprise(self.ent_b):
            self.assertFalse(Marque.objects.filter(nom="FOTON").exists())

    def test_formulaire_ne_propose_que_les_donnees_de_l_entreprise(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("flotte:entretien_creer"))
        self.assertContains(rep, "RC-1234-A")
        self.assertNotContains(rep, "RC-9999-B")

    def test_marque_en_double_refusee_par_entreprise(self):
        self.client.force_login(self.admin_a)
        rep = self.client.post(reverse("flotte:marque_creer"), {"nom": "howo"})
        self.assertEqual(rep.status_code, 200)  # formulaire réaffiché avec l'erreur
        self.assertContains(rep, "existe déjà")
        # Le même nom reste possible dans une autre entreprise.
        self.client.force_login(self.admin_b)
        rep = self.client.post(reverse("flotte:marque_creer"), {"nom": "howo"})
        self.assertEqual(rep.status_code, 302)

    def test_totaux_du_tableau_de_bord_par_entreprise(self):
        with pour_entreprise(self.ent_a):
            t = services_dashboard.totaux(2026)
        self.assertEqual(t["montant_entretien"], Decimal("500000"))
        with pour_entreprise(self.ent_b):
            t = services_dashboard.totaux(2026)
        self.assertEqual(t["montant_entretien"], Decimal("777"))


class DroitsTests(FlotteBase):
    def test_roles(self):
        self.assertTrue(peut_gerer_referentiel(self.admin_a))
        self.assertTrue(peut_saisir(self.admin_a))
        self.assertFalse(peut_gerer_referentiel(self.lecteur_a))
        self.assertFalse(peut_saisir(self.lecteur_a))

    def test_lecteur_ne_peut_pas_modifier(self):
        self.client.force_login(self.lecteur_a)
        self.assertEqual(self.client.get(reverse("flotte:vehicule_liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("flotte:entretien_creer")).status_code, 403)
        self.assertEqual(self.client.get(reverse("flotte:vehicule_creer")).status_code, 403)

    def test_anonyme_redirige_vers_la_connexion(self):
        rep = self.client.get(reverse("flotte:accueil"))
        self.assertEqual(rep.status_code, 302)
        self.assertIn("login", rep["Location"])


class PagesTests(FlotteBase):
    """Chaque page du module s'affiche (200) avec le gabarit Odoo."""

    def test_toutes_les_pages_s_affichent(self):
        self.client.force_login(self.admin_a)
        noms = [
            "accueil", "analyses", "categorie_liste", "marque_liste", "chauffeur_liste",
            "vehicule_liste", "document_liste", "engin_liste", "entretien_liste",
            "carburant_liste", "voyage_liste", "poclain_liste", "portechar_liste",
            "depense_liste", "grille", "employe_liste", "inventaire", "synthese",
            "mouvement_liste", "rapport_mensuel", "rapport_charges_entretien",
            "rapport_carburant", "rapport_poclain",
            "categorie_creer", "marque_creer", "chauffeur_creer", "vehicule_creer",
            "document_creer", "engin_creer", "entretien_creer", "carburant_creer",
            "voyage_creer", "poclain_creer", "portechar_creer", "depense_creer",
            "employe_creer", "article_creer", "mouvement_creer",
        ]
        for nom in noms:
            with self.subTest(page=nom):
                rep = self.client.get(reverse(f"flotte:{nom}"), {"annee": 2026, "mois": 3})
                self.assertEqual(rep.status_code, 200, nom)
                self.assertContains(rep, "o_navbar")

    def test_pages_de_detail_et_modification(self):
        self.client.force_login(self.admin_a)
        for nom, pk in [
            ("vehicule_detail", self.vehicule_a.pk),
            ("vehicule_modifier", self.vehicule_a.pk),
            ("vehicule_supprimer", self.vehicule_a.pk),
            ("entretien_modifier", self.entretien_a.pk),
            ("employe_modifier", self.employe_a.pk),
            ("article_modifier", self.article_a.pk),
        ]:
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(f"flotte:{nom}", args=[pk])).status_code, 200)

    def test_exports(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("flotte:export_excel"), {"annee": 2026})
        self.assertEqual(rep.status_code, 200)
        self.assertIn("spreadsheetml", rep["Content-Type"])
        rep = self.client.get(reverse("flotte:export_pdf"), {"annee": 2026})
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep["Content-Type"], "application/pdf")

    def test_menu_odoo_contient_la_flotte(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("flotte:accueil"))
        self.assertContains(rep, "Entretien &amp; réparations")


class PointageTests(FlotteBase):
    def test_enregistrement_d_un_pointage(self):
        self.client.force_login(self.admin_a)
        rep = self.client.post(reverse("flotte:enregistrer"), {
            "employe": str(self.employe_a.pk), "date": "2026-03-10", "statut": "P"})
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.json()["nb_presence"], 1)
        with pour_entreprise(self.ent_a):
            self.assertEqual(Pointage.objects.count(), 1)

    def test_pointage_d_un_employe_d_une_autre_entreprise_refuse(self):
        self.client.force_login(self.admin_b)
        rep = self.client.post(reverse("flotte:enregistrer"), {
            "employe": str(self.employe_a.pk), "date": "2026-03-10", "statut": "P"})
        self.assertEqual(rep.status_code, 400)

    def test_lecteur_ne_peut_pas_pointer(self):
        self.client.force_login(self.lecteur_a)
        rep = self.client.post(reverse("flotte:enregistrer"), {
            "employe": str(self.employe_a.pk), "date": "2026-03-10", "statut": "P"})
        self.assertEqual(rep.status_code, 403)


class DocumentsTests(FlotteBase):
    def test_document_prive_et_isole(self):
        import tempfile
        from unittest import mock

        from django.core.files.storage import FileSystemStorage

        champ = DocumentVehicule._meta.get_field("fichier")
        with tempfile.TemporaryDirectory() as dossier,                 mock.patch.object(champ, "storage", FileSystemStorage(location=dossier)):
            with pour_entreprise(self.ent_a):
                doc = DocumentVehicule.objects.create(
                    vehicule=self.vehicule_a, type_document="assurance",
                    date_expiration=datetime.date.today() + datetime.timedelta(days=5),
                    fichier=SimpleUploadedFile("police.pdf", b"%PDF-1.4 test"),
                )
            self.assertEqual(doc.statut, DocumentVehicule.BIENTOT)

            self.client.force_login(self.admin_a)
            rep = self.client.get(reverse("flotte:document_fichier", args=[doc.pk]))
            self.assertEqual(rep.status_code, 200)
            self.assertEqual(b"".join(rep.streaming_content), b"%PDF-1.4 test")

            # Une autre entreprise ne peut pas lire la pièce jointe.
            self.client.force_login(self.admin_b)
            rep = self.client.get(reverse("flotte:document_fichier", args=[doc.pk]))
            self.assertEqual(rep.status_code, 404)
