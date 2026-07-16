from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
from employes.models import Employe
from core.models import Utilisateur, Devise, Entreprise

# Import des modèles de prêts
from .models_pret import Pret, EcheancePret

# Import des managers optimisés
from .managers import (
    BulletinPaieManager, ElementSalaireManager, PeriodePaieManager
)


class PeriodePaie(models.Model):
    """Périodes de paie"""
    STATUTS = (
        ('ouverte', 'Ouverte'),
        ('calculee', 'Calculée'),
        ('validee', 'Validée'),
        ('cloturee', 'Clôturée'),
        ('payee', 'Payée'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='periodes_paie', null=True, blank=True)
    annee = models.IntegerField()
    mois = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    libelle = models.CharField(max_length=50, blank=True, null=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    date_paiement = models.DateField(blank=True, null=True)
    statut_periode = models.CharField(max_length=20, choices=STATUTS, default='ouverte')
    nombre_jours_travailles = models.IntegerField(default=22)
    nombre_heures_mois = models.DecimalField(max_digits=6, decimal_places=2, default=173.33)
    date_cloture = models.DateTimeField(blank=True, null=True)
    utilisateur_cloture = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name='periodes_cloturees')
    observations = models.TextField(blank=True, null=True)
    
    # Manager optimisé
    objects = PeriodePaieManager()
    
    class Meta:
        db_table = 'periodes_paie'
        verbose_name = 'Période de paie'
        verbose_name_plural = 'Périodes de paie'
        unique_together = ['entreprise', 'annee', 'mois']
        ordering = ['-annee', '-mois']
    
    def __str__(self):
        mois_fr = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 
                   'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        mois_nom = mois_fr[self.mois] if 1 <= self.mois <= 12 else str(self.mois)
        return f"{mois_nom} {self.annee}"


class RubriquePaie(models.Model):
    """Rubriques de paie"""
    TYPES = (
        ('gain', 'Gain'),
        ('retenue', 'Retenue'),
        ('cotisation', 'Cotisation'),
        ('information', 'Information'),
    )

    CATEGORIES = (
        ('salaire_base', 'Salaire de base'),
        ('prime', 'Prime (récompense/motivation)'),
        ('indemnite', 'Indemnité (compensation/remboursement)'),
        ('avantage', 'Avantage en nature'),
        ('cotisation', 'Cotisation sociale'),
        ('retenue', 'Retenue fiscale'),
        ('autre', 'Autre'),
    )

    MODES_CALCUL = (
        ('fixe', 'Montant fixe'),
        ('pourcentage_base', '% du salaire de base'),
        ('pourcentage_brut', '% du brut'),
        ('horaire', 'Taux horaire × heures'),
        ('formule', 'Formule personnalisée'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, null=True, blank=True, related_name='rubriques_paie')
    code_rubrique = models.CharField(max_length=20)
    libelle_rubrique = models.CharField(max_length=200)
    type_rubrique = models.CharField(max_length=20, choices=TYPES)
    categorie_rubrique = models.CharField(max_length=20, choices=CATEGORIES, default='autre',
        help_text='Prime = imposable+CNSS | Indemnité = exonérable selon plafond')
    mode_calcul = models.CharField(max_length=20, choices=MODES_CALCUL, default='fixe',
        help_text='Comment le montant est calculé')
    formule_calcul = models.TextField(blank=True, null=True)
    taux_rubrique = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True)
    montant_fixe = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    soumis_cnss = models.BooleanField(default=False)
    # Champ historique IRG – alias RTS utilisé côté métier (Option C)
    soumis_irg = models.BooleanField(default=False)
    inclus_brut = models.BooleanField(default=True,
        help_text='Inclus dans le salaire brut (False = versé en plus du net)')
    exonere_rts = models.BooleanField(default=False,
        help_text='Exonéré de RTS (indemnités forfaitaires intégralement exonérées, CGI Guinée)')
    ordre_calcul = models.IntegerField(default=100)
    ordre_affichage = models.IntegerField(default=100)
    affichage_bulletin = models.BooleanField(default=True)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'rubriques_paie'
        verbose_name = 'Rubrique de paie'
        verbose_name_plural = 'Rubriques de paie'
        ordering = ['ordre_calcul']
        unique_together = ['entreprise', 'code_rubrique']
    
    def __str__(self):
        return f"{self.code_rubrique} - {self.libelle_rubrique}"
    
    @property
    def soumis_rts(self):
        """Alias RTS pour soumis_irg"""
        return self.soumis_irg
    
    @soumis_rts.setter
    def soumis_rts(self, value):
        self.soumis_irg = value


class BulletinPaie(models.Model):
    """Bulletins de paie"""
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('calcule', 'Calculé'),
        ('valide', 'Validé'),
        ('paye', 'Payé'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='bulletins')
    periode = models.ForeignKey(PeriodePaie, on_delete=models.CASCADE, related_name='bulletins')
    numero_bulletin = models.CharField(max_length=50, unique=True)
    mois_paie = models.IntegerField()
    annee_paie = models.IntegerField()
    
    # Heures et temps de travail
    heures_normales = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="Heures normales travaillées")
    heures_supplementaires_30 = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="HS à +30% (4 premières HS/semaine)")
    heures_supplementaires_60 = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="HS à +60% (au-delà 4 HS/semaine)")
    heures_nuit = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="Heures de nuit (20h-6h) à +20%")
    heures_feries = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="Heures jours fériés (jour)")
    heures_feries_nuit = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="Heures jours fériés (nuit) à +100%")
    
    # Calculs de paie
    salaire_base = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Salaire de base")
    prime_heures_sup = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Prime heures supplémentaires")
    prime_nuit = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Prime de nuit")
    prime_feries = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Prime jours fériés (jour)")
    prime_feries_nuit = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Prime jours fériés (nuit)")
    salaire_brut = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cnss_employe = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cnss_employeur = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    # Champ historique IRG – alias RTS utilisé côté métier (Option C)
    irg = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    base_rts = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Base imposable RTS')
    abattement_forfaitaire = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Abattement forfaitaire 25% sur base RTS')
    taux_effectif_rts = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Taux effectif RTS en %')
    net_a_payer = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Rappels et manquements (hors base de calcul)
    rappel_salaire = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Complément salaire mois précédent (hors base)')
    retenue_trop_percu = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Retenue trop-perçu mois précédent (hors base)')
    
    # Charges patronales
    base_vf = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Base de calcul du VF (brut par défaut)')
    versement_forfaitaire = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='VF 6% sur base VF')
    taxe_apprentissage = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='TA 2% sur base VF')
    taux_ta = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Taux TA appliqué (%)')
    base_onfpp = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Base de calcul ONFPP')
    contribution_onfpp = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='ONFPP 1,5% sur base VF/ONFPP')
    nombre_salaries = models.IntegerField(default=1, help_text='Nombre de salariés pour déterminer TA vs ONFPP')
    
    # Devise du bulletin
    devise_bulletin = models.ForeignKey(Devise, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='bulletins_devise',
                                      help_text='Devise utilisée pour ce bulletin')
    
    statut_bulletin = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    date_calcul = models.DateTimeField(blank=True, null=True)
    observations = models.TextField(blank=True, null=True)

    # Snapshot des paramètres figés au moment du calcul (audit + reproductibilité)
    snapshot_parametres = models.JSONField(
        blank=True, null=True,
        help_text='Paramètres figés au calcul : constantes, barème RTS, config entreprise'
    )
    
    # Token pour accès public au PDF
    token_public = models.CharField(max_length=64, blank=True, null=True, unique=True,
                                   help_text='Token pour téléchargement public du PDF')
    
    # Manager optimisé
    objects = BulletinPaieManager()
    
    class Meta:
        db_table = 'bulletins_paie'
        verbose_name = 'Bulletin de paie'
        verbose_name_plural = 'Bulletins de paie'
        unique_together = ['employe', 'periode']
        ordering = ['-annee_paie', '-mois_paie']
        indexes = [
            models.Index(fields=['periode', 'statut_bulletin'], name='idx_bulletin_periode_statut'),
            models.Index(fields=['employe', 'annee_paie', 'mois_paie'], name='idx_bulletin_emp_periode'),
            models.Index(fields=['statut_bulletin'], name='idx_bulletin_statut'),
            models.Index(fields=['annee_paie', 'mois_paie'], name='idx_bulletin_annee_mois'),
        ]
    
    def __str__(self):
        return f"{self.numero_bulletin} - {self.employe.nom} {self.employe.prenoms}"

    # --- Verrouillage des bulletins validés ---
    STATUTS_VERROUILLES = ('valide', 'paye')
    # Champs modifiables même sur un bulletin verrouillé (token, observations)
    _CHAMPS_TOUJOURS_MODIFIABLES = frozenset({
        'token_public', 'observations', 'statut_bulletin',
    })

    @property
    def est_verrouille(self):
        """True si le bulletin est validé ou payé (non modifiable)."""
        return self.statut_bulletin in self.STATUTS_VERROUILLES

    def save(self, *args, **kwargs):
        """Empêche la modification d'un bulletin verrouillé sauf champs autorisés."""
        if self.pk and self.est_verrouille:
            update_fields = kwargs.get('update_fields')
            if update_fields:
                champs_interdits = set(update_fields) - self._CHAMPS_TOUJOURS_MODIFIABLES
                if champs_interdits:
                    raise PermissionError(
                        f"Bulletin {self.numero_bulletin} verrouillé (statut={self.statut_bulletin}). "
                        f"Impossible de modifier : {', '.join(sorted(champs_interdits))}"
                    )
            else:
                # save() complet sur bulletin verrouillé → vérifier si c'est un changement de statut
                if self.pk:
                    try:
                        ancien = BulletinPaie.objects.only('statut_bulletin').get(pk=self.pk)
                        if ancien.statut_bulletin in self.STATUTS_VERROUILLES and self.statut_bulletin in self.STATUTS_VERROUILLES:
                            raise PermissionError(
                                f"Bulletin {self.numero_bulletin} verrouillé (statut={ancien.statut_bulletin}). "
                                f"Recalculez la période pour le débloquer."
                            )
                    except BulletinPaie.DoesNotExist:
                        pass
        super().save(*args, **kwargs)
    
    def generer_token_public(self):
        """Génère un token unique pour l'accès public au PDF"""
        import secrets
        if not self.token_public:
            self.token_public = secrets.token_urlsafe(32)
            self.save(update_fields=['token_public'])
        return self.token_public
    
    @property
    def total_charges_patronales(self):
        """Total des charges patronales (CNSS + VF + TA ou ONFPP)"""
        return (self.cnss_employeur or 0) + (self.versement_forfaitaire or 0) + (self.taxe_apprentissage or 0) + (self.contribution_onfpp or 0)

    @property
    def total_charges_salariales(self):
        """Total des charges salariales legales (CNSS salarie + RTS)."""
        return (self.cnss_employe or 0) + (self.irg or 0)

    @property
    def total_retenues(self):
        """Total réel des retenues = brut - net + rappel - trop_percu"""
        brut = self.salaire_brut or 0
        net = self.net_a_payer or 0
        rappel = self.rappel_salaire or 0
        trop_percu = self.retenue_trop_percu or 0
        return brut + rappel - trop_percu - net

    @property
    def mode_base_vf_effectif(self):
        """Mode de base VF/ONFPP constate sur le bulletin."""
        brut = Decimal(self.salaire_brut or 0)
        base_vf = Decimal(self.base_vf or 0)
        if brut <= 0 or base_vf <= 0:
            return 'indetermine'
        return 'strict' if abs(brut - base_vf) <= Decimal('1') else 'optimise'

    @property
    def taux_optimisation_vf_onfpp(self):
        """Part du brut retiree de la base VF/ONFPP."""
        brut = Decimal(self.salaire_brut or 0)
        base_vf = Decimal(self.base_vf or 0)
        if brut <= 0 or base_vf <= 0:
            return Decimal('0.00')
        deduction = max(Decimal('0'), brut - base_vf)
        return (deduction * Decimal('100') / brut).quantize(Decimal('0.01'))

    @property
    def economie_vf_onfpp_vs_strict(self):
        """Economie estimee par rapport au mode strict brut."""
        brut = Decimal(self.salaire_brut or 0)
        base_vf = Decimal(self.base_vf or 0)
        if brut <= 0 or base_vf <= 0:
            return Decimal('0')
        taux_ta_onfpp = Decimal('2.00') if (self.taxe_apprentissage or 0) > 0 else Decimal('1.50')
        taux_total = Decimal('6.00') + taux_ta_onfpp
        return ((brut - base_vf) * taux_total / Decimal('100')).quantize(Decimal('1'))

    @property
    def risque_fiscal_bulletin(self):
        """Indicateur simple pour audit: faible, moyen ou eleve."""
        brut = Decimal(self.salaire_brut or 0)
        base_vf = Decimal(self.base_vf or 0)
        taux = self.taux_optimisation_vf_onfpp
        raisons = []
        niveau = 'faible'
        classe = 'success'

        if brut <= 0 or base_vf <= 0:
            niveau = 'eleve'
            classe = 'danger'
            raisons.append('Base VF/ONFPP manquante')
        elif abs(brut - base_vf) > Decimal('1'):
            niveau = 'eleve'
            classe = 'danger'
            raisons.append('Base VF differente du brut')

        if base_vf > 0:
            vf_attendue = (brut * Decimal('0.06')).quantize(Decimal('1'))
            vf_reelle = Decimal(self.versement_forfaitaire or 0).quantize(Decimal('1'))
            if abs(vf_reelle - vf_attendue) > Decimal('1'):
                niveau = 'eleve'
                classe = 'danger'
                raisons.append('Ecart VF')

            if (self.taxe_apprentissage or 0) > 0:
                base_charge = brut
                taux_ta_onfpp = Decimal('0.02')
                reel = Decimal(self.taxe_apprentissage or 0).quantize(Decimal('1'))
            else:
                base_charge = brut
                taux_ta_onfpp = Decimal('0.015')
                reel = Decimal(self.contribution_onfpp or 0).quantize(Decimal('1'))
            attendu = (base_charge * taux_ta_onfpp).quantize(Decimal('1'))
            if abs(reel - attendu) > Decimal('1'):
                niveau = 'eleve'
                classe = 'danger'
                raisons.append('Ecart TA/ONFPP')

        labels = {'faible': 'Faible', 'moyen': 'Moyen', 'eleve': 'Eleve'}
        return {
            'niveau': niveau,
            'label': labels[niveau],
            'classe': classe,
            'raisons': raisons or ['Controles coherents'],
        }

    @property
    def rts(self):
        """Alias RTS pour irg (Retenue à la Source = ancien IRG)"""
        return self.irg
    
    @rts.setter
    def rts(self, value):
        """Setter pour l'alias RTS"""
        self.irg = value


