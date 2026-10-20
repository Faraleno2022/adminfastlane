from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.db import models, IntegrityError
import hmac
import logging
from .models import LogActivite, Utilisateur, TentativeCodeAcces
from .decorators import rate_limit

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Récupère l'adresse IP du client"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_activity(request, action, module=None, table=None, id_enreg=None, details=None):
    """Enregistre une activité dans les logs"""
    if request.user.is_authenticated:
        LogActivite.objects.create(
            utilisateur=request.user,
            action=action,
            module=module,
            table_concernee=table,
            id_enregistrement=id_enreg,
            details=details,
            adresse_ip=get_client_ip(request)
        )


def documentation_legale(request):
    """Page publique de documentation légale sur la paie en Guinée"""
    return render(request, 'core/documentation_legale.html')


def documentation_legale_print(request):
    """Version imprimable de la documentation légale"""
    return render(request, 'core/documentation_legale_print.html')


@login_required
def guide_utilisateur(request):
    """Guide utilisateur complet de GuinéeRH"""
    return render(request, 'documentation/guide_utilisateur.html')


def login_view(request):
    """Vue de connexion"""
    if request.user.is_authenticated:
        # Rediriger selon le type de module
        return redirect('core:home_menu')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.actif:
                login(request, user)
                user.enregistrer_connexion()
                log_activity(request, 'Connexion', 'core')
                messages.success(request, f'Bienvenue {user.get_full_name()}!')
                # Rediriger selon le type de module
                return redirect('core:home_menu')
            else:
                messages.error(request, 'Votre compte est désactivé.')
        else:
            messages.error(request, 'Identifiants incorrects.')
    
    return render(request, 'core/login.html')


@login_required
def logout_view(request):
    """Vue de déconnexion"""
    log_activity(request, 'Déconnexion', 'core')
    logout(request)
    messages.info(request, 'Vous avez été déconnecté.')
    return redirect('core:login')


@login_required
def profile_view(request):
    """Vue du profil utilisateur"""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_profile':
            # Mise à jour du profil
            user = request.user
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = request.POST.get('email', user.email)
            user.telephone = request.POST.get('telephone', '')
            
            # Gestion de la photo
            if 'photo' in request.FILES:
                user.photo = request.FILES['photo']
            
            user.save()
            
            log_activity(request, 'Modification profil', 'core')
            messages.success(request, 'Profil mis à jour avec succès')
            
        elif action == 'change_password':
            # Changement de mot de passe
            from django.contrib.auth import update_session_auth_hash
            
            old_password = request.POST.get('old_password')
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            
            if not request.user.check_password(old_password):
                messages.error(request, 'Mot de passe actuel incorrect')
            elif new_password1 != new_password2:
                messages.error(request, 'Les nouveaux mots de passe ne correspondent pas')
            elif len(new_password1) < 8:
                messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères')
            else:
                request.user.set_password(new_password1)
                request.user.save()
                update_session_auth_hash(request, request.user)
                
                log_activity(request, 'Changement mot de passe', 'core')
                messages.success(request, 'Mot de passe changé avec succès')
        
        return redirect('core:profile')
    
    return render(request, 'core/profile.html')


@login_required
def home_menu(request):
    """Lanceur d'applications façon Odoo (écran d'accueil après connexion)."""
    return render(request, 'core/home_menu.html', {'odoo_home': True})


def index_view(request):
    """Page d'accueil - redirige vers le lanceur d'applications si connecté, sinon affiche landing page"""
    if request.user.is_authenticated:
        return redirect('core:home_menu')
    
    # Récupérer les offres d'emploi ouvertes et non expirées pour affichage public
    from recrutement.models import OffreEmploi
    from formation.models import CatalogueFormation
    from datetime import date
    from django.db.models import Q
    
    # Toutes les offres ouvertes (aucune limite) pour affichage public
    offres_emploi = OffreEmploi.objects.filter(
        statut_offre='ouverte'
    ).select_related('entreprise', 'service').order_by('-date_publication')

    # Toutes les formations publiées (aucune limite) pour affichage public
    formations = CatalogueFormation.objects.filter(
        publiee=True,
        actif=True
    ).select_related('entreprise').order_by('-date_publication')
    
    return render(request, 'landing.html', {
        'offres_emploi': offres_emploi,
        'formations': formations,
        'today': date.today(),
    })


def landing_page(request):
    """Landing page publique pour le schéma public (multi-tenant)"""
    return render(request, 'landing.html')


def csrf_failure(request, reason=""):
    """Vue personnalisée pour les erreurs CSRF — JSON pour AJAX, HTML sinon"""
    from django.http import JsonResponse
    # Requête AJAX / API → renvoyer JSON
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('Content-Type', '').startswith('application/json')
        or request.headers.get('Accept', '').startswith('application/json')
    )
    if is_ajax:
        return JsonResponse(
            {'error': 'Session expirée ou token CSRF invalide. Rechargez la page (F5).'},
            status=403
        )
    return render(request, 'core/csrf_failure.html', {
        'reason': reason
    }, status=403)


