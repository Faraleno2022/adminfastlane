"""
Module Gestion du Stock — Vues
Tableau de bord, articles, catégories, fournisseurs, mouvements de stock
(entrées / sorties / ajustements), inventaires physiques et rapports.
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

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
    Client, PrixSpecialClient, DocumentVente, LigneVente, BonLivraison,
    LigneLivraison, PaiementClient, ProfilStock, JournalAudit,
    Lot, NumeroSerie,
    BesoinAchat, LigneBesoinAchat, DemandeVente, LigneDemandeVente,
)
from .forms import (
    CategorieArticleForm, FournisseurForm, ArticleForm,
    MouvementStockForm, InventaireForm, DepotForm, TransfertForm,
    CommandeFournisseurForm, LigneCommandeForm, ReceptionForm,
    FactureFournisseurForm, PaiementFournisseurForm,
    ClientForm, DocumentVenteForm, LigneVenteForm, BonLivraisonForm,
    PaiementClientForm, PrixSpecialClientForm, LotForm, NumeroSerieForm,
    BesoinAchatForm, LigneBesoinAchatForm, DemandeVenteForm, LigneDemandeVenteForm,
)
from .permissions import require_perm, a_permission, get_role
from . import exports

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
        if quantite > avant:
            raise ValueError(f"Stock insuffisant : {avant} disponible(s), {quantite} demandée(s).")
        apres = avant - quantite
    elif type_mouvement == 'ajustement':  # la quantité devient le stock réel du dépôt
        if quantite < 0:
            raise ValueError("Le stock physique ne peut pas être négatif.")
        apres = quantite
    else:
        raise ValueError(f"Type de mouvement inconnu : {type_mouvement}.")
    sad.quantite = apres
    sad.save(update_fields=['quantite'])
    article.recalculer_total(sauver=True)
    return avant, apres


def get_depot_defaut(entreprise):
    """Renvoie le dépôt par défaut de l'entreprise (ou le premier actif)."""
    return (Depot.objects.filter(entreprise=entreprise, par_defaut=True, actif=True).first()
            or Depot.objects.filter(entreprise=entreprise, actif=True).first())


def maj_cmup(article, quantite_entree, prix_unitaire, stock_avant):
    """Met à jour le coût moyen unitaire pondéré (CMUP) lors d'une entrée d'achat.

    CMUP = (stock_avant * CMUP_actuel + quantité_entrée * prix) / (stock_avant + quantité_entrée)
    À appeler avec le stock global AVANT l'entrée. Sauvegarde le champ cmup.
    """
    if prix_unitaire is None or prix_unitaire <= 0:
        return
    stock_avant = stock_avant or Decimal('0')
    ancien_cmup = article.cmup if (article.cmup and article.cmup > 0) else (article.prix_achat or Decimal('0'))
    total = stock_avant + quantite_entree
    if total > 0:
        article.cmup = ((stock_avant * ancien_cmup + quantite_entree * prix_unitaire) / total).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        article.cmup = Decimal(str(prix_unitaire)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
    article.save(update_fields=['cmup'])


def erreurs_disponibilite_livraison(a_livrer, depot):
    """Valide le stock en cumulant les lignes qui visent le meme article."""
    demandes_par_article = {}
    for ligne, qte in a_livrer.values():
        demandes_par_article.setdefault(
            ligne.article_id, [ligne.article, Decimal('0')])[1] += qte
    erreurs = []
    for article, qte_totale in demandes_par_article.values():
        dispo = article.stock_dans(depot)
        if qte_totale > dispo:
            erreurs.append(
                f"{article.designation} : {dispo} en stock dans {depot.nom}, "
                f"{qte_totale} demandé(s) au total.")
    return erreurs


def valeur_stock_expr():
    """Expression SQL de la valeur du stock : quantité × (CMUP si > 0, sinon prix d'achat)."""
    from django.db.models import Case, When
    cout = Case(
        When(cmup__gt=0, then=F('cmup')),
        default=F('prix_achat'),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    return ExpressionWrapper(F('quantite_stock') * cout, output_field=DecimalField(max_digits=18, decimal_places=2))


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

    valeur_expr = valeur_stock_expr()
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

    # Péremption des lots
    aujourdhui = timezone.now().date()
    limite_perem = aujourdhui + timedelta(days=Lot.SEUIL_PROCHE_JOURS)
    lots_actifs = Lot.objects.filter(entreprise=entreprise, date_peremption__isnull=False, quantite_restante__gt=0)
    nb_perime = lots_actifs.filter(date_peremption__lt=aujourdhui).count()
    nb_proche_perem = lots_actifs.filter(date_peremption__gte=aujourdhui, date_peremption__lte=limite_perem).count()

    stats = {
        'total_articles': articles.count(),
        'total_depots': Depot.objects.filter(entreprise=entreprise, actif=True).count(),
        'nb_perime': nb_perime,
        'nb_proche_perem': nb_proche_perem,
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
        'besoins_achat_en_attente': BesoinAchat.objects.filter(entreprise=entreprise, statut='soumise').count(),
        'demandes_vente_en_attente': DemandeVente.objects.filter(entreprise=entreprise, statut='soumise').count(),
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
@require_perm('stock')
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
@require_perm('stock')
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
@require_perm('stock')
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
    categorie = request.GET.get('categorie', '')
    if categorie:
        fournisseurs = fournisseurs.filter(categorie=categorie)
    fournisseurs = fournisseurs.order_by('-note_evaluation', 'nom')
    return render(request, 'stock/fournisseur_list.html', {
        'fournisseurs': fournisseurs, 'recherche': recherche,
        'categories': Fournisseur.CATEGORIES, 'categorie_filter': categorie,
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
@require_perm('stock')
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
                stock_global_avant = article.quantite_stock or Decimal('0')

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
                # Entrée d'achat avec prix : mise à jour du CMUP.
                if mouvement.type_mouvement == 'entree':
                    maj_cmup(article, quantite, mouvement.prix_unitaire, stock_global_avant)
                else:
                    mouvement.prix_unitaire = article.cout_unitaire
                    if mouvement.type_mouvement == 'ajustement':
                        mouvement.quantite = apres - avant
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
    from django.db.models import Case, When
    cout = Case(
        When(stocks_articles__article__cmup__gt=0, then=F('stocks_articles__article__cmup')),
        default=F('stocks_articles__article__prix_achat'),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    valeur_expr = ExpressionWrapper(
        F('stocks_articles__quantite') * cout, output_field=DecimalField(max_digits=18, decimal_places=2)
    )
    depots = (Depot.objects.filter(entreprise=entreprise)
              .annotate(nb_articles=Count('stocks_articles', distinct=True),
                        valeur=Sum(valeur_expr)))
    return render(request, 'stock/depot_list.html', {'depots': depots, 'types': Depot.TYPES})


@reauth_required
@login_required
@stock_required
@require_perm('stock')
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
@require_perm('stock')
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
@require_perm('stock')
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
@require_perm('stock')
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
                stock_source = article.stock_dans(transfert.depot_source)
                if transfert.quantite > stock_source:
                    form.add_error(
                        'quantite',
                        f"Stock insuffisant dans {transfert.depot_source.nom} : "
                        f"{stock_source} disponible(s).",
                    )
                    return render(request, 'stock/form.html', {
                        'form': form, 'titre': 'Nouveau transfert',
                        'retour': 'stock:transfert_list',
                    })
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
                    quantite_avant=av_s, quantite_apres=ap_s, prix_unitaire=article.cout_unitaire,
                    motif=f"Transfert vers {transfert.depot_destination.nom}", reference_document=ref,
                    date_mouvement=transfert.date_transfert, cree_par=request.user,
                )
                # Entrée dans le dépôt destination
                av_d, ap_d = appliquer_mouvement_depot(article, transfert.depot_destination, 'entree', transfert.quantite)
                MouvementStock.objects.create(
                    entreprise=entreprise, article=article, depot=transfert.depot_destination,
                    type_mouvement='transfert', quantite=transfert.quantite,
                    quantite_avant=av_d, quantite_apres=ap_d, prix_unitaire=article.cout_unitaire,
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
@require_perm('stock')
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
                    quantite_physique = Decimal(valeur) if valeur else Decimal('0')
                    if quantite_physique < 0:
                        messages.error(
                            request,
                            f"{ligne.article.designation} : la quantité physique ne peut pas être négative.")
                        continue
                    ligne.quantite_physique = quantite_physique
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
@require_perm('stock')
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
                    quantite=apres - avant,
                    quantite_avant=avant,
                    quantite_apres=apres,
                    prix_unitaire=article.cout_unitaire,
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

    valeur_expr = valeur_stock_expr()

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
@require_perm('achats')
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


# ---------------------------------------------------------------------------
# Expression de besoin (achat) — n'importe quel employé peut exprimer un
# besoin ; la validation (permission 'achats') l'expose ensuite dans l'écran
# de réapprovisionnement pour générer le bon de commande automatiquement.
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def besoin_achat_list(request):
    entreprise = request.user.entreprise
    besoins = (BesoinAchat.objects.filter(entreprise=entreprise)
               .select_related('demandeur', 'service').prefetch_related('lignes'))
    if not a_permission(request.user, 'achats'):
        besoins = besoins.filter(demandeur=request.user)
    statut = request.GET.get('statut', '')
    if statut:
        besoins = besoins.filter(statut=statut)
    return render(request, 'stock/besoin_achat_list.html', {
        'besoins': besoins, 'statuts': BesoinAchat.STATUTS, 'statut_filter': statut,
        'peut_valider': a_permission(request.user, 'achats'),
    })


@reauth_required
@login_required
@stock_required
def besoin_achat_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = BesoinAchatForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            besoin = form.save(commit=False)
            besoin.entreprise = entreprise
            besoin.reference = _generer_reference(BesoinAchat, entreprise, 'EB')
            besoin.demandeur = request.user
            besoin.save()
            messages.success(request, f"Besoin {besoin.reference} soumis. Ajoutez les articles souhaités.")
            return redirect('stock:besoin_achat_detail', pk=besoin.pk)
    else:
        form = BesoinAchatForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': "Exprimer un besoin d'achat", 'retour': 'stock:besoin_achat_list',
    })


@reauth_required
@login_required
@stock_required
def besoin_achat_detail(request, pk):
    entreprise = request.user.entreprise
    besoin = get_object_or_404(BesoinAchat, pk=pk, entreprise=entreprise)
    peut_gerer = a_permission(request.user, 'achats')
    if besoin.demandeur_id != request.user.id and not peut_gerer:
        messages.error(request, "Vous ne pouvez pas consulter ce besoin.")
        return redirect('stock:besoin_achat_list')
    lignes = besoin.lignes.select_related('article', 'ligne_commande__commande')

    if request.method == 'POST':
        if not besoin.modifiable:
            messages.error(request, "Ce besoin ne peut plus être modifié.")
            return redirect('stock:besoin_achat_detail', pk=pk)
        form = LigneBesoinAchatForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            ligne = form.save(commit=False)
            ligne.besoin = besoin
            ligne.save()
            messages.success(request, "Article ajouté au besoin.")
            return redirect('stock:besoin_achat_detail', pk=pk)
    else:
        form = LigneBesoinAchatForm(entreprise=entreprise)

    return render(request, 'stock/besoin_achat_detail.html', {
        'besoin': besoin, 'lignes': lignes, 'form': form, 'peut_gerer': peut_gerer,
    })


@reauth_required
@login_required
@stock_required
def ligne_besoin_achat_delete(request, pk):
    ligne = get_object_or_404(LigneBesoinAchat, pk=pk, besoin__entreprise=request.user.entreprise)
    besoin_pk = ligne.besoin_id
    peut_gerer = a_permission(request.user, 'achats')
    if ligne.besoin.demandeur_id != request.user.id and not peut_gerer:
        messages.error(request, "Action non autorisée.")
        return redirect('stock:besoin_achat_detail', pk=besoin_pk)
    if ligne.besoin.modifiable:
        ligne.delete()
        messages.success(request, "Ligne supprimée.")
    else:
        messages.error(request, "Besoin non modifiable.")
    return redirect('stock:besoin_achat_detail', pk=besoin_pk)


@reauth_required
@login_required
@stock_required
@require_perm('achats')
def besoin_achat_valider(request, pk):
    besoin = get_object_or_404(BesoinAchat, pk=pk, entreprise=request.user.entreprise)
    if besoin.statut != 'soumise':
        messages.warning(request, "Ce besoin a déjà été traité.")
        return redirect('stock:besoin_achat_detail', pk=pk)
    if not besoin.lignes.exists():
        messages.error(request, "Ajoutez au moins un article avant de valider.")
        return redirect('stock:besoin_achat_detail', pk=pk)
    besoin.statut = 'validee'
    besoin.valide_par = request.user
    besoin.date_validation = timezone.now()
    besoin.save(update_fields=['statut', 'valide_par', 'date_validation'])
    messages.success(request, f"Besoin {besoin.reference} validé. Il apparaît dans le réapprovisionnement.")
    return redirect('stock:besoin_achat_detail', pk=pk)


@reauth_required
@login_required
@stock_required
@require_perm('achats')
def besoin_achat_rejeter(request, pk):
    besoin = get_object_or_404(BesoinAchat, pk=pk, entreprise=request.user.entreprise)
    if besoin.statut != 'soumise':
        messages.warning(request, "Ce besoin a déjà été traité.")
        return redirect('stock:besoin_achat_detail', pk=pk)
    if request.method == 'POST':
        besoin.statut = 'rejetee'
        besoin.valide_par = request.user
        besoin.date_validation = timezone.now()
        besoin.commentaire_validation = request.POST.get('commentaire', '').strip()
        besoin.save(update_fields=['statut', 'valide_par', 'date_validation', 'commentaire_validation'])
        messages.success(request, f"Besoin {besoin.reference} rejeté.")
    return redirect('stock:besoin_achat_detail', pk=pk)


@reauth_required
@login_required
@stock_required
@require_perm('achats')
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
@require_perm('achats')
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
                    stock_global_avant = article.quantite_stock or Decimal('0')
                    avant, apres = appliquer_mouvement_depot(article, depot, 'entree', qte)
                    maj_cmup(article, qte, ligne.prix_unitaire, stock_global_avant)
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
@require_perm('achats')
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


# ===========================================================================
# VENTES — Clients
# ===========================================================================
@reauth_required
@login_required
@stock_required
def client_list(request):
    entreprise = request.user.entreprise
    clients = Client.objects.filter(entreprise=entreprise)
    recherche = request.GET.get('q', '')
    if recherche:
        clients = clients.filter(
            Q(nom__icontains=recherche) | Q(contact__icontains=recherche) |
            Q(email__icontains=recherche) | Q(telephone__icontains=recherche)
        )
    return render(request, 'stock/client_list.html', {'clients': clients, 'recherche': recherche})


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def client_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.entreprise = entreprise
            c.save()
            messages.success(request, "Client ajouté.")
            return redirect('stock:client_list')
    else:
        form = ClientForm()
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau client', 'retour': 'stock:client_list',
    })


@reauth_required
@login_required
@stock_required
def client_edit(request, pk):
    c = get_object_or_404(Client, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=c)
        if form.is_valid():
            form.save()
            messages.success(request, "Client mis à jour.")
            return redirect('stock:client_detail', pk=c.pk)
    else:
        form = ClientForm(instance=c)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Modifier le client', 'retour': 'stock:client_detail', 'retour_pk': c.pk,
    })


@reauth_required
@login_required
@stock_required
def client_delete(request, pk):
    c = get_object_or_404(Client, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        c.delete()
        messages.success(request, "Client supprimé.")
        return redirect('stock:client_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': c.nom, 'retour': 'stock:client_list',
    })


@reauth_required
@login_required
@stock_required
def client_detail(request, pk):
    entreprise = request.user.entreprise
    client = get_object_or_404(Client, pk=pk, entreprise=entreprise)

    if request.method == 'POST':
        form = PrixSpecialClientForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            ps = form.save(commit=False)
            ps.client = client
            ps.save()
            messages.success(request, "Prix spécial enregistré.")
            return redirect('stock:client_detail', pk=client.pk)
    else:
        form = PrixSpecialClientForm(entreprise=entreprise)

    documents = client.documents.order_by('-date_document')
    factures = [d for d in documents if d.type_document == 'facture']
    creance = sum((f.montant_du for f in factures if f.statut != 'annulee'), Decimal('0'))
    total_vendu = sum((f.montant_ttc for f in factures if f.statut != 'annulee'), Decimal('0'))

    return render(request, 'stock/client_detail.html', {
        'client': client, 'documents': documents[:20], 'factures': factures[:20],
        'creance': creance, 'total_vendu': total_vendu,
        'prix_speciaux': client.prix_speciaux.select_related('article'),
        'form': form,
    })


@reauth_required
@login_required
@stock_required
def prix_special_delete(request, pk):
    ps = get_object_or_404(PrixSpecialClient, pk=pk, client__entreprise=request.user.entreprise)
    client_pk = ps.client_id
    ps.delete()
    messages.success(request, "Prix spécial supprimé.")
    return redirect('stock:client_detail', pk=client_pk)


# ---------------------------------------------------------------------------
# Expression de besoin (vente) — un commercial saisit ce que le client
# souhaite ; la validation (permission 'ventes') génère automatiquement le
# devis (DocumentVente) avec client et prix pré-remplis.
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@stock_required
def demande_vente_list(request):
    entreprise = request.user.entreprise
    demandes = (DemandeVente.objects.filter(entreprise=entreprise)
                .select_related('client', 'demandeur').prefetch_related('lignes'))
    if not a_permission(request.user, 'ventes'):
        demandes = demandes.filter(demandeur=request.user)
    statut = request.GET.get('statut', '')
    if statut:
        demandes = demandes.filter(statut=statut)
    return render(request, 'stock/demande_vente_list.html', {
        'demandes': demandes, 'statuts': DemandeVente.STATUTS, 'statut_filter': statut,
        'peut_valider': a_permission(request.user, 'ventes'),
    })


@reauth_required
@login_required
@stock_required
def demande_vente_create(request):
    entreprise = request.user.entreprise
    if not Client.objects.filter(entreprise=entreprise, actif=True).exists():
        messages.warning(request, "Créez d'abord un client.")
        return redirect('stock:client_create')
    if request.method == 'POST':
        form = DemandeVenteForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            demande = form.save(commit=False)
            demande.entreprise = entreprise
            demande.reference = _generer_reference(DemandeVente, entreprise, 'DV')
            demande.demandeur = request.user
            demande.save()
            messages.success(request, f"Demande {demande.reference} soumise. Ajoutez les articles souhaités.")
            return redirect('stock:demande_vente_detail', pk=demande.pk)
    else:
        form = DemandeVenteForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': "Exprimer un besoin client", 'retour': 'stock:demande_vente_list',
    })


@reauth_required
@login_required
@stock_required
def demande_vente_detail(request, pk):
    entreprise = request.user.entreprise
    demande = get_object_or_404(DemandeVente, pk=pk, entreprise=entreprise)
    peut_gerer = a_permission(request.user, 'ventes')
    if demande.demandeur_id != request.user.id and not peut_gerer:
        messages.error(request, "Vous ne pouvez pas consulter cette demande.")
        return redirect('stock:demande_vente_list')
    lignes = demande.lignes.select_related('article')

    if request.method == 'POST':
        if not demande.modifiable:
            messages.error(request, "Cette demande ne peut plus être modifiée.")
            return redirect('stock:demande_vente_detail', pk=pk)
        form = LigneDemandeVenteForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            ligne = form.save(commit=False)
            ligne.demande = demande
            ligne.save()
            messages.success(request, "Article ajouté à la demande.")
            return redirect('stock:demande_vente_detail', pk=pk)
    else:
        form = LigneDemandeVenteForm(entreprise=entreprise)

    return render(request, 'stock/demande_vente_detail.html', {
        'demande': demande, 'lignes': lignes, 'form': form, 'peut_gerer': peut_gerer,
    })


@reauth_required
@login_required
@stock_required
def ligne_demande_vente_delete(request, pk):
    ligne = get_object_or_404(LigneDemandeVente, pk=pk, demande__entreprise=request.user.entreprise)
    demande_pk = ligne.demande_id
    peut_gerer = a_permission(request.user, 'ventes')
    if ligne.demande.demandeur_id != request.user.id and not peut_gerer:
        messages.error(request, "Action non autorisée.")
        return redirect('stock:demande_vente_detail', pk=demande_pk)
    if ligne.demande.modifiable:
        ligne.delete()
        messages.success(request, "Ligne supprimée.")
    else:
        messages.error(request, "Demande non modifiable.")
    return redirect('stock:demande_vente_detail', pk=demande_pk)


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def demande_vente_valider(request, pk):
    entreprise = request.user.entreprise
    demande = get_object_or_404(DemandeVente, pk=pk, entreprise=entreprise)
    if demande.statut != 'soumise':
        messages.warning(request, "Cette demande a déjà été traitée.")
        return redirect('stock:demande_vente_detail', pk=pk)
    lignes = list(demande.lignes.select_related('article'))
    if not lignes:
        messages.error(request, "Ajoutez au moins un article avant de valider.")
        return redirect('stock:demande_vente_detail', pk=pk)

    with transaction.atomic():
        doc = DocumentVente.objects.create(
            entreprise=entreprise,
            reference=_generer_reference(DocumentVente, entreprise, _PREFIXES_VENTE['devis']),
            type_document='devis', client=demande.client, statut='brouillon',
            notes=f"Généré automatiquement depuis la demande {demande.reference}.",
            cree_par=request.user,
        )
        for ligne in lignes:
            # Même logique de prix/remise que la saisie manuelle d'une ligne de vente :
            # prix spécial client, sinon prix de vente ; remise habituelle du client.
            sp = PrixSpecialClient.objects.filter(client=demande.client, article=ligne.article).first()
            prix = sp.prix if sp else (ligne.article.prix_vente or Decimal('0'))
            LigneVente.objects.create(
                document=doc, article=ligne.article, quantite=ligne.quantite_souhaitee,
                prix_unitaire=prix, remise_pct=demande.client.remise_defaut or Decimal('0'),
            )
        demande.statut = 'convertie'
        demande.valide_par = request.user
        demande.date_validation = timezone.now()
        demande.document_genere = doc
        demande.save(update_fields=['statut', 'valide_par', 'date_validation', 'document_genere'])
    messages.success(request, f"Demande validée : devis {doc.reference} généré automatiquement.")
    return redirect('stock:vente_detail', pk=doc.pk)


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def demande_vente_rejeter(request, pk):
    demande = get_object_or_404(DemandeVente, pk=pk, entreprise=request.user.entreprise)
    if demande.statut != 'soumise':
        messages.warning(request, "Cette demande a déjà été traitée.")
        return redirect('stock:demande_vente_detail', pk=pk)
    if request.method == 'POST':
        demande.statut = 'rejetee'
        demande.valide_par = request.user
        demande.date_validation = timezone.now()
        demande.commentaire_validation = request.POST.get('commentaire', '').strip()
        demande.save(update_fields=['statut', 'valide_par', 'date_validation', 'commentaire_validation'])
        messages.success(request, f"Demande {demande.reference} rejetée.")
    return redirect('stock:demande_vente_detail', pk=pk)


# ===========================================================================
# VENTES — Devis / Proforma / Factures
# ===========================================================================
_PREFIXES_VENTE = {'devis': 'DEV', 'proforma': 'PRO', 'facture': 'FACT'}


@reauth_required
@login_required
@stock_required
def vente_list(request):
    entreprise = request.user.entreprise
    documents = (DocumentVente.objects.filter(entreprise=entreprise)
                 .select_related('client').prefetch_related('lignes'))
    type_filter = request.GET.get('type', '')
    statut = request.GET.get('statut', '')
    if type_filter:
        documents = documents.filter(type_document=type_filter)
    if statut:
        documents = documents.filter(statut=statut)
    return render(request, 'stock/vente_list.html', {
        'documents': documents, 'types': DocumentVente.TYPES, 'statuts': DocumentVente.STATUTS,
        'type_filter': type_filter, 'statut_filter': statut,
    })


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def vente_create(request):
    entreprise = request.user.entreprise
    if not Client.objects.filter(entreprise=entreprise, actif=True).exists():
        messages.warning(request, "Créez d'abord un client.")
        return redirect('stock:client_create')
    type_initial = request.GET.get('type', 'devis')
    if request.method == 'POST':
        form = DocumentVenteForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.entreprise = entreprise
            doc.reference = _generer_reference(DocumentVente, entreprise,
                                               _PREFIXES_VENTE.get(doc.type_document, 'DOC'))
            doc.cree_par = request.user
            if doc.est_facture:
                doc.statut = 'emise'
            doc.save()
            messages.success(request, f"{doc.get_type_document_display()} {doc.reference} créé. Ajoutez les articles.")
            return redirect('stock:vente_detail', pk=doc.pk)
    else:
        form = DocumentVenteForm(entreprise=entreprise, initial={'type_document': type_initial})
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau document de vente', 'retour': 'stock:vente_list',
    })


@reauth_required
@login_required
@stock_required
def vente_detail(request, pk):
    entreprise = request.user.entreprise
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=entreprise)
    lignes = doc.lignes.select_related('article')

    if request.method == 'POST':
        if not doc.modifiable:
            messages.error(request, "Ce document ne peut plus être modifié.")
            return redirect('stock:vente_detail', pk=pk)
        form = LigneVenteForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            ligne = form.save(commit=False)
            ligne.document = doc
            # Prix : prix spécial client, sinon prix de vente de l'article.
            if not ligne.prix_unitaire:
                sp = PrixSpecialClient.objects.filter(client=doc.client, article=ligne.article).first()
                ligne.prix_unitaire = sp.prix if sp else (ligne.article.prix_vente or Decimal('0'))
            # Remise : celle saisie, sinon remise habituelle du client.
            if form.cleaned_data.get('remise_pct') in (None, ''):
                ligne.remise_pct = doc.client.remise_defaut or Decimal('0')
            ligne.save()
            messages.success(request, "Article ajouté.")
            return redirect('stock:vente_detail', pk=pk)
    else:
        form = LigneVenteForm(entreprise=entreprise)

    paiement_form = PaiementClientForm(initial={'montant': doc.montant_du}) if doc.est_facture else None
    return render(request, 'stock/vente_detail.html', {
        'doc': doc, 'lignes': lignes, 'form': form, 'paiement_form': paiement_form,
        'livraisons': doc.livraisons.select_related('depot'),
        'paiements': doc.paiements.all() if doc.est_facture else [],
    })


@reauth_required
@login_required
@stock_required
def vente_edit(request, pk):
    entreprise = request.user.entreprise
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=entreprise)
    if not doc.modifiable:
        messages.error(request, "Ce document ne peut plus être modifié.")
        return redirect('stock:vente_detail', pk=pk)
    if request.method == 'POST':
        form = DocumentVenteForm(request.POST, instance=doc, entreprise=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Document mis à jour.")
            return redirect('stock:vente_detail', pk=pk)
    else:
        form = DocumentVenteForm(instance=doc, entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': f'Modifier {doc.reference}', 'retour': 'stock:vente_detail', 'retour_pk': doc.pk,
    })


@reauth_required
@login_required
@stock_required
def ligne_vente_delete(request, pk):
    ligne = get_object_or_404(LigneVente, pk=pk, document__entreprise=request.user.entreprise)
    doc_pk = ligne.document_id
    if ligne.document.modifiable:
        ligne.delete()
        messages.success(request, "Ligne supprimée.")
    else:
        messages.error(request, "Document non modifiable.")
    return redirect('stock:vente_detail', pk=doc_pk)


@reauth_required
@login_required
@stock_required
def vente_statut(request, pk, action):
    """Transitions de statut pour devis/proforma : envoyer, accepter, refuser."""
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=request.user.entreprise)
    transitions = {
        'envoyer': ('envoye', "Document marqué comme envoyé."),
        'accepter': ('accepte', "Devis accepté."),
        'refuser': ('refuse', "Devis refusé."),
    }
    if action in transitions and not doc.est_facture:
        doc.statut = transitions[action][0]
        doc.save(update_fields=['statut'])
        messages.success(request, transitions[action][1])
    return redirect('stock:vente_detail', pk=pk)


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def vente_convertir(request, pk):
    """Convertit un devis / proforma en facture (copie des lignes)."""
    entreprise = request.user.entreprise
    devis = get_object_or_404(DocumentVente, pk=pk, entreprise=entreprise)
    if devis.est_facture:
        messages.warning(request, "Ce document est déjà une facture.")
        return redirect('stock:vente_detail', pk=pk)
    if not devis.lignes.exists():
        messages.error(request, "Ajoutez au moins un article avant de convertir.")
        return redirect('stock:vente_detail', pk=pk)
    with transaction.atomic():
        facture = DocumentVente.objects.create(
            entreprise=entreprise, type_document='facture',
            reference=_generer_reference(DocumentVente, entreprise, 'FACT'),
            client=devis.client, depot=devis.depot, date_document=timezone.now().date(),
            remise_globale_pct=devis.remise_globale_pct, taux_tva=devis.taux_tva,
            statut='emise', notes=devis.notes, converti_depuis=devis, cree_par=request.user,
        )
        for l in devis.lignes.all():
            LigneVente.objects.create(
                document=facture, article=l.article, quantite=l.quantite,
                prix_unitaire=l.prix_unitaire, remise_pct=l.remise_pct,
            )
        devis.statut = 'converti'
        devis.save(update_fields=['statut'])
    messages.success(request, f"Facture {facture.reference} créée depuis {devis.reference}.")
    return redirect('stock:vente_detail', pk=facture.pk)


@reauth_required
@login_required
@stock_required
def vente_annuler(request, pk):
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        if doc.livraisons.exists() or (doc.montant_paye or 0) > 0:
            messages.error(request, "Impossible d'annuler : livraisons ou paiements existants.")
        else:
            doc.statut = 'annulee'
            doc.save(update_fields=['statut'])
            messages.success(request, "Document annulé.")
        return redirect('stock:vente_detail', pk=pk)
    return render(request, 'stock/confirm_action.html', {
        'titre': 'Annuler le document',
        'message': f"Annuler {doc.reference} ?",
        'bouton': 'Annuler', 'retour': 'stock:vente_detail', 'retour_pk': doc.pk,
    })


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def vente_paiement(request, pk):
    """Enregistre un encaissement (reçu) sur une facture."""
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=request.user.entreprise)
    if not doc.est_facture:
        messages.error(request, "Seules les factures acceptent des paiements.")
        return redirect('stock:vente_detail', pk=pk)
    if request.method == 'POST':
        form = PaiementClientForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                paiement = form.save(commit=False)
                if paiement.montant > doc.montant_du:
                    messages.error(request, f"Le paiement dépasse le solde dû ({doc.montant_du}).")
                    return redirect('stock:vente_detail', pk=pk)
                paiement.document = doc
                paiement.cree_par = request.user
                paiement.save()
                doc.montant_paye = (doc.montant_paye or Decimal('0')) + paiement.montant
                doc.maj_statut_paiement(sauver=False)
                doc.save(update_fields=['montant_paye', 'statut'])
            messages.success(request, "Encaissement enregistré.")
    return redirect('stock:vente_detail', pk=pk)


@reauth_required
@login_required
@stock_required
@require_perm('ventes')
def livraison_create(request, pk):
    """Bon de livraison : sortie de stock vers le client."""
    entreprise = request.user.entreprise
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=entreprise)
    if not doc.est_facture:
        messages.error(request, "Le bon de livraison se génère depuis une facture.")
        return redirect('stock:vente_detail', pk=pk)
    if not doc.lignes.exists():
        messages.error(request, "Aucun article à livrer.")
        return redirect('stock:vente_detail', pk=pk)
    lignes = doc.lignes.select_related('article')

    if request.method == 'POST':
        form = BonLivraisonForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            depot = form.cleaned_data['depot']
            # Vérifier le stock disponible avant d'écrire quoi que ce soit.
            erreurs = []
            a_livrer = {}
            for ligne in lignes:
                valeur = request.POST.get(f'livre_{ligne.pk}', '').strip().replace(',', '.')
                if not valeur:
                    continue
                try:
                    qte = Decimal(valeur)
                except (ValueError, ArithmeticError):
                    continue
                if qte <= 0:
                    continue
                qte = min(qte, ligne.reste_a_livrer)
                if qte <= 0:
                    continue
                a_livrer[ligne.pk] = (ligne, qte)
            # Plusieurs lignes peuvent viser le même article : la disponibilité
            # doit être contrôlée sur leur somme.
            erreurs.extend(erreurs_disponibilite_livraison(a_livrer, depot))
            if erreurs:
                for e in erreurs:
                    messages.error(request, e)
                return redirect('stock:livraison_create', pk=pk)
            if not a_livrer:
                messages.error(request, "Aucune quantité à livrer saisie.")
                return redirect('stock:livraison_create', pk=pk)

            with transaction.atomic():
                bl = form.save(commit=False)
                bl.entreprise = entreprise
                bl.document = doc
                bl.reference = _generer_reference(BonLivraison, entreprise, 'BL')
                bl.cree_par = request.user
                bl.save()
                for ligne, qte in a_livrer.values():
                    article = Article.objects.select_for_update().get(pk=ligne.article_id)
                    avant, apres = appliquer_mouvement_depot(article, depot, 'sortie', qte)
                    MouvementStock.objects.create(
                        entreprise=entreprise, article=article, depot=depot,
                        type_mouvement='sortie', quantite=qte, quantite_avant=avant, quantite_apres=apres,
                        prix_unitaire=article.cout_unitaire, motif=f"Livraison {bl.reference} - {doc.client.nom}",
                        reference_document=doc.reference, date_mouvement=timezone.now(), cree_par=request.user,
                    )
                    LigneLivraison.objects.create(livraison=bl, ligne_vente=ligne, quantite=qte)
                    ligne.quantite_livree = (ligne.quantite_livree or Decimal('0')) + qte
                    ligne.save(update_fields=['quantite_livree'])
            messages.success(request, f"Bon de livraison {bl.reference} créé (stock déduit de {depot.nom}).")
            return redirect('stock:vente_detail', pk=pk)
    else:
        initial = {}
        if doc.depot_id:
            initial['depot'] = doc.depot_id
        if doc.client.adresse:
            initial['adresse_livraison'] = doc.client.adresse
        form = BonLivraisonForm(entreprise=entreprise, initial=initial)

    return render(request, 'stock/livraison_form.html', {
        'doc': doc, 'lignes': lignes, 'form': form,
    })


