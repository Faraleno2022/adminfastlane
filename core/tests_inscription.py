"""Inscription façon Odoo : choix des applications, e-mail / nom / téléphone réutilisables."""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import UserInvitationForm, type_module_pour
from .models import Entreprise, Utilisateur
from .odoo_menu import build_shell, cles_selectionnables


def _donnees(**autres):
    donnees = {
        "applications": ["carburant", "projets"],
        "nom_entreprise": "Fastlane Logistic", "email": "contact@fastlane.test", "telephone": "620000000",
        "ville": "Conakry", "pays": "Guinée", "plan_abonnement": "gratuit",
        "admin_first_name": "Mamadou", "admin_last_name": "Diallo", "admin_email": "gerant@fastlane.test",
        "admin_username": "mdiallo", "admin_password": "Mdp-tres-solide-2026",
        "admin_password_confirm": "Mdp-tres-solide-2026",
    }
    donnees.update(autres)
    return donnees


@override_settings(REGISTRATION_DISABLED=False)
class InscriptionTests(TestCase):
    def setUp(self):
        cache.clear()  # limite de débit de la vue d'inscription

    def _lanceur(self, user):
        requete = self.client.get(reverse("core:home_menu")).wsgi_request
        requete.user = user
        return [a["key"] for a in build_shell(requete)["odoo_apps"]]

    def test_page_avec_grille_et_preselection(self):
        rep = self.client.get(reverse("core:register_entreprise"), {"apps": "carburant,flotte"})
        self.assertEqual(rep.status_code, 200)
        self.assertContains(rep, "Transport de carburant")
        self.assertContains(rep, "Logistique")
        self.assertEqual(rep.context["choisies"], {"carburant", "flotte"})

    def test_inscription_avec_applications_choisies(self):
        rep = self.client.post(reverse("core:register_entreprise"), _donnees(applications=["projets", "carburant", "paie"]))
        self.assertRedirects(rep, reverse("core:home_menu"), fetch_redirect_response=False)
        entreprise = Entreprise.objects.get(nom_entreprise="Fastlane Logistic")
        self.assertEqual(entreprise.applications, ["paie", "projets", "carburant"])  # ordre du catalogue
        self.assertEqual(entreprise.type_module, "rh")
        admin = entreprise.utilisateurs.get()
        self.assertTrue(admin.est_admin_entreprise)
        self.assertEqual(admin.telephone, "620000000")
        cles = self._lanceur(admin)
        self.assertEqual(cles, ["paie", "projets", "carburant", "parametres"])

    def test_email_nom_et_telephone_reutilisables(self):
        self.client.post(reverse("core:register_entreprise"), _donnees())
        cache.clear()
        self.client.logout()
        rep = self.client.post(reverse("core:register_entreprise"), _donnees(admin_username="mdiallo2"))
        self.assertEqual(rep.status_code, 302)
        self.assertEqual(Entreprise.objects.filter(nom_entreprise="Fastlane Logistic").count(), 2)
        self.assertEqual(Utilisateur.objects.filter(email="gerant@fastlane.test").count(), 2)
        self.assertEqual(len(set(Entreprise.objects.values_list("slug", flat=True))), 2)

    def test_identifiant_de_connexion_unique(self):
        self.client.post(reverse("core:register_entreprise"), _donnees())
        cache.clear()
        self.client.logout()
        rep = self.client.post(reverse("core:register_entreprise"), _donnees(admin_username="MDiallo"))
        self.assertEqual(rep.status_code, 200)
        self.assertIn("admin_username", rep.context["form"].errors)
        self.assertEqual(Entreprise.objects.count(), 1)

    def test_au_moins_une_application(self):
        rep = self.client.post(reverse("core:register_entreprise"), _donnees(applications=[]))
        self.assertEqual(rep.status_code, 200)
        self.assertIn("applications", rep.context["form"].errors)
        rep = self.client.post(reverse("core:register_entreprise"), _donnees(applications=["inconnue"]))
        self.assertIn("applications", rep.context["form"].errors)

    def test_type_de_compte_deduit(self):
        self.assertEqual(type_module_pour(["rh", "compta"]), "both")
        self.assertEqual(type_module_pour(["compta", "stock"]), "compta")
        self.assertEqual(type_module_pour(["ventes", "stock"]), "stock")
        self.assertEqual(type_module_pour(["carburant"]), "secretariat")

    def test_invitation_avec_email_deja_utilise(self):
        Utilisateur.objects.create_user(username="existant", email="partage@fastlane.test", password="x-Mdp-1234567")
        form = UserInvitationForm({"username": "nouveau", "email": "partage@fastlane.test", "first_name": "A",
                                   "last_name": "B", "password": "Mdp-tres-solide-2026",
                                   "password_confirm": "Mdp-tres-solide-2026"})
        self.assertNotIn("email", form.errors)


class ApplicationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(
            nom_entreprise="Ancienne", slug="ancienne", email="a@ancienne.test", type_module="rh")
        cls.admin = Utilisateur.objects.create_user(
            username="admin_anc", email="a@ancienne.test", password="Mdp-tres-solide-2026",
            entreprise=cls.entreprise, est_admin_entreprise=True)
        cls.employe = Utilisateur.objects.create_user(
            username="employe_anc", email="a@ancienne.test", password="Mdp-tres-solide-2026",
            entreprise=cls.entreprise)

    @mock.patch("core.licence_utils.licence_offline_valide", return_value=False)  # une licence hors ligne débloque tout
    def test_compte_existant_garde_ses_applications(self, _licence):
        self.client.force_login(self.admin)
        rep = self.client.get(reverse("core:applications"))
        self.assertEqual(rep.status_code, 200)
        self.assertIn("rh", rep.context["choisies"])
        self.assertNotIn("compta", rep.context["choisies"])  # type « rh » : pas de comptabilité

    def test_modifier_les_applications(self):
        self.client.force_login(self.admin)
        rep = self.client.post(reverse("core:applications"), {"applications": ["compta", "flotte"]})
        self.assertRedirects(rep, reverse("core:home_menu"), fetch_redirect_response=False)
        self.entreprise.refresh_from_db()
        self.assertEqual(self.entreprise.applications, ["compta", "flotte"])
        self.assertEqual(self.entreprise.type_module, "compta")
        self.assertTrue(self.entreprise.has_compta)
        rep = self.client.get(reverse("core:home_menu"))
        cles = [a["key"] for a in rep.context["odoo_apps"]]
        self.assertEqual(cles, ["compta", "flotte", "parametres"])
        # Le tableau de bord RH renvoie au lanceur quand Employés n'est pas installé
        self.assertRedirects(self.client.get(reverse("dashboard:index")), reverse("core:home_menu"),
                             fetch_redirect_response=False)

    def test_aucune_application_refusee(self):
        self.client.force_login(self.admin)
        rep = self.client.post(reverse("core:applications"), {})
        self.assertEqual(rep.status_code, 200)
        self.entreprise.refresh_from_db()
        self.assertEqual(self.entreprise.applications, [])

    def test_reserve_a_l_administrateur(self):
        self.client.force_login(self.employe)
        rep = self.client.post(reverse("core:applications"), {"applications": ["flotte"]})
        self.assertRedirects(rep, reverse("core:home_menu"), fetch_redirect_response=False)
        self.entreprise.refresh_from_db()
        self.assertEqual(self.entreprise.applications, [])

    def test_catalogue_couvre_les_applications_metier(self):
        self.assertIn("carburant", cles_selectionnables())
        self.assertNotIn("parametres", cles_selectionnables())
