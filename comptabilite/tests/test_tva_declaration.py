"""
Tests du recalcul des totaux d'une déclaration TVA.

Vérifie que le service écrit bien les VRAIS champs du modèle DeclarationTVA
(montant_ht, montant_tva_collecte, montant_tva_deductible, montant_tva_due)
et que les valeurs persistent après rechargement depuis la base — les vues
écrivaient auparavant des attributs inexistants (montant_total_*) que Django
acceptait silencieusement sans jamais les enregistrer.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Entreprise, Utilisateur
from comptabilite.models import (
    ExerciceComptable, RegimeTVA, TauxTVA, DeclarationTVA, LigneDeclarationTVA,
)
from comptabilite.services.calcul_tva_service import CalculTVAService
from comptabilite.services.fiscalite_service import FiscaliteService


class DeclarationTVATotauxTest(TestCase):

    def setUp(self):
        self.entreprise = Entreprise.objects.create(nom_entreprise='ACME Guinée')
        self.user = Utilisateur.objects.create_user(
            username='comptable1', password='pass12345',
            email='comptable1@test.gn', entreprise=self.entreprise)
        self.exercice = ExerciceComptable.objects.create(
            entreprise=self.entreprise, libelle='Exercice 2026',
            date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31), statut='ouvert')
        self.regime = RegimeTVA.objects.create(
            entreprise=self.entreprise, code='GN_NORMAL', nom='Régime normal Guinée',
            regime='NORMAL', taux_normal=Decimal('18.00'), date_debut=date(2026, 1, 1),
            utilisateur_creation=self.user, utilisateur_modification=self.user)
        self.taux = TauxTVA.objects.create(
            regime_tva=self.regime, code='TVA_18', nom='TVA 18%',
            taux=Decimal('18.00'), nature='VENTE', date_debut=date(2026, 1, 1))
        self.declaration = DeclarationTVA.objects.create(
            entreprise=self.entreprise, regime_tva=self.regime, exercice=self.exercice,
            periode_debut=date(2026, 7, 1), periode_fin=date(2026, 7, 31),
            statut='BROUILLON',
            utilisateur_creation=self.user, utilisateur_modification=self.user)

    def _ligne(self, numero, ht, tva, sens):
        return LigneDeclarationTVA.objects.create(
            declaration=self.declaration, numero_ligne=numero,
            description=f'Ligne {numero}', taux=self.taux,
            montant_ht=Decimal(ht), montant_tva=Decimal(tva), sens=sens)

    def test_totaux_ecrits_dans_les_vrais_champs_et_persistes(self):
        # 2 lignes collectées (ventes) + 1 ligne déductible (achats)
        self._ligne(1, '100000', '18000', 'COLLECTEE')
        self._ligne(2, '200000', '36000', 'COLLECTEE')
        self._ligne(3, '50000', '9000', 'DEDUCTIBLE')

        service = CalculTVAService(self.user)
        montants = service.appliquer_montants_declaration(self.declaration)

        self.assertEqual(montants['montant_ht'], Decimal('350000'))
        self.assertEqual(montants['montant_tva_collecte'], Decimal('54000'))
        self.assertEqual(montants['montant_tva_deductible'], Decimal('9000'))
        self.assertEqual(montants['montant_tva_due'], Decimal('45000'))

        # Point clé : recharger depuis la base — les totaux doivent avoir été
        # enregistrés dans les champs réels du modèle, pas dans des attributs
        # dynamiques perdus à la fin de la requête.
        rechargee = DeclarationTVA.objects.get(pk=self.declaration.pk)
        self.assertEqual(rechargee.montant_ht, Decimal('350000'))
        self.assertEqual(rechargee.montant_tva_collecte, Decimal('54000'))
        self.assertEqual(rechargee.montant_tva_deductible, Decimal('9000'))
        self.assertEqual(rechargee.montant_tva_due, Decimal('45000'))

    def test_declaration_sans_ligne_totaux_zero(self):
        service = CalculTVAService(self.user)
        service.appliquer_montants_declaration(self.declaration)
        rechargee = DeclarationTVA.objects.get(pk=self.declaration.pk)
        self.assertEqual(rechargee.montant_ht, Decimal('0.00'))
        self.assertEqual(rechargee.montant_tva_due, Decimal('0.00'))

    def test_calcul_tva_depuis_regime_reel(self):
        """Le calcul depuis un régime (Decimal) ne renvoie plus un dict vide."""
        service = CalculTVAService(self.user)
        r = service.calculer_tva_depuis_regime(Decimal('100000'), self.regime)
        self.assertEqual(r['montant_tva'], Decimal('18000.00'))
        self.assertEqual(r['montant_ttc'], Decimal('118000.00'))

    def test_calcul_ht_accepte_taux_cent_pour_cent(self):
        service = CalculTVAService(self.user)
        self.assertEqual(
            service.calculer_ht(Decimal('200.00'), Decimal('100')),
            Decimal('100.00'))

    def test_calcul_ttc_refuse_taux_superieur_a_cent(self):
        service = CalculTVAService(self.user)
        self.assertEqual(
            service.calculer_ttc(Decimal('100.00'), Decimal('101')),
            Decimal('0.00'))

    def test_calcul_ttc_refuse_montant_negatif(self):
        service = CalculTVAService(self.user)
        self.assertEqual(
            service.calculer_ttc(Decimal('-100.00'), Decimal('18')),
            Decimal('0.00'))

    def test_arrondi_tva_montant_limite_half_up(self):
        service = CalculTVAService(self.user)
        self.assertEqual(
            service.calculer_tva(Decimal('0.005'), Decimal('100')),
            Decimal('0.01'))

    def test_ancien_service_fiscal_utilise_le_sens_des_lignes(self):
        # Le taux est volontairement applicable aux ventes ET aux achats :
        # seule la colonne sens doit décider de la répartition.
        self._ligne(1, '100000', '18000', 'COLLECTEE')
        self._ligne(2, '50000', '9000', 'DEDUCTIBLE')
        montants = FiscaliteService(self.user).calculer_montants_declaration(self.declaration)
        self.assertEqual(montants['montant_tva_collecte'], Decimal('18000'))
        self.assertEqual(montants['montant_tva_deductible'], Decimal('9000'))
        self.assertEqual(montants['montant_tva_due'], Decimal('9000'))
