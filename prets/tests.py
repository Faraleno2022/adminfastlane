import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Entreprise, ProfilUtilisateur
from core.tenancy import pour_entreprise

from .forms import PretForm
from .models import Pret, Remboursement

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


def _donnees(**extra):
    base = {
        "designation": "Prêt fournisseur", "montant_pret": "1000000", "valeur_interet": "100000",
        "montant_a_recouvrer": "1100000", "date_debut": "2026-10-01", "date_fin": "2026-11-21",
        "observation": "en_cours", "note": "",
    }
    base.update(extra)
    return base


class PretsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent_a, cls.ent_b = _entreprise("alpha"), _entreprise("bravo")
        cls.admin_a = _user(cls.ent_a, "admin_a", admin=True)
        cls.saisie_a = _user(cls.ent_a, "saisie_a", niveau=2)
        cls.lecteur_a = _user(cls.ent_a, "lecteur_a", niveau=1)
        cls.admin_b = _user(cls.ent_b, "admin_b", admin=True)
        with pour_entreprise(cls.ent_a):
            cls.pret = Pret.objects.create(
                designation="Prêt A", montant_pret=D("1000000"), montant_a_recouvrer=D("1100000"),
                valeur_interet=D("100000"), date_debut=datetime.date(2026, 10, 1),
                date_fin=datetime.date(2026, 11, 21))
        with pour_entreprise(cls.ent_b):
            cls.pret_b = Pret.objects.create(
                designation="Prêt B", montant_pret=D("5"), montant_a_recouvrer=D("5"),
                date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2026, 11, 1))


class ModeleTests(PretsBase):
    def test_duree_en_jours(self):
        self.assertEqual(self.pret.duree_jours, 51)

    def test_remboursement_partiel_puis_total(self):
        with pour_entreprise(self.ent_a):
            Remboursement.objects.create(pret=self.pret, montant=D("400000"))
            self.assertEqual(self.pret.reste_a_recouvrer, D("700000"))
            self.pret.synchroniser_statut()
            self.pret.refresh_from_db()
            self.assertEqual(self.pret.observation, Pret.EN_COURS)
            Remboursement.objects.create(pret=self.pret, montant=D("700000"))
            self.pret.synchroniser_statut()
            self.pret.refresh_from_db()
            self.assertEqual(self.pret.observation, Pret.PAYE)

    def test_echu_seulement_si_non_paye(self):
        passe = timezone.localdate() - datetime.timedelta(days=1)
        self.assertTrue(Pret(date_debut=passe, date_fin=passe, observation=Pret.EN_COURS).est_echu)
        self.assertFalse(Pret(date_debut=passe, date_fin=passe, observation=Pret.PAYE).est_echu)


class FormulaireTests(PretsBase):
    def test_interet_deduit_du_total(self):
        form = PretForm(_donnees(valeur_interet=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["valeur_interet"], D("100000"))

    def test_total_deduit_du_capital_et_de_l_interet(self):
        form = PretForm(_donnees(montant_a_recouvrer=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["montant_a_recouvrer"], D("1100000"))

    def test_sans_interet_ni_total(self):
        form = PretForm(_donnees(valeur_interet="", montant_a_recouvrer=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["montant_a_recouvrer"], D("1000000"))

    def test_fin_avant_debut_refusee(self):
        form = PretForm(_donnees(date_fin="2026-09-01"))
        self.assertFalse(form.is_valid())
        self.assertIn("date_fin", form.errors)


class VuesTests(PretsBase):
    def test_pages_accessibles(self):
        self.client.force_login(self.admin_a)
        for nom, args in (("tableau_de_bord", []), ("liste", []), ("nouveau", []),
                          ("detail", [self.pret.pk]), ("modifier", [self.pret.pk])):
            rep = self.client.get(reverse(f"prets:{nom}", args=args))
            self.assertEqual(rep.status_code, 200, nom)

    def test_isolation_entre_entreprises(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("prets:liste"))
        self.assertContains(rep, "Prêt A")
        self.assertNotContains(rep, "Prêt B")
        self.assertEqual(self.client.get(reverse("prets:detail", args=[self.pret_b.pk])).status_code, 404)

    def test_creation(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("prets:nouveau"), _donnees(designation="Nouveau prêt"))
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            self.assertTrue(Pret.objects.filter(designation="Nouveau prêt").exists())

    def test_lecteur_ne_peut_pas_saisir(self):
        self.client.force_login(self.lecteur_a)
        self.assertEqual(self.client.get(reverse("prets:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("prets:nouveau")).status_code, 403)
        self.assertEqual(self.client.post(reverse("prets:remboursement_ajouter", args=[self.pret.pk]),
                                          {"date": "2026-10-05", "montant": "1"}).status_code, 403)

    def test_remboursement_via_la_vue_solde_le_pret(self):
        self.client.force_login(self.saisie_a)
        self.client.post(reverse("prets:remboursement_ajouter", args=[self.pret.pk]),
                         {"date": "2026-10-05", "montant": "1100000"})
        self.pret.refresh_from_db()
        self.assertEqual(self.pret.observation, Pret.PAYE)

    def test_remboursement_negatif_refuse(self):
        self.client.force_login(self.saisie_a)
        self.client.post(reverse("prets:remboursement_ajouter", args=[self.pret.pk]),
                         {"date": "2026-10-05", "montant": "-5"})
        with pour_entreprise(self.ent_a):
            self.assertEqual(Remboursement.objects.count(), 0)

    def test_suppression_reservee(self):
        self.client.force_login(self.saisie_a)
        self.assertEqual(self.client.post(reverse("prets:supprimer", args=[self.pret.pk])).status_code, 403)
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.post(reverse("prets:supprimer", args=[self.pret.pk])).status_code, 302)
        with pour_entreprise(self.ent_a):
            self.assertFalse(Pret.objects.exists())

    def test_filtre_statut_et_exports(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("prets:liste"), {"statut": "paye"})
        self.assertNotContains(rep, "Prêt A")
        rep = self.client.get(reverse("prets:liste"), {"export": "xlsx"})
        self.assertEqual(rep.status_code, 200)
        self.assertIn("spreadsheetml", rep["Content-Type"])
        rep = self.client.get(reverse("prets:liste"), {"export": "pdf"})
        self.assertEqual(rep["Content-Type"], "application/pdf")

    def test_menu_application_prets(self):
        from core.odoo_menu import APPS
        self.assertIn("prets", [a["key"] for a in APPS])
