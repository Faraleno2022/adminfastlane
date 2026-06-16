"""
Module Gestion du Stock — Vues
Tableau de bord, articles, catégories, fournisseurs, mouvements de stock
(entrées / sorties / ajustements), inventaires physiques et rapports.
"""
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Sum, F, DecimalField, ExpressionWrapper

from django.utils import timezone

from core.decorators import reauth_required

from .models import (
    CategorieArticle, Fournisseur, Article, MouvementStock,
    Inventaire, LigneInventaire,
)
from .forms import (
    CategorieArticleForm, FournisseurForm, ArticleForm,
    MouvementStockForm, InventaireForm,
)


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

    derniers_mouvements = (MouvementStock.objects
                           .filter(entreprise=entreprise)
                           .select_related('article')[:10])

    stats = {
        'total_articles': articles.count(),
        'total_categories': CategorieArticle.objects.filter(entreprise=entreprise).count(),
        'total_fournisseurs': Fournisseur.objects.filter(entreprise=entreprise).count(),
        'valeur_totale': valeur_totale,
        'nb_alerte': len(articles_alerte),
        'nb_rupture': len(articles_rupture),
        'mouvements_jour': MouvementStock.objects.filter(
            entreprise=entreprise, date_mouvement__date=timezone.now().date()
        ).count(),
        'inventaires_en_cours': Inventaire.objects.filter(entreprise=entreprise, statut='en_cours').count(),
    }

    return render(request, 'stock/dashboard.html', {
        'stats': stats,
        'articles_alerte': articles_alerte[:10],
        'articles_rupture': articles_rupture[:10],
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
    mouvements = article.mouvements.select_related('fournisseur')[:50]
    return render(request, 'stock/article_detail.html', {
        'article': article, 'mouvements': mouvements,
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
    if request.method == 'POST':
        form = MouvementStockForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            with transaction.atomic():
                mouvement = form.save(commit=False)
                # Verrou sur l'article pour éviter les courses sur la quantité.
                article = Article.objects.select_for_update().get(
                    pk=mouvement.article_id, entreprise=entreprise
                )
                avant = article.quantite_stock or Decimal('0')
                quantite = mouvement.quantite

                if mouvement.type_mouvement == 'entree':
                    apres = avant + quantite
                elif mouvement.type_mouvement == 'sortie':
                    if quantite > avant:
                        messages.error(
                            request,
                            f"Stock insuffisant : {avant} en stock, sortie de {quantite} demandée."
                        )
                        return render(request, 'stock/form.html', {
                            'form': form, 'titre': 'Nouveau mouvement de stock',
                            'retour': 'stock:mouvement_list',
                        })
                    apres = avant - quantite
                else:  # ajustement : la quantité saisie devient le stock réel
                    apres = quantite

                mouvement.entreprise = entreprise
                mouvement.quantite_avant = avant
                mouvement.quantite_apres = apres
                mouvement.cree_par = request.user
                mouvement.save()

                article.quantite_stock = apres
                article.save(update_fields=['quantite_stock', 'date_modification'])

            messages.success(
                request,
                f"Mouvement enregistré. Stock de « {article.designation} » : {apres}."
            )
            return redirect('stock:mouvement_list')
    else:
        form = MouvementStockForm(entreprise=entreprise, initial={'type_mouvement': type_initial})
    return render(request, 'stock/form.html', {
        'form': form, 'titre': 'Nouveau mouvement de stock', 'retour': 'stock:mouvement_list',
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
    if request.method == 'POST':
        form = InventaireForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                inv = form.save(commit=False)
                inv.entreprise = entreprise
                inv.reference = _generer_reference(Inventaire, entreprise, 'INV')
                inv.cree_par = request.user
                inv.save()
                # Pré-remplir avec tous les articles actifs (stock théorique courant).
                lignes = [
                    LigneInventaire(
                        inventaire=inv, article=a,
                        quantite_theorique=a.quantite_stock,
                        quantite_physique=a.quantite_stock,
                        ecart=0,
                    )
                    for a in Article.objects.filter(entreprise=entreprise, actif=True)
                ]
                LigneInventaire.objects.bulk_create(lignes)
            messages.success(request, f"Inventaire {inv.reference} créé avec {len(lignes)} article(s).")
            return redirect('stock:inventaire_detail', pk=inv.pk)
    else:
        form = InventaireForm()
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
        with transaction.atomic():
            for ligne in inv.lignes.select_related('article'):
                if ligne.ecart == 0:
                    continue
                article = Article.objects.select_for_update().get(pk=ligne.article_id)
                avant = article.quantite_stock or Decimal('0')
                MouvementStock.objects.create(
                    entreprise=entreprise,
                    article=article,
                    type_mouvement='ajustement',
                    quantite=ligne.quantite_physique,
                    quantite_avant=avant,
                    quantite_apres=ligne.quantite_physique,
                    prix_unitaire=article.prix_achat,
                    motif=f"Ajustement inventaire {inv.reference}",
                    reference_document=inv.reference,
                    cree_par=request.user,
                )
                article.quantite_stock = ligne.quantite_physique
                article.save(update_fields=['quantite_stock', 'date_modification'])
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
