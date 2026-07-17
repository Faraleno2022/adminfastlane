"""
Service de rétro-calcul salarial : Net → Brut
=============================================
Permet de déterminer le salaire BRUT à saisir pour qu'un employé
reçoive exactement le NET négocié/convenu (ex: 5 500 000 GNF net).

Algorithme : Dichotomie (binary search) sur la fonction brut→net
Conformité  : Législation guinéenne (CNSS + RTS barème CGI officiel)

Utilisation :
    from paie.services_retropaie import retropaie_net_vers_brut
    resultat = retropaie_net_vers_brut(net_cible=5_500_000, annee=2025)
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from datetime import date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _d(valeur):
    """Convertit en Decimal propre."""
    return Decimal(str(valeur))


def _arrondir(montant):
    """Arrondit à l'unité (pas de centimes en GNF)."""
    return _d(montant).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _verrouiller_cnss_legale(constantes):
    """CNSS Guinee: base et taux fixes, sans surcharge flottante."""
    constantes['PLANCHER_CNSS'] = Decimal('550000')
    constantes['PLAFOND_CNSS'] = Decimal('2500000')
    constantes['TAUX_CNSS_EMPLOYE'] = Decimal('5')
    constantes['TAUX_CNSS_EMPLOYEUR'] = Decimal('18')
    return constantes


# ---------------------------------------------------------------------------
# Calcul CNSS employé
# ---------------------------------------------------------------------------

def _calculer_cnss(brut, plancher, plafond, taux_employe):
    """
    Calcule la cotisation CNSS salarié selon les règles guinéennes.

    Règles :
    - Brut < 10 % du plancher  → pas de cotisation
    - Brut < plancher          → cotiser sur le plancher
    - Plancher ≤ brut ≤ plafond → cotiser sur le brut réel
    - Brut > plafond           → cotiser sur le plafond

    Retourne (cnss_employe, base_cnss_plafonnee).
    """
    seuil_min = _arrondir(plancher * Decimal('0.10'))   # 10 % du plancher
    if brut < seuil_min:
        return Decimal('0'), Decimal('0')

    base = _arrondir(max(min(brut, plafond), plancher))
    cnss = _arrondir(base * taux_employe / Decimal('100'))
    return cnss, base


# ---------------------------------------------------------------------------
# Calcul RTS/IRG progressif
# ---------------------------------------------------------------------------

def _calculer_rts(base_imposable, tranches):
    """
    Calcule l'IRG/RTS selon le barème progressif à tranches.

    tranches : liste de dict {borne_inferieure, borne_superieure, taux_irg}
               ou objets TrancheRTS (accès par attributs).
    """
    if base_imposable <= 0:
        return Decimal('0')

    # Normaliser les tranches en tuples (borne_inf, borne_sup, taux)
    seuils = []
    for i, t in enumerate(tranches):
        if isinstance(t, dict):
            bi  = _d(t['borne_inferieure'])
            bs  = _d(t['borne_superieure']) if t.get('borne_superieure') is not None else None
            tx  = _d(t['taux_irg'])
        else:
            bi  = _d(t.borne_inferieure)
            bs  = _d(t.borne_superieure) if t.borne_superieure is not None else None
            tx  = _d(t.taux_irg)

        # Combler les gaps d'1 GNF entre tranches (1 000 001 → 1 000 000)
        if i > 0 and seuils:
            prev_sup = seuils[-1][1]
            if prev_sup is not None and bi > prev_sup and bi <= prev_sup + 2:
                bi = prev_sup

        seuils.append((bi, bs, tx))

    irg = Decimal('0')
    for bi, bs, tx in seuils:
        if base_imposable <= bi:
            break
        montant = (min(base_imposable, bs) - bi) if bs is not None else (base_imposable - bi)
        if montant > 0:
            irg += _arrondir(montant * tx / Decimal('100'))

    return irg


# ---------------------------------------------------------------------------
# Calcul NET depuis BRUT (sens direct)
# ---------------------------------------------------------------------------

def _net_depuis_brut(brut, constantes, tranches, pct_indem_exonerees=Decimal('0')):
    """
    Calcule le net depuis un brut donné.

    pct_indem_exonerees : pourcentage du brut représenté par des indemnités
                          forfaitaires exonérées de RTS (0 à 25, ex: 15 pour 15 %).
    Retourne (net, cnss, base_cnss, base_rts, rts).
    """
    plancher  = constantes.get('PLANCHER_CNSS',     Decimal('550000'))
    plafond   = constantes.get('PLAFOND_CNSS',      Decimal('2500000'))
    taux_cnss = constantes.get('TAUX_CNSS_EMPLOYE', Decimal('5'))

    cnss, base_cnss = _calculer_cnss(brut, plancher, plafond, taux_cnss)

    pct_indem_exonerees = max(
        Decimal('0'), min(Decimal('25'), _d(pct_indem_exonerees))
    )

    # Exonération indemnités forfaitaires (CGI Guinée : max 25 % du brut)
    # ROUND_FLOOR pour cohérence avec services.py (plafond CGI arrondi vers le bas)
    exo = _d(brut * min(pct_indem_exonerees, Decimal('25')) / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_FLOOR)

    base_rts = max(brut - cnss - exo, Decimal('0'))
    rts      = _calculer_rts(base_rts, tranches)
    net      = _arrondir(brut - cnss - rts)

    return net, cnss, base_cnss, base_rts, rts


# ---------------------------------------------------------------------------
# Service principal : Net → Brut (dichotomie)
# ---------------------------------------------------------------------------

def retropaie_net_vers_brut(
    net_cible,
    annee=None,
    pct_indemnites_forfaitaires=0,
    garantir_net_minimum=True,
    max_iterations=50,
    tolerance=1,
):
    """
    Calcule le salaire BRUT nécessaire pour obtenir exactement le NET convenu.

    Paramètres
    ----------
    net_cible : int | float | Decimal
        Net mensuel souhaité en GNF (ex: 5_500_000).
    annee : int, optionnel
        Année du barème RTS à utiliser (défaut : année courante).
    pct_indemnites_forfaitaires : int | float
        Pourcentage du brut constitué d'indemnités forfaitaires exonérées de RTS
        (ex: 15 si transport + logement = 15 % du brut). Max effectif = 25 %.
    garantir_net_minimum : bool
        Si True, arrondit légèrement le brut vers le haut pour s'assurer que
        l'employé reçoit AU MOINS le net négocié (recommandé).
    max_iterations : int
        Nombre maximum d'itérations de dichotomie (120 suffit largement).
    tolerance : int
        Écart maximal acceptable en GNF entre net_calculé et net_cible (défaut : 1 GNF).

    Retourne
    --------
    dict avec les clés :
        brut           – Brut à saisir dans l'application
        cnss           – CNSS employé déduit
        base_cnss      – Base plafonnée de la CNSS
        base_rts       – Base imposable à l'IRG/RTS
        rts            – Montant RTS déduit
        net_calcule    – Net effectif avec ce brut (≥ net_cible si garantir_net_minimum)
        net_cible      – Net demandé
        ecart          – net_calcule − net_cible (0 ou 1 GNF max)
        ok             – True si convergence réussie
        iterations     – Nombre d'itérations utilisées
        detail_tranches – Détail par tranche RTS (liste)
    """
    from .cache_service import PayrollCacheService

    net_cible = _arrondir(_d(net_cible))
    pct_indem = max(
        Decimal('0'), min(Decimal('25'), _d(pct_indemnites_forfaitaires))
    )

    if annee is None:
        annee = date.today().year

    # ---- Chargement des paramètres de paie --------------------------------
    constantes = _verrouiller_cnss_legale(PayrollCacheService.get_constantes(date_reference=date(annee, 1, 1)))
    tranches   = PayrollCacheService.get_tranches_rts(annee)

    # Valeurs par défaut si base vide
    constantes.setdefault('PLANCHER_CNSS',     Decimal('550000'))
    constantes.setdefault('PLAFOND_CNSS',      Decimal('2500000'))
    constantes.setdefault('TAUX_CNSS_EMPLOYE', Decimal('5'))

    # La fonction brut->net baisse au seuil d'assujettissement CNSS. Une
    # dichotomie unique peut donc ignorer la solution de brut minimale.
    # Chercher séparément dans les deux segments monotones corrige ce cas.
    cible = int(net_cible)
    borne_haute = max(cible * 2, cible + int(constantes['PLAFOND_CNSS']))
    seuil_cnss = int(_arrondir(
        constantes['PLANCHER_CNSS'] * Decimal('0.10')
    ))
    segments = [(0, min(borne_haute, seuil_cnss - 1))]
    if borne_haute >= seuil_cnss:
        segments.append((seuil_cnss, borne_haute))

    candidats = set()
    iterations = 0
    for debut, fin in segments:
        if debut > fin:
            continue
        low, high = debut, fin
        for _ in range(max_iterations):
            if low > high:
                break
            iterations += 1
            mid = (low + high) // 2
            net_mid, *_ = _net_depuis_brut(
                Decimal(mid), constantes, tranches, pct_indem
            )
            if int(net_mid) < cible:
                low = mid + 1
            else:
                high = mid - 1
        for brut_candidat in (low - 1, low, low + 1):
            if debut <= brut_candidat <= fin:
                candidats.add(brut_candidat)

    if not candidats:
        candidats.add(borne_haute)

    evaluations = []
    for brut_candidat in candidats:
        net_candidat, *_ = _net_depuis_brut(
            Decimal(brut_candidat), constantes, tranches, pct_indem
        )
        evaluations.append((brut_candidat, int(net_candidat)))

    if garantir_net_minimum:
        admissibles = [item for item in evaluations if item[1] >= cible]
        if not admissibles:
            admissibles = evaluations
        brut_choisi, _ = min(admissibles, key=lambda item: item[0])
        mode = 'net_minimum'
    else:
        brut_choisi, _ = min(
            evaluations,
            key=lambda item: (abs(item[1] - cible), item[0]),
        )
        mode = 'net_exact'

    brut_opt = Decimal(brut_choisi)

    # ---- Résultat final + Assertion de sécurité ---------------------------
    net_final, cnss_f, base_cnss_f, base_rts_f, rts_f = _net_depuis_brut(
        brut_opt, constantes, tranches, pct_indem
    )

    ecart_final = abs(int(net_final) - int(net_cible))
    precision_ok = ecart_final <= int(tolerance)

    # Détail par tranche RTS
    detail_tranches = _detail_tranches(base_rts_f, tranches)

    return {
        'brut':            brut_opt,
        'cnss':            cnss_f,
        'base_cnss':       base_cnss_f,
        'base_rts':        base_rts_f,
        'rts':             rts_f,
        'net_calcule':     net_final,
        'net_cible':       net_cible,
        'ecart':           net_final - net_cible,
        'ok':              precision_ok,
        'iterations':      iterations,
        'detail_tranches': detail_tranches,
        'mode':            mode,
        'precision_ok':    precision_ok,
        'meta': {
            'version_bareme': f'GN-{annee}-v1',
            'methode_inverse': 'binary_search_segments_cnss_v3',
            'max_iterations': max_iterations,
            'tolerance_gnf': int(tolerance),
        },
    }


def verifier_monotonie(annee=None, pct_indemnites_forfaitaires=0, pas=500_000,
                       brut_max=50_000_000):
    """
    Vérifie que la fonction brut→net est monotone croissante.
    Retourne True si OK, lève ValueError si une anomalie est détectée.
    Utile en CI/dev pour valider un barème.
    """
    from .cache_service import PayrollCacheService

    if annee is None:
        annee = date.today().year

    constantes = _verrouiller_cnss_legale(PayrollCacheService.get_constantes(date_reference=date(annee, 1, 1)))
    tranches   = PayrollCacheService.get_tranches_rts(annee)
    constantes.setdefault('PLANCHER_CNSS',     Decimal('550000'))
    constantes.setdefault('PLAFOND_CNSS',      Decimal('2500000'))
    constantes.setdefault('TAUX_CNSS_EMPLOYE', Decimal('5'))

    pct_indem = max(
        Decimal('0'), min(Decimal('25'), _d(pct_indemnites_forfaitaires))
    )
    seuil_cnss = int(_arrondir(
        constantes['PLANCHER_CNSS'] * Decimal('0.10')
    ))
    points = set(range(0, brut_max + 1, pas))
    points.update(
        point for point in (seuil_cnss - 1, seuil_cnss, seuil_cnss + 1)
        if 0 <= point <= brut_max
    )
    prev_net = 0
    prev_brut = 0

    for brut in sorted(points):
        net, *_ = _net_depuis_brut(Decimal(str(brut)), constantes, tranches, pct_indem)
        net = int(net)
        saut_cnss_legal = prev_brut == seuil_cnss - 1 and brut == seuil_cnss
        if net < prev_net and not saut_cnss_legal:
            raise ValueError(
                f"Anomalie de monotonicité : brut={brut:,} → net={net:,} "
                f"< précédent net={prev_net:,} (brut={prev_brut:,})"
            )
        prev_net = net
        prev_brut = brut

    return True


# ---------------------------------------------------------------------------
# Détail par tranche (pour affichage pédagogique)
# ---------------------------------------------------------------------------

def calculer_charges_patronales(
    brut,
    annee=None,
    nb_salaries=0,
    pct_indemnites_forfaitaires=25,
    mode_base_vf='brut',
    mode_base_onfpp='brut',
):
    """
    Calcule les charges patronales pour un brut donné.

    Retourne dict :
        cnss_employeur, vf, ta, libelle_ta, total, cout_total_employeur
    """
    from .cache_service import PayrollCacheService

    if annee is None:
        annee = date.today().year

    constantes = _verrouiller_cnss_legale(PayrollCacheService.get_constantes(date_reference=date(annee, 1, 1)))
    constantes.setdefault('PLANCHER_CNSS',       Decimal('550000'))
    constantes.setdefault('PLAFOND_CNSS',        Decimal('2500000'))
    constantes.setdefault('TAUX_CNSS_EMPLOYEUR', Decimal('18'))
    constantes.setdefault('TAUX_VF',             Decimal('6'))
    constantes.setdefault('TAUX_TA',             Decimal('2'))
    constantes.setdefault('TAUX_ONFPP',          Decimal('1.5'))
    constantes.setdefault('SEUIL_TA_ONFPP',      Decimal('30'))

    brut = _arrondir(_d(brut))
    pct_indem = max(Decimal('0'), min(Decimal('25'), _d(pct_indemnites_forfaitaires)))
    plancher     = constantes['PLANCHER_CNSS']
    plafond      = constantes['PLAFOND_CNSS']
    taux_cnss_pat = constantes['TAUX_CNSS_EMPLOYEUR']
    taux_vf       = constantes['TAUX_VF']
    seuil_ta_onfpp = int(constantes['SEUIL_TA_ONFPP'])
    onfpp_actif   = nb_salaries >= seuil_ta_onfpp
    libelle_ta    = 'ONFPP' if onfpp_actif else 'TA'

    seuil = _arrondir(plancher * Decimal('0.10'))
    if brut < seuil:
        cnss_pat = Decimal('0')
    else:
        base = _arrondir(max(min(brut, plafond), plancher))
        cnss_pat = _arrondir(base * taux_cnss_pat / Decimal('100'))

    deduction_vf = Decimal('0') if mode_base_vf == 'brut' else _arrondir(brut * pct_indem / Decimal('100'))
    base_vf = max(Decimal('0'), brut - deduction_vf)
    vf = _arrondir(base_vf * taux_vf / Decimal('100'))
    taux_ta = constantes['TAUX_ONFPP'] if onfpp_actif else constantes['TAUX_TA']
    base_ta_onfpp = brut if onfpp_actif and mode_base_onfpp == 'brut' else base_vf
    ta = _arrondir(base_ta_onfpp * taux_ta / Decimal('100'))
    total = cnss_pat + vf + ta

    return {
        'cnss_employeur':      int(cnss_pat),
        'mode_base_vf':         mode_base_vf,
        'mode_base_onfpp':      mode_base_onfpp,
        'deduction_vf':         int(deduction_vf),
        'base_vf':             int(base_vf),
        'base_onfpp':          int(base_ta_onfpp) if onfpp_actif else 0,
        'base_ta_onfpp':       int(base_ta_onfpp),
        'vf':                  int(vf),
        'ta':                  int(ta),
        'libelle_ta':          libelle_ta,
        'total':               int(total),
        'cout_total_employeur': int(brut) + int(total),
    }


def cout_total_vers_brut(
    cout_total,
    annee=None,
    pct_indemnites_forfaitaires=0,
    nb_salaries=0,
    max_iterations=50,
):
    """
    Calcule le brut et le net depuis un coût total employeur (budget tout compris).

    cout_total = brut + CNSS_employeur + VF + TA (ou ONFPP)

    Paramètres
    ----------
    cout_total : montant total que l'entreprise paie pour l'employé
    nb_salaries : nombre de salariés (>= 30 -> ONFPP 1.5%, sinon TA 2%)

    Retourne
    --------
    dict : brut, net, cnss_employe, rts, charges_patronales (détail), cout_total_reel
    """
    from .cache_service import PayrollCacheService

    cout_total = _arrondir(_d(cout_total))
    pct_indem = max(
        Decimal('0'), min(Decimal('25'), _d(pct_indemnites_forfaitaires))
    )

    if annee is None:
        annee = date.today().year

    constantes = _verrouiller_cnss_legale(PayrollCacheService.get_constantes(date_reference=date(annee, 1, 1)))
    tranches = PayrollCacheService.get_tranches_rts(annee)

    constantes.setdefault('PLANCHER_CNSS',     Decimal('550000'))
    constantes.setdefault('PLAFOND_CNSS',      Decimal('2500000'))
    constantes.setdefault('TAUX_CNSS_EMPLOYE', Decimal('5'))
    constantes.setdefault('TAUX_CNSS_EMPLOYEUR', Decimal('18'))
    constantes.setdefault('TAUX_VF',           Decimal('6'))
    constantes.setdefault('TAUX_TA',           Decimal('2'))
    constantes.setdefault('TAUX_ONFPP',        Decimal('1.5'))
    constantes.setdefault('SEUIL_TA_ONFPP',    Decimal('30'))

    plancher     = constantes['PLANCHER_CNSS']
    plafond      = constantes['PLAFOND_CNSS']
    taux_cnss_pat = constantes['TAUX_CNSS_EMPLOYEUR']
    taux_vf       = constantes['TAUX_VF']
    seuil_ta_onfpp = int(constantes['SEUIL_TA_ONFPP'])
    onfpp_actif   = nb_salaries >= seuil_ta_onfpp
    libelle_ta    = 'ONFPP' if onfpp_actif else 'TA'

    def _charges_pat(brut):
        seuil = _arrondir(plancher * Decimal('0.10'))
        if brut < seuil:
            cnss_pat = Decimal('0')
        else:
            base = _arrondir(max(min(brut, plafond), plancher))
            cnss_pat = _arrondir(base * taux_cnss_pat / Decimal('100'))
        base_vf = max(Decimal('0'), brut)
        vf = _arrondir(base_vf * taux_vf / Decimal('100'))
        taux_ta_onfpp = constantes['TAUX_ONFPP'] if onfpp_actif else constantes['TAUX_TA']
        base_ta_onfpp = brut
        ta = _arrondir(base_ta_onfpp * taux_ta_onfpp / Decimal('100'))
        return cnss_pat, vf, ta

    def _cout(brut):
        c, v, t = _charges_pat(brut)
        return brut + c + v + t

    # Dichotomie : trouver brut tel que _cout(brut) ≈ cout_total
    low  = Decimal('0')
    high = cout_total  # brut ne peut dépasser le budget total
    brut_opt = _arrondir(cout_total / Decimal('1.26'))  # estimation init

    for _ in range(max_iterations):
        mid = _arrondir((low + high) / 2)
        if abs(_cout(mid) - cout_total) <= _d('1'):
            brut_opt = mid
            break
        if _cout(mid) < cout_total:
            low = mid
        else:
            high = mid
        brut_opt = mid

    # Garantir que le coût calculé ne dépasse pas le budget
    while _cout(brut_opt) > cout_total:
        brut_opt -= Decimal('1')

    # Résultats complets
    cnss_pat, vf, ta = _charges_pat(brut_opt)
    total_pat = cnss_pat + vf + ta
    net, cnss_emp, base_cnss, base_rts, rts = _net_depuis_brut(
        brut_opt, constantes, tranches, pct_indem
    )
    detail_t = _detail_tranches(base_rts, tranches)

    return {
        'cout_total_vise':  int(cout_total),
        'cout_total_reel':  int(_cout(brut_opt)),
        'brut':             brut_opt,
        'cnss_employe':     cnss_emp,
        'base_cnss':        base_cnss,
        'base_rts':         base_rts,
        'rts':              rts,
        'net':              net,
        'charges_patronales': {
            'cnss_employeur': int(cnss_pat),
            'vf':             int(vf),
            'ta':             int(ta),
            'libelle_ta':     libelle_ta,
            'total':          int(total_pat),
        },
        'detail_tranches':  detail_t,
        'ok': abs(int(_cout(brut_opt)) - int(cout_total)) <= 1000,
        'annee':            annee,
    }


def _detail_tranches(base_imposable, tranches):
    """Retourne le détail du calcul RTS tranche par tranche."""
    if base_imposable <= 0:
        return []

    seuils = []
    for i, t in enumerate(tranches):
        if isinstance(t, dict):
            bi = _d(t['borne_inferieure'])
            bs = _d(t['borne_superieure']) if t.get('borne_superieure') is not None else None
            tx = _d(t['taux_irg'])
        else:
            bi = _d(t.borne_inferieure)
            bs = _d(t.borne_superieure) if t.borne_superieure is not None else None
            tx = _d(t.taux_irg)

        if i > 0 and seuils:
            prev_sup = seuils[-1][1]
            if prev_sup is not None and bi > prev_sup and bi <= prev_sup + 2:
                bi = prev_sup
        seuils.append((bi, bs, tx))

    detail = []
    for bi, bs, tx in seuils:
        if base_imposable <= bi:
            break
        montant = (min(base_imposable, bs) - bi) if bs is not None else (base_imposable - bi)
        if montant > 0:
            impot_tranche = _arrondir(montant * tx / Decimal('100'))
            detail.append({
                'borne_inf': int(bi),
                'borne_sup': int(bs) if bs is not None else None,
                'taux':      float(tx),
                'montant_tranche': int(montant),
                'impot_tranche':   int(impot_tranche),
            })

    return detail
