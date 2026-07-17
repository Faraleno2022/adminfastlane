"""
Moteur de simulation fiscale multi-barèmes - Guinée
Conformité CGI guinéen: barème RTS progressif + plafond 25% indemnités

Algorithme validé par les tests T01–T17 (cf. _test_rts_tmp.py)
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from datetime import date

from .models import TrancheRTS


# ---------------------------------------------------------------------------
# Helpers d'arrondi (identiques aux tests validés)
# ---------------------------------------------------------------------------

def _half_up(x) -> int:
    """Arrondi ROUND_HALF_UP à l'entier (GNF)."""
    return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _floor_gnf(x) -> int:
    """Arrondi ROUND_FLOOR à l'entier (GNF)."""
    return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_FLOOR))


# ---------------------------------------------------------------------------
# Barème RTS officiel Guinée – fallback intégré (6 tranches)
# Source : Code général des impôts (CGI) guinéen, art. relatifs à l'IRG/RTS
# Tranches : 0 %, 5 %, 8 %, 10 %, 15 %, 20 %
# ---------------------------------------------------------------------------

BAREME_CGI_REFERENCE = [
    {'borne_inf': 0,          'borne_sup': 1_000_000,  'taux': Decimal('0')},
    {'borne_inf': 1_000_000,  'borne_sup': 3_000_000,  'taux': Decimal('5')},
    {'borne_inf': 3_000_000,  'borne_sup': 5_000_000,  'taux': Decimal('8')},
    {'borne_inf': 5_000_000,  'borne_sup': 10_000_000, 'taux': Decimal('10')},
    {'borne_inf': 10_000_000, 'borne_sup': 20_000_000, 'taux': Decimal('15')},
    {'borne_inf': 20_000_000, 'borne_sup': None,        'taux': Decimal('20')},
]

# Label affiché pour le fallback
BAREME_CGI_LABEL = 'Barème RTS officiel Guinée 2022+ (0 %/5 %/8 %/10 %/15 %/20 %)'
BAREME_FALLBACK_ID = 'fallback'

# Version du barème pour traçabilité / reproductibilité
VERSION_BAREME = 'GN-2026-v1'


# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------

def _charger_tranches_db(annee: int, type_bareme: str = 'officiel') -> list:
    """
    Charge les tranches depuis la DB pour une (annee, type_bareme).
    Retourne [] si aucune tranche active trouvée.
    """
    qs = TrancheRTS.objects.filter(
        annee_validite=annee,
        type_bareme=type_bareme,
        actif=True,
    ).order_by('numero_tranche').values('borne_inferieure', 'borne_superieure', 'taux_irg')

    if not qs.exists():
        return []

    result = []
    for t in qs:
        result.append({
            'borne_inf': int(t['borne_inferieure']),
            'borne_sup': int(t['borne_superieure']) if t['borne_superieure'] is not None else None,
            'taux': Decimal(str(t['taux_irg'])),
        })
    return result


def _charger_constantes(date_reference=None) -> dict:
    """
    Charge les constantes fiscales actives.
    Complète avec des valeurs par défaut si absentes de la DB.
    """
    from .cache_service import PayrollCacheService

    constantes = dict(PayrollCacheService.get_constantes(
        date_reference=date_reference
    ))

    defaults = {
        'TAUX_CNSS_EMPLOYE':   Decimal('5'),
        'TAUX_CNSS_EMPLOYEUR': Decimal('18'),
        'PLAFOND_CNSS':        Decimal('2500000'),
        'PLANCHER_CNSS':       Decimal('550000'),
        'TAUX_VF':             Decimal('6'),
        'TAUX_TA':             Decimal('2'),
        'TAUX_ONFPP':          Decimal('1.5'),
        'SEUIL_TA_ONFPP':      Decimal('30'),
    }
    for k, v in defaults.items():
        constantes.setdefault(k, v)
    return constantes


