"""
Utilitaires de licence offline — GestionnaireRH Guinée
=======================================================
Une licence fichier valide (license.dat / .lic via license_manager)
débloque TOUS les modules de l'application : aucun module ne doit être
masqué, grisé ou bloqué pour un utilisateur licencié, et les quotas
« plan d'abonnement » (logique SaaS) ne s'appliquent pas.
"""
import time

# Cache mémoire pour éviter une lecture fichier à chaque accès
_cache = {'valid': None, 'checked_at': 0.0}
_CACHE_TTL = 300  # 5 minutes


def licence_offline_valide() -> bool:
    """
    True si une licence offline valide (hors période d'essai) est installée
    sur cette machine. Résultat mis en cache 5 minutes.
    """
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
