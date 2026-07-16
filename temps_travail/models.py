from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from employes.models import Employe
from core.models import Entreprise


class JourFerie(models.Model):
    """Jours fériés"""
    TYPES = (
        ('national', 'National'),
        ('religieux', 'Religieux'),
        ('local', 'Local'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='jours_feries', null=True, blank=True)
    libelle = models.CharField(max_length=100)
    date_jour_ferie = models.DateField()
    annee = models.IntegerField()
    type_ferie = models.CharField(max_length=50, choices=TYPES)
    recurrent = models.BooleanField(default=False)
    jour_recuperation = models.DateField(blank=True, null=True)
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'calendrier_jours_feries'
        verbose_name = 'Jour férié'
        verbose_name_plural = 'Jours fériés'
        ordering = ['date_jour_ferie']
    
    def __str__(self):
        return f"{self.libelle} - {self.date_jour_ferie}"


class Conge(models.Model):
    """Congés des employés - Conformes au Code du Travail guinéen"""
    TYPES = (
        # Congés légaux
        ('annuel', 'Congé annuel (2,5j/mois)'),
        ('anciennete', 'Congé d\'ancienneté'),
        ('maladie', 'Congé maladie'),
        ('maternite', 'Congé maternité (14 semaines)'),
        ('paternite', 'Congé paternité (3 jours)'),
        # Congés exceptionnels (événements familiaux)
        ('mariage', 'Congé mariage (4 jours)'),
        ('naissance', 'Congé naissance (3 jours)'),
        ('deces_conjoint', 'Décès conjoint/enfant (5 jours)'),
        ('deces_parent', 'Décès parent/beau-parent (3 jours)'),
        ('deces_autre', 'Décès autre famille (1 jour)'),
        # Autres congés
        ('formation', 'Congé formation'),
        ('examen', 'Congé pour examen'),
        ('sans_solde', 'Congé sans solde'),
        ('recuperation', 'Récupération'),
    )
    
    STATUTS = (
        ('en_attente', 'En attente'),
        ('approuve', 'Approuvé'),
        ('rejete', 'Rejeté'),
        ('annule', 'Annulé'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='conges')
    type_conge = models.CharField(max_length=50, choices=TYPES)
    date_debut = models.DateField()
    date_fin = models.DateField()
    nombre_jours = models.IntegerField(validators=[MinValueValidator(1)])
    annee_reference = models.IntegerField(blank=True, null=True)
    motif = models.TextField(blank=True, null=True)
    justificatif = models.FileField(upload_to='conges/', blank=True, null=True)
    statut_demande = models.CharField(max_length=20, choices=STATUTS, default='en_attente')
    date_demande = models.DateField(auto_now_add=True)
    approbateur = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, related_name='conges_approuves')
    date_approbation = models.DateField(blank=True, null=True)
    commentaire_approbateur = models.TextField(blank=True, null=True)
    remplacant = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='remplacements')
    
    class Meta:
        db_table = 'conges'
        verbose_name = 'Congé'
        verbose_name_plural = 'Congés'
        ordering = ['-date_debut']
        indexes = [
            models.Index(fields=['employe', 'statut_demande'], name='idx_conge_emp_statut'),
            models.Index(fields=['date_debut', 'date_fin'], name='idx_conge_dates'),
            models.Index(fields=['statut_demande'], name='idx_conge_statut'),
            models.Index(fields=['employe', 'annee_reference'], name='idx_conge_emp_annee'),
        ]
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.get_type_conge_display()} ({self.date_debut})"


