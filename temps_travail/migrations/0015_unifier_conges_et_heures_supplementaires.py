from decimal import Decimal

from django.db import migrations, models


def convertir_anciens_types_hs(apps, schema_editor):
    HeureSupplementaire = apps.get_model('temps_travail', 'HeureSupplementaire')
    correspondances = {
        'jour_15': 'jour_30',
        'jour_25': 'jour_30',
        'jour_50': 'jour_60',
        'nuit_50': 'nuit_20',
        'dimanche_75': 'ferie_60',
        'dimanche_nuit_100': 'ferie_nuit_100',
    }
    for ancien, nouveau in correspondances.items():
        HeureSupplementaire.objects.filter(type_hs=ancien).update(type_hs=nouveau)


class Migration(migrations.Migration):

    dependencies = [
        ('temps_travail', '0014_alter_parametrageconges_jours_conges_annuels_and_more'),
    ]

    operations = [
        migrations.RunPython(convertir_anciens_types_hs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='soldeconge',
            name='conges_acquis',
            field=models.DecimalField(decimal_places=2, default=30.0, max_digits=5),
        ),
        migrations.AlterField(
            model_name='soldeconge',
            name='conges_restants',
            field=models.DecimalField(decimal_places=2, default=30.0, max_digits=5),
        ),
        migrations.AlterField(
            model_name='heuresupplementaire',
            name='type_hs',
            field=models.CharField(
                choices=[
                    ('jour_30', '4 premières heures/semaine (+30%)'),
                    ('jour_60', 'Au-delà de 4 heures/semaine (+60%)'),
                    ('nuit_20', 'Heures de nuit (+20%)'),
                    ('ferie_60', 'Jour férié (+60%)'),
                    ('ferie_nuit_100', 'Jour férié de nuit (+100%)'),
                ],
                default='jour_30',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='reglementationtemps',
            name='jours_conges_annuels',
            field=models.DecimalField(
                decimal_places=2,
                default=30.0,
                help_text='Jours de congés annuels (2,5j ouvrables/mois)',
                max_digits=4,
            ),
        ),
    ]