class ParametrePaie(models.Model):
    """Paramètres généraux de la paie"""
    TYPES_BULLETIN = (
        ('standard', 'Standard'),
        ('simplifie', 'Simplifié'),
        ('detaille', 'Détaillé'),
    )
    
    TYPES_PAIEMENT = (
        ('virement', 'Virement bancaire'),
        ('cheque', 'Chèque'),
        ('espece', 'Espèces'),
        ('mobile_money', 'Mobile Money'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, null=True, blank=True, related_name='parametres_paie')
    
    # Période en cours
    mois_en_cours = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    annee_en_cours = models.IntegerField()
    date_debut_periode = models.DateField()
    date_fin_periode = models.DateField()
    
    # Paramètres de calcul
    regulation_active = models.BooleanField(default=True, help_text="Activer la régulation automatique")
    plafond_abattement_irg = models.DecimalField(max_digits=15, decimal_places=2, default=300000, help_text="Plafond abattement RTS en GNF")
    taux_abattement_irg = models.DecimalField(max_digits=5, decimal_places=2, default=20.00, help_text="Taux d'abattement RTS en %")
    
    # Configuration
    type_bulletin_defaut = models.CharField(max_length=20, choices=TYPES_BULLETIN, default='standard')
    type_paiement_defaut = models.CharField(max_length=20, choices=TYPES_PAIEMENT, default='virement')
    nombre_max_rubriques = models.IntegerField(default=100)
    
    # Acomptes
    acompte_regulier_actif = models.BooleanField(default=True)
    acompte_exceptionnel_actif = models.BooleanField(default=True)
    montant_max_acompte_pct = models.DecimalField(max_digits=5, decimal_places=2, default=50.00, help_text="% max du salaire")
    
    # Devise
    devise = models.CharField(max_length=3, default='GNF')
    
    # Suppression automatique
    suppression_auto_non_presents = models.BooleanField(default=False, help_text="Supprimer les salariés non présents en clôture annuelle")
    
    # Gestion historique
    conserver_historique_admin = models.BooleanField(default=True)
    duree_conservation_mois = models.IntegerField(default=120, help_text="Durée de conservation en mois")
    
    # Coordonnées société (pour bulletins)
    nom_societe = models.CharField(max_length=200, blank=True)
    adresse_societe = models.TextField(blank=True)
    telephone_societe = models.CharField(max_length=20, blank=True)
    email_societe = models.CharField(max_length=100, blank=True)
    nif_societe = models.CharField(max_length=50, blank=True, help_text="Numéro d'Identification Fiscale")
    num_cnss_employeur = models.CharField(max_length=50, blank=True)
    
    # Audit
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    utilisateur_modification = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'parametres_paie'
        verbose_name = 'Paramètre de paie'
        verbose_name_plural = 'Paramètres de paie'
    
    def __str__(self):
        return f"Paramètres Paie {self.mois_en_cours}/{self.annee_en_cours}"
    
    @property
    def plafond_abattement_rts(self):
        """Alias RTS pour plafond_abattement_irg"""
        return self.plafond_abattement_irg
    
    @property
    def taux_abattement_rts(self):
        """Alias RTS pour taux_abattement_irg"""
        return self.taux_abattement_irg


class Constante(models.Model):
    """Constantes de calcul de paie"""
    TYPES_VALEUR = (
        ('montant', 'Montant'),
        ('pourcentage', 'Pourcentage'),
        ('nombre', 'Nombre'),
    )
    
    CATEGORIES = (
        ('cnss', 'CNSS'),
        ('irg', 'RTS'),
        ('inam', 'INAM'),
        ('general', 'Général'),
        ('temps', 'Temps de travail'),
    )
    
    code = models.CharField(max_length=50, unique=True, help_text="Code mémo de la constante")
    libelle = models.CharField(max_length=200)
    valeur = models.DecimalField(max_digits=15, decimal_places=4)
    type_valeur = models.CharField(max_length=20, choices=TYPES_VALEUR)
    categorie = models.CharField(max_length=50, choices=CATEGORIES, default='general')
    unite = models.CharField(max_length=20, blank=True, help_text="%, GNF, jours, heures")
    
    date_debut_validite = models.DateField()
    date_fin_validite = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'constantes'
        verbose_name = 'Constante'
        verbose_name_plural = 'Constantes'
        ordering = ['categorie', 'code']
    
    def __str__(self):
        return f"{self.code} - {self.libelle} ({self.valeur} {self.unite})"


class TrancheRTS(models.Model):
    """Tranches du barème RTS"""
    TYPES_BAREME = (
        ('officiel', 'Officiel (en vigueur)'),
        ('simulation', 'Simulation'),
        ('test', 'Test'),
    )

    numero_tranche = models.IntegerField()
    borne_inferieure = models.DecimalField(max_digits=15, decimal_places=2)
    borne_superieure = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Null = illimité")
    # Champ historique IRG – alias taux_rts utilisé côté métier (Option C)
    taux_irg = models.DecimalField(max_digits=5, decimal_places=2, help_text="Taux en %")
    annee_validite = models.IntegerField()
    type_bareme = models.CharField(
        max_length=20, choices=TYPES_BAREME, default='officiel',
        help_text='Officiel = utilisé pour les bulletins, Simulation/Test = comparaison uniquement'
    )
    date_debut_validite = models.DateField()
    date_fin_validite = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'tranches_irg'
        verbose_name = 'Tranche RTS'
        verbose_name_plural = 'Tranches RTS'
        ordering = ['annee_validite', 'numero_tranche']
    
    def __str__(self):
        if self.borne_superieure:
            return f"Tranche {self.numero_tranche}: {self.borne_inferieure:,.0f} - {self.borne_superieure:,.0f} GNF ({self.taux_irg}%)"
        return f"Tranche {self.numero_tranche}: > {self.borne_inferieure:,.0f} GNF ({self.taux_irg}%)"
    
    @property
    def taux_rts(self):
        """Alias RTS pour taux_irg"""
        return self.taux_irg
    
    @taux_rts.setter
    def taux_rts(self, value):
        self.taux_irg = value


class Variable(models.Model):
    """Variables de paie"""
    TYPES_VARIABLE = (
        ('numerique', 'Numérique'),
        ('texte', 'Texte'),
        ('booleen', 'Booléen'),
        ('date', 'Date'),
    )
    
    PORTEES = (
        ('global', 'Global'),
        ('employe', 'Par employé'),
        ('periode', 'Par période'),
    )
    
    code = models.CharField(max_length=50, unique=True, help_text="Code mémo de la variable")
    libelle = models.CharField(max_length=100)
    type_variable = models.CharField(max_length=20, choices=TYPES_VARIABLE)
    portee = models.CharField(max_length=20, choices=PORTEES)
    valeur_defaut = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'variables'
        verbose_name = 'Variable'
        verbose_name_plural = 'Variables'
        ordering = ['portee', 'code']
    
    def __str__(self):
        return f"{self.code} - {self.libelle}"


class ElementSalaire(models.Model):
    """Éléments de salaire fixes par employé"""
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='elements_salaire')
    rubrique = models.ForeignKey(RubriquePaie, on_delete=models.CASCADE, related_name='elements_employes')
    
    # Montant ou taux
    montant = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Montant fixe")
    taux = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, help_text="Taux en %")
    
    # Base de calcul (si taux)
    base_calcul = models.CharField(max_length=50, blank=True, help_text="Ex: SALAIRE_BASE, BRUT, etc.")
    
    # Validité
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    
    # Récurrence
    recurrent = models.BooleanField(default=True, help_text="Appliqué chaque mois")
    
    class Meta:
        db_table = 'elements_salaire'
        verbose_name = 'Élément de salaire'
        verbose_name_plural = 'Éléments de salaire'
        ordering = ['employe', 'rubrique__ordre_calcul']
        indexes = [
            models.Index(fields=['employe', 'actif'], name='idx_elem_employe_actif'),
            models.Index(fields=['employe', 'date_debut', 'date_fin'], name='idx_elem_employe_dates'),
            models.Index(fields=['rubrique'], name='idx_elem_rubrique'),
        ]
    
    def __str__(self):
        if self.montant:
            return f"{self.employe.matricule} - {self.rubrique.code_rubrique}: {self.montant:,.0f} GNF"
        elif self.taux:
            return f"{self.employe.matricule} - {self.rubrique.code_rubrique}: {self.taux}%"
        return f"{self.employe.matricule} - {self.rubrique.code_rubrique}"


