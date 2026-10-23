from django import forms

from .models import Citerne, Client, FraisVoyage, Paiement, Voyage


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


def _pourcentage(form, champ):
    valeur = form.cleaned_data.get(champ)
    if valeur is not None and valeur > 100:
        form.add_error(champ, "Le pourcentage ne peut pas dépasser 100.")


class ClientForm(_Bootstrap):
    class Meta:
        model = Client
        fields = ["nom", "contact", "telephone", "email", "adresse", "nif", "tarif_litre", "tolerance_pct", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        _positif(self, ("tarif_litre", "tolerance_pct"))
        _pourcentage(self, "tolerance_pct")
        return data


class CiterneForm(_Bootstrap):
    class Meta:
        model = Citerne
        fields = ["immatriculation", "vehicule", "capacite", "nb_compartiments", "numero_barremage",
                  "expiration_barremage", "active", "note"]
        widgets = {"expiration_barremage": _date()}

    def clean_capacite(self):
        capacite = self.cleaned_data["capacite"]
        if capacite <= 0:
            raise forms.ValidationError("La capacité doit être positive.")
        return capacite


class VoyageForm(_Bootstrap):
    """Planification et conditions de facturation. Tarif et tolérance vides = ceux du client."""

    class Meta:
        model = Voyage
        fields = ["client", "citerne", "vehicule", "chauffeur", "produit", "lieu_chargement", "destination",
                  "date_prevue", "base_facturation", "tarif_litre", "forfait", "tolerance_pct", "prix_produit", "note"]
        widgets = {"date_prevue": _date(), "note": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["citerne"].queryset = Citerne.objects.filter(active=True) if not self.instance.pk \
            else Citerne.objects.all()
        for champ in ("tarif_litre", "tolerance_pct", "forfait", "prix_produit"):
            self.fields[champ].required = False
        self.fields["tarif_litre"].help_text = "Laisser vide pour appliquer le tarif du client."
        self.fields["tolerance_pct"].help_text = "Laisser vide pour appliquer la tolérance du client."

    def clean(self):
        data = super().clean()
        client = data.get("client")
        if data.get("tarif_litre") is None:
            data["tarif_litre"] = client.tarif_litre if client else 0
        if data.get("tolerance_pct") is None:
            data["tolerance_pct"] = client.tolerance_pct if client else 0
        for champ in ("forfait", "prix_produit"):
            if data.get(champ) is None:
                data[champ] = 0
        _positif(self, ("tarif_litre", "forfait", "tolerance_pct", "prix_produit"))
        _pourcentage(self, "tolerance_pct")
        if data.get("base_facturation") == Voyage.FORFAIT and not data.get("forfait"):
            self.add_error("forfait", "Indiquez le montant du forfait.")
        elif data.get("base_facturation") in (Voyage.LIVREE, Voyage.CHARGEE) and not data.get("tarif_litre"):
            self.add_error("tarif_litre", "Indiquez le tarif par litre (ou renseignez-le sur la fiche du client).")
        return data


class ChargementForm(_Bootstrap):
    """Chargement au dépôt : contrôle la capacité, le barémage et la disponibilité de la citerne."""

    class Meta:
        model = Voyage
        fields = ["date_chargement", "bon_chargement", "quantite_chargee"]
        widgets = {"date_chargement": _date()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.required = True

    def clean(self):
        data = super().clean()
        voyage, citerne = self.instance, self.instance.citerne
        quantite = data.get("quantite_chargee")
        if quantite is not None:
            if quantite <= 0:
                self.add_error("quantite_chargee", "La quantité doit être positive.")
            elif quantite > citerne.capacite:
                self.add_error("quantite_chargee",
                               f"Dépasse la capacité de la citerne ({citerne.capacite:,.0f} L).".replace(",", " "))
        if citerne.etat_barremage == Citerne.EXPIRE:
            raise forms.ValidationError("Le certificat de barémage de cette citerne a expiré : chargement refusé.")
        occupee = Voyage.objects.filter(citerne=citerne, statut=Voyage.EN_ROUTE).exclude(pk=voyage.pk).first()
        if occupee:
            raise forms.ValidationError(f"Cette citerne est déjà en route (voyage {occupee.reference}).")
        return data


class LivraisonForm(_Bootstrap):
    class Meta:
        model = Voyage
        fields = ["date_livraison", "bon_livraison", "quantite_livree"]
        widgets = {"date_livraison": _date()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_livraison"].required = True
        self.fields["quantite_livree"].required = True

    def clean(self):
        data = super().clean()
        quantite = data.get("quantite_livree")
        if quantite is not None and quantite <= 0:
            self.add_error("quantite_livree", "La quantité doit être positive.")
        livraison, chargement = data.get("date_livraison"), self.instance.date_chargement
        if livraison and chargement and livraison < chargement:
            self.add_error("date_livraison", "La livraison ne peut pas précéder le chargement.")
        return data


class FraisForm(_Bootstrap):
    class Meta:
        model = FraisVoyage
        fields = ["type", "date", "montant", "note"]
        widgets = {"date": _date()}

    def clean_montant(self):
        montant = self.cleaned_data["montant"]
        if montant <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return montant


class PaiementForm(_Bootstrap):
    class Meta:
        model = Paiement
        fields = ["date", "montant", "mode", "reference", "note"]
        widgets = {"date": _date()}

    def clean_montant(self):
        montant = self.cleaned_data["montant"]
        if montant <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return montant
