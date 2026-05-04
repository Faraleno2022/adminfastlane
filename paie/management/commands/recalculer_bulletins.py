"""
Commande pour recalculer les bulletins de paie en production.
Applique les nouvelles constantes CNSS (plancher/plafond).

Usage:
    # Recalculer tous les bulletins d'une période
    python manage.py recalculer_bulletins --periode 12 --annee 2025
    
    # Recalculer un bulletin spécifique
    python manage.py recalculer_bulletins --bulletin BUL-2025-12-0004
    
    # Recalculer tous les bulletins non clôturés
    python manage.py recalculer_bulletins --non-clotures
    
    # Mode simulation (affiche sans modifier)
    python manage.py recalculer_bulletins --periode 12 --annee 2025 --dry-run
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from paie.models import BulletinPaie, PeriodePaie, Constante
from paie.services import MoteurCalculPaie


class Command(BaseCommand):
    help = 'Recalcule les bulletins de paie avec les nouvelles constantes CNSS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--periode', '-p',
            type=int,
            help='Mois de la période (1-12)'
        )
        parser.add_argument(
            '--annee', '-a',
            type=int,
            help='Année de la période'
        )
        parser.add_argument(
            '--bulletin', '-b',
            type=str,
            help='Numéro de bulletin spécifique (ex: BUL-2025-12-0004)'
        )
        parser.add_argument(
            '--non-clotures',
            action='store_true',
            help='Recalculer tous les bulletins des périodes non clôturées'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mode simulation - affiche les changements sans les appliquer'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forcer le recalcul même pour les bulletins validés/payés'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('=' * 60))
        self.stdout.write(self.style.NOTICE('RECALCUL DES BULLETINS DE PAIE'))
        self.stdout.write(self.style.NOTICE('=' * 60))
        
        # Afficher les constantes CNSS actuelles
        self._afficher_constantes()
        
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nMODE SIMULATION - Aucune modification ne sera effectuee\n'))
        
        # Récupérer les bulletins à recalculer
        bulletins = self._get_bulletins(options)
        
        if not bulletins.exists():
            self.stdout.write(self.style.WARNING('Aucun bulletin trouvé avec ces critères.'))
            return
        
        self.stdout.write(f'\n{bulletins.count()} bulletin(s) a recalculer\n')
        
        # Recalculer chaque bulletin
        total_modifies = 0
        total_erreurs = 0
        
        for bulletin in bulletins:
            try:
                modifie = self._recalculer_bulletin(bulletin, dry_run, force)
                if modifie:
                    total_modifies += 1
            except Exception as e:
                total_erreurs += 1
                self.stdout.write(self.style.ERROR(f'  ERREUR {bulletin.numero_bulletin}: {e}'))
        
        # Résumé
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'{total_modifies} bulletin(s) {"seraient modifie(s)" if dry_run else "modifie(s)"}'))
        if total_erreurs:
            self.stdout.write(self.style.ERROR(f'{total_erreurs} erreur(s)'))
        self.stdout.write('=' * 60)

    def _afficher_constantes(self):
        """Affiche les constantes CNSS actuelles"""
        self.stdout.write('\nCONSTANTES CNSS ACTUELLES:')
        self.stdout.write('-' * 40)
        
        constantes = ['PLANCHER_CNSS', 'PLAFOND_CNSS', 'TAUX_CNSS_EMPLOYE', 'TAUX_CNSS_EMPLOYEUR']
        for code in constantes:
            const = Constante.objects.filter(code=code, actif=True).first()
            if const:
                self.stdout.write(f'  {code}: {const.valeur:,.0f} {const.unite}')
            else:
                self.stdout.write(self.style.WARNING(f'  {code}: Non defini'))

    def _get_bulletins(self, options):
        """Récupère les bulletins selon les options"""
        bulletins = BulletinPaie.objects.select_related('employe', 'periode')
        
        if options.get('bulletin'):
            bulletins = bulletins.filter(numero_bulletin=options['bulletin'])
        elif options.get('periode') and options.get('annee'):
            bulletins = bulletins.filter(
                periode__mois=options['periode'],
                periode__annee=options['annee']
            )
        elif options.get('non_clotures'):
            bulletins = bulletins.filter(
                periode__statut_periode__in=['brouillon', 'en_cours', 'validee']
            )
        else:
            self.stdout.write(self.style.ERROR(
                'Spécifiez --periode et --annee, --bulletin, ou --non-clotures'
            ))
            return BulletinPaie.objects.none()
        
        return bulletins.order_by('numero_bulletin')

    def _recalculer_bulletin(self, bulletin, dry_run=False, force=False):
        """Recalcule un bulletin individuel"""
        # Vérifier si le bulletin peut être modifié
        if bulletin.statut_bulletin in ['paye'] and not force:
            self.stdout.write(self.style.WARNING(
                f'  {bulletin.numero_bulletin} - Ignore (statut: {bulletin.statut_bulletin})'
            ))
            return False
        
        # Sauvegarder les anciennes valeurs
        ancien_cnss_employe = bulletin.cnss_employe
        ancien_cnss_employeur = bulletin.cnss_employeur
        ancien_net = bulletin.net_a_payer
        ancien_vf = bulletin.versement_forfaitaire
        ancien_ta = bulletin.taxe_apprentissage
        ancien_onfpp = bulletin.contribution_onfpp
        ancien_total_pat = bulletin.total_charges_patronales
        
        # Recalculer avec le moteur de paie
        moteur = MoteurCalculPaie(bulletin.employe, bulletin.periode)
        nouveaux_montants = moteur.calculer_bulletin()
        
        # Calculer les différences
        diff_cnss_employe = nouveaux_montants['cnss_employe'] - ancien_cnss_employe
        diff_cnss_employeur = nouveaux_montants['cnss_employeur'] - ancien_cnss_employeur
        nouveau_net = nouveaux_montants['net']
        diff_net = nouveau_net - ancien_net
        diff_vf = nouveaux_montants['versement_forfaitaire'] - ancien_vf
        diff_ta = nouveaux_montants['taxe_apprentissage'] - ancien_ta
        diff_onfpp = nouveaux_montants['contribution_onfpp'] - ancien_onfpp
        diff_total_pat = nouveaux_montants['total_charges_patronales'] - ancien_total_pat
        
        # Afficher les changements
        self.stdout.write(f'\n  {bulletin.numero_bulletin} - {bulletin.employe}')
        self.stdout.write(f'     Brut: {bulletin.salaire_brut:,.0f} GNF')
        
        if (
            diff_cnss_employe != 0 or diff_cnss_employeur != 0
            or diff_vf != 0 or diff_ta != 0 or diff_onfpp != 0
            or diff_total_pat != 0
        ):
            self.stdout.write(f'     CNSS Employe: {ancien_cnss_employe:,.0f} -> {nouveaux_montants["cnss_employe"]:,.0f} ({diff_cnss_employe:+,.0f})')
            self.stdout.write(f'     CNSS Employeur: {ancien_cnss_employeur:,.0f} -> {nouveaux_montants["cnss_employeur"]:,.0f} ({diff_cnss_employeur:+,.0f})')
            self.stdout.write(f'     Net a payer: {ancien_net:,.0f} -> {nouveau_net:,.0f} ({diff_net:+,.0f})')
            
            if not dry_run:
                with transaction.atomic():
                    bulletin.cnss_employe = nouveaux_montants['cnss_employe']
                    bulletin.cnss_employeur = nouveaux_montants['cnss_employeur']
                    bulletin.irg = nouveaux_montants['irg']
                    bulletin.net_a_payer = nouveaux_montants['net']
                    bulletin.base_vf = nouveaux_montants['base_vf']
                    bulletin.versement_forfaitaire = nouveaux_montants['versement_forfaitaire']
                    bulletin.taxe_apprentissage = nouveaux_montants['taxe_apprentissage']
                    bulletin.taux_ta = nouveaux_montants['taux_ta']
                    bulletin.contribution_onfpp = nouveaux_montants['contribution_onfpp']
                    bulletin.save()
                self.stdout.write(self.style.SUCCESS('     Mis a jour'))
            else:
                self.stdout.write(self.style.WARNING('     Serait mis a jour (dry-run)'))
            
            return True
        else:
            self.stdout.write(self.style.SUCCESS('     Deja correct'))
            return False
