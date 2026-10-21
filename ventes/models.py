"""Modèles du module Ventes & caisse (comptes clients prépayés, produits, stock, caisse).

Repris de l'application « Gestionnaire Dépôt / Retrait » (EMAB) : un client,
identifié par son matricule, alimente un compte par des dépôts, puis retire
de l'argent ou achète des produits (la vente débite le compte ou est encaissée
en caisse). Toutes les données sont isolées par entreprise.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.tenancy import EntrepriseModel

ZERO = Decimal("0")
PLAFOND_DEPOT_DEFAUT = Decimal("40000")


def _agent_nom(user):
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username() or "").strip()


class ParametreVentes(EntrepriseModel):
    """Réglages du module pour l'entreprise (un seul enregistrement)."""

    plafond_depot_journalier = models.DecimalField(
        "Plafond de dépôt par matricule et par jour (GNF)", max_digits=14, decimal_places=2,
        default=PLAFOND_DEPOT_DEFAUT,
        help_text="0 = aucun plafond.",
    )
    devise = models.CharField("Devise", max_length=10, default="GNF")
    ticket_titre = models.CharField("Titre du ticket", max_length=120, blank=True)
    ticket_adresse = models.CharField("Adresse / contact (ticket)", max_length=200, blank=True)
    ticket_pied = models.CharField("Pied de ticket", max_length=200, blank=True, default="Merci de votre confiance")

    class Meta:
        verbose_name = "Paramètres des ventes"
        verbose_name_plural = "Paramètres des ventes"
        constraints = [models.UniqueConstraint(fields=["entreprise"], name="ventes_parametre_unique")]

    def __str__(self):
        return f"Paramètres ventes — {self.entreprise_id}"

    @classmethod
    def courant(cls):
        """Paramètres de l'entreprise courante (créés au besoin avec les valeurs par défaut)."""
        param = cls.objects.first()
        if param is None:
            param = cls(); param.save()
        return param


class ClientCompte(EntrepriseModel):
    """Fiche d'un titulaire de compte (identifié par son matricule)."""

    matricule = models.CharField("Matricule", max_length=80)
    nom = models.CharField("Nom", max_length=200, blank=True)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)
    actif = models.BooleanField("Actif", default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["matricule"]
        constraints = [models.UniqueConstraint(fields=["entreprise", "matricule"], name="ventes_client_matricule_unique")]

    def __str__(self):
        return f"{self.matricule} ({self.nom})" if self.nom else self.matricule


class Produit(EntrepriseModel):
    reference = models.CharField("Référence", max_length=80, blank=True)
    nom = models.CharField("Nom", max_length=200)
    description = models.TextField("Description", blank=True)
    categorie = models.CharField("Catégorie", max_length=120, blank=True)
    unite = models.CharField("Unité", max_length=40, blank=True)
    prix_unitaire = models.DecimalField("Prix de vente", max_digits=14, decimal_places=2, default=0)
    prix_achat = models.DecimalField("Prix d'achat", max_digits=14, decimal_places=2, default=0)
    quantite_stock = models.DecimalField("Stock", max_digits=14, decimal_places=3, default=0)
    seuil_alerte = models.DecimalField("Seuil d'alerte", max_digits=14, decimal_places=3, default=0)
    stock_max = models.DecimalField("Stock maximum", max_digits=14, decimal_places=3, default=0)
    emplacement = models.CharField("Emplacement", max_length=120, blank=True)
    suivi_stock = models.BooleanField(
        "Suivi du stock", default=True,
        help_text="Décocher pour un article vendu sans stock (plat servi, service rendu).",
    )
    actif = models.BooleanField("Actif", default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def valeur_stock(self):
        return (self.quantite_stock or ZERO) * (self.prix_unitaire or ZERO)

    @property
    def etat_stock(self):
        """rupture / bas / surstock / ok (ou « » si le stock n'est pas suivi)."""
        if not self.suivi_stock:
            return ""
        if self.quantite_stock <= 0:
            return "rupture"
        if self.quantite_stock <= (self.seuil_alerte or ZERO):
            return "bas"
        if self.stock_max and self.quantite_stock > self.stock_max:
            return "surstock"
        return "ok"


class Operation(EntrepriseModel):
    """Dépôt ou retrait d'espèces sur le compte d'un client."""

    DEPOT, RETRAIT = "depot", "retrait"
    TYPES = [(DEPOT, "Dépôt"), (RETRAIT, "Retrait")]

    matricule = models.CharField("Matricule", max_length=80, db_index=True)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    type = models.CharField("Type", max_length=10, choices=TYPES)
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2)
    solde_apres = models.DecimalField("Solde après", max_digits=14, decimal_places=2, default=0)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    agent_nom = models.CharField("Agent", max_length=200, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    deleted = models.BooleanField("Dans la corbeille", default=False, db_index=True)

    class Meta:
        verbose_name = "Opération (dépôt/retrait)"
        verbose_name_plural = "Opérations (dépôts/retraits)"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_type_display()} {self.montant} — {self.matricule}"


class Vente(EntrepriseModel):
    """Vente d'une ligne de produit (une ligne par produit vendu)."""

    COMPTE, CAISSE = "compte", "caisse"
    MODES = [(COMPTE, "Débit du compte client"), (CAISSE, "Encaissée en caisse")]

    matricule = models.CharField("Matricule", max_length=80, blank=True, db_index=True)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    produit = models.ForeignKey(Produit, null=True, on_delete=models.SET_NULL, related_name="ventes")
    produit_nom = models.CharField("Produit", max_length=200)
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)
    montant_total = models.DecimalField("Montant", max_digits=14, decimal_places=2)
    solde_apres = models.DecimalField("Solde après", max_digits=14, decimal_places=2, default=0)
    mode_paiement = models.CharField("Paiement", max_length=10, choices=MODES, default=COMPTE)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    agent_nom = models.CharField("Agent", max_length=200, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    deleted = models.BooleanField("Dans la corbeille", default=False, db_index=True)

    class Meta:
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.produit_nom} x{self.quantite} — {self.matricule or 'caisse'}"