class LigneBulletin(models.Model):
    """Lignes de détail d'un bulletin de paie"""
    bulletin = models.ForeignKey(BulletinPaie, on_delete=models.CASCADE, related_name='lignes')
    rubrique = models.ForeignKey(RubriquePaie, on_delete=models.CASCADE)
    
    # Calcul
    base = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Base de calcul")
    taux = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, help_text="Taux appliqué")
    nombre = models.DecimalField(max_digits=10, decimal_places=2, default=1, help_text="Quantité (heures, jours, etc.)")
    montant = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Montant calculé")
    
    # Ordre d'affichage
    ordre = models.IntegerField(default=100)
    
    # Informations complémentaires
    libelle_personnalise = models.CharField(max_length=200, blank=True, help_text="Libellé spécifique pour ce bulletin")
    commentaire = models.CharField(max_length=500, blank=True)
    
    class Meta:
        db_table = 'lignes_bulletin'
        verbose_name = 'Ligne de bulletin'
        verbose_name_plural = 'Lignes de bulletin'
        ordering = ['bulletin', 'ordre']
        indexes = [
            models.Index(fields=['bulletin'], name='idx_ligne_bulletin'),
            models.Index(fields=['rubrique'], name='idx_ligne_rubrique'),
        ]
    
    def __str__(self):
        return f"{self.bulletin.numero_bulletin} - {self.rubrique.code_rubrique}: {self.montant:,.0f}"


