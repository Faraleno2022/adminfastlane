from django.contrib import admin

from . import models


class AgenceAdmin(admin.ModelAdmin):
    list_filter = ("entreprise",)


for _modele in (
    models.Client, models.Fournisseur, models.Dossier, models.Prestation, models.Voyageur,
    models.PaiementClient, models.PaiementFournisseur,
):
    admin.site.register(_modele, AgenceAdmin)
