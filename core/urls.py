from django.urls import path
from . import views
from .views_modules import cnss, expatries, inspection
from . import views_dashboard
from . import views_licence

app_name = 'core'

urlpatterns = [
    # Licence
    path('licence/', views_licence.licence_statut, name='licence_statut'),
    path('licence/activer/', views_licence.licence_activation, name='licence_activation'),
    path('licence/renouveler/', views_licence.licence_renouveler, name='licence_renouveler'),
    path('licence/expiree/', views_licence.licence_expiree, name='licence_expiree'),
    path('api/licence/verifier/', views_licence.api_verifier_licence, name='api_verifier_licence'),
    
    path('', views.index_view, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('documentation-legale/', views.documentation_legale, name='documentation_legale'),
    path('documentation-legale/print/', views.documentation_legale_print, name='documentation_legale_print'),
    path('guide-utilisateur/', views.guide_utilisateur, name='guide_utilisateur'),
    path('profile/', views.profile_view, name='profile'),
    path('users/', views.profile_view, name='users'),
    path('parametres/', views.profile_view, name='parametres'),
    
    # Multi-entreprise
    path('changer-societe/', views.changer_societe, name='changer_societe'),
    path('register-entreprise/', views.register_entreprise, name='register_entreprise'),
    path('reauth/', views.reauth_view, name='reauth'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('toggle-user-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('send-invitation/', views.send_invitation, name='send_invitation'),
    
    # Superuser - contrôle global
    path('superuser/users/', views.superuser_manage_users, name='superuser_manage_users'),
    path('superuser/toggle-user/<int:user_id>/', views.superuser_toggle_user, name='superuser_toggle_user'),
    path('superuser/delete-user/<int:user_id>/', views.superuser_delete_user, name='superuser_delete_user'),
    path('superuser/delete-entreprise/<uuid:entreprise_id>/', views.superuser_delete_entreprise, name='superuser_delete_entreprise'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('entreprise-settings/', views.entreprise_settings, name='entreprise_settings'),
    
    # Gestion structure entreprise (Etablissements, Services, Postes)
    path('structure/', views.gestion_structure, name='gestion_structure'),
    path('structure/etablissement/creer/', views.creer_etablissement, name='creer_etablissement'),
    path('structure/etablissement/<int:pk>/supprimer/', views.supprimer_etablissement, name='supprimer_etablissement'),
    path('structure/service/creer/', views.creer_service, name='creer_service'),
    path('structure/service/<int:pk>/supprimer/', views.supprimer_service, name='supprimer_service'),
    path('structure/poste/creer/', views.creer_poste, name='creer_poste'),
    path('structure/poste/<int:pk>/supprimer/', views.supprimer_poste, name='supprimer_poste'),
    
    # CNSS Télédéclaration
    path('cnss/', cnss.cnss_dashboard, name='cnss_dashboard'),
    path('cnss/configuration/', cnss.cnss_configuration, name='cnss_configuration'),
    path('cnss/generer/', cnss.cnss_generer_declaration, name='cnss_generer'),
    path('cnss/<int:pk>/', cnss.cnss_detail, name='cnss_detail'),
    path('cnss/<int:pk>/telecharger/', cnss.cnss_telecharger, name='cnss_telecharger'),
    path('cnss/<int:pk>/transmis/', cnss.cnss_marquer_transmis, name='cnss_marquer_transmis'),
    path('cnss/historique/', cnss.cnss_historique, name='cnss_historique'),
    
    # Gestion des expatriés
    path('expatries/', expatries.expatries_liste, name='expatries_liste'),
    path('expatries/ajouter/', expatries.expatrie_ajouter, name='expatrie_ajouter'),
    path('expatries/<int:pk>/', expatries.expatrie_detail, name='expatrie_detail'),
    path('expatries/<int:pk>/modifier/', expatries.expatrie_modifier, name='expatrie_modifier'),
    path('expatries/<int:pk>/supprimer/', expatries.expatrie_supprimer, name='expatrie_supprimer'),
    path('expatries/<int:expatrie_id>/permis/ajouter/', expatries.permis_ajouter, name='permis_ajouter'),
    path('expatries/permis/<int:pk>/modifier/', expatries.permis_modifier, name='permis_modifier'),
    path('expatries/alertes/', expatries.alertes_expatries, name='alertes_expatries'),
    
    # Inspection du travail
    path('inspection/', inspection.inspection_dashboard, name='inspection_dashboard'),
    path('inspection/registres/', inspection.registres_liste, name='registres_liste'),
    path('inspection/registres/ajouter/', inspection.registre_ajouter, name='registre_ajouter'),
    path('inspection/registres/<int:pk>/modifier/', inspection.registre_modifier, name='registre_modifier'),
    path('inspection/visites/', inspection.visites_liste, name='visites_liste'),
    path('inspection/visites/ajouter/', inspection.visite_ajouter, name='visite_ajouter'),
    path('inspection/visites/<int:pk>/', inspection.visite_detail, name='visite_detail'),
    path('inspection/checklist/', inspection.checklist_conformite, name='checklist_conformite'),
    path('inspection/rapport/', inspection.generer_rapport_conformite, name='generer_rapport'),
    
    # Tableau de bord RH
    path('dashboard-rh/', views_dashboard.tableau_bord_rh, name='tableau_bord_rh'),
    
    # Documentation
    path('documentation/telecharger/', views.telecharger_documentation, name='telecharger_documentation'),
    
    # Partenariat
    path('partenariat/', views.demande_partenariat, name='demande_partenariat'),
    path('superuser/partenariats/', views.superuser_demandes_partenariat, name='superuser_demandes_partenariat'),
    path('superuser/partenariats/<int:pk>/', views.superuser_demande_detail, name='superuser_demande_detail'),
    path('superuser/partenariats/<int:pk>/document/<str:type_doc>/', views.telecharger_document_partenariat, name='telecharger_document_partenariat'),
]
