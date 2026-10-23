"""Opérations de migration propres à temps_travail."""
from django.db import migrations


class AjouterChampSiAbsent(migrations.AddField):
    """AddField qui laisse la base intacte quand la colonne existe déjà.

    Les migrations 0006_absence_approuve_par_… et 0006_reglementationtemps_… ont
    été créées en parallèle et ajoutent toutes deux les mêmes colonnes à
    reglementation_temps : sur une base neuve, la seconde appliquée échouait
    (« column … already exists »). L'état des modèles reste celui d'un AddField.
    """

    def _colonne_existe(self, app_label, schema_editor, state):
        modele = state.apps.get_model(app_label, self.model_name)
        connexion = schema_editor.connection
        with connexion.cursor() as curseur:
            colonnes = {c.name for c in connexion.introspection.get_table_description(curseur, modele._meta.db_table)}
        return modele._meta.get_field(self.name).column in colonnes

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self._colonne_existe(app_label, schema_editor, to_state):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