def get_baremes_disponibles() -> list:
    """
    Retourne la liste des barèmes utilisables (DB + fallback intégré).
    Chaque entrée : {'id', 'label', 'annee', 'type'}.
    """
    from django.db.models import Count

    options = []
    groupes = (
        TrancheRTS.objects
        .filter(actif=True)
        .values('annee_validite', 'type_bareme')
        .annotate(nb=Count('id'))
        .order_by('-annee_validite', 'type_bareme')
    )

    type_labels = {'officiel': 'Officiel', 'simulation': 'Simulation', 'test': 'Test'}
    for g in groupes:
        annee = g['annee_validite']
        type_b = g['type_bareme']
        bid = f"{annee}-{type_b}"
        options.append({
            'id': bid,
            'label': f'Barème {annee} — {type_labels.get(type_b, type_b)} ({g["nb"]} tranches)',
            'annee': annee,
            'type': type_b,
        })

    # Toujours proposer le barème de référence intégré
    options.append({
        'id': BAREME_FALLBACK_ID,
        'label': BAREME_CGI_LABEL,
        'annee': None,
        'type': 'reference',
    })
    return options


# ---------------------------------------------------------------------------
# Moteur de calcul (un barème)
# ---------------------------------------------------------------------------

def _calcul_rts_par_tranches(base: Decimal, tranches: list) -> tuple:
    """
    Calcul progressif de la RTS par tranches.
    Retourne (total_rts: int, detail_tranches: list).

    Formule: pour chaque tranche [borne_inf, borne_sup) :
        base_tranche = min(base, borne_sup) - borne_inf  (si base > borne_inf)
        impot_tranche = base_tranche * taux / 100  (arrondi HALF_UP)
    """
    if base <= 0:
        return 0, []

    base = Decimal(str(base))
    impot_total = 0
    details = []

    for t in tranches:
        borne_inf = Decimal(str(t['borne_inf']))
        taux = Decimal(str(t['taux']))
        borne_sup = Decimal(str(t['borne_sup'])) if t['borne_sup'] is not None else None

        if base <= borne_inf:
            break

        plafond = min(base, borne_sup) if borne_sup is not None else base
        base_tranche = plafond - borne_inf
        impot_tranche = _half_up(base_tranche * taux / Decimal('100'))
        impot_total += impot_tranche

        details.append({
            'borne_inf': int(borne_inf),
            'borne_sup': int(borne_sup) if borne_sup is not None else None,
            'taux': float(taux),
            'base_tranche': _half_up(base_tranche),
            'impot_tranche': impot_tranche,
        })

    return impot_total, details


def calculer_un_bareme(
    brut: Decimal,
    total_indemnites: Decimal,
    tranches: list,
    constantes: dict,
    nb_salaries: int = 0,
) -> dict:
    """
    Calcule le bulletin complet pour un barème donné.

    Formule CGI Guinée (validée par tests T01–T17):
      CNSS   = half_up(assiette CNSS encadrée plancher/plafond × taux_cnss_emp / 100)
      plafond_exon = floor(brut × 25%)
      exon   = min(indemnites, plafond_exon)
      depasse = max(0, indemnites − plafond_exon)
      base_rts = brut − CNSS − exon
      RTS    = calcul progressif (ROUND_HALF_UP sur montants partiels)
      net    = brut − CNSS − RTS
      VF/TA/ONFPP = base VF × taux
    """
    brut = max(Decimal('0'), Decimal(str(brut)))
    total_indemnites = max(Decimal('0'), Decimal(str(total_indemnites)))

    # CNSS Guinee: parametres legaux fixes, sans surcharge flottante.
    plancher_cnss   = Decimal('550000')
    plafond_cnss    = Decimal('2500000')
    taux_cnss_emp   = Decimal('5')
    taux_cnss_pat   = Decimal('18')
    taux_vf         = constantes.get('TAUX_VF',             Decimal('6'))
    # Les taux TA et ONFPP sont FIXES par la loi guinéenne (non configurables)
    TAUX_TA_LEGAL    = Decimal('2')      # Taxe d'Apprentissage: 2% (loi)
    TAUX_ONFPP_LEGAL = Decimal('1.5')    # ONFPP: 1,5% (loi)

    seuil_minimum_cnss = plancher_cnss * Decimal('0.10')
    if brut < seuil_minimum_cnss:
        assiette_cnss = Decimal('0')
    else:
        assiette_cnss = max(min(brut, plafond_cnss), plancher_cnss)

    # -- CNSS employé --
    cnss = _half_up(assiette_cnss * taux_cnss_emp / Decimal('100'))

    # -- CNSS employeur --
    cnss_employeur = _half_up(assiette_cnss * taux_cnss_pat / Decimal('100'))

    # -- Plafond d'exonération indemnités = 25% brut (floor) --
    plafond_exon = _floor_gnf(brut * Decimal('25') / Decimal('100'))
    exon   = int(min(total_indemnites, Decimal(str(plafond_exon))))
    depasse = int(max(Decimal('0'), total_indemnites - Decimal(str(plafond_exon))))

    # -- Base RTS --
    # Le brut inclut deja toutes les indemnites. Soustraire l'exoneration
    # suffit : la fraction depassant 25 % reste donc taxable dans le brut.
    # Ajouter ``depasse`` ici la compterait une seconde fois.
    base_rts_raw = int(brut) - cnss - exon
    base_rts     = max(0, base_rts_raw)

    # -- RTS par tranches --
    rts, detail_tranches = _calcul_rts_par_tranches(Decimal(str(base_rts)), tranches)

    # -- Taux effectif --
    if base_rts > 0:
        taux_effectif = round(rts * 100 / base_rts, 2)
    else:
        taux_effectif = 0.0

    # -- Net --
    net = int(brut) - cnss - rts

    # -- Charges patronales --
    # L'exonération indemnitaire est réservée à la RTS.
    deduction_vf = 0
    base_vf = max(Decimal('0'), brut)
    vf = _half_up(base_vf * taux_vf / Decimal('100'))
    # Seuil TA/ONFPP : < seuil -> TA 2%, >= seuil -> ONFPP 1,5% sur base VF
    seuil_ta_onfpp = int(constantes.get('SEUIL_TA_ONFPP', Decimal('30')))
    if nb_salaries < seuil_ta_onfpp:
        ta    = _half_up(base_vf * TAUX_TA_LEGAL / Decimal('100'))
        onfpp = 0
        base_onfpp = Decimal('0')
    else:
        ta    = 0
        base_onfpp = brut
        onfpp = _half_up(base_onfpp * TAUX_ONFPP_LEGAL / Decimal('100'))

    return {
        'brut':                  int(brut),
        'total_indemnites':      int(total_indemnites),
        'cnss':                  cnss,
        'cnss_employeur':        cnss_employeur,
        'assiette_cnss':         int(assiette_cnss),
        'deduction_vf':          int(deduction_vf),
        'plafond_exon':          plafond_exon,
        'exon':                  exon,
        'depasse':               depasse,
        'base_rts':              base_rts,
        'rts':                   rts,
        'taux_effectif':         taux_effectif,
        'net':                   net,
        'vf':                    vf,
        'base_vf':               int(base_vf),
        'ta':                    ta,
        'onfpp':                 onfpp,
        'base_onfpp':            int(base_onfpp),
        'total_charges_pat':     cnss_employeur + vf + ta + onfpp,
        'detail_tranches':       detail_tranches,
    }


# ---------------------------------------------------------------------------
# Optimisation dynamique de la structuration (10-25%)
# ---------------------------------------------------------------------------

def optimiser_structure_dynamique(
    brut: int,
    tranches: list,
    constantes: dict,
    nb_salaries: int = 0,
    objectif: str = 'max_net',
    taux_max: int = 25,
) -> dict:
    """
    Teste toutes les répartitions d'indemnités de 0% à taux_max% (pas de 1%)
    et retourne la meilleure selon l'objectif.

    objectif:
        'max_net'         → maximise le net employé
        'min_cout'        → minimise le coût total employeur
    taux_max:
        Plafond personnalisable (défaut 25% = max CGI Guinée).
        Certaines entreprises imposent un plafond interne (ex: 20%).

    Retourne:
        best      : dict du meilleur scénario (résultat calculer_un_bareme enrichi)
        scenarios : liste de tous les scénarios testés
    """
    taux_max = max(0, min(25, int(taux_max)))  # Sécurité : borné à [0, 25]
    brut_d = Decimal(str(brut))
    best = None
    scenarios = []

    # Phase 1 : balayage 0% → taux_max%
    for taux_pct in range(0, taux_max + 1):
        indem = _half_up(brut_d * Decimal(str(taux_pct)) / Decimal('100'))
        result = calculer_un_bareme(brut_d, Decimal(str(indem)), tranches, constantes, nb_salaries)
        result['taux_indem_pct'] = taux_pct
        result['cout_total_employeur'] = result['brut'] + result['total_charges_pat']
        scenarios.append(result)

        if best is None:
            best = result
        elif objectif == 'max_net' and result['net'] > best['net']:
            best = result
        elif objectif == 'min_cout' and result['cout_total_employeur'] < best['cout_total_employeur']:
            best = result

    # Phase 2 : micro-ajustement autour du meilleur (pas de 0.5%)
    best_taux = best['taux_indem_pct']
    for delta in [-1.5, -1.0, -0.5, 0.5, 1.0, 1.5]:
        taux_fin = best_taux + delta
        if taux_fin < 0 or taux_fin > taux_max:
            continue
        indem = _half_up(brut_d * Decimal(str(taux_fin)) / Decimal('100'))
        result = calculer_un_bareme(brut_d, Decimal(str(indem)), tranches, constantes, nb_salaries)
        result['taux_indem_pct'] = taux_fin
        result['cout_total_employeur'] = result['brut'] + result['total_charges_pat']
        if objectif == 'max_net' and result['net'] > best['net']:
            best = result
        elif objectif == 'min_cout' and result['cout_total_employeur'] < best['cout_total_employeur']:
            best = result

    # Référence : scénario standard (0% indemnités)
    ref_standard = scenarios[0]  # taux_pct = 0

    # Détection gain sans surcoût
    cout_standard = ref_standard['cout_total_employeur']
    cout_optimal = best['cout_total_employeur']
    gain_net = best['net'] - ref_standard['net']
    gain_sans_surcout = (gain_net > 0 and abs(cout_optimal - cout_standard) == 0)
    gain_pct = round(gain_net * 100 / ref_standard['net'], 1) if ref_standard['net'] > 0 else 0

    return {
        'best': best,
        'scenarios': scenarios,
        'objectif': objectif,
        'ref_standard': ref_standard,
        'gain_net': gain_net,
        'gain_pct': gain_pct,
        'gain_sans_surcout': gain_sans_surcout,
    }


# ---------------------------------------------------------------------------
# Moteur multi-barèmes
# ---------------------------------------------------------------------------

def simuler_multi_baremes(
    brut,
    total_indemnites,
    baremes_ids: list,
    annee_ref: int = None,
    nb_salaries: int = 0,
) -> list:
    """
    Lance la simulation pour plusieurs barèmes et retourne les résultats comparatifs.

    baremes_ids: liste de strings "ANNEE-TYPE" (ex: "2026-officiel") ou "fallback".
    Retourne une liste de dicts enrichis avec bareme_id, bareme_label, etc.
    """
    if annee_ref is None:
        annee_ref = date.today().year

    brut             = Decimal(str(brut))
    total_indemnites = Decimal(str(max(0, total_indemnites)))
    resultats        = []
    type_labels      = {'officiel': 'Officiel', 'simulation': 'Simulation', 'test': 'Test'}

    for bid in baremes_ids:
        if bid == BAREME_FALLBACK_ID:
            tranches = list(BAREME_CGI_REFERENCE)
            label    = BAREME_CGI_LABEL
            annee    = None
            type_b   = 'reference'
        else:
            parts = bid.split('-', 1)
            try:
                annee  = int(parts[0])
                type_b = parts[1] if len(parts) > 1 else 'officiel'
            except (ValueError, IndexError):
                annee  = annee_ref
                type_b = 'officiel'

            tranches = _charger_tranches_db(annee, type_b)
            if not tranches:
                # Fallback : barème intégré si la DB ne contient rien
                tranches = list(BAREME_CGI_REFERENCE)
                label    = f'Barème {annee} {type_b} (fallback référence)'
            else:
                label = f'Barème {annee} — {type_labels.get(type_b, type_b)}'

        annee_constantes = annee if annee is not None else annee_ref
        constantes = _charger_constantes(date(annee_constantes, 1, 1))

        result = calculer_un_bareme(
            brut, total_indemnites, tranches, constantes, nb_salaries
        )
        result['bareme_id']      = bid
        result['bareme_label']   = label
        result['annee']          = annee
        result['type_bareme']    = type_b
        result['tranches_bareme'] = [
            {'borne_inf': t['borne_inf'], 'borne_sup': t['borne_sup'], 'taux': float(t['taux'])}
            for t in tranches
        ]
        resultats.append(result)

    return resultats


# ---------------------------------------------------------------------------
# Optimisation du net (aide à la décision)
# ---------------------------------------------------------------------------

def optimiser_net(
    enveloppe_totale,
    bareme_id: str = None,
    annee_ref: int = None,
    nb_salaries: int = 0,
) -> dict:
    """
    Trouve la répartition interne du brut total qui maximise le net à payer.

    Le brut fourni inclut les indemnités, comme ``calculer_un_bareme`` et le
    bulletin réel. Le montant brut reste donc constant entre les scénarios ;
    seule la part d'indemnités varie de 0 % à 25 % du brut.

    On compare aussi avec le scénario "tout en brut" (indemnités=0)
    et le scénario actuel si fourni.

    Retourne un dict avec scenarios[] et recommandation.
    """
    if annee_ref is None:
        annee_ref = date.today().year

    enveloppe = Decimal(str(enveloppe_totale))
    # Charger le barème
    if bareme_id and bareme_id != BAREME_FALLBACK_ID:
        parts = bareme_id.split('-', 1)
        try:
            annee = int(parts[0])
            type_b = parts[1] if len(parts) > 1 else 'officiel'
        except (ValueError, IndexError):
            annee = annee_ref
            type_b = 'officiel'
        tranches = _charger_tranches_db(annee, type_b)
        if not tranches:
            tranches = list(BAREME_CGI_REFERENCE)
    else:
        annee = annee_ref
        tranches = list(BAREME_CGI_REFERENCE)

    constantes = _charger_constantes(date(annee, 1, 1))

    # Scénario 1 : Tout en brut (indemnités = 0)
    r_brut_pur = calculer_un_bareme(enveloppe, Decimal('0'), tranches, constantes, nb_salaries)
    r_brut_pur['scenario'] = 'Tout en brut (0 indemnités)'
    r_brut_pur['conforme_25'] = True

    # Scénario 2 : Optimal 25% du brut total
    brut_optimal = int(enveloppe)
    indem_optimal = _floor_gnf(enveloppe * Decimal('25') / Decimal('100'))
    r_optimal = calculer_un_bareme(
        Decimal(str(brut_optimal)), Decimal(str(indem_optimal)),
        tranches, constantes, nb_salaries
    )
    r_optimal['scenario'] = 'Optimal (indemnités = 25% du brut)'
    r_optimal['conforme_25'] = True

    # Scénario 3 : 30% indemnités (au-delà du plafond, pour montrer l'effet)
    brut_30 = int(enveloppe)
    indem_30 = _floor_gnf(enveloppe * Decimal('30') / Decimal('100'))
    r_30 = calculer_un_bareme(
        Decimal(str(brut_30)), Decimal(str(indem_30)),
        tranches, constantes, nb_salaries
    )
    r_30['scenario'] = 'Indemnités 30% du brut (⚠ dépasse plafond CGI)'
    r_30['conforme_25'] = False

    scenarios = [r_brut_pur, r_optimal, r_30]

    # Trouver le meilleur net PARMI LES SCÉNARIOS CONFORMES (≤ 25%)
    conformes = [s for s in scenarios if s.get('conforme_25', True)]
    meilleur = max(conformes, key=lambda s: s['net'])
    economie_vs_brut_pur = meilleur['net'] - r_brut_pur['net']

    gain_mensuel = economie_vs_brut_pur
    gain_annuel = gain_mensuel * 12

    return {
        'enveloppe_totale': int(enveloppe),
        'scenarios': scenarios,
        'recommandation': {
            'scenario': meilleur['scenario'],
            'brut': meilleur['brut'],
            'indemnites': meilleur['total_indemnites'],
            'net': meilleur['net'],
            'rts': meilleur['rts'],
            'economie_rts': r_brut_pur['rts'] - meilleur['rts'],
            'gain_net': gain_mensuel,
            'gain_net_annuel': gain_annuel,
        },
        'meta': {
            'plafond_exoneration': 0.25,
            'plafond_cnss': int(constantes.get('PLAFOND_CNSS', 2500000)),
            'taux_cnss_employe': float(constantes.get('TAUX_CNSS_EMPLOYE', 5)),
            'taux_cnss_employeur': float(constantes.get('TAUX_CNSS_EMPLOYEUR', 18)),
            'regle': 'Indemnités exonérées dans la limite de 25% du brut (CGI Guinée)',
        },
    }


def simuler_scenario_augmentation(
    brut_actuel,
    indemnites_actuelles,
    pourcentage_augmentation: float,
    baremes_ids: list,
    annee_ref: int = None,
    nb_salaries: int = 0,
) -> dict:
    """
    Simule l'impact d'une augmentation (%) sur le brut.
    Compare avant/après sur chaque barème.
    """
    brut = Decimal(str(brut_actuel))
    indemnites = Decimal(str(indemnites_actuelles))
    pct = Decimal(str(pourcentage_augmentation))

    nouveau_brut = _half_up(brut * (Decimal('100') + pct) / Decimal('100'))
    nouvelles_indemnites = _half_up(indemnites * (Decimal('100') + pct) / Decimal('100'))

    avant = simuler_multi_baremes(brut, indemnites, baremes_ids, annee_ref, nb_salaries)
    apres = simuler_multi_baremes(
        Decimal(str(nouveau_brut)), Decimal(str(nouvelles_indemnites)),
        baremes_ids, annee_ref, nb_salaries
    )

    comparaison = []
    for a, b in zip(avant, apres):
        comparaison.append({
            'bareme_label': a['bareme_label'],
            'avant': {'brut': a['brut'], 'rts': a['rts'], 'net': a['net'],
                      'total_charges_pat': a['total_charges_pat']},
            'apres': {'brut': b['brut'], 'rts': b['rts'], 'net': b['net'],
                      'total_charges_pat': b['total_charges_pat']},
            'delta_brut': b['brut'] - a['brut'],
            'delta_rts': b['rts'] - a['rts'],
            'delta_net': b['net'] - a['net'],
            'delta_charges': b['total_charges_pat'] - a['total_charges_pat'],
            'cout_total_avant': a['brut'] + a['total_charges_pat'],
            'cout_total_apres': b['brut'] + b['total_charges_pat'],
        })

    if annee_ref is None:
        annee_ref = date.today().year
    constantes = _charger_constantes(date(annee_ref, 1, 1))
    return {
        'pourcentage': float(pct),
        'brut_actuel': int(brut),
        'nouveau_brut': nouveau_brut,
        'comparaison': comparaison,
        'meta': {
            'plafond_exoneration': 0.25,
            'plafond_cnss': int(constantes.get('PLAFOND_CNSS', 2500000)),
            'taux_cnss_employe': float(constantes.get('TAUX_CNSS_EMPLOYE', 5)),
            'taux_cnss_employeur': float(constantes.get('TAUX_CNSS_EMPLOYEUR', 18)),
        },
    }
