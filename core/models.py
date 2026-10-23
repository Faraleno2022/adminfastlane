from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid


class Entreprise(models.Model):
    """Modèle pour gérer plusieurs entreprises"""
    TYPES_MODULE = [
        ('rh', 'Ressources Humaines'),
        ('compta', 'Comptabilité'),
        ('secretariat', 'Secrétariat'),
        ('stock', 'Gestion de Stock'),
        ('both', 'RH + Comptabilité'),
        ('all', 'RH + Comptabilité + Secrétariat'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_entreprise = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=100)
    type_module = models.CharField(max_length=20, choices=TYPES_MODULE, default='rh', verbose_name='Type de compte')
    secteur_activite = models.CharField(max_length=100, blank=True, null=True, verbose_name='Secteur d\'activité')
    nif = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='NIF')
    nifp = models.CharField(max_length=50, blank=True, null=True, verbose_name='NIF-p (eTax DGI)')
    num_cnss = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='N° CNSS')
    adresse = models.TextField(blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    pays = models.CharField(max_length=50, default='Guinée')
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField()
    logo = models.ImageField(upload_to='entreprises/logos/', blank=True, null=True)

    # Coordonnées bancaires (télépaiement DGI / virements)
    banque_nom = models.CharField(max_length=200, blank=True, null=True, verbose_name='Nom de la banque')
    banque_code = models.CharField(max_length=10, blank=True, null=True, verbose_name='Code banque')
    banque_guichet = models.CharField(max_length=10, blank=True, null=True, verbose_name='Code guichet')
    banque_compte = models.CharField(max_length=30, blank=True, null=True, verbose_name='Numéro de compte')
    banque_cle_rib = models.CharField(max_length=20, blank=True, null=True, verbose_name='Clé RIB')
    banque_iban = models.CharField(max_length=34, blank=True, null=True, verbose_name='IBAN')
    telepaiement_autorise = models.BooleanField(default=False, verbose_name='Télépaiement DGI autorisé')

    date_creation = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateField(blank=True, null=True, help_text='Date d\'expiration de l\'abonnement')
    actif = models.BooleanField(default=True)
    plan_abonnement = models.CharField(max_length=50, default='gratuit', choices=[
        ('gratuit', 'Gratuit'),
        ('basique', 'Basique'),
        ('starter', 'Starter'),
        ('pro', 'Pro'),
        ('premium', 'Premium'),
        ('entreprise', 'Entreprise'),
    ])
    max_utilisateurs = models.IntegerField(default=5, help_text='Nombre maximum d\'utilisateurs')
    max_employes = models.IntegerField(default=30, help_text='Nombre maximum d\'employés')

    # Flags modules — synchronisés depuis PlanAbonnement lors de l'activation
    module_paie = models.BooleanField(default=True)
    module_conges = models.BooleanField(default=True)
    module_recrutement = models.BooleanField(default=False)
    module_formation = models.BooleanField(default=False)
    module_comptabilite = models.BooleanField(default=False)
    module_portail = models.BooleanField(default=False)
    acces_declarations_fiscales = models.BooleanField(default=False)
    acces_export_comptable = models.BooleanField(default=False)
    # Applications choisies à l'inscription ou dans Paramètres > Applications (clés de
    # core.odoo_menu). Liste vide = comptes antérieurs : règles fondées sur type_module.
    applications = models.JSONField(default=list, blank=True, verbose_name='Applications installées')

    @property
    def has_rh(self):
        from core.licence_utils import licence_offline_valide
        if licence_offline_valide():
            return True
        if self.applications:
            from core.odoo_menu import CLES_RH
            return any(cle in self.applications for cle in CLES_RH)
        return self.type_module in ['rh', 'both', 'all']

    @property
    def has_compta(self):
        from core.licence_utils import licence_offline_valide
        if licence_offline_valide():
            return True
        if self.applications:
            return 'compta' in self.applications
        return self.type_module in ['compta', 'both', 'all']

    @property
    def has_secretariat(self):
        """Le module Secrétariat est inclus dans tous les types de compte."""
        return True

    @property
    def has_stock(self):
        """Le module Gestion du Stock est inclus dans tous les types de compte."""
        return True

    def has_module(self, module_name):
        """Vérifie si l'entreprise a accès à un module donné.
        Une licence offline valide débloque tous les modules."""
        from core.licence_utils import licence_offline_valide
        if licence_offline_valide():
            return True
        module_map = {
            'paie': self.module_paie,
            'conges': self.module_conges,
            'recrutement': self.module_recrutement,
            'formation': self.module_formation,
            'comptabilite': self.module_comptabilite,
            'portail': self.module_portail,
        }
        return module_map.get(module_name, False)

    def sync_from_plan(self, plan):
        """Synchronise les limites et modules depuis un PlanAbonnement"""
        self.max_utilisateurs = plan.max_utilisateurs
        self.max_employes = plan.max_employes
        self.module_paie = plan.module_paie
        self.module_conges = plan.module_conges
        self.module_recrutement = plan.module_recrutement
        self.module_formation = plan.module_formation
        self.module_comptabilite = getattr(plan, 'module_comptabilite', False)
        self.module_portail = getattr(plan, 'module_portail', False)
        self.acces_declarations_fiscales = getattr(plan, 'declarations_fiscales', False)
        self.acces_export_comptable = getattr(plan, 'export_comptable', False)
    
    class Meta:
        db_table = 'entreprises'
        verbose_name = 'Entreprise'
        verbose_name_plural = 'Entreprises'
        ordering = ['nom_entreprise']
    
    def __str__(self):
        return self.nom_entreprise


class ProfilUtilisateur(models.Model):
    """Profils d'utilisateurs avec niveaux d'accès"""
    NIVEAUX_ACCES = (
        (1, 'Consultation'),
        (2, 'Opérateur'),
        (3, 'Manager'),
        (4, 'RH'),
        (5, 'Administrateur'),
    )
    
    nom_profil = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    niveau_acces = models.IntegerField(choices=NIVEAUX_ACCES, default=1)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'profils_utilisateurs'
        verbose_name = 'Profil utilisateur'
        verbose_name_plural = 'Profils utilisateurs'
        ordering = ['niveau_acces']
    
    def __str__(self):
        return self.nom_profil


class Utilisateur(AbstractUser):
    """Modèle utilisateur personnalisé avec support multi-entreprise"""
    # L'identifiant de connexion est le nom d'utilisateur : un même e-mail peut servir
    # à plusieurs comptes (par exemple un gérant inscrit dans plusieurs entreprises).
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True, null=True)
    # SET_NULL : supprimer une entreprise ne doit JAMAIS supprimer ses
    # utilisateurs (ils gardent leur compte et leur historique)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.SET_NULL,
                                   related_name='utilisateurs', null=True, blank=True)
    profil = models.ForeignKey(ProfilUtilisateur, on_delete=models.SET_NULL, null=True, related_name='utilisateurs')
    est_admin_entreprise = models.BooleanField(default=False, help_text='Administrateur de l\'entreprise')
    actif = models.BooleanField(default=True)
    date_derniere_connexion = models.DateTimeField(null=True, blank=True)
    tentatives_connexion = models.IntegerField(default=0)
    photo = models.ImageField(upload_to='utilisateurs/', blank=True, null=True)
    require_reauth = models.BooleanField(default=False, help_text='Nécessite une réauthentification pour accéder aux menus')
    last_reauth = models.DateTimeField(null=True, blank=True, help_text='Dernière réauthentification')
    
    # Fix for groups and user_permissions clash
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='utilisateur_set',
        related_query_name='utilisateur',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='utilisateur_set',
        related_query_name='utilisateur',
    )
    
    class Meta:
        db_table = 'utilisateurs'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"
    
    def enregistrer_connexion(self):
        """Enregistre la date de dernière connexion"""
        self.date_derniere_connexion = timezone.now()
        self.tentatives_connexion = 0
        self.save(update_fields=['date_derniere_connexion', 'tentatives_connexion'])

    def role_dans(self, entreprise=None):
        """Rôle métier de l'utilisateur dans une entreprise (défaut : la sienne).
        L'admin d'entreprise et le superuser sont administrateurs implicites."""
        entreprise = entreprise or self.entreprise
        if self.is_superuser or self.est_admin_entreprise:
            return 'administrateur'
        if entreprise is None:
            return None
        acces = self.acces_entreprises.filter(entreprise=entreprise).first()
        if acces and acces.est_valide():
            return acces.role
        return None

    def has_permission(self, code, entreprise=None, _sans_delegation=False):
        """Moteur d'autorisations : True si le rôle de l'utilisateur possède
        la permission (ex. 'facture.approuver'), ou si une délégation valide
        lui transmet celle d'un délégant. Superuser : tout."""
        if self.is_superuser:
            return True
        entreprise = entreprise or self.entreprise
        role = self.role_dans(entreprise)
        if role and PermissionRole.objects.filter(role=role, permission=code).exists():
            return True
        # Délégation de pouvoir active
        if not _sans_delegation and entreprise is not None:
            aujourd_hui = timezone.now().date()
            delegations = Delegation.objects.filter(
                delegataire=self, entreprise=entreprise, actif=True,
                date_debut__lte=aujourd_hui, date_fin__gte=aujourd_hui
            ).select_related('delegant')
            for d in delegations:
                if d.delegant.has_permission(code, entreprise, _sans_delegation=True):
                    return True
        return False


