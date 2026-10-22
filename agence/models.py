"""Modèles du module Agence de voyage.

Flux géré : un client demande un voyage → un dossier est ouvert (devis) → on y
ajoute les prestations vendues (billets, hôtels, visas, assurances…), chacune
achetée à un fournisseur → le client règle par acomptes → l'agence règle ses
fournisseurs → le dossier est clôturé. La marge est la différence entre le prix
de vente et le prix d'achat. Toutes les données sont isolées par entreprise.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.tenancy import EntrepriseModel

ZERO = Decimal("0")

MODES_PAIEMENT = [
    ("especes", "Espèces"),
    ("virement", "Virement bancaire"),
    ("mobile_money", "Mobile Money"),
    ("cheque", "Chèque"),
    ("carte", "Carte bancaire"),
]


class Client(EntrepriseModel):
    nom = models.CharField("Nom complet", max_length=200)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    email = models.EmailField("E-mail", blank=True)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    nationalite = models.CharField("Nationalité", max_length=80, blank=True)
    date_naissance = models.DateField("Date de naissance", null=True, blank=True)
    passeport_numero = models.CharField("N° de passeport", max_length=60, blank=True)
    passeport_expiration = models.DateField("Expiration du passeport", null=True, blank=True)
    note = models.TextField("Note", blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Fournisseur(EntrepriseModel):
    COMPAGNIE, HOTEL, TRANSPORT, ASSURANCE, VISA, AUTRE = "compagnie", "hotel", "transport", "assurance", "visa", "autre"
    TYPES = [
        (COMPAGNIE, "Compagnie aérienne"), (HOTEL, "Hôtel / hébergement"), (TRANSPORT, "Transport / location"),
        (ASSURANCE, "Assurance"), (VISA, "Ambassade / visa"), (AUTRE, "Autre"),
    ]

    nom = models.CharField("Nom", max_length=200)
    type = models.CharField("Type", max_length=12, choices=TYPES, default=AUTRE)
    contact = models.CharField("Personne à contacter", max_length=150, blank=True)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    email = models.EmailField("E-mail", blank=True)
    note = models.CharField("Note", max_length=255, blank=True)

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Dossier(EntrepriseModel):
    DEVIS, CONFIRME, TERMINE, ANNULE = "devis", "confirme", "termine", "annule"
    STATUTS = [(DEVIS, "Devis"), (CONFIRME, "Confirmé"), (TERMINE, "Terminé"), (ANNULE, "Annulé")]
    STATUTS_ACTIFS = (CONFIRME, TERMINE)  # comptés dans le chiffre d'affaires

    reference = models.CharField("Référence", max_length=30, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="dossiers", verbose_name="Client")
    destination = models.CharField("Destination", max_length=200)
    objet = models.CharField("Objet du voyage", max_length=200, blank=True,
                             help_text="Affaires, tourisme, pèlerinage, études, famille…")
    date_depart = models.DateField("Départ", null=True, blank=True)
    date_retour = models.DateField("Retour", null=True, blank=True)
    nb_voyageurs = models.PositiveIntegerField("Nombre de voyageurs", default=1)
    statut = models.CharField("Statut", max_length=10, choices=STATUTS, default=DEVIS, db_index=True)
    agent = models.CharField("Agent", max_length=150, blank=True, editable=False)
    note = models.TextField("Note", blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Dossier de voyage"
        verbose_name_plural = "Dossiers de voyage"
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["entreprise", "reference"], name="agence_dossier_ref_unique")]

    def __str__(self):
        return f"{self.reference} — {self.client}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._prochaine_reference()
        super().save(*args, **kwargs)

    def _prochaine_reference(self):
        annee = timezone.localdate().year
        prefixe = f"DV-{annee}-"
        dernier = 0
        for ref in Dossier.objects.filter(reference__startswith=prefixe).values_list("reference", flat=True):
            try:
                dernier = max(dernier, int(ref[len(prefixe):]))
            except ValueError:
                continue
        return f"{prefixe}{dernier + 1:04d}"

    # Les totaux parcourent les relations en mémoire : ils profitent d'un prefetch_related.
    def _prestations_valides(self):
        return [p for p in self.prestations.all() if p.statut != Prestation.ANNULEE]

    @property
    def total_vente(self):
        return sum((p.total_vente for p in self._prestations_valides()), ZERO)

    @property
    def total_achat(self):
        return sum((p.total_achat for p in self._prestations_valides()), ZERO)

    @property
    def marge(self):
        return self.total_vente - self.total_achat

    @property
    def total_paye(self):
        return sum((p.montant for p in self.paiements.all()), ZERO)

    @property
    def reste_a_payer(self):
        return self.total_vente - self.total_paye

    @property
    def dette_fournisseurs(self):
        return sum((p.reste_fournisseur for p in self._prestations_valides()), ZERO)

    @property
    def est_solde(self):
        return self.total_vente > 0 and self.reste_a_payer <= 0


class Prestation(EntrepriseModel):
    BILLET, HOTEL, VISA, ASSURANCE, TRANSPORT, VOYAGE, EXCURSION, AUTRE = (
        "billet", "hotel", "visa", "assurance", "transport", "voyage", "excursion", "autre")
    TYPES = [
        (BILLET, "Billet d'avion"), (HOTEL, "Hôtel / hébergement"), (VISA, "Visa"), (ASSURANCE, "Assurance voyage"),
        (TRANSPORT, "Transport / location / transfert"), (VOYAGE, "Voyage organisé"), (EXCURSION, "Excursion / activité"),
        (AUTRE, "Autre"),
    ]
    ATTENTE, CONFIRMEE, ANNULEE = "attente", "confirmee", "annulee"
    STATUTS = [(ATTENTE, "En attente"), (CONFIRMEE, "Confirmée / émise"), (ANNULEE, "Annulée")]

    dossier = models.ForeignKey(Dossier, on_delete=models.CASCADE, related_name="prestations")
    type = models.CharField("Type", max_length=12, choices=TYPES, default=BILLET)
    description = models.CharField("Description", max_length=255,
                                   help_text="Ex. : Conakry → Paris, Air France, classe économique.")
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="prestations", verbose_name="Fournisseur")
    reference_fournisseur = models.CharField("Réf. fournisseur (PNR, n° de réservation, n° de visa)",
                                             max_length=80, blank=True)
    date_debut = models.DateField("Du", null=True, blank=True)
    date_fin = models.DateField("Au", null=True, blank=True)
    quantite = models.DecimalField("Quantité", max_digits=8, decimal_places=2, default=1)
    prix_achat = models.DecimalField("Prix d'achat unitaire", max_digits=16, decimal_places=2, default=0)
    prix_vente = models.DecimalField("Prix de vente unitaire", max_digits=16, decimal_places=2, default=0)
    statut = models.CharField("Statut", max_length=10, choices=STATUTS, default=ATTENTE)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Prestation"
        verbose_name_plural = "Prestations"
        ordering = ["date_debut", "id"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.description}"

    @property
    def total_vente(self):
        return self.quantite * self.prix_vente

    @property
    def total_achat(self):
        return self.quantite * self.prix_achat

    @property
    def marge(self):
        return self.total_vente - self.total_achat

    @property
    def paye_fournisseur(self):
        return sum((p.montant for p in self.paiements.all()), ZERO)

    @property
    def reste_fournisseur(self):
        return max(self.total_achat - self.paye_fournisseur, ZERO)


class Voyageur(EntrepriseModel):
    dossier = models.ForeignKey(Dossier, on_delete=models.CASCADE, related_name="voyageurs")
    nom = models.CharField("Nom complet", max_length=200)
    date_naissance = models.DateField("Date de naissance", null=True, blank=True)
    nationalite = models.CharField("Nationalité", max_length=80, blank=True)
    passeport_numero = models.CharField("N° de passeport", max_length=60, blank=True)
    passeport_expiration = models.DateField("Expiration du passeport", null=True, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)

    class Meta:
        verbose_name = "Voyageur"
        verbose_name_plural = "Voyageurs"
        ordering = ["id"]

    def __str__(self):
        return self.nom

    @property
    def passeport_a_verifier(self):
        """Beaucoup de pays exigent un passeport valable 6 mois après le retour."""
        if not self.passeport_expiration:
            return False
        reference = self.dossier.date_retour or self.dossier.date_depart or timezone.localdate()
        return self.passeport_expiration < reference + timedelta(days=180)


class PaiementClient(EntrepriseModel):
    dossier = models.ForeignKey(Dossier, on_delete=models.CASCADE, related_name="paiements")
    date = models.DateField("Date", default=timezone.localdate)
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    mode = models.CharField("Mode de paiement", max_length=15, choices=MODES_PAIEMENT, default="especes")
    reference = models.CharField("Référence", max_length=80, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)
    agent = models.CharField("Encaissé par", max_length=150, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Paiement client"
        verbose_name_plural = "Paiements clients"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.dossier.reference} — {self.montant}"


class PaiementFournisseur(EntrepriseModel):
    prestation = models.ForeignKey(Prestation, on_delete=models.CASCADE, related_name="paiements")
    date = models.DateField("Date", default=timezone.localdate)
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    mode = models.CharField("Mode de paiement", max_length=15, choices=MODES_PAIEMENT, default="virement")
    reference = models.CharField("Référence", max_length=80, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Paiement fournisseur"
        verbose_name_plural = "Paiements fournisseurs"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.prestation} — {self.montant}"
