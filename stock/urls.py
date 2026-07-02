from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token

from . import views
from .api import router as api_router

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

    # Expression de besoin (achat)
    path('besoins-achat/', views.besoin_achat_list, name='besoin_achat_list'),
    path('besoins-achat/nouveau/', views.besoin_achat_create, name='besoin_achat_create'),
    path('besoins-achat/<int:pk>/', views.besoin_achat_detail, name='besoin_achat_detail'),
    path('besoins-achat/<int:pk>/valider/', views.besoin_achat_valider, name='besoin_achat_valider'),
    path('besoins-achat/<int:pk>/rejeter/', views.besoin_achat_rejeter, name='besoin_achat_rejeter'),
    path('besoins-achat/lignes/<int:pk>/supprimer/', views.ligne_besoin_achat_delete, name='ligne_besoin_achat_delete'),

    # Réapprovisionnement
    path('reapprovisionnement/', views.reapprovisionnement, name='reapprovisionnement'),

    # Factures fournisseurs
    path('factures-fournisseur/', views.facture_list, name='facture_list'),
    path('factures-fournisseur/nouvelle/', views.facture_create, name='facture_create'),
    path('factures-fournisseur/<int:pk>/', views.facture_detail, name='facture_detail'),
    path('factures-fournisseur/<int:pk>/supprimer/', views.facture_delete, name='facture_delete'),

    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/nouveau/', views.client_create, name='client_create'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/modifier/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/supprimer/', views.client_delete, name='client_delete'),
    path('clients/prix-special/<int:pk>/supprimer/', views.prix_special_delete, name='prix_special_delete'),

    # Expression de besoin (vente)
    path('demandes-vente/', views.demande_vente_list, name='demande_vente_list'),
    path('demandes-vente/nouveau/', views.demande_vente_create, name='demande_vente_create'),
    path('demandes-vente/<int:pk>/', views.demande_vente_detail, name='demande_vente_detail'),
    path('demandes-vente/<int:pk>/valider/', views.demande_vente_valider, name='demande_vente_valider'),
    path('demandes-vente/<int:pk>/rejeter/', views.demande_vente_rejeter, name='demande_vente_rejeter'),
    path('demandes-vente/lignes/<int:pk>/supprimer/', views.ligne_demande_vente_delete, name='ligne_demande_vente_delete'),

    # Ventes (devis / proforma / factures)
    path('ventes/', views.vente_list, name='vente_list'),
    path('ventes/nouveau/', views.vente_create, name='vente_create'),
    path('ventes/<int:pk>/', views.vente_detail, name='vente_detail'),
    path('ventes/<int:pk>/modifier/', views.vente_edit, name='vente_edit'),
    path('ventes/<int:pk>/statut/<str:action>/', views.vente_statut, name='vente_statut'),
    path('ventes/<int:pk>/convertir/', views.vente_convertir, name='vente_convertir'),
    path('ventes/<int:pk>/annuler/', views.vente_annuler, name='vente_annuler'),
    path('ventes/<int:pk>/paiement/', views.vente_paiement, name='vente_paiement'),
    path('ventes/<int:pk>/livraison/', views.livraison_create, name='livraison_create'),
    path('ventes/lignes/<int:pk>/supprimer/', views.ligne_vente_delete, name='ligne_vente_delete'),

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

    # Rapports & exports
    path('rapports/', views.rapports, name='rapports'),
    path('rapports/export/stock/<str:fmt>/', views.export_stock, name='export_stock'),
    path('rapports/export/mouvements/<str:fmt>/', views.export_mouvements, name='export_mouvements'),
    path('rapports/export/ventes/<str:fmt>/', views.export_ventes, name='export_ventes'),
    path('rapports/export/achats/<str:fmt>/', views.export_achats, name='export_achats'),
    path('ventes/<int:pk>/pdf/', views.vente_pdf, name='vente_pdf'),

    # Lots, numéros de série & péremption
    path('lots/', views.lot_list, name='lot_list'),
    path('lots/nouveau/', views.lot_create, name='lot_create'),
    path('lots/<int:pk>/modifier/', views.lot_edit, name='lot_edit'),
    path('lots/<int:pk>/supprimer/', views.lot_delete, name='lot_delete'),
    path('series/', views.serie_list, name='serie_list'),
    path('series/nouveau/', views.serie_create, name='serie_create'),
    path('series/<int:pk>/modifier/', views.serie_edit, name='serie_edit'),
    path('series/<int:pk>/supprimer/', views.serie_delete, name='serie_delete'),
    path('peremptions/', views.peremptions, name='peremptions'),

    # Traçabilité & rôles
    path('journal/', views.journal_audit, name='journal_audit'),
    path('roles/', views.roles_list, name='roles_list'),
    path('api-info/', views.api_info, name='api_info'),

    # API REST
    path('api/', include(api_router.urls)),
    path('api/token/', obtain_auth_token, name='api_token'),
]
