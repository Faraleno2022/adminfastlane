from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Entreprise, Utilisateur, ProfilUtilisateur, DroitAcces, LogActivite,
    Societe, Etablissement, Service, Poste, TentativeCodeAcces
)


@admin.register(Entreprise)
class EntrepriseAdmin(admin.ModelAdmin):
    list_display = ['nom_entreprise', 'slug', 'email', 'ville', 'plan_abonnement', 'actif', 'date_creation']
    list_filter = ['actif', 'plan_abonnement', 'ville']
    search_fields = ['nom_entreprise', 'slug', 'email', 'nif']
    readonly_fields = ['date_creation']
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom_entreprise', 'slug', 'logo')
        }),
        ('Immatriculation', {
            'fields': ('nif', 'num_cnss')
        }),
        ('Coordonnées', {
            'fields': ('adresse', 'ville', 'pays', 'telephone', 'email')
        }),
        ('Abonnement', {
            'fields': ('plan_abonnement', 'max_utilisateurs', 'date_expiration')
        }),
        ('Statut', {
            'fields': ('actif', 'date_creation')
        }),
    )


@admin.register(ProfilUtilisateur)
class ProfilUtilisateurAdmin(admin.ModelAdmin):
    list_display = ['nom_profil', 'niveau_acces', 'actif']
    list_filter = ['niveau_acces', 'actif']
    search_fields = ['nom_profil']


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'entreprise', 'profil', 'est_admin_entreprise', 'actif', 'date_derniere_connexion']
    list_filter = ['actif', 'profil', 'entreprise', 'est_admin_entreprise', 'require_reauth', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = UserAdmin.fieldsets + (
        ('Entreprise', {
            'fields': ('entreprise', 'est_admin_entreprise')
        }),
        ('Informations supplémentaires', {
            'fields': ('telephone', 'profil', 'actif', 'photo', 'date_derniere_connexion', 'tentatives_connexion')
        }),
        ('Sécurité', {
            'fields': ('require_reauth', 'last_reauth')
        }),
    )


@admin.register(DroitAcces)
class DroitAccesAdmin(admin.ModelAdmin):
    list_display = ['profil', 'module', 'lecture', 'ecriture', 'modification', 'suppression', 'validation']
    list_filter = ['profil', 'module']
    search_fields = ['profil__nom_profil']


@admin.register(LogActivite)
class LogActiviteAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'action', 'module', 'date_action', 'adresse_ip']
    list_filter = ['module', 'date_action']
    search_fields = ['utilisateur__username', 'action', 'details']
    readonly_fields = ['utilisateur', 'action', 'module', 'table_concernee', 'id_enregistrement', 'details', 'adresse_ip', 'date_action']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TentativeCodeAcces)
class TentativeCodeAccesAdmin(admin.ModelAdmin):
    list_display = ['adresse_ip', 'succes', 'date_tentative', 'user_agent_court']
    list_filter = ['succes', 'date_tentative']
    search_fields = ['adresse_ip']
    readonly_fields = ['adresse_ip', 'code_saisi', 'succes', 'date_tentative', 'user_agent']
    list_per_page = 50

    def user_agent_court(self, obj):
        return (obj.user_agent or '')[:80]
    user_agent_court.short_description = 'User Agent'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Societe)
class SocieteAdmin(admin.ModelAdmin):
    list_display = ['raison_sociale', 'nif', 'num_cnss_employeur', 'ville', 'actif']
    list_filter = ['actif', 'ville']
    search_fields = ['raison_sociale', 'nif']
    fieldsets = (
        ('Informations générales', {
            'fields': ('raison_sociale', 'forme_juridique', 'secteur_activite', 'code_ape', 'logo')
        }),
        ('Immatriculation', {
            'fields': ('nif', 'num_cnss_employeur', 'num_inam')
        }),
        ('Coordonnées', {
            'fields': ('adresse', 'commune', 'prefecture', 'ville', 'pays', 'telephone', 'email', 'site_web')
        }),
        ('Informations financières', {
            'fields': ('date_creation', 'capital_social')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(entreprise=request.user.entreprise)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and not getattr(obj, 'entreprise_id', None):
            obj.entreprise = request.user.entreprise
        super().save_model(request, obj, form, change)


@admin.register(Etablissement)
class EtablissementAdmin(admin.ModelAdmin):
    list_display = ['code_etablissement', 'nom_etablissement', 'type_etablissement', 'ville', 'actif']
    list_filter = ['type_etablissement', 'actif', 'ville']
    search_fields = ['code_etablissement', 'nom_etablissement']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(societe__entreprise=request.user.entreprise)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.name == 'societe':
            kwargs['queryset'] = Societe.objects.filter(entreprise=request.user.entreprise)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['code_service', 'nom_service', 'etablissement', 'responsable_service', 'actif']
    list_filter = ['actif', 'etablissement']
    search_fields = ['code_service', 'nom_service']
    raw_id_fields = ['responsable_service']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(etablissement__societe__entreprise=request.user.entreprise)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.name == 'etablissement':
            kwargs['queryset'] = Etablissement.objects.filter(societe__entreprise=request.user.entreprise)
        if not request.user.is_superuser and db_field.name == 'responsable_service':
            kwargs['queryset'] = db_field.remote_field.model.objects.filter(entreprise=request.user.entreprise)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Poste)
class PosteAdmin(admin.ModelAdmin):
    list_display = ['code_poste', 'intitule_poste', 'service', 'categorie_professionnelle', 'actif']
    list_filter = ['categorie_professionnelle', 'actif']
    search_fields = ['code_poste', 'intitule_poste']
    fieldsets = (
        ('Informations de base', {
            'fields': ('code_poste', 'intitule_poste', 'service', 'categorie_professionnelle', 'classification')
        }),
        ('Prérequis', {
            'fields': ('niveau_requis', 'experience_requise')
        }),
        ('Description', {
            'fields': ('description_poste', 'responsabilites', 'competences_requises')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(service__etablissement__societe__entreprise=request.user.entreprise)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.name == 'service':
            kwargs['queryset'] = Service.objects.filter(etablissement__societe__entreprise=request.user.entreprise)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


from .models import AccesEntreprise


@admin.register(AccesEntreprise)
class AccesEntrepriseAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'entreprise', 'role', 'date_debut', 'date_fin', 'actif', 'accorde_par']
    list_filter = ['role', 'actif', 'entreprise']
    search_fields = ['utilisateur__username', 'utilisateur__email', 'entreprise__nom_entreprise']
    autocomplete_fields = []


from .models import PermissionRole, Delegation


@admin.register(PermissionRole)
class PermissionRoleAdmin(admin.ModelAdmin):
    list_display = ['role', 'permission']
    list_filter = ['role']
    search_fields = ['permission']


@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = ['delegant', 'delegataire', 'entreprise', 'date_debut', 'date_fin', 'motif', 'actif']
    list_filter = ['actif', 'entreprise']
    search_fields = ['delegant__username', 'delegataire__username', 'motif']
