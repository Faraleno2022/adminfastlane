"""Sérialiseurs DRF du module Stock (API REST)."""
from rest_framework import serializers

from .models import (
    CategorieArticle, Fournisseur, Depot, Article, MouvementStock,
    Client, DocumentVente, CommandeFournisseur, Lot,
)


class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieArticle
        fields = ['id', 'nom', 'description', 'actif']


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ['id', 'nom', 'contact', 'telephone', 'email', 'nif', 'actif']


class DepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Depot
        fields = ['id', 'nom', 'type_depot', 'code', 'responsable', 'par_defaut', 'actif']


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'nom', 'type_client', 'telephone', 'email', 'nif', 'remise_defaut', 'actif']


class ArticleSerializer(serializers.ModelSerializer):
    categorie_nom = serializers.CharField(source='categorie.nom', read_only=True, default=None)
    valeur_stock = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    cout_unitaire = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    en_rupture = serializers.BooleanField(read_only=True)
    en_alerte = serializers.BooleanField(read_only=True)

    class Meta:
        model = Article
        fields = ['id', 'reference', 'code_barres', 'designation', 'categorie', 'categorie_nom',
                  'unite', 'prix_achat', 'prix_vente', 'cmup', 'cout_unitaire', 'quantite_stock',
                  'seuil_alerte', 'stock_max', 'valeur_stock', 'emplacement',
                  'en_rupture', 'en_alerte', 'actif']
        read_only_fields = ['cmup', 'quantite_stock']


class MouvementSerializer(serializers.ModelSerializer):
    article_designation = serializers.CharField(source='article.designation', read_only=True)
    depot_nom = serializers.CharField(source='depot.nom', read_only=True, default=None)

    class Meta:
        model = MouvementStock
        fields = ['id', 'date_mouvement', 'type_mouvement', 'article', 'article_designation',
                  'depot', 'depot_nom', 'quantite', 'quantite_avant', 'quantite_apres',
                  'prix_unitaire', 'motif', 'reference_document']


class LotSerializer(serializers.ModelSerializer):
    article_designation = serializers.CharField(source='article.designation', read_only=True)
    jours_avant_peremption = serializers.IntegerField(read_only=True)
    est_perime = serializers.BooleanField(read_only=True)

    class Meta:
        model = Lot
        fields = ['id', 'numero_lot', 'article', 'article_designation', 'depot',
                  'date_peremption', 'quantite_restante', 'jours_avant_peremption', 'est_perime']


class CommandeFournisseurSerializer(serializers.ModelSerializer):
    fournisseur_nom = serializers.CharField(source='fournisseur.nom', read_only=True)
    montant_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = CommandeFournisseur
        fields = ['id', 'reference', 'fournisseur', 'fournisseur_nom', 'depot', 'date_commande',
                  'statut', 'montant_total']


class DocumentVenteSerializer(serializers.ModelSerializer):
    client_nom = serializers.CharField(source='client.nom', read_only=True)
    montant_ttc = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    montant_du = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = DocumentVente
        fields = ['id', 'reference', 'type_document', 'client', 'client_nom', 'date_document',
                  'statut', 'montant_ttc', 'montant_paye', 'montant_du']


class MouvementCreateSerializer(serializers.Serializer):
    """Création d'un mouvement (entrée / sortie / ajustement) dans un dépôt."""
    article = serializers.IntegerField()
    depot = serializers.IntegerField()
    type_mouvement = serializers.ChoiceField(choices=['entree', 'sortie', 'ajustement'])
    quantite = serializers.DecimalField(max_digits=14, decimal_places=2)
    prix_unitaire = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)
    motif = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_quantite(self, v):
        type_mouvement = self.initial_data.get('type_mouvement')
        if v is None or (type_mouvement == 'ajustement' and v < 0) or (type_mouvement != 'ajustement' and v <= 0):
            raise serializers.ValidationError("Quantité invalide.")
        return v