class CumulPaie(models.Model):
    """Cumuls de paie par employé et par année"""
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='cumuls_paie')
    annee = models.IntegerField()
    
    # Cumuls bruts
    cumul_brut = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cumul_imposable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cumul_net = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Cumuls cotisations
    cumul_cnss_employe = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cumul_cnss_employeur = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    # Champ historique IRG – alias cumul_rts utilisé côté métier (Option C)
    cumul_irg = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Cumuls par rubrique (JSON pour flexibilité)
    cumuls_rubriques = models.JSONField(default=dict, blank=True, help_text="Cumuls détaillés par rubrique")
    
    # Nombre de bulletins
    nombre_bulletins = models.IntegerField(default=0)
    
    # Dates de mise à jour
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cumuls_paie'
        verbose_name = 'Cumul de paie'
        verbose_name_plural = 'Cumuls de paie'
        unique_together = ['employe', 'annee']
        ordering = ['-annee', 'employe']
    
    def __str__(self):
        return f"{self.employe.matricule} - {self.annee}: {self.cumul_net:,.0f} GNF"
    
    @property
    def cumul_rts(self):
        """Alias RTS pour cumul_irg"""
        return self.cumul_irg
    
    @cumul_rts.setter
    def cumul_rts(self, value):
        self.cumul_irg = value


class HistoriquePaie(models.Model):
    """Historique des modifications de paie"""
    TYPES_ACTION = (
        ('creation', 'Création'),
        ('modification', 'Modification'),
        ('suppression', 'Suppression'),
        ('validation', 'Validation'),
        ('cloture', 'Clôture'),
        ('recalcul', 'Recalcul'),
    )
    
    bulletin = models.ForeignKey(BulletinPaie, on_delete=models.CASCADE, related_name='historique', null=True, blank=True)
    periode = models.ForeignKey(PeriodePaie, on_delete=models.CASCADE, related_name='historique', null=True, blank=True)
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='historique_paie', null=True, blank=True)
    
    type_action = models.CharField(max_length=20, choices=TYPES_ACTION)
    description = models.TextField()
    
    # Valeurs avant/après (JSON)
    valeurs_avant = models.JSONField(null=True, blank=True)
    valeurs_apres = models.JSONField(null=True, blank=True)
    
    # Utilisateur et date
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    date_action = models.DateTimeField(auto_now_add=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'historique_paie'
        verbose_name = 'Historique de paie'
        verbose_name_plural = 'Historiques de paie'
        ordering = ['-date_action']
    
    def __str__(self):
        return f"{self.type_action} - {self.date_action.strftime('%d/%m/%Y %H:%M')}"


# ============= CONFORMITÉ LÉGISLATIVE GUINÉENNE =============

class GrilleIndiciaire(models.Model):
    """Grille indiciaire pour fonction publique ou convention collective"""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='grilles_indiciaires', null=True, blank=True)
    code_grille = models.CharField(max_length=20)
    libelle = models.CharField(max_length=100)
    categorie = models.CharField(max_length=20, help_text="Catégorie professionnelle (A, B, C, D...)")
    echelon = models.IntegerField(help_text="Échelon dans la catégorie")
    indice = models.IntegerField(help_text="Indice de rémunération")
    valeur_point = models.DecimalField(max_digits=10, decimal_places=2, default=1, help_text="Valeur du point indiciaire")
    salaire_base = models.DecimalField(max_digits=15, decimal_places=2, help_text="Salaire de base correspondant")
    convention_collective = models.CharField(max_length=100, blank=True, null=True)
    date_effet = models.DateField()
    actif = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'grilles_indiciaires'
        verbose_name = 'Grille indiciaire'
        verbose_name_plural = 'Grilles indiciaires'
        unique_together = ['entreprise', 'categorie', 'echelon', 'date_effet']
        ordering = ['categorie', 'echelon']
    
    def __str__(self):
        return f"{self.categorie}-{self.echelon} : {self.salaire_base:,.0f} GNF"


