from decimal import Decimal

from django.db import migrations


def normaliser_heures_supplementaires_code_travail(apps, schema_editor):
    """Aligne les taux existants sur le mode explicitement sélectionné."""
    Configuration = apps.get_model('paie', 'ConfigurationPaieEntreprise')
    Configuration.objects.filter(mode_heures_sup='code_travail').update(
        taux_hs_4_premieres=Decimal('30.00'),
        taux_hs_au_dela=Decimal('60.00'),
        taux_hs_nuit=Decimal('20.00'),
        taux_hs_dimanche=Decimal('60.00'),
        taux_hs_ferie_nuit=Decimal('100.00'),
    )


class Migration(migrations.Migration):
    dependencies = [
        ('paie', '0142_vf_onfpp_brut_par_defaut'),
    ]

    operations = [
        migrations.RunPython(
            normaliser_heures_supplementaires_code_travail,
            migrations.RunPython.noop,
        ),
    ]
