"""
Module Gestion du Stock — Modèles
Gestion des articles, catégories, fournisseurs, mouvements de stock
(entrées / sorties / ajustements) et inventaires physiques.

Tous les modèles sont rattachés à une entreprise (multi-entreprise) sur le
même principe que les modules RH, Comptabilité et Secrétariat.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from core.models import Entreprise, Utilisateur, Service


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
    CATEGORIES = (
        ('strategique', 'Stratégique (A)'),
        ('standard', 'Standard (B)'),
        ('occasionnel', 'Occasionnel (C)'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='fournisseurs_stock')
    nom = models.CharField(max_length=200, verbose_name='Nom / Raison sociale')
    contact = models.CharField(max_length=200, blank=True, verbose_name='Personne de contact')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    email = models.EmailField(blank=True, verbose_name='Email')
    adresse = models.TextField(blank=True, verbose_name='Adresse')
    nif = models.CharField(max_length=50, blank=True, verbose_name='NIF')
    delai_livraison_jours = models.PositiveIntegerField(default=0, verbose_name='Délai moyen de livraison (jours)')
    categorie = models.CharField(max_length=12, choices=CATEGORIES, default='standard',
                                 verbose_name='Classification')
    note_evaluation = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True,
                                          verbose_name="Note d'évaluation (/20)")
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


class Depot(models.Model):
    """Dépôt / magasin / point de stockage (multi-dépôts)."""
    TYPES = (
        ('principal', 'Magasin principal'),
        ('secondaire', 'Dépôt secondaire'),
        ('vehicule', 'Véhicule (stock mobile)'),
        ('boutique', 'Boutique / Point de vente'),
        ('chantier', 'Chantier'),
        ('autre', 'Autre'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='depots')
    nom = models.CharField(max_length=150, verbose_name='Nom du dépôt')
    type_depot = models.CharField(max_length=12, choices=TYPES, default='principal', verbose_name='Type de dépôt')
    code = models.CharField(max_length=20, blank=True, verbose_name='Code')
    adresse = models.CharField(max_length=255, blank=True, verbose_name='Adresse / Localisation')
    responsable = models.CharField(max_length=150, blank=True, verbose_name='Responsable')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    par_defaut = models.BooleanField(default=False, verbose_name='Dépôt par défaut')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_depot'
        verbose_name = 'Dépôt'
        verbose_name_plural = 'Dépôts'
        ordering = ['-par_defaut', 'nom']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'nom'], name='unique_depot_nom_par_entreprise'),
        ]

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
    code_barres = models.CharField(max_length=80, blank=True, verbose_name='Code-barres / QR')
    designation = models.CharField(max_length=255, verbose_name='Désignation')
    categorie = models.ForeignKey(CategorieArticle, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='articles', verbose_name='Catégorie')
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='articles', verbose_name='Fournisseur principal')
    unite = models.CharField(max_length=10, choices=UNITES, default='piece', verbose_name='Unité de mesure')
    prix_achat = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Prix d'achat (GNF)")
    prix_vente = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Prix de vente (GNF)')
    cmup = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                               verbose_name='Coût moyen pondéré (CMUP)')
    quantite_stock = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                         verbose_name='Quantité en stock (tous dépôts)')
    seuil_alerte = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Stock minimum (alerte)")
    stock_max = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Stock maximum (0 = illimité)')
    emplacement = models.CharField(max_length=120, blank=True, verbose_name='Emplacement / Rayon / Étagère')
    photo = models.ImageField(upload_to='stock/articles/', blank=True, null=True, verbose_name='Photo du produit')
    perissable = models.BooleanField(default=False, verbose_name='Produit périssable')
    gestion_lot = models.BooleanField(default=False, verbose_name='Suivi par lot')
    gestion_serie = models.BooleanField(default=False, verbose_name='Suivi par numéro de série')
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
    def cout_unitaire(self):
        """Coût unitaire retenu pour la valorisation : CMUP si disponible, sinon prix d'achat."""
        if self.cmup and self.cmup > 0:
            return self.cmup
        return self.prix_achat or Decimal('0')

    @property
    def valeur_stock(self):
        """Valeur du stock au coût moyen pondéré (CMUP), sinon au prix d'achat."""
        return (self.quantite_stock or Decimal('0')) * self.cout_unitaire

    @property
    def en_rupture(self):
        return (self.quantite_stock or 0) <= 0

    @property
    def en_alerte(self):
        """Stock au seuil ou en dessous (mais pas forcément en rupture)."""
        seuil = self.seuil_alerte or 0
        return seuil > 0 and (self.quantite_stock or 0) <= seuil

    @property
    def en_surstock(self):
        """Stock au-dessus du maximum autorisé."""
        maxi = self.stock_max or 0
        return maxi > 0 and (self.quantite_stock or 0) >= maxi

    def stock_dans(self, depot):
        """Quantité en stock dans un dépôt donné."""
        ligne = self.stocks_depots.filter(depot=depot).first()
        return ligne.quantite if ligne else Decimal('0')

    def recalculer_total(self, sauver=True):
        """Recalcule la quantité globale comme somme des stocks par dépôt."""
        from django.db.models import Sum
        total = self.stocks_depots.aggregate(t=Sum('quantite'))['t'] or Decimal('0')
        self.quantite_stock = total
        if sauver:
            self.save(update_fields=['quantite_stock', 'date_modification'])
        return total


