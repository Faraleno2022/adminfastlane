from decimal import Decimal
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('stock', '0011_alter_client_remise_defaut_and_more')]
    operations = [migrations.CreateModel(name='ParametresCommerciaux', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('devise', models.CharField(default='GNF', max_length=3, verbose_name='Devise principale')),
        ('taux_tva_defaut', models.DecimalField(decimal_places=2, default=18, max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='TVA par défaut (%)')),
        ('methode_valorisation', models.CharField(choices=[('cmup', 'Coût moyen pondéré (CMUP)'), ('fifo', 'FIFO')], default='cmup', max_length=10, verbose_name='Méthode de valorisation')),
        ('stock_negatif_autorise', models.BooleanField(default=False, verbose_name='Autoriser le stock négatif')),
        ('remise_max_vendeur', models.DecimalField(decimal_places=2, default=5, max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='Remise maximale vendeur (%)')),
        ('remise_max_responsable', models.DecimalField(decimal_places=2, default=20, max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='Remise maximale responsable (%)')),
        ('vente_credit_autorisee', models.BooleanField(default=True, verbose_name='Autoriser les ventes à crédit')),
        ('delai_credit_jours', models.PositiveIntegerField(default=30, verbose_name='Délai de crédit par défaut (jours)')),
        ('prefixe_facture', models.CharField(default='FAC', max_length=12, verbose_name='Préfixe des factures')),
        ('numerotation_annuelle', models.BooleanField(default=True, verbose_name='Réinitialiser la numérotation chaque année')),
        ('alerte_stock_faible', models.BooleanField(default=True, verbose_name='Alerte de stock faible')),
        ('alerte_peremption_jours', models.PositiveIntegerField(default=30, verbose_name='Alerte avant péremption (jours)')),
        ('conditions_vente', models.TextField(blank=True, verbose_name='Conditions générales de vente')),
        ('date_modification', models.DateTimeField(auto_now=True)),
        ('entreprise', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='parametres_commerciaux', to='core.entreprise')),
    ], options={'verbose_name': 'Paramètres commerciaux', 'db_table': 'stock_parametres_commerciaux'})]
