import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Entreprise, ProfilUtilisateur
from core.tenancy import pour_entreprise

from . import services
from .models import (
    ClientCompte, DemandeStock, EcritureCaisse, MouvementStock, Operation, ParametreVentes, Produit, Vente,
)
from .services import ErreurMetier

User = get_user_model()
D = Decimal


def _entreprise(slug):
    return Entreprise.objects.create(
        nom_entreprise=f"Entreprise {slug}", slug=slug, email=f"{slug}@example.test", type_module="all")


def _user(entreprise, nom, niveau=None, admin=False):
    profil = None
    if niveau:
        profil, _ = ProfilUtilisateur.objects.get_or_create(
            nom_profil=f"niveau{niveau}", defaults={"niveau_acces": niveau})
    return User.objects.create_user(
        username=nom, email=f"{nom}@example.test", password="Mdp-test-1234", entreprise=entreprise,
        est_admin_entreprise=admin, actif=True, profil=profil)


class VentesBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent_a, cls.ent_b = _entreprise("alpha"), _entreprise("bravo")
        cls.admin_a = _user(cls.ent_a, "admin_a", admin=True)
        cls.caissier_a = _user(cls.ent_a, "caissier_a", niveau=2)
        cls.lecteur_a = _user(cls.ent_a, "lecteur_a", niveau=1)
        cls.admin_b = _user(cls.ent_b, "admin_b", admin=True)
        with pour_entreprise(cls.ent_a):
            cls.riz = Produit.objects.create(nom="Riz 1kg", prix_unitaire=D("10000"),
                                             quantite_stock=D("20"), seuil_alerte=D("5"))
            cls.plat = Produit.objects.create(nom="Plat du jour", prix_unitaire=D("15000"), suivi_stock=False)
            ClientCompte.objects.create(matricule="M001", nom="Camara Moussa")
        with pour_entreprise(cls.ent_b):
            cls.produit_b = Produit.objects.create(nom="Produit B", prix_unitaire=D("1"), quantite_stock=D("1"))
            ClientCompte.objects.create(matricule="B001", nom="Client B")