class AccesEntreprise(models.Model):
    """Table d'association Utilisateur ↔ Entreprise (multi-sociétés) :
    rôle métier, période de validité, activation. Supprimer une entreprise
    ne supprime que les accès, jamais les utilisateurs."""
    ROLES = (
        ('comptable', 'Comptable (saisie)'),
        ('chef_comptable', 'Chef comptable (validation comptable)'),
        ('daf', 'DAF (validation financière)'),
        ('dg', 'Directeur général (validation exceptionnelle)'),
        ('auditeur', 'Auditeur (lecture seule)'),
        ('administrateur', 'Administrateur (paramétrage)'),
    )

    utilisateur = models.ForeignKey('Utilisateur', on_delete=models.CASCADE,
                                    related_name='acces_entreprises')
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE,
                                   related_name='acces_utilisateurs')
    role = models.CharField(max_length=20, choices=ROLES, default='comptable',
                            verbose_name='Rôle dans cette entreprise')
    date_debut = models.DateField(null=True, blank=True,
                                  verbose_name='Début de validité (vide = immédiat)')
    date_fin = models.DateField(null=True, blank=True,
                                verbose_name='Fin de validité (vide = illimité)')
    actif = models.BooleanField(default=True)
    accorde_par = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='acces_accordes')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'acces_entreprises'
        verbose_name = 'Accès entreprise (multi-sociétés)'
        verbose_name_plural = 'Accès entreprises (multi-sociétés)'
        unique_together = ['utilisateur', 'entreprise']

    def __str__(self):
        return f"{self.utilisateur} → {self.entreprise} ({self.get_role_display()})"

    def est_valide(self, a_date=None):
        from django.utils import timezone as tz
        a_date = a_date or tz.now().date()
        if not self.actif:
            return False
        if self.date_debut and a_date < self.date_debut:
            return False
        if self.date_fin and a_date > self.date_fin:
            return False
        return True


