from decimal import Decimal

from django.test import SimpleTestCase

from .models import Conge, HeureSupplementaire, SoldeConge


class ReglesRessourcesHumainesTests(SimpleTestCase):
    def test_codes_conges_utilises_par_le_portail_existent(self):
        types = dict(Conge.TYPES)
        statuts = dict(Conge.STATUTS)
        self.assertIn('annuel', types)
        self.assertIn('rejete', statuts)

    def test_soldes_conges_par_defaut_sont_unifies_a_trente_jours(self):
        solde = SoldeConge()
        self.assertEqual(solde.conges_acquis, Decimal('30.00'))
        self.assertEqual(solde.conges_restants, Decimal('30.00'))

    def test_taux_hs_correspondent_aux_choix_du_formulaire(self):
        attendus = {
            'jour_30': Decimal('30'),
            'jour_60': Decimal('60'),
            'nuit_20': Decimal('20'),
            'ferie_60': Decimal('60'),
            'ferie_nuit_100': Decimal('100'),
        }
        self.assertEqual(set(dict(HeureSupplementaire.TYPES_HS)), set(attendus))
        for code, taux in attendus.items():
            self.assertEqual(HeureSupplementaire.get_taux_majoration(code), taux)
