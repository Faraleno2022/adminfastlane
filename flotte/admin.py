from django.contrib import admin

from . import models


class FlotteAdmin(admin.ModelAdmin):
    """Administration : tous les enregistrements (y compris supprimés logiquement)."""

    list_filter = ("entreprise", "is_deleted")

    def get_queryset(self, request):
        return self.model.all_objects.all()


for _modele in (
    models.CategorieRoues, models.Marque, models.Chauffeur, models.Vehicule,
    models.DocumentVehicule, models.Engin, models.Entretien, models.PleinCarburant,
    models.Voyage, models.ActiviteEngin, models.TrajetPorteChar, models.AutreDepense,
    models.EmployeFlotte, models.Pointage, models.Article, models.MouvementStock,
):
    admin.site.register(_modele, FlotteAdmin)