class SoldeConge(models.Model):
    """Soldes de congés"""
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='soldes_conges')
    annee = models.IntegerField()
    conges_acquis = models.DecimalField(max_digits=5, decimal_places=2, default=30.00)
    conges_pris = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    conges_restants = models.DecimalField(max_digits=5, decimal_places=2, default=30.00)
    conges_reports = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    date_mise_a_jour = models.DateField(auto_now=True)
    
    class Meta:
        db_table = 'soldes_conges'
        verbose_name = 'Solde de congé'
        verbose_name_plural = 'Soldes de congés'
        unique_together = ['employe', 'annee']
        ordering = ['-annee']
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.annee} ({self.conges_restants} jours)"
    
    def calculer_conges_acquis(self):
        """Calcule les congés acquis selon le Code du Travail guinéen (Art. 222)"""
        # Base: 2,5 jours ouvrables par mois = 30 jours/an (minimum légal)
        conges_base = Decimal('30.00')

        # Bonus d'ancienneté: +2 jours par tranche de 5 ans
        if hasattr(self.employe, 'date_embauche') and self.employe.date_embauche:
            anciennete_annees = (date(self.annee, 12, 31) - self.employe.date_embauche).days // 365
            bonus_anciennete = (anciennete_annees // 5) * 2
            conges_base += Decimal(str(bonus_anciennete))

        # Cas spécial mineurs (< 18 ans) : jamais inférieur à la base adulte
        if hasattr(self.employe, 'date_naissance') and self.employe.date_naissance:
            age_fin_annee = self.annee - self.employe.date_naissance.year
            if age_fin_annee < 18:
                conges_base = max(conges_base, Decimal('30.00'))

        return conges_base
    
    def calculer_conges_proportionnels(self, date_embauche):
        """Calcule les congés proportionnels pour la première année"""
        if date_embauche.year != self.annee:
            return self.calculer_conges_acquis()
        
        # Calcul proportionnel: 2,5 jours par mois travaillé (Art. 222)
        mois_travailles = 12 - date_embauche.month + 1
        if date_embauche.day > 15:  # Si embauché après le 15, mois non complet
            mois_travailles -= 0.5

        conges_proportionnels = Decimal(str(mois_travailles * 2.5))
        return min(conges_proportionnels, self.calculer_conges_acquis())
    
    def mettre_a_jour_solde(self):
        """Met à jour automatiquement le solde de congés"""
        # Recalculer les congés acquis
        if hasattr(self.employe, 'date_embauche'):
            self.conges_acquis = self.calculer_conges_proportionnels(self.employe.date_embauche)
        else:
            self.conges_acquis = self.calculer_conges_acquis()
        
        # Calculer les congés pris dans l'année
        conges_pris_annee = self.employe.conges.filter(
            annee_reference=self.annee,
            statut_demande='approuve'
        ).aggregate(total=models.Sum('nombre_jours'))['total'] or 0
        
        self.conges_pris = Decimal(str(conges_pris_annee))
        self.conges_restants = self.conges_acquis + self.conges_reports - self.conges_pris
        
        self.save()
        return self.conges_restants


class Pointage(models.Model):
    """Pointages quotidiens"""
    STATUTS = (
        ('present', 'Présent'),
        ('present_am', 'Présent AM'),
        ('present_pm', 'Présent PM'),
        ('present_am_pm', 'Présent AM et PM'),
        ('absent', 'Absent'),
        ('retard', 'Retard'),
        ('absence_justifiee', 'Absence justifiée'),
        ('malade', 'Malade'),
        ('p', 'P'),
        ('a', 'A'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='pointages')
    date_pointage = models.DateField()
    heure_entree = models.TimeField(blank=True, null=True)
    heure_sortie = models.TimeField(blank=True, null=True)
    heures_travaillees = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    heures_supplementaires = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, default=0)
    statut_pointage = models.CharField(max_length=20, choices=STATUTS, default='present')
    motif_absence = models.CharField(max_length=50, blank=True, null=True)
    justificatif = models.FileField(upload_to='pointages/', blank=True, null=True)
    valide = models.BooleanField(default=False)
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'pointages'
        verbose_name = 'Pointage'
        verbose_name_plural = 'Pointages'
        unique_together = ['employe', 'date_pointage']
        ordering = ['-date_pointage']
        indexes = [
            models.Index(fields=['date_pointage', 'statut_pointage'], name='idx_pointage_date_statut'),
            models.Index(fields=['employe', 'date_pointage'], name='idx_pointage_emp_date'),
        ]
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.date_pointage}"


