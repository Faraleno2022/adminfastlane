"""
Module Gestion du Stock — Formulaires (ModelForms)
Le widget Bootstrap est appliqué automatiquement à tous les champs.
"""
from django import forms

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock, Inventaire,
)


class BootstrapModelForm(forms.ModelForm):
    """Applique les classes Bootstrap à tous les widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select')
            else:
                widget.attrs.setdefault('class', 'form-control')


class CategorieArticleForm(BootstrapModelForm):
    class Meta:
        model = CategorieArticle
        fields = ['nom', 'description', 'actif']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class FournisseurForm(BootstrapModelForm):
    class Meta:
        model = Fournisseur
        fields = ['nom', 'contact', 'telephone', 'email', 'adresse', 'nif', 'actif', 'observations']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'observations': forms.Textarea(attrs={'rows': 2}),
        }


class ArticleForm(BootstrapModelForm):
    class Meta:
        model = Article
        fields = ['reference', 'designation', 'categorie', 'fournisseur', 'unite',
                  'prix_achat', 'prix_vente', 'seuil_alerte', 'emplacement',
                  'description', 'actif']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['categorie'].queryset = CategorieArticle.objects.filter(entreprise=entreprise, actif=True)
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, actif=True)
        self.fields['categorie'].required = False
        self.fields['fournisseur'].required = False


class MouvementStockForm(BootstrapModelForm):
    class Meta:
        model = MouvementStock
        fields = ['article', 'type_mouvement', 'quantite', 'prix_unitaire',
                  'motif', 'reference_document', 'fournisseur', 'date_mouvement']
        widgets = {
            'date_mouvement': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'motif': forms.TextInput(),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, actif=True)
        self.fields['fournisseur'].required = False
        self.fields['date_mouvement'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
        self.fields['quantite'].help_text = (
            "Entrée/Sortie : quantité déplacée. Ajustement : nouvelle quantité réelle en stock."
        )

    def clean(self):
        cleaned = super().clean()
        quantite = cleaned.get('quantite')
        type_mouvement = cleaned.get('type_mouvement')
        if quantite is None:
            return cleaned
        # L'ajustement peut ramener le stock à 0 ; les entrées/sorties doivent être positives.
        if type_mouvement == 'ajustement':
            if quantite < 0:
                self.add_error('quantite', "La quantité ne peut pas être négative.")
        elif quantite <= 0:
            self.add_error('quantite', "La quantité doit être supérieure à zéro.")
        return cleaned


class InventaireForm(BootstrapModelForm):
    class Meta:
        model = Inventaire
        fields = ['date_inventaire', 'commentaire']
        widgets = {
            'date_inventaire': forms.DateInput(attrs={'type': 'date'}),
            'commentaire': forms.Textarea(attrs={'rows': 3}),
        }
