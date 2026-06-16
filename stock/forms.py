"""
Module Gestion du Stock — Formulaires (ModelForms)
Le widget Bootstrap est appliqué automatiquement à tous les champs.
"""
from django import forms

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock, Inventaire,
    Depot, Transfert,
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
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault('class', 'form-control')
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


class DepotForm(BootstrapModelForm):
    class Meta:
        model = Depot
        fields = ['nom', 'type_depot', 'code', 'adresse', 'responsable', 'telephone', 'par_defaut', 'actif']


class ArticleForm(BootstrapModelForm):
    class Meta:
        model = Article
        fields = ['reference', 'code_barres', 'designation', 'categorie', 'fournisseur', 'unite',
                  'prix_achat', 'prix_vente', 'seuil_alerte', 'stock_max', 'emplacement',
                  'photo', 'description', 'actif']
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
        self.fields['code_barres'].help_text = "Scannable avec une douchette (laisser vide pour saisir plus tard)."


class MouvementStockForm(BootstrapModelForm):
    # Les transferts passent par le formulaire dédié, pas ici.
    TYPES_MANUELS = (
        ('entree', 'Entrée'),
        ('sortie', 'Sortie'),
        ('ajustement', 'Ajustement'),
    )

    class Meta:
        model = MouvementStock
        fields = ['article', 'depot', 'type_mouvement', 'quantite', 'prix_unitaire',
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
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
        self.fields['type_mouvement'].choices = self.TYPES_MANUELS
        self.fields['depot'].required = True
        self.fields['fournisseur'].required = False
        self.fields['date_mouvement'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
        self.fields['quantite'].help_text = (
            "Entrée/Sortie : quantité déplacée. Ajustement : nouvelle quantité réelle dans ce dépôt."
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


class TransfertForm(BootstrapModelForm):
    class Meta:
        model = Transfert
        fields = ['article', 'depot_source', 'depot_destination', 'quantite', 'motif', 'date_transfert']
        widgets = {
            'date_transfert': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'motif': forms.TextInput(),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)
            depots = Depot.objects.filter(entreprise=entreprise, actif=True)
            self.fields['depot_source'].queryset = depots
            self.fields['depot_destination'].queryset = depots
        self.fields['date_transfert'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get('depot_source')
        dest = cleaned.get('depot_destination')
        quantite = cleaned.get('quantite')
        article = cleaned.get('article')
        if quantite is not None and quantite <= 0:
            self.add_error('quantite', "La quantité doit être supérieure à zéro.")
        if source and dest and source == dest:
            self.add_error('depot_destination', "Le dépôt destination doit être différent du dépôt source.")
        if article and source and quantite and quantite > 0:
            dispo = article.stock_dans(source)
            if quantite > dispo:
                self.add_error('quantite', f"Stock insuffisant dans {source.nom} : {dispo} disponible(s).")
        return cleaned


class InventaireForm(BootstrapModelForm):
    categorie = forms.ModelChoiceField(queryset=CategorieArticle.objects.none(), required=False,
                                       label='Limiter à une catégorie (optionnel)')

    class Meta:
        model = Inventaire
        fields = ['depot', 'date_inventaire', 'commentaire']
        widgets = {
            'date_inventaire': forms.DateInput(attrs={'type': 'date'}),
            'commentaire': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
            self.fields['categorie'].queryset = CategorieArticle.objects.filter(entreprise=entreprise, actif=True)
        self.fields['depot'].required = True
        self.fields['depot'].label = 'Dépôt à inventorier'
