"""
Utilitaires de paie - Génération PDF de bulletins
"""
import io
import os
from decimal import Decimal


def _generer_qr_code(contenu, taille_cm=2.0):
    """Génère un QR code ReportLab-compatible depuis un texte."""
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(contenu)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os as _os


def _to_date(value):
    if not value:
        return None
    if hasattr(value, "date"):
        return value.date()
    return value


def date_reference_bulletin(bulletin):
    """Date utilisee pour afficher l'anciennete sur le bulletin."""
    date_calcul = _to_date(getattr(bulletin, "date_calcul", None))
    if date_calcul:
        return date_calcul

    periode = getattr(bulletin, "periode", None)
    date_fin = _to_date(getattr(periode, "date_fin", None))
    if date_fin:
        return date_fin

    try:
        from calendar import monthrange
        from datetime import date as date_cls
        dernier_jour = monthrange(bulletin.annee_paie, bulletin.mois_paie)[1]
        return date_cls(bulletin.annee_paie, bulletin.mois_paie, dernier_jour)
    except Exception:
        return None


def format_anciennete_bulletin(emp, bulletin):
    """Formate l'anciennete en annees, mois complets et jours."""
    date_embauche = _to_date(getattr(emp, "date_embauche", None))
    ref_date = date_reference_bulletin(bulletin)
    if not date_embauche or not ref_date:
        return "-"
    if ref_date < date_embauche:
        return "0 jour"

    from dateutil.relativedelta import relativedelta
    rd = relativedelta(ref_date, date_embauche)
    parts = []
    if rd.years:
        parts.append(f"{rd.years} an{'s' if rd.years > 1 else ''}")
    if rd.months:
        parts.append(f"{rd.months} mois")
    if rd.days:
        parts.append(f"{rd.days} jour{'s' if rd.days > 1 else ''}")
    if not parts:
        return "0 jour"
    if len(parts) == 1:
        return parts[0]
    return f"{' '.join(parts[:-1])} et {parts[-1]}"


# Enregistrer Arial avec support UTF-8/accents, avec fallback ReportLab fiable.
_FONT_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'static', 'fonts')
_FONT_NORMAL = 'Helvetica'
_FONT_BOLD = 'Helvetica-Bold'
_FONT_ITALIC = 'Helvetica-Oblique'

try:
    arial_regular = _os.path.join(_FONT_DIR, 'Arial.ttf')
    arial_bold = _os.path.join(_FONT_DIR, 'Arial-Bold.ttf')
    arial_italic = _os.path.join(_FONT_DIR, 'Arial-Italic.ttf')

    if all(_os.path.exists(path) for path in (arial_regular, arial_bold, arial_italic)):
        pdfmetrics.registerFont(TTFont('Arial', arial_regular))
        pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold))
        pdfmetrics.registerFont(TTFont('Arial-Italic', arial_italic))
        _FONT_NORMAL = 'Arial'
        _FONT_BOLD = 'Arial-Bold'
        _FONT_ITALIC = 'Arial-Italic'
except Exception:
    pass
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from django.utils import timezone


def calculer_detail_tranches_rts(base_rts):
    """
    Calcule le détail progressif RTS par tranche à partir de la base imposable.
    Barème CGI 2022 (6 tranches).
    
    Returns:
        list of dict avec clés: borne_inf, borne_sup, taux, base_tranche, impot_tranche
    """
    from decimal import ROUND_HALF_UP
    
    base_rts = Decimal(str(base_rts or 0))
    if base_rts <= 0:
        return []
    
    # Charger les tranches depuis la BDD si possible
    tranches_db = []
    try:
        from .models import TrancheRTS
        annee = timezone.now().year
        tranches_db = list(TrancheRTS.objects.filter(
            annee_validite=annee, actif=True
        ).order_by('numero_tranche').values(
            'borne_inferieure', 'borne_superieure', 'taux_irg'
        ))
        if not tranches_db:
            tranches_db = list(TrancheRTS.objects.filter(
                actif=True
            ).order_by('-annee_validite', 'numero_tranche'))
            if tranches_db:
                annee_found = tranches_db[0].get('annee_validite') if isinstance(tranches_db[0], dict) else tranches_db[0].annee_validite
                tranches_db = list(TrancheRTS.objects.filter(
                    annee_validite=annee_found, actif=True
                ).order_by('numero_tranche').values(
                    'borne_inferieure', 'borne_superieure', 'taux_irg'
                ))
    except Exception:
        tranches_db = []
    
    # Fallback: barème CGI 2022
    if not tranches_db:
        tranches_db = [
            {'borne_inferieure': Decimal('0'), 'borne_superieure': Decimal('1000000'), 'taux_irg': Decimal('0')},
            {'borne_inferieure': Decimal('1000000'), 'borne_superieure': Decimal('3000000'), 'taux_irg': Decimal('5')},
            {'borne_inferieure': Decimal('3000000'), 'borne_superieure': Decimal('5000000'), 'taux_irg': Decimal('8')},
            {'borne_inferieure': Decimal('5000000'), 'borne_superieure': Decimal('10000000'), 'taux_irg': Decimal('10')},
            {'borne_inferieure': Decimal('10000000'), 'borne_superieure': Decimal('20000000'), 'taux_irg': Decimal('15')},
            {'borne_inferieure': Decimal('20000000'), 'borne_superieure': None, 'taux_irg': Decimal('20')},
        ]
    
    # Normaliser les bornes (éliminer les gaps de 1 GNF)
    seuils = []
    for i, t in enumerate(tranches_db):
        b_inf = Decimal(str(t['borne_inferieure']))
        b_sup = t.get('borne_superieure')
        taux = Decimal(str(t['taux_irg']))
        if i > 0 and seuils:
            prev_sup = seuils[-1][1]
            if prev_sup is not None and b_inf > prev_sup and b_inf <= prev_sup + 2:
                b_inf = prev_sup
        if b_sup is not None:
            b_sup = Decimal(str(b_sup))
        seuils.append((b_inf, b_sup, taux))
    
    # Calcul progressif
    detail = []
    for b_inf, b_sup, taux in seuils:
        if base_rts <= b_inf:
            break
        if b_sup is not None:
            base_tranche = min(base_rts, b_sup) - b_inf
        else:
            base_tranche = base_rts - b_inf
        if base_tranche <= 0:
            continue
        impot = (base_tranche * taux / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        detail.append({
            'borne_inf': b_inf,
            'borne_sup': b_sup,
            'taux': taux,
            'base_tranche': base_tranche,
            'impot_tranche': impot,
        })
    
    return detail


def _dessiner_footer(p, width, margin_left, margin_right, entreprise, emp, bulletin):
    """Dessine le pied de page (signatures, infos légales, badge, QR) — positions absolues.
    Layout :
        L'Employeur (gauche)           L'Employé(e) (droite)    ← 2.15cm
        Nom entreprise                 Nom employé               ← 1.93cm
        Date et signature              Lu et approuvé...         ← 1.74cm
        - - - - - - -                  - - - - - - -             ← 1.67cm
        ─────────────────────────────────────────────            ← 1.60cm
           Infos entreprise centrées                             ← 1.45cm
           NIF — CNSS                                            ← 1.30cm
           Document généré le ...                                ← 1.15cm
        ✓ Conforme CGI ...                        [QR Code]     ← 0.78cm / 0.30cm
    """
    from reportlab.lib.units import cm

    # ── Signatures (angles gauche / droit) ──
    p.setFont(_FONT_BOLD, 6)
    p.setFillColor(colors.black)
    p.drawString(margin_left, 2.15*cm, "L'Employeur")
    p.drawRightString(width - margin_right, 2.15*cm, "L'Employé(e)")
    p.setFont(_FONT_NORMAL, 5.5)
    if entreprise:
        p.drawString(margin_left, 1.93*cm, entreprise.nom_entreprise or '')
    p.drawRightString(width - margin_right, 1.93*cm, f"{emp.nom} {emp.prenoms}")
    p.setFont(_FONT_NORMAL, 5)
    p.drawString(margin_left, 1.74*cm, "Date et signature")
    p.drawRightString(width - margin_right, 1.74*cm, "Lu et approuvé, date et signature")
    # Lignes pointillées
    p.setDash(2, 2)
    p.line(margin_left, 1.67*cm, 6.5*cm, 1.67*cm)
    p.line(width - 6.5*cm, 1.67*cm, width - margin_right, 1.67*cm)
    p.setDash()
    # Trait séparateur sous les signatures
    p.setStrokeColor(colors.HexColor("#dee2e6"))
    p.setLineWidth(0.5)
    p.line(margin_left, 1.60*cm, width - margin_right, 1.60*cm)
    p.setStrokeColor(colors.black)
    # Infos légales centrées
    p.setFont(_FONT_NORMAL, 5)
    p.setFillColor(colors.HexColor("#555555"))
    if entreprise:
        p.drawCentredString(width/2, 1.45*cm,
            f"{entreprise.nom_entreprise} — {entreprise.adresse or ''} — Tél: {entreprise.telephone or ''}")
        p.drawCentredString(width/2, 1.30*cm,
            f"NIF: {entreprise.nif or '-'} — CNSS: {entreprise.num_cnss or '-'}")
    from django.utils import timezone
    p.drawCentredString(width/2, 1.15*cm,
        f"Document généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')}")

    # Badge conformité
    badge_x = margin_left
    badge_y = 0.78*cm
    badge_w = 5.5*cm
    badge_h = 0.40*cm
    p.setFillColor(colors.HexColor("#198754"))
    p.roundRect(badge_x, badge_y, badge_w, badge_h, 3, stroke=0, fill=1)
    p.setFillColor(colors.white)
    p.setFont(_FONT_BOLD, 5.5)
    p.drawCentredString(badge_x + badge_w / 2, badge_y + 0.12*cm,
                        "\u2713 Conforme CGI Guinee | Compatible CNSS")

    # QR Code (coin bas droit)
    qr_size = 1.4*cm
    qr_x = width - margin_right - qr_size
    qr_y = 0.30*cm
    try:
        qr_contenu = (
            f"BUL:{bulletin.numero_bulletin}|"
            f"EMP:{emp.nom} {emp.prenoms}|"
            f"NET:{int(bulletin.net_a_payer)} GNF|"
            f"DATE:{bulletin.date_bulletin.strftime('%d/%m/%Y') if bulletin.date_bulletin else ''}|"
            f"CNSS:{emp.num_cnss_individuel or '-'}"
        )
        qr_img = _generer_qr_code(qr_contenu, taille_cm=qr_size / cm)
        if qr_img:
            p.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size, mask='auto')
            p.setFont(_FONT_NORMAL, 4.5)
            p.setFillColor(colors.HexColor("#666666"))
            p.drawCentredString(qr_x + qr_size / 2, qr_y - 0.18*cm, "Vérification")
    except Exception:
        pass
    p.setFillColor(colors.black)


