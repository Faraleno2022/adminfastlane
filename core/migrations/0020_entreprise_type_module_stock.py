from django.db import migrations, models


class Migration(migrations.Migration):
    """Ajoute le type de compte « Gestion de Stock » aux choix de type_module.

    Migration ecrite a la main (changement de `choices` uniquement, aucun
    impact schema). On evite `makemigrations` qui regenererait a tort une
    suppression des modeles Licence/LicenceLocale definis dans
    core/models_licence.py (non importes au chargement de l'app).
    """

    dependencies = [
        ('core', '0019_alter_entreprise_type_module'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entreprise',
            name='type_module',
            field=models.CharField(
                choices=[
                    ('rh', 'Ressources Humaines'),
                    ('compta', 'Comptabilité'),
                    ('secretariat', 'Secrétariat'),
                    ('stock', 'Gestion de Stock'),
                    ('both', 'RH + Comptabilité'),
                    ('all', 'RH + Comptabilité + Secrétariat'),
                ],
                default='rh',
                max_length=20,
                verbose_name='Type de compte',
            ),
        ),
    ]
