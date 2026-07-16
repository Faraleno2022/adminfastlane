"""
Services pour la gestion des congés payés selon le Code du Travail guinéen.

Règles légales:
- Acquisition: 2,5 jours ouvrables par mois de travail effectif
- Majoration ancienneté:
  - +1 jour après 5 ans
  - +2 jours après 10 ans
  - +3 jours après 15 ans
  - +4 jours après 20 ans
- Indemnité de congés: salaire moyen des 12 derniers mois
- Provision comptable: 1/12 de la masse salariale mensuelle
"""
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Avg

from .models import DroitConge, Conge, SoldeConge, ReglementationTemps
from employes.models import Employe
from paie.models import BulletinPaie


class GestionCongesService:
    """Service de gestion des congés payés"""
    
    # Constantes légales (Code du Travail guinéen, Art. 222 - Loi L/2014/072/CNT)
    JOURS_CONGES_PAR_MOIS = Decimal('2.5')  # 2,5 jours ouvrables par mois (minimum légal)
    JOURS_CONGES_ANNUELS = Decimal('30')    # 30 jours ouvrables (2,5 x 12)
    JOURS_CONGES_MINEURS_PAR_MOIS = Decimal('2.0')  # 2 jours/mois pour moins de 18 ans
    JOURS_CONGES_MINEURS_ANNUELS = Decimal('24')    # 24 jours/an pour moins de 18 ans
    
    # Majorations ancienneté (+2 jours par tranche de 5 ans - Code du Travail)
    MAJORATIONS_ANCIENNETE = {
        5: 2,   # +2 jours après 5 ans
        10: 4,  # +4 jours après 10 ans
        15: 6,  # +6 jours après 15 ans
        20: 8,  # +8 jours après 20 ans
        25: 10, # +10 jours après 25 ans
    }
    
    def __init__(self, employe):
        self.employe = employe
        self.entreprise = employe.entreprise
    
    def calculer_anciennete_annees(self, date_reference=None):
        """Calcule l'ancienneté en années complètes"""
        if not self.employe.date_embauche:
            return 0
        
        date_ref = date_reference or date.today()
        delta = relativedelta(date_ref, self.employe.date_embauche)
        return delta.years
    
    def calculer_majoration_anciennete(self, date_reference=None):
        """Calcule les jours de majoration selon l'ancienneté"""
        anciennete = self.calculer_anciennete_annees(date_reference)
        
        majoration = 0
        for seuil, jours in sorted(self.MAJORATIONS_ANCIENNETE.items(), reverse=True):
            if anciennete >= seuil:
                majoration = jours
                break
        
        return majoration
    
    def calculer_jours_acquis_mois(self, annee, mois):
        """
        Calcule les jours de congés acquis pour un mois donné.
        
        Conditions d'acquisition:
        - Présence effective d'au moins 24 jours ouvrables dans le mois
        - Ou équivalent en cas de maladie, maternité, accident du travail
        """
        # Vérifier si l'employé était présent ce mois
        date_debut_mois = date(annee, mois, 1)
        if mois == 12:
            date_fin_mois = date(annee + 1, 1, 1) - timedelta(days=1)
        else:
            date_fin_mois = date(annee, mois + 1, 1) - timedelta(days=1)
        
        # Vérifier si l'employé était embauché
        if self.employe.date_embauche and self.employe.date_embauche > date_fin_mois:
            return Decimal('0')
        
        # Vérifier si l'employé a quitté l'entreprise
        if self.employe.date_fin_contrat and self.employe.date_fin_contrat < date_debut_mois:
            return Decimal('0')
        
        # Par défaut, acquisition complète si employé actif
        return self.JOURS_CONGES_PAR_MOIS
    
    def calculer_droits_annuels(self, annee):
        """
        Calcule les droits aux congés pour une année complète.
        
        Returns:
            dict: Détail des droits (base, ancienneté, reports, total)
        """
        # Jours acquis de base (2,5 x 12 = 30 jours)
        jours_base = Decimal('0')
        
        for mois in range(1, 13):
            jours_base += self.calculer_jours_acquis_mois(annee, mois)
        
        # Majoration ancienneté
        date_fin_annee = date(annee, 12, 31)
        jours_anciennete = Decimal(str(self.calculer_majoration_anciennete(date_fin_annee)))
        
        # Jours reportés de l'année précédente
        jours_reportes = Decimal('0')
        droit_precedent = DroitConge.objects.filter(
            employe=self.employe,
            annee=annee - 1
        ).first()
        
        if droit_precedent and droit_precedent.solde_disponible > 0:
            # Maximum 15 jours de report (règle courante)
            jours_reportes = min(droit_precedent.solde_disponible, Decimal('15'))
        
        # Jours pris cette année
        jours_pris = Conge.objects.filter(
            employe=self.employe,
            annee_reference=annee,
            statut_demande='approuve',
            type_conge='annuel'
        ).aggregate(total=Sum('nombre_jours'))['total'] or Decimal('0')
        
        # Total et solde
        total_acquis = jours_base + jours_anciennete + jours_reportes
        solde = total_acquis - jours_pris
        
        return {
            'annee': annee,
            'jours_base': jours_base,
            'jours_anciennete': jours_anciennete,
            'jours_reportes': jours_reportes,
            'total_acquis': total_acquis,
            'jours_pris': jours_pris,
            'solde_disponible': solde,
            'anciennete_annees': self.calculer_anciennete_annees(date_fin_annee),
        }
    
    def mettre_a_jour_droits(self, annee):
        """Met à jour ou crée les droits aux congés pour une année"""
        droits = self.calculer_droits_annuels(annee)
        
        droit, created = DroitConge.objects.update_or_create(
            employe=self.employe,
            annee=annee,
            defaults={
                'periode_reference_debut': date(annee, 1, 1),
                'periode_reference_fin': date(annee, 12, 31),
                'jours_acquis_base': droits['jours_base'],
                'jours_acquis_anciennete': droits['jours_anciennete'],
                'jours_reportes': droits['jours_reportes'],
                'jours_pris': droits['jours_pris'],
                'solde_disponible': droits['solde_disponible'],
            }
        )
        
        return droit
    
    def calculer_indemnite_conges(self, nombre_jours):
        """
        Calcule l'indemnité de congés payés.
        
        Méthode: Salaire moyen des 12 derniers mois / 30 x nombre de jours
        
        Args:
            nombre_jours: Nombre de jours de congés
            
        Returns:
            Decimal: Montant de l'indemnité
        """
        # Récupérer les 12 derniers bulletins
        bulletins = BulletinPaie.objects.filter(
            employe=self.employe,
            statut_bulletin__in=['valide', 'paye']
        ).order_by('-periode__annee', '-periode__mois')[:12]
        
        if not bulletins:
            return Decimal('0')
        
        # Calculer le salaire moyen
        total_brut = sum(b.salaire_brut for b in bulletins)
        nb_mois = len(bulletins)
        salaire_moyen = total_brut / nb_mois if nb_mois > 0 else Decimal('0')
        
        # Indemnité = salaire moyen / 30 x nombre de jours
        indemnite_journaliere = salaire_moyen / Decimal('30')
        indemnite_totale = indemnite_journaliere * Decimal(str(nombre_jours))
        
        return indemnite_totale.quantize(Decimal('1'))
    
    def calculer_provision_conges(self, annee, mois):
        """
        Calcule la provision comptable pour congés payés.
        
        Méthode: 1/12 de la masse salariale mensuelle (environ 8,33%)
        
        Args:
            annee: Année
            mois: Mois
            
        Returns:
            Decimal: Montant de la provision
        """
        # Récupérer le bulletin du mois
        bulletin = BulletinPaie.objects.filter(
            employe=self.employe,
            periode__annee=annee,
            periode__mois=mois,
            statut_bulletin__in=['valide', 'paye']
        ).first()
        
        if not bulletin:
            return Decimal('0')
        
        # Provision = salaire brut / 12
        provision = bulletin.salaire_brut / Decimal('12')
        
        return provision.quantize(Decimal('1'))


