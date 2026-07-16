from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from dashboard.views import (
    _build_paie_totaux_context,
    _build_repartition_service_paie,
    _build_risque_fiscal_paie,
)


class DashboardPaieTotauxTests(SimpleTestCase):
    def test_totaux_paie_dashboard_utilisent_les_montants_bulletins(self):
        context = _build_paie_totaux_context({
            'brut': Decimal('247628100'),
            'net': Decimal('201392500'),
            'base_vf': Decimal('247628100'),
            'trs': Decimal('20413988'),
            'vf': Decimal('14857686'),
            'ta': Decimal('0'),
            'onfpp': Decimal('3714422'),
            'cnss_5': Decimal('3125000'),
            'cnss_18': Decimal('11250000'),
        })

        self.assertEqual(context['salaire_brut'], Decimal('247628100'))
        self.assertEqual(context['masse_salariale'], Decimal('277450208'))
        self.assertEqual(context['total_net_a_payer'], Decimal('201392500'))
        self.assertEqual(context['total_cnss_23'], Decimal('14375000'))
        self.assertEqual(context['total_declaration_sociale'], Decimal('14375000'))
        self.assertEqual(context['total_dmu'], Decimal('35271674'))
        self.assertEqual(context['total_etax'], Decimal('35271674'))

    def test_risque_fiscal_detecte_ecart_onfpp(self):
        bulletin = SimpleNamespace(
            salaire_brut=Decimal('10000000'),
            base_rts=Decimal('7500000'),
            base_vf=Decimal('9850000'),
            abattement_forfaitaire=Decimal('2300000'),
            cnss_employe=Decimal('125000'),
            cnss_employeur=Decimal('450000'),
            versement_forfaitaire=Decimal('591000'),
            taxe_apprentissage=Decimal('0'),
            contribution_onfpp=Decimal('150000'),  # ancienne base brut au lieu de base VF
        )

        risque = _build_risque_fiscal_paie([bulletin], effectif_total=30)

        self.assertEqual(risque['bulletins'], 1)
        self.assertGreater(risque['score'], 0)
        self.assertEqual(risque['controles'][5]['valeur'], 1)

    def test_risque_fiscal_ne_rougit_pas_un_profil_indemnitaire_conforme(self):
        bulletin = SimpleNamespace(
            salaire_brut=Decimal('10000000'),
            base_rts=Decimal('7500000'),
            base_vf=Decimal('7500000'),
            abattement_forfaitaire=Decimal('2500000'),
            cnss_employe=Decimal('125000'),
            cnss_employeur=Decimal('450000'),
            versement_forfaitaire=Decimal('450000'),
            taxe_apprentissage=Decimal('0'),
            contribution_onfpp=Decimal('112500'),
        )

        risque = _build_risque_fiscal_paie([bulletin], effectif_total=30)

        self.assertNotEqual(risque['niveau'], 'Rouge')
        self.assertEqual(risque['controles'][2]['valeur'], 1)
        self.assertEqual(risque['controles'][5]['valeur'], 0)

    def test_repartition_service_paie_agrege_les_charges_reelles(self):
        service = SimpleNamespace(pk=1, nom_service='Administration')
        employe = SimpleNamespace(service=service, sexe='F')
        bulletin = SimpleNamespace(
            employe=employe,
            salaire_brut=Decimal('10000000'),
            abattement_forfaitaire=Decimal('2500000'),
            net_a_payer=Decimal('9400000'),
            cnss_employe=Decimal('125000'),
            cnss_employeur=Decimal('450000'),
            irg=Decimal('475000'),
            versement_forfaitaire=Decimal('591000'),
            taxe_apprentissage=Decimal('0'),
            contribution_onfpp=Decimal('147750'),
        )

        lignes = _build_repartition_service_paie([bulletin], effectif_total=30)

        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]['nom'], 'Administration')
        self.assertEqual(lignes[0]['effectif'], 1)
        self.assertEqual(lignes[0]['onfpp'], Decimal('147750'))
        self.assertEqual(lignes[0]['masse_salariale'], Decimal('11188750'))
