"""
Module Gestion du Stock — Vues
Tableau de bord, articles, catégories, fournisseurs, mouvements de stock
(entrées / sorties / ajustements), inventaires physiques et rapports.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Sum, F, Max, DecimalField, ExpressionWrapper

from django.utils import timezone

from core.decorators import reauth_required

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock,
    Inventaire, LigneInventaire, Depot, StockArticleDepot, Transfert,
    CommandeFournisseur, LigneCommande, Reception, LigneReception,
    FactureFournisseur, PaiementFournisseur,
)
from .forms import (
    CategorieArticleForm, FournisseurForm, ArticleForm,
    MouvementStockForm, InventaireForm, DepotForm, TransfertForm,
    CommandeFournisseurForm, LigneCommandeForm, ReceptionForm,
    FactureFournisseurForm, PaiementFournisseurForm,
)

# Nombre de jours sans mouvement au-delà duquel un article est « dormant ».
JOURS_DORMANT = 90


def appliquer_mouvement_depot(article, depot, type_mouvement, quantite):
    """Applique un mouvement au stock d'un dépôt et renvoie (avant, apres).

    Doit être appelé dans une transaction. Met à jour la ligne de stock par
    dépôt puis recalcule le total global de l'article.
    """
    sad, _ = StockArticleDepot.objects.select_for_update().get_or_create(
        article=article, depot=depot, defaults={'quantite': Decimal('0')}
    )
    avant = sad.quantite or Decimal('0')
    if type_mouvement == 'entree':
        apres = avant + quantite
    elif type_mouvement == 'sortie':
        apres = avant - quantite
    else:  # ajustement : la quantité devient le stock réel du dépôt
        apres = quantite
    sad.quantite = apres
    sad.save(update_fields=['quantite'])
    article.recalculer_total(sauver=True)
    return avant, apres


def get_depot_defaut(entreprise):
    """Renvoie le dépôt par défaut de l'entreprise (ou le premier actif)."""
    return (Depot.objects.filter(entreprise=entreprise, par_defaut=True, actif=True).first()
            or Depot.objects.filter(entreprise=entreprise, actif=True).first())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def stock_required(view_func):
    """Vérifie que l'utilisateur est rattaché à une entreprise active."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:login')
        if not getattr(request.user, 'entreprise', None):
            messages.error(request, "Vous devez être associé à une entreprise.")
            return redirect('dashboard:index')
        return view_func(request, *args, **kwargs)
    return wrapper


def _generer_reference(model, entreprise, prefixe):
    """Génère une référence séquentielle : PREFIXE-AAAA-0001 par entreprise."""
    annee = datetime.now().year
    base = f"{prefixe}-{annee}-"
    for _ in range(10):
        with transaction.atomic():
            dernier = (model.objects
                       .select_for_update()
                       .filter(entreprise=entreprise, reference__startswith=base)
                       .order_by('-reference')
                       .first())
            if dernier:
                try:
                    numero = int(dernier.reference.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    numero = 1
            else:
                numero = 1
            nouvelle = f"{base}{numero:04d}"
            if not model.objects.filter(entreprise=entreprise, reference=nouvelle).exists():
                return nouvelle
    import time
    return f"{base}{int(time.time()) % 10000:04d}"


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def dashboard(request):
    entreprise = request.user.entreprise
    articles = Article.objects.filter(entreprise=entreprise, actif=True)

    valeur_expr = ExpressionWrapper(
        F('quantite_stock') * F('prix_achat'), output_field=DecimalField(max_digits=18, decimal_places=2)
    )
    valeur_totale = (articles.aggregate(total=Sum(valeur_expr))['total'] or Decimal('0'))

    articles_alerte = [a for a in articles if a.en_alerte and not a.en_rupture]
    articles_rupture = [a for a in articles if a.en_rupture]
    articles_surstock = [a for a in articles if a.en_surstock]

    derniers_mouvements = (MouvementStock.objects
                           .filter(entreprise=entreprise)
                           .select_related('article', 'depot')[:10])

    # Articles dormants : aucun mouvement depuis JOURS_DORMANT jours (et stock > 0).
    limite_dormant = timezone.now() - timedelta(days=JOURS_DORMANT)
    articles_dormants = list(
        articles.filter(quantite_stock__gt=0)
        .annotate(dernier_mvt=Max('mouvements__date_mouvement'))
        .filter(Q(dernier_mvt__lt=limite_dormant) | Q(dernier_mvt__isnull=True))[:10]
    )

    stats = {
        'total_articles': articles.count(),
        'total_depots': Depot.objects.filter(entreprise=entreprise, actif=True).count(),
        'total_categories': CategorieArticle.objects.filter(entreprise=entreprise).count(),
        'total_fournisseurs': Fournisseur.objects.filter(entreprise=entreprise).count(),
        'valeur_totale': valeur_totale,
        'nb_alerte': len(articles_alerte),
        'nb_rupture': len(articles_rupture),
        'nb_surstock': len(articles_surstock),
        'nb_dormants': len(articles_dormants),
        'mouvements_jour': MouvementStock.objects.filter(
            entreprise=entreprise, date_mouvement__date=timezone.now().date()
        ).count(),
        'inventaires_en_cours': Inventaire.objects.filter(entreprise=entreprise, statut='en_cours').count(),
    }

    return render(request, 'stock/dashboard.html', {
        'stats': stats,
        'articles_alerte': articles_alerte[:10],
        'articles_rupture': articles_rupture[:10],
        'articles_surstock': articles_surstock[:10],
        'articles_dormants': articles_dormants,
        'derniers_mouvements': derniers_mouvements,
    })


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def article_list(request):
    entreprise = request.user.entreprise
    articles = Article.objects.filter(entreprise=entreprise).select_related('categorie', 'fournisseur')

    categorie = request.GET.get('categorie', '')
    etat = request.GET.get('etat', '')
    recherche = request.GET.get('q', '')
    if categorie:
        articles = articles.filter(categorie_id=categorie)
    if recherche:
        articles = articles.filter(
            Q(designation__icontains=recherche) | Q(reference__icontains=recherche) |
            Q(emplacement__icontains=recherche)
        )
    articles = list(articles)
    if etat == 'rupture':
        articles = [a for a in articles if a.en_rupture]
    elif etat == 'alerte':
        articles = [a for a in articles if a.en_alerte]
    elif etat == 'surstock':
        articles = [a for a in articles if a.en_surstock]
    elif etat == 'dormant':
        from django.utils import timezone as _tz
        limite = _tz.now() - timedelta(days=JOURS_DORMANT)
        ids = set(Article.objects.filter(entreprise=entreprise, quantite_stock__gt=0)
                  .annotate(dm=Max('mouvements__date_mouvement'))
                  .filter(Q(dm__lt=limite) | Q(dm__isnull=True)).values_list('id', flat=True))
        articles = [a for a in articles if a.pk in ids]

    return render(request, 'stock/article_list.html', {
        'articles': articles,
        'categories': CategorieArticle.objects.filter(entreprise=entreprise),
        'categorie_filter': categorie,
        'etat_filter': etat,
        'recherche': recherche,
    })


@reauth_required
@login_required
@stock_required
def article_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = ArticleForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            article = form.save(commit=False)
            article.entreprise = entreprise
            article.cree_par = request.user
            article.save()
            messages.success(request, f"Article « {article.designation} » créé.")
            return redirect('stock:article_list')
    else:
        form = ArticleForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouvel article', 'retour': 'stock:article_list',
    })


@reauth_required
@login_required
@stock_required
def article_edit(request, pk):
    entreprise = request.user.entreprise
    article = get_object_or_404(Article, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        form = ArticleForm(request.POST, instance=article, entreprise=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Article mis à jour.")
            return redirect('stock:article_list')
    else:
        form = ArticleForm(instance=article, entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': f'Modifier {article.reference}',
        'retour': 'stock:article_list',
        'note_stock': "La quantité en stock se modifie via les mouvements, pas ici.",
    })


@reauth_required
@login_required
@stock_required
def article_detail(request, pk):
    entreprise = request.user.entreprise
    article = get_object_or_404(Article, pk=pk, entreprise=entreprise)
    mouvements = article.mouvements.select_related('fournisseur', 'depot')[:50]
    stocks_depots = article.stocks_depots.select_related('depot').filter(depot__actif=True)
    return render(request, 'stock/article_detail.html', {
        'article': article, 'mouvements': mouvements, 'stocks_depots': stocks_depots,
    })


@reauth_required
@login_required
@stock_required
def article_delete(request, pk):
    article = get_object_or_404(Article, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        article.delete()
        messages.success(request, "Article supprimé.")
        return redirect('stock:article_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': str(article), 'retour': 'stock:article_list',
    })


# ---------------------------------------------------------------------------
# Catégories
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def categorie_list(request):
    entreprise = request.user.entreprise
    categories = (CategorieArticle.objects.filter(entreprise=entreprise)
                  .annotate(nb_articles=Count('articles')))
    return render(request, 'stock/categorie_list.html', {'categories': categories})


@reauth_required
@login_required
@stock_required
def categorie_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = CategorieArticleForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.entreprise = entreprise
            c.save()
            messages.success(request, "Catégorie ajoutée.")
            return redirect('stock:categorie_list')
    else:
        form = CategorieArticleForm()
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouvelle catégorie', 'retour': 'stock:categorie_list',
    })


@reauth_required
@login_required
@stock_required
def categorie_edit(request, pk):
    c = get_object_or_404(CategorieArticle, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = CategorieArticleForm(request.POST, instance=c)
        if form.is_valid():
            form.save()
            messages.success(request, "Catégorie mise à jour.")
            return redirect('stock:categorie_list')
    else:
        form = CategorieArticleForm(instance=c)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Modifier la catégorie', 'retour': 'stock:categorie_list',
    })


@reauth_required
@login_required
@stock_required
def categorie_delete(request, pk):
    c = get_object_or_404(CategorieArticle, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        c.delete()
        messages.success(request, "Catégorie supprimée.")
        return redirect('stock:categorie_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': c.nom, 'retour': 'stock:categorie_list',
    })


# ---------------------------------------------------------------------------
# Fournisseurs
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def fournisseur_list(request):
    entreprise = request.user.entreprise
    fournisseurs = Fournisseur.objects.filter(entreprise=entreprise)
    recherche = request.GET.get('q', '')
    if recherche:
        fournisseurs = fournisseurs.filter(
            Q(nom__icontains=recherche) | Q(contact__icontains=recherche) |
            Q(email__icontains=recherche) | Q(telephone__icontains=recherche)
        )
    return render(request, 'stock/fournisseur_list.html', {
        'fournisseurs': fournisseurs, 'recherche': recherche,
    })


@reauth_required
@login_required
@stock_required
def fournisseur_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = FournisseurForm(request.POST)
        if form.is_valid():
            f = form.save(commit=False)
            f.entreprise = entreprise
            f.save()
            messages.success(request, "Fournisseur ajouté.")
            return redirect('stock:fournisseur_list')
    else:
        form = FournisseurForm()
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau fournisseur', 'retour': 'stock:fournisseur_list',
    })


@reauth_required
@login_required
@stock_required
def fournisseur_edit(request, pk):
    f = get_object_or_404(Fournisseur, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = FournisseurForm(request.POST, instance=f)
        if form.is_valid():
            form.save()
            messages.success(request, "Fournisseur mis à jour.")
            return redirect('stock:fournisseur_list')
    else:
        form = FournisseurForm(instance=f)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Modifier le fournisseur', 'retour': 'stock:fournisseur_list',
    })


@reauth_required
@login_required
@stock_required
def fournisseur_delete(request, pk):
    f = get_object_or_404(Fournisseur, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        f.delete()
        messages.success(request, "Fournisseur supprimé.")
        return redirect('stock:fournisseur_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': f.nom, 'retour': 'stock:fournisseur_list',
    })


# ---------------------------------------------------------------------------
# Mouvements de stock
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def mouvement_list(request):
    entreprise = request.user.entreprise
    mouvements = (MouvementStock.objects.filter(entreprise=entreprise)
                  .select_related('article', 'fournisseur'))
    type_filter = request.GET.get('type', '')
    article_filter = request.GET.get('article', '')
    if type_filter:
        mouvements = mouvements.filter(type_mouvement=type_filter)
    if article_filter:
        mouvements = mouvements.filter(article_id=article_filter)
    return render(request, 'stock/mouvement_list.html', {
        'mouvements': mouvements,
        'types': MouvementStock.TYPES,
        'articles': Article.objects.filter(entreprise=entreprise, actif=True),
        'type_filter': type_filter,
        'article_filter': article_filter,
    })


@reauth_required
@login_required
@stock_required
def mouvement_create(request):
    entreprise = request.user.entreprise
    type_initial = request.GET.get('type', 'entree')
    if not Depot.objects.filter(entreprise=entreprise, actif=True).exists():
        messages.warning(request, "Créez d'abord un dépôt avant d'enregistrer des mouvements.")
        return redirect('stock:depot_create')

    if request.method == 'POST':
        form = MouvementStockForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            with transaction.atomic():
                mouvement = form.save(commit=False)
                article = Article.objects.select_for_update().get(
                    pk=mouvement.article_id, entreprise=entreprise
                )
                depot = mouvement.depot
                quantite = mouvement.quantite
                stock_depot = article.stock_dans(depot)

                if mouvement.type_mouvement == 'sortie' and quantite > stock_depot:
                    messages.error(
                        request,
                        f"Stock insuffisant dans {depot.nom} : {stock_depot} disponible(s), "
                        f"sortie de {quantite} demandée."
                    )
                    return render(request, 'stock/form.html', {
                        'form': form, 'titre': 'Nouveau mouvement de stock',
                        'retour': 'stock:mouvement_list',
                    })

                avant, apres = appliquer_mouvement_depot(
                    article, depot, mouvement.type_mouvement, quantite
                )
                mouvement.entreprise = entreprise
                mouvement.quantite_avant = avant
                mouvement.quantite_apres = apres
                mouvement.cree_par = request.user
                mouvement.save()

            messages.success(
                request,
                f"Mouvement enregistré. Stock de « {article.designation} » dans {depot.nom} : {apres}."
            )
            return redirect('stock:mouvement_list')
    else:
        initial = {'type_mouvement': type_initial}
        defaut = get_depot_defaut(entreprise)
        if defaut:
            initial['depot'] = defaut.pk
        form = MouvementStockForm(entreprise=entreprise, initial=initial)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau mouvement de stock', 'retour': 'stock:mouvement_list',
    })


# ---------------------------------------------------------------------------
# Dépôts
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def depot_list(request):
    entreprise = request.user.entreprise
    valeur_expr = ExpressionWrapper(
        F('quantite') * F('article__prix_achat'), output_field=DecimalField(max_digits=18, decimal_places=2)
    )
    depots = (Depot.objects.filter(entreprise=entreprise)
              .annotate(nb_articles=Count('stocks_articles', distinct=True),
                        valeur=Sum(valeur_expr)))
    return render(request, 'stock/depot_list.html', {'depots': depots, 'types': Depot.TYPES})


@reauth_required
@login_required
@stock_required
def depot_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = DepotForm(request.POST)
        if form.is_valid():
            depot = form.save(commit=False)
            depot.entreprise = entreprise
            # Un seul dépôt par défaut par entreprise.
            if depot.par_defaut:
                Depot.objects.filter(entreprise=entreprise, par_defaut=True).update(par_defaut=False)
            elif not Depot.objects.filter(entreprise=entreprise).exists():
                depot.par_defaut = True  # le premier dépôt devient celui par défaut
            depot.save()
            messages.success(request, f"Dépôt « {depot.nom} » créé.")
            return redirect('stock:depot_list')
    else:
        form = DepotForm()
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau dépôt', 'retour': 'stock:depot_list',
    })


@reauth_required
@login_required
@stock_required
def depot_edit(request, pk):
    entreprise = request.user.entreprise
    depot = get_object_or_404(Depot, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        form = DepotForm(request.POST, instance=depot)
        if form.is_valid():
            d = form.save(commit=False)
            if d.par_defaut:
                Depot.objects.filter(entreprise=entreprise, par_defaut=True).exclude(pk=d.pk).update(par_defaut=False)
            d.save()
            messages.success(request, "Dépôt mis à jour.")
            return redirect('stock:depot_list')
    else:
        form = DepotForm(instance=depot)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': f'Modifier {depot.nom}', 'retour': 'stock:depot_list',
    })


@reauth_required
@login_required
@stock_required
def depot_delete(request, pk):
    depot = get_object_or_404(Depot, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        if depot.stocks_articles.filter(quantite__gt=0).exists():
            messages.error(request, "Impossible de supprimer un dépôt contenant du stock. Transférez-le d'abord.")
            return redirect('stock:depot_list')
        depot.delete()
        messages.success(request, "Dépôt supprimé.")
        return redirect('stock:depot_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': depot.nom, 'retour': 'stock:depot_list',
    })


# ---------------------------------------------------------------------------
# Transferts entre dépôts
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def transfert_list(request):
    entreprise = request.user.entreprise
    transferts = (Transfert.objects.filter(entreprise=entreprise)
                  .select_related('article', 'depot_source', 'depot_destination'))
    return render(request, 'stock/transfert_list.html', {'transferts': transferts})


@reauth_required
@login_required
@stock_required
def transfert_create(request):
    entreprise = request.user.entreprise
    if Depot.objects.filter(entreprise=entreprise, actif=True).count() < 2:
        messages.warning(request, "Il faut au moins deux dépôts actifs pour effectuer un transfert.")
        return redirect('stock:depot_list')

    if request.method == 'POST':
        form = TransfertForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            with transaction.atomic():
                transfert = form.save(commit=False)
                article = Article.objects.select_for_update().get(pk=transfert.article_id, entreprise=entreprise)
                transfert.entreprise = entreprise
                transfert.reference = _generer_reference(Transfert, entreprise, 'TRF')
                transfert.cree_par = request.user
                transfert.save()

                ref = transfert.reference
                motif = transfert.motif or f"Transfert {ref}"
                # Sortie du dépôt source
                av_s, ap_s = appliquer_mouvement_depot(article, transfert.depot_source, 'sortie', transfert.quantite)
                MouvementStock.objects.create(
                    entreprise=entreprise, article=article, depot=transfert.depot_source,
                    type_mouvement='transfert', quantite=transfert.quantite,
                    quantite_avant=av_s, quantite_apres=ap_s, prix_unitaire=article.prix_achat,
                    motif=f"Transfert vers {transfert.depot_destination.nom}", reference_document=ref,
                    date_mouvement=transfert.date_transfert, cree_par=request.user,
                )
                # Entrée dans le dépôt destination
                av_d, ap_d = appliquer_mouvement_depot(article, transfert.depot_destination, 'entree', transfert.quantite)
                MouvementStock.objects.create(
                    entreprise=entreprise, article=article, depot=transfert.depot_destination,
                    type_mouvement='transfert', quantite=transfert.quantite,
                    quantite_avant=av_d, quantite_apres=ap_d, prix_unitaire=article.prix_achat,
                    motif=f"Transfert depuis {transfert.depot_source.nom}", reference_document=ref,
                    date_mouvement=transfert.date_transfert, cree_par=request.user,
                )
            messages.success(request, f"Transfert {ref} effectué : {transfert.quantite} déplacée(s).")
            return redirect('stock:transfert_list')
    else:
        form = TransfertForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau transfert entre dépôts', 'retour': 'stock:transfert_list',
    })


# ---------------------------------------------------------------------------
# Inventaires
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def inventaire_list(request):
    entreprise = request.user.entreprise
    inventaires = Inventaire.objects.filter(entreprise=entreprise)
    return render(request, 'stock/inventaire_list.html', {
        'inventaires': inventaires, 'statuts': Inventaire.STATUTS,
    })


@reauth_required
@login_required
@stock_required
def inventaire_create(request):
    entreprise = request.user.entreprise
    if not Depot.objects.filter(entreprise=entreprise, actif=True).exists():
        messages.warning(request, "Créez d'abord un dépôt avant de lancer un inventaire.")
        return redirect('stock:depot_create')

    if request.method == 'POST':
        form = InventaireForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            with transaction.atomic():
                inv = form.save(commit=False)
                inv.entreprise = entreprise
                inv.reference = _generer_reference(Inventaire, entreprise, 'INV')
                inv.cree_par = request.user
                inv.save()
                # Articles à inventorier (du dépôt choisi), filtrés par catégorie si demandé.
                articles = Article.objects.filter(entreprise=entreprise, actif=True)
                categorie = form.cleaned_data.get('categorie')
                if categorie:
                    articles = articles.filter(categorie=categorie)
                # Stock théorique = stock de l'article DANS le dépôt inventorié.
                lignes = []
                for a in articles:
                    theorique = a.stock_dans(inv.depot)
                    lignes.append(LigneInventaire(
                        inventaire=inv, article=a,
                        quantite_theorique=theorique,
                        quantite_physique=theorique,
                        ecart=0,
                    ))
                LigneInventaire.objects.bulk_create(lignes)
            messages.success(request, f"Inventaire {inv.reference} créé ({inv.depot.nom}, {len(lignes)} article(s)).")
            return redirect('stock:inventaire_detail', pk=inv.pk)
    else:
        form = InventaireForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouvel inventaire', 'retour': 'stock:inventaire_list',
    })


@reauth_required
@login_required
@stock_required
def inventaire_detail(request, pk):
    entreprise = request.user.entreprise
    inv = get_object_or_404(Inventaire, pk=pk, entreprise=entreprise)
    lignes = inv.lignes.select_related('article')

    if request.method == 'POST' and inv.statut == 'en_cours':
        # Enregistrer les quantités physiques saisies.
        for ligne in lignes:
            champ = f'qte_{ligne.pk}'
            if champ in request.POST:
                valeur = request.POST.get(champ, '').strip().replace(',', '.')
                try:
                    ligne.quantite_physique = Decimal(valeur) if valeur else Decimal('0')
                    ligne.save()  # recalcule l'écart
                except (ValueError, ArithmeticError):
                    continue
        messages.success(request, "Comptage enregistré.")
        return redirect('stock:inventaire_detail', pk=inv.pk)

    return render(request, 'stock/inventaire_detail.html', {
        'inventaire': inv, 'lignes': lignes,
    })


@reauth_required
@login_required
@stock_required
def inventaire_valider(request, pk):
    """Valide l'inventaire : applique les écarts au stock via des ajustements."""
    entreprise = request.user.entreprise
    inv = get_object_or_404(Inventaire, pk=pk, entreprise=entreprise)
    if inv.statut != 'en_cours':
        messages.warning(request, "Cet inventaire est déjà clôturé.")
        return redirect('stock:inventaire_detail', pk=inv.pk)

    if request.method == 'POST':
        nb_ajustements = 0
        depot = inv.depot
        with transaction.atomic():
            for ligne in inv.lignes.select_related('article'):
                if ligne.ecart == 0:
                    continue
                article = Article.objects.select_for_update().get(pk=ligne.article_id)
                # Ajustement du stock DANS le dépôt inventorié vers la quantité comptée.
                avant, apres = appliquer_mouvement_depot(
                    article, depot, 'ajustement', ligne.quantite_physique
                )
                MouvementStock.objects.create(
                    entreprise=entreprise,
                    article=article,
                    depot=depot,
                    type_mouvement='ajustement',
                    quantite=ligne.quantite_physique,
                    quantite_avant=avant,
                    quantite_apres=apres,
                    prix_unitaire=article.prix_achat,
                    motif=f"Ajustement inventaire {inv.reference} ({depot.nom})",
                    reference_document=inv.reference,
                    cree_par=request.user,
                )
                nb_ajustements += 1

            inv.statut = 'valide'
            inv.date_validation = timezone.now()
            inv.save(update_fields=['statut', 'date_validation'])

        messages.success(request, f"Inventaire {inv.reference} validé. {nb_ajustements} ajustement(s) appliqué(s).")
        return redirect('stock:inventaire_detail', pk=inv.pk)

    return render(request, 'stock/confirm_action.html', {
        'titre': 'Valider l\'inventaire',
        'message': f"Valider l'inventaire {inv.reference} ajustera le stock des articles présentant un écart. "
                   "Cette action est irréversible.",
        'bouton': 'Valider et ajuster le stock',
        'retour': 'stock:inventaire_detail', 'retour_pk': inv.pk,
    })


