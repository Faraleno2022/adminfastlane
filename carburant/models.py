"""Modèles du module Transport de carburant.

Flux géré : un client (marketeur pétrolier, société minière, station…) commande
un transport → un voyage est planifié avec une citerne, un tracteur et un
chauffeur de la Flotte → la citerne est chargée au dépôt (bon de chargement,
litres chargés) → le produit est livré à destination (bon de livraison, litres
livrés) → l'écart chargé/livré au-delà de la tolérance est un manquant imputé au
transporteur au prix du produit → le transport est facturé au litre (chargé ou
livré) ou au forfait, net des pénalités → le client règle ; les frais de route
du voyage donnent la marge. Toutes les données sont isolées par entreprise.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.tenancy import EntrepriseModel

ZERO = Decimal("0")
CENT = Decimal("100")

PRODUITS = [
    ("gasoil", "Gasoil"), ("essence", "Essence (super)"), ("petrole", "Pétrole lampant"),
    ("jet", "Jet A1"), ("fuel", "Fuel oil"), ("autre", "Autre"),
]

MODES_PAIEMENT = [
    ("virement", "Virement bancaire"),
    ("cheque", "Chèque"),
    ("especes", "Espèces"),
    ("mobile_money", "Mobile Money"),
]


class Client(EntrepriseModel):
    nom = models.CharField("Nom / raison sociale", max_length=200)
    contact = models.CharField("Personne à contacter", max_length=150, blank=True)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    email = models.EmailField("E-mail", blank=True)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    nif = models.CharField("NIF", max_length=60, blank=True)
    tarif_litre = models.DecimalField("Tarif de transport par litre", max_digits=12, decimal_places=2, default=0,
                                      help_text="Proposé par défaut sur les nouveaux voyages de ce client.")
    tolerance_pct = models.DecimalField("Tolérance de manquant (%)", max_digits=5, decimal_places=2,
                                        default=Decimal("0.50"),
                                        help_text="Écart chargé/livré admis sans pénalité.")
    note = models.TextField("Note", blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Citerne(EntrepriseModel):
    OK, BIENTOT, EXPIRE, INCONNU = "ok", "bientot", "expire", "inconnu"
    ALERTE_JOURS = 30

    immatriculation = models.CharField("Immatriculation / n° de citerne", max_length=40)
    vehicule = models.ForeignKey("flotte.Vehicule", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="citernes_carburant", verbose_name="Tracteur habituel (Flotte)")
    capacite = models.DecimalField("Capacité (litres)", max_digits=10, decimal_places=0)
    nb_compartiments = models.PositiveSmallIntegerField("Compartiments", default=1)
    numero_barremage = models.CharField("N° du certificat de barémage", max_length=60, blank=True)
    expiration_barremage = models.DateField("Barémage valable jusqu'au", null=True, blank=True)
    active = models.BooleanField("En service", default=True)
    note = models.CharField("Note", max_length=255, blank=True)

    class Meta:
        verbose_name = "Citerne"
        verbose_name_plural = "Citernes"
        ordering = ["immatriculation"]

    def __str__(self):
        return f"{self.immatriculation} ({self.capacite:,.0f} L)".replace(",", " ")

    @property
    def etat_barremage(self):
        if not self.expiration_barremage:
            return self.INCONNU
        aujourdhui = timezone.localdate()
        if self.expiration_barremage < aujourdhui:
            return self.EXPIRE
        if self.expiration_barremage <= aujourdhui + timedelta(days=self.ALERTE_JOURS):
            return self.BIENTOT
        return self.OK


class Voyage(EntrepriseModel):
    PLANIFIE, EN_ROUTE, LIVRE, ANNULE = "planifie", "en_route", "livre", "annule"
    STATUTS = [(PLANIFIE, "Planifié"), (EN_ROUTE, "Chargé / en route"), (LIVRE, "Livré"), (ANNULE, "Annulé")]
    LIVREE, CHARGEE, FORFAIT = "livree", "chargee", "forfait"
    BASES = [(LIVREE, "Au litre livré"), (CHARGEE, "Au litre chargé"), (FORFAIT, "Forfait par voyage")]

    reference = models.CharField("Référence", max_length=30, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="voyages", verbose_name="Client")
    citerne = models.ForeignKey(Citerne, on_delete=models.PROTECT, related_name="voyages", verbose_name="Citerne")
    vehicule = models.ForeignKey("flotte.Vehicule", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="voyages_carburant", verbose_name="Tracteur",
                                 help_text="Laisser vide pour prendre le tracteur habituel de la citerne.")
    chauffeur = models.ForeignKey("flotte.Chauffeur", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="voyages_carburant", verbose_name="Chauffeur",
                                  help_text="Laisser vide pour prendre le chauffeur principal du tracteur.")
    produit = models.CharField("Produit", max_length=10, choices=PRODUITS, default="gasoil")
    lieu_chargement = models.CharField("Dépôt de chargement", max_length=150)
    destination = models.CharField("Lieu de livraison", max_length=200)
    date_prevue = models.DateField("Date prévue", default=timezone.localdate)

    date_chargement = models.DateField("Date de chargement", null=True, blank=True)
    bon_chargement = models.CharField("N° du bon de chargement", max_length=60, blank=True)
    quantite_chargee = models.DecimalField("Quantité chargée (L)", max_digits=12, decimal_places=2,
                                           null=True, blank=True)
    date_livraison = models.DateField("Date de livraison", null=True, blank=True)
    bon_livraison = models.CharField("N° du bon de livraison", max_length=60, blank=True)
    quantite_livree = models.DecimalField("Quantité livrée (L)", max_digits=12, decimal_places=2,
                                          null=True, blank=True)

    base_facturation = models.CharField("Facturation", max_length=8, choices=BASES, default=LIVREE)
    tarif_litre = models.DecimalField("Tarif par litre", max_digits=12, decimal_places=2, default=0)
    forfait = models.DecimalField("Montant forfaitaire", max_digits=16, decimal_places=2, default=0)
    tolerance_pct = models.DecimalField("Tolérance de manquant (%)", max_digits=5, decimal_places=2, default=0)
    prix_produit = models.DecimalField("Prix du produit par litre", max_digits=12, decimal_places=2, default=0,
                                       help_text="Sert à valoriser les manquants au-delà de la tolérance.")

    statut = models.CharField("Statut", max_length=10, choices=STATUTS, default=PLANIFIE, db_index=True)
    note = models.TextField("Note", blank=True)
    agent = models.CharField("Saisi par", max_length=150, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Voyage"
        verbose_name_plural = "Voyages"
        ordering = ["-date_prevue", "-id"]
        constraints = [models.UniqueConstraint(fields=["entreprise", "reference"], name="carburant_voyage_ref_unique")]

    def __str__(self):
        return f"{self.reference} — {self.client}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._prochaine_reference()
        if self.vehicule_id is None and self.citerne_id and self.citerne.vehicule_id:
            self.vehicule_id = self.citerne.vehicule_id
        if self.chauffeur_id is None and self.vehicule_id and self.vehicule.chauffeur_actuel_id:
            self.chauffeur_id = self.vehicule.chauffeur_actuel_id
        super().save(*args, **kwargs)

    def _prochaine_reference(self):
        annee = timezone.localdate().year
        prefixe = f"TC-{annee}-"
        dernier = 0
        for ref in Voyage.objects.filter(reference__startswith=prefixe).values_list("reference", flat=True):
            try:
                dernier = max(dernier, int(ref[len(prefixe):]))
            except ValueError:
                continue
        return f"{prefixe}{dernier + 1:04d}"

    # --- Quantités et manquants -------------------------------------------
    @property
    def ecart(self):
        """Litres perdus entre chargement et livraison (négatif si gain de température)."""
        if self.quantite_chargee is None or self.quantite_livree is None:
            return None
        return self.quantite_chargee - self.quantite_livree

    @property
    def taux_ecart(self):
        if self.ecart is None or not self.quantite_chargee:
            return None
        return (self.ecart * CENT / self.quantite_chargee).quantize(Decimal("0.01"))

    @property
    def tolerance_litres(self):
        return ((self.quantite_chargee or ZERO) * self.tolerance_pct / CENT).quantize(Decimal("0.01"))

    @property
    def manquant_imputable(self):
        if self.ecart is None:
            return ZERO
        return max(self.ecart - self.tolerance_litres, ZERO)

    @property
    def penalite(self):
        return (self.manquant_imputable * self.prix_produit).quantize(Decimal("1"))

    # --- Facturation --------------------------------------------------------
    @property
    def litres_factures(self):
        if self.base_facturation == self.CHARGEE:
            return self.quantite_chargee or ZERO
        if self.base_facturation == self.LIVREE:
            return self.quantite_livree or ZERO
        return ZERO

    @property
    def montant_transport(self):
        if self.base_facturation == self.FORFAIT:
            return self.forfait
        return (self.litres_factures * self.tarif_litre).quantize(Decimal("1"))

    @property
    def montant_net(self):
        """Ce que le client doit pour ce voyage (transport − pénalité), compté une fois livré."""
        return self.montant_transport - self.penalite

    @property
    def facturable(self):
        return self.statut == self.LIVRE

    # Les frais parcourent la relation en mémoire : ils profitent d'un prefetch_related.
    @property
    def total_frais(self):
        return sum((f.montant for f in self.frais.all()), ZERO)

    @property
    def marge(self):
        return self.montant_net - self.total_frais


class FraisVoyage(EntrepriseModel):
    TYPES = [
        ("gasoil_camion", "Carburant du camion"), ("peage", "Péages, taxes et barrières"),
        ("mission", "Frais de mission du chauffeur"), ("reparation", "Réparation en route"),
        ("manutention", "Chargement / déchargement"), ("autre", "Autre"),
    ]

    voyage = models.ForeignKey(Voyage, on_delete=models.CASCADE, related_name="frais")
    type = models.CharField("Type de frais", max_length=15, choices=TYPES, default="gasoil_camion")
    date = models.DateField("Date", default=timezone.localdate)
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2)
    note = models.CharField("Détail", max_length=255, blank=True)

    class Meta:
        verbose_name = "Frais de voyage"
        verbose_name_plural = "Frais de voyage"
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.montant}"


class Paiement(EntrepriseModel):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="paiements", verbose_name="Client")
    date = models.DateField("Date", default=timezone.localdate)
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    mode = models.CharField("Mode de paiement", max_length=15, choices=MODES_PAIEMENT, default="virement")
    reference = models.CharField("Référence (n° de chèque, de virement…)", max_length=80, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)
    agent = models.CharField("Encaissé par", max_length=150, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Paiement client"
        verbose_name_plural = "Paiements clients"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.client} — {self.montant}"
