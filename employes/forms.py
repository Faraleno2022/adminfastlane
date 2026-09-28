from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column, Submit, Button, HTML
from crispy_forms.bootstrap import TabHolder, Tab
from .models import Employe, ContratEmploye, EvaluationEmploye, SanctionDisciplinaire
from core.models import Devise, Etablissement, Service, Poste
from core.widgets import ScrollableSelectWidget


class EmployeForm(forms.ModelForm):
    """Formulaire de création/modification d'un employé"""
    
    class Meta:
        model = Employe
        fields = [
            # État civil
            'civilite', 'nom', 'prenoms', 'nom_jeune_fille', 'sexe',
            'situation_matrimoniale', 'nombre_enfants', 'photo',
            
            # Naissance
            'date_naissance', 'lieu_naissance', 'commune_naissance',
            'prefecture_naissance', 'nationalite',
            
            # Identification
            'type_piece_identite', 'numero_piece_identite',
            'date_delivrance_piece', 'date_expiration_piece',
            'num_cnss_individuel',
            
            # Contact
            'adresse_actuelle', 'commune_residence', 'prefecture_residence',
            'telephone_principal', 'telephone_secondaire',
            'email_personnel', 'email_professionnel',
            
            # Contact d'urgence
            'contact_urgence_nom', 'contact_urgence_lien',
            'contact_urgence_telephone',
            
            # Professionnel
            'matricule', 'etablissement', 'service', 'poste',
            'date_embauche', 'date_anciennete', 'type_contrat',
            'superieur_hierarchique',
            
            # Filiation
            'nom_pere', 'nom_mere', 'nombre_femmes',

            # Conducteur / Transport
            'id_conducteur', 'tracteur', 'citerne', 'vehicule_assigne',
            'numero_permis', 'date_obtention_permis', 'date_validite_permis',
            'groupe_sanguin', 'base_chauffeur',

            # Formation transport / sécurité
            'date_formation_apth', 'anciennete_transport_hcl',
            'date_dernier_recyclage', 'formation_extincteur',

            # Visite médicale (suivi rapide)
            'date_derniere_visite_medicale', 'service_medical_accredite',
            'date_prochaine_visite_medicale',

            # Bancaire
            'mode_paiement', 'nom_banque', 'agence_banque',
            'numero_compte', 'rib', 'operateur_mobile_money',
            'numero_mobile_money', 'devise_paie'
        ]
        
        widgets = {
            'date_naissance': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_delivrance_piece': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_expiration_piece': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_embauche': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_anciennete': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'adresse_actuelle': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'date_obtention_permis': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_validite_permis': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_formation_apth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_dernier_recyclage': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_derniere_visite_medicale': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'date_prochaine_visite_medicale': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            # Listes déroulantes avec recherche et scrollbar
            'etablissement': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'service': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'poste': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'superieur_hierarchique': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'devise_paie': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'nom_banque': forms.TextInput(attrs={'class': 'form-control'}),
            'operateur_mobile_money': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        entreprise = kwargs.pop('entreprise', None)
        super().__init__(*args, **kwargs)
        
        # Rendre plusieurs champs optionnels pour permettre un enregistrement rapide
        # L'utilisateur pourra mettre à jour les informations manquantes plus tard
        optional_fields = [
            'matricule', 'sexe', 'date_naissance', 'nationalite',
            'date_embauche', 'type_contrat', 'nombre_enfants',
            'etablissement', 'service'
        ]
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False
        
        # Filtrer les devises actives uniquement
        self.fields['devise_paie'].queryset = Devise.objects.filter(actif=True)
        self.fields['devise_paie'].empty_label = "GNF (par défaut)"
        
        # Isolation multi-tenant : filtrer les FK par entreprise
        if entreprise:
            self.fields['etablissement'].queryset = Etablissement.objects.filter(
                societe__entreprise=entreprise)
            self.fields['service'].queryset = Service.objects.filter(
                entreprise=entreprise)
            self.fields['poste'].queryset = Poste.objects.filter(
                entreprise=entreprise)
            self.fields['superieur_hierarchique'].queryset = Employe.objects.filter(
                entreprise=entreprise)
        # Un poste reste obligatoire lorsqu'il existe une liste de choix.
        # Sur une nouvelle installation desktop, la structure peut toutefois
        # ne contenir encore aucun poste. Rendre alors ce champ optionnel évite
        # de créer un formulaire impossible à soumettre ; l'affectation pourra
        # être complétée après la création du premier poste.
        poste_field = self.fields['poste']
        poste_field.required = poste_field.queryset.exists()
        if poste_field.required:
            poste_field.empty_label = "Choisir un poste (obligatoire)"
        else:
            poste_field.empty_label = "Aucun poste configuré"
            poste_field.help_text = (
                "Aucun poste n'est encore configuré pour cette entreprise. "
                "Vous pourrez affecter l'employé après avoir créé un poste."
            )
        
        # Helper Crispy Forms
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = 'post'
        self.helper.form_enctype = 'multipart/form-data'
        self.helper.form_class = 'form-horizontal'
        
        self.helper.layout = Layout(
            TabHolder(
                Tab('État civil',
                    Fieldset('Informations personnelles',
                        Row(
                            Column('civilite', css_class='col-md-2'),
                            Column('nom', css_class='col-md-5'),
                            Column('prenoms', css_class='col-md-5'),
                        ),
                        Row(
                            Column('nom_jeune_fille', css_class='col-md-4'),
                            Column('sexe', css_class='col-md-4'),
                            Column('situation_matrimoniale', css_class='col-md-4'),
                        ),
                        Row(
                            Column('photo', css_class='col-md-8'),
                        ),
                    ),
                    Fieldset('Naissance',
                        Row(
                            Column('date_naissance', css_class='col-md-4'),
                            Column('lieu_naissance', css_class='col-md-8'),
                        ),
                        Row(
                            Column('commune_naissance', css_class='col-md-6'),
                            Column('prefecture_naissance', css_class='col-md-6'),
                        ),
                        'nationalite',
                    ),
                ),
                
                Tab('Identification',
                    Fieldset('Pièce d\'identité',
                        Row(
                            Column('type_piece_identite', css_class='col-md-6'),
                            Column('numero_piece_identite', css_class='col-md-6'),
                        ),
                        Row(
                            Column('date_delivrance_piece', css_class='col-md-6'),
                            Column('date_expiration_piece', css_class='col-md-6'),
                        ),
                    ),
                    Fieldset('Sécurité sociale',
                        'num_cnss_individuel',
                        HTML('<small class="form-text text-muted">Numéro CNSS obligatoire pour la paie</small>'),
                    ),
                ),
                
                Tab('Contact',
                    Fieldset('Adresse',
                        'adresse_actuelle',
                        Row(
                            Column('commune_residence', css_class='col-md-6'),
                            Column('prefecture_residence', css_class='col-md-6'),
                        ),
                    ),
                    Fieldset('Téléphones et emails',
                        Row(
                            Column('telephone_principal', css_class='col-md-6'),
                            Column('telephone_secondaire', css_class='col-md-6'),
                        ),
                        Row(
                            Column('email_personnel', css_class='col-md-6'),
                            Column('email_professionnel', css_class='col-md-6'),
                        ),
                    ),
                ),

                Tab('Professionnel',
                    Fieldset('Affectation',
                        'matricule',
                        HTML('<small class="form-text text-muted">Laisser vide pour génération automatique</small>'),
                        Row(
                            Column('etablissement', css_class='col-md-4'),
                            Column('service', css_class='col-md-4'),
                            Column('poste', css_class='col-md-4'),
                        ),
                        'superieur_hierarchique',
                    ),
                    Fieldset('Contrat',
                        Row(
                            Column('date_embauche', css_class='col-md-4'),
                            Column('date_anciennete', css_class='col-md-4'),
                            Column('type_contrat', css_class='col-md-4'),
                        ),
                        HTML('<small class="form-text text-muted">La date d\'ancienneté peut différer de la date d\'embauche</small>'),
                    ),
                ),
                
                Tab('Filiation',
                    Fieldset('Famille',
                        Row(
                            Column('nombre_femmes', css_class='col-md-4'),
                            Column('nombre_enfants', css_class='col-md-4'),
                        ),
                        Row(
                            Column('nom_pere', css_class='col-md-6'),
                            Column('nom_mere', css_class='col-md-6'),
                        ),
                    ),
                    Fieldset('Contact d\'urgence',
                        Row(
                            Column('contact_urgence_nom', css_class='col-md-4'),
                            Column('contact_urgence_lien', css_class='col-md-4'),
                            Column('contact_urgence_telephone', css_class='col-md-4'),
                        ),
                    ),
                ),

                Tab('Conducteur',
                    Fieldset('Identification conducteur',
                        Row(
                            Column('id_conducteur', css_class='col-md-4'),
                            Column('groupe_sanguin', css_class='col-md-4'),
                            Column('base_chauffeur', css_class='col-md-4'),
                        ),
                    ),
                    Fieldset('Véhicules assignés',
                        Row(
                            Column('vehicule_assigne', css_class='col-md-12'),
                        ),
                        Row(
                            Column('tracteur', css_class='col-md-6'),
                            Column('citerne', css_class='col-md-6'),
                        ),
                    ),
                    Fieldset('Permis de conduire',
                        Row(
                            Column('numero_permis', css_class='col-md-4'),
                            Column('date_obtention_permis', css_class='col-md-4'),
                            Column('date_validite_permis', css_class='col-md-4'),
                        ),
                    ),
                ),

                Tab('Formation & Sécurité',
                    Fieldset('Formation transport',
                        Row(
                            Column('date_formation_apth', css_class='col-md-4'),
                            Column('anciennete_transport_hcl', css_class='col-md-4'),
                            Column('formation_extincteur', css_class='col-md-4'),
                        ),
                        Row(
                            Column('date_dernier_recyclage', css_class='col-md-6'),
                        ),
                    ),
                    Fieldset('Visite médicale',
                        Row(
                            Column('date_derniere_visite_medicale', css_class='col-md-4'),
                            Column('service_medical_accredite', css_class='col-md-4'),
                            Column('date_prochaine_visite_medicale', css_class='col-md-4'),
                        ),
                    ),
                ),

                Tab('Bancaire',
                    Fieldset('Mode de paiement',
                        Row(
                            Column('mode_paiement', css_class='col-md-6'),
                            Column('devise_paie', css_class='col-md-6'),
                        ),
                        HTML('<small class="form-text text-muted">La devise de paie est utilisée pour les calculs de salaire et les bulletins de paie</small>'),
                    ),
                    Fieldset('Informations bancaires',
                        Row(
                            Column('nom_banque', css_class='col-md-6'),
                            Column('agence_banque', css_class='col-md-6'),
                        ),
                        Row(
                            Column('numero_compte', css_class='col-md-6'),
                            Column('rib', css_class='col-md-6'),
                        ),
                    ),
                    Fieldset('Mobile Money',
                        Row(
                            Column('operateur_mobile_money', css_class='col-md-6'),
                            Column('numero_mobile_money', css_class='col-md-6'),
                        ),
                    ),
                ),
            ),
        )
    
    def clean_matricule(self):
        """Validation du matricule pour éviter les doublons"""
        matricule = self.cleaned_data.get('matricule')
        
        if matricule:
            # Vérifier l'unicité du matricule
            if self.instance.pk:
                # Mode édition
                if Employe.objects.exclude(pk=self.instance.pk).filter(
                    matricule=matricule
                ).exists():
                    raise forms.ValidationError('Ce matricule est déjà utilisé par un autre employé')
            else:
                # Mode création
                if Employe.objects.filter(matricule=matricule).exists():
                    raise forms.ValidationError('Ce matricule est déjà utilisé')
        
        return matricule
    
    def clean_num_cnss_individuel(self):
        """Validation du numéro CNSS"""
        num_cnss = self.cleaned_data.get('num_cnss_individuel')
        if num_cnss:
            # Vérifier l'unicité
            if self.instance.pk:
                # Mode édition
                if Employe.objects.exclude(pk=self.instance.pk).filter(
                    num_cnss_individuel=num_cnss
                ).exists():
                    raise forms.ValidationError('Ce numéro CNSS est déjà utilisé par un autre employé')
            else:
                # Mode création
                if Employe.objects.filter(num_cnss_individuel=num_cnss).exists():
                    raise forms.ValidationError('Ce numéro CNSS est déjà utilisé')
        return num_cnss
    
    def clean(self):
        """Validation globale du formulaire"""
        cleaned_data = super().clean()
        
        # Vérifier que la date de naissance est cohérente
        date_naissance = cleaned_data.get('date_naissance')
        date_embauche = cleaned_data.get('date_embauche')
        
        if date_naissance and date_embauche:
            age_embauche = (date_embauche - date_naissance).days // 365
            if age_embauche < 16:
                raise forms.ValidationError(
                    'L\'âge à l\'embauche doit être d\'au moins 16 ans'
                )
        
        # Vérifier les dates de pièce d'identité
        date_delivrance = cleaned_data.get('date_delivrance_piece')
        date_expiration = cleaned_data.get('date_expiration_piece')
        
        if date_delivrance and date_expiration:
            if date_expiration <= date_delivrance:
                raise forms.ValidationError(
                    'La date d\'expiration doit être postérieure à la date de délivrance'
                )
        
        return cleaned_data


class ContratForm(forms.ModelForm):
    """Formulaire de contrat d'employé"""
    
    class Meta:
        model = ContratEmploye
        fields = [
            'num_contrat', 'type_contrat', 'date_debut', 'date_fin',
            'duree_mois', 'motif_contrat', 'periode_essai_mois',
            'date_fin_essai', 'fichier_contrat', 'observations',
            'date_signature'
        ]
        
        widgets = {
            'date_debut': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_fin_essai': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_signature': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'motif_contrat': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'observations': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'fichier_contrat': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = 'post'
        self.helper.form_enctype = 'multipart/form-data'
        
        self.helper.layout = Layout(
            Fieldset('Informations du contrat',
                Row(
                    Column('num_contrat', css_class='col-md-6'),
                    Column('type_contrat', css_class='col-md-6'),
                ),
                Row(
                    Column('date_debut', css_class='col-md-6'),
                    Column('date_fin', css_class='col-md-6'),
                ),
                'duree_mois',
                'motif_contrat',
            ),
            Fieldset('Période d\'essai',
                Row(
                    Column('periode_essai_mois', css_class='col-md-6'),
                    Column('date_fin_essai', css_class='col-md-6'),
                ),
            ),
            Fieldset('Document',
                'fichier_contrat',
                'date_signature',
                'observations',
            ),
        )
    
    def clean(self):
        cleaned_data = super().clean()
        
        type_contrat = cleaned_data.get('type_contrat')
        date_fin = cleaned_data.get('date_fin')
        
        # Pour un CDD, la date de fin est obligatoire
        if type_contrat == 'CDD' and not date_fin:
            raise forms.ValidationError(
                'La date de fin est obligatoire pour un contrat CDD'
            )
        
        # Vérifier que la date de fin est après la date de début
        date_debut = cleaned_data.get('date_debut')
        if date_debut and date_fin:
            if date_fin <= date_debut:
                raise forms.ValidationError(
                    'La date de fin doit être postérieure à la date de début'
                )
        
        return cleaned_data


class EmployeSearchForm(forms.Form):
    """Formulaire de recherche d'employés"""
    search = forms.CharField(
        required=False,
        label='Rechercher',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nom, prénom, matricule, N° CNSS...'
        })
    )
    
    statut = forms.ChoiceField(
        required=False,
        label='Statut',
        choices=[('', 'Tous')] + list(Employe.STATUTS),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    type_contrat = forms.ChoiceField(
        required=False,
        label='Type de contrat',
        choices=[('', 'Tous')] + list(Employe.TYPES_CONTRATS),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    sexe = forms.ChoiceField(
        required=False,
        label='Sexe',
        choices=[('', 'Tous'), ('M', 'Masculin'), ('F', 'Féminin')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class EvaluationEmployeForm(forms.ModelForm):
    class Meta:
        model = EvaluationEmploye
        fields = [
            'annee_evaluation', 'periode', 'date_evaluation', 'evaluateur',
            'objectifs_atteints', 'competences_techniques', 'competences_comportementales',
            'note_globale', 'appreciation',
            'points_forts', 'points_amelioration', 'plan_developpement',
            'recommandations', 'date_prochain_entretien'
        ]
        widgets = {
            'date_evaluation': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_prochain_entretien': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'points_forts': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'points_amelioration': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'plan_developpement': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'recommandations': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        entreprise = kwargs.pop('entreprise', None)
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['evaluateur'].queryset = Employe.objects.filter(entreprise=entreprise)


class SanctionDisciplinaireForm(forms.ModelForm):
    class Meta:
        model = SanctionDisciplinaire
        fields = [
            'type_sanction', 'motif',
            'date_faits', 'date_convocation', 'date_entretien', 'proces_verbal_entretien',
            'date_notification', 'lettre_notification',
            'date_debut_application', 'date_fin_application', 'duree_jours',
            'recours_depose', 'date_recours', 'decision_recours',
            'statut', 'observations'
        ]
        widgets = {
            'date_faits': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_convocation': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_entretien': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_notification': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_debut_application': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_fin_application': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_recours': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'motif': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'decision_recours': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'observations': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
