"""Interrupteur ABONNEMENTS_ACTIFS : plans, quotas et licence désactivables."""
import datetime
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from .licence_utils import invalider_cache_licence
from .middleware import EntrepriseQuotaMiddleware
from .models import Entreprise, Utilisateur
from .odoo_menu import build_shell


class AbonnementsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(
            nom_entreprise="Sans plan", slug="sans-plan", email="a@sans-plan.test", type_module="rh",
            module_recrutement=False, date_expiration=datetime.date(2020, 1, 1))
        cls.admin = Utilisateur.objects.create_user(
            username="admin_sp", email="a@sans-plan.test", password="Mdp-tres-solide-2026",
            entreprise=cls.entreprise, est_admin_entreprise=True)

    def setUp(self):
        invalider_cache_licence()
        # Aucune licence fichier : seul l'interrupteur décide (license.dat peut exister sur le poste).
        patcheur = mock.patch("license_manager.load_and_validate_license", return_value={"valid": False})
        patcheur.start()
        self.addCleanup(patcheur.stop)
        self.addCleanup(invalider_cache_licence)

    def _requete(self, chemin):
        requete = RequestFactory().get(chemin)
        SessionMiddleware(lambda r: None).process_request(requete)
        requete._messages = FallbackStorage(requete)
        requete.user = self.admin
        return requete

    def _passe(self, chemin):
        reponse = EntrepriseQuotaMiddleware(lambda r: HttpResponse("ok"))(self._requete(chemin))
        return reponse.status_code == 200

    def _menus(self, chemin):
        contexte = build_shell(self._requete(chemin))
        return [a["key"] for a in contexte["odoo_apps"]], [m["label"] for m in contexte["odoo_menus"]]

    @override_settings(ABONNEMENTS_ACTIFS=False)
    def test_desactives_tout_est_accessible(self):
        self.assertTrue(self.entreprise.has_module("recrutement"))
        self.assertTrue(self._passe("/recrutement/"))  # module hors plan et abonnement expiré
        apps, menus = self._menus("/profile/")
        self.assertNotIn("abonnement", apps)
        self.assertNotIn("Licence", menus)

    @override_settings(ABONNEMENTS_ACTIFS=True)
    def test_actives_les_plans_s_appliquent(self):
        self.assertFalse(self.entreprise.has_module("recrutement"))
        self.assertFalse(self._passe("/recrutement/"))
        apps, menus = self._menus("/profile/")
        self.assertIn("abonnement", apps)
        self.assertIn("Licence", menus)