@rate_limit(max_requests=10, time_window=300)
def register_entreprise(request):
    """Vue d'inscription d'une nouvelle entreprise"""
    from django.conf import settings
    from .forms import EntrepriseRegistrationForm
    
    # Vérifier si les inscriptions sont désactivées
    if getattr(settings, 'REGISTRATION_DISABLED', False):
        admin_code = getattr(settings, 'ADMIN_REGISTRATION_CODE', '')
        ip = get_client_ip(request)
        
        # Vérifier si l'IP est bloquée (trop de tentatives échouées)
        max_tentatives = getattr(settings, 'CODE_ACCES_MAX_TENTATIVES', 5)
        duree_blocage = getattr(settings, 'CODE_ACCES_DUREE_BLOCAGE', 30)  # minutes
        
        if TentativeCodeAcces.ip_bloquee(ip, max_tentatives, duree_blocage):
            logger.warning(f"IP bloquée pour tentatives excessives: {ip}")
            messages.error(
                request,
                f"Trop de tentatives échouées. Réessayez dans {duree_blocage} minutes."
            )
            return render(request, 'core/registration_disabled.html', {'bloquee': True})
        
        code_saisi = request.GET.get('code', '') or request.session.get('admin_registration_code', '')
        
        # Si code fourni en GET, valider avec comparaison à temps constant
        if request.GET.get('code'):
            code_soumis = request.GET.get('code')
            code_valide = hmac.compare_digest(code_soumis, admin_code)
            
            # Enregistrer la tentative
            TentativeCodeAcces.enregistrer(request, code_soumis, code_valide)
            
            if code_valide:
                request.session['admin_registration_code'] = 'validated'
                code_saisi = admin_code  # Pour passer le check suivant
            else:
                nb_restantes = max_tentatives - TentativeCodeAcces.tentatives_recentes(ip, duree_blocage)
                if nb_restantes > 0:
                    messages.error(
                        request,
                        f"Code de vérification incorrect. {nb_restantes} tentative(s) restante(s)."
                    )
                else:
                    messages.error(
                        request,
                        f"Code incorrect. IP bloquée pour {duree_blocage} minutes."
                    )
                return render(request, 'core/registration_disabled.html')
        
        # Si pas de code valide, afficher la page de blocage
        # Vérifier soit le code direct, soit le marqueur de session
        session_code = request.session.get('admin_registration_code', '')
        if session_code != 'validated' and not hmac.compare_digest(code_saisi, admin_code):
            return render(request, 'core/registration_disabled.html')
    
    if request.method == 'POST':
        form = EntrepriseRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                entreprise = form.save()
            except IntegrityError as e:
                if 'utilisateurs.email' in str(e):
                    form.add_error('admin_email', 'Cet email est déjà utilisé par un autre compte.')
                    return render(request, 'core/register_entreprise.html', {'form': form})
                else:
                    raise e
            
            # Connecter automatiquement l'administrateur
            admin_user = entreprise.utilisateurs.filter(est_admin_entreprise=True).first()
            if admin_user:
                login(request, admin_user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(
                    request,
                    f'Entreprise {entreprise.nom_entreprise} créée avec succès! Bienvenue {admin_user.get_full_name()}!'
                )
                # Rediriger selon le type de module choisi
                if entreprise.type_module == 'secretariat':
                    return redirect('secretariat:dashboard')
                elif entreprise.type_module == 'stock':
                    return redirect('stock:dashboard')
                else:
                    return redirect('dashboard:index')
        else:
            messages.error(request, 'Veuillez corriger les erreurs ci-dessous.')
    else:
        form = EntrepriseRegistrationForm()
    
    return render(request, 'core/register_entreprise.html', {'form': form})


@login_required
def reauth_view(request):
    """Vue de réauthentification"""
    from .forms import ReauthForm
    
    if request.method == 'POST':
        form = ReauthForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['password']
            
            # Vérifier le mot de passe
            if request.user.check_password(password):
                # Mettre à jour la dernière réauthentification
                request.user.last_reauth = timezone.now()
                request.user.save(update_fields=['last_reauth'])
                
                log_activity(request, 'Réauthentification réussie', 'core')
                messages.success(request, 'Réauthentification réussie!')
                
                # Rediriger vers la page demandée
                next_url = request.session.get('reauth_next', 'dashboard:index')
                if 'reauth_next' in request.session:
                    del request.session['reauth_next']
                return redirect(next_url)
            else:
                messages.error(request, 'Mot de passe incorrect.')
    else:
        form = ReauthForm()
    
    return render(request, 'core/reauth.html', {'form': form})


@login_required
def manage_users(request):
    """Vue de gestion des utilisateurs de l'entreprise"""
    from .forms import UserInvitationForm
    from .decorators import entreprise_active_required
    
    # Vérifier que l'utilisateur est admin de son entreprise
    if not request.user.est_admin_entreprise:
        messages.error(request, "Vous n'avez pas les permissions pour gérer les utilisateurs.")
        return redirect('dashboard:index')
    
    # Vérifier le quota d'utilisateurs (aucun quota avec une licence offline valide)
    from .licence_utils import licence_offline_valide
    entreprise = request.user.entreprise
    current_users = entreprise.utilisateurs.filter(actif=True).count()
    quota_reached = current_users >= entreprise.max_utilisateurs and not licence_offline_valide()
    quota_percentage = int((current_users / entreprise.max_utilisateurs) * 100) if entreprise.max_utilisateurs > 0 else 0
    
    if request.method == 'POST':
        if quota_reached:
            messages.error(
                request,
                f"Quota d'utilisateurs atteint ({entreprise.max_utilisateurs}). "
                f"Veuillez upgrader votre plan."
            )
            return redirect('core:manage_users')
        
        form = UserInvitationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.entreprise = request.user.entreprise
            user.set_password(form.cleaned_data['password'])
            # Sécurité : forcer les valeurs par défaut pour les nouveaux utilisateurs
            user.est_admin_entreprise = False
            user.is_superuser = False
            user.is_staff = False
            user.actif = True  # Compte actif par défaut
            user.save()
            
            log_activity(request, f'Création utilisateur {user.username}', 'core')
            messages.success(request, f'Utilisateur {user.username} créé avec succès!')
            return redirect('core:manage_users')
    else:
        form = UserInvitationForm()
    
    # Liste des utilisateurs de l'entreprise
    users = request.user.entreprise.utilisateurs.all().order_by('-date_joined')
    
    return render(request, 'core/manage_users.html', {
        'form': form,
        'users': users,
        'quota_reached': quota_reached,
        'current_users': current_users,
        'max_users': entreprise.max_utilisateurs,
        'quota_percentage': quota_percentage,
    })


@login_required
def send_invitation(request):
    """Envoyer une invitation par email à un nouvel utilisateur"""
    from django.core.mail import send_mail
    from django.contrib.sites.shortcuts import get_current_site
    from django.utils.crypto import get_random_string
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Vous n'avez pas les permissions pour inviter des utilisateurs.")
        return redirect('dashboard:index')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        profil_id = request.POST.get('profil')
        
        # Vérifier le quota (aucun quota avec une licence offline valide)
        from .licence_utils import licence_offline_valide
        entreprise = request.user.entreprise
        current_users = entreprise.utilisateurs.filter(actif=True).count()
        if current_users >= entreprise.max_utilisateurs and not licence_offline_valide():
            messages.error(request, "Quota d'utilisateurs atteint.")
            return redirect('core:manage_users')
        
        # Générer un token d'invitation
        token = get_random_string(32)
        
        # Créer l'utilisateur inactif
        from .models import ProfilUtilisateur
        profil = get_object_or_404(ProfilUtilisateur, pk=profil_id)
        
        username = email.split('@')[0]
        # S'assurer que le username est unique
        base_username = username
        counter = 1
        while Utilisateur.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        user = Utilisateur.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            entreprise=entreprise,
            profil=profil,
            actif=False,  # Inactif jusqu'à activation par email
            is_active=False,
            # Sécurité : empêcher l'accès admin
            est_admin_entreprise=False,
            is_superuser=False,
            is_staff=False
        )
        user.set_password(token)  # Mot de passe temporaire
        user.save()
        
        # Envoyer l'email d'invitation
        current_site = get_current_site(request)
        activation_link = f"http://{current_site.domain}/activate/{token}/"
        
        subject = f"Invitation à rejoindre {entreprise.nom_entreprise}"
        message = f"""
Bonjour {first_name} {last_name},

Vous avez été invité(e) à rejoindre {entreprise.nom_entreprise} sur Gestionnaire RH Guinée.

Pour activer votre compte, cliquez sur le lien ci-dessous:
{activation_link}

Votre nom d'utilisateur: {username}

Cordialement,
L'équipe {entreprise.nom_entreprise}
        """
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@gestionrh.gn',
                [email],
                fail_silently=False,
            )
            
            log_activity(request, f'Invitation envoyée à {email}', 'core')
            messages.success(request, f'Invitation envoyée à {email}!')
        except Exception as e:
            messages.error(request, f'Erreur lors de l\'envoi de l\'email: {str(e)}')
            user.delete()  # Supprimer l'utilisateur si l'email échoue
        
        return redirect('core:manage_users')
    
    # GET: Afficher le formulaire
    from .models import ProfilUtilisateur
    profils = ProfilUtilisateur.objects.filter(actif=True)
    
    return render(request, 'core/send_invitation.html', {
        'profils': profils
    })


