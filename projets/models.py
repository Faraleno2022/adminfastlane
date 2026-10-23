"""Modèles du module Gestion de projet (repris du module « projects » d'Etragsarlu).

Flux géré : un client (maître d'ouvrage) confie un projet → on fixe son budget
prévu et son planning → on découpe le travail en tâches suivies en avancement →
on affecte une équipe → on enregistre les mouvements financiers du projet :
dépôts (fonds reçus), retraits et dépenses (matériaux, main-d'œuvre…).

Solde disponible = budget prévu + dépôts − retraits − dépenses (règle Etragsarlu).
Toutes les données sont isolées par entreprise.
"""
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
]


class Client(EntrepriseModel):
    nom = models.CharField("Nom / raison sociale", max_length=200)
    contact = models.CharField("Personne à contacter", max_length=150, blank=True)
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    email = models.EmailField("E-mail", blank=True)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    nif = models.CharField("NIF", max_length=60, blank=True)
    note = models.TextField("Note", blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Projet(EntrepriseModel):
    PLANIFIE, EN_COURS, SUSPENDU, TERMINE, ANNULE = "planifie", "en_cours", "suspendu", "termine", "annule"
    STATUTS = [(PLANIFIE, "Planifié"), (EN_COURS, "En cours"), (SUSPENDU, "Suspendu"),
               (TERMINE, "Terminé"), (ANNULE, "Annulé")]
    STATUTS_OUVERTS = (PLANIFIE, EN_COURS, SUSPENDU)

    reference = models.CharField("Code projet", max_length=30, editable=False)
    nom = models.CharField("Nom du projet", max_length=255)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, null=True, blank=True,
                               related_name="projets", verbose_name="Client")
    responsable = models.CharField("Chef de projet", max_length=150, blank=True)
    budget = models.DecimalField("Budget prévu", max_digits=16, decimal_places=2, default=0)
    date_debut = models.DateField("Date de début", null=True, blank=True)
    date_fin_prevue = models.DateField("Date de fin prévue", null=True, blank=True)
    date_fin_reelle = models.DateField("Date de fin réelle", null=True, blank=True)
    statut = models.CharField("Statut", max_length=10, choices=STATUTS, default=PLANIFIE, db_index=True)
    lieu = models.CharField("Lieu / adresse du chantier", max_length=255, blank=True)
    ville = models.CharField("Ville", max_length=100, blank=True)
    avancement = models.PositiveSmallIntegerField(
        "Avancement (%)", default=0,
        help_text="Utilisé tant que le projet n'a pas de tâches ; ensuite calculé à partir des tâches.")
    description = models.TextField("Description", blank=True)
    cree_par = models.CharField("Créé par", max_length=150, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Projet"
        verbose_name_plural = "Projets"
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["entreprise", "reference"], name="projets_projet_ref_unique")]

    def __str__(self):
        return f"{self.reference} — {self.nom}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._prochaine_reference()
        if self.statut == self.TERMINE and not self.date_fin_reelle:
            self.date_fin_reelle = timezone.localdate()
        super().save(*args, **kwargs)

    def _prochaine_reference(self):
        annee = timezone.localdate().year
        prefixe = f"PRJ-{annee}-"
        dernier = 0
        for ref in Projet.objects.filter(reference__startswith=prefixe).values_list("reference", flat=True):
            try:
                dernier = max(dernier, int(ref[len(prefixe):]))
            except ValueError:
                continue
        return f"{prefixe}{dernier + 1:04d}"

    # Les totaux parcourent les relations en mémoire : ils profitent d'un prefetch_related.
    def _total(self, type_mouvement):
        return sum((m.montant for m in self.mouvements.all() if m.type == type_mouvement), ZERO)

    @property
    def total_depots(self):
        return self._total(Mouvement.DEPOT)

    @property
    def total_retraits(self):
        return self._total(Mouvement.RETRAIT)

    @property
    def total_depenses(self):
        return self._total(Mouvement.DEPENSE)

    @property
    def solde_disponible(self):
        return self.budget + self.total_depots - self.total_retraits - self.total_depenses

    @property
    def budget_consomme_pct(self):
        enveloppe = self.budget + self.total_depots
        if enveloppe <= 0:
            return 100 if self.total_depenses > 0 else 0
        return int(round(self.total_depenses * 100 / enveloppe))

    @property
    def budget_depasse(self):
        return self.solde_disponible < 0

    def _taches_valides(self):
        return [t for t in self.taches.all() if t.statut != Tache.ANNULEE]

    @property
    def progression(self):
        taches = self._taches_valides()
        if not taches:
            return min(self.avancement, 100)
        return int(round(sum(t.progression for t in taches) / len(taches)))

    @property
    def nb_taches_en_retard(self):
        return sum(1 for t in self._taches_valides() if t.en_retard)

    @property
    def en_retard(self):
        return bool(self.statut in self.STATUTS_OUVERTS and self.date_fin_prevue
                    and timezone.localdate() > self.date_fin_prevue)

    @property
    def jours_restants(self):
        if self.date_fin_prevue and self.statut in self.STATUTS_OUVERTS:
            return (self.date_fin_prevue - timezone.localdate()).days
        return None


