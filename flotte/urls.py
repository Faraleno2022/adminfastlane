"""URLs du module Gestion de flotte (préfixe /flotte/, espace de noms « flotte »)."""
from django.urls import path

from core.decorators import entreprise_active_required

from . import (
    views_dashboard,
    views_operations as ops,
    views_pointage,
    views_rapports,
    views_referentiel as ref,
    views_stock,
)

app_name = "flotte"


def _protege(vue):
    """Exige un compte rattaché à une entreprise active (comme les autres modules)."""
    if hasattr(vue, "as_view"):
        vue = vue.as_view()
    return entreprise_active_required(vue)


def _crud(prefixe, nom, liste, creer, modifier, supprimer):
    return [
        path(f"{prefixe}/", _protege(liste), name=f"{nom}_liste"),
        path(f"{prefixe}/ajouter/", _protege(creer), name=f"{nom}_creer"),
        path(f"{prefixe}/<uuid:pk>/modifier/", _protege(modifier), name=f"{nom}_modifier"),
        path(f"{prefixe}/<uuid:pk>/supprimer/", _protege(supprimer), name=f"{nom}_supprimer"),
    ]


urlpatterns = [
    # Tableau de bord et analyses
    path("", _protege(views_dashboard.accueil), name="accueil"),
    path("analyses/", _protege(views_dashboard.analyses), name="analyses"),

    # Référentiel
    *_crud("referentiel/categories", "categorie",
           ref.CategorieListe, ref.CategorieCreer, ref.CategorieModifier, ref.CategorieSupprimer),
    *_crud("referentiel/marques", "marque",
           ref.MarqueListe, ref.MarqueCreer, ref.MarqueModifier, ref.MarqueSupprimer),
    *_crud("referentiel/chauffeurs", "chauffeur",
           ref.ChauffeurListe, ref.ChauffeurCreer, ref.ChauffeurModifier, ref.ChauffeurSupprimer),
    *_crud("referentiel/vehicules", "vehicule",
           ref.VehiculeListe, ref.VehiculeCreer, ref.VehiculeModifier, ref.VehiculeSupprimer),
    path("referentiel/vehicules/<uuid:pk>/", _protege(ref.vehicule_detail), name="vehicule_detail"),
    path("referentiel/documents/", _protege(ref.document_liste), name="document_liste"),
    path("referentiel/documents/ajouter/", _protege(ref.DocumentCreer), name="document_creer"),
    path("referentiel/documents/<uuid:pk>/modifier/", _protege(ref.DocumentModifier), name="document_modifier"),
    path("referentiel/documents/<uuid:pk>/supprimer/", _protege(ref.DocumentSupprimer), name="document_supprimer"),
    path("referentiel/documents/<uuid:pk>/fichier/", _protege(ref.document_fichier), name="document_fichier"),
    *_crud("referentiel/engins", "engin",
           ref.EnginListe, ref.EnginCreer, ref.EnginModifier, ref.EnginSupprimer),

    # Saisie
    *_crud("entretien", "entretien",
           ops.EntretienListe, ops.EntretienCreer, ops.EntretienModifier, ops.EntretienSupprimer),
    *_crud("carburant", "carburant",
           ops.PleinListe, ops.PleinCreer, ops.PleinModifier, ops.PleinSupprimer),
    *_crud("voyages", "voyage",
           ops.VoyageListe, ops.VoyageCreer, ops.VoyageModifier, ops.VoyageSupprimer),
    *_crud("poclain", "poclain",
           ops.ActiviteListe, ops.ActiviteCreer, ops.ActiviteModifier, ops.ActiviteSupprimer),
    *_crud("porte-char", "portechar",
           ops.TrajetListe, ops.TrajetCreer, ops.TrajetModifier, ops.TrajetSupprimer),
    *_crud("depenses", "depense",
           ops.DepenseListe, ops.DepenseCreer, ops.DepenseModifier, ops.DepenseSupprimer),

    # Pointage
    path("pointage/", _protege(views_pointage.grille), name="grille"),
    path("pointage/enregistrer/", _protege(views_pointage.enregistrer), name="enregistrer"),
    *_crud("pointage/employes", "employe",
           views_pointage.EmployeListe, views_pointage.EmployeCreer,
           views_pointage.EmployeModifier, views_pointage.EmployeSupprimer),

    # Stock de la flotte
    path("stock/", _protege(views_stock.inventaire), name="inventaire"),
    path("stock/synthese/", _protege(views_stock.synthese), name="synthese"),
    path("stock/articles/ajouter/", _protege(views_stock.ArticleCreer), name="article_creer"),
    path("stock/articles/<uuid:pk>/modifier/", _protege(views_stock.ArticleModifier), name="article_modifier"),
    path("stock/articles/<uuid:pk>/supprimer/", _protege(views_stock.ArticleSupprimer), name="article_supprimer"),
    *_crud("stock/mouvements", "mouvement",
           views_stock.MouvementListe, views_stock.MouvementCreer,
           views_stock.MouvementModifier, views_stock.MouvementSupprimer),

    # Rapports
    path("rapports/mensuel/", _protege(views_rapports.rapport_mensuel), name="rapport_mensuel"),
    path("rapports/charges-entretien/", _protege(views_rapports.charges_entretien),
         name="rapport_charges_entretien"),
    path("rapports/carburant/", _protege(views_rapports.consommation_carburant), name="rapport_carburant"),
    path("rapports/poclain/", _protege(views_rapports.analyse_poclain), name="rapport_poclain"),
    path("rapports/excel/", _protege(views_rapports.export_excel), name="export_excel"),
    path("rapports/pdf/", _protege(views_rapports.export_pdf), name="export_pdf"),
]