class StockArticleDepot(models.Model):
    """Quantité d'un article dans un dépôt donné (stock par dépôt)."""
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='stocks_depots')
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='stocks_articles')
    quantite = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Quantité')

    class Meta:
        db_table = 'stock_article_depot'
        verbose_name = 'Stock par dépôt'
        verbose_name_plural = 'Stocks par dépôt'
        ordering = ['depot__nom']
        constraints = [
            models.UniqueConstraint(fields=['article', 'depot'], name='unique_article_par_depot'),
        ]

    def __str__(self):
        return f"{self.article.designation} @ {self.depot.nom} : {self.quantite}"


class MouvementStock(models.Model):
    """Mouvement de stock : entrée, sortie ou ajustement d'inventaire."""
    TYPES = (
        ('entree', 'Entrée'),
        ('sortie', 'Sortie'),
        ('ajustement', 'Ajustement'),
        ('transfert', 'Transfert'),
    )
    MOTIFS_SORTIE = (
        ('vente', 'Vente'),
        ('livraison', 'Livraison'),
        ('consommation', 'Consommation interne'),
        ('perte', 'Perte'),
        ('casse', 'Casse'),
        ('vol', 'Vol'),
        ('transfert', 'Transfert vers un autre dépôt'),
        ('autre', 'Autre'),
    )
    MOTIFS_ENTREE = (
        ('achat', 'Achat fournisseur'),
        ('retour_client', 'Retour client'),
        ('production', 'Production interne'),
        ('regularisation', 'Régularisation positive'),
        ('transfert', 'Transfert depuis un autre dépôt'),
        ('autre', 'Autre'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='mouvements_stock')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='mouvements')
    depot = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='mouvements', verbose_name='Dépôt')
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


