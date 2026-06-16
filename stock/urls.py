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
    path('fournisseurs/<int:pk>/modifier/', views.fournisseur_edit, name='fournisseur_edit'),
    path('fournisseurs/<int:pk>/supprimer/', views.fournisseur_delete, name='fournisseur_delete'),

    # Mouvements de stock
    path('mouvements/', views.mouvement_list, name='mouvement_list'),
    path('mouvements/nouveau/', views.mouvement_create, name='mouvement_create'),

    # Inventaires
    path('inventaires/', views.inventaire_list, name='inventaire_list'),
    path('inventaires/nouveau/', views.inventaire_create, name='inventaire_create'),
    path('inventaires/<int:pk>/', views.inventaire_detail, name='inventaire_detail'),
    path('inventaires/<int:pk>/valider/', views.inventaire_valider, name='inventaire_valider'),
    path('inventaires/<int:pk>/supprimer/', views.inventaire_delete, name='inventaire_delete'),

    # Rapports
    path('rapports/', views.rapports, name='rapports'),
]
