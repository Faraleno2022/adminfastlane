from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def gnf(valeur):
    """1250000 -> « 1 250 000 GNF »."""
    try:
        n = Decimal(valeur or 0)
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    return f"{n:,.0f}".replace(",", " ") + " GNF"


@register.filter
def nb(valeur):
    """Quantité sans zéros inutiles : 12.500 -> « 12,5 »."""
    try:
        n = Decimal(valeur or 0)
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    texte = format(n.normalize(), "f")
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte.replace(".", ",")
