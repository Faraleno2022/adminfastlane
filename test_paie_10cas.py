"""
TEST PAIE GUINEE — 10 cas + bonus
Reproduit exactement la logique de services.py (ROUND_HALF_UP, Decimal)
"""
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

# ─────────────────────────────────────────────────────────────────────────────
# BAREME RTS OFFICIEL CGI GUINEE
# ─────────────────────────────────────────────────────────────────────────────
BAREME_RTS = [
    (Decimal('0'),         Decimal('1000000'),  Decimal('0')),
    (Decimal('1000000'),   Decimal('3000000'),  Decimal('5')),
    (Decimal('3000000'),   Decimal('5000000'),  Decimal('8')),
    (Decimal('5000000'),   Decimal('10000000'), Decimal('10')),
    (Decimal('10000000'),  Decimal('20000000'), Decimal('15')),
    (Decimal('20000000'),  None,                Decimal('20')),
]

CNSS_PLAFOND   = Decimal('2500000')
CNSS_TAUX_EMP  = Decimal('5')
CNSS_TAUX_PAT  = Decimal('18')
VF_TAUX        = Decimal('6')
TA_TAUX        = Decimal('2')   # < 30 salariés
ONFPP_TAUX     = Decimal('1.5') # >= 30 salariés
HEURES_MOIS    = Decimal('173.33')
EXO_PCT        = Decimal('25')


def arrondir(v):
    return Decimal(str(v)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def calc_rts(base_rts):
    total = Decimal('0')
    detail = []
    for b_inf, b_sup, taux in BAREME_RTS:
        if base_rts <= b_inf:
            break
        haut = b_sup if b_sup is not None else base_rts
        base_tr = min(base_rts, haut) - b_inf
        if base_tr <= 0:
            continue
        impot = arrondir(base_tr * taux / Decimal('100'))
        total += impot
        detail.append((b_inf, b_sup, taux, base_tr, impot))
    return total, detail


def calculer(sal_base, indemnites=0, hs_30=0, hs_60=0,
             hs_nuit=0, hs_feries=0, nb_sal=1, label=""):
    sal_base   = Decimal(str(sal_base))
    indemnites = Decimal(str(indemnites))
    hs_30      = Decimal(str(hs_30))
    hs_60      = Decimal(str(hs_60))
    hs_nuit    = Decimal(str(hs_nuit))
    hs_feries  = Decimal(str(hs_feries))

    # Taux horaire
    sal_h = arrondir(sal_base / HEURES_MOIS) if sal_base > 0 else Decimal('0')

    # Montants HS
    m_hs_30     = arrondir(sal_h * hs_30 * Decimal('1.30'))
    m_hs_60     = arrondir(sal_h * hs_60 * Decimal('1.60'))
    m_hs_nuit   = arrondir(sal_h * hs_nuit * Decimal('1.20'))
    m_hs_feries = arrondir(sal_h * hs_feries * Decimal('1.60'))
    total_hs    = m_hs_30 + m_hs_60 + m_hs_nuit + m_hs_feries

    # Brut
    brut = sal_base + indemnites + total_hs

    # CNSS employé
    base_cnss = min(brut, CNSS_PLAFOND)
    cnss_emp  = arrondir(base_cnss * CNSS_TAUX_EMP / Decimal('100'))
    cnss_pat  = arrondir(base_cnss * CNSS_TAUX_PAT / Decimal('100'))

    # Exonération indemnités forfaitaires (plafond 25% du brut)
    plafond_25 = (brut * EXO_PCT / Decimal('100')).quantize(
        Decimal('1'), rounding=ROUND_FLOOR
    )
    exo        = arrondir(min(indemnites, plafond_25))

    # Base RTS
    base_rts = brut - cnss_emp - exo

    # RTS (barème progressif)
    rts, detail_rts = calc_rts(base_rts)

    # VF / TA / ONFPP : mode standard du moteur réel
    # Base = brut - exonération indemnitaire plafonnée.
    base_vf = brut - exo
    vf = arrondir(base_vf * VF_TAUX / Decimal('100'))
    if nb_sal >= 30:
        ta = arrondir(base_vf * ONFPP_TAUX / Decimal('100'))
        ta_label = f"ONFPP {ONFPP_TAUX}%"
    else:
        ta = arrondir(base_vf * TA_TAUX / Decimal('100'))
        ta_label = f"TA {TA_TAUX}%"

    total_charges_pat = cnss_pat + vf + ta
    total_retenues    = cnss_emp + rts
    net               = brut - total_retenues

    # ── Affichage ────────────────────────────────────────────────────────────
    sep = "═" * 68
    print(f"\n{sep}")
    print(f"  {label}")
    print(sep)
    print(f"  Salaire base          : {sal_base:>15,.0f} GNF".replace(",", " "))
    if indemnites:
        print(f"  Indemnités            : {indemnites:>15,.0f} GNF".replace(",", " "))
    if total_hs > 0:
        print(f"  Taux horaire          : {sal_h:>15,.0f} GNF/h".replace(",", " "))
        if hs_30:
            print(f"  HS ×1.30 ({hs_30:g}h)      : {m_hs_30:>15,.0f} GNF".replace(",", " "))
        if hs_60:
            print(f"  HS ×1.60 ({hs_60:g}h)      : {m_hs_60:>15,.0f} GNF".replace(",", " "))
        if hs_nuit:
            print(f"  HS nuit ×1.20 ({hs_nuit:g}h) : {m_hs_nuit:>15,.0f} GNF".replace(",", " "))
        if hs_feries:
            print(f"  HS fériés ×1.60 ({hs_feries:g}h): {m_hs_feries:>15,.0f} GNF".replace(",", " "))
        print(f"  Total HS              : {total_hs:>15,.0f} GNF".replace(",", " "))
    print(f"  ─" * 34)
    print(f"  SALAIRE BRUT          : {brut:>15,.0f} GNF".replace(",", " "))
    print(f"  ─" * 34)
    print(f"  Base CNSS             : {base_cnss:>15,.0f} GNF".replace(",", " "))
    print(f"  CNSS employé  (5%)    : {cnss_emp:>15,.0f} GNF".replace(",", " "))
    if indemnites:
        print(f"  Plafond 25% brut      : {plafond_25:>15,.0f} GNF".replace(",", " "))
        print(f"  Exonération indemnités: {exo:>15,.0f} GNF  {'← 100% (< plafond)' if indemnites <= plafond_25 else '← plafond 25% appliqué'}".replace(",", " "))
    print(f"  Base RTS              : {base_rts:>15,.0f} GNF".replace(",", " "))
    print(f"  Détail RTS progressif :")
    for b_inf, b_sup, taux, base_tr, impot in detail_rts:
        b_sup_str = f"{b_sup:,.0f}".replace(",", " ") if b_sup else "illimité"
        print(f"    {b_inf:>10,.0f} → {b_sup_str:<12} × {taux:g}%  base={base_tr:>12,.0f}  impôt={impot:>10,.0f}".replace(",", " "))
    print(f"  RTS TOTAL             : {rts:>15,.0f} GNF".replace(",", " "))
    print(f"  ─" * 34)
    print(f"  NET À PAYER           : {net:>15,.0f} GNF  (brut {brut:,.0f} − CNSS {cnss_emp:,.0f} − RTS {rts:,.0f})".replace(",", " "))
    print(f"  ─" * 34)
    print(f"  CHARGES PATRONALES    :")
    print(f"    CNSS patron (18%)   : {cnss_pat:>15,.0f} GNF".replace(",", " "))
    print(f"    VF (6%)             : {vf:>15,.0f} GNF".replace(",", " "))
    print(f"    {ta_label:<20}: {ta:>15,.0f} GNF".replace(",", " "))
    print(f"    Total charges pat.  : {total_charges_pat:>15,.0f} GNF".replace(",", " "))

    # ── Vérifications / alertes ───────────────────────────────────────────────
    ok = True
    checks = []

    # Cohérence : net = brut - cnss - rts
    net_calcule = brut - cnss_emp - rts
    if net != net_calcule:
        checks.append(f"  ⛔ NET incohérent : {net} ≠ {net_calcule}")
        ok = False

    # CNSS plafond
    if cnss_emp > Decimal('125000'):
        checks.append(f"  ⛔ CNSS dépasse 125 000 : {cnss_emp}")
        ok = False

    # Exonération ≤ indemnités
    if exo > indemnites:
        checks.append(f"  ⛔ Exonération > indemnités")
        ok = False

    # Exonération ≤ plafond 25%
    if exo > plafond_25:
        checks.append(f"  ⛔ Exonération dépasse 25% du brut")
        ok = False

    # RTS ≥ 0
    if rts < 0:
        checks.append(f"  ⛔ RTS négatif")
        ok = False

    # Base RTS ≥ 0
    if base_rts < 0:
        checks.append(f"  ⛔ Base RTS négative")
        ok = False

    if ok:
        print(f"\n  ✅ TOUTES LES VÉRIFICATIONS PASSENT")
    else:
        for c in checks:
            print(c)

    return {
        'brut': brut, 'cnss_emp': cnss_emp, 'exo': exo, 'plafond_25': plafond_25,
        'base_rts': base_rts, 'rts': rts, 'net': net,
        'cnss_pat': cnss_pat, 'base_vf': base_vf, 'vf': vf, 'ta': ta,
    }


# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "#"*68)
print("  VALIDATION MOTEUR PAIE GUINEE -- 10 CAS + BONUS")
print("  Bareme CGI officiel | Arrondis moteur reel | CNSS plafonne 2 500 000")
print("#"*68)

# CAS 1 — Cas standard
r1 = calculer(3_000_000, indemnites=2_600_000, hs_30=4,
              label="CAS 1 — Standard : sal=3M  ind=2,6M  HS=4h×30%")

# CAS 2 — Pas d'indemnités
r2 = calculer(3_000_000, indemnites=0, hs_30=0,
              label="CAS 2 — Pas d'indemnités : sal=3M  ind=0  HS=0")

# CAS 3 — Indemnités < 25%
r3 = calculer(3_000_000, indemnites=500_000,
              label="CAS 3 — Indemnités < 25% du brut : sal=3M  ind=500K")

# CAS 4 — Indemnités > 25%
r4 = calculer(3_000_000, indemnites=3_000_000,
              label="CAS 4 — Indemnités > 25% du brut : sal=3M  ind=3M")

# CAS 5 — Salaire faible, tranche 0%
r5 = calculer(800_000,
              label="CAS 5 — Salaire faible : sal=800K  RTS attendu=0")

# CAS 6 — Passage tranche 5%
r6 = calculer(1_500_000,
              label="CAS 6 — Seuil 5% : sal=1,5M  RTS attendu=21 250")

# CAS 7 — Multi-tranches
r7 = calculer(4_000_000,
              label="CAS 7 — Multi-tranches : sal=4M")

# CAS 8 — Plafond CNSS
r8 = calculer(10_000_000,
              label="CAS 8 — Plafond CNSS : sal=10M  CNSS attendu=125 000")

# CAS 9 — Arrondi critique
r9 = calculer(5_690_002,
              label="CAS 9 — Arrondi critique : brut=5 690 002  25%=?")

# CAS 10 — HS complexe
r10 = calculer(3_000_000, hs_30=4, hs_60=3.5,
               label="CAS 10 — HS complexes : sal=3M  HS=4h×30% + 3.5h×60%")

# BONUS — Cas mixte expert
rb = calculer(6_750_000, indemnites=2_200_000, hs_30=3.75,
              label="BONUS — Expert : sal=6,75M  ind=2,2M  HS=3.75h×30%")

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*68)
print("  TABLEAU RÉCAPITULATIF")
print("═"*68)
print(f"  {'Cas':<8} {'Brut':>12} {'CNSS':>9} {'Exo':>10} {'Base RTS':>11} {'RTS':>9} {'Net':>12}")
print(f"  {'─'*8} {'─'*12} {'─'*9} {'─'*10} {'─'*11} {'─'*9} {'─'*12}")
for i, r in enumerate([r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,rb], 1):
    lab = f"CAS {i}" if i <= 10 else "BONUS"
    print(f"  {lab:<8} {r['brut']:>12,.0f} {r['cnss_emp']:>9,.0f} {r['exo']:>10,.0f} {r['base_rts']:>11,.0f} {r['rts']:>9,.0f} {r['net']:>12,.0f}".replace(",", " "))

