"""Mixins et vues génériques CRUD partagés par les modules de saisie."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .permissions import peut_gerer_referentiel, peut_saisir


class RoleRequisMixin(LoginRequiredMixin):
    """
    Accès réservé aux utilisateurs connectés.

    Les vues de modification exigent en plus le rôle de saisie ; le contrôle
    fin par rôle est appliqué via ``PeutSaisirMixin`` / ``AdminRequisMixin``.
    """


class PeutSaisirMixin:
    """Autorise la création/modification aux rôles 'admin' et 'saisie'."""

    def dispatch(self, request, *args, **kwargs):
        if peut_saisir(request.user):
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied("Vous n'avez pas le droit de modifier ces données.")


class AdminRequisMixin:
    """Réserve la gestion du référentiel au rôle 'admin' (ou superutilisateur)."""

    def dispatch(self, request, *args, **kwargs):
        if peut_gerer_referentiel(request.user):
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied("Seul un administrateur peut gérer le référentiel.")


class BaseListe(RoleRequisMixin, ListView):
    """Liste générique : n'affiche que les enregistrements vivants."""

    template_name = "flotte/liste.html"
    paginate_by = 25
    context_object_name = "objets"
    titre = ""
    colonnes: list = []          # [(label, attribut_ou_methode), ...]
    url_creer = None
    url_modifier = None
    url_supprimer = None
    url_detail = None            # bouton de consultation (visible par tous)
    libelle_detail = "Détail"
    # Droit requis pour éditer depuis cette liste : "saisir" ou "referentiel".
    permission_edition = "saisir"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.permission_edition == "referentiel":
            peut_editer = peut_gerer_referentiel(self.request.user)
        else:
            peut_editer = peut_saisir(self.request.user)
        ctx.update(
            titre=self.titre or self.model._meta.verbose_name_plural,
            colonnes=self.colonnes,
            url_creer=self.url_creer,
            url_modifier=self.url_modifier,
            url_supprimer=self.url_supprimer,
            url_detail=self.url_detail,
            libelle_detail=self.libelle_detail,
            peut_editer=peut_editer,
        )
        return ctx


class BaseCreer(RoleRequisMixin, PeutSaisirMixin, CreateView):
    template_name = "flotte/formulaire.html"
    titre = "Ajouter"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titre"] = self.titre
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Enregistrement créé.")
        return super().form_valid(form)


class BaseModifier(RoleRequisMixin, PeutSaisirMixin, UpdateView):
    template_name = "flotte/formulaire.html"
    titre = "Modifier"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titre"] = self.titre
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Enregistrement mis à jour.")
        return super().form_valid(form)


class BaseSupprimer(RoleRequisMixin, PeutSaisirMixin, DeleteView):
    template_name = "flotte/confirmer_suppression.html"

    def form_valid(self, form):
        messages.success(self.request, "Enregistrement supprimé.")
        return super().form_valid(form)


# --- Variantes réservées au référentiel (admin uniquement) ---------------
class BaseCreerReferentiel(RoleRequisMixin, AdminRequisMixin, CreateView):
    template_name = "flotte/formulaire.html"
    titre = "Ajouter"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titre"] = self.titre
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Enregistrement créé.")
        return super().form_valid(form)


class BaseModifierReferentiel(RoleRequisMixin, AdminRequisMixin, UpdateView):
    template_name = "flotte/formulaire.html"
    titre = "Modifier"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titre"] = self.titre
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Enregistrement mis à jour.")
        return super().form_valid(form)


class BaseSupprimerReferentiel(RoleRequisMixin, AdminRequisMixin, DeleteView):
    template_name = "flotte/confirmer_suppression.html"

    def form_valid(self, form):
        messages.success(self.request, "Enregistrement supprimé.")
        return super().form_valid(form)
