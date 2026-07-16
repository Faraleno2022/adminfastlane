"""
Vues pour les paramètres de calcul de paie personnalisés.
"""
import json
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.decorators import reauth_required, entreprise_active_required
from .models import ParametresCalculPaie, HistoriqueParametresPaie
from .formules import tester_formule, valider_formule, EXEMPLES_FORMULES


def _utilisateur_peut_modifier(user):
    """Retourne True si l'utilisateur peut modifier les paramètres de calcul."""
    if user.is_superuser:
        return True
    if getattr(user, 'est_admin_entreprise', False):
        return True
    # Profil niveau 5 (Administrateur)
    profil = getattr(user, 'profil', None)
    if profil and getattr(profil, 'niveau_acces', 0) >= 5:
        return True
    return False


def _enregistrer_historique(params, user, champ, ancienne, nouvelle, raison=''):
    """Crée une entrée d'historique si la valeur a changé."""
    if str(ancienne) != str(nouvelle):
        HistoriqueParametresPaie.objects.create(
            parametres=params,
            modifie_par=user,
            champ_modifie=champ,
            ancienne_valeur=str(ancienne),
            nouvelle_valeur=str(nouvelle),
            raison=raison,
        )


@login_required
@entreprise_active_required
@reauth_required
def parametres_calcul_paie(request):
    """
    Affiche et enregistre les paramètres du moteur de calcul de paie
    pour l'entreprise de l'utilisateur connecté.
    """
    entreprise = request.user.entreprise
    params, _ = ParametresCalculPaie.objects.get_or_create(entreprise=entreprise)

    peut_modifier = _utilisateur_peut_modifier(request.user)

    if request.method == 'POST':
        if not peut_modifier:
            messages.error(request, "Vous n'avez pas les droits pour modifier ces paramètres.")
            return redirect('paie:parametres_calcul')

        raison = request.POST.get('raison', '').strip()
        action = request.POST.get('action', '')

        if action == 'appliquer_modele_standard':
            valeurs_avant = {
                'mode_exoneration_indemnites': params.mode_exoneration_indemnites,
                'plafond_exoneration_pct': params.plafond_exoneration_pct,
                'formule_exoneration': params.formule_exoneration,
                'mode_base_vf': params.mode_base_vf,
                'formule_base_vf': params.formule_base_vf,
                'mode_base_onfpp': params.mode_base_onfpp,
                'utiliser_formule_base_rts': params.utiliser_formule_base_rts,
                'formule_base_rts': params.formule_base_rts,
            }
            params.appliquer_modele_standard_guineerh()
            raison_standard = raison or "Application du modèle standard GuinéeRH"
            for champ, ancienne in valeurs_avant.items():
                _enregistrer_historique(
                    params, request.user, champ, ancienne,
                    getattr(params, champ), raison_standard,
                )
            params.save()
            messages.success(
                request,
                "Modèle standard GuinéeRH appliqué : indemnités plafonnées à 25 %, "
                "base VF avec déduction CGI, ONFPP sur base VF, base RTS standard."
            )
            return redirect('paie:parametres_calcul')

        # --- Indemnités forfaitaires ---
        nouveau_mode_exo = request.POST.get('mode_exoneration_indemnites', 'plafond_pct')
        # ── Verrouillage CGI : seul le mode plafond_pct est autorisé ──
        if nouveau_mode_exo not in ('plafond_pct',):
            nouveau_mode_exo = 'plafond_pct'
        _enregistrer_historique(
            params, request.user,
            'mode_exoneration_indemnites',
            params.mode_exoneration_indemnites,
            nouveau_mode_exo, raison,
        )
        params.mode_exoneration_indemnites = nouveau_mode_exo

        pct_raw = request.POST.get('plafond_exoneration_pct', '25')
        try:
            from decimal import Decimal
            nouveau_pct = Decimal(pct_raw)
        except Exception:
            nouveau_pct = Decimal('25')
        # ── Verrouillage CGI : plafond max 25% ──
        PLAFOND_MAX_CGI = Decimal('25')
        if nouveau_pct > PLAFOND_MAX_CGI:
            nouveau_pct = PLAFOND_MAX_CGI
        if nouveau_pct < Decimal('0'):
            nouveau_pct = Decimal('0')
        _enregistrer_historique(
            params, request.user,
            'plafond_exoneration_pct',
            params.plafond_exoneration_pct,
            nouveau_pct, raison,
        )
        params.plafond_exoneration_pct = nouveau_pct

        nouvelle_formule_exo = request.POST.get('formule_exoneration', '').strip()
        _enregistrer_historique(
            params, request.user,
            'formule_exoneration',
            params.formule_exoneration,
            nouvelle_formule_exo, raison,
        )
        params.formule_exoneration = nouvelle_formule_exo

        # --- Base VF/TA ---
        nouveau_mode_vf = request.POST.get('mode_base_vf', 'brut')
        _enregistrer_historique(
            params, request.user,
            'mode_base_vf',
            params.mode_base_vf,
            nouveau_mode_vf, raison,
        )
        params.mode_base_vf = nouveau_mode_vf

        nouvelle_formule_vf = request.POST.get('formule_base_vf', '').strip()
        _enregistrer_historique(
            params, request.user,
            'formule_base_vf',
            params.formule_base_vf,
            nouvelle_formule_vf, raison,
        )
        params.formule_base_vf = nouvelle_formule_vf

        nouveau_mode_onfpp = request.POST.get('mode_base_onfpp', 'brut')
        if nouveau_mode_onfpp not in ('base_vf', 'brut'):
            nouveau_mode_onfpp = 'brut'
        _enregistrer_historique(
            params, request.user,
            'mode_base_onfpp',
            params.mode_base_onfpp,
            nouveau_mode_onfpp, raison,
        )
        params.mode_base_onfpp = nouveau_mode_onfpp

        # --- Base RTS ---
        nouveau_utiliser_rts = request.POST.get('utiliser_formule_base_rts') == 'on'
        _enregistrer_historique(
            params, request.user,
            'utiliser_formule_base_rts',
            params.utiliser_formule_base_rts,
            nouveau_utiliser_rts, raison,
        )
        params.utiliser_formule_base_rts = nouveau_utiliser_rts

        nouvelle_formule_rts = request.POST.get('formule_base_rts', '').strip()
        _enregistrer_historique(
            params, request.user,
            'formule_base_rts',
            params.formule_base_rts,
            nouvelle_formule_rts, raison,
        )
        params.formule_base_rts = nouvelle_formule_rts

        params.save()
        messages.success(request, "Paramètres de calcul enregistrés avec succès.")
        return redirect('paie:parametres_calcul')

    contexte = {
        'params': params,
        'peut_modifier': peut_modifier,
        'modes_exoneration': ParametresCalculPaie.MODE_EXONERATION,
        'modes_base_vf': ParametresCalculPaie.MODE_BASE_VF,
        'modes_base_onfpp': ParametresCalculPaie.MODE_BASE_ONFPP,
        'variables_disponibles': [
            ('brut', 'Salaire brut total'),
            ('cnss', 'Cotisation CNSS salarié'),
            ('indemnites', 'Total des indemnités forfaitaires'),
            ('salaire_base', 'Salaire de base'),
            ('primes', 'Total des primes'),
            ('heures_sup', 'Total heures supplémentaires'),
            ('anciennete_mois', 'Ancienneté en mois'),
            ('anciennete_ans', 'Ancienneté en années'),
            ('nb_enfants', 'Nombre d\'enfants'),
            ('nb_conjoints', 'Nombre de conjoints'),
            ('plafond_cnss', 'Plafond CNSS (2 500 000 GNF)'),
        ],
        'exemples_formules': {
            'exoneration': [
                ('Plafond 25% (CGI strict)', 'min(indemnites, brut * 0.25)'),
                ('Plafond 30%', 'min(indemnites, brut * 0.30)'),
                ('Exonération conditionnelle', 'indemnites if indemnites <= brut * 0.25 else brut * 0.25'),
            ],
            'base_vf': [
                ('Brut direct', 'brut'),
                ('Brut moins abattement', 'brut - 150000 if brut >= 2500000 else brut'),
                ('94% du brut', 'brut * 0.94'),
            ],
            'base_rts': [
                ('Formule standard', 'brut - cnss - min(indemnites, brut * 0.25)'),
                ('Avec plafond 30%', 'brut - cnss - min(indemnites, brut * 0.30)'),
            ],
        },
        'nb_historique': HistoriqueParametresPaie.objects.filter(parametres=params).count(),
    }
    return render(request, 'paie/parametres_calcul.html', contexte)


