"""
Module Gestion du Stock — Formulaires (ModelForms)
Le widget Bootstrap est appliqué automatiquement à tous les champs.
"""
from django import forms

from core.models import Service

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock, Inventaire,
    Depot, Transfert, CommandeFournisseur, LigneCommande, Reception,
    FactureFournisseur, PaiementFournisseur,
    Client, PrixSpecialClient, DocumentVente, LigneVente, BonLivraison,
    PaiementClient, Lot, NumeroSerie,
    BesoinAchat, LigneBesoinAchat, DemandeVente, LigneDemandeVente,
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
        fields = ['nom', 'contact', 'telephone', 'email', 'adresse', 'nif',
                  'delai_livraison_jours', 'categorie', 'note_evaluation', 'actif', 'observations']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'observations': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['note_evaluation'].required = False
        self.fields['note_evaluation'].help_text = 'Optionnel — note globale de fiabilité (0 à 20).'


class DepotForm(BootstrapModelForm):
    class Meta:
        model = Depot
        fields = ['nom', 'type_depot', 'code', 'adresse', 'responsable', 'telephone', 'par_defaut', 'actif']


class ArticleForm(BootstrapModelForm):
    class Meta:
        model = Article
        fields = ['reference', 'code_barres', 'designation', 'categorie', 'fournisseur', 'unite',
                  'prix_achat', 'prix_vente', 'seuil_alerte', 'stock_max', 'emplacement',
                  'photo', 'perissable', 'gestion_lot', 'gestion_serie', 'description', 'actif']
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


# ---------------------------------------------------------------------------
# Achats
# ---------------------------------------------------------------------------
class CommandeFournisseurForm(BootstrapModelForm):
    class Meta:
        model = CommandeFournisseur
        fields = ['fournisseur', 'depot', 'date_commande', 'date_livraison_prevue', 'notes']
        widgets = {
            'date_commande': forms.DateInput(attrs={'type': 'date'}),
            'date_livraison_prevue': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, actif=True)
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
        self.fields['depot'].required = False
        self.fields['depot'].help_text = "Dépôt où les marchandises seront reçues."


class LigneCommandeForm(BootstrapModelForm):
    class Meta:
        model = LigneCommande
        fields = ['article', 'quantite_commandee', 'prix_unitaire']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)

    def clean_quantite_commandee(self):
        q = self.cleaned_data['quantite_commandee']
        if q is None or q <= 0:
            raise forms.ValidationError("La quantité doit être supérieure à zéro.")
        return q


class BesoinAchatForm(BootstrapModelForm):
    class Meta:
        model = BesoinAchat
        fields = ['service', 'urgence', 'date_besoin_souhaitee', 'motif']
        widgets = {
            'date_besoin_souhaitee': forms.DateInput(attrs={'type': 'date'}),
            'motif': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['service'].queryset = Service.objects.filter(entreprise=entreprise, actif=True)
        self.fields['service'].required = False
        self.fields['motif'].required = False


class LigneBesoinAchatForm(BootstrapModelForm):
    class Meta:
        model = LigneBesoinAchat
        fields = ['article', 'quantite_demandee']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)

    def clean_quantite_demandee(self):
        q = self.cleaned_data['quantite_demandee']
        if q is None or q <= 0:
            raise forms.ValidationError("La quantité doit être supérieure à zéro.")
        return q


