from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paie', '0140_alter_configurationpaieentreprise_jours_conges_par_mois'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configurationpaieentreprise',
            name='mode_conges',
            field=models.CharField(
                choices=[
                    ('code_travail', 'Code du Travail (2,5 j/mois)'),
                    ('convention', 'Convention Collective (2,5 j/mois)'),
                    ('personnalise', 'Personnalisé'),
                ],
                default='code_travail',
                max_length=20,
                verbose_name='Mode calcul congés',
            ),
        ),
        migrations.AlterField(
            model_name='configurationpaieentreprise',
            name='taux_hs_nuit',
            field=models.DecimalField(
                decimal_places=2,
                default=20.0,
                help_text='20h-6h. Code du Travail: 20%, Convention: 50%',
                max_digits=5,
                verbose_name='Majoration heures de nuit (%)',
            ),
        ),
        migrations.AlterField(
            model_name='configurationpaieentreprise',
            name='taux_hs_dimanche',
            field=models.DecimalField(
                decimal_places=2,
                default=60.0,
                help_text='Jour férié: 60%',
                max_digits=5,
                verbose_name='Majoration dimanche/férié jour (%)',
            ),
        ),
    ]
