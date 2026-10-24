"""
Utilitaires de licence offline — GestionnaireRH Guinée
=======================================================
Une licence fichier valide (license.dat / .lic via license_manager)
débloque TOUS les modules de l'application : aucun module ne doit être
masqué, grisé ou bloqué pour un utilisateur licencié, et les quotas
« plan d'abonnement » (logique SaaS) ne s'appliquent pas.
"""
import time

from django.conf import settings

# Cache mémoire pour éviter une lecture fichier à chaque accès
_cache = {'valid': None, 'checked_at': 0.0}
_CACHE_TTL = 300  # 5 minutes


def licence_offline_valide() -> bool:
    """
    True si tous les modules sont débloqués, sans plan ni quota : abonnements
    désactivés (ABONNEMENTS_ACTIFS=False), ou licence offline valide (hors période
    d'essai) installée sur cette machine. Lecture du fichier mise en cache 5 minutes.
    """
    if not getattr(settings, 'ABONNEMENTS_ACTIFS', True):
        return True
    now = time.time()
    if _cache['valid'] is None or now - _cache['checked_at'] > _CACHE_TTL:
        try:
            import license_manager
            status = license_manager.load_and_validate_license()
            _cache['valid'] = bool(status.get('valid'))
        except Exception:
            _cache['valid'] = False
        _cache['checked_at'] = now
    return _cache['valid']


def invalider_cache_licence():
    """Force une re-vérification de la licence au prochain appel."""
    _cache['valid'] = None
    _cache['checked_at'] = 0.0
