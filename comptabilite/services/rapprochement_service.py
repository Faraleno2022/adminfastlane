"""
Service pour la gestion des rapprochements bancaires.

Encapsule la logique métier:
- Rapprochement des opérations
- Lettrage des écritures
- Gestion des écarts
"""

from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import logging

from .base_service import BaseComptaService
from ..models import (
    RapprochementBancaire, CompteBancaire, OperationBancaire,
    LettrageOperation, EcartBancaire, EcritureComptable, LigneEcriture
)

logger = logging.getLogger(__name__)


class RapprochementService(BaseComptaService):
    """Service métier pour les rapprochements bancaires."""
    
    def calculer_solde_comptable(self, compte_bancaire, date_fin):
        """
        Calcule le solde comptable à une date donnée.
        
        Args:
            compte_bancaire: Instance de CompteBancaire
            date_fin: Date limite
        
        Returns:
            Decimal: Solde comptable
        """
        from ..models import PlanComptable
        
        if not compte_bancaire.compte_comptable:
            raise ValidationError("Compte bancaire non lié à un compte comptable")
        
        # Récupère toutes les écritures jusqu'à la date
        compte = compte_bancaire.compte_comptable
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        
        for ligne in LigneEcriture.objects.filter(
            compte=compte,
            ecriture__date_ecriture__lte=date_fin,
            ecriture__est_validee=True,
        ):
            total_debit += ligne.montant_debit
            total_credit += ligne.montant_credit
        
        # Le solde d'ouverture du compte bancaire precede les mouvements du
        # grand livre. Les brouillons sont exclus ci-dessus.
        solde = compte_bancaire.solde_initial + total_debit - total_credit
        return solde
    
    def calculer_solde_bancaire(self, releve):
        """
        Calcule le solde bancaire d'un relevé.
        
        Args:
            releve: Instance de ReleveBancaire
        
        Returns:
            Decimal: Solde bancaire
        """
        operations = OperationBancaire.objects.filter(releve=releve)
        solde = releve.solde_initial
        
        for op in operations:
            if op.type_operation == 'credit':
                solde += op.montant
            else:
                solde -= op.montant
        
        return solde
    
    @transaction.atomic
    def creer_rapprochement(self, compte_bancaire, releve, date_rapprochement):
        """
        Crée un rapprochement bancaire.
        
        Args:
            compte_bancaire: Instance de CompteBancaire
            releve: Instance de ReleveBancaire
            date_rapprochement: Date du rapprochement
        
        Returns:
            RapprochementBancaire: Nouveau rapprochement
        """
        # Valide l'exercice
        from ..models import ExerciceComptable
        exercice = ExerciceComptable.objects.filter(
            entreprise=self.entreprise,
            date_debut__lte=date_rapprochement,
            date_fin__gte=date_rapprochement
        ).first()
        
        if not exercice:
            raise ValidationError(f"Aucun exercice pour la date {date_rapprochement}")
        
        self.valider_exercice(exercice)
        
        # Calcule les soldes
        solde_comptable = self.calculer_solde_comptable(compte_bancaire, date_rapprochement)
        solde_bancaire = self.calculer_solde_bancaire(releve)
        ecart = abs(solde_comptable - solde_bancaire)
        
        # Crée le rapprochement
        rapprochement = RapprochementBancaire.objects.create(
            compte_bancaire=compte_bancaire,
            date_rapprochement=date_rapprochement,
            solde_bancaire=solde_bancaire,
            solde_comptable=solde_comptable,
            ecart=ecart,
            statut='en_cours',
            responsable=self.utilisateur
        )
        
        # Enregistre l'audit
        self.enregistrer_audit(
            'create', 'Rapprochements bancaires', 'RapprochementBancaire',
            rapprochement.id, {'solde_bancaire': str(solde_bancaire)}
        )
        
        logger.info(f"Rapprochement créé: {rapprochement}")
        return rapprochement
    
    @transaction.atomic
    def lettrer_operation(self, operation_bancaire, ecriture_comptable):
        """
        Lettre une opération bancaire avec une écriture comptable.
        
        Args:
            operation_bancaire: Instance de OperationBancaire
            ecriture_comptable: Instance de EcritureComptable
        
        Returns:
            LettrageOperation: Nouveau lettrage
        """
        compte_bancaire = operation_bancaire.releve.compte_bancaire
        compte_comptable = compte_bancaire.compte_comptable
        if not compte_comptable:
            raise ValidationError("Compte bancaire non lié à un compte comptable")

        # Une écriture peut contenir plusieurs contreparties. Le montant à
        # rapprocher est le mouvement net du compte bancaire concerné.
        lignes_banque = ecriture_comptable.lignes.filter(compte=compte_comptable)
        debit_banque = sum(
            (ligne.montant_debit or Decimal('0.00') for ligne in lignes_banque),
            Decimal('0.00'),
        )
        credit_banque = sum(
            (ligne.montant_credit or Decimal('0.00') for ligne in lignes_banque),
            Decimal('0.00'),
        )
        montant_banque = abs(debit_banque - credit_banque)
        if operation_bancaire.montant != montant_banque:
            raise ValidationError(
                f"Montants différents: {operation_bancaire.montant} vs "
                f"{montant_banque} sur le compte bancaire"
            )
        
        # Crée le lettrage
        lettrage = LettrageOperation.objects.create(
            operation_bancaire=operation_bancaire,
            ecriture=ecriture_comptable
        )
        
        # Enregistre l'audit
        self.enregistrer_audit(
            'create', 'Rapprochements bancaires', 'LettrageOperation',
            lettrage.id, {'operation_id': str(operation_bancaire.id)}
        )
        
        logger.info(f"Lettrage créé: {lettrage}")
        return lettrage
    
    def generer_ecarts(self, rapprochement):
        """
        Génère les écarts non lettrés.
        
        Args:
            rapprochement: Instance de RapprochementBancaire
        
        Returns:
            List[EcartBancaire]: Liste des écarts
        """
        ecarts = []
        
        # Trouve les opérations non lettrées
        operations_non_lettrees = OperationBancaire.objects.filter(
            releve__compte_bancaire=rapprochement.compte_bancaire,
            lettrage_id__isnull=True
        )
        
        for op in operations_non_lettrees:
            # Crée un écart potentiel
            # (Peut être un délai de compensation, frais bancaires, etc.)
            if op.date_operation < rapprochement.date_rapprochement - timedelta(days=10):
                ecart = EcartBancaire.objects.create(
                    rapprochement=rapprochement,
                    type_ecart='retard',
                    montant=op.montant,
                    description=f"Opération non compensée: {op.description}"
                )
                ecarts.append(ecart)
        
        return ecarts
    
    @transaction.atomic
    def valider_rapprochement(self, rapprochement):
        """
        Valide un rapprochement (si écart résolu).
        
        Args:
            rapprochement: Instance de RapprochementBancaire
        
        Raises:
            ValidationError si écarts non résolus
        """
        # Recalcule l'écart
        solde_comptable = self.calculer_solde_comptable(
            rapprochement.compte_bancaire,
            rapprochement.date_rapprochement
        )
        
        ecart = abs(solde_comptable - rapprochement.solde_bancaire)
        if ecart > Decimal('0.01'):
            ecarts_non_resolus = EcartBancaire.objects.filter(
                rapprochement=rapprochement,
                est_resolu=False
            ).count()
            raise ValidationError(
                f"Rapprochement déséquilibré de {ecart}: "
                f"{ecarts_non_resolus} écart(s) non résolu(s)"
            )
        
        rapprochement.statut = 'termine'
        rapprochement.save()
        
        self.enregistrer_audit(
            'validation', 'Rapprochements bancaires', 'RapprochementBancaire',
            rapprochement.id
        )
        
        logger.info(f"Rapprochement validé: {rapprochement}")
