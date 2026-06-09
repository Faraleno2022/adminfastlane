from django.urls import path

from . import views

app_name = 'secretariat'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Courrier
    path('courriers/', views.courrier_list, name='courrier_list'),
    path('courriers/nouveau/', views.courrier_create, name='courrier_create'),
    path('courriers/<int:pk>/modifier/', views.courrier_edit, name='courrier_edit'),
    path('courriers/<int:pk>/supprimer/', views.courrier_delete, name='courrier_delete'),

    # Rendez-vous
    path('rendez-vous/', views.rdv_list, name='rdv_list'),
    path('rendez-vous/nouveau/', views.rdv_create, name='rdv_create'),
    path('rendez-vous/<int:pk>/modifier/', views.rdv_edit, name='rdv_edit'),
    path('rendez-vous/<int:pk>/supprimer/', views.rdv_delete, name='rdv_delete'),

    # Visiteurs
    path('visiteurs/', views.visiteur_list, name='visiteur_list'),
    path('visiteurs/nouveau/', views.visiteur_create, name='visiteur_create'),
    path('visiteurs/<int:pk>/modifier/', views.visiteur_edit, name='visiteur_edit'),
    path('visiteurs/<int:pk>/sortie/', views.visiteur_sortie, name='visiteur_sortie'),
    path('visiteurs/<int:pk>/badge/', views.visiteur_badge, name='visiteur_badge'),
    path('visiteurs/<int:pk>/supprimer/', views.visiteur_delete, name='visiteur_delete'),

    # Appels
    path('appels/', views.appel_list, name='appel_list'),
    path('appels/nouveau/', views.appel_create, name='appel_create'),
    path('appels/<int:pk>/modifier/', views.appel_edit, name='appel_edit'),
    path('appels/<int:pk>/supprimer/', views.appel_delete, name='appel_delete'),

    # Documents
    path('documents/', views.document_list, name='document_list'),
    path('documents/nouveau/', views.document_create, name='document_create'),
    path('documents/<int:pk>/modifier/', views.document_edit, name='document_edit'),
    path('documents/<int:pk>/supprimer/', views.document_delete, name='document_delete'),

    # Tâches
    path('taches/', views.tache_list, name='tache_list'),
    path('taches/nouvelle/', views.tache_create, name='tache_create'),
    path('taches/<int:pk>/modifier/', views.tache_edit, name='tache_edit'),
    path('taches/<int:pk>/supprimer/', views.tache_delete, name='tache_delete'),

    # Contacts
    path('contacts/', views.contact_list, name='contact_list'),
    path('contacts/nouveau/', views.contact_create, name='contact_create'),
    path('contacts/<int:pk>/modifier/', views.contact_edit, name='contact_edit'),
    path('contacts/<int:pk>/supprimer/', views.contact_delete, name='contact_delete'),

    # Réunions
    path('reunions/', views.reunion_list, name='reunion_list'),
    path('reunions/nouvelle/', views.reunion_create, name='reunion_create'),
    path('reunions/<int:pk>/', views.reunion_detail, name='reunion_detail'),
    path('reunions/<int:pk>/modifier/', views.reunion_edit, name='reunion_edit'),
    path('reunions/<int:pk>/supprimer/', views.reunion_delete, name='reunion_delete'),
    path('reunions/actions/<int:pk>/supprimer/', views.action_delete, name='action_delete'),

    # Rapports
    path('rapports/', views.rapports, name='rapports'),

    # Paramètres
    path('parametres/', views.parametres, name='parametres'),
    path('parametres/modeles/nouveau/', views.modele_create, name='modele_create'),
    path('parametres/modeles/<int:pk>/modifier/', views.modele_edit, name='modele_edit'),
    path('parametres/modeles/<int:pk>/supprimer/', views.modele_delete, name='modele_delete'),
]