class Transfert(models.Model):
    """Transfert de stock d'un dépôt vers un autre."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='transferts')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='transferts')
    depot_source = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='transferts_sortants',
                                     verbose_name='Dépôt source')
    depot_destination = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='transferts_entrants',
                                          verbose_name='Dépôt destination')
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité')
    motif = models.CharField(max_length=255, blank=True, verbose_name='Motif')
    date_transfert = models.DateTimeField(default=timezone.now, verbose_name='Date du transfert')
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='transferts_crees')

    class Meta:
        db_table = 'stock_transfert'
        verbose_name = 'Transfert'
        verbose_name_plural = 'Transferts'
        ordering = ['-date_transfert', '-id']

    def __str__(self):
        return f"{self.reference} : {self.article.designation} {self.depot_source} → {self.depot_destination}"


class Inventaire(models.Model):
    """Inventaire physique : comparaison stock théorique / stock physique."""
    STATUTS = (
        ('en_cours', 'En cours'),
        ('valide', 'Validé'),
        ('annule', 'Annulé'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='inventaires_stock')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    depot = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='inventaires', verbose_name='Dépôt inventorié')
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


# ===========================================================================
# ACHATS — Commandes fournisseurs, réceptions, factures, paiements
# ===========================================================================
class CommandeFournisseur(models.Model):
    """Demande d'achat / bon de commande fournisseur."""
    STATUTS = (
        ('brouillon', "Demande d'achat"),
        ('validee', 'Bon de commande validé'),
        ('partiellement_recue', 'Partiellement reçue'),
        ('recue', 'Réception complète'),
        ('annulee', 'Annulée'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='commandes_fournisseur')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name='commandes')
    depot = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='commandes_recues', verbose_name='Dépôt de réception')
    date_commande = models.DateField(default=timezone.now, verbose_name='Date')
    date_livraison_prevue = models.DateField(null=True, blank=True, verbose_name='Livraison prévue le')
    statut = models.CharField(max_length=22, choices=STATUTS, default='brouillon')
    notes = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes_creees')
    validee_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes_validees')
    date_validation = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'stock_commande_fournisseur'
        verbose_name = 'Commande fournisseur'
        verbose_name_plural = 'Commandes fournisseur'
        ordering = ['-date_commande', '-id']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'reference'], name='unique_commande_reference_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.reference} - {self.fournisseur.nom}"

    @property
    def montant_total(self):
        return sum((l.montant for l in self.lignes.all()), Decimal('0'))

    @property
    def modifiable(self):
        return self.statut in ('brouillon', 'validee')

    @property
    def receptionnable(self):
        return self.statut in ('validee', 'partiellement_recue')


class LigneCommande(models.Model):
    """Ligne d'une commande fournisseur."""
    commande = models.ForeignKey(CommandeFournisseur, on_delete=models.CASCADE, related_name='lignes')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='lignes_commande')
    quantite_commandee = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité commandée')
    quantite_recue = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Quantité reçue')
    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Prix unitaire (GNF)')

    class Meta:
        db_table = 'stock_ligne_commande'
        verbose_name = 'Ligne de commande'
        verbose_name_plural = 'Lignes de commande'
        ordering = ['id']

    def __str__(self):
        return f"{self.article.designation} x {self.quantite_commandee}"

    @property
    def montant(self):
        return (self.quantite_commandee or Decimal('0')) * (self.prix_unitaire or Decimal('0'))

    @property
    def reste_a_recevoir(self):
        return (self.quantite_commandee or Decimal('0')) - (self.quantite_recue or Decimal('0'))


class BesoinAchat(models.Model):
    """Expression de besoin d'achat : un employé signale un besoin, avant tout
    choix de fournisseur. Une fois validée, elle alimente l'écran de
    réapprovisionnement pour générer automatiquement le(s) bon(s) de commande."""
    URGENCES = (
        ('normale', 'Normale'),
        ('urgente', 'Urgente'),
        ('critique', 'Critique'),
    )
    STATUTS = (
        ('soumise', 'Soumise'),
        ('validee', 'Validée'),
        ('rejetee', 'Rejetée'),
        ('traitee', 'Traitée (commande générée)'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='besoins_achat')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    demandeur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='besoins_achat_exprimes', verbose_name='Demandeur')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='besoins_achat', verbose_name='Service demandeur')
    motif = models.TextField(blank=True, verbose_name='Motif / Justification')
    urgence = models.CharField(max_length=10, choices=URGENCES, default='normale')
    date_besoin_souhaitee = models.DateField(null=True, blank=True, verbose_name='Besoin pour le')
    statut = models.CharField(max_length=10, choices=STATUTS, default='soumise')
    commentaire_validation = models.TextField(blank=True, verbose_name='Commentaire du valideur')
    valide_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='besoins_achat_valides')
    date_validation = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_besoin_achat'
        verbose_name = 'Expression de besoin (achat)'
        verbose_name_plural = 'Expressions de besoin (achat)'
        ordering = ['-date_creation', '-id']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'reference'], name='unique_besoin_achat_reference_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.reference} - {self.demandeur or ''}"

    @property
    def modifiable(self):
        return self.statut == 'soumise'

    @property
    def traite(self):
        return self.statut == 'traitee' or (
            self.lignes.exists() and not self.lignes.filter(ligne_commande__isnull=True).exists()
        )


