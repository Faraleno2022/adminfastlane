"""Contrôle des calculs enregistrés pour une entreprise.

    python manage.py verifier_calculs --utilisateur Myschool

Chaque montant est recalculé à partir des données saisies, avec les règles légales
codées ici indépendamment des moteurs de l'application (paie : CNSS, RTS CGI 2022,
VF, TA/ONFPP ; carburant : manquants et pénalités ; projets, agence, prêts, flotte,
ventes). La commande ne modifie rien : elle affiche les contrôles et chaque écart.
"""
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from core.models import Utilisateur
from core.tenancy import pour_entreprise

D = Decimal
ZERO = D(0)
TOLERANCE = D(1)  # GNF : écarts d'arrondi admis

# Règles légales (Guinée)
CNSS_PLANCHER, CNSS_PLAFOND, CNSS_SEUIL = D(550000), D(2500000), D(55000)
CNSS_SALARIE, CNSS_EMPLOYEUR = D(5), D(18)
TAUX_VF, TAUX_TA, TAUX_ONFPP, SEUIL_TA_ONFPP = D(6), D(2), D("1.5"), 30
PLAFOND_INDEMNITES = D("0.25")  # indemnités exonérées de RTS dans la limite de 25 % du brut
SEUIL_STAGIAIRE = D(1200000)
BAREME_RTS_CGI_2022 = [(D(0), D(1000000), D(0)), (D(1000000), D(3000000), D(5)), (D(3000000), D(5000000), D(8)),
                       (D(5000000), D(10000000), D(10)), (D(10000000), D(20000000), D(15)), (D(20000000), None, D(20))]
RUBRIQUES_CNSS_RTS = re.compile(r"CNSS|RTS|IRG|IRS|IRPP", re.IGNORECASE)


def arrondi(valeur):
    return D(valeur).quantize(D(1), rounding=ROUND_HALF_UP)


def rts_bareme(base):
    total = ZERO
    for bas, haut, taux in BAREME_RTS_CGI_2022:
        tranche = (min(base, haut) if haut else base) - bas
        if tranche > 0:
            total += tranche * taux / 100
    return arrondi(total)


def gnf(valeur):
    return f"{D(valeur or 0):,.0f}".replace(",", " ")


class Rapport:
    def __init__(self):
        self.sections = []

    def section(self, titre):
        bloc = {"titre": titre, "controles": 0, "ecarts": []}
        self.sections.append(bloc)
        return bloc


def controler(bloc, libelle, obtenu, attendu, tolerance=TOLERANCE, detail=""):
    bloc["controles"] += 1
    if obtenu is None or attendu is None or abs(D(obtenu) - D(attendu)) > tolerance:
        bloc["ecarts"].append(f"{libelle} : {gnf(obtenu)} au lieu de {gnf(attendu)}" + (f" ({detail})" if detail else ""))


def signaler(bloc, condition, message):
    bloc["controles"] += 1
    if not condition:
        bloc["ecarts"].append(message)