@login_required
@entreprise_active_required
def historique_parametres_paie(request):
    """
    Affiche l'historique des modifications des paramètres de calcul de paie.
    """
    entreprise = request.user.entreprise
    params = get_object_or_404(ParametresCalculPaie, entreprise=entreprise)
    historique = HistoriqueParametresPaie.objects.filter(
        parametres=params
    ).select_related('modifie_par').order_by('-date_modification')

    contexte = {
        'params': params,
        'historique': historique,
        'peut_modifier': _utilisateur_peut_modifier(request.user),
    }
    return render(request, 'paie/historique_parametres.html', contexte)


@login_required
@require_POST
def tester_formule_ajax(request):
    """
    Vue AJAX : teste une formule de paie avec des valeurs d'exemple
    et retourne le résultat en JSON.
    """
    try:
        body = json.loads(request.body)
        formule = body.get('formule', '').strip()
    except (json.JSONDecodeError, AttributeError):
        formule = request.POST.get('formule', '').strip()

    if not formule:
        return JsonResponse({'succes': False, 'erreur': 'Formule vide'})

    resultat = tester_formule(formule)
    if resultat.get('succes'):
        resultat['resultat'] = float(resultat['resultat'])
    return JsonResponse(resultat)


@login_required
@require_POST
def valider_formule_ajax(request):
    """
    Vue AJAX : valide une formule (détection d'erreurs et avertissements).
    Retourne JSON avec valide, erreurs, avertissements et resultat_test.
    """
    try:
        body = json.loads(request.body)
        formule = body.get('formule', '').strip()
    except (json.JSONDecodeError, AttributeError):
        formule = request.POST.get('formule', '').strip()

    if not formule:
        return JsonResponse({'valide': False, 'erreurs': ['Formule vide'], 'avertissements': []})

    resultat = valider_formule(formule)
    if resultat.get('resultat_test') is not None:
        resultat['resultat_test'] = float(resultat['resultat_test'])
    return JsonResponse(resultat)


