"""Droits du module Ventes & caisse, déduits des comptes existants.

- administrateur : superutilisateur, administrateur d'entreprise ou niveau d'accès 5
  (produits, validations de stock, inventaire, paramètres, journal d'audit) ;
- responsable    : administrateur ou niveau d'accès >= 3 (suppression / restauration) ;
- caissier       : niveau d'accès >= 2 ou groupe « caissier » (dépôts, ventes, caisse) ;
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
    if not user.is_authenticated:
        return False
    return est_admin(user) or _niveau(user) >= 2 or user.groups.filter(name="caissier").exists()


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


admin_requis = exige(est_admin, "Page réservée aux administrateurs.")
suppression_requise = exige(peut_supprimer, "Suppression réservée aux administrateurs et responsables.")
saisie_requise = exige(peut_saisir, "Vous n'avez pas le droit de saisir des opérations.")
