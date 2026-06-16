"""Crée un dépôt « Magasin principal » par entreprise ayant des articles et
y bascule le stock et les mouvements existants (transition mono → multi-dépôts).

Réversible : la suppression des dépôts par défaut recrée l'état mono-dépôt
(les quantités restent portées par Article.quantite_stock)."""
from django.db import migrations


def creer_depots_par_defaut(apps, schema_editor):
    Entreprise = apps.get_model('core', 'Entreprise')
    Depot = apps.get_model('stock', 'Depot')
    Article = apps.get_model('stock', 'Article')
    StockArticleDepot = apps.get_model('stock', 'StockArticleDepot')
    MouvementStock = apps.get_model('stock', 'MouvementStock')

    # Entreprises concernées : celles qui ont au moins un article.
    ids_entreprises = Article.objects.values_list('entreprise_id', flat=True).distinct()
    for entreprise in Entreprise.objects.filter(id__in=list(ids_entreprises)):
        depot = (Depot.objects.filter(entreprise=entreprise, par_defaut=True).first()
                 or Depot.objects.filter(entreprise=entreprise).first())
        if depot is None:
            depot = Depot.objects.create(
                entreprise=entreprise, nom='Magasin principal',
                type_depot='principal', par_defaut=True, actif=True,
            )

        # Stock courant de chaque article -> ligne de stock dans le dépôt par défaut.
        for article in Article.objects.filter(entreprise=entreprise):
            StockArticleDepot.objects.get_or_create(
                article=article, depot=depot,
                defaults={'quantite': article.quantite_stock or 0},
            )

        # Mouvements existants sans dépôt -> rattachés au dépôt par défaut.
        MouvementStock.objects.filter(entreprise=entreprise, depot__isnull=True).update(depot=depot)


def supprimer_depots_par_defaut(apps, schema_editor):
    # On retire uniquement les lignes de stock et le rattachement des mouvements ;
    # les dépôts eux-mêmes sont supprimés par l'annulation de la migration 0002.
    StockArticleDepot = apps.get_model('stock', 'StockArticleDepot')
    MouvementStock = apps.get_model('stock', 'MouvementStock')
    MouvementStock.objects.update(depot=None)
    StockArticleDepot.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0002_article_code_barres_article_photo_article_stock_max_and_more'),
    ]

    operations = [
        migrations.RunPython(creer_depots_par_defaut, supprimer_depots_par_defaut),
    ]