# ---------------------------------------------------------------------------
# CONSTANTES DE PAIE — liste + modification
# ---------------------------------------------------------------------------

@login_required
@entreprise_active_required
def liste_constantes(request):
    """Liste des constantes de paie avec filtre par catégorie."""
    from .models import Constante

    categorie = request.GET.get('categorie', '')
    qs = Constante.objects.all()
    if categorie:
        qs = qs.filter(categorie=categorie)

    return render(request, 'paie/constantes/liste.html', {
        'constantes': qs,
        'categorie_active': categorie,
        'categories': Constante.CATEGORIES,
        'peut_modifier': _utilisateur_peut_modifier(request.user),
    })


@login_required
@entreprise_active_required
@reauth_required
def modifier_constante(request, pk):
    """Modifier la valeur d'une constante de paie."""
    from decimal import Decimal
    from .models import Constante

    constante = get_object_or_404(Constante, pk=pk)

    if not _utilisateur_peut_modifier(request.user):
        messages.error(request, "Droits insuffisants pour modifier les constantes.")
        return redirect('paie:liste_constantes')

    if request.method == 'POST':
        ancienne_valeur = constante.valeur
        try:
            nouvelle_valeur = Decimal(request.POST.get('valeur', '0'))
        except Exception:
            messages.error(request, "Valeur invalide.")
            return redirect('paie:modifier_constante', pk=pk)

        constante.valeur = nouvelle_valeur
        constante.save()

        messages.success(
            request,
            f"Constante {constante.code} modifiée : {ancienne_valeur} → {nouvelle_valeur}"
        )
        return redirect('paie:liste_constantes')

    return render(request, 'paie/constantes/modifier.html', {
        'constante': constante,
    })


# ---------------------------------------------------------------------------
# BARÈME RTS — liste, ajout, modification, duplication
# ---------------------------------------------------------------------------

@login_required
@entreprise_active_required
def liste_tranches_rts(request):
    """Barème RTS par année, avec simulation inline et filtre type_bareme."""
    from .models import TrancheRTS

    annee = request.GET.get('annee', '')
    if annee:
        try:
            annee = int(annee)
        except ValueError:
            annee = datetime.date.today().year
    else:
        annee = datetime.date.today().year

    type_filtre = request.GET.get('type', '')  # officiel / simulation / test / '' (tous)

    qs = TrancheRTS.objects.filter(annee_validite=annee)
    if type_filtre:
        qs = qs.filter(type_bareme=type_filtre)
    tranches = qs.order_by('numero_tranche')

    annees_dispo = (
        TrancheRTS.objects.values_list('annee_validite', flat=True)
        .distinct().order_by('-annee_validite')
    )

    return render(request, 'paie/tranches_rts/liste.html', {
        'tranches': tranches,
        'annee_active': annee,
        'annees_dispo': annees_dispo,
        'type_filtre': type_filtre,
        'types_bareme': TrancheRTS.TYPES_BAREME,
        'peut_modifier': _utilisateur_peut_modifier(request.user),
    })


