from django.contrib import admin

from . import models


class PretsAdmin(admin.ModelAdmin):
    list_filter = ("entreprise",)


for _modele in (models.Pret, models.Remboursement):
    admin.site.register(_modele, PretsAdmin)
