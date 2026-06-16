from django.contrib import admin

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock,
    Inventaire, LigneInventaire, Depot, StockArticleDepot, Transfert,
    CommandeFournisseur, LigneCommande, Reception, LigneReception,
    FactureFournisseur, PaiementFournisseur,
)


class LigneCommandeInline(admin.TabularInline):
    model = LigneCommande
    extra = 0


@admin.register(CommandeFournisseur)
class CommandeFournisseurAdmin(admin.ModelAdmin):
    list_display = ('reference', 'fournisseur', 'statut', 'date_commande', 'depot', 'entreprise')
    list_filter = ('statut', 'entreprise')
    search_fields = ('reference', 'fournisseur__nom')
    date_hierarchy = 'date_commande'
    inlines = [LigneCommandeInline]


class LigneReceptionInline(admin.TabularInline):
    model = LigneReception
    extra = 0


@admin.register(Reception)
class ReceptionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'commande', 'depot', 'date_reception')
    list_filter = ('entreprise', 'depot')
    search_fields = ('reference', 'commande__reference')
    inlines = [LigneReceptionInline]


class PaiementFournisseurInline(admin.TabularInline):
    model = PaiementFournisseur
    extra = 0


@admin.register(FactureFournisseur)
class FactureFournisseurAdmin(admin.ModelAdmin):
    list_display = ('numero', 'fournisseur', 'date_facture', 'montant_ht', 'montant_paye', 'statut')
    list_filter = ('statut', 'entreprise')
    search_fields = ('numero', 'fournisseur__nom')
    date_hierarchy = 'date_facture'
    inlines = [PaiementFournisseurInline]


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_depot', 'responsable', 'par_defaut', 'actif', 'entreprise')
    list_filter = ('type_depot', 'actif', 'par_defaut', 'entreprise')
    search_fields = ('nom', 'code', 'responsable')


@admin.register(StockArticleDepot)
class StockArticleDepotAdmin(admin.ModelAdmin):
    list_display = ('article', 'depot', 'quantite')
    list_filter = ('depot',)
    search_fields = ('article__reference', 'article__designation')


@admin.register(Transfert)
class TransfertAdmin(admin.ModelAdmin):
    list_display = ('reference', 'article', 'depot_source', 'depot_destination', 'quantite', 'date_transfert')
    list_filter = ('entreprise', 'depot_source', 'depot_destination')
    search_fields = ('reference', 'article__designation')
    date_hierarchy = 'date_transfert'


@admin.register(CategorieArticle)
class CategorieArticleAdmin(admin.ModelAdmin):
    list_display = ('nom', 'actif', 'entreprise')
    list_filter = ('actif', 'entreprise')
    search_fields = ('nom',)


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ('nom', 'contact', 'telephone', 'email', 'actif')
    list_filter = ('actif', 'entreprise')
    search_fields = ('nom', 'contact', 'email', 'telephone')


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('reference', 'designation', 'categorie', 'quantite_stock',
                    'seuil_alerte', 'prix_achat', 'prix_vente', 'actif')
    list_filter = ('actif', 'categorie', 'unite', 'entreprise')
    search_fields = ('reference', 'code_barres', 'designation', 'emplacement')
    readonly_fields = ('quantite_stock',)


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ('date_mouvement', 'type_mouvement', 'article', 'depot', 'quantite',
                    'quantite_avant', 'quantite_apres', 'cree_par')
    list_filter = ('type_mouvement', 'depot', 'entreprise')
    search_fields = ('article__reference', 'article__designation', 'motif', 'reference_document')
    date_hierarchy = 'date_mouvement'


class LigneInventaireInline(admin.TabularInline):
    model = LigneInventaire
    extra = 0
    readonly_fields = ('ecart',)


@admin.register(Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    list_display = ('reference', 'date_inventaire', 'statut', 'entreprise')
    list_filter = ('statut', 'entreprise')
    search_fields = ('reference',)
    inlines = [LigneInventaireInline]