class MouvementStock(EntrepriseModel):
    ENTREE, SORTIE = "entree", "sortie"
    TYPES = [(ENTREE, "Entrée"), (SORTIE, "Sortie")]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="mouvements")
    produit_nom = models.CharField("Produit", max_length=200)
    type = models.CharField("Type", max_length=10, choices=TYPES)
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    stock_apres = models.DecimalField("Stock après", max_digits=14, decimal_places=3)
    motif = models.CharField("Motif", max_length=255, blank=True)
    vente = models.ForeignKey(Vente, null=True, blank=True, on_delete=models.SET_NULL, related_name="mouvements")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    agent_nom = models.CharField("Agent", max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    deleted = models.BooleanField("Dans la corbeille", default=False, db_index=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_type_display()} {self.quantite} — {self.produit_nom}"


class EcritureCaisse(EntrepriseModel):
    """Écriture du journal de caisse ; le solde progressif se recalcule en cumul."""

    MANUEL, VENTE, OUVERTURE = "manuel", "vente", "ouverture"

    date = models.DateField("Date", db_index=True)
    libelle = models.CharField("Libellé", max_length=255)
    entree = models.DecimalField("Entrée", max_digits=14, decimal_places=2, default=0)
    sortie = models.DecimalField("Sortie", max_digits=14, decimal_places=2, default=0)
    source = models.CharField("Source", max_length=12, default=MANUEL)
    vente = models.ForeignKey(Vente, null=True, blank=True, on_delete=models.SET_NULL, related_name="ecritures_caisse")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    agent_nom = models.CharField("Agent", max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    deleted = models.BooleanField("Annulée", default=False, db_index=True)

    class Meta:
        verbose_name = "Écriture de caisse"
        verbose_name_plural = "Écritures de caisse"
        ordering = ["date", "created_at", "id"]

    def __str__(self):
        return f"{self.date} — {self.libelle}"


class DemandeStock(EntrepriseModel):
    """Demande d'entrée de stock ou de création de produit, à valider par un administrateur."""

    EN_ATTENTE, VALIDE, REJETE = "en_attente", "valide", "rejete"
    STATUTS = [(EN_ATTENTE, "En attente"), (VALIDE, "Validée"), (REJETE, "Rejetée")]
    ENTREE, NOUVEAU = "entree", "nouveau_produit"
    KINDS = [(ENTREE, "Entrée sur produit existant"), (NOUVEAU, "Création d'un nouveau produit")]

    kind = models.CharField(max_length=16, choices=KINDS, default=ENTREE, db_index=True)
    produit = models.ForeignKey(Produit, null=True, blank=True, on_delete=models.SET_NULL, related_name="demandes")
    produit_nom = models.CharField("Produit", max_length=200)
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    motif = models.CharField("Motif", max_length=255, blank=True)
    new_reference = models.CharField("Référence proposée", max_length=80, blank=True)
    new_prix_unitaire = models.DecimalField("Prix proposé", max_digits=14, decimal_places=2, default=0)
    new_seuil_alerte = models.DecimalField("Seuil proposé", max_digits=14, decimal_places=3, default=0)
    new_description = models.TextField("Description proposée", blank=True)
    statut = models.CharField(max_length=12, choices=STATUTS, default=EN_ATTENTE, db_index=True)
    demandeur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    demandeur_nom = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    decide_par_nom = models.CharField(max_length=200, blank=True)
    decide_le = models.DateTimeField(null=True, blank=True)
    decision_motif = models.CharField(max_length=255, blank=True)
    mouvement = models.ForeignKey(MouvementStock, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "Demande d'entrée de stock"
        verbose_name_plural = "Demandes d'entrée de stock"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.produit_nom} +{self.quantite} [{self.statut}]"


class JournalAudit(EntrepriseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user_identifiant = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Entrée d'audit"
        verbose_name_plural = "Journal d'audit"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.user_identifiant} : {self.action}"
