"""
Seed des constantes de paie légales (CGI Guinée) dans la table `Constante`.

Idempotent : utilise update_or_create sur le `code`. Relancer la commande
met à jour les valeurs sans créer de doublons.

NB: PLANCHER_CNSS / PLAFOND_CNSS / TAUX_CNSS_EMPLOYE / TAUX_CNSS_EMPLOYEUR sont
verrouillés à l'exécution par appliquer_constantes_cnss_legales() (CNSS_LEGALE),
mais on les enregistre quand même pour qu'ils soient visibles/éditables dans l'UI
et cohérents avec le moteur.

Usage:
    python manage.py seed_constantes
    python manage.py seed_constantes --force   # réécrit même les valeurs existantes
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from paie.models import Constante


# (code, libelle, valeur, type_valeur, categorie, unite)
CONSTANTES = [
    # --- CNSS (taux légaux verrouillés par CNSS_LEGALE) ---
    ('PLANCHER_CNSS',        'Plancher CNSS (assiette minimale = SMIG)', Decimal('550000'),  'montant',     'cnss',    'GNF'),
    ('PLAFOND_CNSS',         'Plafond CNSS (assiette maximale)',         Decimal('2500000'), 'montant',     'cnss',    'GNF'),
    ('TAUX_CNSS_EMPLOYE',    'Taux CNSS part salariale',                 Decimal('5'),       'pourcentage', 'cnss',    '%'),
    ('TAUX_CNSS_EMPLOYEUR',  'Taux CNSS part patronale',                 Decimal('18'),      'pourcentage', 'cnss',    '%'),
    ('SMIG',                 'Salaire Minimum Interprofessionnel Garanti', Decimal('440000'), 'montant',    'general', 'GNF'),

    # --- Charges patronales VF / TA / ONFPP ---
    ('TAUX_VF',              'Versement Forfaitaire (charge patronale)', Decimal('6'),       'pourcentage', 'general', '%'),
    ('SEUIL_TA_ONFPP',      'Seuil effectif TA(<) vs ONFPP(>=)',         Decimal('30'),      'nombre',      'general', 'salariés'),

    # --- Déductions familiales (IGR annuel) ---
    ('DEDUC_CONJOINT',       'Déduction familiale conjoint à charge',    Decimal('100000'),  'montant',     'irg',     'GNF'),
    ('DEDUC_ENFANT',         'Déduction familiale par enfant à charge',  Decimal('50000'),   'montant',     'irg',     'GNF'),
    ('MAX_ENFANTS_DEDUC',    "Nombre maximum d'enfants déductibles",     Decimal('4'),       'nombre',      'irg',     'enfants'),

    # --- Abattement professionnel (IGR) ---
    ('TAUX_ABATTEMENT_PRO',  'Taux abattement professionnel',            Decimal('5'),       'pourcentage', 'irg',     '%'),
    ('PLAFOND_ABATTEMENT_PRO', 'Plafond abattement professionnel',       Decimal('1000000'), 'montant',     'irg',     'GNF'),

    # --- Exonération RTS stagiaires / apprentis ---
    ('SEUIL_EXON_STAGIAIRE', 'Seuil indemnité exonérée RTS stagiaire/apprenti', Decimal('1200000'), 'montant', 'irg', 'GNF'),

    # --- Heures supplémentaires (coefficients = 100% + majoration) ---
    ('TAUX_HS_4PREM',        'Coefficient HS 4 premières heures (+30%)', Decimal('130'),     'pourcentage', 'temps',   '%'),
    ('TAUX_HS_AUDELA',       'Coefficient HS au-delà de 4h (+60%)',      Decimal('160'),     'pourcentage', 'temps',   '%'),
    ('TAUX_HS_NUIT',         'Coefficient HS nuit 20h-6h (+20%)',        Decimal('120'),     'pourcentage', 'temps',   '%'),
    ('TAUX_HS_FERIE_JOUR',   'Coefficient HS férié/dimanche jour (+60%)', Decimal('160'),    'pourcentage', 'temps',   '%'),
    ('TAUX_HS_FERIE_NUIT',   'Coefficient HS férié nuit (+100%)',        Decimal('200'),     'pourcentage', 'temps',   '%'),
]


class Command(BaseCommand):
    help = "Crée/met à jour les constantes de paie légales (CGI Guinée) dans la table Constante."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help="Réécrit la valeur des constantes déjà présentes (sinon ne touche que libellé/méta)."
        )

    def handle(self, *args, **options):
        force = options['force']
        debut = date(date.today().year, 1, 1)

        crees, maj, inchanges = 0, 0, 0
        for code, libelle, valeur, type_valeur, categorie, unite in CONSTANTES:
            defaults = {
                'libelle': libelle,
                'type_valeur': type_valeur,
                'categorie': categorie,
                'unite': unite,
                'actif': True,
            }
            existing = Constante.objects.filter(code=code).first()
            if existing is None:
                Constante.objects.create(
                    code=code, valeur=valeur,
                    date_debut_validite=debut, **defaults
                )
                crees += 1
                self.stdout.write(self.style.SUCCESS(f"  + {code} = {valeur} {unite}"))
            else:
                changed = False
                for k, v in defaults.items():
                    if getattr(existing, k) != v:
                        setattr(existing, k, v)
                        changed = True
                if force and existing.valeur != valeur:
                    existing.valeur = valeur
                    changed = True
                if changed:
                    existing.save()
                    maj += 1
                    self.stdout.write(self.style.WARNING(f"  ~ {code} (mis à jour)"))
                else:
                    inchanges += 1

        # Invalider le cache des constantes
        try:
            from paie.cache_service import PayrollCacheService
            PayrollCacheService.get_constantes(force_refresh=True)
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé : {crees} créées, {maj} mises à jour, {inchanges} inchangées "
            f"(sur {len(CONSTANTES)} constantes)."
        ))
        if not force and maj == 0 and crees == 0:
            self.stdout.write("Astuce : utilisez --force pour réécrire les valeurs existantes.")
