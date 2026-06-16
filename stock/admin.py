from django.contrib import admin

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock,
    Inventaire, LigneInventaire,
)


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
    search_fields = ('reference', 'designation', 'emplacement')
    readonly_fields = ('quantite_stock',)


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ('date_mouvement', 'type_mouvement', 'article', 'quantite',
                    'quantite_avant', 'quantite_apres', 'cree_par')
    list_filter = ('type_mouvement', 'entreprise')
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
