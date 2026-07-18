"""
Middleware de vérification de licence — GestionnaireRH Guinée
Bloque l'accès web si la licence ou l'essai sont expirés.
Vérifié à chaque requête (avec cache 5 min pour la performance).
"""
import time
from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.shortcuts import redirect
from django.http import HttpResponse
from django.contrib import messages


# ─── Cache en mémoire pour éviter une lecture de fichier à chaque requête ─────
_license_cache = {'valid': None, 'checked_at': 0, 'days_left': 0, 'trial': False}
_CACHE_TTL = 1800  # 30 minutes (licence vérifiée au démarrage)


def _check_license_cached() -> dict:
    """Vérifie la licence avec cache de 5 minutes."""
    global _license_cache
    now = time.time()
    if now - _license_cache['checked_at'] > _CACHE_TTL or _license_cache['valid'] is None:
        try:
            import license_manager
            status = license_manager.check_license_or_trial()
            _license_cache = {
                'valid':      status.get('valid', False),
                'trial':      status.get('trial', False),
                'days_left':  status.get('days_left', 0),
                'checked_at': now,
            }
        except Exception:
            # En cas d'erreur d'import, on laisse passer (failsafe)
            _license_cache = {'valid': True, 'trial': False,
                              'days_left': 999, 'checked_at': now}
    return _license_cache


# ─── Page de blocage HTML intégrée ────────────────────────────────────────────
_BLOCKED_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GestionnaireRH — Licence expirée</title>
<style>
  body {{ font-family: Arial, sans-serif; background: #1a3a5c;
          display: flex; align-items: center; justify-content: center;
          min-height: 100vh; margin: 0; }}
  .card {{ background: white; border-radius: 12px; padding: 48px 40px;
            max-width: 480px; width: 90%; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }}
  h1 {{ color: #c0392b; font-size: 1.6rem; margin-bottom: 8px; }}
  .icon {{ font-size: 4rem; margin-bottom: 16px; }}
  p {{ color: #555; line-height: 1.6; }}
  .reason {{ background: #fdf2f2; border: 1px solid #f5c6cb; border-radius: 6px;
              padding: 12px 16px; color: #c0392b; font-weight: bold; margin: 20px 0; }}
  .contact {{ background: #eaf4fb; border-radius: 6px; padding: 12px 16px;
               color: #1a5276; margin-top: 16px; }}
  .btn {{ display: inline-block; margin-top: 24px; padding: 12px 28px;
           background: #27ae60; color: white; text-decoration: none;
           border-radius: 6px; font-weight: bold; font-size: 1rem; }}
  small {{ color: #aaa; display: block; margin-top: 20px; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">&#x1F512;</div>
  <h1>Accès bloqué</h1>
  <p>Votre accès à <strong>GestionnaireRH</strong> est suspendu.</p>
  <div class="reason">{reason}</div>
  <div class="contact">
    Pour renouveler votre licence, contactez :<br>
    <strong>ICG Guinea</strong>
  </div>
  <small>Redémarrez l'application après activation.</small>
</div>
</body>
</html>"""


class LicenceMiddleware:
    """
    Middleware qui vérifie la validité de la licence à chaque requête.
    Bloque COMPLETEMENT l'accès (retourne 403) si essai/licence expiré.
    """

    EXEMPT_PREFIXES = (
        '/static/', '/media/', '/favicon',
    )
    EXEMPT_EXACT = {'/', '/login/', '/core/login/'}

    def __init__(self, get_response):
        # Désactiver totalement le middleware si l'application de la licence
        # est off (version en ligne). MiddlewareNotUsed le retire de la chaîne
        # au démarrage : aucune vérification ni page de blocage.
        if not getattr(settings, 'LICENCE_ENFORCEMENT', True):
            raise MiddlewareNotUsed()
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Toujours autoriser les ressources statiques
        if path.startswith(('/static/', '/media/', '/favicon')):
            return self.get_response(request)

        # Autoriser la page d'accueil et login
        if path in self.EXEMPT_EXACT:
            return self.get_response(request)

        # Vérifier la licence (avec cache)
        status = _check_license_cached()

        if not status['valid']:
            # Licence/essai expiré → page de blocage HTTP 403
            days = status.get('days_left', 0)
            if status.get('trial'):
                reason = "Votre période d'essai gratuit de 3 mois est expirée."
            else:
                reason = "Votre licence a expiré ou est invalide."
            html = _BLOCKED_HTML.format(reason=reason)
            return HttpResponse(html, status=403, content_type='text/html; charset=utf-8')

        # Avertissement dans les 7 derniers jours
        if status['valid'] and status.get('days_left', 999) <= 7:
            if not request.session.get('_lic_warn_shown'):
                messages.warning(
                    request,
                    f"Votre {'essai' if status.get('trial') else 'licence'} "
                    f"expire dans {status['days_left']} jour(s). "
                    "Contactez ICG Guinea pour renouveler."
                )
                request.session['_lic_warn_shown'] = True

        return self.get_response(request)
