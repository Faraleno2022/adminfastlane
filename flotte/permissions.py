"""Droits d'accès du module Flotte.

- administrateur : tout (référentiel + écritures + suppression) ;
- saisie         : création/modification des écritures (pas le référentiel) ;
- lecture        : consultation seule.

Le rôle se déduit du compte : superutilisateur, administrateur de l'entreprise
ou niveau d'accès 5 -> administrateur ; niveau d'accès >= 2 -> saisie. Les
groupes Django « admin » et « saisie » restent pris en compte.
"""


def _groupes(user):
    if not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True))


def _niveau(user):
    profil = getattr(user, "profil", None)
    return getattr(profil, "niveau_acces", 0) or 0


def peut_gerer_referentiel(user):
    """Véhicules, chauffeurs, marques, engins, catégories, documents."""
    if not user.is_authenticated:
        return False
    return bool(
        user.is_superuser
        or getattr(user, "est_admin_entreprise", False)
        or _niveau(user) >= 5
        or "admin" in _groupes(user)
    )


def peut_saisir(user):
    """Écritures : entretien, carburant, voyages, pointage, stock, etc."""
    if not user.is_authenticated:
        return False
    return bool(
        peut_gerer_referentiel(user)
        or _niveau(user) >= 2
        or "saisie" in _groupes(user)
    )
