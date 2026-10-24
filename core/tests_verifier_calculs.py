"""Commande verifier_calculs : aucun écart sur des données justes, détection des montants faussés."""
from decimal import Decimal
from io import StringIO

from django.core.management import CommandError, call_command
from django.db.models import F
from django.test import TestCase

from core.models import Entreprise, Utilisateur
from core.tenancy import pour_entreprise


class VerifierCalculsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(nom_entreprise="Myschool", slug="myschool", email="a@myschool.test")
        Utilisateur.objects.create_user(username="Myschool", email="a@myschool.test", password="Mdp-tres-solide-2026",
                                        entreprise=cls.entreprise, est_admin_entreprise=True)
        call_command("charger_demo", utilisateur="Myschool", stdout=StringIO())

    def _verifier(self):
        sortie = StringIO()
        call_command("verifier_calculs", utilisateur="Myschool", stdout=sortie)
        return sortie.getvalue()

    def test_aucun_ecart_sur_les_donnees_de_demonstration(self):
        sortie = self._verifier()
        self.assertIn("Résultat : aucun écart", sortie, sortie)
        for section in ("Paie (bulletins)", "Transport de carburant", "Gestion de projet", "Agence de voyage",
                        "Suivi des prêts", "Flotte", "Ventes (comptes et stock)"):
            self.assertIn(f"[OK] {section}", sortie)

    def test_montants_faux_detectes(self):
        from carburant.models import Voyage
        from paie.models import BulletinPaie
        from prets.models import Pret
        from ventes.models import Operation
        BulletinPaie.objects.filter(employe__nom="CAMARA").update(irg=F("irg") + 1000)
        with pour_entreprise(self.entreprise):
            Pret.objects.filter(designation__startswith="Prêt d'équipement").update(observation=Pret.PAYE)
            Operation.objects.filter(type=Operation.DEPOT).update(solde_apres=Decimal("1"))
            Voyage.objects.filter(statut=Voyage.EN_ROUTE).update(quantite_chargee=Decimal("90000"))
        sortie = self._verifier()
        self.assertIn("RTS : 748 500 au lieu de 747 500", sortie)
        self.assertIn("net à payer", sortie)
        self.assertIn("statut « Payé » avec un reste de 4 500 000", sortie)
        self.assertIn("[!!] Ventes (comptes et stock)", sortie)
        self.assertIn("90 000 L chargés pour une citerne", sortie)
        self.assertNotIn("Résultat : aucun écart", sortie)

    def test_lecture_seule(self):
        from paie.models import BulletinPaie
        avant = list(BulletinPaie.objects.values_list("pk", "net_a_payer", "irg"))
        self._verifier()
        self.assertEqual(list(BulletinPaie.objects.values_list("pk", "net_a_payer", "irg")), avant)

    def test_utilisateur_inconnu(self):
        with self.assertRaises(CommandError):
            call_command("verifier_calculs", utilisateur="personne", stdout=StringIO())