@login_required
def admin_dashboard(request):
    """Tableau de bord pour les administrateurs d'entreprise"""
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    entreprise = request.user.entreprise
    
    # Statistiques de l'entreprise
    from employes.models import Employe
    from paie.models import BulletinPaie, PeriodePaie
    from temps_travail.models import Conge
    
    stats = {
        'entreprise': entreprise,
        'total_users': entreprise.utilisateurs.count(),
        'active_users': entreprise.utilisateurs.filter(actif=True).count(),
        'quota_users': entreprise.max_utilisateurs,
        'total_employes': Employe.objects.filter(entreprise=entreprise).count(),
        'employes_actifs': Employe.objects.filter(entreprise=entreprise, statut_employe='actif').count(),
        'bulletins_mois': 0,
        'conges_en_attente': Conge.objects.filter(
            employe__entreprise=entreprise,
            statut_demande='en_attente'
        ).count(),
    }
    
    # Bulletins du mois en cours - inclure toutes les périodes actives
    periode_actuelle = PeriodePaie.objects.filter(
        entreprise=entreprise,
        statut_periode__in=['ouverte', 'calculee', 'validee', 'payee']
    ).order_by('-annee', '-mois').first()
    if periode_actuelle:
        stats['bulletins_mois'] = BulletinPaie.objects.filter(
            periode=periode_actuelle,
            employe__entreprise=entreprise,
        ).count()
    
    # Activités récentes
    recent_logs = LogActivite.objects.filter(
        utilisateur__entreprise=entreprise
    ).select_related('utilisateur').order_by('-date_action')[:20]
    
    # Utilisateurs récents
    recent_users = entreprise.utilisateurs.all().order_by('-date_joined')[:5]
    
    return render(request, 'core/admin_dashboard.html', {
        'stats': stats,
        'recent_logs': recent_logs,
        'recent_users': recent_users,
    })


