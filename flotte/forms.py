"""Formulaires du module Gestion de flotte."""
from django import forms
from django.conf import settings

from .models import (
    ActiviteEngin, Article, AutreDepense, CategorieRoues, Chauffeur, DocumentVehicule,
    Engin, EmployeFlotte, Entretien, Marque, MouvementStock, PleinCarburant,
    TrajetPorteChar, Vehicule, Voyage,
)


class DateInputFr(forms.DateInput):
    input_type = "date"


class BootstrapModelForm(forms.ModelForm):
    """ModelForm appliquant automatiquement les classes Bootstrap."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            # Les listes déroulantes sont construites à l'import du code, avant de
            # connaître l'entreprise : on les recalcule pour la requête en cours.
            if isinstance(field, forms.ModelChoiceField):
                field.queryset = field.queryset.model._default_manager.all()
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.DateInput):
                widget.attrs.setdefault("class", "form-control")
                widget.input_type = "date"
            else:
                widget.attrs.setdefault("class", "form-control")


_BootstrapForm = BootstrapModelForm


def _deja_utilise(form, modele, champ, valeur):
    """Vrai si ``valeur`` existe déjà pour ce champ dans l'entreprise courante."""
    qs = modele.all_objects.filter(**{champ + "__iexact": valeur})
    if form.instance.pk:
        qs = qs.exclude(pk=form.instance.pk)
    return qs.exists()

class CategorieRouesForm(_BootstrapForm):
    class Meta:
        model = CategorieRoues
        fields = ["libelle"]

    def clean_libelle(self):
        valeur = self.cleaned_data["libelle"].strip()
        if _deja_utilise(self, CategorieRoues, "libelle", valeur):
            raise forms.ValidationError("Cette catégorie existe déjà.")
        return valeur


class MarqueForm(_BootstrapForm):
    class Meta:
        model = Marque
        fields = ["nom"]

    def clean_nom(self):
        valeur = self.cleaned_data["nom"].strip().upper()
        if _deja_utilise(self, Marque, "nom", valeur):
            raise forms.ValidationError("Cette marque existe déjà.")
        return valeur


class ChauffeurForm(_BootstrapForm):
    class Meta:
        model = Chauffeur
        fields = ["nom_prenoms", "telephone", "actif"]


class VehiculeForm(_BootstrapForm):
    class Meta:
        model = Vehicule
        fields = [
            "immatriculation",
            "marque",
            "type_vehicule",
            "capacite_tonnes",
            "numero_chassis",
            "chauffeur_actuel",
            "chauffeur_secondaire",
            "actif",
        ]

    def clean(self):
        data = super().clean()
        principal, second = data.get("chauffeur_actuel"), data.get("chauffeur_secondaire")
        if principal and second and principal == second:
            self.add_error("chauffeur_secondaire", "Le second chauffeur doit être différent du chauffeur principal.")
        if second and not principal:
            self.add_error("chauffeur_actuel", "Renseignez d'abord le chauffeur principal.")
        return data


class DocumentVehiculeForm(_BootstrapForm):
    class Meta:
        model = DocumentVehicule
        fields = [
            "vehicule",
            "type_document",
            "numero",
            "date_emission",
            "date_expiration",
            "fichier",
            "observations",
        ]
        widgets = {
            "date_emission": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_expiration": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            # Simple champ fichier : le lien « actuel » de Django pointerait
            # vers /media/, volontairement non servi publiquement.
            "fichier": forms.FileInput(
                attrs={"accept": ".pdf,.jpg,.jpeg,.png,.webp"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = Vehicule.objects.all()
        aide = f"PDF, JPG, PNG ou WEBP — {settings.DOCUMENTS_TAILLE_MAX_MO} Mo maximum."
        if self.instance.pk and self.instance.fichier:
            aide += " Laisser vide pour conserver le fichier actuel."
        self.fields["fichier"].help_text = aide

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        if fichier and getattr(fichier, "size", 0) > settings.DOCUMENTS_TAILLE_MAX_MO * 1024 * 1024:
            raise forms.ValidationError(
                f"Fichier trop volumineux (maximum {settings.DOCUMENTS_TAILLE_MAX_MO} Mo)."
            )
        return fichier

    def clean(self):
        data = super().clean()
        emission, expiration = data.get("date_emission"), data.get("date_expiration")
        if emission and expiration and expiration < emission:
            self.add_error("date_expiration", "La date d'expiration précède la date de délivrance.")
        return data


class EnginForm(_BootstrapForm):
    class Meta:
        model = Engin
        fields = ["nom", "type_engin", "capacite", "actif"]


class EntretienForm(BootstrapModelForm):
    class Meta:
        model = Entretien
        fields = [
            "date", "vehicule", "chauffeur", "n_facture",
            "km_depart", "km_arrivee", "garage",
            "nature_operations", "montant_ttc", "observation",
        ]
        widgets = {
            "date": DateInputFr(),
            "nature_operations": forms.Textarea(attrs={"rows": 2}),
        }


class PleinCarburantForm(BootstrapModelForm):
    class Meta:
        model = PleinCarburant
        fields = [
            "date", "vehicule", "chauffeur", "litres",
            "prix_litre", "kilometrage", "n_bon", "observation",
        ]
        widgets = {"date": DateInputFr()}


class VoyageForm(BootstrapModelForm):
    class Meta:
        model = Voyage
        fields = [
            "date", "vehicule", "chauffeur", "superviseur1", "superviseur2",
            "n_bon", "nb_voyage", "pu_voyage",
            "km_depart", "km_arrivee", "nb_heures",
        ]
        widgets = {"date": DateInputFr()}


class ActiviteEnginForm(BootstrapModelForm):
    class Meta:
        model = ActiviteEngin
        fields = [
            "date", "engin", "categorie_roues", "nb_chargement", "pu_chargement",
            "qte_carburant", "prix_litre", "observation",
        ]
        widgets = {"date": DateInputFr()}


class TrajetPorteCharForm(BootstrapModelForm):
    class Meta:
        model = TrajetPorteChar
        fields = [
            "date", "engin", "point_depart", "point_arrivee",
            "km_depart", "km_arrivee", "montant_paye", "observation",
        ]
        widgets = {"date": DateInputFr()}


class AutreDepenseForm(BootstrapModelForm):
    class Meta:
        model = AutreDepense
        fields = ["date", "designation", "prix_unitaire", "quantite", "observation"]
        widgets = {"date": DateInputFr()}


class EmployeFlotteForm(BootstrapModelForm):
    class Meta:
        model = EmployeFlotte
        fields = [
            "nom_complet", "matricule", "fonction", "service",
            "telephone", "numero_permis", "actif",
        ]


class ArticleForm(BootstrapModelForm):
    class Meta:
        model = Article
        fields = [
            "code", "designation", "specification", "categorie",
            "stock_initial", "seuil_mini", "observation",
        ]


class MouvementStockForm(BootstrapModelForm):
    class Meta:
        model = MouvementStock
        fields = ["date", "article", "type", "quantite", "motif", "responsable"]
        widgets = {"date": DateInputFr()}

