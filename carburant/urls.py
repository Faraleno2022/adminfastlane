"""URLs du module Transport de carburant (préfixe /carburant/, espace de noms « carburant »)."""
from django.urls import path

from core.decorators import entreprise_active_required

from . import views as v

app_name = "carburant"


def _p(vue):
    """Exige un compte rattaché à une entreprise active (comme les autres modules)."""
    return entreprise_active_required(vue)


urlpatterns = [
    path("", _p(v.tableau_de_bord), name="tableau_de_bord"),

    # Voyages
    path("voyages/", _p(v.voyages), name="voyages"),
    path("voyages/nouveau/", _p(v.voyage_nouveau), name="voyage_nouveau"),
    path("voyages/<int:pk>/", _p(v.voyage_detail), name="voyage_detail"),
    path("voyages/<int:pk>/modifier/", _p(v.voyage_modifier), name="voyage_modifier"),
    path("voyages/<int:pk>/chargement/", _p(v.voyage_chargement), name="voyage_chargement"),
    path("voyages/<int:pk>/livraison/", _p(v.voyage_livraison), name="voyage_livraison"),
    path("voyages/<int:pk>/statut/", _p(v.voyage_statut), name="voyage_statut"),
    path("voyages/<int:pk>/supprimer/", _p(v.voyage_supprimer), name="voyage_supprimer"),
    path("voyages/<int:pk>/bon/", _p(v.bon), name="bon"),
    path("voyages/<int:pk>/frais/", _p(v.frais_nouveau), name="frais_nouveau"),
    path("frais/<int:pk>/supprimer/", _p(v.frais_supprimer), name="frais_supprimer"),

    # Citernes
    path("citernes/", _p(v.citernes), name="citernes"),
    path("citernes/nouvelle/", _p(v.citerne_nouvelle), name="citerne_nouvelle"),
    path("citernes/<int:pk>/", _p(v.citerne_detail), name="citerne_detail"),
    path("citernes/<int:pk>/modifier/", _p(v.citerne_modifier), name="citerne_modifier"),
    path("citernes/<int:pk>/supprimer/", _p(v.citerne_supprimer), name="citerne_supprimer"),

    # Clients, paiements, relevés
    path("clients/", _p(v.clients), name="clients"),
    path("clients/nouveau/", _p(v.client_nouveau), name="client_nouveau"),
    path("clients/<int:pk>/", _p(v.client_detail), name="client_detail"),
    path("clients/<int:pk>/modifier/", _p(v.client_modifier), name="client_modifier"),
    path("clients/<int:pk>/supprimer/", _p(v.client_supprimer), name="client_supprimer"),
    path("clients/<int:pk>/releve/", _p(v.releve), name="releve"),
    path("clients/<int:pk>/paiement/", _p(v.paiement_nouveau), name="paiement_nouveau"),
    path("paiements/<int:pk>/supprimer/", _p(v.paiement_supprimer), name="paiement_supprimer"),
    path("paiements/<int:pk>/recu/", _p(v.recu), name="recu"),

    # Rapports
    path("rapports/", _p(v.rapports), name="rapports"),
]
