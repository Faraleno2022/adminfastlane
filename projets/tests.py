import datetime
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Entreprise, ProfilUtilisateur
from core.tenancy import pour_entreprise

from .forms import MouvementForm, ProjetForm, TacheForm
from .models import Client, Membre, Mouvement, Projet, Tache

User = get_user_model()
D = Decimal
MEDIA_TEST = tempfile.mkdtemp(prefix="projets_tests_")


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


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class ProjetsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent_a, cls.ent_b = _entreprise("alpha"), _entreprise("bravo")
        cls.admin_a = _user(cls.ent_a, "admin_a", admin=True)
        cls.saisie_a = _user(cls.ent_a, "saisie_a", niveau=2)
        cls.lecteur_a = _user(cls.ent_a, "lecteur_a", niveau=1)
        cls.admin_b = _user(cls.ent_b, "admin_b", admin=True)
        aujourdhui = timezone.localdate()
        with pour_entreprise(cls.ent_a):
            cls.client_a = Client.objects.create(nom="Société Kaloum BTP", telephone="620000000")
            cls.projet = Projet.objects.create(
                nom="Villa moderne", client=cls.client_a, budget=D("100000000"), statut=Projet.EN_COURS,
                date_debut=aujourdhui - datetime.timedelta(days=30), date_fin_prevue=aujourdhui + datetime.timedelta(days=60))
            cls.fondations = Tache.objects.create(
                projet=cls.projet, titre="Fondations", progression=100, statut=Tache.TERMINEE,
                date_fin_prevue=aujourdhui - datetime.timedelta(days=5))
            cls.murs = Tache.objects.create(
                projet=cls.projet, titre="Élévation des murs", progression=40, statut=Tache.EN_COURS,
                date_fin_prevue=aujourdhui - datetime.timedelta(days=2))
            Mouvement.objects.create(projet=cls.projet, type=Mouvement.DEPOT, montant=D("50000000"), libelle="Avance client")
            Mouvement.objects.create(projet=cls.projet, type=Mouvement.RETRAIT, montant=D("5000000"), libelle="Retrait caisse")
            cls.ciment = Mouvement.objects.create(
                projet=cls.projet, type=Mouvement.DEPENSE, categorie="materiaux", montant=D("30000000"),
                libelle="Ciment et fer")
        with pour_entreprise(cls.ent_b):
            cls.client_b = Client.objects.create(nom="Client B")
            cls.projet_b = Projet.objects.create(nom="Projet secret B", client=cls.client_b)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)


class ModeleTests(ProjetsBase):
    def test_reference_incrementale_par_entreprise(self):
        annee = timezone.localdate().year
        self.assertEqual(self.projet.reference, f"PRJ-{annee}-0001")
        self.assertEqual(self.projet_b.reference, f"PRJ-{annee}-0001")
        with pour_entreprise(self.ent_a):
            second = Projet.objects.create(nom="Immeuble R+3")
        self.assertEqual(second.reference, f"PRJ-{annee}-0002")

    def test_solde_regle_etragsarlu(self):
        p = Projet.objects.prefetch_related("mouvements").get(pk=self.projet.pk)
        self.assertEqual(p.total_depots, D("50000000"))
        self.assertEqual(p.total_retraits, D("5000000"))
        self.assertEqual(p.total_depenses, D("30000000"))
        # 100 000 000 + 50 000 000 − 5 000 000 − 30 000 000
        self.assertEqual(p.solde_disponible, D("115000000"))
        self.assertEqual(p.budget_consomme_pct, 20)
        self.assertFalse(p.budget_depasse)

    def test_budget_depasse(self):
        with pour_entreprise(self.ent_a):
            Mouvement.objects.create(projet=self.projet, type=Mouvement.DEPENSE, categorie="autre",
                                     montant=D("200000000"), libelle="Gros achat")
        self.assertTrue(Projet.objects.get(pk=self.projet.pk).budget_depasse)

    def test_progression_moyenne_des_taches_hors_annulees(self):
        p = Projet.objects.get(pk=self.projet.pk)
        self.assertEqual(p.progression, 70)
        with pour_entreprise(self.ent_a):
            Tache.objects.create(projet=self.projet, titre="Annulée", statut=Tache.ANNULEE)
        self.assertEqual(Projet.objects.get(pk=self.projet.pk).progression, 70)

    def test_progression_manuelle_sans_tache(self):
        with pour_entreprise(self.ent_a):
            p = Projet.objects.create(nom="Étude", avancement=35)
        self.assertEqual(p.progression, 35)

    def test_tache_terminee_et_retard(self):
        fondations = Tache.objects.get(pk=self.fondations.pk)
        self.assertEqual(fondations.date_fin_reelle, timezone.localdate())
        self.assertFalse(fondations.en_retard)
        murs = Tache.objects.get(pk=self.murs.pk)
        self.assertTrue(murs.en_retard)
        self.assertEqual(murs.jours_retard, 2)

    def test_tache_rouverte_perd_sa_date_de_fin(self):
        t = Tache.objects.get(pk=self.fondations.pk)
        t.statut = Tache.EN_COURS
        t.save()
        self.assertIsNone(t.date_fin_reelle)

    def test_projet_termine_date(self):
        p = Projet.objects.get(pk=self.projet.pk)
        p.statut = Projet.TERMINE
        p.save()
        self.assertEqual(p.date_fin_reelle, timezone.localdate())

    def test_membre_actif(self):
        hier = timezone.localdate() - datetime.timedelta(days=1)
        self.assertTrue(Membre(projet=self.projet, nom="A").actif)
        self.assertFalse(Membre(projet=self.projet, nom="B", date_fin=hier).actif)