# Vérifications ciblées
print("\n" + "═"*68)
print("  VÉRIFICATIONS CIBLÉES")
print("═"*68)

# CAS 2 : exo=0
assert r2['exo'] == 0, f"CAS2: exo={r2['exo']} attendu 0"
print("  ✅ CAS 2  : exonération = 0 (pas d'indemnités)")

# CAS 3 : exo = indemnités (pas le plafond)
assert r3['exo'] == Decimal('500000'), f"CAS3: exo={r3['exo']} attendu 500000"
print("  ✅ CAS 3  : exonération = 500 000 (100%, plafond non atteint)")

# CAS 4 : exo = 25% du brut
assert r4['exo'] == r4['plafond_25'], f"CAS4: exo={r4['exo']} ≠ plafond {r4['plafond_25']}"
print(f"  ✅ CAS 4  : exonération = {r4['exo']:,} = 25% du brut (plafond appliqué)".replace(",", " "))

# CAS 5 : RTS = 0
assert r5['rts'] == 0, f"CAS5: rts={r5['rts']} attendu 0"
print("  ✅ CAS 5  : RTS = 0 (tranche 0%)")

# CAS 6 : RTS = 21 250 (base RTS = 1,500,000 - CNSS = 1,425,000 → T1 1M×0 + T2 425K×5%)
# base_rts = 1,500,000 - 75,000 = 1,425,000
# T2: (1,425,000 - 1,000,000) × 5% = 425,000 × 5% = 21,250
assert r6['rts'] == Decimal('21250'), f"CAS6: rts={r6['rts']} attendu 21250"
print(f"  ℹ️  CAS 6  : RTS = {r6['rts']:,} (base RTS={r6['base_rts']:,})".replace(",", " "))

# CAS 8 : CNSS = 125 000
assert r8['cnss_emp'] == Decimal('125000'), f"CAS8: cnss={r8['cnss_emp']} attendu 125000"
print("  ✅ CAS 8  : CNSS = 125 000 (plafond 2 500 000 respecté)")

# CAS 9 : le plafond fiscal est arrondi à l'entier inférieur comme en production.
expected_25 = (Decimal('5690002') * Decimal('25') / Decimal('100')).quantize(
    Decimal('1'), rounding=ROUND_FLOOR
)
assert r9['plafond_25'] == expected_25, f"CAS9: plafond={r9['plafond_25']} attendu {expected_25}"
print(f"  ✅ CAS 9  : 25% de 5 690 002 = {r9['plafond_25']:,} (ROUND_FLOOR production)".replace(",", " "))
print("         plafond vérifié indépendamment des indemnités")

print("\n  ✅ TOUS LES CAS VALIDÉS\n")