def _saut_page_si_necessaire(p, y, hauteur_necessaire, width, height, margin_top,
                              margin_left, margin_right, footer_zone,
                              entreprise, emp, bulletin):
    """Si l'espace restant est insuffisant, dessine le footer, saute de page
    et ajoute un mini en-tête de continuation."""
    if y - hauteur_necessaire < footer_zone:
        _dessiner_footer(p, width, margin_left, margin_right, entreprise, emp, bulletin)
        p.showPage()
        y = height - margin_top
        p.setFont(_FONT_BOLD, 9)
        p.setFillColor(colors.black)
        p.drawString(margin_left, y, f"BULLETIN DE PAIE \u2014 {bulletin.numero_bulletin} (suite)")
        p.setStrokeColor(colors.HexColor("#ce1126"))
        p.setLineWidth(1)
        p.line(margin_left, y - 0.15*cm, width - margin_right, y - 0.15*cm)
        p.setStrokeColor(colors.black)
        p.setLineWidth(0.5)
        y -= 0.50*cm
    return y


def generer_bulletin_pdf(bulletin):
    """
    Génère le PDF d'un bulletin de paie et retourne les bytes du PDF.

    Args:
        bulletin: Instance BulletinPaie
        
    Returns:
        bytes: Contenu du fichier PDF
    """
    from .models import LigneBulletin
    
    lignes = LigneBulletin.objects.filter(bulletin=bulletin).select_related('rubrique')
    gains = lignes.filter(rubrique__type_rubrique='gain')
    retenues = lignes.filter(rubrique__type_rubrique__in=['retenue', 'cotisation'])
    
    # Créer le buffer PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Variables de position — marges optimisées pour éviter chevauchement
    margin_top = 0.8*cm
    margin_left = 1.2*cm
    margin_right = 1.2*cm
    footer_zone = 4.5*cm  # zone réservée en bas (footer absolu à 3.1cm + marge sécurité 1.4cm)
    y = height - margin_top

    # === EN-TÊTE ===
    entreprise = bulletin.employe.entreprise

    # Logo entreprise à gauche
    if entreprise and entreprise.logo:
        try:
            logo_path = entreprise.logo.path
            if os.path.exists(logo_path):
                p.drawImage(logo_path, margin_left, y - 1.8*cm, width=1.8*cm, height=1.8*cm, preserveAspectRatio=True)
        except:
            pass

    # Titre centré
    p.setFont(_FONT_BOLD, 10)
    p.drawCentredString(width/2, y, "RÉPUBLIQUE DE GUINÉE")
    y -= 0.30*cm
    p.setFont(_FONT_ITALIC, 7)
    p.drawCentredString(width/2, y, "Travail - Justice - Solidarité")
    y -= 0.40*cm

    # Nom entreprise
    p.setFont(_FONT_BOLD, 11)
    nom_entreprise = entreprise.nom_entreprise if entreprise else "ENTREPRISE"
    p.drawCentredString(width/2, y, nom_entreprise)
    y -= 0.35*cm
    # NIF et CNSS entreprise sous le nom
    if entreprise:
        nif_str = entreprise.nif or "Non renseigné"
        cnss_str = getattr(entreprise, 'num_cnss', None) or "Non renseigné"
        p.setFont(_FONT_NORMAL, 7)
        p.setFillColor(colors.HexColor("#444444"))
        p.drawCentredString(width/2, y, f"NIF: {nif_str}   |   CNSS Employeur: {cnss_str}")
        p.setFillColor(colors.black)
    y -= 0.35*cm

    # Titre bulletin
    p.setFont(_FONT_BOLD, 12)
    p.drawCentredString(width/2, y, "BULLETIN DE PAIE")
    y -= 0.30*cm

    # Ligne de séparation
    p.setStrokeColor(colors.HexColor("#ce1126"))
    p.setLineWidth(2)
    p.line(margin_left, y, width - margin_right, y)
    y -= 0.40*cm

    # Infos bulletin sur une ligne
    p.setFont(_FONT_NORMAL, 8)
    p.setFillColor(colors.black)
    p.drawString(margin_left, y, f"N°: {bulletin.numero_bulletin}")
    p.drawCentredString(width/2, y, f"Période: {bulletin.periode}")
    p.drawRightString(width - margin_right, y, f"Date: {bulletin.date_calcul.strftime('%d/%m/%Y') if bulletin.date_calcul else '-'}")
    y -= 0.25*cm
    # Dates de la période
    p.setFont(_FONT_NORMAL, 7)
    periode_detail = f"Du {bulletin.periode.date_debut.strftime('%d/%m/%Y')} au {bulletin.periode.date_fin.strftime('%d/%m/%Y')}" if bulletin.periode.date_debut and bulletin.periode.date_fin else ""
    p.drawCentredString(width/2, y, periode_detail)
    y -= 0.40*cm

    # === INFORMATIONS EMPLOYÉ ===
    p.setFillColor(colors.HexColor("#ce1126"))
    p.setFont(_FONT_BOLD, 8)
    p.drawString(margin_left, y, "INFORMATIONS EMPLOYÉ")
    p.setFillColor(colors.black)
    y -= 0.35*cm
    
    emp = bulletin.employe
    
    # Ancienneté en années, mois complets et jours à la date du bulletin.
    anciennete_str = format_anciennete_bulletin(emp, bulletin)
    
    # Récupération des congés
    from temps_travail.models import SoldeConge
    solde_conge = SoldeConge.objects.filter(employe=emp, annee=bulletin.annee_paie).first()
    conges_acquis = solde_conge.conges_acquis if solde_conge else Decimal('0')
    conges_pris = solde_conge.conges_pris if solde_conge else Decimal('0')
    conges_restants = solde_conge.conges_restants if solde_conge else Decimal('0')

    # Acquisition mensuelle (jours acquis ce mois)
    acquis_ce_mois = Decimal('0')
    try:
        from .models import ConfigurationPaie
        config_paie = ConfigurationPaie.objects.filter(entreprise=entreprise).first()
        if config_paie:
            acquis_ce_mois = config_paie.jours_conges_par_mois
        else:
            acquis_ce_mois = Decimal('2.5')  # défaut légal Guinée (Art. 222 : 2,5 j/mois = 30 j/an)
    except Exception:
        acquis_ce_mois = Decimal('2.5')

    infos_emp = [
        ["Matricule:", emp.matricule or "-", "N° CNSS:", emp.num_cnss_individuel or "-"],
        ["Nom et Prénoms:", f"{emp.nom} {emp.prenoms}", "Ancienneté:", anciennete_str],
        ["Poste:", str(emp.poste or "-"), "Service:", str(emp.service or "-")],
        ["Date embauche:", emp.date_embauche.strftime('%d/%m/%Y') if emp.date_embauche else "-", "Mode paiement:", emp.mode_paiement or "-"],
        ["Congés acquis:", f"{conges_acquis:g} j", "Congés pris:", f"{conges_pris:g} j"],
        ["Solde congés:", f"{conges_restants:g} j", "Acquis ce mois:", f"{acquis_ce_mois:g} j"],
        ["Nature contrat:", dict(emp.TYPES_CONTRATS).get(emp.type_contrat, emp.type_contrat or "-"), "", ""],
    ]
    
    for row in infos_emp:
        p.setFont(_FONT_BOLD, 7)
        p.drawString(margin_left, y, row[0])
        p.setFont(_FONT_NORMAL, 7)
        p.drawString(3.8*cm, y, str(row[1]))
        if row[2]:
            p.setFont(_FONT_BOLD, 7)
            p.drawString(10.5*cm, y, row[2])
            p.setFont(_FONT_NORMAL, 7)
            p.drawString(13.5*cm, y, str(row[3]))
        y -= 0.32*cm

    y -= 0.15*cm

    # === GAINS ===
    p.setFillColor(colors.HexColor("#28a745"))
    p.setFont(_FONT_BOLD, 8)
    p.drawString(margin_left, y, "GAINS ET RÉMUNÉRATIONS")
    p.setFillColor(colors.black)
    y -= 0.20*cm

    # Tableau des gains (5 colonnes avec Nbre pour les heures)
    gains_data = [["Libellé", "Nbre", "Base", "Taux", "Montant"]]
    for g in gains:
        nbre_str = f"{g.nombre:g}" if g.nombre and g.nombre != 1 else ""
        # Nettoyer le taux : supprimer les zéros inutiles (30.0000% → 30%)
        taux_val = g.taux
        if taux_val:
            taux_str = f"{float(taux_val):g}%"
        else:
            taux_str = "-"
        # Corriger libellé: "Prime de transport" → "Indemnité de transport" si forfaitaire
        libelle = g.rubrique.libelle_rubrique[:35]
        code_rub = (g.rubrique.code_rubrique or '').upper()
        if libelle.lower().startswith('prime'):
            from .services import PATTERNS_CODES_FORFAITAIRES, MOTS_CLES_LIBELLE_FORFAITAIRES
            lib_low = libelle.lower()
            is_indem = any(p in code_rub for p in PATTERNS_CODES_FORFAITAIRES) or \
                       any(m in lib_low for m in MOTS_CLES_LIBELLE_FORFAITAIRES)
            if is_indem:
                libelle = 'Indemnité' + libelle[5:]  # "Prime de X" → "Indemnité de X"
        if ('HS' in code_rub or 'HEURE' in libelle.upper()) and 'SUP' in libelle.upper():
            import re
            libelle = re.sub(r'\s*\+?\d+\s*%', '', libelle).strip()
        gains_data.append([
            libelle,
            nbre_str,
            f"{g.base:,.0f}".replace(",", " ") if g.base else "-",
            taux_str,
            f"{g.montant:,.0f}".replace(",", " ")
        ])
    gains_data.append(["TOTAL BRUT", "", "", "", f"{bulletin.salaire_brut:,.0f} GNF".replace(",", " ")])
    
    row_height = 12
    gains_table = Table(gains_data, colWidths=[6.5*cm, 1.5*cm, 3*cm, 2*cm, 4*cm], rowHeights=row_height)
    gains_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#28a745")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), _FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#d4edda")),
        ('FONTNAME', (0, -1), (-1, -1), _FONT_BOLD),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    table_height = len(gains_data) * row_height
    # Vérifier espace pour le tableau des gains
    y = _saut_page_si_necessaire(p, y, table_height + 0.3*cm, width, height, margin_top,
                                  margin_left, margin_right, footer_zone, entreprise, emp, bulletin)
    gains_table.wrapOn(p, width, height)
    gains_table.drawOn(p, margin_left, y - table_height)
    y -= table_height + 0.3*cm

    # === DÉTAIL HEURES SUPPLÉMENTAIRES ===
    hs_30 = getattr(bulletin, 'heures_supplementaires_30', 0) or 0
    hs_60 = getattr(bulletin, 'heures_supplementaires_60', 0) or 0
    hs_nuit = getattr(bulletin, 'heures_nuit', 0) or 0
    hs_feries = getattr(bulletin, 'heures_feries', 0) or 0
    hs_feries_nuit = getattr(bulletin, 'heures_feries_nuit', 0) or 0
    prime_hs = getattr(bulletin, 'prime_heures_sup', 0) or 0
    prime_nuit = getattr(bulletin, 'prime_nuit', 0) or 0
    prime_feries = getattr(bulletin, 'prime_feries', 0) or 0
    prime_feries_nuit = getattr(bulletin, 'prime_feries_nuit', 0) or 0
    total_hs_heures = float(hs_30) + float(hs_60) + float(hs_nuit) + float(hs_feries) + float(hs_feries_nuit)
    
    if total_hs_heures > 0 or float(prime_hs) > 0:
        p.setFont(_FONT_BOLD, 7)
        p.setFillColor(colors.HexColor("#6c757d"))
        p.drawString(1.5*cm, y, "DÉTAIL HEURES SUPPLÉMENTAIRES (Code du Travail Art. 221)")
        p.setFillColor(colors.black)
        y -= 0.25*cm
        
        # Calcul des montants individuels (salaire_base / 173,33 × h × coefficient)
        _sal_base = Decimal(str(bulletin.salaire_base or 0))
        # Fallback: si salaire_base=0 (ancien bulletin), chercher dans les gains
        if _sal_base == 0:
            try:
                from .models import LigneBulletin
                from django.db.models import Q, Case, When, Value, IntegerField
                ligne_base = LigneBulletin.objects.filter(
                    bulletin=bulletin,
                    rubrique__type_rubrique='gain',
                ).filter(
                    Q(rubrique__categorie_rubrique='salaire_base') |
                    Q(rubrique__code_rubrique__icontains='SAL_BASE') |
                    Q(rubrique__code_rubrique__iexact='BASE') |
                    Q(rubrique__libelle_rubrique__icontains='Salaire de base')
                ).annotate(
                    _base_priority=Case(
                        When(rubrique__categorie_rubrique='salaire_base', then=Value(0)),
                        When(rubrique__code_rubrique__icontains='SAL_BASE', then=Value(1)),
                        When(rubrique__code_rubrique__iexact='BASE', then=Value(2)),
                        default=Value(9),
                        output_field=IntegerField(),
                    )
                ).order_by('_base_priority', 'ordre', 'id').first()
                if ligne_base:
                    _sal_base = Decimal(str(ligne_base.montant or 0))
            except Exception:
                pass
        _sal_h = _sal_base / Decimal('173.33') if _sal_base > 0 else Decimal('0')
        _montant_30 = round(_sal_h * Decimal(str(hs_30)) * Decimal('1.30'))
        _montant_60 = round(_sal_h * Decimal(str(hs_60)) * Decimal('1.60'))
        _montant_nuit = round(_sal_h * Decimal(str(hs_nuit)) * Decimal('1.20')) if float(hs_nuit) > 0 else 0
        _montant_feries = round(_sal_h * Decimal(str(hs_feries)) * Decimal('1.60')) if float(hs_feries) > 0 else 0
        _montant_feries_nuit = round(_sal_h * Decimal(str(hs_feries_nuit)) * Decimal('2.00')) if float(hs_feries_nuit) > 0 else 0
        _total_hs_calcule = (
            Decimal(str(_montant_30)) + Decimal(str(_montant_60)) +
            Decimal(str(_montant_nuit)) + Decimal(str(_montant_feries)) +
            Decimal(str(_montant_feries_nuit))
        )

        hs_detail_data = [["Type", "Heures", "Majoration", "Montant"]]
        # (données HS construites ci-dessous, page break vérifié avant le dessin)
        if float(hs_30) > 0:
            hs_detail_data.append(["4 prem. HS/sem.", f"{hs_30:g}h", "+30% (130%)",
                                    f"{_montant_30:,.0f}".replace(",", " ")])
        if float(hs_60) > 0:
            hs_detail_data.append(["Au-delà 4 HS/sem.", f"{hs_60:g}h", "+60% (160%)",
                                    f"{_montant_60:,.0f}".replace(",", " ")])
        if float(hs_nuit) > 0:
            hs_detail_data.append(["Heures de nuit (20h-6h)", f"{hs_nuit:g}h", "+20% (120%)",
                                    f"{_montant_nuit:,.0f}".replace(",", " ")])
        if float(hs_feries) > 0:
            hs_detail_data.append(["Jours fériés (jour)", f"{hs_feries:g}h", "+60% (160%)",
                                    f"{_montant_feries:,.0f}".replace(",", " ")])
        if float(hs_feries_nuit) > 0:
            hs_detail_data.append(["Jours fériés (nuit)", f"{hs_feries_nuit:g}h", "+100% (200%)",
                                    f"{_montant_feries_nuit:,.0f}".replace(",", " ")])

        total_prime = float(prime_hs) + float(prime_nuit) + float(prime_feries) + float(prime_feries_nuit)
        if total_prime <= 0 and _total_hs_calcule > 0:
            total_prime = float(_total_hs_calcule)
        hs_detail_data.append(["", f"{total_hs_heures:g}h", "Total HS:",
                                f"{total_prime:,.0f} GNF".replace(",", " ")])
        
        hs_row_h = 12
        hs_table = Table(hs_detail_data, colWidths=[5.5*cm, 2*cm, 4.5*cm, 5*cm], rowHeights=hs_row_h)
        nb_hs_rows = len(hs_detail_data)
        hs_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#6c757d")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), _FONT_BOLD),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, -1), (-1, -1), _FONT_BOLD),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#f8f9fa")),
        ]))
        
        hs_table_h = nb_hs_rows * hs_row_h
        # Vérifier espace pour le tableau HS
        y = _saut_page_si_necessaire(p, y, hs_table_h + 0.60*cm, width, height, margin_top,
                                      margin_left, margin_right, footer_zone, entreprise, emp, bulletin)
        hs_table.wrapOn(p, width, height)
        hs_table.drawOn(p, 1.5*cm, y - hs_table_h)
        y -= hs_table_h + 0.35*cm
    else:
        y += 0.35*cm
    
    # === RETENUES ===
    retenues_data = [["Libellé", "Base", "Taux", "Montant"]]
    cnss_irg_codes = ['CNSS', 'IRG', 'RTS', 'IRS', 'IRPP']
    for r in retenues:
        code = r.rubrique.code_rubrique.upper() if r.rubrique.code_rubrique else ''
        libelle = r.rubrique.libelle_rubrique.upper() if r.rubrique.libelle_rubrique else ''
        is_cnss_irg = any(c in code or c in libelle for c in cnss_irg_codes)
        if not is_cnss_irg:
            retenues_data.append([
                r.rubrique.libelle_rubrique[:35],
                f"{r.base:,.0f}".replace(",", " ") if r.base else "-",
                f"{r.taux}%" if r.taux else "-",
                f"{r.montant:,.0f}".replace(",", " ")
            ])
    
    # Ajouter CNSS et RTS
    base_cnss = min(bulletin.salaire_brut, 2500000)
    retenues_data.append(["CNSS Employé (5%)", f"{base_cnss:,.0f}".replace(",", " "), "5%", f"{bulletin.cnss_employe:,.0f}".replace(",", " ")])
    base_rts_val = getattr(bulletin, 'base_rts', 0) or 0
    taux_eff_rts_val = getattr(bulletin, 'taux_effectif_rts', 0) or 0
    rts_base_str = f"{base_rts_val:,.0f}".replace(",", " ") if base_rts_val else "-"
    # Note: l'abattement forfaitaire (exonération 25%) est un ajustement fiscal,
    # pas une retenue réelle → affiché uniquement dans la section DÉTAIL RTS.
    retenues_data.append(["RTS (Impôt sur le revenu \u2013 barème progressif)", rts_base_str, f"moy. {taux_eff_rts_val:.2f}%" if taux_eff_rts_val else "-", f"{bulletin.irg:,.0f}".replace(",", " ")])

    # Vérifier espace avant de dessiner la section retenues
    ret_table_height = len(retenues_data) * row_height
    ret_section_height = ret_table_height + 0.7*cm
    y = _saut_page_si_necessaire(p, y, ret_section_height, width, height, margin_top,
                                  margin_left, margin_right, footer_zone, entreprise, emp, bulletin)

    p.setFillColor(colors.HexColor("#dc3545"))
    p.setFont(_FONT_BOLD, 9)
    p.drawString(1.5*cm, y, "RETENUES ET COTISATIONS")
    p.setFillColor(colors.black)
    y -= 0.4*cm

    retenues_table = Table(retenues_data, colWidths=[8*cm, 3*cm, 2*cm, 4*cm], rowHeights=row_height)
    retenues_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#dc3545")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), _FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    retenues_table.wrapOn(p, width, height)
    retenues_table.drawOn(p, margin_left, y - ret_table_height)
    y -= ret_table_height + 0.3*cm

    # === DÉTAIL CALCUL RTS (barème progressif) ===
    detail_rts = calculer_detail_tranches_rts(base_rts_val)
    if detail_rts:
        # Estimer hauteur section RTS (titre + nb tranches + 2 lignes entête/total)
        rts_est_rows = len(detail_rts) + 2
        rts_est_height = rts_est_rows * 12 + 0.5*cm
        y = _saut_page_si_necessaire(p, y, rts_est_height, width, height, margin_top,
                                      margin_left, margin_right, footer_zone, entreprise, emp, bulletin)

        p.setFont(_FONT_BOLD, 7)
        p.setFillColor(colors.HexColor("#6c757d"))
        # Explication de la base imposable avec nature de l'abattement
        abattement_val = getattr(bulletin, 'abattement_forfaitaire', 0) or 0
        if float(abattement_val) > 0:
            # Utiliser abattement_val (stocké par services.py, ROUND_FLOOR) — même valeur partout
            p.drawString(1.5*cm, y,
                f"DÉTAIL RTS — Base imposable: {base_rts_val:,.0f} = "
                f"Brut {bulletin.salaire_brut:,.0f} − CNSS {bulletin.cnss_employe:,.0f} "
                f"− Exonération indemnités {abattement_val:,.0f} (plafond 25%)"
                .replace(",", " "))
        else:
            p.drawString(1.5*cm, y,
                f"DÉTAIL RTS — Base imposable: {base_rts_val:,.0f} = "
                f"Brut {bulletin.salaire_brut:,.0f} − CNSS {bulletin.cnss_employe:,.0f}"
                .replace(",", " "))
        p.setFillColor(colors.black)
        y -= 0.25*cm

        rts_detail_data = [["Tranche (bornes)", "Base taxable", "Taux", "Impôt"]]
        cumul_impot = Decimal('0')
        for i, t in enumerate(detail_rts, start=1):
            taux_pct = f"{t['taux']:g}"
            b_inf = f"{t['borne_inf']:,.0f}".replace(",", " ")
            b_sup = f"{t['borne_sup']:,.0f}".replace(",", " ") if t.get('borne_sup') else "∞"
            base_tr = f"{t['base_tranche']:,.0f}".replace(",", " ")
            rts_detail_data.append([
                f"{b_inf} à {b_sup}",
                base_tr,
                f"{taux_pct}%",
                f"{t['impot_tranche']:,.0f}".replace(",", " "),
            ])
            cumul_impot += t['impot_tranche']
        rts_detail_data.append(["", "", "Total RTS:", f"{cumul_impot:,.0f} GNF".replace(",", " ")])

        rts_row_h = 12
        rts_table = Table(rts_detail_data, colWidths=[5*cm, 4*cm, 3*cm, 5*cm], rowHeights=rts_row_h)
        nb_rows = len(rts_detail_data)
        rts_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#6c757d")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), _FONT_BOLD),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, -1), (-1, -1), _FONT_BOLD),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#f8f9fa")),
        ]))
        
        rts_table_h = nb_rows * rts_row_h
        rts_table.wrapOn(p, width, height)
        rts_table.drawOn(p, 1.5*cm, y - rts_table_h)
        y -= rts_table_h + 0.25*cm
    else:
        y -= 0.2*cm
    
    # === RÉCAPITULATIF ===
    rappel = getattr(bulletin, 'rappel_salaire', 0) or 0
    trop_percu = getattr(bulletin, 'retenue_trop_percu', 0) or 0
    has_rappel = rappel > 0
    has_trop_percu = trop_percu > 0
    extra_lines = (1 if has_rappel else 0) + (1 if has_trop_percu else 0)
    recap_height = 1.6*cm + extra_lines * 0.3*cm
    y = _saut_page_si_necessaire(p, y, recap_height + 0.3*cm, width, height, margin_top,
                                  margin_left, margin_right, footer_zone, entreprise, emp, bulletin)
    p.setStrokeColor(colors.HexColor("#ce1126"))
    p.setLineWidth(2)
    p.rect(margin_left, y - recap_height, width - 2*margin_left, recap_height, stroke=1, fill=0)

    p.setFont(_FONT_BOLD, 9)
    p.setFillColor(colors.black)
    p.drawString(margin_left + 0.3*cm, y - 0.35*cm, "SALAIRE BRUT:")
    p.drawRightString(width - margin_right - 0.3*cm, y - 0.35*cm, f"{bulletin.salaire_brut:,.0f} GNF".replace(",", " "))

    # CNSS et RTS alignés sur la même ligne
    p.setFont(_FONT_NORMAL, 7)
    p.setFillColor(colors.HexColor("#dc3545"))
    mid_x = width / 2
    p.drawString(margin_left + 0.3*cm, y - 0.7*cm, f"CNSS (5%): -{bulletin.cnss_employe:,.0f}".replace(",", " "))
    p.drawString(mid_x, y - 0.7*cm, f"RTS: -{bulletin.irg:,.0f}".replace(",", " "))
    p.drawRightString(width - margin_right - 0.3*cm, y - 0.7*cm, f"Total retenues: -{bulletin.total_retenues:,.0f} GNF".replace(",", " "))

    offset_y = 0.7*cm
    if has_rappel:
        offset_y += 0.3*cm
        p.setFillColor(colors.HexColor("#007bff"))
        p.drawString(margin_left + 0.3*cm, y - offset_y, f"Rappel: +{rappel:,.0f} GNF".replace(",", " "))
    if has_trop_percu:
        offset_y += 0.3*cm
        p.setFillColor(colors.HexColor("#dc3545"))
        p.drawString(margin_left + 0.3*cm, y - offset_y, f"Retenue trop-perçu: -{trop_percu:,.0f} GNF".replace(",", " "))

    p.setFillColor(colors.HexColor("#28a745"))
    p.setFont(_FONT_BOLD, 14)
    p.drawString(margin_left + 0.3*cm, y - offset_y - 0.55*cm, "NET À PAYER:")
    p.drawRightString(width - margin_right - 0.3*cm, y - offset_y - 0.55*cm, f"{bulletin.net_a_payer:,.0f} GNF".replace(",", " "))
    p.setFillColor(colors.black)

    y -= recap_height + 0.3*cm
    
    # === CHARGES PATRONALES ===
    vf = getattr(bulletin, 'versement_forfaitaire', 0) or 0
    ta = getattr(bulletin, 'taxe_apprentissage', 0) or 0
    taux_ta = getattr(bulletin, 'taux_ta', 0) or 0
    onfpp = getattr(bulletin, 'contribution_onfpp', 0) or 0
    base_vf = getattr(bulletin, 'base_vf', 0) or 0
    nb_sal = getattr(bulletin, 'nombre_salaries', 0) or 0
    total_charges = bulletin.cnss_employeur + vf + ta + onfpp
    taux_ta_label = str(taux_ta).rstrip('0').rstrip('.').replace('.', ',') if taux_ta else '1,5'

    # Tableau charges patronales
    charges_data = [["Charge patronale", "Base", "Taux", "Montant"]]
    charges_data.append(["CNSS Employeur",
        f"{min(bulletin.salaire_brut, 2500000):,.0f}".replace(",", " "),
        "18%",
        f"{bulletin.cnss_employeur:,.0f}".replace(",", " ")])
    charges_data.append(["Versement Forfaitaire (VF)",
        f"{base_vf:,.0f}".replace(",", " ") if base_vf else "-",
        "6%",
        f"{vf:,.0f}".replace(",", " ")])
    if ta > 0:
        charges_data.append([f"TA (applicable si effectif < 30 sal. \u2014 effectif actuel : {nb_sal})",
            f"{base_vf:,.0f}".replace(",", " ") if base_vf else "-",
            f"{taux_ta_label}%",
            f"{ta:,.0f}".replace(",", " ")])
    elif onfpp > 0:
        charges_data.append([f"ONFPP (applicable si effectif \u2265 30 sal. \u2014 effectif actuel : {nb_sal})",
            f"{base_vf:,.0f}".replace(",", " ") if base_vf else "-",
            "1,5%",
            f"{onfpp:,.0f}".replace(",", " ")])
    charges_data.append(["TOTAL CHARGES PATRONALES", "", "",
        f"{total_charges:,.0f} GNF".replace(",", " ")])

    ch_row_h = 11
    ch_table_h = len(charges_data) * ch_row_h
    # Espace nécessaire = tableau charges + note VF + marge sécurité
    espace_necessaire = ch_table_h + 0.8*cm
    y = _saut_page_si_necessaire(p, y, espace_necessaire, width, height, margin_top,
                                  margin_left, margin_right, footer_zone, entreprise, emp, bulletin)

    charges_table = Table(charges_data, colWidths=[7*cm, 3.5*cm, 2*cm, 4.5*cm], rowHeights=ch_row_h)
    charges_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#fd7e14")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), _FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#dee2e6")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fff3cd")),
        ('FONTNAME', (0, -1), (-1, -1), _FONT_BOLD),
    ]))
    charges_table.wrapOn(p, width, height)
    charges_table.drawOn(p, margin_left, y - ch_table_h)
    y -= ch_table_h + 0.15*cm
    # Note VF/TA complete, en petit gras, decoupee pour eviter tout debordement.
    if base_vf > 0:
        base_vf_f = float(base_vf)
        brut_gnf = float(bulletin.salaire_brut)
        deduction = max(0, brut_gnf - base_vf_f)
        ta_ou_onfpp = 'ONFPP' if onfpp > 0 else 'TA'
        taux_note = '1,5' if onfpp > 0 else taux_ta_label
        charge_valeur = onfpp if onfpp > 0 else ta
        p.setFont(_FONT_BOLD, 4.8)
        p.setFillColor(colors.HexColor("#444444"))
        p.drawString(margin_left, y,
            f"Base VF/{ta_ou_onfpp} = Brut {brut_gnf:,.0f} - indemnites exonerees plafonnees {deduction:,.0f} "
            f"(25% max du brut) = {base_vf_f:,.0f} GNF"
            .replace(",", " "))
        y -= 0.16*cm
        p.drawString(margin_left, y,
            f"VF = {base_vf_f:,.0f} x 6% = {vf:,.0f} GNF | "
            f"{ta_ou_onfpp} = {base_vf_f:,.0f} x {taux_note}% = {charge_valeur:,.0f} GNF"
            .replace(",", " "))
        y -= 0.16*cm
        p.drawString(margin_left, y,
            "Ref : Code General des Impots - Guinee (Versement Forfaitaire sur salaires, taux 6%)")
        y -= 0.20*cm
    p.setFillColor(colors.black)

    # === PIED DE PAGE (footer unique — position absolue en bas de la dernière page) ===
    # _saut_page_si_necessaire garantit que y >= footer_zone (4.5cm) > footer_top (2.15cm)
    # → aucun chevauchement possible ; on dessine simplement le footer sur la page courante.
    _dessiner_footer(p, width, margin_left, margin_right, entreprise, emp, bulletin)

    # Finaliser le PDF
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer.read()