class PermissionRole(models.Model):
    """Moteur d'autorisations : quelles permissions chaque rôle possède.
    Configurable via l'admin — ex. ('daf', 'facture.approuver').
    Codes : <domaine>.<action> — facture.saisir, facture.approuver,
    ecriture.saisir, ecriture.valider, reglement.approuver,
    cloture.periode, cloture.exercice, parametrage.gerer, lecture.etats…"""
    role = models.CharField(max_length=20, choices=AccesEntreprise.ROLES)
    permission = models.CharField(max_length=60, verbose_name='Code permission')

    class Meta:
        db_table = 'permissions_roles'
        verbose_name = 'Permission de rôle'
        verbose_name_plural = 'Permissions des rôles'
        unique_together = ['role', 'permission']
        ordering = ['role', 'permission']

    def __str__(self):
        return f"{self.get_role_display()} : {self.permission}"

    # Jeu de permissions par défaut (seed idempotent)
    DEFAUTS = {
        'comptable': ['lecture.etats', 'ecriture.saisir', 'facture.saisir',
                      'piece_caisse.saisir', 'operation.saisir'],
        'chef_comptable': ['lecture.etats', 'ecriture.saisir', 'ecriture.valider',
                           'facture.saisir', 'facture.valider', 'facture.approuver',
                           'piece_caisse.saisir', 'piece_caisse.approuver',
                           'operation.saisir', 'cloture.periode'],
        'daf': ['lecture.etats', 'facture.valider', 'facture.approuver',
                'reglement.approuver', 'operation.approuver',
                'cloture.periode', 'cloture.exercice'],
        'dg': ['lecture.etats', 'facture.approuver', 'reglement.approuver',
               'piece_caisse.approuver', 'operation.approuver', 'cloture.exercice'],
        'auditeur': ['lecture.etats'],
        'administrateur': ['lecture.etats', 'ecriture.saisir', 'ecriture.valider',
                           'facture.saisir', 'facture.valider', 'facture.approuver',
                           'reglement.approuver', 'piece_caisse.saisir',
                           'piece_caisse.approuver', 'operation.saisir',
                           'operation.approuver', 'cloture.periode',
                           'cloture.exercice', 'parametrage.gerer'],
    }

    @classmethod
    def initialiser_defauts(cls):
        crees = 0
        for role, permissions in cls.DEFAUTS.items():
            for permission in permissions:
                _, cree = cls.objects.get_or_create(role=role, permission=permission)
                crees += cree
        return crees


class Delegation(models.Model):
    """Délégation de pouvoir temporaire : pendant la période, le délégataire
    exerce les permissions du délégant (ex. DAF en congé)."""
    delegant = models.ForeignKey('Utilisateur', on_delete=models.CASCADE,
                                 related_name='delegations_accordees')
    delegataire = models.ForeignKey('Utilisateur', on_delete=models.CASCADE,
                                    related_name='delegations_obtenues')
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE,
                                   related_name='delegations')
    date_debut = models.DateField(verbose_name='Début')
    date_fin = models.DateField(verbose_name='Fin')
    motif = models.CharField(max_length=200, blank=True, verbose_name='Motif (congé, mission…)')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'delegations'
        verbose_name = 'Délégation'
        verbose_name_plural = 'Délégations'

    def __str__(self):
        return f"{self.delegant} → {self.delegataire} ({self.date_debut} au {self.date_fin})"

    def est_valide(self, a_date=None):
        from django.utils import timezone as tz
        a_date = a_date or tz.now().date()
        return self.actif and self.date_debut <= a_date <= self.date_fin


class DroitAcces(models.Model):
    """Droits d'accès par module pour chaque profil"""
    MODULES = (
        ('employes', 'Employés'),
        ('paie', 'Paie'),
        ('temps_travail', 'Temps de travail'),
        ('conges', 'Congés'),
        ('formation', 'Formation'),
        ('recrutement', 'Recrutement'),
        ('comptabilite', 'Comptabilité'),
        ('dashboard', 'Tableau de bord'),
        ('rapports', 'Rapports'),
        ('parametres', 'Paramètres'),
    )
    
    profil = models.ForeignKey(ProfilUtilisateur, on_delete=models.CASCADE, related_name='droits')
    module = models.CharField(max_length=50, choices=MODULES)
    lecture = models.BooleanField(default=False)
    ecriture = models.BooleanField(default=False)
    modification = models.BooleanField(default=False)
    suppression = models.BooleanField(default=False)
    validation = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'droits_acces'
        verbose_name = 'Droit d\'accès'
        verbose_name_plural = 'Droits d\'accès'
        unique_together = ['profil', 'module']
    
    def __str__(self):
        return f"{self.profil.nom_profil} - {self.get_module_display()}"


