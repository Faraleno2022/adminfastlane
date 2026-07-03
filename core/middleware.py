"""
Middleware de sécurité personnalisé pour l'application
"""
import logging
import json
from django.http import HttpResponseForbidden
from django.core.cache import cache
from django.conf import settings
import re

logger = logging.getLogger(__name__)


def _is_json_request(request):
    content_type = request.META.get('CONTENT_TYPE', '').lower()
    return 'application/json' in content_type


def _iter_request_strings(request):
    if _is_json_request(request):
        try:
            payload = json.loads(request.body or b'{}')
        except (TypeError, ValueError):
            return []
        return list(_walk_json_strings(payload))

    return list(request.POST.items())


def _walk_json_strings(value, prefix='json'):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_json_strings(item, f'{prefix}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_json_strings(item, f'{prefix}[{index}]')
    elif isinstance(value, str):
        yield prefix, value


class SecurityHeadersMiddleware:
    """
    Ajoute des en-têtes de sécurité supplémentaires
    non couverts nativement par Django ou django-csp.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Protection contre le clickjacking
        response['X-Frame-Options'] = 'DENY'
        
        # Protection XSS
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '1; mode=block'
        
        # Référer Policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Cross-Origin policies
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        response['Cross-Origin-Resource-Policy'] = 'same-origin'

        # Masquer la version du serveur
        response['Server'] = 'GuinéeRH'

        # Empêcher la mise en cache de pages sensibles
        if request.path.startswith(('/paie/', '/employes/', '/comptabilite/', '/portail/')):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

        return response


class SQLInjectionProtectionMiddleware:
    """
    Protection contre les injections SQL
    """
    # Patterns suspects d'injection SQL
    SQL_PATTERNS = [
        r"(\bunion\b.*\bselect\b)",
        r"(\bselect\b.*\bfrom\b)",
        r"(\binsert\b.*\binto\b)",
        r"(\bdelete\b.*\bfrom\b)",
        r"(\bdrop\b.*\btable\b)",
        r"(\bupdate\b.*\bset\b)",
        r"(--)",
        r"(;.*--)",
        r"(\bor\b.*=.*)",
        r"(\band\b.*=.*)",
        r"('.*or.*'.*=.*')",
        r"(exec\s*\()",
        r"(execute\s*\()",
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.SQL_PATTERNS]

    def __call__(self, request):
        # Fichiers statiques/media → pas de paramètres utilisateur, skip
        if request.path.startswith(('/static/', '/media/', '/favicon')):
            return self.get_response(request)
        # Vérifier les paramètres GET
        for key, value in request.GET.items():
            if self._contains_sql_injection(value):
                logger.warning(f"Tentative d'injection SQL détectée dans GET: {key}={value} depuis {request.META.get('REMOTE_ADDR')}")
                return HttpResponseForbidden("Requête invalide détectée")
        
        # Vérifier les paramètres POST
        if request.method == 'POST':
            for key, value in _iter_request_strings(request):
                if isinstance(value, str) and self._contains_sql_injection(value):
                    logger.warning(f"Tentative d'injection SQL détectée dans POST: {key} depuis {request.META.get('REMOTE_ADDR')}")
                    return HttpResponseForbidden("Requête invalide détectée")
        
        return self.get_response(request)

    def _contains_sql_injection(self, value):
        """Vérifie si la valeur contient des patterns d'injection SQL"""
        if not isinstance(value, str):
            return False
        
        for pattern in self.patterns:
            if pattern.search(value):
                return True
        return False


class XSSProtectionMiddleware:
    """
    Protection contre les attaques XSS
    """
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
        r"onclick\s*=",
        r"<iframe",
        r"<embed",
        r"<object",
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.XSS_PATTERNS]

    def __call__(self, request):
        # Fichiers statiques/media → pas de paramètres utilisateur, skip
        if request.path.startswith(('/static/', '/media/', '/favicon')):
            return self.get_response(request)
        # Vérifier les paramètres GET
        for key, value in request.GET.items():
            if self._contains_xss(value):
                logger.warning(f"Tentative XSS détectée dans GET: {key}={value} depuis {request.META.get('REMOTE_ADDR')}")
                return HttpResponseForbidden("Requête invalide détectée")
        
        # Vérifier les paramètres POST
        if request.method == 'POST':
            for key, value in _iter_request_strings(request):
                if isinstance(value, str) and self._contains_xss(value):
                    logger.warning(f"Tentative XSS détectée dans POST: {key} depuis {request.META.get('REMOTE_ADDR')}")
                    return HttpResponseForbidden("Requête invalide détectée")
        
        return self.get_response(request)

    def _contains_xss(self, value):
        """Vérifie si la valeur contient des patterns XSS"""
        if not isinstance(value, str):
            return False
        
        for pattern in self.patterns:
            if pattern.search(value):
                return True
        return False


