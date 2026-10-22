"""URLs du module Suivi des prêts (préfixe /prets/, espace de noms « prets »)."""
from django.urls import path

from core.decorators import entreprise_active_required

from . import views as v

app_name = "prets"


def _p(vue):
    """Exige un compte rattaché à une entreprise active (comme les autres modules)."""
    return entreprise_active_required(vue)


urlpatterns = [
    path("", _p(v.tableau_de_bord), name="tableau_de_bord"),
    path("liste/", _p(v.prets), name="liste"),
    path("nouveau/", _p(v.pret_nouveau), name="nouveau"),
    path("<int:pk>/", _p(v.pret_detail), name="detail"),
    path("<int:pk>/modifier/", _p(v.pret_modifier), name="modifier"),
    path("<int:pk>/supprimer/", _p(v.pret_supprimer), name="supprimer"),
    path("<int:pk>/remboursement/", _p(v.remboursement_ajouter), name="remboursement_ajouter"),
    path("remboursement/<int:pk>/supprimer/", _p(v.remboursement_supprimer), name="remboursement_supprimer"),
]
