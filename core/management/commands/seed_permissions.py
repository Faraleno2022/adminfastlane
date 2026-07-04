"""Initialise les permissions par défaut de chaque rôle métier (idempotent)."""
from django.core.management.base import BaseCommand
from core.models import PermissionRole


class Command(BaseCommand):
    help = "Crée les permissions par défaut des rôles (comptable, chef comptable, DAF, DG, auditeur, administrateur)."

    def handle(self, *args, **options):
        crees = PermissionRole.initialiser_defauts()
        total = PermissionRole.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"{crees} permission(s) créée(s) — {total} au total."))
