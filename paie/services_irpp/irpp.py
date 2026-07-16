"""
Service de calcul IRPP (Impôt sur le Revenu des Personnes Physiques) - Guinée
Barème progressif avec déductions fiscales
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from django.db.models import Q
from paie.models import TrancheRTS
from core.models import BaremeIRPP, DeductionFiscale


class IRPPService:
    """Service de calcul de l'IRPP selon le barème progressif guinéen"""

    # Bornes CNSS (GNF) — identiques au bulletin réel (paie/services.py)
    PLAFOND_CNSS = Decimal('2500000')
    PLANCHER_CNSS = Decimal('550000')

    def __init__(self, annee: int, entreprise=None):
        self.annee = annee
        self.entreprise = entreprise
        self.tranches = self._charger_tranches()
        self.deductions = self._charger_deductions()
    
    def _charger_tranches(self):
        """Charger les tranches IRPP pour l'année"""
        # Essayer d'abord le modèle TrancheRTS (paie)
        tranches = TrancheRTS.objects.filter(
            annee_validite=self.annee,
            actif=True
        ).order_by('numero_tranche')
        
        if tranches.exists():
            return list(tranches)
        
        # Sinon utiliser BaremeIRPP (core)
        query = Q(annee=self.annee, actif=True)
        if self.entreprise:
            query &= Q(entreprise=self.entreprise) | Q(entreprise__isnull=True)
        else:
            query &= Q(entreprise__isnull=True)
        
        baremes = BaremeIRPP.objects.filter(query).order_by('tranche_numero')
        return list(baremes)
    
    def _charger_deductions(self):
        """Charger les déductions fiscales pour l'année"""
        query = Q(annee=self.annee, actif=True)
        if self.entreprise:
            query &= Q(entreprise=self.entreprise) | Q(entreprise__isnull=True)
        else:
            query &= Q(entreprise__isnull=True)
        
        return {d.type_deduction: d for d in DeductionFiscale.objects.filter(query)}
    
    def calculer_irpp(self, base_imposable: Decimal, situation_familiale: dict = None) -> dict:
        """
        Calculer l'IRPP sur une base imposable
        
        Args:
            base_imposable: Revenu imposable mensuel en GNF
            situation_familiale: Dict avec nombre_enfants, conjoint_charge, etc.
        
        Returns:
            Dict avec irpp_brut, deductions, irpp_net, details_tranches
        """
        if base_imposable <= 0:
            return {
                'irpp_brut': Decimal('0'),
                'deductions': Decimal('0'),
                'irpp_net': Decimal('0'),
                'base_imposable': base_imposable,
                'details_tranches': []
            }
        
        # Calculer les déductions familiales
        deductions_familiales = self._calculer_deductions_familiales(situation_familiale or {})
        
        # Base après déductions
        base_apres_deductions = max(base_imposable - deductions_familiales, Decimal('0'))
        
        # Calculer l'IRPP progressif
        irpp_brut, details = self._calculer_progressif(base_apres_deductions)
        
        return {
            'irpp_brut': irpp_brut,
            'deductions': deductions_familiales,
            'irpp_net': irpp_brut,  # Pour l'instant pas de crédits d'impôt
            'base_imposable': base_imposable,
            'base_apres_deductions': base_apres_deductions,
            'details_tranches': details
        }
    
    def _calculer_deductions_familiales(self, situation: dict) -> Decimal:
        """Calculer les déductions pour charges de famille"""
        total_deductions = Decimal('0')
        
        # Déduction conjoint
        if situation.get('conjoint_charge', False) and 'conjoint' in self.deductions:
            total_deductions += self.deductions['conjoint'].montant_deduction
        
        # Déduction enfants
        nb_enfants = situation.get('nombre_enfants', 0)
        if nb_enfants > 0 and 'enfant' in self.deductions:
            ded_enfant = self.deductions['enfant']
            nb_max = ded_enfant.nombre_max or 10
            nb_applique = min(nb_enfants, nb_max)
            total_deductions += ded_enfant.montant_deduction * nb_applique
        
        # Déduction ascendants
        nb_ascendants = situation.get('nombre_ascendants', 0)
        if nb_ascendants > 0 and 'ascendant' in self.deductions:
            ded_asc = self.deductions['ascendant']
            nb_max = ded_asc.nombre_max or 4
            nb_applique = min(nb_ascendants, nb_max)
            total_deductions += ded_asc.montant_deduction * nb_applique
        
        return total_deductions
    
    def _calculer_progressif(self, base: Decimal) -> tuple:
        """Calculer l'impôt selon le barème progressif.

        Les bornes sont normalisées pour éliminer les gaps de 1 GNF
        (ex: T1 finit à 1 000 000 et T2 commence à 1 000 001) afin qu'aucun
        franc n'échappe au barème, et chaque tranche est arrondie ROUND_HALF_UP
        — identique à paie/services.py::_calculer_irg_progressif.
        """
        if base <= 0:
            return Decimal('0'), []

        # Construire des seuils contigus (borne_inf, borne_sup, taux, numero)
        seuils = []
        prev_sup = None
        for tranche in self.tranches:
            if hasattr(tranche, 'borne_inferieure'):  # TrancheRTS
                borne_inf, borne_sup, taux = tranche.borne_inferieure, tranche.borne_superieure, tranche.taux_irg
            else:  # BaremeIRPP
                borne_inf, borne_sup, taux = tranche.revenu_min, tranche.revenu_max, tranche.taux
            numero = getattr(tranche, 'numero_tranche', getattr(tranche, 'tranche_numero', 0))
            borne_inf = Decimal(str(borne_inf))
            # Aligner borne_inf sur la borne_sup précédente si gap de 1-2 GNF
            if prev_sup is not None and prev_sup < borne_inf <= prev_sup + 2:
                borne_inf = prev_sup
            borne_sup = Decimal(str(borne_sup)) if borne_sup is not None else None
            seuils.append((borne_inf, borne_sup, Decimal(str(taux)), numero))
            prev_sup = borne_sup

        irpp_total = Decimal('0')
        details = []
        for borne_inf, borne_sup, taux, numero in seuils:
            if base <= borne_inf:
                break
            if borne_sup is not None:
                montant_dans_tranche = min(base, borne_sup) - borne_inf
            else:
                montant_dans_tranche = base - borne_inf
            if montant_dans_tranche <= 0:
                continue

            irpp_tranche = (montant_dans_tranche * taux / Decimal('100')).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
            irpp_total += irpp_tranche

            details.append({
                'tranche': numero,
                'borne_inf': borne_inf,
                'borne_sup': borne_sup,
                'taux': taux,
                'montant_imposable': montant_dans_tranche,
                'irpp': irpp_tranche,
            })

        return irpp_total, details
    
    def _arrondir(self, montant: Decimal) -> Decimal:
        """Arrondir au franc près"""
        return Decimal(str(round(montant, 0)))
    
    def simuler_irpp(self, salaire_brut: Decimal, taux_cnss: Decimal = Decimal('5')) -> dict:
        """
        Simuler l'IRPP à partir d'un salaire brut
        
        Args:
            salaire_brut: Salaire brut mensuel
            taux_cnss: Taux CNSS employé (default 5%)
        
        Returns:
            Dict avec tous les détails du calcul
        """
        # Calculer CNSS — base plafonnée/planchée comme le bulletin réel.
        # En dessous de 10% du plancher (salaire quasi nul), pas de cotisation.
        seuil_minimum = self.PLANCHER_CNSS * Decimal('0.10')
        if salaire_brut < seuil_minimum:
            base_cnss = Decimal('0')
        else:
            base_cnss = max(min(salaire_brut, self.PLAFOND_CNSS), self.PLANCHER_CNSS)
        cnss = base_cnss * taux_cnss / Decimal('100')

        # Base imposable = Brut - CNSS
        base_imposable = salaire_brut - cnss
        
        # Calculer IRPP
        resultat = self.calculer_irpp(base_imposable)
        
        # Ajouter infos supplémentaires
        resultat['salaire_brut'] = salaire_brut
        resultat['cnss'] = cnss
        resultat['net_imposable'] = base_imposable
        resultat['salaire_net'] = salaire_brut - cnss - resultat['irpp_net']
        
        return resultat
    
    @staticmethod
    def get_bareme_actuel(annee: int = None) -> list:
        """Récupérer le barème IRPP actuel"""
        if annee is None:
            annee = date.today().year
        
        tranches = TrancheRTS.objects.filter(
            annee_validite=annee,
            actif=True
        ).order_by('numero_tranche')
        
        return [
            {
                'numero': t.numero_tranche,
                'borne_inf': t.borne_inferieure,
                'borne_sup': t.borne_superieure,
                'taux': t.taux_irg
            }
            for t in tranches
        ]