class AvanceSalaire(models.Model):
    """Gestion des avances sur salaire"""
    STATUTS = (
        ('en_cours', 'En cours'),
        ('soldee', 'Soldée'),
        ('annulee', 'Annulée'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='avances_salaire')
    date_demande = models.DateField()
    date_accord = models.DateField(null=True, blank=True)
    montant_total = models.DecimalField(max_digits=15, decimal_places=2)
    nb_mensualites = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    montant_mensuel = models.DecimalField(max_digits=15, decimal_places=2)
    montant_rembourse = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    solde_restant = models.DecimalField(max_digits=15, decimal_places=2)
    motif = models.TextField(blank=True, null=True)
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_cours')
    periode_debut = models.ForeignKey(PeriodePaie, on_delete=models.SET_NULL, null=True, related_name='avances_debut')
    approuve_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name='avances_approuvees')
    
    class Meta:
        db_table = 'avances_salaire'
        verbose_name = 'Avance sur salaire'
        verbose_name_plural = 'Avances sur salaire'
        ordering = ['-date_demande']
    
    def __str__(self):
        return f"{self.employe.matricule} - {self.montant_total:,.0f} GNF ({self.statut})"
    
    def save(self, *args, **kwargs):
        if not self.montant_mensuel:
            self.montant_mensuel = self.montant_total / self.nb_mensualites
        self.solde_restant = self.montant_total - self.montant_rembourse
        super().save(*args, **kwargs)


class SaisieArret(models.Model):
    """Saisie-arrêt sur salaire"""
    TYPES_SAISIE = (
        ('pension_alimentaire', 'Pension alimentaire'),
        ('credit_bancaire', 'Crédit bancaire'),
        ('judiciaire', 'Saisie judiciaire'),
        ('fiscale', 'Saisie fiscale'),
        ('autre', 'Autre'),
    )
    STATUTS = (
        ('active', 'Active'),
        ('suspendue', 'Suspendue'),
        ('terminee', 'Terminée'),
    )
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='saisies_arret')
    type_saisie = models.CharField(max_length=30, choices=TYPES_SAISIE)
    reference_decision = models.CharField(max_length=100, help_text="Référence du jugement ou décision")
    date_notification = models.DateField()
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    montant_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    montant_mensuel = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    taux_saisie = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Pourcentage du salaire")
    quote_saisissable = models.DecimalField(max_digits=5, decimal_places=2, default=33.33, help_text="Quote-part saisissable selon barème légal")
    beneficiaire = models.CharField(max_length=200)
    rib_beneficiaire = models.CharField(max_length=50, blank=True, null=True)
    montant_preleve = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=STATUTS, default='active')
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'saisies_arret'
        verbose_name = 'Saisie-arrêt'
        verbose_name_plural = 'Saisies-arrêt'
        ordering = ['-date_debut']
    
    def __str__(self):
        return f"{self.employe.matricule} - {self.get_type_saisie_display()} ({self.statut})"


class DeclarationSociale(models.Model):
    """Déclarations sociales obligatoires"""
    TYPES_DECLARATION = (
        ('cnss_mensuelle', 'Déclaration CNSS mensuelle'),
        ('irpp_mensuelle', 'Déclaration IRPP mensuelle'),
        ('dipe', 'DIPE - Déclaration Individuelle Préalable à l\'Embauche'),
        ('etat_annuel', 'État récapitulatif annuel'),
        ('das', 'Déclaration Annuelle des Salaires'),
    )
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('generee', 'Générée'),
        ('validee', 'Validée'),
        ('transmise', 'Transmise'),
        ('acceptee', 'Acceptée'),
        ('rejetee', 'Rejetée'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='declarations_sociales')
    type_declaration = models.CharField(max_length=30, choices=TYPES_DECLARATION)
    periode = models.ForeignKey(PeriodePaie, on_delete=models.CASCADE, null=True, blank=True, related_name='declarations')
    annee = models.IntegerField()
    mois = models.IntegerField(null=True, blank=True)
    reference = models.CharField(max_length=50, unique=True)
    
    # Montants
    effectif_declare = models.IntegerField(default=0)
    masse_salariale = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    base_cotisation = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    montant_cotisation_employe = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_cotisation_employeur = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Statut et dates
    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    date_generation = models.DateTimeField(null=True, blank=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_transmission = models.DateTimeField(null=True, blank=True)
    date_limite = models.DateField(null=True, blank=True)
    
    # Fichiers
    fichier_declaration = models.FileField(upload_to='declarations/', null=True, blank=True)
    accuse_reception = models.FileField(upload_to='declarations/ar/', null=True, blank=True)
    
    # Utilisateurs
    genere_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name='declarations_generees')
    valide_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name='declarations_validees')
    
    observations = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'declarations_sociales'
        verbose_name = 'Déclaration sociale'
        verbose_name_plural = 'Déclarations sociales'
        ordering = ['-annee', '-mois']
    
    def __str__(self):
        return f"{self.get_type_declaration_display()} - {self.reference}"


class LigneDeclaration(models.Model):
    """Lignes détaillées d'une déclaration sociale"""
    declaration = models.ForeignKey(DeclarationSociale, on_delete=models.CASCADE, related_name='lignes')
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE)
    bulletin = models.ForeignKey(BulletinPaie, on_delete=models.SET_NULL, null=True, blank=True)
    
    salaire_brut = models.DecimalField(max_digits=15, decimal_places=2)
    base_cotisation = models.DecimalField(max_digits=15, decimal_places=2)
    cotisation_employe = models.DecimalField(max_digits=15, decimal_places=2)
    cotisation_employeur = models.DecimalField(max_digits=15, decimal_places=2)
    
    class Meta:
        db_table = 'lignes_declarations'
        verbose_name = 'Ligne de déclaration'
        verbose_name_plural = 'Lignes de déclaration'
    
    def __str__(self):
        return f"{self.declaration.reference} - {self.employe.matricule}"


class DeclarationEtax(models.Model):
    """Historique des déclarations préparées pour le portail eTax Guinée."""
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('generee', 'Générée'),
        ('declaree', 'Déclarée sur eTax'),
        ('payee', 'Payée'),
        ('rejetee', 'Rejetée'),
    )

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='declarations_etax')
    periode = models.ForeignKey(PeriodePaie, on_delete=models.SET_NULL, null=True, blank=True, related_name='declarations_etax')
    annee = models.IntegerField()
    mois = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    reference = models.CharField(max_length=60, unique=True)

    effectif_declare = models.IntegerField(default=0)
    total_brut = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_base_rts = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_rts = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_vf = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_ta = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_onfpp = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_fiscal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_cnss_employe = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_cnss_employeur = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_cnss = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_general = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    reference_etax = models.CharField(max_length=100, blank=True, null=True)
    date_generation = models.DateTimeField(null=True, blank=True)
    date_declaration = models.DateField(null=True, blank=True)
    date_paiement = models.DateField(null=True, blank=True)

    fichier_pdf = models.FileField(upload_to='declarations/etax/pdf/', null=True, blank=True)
    fichier_excel = models.FileField(upload_to='declarations/etax/excel/', null=True, blank=True)
    fichier_recu = models.FileField(upload_to='declarations/etax/recus/', null=True, blank=True)

    genere_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='declarations_etax_generees')
    observations = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'declarations_etax'
        verbose_name = 'Déclaration eTax'
        verbose_name_plural = 'Déclarations eTax'
        ordering = ['-annee', '-mois']
        unique_together = ['entreprise', 'annee', 'mois']

    def __str__(self):
        return f"eTax {self.mois:02d}/{self.annee} - {self.reference}"


class AlerteEcheance(models.Model):
    """Alertes pour les échéances de déclarations sociales et fiscales"""
    TYPES_ECHEANCE = (
        ('cnss', 'Déclaration CNSS'),
        ('rts', 'Déclaration RTS'),
        ('vf', 'Versement Forfaitaire'),
        ('ta', 'Taxe d\'Apprentissage'),
        ('dmu', 'Déclaration Mensuelle Unique'),
    )
    
    STATUTS = (
        ('a_venir', 'À venir'),
        ('urgent', 'Urgent'),
        ('en_retard', 'En retard'),
        ('traite', 'Traité'),
    )
    
    NIVEAUX_ALERTE = (
        ('info', 'Information'),
        ('warning', 'Avertissement'),
        ('danger', 'Urgent'),
    )
    
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='alertes_echeances')
    type_echeance = models.CharField(max_length=20, choices=TYPES_ECHEANCE)
    annee = models.IntegerField()
    mois = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    
    date_echeance = models.DateField(help_text='Date limite de déclaration (15 du mois suivant)')
    date_alerte = models.DateField(help_text='Date à laquelle l\'alerte a été créée')
    
    statut = models.CharField(max_length=20, choices=STATUTS, default='a_venir')
    niveau_alerte = models.CharField(max_length=20, choices=NIVEAUX_ALERTE, default='info')
    
    jours_restants = models.IntegerField(default=0, help_text='Jours restants avant l\'échéance')
    
    montant_estime = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
                                         help_text='Montant estimé de la déclaration')
    
    message = models.TextField(blank=True, null=True)
    lu = models.BooleanField(default=False)
    date_lecture = models.DateTimeField(null=True, blank=True)
    
    declaration = models.ForeignKey(DeclarationSociale, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='alertes')
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'alertes_echeances'
        verbose_name = 'Alerte échéance'
        verbose_name_plural = 'Alertes échéances'
        ordering = ['date_echeance', '-niveau_alerte']
        unique_together = ['entreprise', 'type_echeance', 'annee', 'mois']
    
    def __str__(self):
        return f"{self.get_type_echeance_display()} - {self.mois}/{self.annee} - {self.get_statut_display()}"
    
    def actualiser_statut(self):
        """Actualise le statut et le niveau d'alerte en fonction de la date"""
        from datetime import date
        aujourd_hui = date.today()
        
        self.jours_restants = (self.date_echeance - aujourd_hui).days
        
        if self.statut == 'traite':
            return  # Ne pas modifier si déjà traité
        
        if self.jours_restants < 0:
            self.statut = 'en_retard'
            self.niveau_alerte = 'danger'
            self.message = f"⚠️ RETARD: Échéance dépassée de {abs(self.jours_restants)} jour(s). Risque de pénalités!"
        elif self.jours_restants <= 1:
            self.statut = 'urgent'
            self.niveau_alerte = 'danger'
            self.message = f"🚨 URGENT: Échéance demain! Déclarez immédiatement."
        elif self.jours_restants <= 3:
            self.statut = 'urgent'
            self.niveau_alerte = 'warning'
            self.message = f"⏰ Attention: {self.jours_restants} jour(s) restant(s) avant l'échéance."
        elif self.jours_restants <= 5:
            self.statut = 'a_venir'
            self.niveau_alerte = 'warning'
            self.message = f"📅 Rappel: {self.jours_restants} jour(s) avant l'échéance du {self.date_echeance.strftime('%d/%m/%Y')}."
        else:
            self.statut = 'a_venir'
            self.niveau_alerte = 'info'
            self.message = f"ℹ️ Échéance prévue le {self.date_echeance.strftime('%d/%m/%Y')} ({self.jours_restants} jours)."
        
        self.save()
    
    @classmethod
    def generer_alertes_mois(cls, entreprise, annee, mois):
        """Génère les alertes pour un mois donné"""
        from datetime import date
        from calendar import monthrange
        
        # L'échéance est le 15 du mois suivant
        if mois == 12:
            mois_echeance = 1
            annee_echeance = annee + 1
        else:
            mois_echeance = mois + 1
            annee_echeance = annee
        
        date_echeance = date(annee_echeance, mois_echeance, 15)
        aujourd_hui = date.today()
        
        types_declarations = [
            ('cnss', 'Déclaration CNSS'),
            ('rts', 'Déclaration RTS'),
            ('vf', 'Versement Forfaitaire'),
        ]
        
        alertes_creees = []
        
        for type_code, type_libelle in types_declarations:
            alerte, created = cls.objects.update_or_create(
                entreprise=entreprise,
                type_echeance=type_code,
                annee=annee,
                mois=mois,
                defaults={
                    'date_echeance': date_echeance,
                    'date_alerte': aujourd_hui,
                }
            )
            alerte.actualiser_statut()
            alertes_creees.append(alerte)
        
        return alertes_creees


class ArchiveBulletin(models.Model):
    """Archive des bulletins de paie en PDF - Conservation légale 10 ans"""
    bulletin = models.OneToOneField(BulletinPaie, on_delete=models.CASCADE, related_name='archive')
    
    # Fichier PDF
    fichier_pdf = models.FileField(upload_to='archives/bulletins/%Y/%m/', help_text='Bulletin PDF archivé')
    taille_fichier = models.IntegerField(default=0, help_text='Taille en octets')
    hash_fichier = models.CharField(max_length=64, blank=True, help_text='SHA256 pour vérification intégrité')
    
    # Métadonnées
    employe_matricule = models.CharField(max_length=20)
    employe_nom = models.CharField(max_length=200)
    periode_annee = models.IntegerField()
    periode_mois = models.IntegerField()
    montant_net = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Dates
    date_generation = models.DateTimeField(auto_now_add=True)
    date_archivage = models.DateTimeField(auto_now_add=True)
    
    # Accès
    nombre_telechargements = models.IntegerField(default=0)
    dernier_telechargement = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'archives_bulletins'
        verbose_name = 'Archive bulletin'
        verbose_name_plural = 'Archives bulletins'
        ordering = ['-periode_annee', '-periode_mois', 'employe_nom']
        indexes = [
            models.Index(fields=['employe_matricule', 'periode_annee', 'periode_mois']),
            models.Index(fields=['periode_annee', 'periode_mois']),
        ]
    
    def __str__(self):
        return f"{self.employe_matricule} - {self.periode_mois:02d}/{self.periode_annee}"


