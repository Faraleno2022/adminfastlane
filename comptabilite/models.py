from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP
import uuid
from core.models import Entreprise, Utilisateur

# Import des modèles de trésorerie avancée à la fin du fichier pour éviter les imports circulaires
# from .models_tresorerie import *


class PlanComptable(models.Model):
    """Plan comptable SYSCOHADA"""
    CLASSES = [
        ('1', 'Classe 1 - Comptes de ressources durables'),
        ('2', 'Classe 2 - Comptes d\'actif immobilisé'),
        ('3', 'Classe 3 - Comptes de stocks'),
        ('4', 'Classe 4 - Comptes de tiers'),
        ('5', 'Classe 5 - Comptes de trésorerie'),
        ('6', 'Classe 6 - Comptes de charges'),
        ('7', 'Classe 7 - Comptes de produits'),
        ('8', 'Classe 8 - Comptes des autres charges'),
        ('9', 'Classe 9 - Comptes analytiques'),
    ]
    
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='comptes_comptables')
    numero_compte = models.CharField(max_length=20, verbose_name='N° Compte')
    intitule = models.CharField(max_length=200, verbose_name='Intitulé')
    classe = models.CharField(max_length=1, choices=CLASSES)
    compte_parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='sous_comptes')
    est_actif = models.BooleanField(default=True)
    solde_debiteur = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    solde_crediteur = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'plan_comptable'
        verbose_name = 'Compte comptable'
        verbose_name_plural = 'Plan comptable'
        unique_together = ['entreprise', 'numero_compte']
        ordering = ['numero_compte']
    
    def __str__(self):
        return f"{self.numero_compte} - {self.intitule}"
    
    @property
    def solde(self):
        return self.solde_debiteur - self.solde_crediteur


class Journal(models.Model):
    """Journaux comptables"""
    TYPES_JOURNAL = [
        ('AC', 'Achats'),
        ('VT', 'Ventes'),
        ('BQ', 'Banque'),
        ('CA', 'Caisse'),
        ('OD', 'Opérations diverses'),
        ('AN', 'À nouveau'),
        ('SA', 'Salaires'),
    ]
    
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='journaux')
    code = models.CharField(max_length=5, verbose_name='Code journal')
    libelle = models.CharField(max_length=100, verbose_name='Libellé')
    type_journal = models.CharField(max_length=2, choices=TYPES_JOURNAL)
    compte_contrepartie = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'journaux_comptables'
        verbose_name = 'Journal'
        verbose_name_plural = 'Journaux'
        unique_together = ['entreprise', 'code']
    
    def __str__(self):
        return f"{self.code} - {self.libelle}"


class ExerciceComptable(models.Model):
    """Exercice comptable (année fiscale)"""
    STATUTS = [
        ('ouvert', 'Ouvert'),
        ('cloture', 'Clôturé'),
    ]
    
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='exercices')
    libelle = models.CharField(max_length=100, verbose_name='Libellé')
    date_debut = models.DateField(verbose_name='Date début')
    date_fin = models.DateField(verbose_name='Date fin')
    statut = models.CharField(max_length=10, choices=STATUTS, default='ouvert')
    est_courant = models.BooleanField(default=False, verbose_name='Exercice courant')
    
    class Meta:
        db_table = 'exercices_comptables'
        verbose_name = 'Exercice comptable'
        verbose_name_plural = 'Exercices comptables'
        ordering = ['-date_debut']
    
    def __str__(self):
        return self.libelle


