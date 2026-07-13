"""
Vues pour la gestion de la TVA et des déclarations fiscales.

Fournissent:
- Gestion des régimes TVA (création, modification, listing)
- Gestion des déclarations TVA (CRUD complet)
- Validation et dépôt des déclarations
- Gestion des lignes de déclaration
- Gestion des taux TVA
"""

from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, View
)
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
import logging

from ...models import (
    RegimeTVA, TauxTVA, DeclarationTVA, LigneDeclarationTVA
)
from ...services.fiscalite_service import FiscaliteService
from ...services.calcul_tva_service import CalculTVAService
from ...mixins.views import ComptabiliteAccessMixin, EntrepriseFilterMixin, AuditMixin
from ...forms import (
    RegimeTVAForm, TauxTVAForm, DeclarationTVAForm,
    LigneDeclarationTVAForm, LigneDeclarationTVAFormSet
)

logger = logging.getLogger(__name__)


# ============================================================================
# RÉGIME TVA VIEWS
# ============================================================================

class RegimeTVAListView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    ListView
):
    """Liste les régimes TVA disponibles pour l'entreprise."""
    
    model = RegimeTVA
    template_name = 'comptabilite/fiscalite/regime_tva_list.html'
    context_object_name = 'regimes'
    paginate_by = 25
    
    def get_queryset(self):
        qs = super().get_queryset()
        # Trier par ordre de date décroissante
        return qs.order_by('-date_creation')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Régimes TVA")
        context['breadcrumbs'] = [
            {'label': _('Accueil'), 'url': 'comptabilite:dashboard'},
            {'label': _('Fiscalité'), 'url': 'comptabilite:tva_dashboard'},
            {'label': _('Régimes TVA'), 'url': None},
        ]
        return context


class RegimeTVADetailView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    DetailView
):
    """Affiche les détails d'un régime TVA."""
    
    model = RegimeTVA
    template_name = 'comptabilite/fiscalite/regime_tva_detail.html'
    context_object_name = 'regime'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Détail du régime TVA")
        context['taux_list'] = self.object.taux.all()
        context['breadcrumbs'] = [
            {'label': _('Accueil'), 'url': 'comptabilite:dashboard'},
            {'label': _('Fiscalité'), 'url': 'comptabilite:tva_dashboard'},
            {'label': _('Régimes TVA'), 'url': 'comptabilite:regime_tva_list'},
            {'label': self.object.nom, 'url': None},
        ]
        return context


class RegimeTVACreateView(
    ComptabiliteAccessMixin,
    AuditMixin,
    SuccessMessageMixin,
    CreateView
):
    """Crée un nouveau régime TVA."""
    
    model = RegimeTVA
    form_class = RegimeTVAForm
    template_name = 'comptabilite/fiscalite/regime_tva_form.html'
    success_url = reverse_lazy('comptabilite:regime_tva_list')
    success_message = _("Régime TVA '%(nom)s' créé avec succès")
    
    def form_valid(self, form):
        form.instance.entreprise = self.request.user.entreprise
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Créer un régime TVA")
        context['action'] = 'create'
        return context
    
    def get_audit_action(self):
        return 'create'
    
    def get_audit_module(self):
        return 'fiscalite'


class RegimeTVAUpdateView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    AuditMixin,
    SuccessMessageMixin,
    UpdateView
):
    """Modifie un régime TVA existant."""
    
    model = RegimeTVA
    form_class = RegimeTVAForm
    template_name = 'comptabilite/fiscalite/regime_tva_form.html'
    success_url = reverse_lazy('comptabilite:regime_tva_list')
    success_message = _("Régime TVA '%(nom)s' modifié avec succès")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Modifier le régime TVA")
        context['action'] = 'update'
        return context
    
    def get_audit_action(self):
        return 'update'
    
    def get_audit_module(self):
        return 'fiscalite'


# ============================================================================
# TAUX TVA VIEWS
# ============================================================================

class TauxTVAListView(
    ComptabiliteAccessMixin,
    ListView
):
    """Liste tous les taux TVA."""
    
    model = TauxTVA
    template_name = 'comptabilite/fiscalite/taux_tva_list.html'
    context_object_name = 'taux_list'
    paginate_by = 50
    
    def get_queryset(self):
        qs = super().get_queryset()
        # Filtrer par entreprise
        return qs.filter(
            entreprise=self.request.user.entreprise
        ).order_by('-date_debut')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Taux TVA")
        return context


class TauxTVACreateView(
    ComptabiliteAccessMixin,
    AuditMixin,
    SuccessMessageMixin,
    CreateView
):
    """Crée un nouveau taux TVA."""
    
    model = TauxTVA
    form_class = TauxTVAForm
    template_name = 'comptabilite/fiscalite/taux_tva_form.html'
    success_url = reverse_lazy('comptabilite:taux_tva_list')
    success_message = _("Taux TVA créé avec succès")
    
    def form_valid(self, form):
        form.instance.entreprise = self.request.user.entreprise
        return super().form_valid(form)


class TauxTVAUpdateView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    AuditMixin,
    SuccessMessageMixin,
    UpdateView
):
    """Modifie un taux TVA existant."""
    
    model = TauxTVA
    template_name = 'comptabilite/fiscalite/taux_tva_form.html'
    form_class = TauxTVAForm
    success_url = reverse_lazy('comptabilite:taux_tva_list')
    success_message = _("Taux TVA modifié avec succès")


# ============================================================================
# DÉCLARATION TVA VIEWS
# ============================================================================

class DeclarationTVAListView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    ListView
):
    """Liste les déclarations TVA de l'entreprise."""
    
    model = DeclarationTVA
    template_name = 'comptabilite/fiscalite/declaration_tva_list.html'
    context_object_name = 'declarations'
    paginate_by = 25
    
    def get_queryset(self):
        qs = super().get_queryset()
        # Filtrer par statut si fourni
        statut = self.request.GET.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return qs.order_by('-periode_debut')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Déclarations TVA")
        context['statuts'] = DeclarationTVA.STATUT_CHOICES
        context['statut_actuel'] = self.request.GET.get('statut', '')
        context['breadcrumbs'] = [
            {'label': _('Accueil'), 'url': 'comptabilite:dashboard'},
            {'label': _('Fiscalité'), 'url': 'comptabilite:tva_dashboard'},
            {'label': _('Déclarations TVA'), 'url': None},
        ]
        return context


class DeclarationTVADetailView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    DetailView
):
    """Affiche les détails d'une déclaration TVA."""
    
    model = DeclarationTVA
    template_name = 'comptabilite/fiscalite/declaration_tva_detail.html'
    context_object_name = 'declaration'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Déclaration TVA - %(periode)s") % {
            'periode': self.object.get_periode_display()
        }
        context['lignes'] = self.object.lignes.all()
        context['can_edit'] = self.object.statut == DeclarationTVA.STATUT_BROUILLON
        context['can_validate'] = self.object.statut == DeclarationTVA.STATUT_BROUILLON
        context['can_depot'] = self.object.statut == DeclarationTVA.STATUT_VALIDEE
        context['montant_total_ht'] = sum(
            ligne.montant_ht for ligne in context['lignes']
        )
        context['montant_total_tva'] = sum(
            ligne.montant_tva for ligne in context['lignes']
        )
        context['montant_total_ttc'] = sum(
            ligne.montant_ttc for ligne in context['lignes']
        )
        return context


class DeclarationTVACreateView(
    ComptabiliteAccessMixin,
    AuditMixin,
    SuccessMessageMixin,
    CreateView
):
    """Crée une nouvelle déclaration TVA."""
    
    model = DeclarationTVA
    form_class = DeclarationTVAForm
    template_name = 'comptabilite/fiscalite/declaration_tva_form.html'
    success_message = _("Déclaration TVA créée avec succès")
    
    def form_valid(self, form):
        form.instance.entreprise = self.request.user.entreprise
        form.instance.statut = DeclarationTVA.STATUT_BROUILLON
        response = super().form_valid(form)
        messages.success(
            self.request,
            _("Déclaration créée. Vous pouvez maintenant ajouter des lignes.")
        )
        return response
    
    def get_success_url(self):
        return self.object.get_absolute_url()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Créer une déclaration TVA")
        context['action'] = 'create'
        return context