class LogActivite(models.Model):
    """Journal des activités utilisateurs"""
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name='logs')
    action = models.CharField(max_length=100)
    module = models.CharField(max_length=50, blank=True, null=True)
    table_concernee = models.CharField(max_length=50, blank=True, null=True)
    id_enregistrement = models.IntegerField(null=True, blank=True)
    details = models.TextField(blank=True, null=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    date_action = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'logs_activite'
        verbose_name = 'Log d\'activité'
        verbose_name_plural = 'Logs d\'activité'
        ordering = ['-date_action']
    
    def __str__(self):
        return f"{self.utilisateur} - {self.action} - {self.date_action}"


class Societe(models.Model):
    """Informations sur la société"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='societes', null=True, blank=True)
    raison_sociale = models.CharField(max_length=200)
    forme_juridique = models.CharField(max_length=50, blank=True, null=True)
    nif = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='NIF')
    num_cnss_employeur = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='N° CNSS Employeur')
    num_inam = models.CharField(max_length=50, blank=True, null=True, verbose_name='N° INAM')
    adresse = models.TextField(blank=True, null=True)
    commune = models.CharField(max_length=100, blank=True, null=True)
    prefecture = models.CharField(max_length=100, blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    pays = models.CharField(max_length=50, default='Guinée')
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    site_web = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='societe/', blank=True, null=True)
    date_creation = models.DateField(blank=True, null=True)
    capital_social = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    secteur_activite = models.CharField(max_length=100, blank=True, null=True)
    code_ape = models.CharField(max_length=10, blank=True, null=True)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'societe'
        verbose_name = 'Société'
        verbose_name_plural = 'Sociétés'
    
    def __str__(self):
        return self.raison_sociale


class Etablissement(models.Model):
    """Établissements de la société"""
    TYPES = (
        ('siege', 'Siège'),
        ('agence', 'Agence'),
        ('succursale', 'Succursale'),
        ('usine', 'Usine'),
    )
    
    societe = models.ForeignKey(Societe, on_delete=models.CASCADE, related_name='etablissements')
    code_etablissement = models.CharField(max_length=20, unique=True)
    nom_etablissement = models.CharField(max_length=200)
    type_etablissement = models.CharField(max_length=50, choices=TYPES, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    commune = models.CharField(max_length=100, blank=True, null=True)
    prefecture = models.CharField(max_length=100, blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    responsable = models.CharField(max_length=100, blank=True, null=True)
    date_ouverture = models.DateField(blank=True, null=True)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'etablissements'
        verbose_name = 'Établissement'
        verbose_name_plural = 'Établissements'
        ordering = ['nom_etablissement']
    
    def __str__(self):
        return f"{self.code_etablissement} - {self.nom_etablissement}"


class Service(models.Model):
    """Services/Départements"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='services', null=True, blank=True)
    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='services', null=True, blank=True)
    code_service = models.CharField(max_length=20)
    nom_service = models.CharField(max_length=100)
    service_parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sous_services')
    niveau_hierarchique = models.IntegerField(default=1)
    responsable_service = models.ForeignKey('employes.Employe', on_delete=models.SET_NULL, null=True, blank=True, related_name='services_geres')
    description = models.TextField(blank=True, null=True)
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'services'
        verbose_name = 'Service'
        verbose_name_plural = 'Services'
        ordering = ['nom_service']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'code_service'], name='unique_service_par_entreprise'),
        ]
    
    def __str__(self):
        return f"{self.code_service} - {self.nom_service}"


class Poste(models.Model):
    """Postes de travail"""
    CATEGORIES = (
        ('cadre', 'Cadre'),
        ('agent_maitrise', 'Agent de maîtrise'),
        ('employe', 'Employé'),
        ('ouvrier', 'Ouvrier'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='postes', null=True, blank=True)
    code_poste = models.CharField(max_length=20)
    intitule_poste = models.CharField(max_length=100)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='postes')
    categorie_professionnelle = models.CharField(max_length=50, choices=CATEGORIES, blank=True, null=True)
    classification = models.CharField(max_length=10, blank=True, null=True, help_text='A1, B2, C3, etc.')
    niveau_requis = models.CharField(max_length=100, blank=True, null=True)
    experience_requise = models.IntegerField(blank=True, null=True, help_text='En années')
    description_poste = models.TextField(blank=True, null=True)
    responsabilites = models.TextField(blank=True, null=True)
    competences_requises = models.TextField(blank=True, null=True)
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'postes'
        verbose_name = 'Poste'
        verbose_name_plural = 'Postes'
        ordering = ['intitule_poste']
        constraints = [
            models.UniqueConstraint(fields=['entreprise', 'code_poste'], name='unique_poste_par_entreprise'),
        ]
    
    def __str__(self):
        return f"{self.code_poste} - {self.intitule_poste}"


# ============= MODULES STRATÉGIQUES GUINÉE =============

class Devise(models.Model):
    """Gestion des devises pour multi-currency"""
    code = models.CharField(max_length=3, unique=True, help_text="Code ISO (GNF, USD, EUR)")
    nom = models.CharField(max_length=50)
    symbole = models.CharField(max_length=5)
    est_devise_base = models.BooleanField(default=False, help_text="GNF est la devise de base")
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'devises'
        verbose_name = 'Devise'
        verbose_name_plural = 'Devises'
    
    def __str__(self):
        return f"{self.code} - {self.nom}"