@reauth_required
@login_required
@stock_required
def inventaire_delete(request, pk):
    inv = get_object_or_404(Inventaire, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        inv.delete()
        messages.success(request, "Inventaire supprimé.")
        return redirect('stock:inventaire_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': inv.reference, 'retour': 'stock:inventaire_list',
    })


# ---------------------------------------------------------------------------
# Rapports
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def rapports(request):
    entreprise = request.user.entreprise
    articles = Article.objects.filter(entreprise=entreprise, actif=True).select_related('categorie')

    valeur_expr = ExpressionWrapper(
        F('quantite_stock') * F('prix_achat'), output_field=DecimalField(max_digits=18, decimal_places=2)
    )

    valeur_par_categorie = list(
        articles.values('categorie__nom')
        .annotate(valeur=Sum(valeur_expr), nb=Count('id'))
        .order_by('-valeur')
    )

    mouvements_par_type = list(
        MouvementStock.objects.filter(entreprise=entreprise)
        .values('type_mouvement').annotate(n=Count('id'))
    )

    articles_alerte = [a for a in articles if a.en_alerte]
    valeur_totale = articles.aggregate(total=Sum(valeur_expr))['total'] or Decimal('0')

    return render(request, 'stock/rapports.html', {
        'valeur_par_categorie': valeur_par_categorie,
        'mouvements_par_type': mouvements_par_type,
        'articles_alerte': articles_alerte,
        'valeur_totale': valeur_totale,
        'nb_articles': articles.count(),
    })


