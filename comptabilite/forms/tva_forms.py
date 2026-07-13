"""
Formulaires pour la gestion de la TVA et des déclarations fiscales.

Fournissent:
- Validation des régimes TVA
- Validation des taux TVA
- Validation des déclarations TVA
- Validation des lignes de déclaration
- Widgets et aide à la saisie
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from decimal import Decimal
import logging

from ..models import (
    RegimeTVA, TauxTVA, DeclarationTVA, LigneDeclarationTVA
)
from .base import ComptaBaseForm, DecimalMoneyField

logger = logging.getLogger(__name__)


# ============================================================================
# RÉGIME TVA FORMS
# ============================================================================

class RegimeTVAForm(ComptaBaseForm):
    """Formulaire pour la création/édition de régimes TVA."""
    
    class Meta:
        model = RegimeTVA
        fields = ['code', 'nom', 'description', 'regime', 'actif']
        widgets = {
            'code': forms.TextInput(attrs={
                'placeholder': 'ex: NORMAL',
                'class': 'form-control',
                'maxlength': '50'
            }),
            'nom': forms.TextInput(attrs={
                'placeholder': 'ex: Régime normal',
                'class': 'form-control',
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description du régime...',
                'class': 'form-control',
            }),
            'regime': forms.Select(attrs={
                'class': 'form-control',
            }),
            'actif': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def clean_code(self):
        """Valide que le code est unique par entreprise."""
        code = self.cleaned_data.get('code')
        if not code:
            return code
        
        # Vérifier l'unicité (sauf pour l'édition)
        qs = RegimeTVA.objects.filter(
            code=code,
            entreprise=self.instance.entreprise
        )
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise ValidationError(
                _("Un régime TVA avec ce code existe déjà")
            )
        return code
    
    def clean_nom(self):
        """Valide que le nom est fourni."""
        nom = self.cleaned_data.get('nom')
        if not nom or len(nom.strip()) < 3:
            raise ValidationError(
                _("Le nom doit contenir au moins 3 caractères")
            )
        return nom.strip()


# ============================================================================
# TAUX TVA FORMS
# ============================================================================

class TauxTVAForm(ComptaBaseForm):
    """Formulaire pour la création/édition de taux TVA."""
    
    taux = forms.DecimalField(
        label=_("Taux (%)"),
        decimal_places=2,
        max_digits=5,
        help_text=_("Taux en pourcentage, ex: 20.00")
    )
    
    class Meta:
        model = TauxTVA
        fields = ['code', 'nom', 'taux', 'regime_tva', 'date_debut', 'date_fin', 'actif']
        widgets = {
            'code': forms.TextInput(attrs={
                'placeholder': 'ex: NORMAL_20',
                'class': 'form-control',
                'maxlength': '50'
            }),
            'nom': forms.TextInput(attrs={
                'placeholder': 'ex: TVA normale 20%',
                'class': 'form-control',
            }),
            'regime_tva': forms.Select(attrs={
                'class': 'form-control',
            }),
            'date_debut': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'date_fin': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'actif': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def clean_taux(self):
        """Valide que le taux est dans les limites raisonnables."""
        taux = self.cleaned_data.get('taux')
        if taux is None:
            return taux
        
        if taux < Decimal('0') or taux > Decimal('100'):
            raise ValidationError(
                _("Le taux doit être entre 0% et 100%")
            )
        return taux
    
    def clean(self):
        """Valide les dates."""
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        
        if date_debut and date_fin and date_fin < date_debut:
            raise ValidationError(
                _("La date de fin doit être après la date de début")
            )
        
        return cleaned_data


# ============================================================================
# DÉCLARATION TVA FORMS
# ============================================================================

class DeclarationTVAForm(ComptaBaseForm):
    """Formulaire pour la création/édition de déclarations TVA."""
    
    class Meta:
        model = DeclarationTVA
        fields = ['regime_tva', 'exercice', 'periode_debut', 'periode_fin', 'statut']
        widgets = {
            'regime_tva': forms.Select(attrs={
                'class': 'form-control',
            }),
            'exercice': forms.Select(attrs={
                'class': 'form-control',
            }),
            'periode_debut': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'periode_fin': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'statut': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        # Filtrer les régimes par entreprise
        if user and user.entreprise:
            self.fields['regime_tva'].queryset = RegimeTVA.objects.filter(
                entreprise=user.entreprise,
                actif=True
            )
    
    def clean(self):
        """Valide les périodes."""
        cleaned_data = super().clean()
        periode_debut = cleaned_data.get('periode_debut')
        periode_fin = cleaned_data.get('periode_fin')
        
        if periode_debut and periode_fin and periode_fin < periode_debut:
            raise ValidationError(
                _("La date de fin de période doit être après la date de début")
            )
        
        return cleaned_data


class LigneDeclarationTVAForm(ComptaBaseForm):
    """Formulaire pour l'ajout/édition de lignes dans une déclaration TVA."""
    
    montant_ht = DecimalMoneyField(
        label=_("Montant HT"),
        help_text=_("Montant hors taxes")
    )
    
    montant_tva = DecimalMoneyField(
        label=_("Montant TVA"),
        help_text=_("Montant de la TVA"),
        required=False
    )
    
    montant_ttc = DecimalMoneyField(
        label=_("Montant TTC"),
        help_text=_("Montant toutes taxes comprises"),
        required=False
    )
    
    class Meta:
        model = LigneDeclarationTVA
        fields = ['numero_ligne', 'description', 'taux', 'sens', 'montant_ht', 'montant_tva', 'type_ligne', 'compte_comptable']
        widgets = {
            'numero_ligne': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'description': forms.TextInput(attrs={
                'placeholder': 'Description de l\'opération',
                'class': 'form-control',
            }),
            'taux': forms.Select(attrs={
                'class': 'form-control',
            }),
            'sens': forms.Select(attrs={
                'class': 'form-control',
            }),
            'montant_ht': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'montant_tva': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'type_ligne': forms.Select(attrs={
                'class': 'form-control',
            }),
            'compte_comptable': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
    
    def __init__(self, *args, declaration=None, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.declaration = declaration
        
        # Filtrer les taux par entreprise et régime
        if declaration and declaration.regime_tva:
            self.fields['taux'].queryset = TauxTVA.objects.filter(
                regime_tva=declaration.regime_tva,
                actif=True
            )
    
    def clean_montant_ht(self):
        """Valide le montant HT."""
        montant = self.cleaned_data.get('montant_ht')
        if montant and montant < Decimal('0'):
            raise ValidationError(
                _("Le montant HT doit être positif")
            )
        return montant
    
    def clean_taux_tva(self):
        """Valide que le taux est fourni."""
        taux = self.cleaned_data.get('taux_tva')
        if not taux:
            raise ValidationError(
                _("Vous devez sélectionner un taux TVA")
            )
        return taux


class LigneDeclarationTVAFormSet(forms.BaseInlineFormSet):
    """FormSet pour l'édition de plusieurs lignes."""
    
    def clean(self):
        """Valide l'ensemble des lignes."""
        super().clean()
        
        if any(self.errors):
            return
        
        # Vérifier qu'il y a au moins une ligne valide
        valid_forms = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if not valid_forms:
            raise ValidationError(
                _("Une déclaration doit contenir au moins une ligne")
            )


# Créer le formset pour les lignes
LigneDeclarationTVAInlineFormSet = inlineformset_factory(
    DeclarationTVA,
    LigneDeclarationTVA,
    form=LigneDeclarationTVAForm,
    formset=LigneDeclarationTVAFormSet,
    extra=1,
    can_delete=True
)


# ============================================================================
# FORMULAIRES DE FILTRE
# ============================================================================

class DeclarationTVAFilterForm(forms.Form):
    """Formulaire pour filtrer les déclarations TVA."""
    
    statut = forms.ChoiceField(
        label=_("Statut"),
        choices=[('', '--- Tous les statuts ---')] + list(DeclarationTVA.STATUTS),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    regime_tva = forms.ModelChoiceField(
        label=_("Régime TVA"),
        queryset=RegimeTVA.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    periode_debut = forms.DateField(
        label=_("Période à partir du"),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    periode_fin = forms.DateField(
        label=_("Période jusqu'au"),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    def clean(self):
        """Valide les filtres."""
        cleaned_data = super().clean()
        debut = cleaned_data.get('periode_debut')
        fin = cleaned_data.get('periode_fin')
        
        if debut and fin and fin < debut:
            raise ValidationError(
                _("La date de fin doit être après la date de début")
            )
        
        return cleaned_data


class RegimeTVAFilterForm(forms.Form):
    """Formulaire pour filtrer les régimes TVA."""
    
    actif = forms.NullBooleanField(
        label=_("Actif"),
        required=False,
        widget=forms.Select(
            choices=[
                ('', '--- Tous ---'),
                (True, _('Actifs')),
                (False, _('Inactifs')),
            ],
            attrs={'class': 'form-control'}
        )
    )
    
    code = forms.CharField(
        label=_("Code ou nom"),
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Rechercher...',
            'class': 'form-control'
        })
    )
