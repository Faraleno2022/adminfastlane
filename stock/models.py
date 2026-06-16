"""
Module Gestion du Stock — Modèles
Gestion des articles, catégories, fournisseurs, mouvements de stock
(entrées / sorties / ajustements) et inventaires physiques.

Tous les modèles sont rattachés à une entreprise (multi-entreprise) sur le
même principe que les modules RH, Comptabilité et Secrétariat.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import Entreprise, Utilisateur


class CategorieArticle(models.Model):
    """Catégorie / famille d'articles."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='categories_articles')
    nom = models.CharField(max_length=120, verbose_name='Nom de la catégorie')
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_categorie'
        verbose_name = 'Catégorie'
        verbose_name_plural = 'Catégories'
        ordering = ['nom']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'nom'], name='unique_categorie_nom_par_entreprise'),
        ]

    def __str__(self):
        return self.nom


class Fournisseur(models.Model):
    """Fournisseur d'articles."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='fournisseurs_stock')
    nom = models.CharField(max_length=200, verbose_name='Nom / Raison sociale')
    contact = models.CharField(max_length=200, blank=True, verbose_name='Personne de contact')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    email = models.EmailField(blank=True, verbose_name='Email')
    adresse = models.TextField(blank=True, verbose_name='Adresse')
    nif = models.CharField(max_length=50, blank=True, verbose_name='NIF')
    actif = models.BooleanField(default=True)
    observations = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_fournisseur'
        verbose_name = 'Fournisseur'
        verbose_name_plural = 'Fournisseurs'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Article(models.Model):
    """Article / produit suivi en stock."""
    UNITES = (
        ('piece', 'Pièce'),
        ('kg', 'Kilogramme'),
        ('g', 'Gramme'),
        ('litre', 'Litre'),
        ('metre', 'Mètre'),
        ('carton', 'Carton'),
        ('paquet', 'Paquet'),
        ('sac', 'Sac'),
        ('lot', 'Lot'),
        ('autre', 'Autre'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='articles')
    reference = models.CharField(max_length=50, verbose_name='Référence / Code')
    designation = models.CharField(max_length=255, verbose_name='Désignation')
    categorie = models.ForeignKey(CategorieArticle, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='articles', verbose_name='Catégorie')
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='articles', verbose_name='Fournisseur principal')
    unite = models.CharField(max_length=10, choices=UNITES, default='piece', verbose_name='Unité de mesure')
    prix_achat = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Prix d'achat (GNF)")
    prix_vente = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Prix de vente (GNF)')
    quantite_stock = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Quantité en stock')
    seuil_alerte = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Seuil d'alerte")
    emplacement = models.CharField(max_length=120, blank=True, verbose_name='Emplacement / Magasin')
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles_crees')

    class Meta:
        db_table = 'stock_article'
        verbose_name = 'Article'
        verbose_name_plural = 'Articles'
        ordering = ['designation']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'reference'], name='unique_article_reference_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.reference} - {self.designation}"

    @property
    def valeur_stock(self):
        """Valeur du stock au prix d'achat."""
        return (self.quantite_stock or Decimal('0')) * (self.prix_achat or Decimal('0'))

    @property
    def en_rupture(self):
        return (self.quantite_stock or 0) <= 0

    @property
    def en_alerte(self):
        """Stock au seuil ou en dessous (mais pas forcément en rupture)."""
        seuil = self.seuil_alerte or 0
        return seuil > 0 and (self.quantite_stock or 0) <= seuil


class MouvementStock(models.Model):
    """Mouvement de stock : entrée, sortie ou ajustement d'inventaire."""
    TYPES = (
        ('entree', 'Entrée'),
        ('sortie', 'Sortie'),
        ('ajustement', 'Ajustement'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='mouvements_stock')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='mouvements')
    type_mouvement = models.CharField(max_length=12, choices=TYPES, default='entree', verbose_name='Type de mouvement')
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité')
    quantite_avant = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Stock avant')
    quantite_apres = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Stock après')
    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Prix unitaire (GNF)')
    motif = models.CharField(max_length=255, blank=True, verbose_name='Motif / Justification')
    reference_document = models.CharField(max_length=80, blank=True, verbose_name='Réf. document (BL, facture...)')
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='mouvements', verbose_name='Fournisseur')
    date_mouvement = models.DateTimeField(default=timezone.now, verbose_name='Date du mouvement')
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='mouvements_crees')

    class Meta:
        db_table = 'stock_mouvement'
        verbose_name = 'Mouvement de stock'
        verbose_name_plural = 'Mouvements de stock'
        ordering = ['-date_mouvement', '-id']

    def __str__(self):
        return f"{self.get_type_mouvement_display()} - {self.article.designation} ({self.quantite})"

    @property
    def valeur(self):
        return (self.quantite or Decimal('0')) * (self.prix_unitaire or Decimal('0'))


class Inventaire(models.Model):
    """Inventaire physique : comparaison stock théorique / stock physique."""
    STATUTS = (
        ('en_cours', 'En cours'),
        ('valide', 'Validé'),
        ('annule', 'Annulé'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='inventaires_stock')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    date_inventaire = models.DateField(default=timezone.now, verbose_name="Date de l'inventaire")
    statut = models.CharField(max_length=10, choices=STATUTS, default='en_cours')
    commentaire = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventaires_crees')

    class Meta:
        db_table = 'stock_inventaire'
        verbose_name = 'Inventaire'
        verbose_name_plural = 'Inventaires'
        ordering = ['-date_inventaire', '-id']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'reference'], name='unique_inventaire_reference_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.reference} ({self.date_inventaire:%d/%m/%Y})"

    @property
    def nb_ecarts(self):
        return self.lignes.exclude(ecart=0).count()


class LigneInventaire(models.Model):
    """Ligne d'inventaire : un article compté."""
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='lignes_inventaire')
    quantite_theorique = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Stock théorique')
    quantite_physique = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Stock physique compté')
    ecart = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Écart')

    class Meta:
        db_table = 'stock_ligne_inventaire'
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"
        ordering = ['article__designation']
        constraints = [
            models.UniqueConstraint(fields=['inventaire', 'article'], name='unique_article_par_inventaire'),
        ]

    def __str__(self):
        return f"{self.article.designation} : {self.quantite_physique}"

    def save(self, *args, **kwargs):
        self.ecart = (self.quantite_physique or 0) - (self.quantite_theorique or 0)
        super().save(*args, **kwargs)
