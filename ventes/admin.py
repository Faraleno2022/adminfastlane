from django.contrib import admin

from . import models


class VentesAdmin(admin.ModelAdmin):
    list_filter = ("entreprise",)


for _modele in (
    models.ParametreVentes, models.ClientCompte, models.Produit, models.Operation, models.Vente,
    models.MouvementStock, models.EcritureCaisse, models.DemandeStock, models.JournalAudit,
):
    admin.site.register(_modele, VentesAdmin)
