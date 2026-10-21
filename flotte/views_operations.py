"""Vues de saisie : entretien, carburant, voyages, Poclain, porte-char, autres dépenses."""
from django.urls import reverse_lazy

from .forms import (
    ActiviteEnginForm, AutreDepenseForm, EntretienForm, PleinCarburantForm,
    TrajetPorteCharForm, VoyageForm,
)
from .mixins import BaseCreer, BaseListe, BaseModifier, BaseSupprimer
from .models import (
    ActiviteEngin, AutreDepense, Entretien, PleinCarburant, TrajetPorteChar, Voyage,
)

class EntretienListe(BaseListe):
    model = Entretien
    titre = "Entretiens & Réparations"
    colonnes = [
        ("Date", "date"),
        ("Véhicule", "vehicule"),
        ("Garage", "garage"),
        ("Nature", "nature_operations"),
        ("Montant TTC", "montant_ttc"),
    ]
    url_creer = "flotte:entretien_creer"
    url_modifier = "flotte:entretien_modifier"
    url_supprimer = "flotte:entretien_supprimer"

    def get_queryset(self):
        return super().get_queryset().select_related("vehicule", "chauffeur")


class EntretienCreer(BaseCreer):
    model = Entretien
    form_class = EntretienForm
    success_url = reverse_lazy("flotte:entretien_liste")
    titre = "Ajouter un entretien"


class EntretienModifier(BaseModifier):
    model = Entretien
    form_class = EntretienForm
    success_url = reverse_lazy("flotte:entretien_liste")
    titre = "Modifier l'entretien"


class EntretienSupprimer(BaseSupprimer):
    model = Entretien
    success_url = reverse_lazy("flotte:entretien_liste")


class PleinListe(BaseListe):
    model = PleinCarburant
    titre = "Pleins de carburant"
    colonnes = [
        ("Date", "date"),
        ("Véhicule", "vehicule"),
        ("Litres", "litres"),
        ("Prix/L", "prix_litre"),
        ("Montant", "montant"),
    ]
    url_creer = "flotte:carburant_creer"
    url_modifier = "flotte:carburant_modifier"
    url_supprimer = "flotte:carburant_supprimer"

    def get_queryset(self):
        return super().get_queryset().select_related("vehicule", "chauffeur")


class PleinCreer(BaseCreer):
    model = PleinCarburant
    form_class = PleinCarburantForm
    success_url = reverse_lazy("flotte:carburant_liste")
    titre = "Ajouter un plein"


class PleinModifier(BaseModifier):
    model = PleinCarburant
    form_class = PleinCarburantForm
    success_url = reverse_lazy("flotte:carburant_liste")
    titre = "Modifier le plein"


class PleinSupprimer(BaseSupprimer):
    model = PleinCarburant
    success_url = reverse_lazy("flotte:carburant_liste")


class VoyageListe(BaseListe):
    model = Voyage
    titre = "Voyages"
    colonnes = [
        ("Date", "date"),
        ("Véhicule", "vehicule"),
        ("Chauffeur", "chauffeur"),
        ("Nb voyages", "nb_voyage"),
        ("Montant", "montant"),
    ]
    url_creer = "flotte:voyage_creer"
    url_modifier = "flotte:voyage_modifier"
    url_supprimer = "flotte:voyage_supprimer"

    def get_queryset(self):
        return super().get_queryset().select_related("vehicule", "chauffeur")


class VoyageCreer(BaseCreer):
    model = Voyage
    form_class = VoyageForm
    success_url = reverse_lazy("flotte:voyage_liste")
    titre = "Ajouter un voyage"


class VoyageModifier(BaseModifier):
    model = Voyage
    form_class = VoyageForm
    success_url = reverse_lazy("flotte:voyage_liste")
    titre = "Modifier le voyage"


class VoyageSupprimer(BaseSupprimer):
    model = Voyage
    success_url = reverse_lazy("flotte:voyage_liste")


class ActiviteListe(BaseListe):
    model = ActiviteEngin
    titre = "Activités Poclain"
    colonnes = [
        ("Date", "date"),
        ("Engin", "engin"),
        ("Roues", "categorie_roues"),
        ("Nb chargements", "nb_chargement"),
        ("Montant chargement", "montant_chargement"),
        ("Carburant (L)", "qte_carburant"),
        ("Montant carburant", "montant_carburant"),
    ]
    url_creer = "flotte:poclain_creer"
    url_modifier = "flotte:poclain_modifier"
    url_supprimer = "flotte:poclain_supprimer"

    def get_queryset(self):
        return super().get_queryset().select_related("engin", "categorie_roues")


class ActiviteCreer(BaseCreer):
    model = ActiviteEngin
    form_class = ActiviteEnginForm
    success_url = reverse_lazy("flotte:poclain_liste")
    titre = "Ajouter une activité Poclain"


class ActiviteModifier(BaseModifier):
    model = ActiviteEngin
    form_class = ActiviteEnginForm
    success_url = reverse_lazy("flotte:poclain_liste")
    titre = "Modifier l'activité"


class ActiviteSupprimer(BaseSupprimer):
    model = ActiviteEngin
    success_url = reverse_lazy("flotte:poclain_liste")


class TrajetListe(BaseListe):
    model = TrajetPorteChar
    titre = "Trajets porte-char"
    colonnes = [
        ("Date", "date"),
        ("Engin", "engin"),
        ("Départ", "point_depart"),
        ("Arrivée", "point_arrivee"),
        ("Montant payé", "montant_paye"),
    ]
    url_creer = "flotte:portechar_creer"
    url_modifier = "flotte:portechar_modifier"
    url_supprimer = "flotte:portechar_supprimer"

    def get_queryset(self):
        return super().get_queryset().select_related("engin")


class TrajetCreer(BaseCreer):
    model = TrajetPorteChar
    form_class = TrajetPorteCharForm
    success_url = reverse_lazy("flotte:portechar_liste")
    titre = "Ajouter un trajet"


class TrajetModifier(BaseModifier):
    model = TrajetPorteChar
    form_class = TrajetPorteCharForm
    success_url = reverse_lazy("flotte:portechar_liste")
    titre = "Modifier le trajet"


class TrajetSupprimer(BaseSupprimer):
    model = TrajetPorteChar
    success_url = reverse_lazy("flotte:portechar_liste")


class DepenseListe(BaseListe):
    model = AutreDepense
    titre = "Autres dépenses"
    colonnes = [
        ("Date", "date"),
        ("Désignation", "designation"),
        ("PU", "prix_unitaire"),
        ("Quantité", "quantite"),
        ("Montant", "montant"),
    ]
    url_creer = "flotte:depense_creer"
    url_modifier = "flotte:depense_modifier"
    url_supprimer = "flotte:depense_supprimer"


class DepenseCreer(BaseCreer):
    model = AutreDepense
    form_class = AutreDepenseForm
    success_url = reverse_lazy("flotte:depense_liste")
    titre = "Ajouter une dépense"


class DepenseModifier(BaseModifier):
    model = AutreDepense
    form_class = AutreDepenseForm
    success_url = reverse_lazy("flotte:depense_liste")
    titre = "Modifier la dépense"


class DepenseSupprimer(BaseSupprimer):
    model = AutreDepense
    success_url = reverse_lazy("flotte:depense_liste")
