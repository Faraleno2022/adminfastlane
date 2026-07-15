"""API REST du module Stock (DRF).

Authentification : session (navigateur) ou token (intégrations serveur).
Chaque endpoint est cloisonné par entreprise. La plupart sont en lecture
seule ; la création de mouvements de stock est autorisée (rôle 'stock').
"""
from decimal import Decimal

from rest_framework import viewsets, mixins, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import (
    CategorieArticle, Fournisseur, Depot, Article, MouvementStock,
    Client, DocumentVente, CommandeFournisseur, Lot,
)
from . import serializers as s
from .permissions import a_permission
from .views import appliquer_mouvement_depot, maj_cmup


class BaseStockViewSet(viewsets.ReadOnlyModelViewSet):
    """Base : auth session/token, cloisonnement par entreprise."""
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def _entreprise(self):
        return getattr(self.request.user, 'entreprise', None)

    def get_queryset(self):
        entreprise = self._entreprise()
        if entreprise is None:
            return self.queryset.none()
        return self.queryset.filter(entreprise=entreprise)


class CategorieViewSet(BaseStockViewSet):
    queryset = CategorieArticle.objects.all()
    serializer_class = s.CategorieSerializer


class FournisseurViewSet(BaseStockViewSet):
    queryset = Fournisseur.objects.all()
    serializer_class = s.FournisseurSerializer


class DepotViewSet(BaseStockViewSet):
    queryset = Depot.objects.all()
    serializer_class = s.DepotSerializer


class ClientViewSet(BaseStockViewSet):
    queryset = Client.objects.all()
    serializer_class = s.ClientSerializer


class LotViewSet(BaseStockViewSet):
    queryset = Lot.objects.select_related('article').all()
    serializer_class = s.LotSerializer


class CommandeViewSet(BaseStockViewSet):
    queryset = CommandeFournisseur.objects.select_related('fournisseur').all()
    serializer_class = s.CommandeFournisseurSerializer


class VenteViewSet(BaseStockViewSet):
    queryset = DocumentVente.objects.select_related('client').all()
    serializer_class = s.DocumentVenteSerializer


class ArticleViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, BaseStockViewSet):
    """Catalogue : lecture pour tous, création/maj réservée au rôle 'stock'."""
    queryset = Article.objects.select_related('categorie').all()
    serializer_class = s.ArticleSerializer

    def perform_create(self, serializer):
        if not a_permission(self.request.user, 'stock'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Rôle insuffisant.")
        serializer.save(entreprise=self._entreprise(), cree_par=self.request.user)

    def perform_update(self, serializer):
        if not a_permission(self.request.user, 'stock'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Rôle insuffisant.")
        serializer.save()


class MouvementViewSet(mixins.CreateModelMixin, BaseStockViewSet):
    """Mouvements : lecture + création (entrée / sortie / ajustement)."""
    queryset = MouvementStock.objects.select_related('article', 'depot').all()
    serializer_class = s.MouvementSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return s.MouvementCreateSerializer
        return s.MouvementSerializer

    def create(self, request, *args, **kwargs):
        entreprise = self._entreprise()
        if entreprise is None:
            return Response({'detail': "Aucune entreprise."}, status=status.HTTP_400_BAD_REQUEST)
        if not a_permission(request.user, 'stock'):
            return Response({'detail': "Rôle insuffisant."}, status=status.HTTP_403_FORBIDDEN)
        ser = s.MouvementCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        article = get_object_or_404(Article, pk=data['article'], entreprise=entreprise)
        depot = get_object_or_404(Depot, pk=data['depot'], entreprise=entreprise)
        type_mvt = data['type_mouvement']
        quantite = data['quantite']
        prix = data.get('prix_unitaire') or Decimal('0')

        with transaction.atomic():
            verrou = Article.objects.select_for_update().get(pk=article.pk)
            stock_depot = verrou.stock_dans(depot)
            if type_mvt == 'sortie' and quantite > stock_depot:
                return Response(
                    {'detail': f"Stock insuffisant dans {depot.nom} ({stock_depot} disponible(s))."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            stock_avant = verrou.quantite_stock or Decimal('0')
            avant, apres = appliquer_mouvement_depot(verrou, depot, type_mvt, quantite)
            if type_mvt == 'entree':
                maj_cmup(verrou, quantite, prix, stock_avant)
                prix_mouvement = prix
                quantite_mouvement = quantite
            else:
                prix_mouvement = verrou.cout_unitaire
                quantite_mouvement = apres - avant if type_mvt == 'ajustement' else quantite
            mvt = MouvementStock.objects.create(
                entreprise=entreprise, article=verrou, depot=depot, type_mouvement=type_mvt,
                quantite=quantite_mouvement, quantite_avant=avant, quantite_apres=apres,
                prix_unitaire=prix_mouvement,
                motif=data.get('motif', ''), cree_par=request.user,
            )
        return Response(s.MouvementSerializer(mvt).data, status=status.HTTP_201_CREATED)


router = DefaultRouter()
router.register('articles', ArticleViewSet, basename='api-article')
router.register('categories', CategorieViewSet, basename='api-categorie')
router.register('fournisseurs', FournisseurViewSet, basename='api-fournisseur')
router.register('depots', DepotViewSet, basename='api-depot')
router.register('clients', ClientViewSet, basename='api-client')
router.register('lots', LotViewSet, basename='api-lot')
router.register('mouvements', MouvementViewSet, basename='api-mouvement')
router.register('commandes', CommandeViewSet, basename='api-commande')
router.register('ventes', VenteViewSet, basename='api-vente')
