"""
Service calcul Solde de Tout Compte - Fin de CDD
Conforme au Code du Travail de la République de Guinée
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from dateutil.relativedelta import relativedelta


def calculer_solde_tout_compte(contrat, date_fin_effective=None):
    """
    Calcule les indemnités de fin de CDD.

    Éléments calculés :
    - Indemnité de fin de CDD (7% du salaire brut total perçu)
    - Indemnité compensatrice de congés non pris (2,5 j/mois)

    Args:
        contrat: Instance du modèle Contrat
        date_fin_effective: date de fin effective (écrase contrat.date_fin si fournie)

    Returns:
        dict avec le détail complet du calcul
    """
    emp = contrat.employe
    date_fin = date_fin_effective or contrat.date_fin or date.today()
    date_debut = contrat.date_debut

    # === 1. DURÉE DU CONTRAT ===
    delta = relativedelta(date_fin, date_debut)
    mois_complets = max(delta.years * 12 + delta.months, 0)
    duree_mois = (
        Decimal(str(mois_complets)) + Decimal(str(max(delta.days, 0))) / Decimal('30')
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    duree_jours = max((date_fin - date_debut).days, 0)
    duree_annees = round(duree_jours / 365, 2)

    # === 2. SALAIRE MENSUEL DE RÉFÉRENCE ===
    salaire_mensuel = Decimal('0')

    bulletins_valides = None
    # Priorité 1 : bulletins validés ou payés compris dans le contrat
    try:
        from paie.models import BulletinPaie
        bulletins_valides = BulletinPaie.objects.filter(
            employe=emp,
            statut_bulletin__in=['valide', 'paye'],
            periode__date_fin__gte=date_debut,
            periode__date_debut__lte=date_fin,
        ).order_by('annee_paie', 'mois_paie')
        dernier_bulletin = bulletins_valides.last()
        if dernier_bulletin and dernier_bulletin.salaire_brut:
            salaire_mensuel = Decimal(str(dernier_bulletin.salaire_brut))
    except Exception:
        pass

    # Priorité 2 : salaire de base du contrat
    if salaire_mensuel == 0 and contrat.salaire_base:
        salaire_mensuel = Decimal(str(contrat.salaire_base))

    # Salaire journalier = salaire mensuel / 30 (méthode du manuel de paie projet
    # et de calculer_indemnite_conges) — diviseur harmonisé à 30.
    salaire_journalier = (salaire_mensuel / 30).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP
    ) if salaire_mensuel else Decimal('0')

    # === 3. INDEMNITÉ DE FIN DE CDD ===
    # Art. Code du Travail guinéen : 7% de la rémunération totale brute perçue
    if bulletins_valides is not None and bulletins_valides.exists():
        from django.db.models import Sum
        remuneration_totale = (
            bulletins_valides.aggregate(total=Sum('salaire_brut'))['total'] or Decimal('0')
        )
    else:
        # Estimation proratisée lorsqu'aucun bulletin validé n'est disponible.
        remuneration_totale = salaire_mensuel * duree_mois
    indemnite_fin_cdd = (remuneration_totale * Decimal('0.07')).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP
    )

    # === 4. INDEMNITÉ COMPENSATRICE DE CONGÉS NON PRIS ===
    conges_acquis = Decimal('2.5') * duree_mois
    conges_pris = Decimal('0')
    conges_restants = Decimal('0')

    try:
        from temps_travail.models import SoldeConge
        solde = SoldeConge.objects.filter(
            employe=emp,
            annee=date_fin.year
        ).first()
        if solde:
            conges_acquis = Decimal(str(solde.conges_acquis or conges_acquis))
            conges_pris = Decimal(str(solde.conges_pris or 0))
            conges_restants = max(
                Decimal(str(getattr(solde, 'conges_restants', 0) or 0)),
                conges_acquis - conges_pris
            )
        else:
            conges_restants = conges_acquis - conges_pris
    except Exception:
        conges_restants = conges_acquis - conges_pris

    indemnite_conges = (conges_restants * salaire_journalier).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP
    )

    # === 5. TOTAUX ===
    total_brut = indemnite_fin_cdd + indemnite_conges
    # Utiliser la même assiette encadrée et le même taux que le moteur de paie.
    try:
        from paie.models import Constante
        constantes = dict(Constante.objects.filter(
            code__in=['PLANCHER_CNSS', 'PLAFOND_CNSS', 'TAUX_CNSS_EMPLOYE'],
            actif=True,
        ).values_list('code', 'valeur'))
    except Exception:
        constantes = {}
    plancher_cnss = Decimal(str(constantes.get('PLANCHER_CNSS', Decimal('550000'))))
    plafond_cnss = Decimal(str(constantes.get('PLAFOND_CNSS', Decimal('2500000'))))
    taux_cnss = Decimal(str(constantes.get('TAUX_CNSS_EMPLOYE', Decimal('5'))))
    seuil_minimum = plancher_cnss * Decimal('0.10')
    if total_brut < seuil_minimum:
        base_cnss = Decimal('0')
    else:
        base_cnss = max(min(total_brut, plafond_cnss), plancher_cnss)
    cnss_employe = (base_cnss * taux_cnss / Decimal('100')).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP
    )
    net_a_payer = total_brut - cnss_employe

    return {
        'employe': emp,
        'contrat': contrat,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'duree_mois': duree_mois,
        'duree_annees': duree_annees,
        'salaire_mensuel': salaire_mensuel,
        'salaire_journalier': salaire_journalier,
        'remuneration_totale': remuneration_totale,
        # Indemnité fin CDD
        'indemnite_fin_cdd': indemnite_fin_cdd,
        'taux_fin_cdd': Decimal('7'),
        # Congés
        'conges_acquis': conges_acquis,
        'conges_pris': conges_pris,
        'conges_restants': conges_restants,
        'indemnite_conges': indemnite_conges,
        # Totaux
        'total_brut': total_brut,
        'base_cnss': base_cnss,
        'cnss_employe': cnss_employe,
        'net_a_payer': net_a_payer,
    }