class DeclarationTVAUpdateView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    AuditMixin,
    SuccessMessageMixin,
    UpdateView
):
    """Modifie une déclaration TVA existante."""
    
    model = DeclarationTVA
    form_class = DeclarationTVAForm
    template_name = 'comptabilite/fiscalite/declaration_tva_form.html'
    success_message = _("Déclaration TVA modifiée avec succès")
    
    def form_valid(self, form):
        # Vérifier que la déclaration est en brouillon
        if self.object.statut != DeclarationTVA.STATUT_BROUILLON:
            messages.error(
                self.request,
                _("Impossible de modifier une déclaration non-brouillon")
            )
            return redirect(self.object.get_absolute_url())
        return super().form_valid(form)
    
    def get_success_url(self):
        return self.object.get_absolute_url()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titre'] = _("Modifier la déclaration TVA")
        context['action'] = 'update'
        context['can_edit'] = self.object.statut == DeclarationTVA.STATUT_BROUILLON
        return context


class DeclarationTVAValidateView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    View
):
    """Valide une déclaration TVA."""
    
    def post(self, request, pk):
        declaration = get_object_or_404(
            DeclarationTVA,
            pk=pk,
            entreprise=request.user.entreprise
        )
        
        if declaration.statut != DeclarationTVA.STATUT_BROUILLON:
            messages.error(
                request,
                _("Impossible de valider une déclaration non-brouillon")
            )
            return redirect(declaration.get_absolute_url())
        
        try:
            service = FiscaliteService(request.user)
            success, errors = service.valider_declaration(declaration)
            
            if success:
                declaration.statut = DeclarationTVA.STATUT_VALIDEE
                declaration.date_validation = timezone.now()
                declaration.save()
                messages.success(
                    request,
                    _("Déclaration TVA validée avec succès")
                )
            else:
                messages.error(
                    request,
                    _("Erreurs de validation: ") + ", ".join(errors)
                )
        except Exception as e:
            logger.error(f"Erreur validation déclaration: {e}")
            messages.error(request, _("Erreur lors de la validation"))
        
        return redirect(declaration.get_absolute_url())


class DeclarationTVADepotView(
    ComptabiliteAccessMixin,
    EntrepriseFilterMixin,
    View
):
    """Dépose une déclaration TVA auprès de l'administration."""
    
    def post(self, request, pk):
        declaration = get_object_or_404(
            DeclarationTVA,
            pk=pk,
            entreprise=request.user.entreprise
        )
        
        if declaration.statut != DeclarationTVA.STATUT_VALIDEE:
            messages.error(
                request,
                _("Seules les déclarations validées peuvent être déposées")
            )
            return redirect(declaration.get_absolute_url())
        
        try:
            service = FiscaliteService(request.user)
            success, errors = service.deposer_declaration(declaration)
            
            if success:
                declaration.statut = DeclarationTVA.STATUT_DEPOSEE
                declaration.date_depot = timezone.now()
                declaration.save()
                messages.success(
                    request,
                    _("Déclaration TVA déposée avec succès")
                )
            else:
                messages.error(
                    request,
                    _("Erreurs de dépôt: ") + ", ".join(errors)
                )
        except Exception as e:
            logger.error(f"Erreur dépôt déclaration: {e}")
            messages.error(request, _("Erreur lors du dépôt"))
        
        return redirect(declaration.get_absolute_url())


# ============================================================================
# LIGNE DÉCLARATION TVA VIEWS
# ============================================================================