class LigneBesoinAchat(models.Model):
    """Ligne d'une expression de besoin : un article existant + quantité."""
    besoin = models.ForeignKey(BesoinAchat, on_delete=models.CASCADE, related_name='lignes')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='lignes_besoin_achat')
    quantite_demandee = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité demandée')
    ligne_commande = models.ForeignKey(LigneCommande, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='lignes_besoin_couvertes',
                                       verbose_name='Ligne de commande générée')

    class Meta:
        db_table = 'stock_ligne_besoin_achat'
        verbose_name = "Ligne d'expression de besoin"
        verbose_name_plural = "Lignes d'expression de besoin"
        ordering = ['id']

    def __str__(self):
        return f"{self.article.designation} x {self.quantite_demandee}"


class Reception(models.Model):
    """Réception (totale ou partielle) d'une commande fournisseur."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='receptions_fournisseur')
    commande = models.ForeignKey(CommandeFournisseur, on_delete=models.CASCADE, related_name='receptions')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    depot = models.ForeignKey(Depot, on_delete=models.PROTECT, related_name='receptions', verbose_name='Dépôt')
    date_reception = models.DateField(default=timezone.now, verbose_name='Date de réception')
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='receptions_creees')

    class Meta:
        db_table = 'stock_reception'
        verbose_name = 'Réception'
        verbose_name_plural = 'Réceptions'
        ordering = ['-date_reception', '-id']

    def __str__(self):
        return f"{self.reference} ({self.commande.reference})"


class LigneReception(models.Model):
    """Quantité reçue pour une ligne de commande lors d'une réception."""
    reception = models.ForeignKey(Reception, on_delete=models.CASCADE, related_name='lignes')
    ligne_commande = models.ForeignKey(LigneCommande, on_delete=models.CASCADE, related_name='receptions')
    quantite_recue = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité reçue')

    class Meta:
        db_table = 'stock_ligne_reception'
        verbose_name = 'Ligne de réception'
        verbose_name_plural = 'Lignes de réception'
        ordering = ['id']

    def __str__(self):
        return f"{self.ligne_commande.article.designation} : {self.quantite_recue}"


