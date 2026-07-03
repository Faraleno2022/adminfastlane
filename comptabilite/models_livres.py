"""
Modèles « livres et documents » — Comptabilité SYSCOHADA
=========================================================
Pièces de caisse (entrée/sortie), bordereaux de versement / remise de
chèques, emprunts avec échéancier. Complète models.py.
"""
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta

from django.db import models
from django.utils import timezone


class PieceCaisse(models.Model):
    """Pièce de caisse : justificatif d'une entrée ou sortie d'espèces."""
    TYPES = (
        ('entree', 'Entrée de caisse'),
        ('sortie', 'Sortie de caisse'),
    )

    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='pieces_caisse')
    numero = models.CharField(max_length=30, verbose_name='Numéro de pièce')
    type_piece = models.CharField(max_length=10, choices=TYPES, verbose_name='Type')
    date_operation = models.DateField(default=timezone.now, verbose_name='Date')
    libelle = models.CharField(max_length=255, verbose_name='Motif / Libellé')
    tiers = models.ForeignKey('comptabilite.Tiers', on_delete=models.SET_NULL, null=True, blank=True,
                              verbose_name='Tiers (payé à / reçu de)')
    beneficiaire = models.CharField(max_length=200, blank=True,
                                    verbose_name='Bénéficiaire / Verseur (si tiers non référencé)')
    montant = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Montant (GNF)')
    reference = models.CharField(max_length=100, blank=True, verbose_name='Référence (facture, contrat…)')
    observation = models.TextField(blank=True, verbose_name='Observation')
    ecriture = models.ForeignKey('comptabilite.EcritureComptable', on_delete=models.SET_NULL,
                                 null=True, blank=True, verbose_name='Écriture liée')
    cree_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pieces_caisse'
        verbose_name = 'Pièce de caisse'
        verbose_name_plural = 'Pièces de caisse'
        ordering = ['-date_operation', '-id']
        unique_together = ['entreprise', 'numero']

    def __str__(self):
        return f"{self.numero} - {self.libelle} ({self.montant} GNF)"

    @property
    def montant_signe(self):
        return self.montant if self.type_piece == 'entree' else -self.montant

    @staticmethod
    def prochain_numero(entreprise, type_piece):
        prefixe = 'PCE' if type_piece == 'entree' else 'PCS'
        annee = timezone.now().year
        base = f"{prefixe}-{annee}-"
        dernier = (PieceCaisse.objects
                   .filter(entreprise=entreprise, numero__startswith=base)
                   .order_by('-numero').first())
        seq = 1
        if dernier:
            try:
                seq = int(dernier.numero.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        return f"{base}{seq:05d}"


class BordereauRemise(models.Model):
    """Bordereau de versement d'espèces ou de remise de chèques en banque."""
    TYPES = (
        ('versement', 'Bordereau de versement (espèces)'),
        ('cheques', 'Bordereau de remise de chèques'),
        ('retrait', 'Bordereau de retrait'),
    )

    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='bordereaux_remise')
    numero = models.CharField(max_length=30, verbose_name='Numéro')
    type_bordereau = models.CharField(max_length=10, choices=TYPES, verbose_name='Type')
    date_remise = models.DateField(default=timezone.now, verbose_name='Date de remise')
    compte_bancaire = models.ForeignKey('comptabilite.CompteBancaire', on_delete=models.PROTECT,
                                        verbose_name='Compte bancaire crédité')
    deposant = models.CharField(max_length=200, blank=True, verbose_name='Déposant')
    observation = models.TextField(blank=True, verbose_name='Observation')
    cree_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bordereaux_remise'
        verbose_name = 'Bordereau de remise'
        verbose_name_plural = 'Bordereaux de remise'
        ordering = ['-date_remise', '-id']
        unique_together = ['entreprise', 'numero']

    def __str__(self):
        return f"{self.numero} ({self.get_type_bordereau_display()})"

    @property
    def montant_total(self):
        return sum((l.montant for l in self.lignes.all()), Decimal('0'))

    @staticmethod
    def prochain_numero(entreprise, type_bordereau):
        prefixe = {'versement': 'BV', 'cheques': 'BRC', 'retrait': 'BR'}.get(type_bordereau, 'BRD')
        annee = timezone.now().year
        base = f"{prefixe}-{annee}-"
        dernier = (BordereauRemise.objects
                   .filter(entreprise=entreprise, numero__startswith=base)
                   .order_by('-numero').first())
        seq = 1
        if dernier:
            try:
                seq = int(dernier.numero.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        return f"{base}{seq:05d}"


class LigneBordereau(models.Model):
    """Ligne d'un bordereau : une coupure/référence espèces ou un chèque."""
    bordereau = models.ForeignKey(BordereauRemise, on_delete=models.CASCADE, related_name='lignes')
    description = models.CharField(max_length=200, verbose_name='Description / N° chèque')
    banque_emettrice = models.CharField(max_length=100, blank=True, verbose_name='Banque émettrice')
    tireur = models.CharField(max_length=200, blank=True, verbose_name='Tireur / Origine')
    montant = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Montant (GNF)')

    class Meta:
        db_table = 'lignes_bordereau'
        verbose_name = 'Ligne de bordereau'
        verbose_name_plural = 'Lignes de bordereau'

    def __str__(self):
        return f"{self.description} - {self.montant} GNF"


class ChequeEmis(models.Model):
    """Chèque émis : suivi des chèques et impression du fac-similé."""
    STATUTS = (
        ('emis', 'Émis'),
        ('encaisse', 'Encaissé'),
        ('annule', 'Annulé'),
        ('oppose', 'Opposition'),
    )

    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='cheques_emis')
    compte_bancaire = models.ForeignKey('comptabilite.CompteBancaire', on_delete=models.PROTECT,
                                        verbose_name='Compte bancaire tiré')
    numero_cheque = models.CharField(max_length=30, verbose_name='N° de chèque')
    beneficiaire = models.CharField(max_length=200, verbose_name='Bénéficiaire (ordre de)')
    montant = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Montant (GNF)')
    date_emission = models.DateField(default=timezone.now, verbose_name="Date d'émission")
    lieu_emission = models.CharField(max_length=100, default='Conakry', verbose_name="Lieu d'émission")
    motif = models.CharField(max_length=255, blank=True, verbose_name='Motif / Référence')
    barre = models.BooleanField(default=True, verbose_name='Chèque barré (non endossable)')
    statut = models.CharField(max_length=10, choices=STATUTS, default='emis')
    cree_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cheques_emis'
        verbose_name = 'Chèque émis'
        verbose_name_plural = 'Chèques émis'
        ordering = ['-date_emission', '-id']
        unique_together = ['entreprise', 'compte_bancaire', 'numero_cheque']

    def __str__(self):
        return f"Chèque {self.numero_cheque} - {self.beneficiaire} ({self.montant} GNF)"


