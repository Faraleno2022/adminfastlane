"""
Signaux Django pour le module comptabilité.

Gère:
- Création de données par défaut
- Notifications
- Audit automatique
"""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='comptabilite.ExerciceComptable')
def on_exercice_created(sender, instance, created, **kwargs):
    """Crée les journaux SYSCOHADA par défaut pour un nouvel exercice."""
    if created:
        try:
            from .moteur_comptable import obtenir_journal, JOURNAUX_DEFAUT
            for type_journal in JOURNAUX_DEFAUT:
                obtenir_journal(instance.entreprise, type_journal)
            logger.info(f"Journaux SYSCOHADA vérifiés pour l'exercice {instance.libelle}")
        except Exception as e:
            logger.error(f"Erreur création journaux: {e}")


@receiver(post_save, sender='comptabilite.RapprochementBancaire')
def on_rapprochement_finalized(sender, instance, created, **kwargs):
    """Exécute les actions quand un rapprochement est finalisé."""
    if instance.statut == 'FINALIZE':
        try:
            from .models import PisteAudit
            
            # Crée une entrée d'audit
            PisteAudit.objects.create(
                entreprise=instance.entreprise,
                utilisateur=None,  # À adapter
                action='FINALIZE',
                module='RAPPROCHEMENT_BANCAIRE',
                type_objet='RapprochementBancaire',
                id_objet=str(instance.id),
                donnees_nouvelles=f"Solde comptable: {instance.solde_comptable}, "
                                  f"Solde bancaire: {instance.solde_bancaire}"
            )
            
            logger.info(f"Rapprochement {instance.id} finalisé")
        except Exception as e:
            logger.error(f"Erreur finalisation rapprochement: {e}")


@receiver(pre_delete, sender='comptabilite.CompteBancaire')
def on_compte_deleted(sender, instance, **kwargs):
    """Empêche la suppression d'un compte avec mouvements."""
    from .models import OperationBancaire
    
    if OperationBancaire.objects.filter(compte_bancaire=instance).exists():
        raise ValueError(
            _("Impossible de supprimer un compte bancaire ayant des opérations")
        )
