"""URLs du module Ventes & caisse (préfixe /ventes/, espace de noms « ventes »)."""
from django.urls import path

from core.decorators import entreprise_active_required

from . import views as v

app_name = "ventes"


def _p(vue):
    """Exige un compte rattaché à une entreprise active (comme les autres modules)."""
    return entreprise_active_required(vue)


urlpatterns = [
    path("", _p(v.tableau_de_bord), name="tableau_de_bord"),

    # Clients
    path("clients/", _p(v.clients), name="clients"),
    path("clients/nouveau/", _p(v.client_nouveau), name="client_nouveau"),
    path("clients/<int:pk>/modifier/", _p(v.client_modifier), name="client_modifier"),
    path("clients/<int:pk>/basculer/", _p(v.client_basculer), name="client_basculer"),
    path("api/solde/", _p(v.solde_api), name="solde_api"),

    # Dépôts, retraits, ventes
    path("depot/", _p(v.depot_nouveau), name="depot_nouveau"),
    path("retrait/", _p(v.retrait_nouveau), name="retrait_nouveau"),
    path("operations/", _p(v.operations), name="operations"),
    path("operations/<int:pk>/supprimer/", _p(v.operation_supprimer), name="operation_supprimer"),
    path("ventes/", _p(v.ventes), name="ventes"),
    path("ventes/<int:pk>/supprimer/", _p(v.vente_supprimer), name="vente_supprimer"),
    path("ticket/<str:kind>/<int:pk>/", _p(v.ticket), name="ticket"),

    # Caisse
    path("caisse/", _p(v.caisse), name="caisse"),
    path("caisse/ecriture/", _p(v.ecriture_nouvelle), name="ecriture_nouvelle"),
    path("caisse/ecriture/<int:pk>/annuler/", _p(v.ecriture_annuler), name="ecriture_annuler"),

    # Produits et stock
    path("produits/", _p(v.produits), name="produits"),
    path("produits/nouveau/", _p(v.produit_nouveau), name="produit_nouveau"),
    path("produits/<int:pk>/modifier/", _p(v.produit_modifier), name="produit_modifier"),
    path("produits/<int:pk>/basculer/", _p(v.produit_basculer), name="produit_basculer"),
    path("produits/<int:pk>/stock/", _p(v.stock_ajuster), name="stock_ajuster"),
    path("produits/<int:pk>/demande-entree/", _p(v.demande_entree), name="demande_entree"),
    path("produits/demande-nouveau/", _p(v.demande_produit), name="demande_produit"),
    path("api/produits/recherche/", _p(v.produit_recherche_api), name="produit_recherche_api"),
    path("stock/validations/", _p(v.validations), name="validations"),
    path("stock/validations/<int:pk>/valider/", _p(v.demande_valider), name="demande_valider"),
    path("stock/validations/<int:pk>/rejeter/", _p(v.demande_rejeter), name="demande_rejeter"),
    path("mouvements/", _p(v.mouvements), name="mouvements"),
    path("inventaire/", _p(v.inventaire), name="inventaire"),

    # Corbeille
    path("corbeille/", _p(v.corbeille), name="corbeille"),
    path("corbeille/operation/<int:pk>/restaurer/", _p(v.operation_restaurer), name="operation_restaurer"),
    path("corbeille/vente/<int:pk>/restaurer/", _p(v.vente_restaurer), name="vente_restaurer"),
    path("corbeille/produit/<int:pk>/restaurer/", _p(v.produit_restaurer), name="produit_restaurer"),
    path("corbeille/client/<int:pk>/restaurer/", _p(v.client_restaurer), name="client_restaurer"),

    # Rapports, journal, paramètres
    path("rapports/", _p(v.rapports), name="rapports"),
    path("journal/", _p(v.journal), name="journal"),
    path("parametres/", _p(v.parametres), name="parametres"),
]
