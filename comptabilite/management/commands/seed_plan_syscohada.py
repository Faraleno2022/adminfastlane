# -*- coding: utf-8 -*-
"""
Initialise le plan comptable SYSCOHADA (comptes essentiels, classes 1 à 8)
pour une ou toutes les entreprises. Idempotent : les comptes existants ne
sont jamais modifiés.

Usage :
    python manage.py seed_plan_syscohada            # toutes les entreprises
    python manage.py seed_plan_syscohada --entreprise <uuid>
"""
from django.core.management.base import BaseCommand

from core.models import Entreprise
from comptabilite.models import PlanComptable

# Comptes essentiels du plan SYSCOHADA révisé (sélection PME)
PLAN_SYSCOHADA = [
    # Classe 1 — Ressources durables
    ('1011', 'Capital souscrit, non appelé'),
    ('1012', 'Capital souscrit, appelé, non versé'),
    ('1013', 'Capital souscrit, appelé, versé'),
    ('1061', 'Réserve légale'),
    ('1181', 'Réserves facultatives'),
    ('1210', 'Report à nouveau créditeur'),
    ('1290', 'Report à nouveau débiteur'),
    ('1310', 'Résultat net : bénéfice'),
    ('1390', 'Résultat net : perte'),
    ('1410', 'Subventions d\'équipement'),
    ('1621', 'Emprunts auprès des établissements de crédit'),
    ('1661', 'Intérêts courus sur emprunts'),
    # Classe 2 — Actif immobilisé
    ('2111', 'Frais de développement'),
    ('2131', 'Logiciels'),
    ('2211', 'Terrains'),
    ('2311', 'Bâtiments industriels et commerciaux'),
    ('2411', 'Matériel et outillage industriel'),
    ('2441', 'Matériel et outillage'),
    ('2442', 'Matériel informatique'),
    ('2444', 'Mobilier de bureau'),
    ('2451', 'Matériel de transport'),
    ('2811', 'Amortissements des frais de développement'),
    ('2831', 'Amortissements des bâtiments'),
    ('2841', 'Amortissements du matériel'),
    ('2844', 'Amortissements du mobilier'),
    ('2845', 'Amortissements du matériel de transport'),
    # Classe 3 — Stocks
    ('3111', 'Marchandises A'),
    ('3211', 'Matières premières'),
    ('3611', 'Produits finis'),
    ('3911', 'Dépréciations des stocks de marchandises'),
    # Classe 4 — Tiers
    ('4011', 'Fournisseurs'),
    ('4081', 'Fournisseurs, factures non parvenues'),
    ('4091', 'Fournisseurs, avances et acomptes versés'),
    ('4111', 'Clients'),
    ('4181', 'Clients, factures à établir'),
    ('4191', 'Clients, avances et acomptes reçus'),
    ('4221', 'Personnel, rémunérations dues'),
    ('4311', 'CNSS, cotisations sociales'),
    ('4421', 'Impôts et taxes d\'État (RTS)'),
    ('4431', 'TVA facturée sur ventes'),
    ('4441', 'État, TVA due'),
    ('4449', 'État, crédit de TVA à reporter'),
    ('4452', 'TVA récupérable sur achats'),
    ('4471', 'État, impôts retenus à la source'),
    ('4491', 'État, avances et acomptes versés sur impôts'),
    ('4712', 'Créditeurs divers'),
    ('4711', 'Débiteurs divers'),
    ('4812', 'Fournisseurs d\'investissements'),
    # Classe 5 — Trésorerie
    ('5211', 'Banque'),
    ('5311', 'Chèques postaux'),
    ('5711', 'Caisse'),
    ('5851', 'Virements de fonds'),
    # Classe 6 — Charges
    ('6011', 'Achats de marchandises'),
    ('6021', 'Achats de matières premières'),
    ('6031', 'Variations des stocks de marchandises'),
    ('6051', 'Fournitures non stockables — eau'),
    ('6052', 'Fournitures non stockables — électricité'),
    ('6055', 'Fournitures de bureau'),
    ('6111', 'Transports sur achats'),
    ('6121', 'Transports sur ventes'),
    ('6221', 'Locations et charges locatives'),
    ('6241', 'Entretien, réparations et maintenance'),
    ('6251', 'Primes d\'assurance'),
    ('6265', 'Frais de télécommunications'),
    ('6271', 'Frais bancaires'),
    ('6281', 'Frais divers'),
    ('6311', 'Impôts et taxes directs (patente)'),
    ('6411', 'Impôts et taxes indirects'),
    ('6588', 'Autres charges diverses'),
    ('6611', 'Appointements et salaires'),
    ('6641', 'Charges sociales (CNSS employeur)'),
    ('6711', 'Intérêts des emprunts'),
    ('6811', 'Dotations aux amortissements d\'exploitation'),
    ('6911', 'Dotations aux provisions d\'exploitation'),
    # Classe 7 — Produits
    ('7011', 'Ventes de marchandises'),
    ('7021', 'Ventes de produits finis'),
    ('7061', 'Services vendus'),
    ('7071', 'Produits accessoires'),
    ('7078', 'Autres produits accessoires'),
    ('7311', 'Variations des stocks de produits finis'),
    ('7588', 'Autres produits divers'),
    ('7711', 'Intérêts de prêts'),
    ('7811', 'Reprises d\'amortissements'),
    ('7911', 'Reprises de provisions d\'exploitation'),
    # Classe 8 — Autres charges et produits
    ('8111', 'Valeurs comptables des cessions d\'immobilisations'),
    ('8211', 'Produits des cessions d\'immobilisations'),
    ('8911', 'Impôts sur le résultat'),
]


class Command(BaseCommand):
    help = 'Initialise le plan comptable SYSCOHADA (comptes essentiels) — idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--entreprise', help='UUID d\'une entreprise précise (défaut : toutes)')

    def handle(self, *args, **options):
        entreprises = Entreprise.objects.filter(actif=True)
        if options.get('entreprise'):
            entreprises = entreprises.filter(pk=options['entreprise'])
        for entreprise in entreprises:
            crees = 0
            for numero, intitule in PLAN_SYSCOHADA:
                _, cree = PlanComptable.objects.get_or_create(
                    entreprise=entreprise, numero_compte=numero,
                    defaults={'intitule': intitule, 'classe': numero[0], 'est_actif': True})
                if cree:
                    crees += 1
            self.stdout.write(self.style.SUCCESS(
                f'{entreprise.nom_entreprise} : {crees} compte(s) créé(s), '
                f'{len(PLAN_SYSCOHADA) - crees} déjà présent(s).'))