class ArreteCaisse(models.Model):
    """Arrêté de caisse : comptage physique (billetage GNF) confronté au
    solde théorique du livre de caisse."""
    # Coupures GNF en circulation
    COUPURES = (20000, 10000, 5000, 2000, 1000, 500)

    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='arretes_caisse')
    numero = models.CharField(max_length=30, verbose_name='Numéro')
    date_arrete = models.DateField(default=timezone.now, verbose_name="Date de l'arrêté")
    nb_20000 = models.PositiveIntegerField(default=0, verbose_name='Billets de 20 000')
    nb_10000 = models.PositiveIntegerField(default=0, verbose_name='Billets de 10 000')
    nb_5000 = models.PositiveIntegerField(default=0, verbose_name='Billets de 5 000')
    nb_2000 = models.PositiveIntegerField(default=0, verbose_name='Billets de 2 000')
    nb_1000 = models.PositiveIntegerField(default=0, verbose_name='Billets de 1 000')
    nb_500 = models.PositiveIntegerField(default=0, verbose_name='Billets de 500')
    autres_valeurs = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'),
                                         verbose_name='Autres valeurs (pièces, etc.)')
    solde_theorique = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'),
                                          verbose_name='Solde théorique (livre de caisse)')
    observation = models.TextField(blank=True, verbose_name='Observation / justification des écarts')
    caissier = models.CharField(max_length=200, blank=True, verbose_name='Caissier')
    cree_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'arretes_caisse'
        verbose_name = 'Arrêté de caisse'
        verbose_name_plural = 'Arrêtés de caisse'
        ordering = ['-date_arrete', '-id']
        unique_together = ['entreprise', 'numero']

    def __str__(self):
        return f"{self.numero} du {self.date_arrete}"

    @property
    def total_compte(self):
        """Total des espèces comptées physiquement."""
        return (Decimal(self.nb_20000 * 20000) + Decimal(self.nb_10000 * 10000) +
                Decimal(self.nb_5000 * 5000) + Decimal(self.nb_2000 * 2000) +
                Decimal(self.nb_1000 * 1000) + Decimal(self.nb_500 * 500) +
                self.autres_valeurs)

    @property
    def ecart(self):
        """Écart entre comptage physique et solde théorique (+ = excédent)."""
        return self.total_compte - self.solde_theorique

    def detail_billetage(self):
        return [
            {'coupure': 20000, 'quantite': self.nb_20000, 'montant': Decimal(self.nb_20000 * 20000)},
            {'coupure': 10000, 'quantite': self.nb_10000, 'montant': Decimal(self.nb_10000 * 10000)},
            {'coupure': 5000, 'quantite': self.nb_5000, 'montant': Decimal(self.nb_5000 * 5000)},
            {'coupure': 2000, 'quantite': self.nb_2000, 'montant': Decimal(self.nb_2000 * 2000)},
            {'coupure': 1000, 'quantite': self.nb_1000, 'montant': Decimal(self.nb_1000 * 1000)},
            {'coupure': 500, 'quantite': self.nb_500, 'montant': Decimal(self.nb_500 * 500)},
        ]

    @staticmethod
    def prochain_numero(entreprise):
        annee = timezone.now().year
        base = f"AC-{annee}-"
        dernier = (ArreteCaisse.objects
                   .filter(entreprise=entreprise, numero__startswith=base)
                   .order_by('-numero').first())
        seq = 1
        if dernier:
            try:
                seq = int(dernier.numero.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        return f"{base}{seq:05d}"


class DeclarationPatente(models.Model):
    """Déclaration de contribution des patentes (Guinée) :
    droit fixe selon l'activité + droit proportionnel sur la valeur locative."""
    STATUTS = (
        ('brouillon', 'Brouillon'),
        ('deposee', 'Déposée'),
        ('payee', 'Payée'),
    )

    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='declarations_patente')
    annee = models.PositiveIntegerField(verbose_name='Année d\'imposition')
    activite = models.CharField(max_length=255, verbose_name='Activité exercée')
    reference_tarif = models.CharField(max_length=100, blank=True,
                                       verbose_name='Classe / référence du tarif des patentes')
    chiffre_affaires = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'),
                                           verbose_name='Chiffre d\'affaires (GNF)')
    valeur_locative = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'),
                                          verbose_name='Valeur locative des locaux (GNF)')
    droit_fixe = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'),
                                     verbose_name='Droit fixe (GNF)')
    taux_proportionnel = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15'),
                                             verbose_name='Taux du droit proportionnel (%)')
    droit_proportionnel = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'),
                                              verbose_name='Droit proportionnel (GNF)')
    date_declaration = models.DateField(default=timezone.now, verbose_name='Date de déclaration')
    statut = models.CharField(max_length=10, choices=STATUTS, default='brouillon')
    observation = models.TextField(blank=True, verbose_name='Observation')
    cree_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'declarations_patente'
        verbose_name = 'Déclaration de patente'
        verbose_name_plural = 'Déclarations de patente'
        ordering = ['-annee', '-date_declaration']
        unique_together = ['entreprise', 'annee']

    def __str__(self):
        return f"Patente {self.annee} - {self.entreprise.nom_entreprise}"

    def save(self, *args, **kwargs):
        # Droit proportionnel calculé depuis la valeur locative si non saisi
        if not self.droit_proportionnel and self.valeur_locative:
            self.droit_proportionnel = (self.valeur_locative * self.taux_proportionnel /
                                        Decimal('100')).quantize(Decimal('1'))
        super().save(*args, **kwargs)

    @property
    def total_patente(self):
        return self.droit_fixe + self.droit_proportionnel