@login_required
def entreprise_settings(request):
    """Paramètres de l'entreprise (logo, informations, etc.)"""
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    entreprise = request.user.entreprise
    from .forms import EntrepriseSettingsForm
    
    if request.method == 'POST':
        form = EntrepriseSettingsForm(request.POST, request.FILES, instance=entreprise)
        if form.is_valid():
            form.save()
            log_activity(request, 'Modification paramètres entreprise', 'core')
            messages.success(request, 'Paramètres de l\'entreprise mis à jour avec succès!')
            return redirect('core:entreprise_settings')
    else:
        form = EntrepriseSettingsForm(instance=entreprise)
    
    return render(request, 'core/entreprise_settings.html', {
        'form': form,
        'entreprise': entreprise,
    })


@login_required
def toggle_user_status(request, user_id):
    """Bloquer ou débloquer un utilisateur"""
    if not request.user.est_admin_entreprise:
        messages.error(request, "Vous n'avez pas les permissions pour cette action.")
        return redirect('dashboard:index')
    
    # Récupérer l'utilisateur à modifier (doit appartenir à la même entreprise)
    user_to_toggle = get_object_or_404(
        Utilisateur,
        pk=user_id,
        entreprise=request.user.entreprise
    )
    
    # Empêcher l'admin de se bloquer lui-même
    if user_to_toggle == request.user:
        messages.error(request, "Vous ne pouvez pas vous bloquer vous-même.")
        return redirect('core:manage_users')
    
    # Inverser le statut actif
    user_to_toggle.actif = not user_to_toggle.actif
    user_to_toggle.save(update_fields=['actif'])
    
    # Log et message
    action = 'Déblocage' if user_to_toggle.actif else 'Blocage'
    log_activity(request, f'{action} utilisateur {user_to_toggle.username}', 'core')
    
    if user_to_toggle.actif:
        messages.success(request, f"L'utilisateur {user_to_toggle.get_full_name()} a été débloqué.")
    else:
        messages.warning(request, f"L'utilisateur {user_to_toggle.get_full_name()} a été bloqué.")
    
    return redirect('core:manage_users')


