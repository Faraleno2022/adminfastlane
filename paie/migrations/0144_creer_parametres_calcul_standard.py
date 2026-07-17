from decimal import Decimal

from django.db import migrations


def creer_parametres_calcul_standard(apps, schema_editor):
    Entreprise = apps.get_model('core', 'Entreprise')
    Parametres = apps.get_model('paie', 'ParametresCalculPaie')

    for entreprise_id in Entreprise.objects.values_list('pk', flat=True):
        Parametres.objects.get_or_create(
            entreprise_id=entreprise_id,
            defaults={
                'mode_exoneration_indemnites': 'plafond_pct',
                'plafond_exoneration_pct': Decimal('25.00'),
                'formule_exoneration': '',
                'mode_base_vf': 'brut',
                'formule_base_vf': '',
                'mode_base_onfpp': 'brut',
                'utiliser_formule_base_rts': False,
                'formule_base_rts': '',
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('paie', '0143_normaliser_hs_code_travail'),
    ]

    operations = [
        migrations.RunPython(
            creer_parametres_calcul_standard,
            migrations.RunPython.noop,
        ),
    ]