class IPWhitelistMiddleware:
    """
    Middleware pour restreindre l'accès à certaines IPs (optionnel)
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.whitelist = getattr(settings, 'IP_WHITELIST', [])
        self.enabled = getattr(settings, 'IP_WHITELIST_ENABLED', False)

    def __call__(self, request):
        if self.enabled and self.whitelist:
            client_ip = self._get_client_ip(request)
            if client_ip not in self.whitelist:
                logger.warning(f"Accès refusé pour IP non autorisée: {client_ip}")
                return HttpResponseForbidden("Accès non autorisé")
        
        return self.get_response(request)
    
    def _get_client_ip(self, request):
        """Récupère l'IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class RequestLoggingMiddleware:
    """
    Log toutes les requêtes pour audit de sécurité
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Ne pas logger les requêtes statiques/media
        if request.path.startswith(('/static/', '/media/', '/favicon')):
            return self.get_response(request)

        # Log avant traitement
        if getattr(settings, 'SECURITY_LOGGING_ENABLED', True):
            logger.info(
                f"Request: {request.method} {request.path} "
                f"from {request.META.get('REMOTE_ADDR')} "
                f"User: {request.user if request.user.is_authenticated else 'Anonymous'}"
            )
        
        response = self.get_response(request)
        
        # Log après traitement si erreur
        if response.status_code >= 400:
            logger.warning(
                f"Response {response.status_code}: {request.method} {request.path} "
                f"from {request.META.get('REMOTE_ADDR')}"
            )
        
        return response


class EntrepriseQuotaMiddleware:
    """
    Middleware pour vérifier les quotas d'abonnement et l'accès aux modules
    selon le plan souscrit (Starter / Pro / Premium).

    Contrôle :
    - Entreprise active
    - Date d'expiration de l'abonnement
    - Quota d'utilisateurs
    - Quota d'employés
    - Accès aux modules selon le plan
    """

    # Mapping URL prefix → module requis
    MODULE_URL_MAP = {
        '/paie/': 'paie',
        '/conges/': 'conges',
        '/recrutement/': 'recrutement',
        '/formation/': 'formation',
        '/comptabilite/': 'comptabilite',
        '/portail/': 'portail',
    }

    # Chemins exemptés (toujours accessibles)
    EXEMPT_PATHS = (
        '/payments/',
        '/renouvellement/',
        '/dashboard/',
        '/core/',
        '/admin/',
        '/static/',
        '/media/',
        '/employes/',
        '/contrats/',
        '/temps/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated or not hasattr(request.user, 'entreprise'):
            return self.get_response(request)

        entreprise = request.user.entreprise
        if not entreprise:
            return self.get_response(request)

        from django.shortcuts import redirect
        from django.contrib import messages

        # ── 1. Entreprise désactivée ──
        if not entreprise.actif:
            messages.error(request, "Votre entreprise est désactivée. Contactez le support.")
            return redirect('core:login')

        # ── Licence offline valide → accès complet, aucune restriction de plan ──
        from core.licence_utils import licence_offline_valide
        if licence_offline_valide():
            return self.get_response(request)

        # ── 2. Abonnement expiré ──
        if entreprise.date_expiration:
            from django.utils import timezone
            if timezone.now().date() > entreprise.date_expiration:
                # Permettre l'accès aux pages de paiement uniquement
                if not any(request.path.startswith(p) for p in ('/payments/', '/renouvellement/', '/static/', '/media/', '/core/login/')):
                    messages.warning(
                        request,
                        "Votre abonnement a expiré. Veuillez le renouveler pour continuer."
                    )
                    return redirect('payments:plans')

        # ── 3. Contrôle d'accès aux modules selon le plan ──
        path = request.path
        for url_prefix, module_name in self.MODULE_URL_MAP.items():
            if path.startswith(url_prefix):
                if not entreprise.has_module(module_name):
                    plan = entreprise.plan_abonnement or 'gratuit'
                    messages.warning(
                        request,
                        f"Le module « {module_name.title()} » n'est pas inclus dans votre "
                        f"plan {plan.title()}. Passez au plan supérieur pour y accéder."
                    )
                    return redirect('payments:plans')
                break

        # ── 4. Quota d'utilisateurs (lors de la création) ──
        if request.path == '/manage-users/' and request.method == 'POST':
            current_users = entreprise.utilisateurs.filter(actif=True).count()
            if current_users >= entreprise.max_utilisateurs:
                messages.error(
                    request,
                    f"Quota d'utilisateurs atteint ({current_users}/{entreprise.max_utilisateurs}). "
                    f"Veuillez upgrader votre plan."
                )
                return redirect('core:manage_users')

        # ── 5. Quota d'employés (lors de l'ajout) ──
        if path.startswith('/employes/') and request.method == 'POST':
            # Ne bloquer que sur les vues de création (pas modification)
            if '/ajouter' in path or '/create' in path or '/import' in path:
                from employes.models import Employe
                current_count = Employe.objects.filter(entreprise=entreprise).count()
                max_emp = getattr(entreprise, 'max_employes', 9999)
                if current_count >= max_emp:
                    messages.error(
                        request,
                        f"Quota d'employés atteint ({current_count}/{max_emp}). "
                        f"Veuillez upgrader votre plan pour ajouter plus d'employés."
                    )
                    return redirect('employes:list')

        response = self.get_response(request)
        return response
