"""URLs du module Gestion de projet (préfixe /projets/, espace de noms « projets »)."""
from django.urls import path

from core.decorators import entreprise_active_required

from . import views as v

app_name = "projets"


def _p(vue):
    """Exige un compte rattaché à une entreprise active (comme les autres modules)."""
    return entreprise_active_required(vue)


urlpatterns = [
    path("", _p(v.tableau_de_bord), name="tableau_de_bord"),

    # Projets
    path("liste/", _p(v.projets), name="projets"),
    path("nouveau/", _p(v.projet_nouveau), name="projet_nouveau"),
    path("<int:pk>/", _p(v.projet_detail), name="projet_detail"),
    path("<int:pk>/modifier/", _p(v.projet_modifier), name="projet_modifier"),
    path("<int:pk>/statut/", _p(v.projet_statut), name="projet_statut"),
    path("<int:pk>/supprimer/", _p(v.projet_supprimer), name="projet_supprimer"),
    path("<int:pk>/fiche/", _p(v.fiche), name="fiche"),

    # Tâches (planning)
    path("taches/", _p(v.taches), name="taches"),
    path("<int:pk>/tache/", _p(v.tache_nouvelle), name="tache_nouvelle"),
    path("taches/<int:pk>/modifier/", _p(v.tache_modifier), name="tache_modifier"),
    path("taches/<int:pk>/statut/", _p(v.tache_statut), name="tache_statut"),
    path("taches/<int:pk>/supprimer/", _p(v.tache_supprimer), name="tache_supprimer"),

    # Équipe
    path("<int:pk>/membre/", _p(v.membre_nouveau), name="membre_nouveau"),
    path("membres/<int:pk>/modifier/", _p(v.membre_modifier), name="membre_modifier"),
    path("membres/<int:pk>/supprimer/", _p(v.membre_supprimer), name="membre_supprimer"),

    # Mouvements financiers
    path("mouvements/", _p(v.mouvements), name="mouvements"),
    path("<int:pk>/mouvement/", _p(v.mouvement_nouveau), name="mouvement_nouveau"),
    path("mouvements/<int:pk>/modifier/", _p(v.mouvement_modifier), name="mouvement_modifier"),
    path("mouvements/<int:pk>/supprimer/", _p(v.mouvement_supprimer), name="mouvement_supprimer"),
    path("mouvements/<int:pk>/piece/", _p(v.mouvement_piece), name="mouvement_piece"),

    # Clients
    path("clients/", _p(v.clients), name="clients"),
    path("clients/nouveau/", _p(v.client_nouveau), name="client_nouveau"),
    path("clients/<int:pk>/", _p(v.client_detail), name="client_detail"),
    path("clients/<int:pk>/modifier/", _p(v.client_modifier), name="client_modifier"),
    path("clients/<int:pk>/supprimer/", _p(v.client_supprimer), name="client_supprimer"),

    # Rapports
    path("rapports/", _p(v.rapports), name="rapports"),
]