# ===========================================================================
# ACHATS — Commandes fournisseurs
# ===========================================================================
@reauth_required
@login_required
@stock_required
def commande_list(request):
    entreprise = request.user.entreprise
    commandes = (CommandeFournisseur.objects.filter(entreprise=entreprise)
                 .select_related('fournisseur', 'depot').prefetch_related('lignes'))
    statut = request.GET.get('statut', '')
    if statut:
        commandes = commandes.filter(statut=statut)
    return render(request, 'stock/commande_list.html', {
        'commandes': commandes, 'statuts': CommandeFournisseur.STATUTS, 'statut_filter': statut,
    })


@reauth_required
@login_required
@stock_required
def commande_create(request):
    entreprise = request.user.entreprise
    if not Fournisseur.objects.filter(entreprise=entreprise, actif=True).exists():
        messages.warning(request, "Créez d'abord un fournisseur.")
        return redirect('stock:fournisseur_create')
    if request.method == 'POST':
        form = CommandeFournisseurForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            commande = form.save(commit=False)
            commande.entreprise = entreprise
            commande.reference = _generer_reference(CommandeFournisseur, entreprise, 'BC')
            commande.cree_par = request.user
            commande.save()
            messages.success(request, f"Commande {commande.reference} créée. Ajoutez les articles.")
            return redirect('stock:commande_detail', pk=commande.pk)
    else:
        form = CommandeFournisseurForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': "Nouvelle demande d'achat", 'retour': 'stock:commande_list',
    })


