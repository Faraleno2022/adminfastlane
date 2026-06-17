"""
Contrôle d'accès du module Stock par rôle.

Domaines de permission :
- 'stock'   : articles, catégories, dépôts, mouvements, transferts, inventaires
- 'achats'  : commandes fournisseurs, réceptions, factures fournisseurs
- 'ventes'  : clients, devis/factures, livraisons, paiements clients
- 'rapports': consultation des rapports et exports
- 'admin'   : gestion des rôles utilisateurs

Lecture : tous les rôles peuvent consulter. Les décorateurs ne protègent que
les actions d'écriture / sensibles.

Par sécurité, un utilisateur SANS profil de rôle est considéré comme
administrateur (pas de blocage des installations existantes).
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

ROLE_PERMISSIONS = {
    'administrateur': {'stock', 'achats', 'ventes', 'rapports', 'admin'},
    'directeur': {'stock', 'achats', 'ventes', 'rapports'},
    'magasinier': {'stock', 'rapports'},
    'responsable_achat': {'achats', 'rapports'},
    'comptable': {'achats', 'ventes', 'rapports'},
    'auditeur': set(),  # lecture seule
}


def get_role(user):
    profil = getattr(user, 'profil_stock', None)
    return profil.role if profil else 'administrateur'


def a_permission(user, domaine):
    return domaine in ROLE_PERMISSIONS.get(get_role(user), set())


def require_perm(domaine):
    """Bloque l'accès à une vue d'écriture si le rôle n'a pas le domaine."""
    def decorateur(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not a_permission(request.user, domaine):
                messages.error(
                    request,
                    "Votre rôle ne vous autorise pas cette action (lecture seule ou accès limité)."
                )
                return redirect('stock:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorateur
