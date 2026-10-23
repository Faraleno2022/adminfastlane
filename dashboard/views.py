from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from employes.models import Employe
from paie.models import BulletinPaie, PeriodePaie
from temps_travail.models import Conge, Pointage


def _arrondir_gnf(montant):
    return Decimal(str(montant or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _base_cnss_attendue(brut):
    brut = Decimal(str(brut or 0))
    plancher = Decimal('550000')
    plafond = Decimal('2500000')
    if brut < plancher * Decimal('0.10'):
        return Decimal('0')
    return _arrondir_gnf(max(min(brut, plafond), plancher))


def _charges_attendues_bulletin(bulletin, effectif):
    brut = Decimal(str(bulletin.salaire_brut or 0))
    base_cnss = _base_cnss_attendue(brut)
    cnss_5 = _arrondir_gnf(base_cnss * Decimal('0.05'))
    cnss_18 = _arrondir_gnf(base_cnss * Decimal('0.18'))
    base_vf = _arrondir_gnf(max(Decimal('0'), brut))
    vf = _arrondir_gnf(base_vf * Decimal('0.06'))
    if effectif >= 30:
        ta = Decimal('0')
        onfpp = _arrondir_gnf(base_vf * Decimal('0.015'))
    else:
        ta = _arrondir_gnf(base_vf * Decimal('0.02'))
        onfpp = Decimal('0')
    return {
        'base_cnss': base_cnss,
        'cnss_5': cnss_5,
        'cnss_18': cnss_18,
        'base_vf': base_vf,
        'vf': vf,
        'ta': ta,
        'onfpp': onfpp,
    }


def _ecart_significatif(valeur, attendu, tolerance=Decimal('2')):
    return abs(Decimal(str(valeur or 0)) - Decimal(str(attendu or 0))) > tolerance


def _build_paie_totaux_context(totaux):
    """Construit les totaux paie affichés sur le tableau de bord."""
    salaire_brut = totaux.get('brut') or 0
    total_cnss_5 = totaux.get('cnss_5') or 0
    total_cnss_18 = totaux.get('cnss_18') or 0
    total_cnss_23 = total_cnss_5 + total_cnss_18
    total_trs = totaux.get('trs') or 0
    total_vf = totaux.get('vf') or 0
    total_ta = totaux.get('ta') or 0
    total_onfpp = totaux.get('onfpp') or 0

    return {
        'salaire_brut': salaire_brut,
        'masse_salariale': salaire_brut + total_cnss_18 + total_onfpp + total_vf,
        'total_net_a_payer': totaux.get('net') or 0,
        'total_base_vf': totaux.get('base_vf') or 0,
        'total_trs': total_trs,
        'total_vf': total_vf,
        'total_ta': total_ta,
        'total_onfpp': total_onfpp,
        'total_cnss_5': total_cnss_5,
        'total_cnss_18': total_cnss_18,
        'total_cnss_23': total_cnss_23,
        'total_declaration_sociale': total_cnss_23,
        'total_dmu': total_trs + total_vf,
        'total_etax': total_trs + total_vf,
    }


def _build_repartition_service_paie(bulletins, effectif_total):
    """Répartition mensuelle réelle des coûts paie par service."""
    services = {}
    iterable = bulletins.select_related('employe__service', 'employe') if hasattr(bulletins, 'select_related') else bulletins
    for bulletin in iterable:
        service = bulletin.employe.service
        key = service.pk if service else 0
        nom = service.nom_service if service else 'Sans service'
        if key not in services:
            services[key] = {
                'nom': nom,
                'effectif': 0,
                'hommes': 0,
                'femmes': 0,
                'brut': Decimal('0'),
                'net': Decimal('0'),
                'cnss_23': Decimal('0'),
                'rts': Decimal('0'),
                'vf': Decimal('0'),
                'ta': Decimal('0'),
                'onfpp': Decimal('0'),
                'masse_salariale': Decimal('0'),
            }
        row = services[key]
        attendu = _charges_attendues_bulletin(bulletin, effectif_total)
        brut = Decimal(str(bulletin.salaire_brut or 0))
        cnss_18 = Decimal(str(bulletin.cnss_employeur or attendu['cnss_18']))
        vf = Decimal(str(bulletin.versement_forfaitaire or attendu['vf']))
        # Les montants des bulletins sont deja arrondis individuellement.
        # Les additionner evite les ecarts entre le total affiche et les
        # declarations, qui reposent elles aussi sur les bulletins figes.
        ta = Decimal(str(bulletin.taxe_apprentissage or 0))
        onfpp = Decimal(str(bulletin.contribution_onfpp or 0))

        row['effectif'] += 1
        if bulletin.employe.sexe == 'M':
            row['hommes'] += 1
        elif bulletin.employe.sexe == 'F':
            row['femmes'] += 1
        row['brut'] += brut
        row['net'] += Decimal(str(bulletin.net_a_payer or 0))
        row['cnss_23'] += Decimal(str(bulletin.cnss_employe or attendu['cnss_5'])) + cnss_18
        row['rts'] += Decimal(str(bulletin.irg or 0))
        row['vf'] += vf
        row['ta'] += ta
        row['onfpp'] += onfpp
        row['masse_salariale'] += brut + cnss_18 + vf + onfpp + ta

    return sorted(services.values(), key=lambda item: item['brut'], reverse=True)


def _build_risque_fiscal_paie(bulletins, effectif_total):
    """Score synthétique de risque fiscal pour la période paie affichée."""
    compteurs = {
        'bulletins': 0,
        'bases_manquantes': 0,
        'indemnites_surveillees': 0,
        'indemnites_plafond': 0,
        'ecarts_cnss': 0,
        'ecarts_vf': 0,
        'ecarts_ta_onfpp': 0,
        'mode_ta_onfpp': 0,
    }

    for bulletin in bulletins:
        compteurs['bulletins'] += 1
        brut = Decimal(str(bulletin.salaire_brut or 0))
        if brut <= 0:
            compteurs['bases_manquantes'] += 1
            continue

        base_rts = Decimal(str(getattr(bulletin, 'base_rts', 0) or 0))
        base_vf = Decimal(str(getattr(bulletin, 'base_vf', 0) or 0))
        if base_rts <= 0 or base_vf <= 0:
            compteurs['bases_manquantes'] += 1

        abattement = Decimal(str(getattr(bulletin, 'abattement_forfaitaire', 0) or 0))
        ratio_indemnites = (abattement / brut * Decimal('100')) if brut else Decimal('0')
        if ratio_indemnites >= Decimal('25'):
            compteurs['indemnites_plafond'] += 1
        elif ratio_indemnites >= Decimal('23'):
            compteurs['indemnites_surveillees'] += 1

        attendu = _charges_attendues_bulletin(bulletin, effectif_total)
        if (
            _ecart_significatif(getattr(bulletin, 'cnss_employe', 0), attendu['cnss_5'])
            or _ecart_significatif(getattr(bulletin, 'cnss_employeur', 0), attendu['cnss_18'])
        ):
            compteurs['ecarts_cnss'] += 1
        if (
            _ecart_significatif(getattr(bulletin, 'base_vf', 0), attendu['base_vf'])
            or _ecart_significatif(getattr(bulletin, 'versement_forfaitaire', 0), attendu['vf'])
        ):
            compteurs['ecarts_vf'] += 1
        if (
            _ecart_significatif(getattr(bulletin, 'taxe_apprentissage', 0), attendu['ta'])
            or _ecart_significatif(getattr(bulletin, 'contribution_onfpp', 0), attendu['onfpp'])
        ):
            compteurs['ecarts_ta_onfpp'] += 1

        if effectif_total >= 30 and Decimal(str(getattr(bulletin, 'taxe_apprentissage', 0) or 0)) > 0:
            compteurs['mode_ta_onfpp'] += 1
        if effectif_total < 30 and Decimal(str(getattr(bulletin, 'contribution_onfpp', 0) or 0)) > 0:
            compteurs['mode_ta_onfpp'] += 1

    nb_bulletins = max(compteurs['bulletins'], 1)
    anomalies_critiques = (
        compteurs['bases_manquantes'] +
        compteurs['ecarts_cnss'] +
        compteurs['ecarts_vf'] +
        compteurs['ecarts_ta_onfpp'] +
        compteurs['mode_ta_onfpp']
    )
    profil_surveille = compteurs['indemnites_surveillees'] + compteurs['indemnites_plafond']
    score = 0
    score += min(85, int((anomalies_critiques / nb_bulletins) * 85))
    score += min(30, int((profil_surveille / nb_bulletins) * 30))
    score += min(10, int((compteurs['indemnites_plafond'] / nb_bulletins) * 10))
    score = min(score, 100)

    if compteurs['bulletins'] == 0:
        niveau = 'Aucun bulletin'
        badge = 'secondary'
        icon = 'bi-info-circle'
        statut = 'Aucune période calculée'
    elif score >= 70:
        niveau = 'Rouge'
        badge = 'danger'
        icon = 'bi-shield-exclamation'
        statut = 'Risque fiscal élevé'
    elif score >= 35:
        niveau = 'Orange'
        badge = 'warning'
        icon = 'bi-exclamation-triangle'
        statut = 'Points à surveiller'
    else:
        niveau = 'Vert'
        badge = 'success'
        icon = 'bi-shield-check'
        statut = 'Contrôles cohérents'

    controles = [
        ('Bases taxables manquantes', compteurs['bases_manquantes'], 'Base RTS/VF absente ou nulle'),
        ('Indemnités ≥ 23%', compteurs['indemnites_surveillees'], 'Profil proche du plafond'),
        ('Indemnités ≥ 25%', compteurs['indemnites_plafond'], 'Plafond fiscal atteint'),
        ('Écarts CNSS', compteurs['ecarts_cnss'], 'Plancher/plafond/taux à vérifier'),
        ('Écarts VF', compteurs['ecarts_vf'], 'Base VF ou montant VF incohérent'),
        ('Écarts TA/ONFPP', compteurs['ecarts_ta_onfpp'], 'Seuil 30 ou base ONFPP à vérifier'),
        ('Mode TA/ONFPP', compteurs['mode_ta_onfpp'], 'TA/ONFPP incompatible avec l’effectif'),
    ]

    return {
        'score': score,
        'niveau': niveau,
        'badge': badge,
        'icon': icon,
        'statut': statut,
        'bulletins': compteurs['bulletins'],
        'controles': [
            {'nom': nom, 'valeur': valeur, 'detail': detail, 'ok': valeur == 0}
            for nom, valeur, detail in controles
        ],
    }


@login_required
def index(request):
    """Tableau de bord principal - Optimisé pour rapidité"""
    entreprise = request.user.entreprise

    # Entreprise qui n'a pas choisi l'application Employés : retour au lanceur
    if entreprise and entreprise.applications and 'rh' not in entreprise.applications:
        return redirect('core:home_menu')

    # Rediriger les utilisateurs comptabilité vers le module comptabilité
    if entreprise and entreprise.type_module == 'compta':
        return redirect('comptabilite:compte-bancaire-list')

    # Rediriger les comptes Secrétariat seul vers le module secrétariat
    if entreprise and entreprise.type_module == 'secretariat':
        return redirect('secretariat:dashboard')

    # Rediriger les comptes Gestion de Stock seul vers le module stock
    if entreprise and entreprise.type_module == 'stock':
        return redirect('stock:dashboard')

    entreprise_id = request.user.entreprise_id

    # Filtre periode (mois/annee). Par defaut, aucun filtre: toutes les periodes.
    now = timezone.now()
    mois_filtre = None
    annee_filtre = None
    mois_param = request.GET.get('mois')
    annee_param = request.GET.get('annee')
    try:
        if mois_param:
            mois_filtre = int(mois_param)
    except (TypeError, ValueError):
        mois_filtre = None
    try:
        if annee_param:
            annee_filtre = int(annee_param)
    except (TypeError, ValueError):
        annee_filtre = None
    if mois_filtre is not None and not (1 <= mois_filtre <= 12):
        mois_filtre = None
    if annee_filtre is not None and not (2000 <= annee_filtre <= 2100):
        annee_filtre = None

    mois_labels = [
        (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
        (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'), (8, 'Août'),
        (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre'),
    ]
    if entreprise_id:
        annees_disponibles = list(
            PeriodePaie.objects.filter(entreprise_id=entreprise_id)
            .values_list('annee', flat=True)
            .distinct()
            .order_by('-annee')
        )
    else:
        annees_disponibles = []
    if now.year not in annees_disponibles:
        annees_disponibles = [now.year, *annees_disponibles]
    mois_nom = dict(mois_labels).get(mois_filtre)
    if mois_filtre and annee_filtre:
        periode_label = f"{mois_nom} {annee_filtre}"
    elif annee_filtre:
        periode_label = f"Année {annee_filtre}"
    elif mois_filtre:
        periode_label = f"{mois_nom} - toutes années"
    else:
        periode_label = "Toutes les périodes"

    filtre_context = {
        'mois_filtre': mois_filtre,
        'annee_filtre': annee_filtre,
        'periode_label': periode_label,
        'mois_labels': mois_labels,
        'annees_disponibles': annees_disponibles,
        'filtre_periode_actif': mois_filtre is not None or annee_filtre is not None,
    }

    # Si l'utilisateur n'a pas d'entreprise, afficher un dashboard vide avec alerte
    if not entreprise_id:
        context = {
            'total_employes': 0, 'employes_hommes': 0, 'employes_femmes': 0,
            'employes_cdi': 0, 'employes_cdd': 0, 'employes_cdimp': 0,
            'employes_cti': 0, 'employes_stage': 0, 'employes_apprentissage': 0,
            'employes_temporaire': 0, 'employes_sans_contrat': 0,
            'contrats_detail': [], 'contrats_actifs': [], 'contrats_sans': 0,
            'conges_en_cours': 0, 'employes_en_conge': [],
            'conges_en_attente': 0, 'bulletins_calcules': 0,
            'bulletins_valides': 0, 'bulletins_en_attente': 0,
            'salaire_brut': 0, 'masse_salariale': 0, 'pointages_jour': 0,
            'total_net_a_payer': 0, 'total_base_vf': 0,
            'total_trs': 0, 'total_vf': 0, 'total_ta': 0, 'total_onfpp': 0,
            'total_cnss_5': 0, 'total_cnss_18': 0, 'total_cnss_23': 0,
            'total_declaration_sociale': 0, 'total_dmu': 0, 'total_etax': 0,
            'risque_fiscal': _build_risque_fiscal_paie([], 0),
            'repartition_service_paie': [],
            'alertes': [{
                'type': 'warning',
                'icon': 'bi-exclamation-triangle',
                'message': 'Aucune entreprise associée à votre compte. Veuillez contacter l\'administrateur.'
            }],
            **filtre_context,
        }
        return render(request, 'dashboard/index.html', context)

    cache_key = f'dashboard_stats_v8_{entreprise_id}_{annee_filtre or "all"}_{mois_filtre or "all"}'

    # Essayer de récupérer du cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return render(request, 'dashboard/index.html', cached_data)
    
    context = {}
    aujourd_hui = timezone.now().date()
    
    # Statistiques employés - Une seule requête avec agrégation complète
    employes_stats = Employe.objects.filter(
        entreprise_id=entreprise_id,
        statut_employe='actif'
    ).aggregate(
        total=Count('id'),
        hommes=Count('id', filter=Q(sexe='M')),
        femmes=Count('id', filter=Q(sexe='F')),
        cdi=Count('id', filter=Q(type_contrat='CDI')),
        cdd=Count('id', filter=Q(type_contrat='CDD')),
        cdimp=Count('id', filter=Q(type_contrat='CDImp')),
        cti=Count('id', filter=Q(type_contrat='CTI')),
        stage=Count('id', filter=Q(type_contrat='stage')),
        apprentissage=Count('id', filter=Q(type_contrat='apprentissage')),
        temporaire=Count('id', filter=Q(type_contrat='temporaire')),
        sans_contrat=Count('id', filter=Q(type_contrat__isnull=True) | Q(type_contrat='')),
        sans_service=Count('id', filter=Q(service__isnull=True)),
    )

    context['total_employes'] = employes_stats['total']
    context['employes_hommes'] = employes_stats['hommes']
    context['employes_femmes'] = employes_stats['femmes']

    # Contrats — tous les types
    context['employes_cdi'] = employes_stats['cdi']
    context['employes_cdd'] = employes_stats['cdd']
    context['employes_cdimp'] = employes_stats['cdimp']
    context['employes_cti'] = employes_stats['cti']
    context['employes_stage'] = employes_stats['stage']
    context['employes_apprentissage'] = employes_stats['apprentissage']
    context['employes_temporaire'] = employes_stats['temporaire']
    context['employes_sans_contrat'] = employes_stats['sans_contrat']

    # Détail structuré pour le tableau et les graphiques
    total = employes_stats['total'] or 1  # éviter division par zéro
    contrats_detail = [
        {'code': 'CDI',   'label': 'CDI — Durée Indéterminée',    'count': employes_stats['cdi'],           'color': '#2563eb', 'icon': 'bi-shield-check'},
        {'code': 'CDD',   'label': 'CDD — Durée Déterminée',      'count': employes_stats['cdd'],           'color': '#f59e0b', 'icon': 'bi-clock-history'},
        {'code': 'CDImp', 'label': 'CDImp — Durée Imprécise',     'count': employes_stats['cdimp'],         'color': '#8b5cf6', 'icon': 'bi-question-circle'},
        {'code': 'CTI',   'label': 'CTI — Travail Intermittent',   'count': employes_stats['cti'],           'color': '#06b6d4', 'icon': 'bi-arrow-repeat'},
        {'code': 'Stage', 'label': 'Stage',                        'count': employes_stats['stage'],         'color': '#10b981', 'icon': 'bi-mortarboard'},
        {'code': 'Apprentissage', 'label': 'Apprentissage',        'count': employes_stats['apprentissage'], 'color': '#ec4899', 'icon': 'bi-tools'},
        {'code': 'Temporaire',    'label': 'Temporaire',           'count': employes_stats['temporaire'],    'color': '#ef4444', 'icon': 'bi-hourglass-split'},
    ]
    # Calculer le pourcentage pour chaque type
    for c in contrats_detail:
        c['pct'] = round(c['count'] / total * 100, 1) if c['count'] else 0

    # Filtrer les types avec au moins 1 employé (pour le graphique)
    context['contrats_detail'] = contrats_detail
    context['contrats_actifs'] = [c for c in contrats_detail if c['count'] > 0]
    context['contrats_sans'] = employes_stats['sans_contrat']
    context['employes_sans_service'] = employes_stats['sans_service']
    
    # Congés en cours
    aujourd_hui = timezone.now().date()
    conges_en_cours = Conge.objects.filter(
        statut_demande='approuve',
        date_debut__lte=aujourd_hui,
        date_fin__gte=aujourd_hui,
        employe__entreprise=request.user.entreprise,
    )
    context['conges_en_cours'] = conges_en_cours.count()
    context['employes_en_conge'] = conges_en_cours.select_related('employe')[:5]
    
    # Congés en attente
    context['conges_en_attente'] = Conge.objects.filter(
        statut_demande='en_attente',
        employe__entreprise=request.user.entreprise,
    ).count()
    
    # Paie de la periode selectionnee. Sans filtre, on affiche le cumul global.
    bulletins_paie = BulletinPaie.objects.filter(
        employe__entreprise=request.user.entreprise,
    )
    if annee_filtre:
        bulletins_paie = bulletins_paie.filter(periode__annee=annee_filtre)
    if mois_filtre:
        bulletins_paie = bulletins_paie.filter(periode__mois=mois_filtre)

    # Un bulletin "calcule" recouvre tous ceux dont les calculs ont ete figes
    # (calcule, valide, paye). Un bulletin "valide" inclut les bulletins payes.
    context['bulletins_calcules'] = bulletins_paie.filter(
        statut_bulletin__in=('calcule', 'valide', 'paye')
    ).count()
    context['bulletins_valides'] = bulletins_paie.filter(
        statut_bulletin__in=('valide', 'paye')
    ).count()
    context['bulletins_en_attente'] = max(
        0, context['bulletins_calcules'] - context['bulletins_valides']
    )
    totaux = bulletins_paie.aggregate(
        brut=Sum('salaire_brut'),
        net=Sum('net_a_payer'),
        base_vf=Sum('base_vf'),
        trs=Sum('irg'),
        vf=Sum('versement_forfaitaire'),
        ta=Sum('taxe_apprentissage'),
        onfpp=Sum('contribution_onfpp'),
        cnss_5=Sum('cnss_employe'),
        cnss_18=Sum('cnss_employeur'),
    )
    # Conserver les sommes des charges arrondies bulletin par bulletin.
    # Recalculer un taux sur la base globale cree des ecarts d'arrondi et
    # masque les eventuelles anomalies, deja exposees par le risque fiscal.
    context.update(_build_paie_totaux_context(totaux))
    context['risque_fiscal'] = _build_risque_fiscal_paie(bulletins_paie, context.get('total_employes', 0))
    context['repartition_service_paie'] = _build_repartition_service_paie(
        bulletins_paie,
        context.get('total_employes', 0),
    )
    
    # Pointages du jour
    context['pointages_jour'] = Pointage.objects.filter(
        date_pointage=aujourd_hui,
        employe__entreprise=request.user.entreprise,
    ).count()
    
    # Alertes
    context['alertes'] = []
    
    # Contrats arrivant à échéance (30 jours) — tous types à durée limitée
    date_limite = aujourd_hui + timedelta(days=30)
    contrats_echeance = Employe.objects.filter(
        entreprise=request.user.entreprise,
        type_contrat__in=['CDD', 'CDImp', 'CTI', 'stage', 'apprentissage', 'temporaire'],
        date_fin_contrat__lte=date_limite,
        date_fin_contrat__gte=aujourd_hui,
        statut_employe='actif'
    )
    contrats_echeance_count = contrats_echeance.count()

    if contrats_echeance_count > 0:
        # Détail par type
        echeance_par_type = contrats_echeance.values('type_contrat').annotate(nb=Count('id'))
        details = ', '.join([f"{e['nb']} {e['type_contrat']}" for e in echeance_par_type])
        context['alertes'].append({
            'type': 'warning',
            'icon': 'bi-exclamation-triangle',
            'message': f'{contrats_echeance_count} contrat(s) arrivent à échéance dans les 30 jours ({details})'
        })

    # Contrats expirés non traités
    contrats_expires = Employe.objects.filter(
        entreprise=request.user.entreprise,
        date_fin_contrat__lt=aujourd_hui,
        statut_employe='actif',
        type_contrat__in=['CDD', 'CDImp', 'CTI', 'stage', 'apprentissage', 'temporaire'],
    ).count()

    if contrats_expires > 0:
        context['alertes'].append({
            'type': 'danger',
            'icon': 'bi-calendar-x',
            'message': f'{contrats_expires} contrat(s) expiré(s) avec employé(s) toujours actif(s) — action requise'
        })

    # Employés sans type de contrat
    if context.get('contrats_sans', 0) > 0:
        context['alertes'].append({
            'type': 'info',
            'icon': 'bi-file-earmark-x',
            'message': f'{context["contrats_sans"]} employé(s) actif(s) sans type de contrat défini'
        })

    # Employés sans service — bloque le pilotage par département
    sans_service = context.get('employes_sans_service', 0)
    if sans_service > 0:
        total_emp = context.get('total_employes') or 1
        ratio = sans_service * 100 // total_emp
        # warning au-dessus de 10% des effectifs, info en-dessous
        type_alerte = 'warning' if ratio >= 10 else 'info'
        context['alertes'].append({
            'type': type_alerte,
            'icon': 'bi-diagram-3',
            'message': (
                f'{sans_service} employé(s) actif(s) sans service affecté '
                f'({ratio}% de l\'effectif) — pilotage par département impossible '
                f'tant que ces employés ne sont pas rattachés.'
            )
        })

    # Congés en attente de validation
    if context['conges_en_attente'] > 0:
        context['alertes'].append({
            'type': 'info',
            'icon': 'bi-calendar-check',
            'message': f'{context["conges_en_attente"]} demande(s) de congé en attente'
        })
    
    # Ajouter les variables de filtre au contexte
    context.update(filtre_context)

    # Mettre en cache pour 2 minutes
    cache.set(cache_key, context, 120)

    return render(request, 'dashboard/index.html', context)


@login_required
def rapports(request):
    """Page des rapports et statistiques"""
    from datetime import date
    from django.db.models import Avg, Count, Q
    from django.db.models.functions import ExtractYear
    
    context = {}
    
    if not request.user.entreprise_id:
        context['effectif_total'] = 0
        context['recrutements'] = 0
        context['departs'] = 0
        context['taux_rotation'] = 0
        context['effectif_mensuel'] = [0] * 12
        context['mois'] = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
                           'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
        context['pyramide_ages'] = {'< 25 ans': 0, '25-34 ans': 0, '35-44 ans': 0, '45-54 ans': 0, '55+ ans': 0}
        context['age_moyen'] = 0
        context['anciennete_moyenne'] = 0
        context['hommes'] = 0
        context['femmes'] = 0
        context['services_stats'] = []
        context['taux_absenteisme'] = 0
        context['annee'] = timezone.now().year
        return render(request, 'dashboard/rapports.html', context)
    
    # Statistiques annuelles
    annee = int(request.GET.get('annee', timezone.now().year))
    context['annee'] = annee
    aujourd_hui = timezone.now().date()
    
    # Employés de l'entreprise
    employes_entreprise = Employe.objects.filter(entreprise=request.user.entreprise)
    employes_actifs = employes_entreprise.filter(statut_employe='actif')
    
    # Effectif total actuel
    effectif_total = employes_actifs.count()
    context['effectif_total'] = effectif_total
    
    # Recrutements de l'année
    recrutements = employes_entreprise.filter(
        date_embauche__year=annee
    ).count()
    context['recrutements'] = recrutements
    
    # Départs de l'année
    departs = employes_entreprise.filter(
        date_depart__year=annee
    ).count()
    context['departs'] = departs
    
    # Taux de rotation (turnover)
    if effectif_total > 0:
        taux_rotation = round((departs / effectif_total) * 100, 1)
    else:
        taux_rotation = 0
    context['taux_rotation'] = taux_rotation
    
    # Évolution effectif par mois (corrigé)
    effectif_mensuel = []
    for mois in range(1, 13):
        fin_mois = date(annee, mois, 28)  # Approximation fin de mois
        
        # Employés embauchés avant ou pendant ce mois
        effectif = employes_entreprise.filter(
            date_embauche__lte=fin_mois
        ).filter(
            Q(date_depart__isnull=True) | Q(date_depart__gt=fin_mois)
        ).count()
        effectif_mensuel.append(effectif)
    
    context['effectif_mensuel'] = effectif_mensuel
    context['mois'] = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 
                       'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
    
    # Pyramide des âges
    pyramide_ages = {
        '< 25 ans': 0,
        '25-34 ans': 0,
        '35-44 ans': 0,
        '45-54 ans': 0,
        '55+ ans': 0
    }
    
    ages = []
    for employe in employes_actifs:
        if employe.date_naissance:
            age = (aujourd_hui - employe.date_naissance).days // 365
            ages.append(age)
            if age < 25:
                pyramide_ages['< 25 ans'] += 1
            elif age < 35:
                pyramide_ages['25-34 ans'] += 1
            elif age < 45:
                pyramide_ages['35-44 ans'] += 1
            elif age < 55:
                pyramide_ages['45-54 ans'] += 1
            else:
                pyramide_ages['55+ ans'] += 1
    
    context['pyramide_ages'] = pyramide_ages
    
    # Âge moyen
    context['age_moyen'] = round(sum(ages) / len(ages), 1) if ages else 0
    
    # Ancienneté moyenne
    anciennetes = []
    for employe in employes_actifs:
        if employe.date_embauche:
            anciennete = (aujourd_hui - employe.date_embauche).days / 365
            anciennetes.append(anciennete)
    context['anciennete_moyenne'] = round(sum(anciennetes) / len(anciennetes), 1) if anciennetes else 0
    
    # Répartition par genre
    hommes = employes_actifs.filter(sexe='M').count()
    femmes = employes_actifs.filter(sexe='F').count()
    context['hommes'] = hommes
    context['femmes'] = femmes
    
    # Répartition par service
    from core.models import Service
    services_stats = []

    # Essayer plusieurs chemins pour trouver les services
    services = Service.objects.filter(entreprise=request.user.entreprise, actif=True)

    for service in services:
        effectif = employes_actifs.filter(service=service).count()
        if effectif > 0:
            hommes = employes_actifs.filter(service=service, sexe='M').count()
            femmes = employes_actifs.filter(service=service, sexe='F').count()
            pourcentage = round((effectif / effectif_total) * 100, 1) if effectif_total > 0 else 0
            services_stats.append({
                'nom': service.nom_service,
                'effectif': effectif,
                'hommes': hommes,
                'femmes': femmes,
                'pourcentage': pourcentage
            })

    # Si aucun service trouvé, regrouper par service_id
    if not services_stats:
        from django.db.models import Count
        services_groupe = employes_actifs.exclude(service__isnull=True).values(
            'service__nom_service'
        ).annotate(
            effectif=Count('id'),
            hommes=Count('id', filter=Q(sexe='M')),
            femmes=Count('id', filter=Q(sexe='F'))
        ).order_by('-effectif')

        for s in services_groupe:
            pourcentage = round((s['effectif'] / effectif_total) * 100, 1) if effectif_total > 0 else 0
            services_stats.append({
                'nom': s['service__nom_service'],
                'effectif': s['effectif'],
                'hommes': s['hommes'],
                'femmes': s['femmes'],
                'pourcentage': pourcentage
            })

    context['services_stats'] = services_stats
    
    # Taux d'absentéisme (placeholder - à calculer si module absences existe)
    context['taux_absenteisme'] = 0
    
    return render(request, 'dashboard/rapports.html', context)


@login_required
def statistiques_paie(request):
    """Statistiques de paie"""
    context = {}
    
    annee = request.GET.get('annee', timezone.now().year)
    context['annee'] = int(annee)
    
    if not request.user.entreprise_id:
        context['masse_mensuelle'] = [0] * 12
        context['mois'] = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
                           'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
        return render(request, 'dashboard/statistiques_paie.html', context)
    
    # Masse salariale mensuelle
    masse_mensuelle = []
    for mois in range(1, 13):
        try:
            periode = PeriodePaie.objects.get(
                entreprise=request.user.entreprise,
                annee=annee,
                mois=mois
            )
            total = BulletinPaie.objects.filter(
                periode=periode,
                statut_bulletin__in=['valide', 'paye'],
                employe__entreprise=request.user.entreprise,
            ).aggregate(total=Sum('net_a_payer'))['total'] or 0
            masse_mensuelle.append(float(total))
        except PeriodePaie.DoesNotExist:
            masse_mensuelle.append(0)
    
    context['masse_mensuelle'] = masse_mensuelle
    context['mois'] = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 
                       'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
    
    return render(request, 'dashboard/statistiques_paie.html', context)


@login_required
def telecharger_manuel(request):
    """Télécharger le manuel d'utilisation en PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    import io
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    def nouvelle_page():
        p.showPage()
        return height - 2*cm
    
    def check_page(y, needed=3*cm):
        if y < needed:
            return nouvelle_page()
        return y
    
    def draw_title(y, text, size=14):
        y = check_page(y, 2*cm)
        p.setFont("Helvetica-Bold", size)
        p.setFillColor(colors.HexColor("#0d6efd"))
        p.drawString(2*cm, y, text)
        p.setFillColor(colors.black)
        return y - 0.7*cm
    
    def draw_subtitle(y, text, size=11):
        y = check_page(y, 1.5*cm)
        p.setFont("Helvetica-Bold", size)
        p.setFillColor(colors.HexColor("#198754"))
        p.drawString(2*cm, y, text)
        p.setFillColor(colors.black)
        return y - 0.5*cm
    
    def draw_definition(y, term, definition):
        y = check_page(y, 1.5*cm)
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.HexColor("#6c757d"))
        p.drawString(2.2*cm, y, f"{term}:")
        p.setFillColor(colors.black)
        p.setFont("Helvetica", 9)
        # Dessiner la définition sur la même ligne ou ligne suivante
        term_width = p.stringWidth(f"{term}: ", "Helvetica-Bold", 9)
        remaining_width = width - 4*cm - term_width
        if p.stringWidth(definition, "Helvetica", 9) < remaining_width:
            p.drawString(2.2*cm + term_width, y, definition)
            return y - 0.45*cm
        else:
            y -= 0.35*cm
            return draw_text(y, definition, 2.2)
    
    def draw_text(y, text, indent=2):
        y = check_page(y, 1*cm)
        p.setFont("Helvetica", 9)
        max_width = width - (indent + 2)*cm
        words = text.split()
        line = ""
        for word in words:
            test_line = line + " " + word if line else word
            if p.stringWidth(test_line, "Helvetica", 9) < max_width:
                line = test_line
            else:
                p.drawString(indent*cm, y, line)
                y -= 0.35*cm
                y = check_page(y, 0.5*cm)
                line = word
        if line:
            p.drawString(indent*cm, y, line)
            y -= 0.35*cm
        return y - 0.15*cm
    
    def draw_bullet(y, text, indent=2.5):
        y = check_page(y, 0.8*cm)
        p.drawString(indent*cm - 0.3*cm, y, "•")
        return draw_text(y, text, indent)
    
    def draw_note(y, text):
        y = check_page(y, 1.2*cm)
        p.setFillColor(colors.HexColor("#0dcaf0"))
        p.rect(1.8*cm, y - 0.1*cm, 0.15*cm, 0.4*cm, fill=1, stroke=0)
        p.setFillColor(colors.black)
        p.setFont("Helvetica-Oblique", 8)
        return draw_text(y, text, 2.2)
    
    y = height - 2*cm
    
    # === PAGE DE COUVERTURE ===
    p.setFont("Helvetica-Bold", 26)
    p.setFillColor(colors.HexColor("#0d6efd"))
    p.drawCentredString(width/2, height - 7*cm, "MANUEL D'UTILISATION")
    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(width/2, height - 8.5*cm, "Gestionnaire RH Guinée")
    
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 12)
    p.drawCentredString(width/2, height - 11*cm, "Application de Gestion des Ressources Humaines")
    p.drawCentredString(width/2, height - 11.8*cm, "Paie, Congés, Pointages, Formations, Recrutement")
    
    p.setFont("Helvetica", 10)
    p.drawCentredString(width/2, height - 14*cm, "Conforme à la législation guinéenne")
    p.drawCentredString(width/2, height - 14.6*cm, "Code du Travail - CNSS - Direction Générale des Impôts")
    
    p.setFont("Helvetica-Oblique", 10)
    p.drawCentredString(width/2, height - 17*cm, f"Version 3.1 - {timezone.now().strftime('%B %Y')}")
    p.drawCentredString(width/2, height - 17.6*cm, "www.guineerh.space")
    
    y = nouvelle_page()
    
    # === TABLE DES MATIÈRES ===
    y = draw_title(y, "TABLE DES MATIÈRES", 14)
    y -= 0.3*cm
    toc = [
        "1. Introduction et Présentation",
        "2. Glossaire et Définitions RH",
        "3. Gestion des Employés",
        "4. Gestion de la Paie",
        "   4.1 Éléments du bulletin de paie",
        "   4.2 Formules de calcul",
        "   4.3 Barème RTS (6 tranches)",
        "   4.4 Exemple de calcul complet",
        "5. Gestion du Temps de Travail",
        "6. Gestion des Congés",
        "7. Déclarations Sociales",
        "8. Gestion des Formations",
        "9. Recrutement",
        "10. Guide d'utilisation rapide",
    ]
    for item in toc:
        p.setFont("Helvetica", 10)
        p.drawString(2.5*cm, y, item)
        y -= 0.4*cm
    
    y = nouvelle_page()
    
    # === 1. INTRODUCTION ===
    y = draw_title(y, "1. INTRODUCTION ET PRÉSENTATION")
    y = draw_text(y, "Le Gestionnaire RH Guinée est une application complète de gestion des ressources humaines spécialement conçue pour les entreprises guinéennes. Elle intègre tous les aspects de la gestion du personnel: administration, paie, temps de travail, congés, formations et recrutement.")
    y -= 0.2*cm
    y = draw_subtitle(y, "Objectifs de l'application")
    y = draw_bullet(y, "Centraliser toutes les données RH dans un seul système sécurisé")
    y = draw_bullet(y, "Automatiser les calculs de paie selon la législation guinéenne")
    y = draw_bullet(y, "Générer les déclarations sociales (CNSS, IRG) automatiquement")
    y = draw_bullet(y, "Suivre les présences, absences et congés des employés")
    y = draw_bullet(y, "Faciliter le processus de recrutement et d'intégration")
    
    y -= 0.3*cm
    y = draw_subtitle(y, "Conformité légale")
    y = draw_text(y, "L'application respecte intégralement le Code du Travail guinéen, les règlements de la Caisse Nationale de Sécurité Sociale (CNSS) et les dispositions fiscales du Code Général des Impôts (CGI 2022+) concernant la Retenue sur Traitements et Salaires (RTS).")
    
    y -= 0.5*cm
    
    # === 2. GLOSSAIRE ===
    y = draw_title(y, "2. GLOSSAIRE ET DÉFINITIONS RH")
    y = draw_text(y, "Cette section définit les termes clés utilisés dans l'application et en gestion des ressources humaines.")
    y -= 0.2*cm
    
    y = draw_subtitle(y, "Termes relatifs à l'emploi")
    y = draw_definition(y, "Matricule", "Identifiant unique attribué à chaque employé dans l'entreprise")
    y = draw_definition(y, "CDI", "Contrat à Durée Indéterminée - contrat sans date de fin prédéfinie")
    y = draw_definition(y, "CDD", "Contrat à Durée Déterminée - contrat avec une date de fin fixée")
    y = draw_definition(y, "Période d'essai", "Période initiale permettant d'évaluer les compétences du salarié")
    y = draw_definition(y, "Ancienneté", "Durée de présence d'un employé dans l'entreprise")
    y = draw_definition(y, "Établissement", "Lieu physique de travail (siège, agence, usine)")
    y = draw_definition(y, "Service", "Département ou unité organisationnelle (RH, Comptabilité, etc.)")
    y = draw_definition(y, "Poste", "Fonction occupée par l'employé (Directeur, Comptable, etc.)")
    
    y -= 0.3*cm
    y = draw_subtitle(y, "Termes relatifs à la paie")
    y = draw_definition(y, "Salaire de base", "Rémunération fixe mensuelle prévue au contrat")
    y = draw_definition(y, "Salaire brut", "Total des gains avant déduction des cotisations et impôts")
    y = draw_definition(y, "Salaire net", "Montant effectivement versé au salarié après retenues")
    y = draw_definition(y, "Prime", "Complément de rémunération (ancienneté, rendement, transport)")
    y = draw_definition(y, "Indemnité", "Compensation pour frais ou sujétions particulières")
    y = draw_definition(y, "Retenue", "Montant prélevé sur le salaire (cotisations, impôts, avances)")
    y = draw_definition(y, "Bulletin de paie", "Document détaillant la rémunération mensuelle")
    y = draw_definition(y, "Période de paie", "Mois de référence pour le calcul du salaire")
    
    y -= 0.3*cm
    y = draw_subtitle(y, "Termes relatifs aux cotisations sociales")
    y = draw_definition(y, "CNSS", "Caisse Nationale de Sécurité Sociale - organisme de protection sociale")
    y = draw_definition(y, "Cotisation salariale", "Part des cotisations payée par l'employé (5% CNSS)")
    y = draw_definition(y, "Cotisation patronale", "Part des cotisations payée par l'employeur (18% CNSS)")
    y = draw_definition(y, "RTS", "Retenue sur Traitements et Salaires - impôt progressif sur les salaires")
    y = draw_definition(y, "Assiette", "Base de calcul des cotisations ou impôts")
    y = draw_definition(y, "Plafond", "Limite maximale de l'assiette de cotisation")
    
    y = nouvelle_page()
    
    # === 3. GESTION DES EMPLOYÉS ===
    y = draw_title(y, "3. GESTION DES EMPLOYÉS")
    y = draw_text(y, "Le module Employés est le cœur de l'application. Il centralise toutes les informations relatives au personnel de l'entreprise.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "À quoi sert ce module ?")
    y = draw_bullet(y, "Créer et maintenir un dossier complet pour chaque employé")
    y = draw_bullet(y, "Suivre l'évolution de carrière (promotions, mutations, augmentations)")
    y = draw_bullet(y, "Gérer les documents administratifs (contrats, pièces d'identité)")
    y = draw_bullet(y, "Calculer automatiquement l'ancienneté et l'âge")
    y = draw_bullet(y, "Générer des rapports sur l'effectif (pyramide des âges, répartition)")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Informations gérées")
    y = draw_text(y, "Pour chaque employé, l'application enregistre:")
    y = draw_bullet(y, "État civil: nom, prénoms, date/lieu de naissance, nationalité, situation matrimoniale")
    y = draw_bullet(y, "Coordonnées: adresse, téléphone, email, personne à contacter en cas d'urgence")
    y = draw_bullet(y, "Données professionnelles: matricule, date d'embauche, type de contrat, poste, service")
    y = draw_bullet(y, "Rémunération: salaire de base, primes fixes, avantages en nature")
    y = draw_bullet(y, "Documents: photo, pièce d'identité, diplômes, contrat signé")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Statuts d'un employé")
    statuts_data = [
        ['Statut', 'Description', 'Impact sur la paie'],
        ['Actif', 'Employé en poste', 'Inclus dans la paie'],
        ['En congé', 'Absence temporaire autorisée', 'Selon type de congé'],
        ['Suspendu', 'Contrat temporairement suspendu', 'Exclu de la paie'],
        ['Démissionnaire', 'A quitté volontairement', 'Solde de tout compte'],
        ['Licencié', 'Contrat rompu par l\'employeur', 'Solde de tout compte'],
        ['Retraité', 'Fin de carrière', 'Exclu définitivement'],
    ]
    table_statuts = Table(statuts_data, colWidths=[3*cm, 6*cm, 5*cm])
    table_statuts.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9ecef')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    tw, th = table_statuts.wrapOn(p, width, height)
    y = check_page(y, th + 1*cm)
    table_statuts.drawOn(p, 2*cm, y - th)
    y = y - th - 0.5*cm
    
    # === 4. GESTION DE LA PAIE ===
    y = draw_title(y, "4. GESTION DE LA PAIE")
    y = draw_text(y, "Le module Paie automatise le calcul des salaires conformément à la législation guinéenne. Il génère les bulletins de paie et prépare les déclarations sociales.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "4.1 Éléments du bulletin de paie")
    y = draw_text(y, "Un bulletin de paie se compose de trois parties principales:")
    
    y -= 0.2*cm
    p.setFont("Helvetica-Bold", 9)
    p.drawString(2.2*cm, y, "A) Les GAINS (ce que l'employé reçoit)")
    y -= 0.4*cm
    y = draw_bullet(y, "Salaire de base: rémunération fixe mensuelle selon le contrat")
    y = draw_bullet(y, "Heures supplémentaires: majoration de 25% à 100% selon les cas")
    y = draw_bullet(y, "Primes: ancienneté, rendement, assiduité, transport, logement")
    y = draw_bullet(y, "Indemnités: déplacement, représentation, panier")
    y = draw_bullet(y, "Avantages en nature: logement, véhicule (valorisés)")
    
    y -= 0.2*cm
    p.setFont("Helvetica-Bold", 9)
    p.drawString(2.2*cm, y, "B) Les RETENUES (ce qui est prélevé)")
    y -= 0.4*cm
    y = draw_bullet(y, "CNSS employé: 5% de l'assiette CNSS (plancher 550K, plafond 2,5M GNF)")
    y = draw_bullet(y, "RTS: impôt progressif sur le revenu selon barème à 6 tranches")
    y = draw_bullet(y, "Avances sur salaire: remboursement des avances consenties")
    y = draw_bullet(y, "Autres retenues: prêts, saisies sur salaire")
    
    y -= 0.2*cm
    p.setFont("Helvetica-Bold", 9)
    p.drawString(2.2*cm, y, "C) Le NET À PAYER")
    y -= 0.4*cm
    y = draw_text(y, "C'est le montant effectivement versé à l'employé: Salaire Brut - Total des Retenues")
    
    y = nouvelle_page()
    
    y = draw_subtitle(y, "4.2 Formules de calcul détaillées")
    y -= 0.2*cm
    
    formules_data = [
        ['Élément', 'Formule', 'Explication'],
        ['Salaire Brut', 'Base + Primes + HS - Absences', 'Somme de tous les gains'],
        ['Assiette CNSS', 'MIN(MAX(Brut, 550K), 2,5M)', 'Plancher 550K, Plafond 2,5M GNF'],
        ['CNSS Employé', 'Assiette CNSS × 5%', 'Cotisation sociale obligatoire'],
        ['CNSS Employeur', 'Assiette CNSS × 18%', 'Charge patronale'],
        ['VF (Versement Forfaitaire)', 'Brut × 6%', 'Charge patronale'],
        ['TA (Taxe Apprentissage)', 'Brut × 2%', 'Charge patronale'],
        ['Base imposable RTS', 'Brut - CNSS Employé', 'Assiette de l\'impôt'],
        ['RTS', 'Selon barème 6 tranches', 'Voir tableau ci-dessous'],
        ['Total Retenues', 'CNSS + RTS + Autres', 'Somme des prélèvements'],
        ['Net à Payer', 'Brut - Total Retenues', 'Montant viré au salarié'],
    ]
    
    table = Table(formules_data, colWidths=[3.5*cm, 4.5*cm, 7*cm])
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    
    tw, th = table.wrapOn(p, width, height)
    table.drawOn(p, 2*cm, y - th)
    y = y - th - 0.5*cm
    
    y = draw_subtitle(y, "4.3 Barème RTS (Retenue sur Traitements et Salaires) - CGI 2022+")
    y = draw_text(y, "La RTS est un impôt progressif par tranches. Le barème 2022 comporte 6 tranches:")
    y -= 0.2*cm
    
    irg_data = [
        ['Tranche de revenu mensuel', 'Taux', 'Impôt max de la tranche'],
        ['0 - 1 000 000 GNF', '0%', '0 GNF'],
        ['1 000 001 - 3 000 000 GNF', '5%', '100 000 GNF'],
        ['3 000 001 - 5 000 000 GNF', '8%', '160 000 GNF'],
        ['5 000 001 - 10 000 000 GNF', '10%', '500 000 GNF'],
        ['10 000 001 - 20 000 000 GNF', '15%', '1 500 000 GNF'],
        ['Au-delà de 20 000 000 GNF', '20%', 'Variable'],
    ]
    
    table_irg = Table(irg_data, colWidths=[6*cm, 2.5*cm, 5*cm])
    table_irg.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ffc107')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    tw, th = table_irg.wrapOn(p, width, height)
    table_irg.drawOn(p, 2*cm, y - th)
    y = y - th - 0.4*cm
    
    y = draw_note(y, "Important: La RTS est calculée par tranches successives. La tranche 8% (3M-5M GNF) a été ajoutée par le CGI 2022.")
    
    y -= 0.3*cm
    y = draw_subtitle(y, "4.4 Exemple de calcul complet")
    y = draw_text(y, "Prenons l'exemple d'un employé avec un salaire brut de 8 000 000 GNF:")
    y -= 0.2*cm
    
    exemple_data = [
        ['Étape', 'Calcul', 'Montant'],
        ['1. Salaire Brut', 'Donné', '8 000 000 GNF'],
        ['2. Assiette CNSS', 'MIN(8M, 2,5M) = Plafond', '2 500 000 GNF'],
        ['3. CNSS Employé', '2 500 000 × 5%', '125 000 GNF'],
        ['4. Base RTS', '8 000 000 - 125 000', '7 875 000 GNF'],
        ['5. RTS Tr.1 (0%)', '1 000 000 × 0%', '0 GNF'],
        ['6. RTS Tr.2 (5%)', '2 000 000 × 5%', '100 000 GNF'],
        ['7. RTS Tr.3 (8%)', '2 000 000 × 8%', '160 000 GNF'],
        ['8. RTS Tr.4 (10%)', '2 875 000 × 10%', '287 500 GNF'],
        ['9. Total RTS', '0+100K+160K+287,5K', '547 500 GNF'],
        ['10. Total Retenues', '125 000 + 547 500', '672 500 GNF'],
        ['11. Net à Payer', '8 000 000 - 672 500', '7 327 500 GNF'],
    ]
    
    table_ex = Table(exemple_data, colWidths=[4*cm, 5.5*cm, 4*cm])
    table_ex.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#198754')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d4edda')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    tw, th = table_ex.wrapOn(p, width, height)
    y = check_page(y, th + 1*cm)
    table_ex.drawOn(p, 2*cm, y - th)
    y = y - th - 0.5*cm
    
    y = draw_note(y, "Note: Charges patronales: CNSS 18% (450K sur plafond 2,5M) + VF 6% (480K) + TA 2% (160K) = 1 090 000 GNF.")
    
    y = nouvelle_page()
    
    # === 5. TEMPS DE TRAVAIL ===
    y = draw_title(y, "5. GESTION DU TEMPS DE TRAVAIL")
    y = draw_text(y, "Le module Pointage permet de suivre la présence des employés et de calculer les heures travaillées pour la paie.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "À quoi sert ce module ?")
    y = draw_bullet(y, "Enregistrer les heures d'arrivée et de départ quotidiennes")
    y = draw_bullet(y, "Détecter automatiquement les retards et absences")
    y = draw_bullet(y, "Calculer les heures supplémentaires")
    y = draw_bullet(y, "Générer des rapports de présence par employé ou service")
    y = draw_bullet(y, "Alimenter automatiquement le calcul de la paie")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Statuts de pointage")
    y = draw_definition(y, "Présent", "L'employé a travaillé normalement")
    y = draw_definition(y, "Absent", "L'employé n'est pas venu sans justification")
    y = draw_definition(y, "Retard", "L'employé est arrivé après l'heure prévue")
    y = draw_definition(y, "Congé", "Absence autorisée (lié au module Congés)")
    y = draw_definition(y, "Mission", "Déplacement professionnel hors du lieu de travail")
    y = draw_definition(y, "Maladie", "Absence pour raison de santé (avec justificatif)")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Heures supplémentaires (Code du Travail, Art. 142)")
    y = draw_text(y, "Selon le Code du Travail guinéen, les heures au-delà de la durée légale (40h/semaine) sont majorées:")
    y = draw_bullet(y, "41e à 48e heure/semaine: majoration de 15%")
    y = draw_bullet(y, "Au-delà de 48e heure: majoration de 25%")
    y = draw_bullet(y, "Heures de nuit (21h-6h): majoration de 50%")
    y = draw_bullet(y, "Dimanches et jours fériés: majoration de 100%")
    
    y -= 0.5*cm
    
    # === 6. CONGÉS ===
    y = draw_title(y, "6. GESTION DES CONGÉS")
    y = draw_text(y, "Le module Congés gère l'ensemble du cycle des absences autorisées: demande, validation, suivi du solde.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Types de congés")
    conges_data = [
        ['Type', 'Durée', 'Rémunération', 'Conditions'],
        ['Annuel', '18 jours/an + ancienneté', '100%', '1,5j ouvrable/mois + 2j/5ans ancienneté'],
        ['Maladie', 'Variable', '50-100%', 'Certificat médical requis'],
        ['Maternité', '14 semaines', '100%', 'Femmes enceintes'],
        ['Paternité', '3 jours', '100%', 'Naissance d\'un enfant'],
        ['Mariage', '3 jours', '100%', 'Mariage de l\'employé'],
        ['Décès', '3-5 jours', '100%', 'Décès d\'un proche'],
        ['Sans solde', 'Variable', '0%', 'Accord de l\'employeur'],
    ]
    table_conges = Table(conges_data, colWidths=[2.5*cm, 2.5*cm, 2.5*cm, 6*cm])
    table_conges.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 7),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17a2b8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
    ]))
    tw, th = table_conges.wrapOn(p, width, height)
    y = check_page(y, th + 1*cm)
    table_conges.drawOn(p, 2*cm, y - th)
    y = y - th - 0.4*cm
    
    y = draw_subtitle(y, "Calcul du solde de congés (Code du Travail, Art. 153)")
    y = draw_text(y, "Chaque employé acquiert 2.5 jours ouvrables de congé par mois de travail effectif. Le solde est calculé automatiquement:")
    y = draw_bullet(y, "Base: 30 jours ouvrables par an (2.5 jours/mois)")
    y = draw_bullet(y, "Majoration ancienneté: +1j (5-10 ans), +2j (10-15 ans), +3j (15-20 ans), +4j (>20 ans)")
    y = draw_bullet(y, "Solde = Jours acquis + Majorations - Jours pris")
    y = draw_bullet(y, "En cas de départ, les congés non pris sont indemnisés")
    
    y = nouvelle_page()
    
    # === 7. DÉCLARATIONS SOCIALES ===
    y = draw_title(y, "7. DÉCLARATIONS SOCIALES")
    y = draw_text(y, "L'application génère automatiquement les déclarations obligatoires à partir des bulletins de paie validés.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "7.1 Déclaration CNSS")
    y = draw_text(y, "La Caisse Nationale de Sécurité Sociale collecte les cotisations pour financer:")
    y = draw_bullet(y, "Les pensions de retraite")
    y = draw_bullet(y, "Les allocations familiales")
    y = draw_bullet(y, "L'assurance maladie et accidents du travail")
    
    y -= 0.2*cm
    cnss_data = [
        ['Cotisation', 'Taux', 'Payée par', 'Échéance'],
        ['Part salariale', '5%', 'Employé (retenue)', '15 du mois suivant'],
        ['Part patronale', '18%', 'Employeur', '15 du mois suivant'],
        ['Total', '23%', '-', '-'],
    ]
    table_cnss = Table(cnss_data, colWidths=[4*cm, 2.5*cm, 4*cm, 4*cm])
    table_cnss.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#cfe2ff')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    tw, th = table_cnss.wrapOn(p, width, height)
    table_cnss.drawOn(p, 2*cm, y - th)
    y = y - th - 0.4*cm
    
    y = draw_subtitle(y, "7.2 Déclaration RTS")
    y = draw_text(y, "La Retenue sur Traitements et Salaires est retenue à la source par l'employeur et reversée au Trésor Public:")
    y = draw_bullet(y, "Calcul: selon le barème progressif à 6 tranches (voir section 4.3)")
    y = draw_bullet(y, "Échéance: avant le 15 du mois suivant")
    y = draw_bullet(y, "Déclaration annuelle récapitulative obligatoire")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "7.3 Versement Forfaitaire (VF) et Taxe d'Apprentissage (TA)")
    y = draw_text(y, "Charges patronales calculées sur le salaire brut total (non plafonné):")
    y = draw_bullet(y, "VF: 6% du salaire brut - Échéance: 15 du mois suivant")
    y = draw_bullet(y, "TA: 2% du salaire brut - Échéance: 15 du mois suivant")
    
    y -= 0.2*cm
    y = draw_note(y, "Pénalités: Le non-respect des échéances entraîne des majorations de retard (10% + intérêts).")
    
    y -= 0.5*cm
    
    # === 8. FORMATIONS ===
    y = draw_title(y, "8. GESTION DES FORMATIONS")
    y = draw_text(y, "Le module Formation permet de développer les compétences des employés et de suivre leur parcours de formation.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Fonctionnalités")
    y = draw_bullet(y, "Catalogue de formations: créer et gérer les formations disponibles")
    y = draw_bullet(y, "Sessions: planifier des sessions avec dates, lieu, formateur et places")
    y = draw_bullet(y, "Inscriptions: inscrire les employés aux sessions")
    y = draw_bullet(y, "Suivi: évaluer les formations et suivre les compétences acquises")
    y = draw_bullet(y, "Budget: suivre les coûts de formation par employé et par service")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Types de formations")
    y = draw_definition(y, "Interne", "Dispensée par un formateur de l'entreprise")
    y = draw_definition(y, "Externe", "Dispensée par un organisme extérieur")
    y = draw_definition(y, "En ligne", "Formation à distance (e-learning)")
    y = draw_definition(y, "Certifiante", "Délivre un certificat ou diplôme reconnu")
    
    y = nouvelle_page()
    
    # === 9. RECRUTEMENT ===
    y = draw_title(y, "9. RECRUTEMENT")
    y = draw_text(y, "Le module Recrutement accompagne tout le processus d'embauche, de la publication de l'offre à l'intégration du nouvel employé.")
    
    y -= 0.2*cm
    y = draw_subtitle(y, "Étapes du processus")
    y = draw_bullet(y, "1. Création de l'offre: définir le poste, les compétences requises, le salaire")
    y = draw_bullet(y, "2. Publication: diffuser l'offre sur différents canaux")
    y = draw_bullet(y, "3. Réception des candidatures: centraliser les CV et lettres de motivation")
    y = draw_bullet(y, "4. Présélection: trier les candidatures selon les critères définis")
    y = draw_bullet(y, "5. Entretiens: planifier et conduire les entretiens")
    y = draw_bullet(y, "6. Sélection: choisir le candidat retenu")
    y = draw_bullet(y, "7. Embauche: créer le dossier employé et le contrat")
    
    y -= 0.5*cm
    
    # === 10. GUIDE RAPIDE ===
    y = draw_title(y, "10. GUIDE D'UTILISATION RAPIDE")
    
    y = draw_subtitle(y, "Créer un employé")
    y = draw_text(y, "Menu Employés → Nouvel employé → Remplir le formulaire → Enregistrer")
    
    y = draw_subtitle(y, "Calculer la paie mensuelle")
    y = draw_text(y, "Menu Paie → Périodes → Créer/Sélectionner le mois → Générer les bulletins → Valider")
    
    y = draw_subtitle(y, "Gérer une demande de congé")
    y = draw_text(y, "Menu Temps → Congés → Nouvelle demande ou Valider une demande en attente")
    
    y = draw_subtitle(y, "Générer les déclarations")
    y = draw_text(y, "Menu Paie → Déclarations sociales → Sélectionner la période → Télécharger/Imprimer")
    
    y -= 0.8*cm
    y = draw_title(y, "SUPPORT ET CONTACT")
    y = draw_text(y, "Pour toute question ou assistance technique:")
    y = draw_bullet(y, "Site web: www.guineerh.space")
    y = draw_bullet(y, "Email: support@guineerh.space")
    y -= 0.3*cm
    y = draw_text(y, "Notre équipe est disponible du lundi au vendredi, de 8h à 17h.")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Manuel_Utilisation_GestionnaireRH.pdf"'
    return response
