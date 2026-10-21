from django import forms

from .models import ClientCompte, ParametreVentes, Produit
from .services import produit_en_double


class _Bootstrap(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            w = champ.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


class ClientForm(_Bootstrap):
    class Meta:
        model = ClientCompte
        fields = ["matricule", "nom", "telephone", "note"]

    def clean_matricule(self):
        valeur = self.cleaned_data["matricule"].strip()
        qs = ClientCompte.objects.filter(matricule__iexact=valeur)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ce matricule a déjà une fiche client.")
        return valeur


class ProduitForm(_Bootstrap):
    class Meta:
        model = Produit
        fields = [
            "reference", "nom", "categorie", "unite", "prix_unitaire", "prix_achat",
            "seuil_alerte", "stock_max", "emplacement", "suivi_stock", "description",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        nom, ref = data.get("nom"), data.get("reference") or ""
        if nom:
            double = produit_en_double(nom, ref)
            if double is not None and double.pk != self.instance.pk:
                raise forms.ValidationError(f"Un produit « {double.nom} » existe déjà (même nom ou référence).")
        for champ in ("prix_unitaire", "prix_achat", "seuil_alerte", "stock_max"):
            if data.get(champ) is not None and data[champ] < 0:
                self.add_error(champ, "La valeur ne peut pas être négative.")
        return data


class ParametresForm(_Bootstrap):
    class Meta:
        model = ParametreVentes
        fields = ["plafond_depot_journalier", "devise", "ticket_titre", "ticket_adresse", "ticket_pied"]
