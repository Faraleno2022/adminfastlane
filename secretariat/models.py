"""
Module Secrétariat — Modèles
Gestion administrative quotidienne : courrier, rendez-vous, visiteurs,
appels, documents, tâches, contacts et réunions.

Tous les modèles sont rattachés à une entreprise (multi-entreprise) sur le
même principe que les modules RH et Comptabilité.
"""
from django.db import models
from django.utils import timezone

from core.models import Entreprise, Utilisateur


class Courrier(models.Model):
    """Courriers entrants et sortants avec numéro d'ordre automatique."""
    TYPES = (
        ('entrant', 'Entrant'),
        ('sortant', 'Sortant'),
    )
    STATUTS = (
        ('recu', 'Reçu'),
        ('en_attente', 'En attente'),
        ('traite', 'Traité'),
        ('archive', 'Archivé'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='courriers')
    numero_ordre = models.CharField(max_length=30, verbose_name="Numéro d'ordre")
    type_courrier = models.CharField(max_length=10, choices=TYPES, default='entrant', verbose_name='Type')
    expediteur = models.CharField(max_length=200, blank=True, verbose_name='Expéditeur')
    destinataire = models.CharField(max_length=200, blank=True, verbose_name='Destinataire')
    objet = models.CharField(max_length=255, verbose_name='Objet')
    date_courrier = models.DateField(verbose_name="Date de réception / envoi", default=timezone.now)
    date_enregistrement = models.DateTimeField(auto_now_add=True)
    piece_jointe = models.FileField(upload_to='secretariat/courriers/', blank=True, null=True, verbose_name='Scan / pièce jointe')
    statut = models.CharField(max_length=15, choices=STATUTS, default='recu')
    observations = models.TextField(blank=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='courriers_crees')

    class Meta:
        db_table = 'secretariat_courrier'
        verbose_name = 'Courrier'
        verbose_name_plural = 'Courriers'
        ordering = ['-date_courrier', '-id']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'numero_ordre'], name='unique_courrier_numero_par_entreprise'),
        ]

    def __str__(self):
        return f"{self.numero_ordre} - {self.objet}"


class RendezVous(models.Model):
    """Rendez-vous (agenda journalier, hebdomadaire, mensuel)."""
    STATUTS = (
        ('en_attente', 'En attente'),
        ('confirme', 'Confirmé'),
        ('reporte', 'Reporté'),
        ('annule', 'Annulé'),
        ('termine', 'Terminé'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='rendez_vous')
    nom_visiteur = models.CharField(max_length=200, verbose_name='Nom du visiteur')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    motif = models.CharField(max_length=255, verbose_name='Motif du rendez-vous')
    personne_concernee = models.CharField(max_length=200, blank=True, verbose_name='Personne concernée')
    date_rdv = models.DateTimeField(verbose_name='Date et heure')
    duree_minutes = models.PositiveIntegerField(default=30, verbose_name='Durée (minutes)')
    rappel = models.BooleanField(default=True, verbose_name='Rappel automatique')
    rappel_minutes = models.PositiveIntegerField(default=30, verbose_name='Rappel (minutes avant)')
    statut = models.CharField(max_length=15, choices=STATUTS, default='en_attente')
    observations = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='rdv_crees')

    class Meta:
        db_table = 'secretariat_rendezvous'
        verbose_name = 'Rendez-vous'
        verbose_name_plural = 'Rendez-vous'
        ordering = ['date_rdv']

    def __str__(self):
        return f"{self.nom_visiteur} - {self.date_rdv:%d/%m/%Y %H:%M}"


