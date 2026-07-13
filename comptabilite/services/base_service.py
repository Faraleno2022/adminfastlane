"""
Service de base réutilisable pour tous les services métier comptables.

Fournit les fonctionnalités communes:
- Gestion d'erreur standardisée
- Logging d'audit
- Validation métier
- Transactions
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class BaseComptaService:
    """
    Classe de base pour tous les services comptables.
    
    Fournit:
    - Validation métier
    - Logging d'audit
    - Gestion des transactions
    - Erreurs standardisées
    """
    
    def __init__(self, entreprise, utilisateur=None):
        """
        Initialise le service.
        
        Args:
            entreprise: Instance de Entreprise
            utilisateur: Utilisateur actuel (optionnel)
        """
        self.entreprise = entreprise
        self.utilisateur = utilisateur
        self.errors = []
        self.warnings = []
    
    @property
    def erreurs(self):
        """Alias français de self.errors (utilisé par plusieurs services)."""
        return self.errors

    def valider(self, conditions):
        """
        Valide une condition métier.

        La liste d'erreurs est réinitialisée à chaque appel : un échec de
        validation antérieur ne doit pas faire rejeter un calcul valide
        effectué ensuite avec la même instance de service.

        Args:
            conditions: Dict de {message: booléen}

        Raises:
            ValidationError si une condition est fausse
        """
        self.errors = [message for message, condition in conditions.items() if not condition]
        if self.errors:
            raise ValidationError('; '.join(self.errors))

    def avertissement(self, message):
        """Enregistre un avertissement."""
        self.warnings.append(message)
        nom = getattr(self.entreprise, 'nom_entreprise', self.entreprise)
        logger.warning(f"[{nom}] {message}")
    
    def enregistrer_audit(self, action, module, type_objet, id_objet, details=None):
        """
        Enregistre une action en piste d'audit.
        
        Args:
            action: Type d'action (create, update, delete, validation)
            module: Module concerné (ex: 'Rapprochements bancaires')
            type_objet: Type d'objet (ex: 'RapprochementBancaire')
            id_objet: ID de l'objet
            details: Détails optionnels
        """
        from ..models import PisteAudit
        import json
        
        try:
            PisteAudit.objects.create(
                entreprise=self.entreprise,
                utilisateur=self.utilisateur,
                action=action,
                module=module,
                type_objet=type_objet,
                id_objet=str(id_objet),
                donnees_nouvelles=json.dumps(details or {})
            )
        except Exception as e:
            logger.error(f"Erreur audit: {e}")
    
    @transaction.atomic
    def executer_avec_transaction(self, fonction, *args, **kwargs):
        """
        Exécute une fonction dans une transaction atomique.
        
        Args:
            fonction: Fonction à exécuter
            *args, **kwargs: Arguments de la fonction
        
        Returns:
            Résultat de la fonction
        """
        try:
            resultat = fonction(*args, **kwargs)
            logger.info(f"Transaction réussie: {fonction.__name__}")
            return resultat
        except Exception as e:
            logger.error(f"Erreur transaction: {e}")
            raise
    
    def valider_montants(self, montants_debit, montants_credit):
        """
        Valide que débits et crédits sont équilibrés.
        
        Args:
            montants_debit: Decimal - Somme des débits
            montants_credit: Decimal - Somme des crédits
        
        Raises:
            ValidationError si déséquilibré
        """
        if abs(montants_debit - montants_credit) > Decimal('0.01'):
            raise ValidationError(
                f"Déséquilibre: Débit={montants_debit} vs Crédit={montants_credit}"
            )
    
    def valider_exercice(self, exercice):
        """
        Valide qu'un exercice est valide et non verrouillé.
        
        Args:
            exercice: Instance de ExerciceComptable
        
        Raises:
            ValidationError si invalide
        """
        if exercice.statut != 'ouvert':
            raise ValidationError(f"Exercice {exercice.libelle} est clôturé")
        
        from ..models import VerrouillageExercice
        verrouillage = VerrouillageExercice.objects.filter(exercice=exercice).first()
        if verrouillage and verrouillage.est_verroui:
            raise ValidationError(f"Exercice {exercice.libelle} est verrouillé")
    
    def nettoyer(self):
        """Nettoie les ressources (optionnel)."""
        self.errors = []
        self.warnings = []
