from django.apps import AppConfig


class StockConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stock'
    verbose_name = 'Gestion du Stock'

    def ready(self):
        # Connecte les signaux du journal d'audit.
        from . import audit
        audit.connecter_signaux()
