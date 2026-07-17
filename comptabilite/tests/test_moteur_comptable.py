# -*- coding: utf-8 -*-
"""
Suite de tests du moteur comptable SYSCOHADA et du workflow de validation.
Exécution : python manage.py test comptabilite.tests.test_moteur_comptable
Chaque test tourne dans une base de test isolée et jetable.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.core.exceptions import ValidationError

from core.models import (Entreprise, Utilisateur, AccesEntreprise,
                         PermissionRole, Delegation)
from comptabilite.models import (
    Tiers, Facture, LigneFacture, Reglement, EcritureComptable, ExerciceComptable,
    Immobilisation, Amortissement, PlanComptable,
    PieceCaisse, RegleEcriture, RegleValidation, DemandeApprobation,
    CompteBancaire, ReleveBancaire, OperationBancaire, RapprochementBancaire,
)
from comptabilite.moteur_comptable import (
    operation_simple, comptabiliser_facture, comptabiliser_reglement,
    comptabiliser_piece_caisse, obtenir_compte_auxiliaire, obtenir_compte,
    generer_ecriture, ErreurComptabilisation, ZERO,
)
from comptabilite.services.rapprochement_service import RapprochementService


class BaseMoteurTest(TestCase):
    """Jeu de données commun : entreprise, utilisateur, tiers."""

    def setUp(self):
        self.e = Entreprise.objects.create(
            nom_entreprise='Test SARL', slug='test-sarl',
            email='test@sarl.gn', type_module='both')
        self.u = Utilisateur.objects.create_user(
            username='comptable', password='x', email='c@t.gn',
            entreprise=self.e, actif=True)
        self.client_t = Tiers.objects.create(
            entreprise=self.e, code='C001', raison_sociale='Client Alpha',
            type_tiers='client')
        self.frs_t = Tiers.objects.create(
            entreprise=self.e, code='F001', raison_sociale='Fournisseur Beta',
            type_tiers='fournisseur')

    def assert_equilibree(self, ecriture):
        debit = sum((l.montant_debit for l in ecriture.lignes.all()), ZERO)
        credit = sum((l.montant_credit for l in ecriture.lignes.all()), ZERO)
        self.assertEqual(debit, credit, 'écriture déséquilibrée')
        self.assertGreater(debit, 0)

    def comptes(self, ecriture):
        return sorted(l.compte.numero_compte for l in ecriture.lignes.all())


class TestOperationsMetier(BaseMoteurTest):
    """Ventes, achats, avoirs, encaissements, caisse, banque, salaires."""

    def test_vente_ht_sans_tva(self):
        ec = operation_simple(self.e, self.u, 'vente', date(2026, 3, 1),
                              'Vente sans TVA', Decimal('1000000'), Decimal('0'),
                              tiers=self.client_t)
        self.assert_equilibree(ec)
        self.assertEqual(ec.journal.type_journal, 'VT')
        self.assertTrue(ec.est_validee)
        # Client (auxiliaire) au débit TTC, ventes au crédit — pas de ligne TVA
        self.assertEqual(len(self.comptes(ec)), 2)
        self.assertIn('7011', self.comptes(ec))

    def test_vente_ttc_avec_tva(self):
        ec = operation_simple(self.e, self.u, 'vente', date(2026, 3, 1),
                              'Vente avec TVA', Decimal('1000000'), Decimal('18'),
                              tiers=self.client_t)
        self.assert_equilibree(ec)
        self.assertIn('4431', self.comptes(ec))   # TVA collectée
        ligne_client = ec.lignes.exclude(montant_debit=0).first()
        self.assertEqual(ligne_client.montant_debit, Decimal('1180000'))

    def test_achat_avec_tva(self):
        ec = operation_simple(self.e, self.u, 'achat', date(2026, 3, 2),
                              'Achat marchandises', Decimal('500000'), Decimal('18'),
                              tiers=self.frs_t)
        self.assert_equilibree(ec)
        self.assertEqual(ec.journal.type_journal, 'AC')
        self.assertIn('6011', self.comptes(ec))
        self.assertIn('4452', self.comptes(ec))   # TVA récupérable

    def test_avoir_client_inverse_la_vente(self):
        ec = operation_simple(self.e, self.u, 'avoir_client', date(2026, 3, 3),
                              'Avoir client', Decimal('200000'), Decimal('18'),
                              tiers=self.client_t)
        self.assert_equilibree(ec)
        # ventes au débit (annulation), client au crédit
        ligne_ventes = ec.lignes.get(compte__numero_compte='7011')
        self.assertGreater(ligne_ventes.montant_debit, 0)

    def test_encaissement_banque_et_caisse(self):
        ec_bq = operation_simple(self.e, self.u, 'encaissement_client', date(2026, 3, 4),
                                 'Encaissement virement', Decimal('300000'),
                                 tiers=self.client_t, mode_paiement='banque')
        self.assertEqual(ec_bq.journal.type_journal, 'BQ')
        self.assertIn('5211', self.comptes(ec_bq))
        ec_ca = operation_simple(self.e, self.u, 'encaissement_client', date(2026, 3, 5),
                                 'Encaissement espèces', Decimal('100000'),
                                 tiers=self.client_t, mode_paiement='especes')
        self.assertEqual(ec_ca.journal.type_journal, 'CA')
        self.assertIn('5711', self.comptes(ec_ca))

    def test_salaire(self):
        ec = operation_simple(self.e, self.u, 'salaire', date(2026, 3, 31),
                              'Salaires mars', Decimal('5000000'))
        self.assert_equilibree(ec)
        self.assertIn('6611', self.comptes(ec))


class TestDocuments(BaseMoteurTest):
    """Comptabilisation automatique des factures, règlements, pièces de caisse."""

    def _facture(self, type_facture='vente', ttc='1180000', ht='1000000', tva='180000'):
        tiers = self.client_t if type_facture in ('vente', 'avoir_client', 'acompte') else self.frs_t
        return Facture.objects.create(
            entreprise=self.e, numero=f'F-{type_facture}-1', type_facture=type_facture,
            tiers=tiers, date_facture=date(2026, 4, 1),
            montant_ht=Decimal(ht), montant_tva=Decimal(tva), montant_ttc=Decimal(ttc),
            statut='validee')

    def test_facture_vente(self):
        f = self._facture('vente')
        ec = comptabiliser_facture(f, self.u)
        self.assert_equilibree(ec)
        f.refresh_from_db()
        self.assertEqual(f.ecriture_id, ec.pk)
        # Idempotent : re-comptabiliser renvoie la même écriture
        self.assertEqual(comptabiliser_facture(f, self.u).pk, ec.pk)

    def test_facture_achat(self):
        ec = comptabiliser_facture(self._facture('achat'), self.u)
        self.assert_equilibree(ec)
        self.assertEqual(ec.journal.type_journal, 'AC')

    def test_lignes_recalculent_et_arrondissent_totaux_facture(self):
        facture = self._facture('vente', ttc='0', ht='0', tva='0')
        ligne1 = LigneFacture.objects.create(
            facture=facture, designation='Article A', quantite=Decimal('2.50'),
            prix_unitaire=Decimal('100.005'), taux_tva=Decimal('18'))
        LigneFacture.objects.create(
            facture=facture, designation='Article B', quantite=Decimal('1'),
            prix_unitaire=Decimal('50.00'), taux_tva=Decimal('0'))
        facture.refresh_from_db()
        self.assertEqual(ligne1.montant_ht, Decimal('250.01'))
        self.assertEqual(ligne1.montant_tva, Decimal('45.00'))
        self.assertEqual(facture.montant_ht, Decimal('300.01'))
        self.assertEqual(facture.montant_tva, Decimal('45.00'))
        self.assertEqual(facture.montant_ttc, Decimal('345.01'))

        ligne1.delete()
        facture.refresh_from_db()
        self.assertEqual(facture.montant_ttc, Decimal('50.00'))

    def test_reglement_client_et_fournisseur(self):
        f = self._facture('vente')
        r = Reglement.objects.create(
            entreprise=self.e, numero='R-1', facture=f, date_reglement=date(2026, 4, 10),
            montant=Decimal('1180000'), mode_paiement='virement')
        ec = comptabiliser_reglement(r, self.u)
        self.assert_equilibree(ec)
        self.assertIn('5211', self.comptes(ec))
        fa = self._facture('achat')
        ra = Reglement.objects.create(
            entreprise=self.e, numero='R-2', facture=fa, date_reglement=date(2026, 4, 11),
            montant=Decimal('1180000'), mode_paiement='especes')
        ec2 = comptabiliser_reglement(ra, self.u)
        self.assertIn('5711', self.comptes(ec2))   # espèces → caisse

    def test_remboursement_avoir_fournisseur_utilise_compte_fournisseur(self):
        facture = self._facture('avoir_fournisseur')
        reglement = Reglement.objects.create(
            entreprise=self.e, numero='R-AF', facture=facture,
            date_reglement=date(2026, 4, 12), montant=Decimal('1180000'),
            mode_paiement='virement')
        ecriture = comptabiliser_reglement(reglement, self.u)
        self.assert_equilibree(ecriture)
        ligne_tiers = ecriture.lignes.get(compte__numero_compte__startswith='401')
        self.assertEqual(ligne_tiers.montant_credit, Decimal('1180000'))
        self.assertFalse(ecriture.lignes.filter(compte__numero_compte__startswith='411').exists())

    def test_remboursement_avoir_client_utilise_compte_client(self):
        facture = self._facture('avoir_client')
        reglement = Reglement.objects.create(
            entreprise=self.e, numero='R-AC', facture=facture,
            date_reglement=date(2026, 4, 13), montant=Decimal('1180000'),
            mode_paiement='virement')
        ecriture = comptabiliser_reglement(reglement, self.u)
        self.assert_equilibree(ecriture)
        ligne_tiers = ecriture.lignes.get(compte__numero_compte__startswith='411')
        self.assertEqual(ligne_tiers.montant_debit, Decimal('1180000'))
        self.assertFalse(ecriture.lignes.filter(compte__numero_compte__startswith='401').exists())

    def test_piece_caisse(self):
        p = PieceCaisse.objects.create(
            entreprise=self.e, numero='PCS-1', type_piece='sortie',
            date_operation=date(2026, 4, 12), libelle='Achat fournitures',
            montant=Decimal('50000'))
        ec = comptabiliser_piece_caisse(p, self.u)
        self.assert_equilibree(ec)
        self.assertEqual(ec.journal.type_journal, 'CA')


class TestControles(BaseMoteurTest):
    """Contrôles du moteur : équilibre, doublons, exercice clôturé."""

    def test_solde_rapprochement_inclut_ouverture_et_exclut_brouillon(self):
        banque = obtenir_compte(self.e, 'banque')
        contrepartie = obtenir_compte(self.e, 'produits_divers')
        compte_bancaire = CompteBancaire.objects.create(
            entreprise=self.e, code='BQ-TEST', libelle='Banque test',
            banque='Banque test', solde_initial=Decimal('1000'),
            compte_comptable=banque)
        validee = generer_ecriture(
            self.e, self.u, 'BQ', date(2026, 4, 1), 'Mouvement valide',
            [(banque, 'Mouvement valide', Decimal('100'), ZERO),
             (contrepartie, 'Mouvement valide', ZERO, Decimal('100'))])
        brouillon = generer_ecriture(
            self.e, self.u, 'BQ', date(2026, 4, 2), 'Mouvement brouillon',
            [(banque, 'Mouvement brouillon', Decimal('900'), ZERO),
             (contrepartie, 'Mouvement brouillon', ZERO, Decimal('900'))])
        brouillon.est_validee = False
        brouillon.save(update_fields=['est_validee'])

        solde = RapprochementService(self.e, self.u).calculer_solde_comptable(
            compte_bancaire, date(2026, 4, 30))
        self.assertEqual(solde, Decimal('1100'))

    def test_rapprochement_desequilibre_refuse_meme_sans_ecart_enregistre(self):
        banque = obtenir_compte(self.e, 'banque')
        compte_bancaire = CompteBancaire.objects.create(
            entreprise=self.e, code='BQ-ECART', libelle='Banque ecart',
            banque='Banque test', solde_initial=Decimal('100'),
            compte_comptable=banque)
        rapprochement = RapprochementBancaire.objects.create(
            compte_bancaire=compte_bancaire,
            date_rapprochement=date(2026, 4, 30),
            solde_bancaire=Decimal('0'), solde_comptable=Decimal('100'),
            ecart=Decimal('100'), responsable=self.u)

        with self.assertRaises(ValidationError):
            RapprochementService(self.e, self.u).valider_rapprochement(
                rapprochement)

    def test_lettrage_compare_uniquement_la_ligne_bancaire(self):
        banque = obtenir_compte(self.e, 'banque')
        charge = obtenir_compte(self.e, 'achats')
        contrepartie = obtenir_compte(self.e, 'fournisseurs')
        compte_bancaire = CompteBancaire.objects.create(
            entreprise=self.e, code='BQ-LET', libelle='Banque lettrage',
            banque='Banque test', compte_comptable=banque)
        ecriture = generer_ecriture(
            self.e, self.u, 'BQ', date(2026, 4, 15), 'Paiement compose',
            [(banque, 'Banque', Decimal('100'), ZERO),
             (charge, 'Frais', Decimal('50'), ZERO),
             (contrepartie, 'Contrepartie', ZERO, Decimal('150'))])
        releve = ReleveBancaire.objects.create(
            compte_bancaire=compte_bancaire, numero='REL-LET',
            date_debut=date(2026, 4, 1), date_fin=date(2026, 4, 30),
            solde_initial=ZERO, solde_final=Decimal('100'))
        operation = OperationBancaire.objects.create(
            releve=releve, date_operation=date(2026, 4, 15),
            description='Paiement compose', montant=Decimal('100'),
            type_operation='credit')

        lettrage = RapprochementService(self.e, self.u).lettrer_operation(
            operation, ecriture)
        self.assertEqual(lettrage.ecriture, ecriture)

    def test_refus_ecriture_desequilibree(self):
        c1 = obtenir_compte(self.e, 'caisse')
        c2 = obtenir_compte(self.e, 'ventes')
        with self.assertRaises(ErreurComptabilisation):
            generer_ecriture(self.e, self.u, 'OD', date(2026, 5, 1), 'Déséquilibre',
                             [(c1, '', Decimal('100'), ZERO), (c2, '', ZERO, Decimal('99'))])

    def test_refus_doublon(self):
        operation_simple(self.e, self.u, 'vente', date(2026, 5, 2), 'Vente unique',
                         Decimal('100000'), tiers=self.client_t)
        with self.assertRaises(ErreurComptabilisation):
            operation_simple(self.e, self.u, 'vente', date(2026, 5, 2), 'Vente unique',
                             Decimal('100000'), tiers=self.client_t)

    def test_refus_exercice_cloture(self):
        ExerciceComptable.objects.create(
            entreprise=self.e, libelle='Exercice 2020', statut='cloture',
            date_debut=date(2020, 1, 1), date_fin=date(2020, 12, 31))
        with self.assertRaises(ErreurComptabilisation):
            operation_simple(self.e, self.u, 'vente', date(2020, 6, 1), 'Vente 2020',
                             Decimal('100000'), tiers=self.client_t)

    def test_compte_auxiliaire_auto(self):
        compte = obtenir_compte_auxiliaire(self.e, self.client_t, 'clients')
        self.assertTrue(compte.numero_compte.startswith('411'))
        self.client_t.refresh_from_db()
        self.assertEqual(self.client_t.compte_comptable_id, compte.pk)
        # Le second tiers reçoit un numéro différent
        compte2 = obtenir_compte_auxiliaire(self.e, self.frs_t, 'fournisseurs')
        self.assertTrue(compte2.numero_compte.startswith('401'))

    def test_regle_en_base_prime_sur_schema(self):
        RegleEcriture.objects.create(operation='vente', ordre=1, sens='debit',
                                     role_compte='tiers', base_montant='ttc')
        RegleEcriture.objects.create(operation='vente', ordre=2, sens='credit',
                                     role_compte='fixe', compte_numero='7061',
                                     compte_intitule='Services vendus', base_montant='ht')
        RegleEcriture.objects.create(operation='vente', ordre=3, sens='credit',
                                     role_compte='fixe', compte_numero='4431',
                                     base_montant='tva')
        ec = operation_simple(self.e, self.u, 'vente', date(2026, 5, 3), 'Vente services',
                              Decimal('100000'), Decimal('18'), tiers=self.client_t)
        self.assertIn('7061', self.comptes(ec))
        self.assertNotIn('7011', self.comptes(ec))


class TestAmortissementsEtCloture(BaseMoteurTest):
    """Dotations automatiques et clôture/réouverture d'exercice."""

    def setUp(self):
        super().setUp()
        self.exercice = ExerciceComptable.objects.create(
            entreprise=self.e, libelle='Exercice 2026', statut='ouvert',
            date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31))

    def test_dotation_lineaire(self):
        from comptabilite.views_livres import _dotations_a_generer
        Immobilisation.objects.create(
            entreprise=self.e, numero='IM-1', designation='Véhicule',
            categorie='vehicule', date_acquisition=date(2026, 1, 10),
            valeur_acquisition=Decimal('50000000'), duree_vie_ans=5)
        propositions = _dotations_a_generer(self.e, self.exercice)
        self.assertEqual(len(propositions), 1)
        self.assertEqual(propositions[0]['dotation'], Decimal('10000000'))

    def test_dotation_plafonnee_a_la_vnc(self):
        from comptabilite.views_livres import _dotations_a_generer
        immo = Immobilisation.objects.create(
            entreprise=self.e, numero='IM-2', designation='PC',
            categorie='informatique', date_acquisition=date(2022, 1, 1),
            valeur_acquisition=Decimal('3000000'), duree_vie_ans=3)
        ex_ancien = ExerciceComptable.objects.create(
            entreprise=self.e, libelle='Exercice 2025', statut='cloture',
            date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        Amortissement.objects.create(immobilisation=immo, exercice=ex_ancien,
                                     taux_amortissement=Decimal('33.33'),
                                     montant_amortissement=Decimal('2500000'),
                                     montant_cumule=Decimal('2500000'))
        propositions = _dotations_a_generer(self.e, self.exercice)
        self.assertEqual(propositions[0]['dotation'], Decimal('500000'))  # VNC restante

    def test_cloture_exercice_resultat_et_a_nouveaux(self):
        operation_simple(self.e, self.u, 'vente', date(2026, 6, 1), 'Vente',
                         Decimal('1000000'), tiers=self.client_t)
        operation_simple(self.e, self.u, 'sortie_caisse', date(2026, 7, 1),
                         'Charges diverses', Decimal('300000'))
        from comptabilite.views_livres import _resultat_exercice, _controles_pre_cloture
        produits, charges, resultat = _resultat_exercice(self.e, self.exercice)
        self.assertEqual(resultat, Decimal('700000'))
        controles = _controles_pre_cloture(self.e, self.exercice)
        self.assertTrue(all(c['ok'] for c in controles if c['bloquant']))


class TestWorkflowValidation(BaseMoteurTest):
    """Validation simple, multiple, permissions par rôle, délégation."""

    def setUp(self):
        super().setUp()
        PermissionRole.initialiser_defauts()
        self.regle = RegleValidation.objects.create(
            entreprise=self.e, type_document='facture',
            seuil_montant=Decimal('5000000'), nb_approbations=1, niveau_acces_min=4)
        self.daf = Utilisateur.objects.create_user(
            username='daf', password='x', email='daf@t.gn', entreprise=self.e, actif=True)
        AccesEntreprise.objects.create(utilisateur=self.daf, entreprise=self.e, role='daf')

    def _demande(self, montant='10000000'):
        f = Facture.objects.create(
            entreprise=self.e, numero='F-GROSSE', type_facture='vente',
            tiers=self.client_t, date_facture=date(2026, 8, 1),
            montant_ht=Decimal(montant), montant_tva=ZERO, montant_ttc=Decimal(montant),
            statut='brouillon')
        return f, DemandeApprobation.objects.create(
            entreprise=self.e, regle=self.regle, type_document='facture',
            objet_id=str(f.pk), libelle=f'Facture {f.numero}',
            montant=f.montant_ttc, demandeur=self.u)

    def test_regle_applicable_selon_seuil(self):
        self.assertIsNotNone(RegleValidation.regle_applicable(
            self.e, 'facture', Decimal('10000000')))
        self.assertIsNone(RegleValidation.regle_applicable(
            self.e, 'facture', Decimal('1000000')))

    def test_permission_par_role(self):
        self.assertTrue(self.daf.has_permission('facture.approuver', self.e))
        self.assertFalse(self.u.has_permission('facture.approuver', self.e))
        # Auditeur : lecture seule
        auditeur = Utilisateur.objects.create_user(
            username='audit', password='x', email='a@t.gn', entreprise=self.e, actif=True)
        AccesEntreprise.objects.create(utilisateur=auditeur, entreprise=self.e, role='auditeur')
        self.assertTrue(auditeur.has_permission('lecture.etats', self.e))
        self.assertFalse(auditeur.has_permission('facture.approuver', self.e))

    def test_acces_expire_ne_donne_plus_le_role(self):
        acces = self.daf.acces_entreprises.get(entreprise=self.e)
        acces.date_fin = date(2020, 1, 1)
        acces.save()
        self.assertFalse(self.daf.has_permission('facture.approuver', self.e))

    def test_delegation_active_transmet_la_permission(self):
        from django.utils import timezone
        aujourd_hui = timezone.now().date()
        self.assertFalse(self.u.has_permission('facture.approuver', self.e))
        Delegation.objects.create(
            delegant=self.daf, delegataire=self.u, entreprise=self.e,
            date_debut=aujourd_hui, date_fin=aujourd_hui, motif='Congé')
        self.assertTrue(self.u.has_permission('facture.approuver', self.e))

    def test_delegation_expiree_sans_effet(self):
        Delegation.objects.create(
            delegant=self.daf, delegataire=self.u, entreprise=self.e,
            date_debut=date(2020, 1, 1), date_fin=date(2020, 1, 15), motif='Ancien congé')
        self.assertFalse(self.u.has_permission('facture.approuver', self.e))

    def test_validation_multiple_quorum(self):
        self.regle.nb_approbations = 2
        self.regle.save()
        f, demande = self._demande()
        from comptabilite.models import DecisionApprobation
        DecisionApprobation.objects.create(demande=demande, approbateur=self.daf,
                                           decision='approuve')
        self.assertEqual(demande.nb_approbations_recues, 1)
        self.assertLess(demande.nb_approbations_recues, demande.nb_approbations_requises)
        dg = Utilisateur.objects.create_user(
            username='dg', password='x', email='dg@t.gn', entreprise=self.e, actif=True)
        DecisionApprobation.objects.create(demande=demande, approbateur=dg,
                                           decision='approuve')
        self.assertEqual(demande.nb_approbations_recues, demande.nb_approbations_requises)


class TestMultiSocietes(TestCase):
    """Suppression d'entreprise sans perte d'utilisateur, cloisonnement."""

    def test_suppression_entreprise_conserve_les_utilisateurs(self):
        e = Entreprise.objects.create(nom_entreprise='Éphémère', slug='ephemere',
                                      email='e@t.gn', type_module='both')
        u = Utilisateur.objects.create_user(username='rescape', password='x',
                                            email='r@t.gn', entreprise=e, actif=True)
        e.delete()
        u.refresh_from_db()          # ne doit PAS lever Utilisateur.DoesNotExist
        self.assertIsNone(u.entreprise)

    def test_cloisonnement_des_ecritures_par_entreprise(self):
        eA = Entreprise.objects.create(nom_entreprise='A', slug='soc-a',
                                       email='a@t.gn', type_module='both')
        eB = Entreprise.objects.create(nom_entreprise='B', slug='soc-b',
                                       email='b@t.gn', type_module='both')
        u = Utilisateur.objects.create_user(username='multi', password='x',
                                            email='m@t.gn', entreprise=eA, actif=True)
        operation_simple(eA, u, 'entree_caisse', date(2026, 9, 1), 'Apport A',
                         Decimal('100000'))
        operation_simple(eB, u, 'entree_caisse', date(2026, 9, 1), 'Apport B',
                         Decimal('200000'))
        self.assertEqual(EcritureComptable.objects.filter(entreprise=eA).count(), 1)
        self.assertEqual(EcritureComptable.objects.filter(entreprise=eB).count(), 1)
        # Plans comptables distincts : le compte caisse existe dans chaque société
        self.assertTrue(PlanComptable.objects.filter(entreprise=eA, numero_compte='5711').exists())
        self.assertTrue(PlanComptable.objects.filter(entreprise=eB, numero_compte='5711').exists())
