"""Compatibilité : l'isolation par entreprise est désormais dans ``core.tenancy``."""
from core.tenancy import (  # noqa: F401
    NON_DEFINIE, definir_entreprise, entreprise_courante, pour_entreprise, reinitialiser,
)