class Tache(EntrepriseModel):
    A_FAIRE, EN_COURS, EN_PAUSE, BLOQUEE, TERMINEE, ANNULEE = (
        "a_faire", "en_cours", "en_pause", "bloquee", "terminee", "annulee")
    STATUTS = [(A_FAIRE, "À faire"), (EN_COURS, "En cours"), (EN_PAUSE, "En pause"), (BLOQUEE, "Bloquée"),
               (TERMINEE, "Terminée"), (ANNULEE, "Annulée")]
    STATUTS_OUVERTS = (A_FAIRE, EN_COURS, EN_PAUSE, BLOQUEE)
    BASSE, MOYENNE, HAUTE, CRITIQUE = "basse", "moyenne", "haute", "critique"
    PRIORITES = [(BASSE, "Basse"), (MOYENNE, "Moyenne"), (HAUTE, "Haute"), (CRITIQUE, "Critique")]

    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="taches", verbose_name="Projet")
    titre = models.CharField("Tâche", max_length=255)
    description = models.TextField("Description", blank=True)
    responsable = models.CharField("Responsable", max_length=150, blank=True)
    date_debut = models.DateField("Début", null=True, blank=True)
    date_fin_prevue = models.DateField("Échéance", null=True, blank=True)
    date_fin_reelle = models.DateField("Terminée le", null=True, blank=True)
    priorite = models.CharField("Priorité", max_length=10, choices=PRIORITES, default=MOYENNE)
    statut = models.CharField("Statut", max_length=10, choices=STATUTS, default=A_FAIRE, db_index=True)
    progression = models.PositiveSmallIntegerField("Progression (%)", default=0)
    ordre = models.PositiveIntegerField("Ordre", default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Tâche"
        verbose_name_plural = "Tâches"
        ordering = ["ordre", "date_debut", "id"]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        # Une tâche terminée est à 100 % et datée ; une tâche rouverte perd sa date de fin.
        if self.statut == self.TERMINEE:
            self.progression = 100
            self.date_fin_reelle = self.date_fin_reelle or timezone.localdate()
        elif self.date_fin_reelle and self.statut != self.ANNULEE:
            self.date_fin_reelle = None
        self.progression = min(self.progression or 0, 100)
        super().save(*args, **kwargs)

    @property
    def en_retard(self):
        return bool(self.statut in self.STATUTS_OUVERTS and self.date_fin_prevue
                    and timezone.localdate() > self.date_fin_prevue)

    @property
    def jours_retard(self):
        return (timezone.localdate() - self.date_fin_prevue).days if self.en_retard else 0


class Membre(EntrepriseModel):
    """Personne affectée à un projet (salarié, ouvrier, sous-traitant…)."""
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="membres", verbose_name="Projet")
    nom = models.CharField("Nom complet", max_length=200)
    role = models.CharField("Rôle / fonction", max_length=150, blank=True,
                            help_text="Ex. : chef de chantier, maçon, électricien, sous-traitant.")
    telephone = models.CharField("Téléphone", max_length=40, blank=True)
    date_debut = models.DateField("Affecté le", default=timezone.localdate)
    date_fin = models.DateField("Jusqu'au", null=True, blank=True)
    note = models.CharField("Note", max_length=255, blank=True)

    class Meta:
        verbose_name = "Membre de l'équipe"
        verbose_name_plural = "Équipe"
        ordering = ["date_fin", "nom"]

    def __str__(self):
        return self.nom

    @property
    def actif(self):
        return self.date_fin is None or self.date_fin >= timezone.localdate()


class Mouvement(EntrepriseModel):
    """Entrée ou sortie d'argent sur un projet."""
    DEPOT, RETRAIT, DEPENSE = "depot", "retrait", "depense"
    TYPES = [(DEPOT, "Dépôt (fonds reçus)"), (RETRAIT, "Retrait"), (DEPENSE, "Dépense")]
    CATEGORIES = [
        ("materiaux", "Achat de matériaux"), ("main_oeuvre", "Main-d'œuvre / paiement du personnel"),
        ("sous_traitance", "Sous-traitance"), ("equipement", "Équipement / location d'engins"),
        ("transport", "Transport / carburant"), ("etudes", "Études / honoraires"),
        ("administratif", "Frais administratifs"), ("autre", "Autre"),
    ]

    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="mouvements", verbose_name="Projet")
    type = models.CharField("Type", max_length=8, choices=TYPES, default=DEPENSE, db_index=True)
    categorie = models.CharField("Catégorie", max_length=15, choices=CATEGORIES, blank=True,
                                 help_text="Pour les dépenses.")
    date = models.DateField("Date", default=timezone.localdate)
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    libelle = models.CharField("Libellé", max_length=255)
    beneficiaire = models.CharField("Bénéficiaire / fournisseur", max_length=200, blank=True)
    mode = models.CharField("Mode de paiement", max_length=15, choices=MODES_PAIEMENT, default="especes")
    reference = models.CharField("Référence (n° de facture, de chèque…)", max_length=100, blank=True)
    piece = models.FileField("Pièce justificative", upload_to="projets/pieces/%Y/%m/", blank=True)
    saisi_par = models.CharField("Saisi par", max_length=150, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Mouvement financier"
        verbose_name_plural = "Mouvements financiers"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.libelle}"

    @property
    def signe(self):
        return 1 if self.type == self.DEPOT else -1
