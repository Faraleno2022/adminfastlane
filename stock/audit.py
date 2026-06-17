"""
Traçabilité du module Stock.

- Un middleware mémorise l'utilisateur courant dans un thread-local.
- Des signaux post_save / post_delete journalisent automatiquement toute
  création / modification / suppression sur les modèles métier du stock.

Ainsi, chaque action est tracée (qui, quand, quoi) sans modifier les vues.
"""
import threading

from django.db.models.signals import post_save, post_delete
from django.apps import apps

_local = threading.local()


def set_current_user(user):
    _local.user = user if (user and getattr(user, 'is_authenticated', False)) else None


def get_current_user():
    return getattr(_local, 'user', None)


class CurrentUserMiddleware:
    """Mémorise l'utilisateur de la requête pour les signaux d'audit."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, 'user', None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)


# Modèles métier journalisés (on exclut les lignes, le stock par dépôt et les
# modèles d'audit/rôles eux-mêmes pour éviter le bruit et la récursion).
MODELES_AUDITES = [
    'CategorieArticle', 'Fournisseur', 'Depot', 'Article', 'MouvementStock',
    'Transfert', 'Inventaire', 'CommandeFournisseur', 'Reception',
    'FactureFournisseur', 'PaiementFournisseur', 'Client', 'DocumentVente',
    'BonLivraison', 'PaiementClient',
]


def _enregistrer(instance, action):
    from .models import JournalAudit
    entreprise = getattr(instance, 'entreprise', None)
    # Certains modèles (Reception, BonLivraison...) portent l'entreprise via une relation.
    if entreprise is None:
        for attr in ('commande', 'document'):
            parent = getattr(instance, attr, None)
            if parent is not None and getattr(parent, 'entreprise', None) is not None:
                entreprise = parent.entreprise
                break
    JournalAudit.objects.create(
        entreprise=entreprise,
        utilisateur=get_current_user(),
        action=action,
        objet_type=instance._meta.verbose_name,
        objet_id=str(instance.pk),
        objet_libelle=str(instance)[:255],
    )


def _on_save(sender, instance, created, **kwargs):
    _enregistrer(instance, 'creation' if created else 'modification')


def _on_delete(sender, instance, **kwargs):
    _enregistrer(instance, 'suppression')


def connecter_signaux():
    """Connecte les signaux d'audit aux modèles métier (appelé dans apps.ready)."""
    for nom in MODELES_AUDITES:
        modele = apps.get_model('stock', nom)
        post_save.connect(_on_save, sender=modele, dispatch_uid=f'audit_save_{nom}')
        post_delete.connect(_on_delete, sender=modele, dispatch_uid=f'audit_delete_{nom}')
