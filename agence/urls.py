"""URLs du module Agence de voyage (préfixe /agence/, espace de noms « agence »)."""
from django.urls import path

from core.decorators import entreprise_active_required

from . import views as v

app_name = "agence"


def _p(vue):
    """Exige un compte rattaché à une entreprise active (comme les autres modules)."""
    return entreprise_active_required(vue)


urlpatterns = [
    path("", _p(v.tableau_de_bord), name="tableau_de_bord"),

    # Clients
    path("clients/", _p(v.clients), name="clients"),
    path("clients/nouveau/", _p(v.client_nouveau), name="client_nouveau"),
    path("clients/<int:pk>/", _p(v.client_detail), name="client_detail"),
    path("clients/<int:pk>/modifier/", _p(v.client_modifier), name="client_modifier"),
    path("clients/<int:pk>/supprimer/", _p(v.client_supprimer), name="client_supprimer"),

    # Fournisseurs
    path("fournisseurs/", _p(v.fournisseurs), name="fournisseurs"),
    path("fournisseurs/nouveau/", _p(v.fournisseur_nouveau), name="fournisseur_nouveau"),
    path("fournisseurs/<int:pk>/", _p(v.fournisseur_detail), name="fournisseur_detail"),
    path("fournisseurs/<int:pk>/modifier/", _p(v.fournisseur_modifier), name="fournisseur_modifier"),
    path("fournisseurs/<int:pk>/supprimer/", _p(v.fournisseur_supprimer), name="fournisseur_supprimer"),

    # Dossiers de voyage
    path("dossiers/", _p(v.dossiers), name="dossiers"),
    path("dossiers/nouveau/", _p(v.dossier_nouveau), name="dossier_nouveau"),
    path("dossiers/<int:pk>/", _p(v.dossier_detail), name="dossier_detail"),
    path("dossiers/<int:pk>/modifier/", _p(v.dossier_modifier), name="dossier_modifier"),
    path("dossiers/<int:pk>/statut/", _p(v.dossier_statut), name="dossier_statut"),
    path("dossiers/<int:pk>/supprimer/", _p(v.dossier_supprimer), name="dossier_supprimer"),
    path("dossiers/<int:pk>/document/", _p(v.document), name="document"),

    # Prestations, voyageurs, paiements
    path("dossiers/<int:pk>/prestation/", _p(v.prestation_nouvelle), name="prestation_nouvelle"),
    path("prestations/<int:pk>/modifier/", _p(v.prestation_modifier), name="prestation_modifier"),
    path("prestations/<int:pk>/supprimer/", _p(v.prestation_supprimer), name="prestation_supprimer"),
    path("prestations/<int:pk>/reglement/", _p(v.paiement_fournisseur_nouveau), name="paiement_fournisseur_nouveau"),
    path("reglements/<int:pk>/supprimer/", _p(v.paiement_fournisseur_supprimer), name="paiement_fournisseur_supprimer"),
    path("dossiers/<int:pk>/voyageur/", _p(v.voyageur_nouveau), name="voyageur_nouveau"),
    path("voyageurs/<int:pk>/modifier/", _p(v.voyageur_modifier), name="voyageur_modifier"),
    path("voyageurs/<int:pk>/supprimer/", _p(v.voyageur_supprimer), name="voyageur_supprimer"),
    path("dossiers/<int:pk>/paiement/", _p(v.paiement_nouveau), name="paiement_nouveau"),
    path("paiements/<int:pk>/supprimer/", _p(v.paiement_supprimer), name="paiement_supprimer"),
    path("paiements/<int:pk>/recu/", _p(v.recu), name="recu"),

    # Rapports
    path("rapports/", _p(v.rapports), name="rapports"),
]