class Visiteur(models.Model):
    """Registre des visiteurs (entrée / sortie)."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='visiteurs')
    nom = models.CharField(max_length=200, verbose_name='Nom')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    structure = models.CharField(max_length=200, blank=True, verbose_name='Structure / Organisation')
    motif = models.CharField(max_length=255, verbose_name='Motif de la visite')
    service_visite = models.CharField(max_length=200, blank=True, verbose_name='Service visité')
    responsable_visite = models.CharField(max_length=200, blank=True, verbose_name='Responsable visité')
    heure_arrivee = models.DateTimeField(default=timezone.now, verbose_name="Heure d'arrivée")
    heure_sortie = models.DateTimeField(null=True, blank=True, verbose_name='Heure de sortie')
    badge_numero = models.CharField(max_length=30, blank=True, verbose_name='Numéro de badge')
    observations = models.TextField(blank=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='visiteurs_crees')

    class Meta:
        db_table = 'secretariat_visiteur'
        verbose_name = 'Visiteur'
        verbose_name_plural = 'Visiteurs'
        ordering = ['-heure_arrivee']

    def __str__(self):
        return f"{self.nom} ({self.heure_arrivee:%d/%m/%Y})"

    @property
    def present(self):
        return self.heure_sortie is None


class Appel(models.Model):
    """Journal des appels entrants et sortants."""
    TYPES = (
        ('entrant', 'Entrant'),
        ('sortant', 'Sortant'),
        ('manque', 'Manqué'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='appels')
    type_appel = models.CharField(max_length=10, choices=TYPES, default='entrant', verbose_name="Type d'appel")
    nom_appelant = models.CharField(max_length=200, verbose_name="Nom de l'appelant")
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Numéro de téléphone')
    objet = models.CharField(max_length=255, verbose_name="Objet de l'appel")
    message = models.TextField(blank=True, verbose_name='Message laissé')
    suivi_a_faire = models.BooleanField(default=False, verbose_name='Suivi à faire')
    suivi_effectue = models.BooleanField(default=False, verbose_name='Suivi effectué')
    date_appel = models.DateTimeField(default=timezone.now, verbose_name="Date de l'appel")
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='appels_crees')

    class Meta:
        db_table = 'secretariat_appel'
        verbose_name = 'Appel'
        verbose_name_plural = 'Appels'
        ordering = ['-date_appel']

    def __str__(self):
        return f"{self.get_type_appel_display()} - {self.nom_appelant}"


class Document(models.Model):
    """Documents administratifs classés par catégorie."""
    CATEGORIES = (
        ('lettre', 'Lettre'),
        ('rapport', 'Rapport'),
        ('note_service', 'Note de service'),
        ('contrat', 'Contrat'),
        ('facture', 'Facture'),
        ('decision', 'Décision'),
        ('proces_verbal', 'Procès-verbal'),
        ('autre', 'Autre'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='documents_secretariat')
    titre = models.CharField(max_length=255, verbose_name='Titre')
    categorie = models.CharField(max_length=20, choices=CATEGORIES, default='lettre', verbose_name='Catégorie')
    reference = models.CharField(max_length=50, blank=True, verbose_name='Référence')
    fichier = models.FileField(upload_to='secretariat/documents/', blank=True, null=True, verbose_name='Fichier (PDF, Word, Excel)')
    description = models.TextField(blank=True)
    date_document = models.DateField(default=timezone.now, verbose_name='Date du document')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents_secretariat_crees')
    modifie_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents_secretariat_modifies')

    class Meta:
        db_table = 'secretariat_document'
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        ordering = ['-date_document', '-id']

    def __str__(self):
        return self.titre


class Tache(models.Model):
    """Tâches à réaliser avec priorité et échéance."""
    PRIORITES = (
        ('faible', 'Faible'),
        ('moyenne', 'Moyenne'),
        ('urgente', 'Urgente'),
    )
    ETATS = (
        ('a_faire', 'À faire'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='taches_secretariat')
    titre = models.CharField(max_length=255, verbose_name='Tâche')
    description = models.TextField(blank=True)
    priorite = models.CharField(max_length=10, choices=PRIORITES, default='moyenne', verbose_name='Priorité')
    date_limite = models.DateField(null=True, blank=True, verbose_name='Date limite')
    responsable = models.CharField(max_length=200, blank=True, verbose_name='Responsable')
    etat = models.CharField(max_length=10, choices=ETATS, default='a_faire', verbose_name='État')
    rappel = models.BooleanField(default=False, verbose_name='Notification / rappel')
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='taches_secretariat_creees')

    class Meta:
        db_table = 'secretariat_tache'
        verbose_name = 'Tâche'
        verbose_name_plural = 'Tâches'
        ordering = ['etat', 'date_limite']

    def __str__(self):
        return self.titre

    @property
    def en_retard(self):
        if self.date_limite and self.etat != 'termine':
            return self.date_limite < timezone.now().date()
        return False


class Contact(models.Model):
    """Carnet de contacts internes et externes."""
    TYPES = (
        ('interne', 'Contact interne'),
        ('client', 'Client'),
        ('fournisseur', 'Fournisseur'),
        ('partenaire', 'Partenaire'),
        ('administration', 'Administration'),
        ('externe', 'Autre contact externe'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='contacts_secretariat')
    type_contact = models.CharField(max_length=20, choices=TYPES, default='externe', verbose_name='Type de contact')
    nom = models.CharField(max_length=200, verbose_name='Nom')
    telephone = models.CharField(max_length=30, blank=True, verbose_name='Téléphone')
    email = models.EmailField(blank=True, verbose_name='Email')
    adresse = models.TextField(blank=True, verbose_name='Adresse')
    fonction = models.CharField(max_length=200, blank=True, verbose_name='Fonction')
    organisation = models.CharField(max_length=200, blank=True, verbose_name='Organisation')
    observations = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'secretariat_contact'
        verbose_name = 'Contact'
        verbose_name_plural = 'Contacts'
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.get_type_contact_display()})"


class Reunion(models.Model):
    """Planification et compte rendu des réunions."""
    STATUTS = (
        ('planifiee', 'Planifiée'),
        ('terminee', 'Terminée'),
        ('annulee', 'Annulée'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='reunions')
    titre = models.CharField(max_length=255, verbose_name='Objet de la réunion')
    date_reunion = models.DateTimeField(verbose_name='Date et heure')
    lieu = models.CharField(max_length=200, blank=True, verbose_name='Lieu')
    participants = models.TextField(blank=True, verbose_name='Liste des participants')
    ordre_du_jour = models.TextField(blank=True, verbose_name='Ordre du jour')
    compte_rendu = models.TextField(blank=True, verbose_name='Compte rendu')
    decisions = models.TextField(blank=True, verbose_name='Décisions prises')
    statut = models.CharField(max_length=15, choices=STATUTS, default='planifiee')
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='reunions_creees')

    class Meta:
        db_table = 'secretariat_reunion'
        verbose_name = 'Réunion'
        verbose_name_plural = 'Réunions'
        ordering = ['-date_reunion']

    def __str__(self):
        return f"{self.titre} - {self.date_reunion:%d/%m/%Y}"


class ActionReunion(models.Model):
    """Suivi des actions décidées en réunion."""
    ETATS = (
        ('a_faire', 'À faire'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
    )

    reunion = models.ForeignKey(Reunion, on_delete=models.CASCADE, related_name='actions')
    description = models.CharField(max_length=255, verbose_name='Action')
    responsable = models.CharField(max_length=200, blank=True, verbose_name='Responsable')
    echeance = models.DateField(null=True, blank=True, verbose_name='Échéance')
    etat = models.CharField(max_length=10, choices=ETATS, default='a_faire', verbose_name='État')

    class Meta:
        db_table = 'secretariat_action_reunion'
        verbose_name = 'Action de réunion'
        verbose_name_plural = 'Actions de réunion'
        ordering = ['echeance']

    def __str__(self):
        return self.description


class ModeleDocument(models.Model):
    """Modèles de documents réutilisables (paramètres)."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='modeles_documents')
    nom = models.CharField(max_length=200, verbose_name='Nom du modèle')
    categorie = models.CharField(max_length=20, choices=Document.CATEGORIES, default='lettre', verbose_name='Catégorie')
    contenu = models.TextField(blank=True, verbose_name='Contenu du modèle')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'secretariat_modele_document'
        verbose_name = 'Modèle de document'
        verbose_name_plural = 'Modèles de documents'
        ordering = ['nom']

    def __str__(self):
        return self.nom
