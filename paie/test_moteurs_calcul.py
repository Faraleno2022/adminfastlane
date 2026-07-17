from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from paie.services_retropaie import (
    _net_depuis_brut,
    retropaie_net_vers_brut,
)
from paie.services_simulation import (
    BAREME_CGI_REFERENCE,
    calculer_un_bareme,
    simuler_multi_baremes,
)


CONSTANTES = {
    'PLANCHER_CNSS': Decimal('550000'),
    'PLAFOND_CNSS': Decimal('2500000'),
    'TAUX_CNSS_EMPLOYE': Decimal('5'),
    'TAUX_CNSS_EMPLOYEUR': Decimal('18'),
    'TAUX_VF': Decimal('6'),
    'TAUX_TA': Decimal('2'),
    'TAUX_ONFPP': Decimal('1.5'),
    'SEUIL_TA_ONFPP': Decimal('30'),
}

TRANCHES_RETRO = [
    {
        'borne_inferieure': tranche['borne_inf'],
        'borne_superieure': tranche['borne_sup'],
        'taux_irg': tranche['taux'],
    }
    for tranche in BAREME_CGI_REFERENCE
]


class RetropaieRobustesseTests(SimpleTestCase):
    @patch(
        'paie.cache_service.PayrollCacheService.get_tranches_rts',
        return_value=TRANCHES_RETRO,
    )
    @patch(
        'paie.cache_service.PayrollCacheService.get_constantes',
        return_value=CONSTANTES,
    )
    def test_retropaie_choisit_le_brut_minimal_sous_seuil_cnss(
        self, _constantes, _tranches
    ):
        resultat = retropaie_net_vers_brut(Decimal('40000'), annee=2026)

        self.assertEqual(resultat['brut'], Decimal('40000'))
        self.assertEqual(resultat['net_calcule'], Decimal('40000'))
        self.assertTrue(resultat['ok'])

    def test_pourcentage_indemnites_negatif_est_ramene_a_zero(self):
        negatif = _net_depuis_brut(
            Decimal('6000000'), CONSTANTES, TRANCHES_RETRO, Decimal('-10')
        )
        zero = _net_depuis_brut(
            Decimal('6000000'), CONSTANTES, TRANCHES_RETRO, Decimal('0')
        )

        self.assertEqual(negatif, zero)


class SimulationHistoriqueTests(SimpleTestCase):
    @patch('paie.services_simulation._charger_constantes', return_value=CONSTANTES)
    def test_simulation_charge_constantes_a_date_du_bareme(self, charger):
        simuler_multi_baremes(
            Decimal('6000000'),
            Decimal('1500000'),
            ['fallback'],
            annee_ref=2024,
            nb_salaries=30,
        )

        charger.assert_called_once_with(date(2024, 1, 1))

    def test_simulation_et_retropaie_restent_identiques(self):
        simulation = calculer_un_bareme(
            Decimal('6000000'),
            Decimal('1500000'),
            BAREME_CGI_REFERENCE,
            CONSTANTES,
            nb_salaries=30,
        )
        retro = _net_depuis_brut(
            Decimal('6000000'),
            CONSTANTES,
            TRANCHES_RETRO,
            Decimal('25'),
        )

        self.assertEqual(simulation['net'], int(retro[0]))
        self.assertEqual(simulation['cnss'], int(retro[1]))
        self.assertEqual(simulation['base_rts'], int(retro[3]))
        self.assertEqual(simulation['rts'], int(retro[4]))