def generer_bulletin_pdf_sdbk(bulletin):
    """
    Compatibilite legacy: l'ancien modele SDBK redirige vers le standard GuineeRH.
    """
    return generer_bulletin_pdf(bulletin)

    from .models import LigneBulletin

    lignes = LigneBulletin.objects.filter(bulletin=bulletin).select_related('rubrique').order_by('rubrique__ordre_affichage')
    gains   = lignes.filter(rubrique__type_rubrique='gain')

    buffer = io.BytesIO()
    p      = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    entreprise = bulletin.employe.entreprise
    emp        = bulletin.employe

    # ── Ancienneté ──────────────────────────────────────────────────────────
    anciennete_str = format_anciennete_bulletin(emp, bulletin)

    # ── Congés ───────────────────────────────────────────────────────────────
    from temps_travail.models import SoldeConge
    solde = SoldeConge.objects.filter(employe=emp, annee=bulletin.annee_paie).first()
    c_acquis   = float(solde.conges_acquis   if solde else 0)
    c_pris     = float(solde.conges_pris     if solde else 0)
    c_restants = float(solde.conges_restants if solde else 0)

    margin_x   = 1.0 * cm
    table_w    = width - 2 * margin_x   # ≈ 19 cm

    # ── helpers ──────────────────────────────────────────────────────────────
    def _fmt(v):
        if not v:
            return ''
        try:
            return f"{int(v):,}".replace(",", " ")
        except Exception:
            return str(v)

    def _fmt0(v):
        if v is None:
            return ''
        if v == 0:
            return '0'
        try:
            return f"{int(v):,}".replace(",", " ")
        except Exception:
            return str(v)

    # ════════════════════════════════════════════════════════════════════════
    # EN-TÊTE
    # ════════════════════════════════════════════════════════════════════════
    y = height - 0.8 * cm

    # ── Dimensions de l'en-tête (zone fixe de 3.0 cm) ──────────────────────
    HDR_H   = 3.0 * cm
    HDR_TOP = y                    # = height - 0.8 cm
    HDR_BOT = HDR_TOP - HDR_H      # ligne de séparation exacte

    nom_ent = entreprise.nom_entreprise if entreprise else "ENTREPRISE"

    # Boîte info (haut droite) — dimensionnée pour tenir dans HDR_H
    bw = 6.2 * cm
    bh = HDR_H
    bx = width - margin_x - bw     # bord droit aligné sur la marge droite
    by = HDR_TOP
    p.setStrokeColor(colors.black)
    p.setLineWidth(0.5)
    p.rect(bx, HDR_BOT, bw, bh)

    periode_debut = bulletin.periode.date_debut.strftime('%d/%m/%y') if bulletin.periode and bulletin.periode.date_debut else ''
    periode_fin   = bulletin.periode.date_fin.strftime('%d/%m/%y')   if bulletin.periode and bulletin.periode.date_fin   else ''
    date_pmt      = bulletin.date_calcul.strftime('%d/%m/%Y')         if bulletin.date_calcul else '-'

    box_lines = [
        ("Période du :", f"{periode_debut} au {periode_fin}"),
        ("Paiement",    date_pmt),
        ("Matricule :", str(emp.matricule or '-')),
        ("Ancienneté :", anciennete_str),
    ]
    iy = by - 0.6 * cm
    for lbl, val in box_lines:
        p.setFont(_FONT_BOLD, 7)
        p.drawString(bx + 0.25 * cm, iy, lbl)
        p.setFont(_FONT_NORMAL, 7)
        p.drawString(bx + 2.6 * cm, iy, val)
        iy -= 0.6 * cm

    # Logo (gauche, centré verticalement dans HDR_H)
    logo_x  = margin_x
    logo_h  = 2.0 * cm
    logo_w  = 3.0 * cm
    logo_y  = HDR_BOT + (HDR_H - logo_h) / 2   # centré verticalement
    if entreprise and entreprise.logo:
        try:
            lp = entreprise.logo.path
            if os.path.exists(lp):
                p.drawImage(lp, logo_x, logo_y, width=logo_w, height=logo_h,
                            preserveAspectRatio=True)
        except Exception:
            pass

    # Raison sociale sous le logo
    p.setFont(_FONT_BOLD, 8)
    p.drawString(logo_x, HDR_BOT + 0.15 * cm, nom_ent)

    # « BULLETIN DE PAIE » centré entre le logo et la boîte info
    title_x = (margin_x + logo_w + bx) / 2
    p.setFont(_FONT_BOLD, 14)
    p.drawCentredString(title_x, HDR_BOT + HDR_H / 2, "BULLETIN DE PAIE")

    y = HDR_BOT

    # Ligne séparatrice
    p.setLineWidth(1)
    p.line(margin_x, y, width - margin_x, y)
    y -= 0.45 * cm

    # ════════════════════════════════════════════════════════════════════════
    # INFORMATIONS EMPLOYÉ  (2 colonnes)
    # ════════════════════════════════════════════════════════════════════════
    left_col  = margin_x
    right_col = width / 2
    lbl_w     = 3.8 * cm

    def _emp_row(label, value, rlabel, rvalue, row_y):
        p.setFont(_FONT_BOLD, 7.5)
        p.drawString(left_col, row_y, label)
        p.setFont(_FONT_NORMAL, 7.5)
        p.drawString(left_col + lbl_w, row_y, str(value))
        if rlabel:
            p.setFont(_FONT_BOLD, 7.5)
            p.drawString(right_col, row_y, rlabel)
        if rvalue:
            p.setFont(_FONT_NORMAL if rlabel != "M." else _FONT_BOLD, 7.5)
            p.drawString(right_col + 2.5 * cm, row_y, str(rvalue))

    nature_contrat = dict(emp.TYPES_CONTRATS).get(emp.type_contrat, emp.type_contrat or '-') if hasattr(emp, 'TYPES_CONTRATS') else (emp.type_contrat or '-')
    mode_pmt       = dict(emp.MODES_PAIEMENT).get(emp.mode_paiement, emp.mode_paiement or '-') if hasattr(emp, 'MODES_PAIEMENT') else (getattr(emp, 'mode_paiement', None) or '-')
    heures_str     = f"{float(bulletin.heures_normales or 173.33):.2f} h"
    sal_base_str   = (_fmt0(bulletin.salaire_base) + " GNF") if bulletin.salaire_base else '-'
    adresse_str    = (str(emp.adresse_actuelle or '').strip()
                      or (str(getattr(entreprise, 'adresse', '') or '').strip())
                      or '-')

    rows_emp = [
        ("N° Sécurité Sociale",  emp.num_cnss_individuel or '-',    "M.",              f"{emp.nom} {emp.prenoms}"),
        ("Emploi",               str(emp.poste or '-'),              "Service",         str(emp.service or '-')),
        ("Salaire de base",      sal_base_str,                       "Heures",          heures_str),
        ("Mode de paiement",     mode_pmt,                           "Statut",          str(emp.statut_employe or '-')),
        ("Nature du contrat",    nature_contrat,                     "Date d'embauche", emp.date_embauche.strftime('%d/%m/%Y') if emp.date_embauche else '-'),
        ("Adresse",              adresse_str,                        "",                ""),
    ]
    for i, (ll, lv, rl, rv) in enumerate(rows_emp):
        _emp_row(ll, lv, rl, rv, y - i * 0.42 * cm)
    y -= len(rows_emp) * 0.42 * cm + 0.25 * cm

    # ════════════════════════════════════════════════════════════════════════
    # TABLEAU CONGÉS
    # ════════════════════════════════════════════════════════════════════════
    conge_data = [
        ['Congé', 'Dates de congés', 'Repos Compensateur'],
        [f'Pris :      {c_pris:.3f}    Du      au', '', f'Pris :      0,000'],
        [f'Restant :  {c_restants:.3f}    Du      au', '', f'Restant :  0,000'],
        [f'Acquis :   {c_acquis:.3f}    Du      au', '', f'Acquis :   0,000'],
    ]
    cw_conge = [table_w * 0.46, table_w * 0.27, table_w * 0.27]
    ct = Table(conge_data, colWidths=cw_conge, rowHeights=11)
    ct.setStyle(TableStyle([
        ('FONTNAME',    (0, 0), (-1, 0),  _FONT_BOLD),
        ('FONTNAME',    (0, 1), (-1, -1), _FONT_NORMAL),
        ('FONTSIZE',    (0, 0), (-1, -1), 6.5),
        ('GRID',        (0, 0), (-1, -1), 0.3, colors.black),
        ('BACKGROUND',  (0, 0), (-1, 0),  colors.HexColor('#eeeeee')),
        ('ALIGN',       (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    ct_h = 4 * 11
    ct.wrapOn(p, width, height)
    ct.drawOn(p, margin_x, y - ct_h)
    y -= ct_h + 0.35 * cm

    # ════════════════════════════════════════════════════════════════════════
    # TABLEAU PRINCIPAL  (10 colonnes)
    # ════════════════════════════════════════════════════════════════════════
    # Colonnes : N° | Désignation | Nombre | Base | TxSal | GainSal | RetSal | TxPat | RetPat | Montant
    col_w = [0.55*cm, 4.1*cm, 1.05*cm, 1.95*cm, 0.85*cm, 2.0*cm, 2.0*cm, 0.85*cm, 2.0*cm, 3.6*cm]
    # total = 0.55+4.1+1.05+1.95+0.85+2.0+2.0+0.85+2.0+3.6 = 19.0 ✓

    # ── En-têtes 2 niveaux ──
    td = [
        ['N°', 'Désignation', 'Nombre', 'Base', 'Part Salariale', '', '', 'Part Patronale', '', 'Montant en GNF'],
        ['',   '',            '',       '',     'Taux', 'Gain', 'Retenue', 'Taux', 'Retenue', ''],
    ]

    # ── Gains ──
    num = 1
    for g in gains:
        nbre  = f"{g.nombre:g}" if g.nombre and g.nombre != 1 else ""
        base  = _fmt(g.base)  if g.base  else ""
        taux  = f"{g.taux}%"  if g.taux  else ""
        mnt   = _fmt0(g.montant)
        td.append([str(num), g.rubrique.libelle_rubrique[:32], nbre, base, taux, mnt, '', '', '', ''])
        num += 1

    # ── HS si non déjà dans gains ──
    hs_30   = float(getattr(bulletin, 'heures_supplementaires_30', 0) or 0)
    hs_60   = float(getattr(bulletin, 'heures_supplementaires_60', 0) or 0)
    prime_hs = float(getattr(bulletin, 'prime_heures_sup', 0) or 0)
    has_hs_in_gains = any('hs' in (g.rubrique.code_rubrique or '').lower() or
                          'heure' in (g.rubrique.libelle_rubrique or '').lower()
                          for g in gains)
    if not has_hs_in_gains:
        # Récupérer salaire de base pour calcul taux horaire
        _sal_base_hs = Decimal(str(bulletin.salaire_base or 0))
        if _sal_base_hs == 0:
            try:
                from .models import LigneBulletin as _LB
                from django.db.models import Q, Case, When, Value, IntegerField
                _lb = _LB.objects.filter(
                    bulletin=bulletin,
                    rubrique__type_rubrique='gain',
                ).filter(
                    Q(rubrique__categorie_rubrique='salaire_base') |
                    Q(rubrique__code_rubrique__icontains='SAL_BASE') |
                    Q(rubrique__code_rubrique__iexact='BASE') |
                    Q(rubrique__libelle_rubrique__icontains='Salaire de base')
                ).annotate(
                    _base_priority=Case(
                        When(rubrique__categorie_rubrique='salaire_base', then=Value(0)),
                        When(rubrique__code_rubrique__icontains='SAL_BASE', then=Value(1)),
                        When(rubrique__code_rubrique__iexact='BASE', then=Value(2)),
                        default=Value(9),
                        output_field=IntegerField(),
                    )
                ).order_by('_base_priority', 'ordre', 'id').first()
                if _lb: _sal_base_hs = Decimal(str(_lb.montant or 0))
            except Exception:
                pass
        _sal_h2 = _sal_base_hs / Decimal('173.33') if _sal_base_hs > 0 else Decimal('0')
        _hs_nuit2 = float(getattr(bulletin, 'heures_nuit', 0) or 0)
        _hs_fer2 = float(getattr(bulletin, 'heures_feries', 0) or 0)
        _hs_fer_n2 = float(getattr(bulletin, 'heures_feries_nuit', 0) or 0)
        mnt30  = int(_sal_h2 * Decimal(str(hs_30)) * Decimal('1.30')) if hs_30 > 0 else 0
        mnt60  = int(_sal_h2 * Decimal(str(hs_60)) * Decimal('1.60')) if hs_60 > 0 else 0
        mnt_nuit2 = int(_sal_h2 * Decimal(str(_hs_nuit2)) * Decimal('1.20')) if _hs_nuit2 > 0 else 0
        mnt_fer2 = int(_sal_h2 * Decimal(str(_hs_fer2)) * Decimal('1.60')) if _hs_fer2 > 0 else 0
        mnt_fer_n2 = int(_sal_h2 * Decimal(str(_hs_fer_n2)) * Decimal('2.00')) if _hs_fer_n2 > 0 else 0
        if hs_30 > 0:
            td.append([str(num), 'HS +30% (Art.221)', f'{hs_30:g}h', '', '130%', _fmt0(mnt30), '', '', '', ''])
            num += 1
        if hs_60 > 0:
            td.append([str(num), 'HS +60% (Art.221)', f'{hs_60:g}h', '', '160%', _fmt0(mnt60), '', '', '', ''])
            num += 1
        if _hs_nuit2 > 0:
            td.append([str(num), 'HS nuit +20% (Art.221)', f'{_hs_nuit2:g}h', '', '120%', _fmt0(mnt_nuit2), '', '', '', ''])
            num += 1
        if _hs_fer2 > 0:
            td.append([str(num), 'HS férié jour +60%', f'{_hs_fer2:g}h', '', '160%', _fmt0(mnt_fer2), '', '', '', ''])
            num += 1
        if _hs_fer_n2 > 0:
            td.append([str(num), 'HS férié nuit +100%', f'{_hs_fer_n2:g}h', '', '200%', _fmt0(mnt_fer_n2), '', '', '', ''])
            num += 1

    # ── Prime d'ancienneté (si absente des gains) ──
    has_anc = any('anciennet' in (g.rubrique.libelle_rubrique or '').lower() for g in gains)
    if not has_anc:
        td.append([str(num), "Prime d'ancienneté", '', '', '', '0', '', '', '', ''])
        num += 1

    # ── Manquant (retenue absence) ──
    absence = float(getattr(bulletin, 'retenue_absence', 0) or 0)
    td.append(['', 'Manquant', '', '', '', '', _fmt0(absence) if absence else '', '', '', ''])

    # ── Total brut ──
    td.append(['', 'Total brut', '', '', '', _fmt0(bulletin.salaire_brut), '', '', '', ''])

    # ── RTS ──
    base_rts = float(getattr(bulletin, 'base_rts', 0) or 0)
    taux_rts = float(getattr(bulletin, 'taux_effectif_rts', 0) or 0)
    td.append(['', f'RTS (Imp\u00f4t sur le revenu \u2013 moy. {taux_rts:.2f}%)' if taux_rts else 'RTS (Imp\u00f4t sur le revenu)', '', _fmt(base_rts), '', '', _fmt0(bulletin.irg), '', '', ''])

    # ── Versement Forfaitaire ──
    vf    = float(getattr(bulletin, 'versement_forfaitaire', 0) or 0)
    td.append(['', 'Versement forfaitaire', '', '', '', '', '', '6%', _fmt0(vf), ''])

    # ── TA ou ONFPP ──
    ta    = float(getattr(bulletin, 'taxe_apprentissage', 0) or 0)
    onfpp = float(getattr(bulletin, 'contribution_onfpp', 0) or 0)
    if onfpp > 0:
        td.append(['', 'ONFPP', '', '', '', '', '', '1,5%', _fmt0(onfpp), ''])
    elif ta > 0:
        td.append(['', 'Taxe Apprentissage', '', '', '', '', '', '2%', _fmt0(ta), ''])

    # ── CNSS ──
    base_cnss = min(float(bulletin.salaire_brut), 2500000)
    td.append(['', 'CNSS', '', '', '5%', _fmt0(bulletin.cnss_employe), '', '18%', _fmt0(bulletin.cnss_employeur), ''])

    # ── Total cotisation ──
    tot_sal = float(bulletin.cnss_employe) + float(bulletin.irg)
    tot_pat = vf + ta + onfpp + float(bulletin.cnss_employeur)
    td.append(['', 'Total cotisation', '', '', '', _fmt0(tot_sal), '', '', _fmt0(tot_pat), ''])

    RH_HDR = 14  # hauteur lignes d'en-tête (pt) — plus haute pour lisibilité
    RH     = 13  # hauteur lignes de données (pt)
    nb     = len(td)
    row_heights = [RH_HDR, RH_HDR] + [RH] * (nb - 2)

    main_t = Table(td, colWidths=col_w, rowHeights=row_heights)

    # ── Index des lignes spéciales ──
    idx_brut = next((i for i, r in enumerate(td) if r[1] == 'Total brut'), None)
    idx_cot  = next((i for i, r in enumerate(td) if r[1] == 'Total cotisation'), None)

    ts = [
        # En-tête fond gris clair
        ('BACKGROUND',    (0, 0), (-1, 1),  colors.HexColor('#d8d8d8')),
        ('FONTNAME',      (0, 0), (-1, 1),  _FONT_BOLD),
        ('FONTSIZE',      (0, 0), (-1, 1),  7),
        ('FONTSIZE',      (0, 2), (-1, -1), 7),
        ('FONTNAME',      (0, 2), (-1, -1), _FONT_NORMAL),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        # Alignements
        ('ALIGN',         (0, 0), (-1,  1), 'CENTER'),   # en-têtes : centré
        ('ALIGN',         (0, 2), (0, -1),  'CENTER'),   # N° : centré
        ('ALIGN',         (1, 2), (1, -1),  'LEFT'),     # Désignation : gauche
        ('ALIGN',         (2, 2), (2, -1),  'CENTER'),   # Nombre : centré
        ('ALIGN',         (3, 2), (-1, -1), 'RIGHT'),    # colonnes numériques : droite
        # Bordures
        ('GRID',          (0, 0), (-1, -1), 0.35, colors.black),
        # Padding
        ('LEFTPADDING',   (0, 0), (-1, -1), 2),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        # Spans en-tête (fusionner les colonnes sur 2 lignes ou entre colonnes)
        ('SPAN', (0, 0), (0, 1)),   # N°
        ('SPAN', (1, 0), (1, 1)),   # Désignation
        ('SPAN', (2, 0), (2, 1)),   # Nombre
        ('SPAN', (3, 0), (3, 1)),   # Base
        ('SPAN', (4, 0), (6, 0)),   # Part Salariale (cols 4-6)
        ('SPAN', (7, 0), (8, 0)),   # Part Patronale (cols 7-8)
        ('SPAN', (9, 0), (9, 1)),   # Montant en GNF
    ]
    if idx_brut is not None:
        ts += [('FONTNAME',   (0, idx_brut), (-1, idx_brut), _FONT_BOLD),
               ('BACKGROUND', (0, idx_brut), (-1, idx_brut), colors.HexColor('#e8e8e8'))]
    if idx_cot is not None:
        ts += [('FONTNAME',   (0, idx_cot),  (-1, idx_cot),  _FONT_BOLD),
               ('BACKGROUND', (0, idx_cot),  (-1, idx_cot),  colors.HexColor('#e8e8e8'))]

    main_t.setStyle(TableStyle(ts))
    mt_h = RH_HDR * 2 + RH * (nb - 2)
    main_t.wrapOn(p, width, height)
    main_t.drawOn(p, margin_x, y - mt_h)
    y -= mt_h + 0.4 * cm

    # ════════════════════════════════════════════════════════════════════════
    # PIED RÉCAPITULATIF
    # ════════════════════════════════════════════════════════════════════════
    # Vérifier espace pour le récap + signatures + pied de page (~6cm)
    sdbk_footer_zone = 6.0 * cm
    if y - sdbk_footer_zone < 0:
        p.showPage()
        y = height - 1.0 * cm
        p.setFont(_FONT_BOLD, 9)
        p.setFillColor(colors.black)
        p.drawString(margin_x, y, f"BULLETIN DE PAIE \u2014 {bulletin.numero_bulletin} (suite)")
        p.setLineWidth(1)
        p.line(margin_x, y - 0.15 * cm, width - margin_x, y - 0.15 * cm)
        y -= 0.50 * cm

    charge_sal = float(bulletin.cnss_employe) + float(bulletin.irg)
    charge_pat = vf + ta + onfpp + float(bulletin.cnss_employeur)
    avnat      = float(getattr(bulletin, 'avantage_nature', 0) or 0)
    net_imp    = float(getattr(bulletin, 'base_rts', 0) or 0)

    per_str  = bulletin.periode.date_debut.strftime('%d/%m/%y') if bulletin.periode and bulletin.periode.date_debut else ''
    ann_str  = str(bulletin.annee_paie)

    # Boîte « Net à payer » : largeur fixe 4.5 cm à droite
    NET_BOX_W = 4.5 * cm
    fc_total  = table_w - NET_BOX_W          # largeur du tableau récap
    # Répartir fc_total entre 7 colonnes proportionnellement
    fc_w = [
        fc_total * 0.158,   # Période
        fc_total * 0.097,   # Année
        fc_total * 0.172,   # S.Brut
        fc_total * 0.145,   # Charge Salariale
        fc_total * 0.152,   # Charge Patronale
        fc_total * 0.130,   # Avan. nature
        fc_total * 0.146,   # Net Imposable
    ]

    fd = [
        ['Période', 'Année', 'S. Brut', 'Ch.\nSalariale', 'Ch.\nPatronale', 'Av.\nNature', 'Net\nImpos.'],
        [per_str,   ann_str, _fmt0(bulletin.salaire_brut), _fmt0(charge_sal),
         _fmt0(charge_pat), _fmt0(avnat) if avnat else '0', _fmt0(net_imp)],
    ]
    FT_H_HDR = 22  # en-tête : 2 lignes de texte (2 × 6.5pt + leading + padding)
    FT_H_DAT = 15  # données  : 1 ligne
    ft = Table(fd, colWidths=fc_w, rowHeights=[FT_H_HDR, FT_H_DAT])
    ft.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (-1, 0),  _FONT_BOLD),
        ('FONTNAME',      (0, 1), (-1, 1),  _FONT_NORMAL),
        ('FONTSIZE',      (0, 0), (-1, -1), 6.5),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.black),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, 0),  'MIDDLE'),   # en-tête : centré verticalement
        ('VALIGN',        (0, 1), (-1, 1),  'MIDDLE'),   # données  : centré verticalement
        ('BACKGROUND',    (0, 0), (-1, 0),  colors.HexColor('#d8d8d8')),
        ('LEFTPADDING',   (0, 0), (-1, -1), 2),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 2),
        ('TOPPADDING',    (0, 0), (-1, 0),  0),   # pas de padding sur en-tête (texte 2 lignes)
        ('BOTTOMPADDING', (0, 0), (-1, 0),  0),
        ('TOPPADDING',    (0, 1), (-1, 1),  2),
        ('BOTTOMPADDING', (0, 1), (-1, 1),  2),
    ]))
    ft_h = FT_H_HDR + FT_H_DAT
    ft.wrapOn(p, width, height)
    ft.drawOn(p, margin_x, y - ft_h)

    # Boîte « Net à payer » — collée directement à droite du tableau
    nb_x = margin_x + fc_total
    nb_w = NET_BOX_W
    p.setStrokeColor(colors.black)
    p.setLineWidth(1.0)
    p.setFillColor(colors.HexColor('#f5f5f5'))
    p.rect(nb_x, y - ft_h, nb_w, ft_h, stroke=1, fill=1)
    p.setFillColor(colors.black)
    p.setFont(_FONT_BOLD, 7.5)
    p.drawCentredString(nb_x + nb_w / 2, y - 0.6 * cm, "Net à payer")
    p.setFont(_FONT_BOLD, 9)
    net_str = f"{int(bulletin.net_a_payer):,} GNF".replace(",", " ")
    p.drawCentredString(nb_x + nb_w / 2, y - 1.1 * cm, net_str)
    y -= ft_h + 0.5 * cm

    # ════════════════════════════════════════════════════════════════════════
    # SIGNATURES
    # ════════════════════════════════════════════════════════════════════════
    # Vérifier espace pour signatures + pied de page (~3.5cm)
    sig_zone = 3.5 * cm
    if y - sig_zone < 0:
        p.showPage()
        y = height - 1.5 * cm

    y -= 0.5 * cm
    p.setFont(_FONT_BOLD, 8)
    p.drawString(margin_x + 1 * cm, y, "Employeur")
    p.drawString(width - 5.5 * cm, y, "Employé(e)")
    y -= 0.3 * cm
    p.setFont(_FONT_NORMAL, 7)
    if entreprise:
        p.drawString(margin_x + 1 * cm, y, nom_ent)
    p.drawString(width - 5.5 * cm, y, f"{emp.nom} {emp.prenoms}")
    y -= 1.4 * cm
    p.setDash(3, 3)
    p.line(margin_x, y, margin_x + 5 * cm, y)
    p.line(width - 6 * cm, y, width - margin_x, y)
    p.setDash()

    # ════════════════════════════════════════════════════════════════════════
    # PIED DE PAGE
    # ════════════════════════════════════════════════════════════════════════
    p.setFont(_FONT_NORMAL, 6)
    p.drawCentredString(width / 2, 1.5 * cm, "Ce bulletin est conforme à la législation guinéenne en vigueur.")
    if entreprise:
        p.drawCentredString(width / 2, 1.1 * cm,
            f"{nom_ent} — {entreprise.adresse or ''} — Tél: {entreprise.telephone or ''}")
    p.drawCentredString(width / 2, 0.7 * cm,
        f"Document généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()

