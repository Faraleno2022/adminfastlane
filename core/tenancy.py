"""Isolation des données par entreprise (modules Flotte, Ventes…).

Chaque requête authentifiée positionne l'entreprise de l'utilisateur dans une
variable de contexte (``TenancyMiddleware``). Les managers des modèles qui
héritent de ``EntrepriseModel`` filtrent automatiquement dessus : aucune vue,
formulaire ou service ne peut donc lire ou écrire les données d'une autre
entreprise, même s'il oublie de filtrer.

Valeurs possibles de l'entreprise courante :
- ``NON_DEFINIE`` : hors requête (shell, commandes, tests) -> aucun filtre ;
- ``None``        : utilisateur sans entreprise -> aucune donnée visible ;
- une ``Entreprise`` : filtre sur cette entreprise.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import models


class _NonDefinie:
    def __repr__(self):
        return "NON_DEFINIE"

    def __bool__(self):
        return False


NON_DEFINIE = _NonDefinie()

_entreprise = ContextVar("entreprise_courante", default=NON_DEFINIE)


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


class TenancyMiddleware:
    """Positionne l'entreprise de l'utilisateur connecté pour la durée de la requête.

    À placer après ``AuthenticationMiddleware``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        entreprise = None
        if user is not None and user.is_authenticated:
            entreprise = getattr(user, "entreprise", None)
        jeton = definir_entreprise(entreprise)
        try:
            return self.get_response(request)
        finally:
            reinitialiser(jeton)


def filtrer_entreprise(qs):
    """Applique le filtre de l'entreprise courante à un queryset."""
    entreprise = entreprise_courante()
    if entreprise is NON_DEFINIE:
        return qs
    if entreprise is None:
        return qs.none()
    return qs.filter(entreprise=entreprise)


class EntrepriseManager(models.Manager):
    """Manager limité à l'entreprise courante."""

    def get_queryset(self):
        return filtrer_entreprise(super().get_queryset())


class EntrepriseModel(models.Model):
    """Base abstraite : rattache chaque enregistrement à l'entreprise courante."""

    entreprise = models.ForeignKey(
        "core.Entreprise", on_delete=models.CASCADE, editable=False, related_name="+",
    )

    objects = EntrepriseManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.entreprise_id is None:
            entreprise = entreprise_courante()
            if not entreprise:
                raise ValueError("Entreprise requise pour enregistrer cet objet.")
            self.entreprise = entreprise
        super().save(*args, **kwargs)