@login_required
def superuser_manage_users(request):
    """Vue de gestion de TOUS les utilisateurs - réservée aux superusers"""
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    # Filtres
    entreprise_filter = request.GET.get('entreprise', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    
    # Récupérer tous les utilisateurs
    users = Utilisateur.objects.all().select_related('entreprise', 'profil').order_by('-date_joined')
    
    # Appliquer les filtres
    if entreprise_filter:
        users = users.filter(entreprise_id=entreprise_filter)
    if status_filter == 'actif':
        users = users.filter(actif=True)
    elif status_filter == 'inactif':
        users = users.filter(actif=False)
    if search:
        users = users.filter(
            models.Q(username__icontains=search) |
            models.Q(email__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search)
        )
    
    # Liste des entreprises pour le filtre avec effectif
    from .models import Entreprise
    from employes.models import Employe
    from django.db.models import Count
    
    entreprises = Entreprise.objects.annotate(
        effectif=Count('employes_entreprise')
    ).order_by('nom_entreprise')
    
    # Statistiques
    stats = {
        'total': Utilisateur.objects.count(),
        'actifs': Utilisateur.objects.filter(actif=True).count(),
        'inactifs': Utilisateur.objects.filter(actif=False).count(),
        'total_entreprises': Entreprise.objects.count(),
    }
    
    return render(request, 'core/superuser_manage_users.html', {
        'users': users,
        'entreprises': entreprises,
        'stats': stats,
        'entreprise_filter': entreprise_filter,
        'status_filter': status_filter,
        'search': search,
    })


@login_required
def superuser_toggle_user(request, user_id):
    """Bloquer/débloquer un utilisateur - réservé aux superusers"""
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    user_to_toggle = get_object_or_404(Utilisateur, pk=user_id)
    
    # Empêcher le superuser de se bloquer lui-même
    if user_to_toggle == request.user:
        messages.error(request, "Vous ne pouvez pas vous bloquer vous-même.")
        return redirect('core:superuser_manage_users')
    
    # Inverser le statut actif
    user_to_toggle.actif = not user_to_toggle.actif
    user_to_toggle.save(update_fields=['actif'])
    
    # Log et message
    action = 'Déblocage' if user_to_toggle.actif else 'Blocage'
    log_activity(request, f'{action} utilisateur {user_to_toggle.username} (superuser)', 'core')
    
    if user_to_toggle.actif:
        messages.success(request, f"L'utilisateur {user_to_toggle.get_full_name()} a été débloqué.")
    else:
        messages.warning(request, f"L'utilisateur {user_to_toggle.get_full_name()} a été bloqué.")
    
    return redirect('core:superuser_manage_users')


@login_required
def superuser_delete_user(request, user_id):
    """Supprimer un utilisateur - réservé aux superusers"""
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    user_to_delete = get_object_or_404(Utilisateur, pk=user_id)
    
    # Empêcher le superuser de se supprimer lui-même
    if user_to_delete == request.user:
        messages.error(request, "Vous ne pouvez pas vous supprimer vous-même.")
        return redirect('core:superuser_manage_users')
    
    username = user_to_delete.username
    full_name = user_to_delete.get_full_name()
    
    # Supprimer l'utilisateur
    user_to_delete.delete()
    
    log_activity(request, f'Suppression utilisateur {username} (superuser)', 'core')
    messages.success(request, f"L'utilisateur {full_name} ({username}) a été supprimé définitivement.")
    
    return redirect('core:superuser_manage_users')


@login_required
def superuser_delete_entreprise(request, entreprise_id):
    """Supprimer une entreprise et tous ses utilisateurs - réservé aux superusers"""
    from .models import Entreprise
    
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    entreprise = get_object_or_404(Entreprise, pk=entreprise_id)
    
    # Vérifier que le superuser ne supprime pas sa propre entreprise
    if request.user.entreprise == entreprise:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre entreprise.")
        return redirect('core:superuser_manage_users')
    
    nom_entreprise = entreprise.nom_entreprise
    nb_users = entreprise.utilisateurs.count()
    
    # Supprimer l'entreprise (cascade supprimera les utilisateurs)
    entreprise.delete()
    
    log_activity(request, f'Suppression entreprise {nom_entreprise} et {nb_users} utilisateurs (superuser)', 'core')
    messages.success(request, f"L'entreprise {nom_entreprise} et ses {nb_users} utilisateur(s) ont été supprimés définitivement.")
    
    return redirect('core:superuser_manage_users')


# ============= GESTION STRUCTURE ENTREPRISE =============

@login_required
def gestion_structure(request):
    """Vue principale pour gérer la structure de l'entreprise (Etablissements, Services, Postes)"""
    from .models import Societe, Etablissement, Service, Poste
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    entreprise = request.user.entreprise
    
    # Récupérer ou créer la société liée à l'entreprise
    societe = Societe.objects.filter(entreprise=entreprise).first()
    if not societe:
        societe = Societe.objects.create(
            entreprise=entreprise,
            raison_sociale=entreprise.nom_entreprise,
            forme_juridique='SARL'
        )
    
    etablissements = Etablissement.objects.filter(societe=societe)
    services = Service.objects.filter(entreprise=entreprise)
    postes = Poste.objects.filter(entreprise=entreprise)
    
    return render(request, 'core/gestion_structure.html', {
        'societe': societe,
        'etablissements': etablissements,
        'services': services,
        'postes': postes
    })


@login_required
def creer_etablissement(request):
    """Créer un établissement"""
    from .models import Societe, Etablissement
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    entreprise = request.user.entreprise
    societe = Societe.objects.filter(entreprise=entreprise).first()
    
    if not societe:
        societe = Societe.objects.create(
            entreprise=entreprise,
            raison_sociale=entreprise.nom_entreprise,
            forme_juridique='SARL'
        )
    
    if request.method == 'POST':
        code = request.POST.get('code_etablissement')
        nom = request.POST.get('nom_etablissement')
        type_etab = request.POST.get('type_etablissement')
        ville = request.POST.get('ville')
        adresse = request.POST.get('adresse')
        telephone = request.POST.get('telephone')
        
        if Etablissement.objects.filter(code_etablissement=code).exists():
            messages.error(request, f"Le code '{code}' existe déjà.")
            return redirect('core:creer_etablissement')
        
        Etablissement.objects.create(
            societe=societe,
            code_etablissement=code,
            nom_etablissement=nom,
            type_etablissement=type_etab,
            ville=ville,
            adresse=adresse,
            telephone=telephone,
            actif=True
        )
        
        log_activity(request, f'Création établissement {code}', 'core')
        messages.success(request, f"Établissement '{nom}' créé avec succès.")
        return redirect('core:gestion_structure')
    
    return render(request, 'core/creer_etablissement.html', {
        'types': Etablissement.TYPES
    })


@login_required
def supprimer_etablissement(request, pk):
    """Supprimer un établissement"""
    from .models import Etablissement
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    etablissement = get_object_or_404(Etablissement, pk=pk, societe__entreprise=request.user.entreprise)
    nom = etablissement.nom_etablissement
    etablissement.delete()
    
    log_activity(request, f'Suppression établissement {nom}', 'core')
    messages.success(request, f"Établissement '{nom}' supprimé.")
    return redirect('core:gestion_structure')


@login_required
def creer_service(request):
    """Créer un service"""
    from .models import Etablissement, Service
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    etablissements = Etablissement.objects.filter(societe__entreprise=request.user.entreprise, actif=True)
    
    if not etablissements.exists():
        messages.error(request, "Vous devez d'abord créer un établissement avant de pouvoir créer un service.")
        return redirect('core:gestion_structure')
    
    entreprise = request.user.entreprise

    if request.method == 'POST':
        code = request.POST.get('code_service')
        nom = request.POST.get('nom_service')
        etablissement_id = request.POST.get('etablissement')
        description = request.POST.get('description')

        if Service.objects.filter(entreprise=entreprise, code_service=code).exists():
            messages.error(request, f"Le code '{code}' existe déjà dans votre entreprise.")
            return redirect('core:creer_service')

        etablissement = get_object_or_404(Etablissement, pk=etablissement_id) if etablissement_id else None

        Service.objects.create(
            entreprise=entreprise,
            etablissement=etablissement,
            code_service=code,
            nom_service=nom,
            description=description,
            actif=True
        )
        
        log_activity(request, f'Création service {code}', 'core')
        messages.success(request, f"Service '{nom}' créé avec succès.")
        return redirect('core:gestion_structure')
    
    return render(request, 'core/creer_service.html', {
        'etablissements': etablissements
    })


@login_required
def supprimer_service(request, pk):
    """Supprimer un service"""
    from .models import Service
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    service = get_object_or_404(Service, pk=pk, entreprise=request.user.entreprise)
    nom = service.nom_service
    service.delete()
    
    log_activity(request, f'Suppression service {nom}', 'core')
    messages.success(request, f"Service '{nom}' supprimé.")
    return redirect('core:gestion_structure')


@login_required
def creer_poste(request):
    """Créer un poste"""
    from .models import Etablissement, Service, Poste
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    if not Etablissement.objects.filter(societe__entreprise=request.user.entreprise, actif=True).exists():
        messages.error(request, "Vous devez d'abord créer un établissement avant de pouvoir créer un poste.")
        return redirect('core:gestion_structure')
    
    services = Service.objects.filter(entreprise=request.user.entreprise, actif=True)
    
    entreprise = request.user.entreprise

    if request.method == 'POST':
        code = request.POST.get('code_poste')
        intitule = request.POST.get('intitule_poste')
        service_id = request.POST.get('service')
        categorie = request.POST.get('categorie_professionnelle')
        classification = request.POST.get('classification')
        description = request.POST.get('description_poste')

        if Poste.objects.filter(entreprise=entreprise, code_poste=code).exists():
            messages.error(request, f"Le code '{code}' existe déjà dans votre entreprise.")
            return redirect('core:creer_poste')

        service = get_object_or_404(Service, pk=service_id) if service_id else None

        Poste.objects.create(
            entreprise=entreprise,
            code_poste=code,
            intitule_poste=intitule,
            service=service,
            categorie_professionnelle=categorie,
            classification=classification,
            description_poste=description,
            actif=True
        )
        
        log_activity(request, f'Création poste {code}', 'core')
        messages.success(request, f"Poste '{intitule}' créé avec succès.")
        return redirect('core:gestion_structure')
    
    return render(request, 'core/creer_poste.html', {
        'services': services,
        'categories': Poste.CATEGORIES
    })


@login_required
def supprimer_poste(request, pk):
    """Supprimer un poste"""
    from .models import Poste
    
    if not request.user.est_admin_entreprise:
        messages.error(request, "Accès réservé aux administrateurs d'entreprise.")
        return redirect('dashboard:index')
    
    poste = get_object_or_404(Poste, pk=pk, entreprise=request.user.entreprise)
    nom = poste.intitule_poste
    poste.delete()
    
    log_activity(request, f'Suppression poste {nom}', 'core')
    messages.success(request, f"Poste '{nom}' supprimé.")
    return redirect('core:gestion_structure')


@login_required
def telecharger_documentation(request):
    """Télécharger tous les documents de conformité en ZIP (PDF)"""
    import zipfile
    import io
    import os
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    
    def markdown_to_pdf(md_path, title):
        """Convertir un fichier Markdown en PDF"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []
        
        # Lire le contenu Markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Titre principal
        story.append(Paragraph(f"<b>{title}</b>", styles['Title']))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("GuineeRH.space - Conforme CGI 2022", styles['Heading2']))
        story.append(Spacer(1, 1*cm))
        
        # Traiter le contenu ligne par ligne
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.3*cm))
            elif line.startswith('# '):
                story.append(Paragraph(f"<b>{line[2:]}</b>", styles['Heading1']))
            elif line.startswith('## '):
                story.append(Paragraph(f"<b>{line[3:]}</b>", styles['Heading2']))
            elif line.startswith('### '):
                story.append(Paragraph(f"<b>{line[4:]}</b>", styles['Heading3']))
            elif line.startswith('- ') or line.startswith('* '):
                story.append(Paragraph(f"• {line[2:]}", styles['Normal']))
            elif line.startswith('|'):
                continue  # Skip table lines for now
            elif line.startswith('```'):
                continue  # Skip code blocks markers
            elif line.startswith('---'):
                story.append(Spacer(1, 0.5*cm))
            else:
                # Nettoyer le markdown basique
                line = line.replace('**', '').replace('`', '').replace('✅', '[OK]').replace('📚', '')
                if line:
                    story.append(Paragraph(line, styles['Normal']))
        
        # Footer
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph("Document généré par GuineeRH.space - Janvier 2026", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.read()
    
    # Liste des documents à convertir
    docs_dir = os.path.join(settings.BASE_DIR, 'docs')
    documents = [
        ('EXERCICE_CALCUL_PAIE_CGI2022.md', 'Exercice Calcul Paie CGI 2022'),
        ('MANUEL_UTILISATION_PAIE_GUINEE_v2.md', 'Manuel Utilisation Paie Guinée'),
        ('RAPPORT_AUDIT_CONFORMITE_CGI2022.md', 'Rapport Audit Conformité CGI 2022'),
        ('PRESENTATION_GUINEEHR_INSTITUTIONNELLE.md', 'Présentation Institutionnelle'),
        ('DOSSIER_SOUMISSION_OFFICIELLE.md', 'Dossier Soumission Officielle'),
    ]
    
    # Créer le ZIP avec les PDF
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, title in documents:
            md_path = os.path.join(docs_dir, filename)
            if os.path.exists(md_path):
                pdf_content = markdown_to_pdf(md_path, title)
                pdf_filename = filename.replace('.md', '.pdf')
                zip_file.writestr(pdf_filename, pdf_content)
    
    zip_buffer.seek(0)
    
    # Retourner le ZIP
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="GuineeRH_Documentation_CGI2022.zip"'
    
    log_activity(request, 'Téléchargement documentation CGI 2022 (PDF)', 'core')
    
    return response


def demande_partenariat(request):
    """Vue publique pour soumettre une demande de partenariat"""
    from .models import DemandePartenariat

    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 Mo

    def _valider_fichier(f):
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f'Type de fichier non autorisé : .{ext}')
        if f.size > MAX_FILE_SIZE:
            raise ValueError(f'Fichier trop volumineux ({f.size // 1024 // 1024} Mo max 5 Mo)')
    
    if request.method == 'POST':
        try:
            # Valider les fichiers AVANT création
            for field in ('document_cgi', 'autre_document'):
                if request.FILES.get(field):
                    _valider_fichier(request.FILES[field])

            demande = DemandePartenariat.objects.create(
                nom_entreprise=request.POST.get('nom_entreprise'),
                secteur_activite=request.POST.get('secteur_activite'),
                nif=request.POST.get('nif') or None,
                adresse=request.POST.get('adresse'),
                ville=request.POST.get('ville'),
                pays=request.POST.get('pays', 'Guinée'),
                nom_contact=request.POST.get('nom_contact'),
                fonction_contact=request.POST.get('fonction_contact'),
                email=request.POST.get('email'),
                telephone=request.POST.get('telephone'),
                type_partenariat=request.POST.get('type_partenariat'),
                description_activite=request.POST.get('description_activite'),
                motivation=request.POST.get('motivation'),
            )
            
            # Gérer les fichiers uploadés (déjà validés)
            if request.FILES.get('document_cgi'):
                demande.document_cgi = request.FILES['document_cgi']
            if request.FILES.get('autre_document'):
                demande.autre_document = request.FILES['autre_document']
            demande.save()
            
            messages.success(request, 'Votre demande de partenariat a été soumise avec succès. Nous vous contacterons prochainement.')
            return redirect('core:index')
        except Exception as e:
            messages.error(request, f'Erreur lors de la soumission : {str(e)}')
    
    return render(request, 'core/demande_partenariat.html', {
        'types_partenariat': DemandePartenariat.TYPES_PARTENARIAT,
    })


@login_required
def superuser_demandes_partenariat(request):
    """Vue superuser pour gérer les demandes de partenariat"""
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    from .models import DemandePartenariat
    
    statut_filter = request.GET.get('statut', '')
    search = request.GET.get('search', '')
    
    demandes = DemandePartenariat.objects.all()
    
    if statut_filter:
        demandes = demandes.filter(statut=statut_filter)
    if search:
        demandes = demandes.filter(
            models.Q(nom_entreprise__icontains=search) |
            models.Q(email__icontains=search) |
            models.Q(nom_contact__icontains=search)
        )
    
    stats = {
        'total': DemandePartenariat.objects.count(),
        'nouveau': DemandePartenariat.objects.filter(statut='nouveau').count(),
        'en_cours': DemandePartenariat.objects.filter(statut='en_cours').count(),
        'accepte': DemandePartenariat.objects.filter(statut='accepte').count(),
        'refuse': DemandePartenariat.objects.filter(statut='refuse').count(),
    }
    
    return render(request, 'core/superuser_demandes_partenariat.html', {
        'demandes': demandes,
        'stats': stats,
        'statut_filter': statut_filter,
        'search': search,
    })


@login_required
def superuser_demande_detail(request, pk):
    """Détail et traitement d'une demande de partenariat"""
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    from .models import DemandePartenariat
    
    demande = get_object_or_404(DemandePartenariat, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accepter':
            demande.statut = 'accepte'
            demande.date_traitement = timezone.now()
            demande.traite_par = request.user
            demande.notes_admin = request.POST.get('notes_admin', '')
            demande.save()
            messages.success(request, 'Demande acceptée.')
        elif action == 'refuser':
            demande.statut = 'refuse'
            demande.date_traitement = timezone.now()
            demande.traite_par = request.user
            demande.notes_admin = request.POST.get('notes_admin', '')
            demande.save()
            messages.success(request, 'Demande refusée.')
        elif action == 'en_cours':
            demande.statut = 'en_cours'
            demande.notes_admin = request.POST.get('notes_admin', '')
            demande.save()
            messages.success(request, 'Demande mise en cours de traitement.')
        
        return redirect('core:superuser_demandes_partenariat')
    
    return render(request, 'core/superuser_demande_detail.html', {
        'demande': demande,
    })


@login_required
def telecharger_document_partenariat(request, pk, type_doc):
    """Télécharger un document de demande de partenariat (superuser only)"""
    if not request.user.is_superuser:
        messages.error(request, "Accès réservé aux super administrateurs.")
        return redirect('dashboard:index')
    
    from .models import DemandePartenariat
    import mimetypes
    
    demande = get_object_or_404(DemandePartenariat, pk=pk)
    
    if type_doc == 'cgi' and demande.document_cgi:
        file_field = demande.document_cgi
    elif type_doc == 'autre' and demande.autre_document:
        file_field = demande.autre_document
    else:
        messages.error(request, "Document non trouvé.")
        return redirect('core:superuser_demande_detail', pk=pk)
    
    file_path = file_field.path
    content_type, _ = mimetypes.guess_type(file_path)
    
    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type=content_type or 'application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{file_field.name.split("/")[-1]}"'
        return response


@login_required
def changer_societe(request):
    """Multi-sociétés : basculer vers une autre entreprise autorisée.
    Superuser : toutes les entreprises actives ; sinon celles accordées
    via AccesEntreprise (+ l'entreprise d'origine)."""
    from .models import Entreprise, AccesEntreprise

    if request.user.is_superuser:
        entreprises = Entreprise.objects.filter(actif=True).order_by('nom_entreprise')
    else:
        ids = set(AccesEntreprise.objects.filter(
            utilisateur=request.user).values_list('entreprise_id', flat=True))
        if request.user.entreprise_id:
            ids.add(request.user.entreprise_id)
        entreprises = Entreprise.objects.filter(pk__in=ids, actif=True).order_by('nom_entreprise')

    if request.method == 'POST':
        cible = entreprises.filter(pk=request.POST.get('entreprise')).first()
        if cible is None:
            messages.error(request, "Vous n'avez pas accès à cette société.")
            return redirect('core:changer_societe')
        if cible.pk == request.user.entreprise_id:
            messages.info(request, f"Vous êtes déjà sur {cible.nom_entreprise}.")
            return redirect('dashboard:index')
        # Mémoriser la société quittée pour pouvoir y revenir
        if request.user.entreprise_id and not request.user.is_superuser:
            AccesEntreprise.objects.get_or_create(
                utilisateur=request.user, entreprise_id=request.user.entreprise_id,
                defaults={'accorde_par': request.user})
        request.user.entreprise = cible
        request.user.save(update_fields=['entreprise'])
        log_activity(request, f'Bascule vers la société {cible.nom_entreprise}', 'core')
        messages.success(request, f"Vous travaillez maintenant sur : {cible.nom_entreprise}.")
        return redirect('dashboard:index')

    return render(request, 'core/changer_societe.html', {
        'entreprises': entreprises,
        'entreprise_courante': request.user.entreprise,
    })
