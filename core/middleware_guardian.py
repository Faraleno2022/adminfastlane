"""
Middleware de Protection Anti-Falsification — GestionnaireRH Guinée
====================================================================
Auteur  : International Consulting Guinea
Version : 2.0.0

Ce middleware vérifie l'intégrité du projet à chaque requête (avec cache)
et bloque l'application si une modification non autorisée est détectée.

AVERTISSEMENT LÉGAL :
  Ce logiciel est la propriété exclusive de International Consulting Guinea.
  Toute modification, redistribution ou ingénierie inverse est interdite.
"""

import time
import logging
from django.http import HttpResponse

logger = logging.getLogger('project_guardian')

# ─── Cache du résultat de vérification ─────────────────────────────────────────
_guardian_cache = {
    'blocked': None,
    'reason': '',
    'checked_at': 0,
}
_CACHE_TTL = 3600  # 1 heure (vérifié au démarrage, inutile de re-scanner souvent)


# ─── Page HTML de blocage sécurité ─────────────────────────────────────────────
_SECURITY_BLOCK_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GestionnaireRH — Alerte Sécurité</title>
<style>
  body {{ font-family: Arial, sans-serif; background: #2c0b0e;
          display: flex; align-items: center; justify-content: center;
          min-height: 100vh; margin: 0; color: #fff; }}
  .card {{ background: #1a1a2e; border: 2px solid #e74c3c; border-radius: 16px;
            padding: 48px 40px; max-width: 560px; width: 90%; text-align: center;
            box-shadow: 0 0 60px rgba(231, 76, 60, 0.3); }}
  .icon {{ font-size: 72px; margin-bottom: 16px; }}
  h1 {{ color: #e74c3c; font-size: 24px; margin: 0 0 16px; }}
  .msg {{ color: #bdc3c7; font-size: 14px; line-height: 1.6; margin: 16px 0; }}
  .reason {{ background: #2d1f1f; border-left: 4px solid #e74c3c;
              padding: 14px 16px; margin: 20px 0; text-align: left;
              font-family: monospace; font-size: 12px; color: #e74c3c;
              border-radius: 4px; word-break: break-word; }}
  .contact {{ color: #3498db; font-weight: bold; }}
  .footer {{ margin-top: 28px; font-size: 11px; color: #7f8c8d;
              border-top: 1px solid #333; padding-top: 16px; }}
  .warn {{ color: #e74c3c; font-weight: bold; font-size: 13px; }}
</style>
</head>
<body>
<div class="card">
    <div class="icon">🛡️</div>
    <h1>ALERTE SÉCURITÉ — APPLICATION BLOQUÉE</h1>
    <p class="msg">
        Une modification non autorisée du code source a été détectée.<br>
        L'application est <strong>bloquée</strong> pour protéger vos données.
    </p>
    <div class="reason">{reason}</div>
    <p class="msg">
        Contactez <span class="contact">International Consulting Guinea</span> pour obtenir
        une copie authentique et non altérée de GestionnaireRH.
    </p>
    <p class="warn">
        ⚠️ Toute tentative de modification, redistribution ou falsification
        de ce logiciel est une violation du droit d'auteur et sera poursuivie.
    </p>
    <div class="footer">
        © 2025 International Consulting Guinea — GestionnaireRH — Tous droits réservés<br>
        Licence propriétaire — Usage non autorisé interdit
    </div>
</div>
</body>
</html>"""


class ProjectIntegrityMiddleware:
    """
    Middleware Django qui vérifie l'intégrité des fichiers critiques du projet.
    Bloque TOUTES les requêtes si une falsification est détectée.
    Intègre les vérifications du guardian ET du runtime_shield.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Fichiers statiques/media → toujours servir immédiatement
        if request.path.startswith(('/static/', '/media/', '/favicon')):
            return self.get_response(request)

        global _guardian_cache
        now = time.time()

        # Vérification avec cache
        if (now - _guardian_cache['checked_at'] > _CACHE_TTL
                or _guardian_cache['blocked'] is None):
            try:
                from project_guardian import full_security_check
                report = full_security_check()
                blocked = report['blocked']
                reason = report.get('reason', '')

                # ── Vérification runtime_shield en complément ──
                if not blocked:
                    try:
                        from runtime_shield import periodic_shield_check
                        shield_report = periodic_shield_check()
                        if shield_report.get('blocked'):
                            blocked = True
                            reason = shield_report.get('reason', 'Falsification détectée par le bouclier.')
                    except ImportError:
                        import sys as _sys
                        if getattr(_sys, 'frozen', False):
                            blocked = True
                            reason = (
                                "Module runtime_shield introuvable. "
                                "Le système de protection a été altéré."
                            )
                    except Exception:
                        pass

                _guardian_cache = {
                    'blocked': blocked,
                    'reason': reason,
                    'checked_at': now,
                }
            except ImportError:
                # Si le guardian est absent, c'est un signe de falsification
                _guardian_cache = {
                    'blocked': True,
                    'reason': (
                        "Module de protection introuvable (project_guardian.py). "
                        "Le projet a été altéré."
                    ),
                    'checked_at': now,
                }
            except Exception as e:
                logger.error("Erreur vérification intégrité : %s", e)
                _guardian_cache = {
                    'blocked': False,
                    'reason': '',
                    'checked_at': now,
                }

        if _guardian_cache['blocked']:
            reason = _guardian_cache['reason'] or "Intégrité du projet compromise."
            logger.critical(
                "GUARDIAN BLOCK REQUEST | path=%s | ip=%s | reason=%s",
                request.path, request.META.get('REMOTE_ADDR', '?'), reason
            )
            html = _SECURITY_BLOCK_HTML.format(reason=reason)
            return HttpResponse(html, status=403, content_type='text/html; charset=utf-8')

        return self.get_response(request)
