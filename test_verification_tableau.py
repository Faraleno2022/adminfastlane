"""
Vérification des calculs de paie avec les salaires du tableau Page 1.
Formules corrigées:
  - Base RTS = Imposable (soumis_irg) - CNSS 5%
  - RTS = barème progressif 6 tranches
  - VF = (Brut - exonération indemnités forfaitaires plafonnée 25%) × 6%
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR

def arrondir(val):
    return val.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

def calculer_cnss(brut, plancher=Decimal('550000'), plafond=Decimal('2500000')):
    base = max(min(brut, plafond), plancher)
    cnss_emp = arrondir(base * Decimal('5') / Decimal('100'))
    cnss_pat = arrondir(base * Decimal('18') / Decimal('100'))
    return cnss_emp, cnss_pat, base

def calculer_base_rts(imposable, cnss_emp):
    """Base RTS = Imposable - CNSS employé (pas d'abattement, pas de déductions familiales)"""
    return imposable - cnss_emp

def calculer_rts_progressif(base):
    """Barème RTS progressif 6 tranches - CGI 2022"""
    tranches = [
        (Decimal('0'),        Decimal('1000000'),  Decimal('0')),
        (Decimal('1000000'),  Decimal('3000000'),  Decimal('5')),
        (Decimal('3000000'),  Decimal('5000000'),  Decimal('8')),
        (Decimal('5000000'),  Decimal('10000000'), Decimal('10')),
        (Decimal('10000000'), Decimal('20000000'), Decimal('15')),
        (Decimal('20000000'), None,                Decimal('20')),
    ]
    total = Decimal('0')
    details = []
    for bi, bs, taux in tranches:
        if base <= bi:
            details.append((bi, bs, taux, Decimal('0'), Decimal('0')))
            continue
        montant = (min(base, bs) - bi) if bs else (base - bi)
        if montant > 0:
            impot = arrondir(montant * taux / Decimal('100'))
            total += impot
            details.append((bi, bs, taux, montant, impot))
        else:
            details.append((bi, bs, taux, Decimal('0'), Decimal('0')))
    return arrondir(total), details

def calculer_vf(brut, indemnites_forfaitaires=Decimal('0'), taux=Decimal('6')):
    """VF = Base VF × 6%.

    Base VF = Brut - exonération des indemnités forfaitaires, plafonnée à 25%
    du brut (mode par défaut 'brut_moins_deduction' de paie/services.py).
    Le plafond est arrondi ROUND_FLOOR comme en production.
    """
    plafond = (brut * Decimal('25') / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_FLOOR)
    exoneration = min(indemnites_forfaitaires, plafond)
    base_vf = brut - exoneration
    vf = arrondir(base_vf * taux / Decimal('100'))
    return vf, exoneration, base_vf

def calculer_onfpp(brut, taux=Decimal('1.5')):
    return arrondir(brut * taux / Decimal('100'))

def calculer_ta(brut, taux=Decimal('1.5')):
    return arrondir(brut * taux / Decimal('100'))

# ============================================================
# DONNÉES DU TABLEAU - Page 1
# Salaire Base + Primes lues depuis l'image
# Imposable = Salaire Base (les primes ont soumis_irg=False)
# ============================================================
employes = [
    {
        'nom': 'Employé 1 (Bulletin 2)',
        'salaire_base': Decimal('10125000'),
        'transport': Decimal('875000'),
        'logement': Decimal('1500000'),
        'cherte': Decimal('1000000'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 2',
        'salaire_base': Decimal('9875000'),
        'transport': Decimal('910000'),
        'logement': Decimal('1000000'),
        'cherte': Decimal('852000'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 3',
        'salaire_base': Decimal('2400000'),
        'transport': Decimal('210000'),
        'logement': Decimal('200000'),
        'cherte': Decimal('387520'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 4',
        'salaire_base': Decimal('3855428'),
        'transport': Decimal('350000'),
        'logement': Decimal('400000'),
        'cherte': Decimal('344406'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 5',
        'salaire_base': Decimal('2013158'),
        'transport': Decimal('210000'),
        'logement': Decimal('225000'),
        'cherte': Decimal('200270'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 6',
        'salaire_base': Decimal('2780256'),
        'transport': Decimal('230000'),
        'logement': Decimal('240000'),
        'cherte': Decimal('0'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 7',
        'salaire_base': Decimal('1525196'),
        'transport': Decimal('150000'),
        'logement': Decimal('200000'),
        'cherte': Decimal('150000'),
        'autres': Decimal('0'),
    },
    {
        'nom': 'Employé 8',
        'salaire_base': Decimal('1050042'),
        'transport': Decimal('110000'),
        'logement': Decimal('121000'),
        'cherte': Decimal('0'),
        'autres': Decimal('283695'),
    },
]


def main():
    print("=" * 130)
    print("VÉRIFICATION CALCULS PAIE - DONNÉES DU TABLEAU PAGE 1")
    print("=" * 130)
    
    # En-tête du tableau de résultats
    print(f"\n{'Employé':<30} {'SBase':>12} {'Brut':>12} {'CNSS5%':>10} {'CNSS18%':>10} "
          f"{'BaseRTS':>12} {'RTS':>10} {'Net':>12} {'VF':>10} {'ONFPP':>10}")
    print("-" * 130)
    
    for emp in employes:
        sb = emp['salaire_base']
        brut = sb + emp['transport'] + emp['logement'] + emp['cherte'] + emp['autres']
        
        # CNSS
        cnss_emp, cnss_pat, base_cnss = calculer_cnss(brut)
        
        # Imposable = salaire_base (les primes sont soumis_irg=False)
        imposable = sb
        
        # Base RTS = Imposable - CNSS employé
        base_rts = calculer_base_rts(imposable, cnss_emp)
        
        # RTS progressif
        rts, details = calculer_rts_progressif(base_rts)
        
        # Net = Brut - CNSS - RTS
        net = brut - cnss_emp - rts

        # VF — indemnités forfaitaires = primes non imposables (transport, logement, cherté, autres)
        indemnites = emp['transport'] + emp['logement'] + emp['cherte'] + emp['autres']
        vf, ded_vf, base_vf = calculer_vf(brut, indemnites)

        # ONFPP
        onfpp = calculer_onfpp(brut)
        
        print(f"{emp['nom']:<30} {sb:>12,.0f} {brut:>12,.0f} {cnss_emp:>10,.0f} {cnss_pat:>10,.0f} "
              f"{base_rts:>12,.0f} {rts:>10,.0f} {net:>12,.0f} {vf:>10,.0f} {onfpp:>10,.0f}")
    
    # Détails par employé
    print("\n\n" + "=" * 130)
    print("DÉTAIL DES TRANCHES RTS PAR EMPLOYÉ")
    print("=" * 130)
    
    for emp in employes:
        sb = emp['salaire_base']
        brut = sb + emp['transport'] + emp['logement'] + emp['cherte'] + emp['autres']
        cnss_emp, _, _ = calculer_cnss(brut)
        base_rts = calculer_base_rts(sb, cnss_emp)
        rts, details = calculer_rts_progressif(base_rts)
        indemnites = emp['transport'] + emp['logement'] + emp['cherte'] + emp['autres']
        vf, ded_vf, base_vf = calculer_vf(brut, indemnites)
        
        print(f"\n--- {emp['nom']} | SBase: {sb:,.0f} | Brut: {brut:,.0f} ---")
        print(f"  CNSS 5% = min({brut:,.0f}, 2,500,000) × 5% = {cnss_emp:,.0f}")
        print(f"  Base RTS = {sb:,.0f} - {cnss_emp:,.0f} = {base_rts:,.0f}")
        
        print(f"  Tranches RTS:")
        for bi, bs, taux, montant, impot in details:
            bs_str = f"{bs:,.0f}" if bs else "∞"
            if montant > 0:
                print(f"    {bi:>12,.0f} - {bs_str:>12}: {montant:>12,.0f} × {taux:>2}% = {impot:>10,.0f}")
        print(f"  RTS TOTAL = {rts:,.0f}")
        
        taux_eff = arrondir(rts * Decimal('100') / base_rts) if base_rts > 0 else Decimal('0')
        print(f"  Taux effectif: {taux_eff}%")
        
        plafond_25 = (brut * Decimal('25') / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_FLOOR)
        print(f"  VF: exonération indemnités = min({indemnites:,.0f}, 25%×{brut:,.0f}={plafond_25:,.0f}) = {ded_vf:,.0f}")
        print(f"       base VF = {brut:,.0f} - {ded_vf:,.0f} = {base_vf:,.0f}")
        print(f"       VF = {base_vf:,.0f} × 6% = {vf:,.0f}")
        
        net = brut - cnss_emp - rts
        print(f"  Net = {brut:,.0f} - {cnss_emp:,.0f} - {rts:,.0f} = {net:,.0f}")


if __name__ == '__main__':
    main()
