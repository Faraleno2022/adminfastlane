from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Entreprise
from employes.models import Employe
from paie.models import BulletinPaie, PeriodePaie
from .models import Contrat, TypeContrat
from .services_stc import calculer_solde_tout_compte


class SoldeToutCompteTests(TestCase):
    def setUp(self):
        self.entreprise = Entreprise.objects.create(
            nom_entreprise='STC SARL', slug='stc-sarl', email='stc@example.com')
        self.employe = Employe.objects.create(
            entreprise=self.entreprise, matricule='STC-001', nom='Test', prenoms='CDD',
            statut_employe='actif', date_embauche=date(2026, 1, 1))
        self.type_cdd = TypeContrat.objects.create(
            entreprise=self.entreprise, nom='CDD test', categorie='cdd')
        self.contrat = Contrat.objects.create(
            employe=self.employe, type_contrat=self.type_cdd, numero_contrat='CDD-001',
            date_debut=date(2026, 1, 1), date_fin=date(2026, 3, 15),
            salaire_base=Decimal('1000000'))

    def _bulletin(self, mois, brut):
        debut = date(2026, mois, 1)
        periode = PeriodePaie.objects.create(
            entreprise=self.entreprise, annee=2026, mois=mois,
            libelle=f'{mois}/2026', date_debut=debut,
            date_fin=date(2026, mois, monthrange(2026, mois)[1]),
            statut_periode='ouverte')
        return BulletinPaie.objects.create(
            employe=self.employe, periode=periode,
            numero_bulletin=f'B-{mois}', mois_paie=mois, annee_paie=2026,
            salaire_brut=Decimal(brut), statut_bulletin='valide')

    def test_duree_partielle_est_proratisee_sans_bulletin(self):
        resultat = calculer_solde_tout_compte(self.contrat)
        self.assertEqual(resultat['duree_mois'], Decimal('2.47'))
        self.assertEqual(resultat['remuneration_totale'], Decimal('2470000.00'))

    def test_remuneration_reelle_somme_les_bulletins_valides(self):
        self._bulletin(1, '900000')
        self._bulletin(2, '1100000')
        resultat = calculer_solde_tout_compte(self.contrat)
        self.assertEqual(resultat['salaire_mensuel'], Decimal('1100000'))
        self.assertEqual(resultat['remuneration_totale'], Decimal('2000000'))
        self.assertEqual(resultat['indemnite_fin_cdd'], Decimal('140000'))