class FormulairesTests(ProjetsBase):
    def test_depense_sans_categorie_refusee(self):
        form = MouvementForm({"type": "depense", "date": "2026-10-01", "montant": "1000", "libelle": "x",
                              "mode": "especes"})
        self.assertFalse(form.is_valid())
        self.assertIn("categorie", form.errors)

    def test_montant_negatif_refuse(self):
        form = MouvementForm({"type": "depot", "date": "2026-10-01", "montant": "-5", "libelle": "x", "mode": "especes"})
        self.assertFalse(form.is_valid())

    def test_categorie_effacee_pour_un_depot(self):
        form = MouvementForm({"type": "depot", "categorie": "materiaux", "date": "2026-10-01", "montant": "5",
                              "libelle": "x", "mode": "especes"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["categorie"], "")

    def test_piece_au_mauvais_format_refusee(self):
        form = MouvementForm(
            {"type": "depot", "date": "2026-10-01", "montant": "5", "libelle": "x", "mode": "especes"},
            {"piece": SimpleUploadedFile("script.exe", b"MZ")})
        self.assertFalse(form.is_valid())
        self.assertIn("piece", form.errors)

    def test_dates_et_pourcentages(self):
        form = ProjetForm({"nom": "X", "budget": "0", "statut": "planifie", "avancement": "150",
                           "date_debut": "2026-10-10", "date_fin_prevue": "2026-10-01"})
        self.assertFalse(form.is_valid())
        self.assertIn("avancement", form.errors)
        self.assertIn("date_fin_prevue", form.errors)
        form = TacheForm({"titre": "T", "priorite": "moyenne", "statut": "a_faire", "progression": "101", "ordre": "1"})
        self.assertFalse(form.is_valid())


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class VuesTests(ProjetsBase):
    def test_pages_accessibles(self):
        with pour_entreprise(self.ent_a):
            membre = Membre.objects.create(projet=self.projet, nom="Diallo Mamadou", role="Chef de chantier")
        self.client.force_login(self.admin_a)
        pages = [
            ("tableau_de_bord", []), ("projets", []), ("projet_nouveau", []), ("projet_detail", [self.projet.pk]),
            ("projet_modifier", [self.projet.pk]), ("fiche", [self.projet.pk]), ("taches", []),
            ("tache_nouvelle", [self.projet.pk]), ("tache_modifier", [self.murs.pk]),
            ("membre_nouveau", [self.projet.pk]), ("membre_modifier", [membre.pk]), ("mouvements", []),
            ("mouvement_nouveau", [self.projet.pk]), ("mouvement_modifier", [self.ciment.pk]),
            ("clients", []), ("client_nouveau", []), ("client_detail", [self.client_a.pk]),
            ("client_modifier", [self.client_a.pk]), ("rapports", []),
        ]
        for nom, args in pages:
            rep = self.client.get(reverse(f"projets:{nom}", args=args))
            self.assertEqual(rep.status_code, 200, nom)

    def test_isolation_entre_entreprises(self):
        self.client.force_login(self.admin_a)
        self.assertNotContains(self.client.get(reverse("projets:projets")), "Projet secret B")
        self.assertNotContains(self.client.get(reverse("projets:clients")), "Client B")
        self.assertEqual(self.client.get(reverse("projets:projet_detail", args=[self.projet_b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("projets:fiche", args=[self.projet_b.pk])).status_code, 404)

    def test_creation_projet(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("projets:projet_nouveau"), {
            "nom": "Route de Kindia", "client": self.client_a.pk, "budget": "250000000", "statut": "planifie",
            "avancement": "0"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            p = Projet.objects.get(nom="Route de Kindia")
        self.assertTrue(p.reference.startswith("PRJ-"))
        self.assertEqual(p.cree_par, "saisie_a")

    def test_client_d_une_autre_entreprise_refuse(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("projets:projet_nouveau"), {
            "nom": "Pirate", "client": self.client_b.pk, "budget": "0", "statut": "planifie", "avancement": "0"})
        self.assertEqual(rep.status_code, 200)
        with pour_entreprise(self.ent_a):
            self.assertFalse(Projet.objects.filter(nom="Pirate").exists())

    def test_ajout_tache_et_terminer(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("projets:tache_nouvelle", args=[self.projet.pk]), {
            "titre": "Toiture", "priorite": "haute", "statut": "a_faire", "progression": "0", "ordre": "3"})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            toiture = Tache.objects.get(titre="Toiture")
        rep = self.client.post(reverse("projets:tache_statut", args=[toiture.pk]),
                               {"statut": "terminee", "retour": "planning"})
        self.assertRedirects(rep, reverse("projets:taches"), fetch_redirect_response=False)
        toiture.refresh_from_db()
        self.assertEqual((toiture.statut, toiture.progression), (Tache.TERMINEE, 100))

    def test_mouvement_avec_piece_et_telechargement(self):
        self.client.force_login(self.saisie_a)
        rep = self.client.post(reverse("projets:mouvement_nouveau", args=[self.projet.pk]), {
            "type": "depense", "categorie": "main_oeuvre", "date": "2026-10-05", "montant": "1500000",
            "libelle": "Paie des maçons", "mode": "mobile_money",
            "piece": SimpleUploadedFile("facture.pdf", b"%PDF-1.4 test", content_type="application/pdf")})
        self.assertEqual(rep.status_code, 302)
        with pour_entreprise(self.ent_a):
            m = Mouvement.objects.get(libelle="Paie des maçons")
        self.assertEqual(m.saisi_par, "saisie_a")
        rep = self.client.get(reverse("projets:mouvement_piece", args=[m.pk]))
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(b"".join(rep.streaming_content), b"%PDF-1.4 test")
        rep.close()
        # Une autre entreprise ne peut pas lire la pièce
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(reverse("projets:mouvement_piece", args=[m.pk])).status_code, 404)

    def test_lecteur_en_lecture_seule(self):
        self.client.force_login(self.lecteur_a)
        self.assertEqual(self.client.get(reverse("projets:projets")).status_code, 200)
        self.assertEqual(self.client.get(reverse("projets:projet_nouveau")).status_code, 403)
        self.assertEqual(self.client.post(reverse("projets:projet_statut", args=[self.projet.pk]),
                                          {"statut": "annule"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("projets:mouvement_nouveau", args=[self.projet.pk])).status_code, 403)

    def test_suppression_reservee_aux_responsables(self):
        self.client.force_login(self.saisie_a)
        self.assertEqual(self.client.post(reverse("projets:tache_supprimer", args=[self.murs.pk])).status_code, 403)

    def test_suppression_projet_avec_mouvements_refusee(self):
        self.client.force_login(self.admin_a)
        self.client.post(reverse("projets:projet_supprimer", args=[self.projet.pk]))
        with pour_entreprise(self.ent_a):
            self.assertTrue(Projet.objects.filter(pk=self.projet.pk).exists())

    def test_suppression_client_avec_projets_refusee(self):
        self.client.force_login(self.admin_a)
        self.client.post(reverse("projets:client_supprimer", args=[self.client_a.pk]))
        with pour_entreprise(self.ent_a):
            self.assertTrue(Client.objects.filter(pk=self.client_a.pk).exists())

    def test_changement_de_statut_termine(self):
        self.client.force_login(self.saisie_a)
        self.client.post(reverse("projets:projet_statut", args=[self.projet.pk]), {"statut": "termine"})
        self.projet.refresh_from_db()
        self.assertEqual(self.projet.statut, Projet.TERMINE)
        self.assertEqual(self.projet.date_fin_reelle, timezone.localdate())

    def test_filtres_et_exports(self):
        self.client.force_login(self.admin_a)
        rep = self.client.get(reverse("projets:taches"), {"filtre": "retard"})
        self.assertContains(rep, "Élévation des murs")
        self.assertNotContains(rep, "Fondations")
        rep = self.client.get(reverse("projets:projets"), {"statut": "annule"})
        self.assertNotContains(rep, self.projet.reference)
        rep = self.client.get(reverse("projets:mouvements"), {"type": "depense"})
        self.assertContains(rep, "Ciment et fer")
        self.assertNotContains(rep, "Avance client")
        for nom in ("projets", "taches", "mouvements"):
            rep = self.client.get(reverse(f"projets:{nom}"), {"export": "xlsx"})
            self.assertIn("spreadsheetml", rep["Content-Type"], nom)
        rep = self.client.get(reverse("projets:rapports"), {"export": "pdf"})
        self.assertEqual(rep["Content-Type"], "application/pdf")

    def test_rapport_par_categorie(self):
        self.client.force_login(self.admin_a)
        jour = timezone.localdate().isoformat()
        rep = self.client.get(reverse("projets:rapports"), {"date_from": jour, "date_to": jour})
        self.assertContains(rep, "Achat de matériaux")
        self.assertContains(rep, self.projet.reference)

    def test_menu_application_projets(self):
        from core.odoo_menu import APPS
        self.assertIn("projets", [a["key"] for a in APPS])