# ===========================================================================
# TRAÇABILITÉ — Journal d'audit
# ===========================================================================
@reauth_required
@login_required
@stock_required
def journal_audit(request):
    entreprise = request.user.entreprise
    entrees = JournalAudit.objects.filter(entreprise=entreprise).select_related('utilisateur')
    action = request.GET.get('action', '')
    recherche = request.GET.get('q', '')
    if action:
        entrees = entrees.filter(action=action)
    if recherche:
        entrees = entrees.filter(
            Q(objet_type__icontains=recherche) | Q(objet_libelle__icontains=recherche)
        )
    return render(request, 'stock/journal_audit.html', {
        'entrees': entrees[:500], 'actions': JournalAudit.ACTIONS,
        'action_filter': action, 'recherche': recherche,
    })


# ===========================================================================
# RÔLES UTILISATEURS
# ===========================================================================
@reauth_required
@login_required
@stock_required
@require_perm('admin')
def roles_list(request):
    entreprise = request.user.entreprise
    from django.contrib.auth import get_user_model
    User = get_user_model()
    utilisateurs = User.objects.filter(entreprise=entreprise).order_by('username')

    if request.method == 'POST':
        user_id = request.POST.get('utilisateur')
        role = request.POST.get('role')
        valides = dict(ProfilStock.ROLES)
        cible = utilisateurs.filter(pk=user_id).first()
        if cible and role in valides:
            profil, _ = ProfilStock.objects.get_or_create(utilisateur=cible)
            profil.role = role
            profil.save()
            nom = cible.get_full_name() or cible.username
            messages.success(request, f"Rôle de {nom} mis à jour.")
        return redirect('stock:roles_list')

    lignes = []
    for u in utilisateurs:
        profil = getattr(u, 'profil_stock', None)
        lignes.append({'u': u, 'role': profil.role if profil else 'administrateur'})
    return render(request, 'stock/roles_list.html', {
        'lignes': lignes, 'roles': ProfilStock.ROLES,
    })


# ===========================================================================
# RAPPORTS — Exports Excel / PDF
# ===========================================================================
def _fmt(n):
    try:
        return f"{float(n):,.0f}".replace(',', ' ')
    except (TypeError, ValueError):
        return str(n)


@reauth_required
@login_required
@stock_required
def export_stock(request, fmt):
    entreprise = request.user.entreprise
    articles = Article.objects.filter(entreprise=entreprise).select_related('categorie')
    colonnes = ['Référence', 'Désignation', 'Catégorie', 'Unité', 'Stock', 'Prix achat', 'CMUP', 'Valeur']
    lignes, total_valeur = [], Decimal('0')
    for a in articles:
        lignes.append([a.reference, a.designation, a.categorie.nom if a.categorie else '-',
                       a.get_unite_display(), _fmt(a.quantite_stock), _fmt(a.prix_achat),
                       _fmt(a.cout_unitaire), _fmt(a.valeur_stock)])
        total_valeur += a.valeur_stock
    total_row = ['', '', '', '', '', '', 'TOTAL', _fmt(total_valeur)]
    if fmt == 'excel':
        return exports.excel_response('etat_stock', 'État du stock', colonnes, lignes, total_row)
    return exports.pdf_table_response('etat_stock', 'État du stock', colonnes, lignes, entreprise, total_row)


@reauth_required
@login_required
@stock_required
def export_mouvements(request, fmt):
    entreprise = request.user.entreprise
    mvts = MouvementStock.objects.filter(entreprise=entreprise).select_related('article', 'depot')
    type_filter = request.GET.get('type', '')
    if type_filter:
        mvts = mvts.filter(type_mouvement=type_filter)
    colonnes = ['Date', 'Type', 'Article', 'Dépôt', 'Quantité', 'Avant', 'Après', 'Motif']
    lignes = [[m.date_mouvement.strftime('%d/%m/%Y %H:%M'), m.get_type_mouvement_display(),
               m.article.designation, m.depot.nom if m.depot else '-', _fmt(m.quantite),
               _fmt(m.quantite_avant), _fmt(m.quantite_apres), m.motif] for m in mvts[:5000]]
    titre = 'Mouvements de stock'
    if fmt == 'excel':
        return exports.excel_response('mouvements', titre, colonnes, lignes)
    return exports.pdf_table_response('mouvements', titre, colonnes, lignes, entreprise)


@reauth_required
@login_required
@stock_required
def export_ventes(request, fmt):
    entreprise = request.user.entreprise
    factures = (DocumentVente.objects.filter(entreprise=entreprise, type_document='facture')
                .select_related('client'))
    colonnes = ['Référence', 'Date', 'Client', 'TTC', 'Encaissé', 'Dû', 'Statut']
    lignes, t_ttc, t_du = [], Decimal('0'), Decimal('0')
    for f in factures:
        lignes.append([f.reference, f.date_document.strftime('%d/%m/%Y'), f.client.nom,
                       _fmt(f.montant_ttc), _fmt(f.montant_paye), _fmt(f.montant_du), f.get_statut_display()])
        t_ttc += f.montant_ttc
        t_du += f.montant_du
    total_row = ['', '', 'TOTAL', _fmt(t_ttc), '', _fmt(t_du), '']
    titre = 'Rapport des ventes (factures)'
    if fmt == 'excel':
        return exports.excel_response('ventes', titre, colonnes, lignes, total_row)
    return exports.pdf_table_response('ventes', titre, colonnes, lignes, entreprise, total_row)


