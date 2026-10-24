"""Commande charger_demo : chargement, exactitude des calculs, suppression sans effet de bord."""
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from core.management.commands.charger_demo import EMPLOYES
from core.models import DonneeDemo, Entreprise, Utilisateur
from core.tenancy import pour_entreprise

D = Decimal
BAREME_RTS = [(D(0), D(1000000), D(0)), (D(1000000), D(3000000), D(5)), (D(3000000), D(5000000), D(8)),
              (D(5000000), D(10000000), D(10)), (D(10000000), D(20000000), D(15)), (D(20000000), None, D(20))]


def _arrondi(valeur):
    return valeur.quantize(D(1), rounding=ROUND_HALF_UP)


def bulletin_attendu(base, transport, logement, prime, stagiaire=False):
    """Recalcul indépendant du moteur, selon les règles appliquées en Guinée (CGI 2022, CNSS)."""
    base, transport, logement, prime = (D(x) for x in (base, transport, logement, prime))
    brut = base + transport + logement + prime
    cnss_base = min(max(brut, D(550000)), D(2500000))         # plancher SMIG, plafond CNSS
    cnss = _arrondi(cnss_base * 5 / 100)
    indemnites = transport + logement
    reintegration = max(indemnites - brut * D("0.25"), D(0))   # indemnités exonérées dans la limite de 25 % du brut
    base_rts = _arrondi(base + prime - cnss + reintegration)
    rts = D(0)
    if not (stagiaire and brut <= D(1200000)):  # stagiaire exonéré jusqu'à 1 200 000 GNF
        for bas, haut, taux in BAREME_RTS:
            tranche = (min(base_rts, haut) if haut else base_rts) - bas
            if tranche > 0:
                rts += tranche * taux / 100
        rts = _arrondi(rts)
    return {"salaire_brut": brut, "cnss_employe": cnss, "irg": rts, "net_a_payer": brut - cnss - rts,
            "cnss_employeur": _arrondi(cnss_base * 18 / 100), "versement_forfaitaire": _arrondi(brut * 6 / 100),
            "taxe_apprentissage": _arrondi(brut * 2 / 100)}


class ChargerDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(nom_entreprise="Myschool", slug="myschool", email="a@myschool.test")
        cls.user = Utilisateur.objects.create_user(username="Myschool", email="a@myschool.test",
                                                   password="Mdp-tres-solide-2026", entreprise=cls.entreprise,
                                                   est_admin_entreprise=True)
        cls.autre = Entreprise.objects.create(nom_entreprise="Autre", slug="autre", email="b@autre.test")
        from carburant.models import Client
        from employes.models import Employe
        with pour_entreprise(cls.entreprise):
            Client.objects.create(nom="Client réel existant")
        Employe.objects.create(entreprise=cls.entreprise, matricule="REEL-001", nom="REEL", prenoms="Employé")

    def _charger(self):
        sortie = StringIO()
        call_command("charger_demo", utilisateur="myschool", stdout=sortie)
        return sortie.getvalue()

    def test_bulletins_conformes_au_recalcul_independant(self):
        from paie.models import BulletinPaie
        sortie = self._charger()
        self.assertIn("Démonstration chargée", sortie)
        bulletins = BulletinPaie.objects.filter(employe__matricule__startswith="D").select_related("employe")
        self.assertEqual(bulletins.count(), len(EMPLOYES) * 3)
        par_nom = {e[1]: e for e in EMPLOYES}
        for bulletin in bulletins:
            e = par_nom[bulletin.employe.nom]
            attendu = bulletin_attendu(e[11], e[12], e[13], e[14], stagiaire=e[5] == "stage")
            for champ, valeur in attendu.items():
                self.assertEqual(getattr(bulletin, champ), valeur, f"{bulletin.employe.nom} {champ}")

    def test_cas_calcules_a_la_main(self):
        from paie.models import BulletinPaie
        self._charger()
        dg = BulletinPaie.objects.filter(employe__nom="CAMARA").latest("annee_paie", "mois_paie")
        # Brut 12 300 000 ; CNSS 5 % du plafond 2 500 000 ; base RTS 12 300 000 − 125 000 − 2 300 000 d'indemnités
        # RTS : 2 000 000 × 5 % + 2 000 000 × 8 % + 4 875 000 × 10 % = 747 500
        self.assertEqual((dg.salaire_brut, dg.cnss_employe, dg.base_rts, dg.irg, dg.net_a_payer),
                         (D(12300000), D(125000), D(9875000), D(747500), D(11427500)))
        self.assertEqual((dg.versement_forfaitaire, dg.taxe_apprentissage, dg.cnss_employeur),
                         (D(738000), D(246000), D(450000)))
        assistante = BulletinPaie.objects.filter(employe__nom="SOUMAH").latest("annee_paie", "mois_paie")
        # Indemnités 700 000 > 25 % de 2 200 000 : 150 000 réintégrés ; base RTS 1 540 000 → RTS 27 000
        self.assertEqual((assistante.base_rts, assistante.irg, assistante.net_a_payer),
                         (D(1540000), D(27000), D(2063000)))
        stagiaire = BulletinPaie.objects.filter(employe__nom="KOUROUMA").latest("annee_paie", "mois_paie")
        self.assertEqual((stagiaire.irg, stagiaire.net_a_payer), (D(0), D(855000)))

    def test_calculs_des_autres_modules(self):
        self._charger()
        from agence.models import Dossier
        from carburant.models import Voyage
        from prets.models import Pret
        from projets.models import Projet
        from ventes.models import Produit
        from ventes.services import solde_matricule
        with pour_entreprise(self.entreprise):
            v = Voyage.objects.get(bon_livraison__endswith="-03", date_livraison__month=Voyage.objects.filter(
                statut=Voyage.LIVRE).earliest("date_livraison").date_livraison.month)
            # 32 000 L chargés, 260 L manquants, tolérance 0,5 % = 160 L → 100 L imputés à 12 000 GNF
            self.assertEqual((v.quantite_chargee, v.ecart, v.manquant_imputable, v.penalite),
                             (D(32000), D(260), D(100), D(1200000)))
            self.assertEqual(v.montant_net, D(31740) * 180 - D(1200000))
            renovation = Projet.objects.prefetch_related("mouvements").get(nom__startswith="Rénovation")
            self.assertEqual(renovation.solde_disponible, D(-5000000))  # 45 M + 40 M − 90 M
            self.assertTrue(renovation.budget_depasse and renovation.en_retard)
            oumra = Dossier.objects.prefetch_related("prestations__paiements", "paiements").get(destination="Djeddah")
            self.assertEqual((oumra.total_vente, oumra.marge, oumra.total_paye),
                             (D(53100000), D(6600000), D(31860000)))
            statuts = dict(Pret.objects.values_list("designation", "observation"))
            self.assertEqual(statuts["Prêt scolaire — Famille Bangoura"], Pret.PAYE)
            self.assertEqual(Pret.objects.get(designation__startswith="Prêt d'équipement").reste_a_recouvrer, D(4500000))
            self.assertEqual(solde_matricule(f"ELV-{self.entreprise.pk.hex[:4].upper()}-001"), D(20000))
            self.assertEqual(Produit.objects.get(reference="SNK-01").quantite_stock, D(52))

    def test_suppression_complete_sans_toucher_aux_vraies_donnees(self):
        from carburant.models import Client
        from employes.models import Employe
        from flotte.models import Vehicule
        from paie.models import BulletinPaie
        from ventes.models import Produit
        self._charger()
        with self.assertRaises(CommandError):  # pas de double chargement
            self._charger()
        sortie = StringIO()
        call_command("charger_demo", utilisateur="Myschool", supprimer=True, stdout=sortie)
        self.assertIn("Démonstration supprimée", sortie.getvalue())
        self.assertFalse(DonneeDemo.objects.exists())
        self.assertEqual(list(Employe.objects.values_list("matricule", flat=True)), ["REEL-001"])
        self.assertFalse(BulletinPaie.objects.exists())
        with pour_entreprise(self.entreprise):
            self.assertEqual(list(Client.objects.values_list("nom", flat=True)), ["Client réel existant"])
            self.assertFalse(Produit.objects.exists())
            self.assertFalse(Vehicule.all_objects.exists())
        self._charger()  # rechargeable après suppression

    def test_utilisateur_inconnu(self):
        with self.assertRaises(CommandError):
            call_command("charger_demo", utilisateur="personne", stdout=StringIO())
