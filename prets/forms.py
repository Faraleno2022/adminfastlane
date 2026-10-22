from django import forms

from .models import Pret, Remboursement


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


class PretForm(_Bootstrap):
    """Le montant à recouvrer ou l'intérêt peut rester vide : l'autre le déduit (capital + intérêt)."""

    class Meta:
        model = Pret
        fields = [
            "designation", "montant_pret", "valeur_interet", "montant_a_recouvrer",
            "date_debut", "date_fin", "observation", "note",
        ]
        widgets = {
            "date_debut": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valeur_interet"].required = False
        self.fields["montant_a_recouvrer"].required = False
        self.fields["montant_a_recouvrer"].help_text = "Laisser vide pour calculer : prêt + intérêt."
        self.fields["valeur_interet"].help_text = "Laisser vide pour calculer : à recouvrer − prêt."

    def clean(self):
        data = super().clean()
        pret = data.get("montant_pret")
        interet = data.get("valeur_interet")
        total = data.get("montant_a_recouvrer")
        for champ in ("montant_pret", "valeur_interet", "montant_a_recouvrer"):
            if data.get(champ) is not None and data[champ] < 0:
                self.add_error(champ, "La valeur ne peut pas être négative.")
        if pret is not None:
            if total is None and interet is None:
                data["valeur_interet"], data["montant_a_recouvrer"] = 0, pret
            elif total is None:
                data["montant_a_recouvrer"] = pret + interet
            elif interet is None:
                data["valeur_interet"] = total - pret
        debut, fin = data.get("date_debut"), data.get("date_fin")
        if debut and fin and fin < debut:
            self.add_error("date_fin", "La date de fin doit être postérieure au début.")
        return data


class RemboursementForm(_Bootstrap):
    class Meta:
        model = Remboursement
        fields = ["date", "montant", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean_montant(self):
        montant = self.cleaned_data["montant"]
        if montant <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return montant