@reauth_required
@login_required
@stock_required
def commande_detail(request, pk):
    entreprise = request.user.entreprise
    commande = get_object_or_404(CommandeFournisseur, pk=pk, entreprise=entreprise)
    lignes = commande.lignes.select_related('article')

    if request.method == 'POST':
        if not commande.modifiable:
            messages.error(request, "Cette commande ne peut plus être modifiée.")
            return redirect('stock:commande_detail', pk=pk)
        form = LigneCommandeForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            ligne = form.save(commit=False)
            ligne.commande = commande
            ligne.save()
            messages.success(request, "Article ajouté à la commande.")
            return redirect('stock:commande_detail', pk=pk)
    else:
        form = LigneCommandeForm(entreprise=entreprise)

    return render(request, 'stock/commande_detail.html', {
        'commande': commande, 'lignes': lignes, 'form': form,
        'receptions': commande.receptions.select_related('depot').prefetch_related('lignes'),
        'factures': commande.factures.all(),
    })


@reauth_required
@login_required
@stock_required
def commande_edit(request, pk):
    entreprise = request.user.entreprise
    commande = get_object_or_404(CommandeFournisseur, pk=pk, entreprise=entreprise)
    if not commande.modifiable:
        messages.error(request, "Cette commande ne peut plus être modifiée.")
        return redirect('stock:commande_detail', pk=pk)
    if request.method == 'POST':
        form = CommandeFournisseurForm(request.POST, instance=commande, entreprise=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Commande mise à jour.")
            return redirect('stock:commande_detail', pk=pk)
    else:
        form = CommandeFournisseurForm(instance=commande, entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': f'Modifier {commande.reference}', 'retour': 'stock:commande_detail',
        'retour_pk': commande.pk,
    })


