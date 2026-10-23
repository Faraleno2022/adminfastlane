from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.text import slugify
from .models import Entreprise, Utilisateur, ProfilUtilisateur
from .widgets import ScrollableSelectWidget


def choix_applications():
    from .odoo_menu import _PAR_CLE, cles_selectionnables
    return [(cle, _PAR_CLE[cle]['name']) for cle in cles_selectionnables()]


def type_module_pour(applications):
    """Type de compte historique déduit des applications choisies (redirections, rapports)."""
    from .odoo_menu import CLES_RH
    rh = any(cle in applications for cle in CLES_RH)
    compta = 'compta' in applications
    if rh and compta:
        return 'both'
    if rh:
        return 'rh'
    if compta:
        return 'compta'
    return 'stock' if 'stock' in applications else 'secretariat'


class EntrepriseRegistrationForm(forms.ModelForm):
    """Inscription d'une entreprise façon Odoo : applications au choix, puis coordonnées.

    Le nom, l'e-mail et le téléphone peuvent déjà exister dans d'autres comptes ;
    seul l'identifiant de connexion (admin_username) doit être libre.
    """

    field_order = [
        'applications', 'nom_entreprise', 'email', 'telephone', 'ville', 'pays', 'plan_abonnement', 'logo',
        'admin_first_name', 'admin_last_name', 'admin_email', 'admin_username', 'admin_password',
        'admin_password_confirm',
    ]

    applications = forms.MultipleChoiceField(
        label="Applications", choices=choix_applications, widget=forms.CheckboxSelectMultiple,
        error_messages={'required': "Choisissez au moins une application."},
    )
    # Champs pour l'administrateur
    admin_username = forms.CharField(
        max_length=150,
        label="Identifiant de connexion",
        help_text="Sert à se connecter : il doit être unique (ex. prenom.entreprise).",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'prenom.entreprise',
                                      'autocomplete': 'username'})
    )
    admin_email = forms.EmailField(
        label="E-mail de l'administrateur",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'admin@entreprise.com'})
    )
    admin_password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    admin_password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    admin_first_name = forms.CharField(
        max_length=150,
        label="Prénom",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    admin_last_name = forms.CharField(
        max_length=150,
        label="Nom",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Entreprise
        fields = ['nom_entreprise', 'email', 'telephone', 'ville', 'pays', 'plan_abonnement', 'logo']
        widgets = {
            'nom_entreprise': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de votre entreprise'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@entreprise.com'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+224 XXX XX XX XX'}),
            'ville': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Conakry'}),
            'pays': forms.TextInput(attrs={'class': 'form-control', 'value': 'Guinée'}),
            'plan_abonnement': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'logo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
        labels = {
            'nom_entreprise': "Nom de l'entreprise", 'email': "E-mail de l'entreprise", 'telephone': 'Téléphone',
            'ville': 'Ville', 'pays': 'Pays', 'plan_abonnement': 'Formule', 'logo': 'Logo',
        }

    def clean_admin_password_confirm(self):
        password = self.cleaned_data.get('admin_password')
        password_confirm = self.cleaned_data.get('admin_password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        
        return password_confirm
    
    def clean_admin_username(self):
        username = self.cleaned_data.get('admin_username')
        if Utilisateur.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Cet identifiant de connexion est déjà pris : choisissez-en un autre.")
        return username

    def clean_applications(self):
        from .odoo_menu import cles_selectionnables
        choisies = set(self.cleaned_data['applications'])
        return [cle for cle in cles_selectionnables() if cle in choisies]  # ordre du catalogue

    def save(self, commit=True):
        # Créer l'entreprise
        entreprise = super().save(commit=False)
        entreprise.applications = self.cleaned_data['applications']
        entreprise.type_module = type_module_pour(entreprise.applications)
        
        # Générer un slug unique
        base_slug = slugify(entreprise.nom_entreprise)
        slug = base_slug
        counter = 1
        while Entreprise.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        entreprise.slug = slug
        
        if commit:
            entreprise.save()
            
            # Créer le profil administrateur s'il n'existe pas
            profil_admin, created = ProfilUtilisateur.objects.get_or_create(
                nom_profil='Administrateur Entreprise',
                defaults={
                    'description': 'Administrateur de l\'entreprise',
                    'niveau_acces': 5,
                    'actif': True
                }
            )
            
            # Créer l'utilisateur administrateur
            admin_user = Utilisateur(
                username=self.cleaned_data['admin_username'],
                email=self.cleaned_data['admin_email'],
                telephone=entreprise.telephone,
                first_name=self.cleaned_data['admin_first_name'],
                last_name=self.cleaned_data['admin_last_name'],
                entreprise=entreprise,
                profil=profil_admin,
                est_admin_entreprise=True,  # Admin de son entreprise uniquement
                actif=True,
                # Sécurité : pas d'accès superuser ni staff
                is_superuser=False,
                is_staff=False
            )
            admin_user.set_password(self.cleaned_data['admin_password'])
            admin_user.save()
        
        return entreprise


class ApplicationsForm(forms.Form):
    """Paramètres > Applications : ajouter ou retirer des applications de l'entreprise."""

    applications = forms.MultipleChoiceField(
        label="Applications", choices=choix_applications, widget=forms.CheckboxSelectMultiple,
        error_messages={'required': "Gardez au moins une application."},
    )

    def clean_applications(self):
        from .odoo_menu import cles_selectionnables
        choisies = set(self.cleaned_data['applications'])
        return [cle for cle in cles_selectionnables() if cle in choisies]


class ReauthForm(forms.Form):
    """Formulaire de réauthentification"""
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Entrez votre mot de passe',
            'autofocus': True
        })
    )


class UserInvitationForm(forms.ModelForm):
    """Formulaire pour inviter un utilisateur dans une entreprise"""
    
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Utilisateur
        fields = ['username', 'email', 'first_name', 'last_name', 'telephone', 'profil', 'require_reauth']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'profil': ScrollableSelectWidget(attrs={'class': 'form-select'}),
            'require_reauth': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'require_reauth': 'Exiger une réauthentification pour accéder aux menus'
        }
    
    def clean_password_confirm(self):
        password = self.cleaned_data.get('password')
        password_confirm = self.cleaned_data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        
        return password_confirm


