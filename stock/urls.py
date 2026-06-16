from django.urls import path

from . import views

app_name = 'stock'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Articles
    path('articles/', views.article_list, name='article_list'),
    path('articles/nouveau/', views.article_create, name='article_create'),
    path('articles/<int:pk>/', views.article_detail, name='article_detail'),
    path('articles/<int:pk>/modifier/', views.article_edit, name='article_edit'),
    path('articles/<int:pk>/supprimer/', views.article_delete, name='article_delete'),

    # Catégories
    path('categories/', views.categorie_list, name='categorie_list'),
    path('categories/nouvelle/', views.categorie_create, name='categorie_create'),
    path('categories/<int:pk>/modifier/', views.categorie_edit, name='categorie_edit'),
    path('categories/<int:pk>/supprimer/', views.categorie_delete, name='categorie_delete'),

    # Fournisseurs
    path('fournisseurs/', views.fournisseur_list, name='fournisseur_list'),
    path('fournisseurs/nouveau/', views.fournisseur_create, name='fournisseur_create'),
    path('fournisseurs/<int:pk>/', views.fournisseur_detail, name='fournisseur_detail'),
    path('fournisseurs/<int:pk>/modifier/', views.fournisseur_edit, name='fournisseur_edit'),
    path('fournisseurs/<int:pk>/supprimer/', views.fournisseur_delete, name='fournisseur_delete'),

    # Commandes fournisseurs (achats)
    path('commandes/', views.commande_list, name='commande_list'),
    path('commandes/nouvelle/', views.commande_create, name='commande_create'),
    path('commandes/<int:pk>/', views.commande_detail, name='commande_detail'),
    path('commandes/<int:pk>/modifier/', views.commande_edit, name='commande_edit'),
    path('commandes/<int:pk>/valider/', views.commande_valider, name='commande_valider'),
    path('commandes/<int:pk>/annuler/', views.commande_annuler, name='commande_annuler'),
    path('commandes/<int:pk>/reception/', views.reception_create, name='reception_create'),
    path('commandes/lignes/<int:pk>/supprimer/', views.ligne_commande_delete, name='ligne_commande_delete'),

    # Factures fournisseurs
    path('factures-fournisseur/', views.facture_list, name='facture_list'),
    path('factures-fournisseur/nouvelle/', views.facture_create, name='facture_create'),
    path('factures-fournisseur/<int:pk>/', views.facture_detail, name='facture_detail'),
    path('factures-fournisseur/<int:pk>/supprimer/', views.facture_delete, name='facture_delete'),

    # Dépôts
    path('depots/', views.depot_list, name='depot_list'),
    path('depots/nouveau/', views.depot_create, name='depot_create'),
    path('depots/<int:pk>/modifier/', views.depot_edit, name='depot_edit'),
    path('depots/<int:pk>/supprimer/', views.depot_delete, name='depot_delete'),

    # Mouvements de stock
    path('mouvements/', views.mouvement_list, name='mouvement_list'),
    path('mouvements/nouveau/', views.mouvement_create, name='mouvement_create'),

    # Transferts entre dépôts
    path('transferts/', views.transfert_list, name='transfert_list'),
    path('transferts/nouveau/', views.transfert_create, name='transfert_create'),

    # Inventaires
    path('inventaires/', views.inventaire_list, name='inventaire_list'),
    path('inventaires/nouveau/', views.inventaire_create, name='inventaire_create'),
    path('inventaires/<int:pk>/', views.inventaire_detail, name='inventaire_detail'),
    path('inventaires/<int:pk>/valider/', views.inventaire_valider, name='inventaire_valider'),
    path('inventaires/<int:pk>/supprimer/', views.inventaire_delete, name='inventaire_delete'),

    # Rapports
    path('rapports/', views.rapports, name='rapports'),
]
