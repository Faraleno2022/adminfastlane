from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from paie.views_rapports import (
    _calcul_rapport,
    _determiner_salaire_base_etat_paie,
)


class RapportMasseSalarialeTests(SimpleTestCase):
    def test_cout_moyen_utilise_cout_employeur_et_employes_distincts(self):
        bulletins = Mock()
        bulletins.aggregate.return_value = {
            'nb': 4,
            'nb_employes': 2,
            'brut': Decimal('4000'),
            'cnss_sal': Decimal('200'),
            'cnss_emp': Decimal('720'),
            'rts': Decimal('100'),
            'net': Decimal('3700'),
            'vf': Decimal('240'),
            'ta': Decimal('0'),
            'onfpp': Decimal('60'),
        }

        resultat = _calcul_rapport(bulletins)

        self.assertEqual(resultat['cout_employeur'], Decimal('5020'))
        self.assertEqual(resultat['cout_moyen'], Decimal('2510'))
        self.assertEqual(resultat['nb_employes'], 2)


class EtatPaieSalaireBaseTests(SimpleTestCase):
    def test_reconstitue_base_depuis_brut_et_autres_gains_historiques(self):
        bulletin = SimpleNamespace(
            salaire_base=Decimal('0'),
            salaire_brut=Decimal('1000'),
        )

        resultat = _determiner_salaire_base_etat_paie(
            bulletin,
            base_lignes=Decimal('0'),
            gains_hors_base=Decimal('250'),
        )

        self.assertEqual(resultat, Decimal('750'))

    def test_prefere_base_figee_sur_bulletin(self):
        bulletin = SimpleNamespace(
            salaire_base=Decimal('800'),
            salaire_brut=Decimal('1000'),
        )

        resultat = _determiner_salaire_base_etat_paie(
            bulletin,
            base_lignes=Decimal('700'),
            gains_hors_base=Decimal('250'),
        )

        self.assertEqual(resultat, Decimal('800'))
