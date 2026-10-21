from .scope import definir_entreprise, reinitialiser


class FlotteEntrepriseMiddleware:
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
