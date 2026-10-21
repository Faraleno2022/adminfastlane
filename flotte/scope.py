"""Entreprise « courante » pour l'isolation des données de la flotte.

Chaque requête authentifiée positionne l'entreprise de l'utilisateur dans une
variable de contexte (voir ``middleware.FlotteEntrepriseMiddleware``). Les
managers des modèles de la flotte filtrent automatiquement dessus : aucune vue,
formulaire ou service ne peut donc lire ou écrire les données d'une autre
entreprise, même s'il oublie de filtrer.

Valeurs possibles :
- ``NON_DEFINIE`` : hors requête (shell, commandes, tests) -> aucun filtre ;
- ``None``        : utilisateur sans entreprise -> aucune donnée visible ;
- une ``Entreprise`` : filtre sur cette entreprise.
"""
from contextlib import contextmanager
from contextvars import ContextVar


class _NonDefinie:
    def __repr__(self):
        return "NON_DEFINIE"

    def __bool__(self):
        return False


NON_DEFINIE = _NonDefinie()

_entreprise = ContextVar("flotte_entreprise", default=NON_DEFINIE)


def entreprise_courante():
    return _entreprise.get()


def definir_entreprise(entreprise):
    """Positionne l'entreprise courante ; renvoie le jeton pour ``reinitialiser``."""
    return _entreprise.set(entreprise)


def reinitialiser(jeton):
    _entreprise.reset(jeton)


@contextmanager
def pour_entreprise(entreprise):
    """Exécute un bloc dans le périmètre d'une entreprise (commandes, tests)."""
    jeton = _entreprise.set(entreprise)
    try:
        yield entreprise
    finally:
        _entreprise.reset(jeton)
