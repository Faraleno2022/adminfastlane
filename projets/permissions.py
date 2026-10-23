"""Droits du module Gestion de projet, déduits des comptes existants.

- administrateur : superutilisateur, administrateur d'entreprise ou niveau d'accès 5 ;
- saisie         : administrateur ou niveau d'accès >= 2 (projets, tâches, équipe, mouvements) ;
- suppression    : administrateur ou niveau d'accès >= 3 ;
- consultation   : les autres comptes (lecture seule).
"""
from functools import wraps

from django.core.exceptions import PermissionDenied


def _niveau(user):
    return getattr(getattr(user, "profil", None), "niveau_acces", 0) or 0


def est_admin(user):
    return bool(
        user.is_authenticated
        and (user.is_superuser or getattr(user, "est_admin_entreprise", False) or _niveau(user) >= 5)
    )


def peut_supprimer(user):
    return bool(user.is_authenticated and (est_admin(user) or _niveau(user) >= 3))


def peut_saisir(user):
    return bool(user.is_authenticated and (est_admin(user) or _niveau(user) >= 2))


def exige(controle, message="Accès refusé."):
    """Décorateur : lève une 403 si ``controle(user)`` est faux."""
    def decorateur(vue):
        @wraps(vue)
        def interne(request, *args, **kwargs):
            if not controle(request.user):
                raise PermissionDenied(message)
            return vue(request, *args, **kwargs)
        return interne
    return decorateur


suppression_requise = exige(peut_supprimer, "Suppression réservée aux administrateurs et responsables.")
saisie_requise = exige(peut_saisir, "Vous n'avez pas le droit de saisir dans la gestion de projet.")
