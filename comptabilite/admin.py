from django.contrib import admin
from .models import (
    PlanComptable, Journal, ExerciceComptable, EcritureComptable,
    LigneEcriture, Tiers, Facture, LigneFacture, Reglement, TauxTVA, PieceComptable,
    PieceCaisse, BordereauRemise, LigneBordereau, Emprunt, ArreteCaisse,
    ChequeEmis, DeclarationPatente, RegleEcriture
)


@admin.register(PlanComptable)
class PlanComptableAdmin(admin.ModelAdmin):
    list_display = ['numero_compte', 'intitule', 'classe', 'entreprise', 'est_actif']
    list_filter = ['classe', 'est_actif', 'entreprise']
    search_fields = ['numero_compte', 'intitule']
    ordering = ['numero_compte']


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ['code', 'libelle', 'type_journal', 'entreprise', 'est_actif']
    list_filter = ['type_journal', 'est_actif', 'entreprise']
    search_fields = ['code', 'libelle']


@admin.register(ExerciceComptable)
class ExerciceComptableAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'date_debut', 'date_fin', 'statut', 'est_courant', 'entreprise']
    list_filter = ['statut', 'est_courant', 'entreprise']
    search_fields = ['libelle']


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcriture
    extra = 2


@admin.register(EcritureComptable)
class EcritureComptableAdmin(admin.ModelAdmin):
    list_display = ['numero_ecriture', 'date_ecriture', 'libelle', 'journal', 'est_validee', 'entreprise']
    list_filter = ['est_validee', 'journal', 'entreprise']
    search_fields = ['numero_ecriture', 'libelle']
    inlines = [LigneEcritureInline]
    date_hierarchy = 'date_ecriture'


@admin.register(Tiers)
class TiersAdmin(admin.ModelAdmin):
    list_display = ['code', 'raison_sociale', 'type_tiers', 'telephone', 'est_actif', 'entreprise']
    list_filter = ['type_tiers', 'est_actif', 'entreprise']
    search_fields = ['code', 'raison_sociale', 'nif']


class LigneFactureInline(admin.TabularInline):
    model = LigneFacture
    extra = 1


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ['numero', 'type_facture', 'tiers', 'date_facture', 'montant_ttc', 'statut', 'entreprise']
    list_filter = ['type_facture', 'statut', 'entreprise']
    search_fields = ['numero', 'tiers__raison_sociale']
    inlines = [LigneFactureInline]
    date_hierarchy = 'date_facture'


@admin.register(Reglement)
class ReglementAdmin(admin.ModelAdmin):
    list_display = ['numero', 'facture', 'date_reglement', 'montant', 'mode_paiement', 'entreprise']
    list_filter = ['mode_paiement', 'entreprise']
    search_fields = ['numero', 'reference']
    date_hierarchy = 'date_reglement'


@admin.register(TauxTVA)
class TauxTVAAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'taux', 'nature', 'actif', 'date_debut']
    list_filter = ['nature', 'actif', 'regime_tva']


@admin.register(PieceComptable)
class PieceComptableAdmin(admin.ModelAdmin):
    list_display = ['numero', 'type_piece', 'date_piece', 'libelle', 'montant_ttc', 'entreprise']
    list_filter = ['type_piece', 'entreprise']
    search_fields = ['numero', 'libelle']
    date_hierarchy = 'date_piece'


@admin.register(PieceCaisse)
class PieceCaisseAdmin(admin.ModelAdmin):
    list_display = ['numero', 'type_piece', 'date_operation', 'libelle', 'montant', 'entreprise']
    list_filter = ['type_piece', 'entreprise']
    search_fields = ['numero', 'libelle', 'beneficiaire']
    date_hierarchy = 'date_operation'


class LigneBordereauInline(admin.TabularInline):
    model = LigneBordereau
    extra = 0


@admin.register(BordereauRemise)
class BordereauRemiseAdmin(admin.ModelAdmin):
    list_display = ['numero', 'type_bordereau', 'date_remise', 'compte_bancaire', 'entreprise']
    list_filter = ['type_bordereau', 'entreprise']
    search_fields = ['numero', 'deposant']
    date_hierarchy = 'date_remise'
    inlines = [LigneBordereauInline]


@admin.register(Emprunt)
class EmpruntAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'preteur', 'capital_emprunte', 'taux_annuel', 'nombre_echeances', 'periodicite', 'statut', 'entreprise']
    list_filter = ['statut', 'periodicite', 'entreprise']
    search_fields = ['libelle', 'preteur', 'reference_contrat']


@admin.register(ArreteCaisse)
class ArreteCaisseAdmin(admin.ModelAdmin):
    list_display = ['numero', 'date_arrete', 'caissier', 'solde_theorique', 'entreprise']
    list_filter = ['entreprise']
    search_fields = ['numero', 'caissier']
    date_hierarchy = 'date_arrete'


@admin.register(ChequeEmis)
class ChequeEmisAdmin(admin.ModelAdmin):
    list_display = ['numero_cheque', 'date_emission', 'beneficiaire', 'montant', 'statut', 'entreprise']
    list_filter = ['statut', 'entreprise']
    search_fields = ['numero_cheque', 'beneficiaire']
    date_hierarchy = 'date_emission'


@admin.register(DeclarationPatente)
class DeclarationPatenteAdmin(admin.ModelAdmin):
    list_display = ['annee', 'activite', 'droit_fixe', 'droit_proportionnel', 'statut', 'entreprise']
    list_filter = ['statut', 'annee', 'entreprise']
    search_fields = ['activite']


@admin.register(RegleEcriture)
class RegleEcritureAdmin(admin.ModelAdmin):
    list_display = ['operation', 'ordre', 'sens', 'role_compte', 'compte_numero',
                    'base_montant', 'journal_type', 'entreprise', 'est_active']
    list_filter = ['operation', 'sens', 'est_active', 'entreprise']
    search_fields = ['operation', 'compte_numero', 'compte_intitule']
    list_editable = ['ordre', 'est_active']
    ordering = ['operation', 'ordre']


from .models_livres import RegleValidation, DemandeApprobation, DecisionApprobation


@admin.register(RegleValidation)
class RegleValidationAdmin(admin.ModelAdmin):
    list_display = ['type_document', 'seuil_montant', 'nb_approbations',
                    'niveau_acces_min', 'description', 'entreprise', 'est_active']
    list_filter = ['type_document', 'est_active', 'entreprise']
    list_editable = ['seuil_montant', 'nb_approbations', 'niveau_acces_min', 'est_active']


class DecisionApprobationInline(admin.TabularInline):
    model = DecisionApprobation
    extra = 0
    readonly_fields = ['approbateur', 'decision', 'commentaire', 'date_decision']


@admin.register(DemandeApprobation)
class DemandeApprobationAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'type_document', 'montant', 'statut', 'demandeur', 'date_creation']
    list_filter = ['statut', 'type_document', 'entreprise']
    search_fields = ['libelle', 'objet_id']
    inlines = [DecisionApprobationInline]