class EntrepriseSettingsForm(forms.ModelForm):
    """Formulaire pour modifier les paramètres de l'entreprise"""
    
    class Meta:
        model = Entreprise
        fields = [
            'nom_entreprise', 'nif', 'nifp', 'num_cnss',
            'adresse', 'ville', 'pays', 'telephone', 'email', 'logo',
            'banque_nom', 'banque_code', 'banque_guichet', 'banque_compte',
            'banque_cle_rib', 'banque_iban', 'telepaiement_autorise',
        ]
        widgets = {
            'nom_entreprise': forms.TextInput(attrs={'class': 'form-control'}),
            'nif': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numéro NIF'}),
            'nifp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'NIF-p eTax DGI'}),
            'num_cnss': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numéro CNSS'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ville': forms.TextInput(attrs={'class': 'form-control'}),
            'pays': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'logo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'banque_nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Banque Centrale, Ecobank...'}),
            'banque_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '036'}),
            'banque_guichet': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '003'}),
            'banque_compte': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0100000334'}),
            'banque_cle_rib': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '89'}),
            'banque_iban': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'GN...'}),
            'telepaiement_autorise': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nom_entreprise': 'Nom de l\'entreprise',
            'nif': 'NIF',
            'nifp': 'NIF-p (identifiant eTax DGI)',
            'num_cnss': 'Numéro CNSS',
            'logo': 'Logo de l\'entreprise',
            'banque_nom': 'Banque',
            'banque_code': 'Code banque',
            'banque_guichet': 'Code guichet',
            'banque_compte': 'N° de compte',
            'banque_cle_rib': 'Clé RIB',
            'banque_iban': 'IBAN',
            'telepaiement_autorise': 'Télépaiement DGI activé',
        }
