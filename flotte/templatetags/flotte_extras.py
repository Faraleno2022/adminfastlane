import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def map_chauffeur_vehicule():
    """
    JSON {id_chauffeur: id_vehicule} d'après les chauffeurs (principal puis
    second) de chaque véhicule. Sert à pré-remplir le véhicule quand on
    choisit le chauffeur, comme la RECHERCHEV du classeur d'origine.
    """
    from flotte.models import Vehicule

    data = {}
    for champ in ("chauffeur_actuel", "chauffeur_secondaire"):
        for v in Vehicule.objects.exclude(**{champ: None}).values("pk", champ):
            data.setdefault(str(v[champ]), str(v["pk"]))
    return mark_safe(json.dumps(data))


@register.filter
def call_attr(obj, attr_name):
    """
    Résout dynamiquement un attribut ou une méthode par son nom.

    Permet aux vues liste génériques de déclarer leurs colonnes sous forme
    de chaînes (ex. "get_type_engin_display", "vehicule", "montant_ttc").
    Retourne une chaîne vide pour les valeurs nulles.
    """
    try:
        value = getattr(obj, attr_name)
    except AttributeError:
        return ""
    if callable(value):
        try:
            value = value()
        except Exception:
            return ""
    if value is None:
        return ""
    if value is True:
        return "Oui"
    if value is False:
        return "Non"
    return value
