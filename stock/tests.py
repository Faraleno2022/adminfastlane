"""
Tests du workflow d'approvisionnement : expression de besoin → validation →
génération automatique du bon de commande (achats) / du devis (ventes).
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import Entreprise, Utilisateur, Service
from .models import (
    Fournisseur, Client, CategorieArticle, Article,
    CommandeFournisseur, LigneCommande,
    BesoinAchat, LigneBesoinAchat,
    DocumentVente, LigneVente,
    DemandeVente, LigneDemandeVente,
    ProfilStock,
)


class BesoinAchatWorkflowTest(TestCase):
    """N'importe quel employé exprime un besoin ; un responsable_achat le
    valide ; le réapprovisionnement génère automatiquement le bon de commande."""

    def setUp(self):
        self.entreprise = Entreprise.objects.create(nom_entreprise='ACME Guinée')
        self.demandeur = Utilisateur.objects.create_user(
            username='magasinier1', password='pass12345', email='magasinier1@test.gn', entreprise=self.entreprise)
        self.acheteur = Utilisateur.objects.create_user(
            username='achat1', password='pass12345', email='achat1@test.gn', entreprise=self.entreprise)
        ProfilStock.objects.create(utilisateur=self.acheteur, role='responsable_achat')
        # Le demandeur n'a AUCUN profil stock -> traité comme "administrateur" par
        # défaut selon stock/permissions.py, donc on force un rôle restrictif
        # (magasinier = pas de permission 'achats') pour vérifier le vrai circuit.
        ProfilStock.objects.create(utilisateur=self.demandeur, role='magasinier')

        self.fournisseur = Fournisseur.objects.create(
            entreprise=self.entreprise, nom='Fournisseur Test', categorie='strategique',
            note_evaluation=Decimal('16.5'), delai_livraison_jours=5,
        )
        categorie = CategorieArticle.objects.create(entreprise=self.entreprise, nom='Consommables')
        self.article = Article.objects.create(
            entreprise=self.entreprise, reference='ART-001', designation='Ramette papier A4',
            categorie=categorie, fournisseur=self.fournisseur, prix_achat=Decimal('50000'),
        )

    def test_workflow_complet_besoin_vers_commande(self):
        # 1. Le magasinier (sans permission 'achats') exprime un besoin.
        self.client.force_login(self.demandeur)
        resp = self.client.post(reverse('stock:besoin_achat_create'), {
            'urgence': 'urgente', 'motif': 'Stock de bureau épuisé',
        })
        besoin = BesoinAchat.objects.get()
        self.assertEqual(besoin.statut, 'soumise')
        self.assertEqual(besoin.demandeur, self.demandeur)
        self.assertRedirects(resp, reverse('stock:besoin_achat_detail', args=[besoin.pk]))

        resp = self.client.post(reverse('stock:besoin_achat_detail', args=[besoin.pk]), {
            'article': self.article.pk, 'quantite_demandee': '20',
        })
        self.assertEqual(besoin.lignes.count(), 1)
        ligne_besoin = besoin.lignes.first()
        self.assertEqual(ligne_besoin.quantite_demandee, Decimal('20'))

        # Le demandeur (rôle magasinier, sans permission 'achats') ne peut PAS valider.
        resp = self.client.get(reverse('stock:besoin_achat_valider', args=[besoin.pk]))
        besoin.refresh_from_db()
        self.assertEqual(besoin.statut, 'soumise', "Un magasinier ne doit pas pouvoir valider un besoin.")

        # 2. Le responsable achat valide le besoin.
        self.client.logout()
        self.client.force_login(self.acheteur)
        resp = self.client.get(reverse('stock:besoin_achat_valider', args=[besoin.pk]))
        besoin.refresh_from_db()
        self.assertEqual(besoin.statut, 'validee')
        self.assertEqual(besoin.valide_par, self.acheteur)

        # 3. Le besoin validé apparaît dans le réapprovisionnement, groupé par fournisseur.
        resp = self.client.get(reverse('stock:reapprovisionnement'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['nb_besoins_en_attente'], 1)
        checkbox_id = f'besoin:{ligne_besoin.pk}'
        trouve = any(
            any(s['checkbox_id'] == checkbox_id for s in suggestions)
            for _, suggestions in resp.context['groupes']
        )
        self.assertTrue(trouve, "La ligne de besoin validée doit apparaître dans le réapprovisionnement.")

        # 4. Génération automatique du bon de commande (infos fournisseur pré-remplies).
        resp = self.client.post(reverse('stock:reapprovisionnement'), {
            'inclure': [checkbox_id],
            f'qte_{checkbox_id}': '20',
        })
        self.assertRedirects(resp, reverse('stock:commande_list'))

        commande = CommandeFournisseur.objects.get()
        self.assertEqual(commande.fournisseur, self.fournisseur)
        self.assertEqual(commande.statut, 'brouillon')
        ligne_commande = LigneCommande.objects.get()
        self.assertEqual(ligne_commande.article, self.article)
        self.assertEqual(ligne_commande.quantite_commandee, Decimal('20'))
        self.assertEqual(ligne_commande.prix_unitaire, self.article.prix_achat)

        ligne_besoin.refresh_from_db()
        besoin.refresh_from_db()
        self.assertEqual(ligne_besoin.ligne_commande, ligne_commande)
        self.assertEqual(besoin.statut, 'traitee')

    def test_reapprovisionnement_alertes_stock_toujours_fonctionnel(self):
        """Le refactor ne doit rien casser du comportement existant (alertes de stock)."""
        self.article.seuil_alerte = Decimal('10')
        self.article.quantite_stock = Decimal('2')
        self.article.stock_max = Decimal('50')
        self.article.save()

        self.client.force_login(self.acheteur)
        resp = self.client.get(reverse('stock:reapprovisionnement'))
        checkbox_id = f'art:{self.article.pk}'
        trouve = any(
            any(s['checkbox_id'] == checkbox_id and s['source'] == 'alerte' for s in suggestions)
            for _, suggestions in resp.context['groupes']
        )
        self.assertTrue(trouve)

        resp = self.client.post(reverse('stock:reapprovisionnement'), {
            'inclure': [checkbox_id],
            f'qte_{checkbox_id}': '48',
        })
        self.assertRedirects(resp, reverse('stock:commande_list'))
        commande = CommandeFournisseur.objects.get()
        self.assertEqual(commande.fournisseur, self.fournisseur)
        self.assertEqual(LigneCommande.objects.get().quantite_commandee, Decimal('48'))


class DemandeVenteWorkflowTest(TestCase):
    """Un commercial exprime le besoin d'un client ; la validation génère
    automatiquement le devis (DocumentVente) avec client et prix pré-remplis."""

    def setUp(self):
        self.entreprise = Entreprise.objects.create(nom_entreprise='ACME Guinée')
        self.commercial = Utilisateur.objects.create_user(
            username='commercial1', password='pass12345', email='commercial1@test.gn', entreprise=self.entreprise)
        self.responsable_ventes = Utilisateur.objects.create_user(
            username='ventes1', password='pass12345', email='ventes1@test.gn', entreprise=self.entreprise)
        ProfilStock.objects.create(utilisateur=self.responsable_ventes, role='comptable')  # a la permission 'ventes'
        ProfilStock.objects.create(utilisateur=self.commercial, role='magasinier')  # PAS la permission 'ventes'

        self.client_obj = Client.objects.create(entreprise=self.entreprise, nom='Client Test', remise_defaut=Decimal('5'))
        categorie = CategorieArticle.objects.create(entreprise=self.entreprise, nom='Bureau')
        self.article = Article.objects.create(
            entreprise=self.entreprise, reference='ART-100', designation='Chaise de bureau',
            categorie=categorie, prix_vente=Decimal('150000'),
        )

    def test_workflow_complet_demande_vers_devis(self):
        self.client.force_login(self.commercial)
        resp = self.client.post(reverse('stock:demande_vente_create'), {
            'client': self.client_obj.pk, 'date_besoin': '2026-08-01', 'notes': 'Client pressé',
        })
        demande = DemandeVente.objects.get()
        self.assertEqual(demande.statut, 'soumise')
        self.assertEqual(demande.demandeur, self.commercial)
        self.assertRedirects(resp, reverse('stock:demande_vente_detail', args=[demande.pk]))

        self.client.post(reverse('stock:demande_vente_detail', args=[demande.pk]), {
            'article': self.article.pk, 'quantite_souhaitee': '4',
        })
        self.assertEqual(demande.lignes.count(), 1)

        # Le commercial (sans permission 'ventes') ne peut PAS valider.
        self.client.get(reverse('stock:demande_vente_valider', args=[demande.pk]))
        demande.refresh_from_db()
        self.assertEqual(demande.statut, 'soumise')

        # Le responsable ventes valide -> génération automatique du devis.
        self.client.logout()
        self.client.force_login(self.responsable_ventes)
        resp = self.client.get(reverse('stock:demande_vente_valider', args=[demande.pk]))

        demande.refresh_from_db()
        self.assertEqual(demande.statut, 'convertie')
        self.assertIsNotNone(demande.document_genere)

        doc = demande.document_genere
        self.assertEqual(doc.type_document, 'devis')
        self.assertEqual(doc.statut, 'brouillon')
        self.assertEqual(doc.client, self.client_obj)
        self.assertRedirects(resp, reverse('stock:vente_detail', args=[doc.pk]))

        ligne_vente = LigneVente.objects.get()
        self.assertEqual(ligne_vente.article, self.article)
        self.assertEqual(ligne_vente.quantite, Decimal('4'))
        self.assertEqual(ligne_vente.prix_unitaire, self.article.prix_vente)
        self.assertEqual(ligne_vente.remise_pct, self.client_obj.remise_defaut)
