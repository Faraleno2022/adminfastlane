from django import forms

from .models import (
    Client, Dossier, Fournisseur, PaiementClient, PaiementFournisseur, Prestation, Voyageur,
)


def _date():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class _Bootstrap(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            if isinstance(champ, forms.ModelChoiceField):
                # Les listes sont construites à l'import (sans entreprise) : on les recalcule
                # pour qu'elles ne proposent que les données de l'entreprise courante.
                champ.queryset = champ.queryset.model.objects.all()
            w = champ.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


def _positif(form, champs):
    for champ in champs:
        valeur = form.cleaned_data.get(champ)
        if valeur is not None and valeur < 0:
            form.add_error(champ, "La valeur ne peut pas être négative.")


def _ordre_dates(form, debut, fin, message="La date de fin doit être postérieure au début."):
    d, f = form.cleaned_data.get(debut), form.cleaned_data.get(fin)
    if d and f and f < d:
        form.add_error(fin, message)


class ClientForm(_Bootstrap):
    class Meta:
        model = Client
        fields = ["nom", "telephone", "email", "adresse", "nationalite", "date_naissance",
                  "passeport_numero", "passeport_expiration", "note"]
        widgets = {"date_naissance": _date(), "passeport_expiration": _date(),
                   "note": forms.Textarea(attrs={"rows": 2})}


class FournisseurForm(_Bootstrap):
    class Meta:
        model = Fournisseur
        fields = ["nom", "type", "contact", "telephone", "email", "note"]


class DossierForm(_Bootstrap):
    class Meta:
        model = Dossier
        fields = ["client", "destination", "objet", "date_depart", "date_retour", "nb_voyageurs", "statut", "note"]
        widgets = {"date_depart": _date(), "date_retour": _date(), "note": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        _ordre_dates(self, "date_depart", "date_retour", "Le retour doit être postérieur au départ.")
        if data.get("nb_voyageurs") is not None and data["nb_voyageurs"] < 1:
            self.add_error("nb_voyageurs", "Au moins un voyageur.")
        return data


class PrestationForm(_Bootstrap):
    class Meta:
        model = Prestation
        fields = ["type", "description", "fournisseur", "reference_fournisseur", "date_debut", "date_fin",
                  "quantite", "prix_achat", "prix_vente", "statut"]
        widgets = {"date_debut": _date(), "date_fin": _date()}

    def clean(self):
        data = super().clean()
        _ordre_dates(self, "date_debut", "date_fin")
        _positif(self, ("quantite", "prix_achat", "prix_vente"))
        if data.get("quantite") is not None and data["quantite"] == 0:
            self.add_error("quantite", "La quantité doit être supérieure à zéro.")
        return data


class VoyageurForm(_Bootstrap):
    class Meta:
        model = Voyageur
        fields = ["nom", "date_naissance", "nationalite", "passeport_numero", "passeport_expiration", "note"]
        widgets = {"date_naissance": _date(), "passeport_expiration": _date()}


class PaiementClientForm(_Bootstrap):
    """Refuse un encaissement supérieur au reste à payer du dossier."""

    class Meta:
        model = PaiementClient
        fields = ["date", "montant", "mode", "reference", "note"]
        widgets = {"date": _date()}

    def __init__(self, *args, dossier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.dossier = dossier

    def clean_montant(self):
        montant = self.cleaned_data["montant"]
        if montant <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        if self.dossier is not None and montant > self.dossier.reste_a_payer:
            raise forms.ValidationError("Ce montant dépasse le reste à payer du dossier.")
        return montant


class PaiementFournisseurForm(_Bootstrap):
    """Refuse un règlement supérieur à ce que l'agence doit encore au fournisseur."""

    class Meta:
        model = PaiementFournisseur
        fields = ["date", "montant", "mode", "reference", "note"]
        widgets = {"date": _date()}

    def __init__(self, *args, prestation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.prestation = prestation

    def clean_montant(self):
        montant = self.cleaned_data["montant"]
        if montant <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        if self.prestation is not None and montant > self.prestation.reste_fournisseur:
            raise forms.ValidationError("Ce montant dépasse ce qui reste dû au fournisseur.")
        return montant