class ServicesTests(VentesBase):
    def setUp(self):
        self._cm = pour_entreprise(self.ent_a)
        self._cm.__enter__()
        self.addCleanup(self._cm.__exit__, None, None, None)

    def test_solde_depot_retrait_vente(self):
        services.creer_depot(self.caissier_a, "M001", "", D("30000"))
        services.creer_retrait_ou_vente(self.caissier_a, "M001", "", "", "compte", [], "10000")
        genre, ventes = services.creer_retrait_ou_vente(
            self.caissier_a, "M001", "", "", "compte", [(self.riz.pk, "1")])
        self.assertEqual(genre, "vente")
        self.assertEqual(services.solde_matricule("M001"), D("10000"))
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("19"))

    def test_plafond_journalier_de_depot(self):
        services.creer_depot(self.caissier_a, "M001", "", D("30000"))
        with self.assertRaises(ErreurMetier) as ctx:
            services.creer_depot(self.caissier_a, "M001", "", D("15000"))
        self.assertIn("Plafond journalier", str(ctx.exception))
        services.creer_depot(self.caissier_a, "M002", "", D("40000"))  # autre matricule : possible

    def test_plafond_modifiable_et_desactivable(self):
        p = ParametreVentes.courant()
        p.plafond_depot_journalier = D("0")
        p.save()
        services.creer_depot(self.caissier_a, "M001", "", D("500000"))
        self.assertEqual(services.solde_matricule("M001"), D("500000"))

    def test_retrait_superieur_au_solde_refuse(self):
        services.creer_depot(self.caissier_a, "M001", "", D("5000"))
        with self.assertRaises(ErreurMetier):
            services.creer_retrait_ou_vente(self.caissier_a, "M001", "", "", "compte", [], "6000")

    def test_vente_en_caisse_n_affecte_pas_le_compte_et_alimente_la_caisse(self):
        genre, ventes = services.creer_retrait_ou_vente(
            self.caissier_a, "", "", "", "caisse", [(self.riz.pk, "2")])
        self.assertEqual(services.solde_caisse(), D("20000"))
        self.assertEqual(ventes[0].matricule, "")
        self.assertEqual(services.solde_matricule(""), D("0"))

    def test_stock_insuffisant_refuse(self):
        with self.assertRaises(ErreurMetier) as ctx:
            services.creer_retrait_ou_vente(self.caissier_a, "", "", "", "caisse", [(self.riz.pk, "21")])
        self.assertIn("Stock insuffisant", str(ctx.exception))
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("20"))  # rien n'a été modifié

    def test_article_sans_suivi_de_stock(self):
        services.creer_retrait_ou_vente(self.caissier_a, "", "", "", "caisse", [(self.plat.pk, "3")])
        self.plat.refresh_from_db()
        self.assertEqual(self.plat.quantite_stock, D("0"))
        self.assertFalse(MouvementStock.objects.filter(produit=self.plat).exists())
        self.assertEqual(services.solde_caisse(), D("45000"))

    def test_annuler_puis_restaurer_une_vente(self):
        _, ventes = services.creer_retrait_ou_vente(self.caissier_a, "", "", "", "caisse", [(self.riz.pk, "4")])
        services.supprimer_vente(self.admin_a, ventes[0])
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("20"))
        self.assertEqual(services.solde_caisse(), D("0"))
        services.restaurer_vente(self.admin_a, Vente.objects.get(pk=ventes[0].pk))
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("16"))
        self.assertEqual(services.solde_caisse(), D("40000"))

    def test_depot_deja_utilise_ne_peut_pas_etre_supprime(self):
        op = services.creer_depot(self.caissier_a, "M001", "", D("10000"))
        services.creer_retrait_ou_vente(self.caissier_a, "M001", "", "", "compte", [], "8000")
        with self.assertRaises(ErreurMetier):
            services.supprimer_operation(self.admin_a, op)

    def test_caisse_sortie_superieure_au_solde_refusee(self):
        services.ecriture_caisse(self.caissier_a, "Ouverture", "ouverture", "10000")
        with self.assertRaises(ErreurMetier):
            services.ecriture_caisse(self.caissier_a, "Achat", "sortie", "10001")
        services.ecriture_caisse(self.caissier_a, "Achat", "sortie", "4000")
        self.assertEqual(services.solde_caisse(), D("6000"))
        with self.assertRaises(ErreurMetier):  # une seule ouverture
            services.ecriture_caisse(self.caissier_a, "Ouverture bis", "ouverture", "1")

    def test_demande_d_entree_validee_et_rejetee(self):
        d1 = services.creer_demande_entree(self.caissier_a, self.riz, "5", "Livraison")
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("20"))  # sans effet tant que non validée
        services.valider_demande(self.admin_a, d1)
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("25"))
        d2 = services.creer_demande_entree(self.caissier_a, self.riz, "9")
        services.rejeter_demande(self.admin_a, d2, "Doublon")
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("25"))
        with self.assertRaises(ErreurMetier):
            services.valider_demande(self.admin_a, d2)

    def test_nouveau_produit_propose_puis_valide(self):
        d = services.creer_demande_produit(self.caissier_a, "Huile 5L", "H5", "60000", "2", "", "10")
        _, produit = services.valider_demande(self.admin_a, d)
        self.assertEqual(produit.quantite_stock, D("10"))
        with self.assertRaises(ErreurMetier):
            services.creer_demande_produit(self.caissier_a, "huile  5l", "", "1", "0", "", "1")

    def test_inventaire_aligne_le_stock(self):
        services.compter_inventaire(self.admin_a, {self.riz.pk: "17"})
        self.riz.refresh_from_db()
        self.assertEqual(self.riz.quantite_stock, D("17"))
        mv = MouvementStock.objects.filter(produit=self.riz).first()
        self.assertEqual((mv.type, mv.quantite), ("sortie", D("3")))

    def test_saisie_avec_espaces_et_virgule(self):
        self.assertEqual(services.nombre("1 250,5"), D("1250.5"))
        with self.assertRaises(ErreurMetier):
            services.nombre("abc")


class IsolationTests(VentesBase):
    def test_les_listes_n_exposent_que_les_donnees_de_l_entreprise(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("ventes:produits"))
        self.assertContains(rep, "Riz 1kg")
        self.assertNotContains(rep, "Produit B")
        rep = self.client.get(reverse("ventes:clients"))
        self.assertContains(rep, "M001")
        self.assertNotContains(rep, "B001")

    def test_acces_a_un_produit_d_une_autre_entreprise(self):
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(reverse("ventes:produit_modifier", args=[self.produit_b.pk])).status_code, 404)

    def test_une_vente_ne_peut_pas_cibler_un_produit_d_une_autre_entreprise(self):
        self.client.force_login(self.caissier_a)
        rep = self.client.post(reverse("ventes:retrait_nouveau"), {
            "mode_paiement": "caisse", "confirme": "1", "prod_id": [str(self.produit_b.pk)], "prod_qte": ["1"]})
        self.assertContains(rep, "invalide ou inactif")
        with pour_entreprise(self.ent_b):
            self.produit_b.refresh_from_db()
            self.assertEqual(self.produit_b.quantite_stock, D("1"))

    def test_soldes_separes_par_entreprise(self):
        with pour_entreprise(self.ent_a):
            services.creer_depot(self.admin_a, "M001", "", D("1000"))
        with pour_entreprise(self.ent_b):
            self.assertEqual(services.solde_matricule("M001"), D("0"))