class Absence(models.Model):
    """Absences des employés"""
    TYPES = (
        ('maladie', 'Maladie'),
        ('accident_travail', 'Accident de travail'),
        ('absence_injustifiee', 'Absence injustifiée'),
        ('permission', 'Permission'),
        ('permission_exceptionnelle', 'Permission exceptionnelle'),
        ('rendez_vous_medical', 'Rendez-vous médical'),
        ('demarche_administrative', 'Démarche administrative'),
        ('urgence_familiale', 'Urgence familiale'),
    )
    
    IMPACTS = (
        ('paye', 'Payé'),
        ('non_paye', 'Non payé'),
        ('partiellement_paye', 'Partiellement payé'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='absences')
    date_absence = models.DateField()
    type_absence = models.CharField(max_length=50, choices=TYPES)
    duree_jours = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    justifie = models.BooleanField(default=False)
    justificatif = models.FileField(upload_to='absences/', blank=True, null=True)
    impact_paie = models.CharField(max_length=20, choices=IMPACTS, default='paye')
    taux_maintien_salaire = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    
    # Permissions exceptionnelles
    heure_debut = models.TimeField(null=True, blank=True, help_text="Heure de début pour permissions partielles")
    heure_fin = models.TimeField(null=True, blank=True, help_text="Heure de fin pour permissions partielles")
    approuve_par = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='absences_approuvees')
    date_approbation = models.DateTimeField(null=True, blank=True)
    heures_a_recuperer = models.BooleanField(default=False, help_text="Heures à récupérer")
    
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'absences'
        verbose_name = 'Absence'
        verbose_name_plural = 'Absences'
        ordering = ['-date_absence']
        indexes = [
            models.Index(fields=['employe', 'date_absence'], name='idx_absence_emp_date'),
            models.Index(fields=['date_absence'], name='idx_absence_date'),
        ]
    
    def __str__(self):
        return f"{self.employe.nom} {self.employe.prenoms} - {self.get_type_absence_display()} ({self.date_absence})"
    
    @property
    def duree_heures(self):
        """Calcule la durée en heures pour les permissions partielles"""
        if self.heure_debut and self.heure_fin:
            from datetime import datetime, timedelta
            debut = datetime.combine(self.date_absence, self.heure_debut)
            fin = datetime.combine(self.date_absence, self.heure_fin)
            duree = fin - debut
            return duree.total_seconds() / 3600
        return float(self.duree_jours * 8)  # 8h par jour par défaut
    
    def est_permission_exceptionnelle(self):
        """Vérifie si c'est une permission exceptionnelle"""
        return self.type_absence in ['permission_exceptionnelle', 'rendez_vous_medical', 'demarche_administrative', 'urgence_familiale']


class ArretTravail(models.Model):
    """Arrêts de travail (maladie, accident)"""
    TYPES = (
        ('maladie', 'Maladie'),
        ('accident_travail', 'Accident de travail'),
        ('maladie_professionnelle', 'Maladie professionnelle'),
    )
    
    ORGANISMES = (
        ('inam', 'INAM'),
        ('employeur', 'Employeur'),
        ('mixte', 'Mixte'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='arrets_travail')
    type_arret = models.CharField(max_length=50, choices=TYPES)
    date_debut = models.DateField()
    date_fin = models.DateField(blank=True, null=True)
    duree_jours = models.IntegerField(blank=True, null=True)
    medecin_prescripteur = models.CharField(max_length=100, blank=True)
    numero_certificat = models.CharField(max_length=50, blank=True)
    organisme_payeur = models.CharField(max_length=50, choices=ORGANISMES, default='inam')
    taux_indemnisation = models.DecimalField(max_digits=5, decimal_places=2, default=100.00, help_text="% du salaire")
    montant_indemnites = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    prolongation = models.BooleanField(default=False)
    arret_initial = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='prolongations')
    fichier_certificat = models.FileField(upload_to='arrets_travail/', blank=True, null=True)
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'arrets_travail'
        verbose_name = 'Arrêt de travail'
        verbose_name_plural = 'Arrêts de travail'
        ordering = ['-date_debut']
    
    def __str__(self):
        return f"{self.employe.nom} {self.employe.prenoms} - {self.get_type_arret_display()} ({self.date_debut})"


class HoraireTravail(models.Model):
    """Horaires de travail"""
    TYPES = (
        ('normal', 'Normal'),
        ('equipe', 'Équipe'),
        ('nuit', 'Nuit'),
        ('flexible', 'Flexible'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='horaires_travail', null=True, blank=True)
    code_horaire = models.CharField(max_length=20, unique=True)
    libelle_horaire = models.CharField(max_length=100)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    heure_pause_debut = models.TimeField(blank=True, null=True)
    heure_pause_fin = models.TimeField(blank=True, null=True)
    heures_jour = models.DecimalField(max_digits=5, decimal_places=2, default=8.00)
    type_horaire = models.CharField(max_length=20, choices=TYPES, default='normal')
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'horaires_travail'
        verbose_name = 'Horaire de travail'
        verbose_name_plural = 'Horaires de travail'
        ordering = ['code_horaire']
    
    def __str__(self):
        return f"{self.code_horaire} - {self.libelle_horaire} ({self.heure_debut}-{self.heure_fin})"


class AffectationHoraire(models.Model):
    """Affectation des horaires aux employés"""
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='affectations_horaires')
    horaire = models.ForeignKey(HoraireTravail, on_delete=models.CASCADE, related_name='affectations')
    date_debut = models.DateField()
    date_fin = models.DateField(blank=True, null=True)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'affectation_horaires'
        verbose_name = 'Affectation horaire'
        verbose_name_plural = 'Affectations horaires'
        ordering = ['-date_debut']
    
    def __str__(self):
        return f"{self.employe.nom} {self.employe.prenoms} - {self.horaire.libelle_horaire}"


