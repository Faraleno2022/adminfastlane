import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.urls import reverse_lazy

from .mixins import BaseCreer, BaseListe, BaseModifier, BaseSupprimer
from .permissions import peut_saisir

from .forms import ArticleForm, MouvementStockForm
from .models import Article, MouvementStock


def _totaux_mouvements():
    """Retourne deux dicts {article_id: quantité} pour entrées et sorties."""
    ent, sor = {}, {}
    for r in (MouvementStock.objects.filter(type=MouvementStock.ENTREE)
              .values("article").annotate(s=Sum("quantite"))):
        ent[r["article"]] = r["s"] or Decimal("0")
    for r in (MouvementStock.objects.filter(type=MouvementStock.SORTIE)
              .values("article").annotate(s=Sum("quantite"))):
        sor[r["article"]] = r["s"] or Decimal("0")
    return ent, sor


def _lignes_inventaire():
    """Construit les lignes d'inventaire avec stock et statut calculés."""
    ent, sor = _totaux_mouvements()
    lignes = []
    for a in Article.objects.all():
        e = ent.get(a.id, Decimal("0"))
        s = sor.get(a.id, Decimal("0"))
        stock = (a.stock_initial or Decimal("0")) + e - s
        lignes.append({
            "article": a,
            "entrees": e,
            "sorties": s,
            "stock_actuel": stock,
            "statut": Article.statut_pour(stock, a.seuil_mini),
        })
    return lignes


# --------------------------------------------------------------- Inventaire
@login_required
def inventaire(request):
    lignes = _lignes_inventaire()

    q = (request.GET.get("q") or "").strip().lower()
    categorie = request.GET.get("categorie") or ""
    statut = request.GET.get("statut") or ""
    if q:
        lignes = [l for l in lignes if q in l["article"].code.lower()
                  or q in l["article"].designation.lower()]
    if categorie:
        lignes = [l for l in lignes if l["article"].categorie == categorie]
    if statut:
        lignes = [l for l in lignes if l["statut"] == statut]

    categories = sorted({a.categorie for a in Article.objects.all() if a.categorie})
    contexte = {
        "titre": "Inventaire",
        "lignes": lignes,
        "categories": categories,
        "q": q, "categorie_sel": categorie, "statut_sel": statut,
        "peut_saisir": peut_saisir(request.user),
    }
    return render(request, "flotte/stock/inventaire.html", contexte)


# ----------------------------------------------------------------- Synthèse
@login_required
def synthese(request):
    lignes = _lignes_inventaire()
    nb_articles = len(lignes)
    qte_totale = sum((l["stock_actuel"] for l in lignes), Decimal("0"))
    nb_alerte = sum(1 for l in lignes if l["statut"] == Article.ALERTE)
    nb_rupture = sum(1 for l in lignes if l["statut"] == Article.RUPTURE)

    par_cat = {}
    for l in lignes:
        cat = l["article"].categorie or "(Sans catégorie)"
        d = par_cat.setdefault(cat, {"nb": 0, "qte": Decimal("0")})
        d["nb"] += 1
        d["qte"] += l["stock_actuel"]
    cats = sorted(par_cat.items(), key=lambda kv: kv[1]["qte"], reverse=True)

    contexte = {
        "titre": "Synthèse du stock",
        "nb_articles": nb_articles,
        "qte_totale": qte_totale,
        "nb_alerte": nb_alerte,
        "nb_rupture": nb_rupture,
        "par_categorie": cats,
        "alertes": [l for l in lignes if l["statut"] in (Article.ALERTE, Article.RUPTURE)],
        "chart_cat": json.dumps({
            "labels": [c for c, _ in cats],
            "valeurs": [float(d["qte"]) for _, d in cats],
        }),
    }
    return render(request, "flotte/stock/synthese.html", contexte)


# ------------------------------------------------------------ Articles CRUD
class ArticleCreer(BaseCreer):
    model = Article
    form_class = ArticleForm
    success_url = reverse_lazy("flotte:inventaire")
    titre = "Ajouter un article"


class ArticleModifier(BaseModifier):
    model = Article
    form_class = ArticleForm
    success_url = reverse_lazy("flotte:inventaire")
    titre = "Modifier l'article"


class ArticleSupprimer(BaseSupprimer):
    model = Article
    success_url = reverse_lazy("flotte:inventaire")


# ----------------------------------------------------------- Mouvements CRUD
class MouvementListe(BaseListe):
    model = MouvementStock
    titre = "Mouvements de stock"
    colonnes = [
        ("Date", "date"),
        ("Article", "article"),
        ("Type", "get_type_display"),
        ("Quantité", "quantite"),
        ("Motif / Bénéficiaire", "motif"),
        ("Responsable", "responsable"),
    ]
    url_creer = "flotte:mouvement_creer"
    url_modifier = "flotte:mouvement_modifier"
    url_supprimer = "flotte:mouvement_supprimer"

    def get_queryset(self):
        return super().get_queryset().select_related("article")


class MouvementCreer(BaseCreer):
    model = MouvementStock
    form_class = MouvementStockForm
    success_url = reverse_lazy("flotte:mouvement_liste")
    titre = "Enregistrer un mouvement"


class MouvementModifier(BaseModifier):
    model = MouvementStock
    form_class = MouvementStockForm
    success_url = reverse_lazy("flotte:mouvement_liste")
    titre = "Modifier le mouvement"


class MouvementSupprimer(BaseSupprimer):
    model = MouvementStock
    success_url = reverse_lazy("flotte:mouvement_liste")