class ConfigurationPaieEntreprise(models.Model):
    """Configuration des paramètres de paie par entreprise
    Permet d'adapter le système au Code du Travail OU aux conventions collectives
    """
    MODES_HS = (
        ('code_travail', 'Code du Travail (+30%/+60%)'),
        ('convention', 'Convention Collective (+15%/+25%/+50%/+100%)'),
        ('personnalise', 'Personnalisé'),
    )
    
    MODES_CONGES = (
        ('code_travail', 'Code du Travail (2,5 j/mois)'),
        ('convention', 'Convention Collective (2,5 j/mois)'),
        ('personnalise', 'Personnalisé'),
    )
    
    entreprise = models.OneToOneField(
        Entreprise, 
        on_delete=models.CASCADE, 
        related_name='config_paie',
        primary_key=True
    )
    
    # === HEURES SUPPLÉMENTAIRES ===
    mode_heures_sup = models.CharField(
        max_length=20, 
        choices=MODES_HS, 
        default='code_travail',
        verbose_name='Mode calcul HS'
    )
    # Code du Travail Art. 221
    taux_hs_4_premieres = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.00,
        verbose_name='Majoration 4 premières HS/semaine (%)',
        help_text='Code du Travail: 30%, Convention: 15%'
    )
    taux_hs_au_dela = models.DecimalField(
        max_digits=5, decimal_places=2, default=60.00,
        verbose_name='Majoration HS au-delà (%)',
        help_text='Code du Travail: 60%, Convention: 25%'
    )
    taux_hs_nuit = models.DecimalField(
        max_digits=5, decimal_places=2, default=20.00,
        verbose_name='Majoration heures de nuit (%)',
        help_text='20h-6h. Code du Travail: 20%, Convention: 50%'
    )
    taux_hs_dimanche = models.DecimalField(
        max_digits=5, decimal_places=2, default=60.00,
        verbose_name='Majoration dimanche/férié jour (%)',
        help_text='Jour férié: 60%'
    )
    taux_hs_ferie_nuit = models.DecimalField(
        max_digits=5, decimal_places=2, default=100.00,
        verbose_name='Majoration férié nuit (%)',
        help_text='Convention: 100%'
    )
    
    # === CONGÉS ===
    mode_conges = models.CharField(
        max_length=20, 
        choices=MODES_CONGES, 
        default='code_travail',
        verbose_name='Mode calcul congés'
    )
    jours_conges_par_mois = models.DecimalField(
        max_digits=4, decimal_places=2, default=2.50,
        verbose_name='Jours de congé acquis par mois',
        help_text='Minimum légal Code du Travail Art. 222 : 2,5 j/mois (30 j/an). Une convention collective peut être plus favorable.'
    )
    jours_conges_anciennete = models.DecimalField(
        max_digits=4, decimal_places=2, default=2.00,
        verbose_name='Jours supplémentaires par tranche ancienneté',
        help_text='Généralement +2 jours par 5 ans d\'ancienneté'
    )
    tranche_anciennete_annees = models.IntegerField(
        default=5,
        verbose_name='Tranche ancienneté (années)',
        help_text='Nombre d\'années pour bonus congés'
    )
    
    # === CNSS ===
    taux_cnss_employe = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        verbose_name='Taux CNSS employé (%)'
    )
    taux_cnss_employeur = models.DecimalField(
        max_digits=5, decimal_places=2, default=18.00,
        verbose_name='Taux CNSS employeur (%)'
    )
    plafond_cnss = models.DecimalField(
        max_digits=15, decimal_places=2, default=2500000.00,
        verbose_name='Plafond CNSS (GNF)'
    )
    plancher_cnss = models.DecimalField(
        max_digits=15, decimal_places=2, default=550000.00,
        verbose_name='Plancher CNSS / SMIG (GNF)'
    )
    
    # === CHARGES PATRONALES ===
    taux_versement_forfaitaire = models.DecimalField(
        max_digits=5, decimal_places=2, default=6.00,
        verbose_name='Versement Forfaitaire VF (%)'
    )
    taux_taxe_apprentissage = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.00,
        verbose_name='Taxe d\'Apprentissage TA (%)'
    )
    taux_onfpp = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.50,
        verbose_name='Contribution ONFPP (%)'
    )

    # === ARRONDI DU NET À PAYER ===
    # Arrondi appliqué uniquement sur le net final (pour faciliter paiement
    # espèces / virements). Les bases CNSS et RTS restent calculées à l'unité
    # exacte pour la conformité fiscale.
    ARRONDIS_NET = (
        (0, 'Aucun (à l\'unité GNF)'),
        (100, 'Centaine de GNF'),
        (500, 'Demi-millier (500 GNF)'),
        (1000, 'Millier de GNF'),
    )
    arrondi_net = models.IntegerField(
        choices=ARRONDIS_NET, default=0,
        verbose_name='Arrondi du net à payer',
        help_text='Arrondi appliqué uniquement sur le net final. '
                  'Les bases fiscales (CNSS, RTS) restent à l\'unité.'
    )

    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    modifie_par = models.ForeignKey(
        Utilisateur, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        db_table = 'config_paie_entreprise'
        verbose_name = 'Configuration paie entreprise'
        verbose_name_plural = 'Configurations paie entreprises'
    
    def __str__(self):
        return f"Config Paie - {self.entreprise.nom_entreprise}"
    
    def appliquer_mode_code_travail(self):
        """Applique les taux du Code du Travail guinéen"""
        self.mode_heures_sup = 'code_travail'
        self.taux_hs_4_premieres = Decimal('30.00')
        self.taux_hs_au_dela = Decimal('60.00')
        self.taux_hs_nuit = Decimal('20.00')
        self.mode_conges = 'code_travail'
        # Code du Travail Art. 222 : minimum légal 2,5 j/mois (30 j/an)
        self.jours_conges_par_mois = Decimal('2.50')
        self.save()
    
    def appliquer_mode_convention(self):
        """Applique les taux des conventions collectives"""
        self.mode_heures_sup = 'convention'
        self.taux_hs_4_premieres = Decimal('15.00')
        self.taux_hs_au_dela = Decimal('25.00')
        self.taux_hs_nuit = Decimal('50.00')
        self.taux_hs_dimanche = Decimal('100.00')
        self.taux_hs_ferie_nuit = Decimal('100.00')
        self.mode_conges = 'convention'
        self.jours_conges_par_mois = Decimal('2.50')
        self.save()
    
    @classmethod
    def get_ou_creer(cls, entreprise):
        """Récupère ou crée la configuration pour une entreprise"""
        config, created = cls.objects.get_or_create(entreprise=entreprise)
        return config


class ParametresCalculPaie(models.Model):
    """Paramètres personnalisables du moteur de calcul de paie"""
    entreprise = models.OneToOneField('core.Entreprise', on_delete=models.CASCADE, related_name='parametres_calcul_paie')

    # Exonération indemnités forfaitaires
    MODE_EXONERATION = [
        ('plafond_pct', 'Plafond % du brut (CGI strict)'),
        # Modes ci-dessous désactivés — non conformes CGI
        # ('integrale', 'Exonération intégrale'),
        # ('formule', 'Formule personnalisée'),
    ]
    mode_exoneration_indemnites = models.CharField(
        max_length=20, choices=MODE_EXONERATION, default='plafond_pct'
    )
    plafond_exoneration_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=25,
        help_text="Plafond % du brut (défaut CGI: 25%)"
    )
    formule_exoneration = models.TextField(
        blank=True,
        help_text="Ex: brut * 0.25 ou indemnites if indemnites <= brut * 0.3 else brut * 0.3"
    )

    # Base VF / TA
    MODE_BASE_VF = [
        ('brut_moins_deduction', 'Mode historique non standard : VF/TA sur brut - deduction'),
        ('brut', 'Mode legal par defaut : VF/TA sur salaire brut'),
        ('formule', 'Formule personnalisee'),
    ]
    mode_base_vf = models.CharField(
        max_length=30, choices=MODE_BASE_VF, default='brut'
    )
    formule_base_vf = models.TextField(
        blank=True,
        help_text="Ex: brut - 150000 if brut >= 2500000 else brut * 0.94"
    )

    MODE_BASE_ONFPP = [
        ('base_vf', 'Mode personnalise : ONFPP sur base VF/TA'),
        ('brut', 'Mode legal par defaut : ONFPP sur salaire brut'),
    ]
    mode_base_onfpp = models.CharField(
        max_length=20, choices=MODE_BASE_ONFPP, default='brut'
    )

    # Base RTS personnalisée
    utiliser_formule_base_rts = models.BooleanField(default=False)
    formule_base_rts = models.TextField(
        blank=True,
        help_text="Ex: brut - cnss - (indemnites if indemnites <= brut*0.25 else brut*0.25)"
    )

    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'parametres_calcul_paie'
        verbose_name = 'Paramètres calcul paie'
        verbose_name_plural = 'Paramètres calcul paie'

    def __str__(self):
        return f"Paramètres calcul paie — {self.entreprise.nom_entreprise}"

    def appliquer_modele_standard_guineerh(self):
        """Applique le modèle validé pour les bulletins GuinéeRH standard."""
        self.mode_exoneration_indemnites = 'plafond_pct'
        self.plafond_exoneration_pct = Decimal('25')
        self.formule_exoneration = ''
        self.mode_base_vf = 'brut'
        self.formule_base_vf = ''
        self.mode_base_onfpp = 'brut'
        self.utiliser_formule_base_rts = False
        self.formule_base_rts = ''