class TauxChange(models.Model):
    """Taux de change journaliers"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='taux_changes', null=True, blank=True)
    devise_source = models.ForeignKey(Devise, on_delete=models.CASCADE, related_name='taux_source')
    devise_cible = models.ForeignKey(Devise, on_delete=models.CASCADE, related_name='taux_cible')
    taux = models.DecimalField(max_digits=15, decimal_places=6, help_text="1 devise_source = X devise_cible")
    date_taux = models.DateField()
    source = models.CharField(max_length=100, blank=True, null=True, help_text="Source du taux (BCRG, marché, etc.)")
    
    class Meta:
        db_table = 'taux_changes'
        verbose_name = 'Taux de change'
        verbose_name_plural = 'Taux de change'
        unique_together = ['devise_source', 'devise_cible', 'date_taux']
        ordering = ['-date_taux']
    
    def __str__(self):
        return f"1 {self.devise_source.code} = {self.taux} {self.devise_cible.code} ({self.date_taux})"


class ParametrePaieDevise(models.Model):
    """Paramètres de paie par devise pour expatriés"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='params_paie_devise')
    devise = models.ForeignKey(Devise, on_delete=models.CASCADE)
    annee = models.IntegerField()
    
    # Plafonds et seuils en devise
    plafond_cnss = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Plafond CNSS dans cette devise")
    seuil_irpp = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Seuil d'imposition IRPP")
    
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'parametres_paie_devise'
        verbose_name = 'Paramètre paie devise'
        verbose_name_plural = 'Paramètres paie devises'
        unique_together = ['entreprise', 'devise', 'annee']
    
    def __str__(self):
        return f"Paramètres {self.devise.code} - {self.annee}"


# ============= GESTION DES EXPATRIÉS =============

class Expatrie(models.Model):
    """Informations spécifiques aux expatriés"""
    TYPES_CONTRAT_EXPAT = (
        ('detachement', 'Détachement'),
        ('expatriation', 'Expatriation'),
        ('local_plus', 'Local Plus'),
        ('vip', 'VIP/Impatrié'),
    )
    
    STATUTS_EXPATRIE = (
        ('actif', 'Actif'),
        ('termine', 'Terminé'),
        ('suspendu', 'Suspendu'),
    )
    
    employe = models.OneToOneField('employes.Employe', on_delete=models.CASCADE, related_name='info_expatrie')
    type_contrat_expat = models.CharField(max_length=30, choices=TYPES_CONTRAT_EXPAT)
    pays_origine = models.CharField(max_length=100)
    nationalite = models.CharField(max_length=100, blank=True, null=True)
    date_arrivee = models.DateField(blank=True, null=True, help_text="Date d'arrivée en Guinée")
    motif_expatriation = models.CharField(max_length=255, blank=True, null=True)
    duree_prevue_mois = models.IntegerField(blank=True, null=True, help_text="Durée prévue en mois")
    statut = models.CharField(max_length=20, choices=STATUTS_EXPATRIE, default='actif')
    devise_salaire = models.ForeignKey(Devise, on_delete=models.SET_NULL, null=True, blank=True, related_name='expatries')
    contact_urgence_pays = models.CharField(max_length=255, blank=True, null=True, help_text="Contact d'urgence au pays d'origine")
    
    # Salaire split (partie locale + partie pays d'origine)
    salaire_local_pct = models.DecimalField(max_digits=5, decimal_places=2, default=100, help_text="% payé en GNF")
    salaire_origine_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="% payé en devise origine")
    
    # Avantages expatriation
    prime_expatriation = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    indemnite_logement = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    indemnite_scolarite = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    billet_avion_annuel = models.IntegerField(default=0, help_text="Nombre de billets A/R par an")
    
    # Couverture sociale
    maintien_secu_origine = models.BooleanField(default=False, help_text="Maintien sécurité sociale pays d'origine")
    assurance_rapatriement = models.BooleanField(default=True)
    
    date_debut_mission = models.DateField()
    date_fin_mission_prevue = models.DateField(null=True, blank=True)
    
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'expatries'
        verbose_name = 'Expatrié'
        verbose_name_plural = 'Expatriés'
    
    def __str__(self):
        return f"{self.employe.nom_complet} - {self.get_type_contrat_expat_display()}"


class PermisVisa(models.Model):
    """Permis de travail et visas pour expatriés"""
    TYPES_DOCUMENT = (
        ('visa_travail', 'Visa de travail'),
        ('visa_affaires', 'Visa d\'affaires'),
        ('permis_travail', 'Permis de travail'),
        ('carte_sejour', 'Carte de séjour'),
        ('autorisation_emploi', 'Autorisation d\'emploi'),
    )
    STATUTS = (
        ('en_cours', 'En cours de validité'),
        ('expire', 'Expiré'),
        ('en_renouvellement', 'En renouvellement'),
        ('refuse', 'Refusé'),
    )
    
    expatrie = models.ForeignKey(Expatrie, on_delete=models.CASCADE, related_name='permis_visas')
    type_document = models.CharField(max_length=30, choices=TYPES_DOCUMENT)
    numero_document = models.CharField(max_length=50)
    
    date_emission = models.DateField()
    date_expiration = models.DateField()
    autorite_emission = models.CharField(max_length=100, help_text="Ex: Direction Nationale de l'Emploi")
    
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_cours')
    
    # Alertes
    alerte_renouvellement_jours = models.IntegerField(default=60, help_text="Jours avant expiration pour alerte")
    
    fichier_document = models.FileField(upload_to='expatries/permis/', null=True, blank=True)
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'permis_visas'
        verbose_name = 'Permis/Visa'
        verbose_name_plural = 'Permis/Visas'
        ordering = ['-date_expiration']
    
    def __str__(self):
        return f"{self.expatrie.employe.nom} - {self.get_type_document_display()} ({self.date_expiration})"
    
    @property
    def est_expire(self):
        from django.utils import timezone
        return self.date_expiration < timezone.now().date()
    
    @property
    def jours_avant_expiration(self):
        from django.utils import timezone
        delta = self.date_expiration - timezone.now().date()
        return delta.days


# ============= INTERFACE CNSS - TÉLÉDÉCLARATION =============