class Emprunt(models.Model):
    """Emprunt bancaire ou financier avec échéancier à annuités constantes."""
    PERIODICITES = (
        ('mensuelle', 'Mensuelle'),
        ('trimestrielle', 'Trimestrielle'),
        ('semestrielle', 'Semestrielle'),
        ('annuelle', 'Annuelle'),
    )
    STATUTS = (
        ('en_cours', 'En cours'),
        ('solde', 'Soldé'),
        ('contentieux', 'Contentieux'),
    )
    _PERIODES_PAR_AN = {'mensuelle': 12, 'trimestrielle': 4, 'semestrielle': 2, 'annuelle': 1}

    entreprise = models.ForeignKey('core.Entreprise', on_delete=models.CASCADE, related_name='emprunts')
    libelle = models.CharField(max_length=200, verbose_name="Libellé de l'emprunt")
    preteur = models.CharField(max_length=200, verbose_name='Prêteur / Banque')
    reference_contrat = models.CharField(max_length=100, blank=True, verbose_name='Référence du contrat')
    capital_emprunte = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Capital emprunté (GNF)')
    taux_annuel = models.DecimalField(max_digits=6, decimal_places=3, verbose_name='Taux annuel (%)')
    nombre_echeances = models.PositiveIntegerField(verbose_name="Nombre d'échéances")
    periodicite = models.CharField(max_length=15, choices=PERIODICITES, default='mensuelle')
    date_deblocage = models.DateField(verbose_name='Date de déblocage des fonds')
    date_premiere_echeance = models.DateField(verbose_name='Date de la première échéance')
    statut = models.CharField(max_length=15, choices=STATUTS, default='en_cours')
    observation = models.TextField(blank=True, verbose_name='Observation')
    cree_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'emprunts'
        verbose_name = 'Emprunt'
        verbose_name_plural = 'Emprunts'
        ordering = ['-date_deblocage']

    def __str__(self):
        return f"{self.libelle} - {self.preteur} ({self.capital_emprunte} GNF)"

    def _taux_periodique(self):
        n_par_an = self._PERIODES_PAR_AN.get(self.periodicite, 12)
        return (self.taux_annuel / Decimal('100')) / Decimal(n_par_an)

    def _pas_echeance(self):
        return {'mensuelle': 1, 'trimestrielle': 3, 'semestrielle': 6, 'annuelle': 12}.get(self.periodicite, 1)

    def annuite(self):
        """Annuité constante : C × i / (1 − (1+i)^−n). Si taux nul : C / n."""
        n = self.nombre_echeances
        if n == 0:
            return Decimal('0')
        i = self._taux_periodique()
        if i == 0:
            montant = self.capital_emprunte / Decimal(n)
        else:
            facteur = (Decimal('1') + i) ** n
            montant = self.capital_emprunte * i * facteur / (facteur - Decimal('1'))
        return montant.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    def echeancier(self):
        """Tableau d'amortissement : liste de dicts (n°, date, CRD début,
        intérêts, amortissement, annuité, CRD fin). La dernière échéance
        absorbe l'écart d'arrondi."""
        lignes = []
        crd = self.capital_emprunte
        i = self._taux_periodique()
        annuite = self.annuite()
        pas = self._pas_echeance()
        date_ech = self.date_premiere_echeance
        for num in range(1, self.nombre_echeances + 1):
            interets = (crd * i).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            if num == self.nombre_echeances:
                amortissement = crd
                annuite_ligne = crd + interets
            else:
                amortissement = annuite - interets
                annuite_ligne = annuite
            crd_fin = crd - amortissement
            lignes.append({
                'numero': num,
                'date': date_ech,
                'crd_debut': crd,
                'interets': interets,
                'amortissement': amortissement,
                'annuite': annuite_ligne,
                'crd_fin': crd_fin,
            })
            crd = crd_fin
            date_ech = date_ech + relativedelta(months=pas)
        return lignes

    def capital_restant_du(self, a_date=None):
        """Capital restant dû à une date (défaut : aujourd'hui)."""
        a_date = a_date or timezone.now().date()
        crd = self.capital_emprunte
        for ligne in self.echeancier():
            if ligne['date'] <= a_date:
                crd = ligne['crd_fin']
            else:
                break
        return crd

    @property
    def total_interets(self):
        return sum((l['interets'] for l in self.echeancier()), Decimal('0'))

    @property
    def cout_total(self):
        return self.capital_emprunte + self.total_interets
