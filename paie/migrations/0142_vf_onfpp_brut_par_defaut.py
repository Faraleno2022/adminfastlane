from django.db import migrations, models


def appliquer_bases_legales_par_defaut(apps, schema_editor):
    Parametres = apps.get_model('paie', 'ParametresCalculPaie')
    Parametres.objects.filter(mode_base_vf='brut_moins_deduction').update(
        mode_base_vf='brut',
        formule_base_vf='',
    )
    Parametres.objects.filter(mode_base_onfpp='base_vf').update(mode_base_onfpp='brut')


class Migration(migrations.Migration):
    dependencies = [('paie', '0141_aligner_parametres_rh_legaux')]

    operations = [
        migrations.AlterField(
            model_name='bulletinpaie',
            name='base_vf',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Base de calcul du VF (brut par défaut)',
                max_digits=15,
            ),
        ),
        migrations.AlterField(
            model_name='parametrescalculpaie',
            name='mode_base_vf',
            field=models.CharField(
                choices=[
                    ('brut_moins_deduction', 'Mode historique non standard : VF/TA sur brut - deduction'),
                    ('brut', 'Mode legal par defaut : VF/TA sur salaire brut'),
                    ('formule', 'Formule personnalisee'),
                ],
                default='brut',
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='parametrescalculpaie',
            name='mode_base_onfpp',
            field=models.CharField(
                choices=[
                    ('base_vf', 'Mode personnalise : ONFPP sur base VF/TA'),
                    ('brut', 'Mode legal par defaut : ONFPP sur salaire brut'),
                ],
                default='brut',
                max_length=20,
            ),
        ),
        migrations.RunPython(appliquer_bases_legales_par_defaut, migrations.RunPython.noop),
    ]

