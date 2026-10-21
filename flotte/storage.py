"""Stockage privé des pièces jointes de la flotte (hors du dossier /media/ public)."""
from django.conf import settings
from django.core.files.storage import FileSystemStorage


def documents_storage():
    """Callable (sérialisé tel quel dans les migrations) : chemin propre à chaque installation."""
    return FileSystemStorage(location=str(settings.FLOTTE_DOCUMENTS_ROOT))