@reauth_required
@login_required
@stock_required
def ligne_commande_delete(request, pk):
    ligne = get_object_or_404(LigneCommande, pk=pk, commande__entreprise=request.user.entreprise)
    commande_pk = ligne.commande_id
    if ligne.commande.modifiable:
        ligne.delete()
        messages.success(request, "Ligne supprimée.")
    else:
        messages.error(request, "Commande non modifiable.")
    return redirect('stock:commande_detail', pk=commande_pk)


@reauth_required
@login_required
@stock_required
def commande_valider(request, pk):
    commande = get_object_or_404(CommandeFournisseur, pk=pk, entreprise=request.user.entreprise)
    if commande.statut != 'brouillon':
        messages.warning(request, "Cette commande est déjà validée.")
        return redirect('stock:commande_detail', pk=pk)
    if not commande.lignes.exists():
        messages.error(request, "Ajoutez au moins un article avant de valider.")
        return redirect('stock:commande_detail', pk=pk)
    commande.statut = 'validee'
    commande.validee_par = request.user
    commande.date_validation = timezone.now()
    commande.save(update_fields=['statut', 'validee_par', 'date_validation'])
    messages.success(request, f"Bon de commande {commande.reference} validé.")
    return redirect('stock:commande_detail', pk=pk)


@reauth_required
@login_required
@stock_required
def commande_annuler(request, pk):
    commande = get_object_or_404(CommandeFournisseur, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        if commande.statut in ('recue',):
            messages.error(request, "Impossible d'annuler une commande déjà reçue.")
        else:
            commande.statut = 'annulee'
            commande.save(update_fields=['statut'])
            messages.success(request, "Commande annulée.")
        return redirect('stock:commande_detail', pk=pk)
    return render(request, 'stock/confirm_action.html', {
        'titre': 'Annuler la commande',
        'message': f"Annuler la commande {commande.reference} ?",
        'bouton': 'Annuler la commande', 'retour': 'stock:commande_detail', 'retour_pk': commande.pk,
    })


@reauth_required
@login_required
@stock_required
def reception_create(request, pk):
    """Réception (partielle ou totale) d'une commande : alimente le stock."""
    entreprise = request.user.entreprise
    commande = get_object_or_404(CommandeFournisseur, pk=pk, entreprise=entreprise)
    if not commande.receptionnable:
        messages.error(request, "Cette commande n'est pas en attente de réception.")
        return redirect('stock:commande_detail', pk=pk)
    lignes = commande.lignes.select_related('article')

    if request.method == 'POST':
        form = ReceptionForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            with transaction.atomic():
                reception = form.save(commit=False)
                reception.entreprise = entreprise
                reception.commande = commande
                reception.reference = _generer_reference(Reception, entreprise, 'REC')
                reception.cree_par = request.user
                reception.save()
                depot = reception.depot
                nb_lignes = 0
                for ligne in lignes:
                    champ = f'recu_{ligne.pk}'
                    valeur = request.POST.get(champ, '').strip().replace(',', '.')
                    if not valeur:
                        continue
                    try:
                        qte = Decimal(valeur)
                    except (ValueError, ArithmeticError):
                        continue
                    if qte <= 0:
                        continue
                    qte = min(qte, ligne.reste_a_recevoir)  # ne pas dépasser le reste
                    if qte <= 0:
                        continue
                    article = Article.objects.select_for_update().get(pk=ligne.article_id)
                    avant, apres = appliquer_mouvement_depot(article, depot, 'entree', qte)
                    MouvementStock.objects.create(
                        entreprise=entreprise, article=article, depot=depot,
                        type_mouvement='entree', quantite=qte, quantite_avant=avant, quantite_apres=apres,
                        prix_unitaire=ligne.prix_unitaire, motif=f"Réception {reception.reference}",
                        reference_document=commande.reference, fournisseur=commande.fournisseur,
                        date_mouvement=timezone.now(), cree_par=request.user,
                    )
                    LigneReception.objects.create(reception=reception, ligne_commande=ligne, quantite_recue=qte)
                    ligne.quantite_recue = (ligne.quantite_recue or Decimal('0')) + qte
                    ligne.save(update_fields=['quantite_recue'])
                    nb_lignes += 1

                if nb_lignes == 0:
                    transaction.set_rollback(True)
                    messages.error(request, "Aucune quantité saisie.")
                    return redirect('stock:reception_create', pk=pk)

                # Mise à jour du statut de la commande
                if all(l.reste_a_recevoir <= 0 for l in commande.lignes.all()):
                    commande.statut = 'recue'
                else:
                    commande.statut = 'partiellement_recue'
                commande.save(update_fields=['statut'])

            messages.success(request, f"Réception {reception.reference} enregistrée dans {depot.nom}.")
            return redirect('stock:commande_detail', pk=pk)
    else:
        initial = {}
        if commande.depot_id:
            initial['depot'] = commande.depot_id
        form = ReceptionForm(entreprise=entreprise, initial=initial)

    return render(request, 'stock/reception_form.html', {
        'commande': commande, 'lignes': lignes, 'form': form,
    })


# ===========================================================================
# ACHATS — Factures fournisseurs & paiements
# ===========================================================================
@reauth_required
@login_required
@stock_required
def facture_list(request):
    entreprise = request.user.entreprise
    factures = FactureFournisseur.objects.filter(entreprise=entreprise).select_related('fournisseur')
    statut = request.GET.get('statut', '')
    if statut:
        factures = factures.filter(statut=statut)
    factures = list(factures)
    total_du = sum((f.montant_du for f in factures), Decimal('0'))
    return render(request, 'stock/facture_list.html', {
        'factures': factures, 'statuts': FactureFournisseur.STATUTS,
        'statut_filter': statut, 'total_du': total_du,
    })


@reauth_required
@login_required
@stock_required
def facture_create(request):
    entreprise = request.user.entreprise
    commande_id = request.GET.get('commande')
    if request.method == 'POST':
        form = FactureFournisseurForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            facture = form.save(commit=False)
            facture.entreprise = entreprise
            facture.cree_par = request.user
            facture.maj_statut(sauver=False)
            facture.save()
            messages.success(request, f"Facture {facture.numero} enregistrée.")
            return redirect('stock:facture_detail', pk=facture.pk)
    else:
        initial = {}
        if commande_id:
            commande = CommandeFournisseur.objects.filter(pk=commande_id, entreprise=entreprise).first()
            if commande:
                initial = {
                    'fournisseur': commande.fournisseur_id, 'commande': commande.pk,
                    'montant_ht': commande.montant_total,
                }
        form = FactureFournisseurForm(entreprise=entreprise, initial=initial)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouvelle facture fournisseur', 'retour': 'stock:facture_list',
    })


