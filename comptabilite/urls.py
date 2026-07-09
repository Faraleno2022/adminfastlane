"""
URLs for the Comptabilité module - Comprehensive routing
This file organizes URLs for accounting operations, bank reconciliation, 
fiscal declarations, and audit operations across multiple phases.

Pattern structure:
- CompteBancaire: comptes/
- RapprochementBancaire: rapprochements/
- OperationBancaire: operations/
- Utility endpoints: /importer/, /exporter/, /ajax/
- Dashboards: /tableau-de-bord/
"""

from django.urls import path, include
from django.views.generic import TemplateView
# Importer les classes depuis les sous-modules avec des imports absolus
from comptabilite.views.rapprochements.views import (
    CompteBancaireListView, CompteBancaireDetailView, CompteBancaireCreateView, CompteBancaireUpdateView, CompteBancaireDeleteView,
    RapprochementListView, RapprochementDetailView, RapprochementCreateView, RapprochementUpdateView, RapprochementDeleteView,
    OperationImportView,
    LettrageView, LettrageAnnulationView, RapprochementFinalisationView,
)

# Importer les vues principales depuis views.py
from django.views.generic import TemplateView

# Utiliser des TemplateViews temporaires pour éviter les erreurs d'import
dashboard = TemplateView.as_view(template_name='comptabilite/dashboard.html')
# plan_comptable_list sera défini plus bas comme vue fonctionnelle
# journal_list sera défini plus bas comme vue fonctionnelle
# exercice_list sera défini plus bas comme vue fonctionnelle
# ecriture_list sera défini plus bas comme vue fonctionnelle
# tiers_list sera défini plus bas comme vue fonctionnelle
facture_list = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
reglement_list = TemplateView.as_view(template_name='comptabilite/coming_soon.html')

# Vues de création temporaires
plan_comptable_create = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
plan_comptable_detail = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
journal_create = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
journal_update = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
exercice_create = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
exercice_update = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
# Import des vraies vues depuis le fichier views.py principal
try:
    import os
    import importlib.util
    
    # NOTE: le dossier `comptabilite/views/` existe (package) et masque le fichier `comptabilite/views.py`.
    # On charge donc explicitement `views.py` avec un nom de module qualifié afin que les imports relatifs fonctionnent.
    base_dir = os.path.dirname(__file__)
    views_path = os.path.join(base_dir, 'views.py')
    if not os.path.exists(views_path):
        views_path = os.path.join(base_dir, 'views.pyc')
    spec = importlib.util.spec_from_file_location('comptabilite.views_legacy', views_path)
    comptabilite_views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comptabilite_views)
    
    # Utiliser les vraies vues
    ecriture_list_view = comptabilite_views.ecriture_list
    ecriture_create_view = comptabilite_views.ecriture_create
    ecriture_detail_view = comptabilite_views.ecriture_detail
    ecriture_update_view = comptabilite_views.ecriture_update
    dashboard_view = comptabilite_views.dashboard
    
    # Plan comptable
    plan_comptable_list_view = comptabilite_views.plan_comptable_list
    plan_comptable_create_view = comptabilite_views.plan_comptable_create
    plan_comptable_detail_view = comptabilite_views.plan_comptable_detail
    plan_comptable_update_view = comptabilite_views.plan_comptable_update
    plan_comptable_delete_view = comptabilite_views.plan_comptable_delete
    
    # Journaux / Exercices / Règlements
    journal_list_view = comptabilite_views.journal_list
    journal_create_view = comptabilite_views.journal_create
    journal_detail_view = comptabilite_views.journal_detail
    journal_update_view = comptabilite_views.journal_update
    journal_delete_view = comptabilite_views.journal_delete
    exercice_list_view = comptabilite_views.exercice_list
    exercice_create_view = comptabilite_views.exercice_create
    exercice_detail_view = comptabilite_views.exercice_detail
    exercice_update_view = comptabilite_views.exercice_update
    exercice_delete_view = comptabilite_views.exercice_delete
    reglement_list_view = comptabilite_views.reglement_list
    reglement_create_view = comptabilite_views.reglement_create
    reglement_detail_view = comptabilite_views.reglement_detail
    reglement_update_view = comptabilite_views.reglement_update
    reglement_delete_view = comptabilite_views.reglement_delete
    
    # Écritures - vues supplémentaires
    ecriture_delete_view = comptabilite_views.ecriture_delete
    ecriture_valider_view = comptabilite_views.ecriture_valider
    
    # Tiers - vue supplémentaire
    tiers_delete_view = comptabilite_views.tiers_delete
    
    # Factures - vues supplémentaires
    facture_delete_view = comptabilite_views.facture_delete
    facture_valider_view = comptabilite_views.facture_valider
    facture_print_view = comptabilite_views.facture_print

    # États financiers
    grand_livre_view = comptabilite_views.grand_livre
    grand_livre_pdf_view = comptabilite_views.grand_livre_pdf
    grand_livre_excel_view = comptabilite_views.grand_livre_excel
    balance_view = comptabilite_views.balance
    balance_pdf_view = comptabilite_views.balance_pdf
    balance_excel_view = comptabilite_views.balance_excel
    journal_general_view = comptabilite_views.journal_general
    bilan_view = comptabilite_views.bilan
    bilan_pdf_view = comptabilite_views.bilan_pdf
    compte_resultat_view = comptabilite_views.compte_resultat
    compte_resultat_pdf_view = comptabilite_views.compte_resultat_pdf
    compte_fournisseur_list_view = comptabilite_views.compte_fournisseur_list
    compte_fournisseur_detail_view = comptabilite_views.compte_fournisseur_detail
    compte_client_list_view = comptabilite_views.compte_client_list
    compte_client_detail_view = comptabilite_views.compte_client_detail
    tiers_list_view = comptabilite_views.tiers_list
    tiers_create_view = comptabilite_views.tiers_create
    tiers_detail_view = comptabilite_views.tiers_detail
    tiers_update_view = comptabilite_views.tiers_update
    facture_list_view = comptabilite_views.facture_list
    facture_create_view = comptabilite_views.facture_create
    facture_detail_view = comptabilite_views.facture_detail
    facture_update_view = comptabilite_views.facture_update
    
    # Vues vieillissement et impayés
    vieillissement_creances_view = comptabilite_views.vieillissement_creances
    impayes_clients_view = comptabilite_views.impayes_clients
    vieillissement_dettes_view = comptabilite_views.vieillissement_dettes
    impayes_fournisseurs_view = comptabilite_views.impayes_fournisseurs
    
    pass  # Import des vues comptabilite reussi
    
