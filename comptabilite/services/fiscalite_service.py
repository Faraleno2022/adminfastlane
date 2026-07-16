"""
Service de gestion des déclarations TVA et fiscalité
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
from django.db import transaction
from django.contrib.auth.models import User

from comptabilite.models import (
    RegimeTVA, TauxTVA, DeclarationTVA, LigneDeclarationTVA,
    EcritureComptable, PlanComptable
)
from core.models import Entreprise
from .base_service import BaseComptaService


class FiscaliteService(BaseComptaService):
    """
    Service métier pour la gestion des déclarations TVA
    - Création de déclarations
    - Calcul des montants
    - Validation et dépôt
    - Gestion des régimes TVA
    """
    
    def __init__(self, utilisateur: User):
        super().__init__(utilisateur)
        self.service_name = 'FiscaliteService'
    
    @transaction.atomic
    def creer_declaration_tva(self, entreprise: Entreprise, regime_tva: RegimeTVA,
                              periode_debut: date, periode_fin: date, exercice=None):
        """
        Crée une nouvelle déclaration TVA
        
        Args:
            entreprise: L'entreprise
            regime_tva: Le régime TVA applicable
            periode_debut: Date de début de période
            periode_fin: Date de fin de période
            exercice: Exercice fiscal (optionnel)
        
        Returns:
            (DeclarationTVA, errors_list)
        """
        try:
            # Validation
            conditions = {
                'entreprise_exists': bool(entreprise),
                'regime_exists': bool(regime_tva),
                'dates_valid': periode_debut < periode_fin,
                'regime_actif': regime_tva.actif,
                'pas_declaration_doublon': not DeclarationTVA.objects.filter(
                    entreprise=entreprise,
                    periode_debut=periode_debut,
                    periode_fin=periode_fin
                ).exists()
            }
            
            self.valider(conditions)
            
            if self.erreurs:
                return None, self.erreurs
            
            # Création
            declaration = DeclarationTVA.objects.create(
                entreprise=entreprise,
                regime_tva=regime_tva,
                exercice=exercice,
                periode_debut=periode_debut,
                periode_fin=periode_fin,
                statut='BROUILLON',
                utilisateur_creation=self.utilisateur,
                utilisateur_modification=self.utilisateur
            )
            
            # Audit
            self.enregistrer_audit(
                action='CREATE',
                module='FISCALITE',
                type_objet='DeclarationTVA',
                id_objet=str(declaration.id),
                details={
                    'regime': regime_tva.nom,
                    'periode': f"{periode_debut} à {periode_fin}"
                }
            )
            
            return declaration, []
            
        except Exception as e:
            self.avertissement(f"Erreur création déclaration: {str(e)}")
            return None, self.erreurs
    
    @transaction.atomic
    def ajouter_ligne_declaration(self, declaration: DeclarationTVA, description: str,
                                 taux_tva: TauxTVA, montant_ht: Decimal,
                                 ecriture: EcritureComptable = None):
        """
        Ajoute une ligne à la déclaration TVA
        
        Args:
            declaration: La déclaration TVA
            description: Description de la ligne
            taux_tva: Le taux TVA à appliquer
            montant_ht: Montant HT
            ecriture: Écriture comptable source (optionnel)
        
        Returns:
            (LigneDeclarationTVA, errors_list)
        """
        try:
            # Validation
            conditions = {
                'declaration_exists': bool(declaration),
                'taux_exists': bool(taux_tva),
                'montant_positif': montant_ht > 0,
                'taux_actif': taux_tva.actif,
                'declaration_non_deposee': declaration.statut in ['BROUILLON', 'EN_COURS']
            }
            
            self.valider(conditions)
            
            if self.erreurs:
                return None, self.erreurs
            
            # Calcul TVA
            montant_tva = (montant_ht * (taux_tva.taux / 100)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # Déterminer numéro de ligne
            derniere_ligne = declaration.lignes.order_by('-numero_ligne').first()
            numero_ligne = (derniere_ligne.numero_ligne + 1) if derniere_ligne else 1
            
            # Création
            ligne = LigneDeclarationTVA.objects.create(
                declaration=declaration,
                numero_ligne=numero_ligne,
                description=description,
                taux=taux_tva,
                montant_ht=montant_ht,
                montant_tva=montant_tva,
                ecriture_comptable=ecriture
            )
            
            # Audit
            self.enregistrer_audit(
                action='CREATE',
                module='FISCALITE',
                type_objet='LigneDeclarationTVA',
                id_objet=str(ligne.id),
                details={
                    'declaration_id': str(declaration.id),
                    'montant_ht': str(montant_ht),
                    'montant_tva': str(montant_tva)
                }
            )
            
            return ligne, []
            
        except Exception as e:
            self.avertissement(f"Erreur ajout ligne: {str(e)}")
            return None, self.erreurs
    
    def calculer_montants_declaration(self, declaration: DeclarationTVA):
        """
        Calcule les montants totaux de la déclaration
        
        Args:
            declaration: La déclaration TVA
        
        Returns:
            dict avec les totaux
        """
        try:
            lignes = declaration.lignes.all()
            
            montant_ht_total = sum(Decimal(l.montant_ht) for l in lignes) or Decimal('0.00')
            # Distinction TVA collectée vs déductible
            montant_tva_collecte = Decimal('0.00')
            montant_tva_deductible = Decimal('0.00')
            
            for ligne in lignes:
                if ligne.sens == 'DEDUCTIBLE':
                    montant_tva_deductible += ligne.montant_tva
                else:
                    montant_tva_collecte += ligne.montant_tva
            
            montant_tva_due = montant_tva_collecte - montant_tva_deductible
            
            return {
                'montant_ht': montant_ht_total,
                'montant_tva_collecte': montant_tva_collecte,
                'montant_tva_deductible': montant_tva_deductible,
                'montant_tva_due': montant_tva_due,
                'montant_a_payer': max(montant_tva_due, Decimal('0.00'))
            }
            
        except Exception as e:
            self.avertissement(f"Erreur calcul montants: {str(e)}")
            return {}
    
    @transaction.atomic
    def valider_declaration(self, declaration: DeclarationTVA):
        """
        Valide une déclaration TVA
        
        Args:
            declaration: La déclaration TVA
        
        Returns:
            (success: bool, errors_list)
        """
        try:
            # Validation
            conditions = {
                'declaration_exists': bool(declaration),
                'declaration_brouillon': declaration.statut == 'BROUILLON',
                'au_moins_une_ligne': declaration.lignes.exists(),
                'montants_positifs': all(
                    l.montant_ht > 0 and l.montant_tva >= 0
                    for l in declaration.lignes.all()
                )
            }
            
            self.valider(conditions)
            
            if self.erreurs:
                return False, self.erreurs
            
            # Calcul des montants
            montants = self.calculer_montants_declaration(declaration)
            
            # Mise à jour
            declaration.montant_ht = montants.get('montant_ht', Decimal('0.00'))
            declaration.montant_tva_collecte = montants.get('montant_tva_collecte', Decimal('0.00'))
            declaration.montant_tva_deductible = montants.get('montant_tva_deductible', Decimal('0.00'))
            declaration.montant_tva_due = montants.get('montant_tva_due', Decimal('0.00'))
            declaration.statut = 'VALIDEE'
            declaration.utilisateur_modification = self.utilisateur
            declaration.save()
            
            # Audit
            self.enregistrer_audit(
                action='UPDATE',
                module='FISCALITE',
                type_objet='DeclarationTVA',
                id_objet=str(declaration.id),
                details={'statut': 'VALIDEE'}
            )
            
            return True, []
            
        except Exception as e:
            self.avertissement(f"Erreur validation: {str(e)}")
            return False, self.erreurs
    
    @transaction.atomic
    def deposer_declaration(self, declaration: DeclarationTVA, numero_depot: str = None):
        """
        Dépose une déclaration TVA
        
        Args:
            declaration: La déclaration TVA validée
            numero_depot: Numéro de dépôt (optionnel)
        
        Returns:
            (success: bool, errors_list)
        """
        try:
            # Validation
            conditions = {
                'declaration_exists': bool(declaration),
                'declaration_validee': declaration.statut == 'VALIDEE',
                'pas_doublon_numero': not numero_depot or not DeclarationTVA.objects.filter(
                    numero_depot=numero_depot
                ).exclude(id=declaration.id).exists()
            }
            
            self.valider(conditions)
            
            if self.erreurs:
                return False, self.erreurs
            
            # Dépôt
            declaration.statut = 'DEPOSEE'
            declaration.date_depot = date.today()
            if numero_depot:
                declaration.numero_depot = numero_depot
            declaration.utilisateur_modification = self.utilisateur
            declaration.save()
            
            # Audit
            self.enregistrer_audit(
                action='UPDATE',
                module='FISCALITE',
                type_objet='DeclarationTVA',
                id_objet=str(declaration.id),
                details={
                    'statut': 'DEPOSEE',
                    'date_depot': str(date.today()),
                    'numero_depot': numero_depot or 'AUTO'
                }
            )
            
            return True, []
            
        except Exception as e:
            self.avertissement(f"Erreur dépôt: {str(e)}")
            return False, self.erreurs
    
    def lister_declarations_periode(self, entreprise: Entreprise, 
                                   date_debut: date, date_fin: date):
        """
        Liste les déclarations pour une période
        
        Args:
            entreprise: L'entreprise
            date_debut: Date de début
            date_fin: Date de fin
        
        Returns:
            QuerySet de DeclarationTVA
        """
        return DeclarationTVA.objects.filter(
            entreprise=entreprise,
            periode_debut__gte=date_debut,
            periode_fin__lte=date_fin
        ).order_by('-periode_debut')
    
    def obtenir_montant_a_payer(self, declaration: DeclarationTVA) -> Decimal:
        """
        Calcule le montant TVA à payer ou récupérer
        
        Args:
            declaration: La déclaration TVA
        
        Returns:
            Montant (positif = à payer, négatif = à récupérer)
        """
        return declaration.montant_tva_collecte - declaration.montant_tva_deductible