class PieceComptable(models.Model):
    """Pièces comptables (factures, reçus, etc.)"""
    TYPES_PIECE = [
        ('FA', 'Facture achat'),
        ('FV', 'Facture vente'),
        ('RC', 'Reçu caisse'),
        ('RB', 'Relevé banque'),
        ('OD', 'Opération diverse'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='pieces_comptables')
    numero = models.CharField(max_length=50, verbose_name='N° Pièce')
    type_piece = models.CharField(max_length=2, choices=TYPES_PIECE)
    date_piece = models.DateField(verbose_name='Date pièce')
    libelle = models.CharField(max_length=200)
    tiers = models.ForeignKey('Tiers', on_delete=models.SET_NULL, null=True, blank=True)
    montant_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    fichier = models.FileField(upload_to='pieces_comptables/', blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'pieces_comptables'
        verbose_name = 'Pièce comptable'
        verbose_name_plural = 'Pièces comptables'
        ordering = ['-date_piece']
    
    def __str__(self):
        return f"{self.numero} - {self.libelle}"


class EcritureComptable(models.Model):
    """Écritures comptables"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='ecritures')
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='ecritures')
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='ecritures')
    piece = models.ForeignKey(PieceComptable, on_delete=models.SET_NULL, null=True, blank=True, related_name='ecritures')
    numero_ecriture = models.CharField(max_length=20, verbose_name='N° Écriture')
    date_ecriture = models.DateField(verbose_name='Date écriture')
    libelle = models.CharField(max_length=200, verbose_name='Libellé')
    piece_jointe = models.FileField(upload_to='ecritures/pieces/', blank=True, null=True,
                                    verbose_name='Pièce justificative (PDF, scan, photo…)')
    est_validee = models.BooleanField(default=False, verbose_name='Validée')
    date_validation = models.DateTimeField(null=True, blank=True)
    validee_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'ecritures_comptables'
        verbose_name = 'Écriture comptable'
        verbose_name_plural = 'Écritures comptables'
        ordering = ['-date_ecriture', '-numero_ecriture']
        indexes = [
            models.Index(fields=['journal', 'date_ecriture'], name='idx_ecriture_journal_date'),
            models.Index(fields=['entreprise', 'date_ecriture'], name='idx_ecriture_ent_date'),
            models.Index(fields=['exercice'], name='idx_ecriture_exercice'),
        ]
    
    def __str__(self):
        return f"{self.numero_ecriture} - {self.libelle}"
    
    @property
    def total_debit(self):
        return sum(l.montant_debit for l in self.lignes.all())
    
    @property
    def total_credit(self):
        return sum(l.montant_credit for l in self.lignes.all())
    
    @property
    def est_equilibree(self):
        """Équilibrée = au moins une ligne ET total débit = total crédit.

        Une écriture sans aucune ligne ne doit jamais être considérée comme
        équilibrée (0 == 0), sinon elle pourrait être validée vide.
        """
        return self.lignes.exists() and self.total_debit == self.total_credit


class LigneEcriture(models.Model):
    """Lignes d'écritures comptables"""
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.CASCADE, related_name='lignes')
    compte = models.ForeignKey(PlanComptable, on_delete=models.CASCADE, related_name='lignes_ecritures')
    libelle = models.CharField(max_length=200, blank=True)
    montant_debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    centre_analyse = models.ForeignKey('CentreAnalyse', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='lignes_ecritures',
                                       verbose_name='Dimension analytique (projet, agence, centre de coût…)')

    class Meta:
        db_table = 'lignes_ecritures'
        verbose_name = 'Ligne d\'écriture'
        verbose_name_plural = 'Lignes d\'écritures'

    def __str__(self):
        return f"{self.compte.numero_compte} - D:{self.montant_debit} C:{self.montant_credit}"

    def _valider_montants(self):
        """Règles comptables de base sur les montants d'une ligne."""
        from django.core.exceptions import ValidationError
        debit = self.montant_debit or Decimal('0.00')
        credit = self.montant_credit or Decimal('0.00')
        if debit < 0 or credit < 0:
            raise ValidationError("Les montants d'une ligne d'écriture ne peuvent pas être négatifs.")
        if debit > 0 and credit > 0:
            raise ValidationError("Une ligne d'écriture ne peut pas porter à la fois un débit et un crédit.")
        if debit == 0 and credit == 0:
            raise ValidationError("Une ligne d'écriture doit porter un débit ou un crédit non nul.")

    def clean(self):
        super().clean()
        self._valider_montants()

    def save(self, *args, **kwargs):
        # Les lignes sont souvent créées via objects.create() (sans formulaire) :
        # on applique les règles de montants à chaque enregistrement.
        self._valider_montants()
        super().save(*args, **kwargs)


class Tiers(models.Model):
    """Tiers (clients, fournisseurs)"""
    TYPES_TIERS = [
        ('client', 'Client'),
        ('fournisseur', 'Fournisseur'),
        ('mixte', 'Client et Fournisseur'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='tiers')
    code = models.CharField(max_length=20, verbose_name='Code tiers')
    raison_sociale = models.CharField(max_length=200, verbose_name='Raison sociale')
    type_tiers = models.CharField(max_length=15, choices=TYPES_TIERS)
    nif = models.CharField(max_length=50, blank=True, null=True, verbose_name='NIF')
    adresse = models.TextField(blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    compte_comptable = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    plafond_credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    solde = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tiers_comptables'
        verbose_name = 'Tiers'
        verbose_name_plural = 'Tiers'
        unique_together = ['entreprise', 'code']
        ordering = ['raison_sociale']
    
    def __str__(self):
        return f"{self.code} - {self.raison_sociale}"


class Facture(models.Model):
    """Factures clients et fournisseurs"""
    TYPES_FACTURE = [
        ('achat', 'Facture d\'achat'),
        ('vente', 'Facture de vente'),
        ('avoir_client', 'Facture d\'avoir (client)'),
        ('avoir_fournisseur', 'Facture d\'avoir (fournisseur)'),
        ('acompte', 'Facture d\'acompte'),
    ]
    STATUTS = [
        ('brouillon', 'Brouillon'),
        ('validee', 'Validée'),
        ('payee', 'Payée'),
        ('annulee', 'Annulée'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='factures')
    numero = models.CharField(max_length=50, verbose_name='N° Facture')
    type_facture = models.CharField(max_length=20, choices=TYPES_FACTURE)
    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name='factures')
    date_facture = models.DateField(verbose_name='Date facture')
    date_echeance = models.DateField(verbose_name='Date échéance', null=True, blank=True)
    reference_externe = models.CharField(max_length=100, blank=True, null=True, verbose_name='Réf. externe')
    montant_ht = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_tva = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_paye = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    statut = models.CharField(max_length=15, choices=STATUTS, default='brouillon')
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    fichier = models.FileField(upload_to='factures/', blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'factures'
        verbose_name = 'Facture'
        verbose_name_plural = 'Factures'
        ordering = ['-date_facture']
        indexes = [
            models.Index(fields=['tiers', 'date_facture'], name='idx_facture_tiers_date'),
            models.Index(fields=['statut'], name='idx_facture_statut'),
            models.Index(fields=['date_echeance'], name='idx_facture_echeance'),
        ]
    
    def __str__(self):
        return f"{self.numero} - {self.tiers.raison_sociale}"
    
    @property
    def reste_a_payer(self):
        return self.montant_ttc - self.montant_paye

    def recalculer_totaux(self, sauvegarder=True):
        """Recalcule les totaux de la facture depuis ses lignes."""
        from django.db.models import Sum

        totaux = self.lignes.aggregate(
            ht=Sum('montant_ht'), tva=Sum('montant_tva'), ttc=Sum('montant_ttc'))
        self.montant_ht = totaux['ht'] or Decimal('0.00')
        self.montant_tva = totaux['tva'] or Decimal('0.00')
        self.montant_ttc = totaux['ttc'] or Decimal('0.00')
        if sauvegarder:
            self.save(update_fields=['montant_ht', 'montant_tva', 'montant_ttc'])
        return self.montant_ht, self.montant_tva, self.montant_ttc


class LigneFacture(models.Model):
    """Lignes de facture"""
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='lignes')
    designation = models.CharField(max_length=200)
    quantite = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    montant_ht = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_tva = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    compte_comptable = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'lignes_factures'
        verbose_name = 'Ligne de facture'
        verbose_name_plural = 'Lignes de factures'
    
    def save(self, *args, **kwargs):
        centime = Decimal('0.01')
        self.montant_ht = (self.quantite * self.prix_unitaire).quantize(
            centime, rounding=ROUND_HALF_UP)
        self.montant_tva = (self.montant_ht * self.taux_tva / Decimal('100')).quantize(
            centime, rounding=ROUND_HALF_UP)
        self.montant_ttc = (self.montant_ht + self.montant_tva).quantize(
            centime, rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)
        self.facture.recalculer_totaux()

    def delete(self, *args, **kwargs):
        facture = self.facture
        resultat = super().delete(*args, **kwargs)
        facture.recalculer_totaux()
        return resultat


class Reglement(models.Model):
    """Règlements (paiements)"""
    MODES_PAIEMENT = [
        ('especes', 'Espèces'),
        ('cheque', 'Chèque'),
        ('virement', 'Virement bancaire'),
        ('mobile', 'Mobile Money'),
        ('carte', 'Carte bancaire'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='reglements')
    numero = models.CharField(max_length=50, verbose_name='N° Règlement')
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='reglements')
    date_reglement = models.DateField(verbose_name='Date règlement')
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    mode_paiement = models.CharField(max_length=15, choices=MODES_PAIEMENT)
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name='Référence paiement')
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'reglements'
        verbose_name = 'Règlement'
        verbose_name_plural = 'Règlements'
        ordering = ['-date_reglement']
    
    def __str__(self):
        return f"{self.numero} - {self.montant} GNF"


class TauxTVASimple(models.Model):
    """Taux de TVA configurables (version simple pour factures)"""
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='taux_tva_simple')
    libelle = models.CharField(max_length=50)
    taux = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    compte_tva_collectee = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True, related_name='tva_collectee')
    compte_tva_deductible = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True, related_name='tva_deductible')
    est_defaut = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'taux_tva_simple'
        verbose_name = 'Taux de TVA (Simple)'
        verbose_name_plural = 'Taux de TVA (Simple)'
    
    def __str__(self):
        return f"{self.libelle} ({self.taux}%)"
# MODULE 1: GESTION DES IMMOBILISATIONS
# ============================================================================

class Immobilisation(models.Model):
    """Registre des immobilisations"""
    CATEGORIES = [
        ('terrain', 'Terrains'),
        ('construction', 'Constructions'),
        ('materiel', 'Matériel'),
        ('mobilier', 'Mobilier'),
        ('informatique', 'Informatique'),
        ('vehicule', 'Véhicules'),
        ('autre', 'Autre'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='immobilisations')
    numero = models.CharField(max_length=50, verbose_name='N° Immobilisation', unique=True)
    designation = models.CharField(max_length=200)
    categorie = models.CharField(max_length=20, choices=CATEGORIES)
    date_acquisition = models.DateField(verbose_name='Date acquisition')
    valeur_acquisition = models.DecimalField(max_digits=15, decimal_places=2)
    lieu = models.CharField(max_length=200, blank=True, null=True)
    fournisseur = models.ForeignKey(Tiers, on_delete=models.SET_NULL, null=True, blank=True)
    compte_immobilisation = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True, related_name='immobilisations')
    compte_amortissement = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True, related_name='amortissements_immo')
    duree_vie_ans = models.IntegerField(verbose_name='Durée de vie (années)', default=5)
    mode_amortissement = models.CharField(max_length=20, choices=[('lineaire', 'Linéaire'), ('degressif', 'Dégressif')], default='lineaire')
    est_actif = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'immobilisations'
        verbose_name = 'Immobilisation'
        verbose_name_plural = 'Immobilisations'
        ordering = ['-date_acquisition']

    def __str__(self):
        return f"{self.numero} - {self.designation}"


class Amortissement(models.Model):
    """Amortissements des immobilisations"""
    immobilisation = models.ForeignKey('Immobilisation', on_delete=models.CASCADE, related_name='amortissements')
    exercice = models.ForeignKey('ExerciceComptable', on_delete=models.CASCADE, related_name='amortissements')
    taux_amortissement = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'))
    montant_amortissement = models.DecimalField(max_digits=15, decimal_places=2)
    montant_cumule = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    ecriture = models.ForeignKey('EcritureComptable', on_delete=models.SET_NULL, null=True, blank=True)
    date_enregistrement = models.DateField(auto_now_add=True)
    
    class Meta:
        db_table = 'amortissements'
        verbose_name = 'Amortissement'
        verbose_name_plural = 'Amortissements'
        unique_together = ['immobilisation', 'exercice']
    
    def __str__(self):
        return f"{self.immobilisation.numero} - {self.exercice.libelle}"


