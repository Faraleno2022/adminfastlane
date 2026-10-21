"""Modèles du module Gestion de flotte.

Toutes les entités portent une clé UUID, une suppression logique (aucune
donnée n'est effacée physiquement) et un rattachement à l'entreprise :
les managers n'exposent que les données de l'entreprise courante (voir
``scope``).
"""
import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .scope import NON_DEFINIE, entreprise_courante
from .storage import documents_storage


# --------------------------------------------------------------------------
# Base commune
# --------------------------------------------------------------------------
class FlotteQuerySet(models.QuerySet):
    def actifs(self):
        """Enregistrements non supprimés."""
        return self.filter(is_deleted=False)


class FlotteManager(models.Manager.from_queryset(FlotteQuerySet)):
    """Filtre sur l'entreprise courante et masque les suppressions logiques."""

    def __init__(self, *args, inclure_supprimes=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.inclure_supprimes = inclure_supprimes

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.inclure_supprimes:
            qs = qs.filter(is_deleted=False)
        entreprise = entreprise_courante()
        if entreprise is NON_DEFINIE:
            return qs
        if entreprise is None:
            return qs.none()
        return qs.filter(entreprise=entreprise)


class FlotteModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entreprise = models.ForeignKey(
        "core.Entreprise", on_delete=models.CASCADE, editable=False, related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = FlotteManager()
    all_objects = FlotteManager(inclure_supprimes=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.entreprise_id is None:
            entreprise = entreprise_courante()
            if not entreprise:
                raise ValueError("Entreprise requise pour enregistrer un objet de la flotte.")
            self.entreprise = entreprise
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Suppression logique."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.updated_at = timezone.now()
        super().save(using=using)

    def hard_delete(self, using=None, keep_parents=False):
        """Suppression physique (maintenance uniquement)."""
        super().delete(using=using, keep_parents=keep_parents)


# --------------------------------------------------------------------------
# Référentiel
# --------------------------------------------------------------------------
class CategorieRoues(FlotteModel):
    """Catégorie de véhicule par nombre de roues (6 roues, 10 roues, …)."""

    libelle = models.CharField("Libellé", max_length=50)

    class Meta:
        verbose_name = "Catégorie de roues"
        verbose_name_plural = "Catégories de roues"
        ordering = ["libelle"]
        unique_together = [("entreprise", "libelle")]

    def __str__(self):
        return self.libelle


class Marque(FlotteModel):
    """Marque de véhicule (HOWO, SHACMAN, FOTON, SHANTUI, …)."""

    nom = models.CharField("Marque", max_length=60)

    class Meta:
        verbose_name = "Marque"
        verbose_name_plural = "Marques"
        ordering = ["nom"]
        unique_together = [("entreprise", "nom")]

    def __str__(self):
        return self.nom


class Chauffeur(FlotteModel):
    nom_prenoms = models.CharField("Prénoms et Noms", max_length=120)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Chauffeur"
        verbose_name_plural = "Chauffeurs"
        ordering = ["nom_prenoms"]

    def __str__(self):
        return self.nom_prenoms


class Vehicule(FlotteModel):
    CAPACITE_CHOICES = [(t, f"{t} tonnes") for t in range(10, 101, 5)]

    immatriculation = models.CharField("Immatriculation", max_length=30)
    marque = models.ForeignKey(
        Marque, verbose_name="Marque", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="vehicules",
    )
    # Ancien classement par nombre de roues : conservé en base mais remplacé
    # par la marque dans l'interface.
    categorie_roues = models.ForeignKey(
        CategorieRoues, verbose_name="Catégorie de roues", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="vehicules",
    )
    chauffeur_actuel = models.ForeignKey(
        Chauffeur, verbose_name="Chauffeur principal", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="vehicules",
    )
    chauffeur_secondaire = models.ForeignKey(
        Chauffeur, verbose_name="Second chauffeur", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="vehicules_secondaire",
    )
    type_vehicule = models.CharField("Type", max_length=60, blank=True)
    capacite_tonnes = models.PositiveSmallIntegerField(
        "Capacité", choices=CAPACITE_CHOICES, null=True, blank=True
    )
    numero_chassis = models.CharField("N° de châssis", max_length=50, blank=True)
    actif = models.BooleanField("En service", default=True)

    class Meta:
        verbose_name = "Véhicule"
        verbose_name_plural = "Véhicules"
        ordering = ["immatriculation"]

    def __str__(self):
        return self.immatriculation

    @property
    def chauffeurs(self):
        """Chauffeur principal puis second chauffeur (ceux renseignés)."""
        return [c for c in (self.chauffeur_actuel, self.chauffeur_secondaire) if c]

    def noms_chauffeurs(self):
        return " / ".join(c.nom_prenoms for c in self.chauffeurs)

    def etat_documents(self):
        """Badges résumant l'état des documents (pour la liste des véhicules)."""
        docs = list(self.documents.all())
        if not docs:
            return format_html('<span class="text-muted small">{}</span>', "Aucun")
        expires = sum(1 for d in docs if d.statut == DocumentVehicule.EXPIRE)
        bientot = sum(1 for d in docs if d.statut == DocumentVehicule.BIENTOT)
        badges = []
        if expires:
            badges.append(("bg-danger", f"{expires} expiré(s)"))
        if bientot:
            badges.append(("bg-warning text-dark", f"{bientot} à renouveler"))
        if not badges:
            badges.append(("bg-success", f"{len(docs)} à jour"))
        return format_html_join(" ", '<span class="badge {}">{}</span>', badges)


def chemin_document(instance, filename):
    """Range les pièces jointes par entreprise puis par véhicule."""
    return (
        f"documents_vehicules/{instance.entreprise_id}/{instance.vehicule_id}/"
        f"{instance.type_document}_{filename}"
    )


class DocumentVehicule(FlotteModel):
    """Document administratif d'un véhicule (carte grise, assurance, …)."""

    TYPE_CHOICES = [
        ("carte_grise", "Carte grise"),
        ("assurance", "Assurance"),
        ("visite_technique", "Visite technique"),
        ("autorisation_transport", "Autorisation de transport"),
        ("vignette", "Vignette / Taxe"),
        ("autre", "Autre"),
    ]
    EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp"]

    # Statuts calculés à partir de la date d'expiration.
    EXPIRE = "expire"
    BIENTOT = "bientot"
    VALIDE = "valide"
    SANS_ECHEANCE = "sans_echeance"

    vehicule = models.ForeignKey(
        Vehicule, verbose_name="Véhicule", on_delete=models.CASCADE,
        related_name="documents",
    )
    type_document = models.CharField("Type de document", max_length=30, choices=TYPE_CHOICES)
    numero = models.CharField("N° du document", max_length=60, blank=True)
    date_emission = models.DateField("Date de délivrance", null=True, blank=True)
    date_expiration = models.DateField(
        "Date d'expiration", null=True, blank=True,
        help_text="Laisser vide si le document n'expire pas (ex. carte grise).",
    )
    fichier = models.FileField(
        "Fichier (PDF ou photo)", upload_to=chemin_document, storage=documents_storage, max_length=255, blank=True,
        validators=[FileExtensionValidator(EXTENSIONS)],
    )
    observations = models.CharField("Observations", max_length=200, blank=True)

    class Meta:
        verbose_name = "Document véhicule"
        verbose_name_plural = "Documents véhicules"
        ordering = ["date_expiration", "type_document"]

    def __str__(self):
        return f"{self.get_type_document_display()} — {self.vehicule}"

    @staticmethod
    def delai_alerte():
        return datetime.timedelta(days=getattr(settings, "DOCUMENTS_DELAI_ALERTE_JOURS", 30))

    @property
    def jours_restants(self):
        if not self.date_expiration:
            return None
        return (self.date_expiration - timezone.localdate()).days

    @property
    def statut(self):
        jours = self.jours_restants
        if jours is None:
            return self.SANS_ECHEANCE
        if jours < 0:
            return self.EXPIRE
        if jours <= self.delai_alerte().days:
            return self.BIENTOT
        return self.VALIDE

    @property
    def statut_badge(self):
        jours = self.jours_restants
        if self.statut == self.EXPIRE:
            return format_html('<span class="badge bg-danger">Expiré depuis {} j</span>', -jours)
        if self.statut == self.BIENTOT:
            texte = "Expire aujourd'hui" if jours == 0 else f"Expire dans {jours} j"
            return format_html('<span class="badge bg-warning text-dark">{}</span>', texte)
        if self.statut == self.VALIDE:
            return format_html('<span class="badge bg-success">{}</span>', "Valide")
        return format_html('<span class="badge bg-secondary">{}</span>', "Sans échéance")

    @classmethod
    def en_alerte(cls):
        """Documents expirés ou expirant dans le délai d'alerte."""
        limite = timezone.localdate() + cls.delai_alerte()
        return (
            cls.objects.filter(
                date_expiration__isnull=False,
                date_expiration__lte=limite,
                vehicule__is_deleted=False,
            )
            .select_related("vehicule")
            .order_by("date_expiration")
        )


class Engin(FlotteModel):
    """Engin spécial : excavateur, chargeur, bulldozer, grue, porte-char, etc."""

    TYPE_CHOICES = [
        ("excavateur", "Excavateur"),
        ("chargeur", "Chargeur"),
        ("bulldozer", "Bulldozer"),
        ("grue_mobile", "Grue mobile"),
        ("forklift", "Forklift (chariot élévateur)"),
        ("compacteur", "Compacteur"),
        ("poclain", "Poclain"),
        ("porte_char", "Porte-char"),
        ("autre", "Autre"),
    ]
    nom = models.CharField("Nom / Désignation", max_length=80)
    type_engin = models.CharField("Type", max_length=20, choices=TYPE_CHOICES, default="autre")
    capacite = models.CharField(
        "Capacité", max_length=40, blank=True,
        help_text="Ex. 1,5 m³ (godet), 25 tonnes (grue), 3 tonnes (forklift).",
    )
    actif = models.BooleanField("En service", default=True)

    class Meta:
        verbose_name = "Engin"
        verbose_name_plural = "Engins"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


# --------------------------------------------------------------------------
# Opérations
# --------------------------------------------------------------------------
class Entretien(FlotteModel):
    """Charge d'entretien / réparation d'un véhicule."""

    date = models.DateField("Date")
    vehicule = models.ForeignKey(
        Vehicule, verbose_name="Véhicule", on_delete=models.PROTECT, related_name="entretiens",
    )
    chauffeur = models.ForeignKey(
        Chauffeur, verbose_name="Chauffeur", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="entretiens",
    )
    n_facture = models.CharField("N° Facture", max_length=50, blank=True)
    km_depart = models.PositiveIntegerField("Kilométrage départ", null=True, blank=True)
    km_arrivee = models.PositiveIntegerField("Kilométrage arrivée", null=True, blank=True)
    garage = models.CharField("Garage", max_length=120, blank=True)
    nature_operations = models.TextField("Nature des opérations", blank=True)
    montant_ttc = models.DecimalField("Montant TTC", max_digits=14, decimal_places=2, default=0)
    observation = models.CharField("Observation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Entretien"
        verbose_name_plural = "Entretiens"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} — {self.vehicule} — {self.montant_ttc}"


class PleinCarburant(FlotteModel):
    """Plein / bon de carburant d'un véhicule."""

    date = models.DateField("Date")
    vehicule = models.ForeignKey(
        Vehicule, verbose_name="Véhicule", on_delete=models.PROTECT, related_name="pleins",
    )
    chauffeur = models.ForeignKey(
        Chauffeur, verbose_name="Chauffeur", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pleins",
    )
    litres = models.DecimalField("Litres", max_digits=10, decimal_places=2, default=0)
    prix_litre = models.DecimalField("Prix / litre", max_digits=10, decimal_places=2, default=0)
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2, default=0, editable=False)
    kilometrage = models.PositiveIntegerField("Kilométrage", null=True, blank=True)
    n_bon = models.CharField("N° du bon", max_length=50, blank=True)
    observation = models.CharField("Observation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Plein de carburant"
        verbose_name_plural = "Pleins de carburant"
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        # Montant recalculé automatiquement.
        self.montant = (self.litres or Decimal("0")) * (self.prix_litre or Decimal("0"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} — {self.vehicule} — {self.litres} L"


class Voyage(FlotteModel):
    """Activité de transport d'un camion."""

    date = models.DateField("Date")
    vehicule = models.ForeignKey(
        Vehicule, verbose_name="Véhicule", on_delete=models.PROTECT, related_name="voyages",
    )
    chauffeur = models.ForeignKey(
        Chauffeur, verbose_name="Chauffeur", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="voyages",
    )
    superviseur1 = models.CharField("Superviseur 1", max_length=120, blank=True)
    superviseur2 = models.CharField("Superviseur 2", max_length=120, blank=True)
    n_bon = models.CharField("N° du bon", max_length=50, blank=True)
    nb_voyage = models.PositiveIntegerField("Nombre de voyages", default=0)
    pu_voyage = models.DecimalField("PU / voyage", max_digits=12, decimal_places=2, default=0)
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2, default=0, editable=False)
    km_depart = models.PositiveIntegerField("Kilométrage départ", null=True, blank=True)
    km_arrivee = models.PositiveIntegerField("Kilométrage arrivée", null=True, blank=True)
    nb_heures = models.DecimalField(
        "Nombre d'heures", max_digits=7, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Voyage"
        verbose_name_plural = "Voyages"
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        self.montant = Decimal(self.nb_voyage or 0) * (self.pu_voyage or Decimal("0"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} — {self.vehicule} — {self.nb_voyage} voyage(s)"


class ActiviteEngin(FlotteModel):
    """Activité d'un engin type Poclain : chargements (recette) + carburant (dépense)."""

    date = models.DateField("Date")
    engin = models.ForeignKey(
        Engin, verbose_name="Engin", on_delete=models.PROTECT, related_name="activites",
    )
    categorie_roues = models.ForeignKey(
        CategorieRoues, verbose_name="Camions chargés (nb de roues)",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="activites_poclain",
    )
    nb_chargement = models.PositiveIntegerField("Nombre de chargements", default=0)
    pu_chargement = models.DecimalField("PU / chargement", max_digits=12, decimal_places=2, default=0)
    montant_chargement = models.DecimalField(
        "Montant chargement", max_digits=14, decimal_places=2, default=0, editable=False
    )
    qte_carburant = models.DecimalField("Quantité carburant (L)", max_digits=10, decimal_places=2, default=0)
    prix_litre = models.DecimalField("Prix / litre", max_digits=10, decimal_places=2, default=0)
    montant_carburant = models.DecimalField(
        "Montant carburant", max_digits=14, decimal_places=2, default=0, editable=False
    )
    observation = models.CharField("Observation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Activité d'engin (Poclain)"
        verbose_name_plural = "Activités d'engins (Poclain)"
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        self.montant_chargement = Decimal(self.nb_chargement or 0) * (self.pu_chargement or Decimal("0"))
        self.montant_carburant = (self.qte_carburant or Decimal("0")) * (self.prix_litre or Decimal("0"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} — {self.engin} — {self.nb_chargement} chargement(s)"


class TrajetPorteChar(FlotteModel):
    """Trajet de transport d'engin par porte-char."""

    date = models.DateField("Date")
    engin = models.ForeignKey(
        Engin, verbose_name="Engin transporté", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="trajets_porte_char",
    )
    point_depart = models.CharField("Point de départ", max_length=120)
    point_arrivee = models.CharField("Point d'arrivée", max_length=120)
    km_depart = models.PositiveIntegerField("Kilométrage départ", null=True, blank=True)
    km_arrivee = models.PositiveIntegerField("Kilométrage arrivée", null=True, blank=True)
    montant_paye = models.DecimalField("Montant payé", max_digits=14, decimal_places=2, default=0)
    observation = models.CharField("Observation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Trajet porte-char"
        verbose_name_plural = "Trajets porte-char"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} — {self.point_depart} → {self.point_arrivee}"


class AutreDepense(FlotteModel):
    """Dépense diverse non rattachée à un véhicule précis."""

    date = models.DateField("Date")
    designation = models.CharField("Désignation", max_length=200)
    prix_unitaire = models.DecimalField("Prix unitaire", max_digits=12, decimal_places=2, default=0)
    quantite = models.DecimalField("Quantité", max_digits=10, decimal_places=2, default=1)
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2, default=0, editable=False)
    observation = models.CharField("Observation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Autre dépense"
        verbose_name_plural = "Autres dépenses"
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        self.montant = (self.prix_unitaire or Decimal("0")) * (self.quantite or Decimal("0"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} — {self.designation} — {self.montant}"


# --------------------------------------------------------------------------
# Pointage
# --------------------------------------------------------------------------
# Namespace fixe pour générer des identifiants déterministes de pointage :
# un même couple (employé, date) donne toujours le même UUID.
PTG_NAMESPACE = uuid.UUID("3f2a9c10-6b4e-4d1a-9b7c-0a1b2c3d4e5f")


class EmployeFlotte(FlotteModel):
    """Personnel suivi par le pointage de présence de la flotte."""

    nom_complet = models.CharField("Nom complet", max_length=150)
    matricule = models.CharField("Matricule", max_length=40)
    fonction = models.CharField("Fonction", max_length=100, blank=True)
    service = models.CharField("Service / Département", max_length=100, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    numero_permis = models.CharField("N° de permis", max_length=40, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Employé (flotte)"
        verbose_name_plural = "Employés (flotte)"
        ordering = ["service", "nom_complet"]

    def __str__(self):
        return f"{self.nom_complet} ({self.matricule})"


class Pointage(FlotteModel):
    """Statut de présence d'un employé pour une journée donnée."""

    PRESENT = "P"
    ABSENT = "A"
    CONGE = "C"
    MISSION = "M"
    REPOS = "R"
    MALADIE = "ML"
    RETARD = "RT"
    SANCTION = "S"

    STATUTS = [
        (PRESENT, "Présent"),
        (ABSENT, "Absent"),
        (CONGE, "Congé"),
        (MISSION, "Mission"),
        (REPOS, "Repos"),
        (MALADIE, "Maladie"),
        (RETARD, "Retard"),
        (SANCTION, "Sanction"),
    ]
    # Statuts comptés comme « présence effective » (un employé en retard est venu).
    STATUTS_PRESENCE = {PRESENT, MISSION, RETARD}

    employe = models.ForeignKey(
        EmployeFlotte, verbose_name="Employé", on_delete=models.CASCADE, related_name="pointages",
    )
    date = models.DateField("Date")
    statut = models.CharField("Statut", max_length=2, choices=STATUTS)

    class Meta:
        verbose_name = "Pointage"
        verbose_name_plural = "Pointages"
        ordering = ["date"]
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.employe} — {self.date} — {self.statut}"

    @staticmethod
    def pk_for(employe_id, date) -> uuid.UUID:
        """Identifiant déterministe pour un couple (employé, date)."""
        return uuid.uuid5(PTG_NAMESPACE, f"{employe_id}:{date}")


# --------------------------------------------------------------------------
# Stock de la flotte
# --------------------------------------------------------------------------
class Article(FlotteModel):
    """Article d'inventaire (outillage, équipement, consommable…)."""

    code = models.CharField("Code", max_length=40)
    designation = models.CharField("Désignation", max_length=200)
    specification = models.CharField("Spécification", max_length=200, blank=True)
    categorie = models.CharField("Catégorie", max_length=100, blank=True)
    stock_initial = models.DecimalField("Stock initial", max_digits=12, decimal_places=2, default=0)
    seuil_mini = models.DecimalField("Seuil minimum", max_digits=12, decimal_places=2, default=0)
    observation = models.CharField("Observation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Article de flotte"
        verbose_name_plural = "Articles de flotte"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.designation}"

    # Statuts calculés
    OK, ALERTE, RUPTURE = "OK", "ALERTE", "RUPTURE"

    @staticmethod
    def statut_pour(stock_actuel, seuil_mini):
        if stock_actuel <= 0:
            return Article.RUPTURE
        if stock_actuel <= (seuil_mini or 0):
            return Article.ALERTE
        return Article.OK

    def stock_actuel(self):
        """Calcul en direct (détail). Les listes agrègent en lot."""
        agg = self.mouvements.aggregate(
            e=models.Sum("quantite", filter=models.Q(type=MouvementStock.ENTREE)),
            s=models.Sum("quantite", filter=models.Q(type=MouvementStock.SORTIE)),
        )
        e = agg["e"] or Decimal("0")
        s = agg["s"] or Decimal("0")
        return (self.stock_initial or Decimal("0")) + e - s


class MouvementStock(FlotteModel):
    """Entrée ou sortie de stock (journal des mouvements)."""

    ENTREE = "E"
    SORTIE = "S"
    TYPES = [(ENTREE, "Entrée"), (SORTIE, "Sortie")]

    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.CASCADE, related_name="mouvements",
    )
    date = models.DateField("Date")
    type = models.CharField("Type", max_length=1, choices=TYPES, default=SORTIE)
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=2, default=0)
    motif = models.CharField("Motif / Bénéficiaire", max_length=255, blank=True)
    responsable = models.CharField("Responsable", max_length=120, blank=True)

    class Meta:
        verbose_name = "Mouvement de stock (flotte)"
        verbose_name_plural = "Mouvements de stock (flotte)"
        ordering = ["-date"]
        indexes = [models.Index(fields=["date"]), models.Index(fields=["type"])]

    def __str__(self):
        return f"{self.date} — {self.get_type_display()} — {self.article.code} ({self.quantite})"