class ProvisionCongesService:
    """Service pour calculer les provisions de congés payés de l'entreprise"""
    
    TAUX_PROVISION = Decimal('8.33')  # 1/12 ≈ 8,33%
    
    def __init__(self, entreprise):
        self.entreprise = entreprise
    
    def calculer_provision_mensuelle(self, annee, mois):
        """
        Calcule la provision de congés payés pour tous les employés.
        
        Returns:
            dict: Détail de la provision
        """
        # Récupérer tous les bulletins du mois
        bulletins = BulletinPaie.objects.filter(
            employe__entreprise=self.entreprise,
            periode__annee=annee,
            periode__mois=mois,
            statut_bulletin__in=['valide', 'paye']
        )
        
        masse_salariale = bulletins.aggregate(total=Sum('salaire_brut'))['total'] or Decimal('0')
        provision = (masse_salariale * self.TAUX_PROVISION / Decimal('100')).quantize(Decimal('1'))
        
        return {
            'annee': annee,
            'mois': mois,
            'masse_salariale': masse_salariale,
            'taux_provision': self.TAUX_PROVISION,
            'provision': provision,
            'nb_employes': bulletins.values('employe').distinct().count(),
        }
    
    def calculer_provision_annuelle(self, annee):
        """Calcule la provision annuelle cumulée"""
        provisions = []
        total_provision = Decimal('0')
        
        for mois in range(1, 13):
            prov = self.calculer_provision_mensuelle(annee, mois)
            provisions.append(prov)
            total_provision += prov['provision']
        
        return {
            'annee': annee,
            'provisions_mensuelles': provisions,
            'total_provision': total_provision,
        }
    
    def generer_etat_droits_conges(self, annee):
        """
        Génère l'état des droits aux congés de tous les employés.
        
        Returns:
            list: Liste des droits par employé
        """
        employes = Employe.objects.filter(
            entreprise=self.entreprise,
            statut_employe='actif'
        )
        
        etats = []
        for employe in employes:
            service = GestionCongesService(employe)
            droits = service.calculer_droits_annuels(annee)
            droits['employe'] = {
                'matricule': employe.matricule,
                'nom': employe.nom,
                'prenoms': employe.prenoms,
                'date_embauche': employe.date_embauche,
            }
            etats.append(droits)
        
        return etats
