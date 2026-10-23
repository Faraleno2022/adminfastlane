from django import forms

from .models import Client, Membre, Mouvement, Projet, Tache


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


def _ordre_dates(form, debut, fin, message="La date de fin doit être postérieure au début."):
    d, f = form.cleaned_data.get(debut), form.cleaned_data.get(fin)
    if d and f and f < d:
        form.add_error(fin, message)


class ClientForm(_Bootstrap):
    class Meta:
        model = Client
        fields = ["nom", "contact", "telephone", "email", "adresse", "nif", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}


class ProjetForm(_Bootstrap):
    class Meta:
        model = Projet
        fields = ["nom", "client", "responsable", "budget", "date_debut", "date_fin_prevue", "date_fin_reelle",
                  "statut", "lieu", "ville", "avancement", "description"]
        widgets = {"date_debut": _date(), "date_fin_prevue": _date(), "date_fin_reelle": _date(),
                   "description": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        data = super().clean()
        _ordre_dates(self, "date_debut", "date_fin_prevue")
        _ordre_dates(self, "date_debut", "date_fin_reelle")
        _positif(self, ("budget",))
        _pourcentage(self, "avancement")
        return data


class TacheForm(_Bootstrap):
    class Meta:
        model = Tache
        fields = ["titre", "responsable", "date_debut", "date_fin_prevue", "priorite", "statut", "progression",
                  "ordre", "description"]
        widgets = {"date_debut": _date(), "date_fin_prevue": _date(), "description": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        _ordre_dates(self, "date_debut", "date_fin_prevue", "L'échéance doit être postérieure au début.")
        _pourcentage(self, "progression")
        return data


class MembreForm(_Bootstrap):
    class Meta:
        model = Membre
        fields = ["nom", "role", "telephone", "date_debut", "date_fin", "note"]
        widgets = {"date_debut": _date(), "date_fin": _date()}

    def clean(self):
        data = super().clean()
        _ordre_dates(self, "date_debut", "date_fin")
        return data


class MouvementForm(_Bootstrap):
    TAILLE_MAX = 5 * 1024 * 1024
    EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".webp")

    class Meta:
        model = Mouvement
        fields = ["type", "categorie", "date", "montant", "libelle", "beneficiaire", "mode", "reference", "piece"]
        widgets = {"date": _date()}

    def clean_montant(self):
        montant = self.cleaned_data["montant"]
        if montant <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return montant

    def clean_piece(self):
        piece = self.cleaned_data.get("piece")
        if piece and hasattr(piece, "size"):
            if piece.size > self.TAILLE_MAX:
                raise forms.ValidationError("Fichier trop volumineux (5 Mo maximum).")
            if not piece.name.lower().endswith(self.EXTENSIONS):
                raise forms.ValidationError("Formats acceptés : PDF, JPG, PNG, WEBP.")
        return piece

    def clean(self):
        data = super().clean()
        if data.get("type") == Mouvement.DEPENSE and not data.get("categorie"):
            self.add_error("categorie", "Indiquez la catégorie de la dépense.")
        elif data.get("type") in (Mouvement.DEPOT, Mouvement.RETRAIT):
            data["categorie"] = ""
        return data