class Command(BaseCommand):
    help = "Recalcule et contrôle les montants enregistrés pour l'entreprise d'un utilisateur (lecture seule)."

    def add_arguments(self, parser):
        parser.add_argument("--utilisateur", required=True, help="Identifiant de connexion d'un utilisateur de l'entreprise.")
        parser.add_argument("--max-ecarts", type=int, default=25, help="Nombre d'écarts affichés par section.")

    def handle(self, *args, **options):
        user = Utilisateur.objects.filter(username__iexact=options["utilisateur"]).select_related("entreprise").first()
        if user is None or user.entreprise is None:
            raise CommandError(f"Utilisateur « {options['utilisateur']} » introuvable ou sans entreprise.")
        entreprise = user.entreprise
        rapport = Rapport()
        with pour_entreprise(entreprise):
            for controle in (self._paie, self._carburant, self._projets, self._agence, self._prets, self._flotte,
                             self._ventes, self._comptabilite):
                controle(rapport, entreprise)

        self.stdout.write(f"Contrôle des calculs — {entreprise.nom_entreprise}")
        total_ecarts = 0
        for bloc in rapport.sections:
            nb = len(bloc["ecarts"])
            total_ecarts += nb
            etat = "OK" if not nb else f"{nb} écart(s)"
            self.stdout.write(f"  [{'OK' if not nb else '!!'}] {bloc['titre']} : {bloc['controles']} contrôles — {etat}")
            for ecart in bloc["ecarts"][:options["max_ecarts"]]:
                self.stdout.write(f"       - {ecart}")
            if nb > options["max_ecarts"]:
                self.stdout.write(f"       … et {nb - options['max_ecarts']} autre(s)")
        total = sum(b["controles"] for b in rapport.sections)
        if total_ecarts:
            self.stdout.write(self.style.WARNING(f"Résultat : {total_ecarts} écart(s) sur {total} contrôles."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Résultat : aucun écart sur {total} contrôles."))

    # ------------------------------------------------------------------
    # Paie
    # ------------------------------------------------------------------
    def _paie(self, rapport, entreprise):
        from paie.models import BulletinPaie

        bloc = rapport.section("Paie (bulletins)")
        try:
            pas = D(int(getattr(entreprise.config_paie, "arrondi_net", 0) or 0))
        except Exception:
            pas = ZERO
        bulletins = (BulletinPaie.objects.filter(employe__entreprise=entreprise).exclude(statut_bulletin="brouillon")
                     .select_related("employe").prefetch_related("lignes__rubrique"))
        for b in bulletins:
            e = b.employe
            nom = f"{b.numero_bulletin} {e.nom} {b.mois_paie:02d}/{b.annee_paie}"
            brut = b.salaire_brut
            gains = [l for l in b.lignes.all() if l.rubrique.type_rubrique == "gain" and l.rubrique.inclus_brut]
            if gains:
                controler(bloc, f"{nom} — brut (somme des gains)", brut, sum((l.montant for l in gains), ZERO))

            base_cnss = ZERO if brut < CNSS_SEUIL else min(max(brut, CNSS_PLANCHER), CNSS_PLAFOND)
            controler(bloc, f"{nom} — CNSS salarié", b.cnss_employe, arrondi(base_cnss * CNSS_SALARIE / 100))
            controler(bloc, f"{nom} — CNSS employeur", b.cnss_employeur, arrondi(base_cnss * CNSS_EMPLOYEUR / 100))

            if gains:
                imposable = sum((l.montant for l in gains if l.rubrique.soumis_irg), ZERO)
                indemnites = sum((l.montant for l in gains if not l.rubrique.soumis_irg), ZERO)
                reintegration = max(indemnites - brut * PLAFOND_INDEMNITES, ZERO)
                controler(bloc, f"{nom} — base RTS", b.base_rts, arrondi(imposable - b.cnss_employe + reintegration),
                          detail=f"imposable {gnf(imposable)}, indemnités {gnf(indemnites)}")
            rts = rts_bareme(b.base_rts)
            stagiaire = e.type_contrat in ("stage", "apprentissage") and brut <= SEUIL_STAGIAIRE
            if stagiaire and b.irg == 0:
                bloc["controles"] += 1  # exonération stagiaire/apprenti
            else:
                controler(bloc, f"{nom} — RTS", b.irg, rts, detail=f"barème CGI 2022 sur {gnf(b.base_rts)}")

            autres = sum((l.montant for l in b.lignes.all()
                          if l.rubrique.type_rubrique in ("retenue", "cotisation")
                          and not RUBRIQUES_CNSS_RTS.search(l.rubrique.code_rubrique or "")), ZERO)
            net = brut - b.cnss_employe - b.irg - autres + (b.rappel_salaire or 0) - (b.retenue_trop_percu or 0)
            controler(bloc, f"{nom} — net à payer", b.net_a_payer, max(arrondi(net), ZERO),
                      tolerance=max(TOLERANCE, pas / 2), detail=f"autres retenues {gnf(autres)}")

            controler(bloc, f"{nom} — base VF (brut)", b.base_vf, brut)
            controler(bloc, f"{nom} — versement forfaitaire 6 %", b.versement_forfaitaire, arrondi(b.base_vf * TAUX_VF / 100))
            if (b.nombre_salaries or 0) < SEUIL_TA_ONFPP:
                controler(bloc, f"{nom} — taxe d'apprentissage 2 %", b.taxe_apprentissage, arrondi(b.base_vf * TAUX_TA / 100))
                controler(bloc, f"{nom} — ONFPP (moins de 30 salariés)", b.contribution_onfpp, ZERO)
            else:
                controler(bloc, f"{nom} — ONFPP 1,5 %", b.contribution_onfpp, arrondi(b.base_onfpp * TAUX_ONFPP / 100))
                controler(bloc, f"{nom} — taxe d'apprentissage (30 salariés et plus)", b.taxe_apprentissage, ZERO)
            signaler(bloc, b.net_a_payer <= brut + (b.rappel_salaire or 0), f"{nom} — net supérieur au brut")

    # ------------------------------------------------------------------
    # Transport de carburant
    # ------------------------------------------------------------------
    def _carburant(self, rapport, entreprise):
        from carburant.models import Client, Paiement, Voyage

        bloc = rapport.section("Transport de carburant")
        factures = defaultdict(lambda: ZERO)
        en_route = defaultdict(list)
        for v in Voyage.objects.select_related("citerne", "client").prefetch_related("frais"):
            if v.statut == Voyage.EN_ROUTE:
                en_route[v.citerne_id].append(v.reference)
            if v.quantite_chargee is not None:
                signaler(bloc, v.quantite_chargee <= v.citerne.capacite,
                         f"{v.reference} — {gnf(v.quantite_chargee)} L chargés pour une citerne de {gnf(v.citerne.capacite)} L")
            if v.statut != Voyage.LIVRE:
                continue
            if v.quantite_chargee is None or v.quantite_livree is None:
                signaler(bloc, False, f"{v.reference} — livré sans quantité chargée ou livrée")
                continue
            signaler(bloc, not (v.date_chargement and v.date_livraison and v.date_livraison < v.date_chargement),
                     f"{v.reference} — livraison datée avant le chargement")
            ecart = v.quantite_chargee - v.quantite_livree
            tolerance = v.quantite_chargee * v.tolerance_pct / 100
            manquant = max(ecart - tolerance, ZERO)
            penalite = arrondi(manquant * v.prix_produit)
            if v.base_facturation == Voyage.FORFAIT:
                transport = v.forfait
            else:
                litres = v.quantite_chargee if v.base_facturation == Voyage.CHARGEE else v.quantite_livree
                transport = arrondi(litres * v.tarif_litre)
            controler(bloc, f"{v.reference} — manquant imputable (L)", v.manquant_imputable, manquant, tolerance=D("0.01"),
                      detail=f"écart {gnf(ecart)} L, tolérance {v.tolerance_pct} %")
            controler(bloc, f"{v.reference} — pénalité", v.penalite, penalite)
            controler(bloc, f"{v.reference} — net facturé", v.montant_net, transport - penalite)
            controler(bloc, f"{v.reference} — marge", v.marge,
                      transport - penalite - sum((f.montant for f in v.frais.all()), ZERO))
            factures[v.client_id] += transport - penalite
        for citerne, refs in en_route.items():
            signaler(bloc, len(refs) <= 1, f"Citerne en route sur plusieurs voyages : {', '.join(refs)}")
        payes = dict(Paiement.objects.values("client").annotate(t=Sum("montant")).values_list("client", "t"))
        for client in Client.objects.all():
            solde = factures[client.pk] - (payes.get(client.pk) or ZERO)
            signaler(bloc, solde >= 0, f"Client {client.nom} — paiements supérieurs au facturé ({gnf(-solde)} de trop-perçu)")

    # ------------------------------------------------------------------
    # Projets
    # ------------------------------------------------------------------
    def _projets(self, rapport, entreprise):
        from projets.models import Mouvement, Projet, Tache

        bloc = rapport.section("Gestion de projet")
        for p in Projet.objects.prefetch_related("mouvements", "taches"):
            sommes = dict(Mouvement.objects.filter(projet=p).values("type").annotate(t=Sum("montant")).values_list("type", "t"))
            solde = (p.budget + (sommes.get(Mouvement.DEPOT) or ZERO) - (sommes.get(Mouvement.RETRAIT) or ZERO)
                     - (sommes.get(Mouvement.DEPENSE) or ZERO))
            controler(bloc, f"{p.reference} — solde disponible", p.solde_disponible, solde,
                      detail="budget + dépôts − retraits − dépenses")
            taches = [t for t in p.taches.all() if t.statut != Tache.ANNULEE]
            if taches:
                controler(bloc, f"{p.reference} — avancement (%)", p.progression,
                          arrondi(D(sum(t.progression for t in taches)) / len(taches)))
            for t in taches:
                signaler(bloc, 0 <= t.progression <= 100 and (t.statut != Tache.TERMINEE or t.progression == 100),
                         f"{p.reference} — tâche « {t.titre} » : progression {t.progression} % incohérente")
            for m in p.mouvements.all():
                signaler(bloc, m.montant > 0, f"{p.reference} — mouvement « {m.libelle} » de montant {gnf(m.montant)}")

    # ------------------------------------------------------------------
    # Agence de voyage
    # ------------------------------------------------------------------
    def _agence(self, rapport, entreprise):
        from agence.models import Dossier, Prestation

        bloc = rapport.section("Agence de voyage")
        for d in Dossier.objects.prefetch_related("prestations__paiements", "paiements"):
            valides = [p for p in d.prestations.all() if p.statut != Prestation.ANNULEE]
            vente = sum((p.quantite * p.prix_vente for p in valides), ZERO)
            achat = sum((p.quantite * p.prix_achat for p in valides), ZERO)
            paye = sum((p.montant for p in d.paiements.all()), ZERO)
            controler(bloc, f"{d.reference} — total à payer", d.total_vente, vente)
            controler(bloc, f"{d.reference} — marge", d.marge, vente - achat)
            controler(bloc, f"{d.reference} — reste à payer", d.reste_a_payer, vente - paye)
            signaler(bloc, paye <= vente or d.statut == Dossier.ANNULE,
                     f"{d.reference} — encaissé {gnf(paye)} pour un total de {gnf(vente)}")
            for p in valides:
                regle = sum((r.montant for r in p.paiements.all()), ZERO)
                signaler(bloc, regle <= p.quantite * p.prix_achat,
                         f"{d.reference} — fournisseur réglé {gnf(regle)} pour un achat de {gnf(p.quantite * p.prix_achat)}")

    # ------------------------------------------------------------------
    # Prêts
    # ------------------------------------------------------------------
    def _prets(self, rapport, entreprise):
        from prets.models import Pret

        bloc = rapport.section("Suivi des prêts")
        for p in Pret.objects.all():
            rembourse = p.remboursements.aggregate(t=Sum("montant"))["t"] or ZERO
            reste = max(p.montant_a_recouvrer - rembourse, ZERO)
            controler(bloc, f"{p.designation} — reste à recouvrer", p.reste_a_recouvrer, reste)
            controler(bloc, f"{p.designation} — à recouvrer = prêt + intérêt", p.montant_a_recouvrer,
                      p.montant_pret + p.valeur_interet)
            if p.montant_a_recouvrer > 0:
                signaler(bloc, (reste == 0) == (p.observation == Pret.PAYE),
                         f"{p.designation} — statut « {p.get_observation_display()} » avec un reste de {gnf(reste)}")

    # ------------------------------------------------------------------
    # Flotte
    # ------------------------------------------------------------------
    def _flotte(self, rapport, entreprise):
        from flotte.models import PleinCarburant, Voyage

        bloc = rapport.section("Flotte")
        for plein in PleinCarburant.objects.select_related("vehicule"):
            controler(bloc, f"Plein du {plein.date:%d/%m/%Y} ({plein.vehicule})", plein.montant,
                      arrondi(plein.litres * plein.prix_litre), detail=f"{plein.litres} L × {gnf(plein.prix_litre)}")
        for voyage in Voyage.objects.select_related("vehicule"):
            controler(bloc, f"Voyage du {voyage.date:%d/%m/%Y} ({voyage.vehicule})", voyage.montant,
                      voyage.nb_voyage * voyage.pu_voyage)

    # ------------------------------------------------------------------
    # Ventes (comptes prépayés, stock)
    # ------------------------------------------------------------------
    def _ventes(self, rapport, entreprise):
        from ventes.models import MouvementStock, Operation, Produit, Vente

        bloc = rapport.section("Ventes (comptes et stock)")
        evenements = defaultdict(list)
        for op in Operation.objects.filter(deleted=False):
            evenements[op.matricule].append((op.created_at, op.pk, "op", op.montant if op.type == Operation.DEPOT else -op.montant, op))
        for v in Vente.objects.filter(deleted=False, mode_paiement=Vente.COMPTE):
            evenements[v.matricule].append((v.created_at, v.pk, "vente", -v.montant_total, v))
        for matricule, liste in evenements.items():
            solde = ZERO
            for _, _, _, montant, obj in sorted(liste, key=lambda x: (x[0], x[2], x[1])):
                solde += montant
                controler(bloc, f"Compte {matricule} — solde après l'opération du {obj.created_at:%d/%m/%Y %H:%M}",
                          obj.solde_apres, solde)
        for v in Vente.objects.filter(deleted=False):
            controler(bloc, f"Vente {v.produit_nom} du {v.created_at:%d/%m/%Y}", v.montant_total,
                      (v.quantite * v.prix_unitaire).quantize(D("0.01")))
        for produit in Produit.objects.filter(suivi_stock=True):
            dernier = MouvementStock.objects.filter(produit=produit, deleted=False).order_by("-created_at", "-pk").first()
            if dernier:
                controler(bloc, f"Stock de « {produit.nom} »", produit.quantite_stock, dernier.stock_apres,
                          tolerance=D("0.001"), detail="dernier mouvement enregistré")
            signaler(bloc, produit.quantite_stock >= 0, f"Stock négatif pour « {produit.nom} »")

    # ------------------------------------------------------------------
    # Comptabilité (SYSCOHADA)
    # ------------------------------------------------------------------
    def _comptabilite(self, rapport, entreprise):
        from comptabilite.models import EcritureComptable, Facture, Reglement, Tiers
        from paie.models import BulletinPaie

        bloc = rapport.section("Comptabilité")
        centime = D("0.01")
        ecritures = list(EcritureComptable.objects.filter(entreprise=entreprise)
                         .select_related("exercice", "journal").prefetch_related("lignes__compte"))
        total_debit = total_credit = ZERO
        par_compte = defaultdict(lambda: ZERO)  # solde débiteur (D − C) par compte
        paie = defaultdict(lambda: {"brut": ZERO, "net": ZERO})
        for ec in ecritures:
            lignes = list(ec.lignes.all())
            debit = sum((l.montant_debit for l in lignes), ZERO)
            credit = sum((l.montant_credit for l in lignes), ZERO)
            signaler(bloc, len(lignes) >= 2, f"{ec.numero_ecriture} — écriture de moins de deux lignes")
            controler(bloc, f"{ec.numero_ecriture} — équilibre débit / crédit", debit, credit, tolerance=centime,
                      detail=ec.libelle[:60])
            signaler(bloc, ec.exercice.date_debut <= ec.date_ecriture <= ec.exercice.date_fin,
                     f"{ec.numero_ecriture} — datée du {ec.date_ecriture:%d/%m/%Y}, hors de l'exercice {ec.exercice}")
            for l in lignes:
                signaler(bloc, l.montant_debit >= 0 and l.montant_credit >= 0
                         and not (l.montant_debit > 0 and l.montant_credit > 0),
                         f"{ec.numero_ecriture} — ligne {l.compte.numero_compte} à la fois au débit et au crédit ou négative")
                par_compte[l.compte_id] += l.montant_debit - l.montant_credit
                if ec.journal.type_journal == "SA" and l.compte.numero_compte == "6611":
                    paie[(ec.date_ecriture.year, ec.date_ecriture.month)]["brut"] += l.montant_debit
                if ec.journal.type_journal == "SA" and l.compte.numero_compte == "4221":
                    paie[(ec.date_ecriture.year, ec.date_ecriture.month)]["net"] += l.montant_credit
            total_debit += debit
            total_credit += credit
        if ecritures:
            controler(bloc, "Balance générale — total des débits = total des crédits", total_debit, total_credit,
                      tolerance=centime)

        # Factures : calculs HT / TVA / TTC, paiements, concordance avec l'écriture générée
        sens = {"vente": (1, "7", "443", "41"), "acompte": (1, "7", "443", "41"),
                "avoir_client": (-1, "7", "443", "41"), "achat": (-1, "6", "445", "40"),
                "avoir_fournisseur": (1, "6", "445", "40")}
        for f in Facture.objects.filter(entreprise=entreprise).prefetch_related("lignes", "reglements"):
            lignes = list(f.lignes.all())
            for l in lignes:
                ht = (l.quantite * l.prix_unitaire).quantize(centime)
                tva = (ht * l.taux_tva / 100).quantize(centime)
                nom = f"Facture {f.numero} — ligne « {l.designation[:40]} »"
                controler(bloc, f"{nom} HT", l.montant_ht, ht, tolerance=centime)
                controler(bloc, f"{nom} TVA {l.taux_tva} %", l.montant_tva, tva, tolerance=centime)
                controler(bloc, f"{nom} TTC", l.montant_ttc, ht + tva, tolerance=centime)
            if lignes:
                controler(bloc, f"Facture {f.numero} — total HT", f.montant_ht,
                          sum((l.montant_ht for l in lignes), ZERO), tolerance=centime)
                controler(bloc, f"Facture {f.numero} — total TVA", f.montant_tva,
                          sum((l.montant_tva for l in lignes), ZERO), tolerance=centime)
                controler(bloc, f"Facture {f.numero} — total TTC", f.montant_ttc, f.montant_ht + f.montant_tva,
                          tolerance=centime)
            paye = sum((r.montant for r in f.reglements.all()), ZERO)
            controler(bloc, f"Facture {f.numero} — montant payé", f.montant_paye, paye, tolerance=centime)
            if f.statut in ("validee", "payee"):
                signaler(bloc, (f.statut == "payee") == (f.montant_ttc > 0 and paye >= f.montant_ttc),
                         f"Facture {f.numero} — statut « {f.get_statut_display()} » pour {gnf(paye)} "
                         f"payés sur {gnf(f.montant_ttc)}")
                signaler(bloc, f.ecriture_id is not None, f"Facture {f.numero} — validée sans écriture comptable")
            if f.ecriture_id and f.type_facture in sens:
                signe, produit_charge, tva_compte, tiers_compte = sens[f.type_facture]
                lignes_ec = list(f.ecriture.lignes.select_related("compte"))

                def solde(prefixe):  # crédit − débit des comptes commençant par le préfixe
                    return sum((l.montant_credit - l.montant_debit for l in lignes_ec
                                if l.compte.numero_compte.startswith(prefixe)), ZERO)
                controler(bloc, f"Facture {f.numero} — écriture : HT en classe {produit_charge}",
                          signe * solde(produit_charge), f.montant_ht, tolerance=centime)
                controler(bloc, f"Facture {f.numero} — écriture : TVA au compte {tva_compte}",
                          signe * solde(tva_compte), f.montant_tva, tolerance=centime)
                controler(bloc, f"Facture {f.numero} — écriture : TTC au compte du tiers ({tiers_compte})",
                          -signe * solde(tiers_compte), f.montant_ttc, tolerance=centime)

        for r in Reglement.objects.filter(entreprise=entreprise, ecriture__isnull=False).prefetch_related("ecriture__lignes"):
            controler(bloc, f"Règlement {r.numero} — montant de l'écriture",
                      sum((l.montant_debit for l in r.ecriture.lignes.all()), ZERO), r.montant, tolerance=centime)

        # Soldes des comptes de tiers = factures comptabilisées − règlements comptabilisés
        signes = {"vente": 1, "acompte": 1, "avoir_client": -1, "achat": -1, "avoir_fournisseur": 1}
        for t in Tiers.objects.filter(entreprise=entreprise, compte_comptable__isnull=False).select_related("compte_comptable"):
            attendu = ZERO  # solde débiteur attendu
            for f in Facture.objects.filter(tiers=t, ecriture__isnull=False).prefetch_related("reglements"):
                regle = sum((r.montant for r in f.reglements.all() if r.ecriture_id), ZERO)
                attendu += signes.get(f.type_facture, 0) * (f.montant_ttc - regle)
            controler(bloc, f"Tiers {t.code} ({t.raison_sociale[:40]}) — solde du compte {t.compte_comptable.numero_compte}",
                      par_compte[t.compte_comptable_id], attendu, tolerance=centime,
                      detail="factures comptabilisées − règlements")

        # Paie : les écritures de salaires reprennent les bulletins du mois
        for (annee, mois), montants in sorted(paie.items()):
            bulletins = (BulletinPaie.objects.filter(employe__entreprise=entreprise, annee_paie=annee, mois_paie=mois)
                         .exclude(statut_bulletin="brouillon").aggregate(brut=Sum("salaire_brut"), net=Sum("net_a_payer")))
            controler(bloc, f"Salaires {mois:02d}/{annee} — compte 6611 = brut des bulletins", montants["brut"],
                      bulletins["brut"] or ZERO)
            controler(bloc, f"Salaires {mois:02d}/{annee} — compte 4221 = nets des bulletins", montants["net"],
                      bulletins["net"] or ZERO)
