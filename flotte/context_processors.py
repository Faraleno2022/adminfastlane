from django.conf import settings

from .permissions import peut_gerer_referentiel, peut_saisir


def flotte(request):
    """Variables du module Flotte (rapports imprimés, droits)."""
    user = getattr(request, "user", None)
    if user is None or not request.path.startswith("/flotte/"):
        return {}
    entreprise = getattr(user, "entreprise", None)
    nom = getattr(entreprise, "nom_entreprise", "") or getattr(settings, "ENTREPRISE_NOM", "")
    contact = " · ".join(
        x for x in (getattr(entreprise, "email", ""), getattr(entreprise, "telephone", "")) if x
    ) or getattr(settings, "ENTREPRISE_CONTACT", "")
    return {
        "PEUT_SAISIR": peut_saisir(user),
        "PEUT_GERER_REFERENTIEL": peut_gerer_referentiel(user),
        "ENTREPRISE_NOM": nom,
        "ENTREPRISE_CONTACT": contact,
        "RAPPORT_LIEU": getattr(settings, "RAPPORT_LIEU", ""),
        "RAPPORT_SIGNATAIRE_TITRE": getattr(settings, "RAPPORT_SIGNATAIRE_TITRE", ""),
        "RAPPORT_SIGNATAIRE_NOM": getattr(settings, "RAPPORT_SIGNATAIRE_NOM", ""),
    }