class HistoriqueParametresPaie(models.Model):
    """Historique des modifications des paramètres de calcul de paie"""
    parametres = models.ForeignKey(ParametresCalculPaie, on_delete=models.CASCADE, related_name='historique')
    modifie_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True)
    date_modification = models.DateTimeField(auto_now_add=True)
    champ_modifie = models.CharField(max_length=100)
    ancienne_valeur = models.TextField(blank=True)
    nouvelle_valeur = models.TextField(blank=True)
    raison = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'historique_parametres_paie'
        ordering = ['-date_modification']
        verbose_name = 'Historique paramètres paie'
        verbose_name_plural = 'Historiques paramètres paie'

    def __str__(self):
        return f"Modification {self.champ_modifie} — {self.date_modification:%d/%m/%Y %H:%M}"


# ============================================================================
# SIMULATION SALARIALE (reproductibilité des calculs)
# ============================================================================

class SimulationPaie(models.Model):
    """Historique des simulations de structuration salariale."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='simulations_paie')
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='simulations_paie', null=True, blank=True)
    utilisateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True)

    brut = models.DecimalField(max_digits=15, decimal_places=0)
    composantes = models.JSONField(help_text="[{cle, label, pct, montant}, ...]")
    impact = models.JSONField(help_text="{cnss, rts, net, taux_effectif, detail_tranches, regles, ...}")
    comparaison = models.JSONField(null=True, blank=True, help_text="[{scenario, rts, cnss, net, taux}, ...]")
    gain = models.JSONField(null=True, blank=True, help_text="{gain_net_mensuel, gain_net_annuel, ...}")
    conformite = models.CharField(max_length=20, default='conforme', help_text="conforme / a_verifier / non_conforme")
    avertissements = models.JSONField(default=list, blank=True, help_text="Liste des warnings détectés")
    version_bareme = models.CharField(max_length=30, default='GN-2026-v1', help_text="Version du barème fiscal utilisé")

    appliquee = models.BooleanField(default=False, help_text="True si les éléments ont été créés en lot")
    date_application = models.DateTimeField(null=True, blank=True)

    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'simulations_paie'
        ordering = ['-date_creation']
        verbose_name = 'Simulation de paie'
        verbose_name_plural = 'Simulations de paie'
        indexes = [
            models.Index(fields=['entreprise', '-date_creation'], name='idx_sim_entreprise_date'),
            models.Index(fields=['employe', '-date_creation'], name='idx_sim_employe_date'),
        ]

    def __str__(self):
        return f"Simulation {self.brut:,.0f} GNF — {self.date_creation:%d/%m/%Y %H:%M}"

    def save(self, *args, **kwargs):
        # Immutabilité : seule la création est autorisée (+ marquage appliquee)
        if self.pk:
            allowed = {'appliquee', 'date_application'}
            update_fields = set(kwargs.get('update_fields') or [])
            if not update_fields or not update_fields.issubset(allowed):
                raise ValueError("SimulationPaie est immutable après création")
        super().save(*args, **kwargs)


class AuditSimulation(models.Model):
    """Journal d'audit léger pour les actions de simulation / création."""
    ACTION_CHOICES = [
        ('validation', 'Validation simulation'),
        ('creation', 'Création éléments en lot'),
        ('pdf', 'Génération PDF'),
        ('proposition', 'Proposition automatique complète'),
    ]
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='audits_simulation')
    utilisateur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    simulation = models.ForeignKey(SimulationPaie, on_delete=models.SET_NULL, null=True, blank=True, related_name='audits')
    metadata = models.JSONField(default=dict, blank=True, help_text="Détails contextuels libres")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_simulations'
        ordering = ['-timestamp']
        verbose_name = 'Audit simulation'
        verbose_name_plural = 'Audits simulation'
        indexes = [
            models.Index(fields=['entreprise', '-timestamp'], name='idx_audit_entreprise_ts'),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.utilisateur} — {self.timestamp:%d/%m/%Y %H:%M}"


# ============================================================================
# RÈGLES DE CONFORMITÉ INDEMNITÉS
# ============================================================================

class RegleIndemnite(models.Model):
    """Règles de conformité par type d'indemnité (fourchettes marché + profil salarié)"""

    TYPES_INDEMNITE = [
        ('transport', 'Transport'),
        ('logement', 'Logement'),
        ('cherte_vie', 'Cherté de vie'),
        ('panier', 'Panier'),
        ('deplacement', 'Déplacement'),
        ('representation', 'Représentation'),
        ('autre', 'Autre'),
    ]

    NIVEAUX_RISQUE = [
        ('info', '🟢 Conforme'),
        ('attention', '🟡 À surveiller'),
        ('risque', '🔴 Risque fiscal'),
    ]

    CATEGORIES_EMPLOYE = [
        ('tous', 'Tous'),
        ('cadre', 'Cadre'),
        ('agent_maitrise', 'Agent de maîtrise'),
        ('employe', 'Employé'),
        ('ouvrier', 'Ouvrier'),
    ]

    entreprise = models.ForeignKey(
        'core.Entreprise', on_delete=models.CASCADE,
        related_name='regles_indemnites'
    )
    type_indemnite = models.CharField(max_length=30, choices=TYPES_INDEMNITE)
    categorie_employe = models.CharField(
        max_length=30, choices=CATEGORIES_EMPLOYE, default='tous',
        help_text='Catégorie professionnelle concernée (tous = toutes)'
    )
    seuil_min_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Seuil minimum recommandé (% du salaire de base)'
    )
    seuil_max_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text='Seuil maximum recommandé (% du salaire de base)'
    )
    justification_requise = models.CharField(
        max_length=200, blank=True,
        help_text='Justificatif attendu en cas de contrôle'
    )
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'regles_indemnites'
        verbose_name = 'Règle indemnité'
        verbose_name_plural = 'Règles indemnités'
        unique_together = ['entreprise', 'type_indemnite', 'categorie_employe']
        ordering = ['type_indemnite', 'categorie_employe']

    def __str__(self):
        cat = self.get_categorie_employe_display()
        return f"{self.get_type_indemnite_display()} ({cat}) : {self.seuil_min_pct}–{self.seuil_max_pct}%"


# Import des modèles de frais
from .models_frais import CategoriesFrais, NoteFrais, LigneFrais, BaremeFrais

# Import des modèles charges sociales
from .models_social import (
    CotisationSociale, DeclarationCNSS, LigneCNSS, MutuelleEntreprise,
    AffiliationMutuelle, RetraiteComplementaire, AffiliationRetraite,
    AffiliationSecuriteSociale, DossierPaie, BilanPaie
)