class CessionImmobilisation(models.Model):
    """Cessions et mises au rebut d'immobilisations"""
    TYPES_SORTIE = [
        ('vente', 'Vente'),
        ('rebut', 'Mise au rebut'),
        ('echange', 'Échange'),
        ('don', 'Don'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    immobilisation = models.ForeignKey('Immobilisation', on_delete=models.CASCADE, related_name='cessions')
    type_sortie = models.CharField(max_length=20, choices=TYPES_SORTIE)
    date_sortie = models.DateField(verbose_name='Date sortie')
    prix_vente = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), blank=True, null=True)
    acheteur = models.ForeignKey('Tiers', on_delete=models.SET_NULL, null=True, blank=True)
    resultat_cession = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), help_text='Plus ou moins-value')
    ecriture = models.ForeignKey('EcritureComptable', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'cessions_immobilisations'
        verbose_name = 'Cession immobilisation'
        verbose_name_plural = 'Cessions immobilisations'
    
    def __str__(self):
        return f"{self.immobilisation.numero} - {self.type_sortie}"


# ============================================================================
# MODULE 2: STOCKS & INVENTAIRES
# ============================================================================

class Stock(models.Model):
    """Gestion des stocks"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='stocks')
    code = models.CharField(max_length=50, verbose_name='Code article', unique=True)
    designation = models.CharField(max_length=200)
    unite = models.CharField(max_length=20, default='Unité')
    quantite_stock = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    quantite_reservee = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    prix_unitaire_moyen = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    valeur_stock = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    stock_minimum = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    stock_maximum = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    compte_stock = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'stocks'
        verbose_name = 'Stock'
        verbose_name_plural = 'Stocks'
    
    def __str__(self):
        return f"{self.code} - {self.designation}"


class Inventaire(models.Model):
    """Inventaires périodiques"""
    STATUTS = [
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('valide', 'Validé'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='inventaires')
    numero = models.CharField(max_length=50, verbose_name='N° Inventaire')
    date_inventaire = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_cours')
    responsable = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'inventaires'
        verbose_name = 'Inventaire'
        verbose_name_plural = 'Inventaires'
    
    def __str__(self):
        return f"{self.numero} - {self.date_inventaire}"


class LigneInventaire(models.Model):
    """Lignes d'inventaire"""
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    quantite_theorique = models.DecimalField(max_digits=15, decimal_places=2)
    quantite_comptee = models.DecimalField(max_digits=15, decimal_places=2)
    
    class Meta:
        db_table = 'lignes_inventaires'
        verbose_name = 'Ligne inventaire'
        verbose_name_plural = 'Lignes inventaires'
        unique_together = ['inventaire', 'stock']
    
    def __str__(self):
        return f"{self.stock.code} - Inventaire {self.inventaire.numero}"


class VariationStock(models.Model):
    """Variations de stocks"""
    TYPES_VARIATION = [
        ('entree', 'Entrée'),
        ('sortie', 'Sortie'),
        ('ajustement', 'Ajustement'),
        ('transfert', 'Transfert'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='variations')
    type_variation = models.CharField(max_length=20, choices=TYPES_VARIATION)
    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    montant = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    date_variation = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'variations_stocks'
        verbose_name = 'Variation stock'
        verbose_name_plural = 'Variations stocks'
    
    def __str__(self):
        return f"{self.stock.code} - {self.type_variation}"


class AjustementStock(models.Model):
    """Ajustements de stock"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='ajustements')
    ancienne_quantite = models.DecimalField(max_digits=15, decimal_places=2)
    nouvelle_quantite = models.DecimalField(max_digits=15, decimal_places=2)
    motif = models.CharField(max_length=200)
    approuve_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_approbation = models.DateTimeField(null=True, blank=True)
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    date_ajustement = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'ajustements_stocks'
        verbose_name = 'Ajustement stock'
        verbose_name_plural = 'Ajustements stocks'
    
    def __str__(self):
        return f"{self.stock.code} - Ajustement"


# ============================================================================
# MODULE 3: RAPPROCHEMENTS BANCAIRES
# ============================================================================

class CompteBancaire(models.Model):
    """Comptes bancaires"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='comptes_bancaires')
    code = models.CharField(max_length=50, verbose_name='Code compte')
    libelle = models.CharField(max_length=200)
    iban = models.CharField(max_length=50, blank=True, null=True)
    bic = models.CharField(max_length=20, blank=True, null=True)
    banque = models.CharField(max_length=200)
    solde_initial = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    compte_comptable = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'comptes_bancaires'
        verbose_name = 'Compte bancaire'
        verbose_name_plural = 'Comptes bancaires'
    
    def __str__(self):
        return f"{self.code} - {self.libelle}"


class RapprochementBancaire(models.Model):
    """Rapprochements bancaires"""
    STATUTS = [
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('valide', 'Validé'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compte_bancaire = models.ForeignKey(CompteBancaire, on_delete=models.CASCADE, related_name='rapprochements')
    date_rapprochement = models.DateField()
    solde_bancaire = models.DecimalField(max_digits=15, decimal_places=2)
    solde_comptable = models.DecimalField(max_digits=15, decimal_places=2)
    ecart = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_cours')
    responsable = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'rapprochements_bancaires'
        verbose_name = 'Rapprochement bancaire'
        verbose_name_plural = 'Rapprochements bancaires'
    
    def __str__(self):
        return f"{self.compte_bancaire.code} - {self.date_rapprochement}"


class ReleveBancaire(models.Model):
    """Relevés bancaires"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compte_bancaire = models.ForeignKey(CompteBancaire, on_delete=models.CASCADE, related_name='releves')
    numero = models.CharField(max_length=50, verbose_name='N° Relevé')
    date_debut = models.DateField()
    date_fin = models.DateField()
    solde_initial = models.DecimalField(max_digits=15, decimal_places=2)
    solde_final = models.DecimalField(max_digits=15, decimal_places=2)
    fichier = models.FileField(upload_to='releves_bancaires/', blank=True, null=True)
    date_import = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'releves_bancaires'
        verbose_name = 'Relevé bancaire'
        verbose_name_plural = 'Relevés bancaires'
    
    def __str__(self):
        return f"{self.numero} - {self.date_fin}"


class OperationBancaire(models.Model):
    """Opérations bancaires"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    releve = models.ForeignKey(ReleveBancaire, on_delete=models.CASCADE, related_name='operations')
    date_operation = models.DateField()
    description = models.CharField(max_length=200)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    type_operation = models.CharField(max_length=20, choices=[('debit', 'Débit'), ('credit', 'Crédit')])
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    lettrage_id = models.CharField(max_length=50, blank=True, null=True)
    
    class Meta:
        db_table = 'operations_bancaires'
        verbose_name = 'Opération bancaire'
        verbose_name_plural = 'Opérations bancaires'
    
    def __str__(self):
        return f"{self.date_operation} - {self.montant}"


class LettrageOperation(models.Model):
    """Lettrage des opérations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation_bancaire = models.OneToOneField(OperationBancaire, on_delete=models.CASCADE, related_name='lettrage')
    ecriture = models.OneToOneField(EcritureComptable, on_delete=models.CASCADE, related_name='lettrage_bancaire')
    date_lettrage = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'lettrages_operations'
        verbose_name = 'Lettrage opération'
        verbose_name_plural = 'Lettrages opérations'


class EcartBancaire(models.Model):
    """Gestion des écarts bancaires"""
    TYPES_ECART = [
        ('frais', 'Frais bancaires'),
        ('interet', 'Intérêts'),
        ('erreur', 'Erreur de saisie'),
        ('retard', 'Retard de compensation'),
        ('autre', 'Autre'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rapprochement = models.ForeignKey(RapprochementBancaire, on_delete=models.CASCADE, related_name='ecarts')
    type_ecart = models.CharField(max_length=20, choices=TYPES_ECART)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField()
    compte_comptable = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    est_resolu = models.BooleanField(default=False)
    date_resolution = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'ecarts_bancaires'
        verbose_name = 'Écart bancaire'
        verbose_name_plural = 'Écarts bancaires'
    
    def __str__(self):
        return f"{self.type_ecart} - {self.montant}"


# ============================================================================
# MODULE 4: ANALYSE FINANCIÈRE
# ============================================================================

class RatioFinancier(models.Model):
    """Ratios financiers"""
    TYPES_RATIO = [
        ('liquidite', 'Liquidité'),
        ('solvabilite', 'Solvabilité'),
        ('rentabilite', 'Rentabilité'),
        ('activite', 'Activité'),
        ('endettement', 'Endettement'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='ratios_financiers')
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='ratios')
    type_ratio = models.CharField(max_length=20, choices=TYPES_RATIO)
    nom = models.CharField(max_length=100)
    valeur = models.DecimalField(max_digits=10, decimal_places=2)
    formule = models.CharField(max_length=200, blank=True, null=True, help_text='Formule de calcul')
    interprtation = models.TextField(blank=True, null=True)
    date_calcul = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'ratios_financiers'
        verbose_name = 'Ratio financier'
        verbose_name_plural = 'Ratios financiers'
    
    def __str__(self):
        return f"{self.nom} ({self.exercice.libelle})"


class FluxTresorerie(models.Model):
    """Tableaux de flux de trésorerie"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='flux_tresorerie')
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='flux')
    flux_exploitation = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    flux_investissement = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    flux_financement = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    variation_nette = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    date_calcul = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'flux_tresorerie'
        verbose_name = 'Flux trésorerie'
        verbose_name_plural = 'Flux trésorerie'
    
    def __str__(self):
        return f"Flux {self.exercice.libelle}"


class Budget(models.Model):
    """Budget & prévisions"""
    STATUTS = [
        ('brouillon', 'Brouillon'),
        ('approuve', 'Approuvé'),
        ('en_cours', 'En cours d\'exécution'),
        ('cloture', 'Clôturé'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='budgets')
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='budgets')
    libelle = models.CharField(max_length=200)
    montant_total = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    approuve_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_approbation = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'budgets'
        verbose_name = 'Budget'
        verbose_name_plural = 'Budgets'
    
    def __str__(self):
        return f"{self.libelle} ({self.exercice.libelle})"


class LigneBudget(models.Model):
    """Lignes de budget"""
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lignes')
    compte = models.ForeignKey(PlanComptable, on_delete=models.CASCADE)
    montant_budget = models.DecimalField(max_digits=15, decimal_places=2)
    montant_realise = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    class Meta:
        db_table = 'lignes_budgets'
        verbose_name = 'Ligne budget'
        verbose_name_plural = 'Lignes budgets'
        unique_together = ['budget', 'compte']
    
    def __str__(self):
        return f"{self.compte.numero_compte} - Budget"


class AnalyseComparative(models.Model):
    """Analyses comparatives (exercices antérieurs)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='analyses_comparatives')
    exercice_actuel = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='analyses_actuel')
    exercice_precedent = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='analyses_precedent')
    compte = models.ForeignKey(PlanComptable, on_delete=models.CASCADE)
    valeur_actuelle = models.DecimalField(max_digits=15, decimal_places=2)
    valeur_precedente = models.DecimalField(max_digits=15, decimal_places=2)
    variation_absolue = models.DecimalField(max_digits=15, decimal_places=2)
    variation_pourcentage = models.DecimalField(max_digits=6, decimal_places=2)
    date_analyse = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'analyses_comparatives'
        verbose_name = 'Analyse comparative'
        verbose_name_plural = 'Analyses comparatives'
    
    def __str__(self):
        return f"Analyse {self.exercice_actuel.libelle} vs {self.exercice_precedent.libelle}"


# ============================================================================
# MODULE 5: FISCALITÉ & DÉCLARATIONS
# ============================================================================

class RecapitulatifTVA(models.Model):
    """Récapitulatifs TVA"""
    declaration = models.ForeignKey('comptabilite.DeclarationTVA', on_delete=models.CASCADE, related_name='recapitulatifs')
    operation = models.CharField(max_length=100)  # ex: "Ventes UE", "Acquisitions UE"
    montant_ht = models.DecimalField(max_digits=15, decimal_places=2)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2)
    montant_tva = models.DecimalField(max_digits=15, decimal_places=2)
    
    class Meta:
        db_table = 'recapitulatifs_tva'
        verbose_name = 'Récapitulatif TVA'
        verbose_name_plural = 'Récapitulatifs TVA'


class DeclarationFiscale(models.Model):
    """Déclarations fiscales"""
    TYPES = [
        ('irpp', 'IRPP'),
        ('is', 'Impôt sur les Sociétés'),
        ('patente', 'Patente'),
        ('autre', 'Autre'),
    ]
    STATUTS = [
        ('brouillon', 'Brouillon'),
        ('declaree', 'Déclarée'),
        ('payee', 'Payée'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='declarations_fiscales')
    type_declaration = models.CharField(max_length=20, choices=TYPES)
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE)
    base_imposable = models.DecimalField(max_digits=15, decimal_places=2)
    taux_imposition = models.DecimalField(max_digits=5, decimal_places=2)
    montant_impot = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    date_declaration = models.DateField(null=True, blank=True)
    montant_paye = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    date_paiement = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'declarations_fiscales'
        verbose_name = 'Déclaration fiscale'
        verbose_name_plural = 'Déclarations fiscales'
    
    def __str__(self):
        return f"{self.get_type_declaration_display()} - {self.exercice.libelle}"


class RetenuAlaSource(models.Model):
    """Gestion des retenues à la source"""
    TYPES_RETENUE = [
        ('prestataire', 'Retenue prestataire'),
        ('dividende', 'Retenue dividende'),
        ('interet', 'Retenue intérêt'),
        ('autre', 'Autre retenue'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name='retenues')
    type_retenue = models.CharField(max_length=20, choices=TYPES_RETENUE)
    montant_brut = models.DecimalField(max_digits=15, decimal_places=2)
    taux_retenue = models.DecimalField(max_digits=5, decimal_places=2)
    montant_retenu = models.DecimalField(max_digits=15, decimal_places=2)
    montant_net = models.DecimalField(max_digits=15, decimal_places=2)
    date_retenue = models.DateField()
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'retenues_source'
        verbose_name = 'Retenue à la source'
        verbose_name_plural = 'Retenues à la source'
    
    def __str__(self):
        return f"{self.tiers.raison_sociale} - {self.montant_retenu}"


class EditionFiscale(models.Model):
    """Éditions fiscales"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='editions_fiscales')
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE)
    type_edition = models.CharField(max_length=100)  # ex: "Déclaration annuelle", "Liasse fiscale"
    date_generation = models.DateTimeField(auto_now_add=True)
    fichier = models.FileField(upload_to='editions_fiscales/')
    validee = models.BooleanField(default=False)
    date_validation = models.DateTimeField(null=True, blank=True)
    validee_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'editions_fiscales'
        verbose_name = 'Édition fiscale'
        verbose_name_plural = 'Éditions fiscales'
    
    def __str__(self):
        return f"{self.type_edition} - {self.exercice.libelle}"


# ============================================================================
# MODULE 6: CONSOLIDATION & MULTI-DEVISES
# ============================================================================

class ConsolidationComptes(models.Model):
    """Consolidation de comptes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.CASCADE, related_name='consolidations')
    entreprise_mere = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='consolidations_mere')
    entreprise_fille = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='consolidations_fille', null=True, blank=True)
    pourcentage_participation = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('100.00'))
    date_consolidation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'consolidations'
        verbose_name = 'Consolidation'
        verbose_name_plural = 'Consolidations'
    
    def __str__(self):
        return f"Consolidation {self.exercice.libelle}"




class TauxChange(models.Model):
    """Taux de change"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    devise_source = models.ForeignKey('core.Devise', on_delete=models.CASCADE, related_name='taux_change_source')
    devise_cible = models.ForeignKey('core.Devise', on_delete=models.CASCADE, related_name='taux_change_cible')
    date_taux = models.DateField()
    taux = models.DecimalField(max_digits=10, decimal_places=4)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'taux_change_compta'
        verbose_name = 'Taux de change'
        verbose_name_plural = 'Taux de change'
        unique_together = ['devise_source', 'devise_cible', 'date_taux']
    
    def __str__(self):
        return f"{self.devise_source.code}/{self.devise_cible.code} - {self.taux}"


class OperationEnDevise(models.Model):
    """Opérations en devises"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name='operations_devise')
    devise = models.ForeignKey('core.Devise', on_delete=models.CASCADE)
    montant_devise = models.DecimalField(max_digits=15, decimal_places=2)
    taux_change = models.DecimalField(max_digits=10, decimal_places=4)
    montant_local = models.DecimalField(max_digits=15, decimal_places=2)
    difference_change = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    date_operation = models.DateField()
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'operations_devise'
        verbose_name = 'Opération en devise'
        verbose_name_plural = 'Opérations en devises'
    
    def __str__(self):
        return f"{self.montant_devise} {self.devise.code}"


class ReeevaluationDevise(models.Model):
    """Réévaluation des créances/dettes en devises"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name='reevaluations')
    devise = models.ForeignKey('core.Devise', on_delete=models.CASCADE)
    date_reevaluation = models.DateField()
    montant_devise = models.DecimalField(max_digits=15, decimal_places=2)
    ancien_taux = models.DecimalField(max_digits=10, decimal_places=4)
    nouveau_taux = models.DecimalField(max_digits=10, decimal_places=4)
    ancien_montant_local = models.DecimalField(max_digits=15, decimal_places=2)
    nouveau_montant_local = models.DecimalField(max_digits=15, decimal_places=2)
    difference_reevaluation = models.DecimalField(max_digits=15, decimal_places=2)
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'reevaluations_devise'
        verbose_name = 'Réévaluation devise'
        verbose_name_plural = 'Réévaluations devises'
    
    def __str__(self):
        return f"Réévaluation {self.date_reevaluation}"


# ============================================================================
# MODULE 7: AUDIT & CONTRÔLE INTERNE
# ============================================================================

class PisteAudit(models.Model):
    """Piste d'audit (traçabilité complète)"""
    ACTIONS = [
        ('create', 'Création'),
        ('update', 'Modification'),
        ('delete', 'Suppression'),
        ('validation', 'Validation'),
        ('cloture', 'Clôture'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='piste_audit')
    utilisateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    module = models.CharField(max_length=100)  # ex: "Factures", "Écritures"
    type_objet = models.CharField(max_length=100)  # ex: "Facture", "Écriture"
    id_objet = models.CharField(max_length=100)
    donnees_anterieres = models.TextField(blank=True, null=True)
    donnees_nouvelles = models.TextField(blank=True, null=True)
    adresse_ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    date_action = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'piste_audit'
        verbose_name = 'Piste audit'
        verbose_name_plural = 'Piste audit'
        ordering = ['-date_action']
        indexes = [
            models.Index(fields=['entreprise', '-date_action']),
            models.Index(fields=['utilisateur', '-date_action']),
        ]
    
    def __str__(self):
        return f"{self.action} - {self.module}"


class LogModification(models.Model):
    """Logs des modifications"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='logs_modification')
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.CASCADE, related_name='logs_modifications')
    utilisateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    ancienne_valeur = models.TextField()
    nouvelle_valeur = models.TextField()
    champ_modifie = models.CharField(max_length=100)
    date_modification = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'logs_modifications'
        verbose_name = 'Log modification'
        verbose_name_plural = 'Logs modifications'
    
    def __str__(self):
        return f"Modification {self.champ_modifie}"


class Approbation(models.Model):
    """Approvals / Validations multi-niveaux"""
    STATUTS = [
        ('en_attente', 'En attente'),
        ('approuvee', 'Approuvée'),
        ('rejetee', 'Rejetée'),
    ]
    NIVEAUX = [
        (1, 'Niveau 1'),
        (2, 'Niveau 2'),
        (3, 'Niveau 3'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.CASCADE, related_name='approbations')
    niveau = models.IntegerField(choices=NIVEAUX)
    approbateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_attente')
    date_approbation = models.DateTimeField(null=True, blank=True)
    commentaire = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'approbations'
        verbose_name = 'Approbation'
        verbose_name_plural = 'Approbations'
        unique_together = ['ecriture', 'niveau']
        ordering = ['niveau']
    
    def __str__(self):
        return f"Approbation Niveau {self.niveau}"


class VerrouillageExercice(models.Model):
    """Verrouillage des périodes comptables"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercice = models.OneToOneField(ExerciceComptable, on_delete=models.CASCADE, related_name='verrouillage')
    verroui_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Verrouillé par')
    est_verroui = models.BooleanField(default=False)
    date_verrouillage = models.DateTimeField(null=True, blank=True)
    raison_verrouillage = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'verrouillages_exercices'
        verbose_name = 'Verrouillage exercice'
        verbose_name_plural = 'Verrouillages exercices'
    
    def __str__(self):
        return f"Verrouillage {self.exercice.libelle}"


# ============================================================================
# MODULE 8: CLIENTS & FOURNISSEURS - DÉTAILS
# ============================================================================

class CompteClientDetail(models.Model):
    """Compte client détaillé"""
    tiers = models.OneToOneField(Tiers, on_delete=models.CASCADE, related_name='compte_detail', limit_choices_to={'type_tiers__in': ['client', 'mixte']})
    date_premiere_achat = models.DateField(null=True, blank=True)
    montant_total_achat = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    solde_courant = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    limite_credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taux_remise_habituel = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    conditions_paiement = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        db_table = 'comptes_clients_detail'
        verbose_name = 'Compte client détaillé'
        verbose_name_plural = 'Comptes clients détaillés'
    
    def __str__(self):
        return f"Compte {self.tiers.raison_sociale}"


class CompteFournisseurDetail(models.Model):
    """Compte fournisseur détaillé"""
    tiers = models.OneToOneField(Tiers, on_delete=models.CASCADE, related_name='compte_fournisseur_detail', limit_choices_to={'type_tiers__in': ['fournisseur', 'mixte']})
    date_premiere_facture = models.DateField(null=True, blank=True)
    montant_total_achat = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    solde_courant = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    delai_paiement_jours = models.IntegerField(default=30)
    taux_remise_habituel = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    termes_paiement = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        db_table = 'comptes_fournisseurs_detail'
        verbose_name = 'Compte fournisseur détaillé'
        verbose_name_plural = 'Comptes fournisseurs détaillés'
    
    def __str__(self):
        return f"Compte {self.tiers.raison_sociale}"


class VieillissementCreances(models.Model):
    """Vieillissement des créances"""
    CATEGORIES = [
        ('courant', 'Courant'),
        ('30j', '30 jours'),
        ('60j', '60 jours'),
        ('90j', '90 jours'),
        ('plus90j', '+90 jours'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name='vieillissements')
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE)
    categorie = models.CharField(max_length=20, choices=CATEGORIES)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    date_facture = models.DateField()
    date_echeance = models.DateField()
    date_calcul = models.DateField(auto_now_add=True)
    
    class Meta:
        db_table = 'vieillissements_creances'
        verbose_name = 'Vieillissement créances'
        verbose_name_plural = 'Vieillissements créances'
    
    def __str__(self):
        return f"{self.tiers.raison_sociale} - {self.categorie}"


class AnalyseImpayes(models.Model):
    """Analyses des impayés"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='analyses_impayes')
    montant_impaye = models.DecimalField(max_digits=15, decimal_places=2)
    jours_retard = models.IntegerField()
    raison_impaye = models.CharField(max_length=200, blank=True, null=True)
    action_prevue = models.CharField(max_length=200, blank=True, null=True)
    date_relance = models.DateField(null=True, blank=True)
    date_analyse = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'analyses_impayes'
        verbose_name = 'Analyse impayé'
        verbose_name_plural = 'Analyses impayés'
    
    def __str__(self):
        return f"Impayé {self.montant_impaye}"


# ============================================================================
# MODULE 9: PARAMÉTRAGES AVANCÉS
# ============================================================================

class ModeleEcriture(models.Model):
    """Modèles d'écritures"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='modeles_ecritures')
    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'modeles_ecritures'
        verbose_name = 'Modèle écriture'
        verbose_name_plural = 'Modèles écritures'
    
    def __str__(self):
        return self.libelle


class LigneModeleEcriture(models.Model):
    """Lignes de modèles d'écritures"""
    modele = models.ForeignKey(ModeleEcriture, on_delete=models.CASCADE, related_name='lignes')
    numero_ligne = models.IntegerField()
    compte = models.ForeignKey(PlanComptable, on_delete=models.CASCADE)
    type_montant = models.CharField(max_length=10, choices=[('debit', 'Débit'), ('credit', 'Crédit')])
    montant_fixe = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    est_montant_variable = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'lignes_modeles_ecritures'
        verbose_name = 'Ligne modèle écriture'
        verbose_name_plural = 'Lignes modèles écritures'
    
    def __str__(self):
        return f"Ligne {self.numero_ligne}"


class CentreAnalyse(models.Model):
    """Centres d'analyse / Centres de coûts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='centres_analyse')
    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=200)
    type_centre = models.CharField(max_length=20, choices=[('cout', 'Centre de coût'), ('profit', 'Centre de profit')])
    responsable = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    budget_annuel = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'centres_analyse'
        verbose_name = 'Centre analyse'
        verbose_name_plural = 'Centres analyse'
    
    def __str__(self):
        return f"{self.code} - {self.libelle}"


class SegmentAnalytique(models.Model):
    """Segments analytiques"""
    TYPES_SEGMENT = [
        ('produit', 'Produit'),
        ('client', 'Client'),
        ('region', 'Région'),
        ('departement', 'Département'),
        ('autre', 'Autre'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='segments_analytiques')
    code = models.CharField(max_length=50)
    libelle = models.CharField(max_length=200)
    type_segment = models.CharField(max_length=20, choices=TYPES_SEGMENT)
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'segments_analytiques'
        verbose_name = 'Segment analytique'
        verbose_name_plural = 'Segments analytiques'
        unique_together = ['entreprise', 'code']
    
    def __str__(self):
        return f"{self.code} - {self.libelle}"


class ComptabiliteAnalytique(models.Model):
    """Comptabilité analytique"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.CASCADE, related_name='analytique')
    centre_analyse = models.ForeignKey(CentreAnalyse, on_delete=models.CASCADE)
    segment = models.ForeignKey(SegmentAnalytique, on_delete=models.CASCADE)
    montant_debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    pourcentage_imputation = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('100.00'))
    
    class Meta:
        db_table = 'comptabilite_analytique'
        verbose_name = 'Comptabilité analytique'
        verbose_name_plural = 'Comptabilité analytique'
    
    def __str__(self):
        return f"Analytique {self.centre_analyse.code}"


# ============================================================================
# MODULE 10: EXPORTS & INTÉGRATIONS
# ============================================================================

class ExportDonnees(models.Model):
    """Exports XML/EDI"""
    FORMATS = [
        ('xml', 'XML'),
        ('edi', 'EDI'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
    ]
    TYPES_EXPORT = [
        ('factures', 'Factures'),
        ('ecritures', 'Écritures'),
        ('tiers', 'Tiers'),
        ('autres', 'Autres'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='exports')
    type_export = models.CharField(max_length=20, choices=TYPES_EXPORT)
    format_export = models.CharField(max_length=10, choices=FORMATS)
    date_export = models.DateTimeField(auto_now_add=True)
    fichier = models.FileField(upload_to='exports/')
    utilisateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'exports_donnees'
        verbose_name = 'Export données'
        verbose_name_plural = 'Exports données'
    
    def __str__(self):
        return f"Export {self.type_export}"


class ImportReleve(models.Model):
    """Imports de relevés bancaires"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compte_bancaire = models.ForeignKey(CompteBancaire, on_delete=models.CASCADE, related_name='imports')
    fichier = models.FileField(upload_to='imports_releves/')
    date_import = models.DateTimeField(auto_now_add=True)
    utilisateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    nombre_operations = models.IntegerField(default=0)
    nombre_operations_acceptees = models.IntegerField(default=0)
    statut_import = models.CharField(max_length=20, default='en_cours')
    
    class Meta:
        db_table = 'imports_releves'
        verbose_name = 'Import relevé'
        verbose_name_plural = 'Imports relevés'
    
    def __str__(self):
        return f"Import {self.compte_bancaire.code}"


class InterfaceEDI(models.Model):
    """Interfaces EDI avec clients/fournisseurs"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name='interfaces_edi')
    code_edi = models.CharField(max_length=50, unique=True)
    format_edi = models.CharField(max_length=20, choices=[('unedifact', 'UNEDIFACT'), ('x12', 'X12'), ('autre', 'Autre')])
    est_actif = models.BooleanField(default=True)
    donnees_config = models.TextField(blank=True, null=True, help_text='Configuration JSON')
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'interfaces_edi'
        verbose_name = 'Interface EDI'
        verbose_name_plural = 'Interfaces EDI'
    
    def __str__(self):
        return f"EDI {self.tiers.code}"


class APIINTEGRATION(models.Model):
    """API d'intégration"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='api_integrations')
    nom = models.CharField(max_length=200)
    type_integration = models.CharField(max_length=100)  # ex: "Banque", "Paie", "Stock"
    url_base = models.URLField()
    token_auth = models.CharField(max_length=500, blank=True, null=True)
    est_actif = models.BooleanField(default=True)
    dernier_sync = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'api_integrations'
        verbose_name = 'API intégration'
        verbose_name_plural = 'API intégrations'
    
    def __str__(self):
        return self.nom


# ============================================================================
# MODULE 11: GESTION DES DEVISES
# ============================================================================

class GestionDeviseCompte(models.Model):
    """Gestion des comptes en devises"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compte = models.ForeignKey(PlanComptable, on_delete=models.CASCADE, related_name='devises_compte')
    devise = models.ForeignKey('core.Devise', on_delete=models.CASCADE)
    solde_devise = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taux_change_dernier = models.DecimalField(max_digits=10, decimal_places=4)
    date_dernier_update = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'gestion_devises_comptes'
        verbose_name = 'Compte en devise'
        verbose_name_plural = 'Comptes en devises'
        unique_together = ['compte', 'devise']
    
    def __str__(self):
        return f"{self.compte.numero_compte} - {self.devise.code}"


class DifferenceChange(models.Model):
    """Différences de change"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation_devise = models.ForeignKey(OperationEnDevise, on_delete=models.CASCADE, related_name='differences_change')
    montant_realise = models.DecimalField(max_digits=15, decimal_places=2)
    montant_provision = models.DecimalField(max_digits=15, decimal_places=2)
    type_difference = models.CharField(max_length=20, choices=[('gain', 'Gain'), ('perte', 'Perte')])
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'differences_change'
        verbose_name = 'Différence change'
        verbose_name_plural = 'Différences change'
    
    def __str__(self):
        return f"Différence {self.type_difference}"


# ============================================================================
# MODULE 12: TRÉSORERIE
# ============================================================================

class PrevisionTresorerie(models.Model):
    """Prévisions de trésorerie"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='previsions_tresorerie')
    mois = models.DateField(verbose_name='Mois de prévision')
    solde_initial = models.DecimalField(max_digits=15, decimal_places=2)
    entrees_prevues = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sorties_prevues = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    solde_prevu = models.DecimalField(max_digits=15, decimal_places=2)
    solde_reel = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    ecart = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'previsions_tresorerie'
        verbose_name = 'Prévision trésorerie'
        verbose_name_plural = 'Prévisions trésorerie'
        unique_together = ['entreprise', 'mois']
    
    def __str__(self):
        return f"Prévision {self.mois.strftime('%m/%Y')}"


class SuiviTresorerie(models.Model):
    """Suivi des flux de trésorerie"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='suivis_tresorerie')
    date_suivi = models.DateField()
    solde_caisse = models.DecimalField(max_digits=15, decimal_places=2)
    solde_banque = models.DecimalField(max_digits=15, decimal_places=2)
    solde_total = models.DecimalField(max_digits=15, decimal_places=2)
    flux_entree_jour = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    flux_sortie_jour = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'suivis_tresorerie'
        verbose_name = 'Suivi trésorerie'
        verbose_name_plural = 'Suivis trésorerie'
        unique_together = ['entreprise', 'date_suivi']
    
    def __str__(self):
        return f"Suivi {self.date_suivi}"


class Placement(models.Model):
    """Gestion des placements"""
    TYPES_PLACEMENT = [
        ('action', 'Action'),
        ('obligation', 'Obligation'),
        ('fonds', 'Fonds commun de placement'),
        ('titre', 'Titre'),
        ('autre', 'Autre'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='placements')
    code = models.CharField(max_length=50)
    designation = models.CharField(max_length=200)
    type_placement = models.CharField(max_length=20, choices=TYPES_PLACEMENT)
    date_acquisition = models.DateField()
    cout_acquisition = models.DecimalField(max_digits=15, decimal_places=2)
    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    prix_unitaire_actuel = models.DecimalField(max_digits=15, decimal_places=2)
    valeur_actuelle = models.DecimalField(max_digits=15, decimal_places=2)
    compte_comptable = models.ForeignKey(PlanComptable, on_delete=models.SET_NULL, null=True, blank=True)
    resultat_non_realise = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taux_rendement = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    date_maj = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'placements'
        verbose_name = 'Placement'
        verbose_name_plural = 'Placements'
    
    def __str__(self):
        return f"{self.code} - {self.designation}"


# ============================================================================
# PHASE 2: FISCALITÉ - TVA ET DÉCLARATIONS
# ============================================================================

class RegimeTVA(models.Model):
    """Régime TVA: Normal, Simplifié, Exempt, Services spécialisés"""
    
    REGIMES = [
        ('NORMAL', 'Normal'),
        ('SIMPLIFIE', 'Simplifié'),
        ('MICRO', 'Micro-entreprise'),
        ('EXEMPT', 'Exempté'),
        ('SERVICES', 'Services spécialisés'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='regimes_tva')
    
    code = models.CharField(max_length=20, unique=True, help_text='Code unique: FR_NORMAL, FR_SIMPLIFIE')
    nom = models.CharField(max_length=100)
    regime = models.CharField(max_length=20, choices=REGIMES)
    
    description = models.TextField(blank=True)
    
    # Configuration des taux
    seuil_chiffre_affaires = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Seuil CA pour changement de régime"
    )
    taux_normal = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'))
    taux_reduit = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.50'))
    taux_super_reduit = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.10'))
    
    # Reporting
    periodicite = models.CharField(
        max_length=20,
        choices=[
            ('MENSUELLE', 'Mensuelle'),
            ('TRIMESTRIELLE', 'Trimestrielle'),
            ('ANNUELLE', 'Annuelle'),
        ],
        default='MENSUELLE'
    )
    
    # Status
    actif = models.BooleanField(default=True)
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    
    # Audit
    utilisateur_creation = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='regimes_tva_created')
    date_creation = models.DateTimeField(auto_now_add=True)
    utilisateur_modification = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='regimes_tva_modified')
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'comptabilite_regime_tva'
        verbose_name = 'Régime TVA'
        verbose_name_plural = 'Régimes TVA'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['entreprise', 'actif']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return f"{self.nom} ({self.code})"
    
    def get_taux_applicable(self, type_taux='NORMAL'):
        """Retourne le taux applicable selon le type"""
        if type_taux == 'NORMAL':
            return self.taux_normal
        elif type_taux == 'REDUIT':
            return self.taux_reduit
        elif type_taux == 'SUPER_REDUIT':
            return self.taux_super_reduit
        return self.taux_normal


class TauxTVA(models.Model):
    """Taux TVA spécifiques pour produits/services"""
    
    NATURES = [
        ('VENTE', 'Vente'),
        ('SERVICE', 'Service'),
        ('TRAVAUX', 'Travaux'),
        ('LIVRAISON', 'Livraison'),
        ('IMPORTATION', 'Importation'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    regime_tva = models.ForeignKey(RegimeTVA, on_delete=models.CASCADE, related_name='taux')
    
    code = models.CharField(max_length=20, help_text='TVA_NORMAL, TVA_5.5')
    nom = models.CharField(max_length=100)
    
    # Taux TVA
    taux = models.DecimalField(max_digits=5, decimal_places=2, help_text='Exemple: 20.00, 5.50')
    nature = models.CharField(max_length=20, choices=NATURES)
    
    description = models.TextField(blank=True)
    
    # Applicabilité
    applicable_au_ventes = models.BooleanField(default=True)
    applicable_aux_achats = models.BooleanField(default=True)
    
    # Status
    actif = models.BooleanField(default=True)
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    
    # Audit
    utilisateur_creation = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='taux_tva_created', null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    utilisateur_modification = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='taux_tva_modified', null=True, blank=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'comptabilite_taux_tva'
        verbose_name = 'Taux TVA'
        verbose_name_plural = 'Taux TVA'
        unique_together = ['regime_tva', 'code']
        ordering = ['-taux']
    
    def __str__(self):
        return f"{self.taux}% - {self.nom}"


class DeclarationTVA(models.Model):
    """Déclaration TVA (DIVA-DEB, DES, etc)"""
    
    STATUTS = [
        ('BROUILLON', 'Brouillon'),
        ('EN_COURS', 'En cours'),
        ('VALIDEE', 'Validée'),
        ('DEPOSEE', 'Déposée'),
        ('ACCEPTEE', 'Acceptée'),
        ('REJETEE', 'Rejetée'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='declarations_tva')
    regime_tva = models.ForeignKey(RegimeTVA, on_delete=models.PROTECT, related_name='declarations')
    exercice = models.ForeignKey(ExerciceComptable, on_delete=models.PROTECT, related_name='declarations_tva')
    
    # Période
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    
    # Totaux (calculés)
    montant_ht = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_tva_collecte = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_tva_deductible = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    montant_tva_due = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Status
    statut = models.CharField(max_length=20, choices=STATUTS, default='BROUILLON')
    
    # Dépôt
    date_depot = models.DateField(null=True, blank=True)
    numero_depot = models.CharField(max_length=50, unique=True, null=True, blank=True)
    
    # Audit
    utilisateur_creation = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='declarations_tva_created')
    date_creation = models.DateTimeField(auto_now_add=True)
    utilisateur_modification = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='declarations_tva_modified')
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'comptabilite_declaration_tva'
        verbose_name = 'Déclaration TVA'
        verbose_name_plural = 'Déclarations TVA'
        unique_together = ['entreprise', 'periode_debut', 'periode_fin']
        ordering = ['-periode_debut']
        indexes = [
            models.Index(fields=['entreprise', 'statut']),
            models.Index(fields=['periode_debut']),
        ]
    
    def __str__(self):
        return f"TVA {self.periode_debut.strftime('%m/%Y')} - {self.entreprise.nom}"
    
    @property
    def montant_a_payer(self):
        """Montant TVA à payer ou à récupérer"""
        return self.montant_tva_collecte - self.montant_tva_deductible


class LigneDeclarationTVA(models.Model):
    """Lignes de détail dans une déclaration TVA"""

    TYPES = [
        ('OPERATIONS', 'Opérations'),
        ('AJUSTEMENT', 'Ajustement'),
        ('CORRECTION', 'Correction'),
        ('OPTION', 'Option'),
    ]
    SENS = [
        ('COLLECTEE', 'TVA collectée (ventes)'),
        ('DEDUCTIBLE', 'TVA déductible (achats)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    declaration = models.ForeignKey(DeclarationTVA, on_delete=models.CASCADE, related_name='lignes')

    # Contenu
    numero_ligne = models.PositiveIntegerField(help_text='Numéro de ligne dans déclaration')
    description = models.CharField(max_length=200)
    taux = models.ForeignKey(TauxTVA, on_delete=models.PROTECT)

    # Montants
    montant_ht = models.DecimalField(max_digits=15, decimal_places=2)
    montant_tva = models.DecimalField(max_digits=15, decimal_places=2)

    type_ligne = models.CharField(max_length=20, choices=TYPES, default='OPERATIONS')
    sens = models.CharField(max_length=12, choices=SENS, default='COLLECTEE',
                            verbose_name='Sens de la TVA',
                            help_text='Collectée sur les ventes ou déductible sur les achats')
    
    # Références
    compte_comptable = models.ForeignKey(PlanComptable, on_delete=models.PROTECT, null=True, blank=True)
    ecriture_comptable = models.ForeignKey(EcritureComptable, on_delete=models.SET_NULL, null=True, blank=True, related_name='lignes_tva')
    
    class Meta:
        db_table = 'comptabilite_ligne_declaration_tva'
        verbose_name = 'Ligne déclaration TVA'
        verbose_name_plural = 'Lignes déclaration TVA'
        ordering = ['declaration', 'numero_ligne']
        unique_together = ['declaration', 'numero_ligne']
    
    def __str__(self):
        return f"Ligne {self.numero_ligne}: {self.description}"


# ============================================================================
# AUDIT & CONFORMITÉ (Phase 2 Week 2)
# ============================================================================

class RapportAudit(models.Model):
    """Rapports d'audit comptable"""
    
    STATUT_CHOICES = [
        ('PLANIFIE', 'Planifié'),
        ('EN_COURS', 'En cours'),
        ('TERMINE', 'Terminé'),
        ('PUBLIE', 'Publié'),
    ]
    
    RISQUE_CHOICES = [
        ('FAIBLE', 'Faible'),
        ('MOYEN', 'Moyen'),
        ('ELEVE', 'Élevé'),
        ('CRITIQUE', 'Critique'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='rapports_audit')
    
    # Informations générales
    code = models.CharField(max_length=50, unique=True)
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Dates
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    date_publication = models.DateField(null=True, blank=True)
    
    # Contenu
    objectifs = models.TextField(help_text='Objectifs de l\'audit')
    perimetre = models.TextField(help_text='Périmètre de l\'audit')
    resultats = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    recommandations = models.TextField(blank=True)
    
    # Méta
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='PLANIFIE')
    niveau_risque_global = models.CharField(max_length=20, choices=RISQUE_CHOICES, default='MOYEN')
    auditeur = models.ForeignKey(Utilisateur, on_delete=models.PROTECT, related_name='rapports_audites')
    responsable_correction = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='corrections_audit')
    
    # Audit
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.PROTECT, related_name='rapports_audit_crees')
    
    class Meta:
        db_table = 'comptabilite_rapport_audit'
        verbose_name = 'Rapport d\'audit'
        verbose_name_plural = 'Rapports d\'audit'
        ordering = ['-date_debut']
        indexes = [
            models.Index(fields=['entreprise', 'statut']),
            models.Index(fields=['date_debut']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return f"Audit {self.code}: {self.titre}"


class AlerteNonConformite(models.Model):
    """Alertes de non-conformité détectées lors des audits"""
    
    SEVERITE_CHOICES = [
        ('MINEURE', 'Mineure'),
        ('MAJEURE', 'Majeure'),
        ('CRITIQUE', 'Critique'),
    ]
    
    STATUT_CHOICES = [
        ('DETECTEE', 'Détectée'),
        ('EN_CORRECTION', 'En correction'),
        ('CORRIGEE', 'Corrigée'),
        ('VERIFIEE', 'Vérifiée'),
        ('ACCEPTEE', 'Acceptée'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='alertes_non_conformite')
    rapport = models.ForeignKey(RapportAudit, on_delete=models.CASCADE, related_name='alertes')
    
    # Identifiant
    numero_alerte = models.CharField(max_length=50)
    titre = models.CharField(max_length=255)
    description = models.TextField()
    
    # Gravité
    severite = models.CharField(max_length=20, choices=SEVERITE_CHOICES)
    domaine = models.CharField(max_length=100, help_text='Domaine affecté: TVA, Comptabilité, etc.')
    
    # Correction
    plan_action = models.TextField(blank=True)
    date_correction_prevue = models.DateField(null=True, blank=True)
    date_correction_reelle = models.DateField(null=True, blank=True)
    
    # Suivi
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='DETECTEE')
    responsable_correction = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True)
    observations = models.TextField(blank=True)
    
    # Audit
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'comptabilite_alerte_non_conformite'
        verbose_name = 'Alerte de non-conformité'
        verbose_name_plural = 'Alertes de non-conformité'
        ordering = ['-date_creation']
        unique_together = ['rapport', 'numero_alerte']
        indexes = [
            models.Index(fields=['entreprise', 'severite']),
            models.Index(fields=['statut']),
            models.Index(fields=['date_correction_prevue']),
        ]
    
    def __str__(self):
        return f"Alerte {self.numero_alerte}: {self.titre}"


class ReglesConformite(models.Model):
    """Règles de conformité à vérifier régulièrement"""
    
    PERIODICITE_CHOICES = [
        ('MENSUELLE', 'Mensuelle'),
        ('TRIMESTRIELLE', 'Trimestrielle'),
        ('SEMESTRIELLE', 'Semestrielle'),
        ('ANNUELLE', 'Annuelle'),
        ('A_LA_DEMANDE', 'À la demande'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='regles_conformite')
    
    # Identification
    code = models.CharField(max_length=50)
    nom = models.CharField(max_length=255)
    description = models.TextField()
    
    # Contenu
    critere_conformite = models.TextField(help_text='Critère exact à vérifier')
    consequence_non_conformite = models.TextField()
    documentation_requise = models.TextField(blank=True)
    
    # Paramètres
    periodicite = models.CharField(max_length=20, choices=PERIODICITE_CHOICES)
    module_concerne = models.CharField(max_length=100, help_text='TVA, Paie, Temps, etc.')
    criticite = models.CharField(max_length=20, choices=[
        ('FAIBLE', 'Faible'),
        ('MOYEN', 'Moyen'),
        ('ELEVE', 'Élevé'),
        ('CRITIQUE', 'Critique'),
    ])
    
    # Statut
    actif = models.BooleanField(default=True)
    
    # Audit
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.PROTECT, related_name='regles_conformite_creees')
    
    class Meta:
        db_table = 'comptabilite_regles_conformite'
        verbose_name = 'Règle de conformité'
        verbose_name_plural = 'Règles de conformité'
        ordering = ['module_concerne', 'code']
        unique_together = ['entreprise', 'code']
        indexes = [
            models.Index(fields=['entreprise', 'module_concerne']),
            models.Index(fields=['actif']),
        ]
    
    def __str__(self):
        return f"{self.code}: {self.nom}"


class HistoriqueModification(models.Model):
    """Historique détaillé des modifications comptables"""
    
    TYPE_OBJET_CHOICES = [
        ('DECLARATION_TVA', 'Déclaration TVA'),
        ('LIGNE_TVA', 'Ligne déclaration TVA'),
        ('ECRITURE', 'Écriture comptable'),
        ('FACTURE', 'Facture'),
        ('REGLEMENT', 'Règlement'),
        ('RAPPORT_AUDIT', 'Rapport d\'audit'),
        ('ALERTE', 'Alerte non-conformité'),
        ('AUTRE', 'Autre'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='historiques_modification')
    
    # Objet modifié
    type_objet = models.CharField(max_length=50, choices=TYPE_OBJET_CHOICES)
    id_objet = models.CharField(max_length=100, help_text='UUID ou ID de l\'objet modifié')
    nom_objet = models.CharField(max_length=255, help_text='Nom/libellé de l\'objet')
    
    # Modification
    action = models.CharField(max_length=20, choices=[
        ('CREATE', 'Création'),
        ('UPDATE', 'Modification'),
        ('DELETE', 'Suppression'),
        ('APPROVE', 'Approbation'),
        ('REJECT', 'Rejet'),
        ('REOPEN', 'Réouverture'),
    ])
    
    # Contenu
    champ_modifie = models.CharField(max_length=100, blank=True, help_text='Champ spécifique modifié')
    valeur_ancienne = models.TextField(blank=True)
    valeur_nouvelle = models.TextField(blank=True)
    description_modification = models.TextField(blank=True)
    
    # Justification
    motif = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True, help_text='Référence: N° ticket, N° demande, etc.')
    
    # Utilisateur
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.PROTECT, related_name='modifications_historique')
    
    # Date
    date_modification = models.DateTimeField(auto_now_add=True)
    
    # Audit
    ip_adresse = models.GenericIPAddressField(null=True, blank=True)
    session_id = models.CharField(max_length=255, blank=True)
    
    class Meta:
        db_table = 'comptabilite_historique_modification'
        verbose_name = 'Historique de modification'
        verbose_name_plural = 'Historiques de modification'
        ordering = ['-date_modification']
        indexes = [
            models.Index(fields=['entreprise', 'type_objet']),
            models.Index(fields=['utilisateur', 'date_modification']),
            models.Index(fields=['id_objet']),
            models.Index(fields=['date_modification']),
        ]
    
    def __str__(self):
        return f"{self.get_action_display()} {self.nom_objet} ({self.date_modification.strftime('%d/%m/%Y %H:%M')})"


# Import des modèles de trésorerie avancée
from .models_tresorerie import (
    SynchronisationBancaire, EcheancierTresorerie, SituationTresorerie,
    OptimisationTresorerie, LiquiditeSouhaitee, GestionNumeraire,
    AlerteTresorerie, FluxTresorerieJournalier
)

# Import des modèles de consolidation
from .models_consolidation import (
    MatriceConsolidation, ConsolidationFiliales, PerimetreConsolidation,
    EliminationIGF, AjustementConsolidation, AffectationResultat,
    VariationCapitaux, NoteExplicative, DocumentationConsolidation,
    BilanConsolide, CompteResultatConsolide, FluxTresorerieConsolide
)

# Import des modèles fiscalité avancée
from .models_fiscalite import (
    DossierFiscalComplet, DeclarationIS, DeclarationCAT,
    DeclarationCVAE, LiasseFiscale, AnnexeFiscale, DocumentationFiscale,
    RobustesseControleFiscal, HistoriqueDeclaration, RegleFiscale
)

# Import des modèles contrôle interne
from .models_controle import (
    MatriceRisques, ProcedureControle, TestControle, NonConformite,
    DelegationPouvoirs, ApprovalMatrix, WorkflowApprobation, EtapeApprobation,
    SegregationTaches, RapportControleInterne, TraceModification
)

# Import des modèles comptabilité analytique
from .models_analytique import (
    CentreCouts, SectionAnalytique, CommandeAnalytique, ImputationAnalytique,
    CleRepartition, TauxRepartition, BudgetAnalytique, AnalyseVariance,
    ReclassementCharge, RepriseCharge, RapportAnalytique, TableauBordAnalytique
)

# Import des modèles gestion comptable des contrats
from .models_contrats_comptables import (
    ContratFournisseur, ContratClient, ConditionsPaiement, ConditionsLivraison,
    PointGaranti, PenaliteRetard, ReclamationContractuelle, SuiviContrat,
    AlerteContrat, HistoriqueContrat
)

# Import des modèles documentation et archivage
from .models_archivage import (
    ClassementDocument, PolitiqueRetention, ArchiveDocument, MatricePiecesJustificatives,
    ValidationDocument, VerificationSignature, FluxDocument, SuppressionDocument,
    TraceAccesDocument, AlerteArchivage, RapportArchivage
)

# Import des modèles livres et documents SYSCOHADA (caisse, bordereaux, emprunts)
from .models_livres import (
    PieceCaisse, BordereauRemise, LigneBordereau, Emprunt, ArreteCaisse,
    ChequeEmis, DeclarationPatente, RegleEcriture,
    RegleValidation, DemandeApprobation, DecisionApprobation
)