class FactureFournisseur(models.Model):
    """Facture reçue d'un fournisseur (suivi des dettes)."""
    STATUTS = (
        ('impayee', 'Impayée'),
        ('partielle', 'Partiellement payée'),
        ('payee', 'Payée'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='factures_fournisseur')
    numero = models.CharField(max_length=60, verbose_name='N° de facture fournisseur')
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name='factures')
    commande = models.ForeignKey(CommandeFournisseur, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='factures', verbose_name='Commande liée')
    date_facture = models.DateField(default=timezone.now, verbose_name='Date de facture')
    date_echeance = models.DateField(null=True, blank=True, verbose_name="Date d'échéance")
    montant_ht = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='Montant HT (GNF)')
    taux_tva = models.DecimalField(
        max_digits=5, decimal_places=2, default=18, verbose_name='Taux TVA (%)',
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    montant_paye = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='Montant payé (GNF)')
    statut = models.CharField(max_length=10, choices=STATUTS, default='impayee')
    notes = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='factures_fournisseur_creees')

    class Meta:
        db_table = 'stock_facture_fournisseur'
        verbose_name = 'Facture fournisseur'
        verbose_name_plural = 'Factures fournisseur'
        ordering = ['-date_facture', '-id']

    def __str__(self):
        return f"{self.numero} - {self.fournisseur.nom}"

    @property
    def montant_tva(self):
        return ((self.montant_ht or Decimal('0')) * (self.taux_tva or Decimal('0')) / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def montant_ttc(self):
        return (self.montant_ht or Decimal('0')) + self.montant_tva

    @property
    def montant_du(self):
        return self.montant_ttc - (self.montant_paye or Decimal('0'))

    def maj_statut(self, sauver=True):
        du = self.montant_du
        if (self.montant_paye or 0) <= 0:
            self.statut = 'impayee'
        elif du <= 0:
            self.statut = 'payee'
        else:
            self.statut = 'partielle'
        if sauver:
            self.save(update_fields=['statut'])


class PaiementFournisseur(models.Model):
    """Paiement d'une facture fournisseur."""
    MODES = (
        ('especes', 'Espèces'),
        ('virement', 'Virement'),
        ('cheque', 'Chèque'),
        ('mobile_money', 'Mobile Money'),
        ('autre', 'Autre'),
    )

    facture = models.ForeignKey(FactureFournisseur, on_delete=models.CASCADE, related_name='paiements')
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name='Montant (GNF)')
    date_paiement = models.DateField(default=timezone.now, verbose_name='Date du paiement')
    mode = models.CharField(max_length=15, choices=MODES, default='especes', verbose_name='Mode de paiement')
    reference = models.CharField(max_length=80, blank=True, verbose_name='Référence')
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements_fournisseur_crees')

    class Meta:
        db_table = 'stock_paiement_fournisseur'
        verbose_name = 'Paiement fournisseur'
        verbose_name_plural = 'Paiements fournisseur'
        ordering = ['-date_paiement', '-id']

    def __str__(self):
        return f"{self.montant} ({self.get_mode_display()})"


# ===========================================================================
# RÔLES & TRAÇABILITÉ
# ===========================================================================
class ProfilStock(models.Model):
    """Rôle d'un utilisateur dans le module Stock (contrôle d'accès)."""
    ROLES = (
        ('administrateur', 'Administrateur'),
        ('directeur', 'Directeur'),
        ('magasinier', 'Magasinier'),
        ('responsable_achat', "Responsable achat"),
        ('comptable', 'Comptable'),
        ('auditeur', 'Auditeur (lecture seule)'),
    )

    utilisateur = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name='profil_stock')
    role = models.CharField(max_length=20, choices=ROLES, default='administrateur')
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_profil'
        verbose_name = 'Rôle Stock'
        verbose_name_plural = 'Rôles Stock'

    def __str__(self):
        return f"{self.utilisateur} - {self.get_role_display()}"


class JournalAudit(models.Model):
    """Journal d'audit : trace chaque action sur les données du module."""
    ACTIONS = (
        ('creation', 'Création'),
        ('modification', 'Modification'),
        ('suppression', 'Suppression'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, null=True, blank=True,
                                   related_name='journaux_stock')
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='actions_stock')
    date_heure = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=15, choices=ACTIONS)
    objet_type = models.CharField(max_length=60, verbose_name="Type d'objet")
    objet_id = models.CharField(max_length=40, blank=True)
    objet_libelle = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)

    class Meta:
        db_table = 'stock_journal_audit'
        verbose_name = "Entrée du journal d'audit"
        verbose_name_plural = "Journal d'audit"
        ordering = ['-date_heure', '-id']
        indexes = [
            models.Index(fields=['entreprise', '-date_heure']),
        ]

    def __str__(self):
        return f"{self.date_heure:%d/%m/%Y %H:%M} - {self.get_action_display()} {self.objet_type}"


