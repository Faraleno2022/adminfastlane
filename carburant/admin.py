from django.contrib import admin

from . import models


class CarburantAdmin(admin.ModelAdmin):
    list_filter = ("entreprise",)


for _modele in (models.Client, models.Citerne, models.Voyage, models.FraisVoyage, models.Paiement):
    admin.site.register(_modele, CarburantAdmin)