@login_required
@entreprise_active_required
@reauth_required
def ajouter_tranche_rts(request):
    """Ajouter une tranche au barème RTS."""
    from decimal import Decimal
    from .models import TrancheRTS

    if not _utilisateur_peut_modifier(request.user):
        messages.error(request, "Droits insuffisants.")
        return redirect('paie:liste_tranches_rts')

    if request.method == 'POST':
        try:
            type_bareme = request.POST.get('type_bareme', 'officiel')
            if type_bareme not in ('officiel', 'simulation', 'test'):
                type_bareme = 'officiel'
            TrancheRTS.objects.create(
                numero_tranche=int(request.POST.get('numero_tranche', 1)),
                borne_inferieure=Decimal(request.POST.get('borne_inferieure', '0')),
                borne_superieure=Decimal(request.POST.get('borne_superieure', '0')) or None,
                taux_irg=Decimal(request.POST.get('taux', '0')),
                annee_validite=int(request.POST.get('annee', datetime.date.today().year)),
                date_debut_validite=datetime.date(
                    int(request.POST.get('annee', datetime.date.today().year)), 1, 1
                ),
                type_bareme=type_bareme,
                actif=True,
            )
            messages.success(request, "Tranche ajoutée avec succès.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
        return redirect('paie:liste_tranches_rts')

    annee = request.GET.get('annee', datetime.date.today().year)
    return render(request, 'paie/tranches_rts/ajouter.html', {
        'annee': annee,
    })


@login_required
@entreprise_active_required
@reauth_required
def modifier_tranche_rts(request, pk):
    """Modifier une tranche du barème RTS."""
    from decimal import Decimal
    from .models import TrancheRTS

    tranche = get_object_or_404(TrancheRTS, pk=pk)

    if not _utilisateur_peut_modifier(request.user):
        messages.error(request, "Droits insuffisants.")
        return redirect('paie:liste_tranches_rts')

    if request.method == 'POST':
        try:
            tranche.numero_tranche = int(request.POST.get('numero_tranche', tranche.numero_tranche))
            tranche.borne_inferieure = Decimal(request.POST.get('borne_inferieure', '0'))
            bs = request.POST.get('borne_superieure', '').strip()
            tranche.borne_superieure = Decimal(bs) if bs else None
            tranche.taux_irg = Decimal(request.POST.get('taux', '0'))
            type_bareme = request.POST.get('type_bareme', tranche.type_bareme)
            if type_bareme in ('officiel', 'simulation', 'test'):
                tranche.type_bareme = type_bareme
            tranche.actif = request.POST.get('actif') == 'on'
            tranche.save()
            messages.success(request, f"Tranche {tranche.numero_tranche} modifiée.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
        return redirect('paie:liste_tranches_rts')

    return render(request, 'paie/tranches_rts/modifier.html', {
        'tranche': tranche,
    })


@login_required
@entreprise_active_required
@reauth_required
def dupliquer_bareme_rts(request):
    """Dupliquer le barème RTS d'une année vers une autre."""
    from .models import TrancheRTS

    if not _utilisateur_peut_modifier(request.user):
        messages.error(request, "Droits insuffisants.")
        return redirect('paie:liste_tranches_rts')

    if request.method == 'POST':
        try:
            annee_source = int(request.POST.get('annee_source', 0))
            annee_cible = int(request.POST.get('annee_cible', 0))

            if annee_source == annee_cible:
                messages.error(request, "L'année source et cible doivent être différentes.")
                return redirect('paie:liste_tranches_rts')

            tranches_source = TrancheRTS.objects.filter(
                annee_validite=annee_source, actif=True, type_bareme='officiel'
            )
            if not tranches_source.exists():
                messages.error(request, f"Aucune tranche officielle trouvée pour {annee_source}.")
                return redirect('paie:liste_tranches_rts')

            # Supprimer les tranches officielles existantes pour l'année cible
            nb_sup = TrancheRTS.objects.filter(
                annee_validite=annee_cible, type_bareme='officiel'
            ).delete()[0]

            nb_crees = 0
            for t in tranches_source:
                TrancheRTS.objects.create(
                    numero_tranche=t.numero_tranche,
                    borne_inferieure=t.borne_inferieure,
                    borne_superieure=t.borne_superieure,
                    taux_irg=t.taux_irg,
                    annee_validite=annee_cible,
                    date_debut_validite=datetime.date(annee_cible, 1, 1),
                    type_bareme='officiel',
                    actif=True,
                )
                nb_crees += 1

            messages.success(
                request,
                f"Barème {annee_source} dupliqué vers {annee_cible} ({nb_crees} tranches créées)."
            )
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

        return redirect('paie:liste_tranches_rts')

    annees_dispo = (
        TrancheRTS.objects.values_list('annee_validite', flat=True)
        .distinct().order_by('-annee_validite')
    )
    annee_courante = datetime.date.today().year
    return render(request, 'paie/tranches_rts/dupliquer.html', {
        'annees_dispo': annees_dispo,
        'annee_suivante': annee_courante + 1,
    })