# ===========================================================================
# VENTES — Clients, devis/factures, bons de livraison, paiements
# ===========================================================================
class Client(models.Model):
    """Client de l'entreprise."""
    TYPES = (
        ('particulier', 'Particulier'),
        ('entreprise', 'Entreprise'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='clients')
    nom = models.CharField(max_length=200, verbose_name='Nom / Raison sociale')
    type_client = models.CharField(max_length=12, choices=TYPES, default='particulier', verbose_name='Type')
    contact = models.CharField(max_length=200, blank=True, verbose_name='Personne de contact')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    email = models.EmailField(blank=True, verbose_name='Email')
    adresse = models.TextField(blank=True, verbose_name='Adresse')
    nif = models.CharField(max_length=50, blank=True, verbose_name='NIF')
    remise_defaut = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name='Remise habituelle (%)',
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    actif = models.BooleanField(default=True)
    observations = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_client'
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class PrixSpecialClient(models.Model):
    """Prix spécial négocié pour un client sur un article donné."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='prix_speciaux')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='prix_speciaux')
    prix = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Prix spécial (GNF)')

    class Meta:
        db_table = 'stock_prix_special_client'
        verbose_name = 'Prix spécial client'
        verbose_name_plural = 'Prix spéciaux client'
        ordering = ['article__designation']
        constraints = [
            models.UniqueConstraint(fields=['client', 'article'], name='unique_prix_special_client_article'),
        ]

    def __str__(self):
        return f"{self.client.nom} - {self.article.designation} : {self.prix}"


class DemandeVente(models.Model):
    """Expression de besoin côté client : un commercial saisit ce que le client
    souhaite. Une fois validée, un devis (DocumentVente) est généré
    automatiquement avec les informations client et les prix pré-remplis."""
    STATUTS = (
        ('soumise', 'Soumise'),
        ('validee', 'Validée'),
        ('rejetee', 'Rejetée'),
        ('convertie', 'Convertie en devis'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='demandes_vente')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='demandes_vente')
    demandeur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='demandes_vente_creees', verbose_name='Saisie par')
    date_besoin = models.DateField(default=timezone.now, verbose_name='Date du besoin')
    notes = models.TextField(blank=True)
    statut = models.CharField(max_length=10, choices=STATUTS, default='soumise')
    commentaire_validation = models.TextField(blank=True, verbose_name='Commentaire du valideur')
    valide_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='demandes_vente_validees')
    date_validation = models.DateTimeField(null=True, blank=True)
    document_genere = models.ForeignKey('DocumentVente', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='demande_origine', verbose_name='Devis généré')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_demande_vente'
        verbose_name = 'Expression de besoin (vente)'
        verbose_name_plural = 'Expressions de besoin (vente)'
        ordering = ['-date_creation', '-id']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'reference'], name='unique_demande_vente_reference_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.nom}"

    @property
    def modifiable(self):
        return self.statut == 'soumise'


class LigneDemandeVente(models.Model):
    """Ligne d'une demande de vente : un article existant + quantité souhaitée."""
    demande = models.ForeignKey(DemandeVente, on_delete=models.CASCADE, related_name='lignes')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='lignes_demande_vente')
    quantite_souhaitee = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité souhaitée')
    prix_indicatif = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                         verbose_name='Prix indicatif (GNF)')

    class Meta:
        db_table = 'stock_ligne_demande_vente'
        verbose_name = 'Ligne de demande de vente'
        verbose_name_plural = 'Lignes de demande de vente'
        ordering = ['id']

    def __str__(self):
        return f"{self.article.designation} x {self.quantite_souhaitee}"


