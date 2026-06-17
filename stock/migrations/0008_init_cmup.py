"""Initialise le CMUP des articles existants à partir du prix d'achat.

Les futures entrées d'achat affineront automatiquement le CMUP."""
from django.db import migrations


def init_cmup(apps, schema_editor):
    Article = apps.get_model('stock', 'Article')
    for article in Article.objects.filter(cmup=0).exclude(prix_achat=0):
        article.cmup = article.prix_achat
        article.save(update_fields=['cmup'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0007_article_cmup'),
    ]

    operations = [
        migrations.RunPython(init_cmup, noop),
    ]
