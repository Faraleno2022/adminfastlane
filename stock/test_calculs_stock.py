from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Entreprise
from stock.models import (
    Article,
    CategorieArticle,
    Client,
    Depot,
    DocumentVente,
    LigneVente,
    MouvementStock,
    StockArticleDepot,
)
from stock.serializers import MouvementCreateSerializer
from stock.views import appliquer_mouvement_depot, maj_cmup


class CalculsStockTest(TestCase):
    def setUp(self):
        self.entreprise = Entreprise.objects.create(nom_entreprise='Stock Test')
        self.categorie = CategorieArticle.objects.create(
            entreprise=self.entreprise, nom='Produits'
        )
        self.depot = Depot.objects.create(entreprise=self.entreprise, nom='Principal')
        self.article = Article.objects.create(
            entreprise=self.entreprise,
            categorie=self.categorie,
            reference='ART-CALC',
            designation='Article calcul',
            prix_achat=Decimal('80.00'),
            cmup=Decimal('100.00'),
        )
        StockArticleDepot.objects.create(
            article=self.article, depot=self.depot, quantite=Decimal('10.00')
        )
        self.article.recalculer_total()

    def test_cmup_apres_entree(self):
        maj_cmup(
            self.article,
            quantite_entree=Decimal('5.00'),
            prix_unitaire=Decimal('130.00'),
            stock_avant=Decimal('10.00'),
        )
        self.article.refresh_from_db()
        self.assertEqual(self.article.cmup, Decimal('110.00'))

    def test_sortie_ne_peut_pas_rendre_stock_negatif(self):
        with self.assertRaises(ValueError):
            appliquer_mouvement_depot(
                self.article, self.depot, 'sortie', Decimal('11.00')
            )
        self.assertEqual(self.article.stock_dans(self.depot), Decimal('10.00'))

    def test_ajustement_retourne_stock_final_et_ecart_signe(self):
        avant, apres = appliquer_mouvement_depot(
            self.article, self.depot, 'ajustement', Decimal('7.00')
        )
        ecart = apres - avant
        mouvement = MouvementStock.objects.create(
            entreprise=self.entreprise,
            article=self.article,
            depot=self.depot,
            type_mouvement='ajustement',
            quantite=ecart,
            quantite_avant=avant,
            quantite_apres=apres,
            prix_unitaire=self.article.cout_unitaire,
        )
        self.assertEqual((avant, apres, ecart), (
            Decimal('10.00'), Decimal('7.00'), Decimal('-3.00')
        ))
        self.assertEqual(mouvement.valeur, Decimal('-300.0000'))

    def test_api_refuse_quantite_nulle_hors_ajustement(self):
        for type_mouvement in ('entree', 'sortie'):
            serializer = MouvementCreateSerializer(data={
                'article': self.article.pk,
                'depot': self.depot.pk,
                'type_mouvement': type_mouvement,
                'quantite': '0',
            })
            self.assertFalse(serializer.is_valid())
            self.assertIn('quantite', serializer.errors)

        serializer = MouvementCreateSerializer(data={
            'article': self.article.pk,
            'depot': self.depot.pk,
            'type_mouvement': 'ajustement',
            'quantite': '0',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)


class PourcentagesStockTest(TestCase):
    def setUp(self):
        self.entreprise = Entreprise.objects.create(nom_entreprise='Pourcentages Test')
        self.client = Client.objects.create(entreprise=self.entreprise, nom='Client')
        self.article = Article.objects.create(
            entreprise=self.entreprise, reference='ART-PCT', designation='Article'
        )

    def test_remises_et_tva_sont_bornees(self):
        self.client.remise_defaut = Decimal('101')
        with self.assertRaises(ValidationError):
            self.client.full_clean()

        document = DocumentVente(
            entreprise=self.entreprise,
            type_document='facture',
            reference='FAC-PCT',
            client=self.client,
            remise_globale_pct=Decimal('-1'),
            taux_tva=Decimal('101'),
        )
        with self.assertRaises(ValidationError) as contexte:
            document.full_clean()
        self.assertIn('remise_globale_pct', contexte.exception.message_dict)
        self.assertIn('taux_tva', contexte.exception.message_dict)

        document.remise_globale_pct = Decimal('0')
        document.taux_tva = Decimal('18')
        document.save()
        ligne = LigneVente(
            document=document,
            article=self.article,
            quantite=Decimal('1'),
            prix_unitaire=Decimal('100'),
            remise_pct=Decimal('101'),
        )
        with self.assertRaises(ValidationError):
            ligne.full_clean()