class DocumentVente(models.Model):
    """Document de vente : devis, facture proforma ou facture."""
    TYPES = (
        ('devis', 'Devis'),
        ('proforma', 'Facture proforma'),
        ('facture', 'Facture'),
    )
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('envoye', 'Envoyé'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé'),
        ('converti', 'Converti en facture'),
        ('emise', 'Émise'),
        ('partielle', 'Partiellement payée'),
        ('payee', 'Payée'),
        ('annulee', 'Annulée'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='documents_vente')
    type_document = models.CharField(max_length=10, choices=TYPES, default='devis', verbose_name='Type')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='documents')
    depot = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='documents_vente', verbose_name='Dépôt de livraison')
    date_document = models.DateField(default=timezone.now, verbose_name='Date')
    date_echeance = models.DateField(null=True, blank=True, verbose_name="Validité / Échéance")
    remise_globale_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name='Remise globale (%)',
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    taux_tva = models.DecimalField(
        max_digits=5, decimal_places=2, default=18, verbose_name='Taux TVA (%)',
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    statut = models.CharField(max_length=10, choices=STATUTS, default='brouillon')
    montant_paye = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='Montant encaissé (GNF)')
    notes = models.TextField(blank=True)
    converti_depuis = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='conversions', verbose_name='Converti depuis')
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents_vente_crees')

    class Meta:
        db_table = 'stock_document_vente'
        verbose_name = 'Document de vente'
        verbose_name_plural = 'Documents de vente'
        ordering = ['-date_document', '-id']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'reference'], name='unique_vente_reference_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.nom}"

    @property
    def total_ht(self):
        brut = sum((l.montant for l in self.lignes.all()), Decimal('0'))
        return (brut * (Decimal('1') - (self.remise_globale_pct or Decimal('0')) / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def montant_tva(self):
        return (self.total_ht * (self.taux_tva or Decimal('0')) / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def montant_ttc(self):
        return (self.total_ht + self.montant_tva).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def montant_du(self):
        return self.montant_ttc - (self.montant_paye or Decimal('0'))

    @property
    def est_facture(self):
        return self.type_document == 'facture'

    @property
    def modifiable(self):
        if self.est_facture:
            return (self.montant_paye or 0) <= 0 and not self.livraisons.exists() and self.statut != 'annulee'
        return self.statut in ('brouillon', 'envoye')

    def maj_statut_paiement(self, sauver=True):
        """Met à jour le statut d'une facture selon les encaissements."""
        if not self.est_facture:
            return
        du = self.montant_du
        if (self.montant_paye or 0) <= 0:
            self.statut = 'emise'
        elif du <= 0:
            self.statut = 'payee'
        else:
            self.statut = 'partielle'
        if sauver:
            self.save(update_fields=['statut'])


class LigneVente(models.Model):
    """Ligne d'un document de vente."""
    document = models.ForeignKey(DocumentVente, on_delete=models.CASCADE, related_name='lignes')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='lignes_vente')
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité')
    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Prix unitaire (GNF)')
    remise_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name='Remise (%)',
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    quantite_livree = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Quantité livrée')

    class Meta:
        db_table = 'stock_ligne_vente'
        verbose_name = 'Ligne de vente'
        verbose_name_plural = 'Lignes de vente'
        ordering = ['id']

    def __str__(self):
        return f"{self.article.designation} x {self.quantite}"

    @property
    def montant(self):
        return ((self.quantite or Decimal('0')) * (self.prix_unitaire or Decimal('0'))
                * (Decimal('1') - (self.remise_pct or Decimal('0')) / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def reste_a_livrer(self):
        return (self.quantite or Decimal('0')) - (self.quantite_livree or Decimal('0'))


class BonLivraison(models.Model):
    """Bon de livraison : sortie de stock vers le client."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='bons_livraison')
    document = models.ForeignKey(DocumentVente, on_delete=models.CASCADE, related_name='livraisons')
    reference = models.CharField(max_length=40, verbose_name='Référence')
    depot = models.ForeignKey(Depot, on_delete=models.PROTECT, related_name='livraisons', verbose_name='Dépôt')
    date_livraison = models.DateField(default=timezone.now, verbose_name='Date de livraison')
    adresse_livraison = models.CharField(max_length=255, blank=True, verbose_name='Adresse de livraison')
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='livraisons_creees')

    class Meta:
        db_table = 'stock_bon_livraison'
        verbose_name = 'Bon de livraison'
        verbose_name_plural = 'Bons de livraison'
        ordering = ['-date_livraison', '-id']

    def __str__(self):
        return f"{self.reference} ({self.document.reference})"


class LigneLivraison(models.Model):
    """Quantité livrée pour une ligne de vente."""
    livraison = models.ForeignKey(BonLivraison, on_delete=models.CASCADE, related_name='lignes')
    ligne_vente = models.ForeignKey(LigneVente, on_delete=models.CASCADE, related_name='livraisons')
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Quantité livrée')

    class Meta:
        db_table = 'stock_ligne_livraison'
        verbose_name = 'Ligne de livraison'
        verbose_name_plural = 'Lignes de livraison'
        ordering = ['id']

    def __str__(self):
        return f"{self.ligne_vente.article.designation} : {self.quantite}"


class PaiementClient(models.Model):
    """Encaissement (reçu) sur une facture client."""
    MODES = (
        ('especes', 'Espèces'),
        ('virement', 'Virement'),
        ('cheque', 'Chèque'),
        ('mobile_money', 'Mobile Money'),
        ('autre', 'Autre'),
    )

    document = models.ForeignKey(DocumentVente, on_delete=models.CASCADE, related_name='paiements')
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name='Montant (GNF)')
    date_paiement = models.DateField(default=timezone.now, verbose_name='Date du paiement')
    mode = models.CharField(max_length=15, choices=MODES, default='especes', verbose_name='Mode de paiement')
    reference = models.CharField(max_length=80, blank=True, verbose_name='Référence du reçu')
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements_client_crees')

    class Meta:
        db_table = 'stock_paiement_client'
        verbose_name = 'Paiement client'
        verbose_name_plural = 'Paiements client'
        ordering = ['-date_paiement', '-id']

    def __str__(self):
        return f"{self.montant} ({self.get_mode_display()})"


# ===========================================================================
# LOTS, NUMÉROS DE SÉRIE & PÉREMPTION
# ===========================================================================
class Lot(models.Model):
    """Lot de fabrication d'un article (traçabilité, péremption)."""
    SEUIL_PROCHE_JOURS = 30

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='lots')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='lots')
    numero_lot = models.CharField(max_length=80, verbose_name='Numéro de lot')
    depot = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='lots', verbose_name='Dépôt')
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='lots', verbose_name='Fournisseur')
    date_entree = models.DateField(default=timezone.now, verbose_name="Date d'entrée")
    date_peremption = models.DateField(null=True, blank=True, verbose_name='Date de péremption')
    quantite = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Quantité initiale')
    quantite_restante = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Quantité restante')
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'stock_lot'
        verbose_name = 'Lot'
        verbose_name_plural = 'Lots'
        ordering = ['date_peremption', 'numero_lot']
        constraints = [
            models.UniqueConstraint(fields=['article', 'numero_lot'], name='unique_lot_par_article'),
        ]

    def __str__(self):
        return f"{self.numero_lot} - {self.article.designation}"

    @property
    def jours_avant_peremption(self):
        if not self.date_peremption:
            return None
        return (self.date_peremption - timezone.now().date()).days

    @property
    def est_perime(self):
        j = self.jours_avant_peremption
        return j is not None and j < 0

    @property
    def proche_peremption(self):
        j = self.jours_avant_peremption
        return j is not None and 0 <= j <= self.SEUIL_PROCHE_JOURS


class NumeroSerie(models.Model):
    """Numéro de série d'une unité d'article (suivi unitaire)."""
    STATUTS = (
        ('en_stock', 'En stock'),
        ('vendu', 'Vendu'),
        ('retire', 'Retiré / SAV'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='numeros_serie')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='numeros_serie')
    numero_serie = models.CharField(max_length=120, verbose_name='Numéro de série')
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name='numeros_serie')
    depot = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='numeros_serie', verbose_name='Dépôt')
    statut = models.CharField(max_length=10, choices=STATUTS, default='en_stock')
    date_entree = models.DateField(default=timezone.now, verbose_name="Date d'entrée")
    date_sortie = models.DateField(null=True, blank=True, verbose_name='Date de sortie')
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'stock_numero_serie'
        verbose_name = 'Numéro de série'
        verbose_name_plural = 'Numéros de série'
        ordering = ['article__designation', 'numero_serie']
        constraints = [
            models.UniqueConstraint(fields=['article', 'numero_serie'], name='unique_serie_par_article'),
        ]

    def __str__(self):
        return f"{self.numero_serie} ({self.article.designation})"
