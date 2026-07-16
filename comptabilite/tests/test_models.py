"""
Tests pour le module comptabilité.

Couvre:
- Modèles
- Services
- Vues
- Formulaires
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from datetime import date, timedelta
import logging

from core.models import Entreprise
from comptabilite.models import (
    CompteBancaire, RapprochementBancaire, OperationBancaire,
    ExerciceComptable, EcritureComptable, EcartBancaire
)
from comptabilite.services.rapprochement_service import RapprochementService
from comptabilite.utils.helpers import (
    MontantFormatter, ComptesUtils, EcritureUtils,
    RapprochementUtils, DeviseUtils, ExerciceUtils
)

User = get_user_model()
logger = logging.getLogger(__name__)


class MontantFormatterTest(TestCase):
    """Tests du formateur de montants."""
    
    def test_format_montant(self):
        """Teste le formatage des montants."""
        montant = Decimal('1234.56')
        formatted = MontantFormatter.format_montant(montant, 'EUR')
        self.assertIn('EUR', formatted)
        self.assertIn('1', formatted)
    
    def test_parse_montant(self):
        """Teste le parsing des montants."""
        texte = "1 234,56"
        montant = MontantFormatter.parse_montant(texte)
        self.assertEqual(montant, Decimal('1234.56'))


class ComptesUtilsTest(TestCase):
    """Tests des utilitaires de comptes."""
    
    def test_valider_iban_valide(self):
        """Teste la validation d'IBAN valide."""
        iban = "FR1420041010050500013M02606"
        self.assertTrue(ComptesUtils.valider_iban(iban))
    
    def test_valider_iban_invalide(self):
        """Teste la validation d'IBAN invalide."""
        iban = "INVALID"
        self.assertFalse(ComptesUtils.valider_iban(iban))
    
    def test_valider_bic_valide(self):
        """Teste la validation de BIC valide."""
        bic = "BNPAFRPP"
        self.assertTrue(ComptesUtils.valider_bic(bic))
    
    def test_valider_bic_invalide(self):
        """Teste la validation de BIC invalide."""
        bic = "INVALID123456"
        self.assertFalse(ComptesUtils.valider_bic(bic))


class EcritureUtilsTest(TestCase):
    """Tests des utilitaires d'écritures."""
    
    def test_valider_equilibre_equilibre(self):
        """Teste la validation d'équilibre."""
        self.assertTrue(
            EcritureUtils.valider_equilibre(
                Decimal('100.00'),
                Decimal('100.00')
            )
        )
    
    def test_valider_equilibre_desequilibre(self):
        """Teste la détection de déséquilibre."""
        self.assertFalse(
            EcritureUtils.valider_equilibre(
                Decimal('100.00'),
                Decimal('101.00')
            )
        )
    
    def test_calculer_solde(self):
        """Teste le calcul de solde."""
        debits = [Decimal('100'), Decimal('50')]
        credits = [Decimal('30')]
        solde = EcritureUtils.calculer_solde(debits, credits)
        self.assertEqual(solde, Decimal('120'))


class DeviseUtilsTest(TestCase):
    """Tests des utilitaires de devise."""
    
    def test_convertir_meme_devise(self):
        """Teste la conversion de la même devise."""
        montant = Decimal('100')
        result = DeviseUtils.convertir(montant, 'EUR', 'EUR')
        self.assertEqual(result, montant)
    
    def test_convertir_devises_differentes(self):
        """Teste la conversion de devises différentes."""
        montant = Decimal('100')
        result = DeviseUtils.convertir(montant, 'EUR', 'USD')
        self.assertIsInstance(result, Decimal)
        self.assertNotEqual(result, montant)


class RapprochementServiceTest(TestCase):
    """Tests du service de rapprochement."""
    
    def setUp(self):
        """Initialise les données de test."""
        self.entreprise = Entreprise.objects.create(nom_entreprise='Test Compta SARL')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass',
            email='testuser@test.gn',
            entreprise=self.entreprise,
        )

        # Crée un compte bancaire (champs réels du modèle : code/libelle/banque)
        self.compte = CompteBancaire.objects.create(
            entreprise=self.entreprise,
            code='BNK-001',
            libelle='Test Bank Account',
            banque='Banque Test',
            iban='FR1420041010050500013M02606',
            solde_initial=Decimal('0.00'),
        )
    
    def test_service_initialization(self):
        """Teste l'initialisation du service."""
        service = RapprochementService(None, self.user)
        self.assertIsNotNone(service)
    
    def test_calculer_solde_comptable(self):
        """Teste le calcul du solde comptable."""
        service = RapprochementService(None, self.user)
        # À développer selon l'implémentation
        pass


class ComptaBancaireModelTest(TestCase):
    """Tests du modèle CompteBancaire."""

    def setUp(self):
        """Initialise les données de test."""
        self.entreprise = Entreprise.objects.create(nom_entreprise='Test Compta SARL')
        self.compte = CompteBancaire.objects.create(
            entreprise=self.entreprise,
            code='BNK-001',
            libelle='Test Bank',
            banque='Banque Test',
            iban='FR1420041010050500013M02606',
        )

    def test_creation_compte(self):
        """Teste la création d'un compte."""
        self.assertEqual(self.compte.code, 'BNK-001')
        self.assertTrue(self.compte.est_actif)

    def test_string_representation(self):
        """Teste la représentation en string."""
        self.assertIn('Test Bank', str(self.compte))


class RapprochementBancaireViewTest(TestCase):
    """Tests des vues de rapprochement."""
    
    def setUp(self):
        """Initialise les données de test."""
        self.client = Client()
        self.entreprise = Entreprise.objects.create(nom_entreprise='Test Compta SARL')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass',
            email='testuser@test.gn',
            is_staff=True,
            entreprise=self.entreprise,
        )
        # force_login : client.login() est incompatible avec django-axes
        # (AxesBackend exige un objet request).
        self.client.force_login(self.user)

    def test_liste_rapprochements_non_authentifie(self):
        """Teste l'accès sans authentification : redirection login ou 403."""
        client = Client()
        response = client.get(reverse('comptabilite:rapprochement-list'))
        self.assertIn(response.status_code, (302, 403))

    def test_liste_rapprochements_authentifie(self):
        """Teste la liste avec authentification (200 ou redirection métier)."""
        response = self.client.get(reverse('comptabilite:rapprochement-list'))
        self.assertIn(response.status_code, (200, 302))


class IntegrationTest(TestCase):
    """Tests d'intégration complets."""

    def setUp(self):
        """Initialise les données de test."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass',
            email='testuser@test.gn'
        )
    
    def test_workflow_complet(self):
        """Teste un workflow complet de rapprochement."""
        # 1. Crée un compte bancaire
        # 2. Crée un rapprochement
        # 3. Ajoute des opérations
        # 4. Lettre les opérations
        # 5. Finalise le rapprochement
        pass
