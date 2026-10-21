"""Génération du rapport PDF de synthèse (reportlab)."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import services_dashboard as services


def _fmt(v):
    if v is None:
        return "n/d"
    if isinstance(v, float):
        return f"{v:,.0f}".replace(",", " ")
    return str(v)


def _style_table(data, entete=True):
    t = Table(data, repeatRows=1 if entete else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if entete:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D6EFD")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style))
    return t


def construire(annee=None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm, bottomMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Gestion de flotte — Rapport de synthèse", styles["Title"]))
    elements.append(Paragraph(f"Année : {annee or 'Toutes'}", styles["Normal"]))
    elements.append(Spacer(1, 0.5 * cm))

    # Synthèse
    t = services.totaux(annee)
    synth = [
        ["Indicateur", "Valeur"],
        ["Carburant véhicules", _fmt(float(t["carburant_vehicules"]))],
        ["Carburant Poclain", _fmt(float(t["carburant_poclain"]))],
        ["Entretien", _fmt(float(t["montant_entretien"]))],
        ["Autres dépenses", _fmt(float(t["montant_autres"]))],
        ["TOTAL DÉPENSES", _fmt(float(t["depenses_totales"]))],
        ["Voyages camions", _fmt(float(t["recettes_voyages"]))],
        ["Porte-char", _fmt(float(t["recettes_portechar"]))],
        ["Chargements Poclain", _fmt(float(t["recettes_poclain"]))],
        ["TOTAL RECETTES", _fmt(float(t["recettes_totales"]))],
        ["RÉSULTAT (recettes − dépenses)", _fmt(float(t["resultat"]))],
        ["Carburant consommé (litres)", _fmt(float(t["litres_carburant"]))],
        ["Nombre de voyages", _fmt(t["nb_voyages"])],
    ]
    elements.append(Paragraph("Synthèse générale", styles["Heading2"]))
    elements.append(_style_table(synth))
    elements.append(Spacer(1, 0.6 * cm))

    # Analyse par véhicule
    elements.append(Paragraph("Analyse par véhicule", styles["Heading2"]))
    entete = [
        "Véhicule", "Distance", "Litres", "L/100km", "Carburant",
        "Entretien", "Coût/km carb.", "Coût/km ent.", "Coût total/km", "Voyages",
    ]
    lignes = [entete]
    for l in services.analyse_vehicules(annee):
        lignes.append([
            l["vehicule"], _fmt(l["distance"]), _fmt(l["litres"]), _fmt(l["l_100km"]),
            _fmt(l["montant_carburant"]), _fmt(l["montant_entretien"]),
            _fmt(l["cout_carburant_km"]), _fmt(l["cout_entretien_km"]),
            _fmt(l["cout_total_km"]), _fmt(l["nb_voyages"]),
        ])
    if len(lignes) == 1:
        lignes.append(["—"] * len(entete))
    elements.append(_style_table(lignes))

    doc.build(elements)
    return buf.getvalue()
