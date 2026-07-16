from django.db import models
from django.utils import timezone
from decimal import Decimal
from datetime import date
from employes.models import Employe


class DemandeCongePublique(models.Model):
    """Demandes de congés depuis l'interface publique employé"""
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('soumise', 'Soumise'),
        ('en_cours', 'En cours de traitement'),
        ('approuvee', 'Approuvée'),
        ('rejetee', 'Rejetée'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='demandes_conges_publiques')
    type_conge = models.CharField(max_length=50, choices=[
        ('annuel', 'Congé annuel'),
        ('maladie', 'Congé maladie'),
        ('maternite', 'Congé maternité'),
        ('paternite', 'Congé paternité'),
        ('formation', 'Congé formation'),
        ('sans_solde', 'Congé sans solde'),
    ])
    date_debut = models.DateField()
    date_fin = models.DateField()
    nombre_jours_demandes = models.IntegerField()
    motif = models.TextField()
    
    # Documents joints
    document_justificatif = models.FileField(
        upload_to='conges/demandes_publiques/', 
        blank=True, 
        null=True,
        help_text="Document signé ou justificatif médical"
    )
    
    # Statut et traitement
    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    date_soumission = models.DateTimeField(null=True, blank=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    traite_par = models.ForeignKey(
        Employe, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='conges_traites'
    )
    commentaire_traitement = models.TextField(blank=True, null=True)
    
    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'demandes_conges_publiques'
        verbose_name = 'Demande de congé (publique)'
        verbose_name_plural = 'Demandes de congés (publiques)'
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.get_type_conge_display()} ({self.date_debut})"
    
    def soumettre(self):
        """Soumet la demande pour traitement"""
        self.statut = 'soumise'
        self.date_soumission = timezone.now()
        self.save()
    
    def peut_etre_modifiee(self):
        """Vérifie si la demande peut encore être modifiée"""
        return self.statut in ['brouillon', 'rejetee']


class PermissionExceptionnelle(models.Model):
    """Permissions exceptionnelles avec pièces justificatives"""
    TYPES_PERMISSION = (
        ('medicale', 'Rendez-vous médical'),
        ('administrative', 'Démarche administrative'),
        ('familiale', 'Événement familial'),
        ('urgence', 'Urgence personnelle'),
        ('formation', 'Formation externe'),
        ('autre', 'Autre motif'),
    )
    
    STATUTS = (
        ('demandee', 'Demandée'),
        ('approuvee', 'Approuvée'),
        ('rejetee', 'Rejetée'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='permissions_exceptionnelles')
    type_permission = models.CharField(max_length=20, choices=TYPES_PERMISSION)
    date_permission = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    duree_heures = models.DecimalField(max_digits=4, decimal_places=2)
    
    motif_detaille = models.TextField()
    piece_justificative = models.FileField(
        upload_to='permissions/justificatifs/', 
        help_text="Convocation, certificat médical, etc."
    )
    
    # Approbation
    statut = models.CharField(max_length=20, choices=STATUTS, default='demandee')
    approuve_par = models.ForeignKey(
        Employe, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='permissions_approuvees'
    )
    date_approbation = models.DateTimeField(null=True, blank=True)
    commentaire_approbation = models.TextField(blank=True, null=True)
    
    # Impact paie
    deduction_salaire = models.BooleanField(default=False)
    heures_a_recuperer = models.BooleanField(default=True)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'permissions_exceptionnelles'
        verbose_name = 'Permission exceptionnelle'
        verbose_name_plural = 'Permissions exceptionnelles'
        ordering = ['-date_permission']
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.get_type_permission_display()} ({self.date_permission})"


class ParametrageConges(models.Model):
    """Paramétrage du calcul automatique des congés par entreprise"""
    entreprise = models.OneToOneField(
        'core.Entreprise', 
        on_delete=models.CASCADE, 
        related_name='parametrage_conges'
    )
    
    # Règles de base
    jours_conges_annuels = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal('30.0'),
        help_text="Nombre de jours de congés annuels de base (Code du Travail Art. 222 : 30 j/an)"
    )
    jours_par_mois = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal('2.5'),
        help_text="Nombre de jours acquis par mois travaillé (Code du Travail Art. 222 : 2,5 j/mois)"
    )
    
    # Bonus d'ancienneté
    bonus_anciennete_actif = models.BooleanField(default=True)
    jours_bonus_par_tranche = models.IntegerField(default=2)
    annees_par_tranche = models.IntegerField(default=5)
    
    # Cas spéciaux
    jours_mineurs = models.IntegerField(default=24, help_text="Jours pour les moins de 18 ans")
    
    # Report de congés
    report_autorise = models.BooleanField(default=True)
    max_jours_report = models.IntegerField(default=5)
    
    # Validation automatique
    auto_calcul_actif = models.BooleanField(default=True)
    mise_a_jour_mensuelle = models.BooleanField(default=True)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'parametrage_conges'
        verbose_name = 'Paramétrage congés'
        verbose_name_plural = 'Paramétrages congés'
    
    def __str__(self):
        return f"Paramétrage congés - {self.entreprise.nom}"