class LigneDeclarationTVACreateView(
    ComptabiliteAccessMixin,
    AuditMixin,
    SuccessMessageMixin,
    CreateView
):
    """Ajoute une ligne à une déclaration TVA."""
    
    model = LigneDeclarationTVA
    form_class = LigneDeclarationTVAForm
    template_name = 'comptabilite/fiscalite/ligne_declaration_tva_form.html'
    success_message = _("Ligne ajoutée avec succès")
    
    def dispatch(self, request, *args, **kwargs):
        # Récupérer la déclaration parente
        self.declaration_id = kwargs.get('declaration_id')
        self.declaration = get_object_or_404(
            DeclarationTVA,
            pk=self.declaration_id,
            entreprise=request.user.entreprise
        )
        
        # Vérifier que la déclaration est en brouillon
        if self.declaration.statut != DeclarationTVA.STATUT_BROUILLON:
            messages.error(
                request,
                _("Impossible d'ajouter des lignes à une déclaration non-brouillon")
            )
            return redirect(self.declaration.get_absolute_url())
        
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.declaration = self.declaration
        response = super().form_valid(form)
        
        # Recalculer et enregistrer les totaux (champs réels du modèle DeclarationTVA)
        service = CalculTVAService(self.request.user)
        try:
            service.appliquer_montants_declaration(self.declaration)
        except Exception as e:
            logger.error(f"Erreur recalcul montants: {e}")

        return response

    def get_success_url(self):
        return self.declaration.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['declaration'] = self.declaration
        context['titre'] = _("Ajouter une ligne")
        return context


class LigneDeclarationTVAUpdateView(
    ComptabiliteAccessMixin,
    AuditMixin,
    SuccessMessageMixin,
    UpdateView
):
    """Modifie une ligne de déclaration TVA."""
    
    model = LigneDeclarationTVA
    form_class = LigneDeclarationTVAForm
    template_name = 'comptabilite/fiscalite/ligne_declaration_tva_form.html'
    success_message = _("Ligne modifiée avec succès")
    
    def dispatch(self, request, *args, **kwargs):
        # Récupérer la ligne et vérifier l'accès
        self.object = self.get_object()
        if self.object.declaration.entreprise != request.user.entreprise:
            messages.error(request, _("Accès refusé"))
            return redirect('comptabilite:dashboard')
        
        if self.object.declaration.statut != DeclarationTVA.STATUT_BROUILLON:
            messages.error(
                request,
                _("Impossible de modifier une ligne d'une déclaration non-brouillon")
            )
            return redirect(self.object.declaration.get_absolute_url())
        
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Recalculer et enregistrer les totaux (champs réels du modèle DeclarationTVA)
        service = CalculTVAService(self.request.user)
        try:
            service.appliquer_montants_declaration(self.object.declaration)
        except Exception as e:
            logger.error(f"Erreur recalcul montants: {e}")

        return response
    
    def get_success_url(self):
        return self.object.declaration.get_absolute_url()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['declaration'] = self.object.declaration
        context['titre'] = _("Modifier la ligne")
        return context


class LigneDeclarationTVADeleteView(
    ComptabiliteAccessMixin,
    DeleteView
):
    """Supprime une ligne de déclaration TVA."""
    
    model = LigneDeclarationTVA
    template_name = 'comptabilite/fiscalite/ligne_declaration_tva_confirm_delete.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Récupérer la ligne et vérifier l'accès
        self.object = self.get_object()
        if self.object.declaration.entreprise != request.user.entreprise:
            messages.error(request, _("Accès refusé"))
            return redirect('comptabilite:dashboard')
        
        if self.object.declaration.statut != DeclarationTVA.STATUT_BROUILLON:
            messages.error(
                request,
                _("Impossible de supprimer une ligne d'une déclaration non-brouillon")
            )
            return redirect(self.object.declaration.get_absolute_url())
        
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        declaration = self.object.declaration
        response = super().delete(request, *args, **kwargs)
        
        # Recalculer et enregistrer les totaux (champs réels du modèle DeclarationTVA)
        service = CalculTVAService(request.user)
        try:
            service.appliquer_montants_declaration(declaration)
        except Exception as e:
            logger.error(f"Erreur recalcul montants: {e}")
        
        messages.success(request, _("Ligne supprimée avec succès"))
        return response
    
    def get_success_url(self):
        return self.object.declaration.get_absolute_url()