class ConfigurationCNSS(models.Model):
    """Configuration pour l'interface CNSS"""
    entreprise = models.OneToOneField(Entreprise, on_delete=models.CASCADE, related_name='config_cnss')
    
    # Identifiants CNSS
    numero_employeur = models.CharField(max_length=50, help_text="Numéro employeur CNSS")
    code_agence = models.CharField(max_length=20, blank=True, null=True)
    
    # API CNSS (si disponible)
    api_url = models.URLField(blank=True, null=True, help_text="URL API télédéclaration CNSS")
    api_username = models.CharField(max_length=100, blank=True, null=True)
    api_password = models.CharField(max_length=100, blank=True, null=True)  # À chiffrer en production
    api_token = models.TextField(blank=True, null=True)
    
    # Paramètres
    mode_declaration = models.CharField(max_length=20, choices=[
        ('manuel', 'Manuel (fichier)'),
        ('api', 'API automatique'),
    ], default='manuel')
    
    format_fichier = models.CharField(max_length=20, choices=[
        ('csv', 'CSV'),
        ('xml', 'XML'),
        ('json', 'JSON'),
    ], default='csv')
    
    actif = models.BooleanField(default=True)
    date_derniere_synchro = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'config_cnss'
        verbose_name = 'Configuration CNSS'
    
    def __str__(self):
        return f"Config CNSS - {self.entreprise.nom_entreprise}"


class TransmissionCNSS(models.Model):
    """Historique des transmissions CNSS"""
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('genere', 'Fichier généré'),
        ('transmis', 'Transmis'),
        ('accepte', 'Accepté'),
        ('rejete', 'Rejeté'),
        ('erreur', 'Erreur'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='transmissions_cnss')
    periode_mois = models.IntegerField()
    periode_annee = models.IntegerField()
    reference = models.CharField(max_length=50, unique=True)
    
    # Données
    nombre_salaries = models.IntegerField(default=0)
    masse_salariale_brute = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    base_cnss_totale = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cotisation_employe = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cotisation_employeur = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cotisations = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Fichier
    fichier_declaration = models.FileField(upload_to='cnss/declarations/', null=True, blank=True)
    
    # Statut
    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    date_generation = models.DateTimeField(null=True, blank=True)
    date_transmission = models.DateTimeField(null=True, blank=True)
    date_reponse = models.DateTimeField(null=True, blank=True)
    
    # Réponse CNSS
    numero_accuse = models.CharField(max_length=50, blank=True, null=True)
    message_retour = models.TextField(blank=True, null=True)
    fichier_accuse = models.FileField(upload_to='cnss/accuses/', null=True, blank=True)
    
    genere_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'transmissions_cnss'
        verbose_name = 'Transmission CNSS'
        verbose_name_plural = 'Transmissions CNSS'
        unique_together = ['entreprise', 'periode_mois', 'periode_annee']
        ordering = ['-periode_annee', '-periode_mois']
    
    def __str__(self):
        return f"CNSS {self.periode_mois:02d}/{self.periode_annee} - {self.get_statut_display()}"


# ============= CONFORMITÉ INSPECTION DU TRAVAIL =============