except Exception as e:
    # Fallback vers TemplateView si import échoue
    print(f"Import error: {e}")
    
    # Créer une vue simple pour le formulaire d'écriture
    from django.shortcuts import render, get_object_or_404
    from django.contrib.auth.decorators import login_required
    from django.contrib import messages
    from django import forms
    from comptabilite.models import PlanComptable, ExerciceComptable, Journal, EcritureComptable
    
    # Créer un formulaire simplifié inline pour éviter les problèmes d'import
    class SimpleEcritureForm(forms.ModelForm):
        class Meta:
            model = EcritureComptable
            fields = ['exercice', 'journal', 'numero_ecriture', 'date_ecriture', 'libelle']
            widgets = {
                'exercice': forms.Select(attrs={'class': 'form-select'}),
                'journal': forms.Select(attrs={'class': 'form-select'}),
                'numero_ecriture': forms.TextInput(attrs={'class': 'form-control'}),
                'date_ecriture': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                'libelle': forms.TextInput(attrs={'class': 'form-control'}),
            }
        
        def __init__(self, *args, entreprise=None, **kwargs):
            super().__init__(*args, **kwargs)
            if entreprise:
                self.fields['exercice'].queryset = ExerciceComptable.objects.filter(
                    entreprise=entreprise, statut='ouvert'
                )
                self.fields['journal'].queryset = Journal.objects.filter(
                    entreprise=entreprise, est_actif=True
                )
    
    @login_required
    def ecriture_create_view(request):
        """Vue simple pour créer une écriture comptable"""
        entreprise = request.user.entreprise
        
        if request.method == 'POST':
            form = SimpleEcritureForm(request.POST, entreprise=entreprise)
            if form.is_valid():
                # Traitement simple - pour l'instant juste afficher un message
                messages.success(request, "Formulaire soumis avec succès!")
                return render(request, 'comptabilite/ecritures/form.html', {
                    'form': form,
                    'comptes': PlanComptable.objects.filter(entreprise=entreprise, est_actif=True).order_by('numero_compte')
                })
        else:
            form = SimpleEcritureForm(entreprise=entreprise)
        
        comptes = PlanComptable.objects.filter(entreprise=entreprise, est_actif=True).order_by('numero_compte')
        
        return render(request, 'comptabilite/ecritures/form.html', {
            'form': form,
            'comptes': comptes,
        })
    
    # Vues fallback pour les autres
    ecriture_detail_view = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
    ecriture_update_view = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
    dashboard_view = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
    
    # Vue fonctionnelle pour la liste des écritures
    @login_required
    def ecriture_list_view(request):
        """Vue simple pour lister les écritures comptables"""
        entreprise = request.user.entreprise
        from comptabilite.models import EcritureComptable, LigneEcriture
        from django.db import models
        
        ecritures = EcritureComptable.objects.filter(entreprise=entreprise).order_by('-date_ecriture')
        
        # Calculer les statistiques
        total_ecritures = ecritures.count()
        total_debit = LigneEcriture.objects.filter(ecriture__entreprise=entreprise).aggregate(
            total=models.Sum('montant_debit')
        )['total'] or 0
        total_credit = LigneEcriture.objects.filter(ecriture__entreprise=entreprise).aggregate(
            total=models.Sum('montant_credit')
        )['total'] or 0
        
        return render(request, 'comptabilite/ecritures/ecriture_list.html', {
            'ecritures': ecritures,
            'total_ecritures': total_ecritures,
            'total_debit': total_debit,
            'total_credit': total_credit,
        })
    compte_fournisseur_list_view = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
    compte_fournisseur_detail_view = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
    # Les vues des comptes fournisseurs et clients sont définies ci-dessous
    
    # Vue fonctionnelle pour le plan comptable
    @login_required
    def plan_comptable_list_view(request):
        """Vue simple pour lister le plan comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import PlanComptable
        from django.db import models
        
        comptes = PlanComptable.objects.filter(entreprise=entreprise).order_by('numero_compte')
        
        # Calculer les statistiques
        total_comptes = comptes.count()
        comptes_actifs = comptes.filter(est_actif=True).count()
        
        # Statistiques par classe
        stats_classes = {}
        for classe_id, classe_label in PlanComptable.CLASSES:
            comptes_classe = comptes.filter(classe=classe_id)
            total_debit = comptes_classe.aggregate(total=models.Sum('solde_debiteur'))['total'] or 0
            total_credit = comptes_classe.aggregate(total=models.Sum('solde_crediteur'))['total'] or 0
            stats_classes[classe_id] = {
                'label': classe_label,
                'count': comptes_classe.count(),
                'total_debit': total_debit,
                'total_credit': total_credit,
                'solde': total_debit - total_credit
            }
        
        # Totaux généraux
        total_debit_general = comptes.aggregate(total=models.Sum('solde_debiteur'))['total'] or 0
        total_credit_general = comptes.aggregate(total=models.Sum('solde_crediteur'))['total'] or 0
        solde_general = total_debit_general - total_credit_general
        
        return render(request, 'comptabilite/plan_comptable/plan_comptable_list.html', {
            'comptes': comptes,
            'total_comptes': total_comptes,
            'comptes_actifs': comptes_actifs,
            'stats_classes': stats_classes,
            'total_debit_general': total_debit_general,
            'total_credit_general': total_credit_general,
            'solde_general': solde_general,
        })
    
    # Vue fonctionnelle pour créer un compte comptable
    @login_required
    def plan_comptable_create_view(request):
        """Vue simple pour créer un compte comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import PlanComptable
        from django import forms
        
        class SimplePlanComptableForm(forms.ModelForm):
            def __init__(self, *args, **kwargs):
                entreprise = kwargs.pop('entreprise', None)
                super().__init__(*args, **kwargs)
                if entreprise:
                    # Filtrer les comptes parents de la même entreprise
                    self.fields['compte_parent'].queryset = PlanComptable.objects.filter(
                        entreprise=entreprise
                    ).order_by('numero_compte')
            
            class Meta:
                model = PlanComptable
                fields = ['numero_compte', 'intitule', 'classe', 'compte_parent', 'est_actif']
                widgets = {
                    'numero_compte': forms.TextInput(attrs={'class': 'form-control'}),
                    'intitule': forms.TextInput(attrs={'class': 'form-control'}),
                    'classe': forms.Select(attrs={'class': 'form-select'}),
                    'compte_parent': forms.Select(attrs={'class': 'form-select'}),
                    'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                }
        
        if request.method == 'POST':
            form = SimplePlanComptableForm(request.POST, entreprise=entreprise)
            if form.is_valid():
                compte = form.save(commit=False)
                compte.entreprise = entreprise
                compte.save()
                from django.contrib import messages
                messages.success(request, f"Compte {compte.numero_compte} créé avec succès!")
                return render(request, 'comptabilite/plan_comptable/plan_comptable_form.html', {
                    'form': SimplePlanComptableForm(entreprise=entreprise),
                    'success': True,
                })
        else:
            form = SimplePlanComptableForm(entreprise=entreprise)
        
        return render(request, 'comptabilite/plan_comptable/plan_comptable_form.html', {
            'form': form,
        })
    
    # Vue fonctionnelle pour détail d'un compte comptable
    @login_required
    def plan_comptable_detail_view(request, pk):
        """Vue simple pour détail d'un compte comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import PlanComptable
        compte = get_object_or_404(PlanComptable, pk=pk, entreprise=entreprise)
        
        # Récupérer les sous-comptes
        sous_comptes = compte.sous_comptes.all().order_by('numero_compte')
        
        return render(request, 'comptabilite/plan_comptable/plan_comptable_detail.html', {
            'compte': compte,
            'sous_comptes': sous_comptes,
        })
    
    # Vue fonctionnelle pour la liste des règlements
    @login_required
    def reglement_list_view(request):
        """Vue simple pour lister les règlements"""
        entreprise = request.user.entreprise
        from comptabilite.models import Reglement, Facture
        from django.db import models
        
        reglements = Reglement.objects.filter(entreprise=entreprise).order_by('-date_reglement')
        
        # Calculer les statistiques
        total_reglements = reglements.count()
        total_montant = reglements.aggregate(total=models.Sum('montant'))['total'] or 0
        
        # Statistiques par mode de paiement
        stats_modes = {}
        for mode, label in Reglement.MODES_PAIEMENT:
            montant_mode = reglements.filter(mode_paiement=mode).aggregate(
                total=models.Sum('montant')
            )['total'] or 0
            stats_modes[mode] = {
                'label': label,
                'montant': montant_mode,
                'count': reglements.filter(mode_paiement=mode).count()
            }
        
        return render(request, 'comptabilite/reglements/reglement_list.html', {
            'reglements': reglements,
            'total_reglements': total_reglements,
            'total_montant': total_montant,
            'stats_modes': stats_modes,
        })
    
    # Vue fonctionnelle pour le journal général
    @login_required
    def journal_general_view(request):
        """Vue simple pour afficher le journal général"""
        entreprise = request.user.entreprise
        from comptabilite.models import EcritureComptable, LigneEcriture, Journal, ExerciceComptable
        from django.db import models
        from django.utils import timezone
        from datetime import datetime, timedelta
        
        # Récupérer les écritures comptables
        ecritures = EcritureComptable.objects.filter(
            entreprise=entreprise
        ).order_by('-date_ecriture', '-date_creation')
        
        # Filtrage par date si spécifié
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        journal_id = request.GET.get('journal')
        exercice_id = request.GET.get('exercice')
        
        if date_debut:
            try:
                date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
                ecritures = ecritures.filter(date_ecriture__gte=date_debut)
            except ValueError:
                date_debut = None
        
        if date_fin:
            try:
                date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
                ecritures = ecritures.filter(date_ecriture__lte=date_fin)
            except ValueError:
                date_fin = None
        
        if journal_id:
            ecritures = ecritures.filter(journal_id=journal_id)
        
        if exercice_id:
            ecritures = ecritures.filter(exercice_id=exercice_id)
        
        # Récupérer les options de filtrage
        journaux = Journal.objects.filter(entreprise=entreprise).order_by('code')
        exercices = ExerciceComptable.objects.filter(entreprise=entreprise).order_by('-date_debut')
        
        # Calculer les statistiques
        total_ecritures = ecritures.count()
        
        # Calculer les totaux débit/crédit
        lignes_ecritures = LigneEcriture.objects.filter(
            ecriture__entreprise=entreprise
        )
        
        if date_debut:
            lignes_ecritures = lignes_ecritures.filter(ecriture__date_ecriture__gte=date_debut)
        if date_fin:
            lignes_ecritures = lignes_ecritures.filter(ecriture__date_ecriture__lte=date_fin)
        if journal_id:
            lignes_ecritures = lignes_ecritures.filter(ecriture__journal_id=journal_id)
        if exercice_id:
            lignes_ecritures = lignes_ecritures.filter(ecriture__exercice_id=exercice_id)
        
        total_debit = lignes_ecritures.aggregate(
            total=models.Sum('montant_debit')
        )['total'] or 0
        total_credit = lignes_ecritures.aggregate(
            total=models.Sum('montant_credit')
        )['total'] or 0
        
        solde = total_debit - total_credit
        
        # Préparer les données pour l'affichage
        journal_general_data = []
        for ecriture in ecritures[:100]:  # Limiter à 100 écritures pour la performance
            lignes = LigneEcriture.objects.filter(ecriture=ecriture).order_by('id')
            for ligne in lignes:
                journal_general_data.append({
                    'date_ecriture': ecriture.date_ecriture,
                    'code_journal': ecriture.journal.code if ecriture.journal else '',
                    'libelle_journal': ecriture.journal.libelle if ecriture.journal else '',
                    'numero_ecriture': ecriture.numero_ecriture,
                    'libelle_ecriture': ecriture.libelle,
                    'compte_numero': ligne.compte.numero_compte if ligne.compte else '',
                    'compte_intitule': ligne.compte.intitule if ligne.compte else '',
                    'reference': getattr(ligne, 'reference', '') or '',
                    'montant_debit': ligne.montant_debit,
                    'montant_credit': ligne.montant_credit,
                    'statut': 'Validée' if ecriture.est_validee else 'Brouillon'
                })
        
        return render(request, 'comptabilite/etats/journal_general.html', {
            'journal_general_data': journal_general_data,
            'total_ecritures': total_ecritures,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'solde': solde,
            'journaux': journaux,
            'exercices': exercices,
            'date_debut': date_debut,
            'date_fin': date_fin,
            'journal_id': journal_id,
            'exercice_id': exercice_id,
        })
    
    # Vue fonctionnelle pour les comptes fournisseurs
    @login_required
    def compte_fournisseur_list_view(request):
        """Vue simple pour lister les comptes fournisseurs"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture, Reglement
        from django.db import models
        
        # Récupérer les fournisseurs
        fournisseurs = Tiers.objects.filter(
            entreprise=entreprise,
            type_tiers='fournisseur'
        ).order_by('raison_sociale')
        
        # Calculer les statistiques
        total_fournisseurs = fournisseurs.count()
        fournisseurs_actifs = fournisseurs.filter(est_actif=True).count()
        
        # Statistiques détaillées par fournisseur
        stats_fournisseurs = {}
        for fournisseur in fournisseurs:
            nb_factures = Facture.objects.filter(tiers=fournisseur).count()
            total_factures = Facture.objects.filter(tiers=fournisseur).aggregate(
                total=models.Sum('montant_ttc')
            )['total'] or 0
            total_paye = Facture.objects.filter(tiers=fournisseur).aggregate(
                total=models.Sum('montant_paye')
            )['total'] or 0
            total_restant = total_factures - total_paye
            
            # Statut du compte (inverse pour les fournisseurs)
            if total_restant > 0:
                statut_compte = 'créditeur'  # On leur doit de l'argent
            elif total_restant < 0:
                statut_compte = 'débiteur'   # On leur a trop payé
            else:
                statut_compte = 'soldé'
            
            stats_fournisseurs[fournisseur.pk] = {
                'nb_factures': nb_factures,
                'total_factures': total_factures,
                'total_paye': total_paye,
                'total_restant': total_restant,
                'statut_compte': statut_compte
            }
        
        # Ajouter les stats aux objets fournisseurs
        for fournisseur in fournisseurs:
            stats = stats_fournisseurs.get(fournisseur.pk, {})
            fournisseur.nb_factures = stats.get('nb_factures', 0)
            fournisseur.total_factures = stats.get('total_factures', 0)
            fournisseur.total_paye = stats.get('total_paye', 0)
            fournisseur.total_restant = stats.get('total_restant', 0)
            fournisseur.statut_compte = stats.get('statut_compte', 'soldé')
        
        # Calculer les totaux généraux
        total_general_factures = sum(fournisseur.total_factures for fournisseur in fournisseurs)
        total_general_paye = sum(fournisseur.total_paye for fournisseur in fournisseurs)
        total_general_restant = sum(fournisseur.total_restant for fournisseur in fournisseurs)
        
        return render(request, 'comptabilite/comptes_fournisseurs/compte_fournisseur_list.html', {
            'fournisseurs': fournisseurs,
            'total_fournisseurs': total_fournisseurs,
            'fournisseurs_actifs': fournisseurs_actifs,
            'stats_fournisseurs': stats_fournisseurs,
            'total_general_factures': total_general_factures,
            'total_general_paye': total_general_paye,
            'total_general_restant': total_general_restant,
        })
    
    # Vue fonctionnelle pour détail d'un compte fournisseur
    @login_required
    def compte_fournisseur_detail_view(request, pk):
        """Vue simple pour détail d'un compte fournisseur"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture, Reglement
        from django.db import models
        
        fournisseur = get_object_or_404(Tiers, pk=pk, entreprise=entreprise, type_tiers='fournisseur')
        
        # Récupérer les factures du fournisseur
        factures = Facture.objects.filter(tiers=fournisseur).order_by('-date_facture')
        
        # Récupérer les règlements du fournisseur
        reglements = Reglement.objects.filter(facture__tiers=fournisseur).order_by('-date_reglement')
        
        # Calculer les totaux
        total_factures = Facture.objects.filter(tiers=fournisseur).aggregate(
            total=models.Sum('montant_ttc')
        )['total'] or 0
        total_paye = Facture.objects.filter(tiers=fournisseur).aggregate(
            total=models.Sum('montant_paye')
        )['total'] or 0
        solde = total_factures - total_paye
        
        # Statistiques par statut de facture
        factures_brouillon = factures.filter(statut='brouillon').count()
        factures_validees = factures.filter(statut='validee').count()
        factures_payees = factures.filter(statut='payee').count()
        
        return render(request, 'comptabilite/comptes_fournisseurs/compte_fournisseur_detail.html', {
            'fournisseur': fournisseur,
            'factures': factures,
            'reglements': reglements,
            'total_factures': total_factures,
            'total_paye': total_paye,
            'solde': solde,
            'factures_brouillon': factures_brouillon,
            'factures_validees': factures_validees,
            'factures_payees': factures_payees,
        })
    
    # Vue fonctionnelle pour les comptes clients
    @login_required
    def compte_client_list_view(request):
        """Vue simple pour lister les comptes clients"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture, Reglement
        from django.db import models
        
        # Récupérer les clients
        clients = Tiers.objects.filter(
            entreprise=entreprise,
            type_tiers='client'
        ).order_by('raison_sociale')
        
        # Calculer les statistiques
        total_clients = clients.count()
        clients_actifs = clients.filter(est_actif=True).count()
        
        # Statistiques détaillées par client
        stats_clients = {}
        for client in clients:
            nb_factures = Facture.objects.filter(tiers=client).count()
            total_factures = Facture.objects.filter(tiers=client).aggregate(
                total=models.Sum('montant_ttc')
            )['total'] or 0
            total_paye = Facture.objects.filter(tiers=client).aggregate(
                total=models.Sum('montant_paye')
            )['total'] or 0
            total_restant = total_factures - total_paye
            
            # Statut du compte
            if total_restant > 0:
                statut_compte = 'débiteur'
            elif total_restant < 0:
                statut_compte = 'créditeur'
            else:
                statut_compte = 'soldé'
            
            stats_clients[client.pk] = {
                'nb_factures': nb_factures,
                'total_factures': total_factures,
                'total_paye': total_paye,
                'total_restant': total_restant,
                'statut_compte': statut_compte
            }
        
        # Ajouter les stats aux objets clients
        for client in clients:
            stats = stats_clients.get(client.pk, {})
            client.nb_factures = stats.get('nb_factures', 0)
            client.total_factures = stats.get('total_factures', 0)
            client.total_paye = stats.get('total_paye', 0)
            client.total_restant = stats.get('total_restant', 0)
            client.statut_compte = stats.get('statut_compte', 'soldé')
        
        # Calculer les totaux généraux
        total_general_factures = sum(client.total_factures for client in clients)
        total_general_paye = sum(client.total_paye for client in clients)
        total_general_restant = sum(client.total_restant for client in clients)
        
        return render(request, 'comptabilite/comptes_clients/compte_client_list.html', {
            'clients': clients,
            'total_clients': total_clients,
            'clients_actifs': clients_actifs,
            'stats_clients': stats_clients,
            'total_general_factures': total_general_factures,
            'total_general_paye': total_general_paye,
            'total_general_restant': total_general_restant,
        })
    
    # Vue fonctionnelle pour détail d'un compte client
    @login_required
    def compte_client_detail_view(request, pk):
        """Vue simple pour détail d'un compte client"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture, Reglement
        from django.db import models
        
        client = get_object_or_404(Tiers, pk=pk, entreprise=entreprise, type_tiers='client')
        
        # Récupérer les factures du client
        factures = Facture.objects.filter(tiers=client).order_by('-date_facture')
        
        # Récupérer les règlements du client
        reglements = Reglement.objects.filter(facture__tiers=client).order_by('-date_reglement')
        
        # Calculer les totaux
        total_factures = Facture.objects.filter(tiers=client).aggregate(
            total=models.Sum('montant_ttc')
        )['total'] or 0
        total_paye = Facture.objects.filter(tiers=client).aggregate(
            total=models.Sum('montant_paye')
        )['total'] or 0
        solde = total_factures - total_paye
        
        # Statistiques par statut de facture
        factures_brouillon = factures.filter(statut='brouillon').count()
        factures_validees = factures.filter(statut='validee').count()
        factures_payees = factures.filter(statut='payee').count()
        
        return render(request, 'comptabilite/comptes_clients/compte_client_detail.html', {
            'client': client,
            'factures': factures,
            'reglements': reglements,
            'total_factures': total_factures,
            'total_paye': total_paye,
            'solde': solde,
            'factures_brouillon': factures_brouillon,
            'factures_validees': factures_validees,
            'factures_payees': factures_payees,
        })
    
    # Vue fonctionnelle pour les journaux
    @login_required
    def journal_list_view(request):
        """Vue simple pour lister les journaux comptables"""
        entreprise = request.user.entreprise
        from comptabilite.models import Journal, EcritureComptable
        from django.db import models
        
        journaux = Journal.objects.filter(entreprise=entreprise).order_by('code')
        
        # Calculer les statistiques
        total_journaux = journaux.count()
        journaux_actifs = journaux.filter(est_actif=True).count()
        
        # Statistiques par type de journal
        stats_types = {}
        for type_id, type_label in Journal.TYPES_JOURNAL:
            journaux_type = journaux.filter(type_journal=type_id)
            count = journaux_type.count()
            actifs = journaux_type.filter(est_actif=True).count()
            pourcentage_actifs = (actifs * 100 / count) if count > 0 else 0
            
            stats_types[type_id] = {
                'label': type_label,
                'count': count,
                'actifs': actifs,
                'pourcentage_actifs': pourcentage_actifs
            }
        
        # Statistiques des écritures par journal
        stats_ecritures = {}
        for journal in journaux:
            nb_ecritures = EcritureComptable.objects.filter(journal=journal).count()
            stats_ecritures[journal.pk] = nb_ecritures
        
        # Ajouter les stats d'écritures aux objets journaux pour un accès facile
        for journal in journaux:
            journal.nb_ecritures = stats_ecritures.get(journal.pk, 0)
        
        # Calculer le total des écritures
        total_ecritures = sum(stats_ecritures.values())
        
        return render(request, 'comptabilite/journaux/journal_list.html', {
            'journaux': journaux,
            'total_journaux': total_journaux,
            'journaux_actifs': journaux_actifs,
            'stats_types': stats_types,
            'stats_ecritures': stats_ecritures,
            'total_ecritures': total_ecritures,
        })
    
    # Vue fonctionnelle pour créer un journal
    @login_required
    def journal_create_view(request):
        """Vue simple pour créer un journal comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import Journal, PlanComptable
        from django import forms
        
        class SimpleJournalForm(forms.ModelForm):
            def __init__(self, *args, **kwargs):
                entreprise = kwargs.pop('entreprise', None)
                super().__init__(*args, **kwargs)
                if entreprise:
                    # Filtrer les comptes de contrepartie de la même entreprise
                    self.fields['compte_contrepartie'].queryset = PlanComptable.objects.filter(
                        entreprise=entreprise,
                        est_actif=True
                    ).order_by('numero_compte')
            
            class Meta:
                model = Journal
                fields = ['code', 'libelle', 'type_journal', 'compte_contrepartie', 'est_actif']
                widgets = {
                    'code': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 5}),
                    'libelle': forms.TextInput(attrs={'class': 'form-control'}),
                    'type_journal': forms.Select(attrs={'class': 'form-select'}),
                    'compte_contrepartie': forms.Select(attrs={'class': 'form-select'}),
                    'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                }
        
        if request.method == 'POST':
            form = SimpleJournalForm(request.POST, entreprise=entreprise)
            if form.is_valid():
                journal = form.save(commit=False)
                journal.entreprise = entreprise
                journal.save()
                from django.contrib import messages
                messages.success(request, f"Journal {journal.code} créé avec succès!")
                return render(request, 'comptabilite/journaux/journal_form.html', {
                    'form': SimpleJournalForm(entreprise=entreprise),
                    'success': True,
                })
        else:
            form = SimpleJournalForm(entreprise=entreprise)
        
        return render(request, 'comptabilite/journaux/journal_form.html', {
            'form': form,
        })
    
    # Vue fonctionnelle pour détail d'un journal
    @login_required
    def journal_detail_view(request, pk):
        """Vue simple pour détail d'un journal comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import Journal, EcritureComptable
        journal = get_object_or_404(Journal, pk=pk, entreprise=entreprise)
        
        # Récupérer les écritures du journal
        ecritures = EcritureComptable.objects.filter(journal=journal).order_by('-date_ecriture')[:20]
        
        return render(request, 'comptabilite/journaux/journal_detail.html', {
            'journal': journal,
            'ecritures': ecritures,
        })
    
    # Vue fonctionnelle pour les exercices comptables
    @login_required
    def exercice_list_view(request):
        """Vue simple pour lister les exercices comptables"""
        entreprise = request.user.entreprise
        from comptabilite.models import ExerciceComptable, EcritureComptable
        from django.db import models
        
        exercices = ExerciceComptable.objects.filter(entreprise=entreprise).order_by('-date_debut')
        
        # Calculer les statistiques
        total_exercices = exercices.count()
        exercices_ouverts = exercices.filter(statut='ouvert').count()
        exercices_clotures = exercices.filter(statut='cloture').count()
        exercice_courant = exercices.filter(est_courant=True).first()
        
        # Statistiques détaillées par exercice
        stats_exercices = {}
        for exercice in exercices:
            nb_ecritures = EcritureComptable.objects.filter(exercice=exercice).count()
            total_debit = EcritureComptable.objects.filter(exercice=exercice).aggregate(
                total=models.Sum('ligneecriture__montant_debit')
            )['total'] or 0
            total_credit = EcritureComptable.objects.filter(exercice=exercice).aggregate(
                total=models.Sum('ligneecriture__montant_credit')
            )['total'] or 0
            
            stats_exercices[exercice.pk] = {
                'nb_ecritures': nb_ecritures,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'solde': total_debit - total_credit
            }
        
        # Ajouter les stats aux objets exercices
        for exercice in exercices:
            stats = stats_exercices.get(exercice.pk, {})
            exercice.nb_ecritures = stats.get('nb_ecritures', 0)
            exercice.total_debit = stats.get('total_debit', 0)
            exercice.total_credit = stats.get('total_credit', 0)
            exercice.solde = stats.get('solde', 0)
        
        # Calculer les totaux généraux
        total_general_debit = sum(exercice.total_debit for exercice in exercices)
        total_general_credit = sum(exercice.total_credit for exercice in exercices)
        total_general_solde = sum(exercice.solde for exercice in exercices)
        
        return render(request, 'comptabilite/exercices/exercice_list.html', {
            'exercices': exercices,
            'total_exercices': total_exercices,
            'exercices_ouverts': exercices_ouverts,
            'exercices_clotures': exercices_clotures,
            'exercice_courant': exercice_courant,
            'stats_exercices': stats_exercices,
            'total_general_debit': total_general_debit,
            'total_general_credit': total_general_credit,
            'total_general_solde': total_general_solde,
        })
    
    # Vue fonctionnelle pour créer un exercice
    @login_required
    def exercice_create_view(request):
        """Vue simple pour créer un exercice comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import ExerciceComptable
        from django import forms
        from datetime import date, timedelta
        
        class SimpleExerciceForm(forms.ModelForm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['libelle'].widget.attrs.update({'class': 'form-control'})
                self.fields['date_debut'].widget.attrs.update({'class': 'form-control', 'type': 'date'})
                self.fields['date_fin'].widget.attrs.update({'class': 'form-control', 'type': 'date'})
                self.fields['statut'].widget.attrs.update({'class': 'form-select'})
                self.fields['est_courant'].widget.attrs.update({'class': 'form-check-input'})
            
            class Meta:
                model = ExerciceComptable
                fields = ['libelle', 'date_debut', 'date_fin', 'statut', 'est_courant']
        
        if request.method == 'POST':
            form = SimpleExerciceForm(request.POST)
            if form.is_valid():
                exercice = form.save(commit=False)
                exercice.entreprise = entreprise
                
                # Si c'est l'exercice courant, décocher les autres
                if exercice.est_courant:
                    ExerciceComptable.objects.filter(entreprise=entreprise, est_courant=True).update(est_courant=False)
                
                exercice.save()
                from django.contrib import messages
                messages.success(request, f"Exercice {exercice.libelle} créé avec succès!")
                return render(request, 'comptabilite/exercices/exercice_form.html', {
                    'form': SimpleExerciceForm(),
                    'success': True,
                })
        else:
            form = SimpleExerciceForm()
        
        return render(request, 'comptabilite/exercices/exercice_form.html', {
            'form': form,
        })
    
    # Vue fonctionnelle pour détail d'un exercice
    @login_required
    def exercice_detail_view(request, pk):
        """Vue simple pour détail d'un exercice comptable"""
        entreprise = request.user.entreprise
        from comptabilite.models import ExerciceComptable, EcritureComptable
        from django.db import models
        
        exercice = get_object_or_404(ExerciceComptable, pk=pk, entreprise=entreprise)
        
        # Récupérer les écritures de l'exercice
        ecritures = EcritureComptable.objects.filter(exercice=exercice).order_by('-date_ecriture')[:20]
        
        # Calculer les totaux
        total_debit = EcritureComptable.objects.filter(exercice=exercice).aggregate(
            total=models.Sum('ligneecriture__montant_debit')
        )['total'] or 0
        total_credit = EcritureComptable.objects.filter(exercice=exercice).aggregate(
            total=models.Sum('ligneecriture__montant_credit')
        )['total'] or 0
        
        return render(request, 'comptabilite/exercices/exercice_detail.html', {
            'exercice': exercice,
            'ecritures': ecritures,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'solde': total_debit - total_credit,
        })
    
    # Vue fonctionnelle pour les tiers
    @login_required
    def tiers_list_view(request):
        """Vue simple pour lister les tiers (clients et fournisseurs)"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture
        
        tiers_list = Tiers.objects.filter(entreprise=entreprise).order_by('raison_sociale')
        
        # Calculer les statistiques
        total_tiers = tiers_list.count()
        clients_count = tiers_list.filter(type_tiers='client').count()
        fournisseurs_count = tiers_list.filter(type_tiers='fournisseur').count()
        mixtes_count = tiers_list.filter(type_tiers='mixte').count()
        tiers_actifs = tiers_list.filter(est_actif=True).count()
        
        # Statistiques détaillées par tiers
        stats_tiers = {}
        for tier in tiers_list:
            nb_factures = Facture.objects.filter(tiers=tier).count()
            total_factures = Facture.objects.filter(tiers=tier).aggregate(
                total=models.Sum('montant_ttc')
            )['total'] or 0
            
            stats_tiers[tier.pk] = {
                'nb_factures': nb_factures,
                'total_factures': total_factures
            }
        
        # Ajouter les stats aux objets tiers
        for tier in tiers_list:
            stats = stats_tiers.get(tier.pk, {})
            tier.nb_factures = stats.get('nb_factures', 0)
            tier.total_factures = stats.get('total_factures', 0)
        
        return render(request, 'comptabilite/tiers/tiers_list.html', {
            'tiers': tiers_list,
            'total_tiers': total_tiers,
            'clients_count': clients_count,
            'fournisseurs_count': fournisseurs_count,
            'mixtes_count': mixtes_count,
            'tiers_actifs': tiers_actifs,
            'stats_tiers': stats_tiers,
        })
    
    # Vue fonctionnelle pour créer un tiers
    @login_required
    def tiers_create_view(request):
        """Vue simple pour créer un tiers"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, PlanComptable
        from django import forms
        
        class SimpleTiersForm(forms.ModelForm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['code'].widget.attrs.update({'class': 'form-control'})
                self.fields['raison_sociale'].widget.attrs.update({'class': 'form-control'})
                self.fields['type_tiers'].widget.attrs.update({'class': 'form-select'})
                self.fields['nif'].widget.attrs.update({'class': 'form-control'})
                self.fields['adresse'].widget.attrs.update({'class': 'form-control', 'rows': 3})
                self.fields['telephone'].widget.attrs.update({'class': 'form-control'})
                self.fields['email'].widget.attrs.update({'class': 'form-control'})
                self.fields['compte_comptable'].widget.attrs.update({'class': 'form-select'})
                self.fields['plafond_credit'].widget.attrs.update({'class': 'form-control'})
                self.fields['est_actif'].widget.attrs.update({'class': 'form-check-input'})
                
                # Filtrer les comptes comptables de l'entreprise
                self.fields['compte_comptable'].queryset = PlanComptable.objects.filter(
                    entreprise=entreprise, est_actif=True
                )
            
            class Meta:
                model = Tiers
                fields = ['code', 'raison_sociale', 'type_tiers', 'nif', 'adresse', 'telephone', 'email', 'compte_comptable', 'plafond_credit', 'est_actif']
        
        if request.method == 'POST':
            form = SimpleTiersForm(request.POST)
            if form.is_valid():
                tier = form.save(commit=False)
                tier.entreprise = entreprise
                tier.save()
                from django.contrib import messages
                messages.success(request, f"Tiers {tier.raison_sociale} créé avec succès!")
                return render(request, 'comptabilite/tiers/tiers_form.html', {
                    'form': SimpleTiersForm(),
                    'success': True,
                })
        else:
            form = SimpleTiersForm()
        
        return render(request, 'comptabilite/tiers/tiers_form.html', {
            'form': form,
        })
    
    # Vue fonctionnelle pour détail d'un tiers
    @login_required
    def tiers_detail_view(request, pk):
        """Vue simple pour détail d'un tiers"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture
        from django.db import models
        
        tier = get_object_or_404(Tiers, pk=pk, entreprise=entreprise)
        
        # Récupérer les factures du tiers
        factures = Facture.objects.filter(tiers=tier).order_by('-date_facture')[:20]
        
        # Calculer les totaux
        total_factures = Facture.objects.filter(tiers=tier).count()
        total_montant = Facture.objects.filter(tiers=tier).aggregate(
            total=models.Sum('montant_ttc')
        )['total'] or 0
        total_paye = Facture.objects.filter(tiers=tier).aggregate(
            total=models.Sum('montant_paye')
        )['total'] or 0
        solde = total_montant - total_paye
        
        return render(request, 'comptabilite/tiers/tiers_detail.html', {
            'tier': tier,
            'factures': factures,
            'total_factures': total_factures,
            'total_montant': total_montant,
            'total_paye': total_paye,
            'solde': solde,
        })
    
    # Vue fonctionnelle pour créer un règlement
    @login_required
    def reglement_create_view(request):
        """Vue simple pour créer un règlement"""
        entreprise = request.user.entreprise
        from comptabilite.models import Reglement, Facture
        from django import forms
        
        class SimpleReglementForm(forms.ModelForm):
            def __init__(self, *args, **kwargs):
                entreprise = kwargs.pop('entreprise', None)
                super().__init__(*args, **kwargs)
                if entreprise:
                    # Filtrer les factures non payées ou partiellement payées
                    self.fields['facture'].queryset = Facture.objects.filter(
                        entreprise=entreprise
                    ).exclude(
                        statut='payee'
                    ).order_by('-date_facture')
            
            class Meta:
                model = Reglement
                fields = ['numero', 'facture', 'date_reglement', 'montant', 'mode_paiement', 'reference', 'notes']
                widgets = {
                    'numero': forms.TextInput(attrs={'class': 'form-control'}),
                    'facture': forms.Select(attrs={'class': 'form-select'}),
                    'date_reglement': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                    'montant': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                    'mode_paiement': forms.Select(attrs={'class': 'form-select'}),
                    'reference': forms.TextInput(attrs={'class': 'form-control'}),
                    'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                }
        
        if request.method == 'POST':
            form = SimpleReglementForm(request.POST, entreprise=entreprise)
            if form.is_valid():
                reglement = form.save(commit=False)
                reglement.entreprise = entreprise
                reglement.save()
                from django.contrib import messages
                messages.success(request, f"Règlement {reglement.numero} enregistré avec succès!")
                return render(request, 'comptabilite/reglements/reglement_form.html', {
                    'form': SimpleReglementForm(entreprise=entreprise),
                    'success': True,
                })
        else:
            form = SimpleReglementForm(entreprise=entreprise)
        
        return render(request, 'comptabilite/reglements/reglement_form.html', {
            'form': form,
        })
    
    # Vue fonctionnelle pour détail d'un règlement
    @login_required
    def reglement_detail_view(request, pk):
        """Vue simple pour détail d'un règlement"""
        entreprise = request.user.entreprise
        from comptabilite.models import Reglement
        reglement = get_object_or_404(Reglement, pk=pk, entreprise=entreprise)
        return render(request, 'comptabilite/reglements/reglement_detail.html', {
            'reglement': reglement,
        })
    
    # Créer des vues fallback fonctionnelles pour tiers et factures
    @login_required
    def tiers_list_view(request):
        """Vue simple pour la liste des tiers"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers
        tiers = Tiers.objects.filter(entreprise=entreprise).order_by('raison_sociale')
        return render(request, 'comptabilite/tiers/tiers_list.html', {
            'tiers': tiers,
            'type_tiers': request.GET.get('type', ''),
        })
    
    @login_required
    def tiers_create_view(request):
        """Vue simple pour créer un tiers"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers
        from django import forms
        
        class SimpleTiersForm(forms.ModelForm):
            class Meta:
                model = Tiers
                fields = ['code', 'raison_sociale', 'type_tiers', 'nif', 'telephone', 'email', 'adresse']
                widgets = {
                    'code': forms.TextInput(attrs={'class': 'form-control'}),
                    'raison_sociale': forms.TextInput(attrs={'class': 'form-control'}),
                    'type_tiers': forms.Select(attrs={'class': 'form-select'}),
                    'nif': forms.TextInput(attrs={'class': 'form-control'}),
                    'telephone': forms.TextInput(attrs={'class': 'form-control'}),
                    'email': forms.EmailInput(attrs={'class': 'form-control'}),
                    'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                }
        
        if request.method == 'POST':
            form = SimpleTiersForm(request.POST)
            if form.is_valid():
                tiers = form.save(commit=False)
                tiers.entreprise = entreprise
                tiers.save()
                from django.contrib import messages
                messages.success(request, f"Tiers {tiers.raison_sociale} créé avec succès!")
                return render(request, 'comptabilite/tiers/tiers_form.html', {
                    'form': SimpleTiersForm(),
                    'success': True,
                })
        else:
            form = SimpleTiersForm()
        
        return render(request, 'comptabilite/tiers/tiers_form.html', {'form': form})
    
    @login_required
    def tiers_detail_view(request, pk):
        """Vue simple pour détail d'un tiers"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers, Facture
        tiers = get_object_or_404(Tiers, pk=pk, entreprise=entreprise)
        factures = Facture.objects.filter(tiers=tiers).order_by('-date_facture')[:10]
        return render(request, 'comptabilite/tiers/tiers_detail.html', {
            'tiers': tiers,
            'factures': factures,
        })
    
    @login_required
    def tiers_update_view(request, pk):
        """Vue simple pour modifier un tiers"""
        entreprise = request.user.entreprise
        from comptabilite.models import Tiers
        from django import forms
        
        tiers = get_object_or_404(Tiers, pk=pk, entreprise=entreprise)
        
        class SimpleTiersForm(forms.ModelForm):
            class Meta:
                model = Tiers
                fields = ['code', 'raison_sociale', 'type_tiers', 'nif', 'telephone', 'email', 'adresse']
                widgets = {
                    'code': forms.TextInput(attrs={'class': 'form-control'}),
                    'raison_sociale': forms.TextInput(attrs={'class': 'form-control'}),
                    'type_tiers': forms.Select(attrs={'class': 'form-select'}),
                    'nif': forms.TextInput(attrs={'class': 'form-control'}),
                    'telephone': forms.TextInput(attrs={'class': 'form-control'}),
                    'email': forms.EmailInput(attrs={'class': 'form-control'}),
                    'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                }
        
        if request.method == 'POST':
            form = SimpleTiersForm(request.POST, instance=tiers)
            if form.is_valid():
                form.save()
                from django.contrib import messages
                messages.success(request, f"Tiers {tiers.raison_sociale} modifié avec succès!")
                return render(request, 'comptabilite/tiers/tiers_form.html', {
                    'form': form,
                    'success': True,
                })
        else:
            form = SimpleTiersForm(instance=tiers)
        
        return render(request, 'comptabilite/tiers/tiers_form.html', {
            'form': form,
            'tiers': tiers,
        })

    @login_required
    def facture_list_view(request):
        """Vue simple pour lister les factures"""
        entreprise = request.user.entreprise
        type_facture = request.GET.get('type', '')
        from comptabilite.models import Facture

        factures = Facture.objects.filter(entreprise=entreprise)
        if type_facture:
            factures = factures.filter(type_facture=type_facture)

        # Calculer les statistiques
        total_factures = factures.count()
        factures_payees = factures.filter(statut='payee').count()
        factures_non_payees = total_factures - factures_payees
        taux_paiement = (factures_payees / total_factures * 100) if total_factures > 0 else 0
        
        # Calculer les totaux des montants
        from django.db.models import Sum
        total_montant_ht = factures.aggregate(total=Sum('montant_ht'))['total'] or 0
        total_montant_tva = factures.aggregate(total=Sum('montant_tva'))['total'] or 0
        total_montant_ttc = factures.aggregate(total=Sum('montant_ttc'))['total'] or 0

        return render(request, 'comptabilite/factures/facture_list.html', {
            'factures': factures,
            'type_facture': type_facture,
            'total_factures': total_factures,
            'factures_payees': factures_payees,
            'factures_non_payees': factures_non_payees,
            'taux_paiement': taux_paiement,
            'total_montant_ht': total_montant_ht,
            'total_montant_tva': total_montant_tva,
            'total_montant_ttc': total_montant_ttc,
        })

    @login_required
    def facture_create_view(request):
        """Vue simple pour créer une facture"""
        entreprise = request.user.entreprise
        type_facture = request.GET.get('type', 'vente')
        from django import forms
        from comptabilite.models import Facture, Tiers
        
        class SimpleFactureForm(forms.ModelForm):
            def __init__(self, *args, **kwargs):
                entreprise = kwargs.pop('entreprise', None)
                super().__init__(*args, **kwargs)
                if entreprise:
                    self.fields['tiers'].queryset = Tiers.objects.filter(entreprise=entreprise)
            
            class Meta:
                model = Facture
                fields = ['numero', 'tiers', 'date_facture', 'date_echeance', 'type_facture', 'montant_ht', 'montant_tva', 'montant_ttc']
                widgets = {
                    'numero': forms.TextInput(attrs={'class': 'form-control'}),
                    'tiers': forms.Select(attrs={'class': 'form-select'}),
                    'date_facture': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                    'date_echeance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                    'type_facture': forms.Select(attrs={'class': 'form-select'}),
                    'montant_ht': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                    'montant_tva': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                    'montant_ttc': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                }
        
        if request.method == 'POST':
            form = SimpleFactureForm(request.POST, entreprise=entreprise)
            if form.is_valid():
                facture = form.save(commit=False)
                facture.entreprise = entreprise
                facture.save()
                from django.contrib import messages
                messages.success(request, f"Facture {facture.numero} créée avec succès!")
                return render(request, 'comptabilite/factures/facture_form.html', {
                    'form': SimpleFactureForm(entreprise=entreprise, initial={'type_facture': type_facture}),
                    'success': True,
                })
        else:
            form = SimpleFactureForm(entreprise=entreprise, initial={'type_facture': type_facture})
        
        return render(request, 'comptabilite/factures/facture_form.html', {
            'form': form,
            'type_facture': type_facture,
        })
    
    @login_required
    def facture_detail_view(request, pk):
        """Vue simple pour détail d'une facture"""
        entreprise = request.user.entreprise
        from comptabilite.models import Facture
        facture = get_object_or_404(Facture, pk=pk, entreprise=entreprise)
        return render(request, 'comptabilite/factures/facture_detail.html', {
            'facture': facture,
        })
    
    @login_required
    def facture_update_view(request, pk):
        """Vue simple pour modifier une facture"""
        entreprise = request.user.entreprise
        from comptabilite.models import Facture
        from django import forms
        
        facture = get_object_or_404(Facture, pk=pk, entreprise=entreprise)
        
        class SimpleFactureForm(forms.ModelForm):
            class Meta:
                model = Facture
                fields = ['numero', 'tiers', 'date_facture', 'date_echeance', 'type_facture', 'montant_ht', 'montant_tva', 'montant_ttc']
                widgets = {
                    'numero': forms.TextInput(attrs={'class': 'form-control'}),
                    'tiers': forms.Select(attrs={'class': 'form-select'}),
                    'date_facture': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                    'date_echeance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                    'type_facture': forms.Select(attrs={'class': 'form-select'}),
                    'montant_ht': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                    'montant_tva': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                    'montant_ttc': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
                }
        
        if request.method == 'POST':
            form = SimpleFactureForm(request.POST, instance=facture)
            if form.is_valid():
                form.save()
                from django.contrib import messages
                messages.success(request, f"Facture {facture.numero} modifiée avec succès!")
                return render(request, 'comptabilite/factures/facture_form.html', {
                    'form': form,
                    'success': True,
                })
        else:
            form = SimpleFactureForm(instance=facture)
        
        return render(request, 'comptabilite/factures/facture_form.html', {
            'form': form,
            'facture': facture,
        })
    
    # Vues fallback pour les états financiers
    @login_required
    def grand_livre_view(request):
        """Vue simple pour le grand livre"""
        entreprise = request.user.entreprise
        from comptabilite.models import EcritureComptable, LigneEcriture, PlanComptable
        
        # Récupérer toutes les lignes d'écritures groupées par compte
        lignes = LigneEcriture.objects.filter(
            ecriture__entreprise=entreprise
        ).select_related('ecriture', 'compte').order_by('compte__numero_compte', 'ecriture__date_ecriture')
        
        # Grouper par compte
        comptes_data = {}
        for ligne in lignes:
            compte_num = ligne.compte.numero_compte
            if compte_num not in comptes_data:
                comptes_data[compte_num] = {
                    'compte': ligne.compte,
                    'lignes': [],
                    'total_debit': 0,
                    'total_credit': 0,
                    'solde': 0
                }
            comptes_data[compte_num]['lignes'].append(ligne)
            comptes_data[compte_num]['total_debit'] += ligne.montant_debit or 0
            comptes_data[compte_num]['total_credit'] += ligne.montant_credit or 0
        
        # Calculer les soldes
        for compte_num in comptes_data:
            data = comptes_data[compte_num]
            data['solde'] = data['total_debit'] - data['total_credit']
        
        return render(request, 'comptabilite/etats/grand_livre.html', {
            'comptes_data': comptes_data,
            'total_general_debit': sum(data['total_debit'] for data in comptes_data.values()),
            'total_general_credit': sum(data['total_credit'] for data in comptes_data.values()),
        })
    
    @login_required
    def balance_view(request):
        """Vue simple pour la balance"""
        entreprise = request.user.entreprise
        from comptabilite.models import LigneEcriture, PlanComptable
        
        # Calculer les totaux par compte
        comptes = PlanComptable.objects.filter(entreprise=entreprise).order_by('numero_compte')
        balance_data = []
        
        for compte in comptes:
            lignes = LigneEcriture.objects.filter(
                ecriture__entreprise=entreprise,
                compte=compte
            )
            
            total_debit = sum(ligne.montant_debit or 0 for ligne in lignes)
            total_credit = sum(ligne.montant_credit or 0 for ligne in lignes)
            solde_debiteur = max(0, total_debit - total_credit)
            solde_crediteur = max(0, total_credit - total_debit)
            
            if total_debit > 0 or total_credit > 0:
                balance_data.append({
                    'compte': compte,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'solde_debiteur': solde_debiteur,
                    'solde_crediteur': solde_crediteur,
                })
        
        total_debit_general = sum(item['total_debit'] for item in balance_data)
        total_credit_general = sum(item['total_credit'] for item in balance_data)
        total_solde_debiteur = sum(item['solde_debiteur'] for item in balance_data)
        total_solde_crediteur = sum(item['solde_crediteur'] for item in balance_data)
        
        return render(request, 'comptabilite/etats/balance.html', {
            'balance_data': balance_data,
            'total_debit_general': total_debit_general,
            'total_credit_general': total_credit_general,
            'total_solde_debiteur': total_solde_debiteur,
            'total_solde_crediteur': total_solde_crediteur,
        })
    
    @login_required
    def bilan_view(request):
        """Vue simple pour le bilan"""
        entreprise = request.user.entreprise
        from comptabilite.models import LigneEcriture, PlanComptable
        
        # Calculer les soldes par classe de comptes
        actif_data = []
        passif_data = []
        
        comptes = PlanComptable.objects.filter(entreprise=entreprise).order_by('numero_compte')
        
        for compte in comptes:
            lignes = LigneEcriture.objects.filter(
                ecriture__entreprise=entreprise,
                compte=compte
            )
            
            total_debit = sum(ligne.montant_debit or 0 for ligne in lignes)
            total_credit = sum(ligne.montant_credit or 0 for ligne in lignes)
            solde = total_debit - total_credit
            
            if solde != 0:
                compte_data = {
                    'compte': compte,
                    'solde': abs(solde)
                }
                
                # Classes 1-5 : Actif, Classes 1-4 et 5 : Passif
                if compte.numero_compte.startswith(('1', '2', '3', '4', '5')):
                    if compte.numero_compte.startswith(('1', '4', '5')):
                        passif_data.append(compte_data)
                    else:
                        actif_data.append(compte_data)
        
        total_actif = sum(item['solde'] for item in actif_data)
        total_passif = sum(item['solde'] for item in passif_data)
        
        return render(request, 'comptabilite/etats/bilan.html', {
            'actif_data': actif_data,
            'passif_data': passif_data,
            'total_actif': total_actif,
            'total_passif': total_passif,
        })
    
    @login_required
    def compte_resultat_view(request):
        """Vue simple pour le compte de résultat"""
        entreprise = request.user.entreprise
        from comptabilite.models import LigneEcriture, PlanComptable
        
        # Calculer les charges et produits
        charges_data = []
        produits_data = []
        
        comptes = PlanComptable.objects.filter(entreprise=entreprise).order_by('numero_compte')
        
        for compte in comptes:
            lignes = LigneEcriture.objects.filter(
                ecriture__entreprise=entreprise,
                compte=compte
            )
            
            total_debit = sum(ligne.montant_debit or 0 for ligne in lignes)
            total_credit = sum(ligne.montant_credit or 0 for ligne in lignes)
            solde = total_debit - total_credit
            
            if solde != 0:
                compte_data = {
                    'compte': compte,
                    'solde': abs(solde)
                }
                
                # Classes 6 : Charges, Classes 7 : Produits
                if compte.numero_compte.startswith('6'):
                    charges_data.append(compte_data)
                elif compte.numero_compte.startswith('7'):
                    produits_data.append(compte_data)
        
        total_charges = sum(item['solde'] for item in charges_data)
        total_produits = sum(item['solde'] for item in produits_data)
        resultat = total_produits - total_charges
        
        return render(request, 'comptabilite/etats/compte_resultat.html', {
            'charges_data': charges_data,
            'produits_data': produits_data,
            'total_charges': total_charges,
            'total_produits': total_produits,
            'resultat': resultat,
        })

    # ── Fallback TemplateView pour toutes les vues _view non définies ci-dessus ──
    _cs = TemplateView.as_view(template_name='comptabilite/coming_soon.html')
    # Tiers
    tiers_list_view = tiers_list_view if 'tiers_list_view' in vars() else _cs
    tiers_create_view = tiers_create_view if 'tiers_create_view' in vars() else _cs
    tiers_detail_view = tiers_detail_view if 'tiers_detail_view' in vars() else _cs
    tiers_update_view = tiers_update_view if 'tiers_update_view' in vars() else _cs
    tiers_delete_view = _cs
    # Factures
    facture_list_view = facture_list_view if 'facture_list_view' in vars() else _cs
    facture_create_view = _cs
    facture_detail_view = _cs
    facture_update_view = _cs
    facture_delete_view = _cs
    facture_valider_view = _cs
    facture_print_view = _cs
    # Écritures
    ecriture_delete_view = _cs
    ecriture_valider_view = _cs
    # Plan comptable
    plan_comptable_update_view = _cs
    plan_comptable_delete_view = _cs
    # Journaux
    journal_list_view = _cs
    journal_create_view = _cs
    journal_detail_view = _cs
    journal_update_view = _cs
    journal_delete_view = _cs
    # Exercices
    exercice_list_view = _cs
    exercice_create_view = _cs
    exercice_detail_view = _cs
    exercice_update_view = _cs
    exercice_delete_view = _cs
    # Règlements
    reglement_create_view = _cs
    reglement_detail_view = _cs
    reglement_update_view = _cs
    reglement_delete_view = _cs
    # Comptes clients/fournisseurs
    compte_client_list_view = _cs
    compte_client_detail_view = _cs
    # Vieillissement/impayés
    vieillissement_creances_view = _cs
    impayes_clients_view = _cs
    vieillissement_dettes_view = _cs
    impayes_fournisseurs_view = _cs

# Vues temporaires pour les autres éléments (seront remplacées progressivement)
tiers_create = tiers_create_view
tiers_detail = tiers_detail_view
tiers_update = tiers_update_view
tiers_delete = tiers_delete_view
facture_create = facture_create_view
facture_detail = facture_detail_view
facture_update = facture_update_view
facture_delete = facture_delete_view
facture_valider = facture_valider_view
facture_print = facture_print_view
ecriture_list = ecriture_list_view
ecriture_delete = ecriture_delete_view
ecriture_valider = ecriture_valider_view
plan_comptable_list = plan_comptable_list_view
plan_comptable_create = plan_comptable_create_view
plan_comptable_detail = plan_comptable_detail_view
plan_comptable_update = plan_comptable_update_view
plan_comptable_delete = plan_comptable_delete_view
journal_list = journal_list_view
journal_create = journal_create_view
journal_detail = journal_detail_view
journal_update = journal_update_view
journal_delete = journal_delete_view
exercice_list = exercice_list_view
exercice_create = exercice_create_view
exercice_detail = exercice_detail_view
exercice_update = exercice_update_view
exercice_delete = exercice_delete_view
tiers_list = tiers_list_view
reglement_list = reglement_list_view
reglement_create = reglement_create_view
reglement_detail = reglement_detail_view
reglement_update = reglement_update_view
reglement_delete = reglement_delete_view

# Les vues comptes clients/fournisseurs sont déjà définies via try/except ci-dessus

app_name = 'comptabilite'

# ============================================================================
# COMPTABILITÉ GÉNÉRALE - Core Module
# ============================================================================

# Plan Comptable URLs
plan_comptable_patterns = [
    path('plan-comptable/', plan_comptable_list, name='plan_comptable_list'),
    path('plan-comptable/nouveau/', plan_comptable_create, name='plan_comptable_create'),
    path('plan-comptable/<int:pk>/', plan_comptable_detail, name='plan_comptable_detail'),
    path('plan-comptable/<int:pk>/editer/', plan_comptable_update, name='plan_comptable_update'),
    path('plan-comptable/<int:pk>/supprimer/', plan_comptable_delete, name='plan_comptable_delete'),
]

# Journaux URLs
journal_patterns = [
    path('journaux/', journal_list, name='journal_list'),
    path('journaux/nouveau/', journal_create, name='journal_create'),
    path('journaux/<int:pk>/', journal_detail, name='journal_detail'),
    path('journaux/<int:pk>/editer/', journal_update, name='journal_update'),
    path('journaux/<int:pk>/supprimer/', journal_delete, name='journal_delete'),
]

# Exercices URLs
exercice_patterns = [
    path('exercices/', exercice_list, name='exercice_list'),
    path('exercices/nouveau/', exercice_create, name='exercice_create'),
    path('exercices/<int:pk>/', exercice_detail, name='exercice_detail'),
    path('exercices/<int:pk>/editer/', exercice_update, name='exercice_update'),
    path('exercices/<int:pk>/supprimer/', exercice_delete, name='exercice_delete'),
]

# Écritures Comptables URLs
ecriture_patterns = [
    path('ecritures/', ecriture_list_view, name='ecriture_list'),
    path('ecritures/nouveau/', ecriture_create_view, name='ecriture_create'),
    path('ecritures/<uuid:pk>/', ecriture_detail_view, name='ecriture_detail'),
    path('ecritures/<uuid:pk>/editer/', ecriture_update_view, name='ecriture_update'),
    path('ecritures/<uuid:pk>/valider/', ecriture_valider, name='ecriture_valider'),
    path('ecritures/<uuid:pk>/supprimer/', ecriture_delete, name='ecriture_delete'),
]

# Tiers URLs
tiers_patterns = [
    path('tiers/', tiers_list_view, name='tiers_list'),
    path('tiers/nouveau/', tiers_create_view, name='tiers_create'),
    path('tiers/<uuid:pk>/', tiers_detail_view, name='tiers_detail'),
    path('tiers/<uuid:pk>/modifier/', tiers_update_view, name='tiers_update'),
    path('tiers/<uuid:pk>/supprimer/', tiers_delete, name='tiers_delete'),
]

# Factures URLs
facture_patterns = [
    path('factures/', facture_list_view, name='facture_list'),
    path('factures/nouveau/', facture_create_view, name='facture_create'),
    path('factures/<uuid:pk>/', facture_detail_view, name='facture_detail'),
    path('factures/<uuid:pk>/editer/', facture_update_view, name='facture_update'),
    path('factures/<uuid:pk>/valider/', facture_valider, name='facture_valider'),
    path('factures/<uuid:pk>/imprimer/', facture_print, name='facture_print'),
    path('factures/<uuid:pk>/supprimer/', facture_delete, name='facture_delete'),
]

# Règlements URLs
reglement_patterns = [
    path('reglements/', reglement_list, name='reglement_list'),
    path('reglements/nouveau/', reglement_create, name='reglement_create'),
    path('reglements/<uuid:pk>/', reglement_detail, name='reglement_detail'),
    path('reglements/<uuid:pk>/editer/', reglement_update, name='reglement_update'),
    path('reglements/<uuid:pk>/supprimer/', reglement_delete, name='reglement_delete'),
]

# Comptes Clients/Fournisseurs URLs
compte_client_patterns = [
    path('comptes-clients/', compte_client_list_view, name='compte_client_list'),
    path('comptes-clients/<uuid:pk>/', compte_client_detail_view, name='compte_client_detail'),
    path('comptes-clients/vieillissement/', vieillissement_creances_view, name='vieillissement_creances'),
    path('comptes-clients/impayes/', impayes_clients_view, name='impayes_clients'),
]

compte_fournisseur_patterns = [
    path('comptes-fournisseurs/', compte_fournisseur_list_view, name='compte_fournisseur_list'),
    path('comptes-fournisseurs/<uuid:pk>/', compte_fournisseur_detail_view, name='compte_fournisseur_detail'),
    path('comptes-fournisseurs/vieillissement/', vieillissement_dettes_view, name='vieillissement_dettes'),
    path('comptes-fournisseurs/impayes/', impayes_fournisseurs_view, name='impayes_fournisseurs'),
]

# États Financiers URLs
grand_livre_pdf_view = globals().get('grand_livre_pdf_view', grand_livre_view)
grand_livre_excel_view = globals().get('grand_livre_excel_view', grand_livre_view)
balance_pdf_view = globals().get('balance_pdf_view', balance_view)
balance_excel_view = globals().get('balance_excel_view', balance_view)
bilan_pdf_view = globals().get('bilan_pdf_view', bilan_view)
compte_resultat_pdf_view = globals().get('compte_resultat_pdf_view', compte_resultat_view)

etats_patterns = [
    path('grand-livre/', grand_livre_view, name='grand_livre'),
    path('grand-livre/pdf/', grand_livre_pdf_view, name='grand_livre_pdf'),
    path('grand-livre/excel/', grand_livre_excel_view, name='grand_livre_excel'),
    path('balance/', balance_view, name='balance'),
    path('balance/pdf/', balance_pdf_view, name='balance_pdf'),
    path('balance/excel/', balance_excel_view, name='balance_excel'),
    path('journal-general/', journal_general_view, name='journal_general'),
    path('bilan/', bilan_view, name='bilan'),
    path('bilan/pdf/', bilan_pdf_view, name='bilan_pdf'),
    path('compte-resultat/', compte_resultat_view, name='compte_resultat'),
    path('compte-resultat/pdf/', compte_resultat_pdf_view, name='compte_resultat_pdf'),
]

# ============================================================================
# RAPPROCHEMENTS BANCAIRES - Main Module for Phase 1
# ============================================================================

# Compte Bancaire URLs
compte_bancaire_patterns = [
    path('comptes/', CompteBancaireListView.as_view(), name='compte-bancaire-list'),
    path('comptes/nouveau/', CompteBancaireCreateView.as_view(), name='compte-bancaire-create'),
    path('comptes/<uuid:pk>/', CompteBancaireDetailView.as_view(), name='compte-bancaire-detail'),
    path('comptes/<uuid:pk>/editer/', CompteBancaireUpdateView.as_view(), name='compte-bancaire-update'),
    path('comptes/<uuid:pk>/supprimer/', CompteBancaireDeleteView.as_view(), name='compte-bancaire-delete'),
]

# Rapprochement Bancaire URLs
rapprochement_patterns = [
    path('rapprochements/', RapprochementListView.as_view(), name='rapprochement-list'),
    path('rapprochements/nouveau/', RapprochementCreateView.as_view(), name='rapprochement-create'),
    path('rapprochements/<uuid:pk>/', RapprochementDetailView.as_view(), name='rapprochement-detail'),
    path('rapprochements/<uuid:pk>/editer/', RapprochementUpdateView.as_view(), name='rapprochement-update'),
    path('rapprochements/<uuid:pk>/supprimer/', RapprochementDeleteView.as_view(), name='rapprochement-delete'),
    path('rapprochements/<uuid:pk>/finaliser/', RapprochementFinalisationView.as_view(), name='rapprochement-finalize'),
]

# Lettrage (Matching) URLs
lettrage_patterns = [
    path('rapprochements/<uuid:rapprochement_id>/lettrer/', LettrageView.as_view(), name='rapprochement-lettrage'),
    path('rapprochements/<uuid:rapprochement_id>/lettrage/<uuid:lettrage_id>/supprimer/', LettrageAnnulationView.as_view(), name='rapprochement-lettrage-delete'),
]

# ============================================================================
# IMPORT/EXPORT Operations
# ============================================================================

import_export_patterns = [
    # Import
    path('importer/', OperationImportView.as_view(), name='operation-import'),
]

# ============================================================================
# AJAX/API Endpoints
# ============================================================================

ajax_patterns = [
]

# ============================================================================
# DASHBOARDS & REPORTS
# ============================================================================

from . import views_livres as _views_livres_dash

dashboard_report_patterns = [
    # Dashboard principal — tableau de bord métier calculé (moteur comptable)
    path('', _views_livres_dash.tableau_bord_compta, name='dashboard'),
    path('tableau-de-bord/', _views_livres_dash.tableau_bord_compta, name='dashboard'),
]

# ============================================================================
# STUBS - PHASES 2/3 (Coming Soon pages)
# ============================================================================

coming_soon_patterns = [
    # Fiscalité (Phase 2)
    path('fiscalite/', TemplateView.as_view(template_name='comptabilite/coming_soon.html'), name='fiscalite-index'),
    # Audit (Phase 3)
    path('audit/', TemplateView.as_view(template_name='comptabilite/coming_soon.html'), name='audit-index'),
]

legacy_patterns = [
    # Les URLs legacy sont désactivées temporairement car elles posent des problèmes d'import
    # TODO: Réimplémenter les vues legacy dans les sous-modules appropriés
]

# ============================================================================
# COMBINED URL PATTERNS
# ============================================================================

from django.urls import include

# Patterns de trésorerie avancée
tresorerie_patterns = [
    path('tresorerie/', include('comptabilite.urls_tresorerie')),
]

# Patterns de consolidation & reporting
consolidation_patterns = [
    path('consolidation/', include('comptabilite.urls_consolidation')),
]

# Patterns de comptabilité analytique
analytique_patterns = [
    path('analytique/', include('comptabilite.urls_analytique')),
]

# Patterns de fiscalité
fiscalite_patterns = [
    path('fiscalite/', include('comptabilite.urls_fiscalite')),
]

# Patterns de contrôle interne
controle_patterns = [
    path('controle/', include('comptabilite.urls_controle')),
]

# Patterns de gestion des contrats
contrats_compta_patterns = [
    path('contrats/', include('comptabilite.urls_contrats')),
]

# Patterns d'archivage
archivage_patterns = [
    path('archivage/', include('comptabilite.urls_archivage')),
]

# ── Livres et documents SYSCOHADA (journaux par type, caisse, bordereaux,
#    emprunts, TFT, notes annexes, registre immobilisations) ────────────────
from . import views_livres

livres_patterns = [
    # Journaux par type (AC/VT/CA/BQ/OD/SA)
    path('livres/journal/<str:type_journal>/', views_livres.journal_par_type, name='journal_par_type'),
    # Balance auxiliaire clients / fournisseurs
    path('livres/balance-auxiliaire/<str:categorie>/', views_livres.balance_auxiliaire, name='balance_auxiliaire'),
    # Caisse
    path('caisse/pieces/', views_livres.piece_caisse_list, name='piece_caisse_list'),
    path('caisse/pieces/nouvelle/', views_livres.piece_caisse_create, name='piece_caisse_create'),
    path('caisse/pieces/<int:pk>/imprimer/', views_livres.piece_caisse_print, name='piece_caisse_print'),
    path('caisse/livre/', views_livres.livre_caisse, name='livre_caisse'),
    path('caisse/situation/', views_livres.situation_caisse, name='situation_caisse'),
    # Reçu / quittance
    path('reglements/<uuid:pk>/recu/', views_livres.reglement_recu, name='reglement_recu'),
    # Bordereaux
    path('bordereaux/', views_livres.bordereau_list, name='bordereau_list'),
    path('bordereaux/nouveau/', views_livres.bordereau_create, name='bordereau_create'),
    path('bordereaux/<int:pk>/imprimer/', views_livres.bordereau_print, name='bordereau_print'),
    # Emprunts
    path('emprunts/', views_livres.emprunt_list, name='emprunt_list'),
    path('emprunts/nouveau/', views_livres.emprunt_create, name='emprunt_create'),
    path('emprunts/<int:pk>/', views_livres.emprunt_detail, name='emprunt_detail'),
    # États financiers complémentaires
    path('etats/flux-tresorerie/', views_livres.tableau_flux_tresorerie, name='flux_tresorerie'),
    path('etats/notes-annexes/', views_livres.notes_annexes, name='notes_annexes'),
    path('etats/registre-immobilisations/', views_livres.registre_immobilisations, name='registre_immobilisations'),
    # Arrêté de caisse
    path('caisse/arretes/', views_livres.arrete_caisse_list, name='arrete_caisse_list'),
    path('caisse/arretes/nouveau/', views_livres.arrete_caisse_create, name='arrete_caisse_create'),
    path('caisse/arretes/<int:pk>/imprimer/', views_livres.arrete_caisse_print, name='arrete_caisse_print'),
    # Relevés de tiers, relances, échéanciers
    path('tiers/<uuid:pk>/releve/', views_livres.releve_tiers, name='releve_tiers'),
    path('tiers/<uuid:pk>/relance/', views_livres.lettre_relance, name='lettre_relance'),
    path('livres/echeancier/<str:categorie>/', views_livres.echeancier_tiers, name='echeancier_tiers'),
    # Journaux spécialisés et livres
    path('livres/journal-tva/', views_livres.journal_tva, name='journal_tva'),
    path('livres/journal-immobilisations/', views_livres.journal_immobilisations, name='journal_immobilisations'),
    path('livres/amortissements/', views_livres.livre_amortissements, name='livre_amortissements'),
    # Analyses et états de gestion
    path('etats/analyse-charges-produits/', views_livres.analyse_charges_produits, name='analyse_charges_produits'),
    path('etats/variation-capitaux/', views_livres.variation_capitaux_propres, name='variation_capitaux'),
    path('etats/situation-bancaire/', views_livres.situation_bancaire, name='situation_bancaire'),
    # Chèques émis
    path('cheques/', views_livres.cheque_list, name='cheque_list'),
    path('cheques/nouveau/', views_livres.cheque_create, name='cheque_create'),
    path('cheques/<int:pk>/imprimer/', views_livres.cheque_print, name='cheque_print'),
    # Assistant opération (moteur comptable)
    path('operations/nouvelle/', views_livres.nouvelle_operation, name='nouvelle_operation'),
    path('plan-comptable/initialiser-syscohada/', views_livres.initialiser_plan_syscohada,
         name='initialiser_plan_syscohada'),
    path('plan-comptable/importer-excel/', views_livres.importer_plan_excel,
         name='importer_plan_excel'),
    path('cloture-periode/', views_livres.cloture_periode, name='cloture_periode'),
    path('cloture-exercice/', views_livres.cloture_exercice, name='cloture_exercice'),
    path('fiscal/situation/', views_livres.situation_fiscale, name='situation_fiscale'),
    path('approbations/', views_livres.approbations, name='approbations'),
    # Déclarations de patente
    path('fiscal/patente/', views_livres.patente_list, name='patente_list'),
    path('fiscal/patente/nouvelle/', views_livres.patente_create, name='patente_create'),
    path('fiscal/patente/<int:pk>/modifier/', views_livres.patente_create, name='patente_update'),
    path('fiscal/patente/<int:pk>/imprimer/', views_livres.patente_print, name='patente_print'),
]

urlpatterns = (
    # Comptabilité Générale
    plan_comptable_patterns +
    journal_patterns +
    exercice_patterns +
    ecriture_patterns +
    tiers_patterns +
    facture_patterns +
    reglement_patterns +
    compte_client_patterns +
    compte_fournisseur_patterns +
    etats_patterns +
    
    # Phase 1: Rapprochements Bancaires (primary)
    rapprochement_patterns +
    compte_bancaire_patterns +
    lettrage_patterns +
    
    # Trésorerie Avancée (CRITIQUE)
    tresorerie_patterns +
    
    # Consolidation & Reporting (CRITIQUE)
    consolidation_patterns +
    
    # Comptabilité Analytique Avancée
    analytique_patterns +
    
    # Fiscalité
    fiscalite_patterns +
    
    # Contrôle Interne & Conformité
    controle_patterns +
    
    # Gestion Comptable des Contrats
    contrats_compta_patterns +
    
    # Documentation & Archivage
    archivage_patterns +

    # Livres et documents SYSCOHADA
    livres_patterns +

    # Utilities
    import_export_patterns +
    ajax_patterns +
    dashboard_report_patterns +
    
    # Stubs for future phases
    coming_soon_patterns +
    
    # Legacy patterns (backward compatibility)
    legacy_patterns
)

# ============================================================================
# FUTURE PHASES (stubs for planning)
# ============================================================================
# Phase 2: FISCALITE
#   - path('declarations/', ...),
#   - path('tva/', ...),
#   - path('cotisations/', ...),
#
# Phase 3: AUDIT
#   - path('audit/', ...),
#   - path('controles/', ...),
#
# Phase 4+: OTHER MODULES
#   - PAIE
#   - IMMOBILISATIONS
#   - STOCKS
#   - ANALYTIQUE
# ============================================================================