@reauth_required
@login_required
@stock_required
def export_achats(request, fmt):
    entreprise = request.user.entreprise
    commandes = (CommandeFournisseur.objects.filter(entreprise=entreprise)
                 .select_related('fournisseur').exclude(statut='annulee'))
    colonnes = ['Référence', 'Date', 'Fournisseur', 'Montant', 'Statut']
    lignes, total = [], Decimal('0')
    for c in commandes:
        lignes.append([c.reference, c.date_commande.strftime('%d/%m/%Y'), c.fournisseur.nom,
                       _fmt(c.montant_total), c.get_statut_display()])
        total += c.montant_total
    total_row = ['', '', 'TOTAL', _fmt(total), '']
    titre = 'Rapport des achats (commandes)'
    if fmt == 'excel':
        return exports.excel_response('achats', titre, colonnes, lignes, total_row)
    return exports.pdf_table_response('achats', titre, colonnes, lignes, entreprise, total_row)


@reauth_required
@login_required
@stock_required
def vente_pdf(request, pk):
    doc = get_object_or_404(DocumentVente, pk=pk, entreprise=request.user.entreprise)
    return exports.pdf_document_vente(doc)


# ===========================================================================
# LOTS, NUMÉROS DE SÉRIE & PÉREMPTION
# ===========================================================================
@reauth_required
@login_required
@stock_required
def lot_list(request):
    entreprise = request.user.entreprise
    lots = Lot.objects.filter(entreprise=entreprise).select_related('article', 'depot', 'fournisseur')
    etat = request.GET.get('etat', '')
    recherche = request.GET.get('q', '')
    if recherche:
        lots = lots.filter(Q(numero_lot__icontains=recherche) | Q(article__designation__icontains=recherche))
    lots = list(lots)
    if etat == 'perime':
        lots = [l for l in lots if l.est_perime]
    elif etat == 'proche':
        lots = [l for l in lots if l.proche_peremption]
    return render(request, 'stock/lot_list.html', {
        'lots': lots, 'etat_filter': etat, 'recherche': recherche,
    })


@reauth_required
@login_required
@stock_required
@require_perm('stock')
def lot_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = LotForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            lot = form.save(commit=False)
            lot.entreprise = entreprise
            if not lot.quantite_restante:
                lot.quantite_restante = lot.quantite
            lot.save()
            messages.success(request, f"Lot {lot.numero_lot} enregistré.")
            return redirect('stock:lot_list')
    else:
        form = LotForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau lot', 'retour': 'stock:lot_list',
    })


@reauth_required
@login_required
@stock_required
@require_perm('stock')
def lot_edit(request, pk):
    entreprise = request.user.entreprise
    lot = get_object_or_404(Lot, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        form = LotForm(request.POST, instance=lot, entreprise=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Lot mis à jour.")
            return redirect('stock:lot_list')
    else:
        form = LotForm(instance=lot, entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': f'Modifier le lot {lot.numero_lot}', 'retour': 'stock:lot_list',
    })


@reauth_required
@login_required
@stock_required
@require_perm('stock')
def lot_delete(request, pk):
    lot = get_object_or_404(Lot, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        lot.delete()
        messages.success(request, "Lot supprimé.")
        return redirect('stock:lot_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': f"lot {lot.numero_lot}", 'retour': 'stock:lot_list',
    })


@reauth_required
@login_required
@stock_required
def serie_list(request):
    entreprise = request.user.entreprise
    series = NumeroSerie.objects.filter(entreprise=entreprise).select_related('article', 'depot', 'lot')
    statut = request.GET.get('statut', '')
    recherche = request.GET.get('q', '')
    if statut:
        series = series.filter(statut=statut)
    if recherche:
        series = series.filter(Q(numero_serie__icontains=recherche) | Q(article__designation__icontains=recherche))
    return render(request, 'stock/serie_list.html', {
        'series': series, 'statuts': NumeroSerie.STATUTS, 'statut_filter': statut, 'recherche': recherche,
    })


@reauth_required
@login_required
@stock_required
@require_perm('stock')
def serie_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = NumeroSerieForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            serie = form.save(commit=False)
            serie.entreprise = entreprise
            serie.save()
            messages.success(request, f"Numéro de série {serie.numero_serie} enregistré.")
            return redirect('stock:serie_list')
    else:
        form = NumeroSerieForm(entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau numéro de série', 'retour': 'stock:serie_list',
    })