@reauth_required
@login_required
@stock_required
def facture_detail(request, pk):
    entreprise = request.user.entreprise
    facture = get_object_or_404(FactureFournisseur, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        form = PaiementFournisseurForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                paiement = form.save(commit=False)
                if paiement.montant > facture.montant_du:
                    messages.error(request, f"Le paiement dépasse le montant dû ({facture.montant_du}).")
                    return redirect('stock:facture_detail', pk=pk)
                paiement.facture = facture
                paiement.cree_par = request.user
                paiement.save()
                facture.montant_paye = (facture.montant_paye or Decimal('0')) + paiement.montant
                facture.maj_statut(sauver=False)
                facture.save(update_fields=['montant_paye', 'statut'])
            messages.success(request, "Paiement enregistré.")
            return redirect('stock:facture_detail', pk=pk)
    else:
        form = PaiementFournisseurForm(initial={'montant': facture.montant_du})
    return render(request, 'stock/facture_detail.html', {
        'facture': facture, 'paiements': facture.paiements.all(), 'form': form,
    })


@reauth_required
@login_required
@stock_required
def facture_delete(request, pk):
    facture = get_object_or_404(FactureFournisseur, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        facture.delete()
        messages.success(request, "Facture supprimée.")
        return redirect('stock:facture_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': f"facture {facture.numero}", 'retour': 'stock:facture_list',
    })


# ===========================================================================
# Fiche fournisseur enrichie
# ===========================================================================
@reauth_required
@login_required
@stock_required
def fournisseur_detail(request, pk):
    entreprise = request.user.entreprise
    fournisseur = get_object_or_404(Fournisseur, pk=pk, entreprise=entreprise)

    articles = Article.objects.filter(entreprise=entreprise, fournisseur=fournisseur)
    commandes = fournisseur.commandes.prefetch_related('lignes').order_by('-date_commande')
    factures = list(fournisseur.factures.all())

    dette = sum((f.montant_du for f in factures), Decimal('0'))
    total_achats = sum((c.montant_total for c in commandes if c.statut != 'annulee'), Decimal('0'))

    # Performance : délai réel moyen (1ère réception - date commande) sur commandes reçues.
    delais = []
    for c in commandes:
        premiere = c.receptions.order_by('date_reception').first()
        if premiere:
            delais.append((premiere.date_reception - c.date_commande).days)
    delai_reel_moyen = round(sum(delais) / len(delais), 1) if delais else None

    return render(request, 'stock/fournisseur_detail.html', {
        'fournisseur': fournisseur, 'articles': articles, 'commandes': commandes[:20],
        'factures': factures[:20], 'dette': dette, 'total_achats': total_achats,
        'delai_reel_moyen': delai_reel_moyen, 'nb_commandes': commandes.count(),
    })
