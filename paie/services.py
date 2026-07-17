"""
Services de calcul de paie
Moteur de calcul automatique conforme à la législation guinéenne

OPTIMISATIONS PERFORMANCE:
- Cache des constantes, rubriques et tranches RTS
- Bulk operations pour les insertions
- Select_related/prefetch_related pour réduire les requêtes N+1
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from paie.utils_arrondi import precise, money, money_int
from datetime import date, timedelta
import calendar
from django.db import transaction
from django.db import models
from django.utils import timezone
from functools import lru_cache

from .models import (
    BulletinPaie, LigneBulletin, ElementSalaire, CumulPaie,
    RubriquePaie, Constante, TrancheRTS, PeriodePaie, HistoriquePaie
)
from .cache_service import PayrollCacheService
from employes.models import Employe
from temps_travail.models import Pointage, Absence, Conge, HeureSupplementaire
from core.services.devises import DeviseService
from core.models import Devise
import calendar


def _to_json_safe(value):
    """Convertit récursivement Decimal/date/datetime en types JSON-sérialisables
    (str pour Decimal, ISO 8601 pour date/datetime). Requis avant stockage dans
    un JSONField SQLite, qui utilise json.dumps sans encodeur custom."""
    from datetime import date as _date, datetime as _datetime
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (_datetime, _date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    return value


def _compter_salaries_a_la_periode(entreprise, periode):
    """Effectif servant à la bascule TA/ONFPP pour le mois calculé."""
    if not entreprise:
        return 0

    # Pour une période déjà calculée, les bulletins figés constituent la
    # source historique la plus fiable et évitent d'utiliser l'effectif actuel.
    if getattr(periode, 'statut_periode', '') in ('calculee', 'cloturee'):
        nb_bulletins = BulletinPaie.objects.filter(
            periode=periode,
            employe__entreprise=entreprise,
        ).values('employe_id').distinct().count()
        if nb_bulletins:
            return nb_bulletins

    premier_jour = date(periode.annee, periode.mois, 1)
    dernier_jour = date(
        periode.annee,
        periode.mois,
        calendar.monthrange(periode.annee, periode.mois)[1],
    )
    return Employe.objects.filter(
        entreprise=entreprise,
    ).filter(
        models.Q(date_embauche__isnull=True) |
        models.Q(date_embauche__lte=dernier_jour)
    ).filter(
        models.Q(statut_employe='actif') |
        models.Q(date_depart__gte=premier_jour)
    ).count()


def salaire_base_rubrique_q(prefix='rubrique__'):
    """Critere commun pour identifier une rubrique de salaire de base."""
    p = prefix
    return (
        models.Q(**{f'{p}categorie_rubrique': 'salaire_base'}) |
        models.Q(**{f'{p}code_rubrique__iexact': 'SAL_BASE'}) |
        models.Q(**{f'{p}code_rubrique__icontains': 'SAL_BASE'}) |
        models.Q(**{f'{p}code_rubrique__iexact': 'SALAIRE_BASE'}) |
        models.Q(**{f'{p}code_rubrique__iexact': 'BASE'}) |
        models.Q(**{f'{p}libelle_rubrique__icontains': 'Salaire de base'}) |
        (
            models.Q(**{f'{p}code_rubrique__icontains': 'BASE'}) &
            models.Q(**{f'{p}libelle_rubrique__icontains': 'salaire'})
        )
    )


def salaire_base_priority_annotation(prefix='rubrique__'):
    """Priorite de choix quand plusieurs rubriques peuvent representer la base."""
    p = prefix
    return models.Case(
        models.When(**{f'{p}categorie_rubrique': 'salaire_base'}, then=models.Value(0)),
        models.When(**{f'{p}code_rubrique__icontains': 'SAL_BASE'}, then=models.Value(1)),
        models.When(**{f'{p}code_rubrique__iexact': 'BASE'}, then=models.Value(2)),
        models.When(**{f'{p}libelle_rubrique__icontains': 'Salaire de base'}, then=models.Value(3)),
        default=models.Value(9),
        output_field=models.IntegerField(),
    )


CNSS_LEGALE = {
    'PLANCHER_CNSS': Decimal('550000'),
    'PLAFOND_CNSS': Decimal('2500000'),
    'TAUX_CNSS_EMPLOYE': Decimal('5'),
    'TAUX_CNSS_EMPLOYEUR': Decimal('18'),
}


def appliquer_constantes_cnss_legales(constantes):
    """Verrouille les parametres CNSS guineens pour eviter les taux flottants."""
    constantes.update(CNSS_LEGALE)
    return constantes


# ============================================================================
# DÉTECTION INTELLIGENTE DES INDEMNITÉS FORFAITAIRES EXONÉRÉES DE RTS
# Législation guinéenne (CGI): les indemnités forfaitaires (transport, logement,
# panier, cherté de vie, etc.) sont intégralement exonérées de RTS.
# Seules les primes (récompense/motivation) sont imposables.
# ============================================================================

# Patterns de codes de rubriques forfaitaires (match par inclusion, insensible à la casse)
# NB: pas de codes courts ici (risque de faux positifs). Les codes courts sont dans CODES_EXACTS.
PATTERNS_CODES_FORFAITAIRES = [
    'TRANSPORT', 'LOGEMENT', 'REPAS', 'PANIER', 'CHERTE',
    'DEPLACEMENT', 'SALISSURE', 'OUTILLAGE', 'VESTIMENTAIRE',
    'HABILLEMENT', 'HEBERGEMENT',
]

# Mots-clés dans le libellé de la rubrique (match par inclusion, insensible à la casse)
MOTS_CLES_LIBELLE_FORFAITAIRES = [
    'transport', 'logement', 'hébergement', 'hebergement',
    'repas', 'panier', 'nourriture', 'restauration',
    'cherté', 'cherte', 'vie chère', 'vie chere',
    'déplacement', 'deplacement',
    'vestimentaire', 'habillement',
    'salissure', 'outillage',
    'indemnité forfaitaire', 'indemnite forfaitaire',
    'prime de logement', 'prime de transport',
    'allocation logement', 'allocation transport',
]

# Codes courts exacts (match exact du code, insensible à la casse)
CODES_EXACTS_FORFAITAIRES = {
    'PT', 'PL', 'PCV',
}


class MoteurCalculPaie:
    """Moteur de calcul automatique de la paie"""
    
    def __init__(self, employe, periode):
        self.employe = employe
        self.periode = periode
        self.lignes = []
        self.montants = {
            'brut': Decimal('0'),
            'imposable': Decimal('0'),
            'cnss_base': Decimal('0'),
            'cnss_employe': Decimal('0'),
            'cnss_employeur': Decimal('0'),
            'irg': Decimal('0'),
            'net': Decimal('0'),
            'total_gains': Decimal('0'),
            'total_retenues': Decimal('0'),
            # Charges patronales supplémentaires
            'versement_forfaitaire': Decimal('0'),  # VF 6%
            'base_vf': Decimal('0'),                # Base nette VF
            'taxe_apprentissage': Decimal('0'),     # TA 2%
            'base_ta': Decimal('0'),                # Base TA
            'taux_vf': Decimal('0'),                # Taux VF appliqué
            'taux_ta': Decimal('0'),                # Taux TA appliqué
            'contribution_onfpp': Decimal('0'),     # ONFPP 1,5%
            'total_charges_patronales': Decimal('0'),
            # Exonération RTS stagiaires/apprentis
            'exoneration_rts': False,
            'raison_exoneration_rts': '',
            # Plafond 25% indemnités forfaitaires
            'indemnites_forfaitaires': Decimal('0'),
            'plafond_indemnites': Decimal('0'),
            'depassement_plafond_indemnites': Decimal('0'),
            'reintegration_base_imposable': Decimal('0'),
            # Temps de travail
            'jours_travailles': Decimal('0'),
            'jours_ouvrables': Decimal('0'),
            'heures_travaillees': Decimal('0'),
            'heures_supplementaires': Decimal('0'),
            'jours_absence': Decimal('0'),
            'jours_conge': Decimal('0'),
            'retenue_absence': Decimal('0'),
            # Rappels et manquements (hors base de calcul)
            'rappel_salaire': Decimal('0'),
            'retenue_trop_percu': Decimal('0'),
            # RTS détail (base, taux effectif)
            'base_rts': Decimal('0'),
            'taux_effectif_rts': Decimal('0'),
            # Audit des bases taxables réellement utilisées avant calcul
            'bases_taxables': {},
        }
        # Nombre de salariés actifs de l'entreprise (pour TA vs ONFPP)
        self.nb_salaries = _compter_salaries_a_la_periode(
            employe.entreprise,
            periode,
        )
        self.constantes = self._charger_constantes()
        self._appliquer_config_entreprise()
        appliquer_constantes_cnss_legales(self.constantes)
        self.tranches_irg = self._charger_tranches_irg()
        
        # Devise de paie de l'employé et service de conversion
        self.devise_employe = employe.devise_paie if employe.devise_paie else DeviseService.get_devise_base()
        self.devise_base = DeviseService.get_devise_base()
        self.date_conversion = date(self.periode.annee, self.periode.mois, 1)
        self._heures_sup_detail_ids = []
    
    def _charger_constantes(self):
        """Charger les constantes actives à la date de la période (avec cache)."""
        date_ref = date(self.periode.annee, self.periode.mois, 1)
        return PayrollCacheService.get_constantes(date_reference=date_ref)

    def _appliquer_config_entreprise(self):
        """Surcharge les constantes globales avec la config entreprise si elle existe.

        Permet à chaque entreprise d'avoir ses propres taux CNSS, VF, TA, HS
        via l'interface /paie/configuration/ sans toucher aux constantes globales.
        """
        from .models import ConfigurationPaieEntreprise
        try:
            config = self.employe.entreprise.config_paie
        except (AttributeError, ConfigurationPaieEntreprise.DoesNotExist):
            return

        # Mapping champ ConfigurationPaieEntreprise -> clé Constante
        # NB: taux_taxe_apprentissage et taux_onfpp sont EXCLUS car fixés par la loi
        mapping = {
            'taux_versement_forfaitaire': 'TAUX_VF',
        }
        # HS : ConfigPaie stocke la majoration (30%), le moteur attend le coefficient (130%)
        mapping_hs = {
            'taux_hs_4_premieres': 'TAUX_HS_4PREM',
            'taux_hs_au_dela': 'TAUX_HS_AUDELA',
            'taux_hs_nuit': 'TAUX_HS_NUIT',
            'taux_hs_dimanche': 'TAUX_HS_FERIE_JOUR',
            'taux_hs_ferie_nuit': 'TAUX_HS_FERIE_NUIT',
        }

        for champ, cle in mapping.items():
            valeur = getattr(config, champ, None)
            if valeur is not None:
                self.constantes[cle] = Decimal(str(valeur))

        for champ, cle in mapping_hs.items():
            valeur = getattr(config, champ, None)
            if valeur is not None:
                # Majoration (30) → coefficient (130)
                self.constantes[cle] = Decimal(str(valeur)) + Decimal('100')

    def _charger_tranches_irg(self):
        """Charger le barème RTS (avec cache et fallback année précédente)"""
        # Récupérer depuis le cache pour l'année en cours
        tranches_data = PayrollCacheService.get_tranches_rts(self.periode.annee)
        
        if tranches_data:
            return tranches_data
        
        # Fallback: requête directe pour l'année en cours (officiels uniquement)
        tranches = list(TrancheRTS.objects.filter(
            annee_validite=self.periode.annee,
            actif=True,
            type_bareme='officiel',
        ).order_by('numero_tranche').values(
            'numero_tranche', 'borne_inferieure',
            'borne_superieure', 'taux_irg'
        ))

        # Si pas de tranches pour l'année en cours, chercher l'année précédente
        if not tranches:
            tranches = list(TrancheRTS.objects.filter(
                annee_validite=self.periode.annee - 1,
                actif=True,
                type_bareme='officiel',
            ).order_by('numero_tranche').values(
                'numero_tranche', 'borne_inferieure',
                'borne_superieure', 'taux_irg'
            ))

        # Dernier recours: chercher la dernière année disponible
        if not tranches:
            derniere_annee = TrancheRTS.objects.filter(
                actif=True, type_bareme='officiel'
            ).order_by('-annee_validite').values_list('annee_validite', flat=True).first()
            if derniere_annee:
                tranches = list(TrancheRTS.objects.filter(
                    annee_validite=derniere_annee,
                    actif=True,
                    type_bareme='officiel',
                ).order_by('numero_tranche').values(
                    'numero_tranche', 'borne_inferieure',
                    'borne_superieure', 'taux_irg'
                ))
        
        # Fallback ultime: barème RTS CGI 2022 codé en dur (bornes continues)
        if not tranches:
            tranches = [
                {'numero_tranche': 1, 'borne_inferieure': Decimal('0'), 'borne_superieure': Decimal('1000000'), 'taux_irg': Decimal('0')},
                {'numero_tranche': 2, 'borne_inferieure': Decimal('1000000'), 'borne_superieure': Decimal('3000000'), 'taux_irg': Decimal('5')},
                {'numero_tranche': 3, 'borne_inferieure': Decimal('3000000'), 'borne_superieure': Decimal('5000000'), 'taux_irg': Decimal('8')},
                {'numero_tranche': 4, 'borne_inferieure': Decimal('5000000'), 'borne_superieure': Decimal('10000000'), 'taux_irg': Decimal('10')},
                {'numero_tranche': 5, 'borne_inferieure': Decimal('10000000'), 'borne_superieure': Decimal('20000000'), 'taux_irg': Decimal('15')},
                {'numero_tranche': 6, 'borne_inferieure': Decimal('20000000'), 'borne_superieure': None, 'taux_irg': Decimal('20')},
            ]
        
        return tranches
    
    def _arrondir(self, montant):
        """Arrondir un montant à l'unité (GNF = pas de centimes)"""
        if not isinstance(montant, Decimal):
            montant = Decimal(str(montant))
        return montant.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    
    def _calculer_anciennete(self):
        """Calculer l'ancienneté en années"""
        if not self.employe.date_embauche:
            return 0
        
        delta = date(self.periode.annee, self.periode.mois, 1) - self.employe.date_embauche
        return delta.days // 365
    
    def _construire_variables_formule(self) -> dict:
        """Construit le dictionnaire de variables exposées aux formules personnalisées."""
        employe = self.employe
        # Ancienneté en mois
        anciennete_mois = 0
        if employe.date_embauche:
            d = date(self.periode.annee, self.periode.mois, 1)
            delta = d - employe.date_embauche
            anciennete_mois = max(0, delta.days // 30)

        return {
            'brut': float(self.montants.get('brut', Decimal('0'))),
            'cnss': float(self.montants.get('cnss_employe', Decimal('0'))),
            'indemnites': float(self.montants.get('indemnites_forfaitaires', Decimal('0'))),
            'salaire_base': float(self.montants.get('salaire_base', Decimal('0'))),
            'primes': float(self.montants.get('total_primes', Decimal('0'))),
            'heures_sup': float(self.montants.get('total_heures_sup', Decimal('0'))),
            'total_gains': float(self.montants.get('total_gains', Decimal('0'))),
            'total_retenues': float(self.montants.get('total_retenues', Decimal('0'))),
            'cnss_base': float(self.montants.get('cnss_base', Decimal('0'))),
            'net': float(self.montants.get('net_a_payer', Decimal('0'))),
            'anciennete_mois': anciennete_mois,
            'anciennete_ans': anciennete_mois // 12,
            'nb_enfants': int(getattr(employe, 'nombre_enfants', 0) or 0),
            'nb_conjoints': int(getattr(employe, 'nombre_femmes', 0) or 0),
            'plafond_cnss': float(self.constantes.get('PLAFOND_CNSS', Decimal('2500000'))),
        }

    def _ajouter_alerte_calcul(self, type_alerte, message):
        self.montants.setdefault('alertes', []).append({
            'type': type_alerte,
            'message': message,
        })

    def _normaliser_base_taxable(self, code, libelle, valeur, formule, fallback=None):
        """Valide et trace une base taxable avant application du calcul."""
        trouvee = valeur is not None
        try:
            if valeur is None:
                raise ValueError("base absente")
            base = Decimal(str(valeur))
            if not base.is_finite():
                raise ValueError("base non finie")
        except Exception:
            base = Decimal(str(fallback)) if fallback is not None else Decimal('0')
            niveau = 'avertissement' if fallback is not None else 'critique'
            self._ajouter_alerte_calcul(
                niveau,
                f"Base taxable {libelle} introuvable ou invalide. "
                f"Base retenue: {base:,.0f} GNF."
            )

        if base < 0:
            self._ajouter_alerte_calcul(
                'avertissement',
                f"Base taxable {libelle} négative ({base:,.0f} GNF). Base ramenée à 0 GNF."
            )
            base = Decimal('0')

        base = self._arrondir(base)
        self.montants.setdefault('bases_taxables', {})[code] = {
            'libelle': libelle,
            'base': base,
            'formule': formule,
            'trouvee': trouvee,
        }
        return base

    def _obtenir_taux_anciennete(self, annees):
        """Obtenir le taux d'ancienneté selon le barème"""
        if annees < 2:
            return self.constantes.get('ANCIEN_0_2ANS', Decimal('2.00'))
        elif annees < 5:
            return self.constantes.get('ANCIEN_2_5ANS', Decimal('5.00'))
        elif annees < 10:
            return self.constantes.get('ANCIEN_5_10ANS', Decimal('7.00'))
        elif annees < 15:
            return self.constantes.get('ANCIEN_10_15ANS', Decimal('10.00'))
        else:
            return self.constantes.get('ANCIEN_15ANS_PLUS', Decimal('12.00'))
    
    def calculer_bulletin(self):
        """Calculer le bulletin de paie complet"""
        
        # Initialiser les alertes
        self.montants['alertes'] = []
        
        # 0. Calculer le temps de travail (pointages, absences, congés)
        self._calculer_temps_travail()
        
        # 1. Calculer les gains
        self._calculer_gains()
        
        # 2. Appliquer les retenues pour absences non payées
        self._appliquer_retenues_absences()
        
        # 3. Calculer le brut (arrondi à l'unité GNF)
        self.montants['brut'] = self._arrondir(self.montants['total_gains'] - self.montants['retenue_absence'])
        
        # 3.1 Vérification: Salaire brut très faible ou nul
        plancher_cnss = self.constantes.get('PLANCHER_CNSS', Decimal('550000'))
        seuil_minimum = plancher_cnss * Decimal('0.10')  # 10% du plancher = 55 000 GNF
        
        if self.montants['brut'] <= 0:
            self.montants['alertes'].append({
                'type': 'critique',
                'message': f"Salaire brut nul ou négatif ({self.montants['brut']:,.0f} GNF). Vérifiez les éléments de salaire."
            })
        elif self.montants['brut'] < seuil_minimum:
            self.montants['alertes'].append({
                'type': 'avertissement',
                'message': f"Salaire brut très faible ({self.montants['brut']:,.0f} GNF < {seuil_minimum:,.0f} GNF). Pas de cotisation CNSS calculée."
            })
        
        # 3.2 Appliquer l'exonération RTS des indemnités forfaitaires sur le brut final.
        self._appliquer_exoneration_indemnites_forfaitaires()

        # 4. Calculer les cotisations sociales
        self._calculer_cotisations_sociales()
        
        # 5. Calculer l'RTS/IRSA
        self._calculer_irg()
        
        # 6. Calculer les autres retenues
        self._calculer_autres_retenues()
        
        # 6.1 Appliquer les rappels et manquements (hors base)
        self._appliquer_rappels_manquements()
        
        # 7. Calculer le net (rappels et retenues trop-perçu inclus) — arrondi à l'unité GNF
        self.montants['total_retenues'] = self._arrondir(self.montants['total_retenues'])
        net_calcule = self._arrondir(self.montants['brut'] - self.montants['total_retenues'] + self.montants['rappel_salaire'] - self.montants['retenue_trop_percu'])

        # 7.0 Arrondi RH du net à payer (config entreprise)
        # N'affecte PAS les bases CNSS/RTS qui doivent rester exactes pour la conformité.
        try:
            pas_arrondi = int(getattr(self.employe.entreprise.config_paie, 'arrondi_net', 0) or 0)
        except (AttributeError, Exception):
            pas_arrondi = 0
        if pas_arrondi > 0 and net_calcule > 0:
            pas = Decimal(pas_arrondi)
            # Arrondi au pas le plus proche (banker's rounding via quantize)
            net_arrondi = (net_calcule / pas).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * pas
            self.montants['ecart_arrondi_net'] = net_arrondi - net_calcule
            net_calcule = net_arrondi
        else:
            self.montants['ecart_arrondi_net'] = Decimal('0')
        
        # 7.1 Protection: Empêcher le net négatif
        # Si les retenues dépassent le brut, on plafonne les retenues au brut
        if net_calcule < 0:
            self.montants['alertes'].append({
                'type': 'critique',
                'message': f"Net à payer serait négatif ({net_calcule:,.0f} GNF). Les retenues ({self.montants['total_retenues']:,.0f} GNF) dépassent le brut ({self.montants['brut']:,.0f} GNF). Retenues plafonnées."
            })
            # Plafonner les retenues au montant du brut pour éviter un net négatif
            self.montants['retenues_excessives'] = abs(net_calcule)
            self.montants['total_retenues'] = self.montants['brut']
            self.montants['net'] = Decimal('0')
        else:
            self.montants['retenues_excessives'] = Decimal('0')
            self.montants['net'] = net_calcule
        
        return self.montants
    
    def _calculer_temps_travail(self):
        """Calculer les données de temps de travail pour la période"""
        # Dates de la période
        premier_jour = date(self.periode.annee, self.periode.mois, 1)
        dernier_jour = date(
            self.periode.annee,
            self.periode.mois,
            calendar.monthrange(self.periode.annee, self.periode.mois)[1]
        )

        # Prendre en compte la date d'embauche : si l'employé a été embauché
        # en cours de mois, les jours ouvrables et les pointages partent de
        # cette date (pas du 1er du mois).
        date_embauche = getattr(self.employe, 'date_embauche', None)
        if date_embauche and premier_jour <= date_embauche <= dernier_jour:
            debut_effectif = date_embauche
        else:
            debut_effectif = premier_jour

        # Calculer les jours ouvrables à partir de la date d'entrée effective
        jours_ouvrables = 0
        current = debut_effectif
        while current <= dernier_jour:
            if current.weekday() < 5:  # Lundi=0, Vendredi=4
                jours_ouvrables += 1
            current += timedelta(days=1)

        self.montants['jours_ouvrables'] = Decimal(str(jours_ouvrables))

        # Récupérer les pointages à partir de la date d'entrée effective
        pointages = Pointage.objects.filter(
            employe=self.employe,
            date_pointage__gte=debut_effectif,
            date_pointage__lte=dernier_jour
        )

        # Compter les jours travaillés
        jours_presents = pointages.filter(statut_pointage='present').count()
        jours_retard = pointages.filter(statut_pointage='retard').count()
        self.montants['jours_travailles'] = Decimal(str(jours_presents + jours_retard))

        # Heures travaillées et supplémentaires (total)
        from django.db.models import Sum
        heures = pointages.aggregate(
            heures_travaillees=Sum('heures_travaillees'),
            heures_sup=Sum('heures_supplementaires')
        )
        self.montants['heures_travaillees'] = heures['heures_travaillees'] or Decimal('0')
        self.montants['heures_supplementaires'] = heures['heures_sup'] or Decimal('0')

        # Répartition hebdomadaire des HS : 4 premières h/semaine à +30%,
        # au-delà à +60% (Code du Travail guinéen Art. 221).
        # On groupe les pointages par semaine (lundi → dimanche) pour
        # respecter le plafond de 4 h hebdomadaires.
        hs_30 = Decimal('0')
        hs_60 = Decimal('0')
        semaine_map = {}
        for p in pointages.order_by('date_pointage'):
            if not p.heures_supplementaires:
                continue
            # Numéro ISO de la semaine (année, semaine) pour le regroupement
            iso = p.date_pointage.isocalendar()
            cle_semaine = (iso[0], iso[1])
            semaine_map.setdefault(cle_semaine, Decimal('0'))
            semaine_map[cle_semaine] += Decimal(str(p.heures_supplementaires))
        for total_hs_semaine in semaine_map.values():
            hs_30 += min(total_hs_semaine, Decimal('4'))
            hs_60 += max(Decimal('0'), total_hs_semaine - Decimal('4'))

        hs_detaillees = HeureSupplementaire.objects.filter(
            employe=self.employe,
            date_hs__gte=debut_effectif,
            date_hs__lte=dernier_jour,
        ).filter(
            models.Q(statut='valide') |
            models.Q(statut='paye', bulletin__periode=self.periode)
        )
        if hs_detaillees.exists():
            hs_30 = Decimal('0')
            hs_60 = Decimal('0')
            hs_nuit = Decimal('0')
            hs_ferie_jour = Decimal('0')
            hs_ferie_nuit = Decimal('0')
            montant_hs_30 = Decimal('0')
            montant_hs_60 = Decimal('0')
            montant_hs_nuit = Decimal('0')
            montant_hs_ferie_jour = Decimal('0')
            montant_hs_ferie_nuit = Decimal('0')
            self._heures_sup_detail_ids = []

            for hs in hs_detaillees:
                nombre = Decimal(str(hs.nombre_heures or 0))
                montant = Decimal(str(hs.montant_hs or 0))
                type_hs = (hs.type_hs or '').lower()
                self._heures_sup_detail_ids.append(hs.pk)

                if type_hs in ('jour_15', 'jour_25', 'jour_30'):
                    hs_30 += nombre
                    montant_hs_30 += montant
                elif type_hs in ('jour_50', 'jour_60'):
                    hs_60 += nombre
                    montant_hs_60 += montant
                elif type_hs in ('nuit_20', 'nuit_50'):
                    hs_nuit += nombre
                    montant_hs_nuit += montant
                elif type_hs in ('dimanche_75', 'ferie_60'):
                    hs_ferie_jour += nombre
                    montant_hs_ferie_jour += montant
                elif type_hs in ('dimanche_nuit_100', 'ferie_nuit_100'):
                    hs_ferie_nuit += nombre
                    montant_hs_ferie_nuit += montant
                else:
                    hs_60 += nombre
                    montant_hs_60 += montant

            self.montants['heures_supplementaires'] = (
                hs_30 + hs_60 + hs_nuit + hs_ferie_jour + hs_ferie_nuit
            )
            self.montants['heures_sup_nuit'] = hs_nuit
            self.montants['heures_sup_ferie_jour'] = hs_ferie_jour
            self.montants['heures_sup_ferie_nuit'] = hs_ferie_nuit
            self.montants['montant_hs_30_detail'] = montant_hs_30
            self.montants['montant_hs_60_detail'] = montant_hs_60
            self.montants['montant_hs_nuit_detail'] = montant_hs_nuit
            self.montants['montant_hs_ferie_jour_detail'] = montant_hs_ferie_jour
            self.montants['montant_hs_ferie_nuit_detail'] = montant_hs_ferie_nuit
            self.montants['montant_heures_sup_detail'] = (
                montant_hs_30 + montant_hs_60 + montant_hs_nuit +
                montant_hs_ferie_jour + montant_hs_ferie_nuit
            )
        self.montants['heures_sup_30'] = hs_30
        self.montants['heures_sup_60'] = hs_60
        
        # Récupérer les absences du mois
        absences = Absence.objects.filter(
            employe=self.employe,
            date_absence__gte=premier_jour,
            date_absence__lte=dernier_jour
        )
        
        jours_absence_non_paye = Decimal('0')
        jours_absence_total = Decimal('0')
        
        for absence in absences:
            jours_absence_total += absence.duree_jours
            if absence.impact_paie == 'non_paye':
                jours_absence_non_paye += absence.duree_jours
            elif absence.impact_paie == 'partiellement_paye':
                # Calculer la partie non payée
                taux_non_paye = (Decimal('100') - absence.taux_maintien_salaire) / Decimal('100')
                jours_absence_non_paye += absence.duree_jours * taux_non_paye
        
        self.montants['jours_absence'] = jours_absence_total
        self.montants['jours_absence_non_paye'] = jours_absence_non_paye
        
        # Récupérer les congés approuvés du mois
        conges = Conge.objects.filter(
            employe=self.employe,
            statut_demande='approuve',
            date_debut__lte=dernier_jour,
            date_fin__gte=premier_jour
        )
        
        jours_conge = Decimal('0')
        for conge in conges:
            # Calculer les jours de congé dans la période
            debut_conge = max(conge.date_debut, premier_jour)
            fin_conge = min(conge.date_fin, dernier_jour)
            jours_dans_periode = (fin_conge - debut_conge).days + 1
            jours_conge += Decimal(str(jours_dans_periode))
        
        self.montants['jours_conge'] = jours_conge
    
    def _appliquer_retenues_absences(self):
        """Appliquer les retenues pour absences non payées"""
        jours_absence_non_paye = self.montants.get('jours_absence_non_paye', Decimal('0'))
        
        if jours_absence_non_paye <= 0:
            return
        
        # Calculer le salaire journalier
        jours_ouvrables = self.montants['jours_ouvrables']
        if jours_ouvrables <= 0:
            jours_ouvrables = Decimal('22')  # Valeur par défaut
        
        salaire_journalier = self.montants['total_gains'] / jours_ouvrables
        
        # Calculer la retenue
        retenue = self._arrondir(salaire_journalier * jours_absence_non_paye)
        self.montants['retenue_absence'] = retenue
        
        # Ajouter la ligne de retenue
        rubrique_absence = RubriquePaie.objects.filter(
            code_rubrique__icontains='ABSENCE',
            type_rubrique='retenue',
            actif=True
        ).first()
        
        if rubrique_absence:
            self.lignes.append({
                'rubrique': rubrique_absence,
                'base': self.montants['total_gains'],
                'taux': Decimal('0'),
                'nombre': jours_absence_non_paye,
                'montant': retenue,
                'ordre': rubrique_absence.ordre_affichage
            })
    
    def _calculer_gains(self):
        """Calculer tous les éléments de gain"""
        # Calculer le dernier jour du mois de la période
        dernier_jour = calendar.monthrange(self.periode.annee, self.periode.mois)[1]
        fin_mois = date(self.periode.annee, self.periode.mois, dernier_jour)
        debut_mois = date(self.periode.annee, self.periode.mois, 1)
        
        # Récupérer les éléments de salaire de l'employé
        # Un élément est valide si sa date_debut <= fin du mois ET (date_fin est null OU date_fin >= debut du mois)
        elements = ElementSalaire.objects.filter(
            employe=self.employe,
            actif=True,
            date_debut__lte=fin_mois
        ).filter(
            models.Q(date_fin__isnull=True) | 
            models.Q(date_fin__gte=debut_mois)
        ).select_related('rubrique')
        
        # Codes hors base (rappels/compléments traités séparément)
        codes_hors_base = ['RAPPEL_SALAIRE', 'COMPLEMENT_SALAIRE', 'RETENUE_TROP_PERCU', 'MANQUEMENT_SALAIRE']
        
        # Accumulateurs pour la détection intelligente
        self._indemnites_detectees = []  # Liste des (rubrique, montant, raison_detection)
        
        for element in elements:
            if element.rubrique.type_rubrique == 'gain':
                # Exclure les rappels/compléments qui sont traités hors base
                if element.rubrique.code_rubrique in codes_hors_base:
                    continue
                
                montant = self._calculer_element(element, phase='gains')

                self.lignes.append({
                    'rubrique': element.rubrique,
                    'base': element.montant or Decimal('0'),
                    'taux': element.taux,
                    'nombre': Decimal('1'),
                    'montant': montant,
                    'ordre': element.rubrique.ordre_affichage
                })

                self.montants['total_gains'] += montant

                # CNSS: le flag soumis_cnss de la rubrique détermine l'inclusion
                if element.rubrique.soumis_cnss:
                    self.montants['cnss_base'] += montant
                
                # RTS: détection intelligente des indemnités forfaitaires
                est_forfaitaire, raison = self._est_indemnite_forfaitaire(element.rubrique)
                if est_forfaitaire:
                    # Indemnité forfaitaire détectée → exonérée de RTS (plafond vérifié après)
                    self._indemnites_detectees.append((element.rubrique, montant, raison))
                else:
                    # Élément de rémunération classique → imposable RTS
                    self.montants['imposable'] += montant
        
        # Ajouter les heures supplémentaires si présentes
        self._calculer_heures_supplementaires()

        # L'exonération RTS est appliquée après le calcul du brut final, pour
        # tenir compte des absences non payées.
    
    def _calculer_element(self, element, phase=None):
        """Calculer le montant d'un élément (montant fixe, taux, ou formule).

        :param phase: Phase de calcul (gains/cotisations/fiscal/retenues/net)
                      pour restreindre les variables accessibles dans les formules.
        """
        if element.montant:
            return self._arrondir(element.montant)
        elif element.taux and element.base_calcul:
            base = self._obtenir_base_calcul(element.base_calcul)
            return self._arrondir(base * element.taux / Decimal('100'))
        elif element.rubrique.mode_calcul == 'formule' and element.rubrique.formule_calcul:
            from .formules import evaluer_formule
            variables = self._construire_variables_formule()
            try:
                return self._arrondir(evaluer_formule(
                    element.rubrique.formule_calcul, variables, phase=phase
                ))
            except ValueError:
                return Decimal('0')
        return Decimal('0')
    
    def _obtenir_base_calcul(self, code_base):
        """Obtenir la base de calcul"""
        if code_base == 'SALAIRE_BASE':
            # Chercher le salaire de base
            element_base = ElementSalaire.objects.filter(
                employe=self.employe,
                actif=True,
                rubrique__type_rubrique='gain',
            ).filter(
                salaire_base_rubrique_q()
            ).select_related('rubrique').annotate(
                _base_priority=salaire_base_priority_annotation()
            ).order_by(
                '_base_priority',
                'rubrique__ordre_calcul',
                'rubrique__ordre_affichage',
                '-date_debut',
                'id',
            ).first()
            if element_base and element_base.montant:
                return element_base.montant

            # Dernier secours pour anciens dossiers sans element structure.
            salaire_employe = getattr(self.employe, 'salaire_base', None)
            return salaire_employe or Decimal('0')
        elif code_base == 'BRUT':
            return self.montants['brut']
        elif code_base == 'CNSS_BASE':
            return self.montants['cnss_base']
        return Decimal('0')
    
    def _calculer_heures_supplementaires(self):
        """
        Calculer la rémunération des heures supplémentaires selon le Code du Travail guinéen (Art. 221).
        
        Barème des majorations (Art. 221):
        - 4 premières HS/semaine: +30% (130% du taux horaire)
        - Au-delà 4 HS/semaine: +60% (160% du taux horaire)
        - Heures de nuit (20h-6h): +20% (120% du taux horaire)
        - Jour férié (jour): +60% (160% du taux horaire)
        - Jour férié (nuit): +100% (200% du taux horaire)
        
        Note: Les pointages doivent distinguer les types d'heures supplémentaires.
        Pour simplifier, on utilise les champs du modèle Pointage si disponibles,
        sinon on applique un taux moyen pondéré.
        """
        # Récupérer les différents types d'heures supplémentaires
        heures_sup_30 = self.montants.get('heures_sup_30', Decimal('0'))  # 4 premières HS/semaine
        heures_sup_60 = self.montants.get('heures_sup_60', Decimal('0'))  # Au-delà 4 HS/semaine
        heures_sup_nuit = self.montants.get('heures_sup_nuit', Decimal('0'))  # Nuit (20h-6h)
        heures_sup_ferie_jour = self.montants.get('heures_sup_ferie_jour', Decimal('0'))  # Jour férié (jour)
        heures_sup_ferie_nuit = self.montants.get('heures_sup_ferie_nuit', Decimal('0'))  # Jour férié (nuit)
        
        # Compatibilité avec anciens champs
        heures_sup_15 = self.montants.get('heures_sup_15', Decimal('0'))
        heures_sup_25 = self.montants.get('heures_sup_25', Decimal('0'))
        heures_sup_50 = self.montants.get('heures_sup_50', Decimal('0'))
        heures_sup_100 = self.montants.get('heures_sup_ferie', Decimal('0'))
        
        # Mapper les anciens champs vers les nouveaux si non renseignés
        if heures_sup_30 == 0 and heures_sup_15 > 0:
            heures_sup_30 = heures_sup_15
        if heures_sup_60 == 0 and heures_sup_25 > 0:
            heures_sup_60 = heures_sup_25
        if heures_sup_nuit == 0 and heures_sup_50 > 0:
            heures_sup_nuit = heures_sup_50
        if heures_sup_ferie_jour == 0 and heures_sup_100 > 0:
            heures_sup_ferie_jour = heures_sup_100
        
        # Total des heures supplémentaires (ancien champ pour compatibilité)
        heures_sup_total = self.montants.get('heures_supplementaires', Decimal('0'))
        
        # Si les heures détaillées ne sont pas disponibles, utiliser le total avec taux +60%
        if heures_sup_30 == 0 and heures_sup_60 == 0 and heures_sup_nuit == 0 and heures_sup_ferie_jour == 0 and heures_sup_ferie_nuit == 0:
            heures_sup_60 = heures_sup_total  # Par défaut, appliquer le taux +60%
        
        heures_total = heures_sup_30 + heures_sup_60 + heures_sup_nuit + heures_sup_ferie_jour + heures_sup_ferie_nuit
        if heures_total <= 0:
            return
        
        # Obtenir le salaire horaire de base
        salaire_base = self._obtenir_base_calcul('SALAIRE_BASE')
        heures_mensuelles = self.constantes.get('HEURES_MENSUELLES', Decimal('173.33'))
        
        if heures_mensuelles <= 0:
            heures_mensuelles = Decimal('173.33')  # 40h x 52 semaines / 12 mois
        
        # precise() : calcul interne sans arrondi — money() uniquement en sortie finale
        salaire_horaire_exact = precise(salaire_base) / precise(heures_mensuelles)
        salaire_horaire = money(salaire_horaire_exact)  # affichage bulletin uniquement
        
        # Taux des heures supplémentaires selon le Code du Travail guinéen (Art. 221)
        TAUX_HS_30 = self.constantes.get('TAUX_HS_4PREM', Decimal('130'))      # 4 premières HS: +30% (130%)
        TAUX_HS_60 = self.constantes.get('TAUX_HS_AUDELA', Decimal('160'))     # Au-delà 4 HS: +60% (160%)
        TAUX_HS_NUIT = self.constantes.get('TAUX_HS_NUIT', Decimal('120'))     # Nuit (20h-6h): +20% (120%)
        TAUX_HS_FERIE_J = self.constantes.get('TAUX_HS_FERIE_JOUR', Decimal('160'))  # Férié jour: +60% (160%)
        TAUX_HS_FERIE_N = self.constantes.get('TAUX_HS_FERIE_NUIT', Decimal('200'))  # Férié nuit: +100% (200%)
        
        # Calculer le montant pour chaque type — arrondi money() en sortie finale uniquement
        montant_detail = self.montants.get('montant_heures_sup_detail', Decimal('0'))
        if montant_detail > 0:
            montant_hs_30 = self.montants.get('montant_hs_30_detail', Decimal('0'))
            montant_hs_60 = self.montants.get('montant_hs_60_detail', Decimal('0'))
            montant_hs_nuit = self.montants.get('montant_hs_nuit_detail', Decimal('0'))
            montant_hs_ferie_j = self.montants.get('montant_hs_ferie_jour_detail', Decimal('0'))
            montant_hs_ferie_n = self.montants.get('montant_hs_ferie_nuit_detail', Decimal('0'))
        else:
            montant_hs_30 = money(salaire_horaire_exact * precise(heures_sup_30) * TAUX_HS_30 / precise(100))
            montant_hs_60 = money(salaire_horaire_exact * precise(heures_sup_60) * TAUX_HS_60 / precise(100))
            montant_hs_nuit = money(salaire_horaire_exact * precise(heures_sup_nuit) * TAUX_HS_NUIT / precise(100))
            montant_hs_ferie_j = money(salaire_horaire_exact * precise(heures_sup_ferie_jour) * TAUX_HS_FERIE_J / precise(100))
            montant_hs_ferie_n = money(salaire_horaire_exact * precise(heures_sup_ferie_nuit) * TAUX_HS_FERIE_N / precise(100))
        
        montant_hs_total = montant_hs_30 + montant_hs_60 + montant_hs_nuit + montant_hs_ferie_j + montant_hs_ferie_n
        
        if montant_hs_total > 0:
            self.montants['total_gains'] += montant_hs_total
            self.montants['montant_heures_sup'] = montant_hs_total
            self.montants['montant_hs_30'] = montant_hs_30
            self.montants['montant_hs_60'] = montant_hs_60
            self.montants['montant_hs_nuit'] = montant_hs_nuit
            self.montants['montant_hs_ferie_jour'] = montant_hs_ferie_j
            self.montants['montant_hs_ferie_nuit'] = montant_hs_ferie_n
            
            # Ajouter à la base CNSS et imposable
            self.montants['cnss_base'] += montant_hs_total
            self.montants['imposable'] += montant_hs_total
            
            # Ajouter les lignes pour chaque type d'heures supplémentaires
            rubrique_hs = RubriquePaie.objects.filter(
                code_rubrique__icontains='HS',
                type_rubrique='gain',
                actif=True
            ).first()
            
            # Auto-création de la rubrique HS si absente
            if not rubrique_hs:
                rubrique_hs, _ = RubriquePaie.objects.get_or_create(
                    code_rubrique='HS_NORM',
                    defaults={
                        'libelle_rubrique': 'Heures supplémentaires',
                        'type_rubrique': 'gain',
                        'categorie_rubrique': 'autre',
                        'mode_calcul': 'horaire',
                        'soumis_cnss': True,
                        'soumis_irg': True,
                        'inclus_brut': True,
                        'exonere_rts': False,
                        'ordre_calcul': 50,
                        'ordre_affichage': 15,
                        'actif': True,
                        'entreprise': self.employe.entreprise if hasattr(self.employe, 'entreprise') else None,
                    }
                )
            if rubrique_hs:
                # Ligne récapitulative des heures supplémentaires
                # Calculer le taux de majoration moyen (en pourcentage de majoration, pas le coefficient appliqué)
                # Formule: (montant_hs_total / (salaire_horaire * heures_total)) * 100 - 100
                # Ou: ((taux_moyen_coeff - 1) * 100)
                if heures_total > 0:
                    coeff_moyen = montant_hs_total / (salaire_horaire * heures_total)
                    # Convertir le coefficient en pourcentage de majoration (ex: 1.60 → 60%)
                    taux_majoration = (coeff_moyen - Decimal('1')) * Decimal('100')
                else:
                    taux_majoration = Decimal('0')
                
                self.lignes.append({
                    'rubrique': rubrique_hs,
                    'base': salaire_horaire,
                    'taux': self._arrondir(taux_majoration),
                    'nombre': heures_total,
                    'montant': montant_hs_total,
                    'ordre': rubrique_hs.ordre_affichage
                })
    
    @staticmethod
    def _est_indemnite_forfaitaire(rubrique):
        """
        Détection intelligente des indemnités forfaitaires exonérées de RTS.
        
        Utilise 3 niveaux de détection (par priorité décroissante):
        1. Code exact (PT, PL, PCV, etc.)
        2. Pattern dans le code (TRANSPORT, LOGEMENT, CHERTE, etc.)
        3. Mots-clés dans le libellé (transport, logement, cherté de vie, etc.)
        
        Returns:
            tuple(bool, str): (est_forfaitaire, raison_detection)
        """
        code = (rubrique.code_rubrique or '').strip().upper()
        libelle = (rubrique.libelle_rubrique or '').strip().lower()
        
        # Niveau 1: Code exact
        if code in CODES_EXACTS_FORFAITAIRES:
            return True, f"code exact '{code}'"
        
        # Niveau 2: Pattern dans le code
        for pattern in PATTERNS_CODES_FORFAITAIRES:
            if pattern in code:
                return True, f"pattern code '{pattern}' dans '{code}'"
        
        # Niveau 3: Mots-clés dans le libellé
        for mot in MOTS_CLES_LIBELLE_FORFAITAIRES:
            if mot in libelle:
                return True, f"mot-clé '{mot}' dans libellé '{rubrique.libelle_rubrique}'"
        
        return False, ''
    
    def _appliquer_exoneration_indemnites_forfaitaires(self):
        """
        Applique l'exonération RTS des indemnités forfaitaires.

        Législation guinéenne (CGI Art. strict) :
        - Les indemnités forfaitaires (transport, logement, cherté de vie, etc.)
          sont exonérées de RTS dans la limite de 25% du salaire brut.
        - L'excédent au-delà du plafond est réintégré dans la base imposable RTS.
        - Les primes (récompense/motivation) sont intégralement imposables.

        Détection: utilise _est_indemnite_forfaitaire() pour classifier
        automatiquement les rubriques par code et libellé.
        """
        # Totaliser les indemnités forfaitaires détectées (arrondi à l'unité)
        total_indemnites = Decimal(str(sum(montant for _, montant, _ in self._indemnites_detectees))).quantize(Decimal("1"), rounding=ROUND_FLOOR)
        salaire_brut = self.montants.get('brut') or self.montants['total_gains']

        self.montants['indemnites_forfaitaires'] = total_indemnites
        self.montants['salaire_base_hors_indemnites'] = self.montants['imposable']

        # Récupérer les paramètres personnalisés de l'entreprise
        from .formules import evaluer_formule as _evaluer
        params = getattr(self.employe.entreprise, 'parametres_calcul_paie', None)

        if params and params.mode_exoneration_indemnites == 'integrale':
            # Exonération intégrale : toutes les indemnités sont exonérées
            exoneration_retenue = total_indemnites
            taux_plafond = Decimal('100')
            plafond = total_indemnites
        elif params and params.mode_exoneration_indemnites == 'formule' and params.formule_exoneration:
            # Formule personnalisée
            variables = self._construire_variables_formule()
            try:
                exoneration_retenue = self._arrondir(_evaluer(params.formule_exoneration, variables))
                exoneration_retenue = min(total_indemnites, exoneration_retenue)
            except ValueError:
                # Fallback plafond 25% si la formule échoue
                exoneration_retenue = min(total_indemnites, (salaire_brut * Decimal('25') / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_FLOOR))
            plafond = exoneration_retenue
            taux_plafond = (plafond * Decimal('100') / salaire_brut).quantize(Decimal('0.01')) if salaire_brut else Decimal('25')
        else:
            # Mode par défaut : plafond % du brut (CGI)
            pct = Decimal(str(params.plafond_exoneration_pct)) if params else Decimal('25')
            taux_plafond = pct
            plafond = (salaire_brut * pct / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_FLOOR)
            exoneration_retenue = min(total_indemnites, plafond)

        # Dépassement : total_indemnites - plafond (plafond déjà ROUND_FLOOR → entier)
        # NE PAS réarrondir exoneration_retenue : elle est min(total_indemnites, plafond)
        # → plafond est ROUND_FLOOR (entier), donc exoneration_retenue est déjà entier
        depassement = self._arrondir(max(Decimal('0'), total_indemnites - plafond))

        self.montants['plafond_indemnites'] = plafond
        self.montants['exoneration_indemnites'] = exoneration_retenue
        self.montants['depassement_plafond_indemnites'] = depassement
        self.montants['reintegration_base_imposable'] = depassement  # réintégré dans base RTS
        self.montants['taux_plafond_indemnites'] = taux_plafond

        # Alerte si dépassement du plafond 25%
        if depassement > 0:
            if 'alertes' not in self.montants:
                self.montants['alertes'] = []
            self.montants['alertes'].append({
                'type': 'avertissement',
                'message': (
                    f"Indemnités forfaitaires ({total_indemnites:,.0f} GNF) dépassent "
                    f"le plafond légal 25% du brut ({plafond:,.0f} GNF). "
                    f"Excédent de {depassement:,.0f} GNF réintégré dans la base RTS."
                )
            })

        # Stocker le détail des détections pour traçabilité
        self.montants['detail_indemnites_detectees'] = [
            {'code': r.code_rubrique, 'libelle': r.libelle_rubrique,
             'montant': m, 'raison': raison}
            for r, m, raison in self._indemnites_detectees
        ]

        # --- Analyse de conformité intelligente ---
        try:
            analyseur = AnalyseurConformiteIndemnites(
                employe=self.employe,
                montants=self.montants,
                indemnites_detectees=self._indemnites_detectees,
            )
            resultat_conformite = analyseur.analyser()
            self.montants['conformite_indemnites'] = resultat_conformite

            # Fusionner les alertes de conformité dans les alertes globales
            if 'alertes' not in self.montants:
                self.montants['alertes'] = []
            for alerte in resultat_conformite.get('alertes', []):
                icone = {'info': '🟢', 'attention': '🟡', 'risque': '🔴'}.get(alerte['niveau'], '⚪')
                self.montants['alertes'].append({
                    'type': alerte['niveau'],
                    'message': f"{icone} {alerte['message']}",
                    'action': alerte.get('action', ''),
                })
        except Exception as e:
            logger_conformite.warning(
                "Erreur analyse conformité indemnités (%s): %s", self.employe, e
            )

    def _calculer_cotisations_sociales(self):
        """Calculer les cotisations sociales (CNSS, etc.)
        
        Règles CNSS Guinée:
        - Plancher: SMIG (550 000 GNF) - on cotise au minimum sur ce montant
        - Plafond: 2 500 000 GNF - on cotise au maximum sur ce montant
        - Taux employé: 5% (retraite 2.5% + assurance maladie 2.5%)
        - Taux employeur: 18% (prestations familiales 6% + AT/MP 4% + retraite 4% + maladie 4%)
        """
        # Base CNSS = salaire brut total (CGI Guinée : CNSS sur l'ensemble de la rémunération)
        # On utilise le brut plutôt que cnss_base (accumulé via soumis_cnss) car toutes les
        # rubriques ne sont pas forcément taguées, et la loi guinéenne applique la CNSS sur
        # le brut global (plancher 550 000 / plafond 2 500 000 GNF).
        # Ne pas utiliser cnss_base accumule via soumis_cnss: il peut exclure les indemnites
        # exonerees de RTS/VF, alors que la CNSS reste calculee sur le brut plafonne.
        base_raw = self.montants['brut']
        base_raw = self._normaliser_base_taxable(
            'cnss_brut',
            'CNSS brute',
            base_raw,
            'salaire brut',
            fallback=self.montants.get('brut', Decimal('0')),
        )

        if self.devise_employe != self.devise_base:
            base_cnss_gnf = DeviseService.convertir_vers_gnf(
                base_raw,
                self.devise_employe,
                self.date_conversion
            )
        else:
            base_cnss_gnf = base_raw
        
        # Récupérer plancher et plafond CNSS (en GNF)
        # Plancher = 550 000 GNF - assiette minimale de cotisation
        plancher_cnss = self.constantes.get('PLANCHER_CNSS', Decimal('550000'))
        # Plafond = 2 500 000 GNF - assiette maximale de cotisation
        plafond_cnss = self.constantes.get('PLAFOND_CNSS', Decimal('2500000'))
        
        # Appliquer plancher et plafond CNSS
        # IMPORTANT: Le plancher ne s'applique que si le salarié a effectivement travaillé
        # Si salaire brut = 0 ou très faible (< 10% du plancher), pas de cotisation CNSS
        # Sinon: Si salaire < plancher : on cotise sur le plancher
        #        Si plancher <= salaire <= plafond : on cotise sur le salaire réel
        #        Si salaire > plafond : on cotise sur le plafond
        seuil_minimum = plancher_cnss * Decimal('0.10')  # 10% du plancher = 55 000 GNF
        
        if base_cnss_gnf < seuil_minimum:
            # Pas de cotisation CNSS si le salaire est quasi nul (absence totale, congé sans solde)
            base_cnss_plafonnee = Decimal('0')
        else:
            base_cnss_plafonnee = self._arrondir(max(min(base_cnss_gnf, plafond_cnss), plancher_cnss))
        base_cnss_plafonnee = self._normaliser_base_taxable(
            'cnss',
            'CNSS plafonnée',
            base_cnss_plafonnee,
            'base CNSS brute encadrée par plancher/plafond',
        )
        
        # Mettre à jour cnss_base avec la valeur réelle utilisée (pour affichage résumé)
        self.montants['cnss_base'] = base_cnss_plafonnee

        # CNSS salarié (utiliser TAUX_CNSS_EMPLOYE au lieu de TAUX_CNSS_SALARIE)
        taux_cnss = self.constantes.get('TAUX_CNSS_EMPLOYE', Decimal('5.00'))
        cnss_employe = self._arrondir(base_cnss_plafonnee * taux_cnss / Decimal('100'))

        self.montants['cnss_employe'] = cnss_employe
        self.montants['total_retenues'] += cnss_employe
        
        # Ajouter ligne CNSS
        rubrique_cnss = RubriquePaie.objects.filter(
            code_rubrique__icontains='CNSS',
            type_rubrique__in=['retenue', 'cotisation'],
            actif=True
        ).first()
        
        # Si pas trouvé, chercher par libellé
        if not rubrique_cnss:
            rubrique_cnss = RubriquePaie.objects.filter(
                libelle_rubrique__icontains='CNSS',
                type_rubrique__in=['retenue', 'cotisation'],
                actif=True
            ).first()
        
        if rubrique_cnss:
            self.lignes.append({
                'rubrique': rubrique_cnss,
                'base': base_cnss_plafonnee,  # Afficher la base plafonnée, pas la base brute
                'taux': taux_cnss,
                'nombre': Decimal('1'),
                'montant': cnss_employe,
                'ordre': rubrique_cnss.ordre_affichage
            })
        
        # CNSS employeur (appliquer aussi le plafond)
        taux_cnss_pat = self.constantes.get('TAUX_CNSS_EMPLOYEUR', Decimal('18.00'))
        self.montants['cnss_employeur'] = self._arrondir(
            base_cnss_plafonnee * taux_cnss_pat / Decimal('100')
        )
        
        # Base VF/TA = salaire brut total (en GNF si devise étrangère)
        base_vf_ta = max(Decimal('0'), self.montants['brut'])
        if self.devise_employe != self.devise_base:
            base_vf_ta = DeviseService.convertir_vers_gnf(
                self.montants['brut'],
                self.devise_employe,
                self.date_conversion
            )
        base_vf_ta = self._normaliser_base_taxable(
            'vf_brut',
            'VF/ONFPP brute',
            base_vf_ta,
            'salaire brut converti en GNF',
            fallback=self.montants.get('brut', Decimal('0')),
        )
        
        # Versement Forfaitaire (VF) - charge patronale
        # Mode standard GuineeRH optimise :
        #   Base VF/ONFPP = Brut - indemnites exonerees plafonnees.
        # Le mode "brut" reste disponible en legacy.
        taux_vf = self.constantes.get('TAUX_VF', Decimal('6.00'))
        exoneration_vf = self.montants.get('exoneration_indemnites', Decimal('0'))

        from .formules import evaluer_formule as _evaluer_vf
        params_vf = getattr(self.employe.entreprise, 'parametres_calcul_paie', None)
        mode_base_vf = params_vf.mode_base_vf if params_vf else 'brut'
        mode_base_onfpp = getattr(params_vf, 'mode_base_onfpp', 'brut') if params_vf else 'brut'

        if params_vf and params_vf.mode_base_vf == 'formule' and params_vf.formule_base_vf:
            # Mode personnalisé : formule définie par l'entreprise
            variables_vf = self._construire_variables_formule()
            variables_vf['brut'] = float(base_vf_ta)
            try:
                base_vf_nette = _evaluer_vf(params_vf.formule_base_vf, variables_vf)
                deduction_vf = base_vf_ta - base_vf_nette
            except ValueError:
                self._ajouter_alerte_calcul(
                    'avertissement',
                    "Formule personnalisée de base VF invalide. Calcul standard appliqué."
                )
                deduction_vf = Decimal('0')
                base_vf_nette = base_vf_ta
        elif not params_vf or params_vf.mode_base_vf == 'brut':
            # Mode legacy : base = brut directement, pas de déduction
            deduction_vf = Decimal('0')
            base_vf_nette = base_vf_ta
        else:
            # Mode par defaut : Brut - exoneration indemnitaire plafonnee
            deduction_vf = self._arrondir(min(exoneration_vf, base_vf_ta))
            base_vf_nette = base_vf_ta - deduction_vf

        base_vf_calculee = self._normaliser_base_taxable(
            'vf_calculee',
            'VF calculée',
            base_vf_nette,
            'formule VF ou calcul standard',
            fallback=base_vf_ta,
        )
        base_vf_nette = self._arrondir(max(Decimal('0'), min(base_vf_calculee, base_vf_ta)))
        deduction_vf = self._arrondir(base_vf_ta - base_vf_nette)
        base_vf_nette = self._normaliser_base_taxable(
            'vf',
            'VF',
            base_vf_nette,
            'remunerations brutes moins exemptions VF explicites',
        )

        self.montants['base_vf'] = base_vf_nette
        self.montants['deduction_vf'] = deduction_vf
        self.montants['mode_base_vf'] = mode_base_vf
        self.montants['mode_base_onfpp'] = mode_base_onfpp
        self.montants['taux_vf'] = taux_vf
        self.montants['versement_forfaitaire'] = self._arrondir(
            base_vf_nette * taux_vf / Decimal('100')
        )

        # TA et ONFPP sont mutuellement exclusifs selon le nombre de salariés:
        # - Moins du seuil: TA (2%) sur la base VF nette
        # - Seuil ou plus: ONFPP (1,5%) sur la base VF nette
        # Les taux sont FIXES par la loi guinéenne, non configurables.
        TAUX_TA_LEGAL = Decimal('2.00')       # Taxe d'Apprentissage: 2% (loi)
        TAUX_ONFPP_LEGAL = Decimal('1.50')    # ONFPP: 1,5% (loi)
        seuil_ta_onfpp = int(self.constantes.get('SEUIL_TA_ONFPP', Decimal('30')))
        if self.nb_salaries < seuil_ta_onfpp:
            self.montants['base_ta'] = self._normaliser_base_taxable(
                'ta',
                'TA',
                base_vf_nette,
                'base VF nette',
            )
            self.montants['taux_ta'] = TAUX_TA_LEGAL
            self.montants['taxe_apprentissage'] = self._arrondir(
                self.montants['base_ta'] * TAUX_TA_LEGAL / Decimal('100')
            )
            self.montants['base_onfpp'] = Decimal('0')
            self.montants['contribution_onfpp'] = Decimal('0')
        else:
            self.montants['taxe_apprentissage'] = Decimal('0')
            base_onfpp_source = base_vf_ta if mode_base_onfpp == 'brut' else base_vf_nette
            base_onfpp_libelle = 'salaire brut' if mode_base_onfpp == 'brut' else 'base VF nette'
            base_onfpp = self._normaliser_base_taxable(
                'onfpp',
                'ONFPP',
                base_onfpp_source,
                base_onfpp_libelle,
            )
            self.montants['base_onfpp'] = base_onfpp
            self.montants['contribution_onfpp'] = self._arrondir(
                base_onfpp * TAUX_ONFPP_LEGAL / Decimal('100')
            )
        
        # Total charges patronales (arrondi à l'unité GNF)
        self.montants['total_charges_patronales'] = self._arrondir(
            self.montants['cnss_employeur'] +
            self.montants['versement_forfaitaire'] +
            self.montants['taxe_apprentissage'] +
            self.montants['contribution_onfpp']
        )
        
        # Autres cotisations (mutuelle, retraite complémentaire, etc.)
        self._calculer_autres_cotisations()
    
    def _calculer_autres_cotisations(self):
        """Calculer les autres cotisations (mutuelle, retraite, etc.)"""
        # Calculer les bornes du mois pour filtrer par date
        dernier_jour = calendar.monthrange(self.periode.annee, self.periode.mois)[1]
        fin_mois = date(self.periode.annee, self.periode.mois, dernier_jour)
        debut_mois = date(self.periode.annee, self.periode.mois, 1)

        # Récupérer les éléments de retenue de type cotisation
        elements_cotis = ElementSalaire.objects.filter(
            employe=self.employe,
            rubrique__type_rubrique__in=['retenue', 'cotisation'],
            rubrique__code_rubrique__in=[
                'RETRAITE_COMPL_SAL', 'ASSUR_SANTE_COMPL',
                'FONDS_SOLID_TELECOM', 'COTIS_SYNDICAT_PROG',
                'MUTUELLE_ENT'
            ],
            actif=True,
            date_debut__lte=fin_mois
        ).filter(
            models.Q(date_fin__isnull=True) |
            models.Q(date_fin__gte=debut_mois)
        ).select_related('rubrique')
        
        for element in elements_cotis:
            montant = self._calculer_element(element, phase='cotisations')
            
            self.lignes.append({
                'rubrique': element.rubrique,
                'base': self.montants['cnss_base'],
                'taux': element.taux,
                'nombre': Decimal('1'),
                'montant': montant,
                'ordre': element.rubrique.ordre_affichage
            })
            
            self.montants['total_retenues'] += montant
    
    def _calculer_irg(self):
        """Calculer la RTS selon le barème progressif CGI Guinée officiel

        Base RTS = Brut - CNSS - Exonération indemnités forfaitaires (plafonnée à 25% du brut)
        L'excédent d'indemnités au-delà du plafond 25% est réintégré dans la base imposable.
        """
        # Base imposable = gains non-forfaitaires - CNSS
        # + réintégration de l'excédent d'indemnités au-delà du plafond 25%
        depassement = self.montants.get('depassement_plafond_indemnites', Decimal('0'))
        imposable_apres_absence = max(
            Decimal('0'),
            self.montants['imposable'] - self.montants.get('retenue_absence', Decimal('0'))
        )
        base_imposable_defaut = self._arrondir(imposable_apres_absence - self.montants['cnss_employe'] + depassement)

        # Vérifier si une formule personnalisée de base RTS est configurée
        from .formules import evaluer_formule as _evaluer_rts
        params_rts = getattr(self.employe.entreprise, 'parametres_calcul_paie', None)

        if params_rts and params_rts.utiliser_formule_base_rts and params_rts.formule_base_rts:
            variables_rts = self._construire_variables_formule()
            try:
                base_imposable = _evaluer_rts(params_rts.formule_base_rts, variables_rts)
            except ValueError:
                self._ajouter_alerte_calcul(
                    'avertissement',
                    "Formule personnalisée de base RTS invalide. Calcul standard appliqué."
                )
                base_imposable = base_imposable_defaut  # fallback calcul standard
        else:
            base_imposable = base_imposable_defaut

        # Exonération retenue = min(total indemnités, plafond 25%) pour affichage bulletin
        self.montants['abattement_forfaitaire'] = self.montants.get('exoneration_indemnites',
            self.montants.get('indemnites_forfaitaires', Decimal('0')))
        
        # Convertir en GNF si nécessaire (la RTS est toujours calculée en GNF)
        if self.devise_employe != self.devise_base:
            base_imposable = DeviseService.convertir_vers_gnf(
                base_imposable, 
                self.devise_employe, 
                self.date_conversion
            )
        base_imposable = self._normaliser_base_taxable(
            'rts',
            'RTS',
            base_imposable,
            'brut imposable - CNSS salarié + réintégrations',
            fallback=base_imposable_defaut,
        )
        
        # Vérifier exonération RTS pour stagiaires/apprentis
        exoneration_rts, raison_exoneration = self._verifier_exoneration_rts_stagiaire()
        
        if exoneration_rts:
            # Stagiaire/apprenti exonéré de RTS
            self.montants['irg'] = Decimal('0')
            self.montants['base_rts'] = base_imposable
            self.montants['taux_effectif_rts'] = Decimal('0')
            self.montants['exoneration_rts'] = True
            self.montants['raison_exoneration_rts'] = raison_exoneration
        else:
            # RTS Guinée (Retenue à la Source) = barème progressif sur base_imposable
            # Base RTS = gains non-forfaitaires - CNSS (indemnités forfaitaires intégralement exonérées)
            # Pas de déductions familiales ni d'abattement professionnel pour la RTS
            # (ces déductions s'appliquent uniquement à l'IGR annuel)
            irg_brut = self._calculer_irg_progressif(base_imposable)
            
            # Appliquer crédits d'impôt
            credits = self._calculer_credits_impot()
            irg_net = max(Decimal('0'), irg_brut - credits)
            
            self.montants['irg'] = self._arrondir(irg_net)
            self.montants['base_rts'] = base_imposable
            # Taux effectif RTS = montant RTS / base imposable × 100
            if base_imposable > 0:
                self.montants['taux_effectif_rts'] = (
                    Decimal(str(self.montants['irg'])) * Decimal('100') / Decimal(str(base_imposable))
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                self.montants['taux_effectif_rts'] = Decimal('0')
            self.montants['exoneration_rts'] = False
        self.montants['total_retenues'] += self.montants['irg']
        
        # Ajouter ligne RTS/IRG
        rubrique_irg = RubriquePaie.objects.filter(
            code_rubrique__iregex=r'(IRS|IRG|RTS|IRPP)',
            type_rubrique__in=['retenue', 'cotisation'],
            actif=True
        ).first()
        
        # Si pas trouvé, chercher par libellé
        if not rubrique_irg:
            rubrique_irg = RubriquePaie.objects.filter(
                libelle_rubrique__iregex=r'(IRS|IRG|RTS|IRPP|Impôt|Revenu)',
                type_rubrique__in=['retenue', 'cotisation'],
                actif=True
            ).first()
        
        if rubrique_irg:
            self.lignes.append({
                'rubrique': rubrique_irg,
                'base': base_imposable,
                'taux': None,
                'nombre': Decimal('1'),
                'montant': self.montants['irg'],
                'ordre': rubrique_irg.ordre_affichage
            })
    
    def _verifier_exoneration_rts_stagiaire(self):
        """
        Vérifie si l'employé est éligible à l'exonération RTS pour stagiaires/apprentis.
        
        Conditions (législation guinéenne):
        - Type de contrat: Stage ou Apprentissage
        - Durée: Maximum 12 mois depuis le début du contrat
        - Indemnité: ≤ 1 200 000 GNF/mois
        
        Returns:
            tuple: (exonere: bool, raison: str)
        """
        from datetime import date
        
        # Seuil d'exonération pour stagiaires/apprentis (depuis constantes ou défaut)
        SEUIL_EXONERATION = self.constantes.get('SEUIL_EXON_STAGIAIRE', Decimal('1200000'))
        
        # Vérifier si l'employé est stagiaire ou apprenti
        if not hasattr(self.employe, 'est_stagiaire_ou_apprenti') or not self.employe.est_stagiaire_ou_apprenti:
            return False, "Non stagiaire/apprenti"
        
        # Vérifier l'éligibilité (durée max 12 mois)
        date_calcul = date(self.periode.annee, self.periode.mois, 1)
        eligible, raison = self.employe.est_eligible_exoneration_rts(date_calcul)
        
        if not eligible:
            return False, raison
        
        # Vérifier le montant de l'indemnité (≤ 1 200 000 GNF)
        salaire_brut = self.montants['brut']
        
        # Convertir en GNF si nécessaire
        if self.devise_employe != self.devise_base:
            salaire_brut = DeviseService.convertir_vers_gnf(
                salaire_brut, 
                self.devise_employe, 
                self.date_conversion
            )
        
        if salaire_brut > SEUIL_EXONERATION:
            return False, f"Indemnité {salaire_brut:,.0f} GNF > seuil {SEUIL_EXONERATION:,.0f} GNF"
        
        return True, f"Exonéré RTS: {raison} - Indemnité ≤ {SEUIL_EXONERATION:,.0f} GNF"
    
    def _calculer_deductions_familiales(self):
        """Calculer les déductions familiales selon la législation guinéenne"""
        deductions = Decimal('0')
        
        # Conjoint (déduction pour personne mariée)
        if self.employe.situation_matrimoniale in ['marie', 'Marié(e)', 'Marié', 'Marié']:
            deduction_conjoint = self.constantes.get('DEDUC_CONJOINT', Decimal('100000'))
            deductions += deduction_conjoint
        
        # Enfants à charge (max 4 enfants en Guinée)
        if self.employe.nombre_enfants:
            max_enfants = int(self.constantes.get('MAX_ENFANTS_DEDUC', Decimal('4')))
            nb_enfants = min(self.employe.nombre_enfants, max_enfants)
            
            deduction_enfant = self.constantes.get('DEDUC_ENFANT', Decimal('50000'))
            deductions += deduction_enfant * nb_enfants
        
        return deductions
    
    def _calculer_abattement_professionnel(self, base):
        """Calculer l'abattement professionnel (5% plafonné)"""
        taux_abattement = self.constantes.get('TAUX_ABATTEMENT_PRO', Decimal('5.00'))
        plafond = self.constantes.get('PLAFOND_ABATTEMENT_PRO', Decimal('1000000'))

        abattement = base * taux_abattement / Decimal('100')
        return min(abattement, plafond)
    
    def _calculer_irg_progressif(self, base_imposable):
        """
        Calcule la RTS (Retenue à la Source) selon le barème progressif CGI Guinée.

        Barème officiel CGI 2022+ (cf. manuel_paie_guinee_CORRIGE_2026) :
            T1 : 0           - 1 000 000   GNF  → 0%
            T2 : 1 000 001   - 3 000 000   GNF  → 5%
            T3 : 3 000 001   - 5 000 000   GNF  → 8%
            T4 : 5 000 001   - 10 000 000  GNF  → 10%
            T5 : 10 000 001  - 20 000 000  GNF  → 15%
            T6 : au-delà de 20 000 000     GNF  → 20%

        Les bornes sont lues depuis TrancheRTS (DB) avec fallback codé en dur
        dans _charger_tranches_irg. On normalise les bornes pour que les gaps
        de 1 GNF (ex : T1 finit à 1 000 000 et T2 commence à 1 000 001) ne
        causent pas de perte de 1 GNF dans le calcul progressif.

        Exemple (base = 3 185 426) :
            T1 :   1 000 000 ×  0% =        0
            T2 :   2 000 000 ×  5% =  100 000
            T3 :     185 426 ×  8% =   14 834
            TOTAL RTS                 114 834 GNF
        """
        if base_imposable <= 0:
            return Decimal('0')

        seuils = self._construire_seuils_rts()

        irg_total = Decimal('0')
        for borne_inf, borne_sup, taux in seuils:
            if base_imposable <= borne_inf:
                break

            if borne_sup is not None:
                montant_tranche = min(base_imposable, borne_sup) - borne_inf
            else:
                montant_tranche = base_imposable - borne_inf

            if montant_tranche > 0:
                irg_total += self._arrondir(montant_tranche * taux / Decimal('100'))

        return irg_total

    def _construire_seuils_rts(self):
        """Normalise les tranches RTS en seuils contigus (borne_inf, borne_sup, taux).

        Source unique de vérité pour le calcul RTS et la trace d'audit : si
        les bornes de la DB présentent un gap de 1 GNF (1 000 000 / 1 000 001),
        on aligne borne_inf sur la borne_sup précédente pour éviter qu'un
        franc de base échappe au calcul progressif.
        """
        seuils = []
        for i, tranche in enumerate(self.tranches_irg):
            if isinstance(tranche, dict):
                borne_inf = Decimal(str(tranche['borne_inferieure']))
                borne_sup = tranche.get('borne_superieure')
                taux = Decimal(str(tranche['taux_irg']))
            else:
                borne_inf = tranche.borne_inferieure
                borne_sup = tranche.borne_superieure
                taux = tranche.taux_irg

            if i > 0 and seuils:
                prev_sup = seuils[-1][1]
                if prev_sup is not None and borne_inf > prev_sup and borne_inf <= prev_sup + 2:
                    borne_inf = prev_sup

            if borne_sup is not None:
                borne_sup = Decimal(str(borne_sup))

            seuils.append((borne_inf, borne_sup, taux))
        return seuils
    
    def _calculer_credits_impot(self):
        """Calculer les crédits d'impôt"""
        # Pour l'instant, retourner 0
        # À implémenter selon les besoins (formation, épargne retraite, etc.)
        return Decimal('0')
    
    def _calculer_autres_retenues(self):
        """Calculer les autres retenues (avances, prêts, etc.)"""
        # Codes déjà traités par CNSS, RTS et rappels/manquements — à exclure
        codes_deja_traites = [
            'RAPPEL_SALAIRE', 'COMPLEMENT_SALAIRE',
            'RETENUE_TROP_PERCU', 'MANQUEMENT_SALAIRE',
        ]

        # Calculer les bornes du mois pour filtrer par date
        dernier_jour = calendar.monthrange(self.periode.annee, self.periode.mois)[1]
        fin_mois = date(self.periode.annee, self.periode.mois, dernier_jour)
        debut_mois = date(self.periode.annee, self.periode.mois, 1)

        # Récupérer TOUTES les retenues actives, sauf celles déjà traitées
        # et sauf les cotisations (traitées dans _calculer_autres_cotisations)
        elements_retenues = ElementSalaire.objects.filter(
            employe=self.employe,
            rubrique__type_rubrique='retenue',
            actif=True,
            date_debut__lte=fin_mois
        ).filter(
            models.Q(date_fin__isnull=True) |
            models.Q(date_fin__gte=debut_mois)
        ).exclude(
            rubrique__code_rubrique__in=codes_deja_traites
        ).exclude(
            # Exclure les rubriques CNSS (déjà calculées dans _calculer_cotisations_sociales)
            rubrique__code_rubrique__icontains='CNSS'
        ).exclude(
            # Exclure les rubriques RTS/IRG (déjà calculées dans _calculer_irg)
            rubrique__code_rubrique__iregex=r'(IRS|IRG|RTS|IRPP)'
        ).exclude(
            # Exclure cotisations déjà traitées dans _calculer_autres_cotisations
            rubrique__code_rubrique__in=[
                'RETRAITE_COMPL_SAL', 'ASSUR_SANTE_COMPL',
                'FONDS_SOLID_TELECOM', 'COTIS_SYNDICAT_PROG',
                'MUTUELLE_ENT'
            ]
        ).select_related('rubrique')
        
        for element in elements_retenues:
            montant = self._calculer_element(element, phase='retenues')
            
            self.lignes.append({
                'rubrique': element.rubrique,
                'base': montant,
                'taux': None,
                'nombre': Decimal('1'),
                'montant': montant,
                'ordre': element.rubrique.ordre_affichage
            })
            
            self.montants['total_retenues'] += montant
    
    def _appliquer_rappels_manquements(self):
        """
        Appliquer les rappels de salaire (compléments) et retenues pour trop-perçu
        du mois précédent. Ces montants ne sont PAS inclus dans la base de calcul
        (CNSS, RTS, VF, TA, ONFPP) — ils affectent uniquement le net à payer.
        """
        # Calculer les bornes du mois pour filtrer par date
        dernier_jour = calendar.monthrange(self.periode.annee, self.periode.mois)[1]
        fin_mois = date(self.periode.annee, self.periode.mois, dernier_jour)
        debut_mois = date(self.periode.annee, self.periode.mois, 1)

        elements_rappels = ElementSalaire.objects.filter(
            employe=self.employe,
            rubrique__type_rubrique='gain',
            rubrique__code_rubrique__in=['RAPPEL_SALAIRE', 'COMPLEMENT_SALAIRE'],
            actif=True,
            date_debut__lte=fin_mois
        ).filter(
            models.Q(date_fin__isnull=True) |
            models.Q(date_fin__gte=debut_mois)
        ).select_related('rubrique')
        
        for element in elements_rappels:
            montant = element.montant or Decimal('0')
            if montant > 0:
                self.montants['rappel_salaire'] += montant
                self.lignes.append({
                    'rubrique': element.rubrique,
                    'base': montant,
                    'taux': None,
                    'nombre': Decimal('1'),
                    'montant': montant,
                    'ordre': element.rubrique.ordre_affichage
                })
        
        elements_trop_percu = ElementSalaire.objects.filter(
            employe=self.employe,
            rubrique__type_rubrique='retenue',
            rubrique__code_rubrique__in=['RETENUE_TROP_PERCU', 'MANQUEMENT_SALAIRE'],
            actif=True,
            date_debut__lte=fin_mois
        ).filter(
            models.Q(date_fin__isnull=True) |
            models.Q(date_fin__gte=debut_mois)
        ).select_related('rubrique')
        
        for element in elements_trop_percu:
            montant = element.montant or Decimal('0')
            if montant > 0:
                self.montants['retenue_trop_percu'] += montant
                self.lignes.append({
                    'rubrique': element.rubrique,
                    'base': montant,
                    'taux': None,
                    'nombre': Decimal('1'),
                    'montant': montant,
                    'ordre': element.rubrique.ordre_affichage
                })

    def _construire_audit_calcul(self) -> dict:
        """
        Trace complète du calcul pour audit DGI/CNSS/client.
        Toutes les valeurs sont passées par money() — vérité comptable.
        """
        m = self.montants

        # Détail des tranches RTS — on utilise les mêmes seuils normalisés
        # que le calcul principal pour garantir que base_imposable affichée
        # par tranche = base réellement taxée. Sans ça, un écart de 1 GNF
        # apparaît quand la DB a des bornes en +1 (1 000 001 vs 1 000 000).
        tranches_detail = []
        base_rts = m.get('base_rts', Decimal('0'))
        seuils = self._construire_seuils_rts()
        for i, (borne_inf, borne_sup, taux) in enumerate(seuils):
            if base_rts <= borne_inf:
                break
            if borne_sup is not None:
                tranche_base = min(base_rts, borne_sup) - borne_inf
            else:
                tranche_base = base_rts - borne_inf
            if tranche_base <= 0:
                continue
            montant_tranche = money(tranche_base * taux / Decimal('100'))
            numero = i + 1
            raw = self.tranches_irg[i] if i < len(self.tranches_irg) else None
            if isinstance(raw, dict):
                numero = int(raw.get('numero_tranche', numero))
            elif raw is not None:
                numero = int(getattr(raw, 'numero_tranche', numero))
            tranches_detail.append({
                'numero': numero,
                'de': int(borne_inf),
                'a': int(borne_sup) if borne_sup is not None else None,
                'taux_pct': float(taux),
                'base': int(money(tranche_base)),
                'impot': int(montant_tranche),
            })

        # Heures supplémentaires
        hs = {}
        if m.get('montant_heures_sup', Decimal('0')) > 0:
            hs = {
                'taux_horaire': int(money(self._obtenir_base_calcul('SALAIRE_BASE') /
                                   self.constantes.get('HEURES_MENSUELLES', Decimal('173.33')))),
                'montant_30pct': int(m.get('montant_hs_30', Decimal('0'))),
                'montant_60pct': int(m.get('montant_hs_60', Decimal('0'))),
                'montant_nuit':  int(m.get('montant_hs_nuit', Decimal('0'))),
                'montant_ferie': int(m.get('montant_hs_ferie_jour', Decimal('0'))),
                'total':         int(m.get('montant_heures_sup', Decimal('0'))),
            }

        brut     = int(money(m.get('brut', Decimal('0'))))
        retenues = int(money(m.get('total_retenues', Decimal('0'))))
        net      = int(money(m.get('net', Decimal('0'))))

        return {
            'version': '2.0',
            'pipeline': {
                '1_gains': {
                    'salaire_base':        int(money(m.get('salaire_base', Decimal('0')))),
                    'indemnites':          int(money(m.get('indemnites_forfaitaires', Decimal('0')))),
                    'heures_sup':          hs,
                    'total_gains':         int(money(m.get('total_gains', Decimal('0')))),
                    'brut':                brut,
                },
                '2_cotisations': {
                    'cnss_base':           int(money(m.get('cnss_base', Decimal('0')))),
                    'cnss_plafond':        int(self.constantes.get('PLAFOND_CNSS', Decimal('2500000'))),
                    'cnss_employe':        int(money(m.get('cnss_employe', Decimal('0')))),
                },
                '3_fiscal': {
                    'indemnites_exonerees':int(money(m.get('indemnites_forfaitaires', Decimal('0')))),
                    'plafond_25pct':       int(money(m.get('brut', Decimal('0')) * Decimal('0.25'))),
                    'base_imposable':      int(money(m.get('base_rts', Decimal('0')))),
                    'formule':             'brut - cnss_employe - indemnites_exonerees',
                    'tranches_rts':        tranches_detail,
                    'rts_total':           int(money(m.get('irg', Decimal('0')))),
                    'taux_effectif_pct':   float(m.get('taux_effectif_rts', Decimal('0'))),
                },
                '4_retenues': {
                    'cnss_employe':        int(money(m.get('cnss_employe', Decimal('0')))),
                    'rts':                 int(money(m.get('irg', Decimal('0')))),
                    'avances':             int(money(m.get('total_retenues', Decimal('0'))
                                               - m.get('cnss_employe', Decimal('0'))
                                               - m.get('irg', Decimal('0')))),
                    'total_retenues':      retenues,
                    'formule':             'brut - total_retenues = net',
                    'verification':        f"{brut} - {retenues} = {brut - retenues} ({'✅ OK' if brut - retenues == net else '❌ ECART'})",
                },
                '5_net': {
                    'brut':                brut,
                    'total_retenues':      retenues,
                    'net_a_payer':         net,
                },
                '6_charges_patronales': {
                    'mode_base_vf':        m.get('mode_base_vf', 'brut_moins_deduction'),
                    'mode_base_onfpp':     m.get('mode_base_onfpp', 'base_vf'),
                    'base_vf':             int(money(m.get('base_vf', Decimal('0')))),
                    'base_onfpp':          int(money(m.get('base_onfpp', Decimal('0')))),
                    'deduction_vf':        int(money(m.get('deduction_vf', Decimal('0')))),
                    'cnss_employeur':      int(money(m.get('cnss_employeur', Decimal('0')))),
                    'vf':                  int(money(m.get('versement_forfaitaire', Decimal('0')))),
                    'ta':                  int(money(m.get('taxe_apprentissage', Decimal('0')))),
                    'onfpp':               int(money(m.get('contribution_onfpp', Decimal('0')))),
                    'total':               int(money(m.get('total_charges_patronales', Decimal('0')))),
                    'cout_total_employeur':brut + int(money(m.get('total_charges_patronales', Decimal('0')))),
                },
            },
        }

    def _construire_snapshot(self):
        """Construit un snapshot JSON des paramètres utilisés pour ce calcul.

        Permet de reproduire exactement le même calcul ultérieurement,
        même si les constantes ou le barème RTS changent entre-temps.
        """
        # Constantes utilisées (déjà surchargées par config entreprise)
        constantes_snapshot = {
            k: str(v) for k, v in self.constantes.items()
        }

        # Barème RTS
        bareme_rts = []
        for t in self.tranches_irg:
            bareme_rts.append({
                'tranche': t.get('numero_tranche'),
                'min': str(t.get('borne_inferieure', 0)),
                'max': str(t.get('borne_superieure', '')),
                'taux': str(t.get('taux_irg', 0)),
            })

        from datetime import datetime

        # ── Traçabilité verrou CGI indemnités ──
        params = getattr(self.employe.entreprise, 'parametres_calcul_paie', None)
        plafond_pct_applique = Decimal(str(params.plafond_exoneration_pct)) if params else Decimal('25')
        mode_exo = params.mode_exoneration_indemnites if params else 'plafond_pct'
        total_ind = self.montants.get('indemnites_forfaitaires', Decimal('0'))
        plafond_val = self.montants.get('plafond_indemnites', Decimal('0'))
        tentative_depassement = total_ind > plafond_val if plafond_val > 0 else False

        snapshot = {
            'version': '2.0',
            'meta': {
                'generated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                'version_bareme': f"GN-{self.periode.annee}-v1",
                'periode': f"{self.periode.mois:02d}/{self.periode.annee}",
                'nb_salaries': self.nb_salaries,
                'devise': str(self.devise_employe) if self.devise_employe else None,
            },
            'constantes': constantes_snapshot,
            'bareme_rts': bareme_rts,
            'audit_calcul': self._construire_audit_calcul(),
            'bases_taxables': self.montants.get('bases_taxables', {}),
            'verrou_cgi': {
                'plafond_indemnites_pct': str(plafond_pct_applique),
                'plafond_applique': True,
                'mode_force': mode_exo,
                'tentative_depassement': tentative_depassement,
                'plafond_max_autorise': '25',
            },
            'conformite_indemnites': self.montants.get('conformite_indemnites', {}),
        }
        return _to_json_safe(snapshot)

    @transaction.atomic
    def generer_bulletin(self, utilisateur=None):
        """Générer le bulletin de paie dans la base de données"""
        # Calculer le bulletin
        self.calculer_bulletin()
        
        bulletin_existant = BulletinPaie.objects.filter(
            employe=self.employe,
            periode=self.periode,
        ).first()
        if bulletin_existant and bulletin_existant.statut_bulletin in BulletinPaie.STATUTS_VERROUILLES:
            raise PermissionError(
                f"Bulletin {bulletin_existant.numero_bulletin} déjà {bulletin_existant.statut_bulletin}; "
                "impossible de le recalculer."
            )

        # Générer le numéro de bulletin uniquement pour une nouvelle fiche.
        numero = bulletin_existant.numero_bulletin if bulletin_existant else self._generer_numero_bulletin()
        
        # Créer le bulletin
        bulletin_data = {
            'employe': self.employe,
            'periode': self.periode,
            'numero_bulletin': numero,
            'mois_paie': self.periode.mois,
            'annee_paie': self.periode.annee,
            'salaire_brut': self.montants['brut'],
            'cnss_employe': self.montants['cnss_employe'],
            'irg': self.montants['irg'],
            'net_a_payer': self.montants['net'],
            'cnss_employeur': self.montants['cnss_employeur'],
            'devise_bulletin': self.devise_employe,
            'statut_bulletin': 'calcule',
            'date_calcul': timezone.now()
        }
        
        # Rappels et manquements (hors base)
        bulletin_data['rappel_salaire'] = self.montants.get('rappel_salaire', Decimal('0'))
        bulletin_data['retenue_trop_percu'] = self.montants.get('retenue_trop_percu', Decimal('0'))
        
        # RTS détail (base, taux effectif)
        bulletin_data['base_rts'] = self.montants.get('base_rts', Decimal('0'))
        bulletin_data['taux_effectif_rts'] = self.montants.get('taux_effectif_rts', Decimal('0'))
        
        # Ajouter VF, TA et ONFPP (charges patronales)
        bulletin_data['versement_forfaitaire'] = self.montants.get('versement_forfaitaire', Decimal('0'))
        bulletin_data['taxe_apprentissage'] = self.montants.get('taxe_apprentissage', Decimal('0'))
        bulletin_data['taux_ta'] = self.montants.get('taux_ta', Decimal('0'))
        bulletin_data['contribution_onfpp'] = self.montants.get('contribution_onfpp', Decimal('0'))
        
        # Salaire de base (pour calcul taux horaire HS dans le PDF)
        bulletin_data['salaire_base'] = self._obtenir_base_calcul('SALAIRE_BASE')

        # Heures de travail et primes HS
        bulletin_data['heures_normales'] = self.montants.get('heures_travaillees', Decimal('0'))
        bulletin_data['heures_supplementaires_30'] = self.montants.get('heures_sup_30', Decimal('0'))
        bulletin_data['heures_supplementaires_60'] = self.montants.get('heures_sup_60', Decimal('0'))
        bulletin_data['heures_nuit'] = self.montants.get('heures_sup_nuit', Decimal('0'))
        bulletin_data['heures_feries'] = self.montants.get('heures_sup_ferie_jour', Decimal('0'))
        bulletin_data['heures_feries_nuit'] = self.montants.get('heures_sup_ferie_nuit', Decimal('0'))
        bulletin_data['prime_heures_sup'] = self.montants.get('montant_heures_sup', Decimal('0'))
        bulletin_data['prime_nuit'] = self.montants.get('montant_hs_nuit', Decimal('0'))
        bulletin_data['prime_feries'] = self.montants.get('montant_hs_ferie_jour', Decimal('0'))
        bulletin_data['prime_feries_nuit'] = self.montants.get('montant_hs_ferie_nuit', Decimal('0'))
        
        # Champs de transparence/conformité
        bulletin_data['abattement_forfaitaire'] = self.montants.get('abattement_forfaitaire', Decimal('0'))
        bulletin_data['base_vf'] = self.montants.get('base_vf', Decimal('0'))
        bulletin_data['base_onfpp'] = self.montants.get('base_onfpp', Decimal('0'))
        bulletin_data['nombre_salaries'] = self.nb_salaries

        # Snapshot des paramètres figés pour audit et reproductibilité
        bulletin_data['snapshot_parametres'] = self._construire_snapshot()
        
        # ✨ NOUVEAU: Calculer et créer automatiquement les congés acquis
        # Cela crée/met à jour le SoldeConge avec ancienneté-based calculation
        self._calculer_conges_acquis()
        
        if bulletin_existant:
            for champ, valeur in bulletin_data.items():
                setattr(bulletin_existant, champ, valeur)
            bulletin_existant.save()
            LigneBulletin.objects.filter(bulletin=bulletin_existant).delete()
            bulletin = bulletin_existant
            action = 'recalcul'
            description = f'Recalcul du bulletin {numero}'
        else:
            bulletin = BulletinPaie.objects.create(**bulletin_data)
            action = 'creation'
            description = f'Création du bulletin {numero}'
        
        # Créer les lignes
        for ligne_data in sorted(self.lignes, key=lambda x: x['ordre']):
            LigneBulletin.objects.create(
                bulletin=bulletin,
                rubrique=ligne_data['rubrique'],
                base=ligne_data['base'],
                taux=ligne_data['taux'],
                nombre=ligne_data['nombre'],
                montant=ligne_data['montant'],
                ordre=ligne_data['ordre']
            )
        
        # Mettre à jour les cumuls
        if self._heures_sup_detail_ids:
            HeureSupplementaire.objects.filter(
                pk__in=self._heures_sup_detail_ids
            ).update(statut='paye', bulletin=bulletin)

        self._mettre_a_jour_cumuls(bulletin)
        
        # Historique
        HistoriquePaie.objects.create(
            bulletin=bulletin,
            periode=self.periode,
            employe=self.employe,
            type_action=action,
            description=description,
            utilisateur=utilisateur,
            valeurs_apres={
                'brut': float(self.montants['brut']),
                'net': float(self.montants['net']),
                'irg': float(self.montants['irg']),
            }
        )
        
        return bulletin
    
    def _generer_numero_bulletin(self):
        """Générer un numéro unique de bulletin — basé sur max id, jamais sur count()"""
        prefix = f"BUL-{self.periode.annee}-{self.periode.mois:02d}"
        # Utiliser le dernier numéro existant pour ce préfixe, pas count()
        # count() provoque des collisions si un bulletin a été supprimé
        last = BulletinPaie.objects.filter(
            numero_bulletin__startswith=prefix
        ).order_by('-numero_bulletin').first()
        if last:
            try:
                last_num = int(last.numero_bulletin.split('-')[-1])
            except (ValueError, IndexError):
                last_num = BulletinPaie.objects.filter(
                    annee_paie=self.periode.annee,
                    mois_paie=self.periode.mois
                ).count()
        else:
            last_num = 0
        return f"{prefix}-{last_num + 1:04d}"
    
    def _mettre_a_jour_cumuls(self, bulletin):
        """Mettre à jour les cumuls annuels"""
        cumul, created = CumulPaie.objects.get_or_create(
            employe=self.employe,
            annee=self.periode.annee,
            defaults={
                'cumul_brut': Decimal('0'),
                'cumul_imposable': Decimal('0'),
                'cumul_net': Decimal('0'),
                'cumul_cnss_employe': Decimal('0'),
                'cumul_cnss_employeur': Decimal('0'),
                'cumul_irg': Decimal('0'),
                'nombre_bulletins': 0
            }
        )

        totaux = BulletinPaie.objects.filter(
            employe=self.employe,
            periode__annee=self.periode.annee,
        ).aggregate(
            cumul_brut=models.Sum('salaire_brut'),
            cumul_net=models.Sum('net_a_payer'),
            cumul_cnss_employe=models.Sum('cnss_employe'),
            cumul_cnss_employeur=models.Sum('cnss_employeur'),
            cumul_irg=models.Sum('irg'),
            nombre_bulletins=models.Count('id'),
        )

        cumul.cumul_brut = totaux['cumul_brut'] or Decimal('0')
        cumul.cumul_net = totaux['cumul_net'] or Decimal('0')
        cumul.cumul_cnss_employe = totaux['cumul_cnss_employe'] or Decimal('0')
        cumul.cumul_cnss_employeur = totaux['cumul_cnss_employeur'] or Decimal('0')
        cumul.cumul_irg = totaux['cumul_irg'] or Decimal('0')
        cumul.nombre_bulletins = totaux['nombre_bulletins'] or 0
        cumul.save()
    
    def _calculer_anciennete_mois(self, date_embauche, date_ref=None):
        """
        Calcule l'ancienneté en mois entre date_embauche et date_ref.
        Règle : un mois est compté si l'employé a travaillé au moins un jour dans ce mois.
        Ex : embauché 01/02/2026, période février 2026 → 1 mois
        Ex : embauché 15/02/2026, période février 2026 → 1 mois
        Ex : embauché 01/01/2026, période février 2026 → 2 mois
        """
        from datetime import date as date_cls
        if date_ref is None:
            date_ref = date_cls.today()

        if not date_embauche:
            return Decimal('0')

        # Nombre de mois entre le mois d'embauche et le mois de référence (inclus)
        # Un mois partiel compte comme 1 mois complet (pro-rata géré ailleurs)
        years_diff = date_ref.year - date_embauche.year
        months_diff = date_ref.month - date_embauche.month
        anciennete = (years_diff * 12) + months_diff + 1  # +1 : mois d'embauche compte

        return max(Decimal('0'), Decimal(str(anciennete)))

    def _calculer_conges_acquis(self):
        """
        Calcule automatiquement les congés acquis selon la règle guinéenne
        et crée/met à jour le SoldeConge de l'employé
        
        Règle: 2.5 jours par mois d'ancienneté (Code du Travail Guinée)
        Bonus ancienneté: +2 jours par 5 ans (configurable via ConfigPaieEntreprise)
        Maximum: 30 jours par an
        
        Returns:
            Decimal: Nombre de congés acquis
        """
        from temps_travail.models import SoldeConge
        
        try:
            emp = self.employe
            
            # Vérifier que l'employé a une date d'embauche
            if not emp.date_embauche:
                return Decimal('0')
            
            # Calculer l'ancienneté totale pour les bonus, puis les seuls mois
            # acquis dans l'année de paie pour le droit de base.
            dernier_jour = date(
                self.periode.annee, 
                self.periode.mois, 
                calendar.monthrange(self.periode.annee, self.periode.mois)[1]
            )
            anciennete_mois = self._calculer_anciennete_mois(emp.date_embauche, dernier_jour)
            if emp.date_embauche > dernier_jour:
                mois_acquis_annee = 0
            else:
                premier_mois = emp.date_embauche.month if emp.date_embauche.year == self.periode.annee else 1
                mois_acquis_annee = max(0, self.periode.mois - premier_mois + 1)
            
            # Récupérer la configuration de paie (jours/mois)
            # Initialiser config_paie à None avant toute tentative
            config_paie = None
            try:
                config_paie = self.config_paie
            except Exception:
                pass
            # Fallback robuste: chercher par entreprise directement dans le modèle
            if not config_paie and emp.entreprise:
                from paie.models import ConfigurationPaieEntreprise
                config_paie = ConfigurationPaieEntreprise.objects.filter(
                    entreprise=emp.entreprise
                ).first()
            # Fallback final: première config disponible
            if not config_paie:
                from paie.models import ConfigurationPaieEntreprise
                config_paie = ConfigurationPaieEntreprise.objects.first()
            
            # Déterminer le nombre de jours par mois
            if config_paie:
                jours_par_mois = config_paie.jours_conges_par_mois or Decimal('2.50')
            else:
                # Par défaut: 2.5 jours/mois (Code du Travail Guinée)
                jours_par_mois = Decimal('2.50')
            
            # Acquisition progressive de l'année, plafonnée à douze mois.
            conges_acquis = Decimal(str(min(mois_acquis_annee, 12))) * jours_par_mois
            
            # Ajouter bonus ancienneté si applicable
            if config_paie and hasattr(config_paie, 'jours_conges_anciennete') and config_paie.jours_conges_anciennete:
                # Bonus: ajout de jours selon tranches d'ancienneté
                # Ex: +2 jours tous les 5 ans
                if hasattr(config_paie, 'tranche_anciennete_annees') and config_paie.tranche_anciennete_annees:
                    anciennete_ans = int(anciennete_mois / 12)
                    bonus = (anciennete_ans // config_paie.tranche_anciennete_annees) * config_paie.jours_conges_anciennete
                    conges_acquis += Decimal(str(bonus))
            
            # La base est plafonnée au droit annuel configuré. Le bonus
            # d'ancienneté reste ajouté au-delà de cette base.
            plafond_annuel = jours_par_mois * Decimal('12')
            conges_base = min(
                Decimal(str(min(mois_acquis_annee, 12))) * jours_par_mois,
                plafond_annuel,
            )
            bonus_anciennete = max(Decimal('0'), conges_acquis - (
                Decimal(str(min(mois_acquis_annee, 12))) * jours_par_mois))
            conges_acquis = conges_base + bonus_anciennete
            
            # Créer ou mettre à jour le SoldeConge
            solde_conge, created = SoldeConge.objects.get_or_create(
                employe=emp,
                annee=self.periode.annee,
                defaults={
                    'conges_acquis': Decimal('0'),
                    'conges_pris': Decimal('0'),
                }
            )
            
            # Toujours mettre à jour les congés acquis
            # (recalcul à chaque génération de bulletin)
            if not solde_conge.conges_pris:
                solde_conge.conges_pris = Decimal('0')
            solde_conge.conges_acquis = conges_acquis
            solde_conge.conges_restants = (
                conges_acquis
                + (solde_conge.conges_reports or Decimal('0'))
                - (solde_conge.conges_pris or Decimal('0'))
            )
            solde_conge.save()
            
            return solde_conge.conges_acquis
        
        except Exception as e:
            # En cas d'erreur, retourner 0 sans bloquer le bulletin
            print(f"⚠️  Erreur calcul congés ({self.employe}): {str(e)}")
            return Decimal('0')


# ============================================================================
# ANALYSEUR DE CONFORMITÉ DES INDEMNITÉS
# ============================================================================

import logging
logger_conformite = logging.getLogger('paie.conformite')

# Mapping type d'indemnité → mots-clés de détection
_MAPPING_TYPE_INDEMNITE = {
    'transport': ['transport', 'deplacement', 'déplacement'],
    'logement': ['logement', 'hébergement', 'hebergement', 'allocation logement'],
    'cherte_vie': ['cherté', 'cherte', 'vie chère', 'vie chere'],
    'panier': ['panier', 'repas', 'nourriture', 'restauration'],
    'deplacement': ['deplacement', 'déplacement', 'mission'],
    'representation': ['représentation', 'representation'],
}


class AnalyseurConformiteIndemnites:
    """
    Moteur d'analyse de conformité des indemnités forfaitaires.

    Produit des alertes à 3 niveaux :
      🟢 info      — conforme
      🟡 attention  — hors fourchette mais total OK
      🔴 risque     — risque de requalification fiscale

    Fournit aussi une recommandation d'optimisation.
    """

    VERSION_MOTEUR = '1.2.2'

    # Fourchettes par défaut (appliquées si aucune RegleIndemnite n'est définie)
    DEFAULTS = {
        'transport':       {'min': Decimal('5'),  'max': Decimal('8'),  'justification': 'Déplacement domicile-travail'},
        'logement':        {'min': Decimal('10'), 'max': Decimal('15'), 'justification': 'Bail ou attestation de résidence'},
        'cherte_vie':      {'min': Decimal('0'),  'max': Decimal('10'), 'justification': 'Coût de la vie local'},
        'panier':          {'min': Decimal('0'),  'max': Decimal('5'),  'justification': 'Frais de repas sur site'},
        'deplacement':     {'min': Decimal('0'),  'max': Decimal('8'),  'justification': 'Ordre de mission'},
        'representation':  {'min': Decimal('0'),  'max': Decimal('5'),  'justification': 'Frais de représentation'},
    }

    # Fourchettes adaptées par catégorie (plafonds différenciés)
    AJUSTEMENTS_CATEGORIE = {
        'cadre':          {'logement': Decimal('15'), 'transport': Decimal('8'),  'representation': Decimal('5')},
        'agent_maitrise': {'logement': Decimal('12'), 'transport': Decimal('7'),  'representation': Decimal('3')},
        'employe':        {'logement': Decimal('10'), 'transport': Decimal('6'),  'representation': Decimal('2')},
        'ouvrier':        {'logement': Decimal('8'),  'transport': Decimal('5'),  'representation': Decimal('1')},
    }

    PLAFOND_TOTAL_PCT = Decimal('25')  # CGI Guinée

    # Stratégies d'optimisation
    # Les plafonds recommandés varient selon le salaire brut
    # pour rester crédible vis-à-vis de l'administration fiscale.
    STRATEGIES = {
        'maximale': {
            'label': 'Optimisation maximale',
            'icone': '🟢',
            'description': 'Plafond CGI utilisé intégralement (25%). Légal mais peut attirer l\'attention.',
            'pct': Decimal('25'),
        },
        'recommandee': {
            'label': 'Optimisation recommandée',
            'icone': '🟡',
            'description': 'Structure crédible et défendable devant un inspecteur.',
            'pct': Decimal('20'),
        },
        'prudente': {
            'label': 'Optimisation prudente',
            'icone': '🟦',
            'description': 'Très conservateur. Aucun risque de contrôle.',
            'pct': Decimal('15'),
        },
    }

    # Seuils salaire brut pour ajuster la stratégie recommandée
    SEUILS_SALAIRE = [
        # (seuil_brut_gnf, plafond_recommandé_pct, raison)
        (Decimal('10000000'), Decimal('25'), 'Cadre supérieur / direction — 25% justifiable'),
        (Decimal('6000000'),  Decimal('22'), 'Cadre intermédiaire — 22% crédible'),
        (Decimal('3000000'),  Decimal('20'), 'Salaire moyen — 20% recommandé'),
        (Decimal('0'),        Decimal('15'), 'Petit salaire — 15% prudent'),
    ]

    def __init__(self, employe, montants, indemnites_detectees):
        """
        :param employe: instance Employe
        :param montants: dict des montants calculés par MoteurCalculPaie
        :param indemnites_detectees: list de (rubrique, montant, raison)
        """
        self.employe = employe
        self.montants = montants
        self.indemnites_detectees = indemnites_detectees
        self._regles_cache = None

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def analyser(self):
        """
        Analyse complète des indemnités.

        Returns:
            dict {
                'alertes': [...],         # chaque alerte a un champ 'action'
                'recommandation': {...},
                'resume': {'niveau_global', 'score', ...},
                'conformite_meta': {...}  # signature d'audit
            }
        """
        from datetime import datetime

        salaire_base = self._obtenir_salaire_base()
        total_gains = self.montants.get('total_gains', Decimal('0'))

        if salaire_base <= 0 or not self.indemnites_detectees:
            return {
                'alertes': [], 'recommandation': None,
                'resume': {'niveau_global': 'info', 'score': 100},
                'conformite_meta': self._meta_signature(datetime.now()),
            }

        alertes = []
        penalites_score = Decimal('0')  # déductions sur le score /100
        categorie = self._categorie_employe()

        # Déterminer la stratégie recommandée selon salaire + catégorie
        strategie = self._determiner_strategie(total_gains, categorie)
        plafond_recommande = strategie['plafond_recommande']

        # 1. Analyse par type d'indemnité
        for rubrique, montant, raison in self.indemnites_detectees:
            type_ind = self._detecter_type(rubrique)
            regle = self._obtenir_regle(type_ind, categorie)

            ratio = (montant / salaire_base * Decimal('100')).quantize(Decimal('0.01'))

            if ratio > regle['max']:
                depassement_pct = ratio - regle['max']
                montant_cible = (salaire_base * regle['max'] / Decimal('100')).quantize(Decimal('1'))
                alertes.append({
                    'niveau': 'attention',
                    'rubrique': rubrique.libelle_rubrique,
                    'type': type_ind,
                    'ratio_pct': ratio,
                    'seuil_max_pct': regle['max'],
                    'message': (
                        f"{rubrique.libelle_rubrique} = {ratio}% du base "
                        f"(fourchette recommandée : {regle['min']}–{regle['max']}%)"
                    ),
                    'action': (
                        f"Réduire à {montant_cible:,.0f} GNF ({regle['max']}%) "
                        f"ou fournir un justificatif : {regle['justification']}"
                    ),
                })
                # -5 pts par % au-dessus du seuil max
                penalites_score += min(depassement_pct * Decimal('5'), Decimal('25'))

            elif ratio < regle['min'] and montant > 0:
                alertes.append({
                    'niveau': 'info',
                    'rubrique': rubrique.libelle_rubrique,
                    'type': type_ind,
                    'ratio_pct': ratio,
                    'message': (
                        f"{rubrique.libelle_rubrique} = {ratio}% du base "
                        f"(en-dessous de la fourchette {regle['min']}–{regle['max']}%)"
                    ),
                    'action': (
                        f"Montant conforme mais inférieur à la norme. "
                        f"Possibilité d'augmenter jusqu'à {regle['min']}% sans risque."
                    ),
                })
            else:
                # Conforme — pas de pénalité
                pass

        # 2. Vérification plafond global 25%
        total_indemnites = sum(m for _, m, _ in self.indemnites_detectees)
        ratio_global = (total_indemnites / total_gains * Decimal('100')).quantize(Decimal('0.01')) if total_gains > 0 else Decimal('0')

        if ratio_global > self.PLAFOND_TOTAL_PCT:
            excedent = total_indemnites - (total_gains * self.PLAFOND_TOTAL_PCT / Decimal('100'))
            alertes.append({
                'niveau': 'risque',
                'rubrique': 'TOTAL INDEMNITÉS',
                'type': 'plafond_global',
                'ratio_pct': ratio_global,
                'seuil_max_pct': self.PLAFOND_TOTAL_PCT,
                'message': (
                    f"Total indemnités = {ratio_global}% du brut "
                    f"(plafond CGI : {self.PLAFOND_TOTAL_PCT}%)"
                ),
                'action': (
                    f"Réduire les indemnités de {excedent:,.0f} GNF pour rester "
                    f"sous le plafond légal. Sinon l'excédent sera réintégré "
                    f"dans la base imposable RTS."
                ),
            })
            penalites_score += Decimal('30')

        elif ratio_global > plafond_recommande and ratio_global <= self.PLAFOND_TOTAL_PCT:
            # Légal mais au-dessus du plafond recommandé pour ce profil
            alertes.append({
                'niveau': 'attention',
                'rubrique': 'TOTAL INDEMNITÉS',
                'type': 'credibilite',
                'ratio_pct': ratio_global,
                'seuil_max_pct': plafond_recommande,
                'message': (
                    f"Total indemnités = {ratio_global}% du brut — légal (≤25%) "
                    f"mais au-dessus du seuil recommandé de {plafond_recommande}% "
                    f"pour ce profil ({strategie['raison']})"
                ),
                'action': (
                    f"Réduire à {plafond_recommande}% pour une structure plus crédible. "
                    f"Un ratio systématique à 25% peut déclencher un contrôle fiscal."
                ),
            })
            penalites_score += Decimal('8')

        elif ratio_global > self.PLAFOND_TOTAL_PCT - Decimal('3'):
            marge = self.PLAFOND_TOTAL_PCT - ratio_global
            alertes.append({
                'niveau': 'attention',
                'rubrique': 'TOTAL INDEMNITÉS',
                'type': 'plafond_global',
                'ratio_pct': ratio_global,
                'message': (
                    f"Total indemnités = {ratio_global}% du brut "
                    f"(marge restante : {marge}% avant plafond CGI)"
                ),
                'action': (
                    f"Surveiller — marge de seulement {marge}% avant le plafond légal de 25%. "
                    f"Éviter toute nouvelle indemnité sans justificatif."
                ),
            })
            penalites_score += Decimal('10')

        # 3. Niveau global + score
        niveaux = [a['niveau'] for a in alertes]
        if 'risque' in niveaux:
            niveau_global = 'risque'
        elif 'attention' in niveaux:
            niveau_global = 'attention'
        else:
            niveau_global = 'info'

        score = max(0, int(Decimal('100') - penalites_score))

        # 4. Évaluation du risque fiscal global
        risque_fiscal = self._evaluer_risque_fiscal(
            ratio_global, plafond_recommande, categorie, alertes, score
        )

        # 5. Recommandation automatique (adaptée à la catégorie)
        recommandation = self._generer_recommandation(salaire_base, categorie)

        # 6. Générer les 3 scénarios d'optimisation
        scenarios = self._generer_scenarios(salaire_base, total_gains, categorie)

        return {
            'alertes': alertes,
            'recommandation': recommandation,
            'scenarios': scenarios,
            'resume': {
                'niveau_global': niveau_global,
                'score': score,
                'risque_fiscal': risque_fiscal,
                'total_indemnites': total_indemnites,
                'ratio_global_pct': ratio_global,
                'salaire_base': salaire_base,
                'categorie_employe': categorie,
                'strategie_recommandee': strategie['nom'],
                'plafond_recommande_pct': plafond_recommande,
            },
            'conformite_meta': self._meta_signature(datetime.now()),
        }

    # ------------------------------------------------------------------
    # Méthodes internes
    # ------------------------------------------------------------------

    def _obtenir_salaire_base(self):
        """Récupère le salaire de base depuis les éléments."""
        base = ElementSalaire.objects.filter(
            employe=self.employe,
            actif=True,
            rubrique__type_rubrique='gain',
        ).filter(
            salaire_base_rubrique_q()
        ).select_related('rubrique').annotate(
            _base_priority=salaire_base_priority_annotation()
        ).order_by(
            '_base_priority',
            'rubrique__ordre_calcul',
            'rubrique__ordre_affichage',
            '-date_debut',
            'id',
        ).first()
        if base and base.montant:
            return base.montant
        return getattr(self.employe, 'salaire_base', None) or Decimal('0')

    def _categorie_employe(self):
        """Retourne la catégorie professionnelle de l'employé."""
        if hasattr(self.employe, 'poste') and self.employe.poste:
            return self.employe.poste.categorie_professionnelle or 'tous'
        return 'tous'

    def _obtenir_regles(self):
        """Charge les règles de l'entreprise (avec cache)."""
        if self._regles_cache is None:
            from .models import RegleIndemnite
            self._regles_cache = list(
                RegleIndemnite.objects.filter(
                    entreprise=self.employe.entreprise,
                    actif=True
                )
            )
        return self._regles_cache

    def _obtenir_regle(self, type_indemnite, categorie):
        """
        Cherche la règle la plus spécifique :
        1. type + catégorie exacte
        2. type + 'tous'
        3. défaut hardcodé
        """
        regles = self._obtenir_regles()

        # Recherche spécifique
        for r in regles:
            if r.type_indemnite == type_indemnite and r.categorie_employe == categorie:
                return {
                    'min': r.seuil_min_pct,
                    'max': r.seuil_max_pct,
                    'justification': r.justification_requise,
                }

        # Recherche générique
        for r in regles:
            if r.type_indemnite == type_indemnite and r.categorie_employe == 'tous':
                return {
                    'min': r.seuil_min_pct,
                    'max': r.seuil_max_pct,
                    'justification': r.justification_requise,
                }

        # Défaut
        return self.DEFAULTS.get(type_indemnite, {
            'min': Decimal('0'),
            'max': Decimal('10'),
            'justification': 'Justificatif selon nature de l\'indemnité',
        })

    def _detecter_type(self, rubrique):
        """Détecte le type d'indemnité à partir du code/libellé."""
        code = (rubrique.code_rubrique or '').upper()
        libelle = (rubrique.libelle_rubrique or '').lower()

        for type_ind, mots in _MAPPING_TYPE_INDEMNITE.items():
            for mot in mots:
                if mot.upper() in code or mot in libelle:
                    return type_ind
        return 'autre'

    def _taux_optimal_pour_categorie(self, type_ind, categorie, regle):
        """
        Calcule le taux optimal en tenant compte de la catégorie.

        Cadre → on vise le haut de la fourchette (max exonération).
        Employé/ouvrier → on reste au 1er tiers (moins de suspicion fiscale).
        """
        ajustements = self.AJUSTEMENTS_CATEGORIE.get(categorie, {})
        plafond_cat = ajustements.get(type_ind)

        if plafond_cat is not None:
            # Utiliser le min entre le plafond catégorie et le seuil max de la règle
            max_effectif = min(plafond_cat, regle['max'])
        else:
            max_effectif = regle['max']

        # Cadres → viser 75% de la fourchette (optimisation légitime)
        # Employés/ouvriers → viser 40% de la fourchette (prudence)
        if categorie == 'cadre':
            position = Decimal('0.75')
        elif categorie in ('employe', 'ouvrier'):
            position = Decimal('0.40')
        else:
            position = Decimal('0.50')  # agent_maitrise ou 'tous'

        taux = regle['min'] + (max_effectif - regle['min']) * position
        return taux.quantize(Decimal('0.01'))

    def _evaluer_risque_fiscal(self, ratio_global, plafond_recommande, categorie, alertes, score):
        """
        Évalue le niveau de risque fiscal global.

        Combine 3 facteurs :
        1. Écart entre le ratio réel et le seuil recommandé
        2. Cohérence de la structure (nb d'alertes attention/risque)
        3. Catégorie du salarié (cadre = plus de marge)

        Returns:
            dict {'niveau': 'faible'|'modere'|'eleve', 'label': ..., 'explication': ...}
        """
        nb_alertes_risque = sum(1 for a in alertes if a['niveau'] == 'risque')
        nb_alertes_attention = sum(1 for a in alertes if a['niveau'] == 'attention')

        # Facteur 1 : position du ratio
        if ratio_global > self.PLAFOND_TOTAL_PCT:
            facteur_ratio = 'eleve'
        elif ratio_global > plafond_recommande:
            facteur_ratio = 'modere'
        else:
            facteur_ratio = 'faible'

        # Facteur 2 : concentration des alertes
        if nb_alertes_risque >= 1:
            facteur_alertes = 'eleve'
        elif nb_alertes_attention >= 2:
            facteur_alertes = 'modere'
        else:
            facteur_alertes = 'faible'

        # Facteur 3 : catégorie (les cadres ont plus de légitimité pour les indemnités)
        bonus_categorie = categorie in ('cadre', 'agent_maitrise')

        # Synthèse
        niveaux = [facteur_ratio, facteur_alertes]
        if 'eleve' in niveaux:
            niveau = 'eleve'
        elif 'modere' in niveaux:
            # Un cadre avec modéré descend à faible si score > 80
            if bonus_categorie and score >= 80:
                niveau = 'faible'
            else:
                niveau = 'modere'
        else:
            niveau = 'faible'

        # Labels, explications, phrase de défense et décision
        labels = {
            'faible': {
                'label': '🟢 Risque faible',
                'explication': (
                    'Structure salariale conforme et crédible. '
                    'Aucun élément susceptible de déclencher un contrôle.'
                ),
                'defense': (
                    'La structure de rémunération est conforme aux seuils usuels '
                    'du Code Général des Impôts et cohérente avec le niveau '
                    'de responsabilité et la catégorie professionnelle du salarié.'
                ),
                'decision': 'Valider',
                'decision_icone': '✅',
                'decision_classe': 'success',
            },
            'modere': {
                'label': '🟡 Risque modéré',
                'explication': (
                    'Structure légale mais optimisée au-delà du seuil recommandé. '
                    'Un inspecteur pourrait demander des justificatifs.'
                ),
                'defense': (
                    'La structure respecte le plafond légal de 25% du CGI mais '
                    'dépasse les pratiques usuelles pour ce profil salarial. '
                    'Une justification documentaire des indemnités forfaitaires '
                    'est recommandée (baux, ordres de mission, attestations).'
                ),
                'decision': 'Ajuster recommandé',
                'decision_icone': '⚠️',
                'decision_classe': 'warning',
            },
            'eleve': {
                'label': '🔴 Risque élevé',
                'explication': (
                    'Structure à risque de requalification fiscale. '
                    'Action corrective recommandée avant tout contrôle.'
                ),
                'defense': (
                    'La structure dépasse les limites fiscales du CGI et expose '
                    'l\'entreprise à un risque élevé de requalification des '
                    'indemnités en salaire imposable, avec redressement '
                    'et pénalités de retard.'
                ),
                'decision': 'Corriger immédiatement',
                'decision_icone': '🚨',
                'decision_classe': 'danger',
            },
        }

        result = labels[niveau].copy()
        result['niveau'] = niveau
        return result

    def _meta_signature(self, now):
        """Signature d'audit pour traçabilité rétroactive."""
        return {
            'version_moteur': self.VERSION_MOTEUR,
            'version_regles': self._version_regles(),
            'date_analyse': now.strftime('%Y-%m-%dT%H:%M:%S'),
            'moteur': 'AnalyseurConformiteIndemnites',
        }

    def _version_regles(self):
        """Hash simplifié de la configuration active."""
        regles = self._obtenir_regles()
        if not regles:
            return 'defaults'
        ids = sorted(r.pk for r in regles)
        return f"db-{len(ids)}-{ids[0]}-{ids[-1]}"

    def _determiner_strategie(self, salaire_brut, categorie):
        """
        Détermine le plafond recommandé selon le salaire brut + catégorie.

        Un cadre à 10M+ peut justifier 25%.
        Un employé à 3M ne devrait pas dépasser 20%.
        """
        # Les cadres bénéficient d'un bonus de +3% sur le plafond recommandé
        bonus_cadre = Decimal('3') if categorie == 'cadre' else Decimal('0')

        for seuil, pct, raison in self.SEUILS_SALAIRE:
            if salaire_brut >= seuil:
                plafond = min(pct + bonus_cadre, self.PLAFOND_TOTAL_PCT)
                return {
                    'nom': self._nom_strategie(plafond),
                    'plafond_recommande': plafond,
                    'raison': raison,
                }

        return {
            'nom': 'prudente',
            'plafond_recommande': Decimal('15'),
            'raison': 'Profil non identifié — prudence par défaut',
        }

    def _nom_strategie(self, plafond):
        """Détermine le nom de la stratégie à partir du plafond."""
        if plafond >= Decimal('25'):
            return 'maximale'
        elif plafond >= Decimal('20'):
            return 'recommandee'
        return 'prudente'

    def _generer_scenarios(self, salaire_base, total_gains, categorie):
        """
        Génère 3 scénarios d'optimisation pour que le client choisisse.

        Chaque scénario montre la répartition recommandée des indemnités
        sous le plafond correspondant.
        """
        scenarios = {}
        strategie_reco = self._determiner_strategie(total_gains, categorie)

        for cle, strat in self.STRATEGIES.items():
            plafond_pct = strat['pct']
            # Budget total indemnités pour ce scénario
            budget = (total_gains * plafond_pct / Decimal('100')).quantize(Decimal('1'))

            # Répartir le budget selon les types d'indemnité détectés
            repartition = {}
            nb_types = max(1, len(self.indemnites_detectees))

            for rubrique, montant_actuel, _ in self.indemnites_detectees:
                type_ind = self._detecter_type(rubrique)
                regle = self._obtenir_regle(type_ind, categorie)

                # Proportionner le budget selon les fourchettes
                taux = self._taux_optimal_pour_categorie(type_ind, categorie, regle)
                montant_scenario = (salaire_base * taux / Decimal('100')).quantize(Decimal('1'))

                repartition[type_ind] = {
                    'rubrique': rubrique.libelle_rubrique,
                    'montant_actuel': montant_actuel,
                    'montant_scenario': montant_scenario,
                    'taux_pct': taux,
                }

            # Vérifier que le total du scénario ne dépasse pas le budget
            total_scenario = sum(r['montant_scenario'] for r in repartition.values())
            if total_scenario > budget and total_scenario > 0:
                facteur = budget / total_scenario
                for key in repartition:
                    repartition[key]['montant_scenario'] = (
                        repartition[key]['montant_scenario'] * facteur
                    ).quantize(Decimal('1'))
                total_scenario = budget

            scenarios[cle] = {
                'label': strat['label'],
                'icone': strat['icone'],
                'description': strat['description'],
                'plafond_pct': plafond_pct,
                'budget_total': budget,
                'total_scenario': total_scenario,
                'repartition': repartition,
                'est_recommande': (cle == strategie_reco['nom']),
            }

        return scenarios

    def _generer_recommandation(self, salaire_base, categorie):
        """
        Génère une structure recommandée conforme et optimisée,
        adaptée à la catégorie professionnelle de l'employé.
        """
        recommandations = {}
        total_recommande = Decimal('0')

        for rubrique, montant, _ in self.indemnites_detectees:
            type_ind = self._detecter_type(rubrique)
            regle = self._obtenir_regle(type_ind, categorie)

            taux_optimal = self._taux_optimal_pour_categorie(type_ind, categorie, regle)
            montant_optimal = (salaire_base * taux_optimal / Decimal('100')).quantize(Decimal('1'))

            recommandations[type_ind] = {
                'rubrique': rubrique.libelle_rubrique,
                'montant_actuel': montant,
                'montant_recommande': montant_optimal,
                'taux_recommande_pct': taux_optimal,
                'fourchette': f"{regle['min']}–{regle['max']}%",
                'categorie_appliquee': categorie,
            }
            total_recommande += montant_optimal

        # Vérifier que le total recommandé ne dépasse pas 25%
        brut = self.montants.get('total_gains', Decimal('0'))
        if brut > 0:
            ratio_recommande = total_recommande / brut * Decimal('100')
            if ratio_recommande > self.PLAFOND_TOTAL_PCT:
                facteur = self.PLAFOND_TOTAL_PCT / ratio_recommande
                for key in recommandations:
                    recommandations[key]['montant_recommande'] = (
                        recommandations[key]['montant_recommande'] * facteur
                    ).quantize(Decimal('1'))

        return recommandations


# Import manquant
from django.db import models
