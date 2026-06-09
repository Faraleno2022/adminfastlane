"""
Module Secrétariat — Formulaires (ModelForms)
Le widget Bootstrap est appliqué automatiquement à tous les champs.
"""
from django import forms

from .models import (
    Courrier, RendezVous, Visiteur, Appel, Document, Tache,
    Contact, Reunion, ActionReunion, ModeleDocument,
)


class BootstrapModelForm(forms.ModelForm):
    """Applique les classes Bootstrap à tous les widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select')
            else:
                widget.attrs.setdefault('class', 'form-control')


class CourrierForm(BootstrapModelForm):
    class Meta:
        model = Courrier
        fields = ['type_courrier', 'expediteur', 'destinataire', 'objet',
                  'date_courrier', 'piece_jointe', 'statut', 'observations']
        widgets = {
            'date_courrier': forms.DateInput(attrs={'type': 'date'}),
            'observations': forms.Textarea(attrs={'rows': 3}),
        }


class RendezVousForm(BootstrapModelForm):
    class Meta:
        model = RendezVous
        fields = ['nom_visiteur', 'telephone', 'motif', 'personne_concernee',
                  'date_rdv', 'duree_minutes', 'rappel', 'rappel_minutes',
                  'statut', 'observations']
        widgets = {
            'date_rdv': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'observations': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_rdv'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']


class VisiteurForm(BootstrapModelForm):
    class Meta:
        model = Visiteur
        fields = ['nom', 'telephone', 'structure', 'motif', 'service_visite',
                  'responsable_visite', 'heure_arrivee', 'heure_sortie',
                  'badge_numero', 'observations']
        widgets = {
            'heure_arrivee': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'heure_sortie': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'observations': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('heure_arrivee', 'heure_sortie'):
            self.fields[f].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']


class AppelForm(BootstrapModelForm):
    class Meta:
        model = Appel
        fields = ['type_appel', 'nom_appelant', 'telephone', 'objet', 'message',
                  'date_appel', 'suivi_a_faire', 'suivi_effectue']
        widgets = {
            'date_appel': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'message': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_appel'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']


class DocumentForm(BootstrapModelForm):
    class Meta:
        model = Document
        fields = ['titre', 'categorie', 'reference', 'fichier', 'description', 'date_document']
        widgets = {
            'date_document': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class TacheForm(BootstrapModelForm):
    class Meta:
        model = Tache
        fields = ['titre', 'description', 'priorite', 'date_limite',
                  'responsable', 'etat', 'rappel']
        widgets = {
            'date_limite': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class ContactForm(BootstrapModelForm):
    class Meta:
        model = Contact
        fields = ['type_contact', 'nom', 'telephone', 'email', 'adresse',
                  'fonction', 'organisation', 'observations']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'observations': forms.Textarea(attrs={'rows': 2}),
        }


class ReunionForm(BootstrapModelForm):
    class Meta:
        model = Reunion
        fields = ['titre', 'date_reunion', 'lieu', 'participants', 'ordre_du_jour',
                  'compte_rendu', 'decisions', 'statut']
        widgets = {
            'date_reunion': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'participants': forms.Textarea(attrs={'rows': 3}),
            'ordre_du_jour': forms.Textarea(attrs={'rows': 4}),
            'compte_rendu': forms.Textarea(attrs={'rows': 4}),
            'decisions': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_reunion'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']


class ActionReunionForm(BootstrapModelForm):
    class Meta:
        model = ActionReunion
        fields = ['description', 'responsable', 'echeance', 'etat']
        widgets = {
            'echeance': forms.DateInput(attrs={'type': 'date'}),
        }


class ModeleDocumentForm(BootstrapModelForm):
    class Meta:
        model = ModeleDocument
        fields = ['nom', 'categorie', 'contenu', 'actif']
        widgets = {
            'contenu': forms.Textarea(attrs={'rows': 8}),
        }