# ============= RÉGLEMENTATION TEMPS DE TRAVAIL (Code du Travail guinéen) =============

class ReglementationTemps(models.Model):
    """Paramètres de réglementation du temps de travail"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='reglementations_temps', null=True, blank=True)
    annee = models.IntegerField()
    
    # Durée légale du travail
    duree_hebdo_legale = models.DecimalField(max_digits=4, decimal_places=2, default=40.00, help_text="Durée hebdomadaire légale (40h en Guinée)")
    duree_journaliere_max = models.DecimalField(max_digits=4, decimal_places=2, default=10.00, help_text="Durée journalière maximale")
    
    # Heures supplémentaires (Code du Travail guinéen Art. 221)
    taux_hs_jour_25 = models.DecimalField(max_digits=5, decimal_places=2, default=130.00, help_text="Taux 4 premières HS/semaine: 130% (majoration 30%)")
    taux_hs_jour_50 = models.DecimalField(max_digits=5, decimal_places=2, default=160.00, help_text="Taux au-delà 4 HS/semaine: 160% (majoration 60%)")
    taux_hs_nuit = models.DecimalField(max_digits=5, decimal_places=2, default=120.00, help_text="Taux HS nuit (20h-6h): 120% (majoration 20%)")
    taux_hs_dimanche = models.DecimalField(max_digits=5, decimal_places=2, default=160.00, help_text="Taux jour férié jour: 160% (majoration 60%)")
    taux_hs_nuit_dimanche = models.DecimalField(max_digits=5, decimal_places=2, default=200.00, help_text="Taux jour férié nuit: 200% (majoration 100%)")
    
    # Travail de nuit
    heure_debut_nuit = models.TimeField(default='20:00', help_text="Début période de nuit (20h - Code du Travail)")
    heure_fin_nuit = models.TimeField(default='06:00', help_text="Fin période de nuit (6h - Code du Travail)")
    majoration_nuit = models.DecimalField(max_digits=5, decimal_places=2, default=20.00, help_text="Majoration travail de nuit: 20% (Art. 221)")
    
    # Repos
    repos_hebdo_jour = models.CharField(max_length=20, default='dimanche', help_text="Jour de repos hebdomadaire")
    duree_repos_hebdo_min = models.IntegerField(default=24, help_text="Durée minimale repos hebdo (heures)")
    
    # Congés (Code du Travail guinéen)
    jours_conges_annuels = models.DecimalField(max_digits=4, decimal_places=2, default=30.00, help_text="Jours de congés annuels (2,5j ouvrables/mois)")
    jours_conges_mineurs = models.DecimalField(max_digits=4, decimal_places=2, default=24.00, help_text="Jours congés moins de 18 ans (2j/mois)")
    jours_conges_anciennete_5ans = models.IntegerField(default=2, help_text="Jours supplémentaires après 5 ans (+2j)")
    jours_conges_anciennete_10ans = models.IntegerField(default=4, help_text="Jours supplémentaires après 10 ans (+2j par tranche de 5 ans)")
    jours_conges_anciennete_15ans = models.IntegerField(default=6, help_text="Jours supplémentaires après 15 ans")
    jours_conges_anciennete_20ans = models.IntegerField(default=8, help_text="Jours supplémentaires après 20 ans")
    jours_conges_anciennete_25ans = models.IntegerField(default=10, help_text="Jours supplémentaires après 25 ans")
    
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'reglementation_temps'
        verbose_name = 'Réglementation temps de travail'
        verbose_name_plural = 'Réglementations temps de travail'
        unique_together = ['entreprise', 'annee']
    
    def __str__(self):
        return f"Réglementation {self.annee}"


class HeureSupplementaire(models.Model):
    """
    Heures supplémentaires selon le Code du Travail guinéen (Art. 221).
    
    Taux de majoration:
    - 4 premières HS/semaine: +30% (130% du taux horaire)
    - Au-delà 4 HS/semaine: +60% (160% du taux horaire)
    - Heures de nuit (20h-6h): +20% (120% du taux horaire)
    - Jour férié (jour): +60% (160% du taux horaire)
    - Jour férié (nuit): +100% (200% du taux horaire)
    """
    TYPES_HS = (
        ('jour_30', '4 premières heures/semaine (+30%)'),
        ('jour_60', 'Au-delà de 4 heures/semaine (+60%)'),
        ('nuit_20', 'Heures de nuit (+20%)'),
        ('ferie_60', 'Jour férié (+60%)'),
        ('ferie_nuit_100', 'Jour férié de nuit (+100%)'),
    )
    
    STATUTS = (
        ('en_attente', 'En attente'),
        ('valide', 'Validé'),
        ('rejete', 'Rejeté'),
        ('paye', 'Payé'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='heures_supplementaires')
    date_hs = models.DateField(help_text="Date des heures supplémentaires")
    type_hs = models.CharField(max_length=20, choices=TYPES_HS, default='jour_30')
    nombre_heures = models.DecimalField(max_digits=5, decimal_places=2, help_text="Nombre d'heures")
    taux_majoration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Taux de majoration en %")
    taux_horaire_base = models.DecimalField(max_digits=15, decimal_places=2, help_text="Taux horaire de base")
    montant_hs = models.DecimalField(max_digits=15, decimal_places=2, help_text="Montant calculé")
    
    motif = models.TextField(blank=True, help_text="Motif des heures supplémentaires")
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_attente')
    
    # Validation
    valideur = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='hs_validees')
    date_validation = models.DateTimeField(null=True, blank=True)
    
    # Paiement
    bulletin = models.ForeignKey('paie.BulletinPaie', on_delete=models.SET_NULL, null=True, blank=True, related_name='heures_sup')
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'heures_supplementaires'
        verbose_name = 'Heure supplémentaire'
        verbose_name_plural = 'Heures supplémentaires'
        ordering = ['-date_hs', 'employe']
    
    def __str__(self):
        return f"{self.employe.matricule} - {self.date_hs} - {self.nombre_heures}h ({self.get_type_hs_display()})"
    
    def calculer_montant(self):
        """Calcule le montant des heures supplémentaires"""
        majoration = 1 + (self.taux_majoration / 100)
        self.montant_hs = (self.taux_horaire_base * self.nombre_heures * majoration).quantize(Decimal('1'))
        return self.montant_hs
    
    @classmethod
    def get_taux_majoration(cls, type_hs):
        """Retourne le taux de majoration selon le type (Code du Travail Art. 221)"""
        taux = {
            'jour_30': Decimal('30'),      # 4 premières HS/semaine
            'jour_60': Decimal('60'),      # Au-delà 4 HS/semaine
            'nuit_20': Decimal('20'),      # Heures de nuit (20h-6h)
            'ferie_60': Decimal('60'),     # Jour férié (jour)
            'ferie_nuit_100': Decimal('100'),  # Jour férié (nuit)
        }
        return taux.get(type_hs, Decimal('30'))


class DroitConge(models.Model):
    """Droits aux congés par employé et par année"""
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='droits_conges')
    annee = models.IntegerField()
    periode_reference_debut = models.DateField()
    periode_reference_fin = models.DateField()
    
    # Jours acquis
    jours_acquis_base = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Jours acquis (base 1,5j ouvrable/mois)")
    jours_acquis_anciennete = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Jours supplémentaires ancienneté")
    jours_reportes = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Jours reportés année précédente")
    jours_exceptionnels = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Jours exceptionnels accordés")
    
    # Jours utilisés
    jours_pris = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    jours_planifies = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Solde
    solde_disponible = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Indemnité compensatrice (en cas de départ)
    indemnite_conge = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'droits_conges'
        verbose_name = 'Droit aux congés'
        verbose_name_plural = 'Droits aux congés'
        unique_together = ['employe', 'annee']
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.annee}: {self.solde_disponible} jours"
    
    def calculer_solde(self):
        """Calculer le solde disponible"""
        total_acquis = (
            self.jours_acquis_base + 
            self.jours_acquis_anciennete + 
            self.jours_reportes + 
            self.jours_exceptionnels
        )
        self.solde_disponible = total_acquis - self.jours_pris - self.jours_planifies
        return self.solde_disponible