class ReceptionForm(BootstrapModelForm):
    class Meta:
        model = Reception
        fields = ['depot', 'date_reception', 'notes']
        widgets = {
            'date_reception': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
        self.fields['depot'].required = True


class FactureFournisseurForm(BootstrapModelForm):
    class Meta:
        model = FactureFournisseur
        fields = ['numero', 'fournisseur', 'commande', 'date_facture', 'date_echeance',
                  'montant_ht', 'taux_tva', 'notes']
        widgets = {
            'date_facture': forms.DateInput(attrs={'type': 'date'}),
            'date_echeance': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, actif=True)
            self.fields['commande'].queryset = CommandeFournisseur.objects.filter(entreprise=entreprise)
        self.fields['commande'].required = False


class PaiementFournisseurForm(BootstrapModelForm):
    class Meta:
        model = PaiementFournisseur
        fields = ['montant', 'date_paiement', 'mode', 'reference']
        widgets = {
            'date_paiement': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_montant(self):
        m = self.cleaned_data['montant']
        if m is None or m <= 0:
            raise forms.ValidationError("Le montant doit être supérieur à zéro.")
        return m


# ---------------------------------------------------------------------------
# Ventes
# ---------------------------------------------------------------------------
class ClientForm(BootstrapModelForm):
    class Meta:
        model = Client
        fields = ['nom', 'type_client', 'contact', 'telephone', 'email', 'adresse',
                  'nif', 'remise_defaut', 'actif', 'observations']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'observations': forms.Textarea(attrs={'rows': 2}),
        }


class DemandeVenteForm(BootstrapModelForm):
    class Meta:
        model = DemandeVente
        fields = ['client', 'date_besoin', 'notes']
        widgets = {
            'date_besoin': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['client'].queryset = Client.objects.filter(entreprise=entreprise, actif=True)
        self.fields['notes'].required = False


class LigneDemandeVenteForm(BootstrapModelForm):
    class Meta:
        model = LigneDemandeVente
        fields = ['article', 'quantite_souhaitee', 'prix_indicatif']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)
        self.fields['prix_indicatif'].required = False
        self.fields['prix_indicatif'].help_text = "Optionnel — le devis utilisera le prix spécial client ou le prix de vente."

    def clean_quantite_souhaitee(self):
        q = self.cleaned_data['quantite_souhaitee']
        if q is None or q <= 0:
            raise forms.ValidationError("La quantité doit être supérieure à zéro.")
        return q


class DocumentVenteForm(BootstrapModelForm):
    class Meta:
        model = DocumentVente
        fields = ['type_document', 'client', 'depot', 'date_document', 'date_echeance',
                  'remise_globale_pct', 'taux_tva', 'notes']
        widgets = {
            'date_document': forms.DateInput(attrs={'type': 'date'}),
            'date_echeance': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['client'].queryset = Client.objects.filter(entreprise=entreprise, actif=True)
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
        self.fields['depot'].required = False
        self.fields['depot'].help_text = "Dépôt depuis lequel la marchandise sera livrée."


class LigneVenteForm(BootstrapModelForm):
    class Meta:
        model = LigneVente
        fields = ['article', 'quantite', 'prix_unitaire', 'remise_pct']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)
        # Prix et remise sont remplis automatiquement si laissés vides.
        self.fields['prix_unitaire'].required = False
        self.fields['remise_pct'].required = False
        self.fields['prix_unitaire'].help_text = "Vide = prix spécial client ou prix de vente."

    def clean_quantite(self):
        q = self.cleaned_data['quantite']
        if q is None or q <= 0:
            raise forms.ValidationError("La quantité doit être supérieure à zéro.")
        return q


class BonLivraisonForm(BootstrapModelForm):
    class Meta:
        model = BonLivraison
        fields = ['depot', 'date_livraison', 'adresse_livraison', 'notes']
        widgets = {
            'date_livraison': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
        self.fields['depot'].required = True


class PaiementClientForm(BootstrapModelForm):
    class Meta:
        model = PaiementClient
        fields = ['montant', 'date_paiement', 'mode', 'reference']
        widgets = {
            'date_paiement': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_montant(self):
        m = self.cleaned_data['montant']
        if m is None or m <= 0:
            raise forms.ValidationError("Le montant doit être supérieur à zéro.")
        return m


class PrixSpecialClientForm(BootstrapModelForm):
    class Meta:
        model = PrixSpecialClient
        fields = ['article', 'prix']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)


# ---------------------------------------------------------------------------
# Lots & numéros de série
# ---------------------------------------------------------------------------
class LotForm(BootstrapModelForm):
    class Meta:
        model = Lot
        fields = ['article', 'numero_lot', 'depot', 'fournisseur', 'date_entree',
                  'date_peremption', 'quantite', 'quantite_restante', 'notes']
        widgets = {
            'date_entree': forms.DateInput(attrs={'type': 'date'}),
            'date_peremption': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, actif=True)
        self.fields['depot'].required = False
        self.fields['fournisseur'].required = False


class NumeroSerieForm(BootstrapModelForm):
    class Meta:
        model = NumeroSerie
        fields = ['article', 'numero_serie', 'lot', 'depot', 'statut', 'date_entree', 'date_sortie', 'notes']
        widgets = {
            'date_entree': forms.DateInput(attrs={'type': 'date'}),
            'date_sortie': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise is not None:
            self.fields['article'].queryset = Article.objects.filter(entreprise=entreprise, actif=True)
            self.fields['depot'].queryset = Depot.objects.filter(entreprise=entreprise, actif=True)
            self.fields['lot'].queryset = Lot.objects.filter(entreprise=entreprise)
        self.fields['lot'].required = False
        self.fields['depot'].required = False