class RegistreObligatoire(models.Model):
    """Registres obligatoires selon le Code du Travail guinéen"""
    TYPES_REGISTRE = (
        ('personnel', 'Registre du personnel'),
        ('paie', 'Registre de paie'),
        ('conges', 'Registre des congés'),
        ('accidents', 'Registre des accidents du travail'),
        ('delegues', 'Registre des délégués du personnel'),
        ('heures_sup', 'Registre des heures supplémentaires'),
        ('visites_medicales', 'Registre des visites médicales'),
        ('sanctions', 'Registre des sanctions'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='registres_obligatoires')
    type_registre = models.CharField(max_length=30, choices=TYPES_REGISTRE)
    annee = models.IntegerField()
    
    # Informations du registre
    numero_registre = models.CharField(max_length=50, blank=True, null=True)
    date_ouverture = models.DateField()
    date_cloture = models.DateField(null=True, blank=True)
    
    # Visa Inspection du Travail
    vise_inspection = models.BooleanField(default=False)
    date_visa = models.DateField(null=True, blank=True)
    numero_visa = models.CharField(max_length=50, blank=True, null=True)
    
    fichier_registre = models.FileField(upload_to='registres/', null=True, blank=True)
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'registres_obligatoires'
        verbose_name = 'Registre obligatoire'
        verbose_name_plural = 'Registres obligatoires'
        unique_together = ['entreprise', 'type_registre', 'annee']
    
    def __str__(self):
        return f"{self.get_type_registre_display()} - {self.annee}"


class VisiteInspection(models.Model):
    """Visites de l'Inspection du Travail"""
    TYPES_VISITE = (
        ('routine', 'Visite de routine'),
        ('controle', 'Contrôle'),
        ('enquete', 'Enquête'),
        ('suite_plainte', 'Suite à plainte'),
        ('verification', 'Vérification'),
    )
    RESULTATS = (
        ('conforme', 'Conforme'),
        ('observations', 'Observations'),
        ('mise_demeure', 'Mise en demeure'),
        ('pv_infraction', 'PV d\'infraction'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='visites_inspection')
    date_visite = models.DateField()
    type_visite = models.CharField(max_length=30, choices=TYPES_VISITE)
    
    # Inspecteur
    nom_inspecteur = models.CharField(max_length=100)
    matricule_inspecteur = models.CharField(max_length=50, blank=True, null=True)
    direction_regionale = models.CharField(max_length=100, blank=True, null=True)
    
    # Objet de la visite
    objet_visite = models.TextField()
    points_controles = models.TextField(blank=True, null=True, help_text="Points vérifiés")
    
    # Résultat
    resultat = models.CharField(max_length=30, choices=RESULTATS, blank=True, null=True)
    observations_inspecteur = models.TextField(blank=True, null=True)
    recommandations = models.TextField(blank=True, null=True)
    
    # Documents
    pv_visite = models.FileField(upload_to='inspection/pv/', null=True, blank=True)
    mise_demeure = models.FileField(upload_to='inspection/mises_demeure/', null=True, blank=True)
    
    # Suivi
    date_limite_regularisation = models.DateField(null=True, blank=True)
    regularisation_effectuee = models.BooleanField(default=False)
    date_regularisation = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'visites_inspection'
        verbose_name = 'Visite inspection'
        verbose_name_plural = 'Visites inspection'
        ordering = ['-date_visite']
    
    def __str__(self):
        return f"Inspection {self.date_visite} - {self.get_type_visite_display()}"


class NonConformite(models.Model):
    """Non-conformités relevées par l'Inspection"""
    GRAVITES = (
        ('mineure', 'Mineure'),
        ('majeure', 'Majeure'),
        ('critique', 'Critique'),
    )
    STATUTS = (
        ('ouverte', 'Ouverte'),
        ('en_cours', 'En cours de traitement'),
        ('resolue', 'Résolue'),
        ('fermee', 'Fermée'),
    )
    
    visite = models.ForeignKey(VisiteInspection, on_delete=models.CASCADE, related_name='non_conformites')
    reference = models.CharField(max_length=50)
    
    # Description
    article_code_travail = models.CharField(max_length=50, blank=True, null=True, help_text="Article du Code du Travail")
    description = models.TextField()
    gravite = models.CharField(max_length=20, choices=GRAVITES)
    
    # Actions correctives
    action_corrective = models.TextField(blank=True, null=True)
    responsable_action = models.CharField(max_length=100, blank=True, null=True)
    date_echeance = models.DateField(null=True, blank=True)
    
    # Statut
    statut = models.CharField(max_length=20, choices=STATUTS, default='ouverte')
    date_resolution = models.DateField(null=True, blank=True)
    preuve_resolution = models.FileField(upload_to='inspection/preuves/', null=True, blank=True)
    
    class Meta:
        db_table = 'non_conformites'
        verbose_name = 'Non-conformité'
        verbose_name_plural = 'Non-conformités'
        ordering = ['-visite__date_visite', 'gravite']
    
    def __str__(self):
        return f"{self.reference} - {self.get_gravite_display()}"


# ============= BARÈME IRPP GUINÉE =============

class BaremeIRPP(models.Model):
    """Barème progressif de l'IRPP (Impôt sur le Revenu des Personnes Physiques)"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='baremes_irpp', null=True, blank=True)
    annee = models.IntegerField()
    
    # Tranche
    tranche_numero = models.IntegerField()
    revenu_min = models.DecimalField(max_digits=15, decimal_places=2)
    revenu_max = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Null = illimité")
    taux = models.DecimalField(max_digits=5, decimal_places=2, help_text="Taux en %")
    
    # Montant forfaitaire (pour calcul rapide)
    montant_cumule_precedent = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Impôt cumulé des tranches précédentes")
    
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'baremes_irpp'
        verbose_name = 'Tranche IRPP'
        verbose_name_plural = 'Barème IRPP'
        unique_together = ['entreprise', 'annee', 'tranche_numero']
        ordering = ['annee', 'tranche_numero']
    
    def __str__(self):
        max_str = f"{self.revenu_max:,.0f}" if self.revenu_max else "∞"
        return f"Tranche {self.tranche_numero}: {self.revenu_min:,.0f} - {max_str} GNF @ {self.taux}%"


class DeductionFiscale(models.Model):
    """Déductions fiscales (charges de famille, etc.)"""
    TYPES_DEDUCTION = (
        ('conjoint', 'Conjoint à charge'),
        ('enfant', 'Enfant à charge'),
        ('ascendant', 'Ascendant à charge'),
        ('handicap', 'Personne handicapée'),
        ('assurance_vie', 'Assurance vie'),
        ('epargne_retraite', 'Épargne retraite'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='deductions_fiscales', null=True, blank=True)
    annee = models.IntegerField()
    type_deduction = models.CharField(max_length=30, choices=TYPES_DEDUCTION)
    
    montant_deduction = models.DecimalField(max_digits=15, decimal_places=2, help_text="Montant de la déduction")
    plafond = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Plafond si applicable")
    nombre_max = models.IntegerField(null=True, blank=True, help_text="Nombre max (ex: 4 enfants)")
    
    conditions = models.TextField(blank=True, null=True, help_text="Conditions d'application")
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'deductions_fiscales'
        verbose_name = 'Déduction fiscale'
        verbose_name_plural = 'Déductions fiscales'
        unique_together = ['entreprise', 'annee', 'type_deduction']
    
    def __str__(self):
        return f"{self.get_type_deduction_display()} - {self.montant_deduction:,.0f} GNF ({self.annee})"


class ParametreConformite(models.Model):
    """Paramètres de conformité pour validation manuelle"""
    CODES_CONFORMITE = (
        ('affichage_horaires', 'Horaires de travail affichés'),
        ('affichage_reglement', 'Règlement intérieur affiché'),
        ('affichage_securite', 'Consignes de sécurité affichées'),
        ('affichage_inspection', 'Coordonnées inspection du travail'),
        ('affichage_medecine', 'Coordonnées médecine du travail'),
        ('securite_extincteurs', 'Extincteurs vérifiés'),
        ('securite_trousse', 'Trousse de premiers secours'),
        ('securite_equipements', 'Équipements de protection fournis'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='parametres_conformite')
    code = models.CharField(max_length=50, choices=CODES_CONFORMITE)
    valide = models.BooleanField(default=False)
    date_validation = models.DateField(null=True, blank=True)
    validateur = models.CharField(max_length=100, blank=True)
    observations = models.TextField(blank=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'parametres_conformite'
        verbose_name = 'Paramètre de conformité'
        verbose_name_plural = 'Paramètres de conformité'
        unique_together = ['entreprise', 'code']
    
    def __str__(self):
        return f"{self.get_code_display()} - {'✓' if self.valide else '✗'}"


class DemandePartenariat(models.Model):
    """Demandes de partenariat soumises via le landing page"""
    STATUTS = (
        ('nouveau', 'Nouveau'),
        ('en_cours', 'En cours de traitement'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé'),
    )
    
    TYPES_PARTENARIAT = (
        ('revendeur', 'Revendeur'),
        ('integrateur', 'Intégrateur'),
        ('consultant', 'Consultant'),
        ('formation', 'Centre de formation'),
        ('autre', 'Autre'),
    )
    
    # Informations entreprise
    nom_entreprise = models.CharField(max_length=200, verbose_name='Nom de l\'entreprise')
    secteur_activite = models.CharField(max_length=100, verbose_name='Secteur d\'activité')
    nif = models.CharField(max_length=50, blank=True, null=True, verbose_name='NIF')
    adresse = models.TextField(verbose_name='Adresse')
    ville = models.CharField(max_length=100, verbose_name='Ville')
    pays = models.CharField(max_length=50, default='Guinée', verbose_name='Pays')
    
    # Contact
    nom_contact = models.CharField(max_length=100, verbose_name='Nom du contact')
    fonction_contact = models.CharField(max_length=100, verbose_name='Fonction')
    email = models.EmailField(verbose_name='Email')
    telephone = models.CharField(max_length=20, verbose_name='Téléphone')
    
    # Partenariat
    type_partenariat = models.CharField(max_length=20, choices=TYPES_PARTENARIAT, verbose_name='Type de partenariat')
    description_activite = models.TextField(verbose_name='Description de l\'activité')
    motivation = models.TextField(verbose_name='Motivation pour le partenariat')
    
    # Documents
    document_cgi = models.FileField(upload_to='partenariats/documents/', blank=True, null=True, verbose_name='Document CGI')
    autre_document = models.FileField(upload_to='partenariats/documents/', blank=True, null=True, verbose_name='Autre document')
    
    # Statut
    statut = models.CharField(max_length=20, choices=STATUTS, default='nouveau')
    date_soumission = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    traite_par = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_traitees')
    notes_admin = models.TextField(blank=True, null=True, verbose_name='Notes administrateur')
    
    class Meta:
        db_table = 'demandes_partenariat'
        verbose_name = 'Demande de partenariat'
        verbose_name_plural = 'Demandes de partenariat'
        ordering = ['-date_soumission']
    
    def __str__(self):
        return f"{self.nom_entreprise} - {self.get_type_partenariat_display()} ({self.get_statut_display()})"


class TentativeCodeAcces(models.Model):
    """Journal des tentatives de saisie du code d'accès inscription"""
    adresse_ip = models.GenericIPAddressField()
    code_saisi = models.CharField(max_length=20)
    succes = models.BooleanField(default=False)
    date_tentative = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = 'tentatives_code_acces'
        verbose_name = 'Tentative code d\'accès'
        verbose_name_plural = 'Tentatives code d\'accès'
        ordering = ['-date_tentative']
        indexes = [
            models.Index(fields=['adresse_ip', 'date_tentative']),
        ]

    def __str__(self):
        status = "✓" if self.succes else "✗"
        return f"{status} {self.adresse_ip} - {self.date_tentative:%d/%m/%Y %H:%M}"

    @classmethod
    def tentatives_recentes(cls, ip, minutes=30):
        """Nombre de tentatives échouées récentes pour une IP"""
        depuis = timezone.now() - timezone.timedelta(minutes=minutes)
        return cls.objects.filter(
            adresse_ip=ip,
            succes=False,
            date_tentative__gte=depuis
        ).count()

    @classmethod
    def ip_bloquee(cls, ip, max_tentatives=5, minutes=30):
        """Vérifie si une IP est bloquée suite à trop de tentatives"""
        return cls.tentatives_recentes(ip, minutes) >= max_tentatives

    @classmethod
    def enregistrer(cls, request, code_saisi, succes):
        """Enregistre une tentative"""
        from .views import get_client_ip
        cls.objects.create(
            adresse_ip=get_client_ip(request),
            code_saisi=code_saisi[:20] if not succes else '***',
            succes=succes,
            user_agent=(request.META.get('HTTP_USER_AGENT', '') or '')[:500]
        )


# ---------------------------------------------------------------------------
# Enregistrement des modèles de licence (définis dans models_licence.py)
# ---------------------------------------------------------------------------
# Ces modèles vivent dans un module séparé importé seulement par les vues.
# On les importe ici pour qu'ils soient enregistrés dans l'app `core` dès le
# chargement : sinon `makemigrations` ne les « voit » pas et génère à tort une
# migration de suppression (Licence/LicenceLocale) à chaque exécution.
from core.models_licence import Licence, LicenceLocale  # noqa: E402,F401
