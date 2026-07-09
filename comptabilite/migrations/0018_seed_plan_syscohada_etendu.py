from pathlib import Path
import ast

from django.db import migrations
from django.utils import timezone


def _load_plan_syscohada():
    command_path = (
        Path(__file__).resolve().parents[1]
        / "management"
        / "commands"
        / "seed_plan_syscohada.py"
    )
    module = ast.parse(command_path.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", None) == "PLAN_SYSCOHADA":
                    return ast.literal_eval(node.value)
    raise RuntimeError("PLAN_SYSCOHADA introuvable")


def seed_plan_syscohada(apps, schema_editor):
    Entreprise = apps.get_model("core", "Entreprise")
    PlanComptable = apps.get_model("comptabilite", "PlanComptable")
    plan = _load_plan_syscohada()
    now = timezone.now()

    comptes = []
    for entreprise in Entreprise.objects.filter(actif=True):
        existants = set(
            PlanComptable.objects.filter(entreprise=entreprise)
            .values_list("numero_compte", flat=True)
        )
        for numero, intitule in plan:
            if numero in existants:
                continue
            comptes.append(
                PlanComptable(
                    entreprise=entreprise,
                    numero_compte=numero,
                    intitule=intitule,
                    classe=numero[0],
                    est_actif=True,
                    solde_debiteur=0,
                    solde_crediteur=0,
                    date_creation=now,
                )
            )

    if comptes:
        PlanComptable.objects.bulk_create(comptes, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite", "0017_reglevalidation_demandeapprobation_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_plan_syscohada, migrations.RunPython.noop),
    ]
