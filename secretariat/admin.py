from django.contrib import admin

from .models import (
    Courrier, RendezVous, Visiteur, Appel, Document, Tache,
    Contact, Reunion, ActionReunion, ModeleDocument,
)


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = ('numero_ordre', 'type_courrier', 'objet', 'expediteur', 'destinataire', 'date_courrier', 'statut')
    list_filter = ('type_courrier', 'statut', 'entreprise')
    search_fields = ('numero_ordre', 'objet', 'expediteur', 'destinataire')


@admin.register(RendezVous)
class RendezVousAdmin(admin.ModelAdmin):
    list_display = ('nom_visiteur', 'motif', 'date_rdv', 'personne_concernee', 'statut')
    list_filter = ('statut', 'entreprise')
    search_fields = ('nom_visiteur', 'motif', 'personne_concernee')


@admin.register(Visiteur)
class VisiteurAdmin(admin.ModelAdmin):
    list_display = ('nom', 'structure', 'motif', 'heure_arrivee', 'heure_sortie')
    list_filter = ('entreprise',)
    search_fields = ('nom', 'structure', 'motif')


@admin.register(Appel)
class AppelAdmin(admin.ModelAdmin):
    list_display = ('type_appel', 'nom_appelant', 'telephone', 'objet', 'date_appel', 'suivi_a_faire')
    list_filter = ('type_appel', 'suivi_a_faire', 'entreprise')
    search_fields = ('nom_appelant', 'objet', 'telephone')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('titre', 'categorie', 'reference', 'date_document')
    list_filter = ('categorie', 'entreprise')
    search_fields = ('titre', 'reference', 'description')


@admin.register(Tache)
class TacheAdmin(admin.ModelAdmin):
    list_display = ('titre', 'priorite', 'date_limite', 'responsable', 'etat')
    list_filter = ('priorite', 'etat', 'entreprise')
    search_fields = ('titre', 'responsable')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_contact', 'telephone', 'email', 'organisation')
    list_filter = ('type_contact', 'entreprise')
    search_fields = ('nom', 'organisation', 'email', 'telephone')


class ActionReunionInline(admin.TabularInline):
    model = ActionReunion
    extra = 1


@admin.register(Reunion)
class ReunionAdmin(admin.ModelAdmin):
    list_display = ('titre', 'date_reunion', 'lieu', 'statut')
    list_filter = ('statut', 'entreprise')
    search_fields = ('titre', 'lieu')
    inlines = [ActionReunionInline]


@admin.register(ModeleDocument)
class ModeleDocumentAdmin(admin.ModelAdmin):
    list_display = ('nom', 'categorie', 'actif')
    list_filter = ('categorie', 'actif', 'entreprise')
    search_fields = ('nom',)
