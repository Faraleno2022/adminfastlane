from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from .models import (
    PlanComptable, Journal, ExerciceComptable, EcritureComptable,
    LigneEcriture, Tiers, Facture, LigneFacture, Reglement
)
from core.widgets import ScrollableSelectWidget


class PlanComptableForm(forms.ModelForm):
    """Formulaire pour le plan comptable"""
    
    class Meta:
        model = PlanComptable
        fields = ['numero_compte', 'intitule', 'compte_parent', 'est_actif']
        widgets = {
            'numero_compte': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 411000'}),
            'intitule': forms.TextInput(attrs={'class': 'form-control'}),
            'compte_parent': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.entreprise = entreprise
        if entreprise:
            self.fields['compte_parent'].queryset = PlanComptable.objects.filter(
                entreprise=entreprise
            ).order_by('numero_compte')
    
    def clean_numero_compte(self):
        """Validation du numéro de compte pour éviter les doublons"""
        numero_compte = self.cleaned_data.get('numero_compte')
        
        if numero_compte and self.entreprise:
            # Vérifier l'unicité du numéro de compte
            if self.instance.pk:
                # Mode édition
                if PlanComptable.objects.exclude(pk=self.instance.pk).filter(
                    entreprise=self.entreprise,
                    numero_compte=numero_compte
                ).exists():
                    raise forms.ValidationError('Ce numéro de compte est déjà utilisé dans cette entreprise.')
            else:
                # Mode création
                if PlanComptable.objects.filter(
                    entreprise=self.entreprise,
                    numero_compte=numero_compte
                ).exists():
                    raise forms.ValidationError('Ce numéro de compte est déjà utilisé dans cette entreprise.')
        
        return numero_compte


class JournalForm(forms.ModelForm):
    """Formulaire pour les journaux"""
    
    class Meta:
        model = Journal
        fields = ['code', 'libelle', 'type_journal', 'compte_contrepartie', 'est_actif']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: AC, VT, BQ'}),
            'libelle': forms.TextInput(attrs={'class': 'form-control'}),
            'type_journal': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'compte_contrepartie': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.entreprise = entreprise
        if entreprise:
            self.fields['compte_contrepartie'].queryset = PlanComptable.objects.filter(
                entreprise=entreprise, est_actif=True
            ).order_by('numero_compte')
    
    def clean_code(self):
        """Validation du code journal pour éviter les doublons"""
        code = self.cleaned_data.get('code')
        
        if code and self.entreprise:
            # Vérifier l'unicité du code journal
            if self.instance.pk:
                # Mode édition
                if Journal.objects.exclude(pk=self.instance.pk).filter(
                    entreprise=self.entreprise,
                    code=code.upper()
                ).exists():
                    raise forms.ValidationError('Ce code journal est déjà utilisé dans cette entreprise.')
            else:
                # Mode création
                if Journal.objects.filter(
                    entreprise=self.entreprise,
                    code=code.upper()
                ).exists():
                    raise forms.ValidationError('Ce code journal est déjà utilisé dans cette entreprise.')
        
        return code.upper() if code else code


class ExerciceForm(forms.ModelForm):
    """Formulaire pour les exercices comptables"""
    
    class Meta:
        model = ExerciceComptable
        fields = ['libelle', 'date_debut', 'date_fin', 'statut', 'est_courant']
        widgets = {
            'libelle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Exercice 2026'}),
            'date_debut': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_fin': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'statut': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'est_courant': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class EcritureForm(forms.ModelForm):
    """Formulaire pour les écritures comptables"""
    
    class Meta:
        model = EcritureComptable
        fields = ['exercice', 'journal', 'numero_ecriture', 'date_ecriture', 'libelle']
        widgets = {
            'exercice': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'journal': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'numero_ecriture': forms.TextInput(attrs={'class': 'form-control'}),
            'date_ecriture': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'libelle': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['exercice'].queryset = ExerciceComptable.objects.filter(
                entreprise=entreprise, statut='ouvert'
            )
            self.fields['journal'].queryset = Journal.objects.filter(
                entreprise=entreprise, est_actif=True
            )


class LigneEcritureForm(forms.ModelForm):
    """Formulaire pour les lignes d'écriture"""
    
    class Meta:
        model = LigneEcriture
        fields = ['compte', 'libelle', 'montant_debit', 'montant_credit']
        widgets = {
            'compte': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'libelle': forms.TextInput(attrs={'class': 'form-control'}),
            'montant_debit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'montant_credit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class TiersForm(forms.ModelForm):
    """Formulaire pour les tiers"""
    
    class Meta:
        model = Tiers
        fields = ['code', 'raison_sociale', 'type_tiers', 'nif', 'adresse', 
                  'telephone', 'email', 'compte_comptable', 'plafond_credit', 'est_actif']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: CLI001'}),
            'raison_sociale': forms.TextInput(attrs={'class': 'form-control'}),
            'type_tiers': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'nif': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'compte_comptable': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'plafond_credit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.entreprise = entreprise
        if entreprise:
            self.fields['compte_comptable'].queryset = PlanComptable.objects.filter(
                entreprise=entreprise, classe='4', est_actif=True
            ).order_by('numero_compte')
    
    def clean_code(self):
        """Validation du code tiers pour éviter les doublons"""
        code = self.cleaned_data.get('code')
        
        if code and self.entreprise:
            # Vérifier l'unicité du code tiers
            if self.instance.pk:
                # Mode édition
                if Tiers.objects.exclude(pk=self.instance.pk).filter(
                    entreprise=self.entreprise,
                    code=code.upper()
                ).exists():
                    raise forms.ValidationError('Ce code tiers est déjà utilisé dans cette entreprise.')
            else:
                # Mode création
                if Tiers.objects.filter(
                    entreprise=self.entreprise,
                    code=code.upper()
                ).exists():
                    raise forms.ValidationError('Ce code tiers est déjà utilisé dans cette entreprise.')
        
        return code.upper() if code else code


class FactureForm(forms.ModelForm):
    """Formulaire pour les factures"""
    
    class Meta:
        model = Facture
        fields = ['numero', 'type_facture', 'tiers', 'date_facture', 'date_echeance',
                  'reference_externe', 'notes']
        widgets = {
            'numero': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: FA-2026-001'}),
            'type_facture': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'tiers': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'date_facture': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_echeance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference_externe': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['tiers'].queryset = Tiers.objects.filter(
                entreprise=entreprise, est_actif=True
            )


class LigneFactureForm(forms.ModelForm):
    """Formulaire pour les lignes de facture"""
    
    class Meta:
        model = LigneFacture
        fields = ['designation', 'quantite', 'prix_unitaire', 'taux_tva', 'compte_comptable']
        widgets = {
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'quantite': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'taux_tva': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'compte_comptable': ScrollableSelectWidget(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['compte_comptable'].queryset = PlanComptable.objects.filter(
                entreprise=entreprise, est_actif=True).order_by('numero_compte')


class BaseLigneFactureFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['entreprise'] = getattr(self.instance, 'entreprise', None)
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lignes = [form for form in self.forms
                  if form.cleaned_data and not form.cleaned_data.get('DELETE', False)]
        if not lignes:
            raise forms.ValidationError('Ajoutez au moins une ligne à la facture.')


LigneFactureFormSet = inlineformset_factory(
    Facture, LigneFacture, form=LigneFactureForm,
    formset=BaseLigneFactureFormSet, extra=1, can_delete=True)


class ReglementForm(forms.ModelForm):
    """Formulaire pour les règlements"""
    
    class Meta:
        model = Reglement
        fields = ['numero', 'facture', 'date_reglement', 'montant', 'mode_paiement', 'reference', 'notes']
        widgets = {
            'numero': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: REG-2026-001'}),
            'facture': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'date_reglement': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'montant': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'mode_paiement': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['facture'].queryset = Facture.objects.filter(
                entreprise=entreprise, statut='validee'
            )
