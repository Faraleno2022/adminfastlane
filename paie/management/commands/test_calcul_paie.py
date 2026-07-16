"""
Script de test pour vérifier l'exactitude des calculs de paie
Conforme à la législation guinéenne 2025
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from decimal import Decimal
from paie.models import (
    PeriodePaie, BulletinPaie, RubriquePaie, ElementSalaire,
    Constante, TrancheRTS
)
from employes.models import Employe
from paie.services import MoteurCalculPaie


class Command(BaseCommand):
    help = 'Teste les calculs de paie avec des exemples concrets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--employe',
            type=str,
            help='Matricule de l\'employé à tester'
        )
        parser.add_argument(
            '--simulation',
            action='store_true',
            help='Mode simulation sans créer de bulletin'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('🧪 TEST DES CALCULS DE PAIE - GUINÉE 2025'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        # 1. Vérifier les constantes
        self.verifier_constantes()
        
        # 2. Vérifier les tranches RTS
        self.verifier_tranches_irg()
        
        # 3. Test de calcul manuel
        self.test_calcul_manuel()
        
        # 4. Test avec un employé réel si spécifié
        if options.get('employe'):
            self.test_employe_reel(options['employe'], options.get('simulation', True))
        else:
            # Tester avec le premier employé actif
            employe = Employe.objects.filter(statut_employe='actif').first()
            if employe:
                self.test_employe_reel(employe.matricule, simulation=True)
            else:
                self.stdout.write(self.style.WARNING('⚠ Aucun employé actif trouvé pour le test'))

    def verifier_constantes(self):
        """Vérifier que toutes les constantes nécessaires sont présentes"""
        self.stdout.write('\n📋 VÉRIFICATION DES CONSTANTES')
        self.stdout.write('-' * 40)
        
        constantes_requises = [
            ('TAUX_CNSS_EMPLOYE', Decimal('5.00'), '%'),
            ('TAUX_CNSS_EMPLOYEUR', Decimal('18.00'), '%'),
            ('PLAFOND_CNSS', Decimal('2500000'), 'GNF'),
            ('PLANCHER_CNSS', Decimal('550000'), 'GNF'),
            ('SMIG', Decimal('440000'), 'GNF'),
            ('DEDUC_CONJOINT', Decimal('100000'), 'GNF'),
            ('DEDUC_ENFANT', Decimal('50000'), 'GNF'),
        ]
        
        toutes_presentes = True
        for code, valeur_attendue, unite in constantes_requises:
            try:
                const = Constante.objects.get(code=code, actif=True)
                status = '✓' if const.valeur == valeur_attendue else '⚠'
                self.stdout.write(f'  {status} {code}: {const.valeur} {unite}')
                if const.valeur != valeur_attendue:
                    self.stdout.write(self.style.WARNING(f'    → Attendu: {valeur_attendue}'))
            except Constante.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'  ✗ {code}: MANQUANTE'))
                toutes_presentes = False
        
        if toutes_presentes:
            self.stdout.write(self.style.SUCCESS('  ✅ Toutes les constantes sont présentes'))

    def verifier_tranches_irg(self):
        """Vérifier les tranches RTS"""
        self.stdout.write('\n📊 VÉRIFICATION DES TRANCHES RTS 2025')
        self.stdout.write('-' * 40)
        
        tranches = TrancheRTS.objects.filter(annee_validite=2025, actif=True).order_by('numero_tranche')
        
        if not tranches.exists():
            self.stdout.write(self.style.ERROR('  ✗ Aucune tranche RTS pour 2025'))
            return
        
        for t in tranches:
            if t.borne_superieure:
                self.stdout.write(
                    f'  Tranche {t.numero_tranche}: {t.borne_inferieure:>12,.0f} - {t.borne_superieure:>12,.0f} GNF → {t.taux_irg}%'
                )
            else:
                self.stdout.write(
                    f'  Tranche {t.numero_tranche}: {t.borne_inferieure:>12,.0f} - Illimité         → {t.taux_irg}%'
                )
        
        self.stdout.write(self.style.SUCCESS(f'  ✅ {tranches.count()} tranches configurées'))

    def test_calcul_manuel(self):
        """Test de calcul manuel avec des valeurs connues"""
        self.stdout.write('\n🧮 TEST DE CALCUL MANUEL')
        self.stdout.write('-' * 40)
        
        # Exemple: Salaire brut de 2,500,000 GNF
        salaire_brut = Decimal('2500000')
        
        # 1. Calcul CNSS employé (5% avec plancher SMIG et plafond 2,500,000)
        # Règles CNSS Guinée:
        # - Plancher: SMIG (550 000 GNF) - on cotise au minimum sur ce montant
        # - Plafond: 2 500 000 GNF - on cotise au maximum sur ce montant
        plancher_cnss = Decimal('550000')  # Plancher CNSS
        plafond_cnss = Decimal('2500000')
        base_cnss = max(min(salaire_brut, plafond_cnss), plancher_cnss)
        taux_cnss_employe = Decimal('5.00')
        cnss_employe = base_cnss * taux_cnss_employe / Decimal('100')
        
        self.stdout.write(f'  Salaire brut: {salaire_brut:,.0f} GNF')
        self.stdout.write(f'  Plancher CNSS (SMIG): {plancher_cnss:,.0f} GNF')
        self.stdout.write(f'  Plafond CNSS: {plafond_cnss:,.0f} GNF')
        self.stdout.write(f'  Base CNSS (avec plancher/plafond): {base_cnss:,.0f} GNF')
        self.stdout.write(f'  CNSS employé (5%): {cnss_employe:,.0f} GNF')
        
        # 2. Calcul CNSS employeur (18%)
        taux_cnss_employeur = Decimal('18.00')
        cnss_employeur = base_cnss * taux_cnss_employeur / Decimal('100')
        self.stdout.write(f'  CNSS employeur (18%): {cnss_employeur:,.0f} GNF')
        
        # 3. Calcul RTS
        # Base RTS = Brut imposable - CNSS employé.
        # IMPORTANT (conformité moteur paie/services.py::_calculer_irg) :
        # la RTS guinéenne n'applique NI déductions familiales NI abattement
        # professionnel — ces déductions ne concernent que l'IGR annuel.
        base_imposable = salaire_brut - cnss_employe
        self.stdout.write(f'  Base imposable RTS (Brut - CNSS): {base_imposable:,.0f} GNF')

        # Calcul RTS progressif
        irg = self.calculer_irg_progressif(base_imposable)
        self.stdout.write(f'  RTS calculé: {irg:,.0f} GNF')
        
        # 4. Net à payer
        net = salaire_brut - cnss_employe - irg
        self.stdout.write(f'\n  💰 NET À PAYER: {net:,.0f} GNF')
        
        # Vérification
        self.stdout.write('\n  📝 RÉCAPITULATIF:')
        self.stdout.write(f'     Brut:           {salaire_brut:>12,.0f} GNF')
        self.stdout.write(f'     - CNSS (5%):    {cnss_employe:>12,.0f} GNF')
        self.stdout.write(f'     - RTS:          {irg:>12,.0f} GNF')
        self.stdout.write(f'     = Net:          {net:>12,.0f} GNF')
        self.stdout.write(f'     Coût employeur: {salaire_brut + cnss_employeur:>12,.0f} GNF')

    def calculer_irg_progressif(self, base_imposable):
        """Calculer l'RTS selon le barème progressif"""
        if base_imposable <= 0:
            return Decimal('0')
        
        # Barème RTS CGI 2022 officiel (6 tranches).
        # Bornes contiguës (pas de gap de 1 GNF) pour éviter qu'un franc de
        # base échappe au calcul progressif — identique à services.py.
        tranches = [
            (Decimal('0'), Decimal('1000000'), Decimal('0')),
            (Decimal('1000000'), Decimal('3000000'), Decimal('5')),
            (Decimal('3000000'), Decimal('5000000'), Decimal('8')),
            (Decimal('5000000'), Decimal('10000000'), Decimal('10')),
            (Decimal('10000000'), Decimal('20000000'), Decimal('15')),
            (Decimal('20000000'), None, Decimal('20')),
        ]
        
        irg_total = Decimal('0')
        reste = base_imposable
        
        for borne_inf, borne_sup, taux in tranches:
            if reste <= 0:
                break
            
            if borne_sup:
                montant_tranche = min(reste, borne_sup - borne_inf)
            else:
                montant_tranche = reste
            
            irg_tranche = montant_tranche * taux / Decimal('100')
            irg_total += irg_tranche
            reste -= montant_tranche
        
        return irg_total.quantize(Decimal('0.01'))

    def test_employe_reel(self, matricule, simulation=True):
        """Tester avec un employé réel"""
        self.stdout.write(f'\n👤 TEST AVEC EMPLOYÉ: {matricule}')
        self.stdout.write('-' * 40)
        
        try:
            employe = Employe.objects.get(matricule=matricule)
        except Employe.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'  ✗ Employé {matricule} non trouvé'))
            return
        
        self.stdout.write(f'  Nom: {employe.nom} {employe.prenoms}')
        self.stdout.write(f'  Situation: {employe.situation_matrimoniale or "N/A"}')
        self.stdout.write(f'  Enfants: {employe.nombre_enfants}')
        self.stdout.write(f'  Date embauche: {employe.date_embauche}')
        
        # Récupérer les éléments de salaire
        elements = ElementSalaire.objects.filter(
            employe=employe,
            actif=True
        ).select_related('rubrique')
        
        self.stdout.write(f'\n  📋 Éléments de salaire ({elements.count()}):')
        total_gains = Decimal('0')
        for elem in elements:
            if elem.rubrique.type_rubrique == 'gain':
                montant = elem.montant or Decimal('0')
                total_gains += montant
                self.stdout.write(f'     - {elem.rubrique.libelle_rubrique}: {montant:,.0f} GNF')
        
        self.stdout.write(f'     TOTAL GAINS: {total_gains:,.0f} GNF')
        
        # Créer ou récupérer une période de test
        aujourd_hui = date.today()
        periode, created = PeriodePaie.objects.get_or_create(
            annee=aujourd_hui.year,
            mois=aujourd_hui.month,
            defaults={
                'date_debut': date(aujourd_hui.year, aujourd_hui.month, 1),
                'date_fin': date(aujourd_hui.year, aujourd_hui.month, 28),
                'statut_periode': 'ouverte'
            }
        )
        
        if simulation:
            self.stdout.write(f'\n  🔄 SIMULATION (sans enregistrement):')
            moteur = MoteurCalculPaie(employe, periode)
            montants = moteur.calculer_bulletin()
            
            self.stdout.write(f'     Brut:           {montants["brut"]:>12,.0f} GNF')
            self.stdout.write(f'     Base CNSS:      {montants["cnss_base"]:>12,.0f} GNF')
            self.stdout.write(f'     CNSS employé:   {montants["cnss_employe"]:>12,.0f} GNF')
            self.stdout.write(f'     CNSS employeur: {montants["cnss_employeur"]:>12,.0f} GNF')
            self.stdout.write(f'     RTS:            {montants["irg"]:>12,.0f} GNF')
            self.stdout.write(f'     Total retenues: {montants["total_retenues"]:>12,.0f} GNF')
            self.stdout.write(self.style.SUCCESS(f'     NET À PAYER:    {montants["net"]:>12,.0f} GNF'))
        else:
            self.stdout.write(f'\n  📝 GÉNÉRATION DU BULLETIN:')
            moteur = MoteurCalculPaie(employe, periode)
            bulletin = moteur.generer_bulletin()
            self.stdout.write(self.style.SUCCESS(f'     ✅ Bulletin {bulletin.numero_bulletin} créé'))
            self.stdout.write(f'     Net à payer: {bulletin.net_a_payer:,.0f} GNF')
