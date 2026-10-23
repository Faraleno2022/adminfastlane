from django.contrib import admin

from . import models


class ProjetsAdmin(admin.ModelAdmin):
    list_filter = ("entreprise",)


for _modele in (models.Client, models.Projet, models.Tache, models.Membre, models.Mouvement):
    admin.site.register(_modele, ProjetsAdmin)
