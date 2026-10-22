"""Modèles du module Suivi des prêts (reprend le classeur « Suivi des Montants de Prêt »).

Un prêt porte une désignation, le montant prêté, le montant global à recouvrer
(capital + intérêt), la période (début / fin → durée) et une observation
(Payé / Impayé / En cours). Les remboursements partiels s'y rattachent.
Toutes les données sont isolées par entreprise.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from core.tenancy import EntrepriseModel

ZERO = Decimal("0")


class Pret(EntrepriseModel):
    EN_COURS, PAYE, IMPAYE = "en_cours", "paye", "impaye"
    STATUTS = [(EN_COURS, "En cours"), (PAYE, "Payé"), (IMPAYE, "Impayé")]

    designation = models.CharField("Désignation", max_length=255)
    montant_pret = models.DecimalField("Montant de prêt", max_digits=16, decimal_places=2, default=0)
    montant_a_recouvrer = models.DecimalField("Montant global à recouvrer", max_digits=16, decimal_places=2, default=0)
    valeur_interet = models.DecimalField("Valeur d'intérêt", max_digits=16, decimal_places=2, default=0)
    date_debut = models.DateField("Début", default=timezone.localdate)
    date_fin = models.DateField("Fin")
    observation = models.CharField("Observation", max_length=10, choices=STATUTS, default=EN_COURS, db_index=True)
    note = models.TextField("Note", blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Prêt"
        verbose_name_plural = "Prêts"
        ordering = ["-date_debut", "-id"]

    def __str__(self):
        return self.designation

    @property
    def duree_jours(self):
        return (self.date_fin - self.date_debut).days

    @property
    def total_rembourse(self):
        return self.remboursements.aggregate(t=Sum("montant"))["t"] or ZERO

    @property
    def reste_a_recouvrer(self):
        return max(self.montant_a_recouvrer - self.total_rembourse, ZERO)

    @property
    def est_echu(self):
        return self.observation != self.PAYE and self.date_fin < timezone.localdate()

    def synchroniser_statut(self):
        """Un prêt entièrement remboursé passe à « Payé » ; le statut est sinon laissé tel quel."""
        if self.montant_a_recouvrer > 0 and self.reste_a_recouvrer <= 0 and self.observation != self.PAYE:
            self.observation = self.PAYE
            self.save(update_fields=["observation"])


class Remboursement(EntrepriseModel):
    pret = models.ForeignKey(Pret, on_delete=models.CASCADE, related_name="remboursements")
    date = models.DateField("Date", default=timezone.localdate)
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    note = models.CharField("Note", max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Remboursement"
        verbose_name_plural = "Remboursements"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.pret} — {self.montant}"