@reauth_required
@login_required
@stock_required
@require_perm('stock')
def serie_edit(request, pk):
    entreprise = request.user.entreprise
    serie = get_object_or_404(NumeroSerie, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        form = NumeroSerieForm(request.POST, instance=serie, entreprise=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Numéro de série mis à jour.")
            return redirect('stock:serie_list')
    else:
        form = NumeroSerieForm(instance=serie, entreprise=entreprise)
    return render(request, 'stock/form.html', {
        'form': form, 'titre': f'Modifier {serie.numero_serie}', 'retour': 'stock:serie_list',
    })


@reauth_required
@login_required
@stock_required
@require_perm('stock')
def serie_delete(request, pk):
    serie = get_object_or_404(NumeroSerie, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        serie.delete()
        messages.success(request, "Numéro de série supprimé.")
        return redirect('stock:serie_list')
    return render(request, 'stock/confirm_delete.html', {
        'objet': f"n° {serie.numero_serie}", 'retour': 'stock:serie_list',
    })


@reauth_required
@login_required
@stock_required
def peremptions(request):
    """Lots périmés et proches de la péremption."""
    entreprise = request.user.entreprise
    aujourdhui = timezone.now().date()
    limite = aujourdhui + timedelta(days=Lot.SEUIL_PROCHE_JOURS)
    lots = (Lot.objects.filter(entreprise=entreprise, date_peremption__isnull=False, quantite_restante__gt=0)
            .select_related('article', 'depot'))
    perimes = lots.filter(date_peremption__lt=aujourdhui)
    proches = lots.filter(date_peremption__gte=aujourdhui, date_peremption__lte=limite)
    return render(request, 'stock/peremptions.html', {
        'perimes': perimes, 'proches': proches, 'seuil': Lot.SEUIL_PROCHE_JOURS,
    })


# ===========================================================================
# RÉAPPROVISIONNEMENT — suggestions de commande
# ===========================================================================
def _quantite_a_commander(article):
    """Quantité suggérée pour ramener le stock à la cible (stock max, sinon 2× le seuil)."""
    if article.stock_max and article.stock_max > 0:
        cible = article.stock_max
    else:
        cible = (article.seuil_alerte or 0) * 2
    if cible <= 0:
        cible = article.seuil_alerte or Decimal('1')
    qte = cible - (article.quantite_stock or Decimal('0'))
    return qte if qte > 0 else Decimal('0')


def _creer_commandes_groupees(entreprise, user, depot, items):
    """Crée un CommandeFournisseur (brouillon) par fournisseur à partir d'une liste
    d'items {'article', 'quantite', 'prix', 'ligne_besoin' (optionnel)}.

    Relie chaque LigneBesoinAchat traitée à la LigneCommande générée et marque le
    BesoinAchat parent comme 'traitee' une fois toutes ses lignes couvertes.
    Doit être appelé à l'intérieur d'une transaction. Renvoie {fournisseur_id: CommandeFournisseur}.
    """
    commandes = {}
    besoins_a_verifier = set()
    for item in items:
        article = item['article']
        frs_id = article.fournisseur_id
        if not frs_id:
            continue
        if frs_id not in commandes:
            commandes[frs_id] = CommandeFournisseur.objects.create(
                entreprise=entreprise,
                reference=_generer_reference(CommandeFournisseur, entreprise, 'BC'),
                fournisseur=article.fournisseur, depot=depot, statut='brouillon',
                notes='Généré automatiquement (réapprovisionnement).', cree_par=user,
            )
        ligne = LigneCommande.objects.create(
            commande=commandes[frs_id], article=article,
            quantite_commandee=item['quantite'], prix_unitaire=(item['prix'] or Decimal('0')),
        )
        ligne_besoin = item.get('ligne_besoin')
        if ligne_besoin is not None:
            ligne_besoin.ligne_commande = ligne
            ligne_besoin.save(update_fields=['ligne_commande'])
            besoins_a_verifier.add(ligne_besoin.besoin_id)
    for besoin_id in besoins_a_verifier:
        besoin = BesoinAchat.objects.filter(pk=besoin_id).first()
        if besoin and not besoin.lignes.filter(ligne_commande__isnull=True).exists():
            besoin.statut = 'traitee'
            besoin.save(update_fields=['statut'])
    return commandes


@reauth_required
@login_required
@stock_required
def reapprovisionnement(request):
    """Articles sous le seuil + besoins d'achat validés, regroupés par fournisseur,
    avec génération automatique des bons de commande."""
    entreprise = request.user.entreprise

    if request.method == 'POST':
        if not a_permission(request.user, 'achats'):
            messages.error(request, "Votre rôle ne permet pas de créer des commandes.")
            return redirect('stock:reapprovisionnement')
        ids = request.POST.getlist('inclure')
        depot = get_depot_defaut(entreprise)
        items = []
        for raw_id in ids:
            valeur = request.POST.get(f'qte_{raw_id}', '').strip().replace(',', '.')
            try:
                qte = Decimal(valeur)
            except (ValueError, ArithmeticError):
                continue
            if qte <= 0:
                continue
            if raw_id.startswith('art:'):
                article = Article.objects.filter(pk=raw_id[4:], entreprise=entreprise, actif=True).first()
                if not article or not article.fournisseur_id:
                    continue
                items.append({'article': article, 'quantite': qte,
                              'prix': article.cout_unitaire or Decimal('0'), 'ligne_besoin': None})
            elif raw_id.startswith('besoin:'):
                ligne_besoin = (LigneBesoinAchat.objects
                                .filter(pk=raw_id[7:], besoin__entreprise=entreprise,
                                        besoin__statut='validee', ligne_commande__isnull=True)
                                .select_related('article__fournisseur', 'besoin').first())
                if not ligne_besoin or not ligne_besoin.article.fournisseur_id:
                    continue
                items.append({'article': ligne_besoin.article, 'quantite': qte,
                              'prix': ligne_besoin.article.cout_unitaire or Decimal('0'),
                              'ligne_besoin': ligne_besoin})
        with transaction.atomic():
            commandes_creees = _creer_commandes_groupees(entreprise, request.user, depot, items)
        n = len(commandes_creees)
        if n:
            messages.success(request, f"{n} bon(s) de commande créé(s) au brouillon. Vérifiez puis validez.")
            return redirect('stock:commande_list')
        messages.warning(request, "Aucun article sélectionné (ou sans fournisseur).")
        return redirect('stock:reapprovisionnement')

    articles = (Article.objects.filter(entreprise=entreprise, actif=True)
                .select_related('fournisseur'))
    groupes = {}          # fournisseur -> liste de suggestions
    sans_fournisseur = []
    for a in articles:
        if not (a.en_rupture or a.en_alerte):
            continue
        suggestion = {'source': 'alerte', 'checkbox_id': f'art:{a.pk}',
                      'article': a, 'qte': _quantite_a_commander(a), 'prix': a.cout_unitaire, 'besoin_ref': ''}
        if a.fournisseur_id:
            groupes.setdefault(a.fournisseur, []).append(suggestion)
        else:
            sans_fournisseur.append(suggestion)

    lignes_besoin = (LigneBesoinAchat.objects
                      .filter(besoin__entreprise=entreprise, besoin__statut='validee', ligne_commande__isnull=True)
                      .select_related('article__fournisseur', 'besoin'))
    for lb in lignes_besoin:
        a = lb.article
        suggestion = {'source': 'besoin', 'checkbox_id': f'besoin:{lb.pk}',
                      'article': a, 'qte': lb.quantite_demandee, 'prix': a.cout_unitaire,
                      'besoin_ref': lb.besoin.reference}
        if a.fournisseur_id:
            groupes.setdefault(a.fournisseur, []).append(suggestion)
        else:
            sans_fournisseur.append(suggestion)

    groupes_list = sorted(groupes.items(), key=lambda kv: kv[0].nom)
    total_articles = sum(len(v) for v in groupes.values()) + len(sans_fournisseur)
    return render(request, 'stock/reapprovisionnement.html', {
        'groupes': groupes_list, 'sans_fournisseur': sans_fournisseur,
        'total_articles': total_articles, 'nb_besoins_en_attente': lignes_besoin.count(),
    })


# ===========================================================================
# API — page d'information
# ===========================================================================
@reauth_required
@login_required
@stock_required
def api_info(request):
    endpoints = [
        ('GET', 'api/articles/', 'Catalogue des articles (stock, prix, CMUP, valeur)'),
        ('POST/PUT', 'api/articles/', 'Créer / modifier un article (rôle stock)'),
        ('GET', 'api/categories/', 'Catégories'),
        ('GET', 'api/fournisseurs/', 'Fournisseurs'),
        ('GET', 'api/depots/', 'Dépôts'),
        ('GET', 'api/clients/', 'Clients'),
        ('GET', 'api/lots/', 'Lots (péremption)'),
        ('GET', 'api/mouvements/', 'Mouvements de stock'),
        ('POST', 'api/mouvements/', 'Créer un mouvement entrée/sortie/ajustement (rôle stock)'),
        ('GET', 'api/commandes/', 'Commandes fournisseurs'),
        ('GET', 'api/ventes/', 'Documents de vente (devis/factures)'),
        ('POST', 'api/token/', 'Obtenir un jeton (username + password)'),
    ]
    return render(request, 'stock/api_info.html', {'endpoints': endpoints})