class DroitsEtPagesTests(VentesBase):
    def test_lecteur_ne_peut_pas_saisir(self):
        self.client.force_login(self.lecteur_a)
        self.assertEqual(self.client.get(reverse("ventes:tableau_de_bord")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ventes:depot_nouveau")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ventes:retrait_nouveau")).status_code, 403)

    def test_caissier_n_est_pas_administrateur(self):
        self.client.force_login(self.caissier_a)
        self.assertEqual(self.client.get(reverse("ventes:depot_nouveau")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ventes:produit_nouveau")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ventes:journal")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ventes:validations")).status_code, 403)

    def test_toutes_les_pages_s_affichent(self):
        self.client.force_login(self.admin_a)
        with pour_entreprise(self.ent_a):
            services.creer_depot(self.admin_a, "M001", "", D("1000"))
            _, v = services.creer_retrait_ou_vente(self.admin_a, "", "", "", "caisse", [(self.riz.pk, "1")])
            services.creer_demande_entree(self.caissier_a, self.riz, "2")
        noms = [
            "tableau_de_bord", "clients", "client_nouveau", "depot_nouveau", "retrait_nouveau", "operations",
            "ventes", "caisse", "produits", "produit_nouveau", "demande_produit", "validations", "mouvements",
            "inventaire", "corbeille", "rapports", "journal", "parametres",
        ]
        for nom in noms:
            with self.subTest(page=nom):
                rep = self.client.get(reverse(f"ventes:{nom}"))
                self.assertEqual(rep.status_code, 200, nom)
                self.assertContains(rep, "o_navbar")
        with pour_entreprise(self.ent_a):
            op, vente = Operation.objects.first(), Vente.objects.first()
        self.assertEqual(self.client.get(reverse("ventes:ticket", args=["operation", op.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("ventes:ticket", args=["vente", vente.pk])).status_code, 200)

    def test_exports_et_rapports(self):
        self.client.force_login(self.admin_a)
        for nom in ("clients", "operations", "ventes", "caisse", "produits"):
            with self.subTest(export=nom):
                x = self.client.get(reverse(f"ventes:{nom}"), {"export": "xlsx"})
                self.assertEqual(x.status_code, 200)
                self.assertIn("spreadsheetml", x["Content-Type"])
                p = self.client.get(reverse(f"ventes:{nom}"), {"export": "pdf"})
                self.assertEqual(p["Content-Type"], "application/pdf")
        rep = self.client.post(reverse("ventes:rapports"), {"dataset": "ventes", "kind": "all", "format": "xlsx"})
        self.assertEqual(rep.status_code, 200)

    def test_depot_via_la_page_puis_corbeille(self):
        self.client.force_login(self.admin_a)
        rep = self.client.post(reverse("ventes:depot_nouveau"), {"matricule": "M001", "montant": "12 000"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            op = Operation.objects.get()
        self.client.post(reverse("ventes:operation_supprimer", args=[op.pk]))
        with pour_entreprise(self.ent_a):
            self.assertTrue(Operation.objects.get().deleted)
        self.client.post(reverse("ventes:operation_restaurer", args=[op.pk]))
        with pour_entreprise(self.ent_a):
            self.assertFalse(Operation.objects.get().deleted)

    def test_caissier_ne_supprime_pas(self):
        with pour_entreprise(self.ent_a):
            op = services.creer_depot(self.admin_a, "M001", "", D("1000"))
        self.client.force_login(self.caissier_a)
        self.assertEqual(self.client.post(reverse("ventes:operation_supprimer", args=[op.pk])).status_code, 403)

    def test_solde_api(self):
        self.client.force_login(self.caissier_a)
        with pour_entreprise(self.ent_a):
            services.creer_depot(self.admin_a, "M001", "", D("2500"))
        data = self.client.get(reverse("ventes:solde_api"), {"matricule": "M001"}).json()
        self.assertEqual(data["solde"], 2500)
        self.assertEqual(data["nom"], "Camara Moussa")
