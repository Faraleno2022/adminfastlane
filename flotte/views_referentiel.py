import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy

from .mixins import (
    BaseCreerReferentiel as BaseCreer,
    BaseListe,
    BaseModifierReferentiel as BaseModifier,
    BaseSupprimerReferentiel as BaseSupprimer,
)

from .permissions import peut_gerer_referentiel

from .forms import (
    CategorieRouesForm,
    ChauffeurForm,
    DocumentVehiculeForm,
    EnginForm,
    MarqueForm,
    VehiculeForm,
)
from .models import CategorieRoues, Chauffeur, DocumentVehicule, Engin, Marque, Vehicule


# --- Catégories de roues -------------------------------------------------
class CategorieListe(BaseListe):
    permission_edition = "referentiel"
    model = CategorieRoues
    titre = "Catégories de roues"
    colonnes = [("Libellé", "libelle")]
    url_creer = "flotte:categorie_creer"
    url_modifier = "flotte:categorie_modifier"
    url_supprimer = "flotte:categorie_supprimer"


class CategorieCreer(BaseCreer):
    model = CategorieRoues
    form_class = CategorieRouesForm
    success_url = reverse_lazy("flotte:categorie_liste")
    titre = "Ajouter une catégorie"


class CategorieModifier(BaseModifier):
    model = CategorieRoues
    form_class = CategorieRouesForm
    success_url = reverse_lazy("flotte:categorie_liste")
    titre = "Modifier la catégorie"


class CategorieSupprimer(BaseSupprimer):
    model = CategorieRoues
    success_url = reverse_lazy("flotte:categorie_liste")


# --- Marques -------------------------------------------------------------
class MarqueListe(BaseListe):
    permission_edition = "referentiel"
    model = Marque
    titre = "Marques"
    colonnes = [("Marque", "nom")]
    url_creer = "flotte:marque_creer"
    url_modifier = "flotte:marque_modifier"
    url_supprimer = "flotte:marque_supprimer"


class MarqueCreer(BaseCreer):
    model = Marque
    form_class = MarqueForm
    success_url = reverse_lazy("flotte:marque_liste")
    titre = "Ajouter une marque"


class MarqueModifier(BaseModifier):
    model = Marque
    form_class = MarqueForm
    success_url = reverse_lazy("flotte:marque_liste")
    titre = "Modifier la marque"


class MarqueSupprimer(BaseSupprimer):
    model = Marque
    success_url = reverse_lazy("flotte:marque_liste")


# --- Chauffeurs ----------------------------------------------------------
class ChauffeurListe(BaseListe):
    permission_edition = "referentiel"
    model = Chauffeur
    titre = "Chauffeurs"
    colonnes = [
        ("Prénoms et Noms", "nom_prenoms"),
        ("Téléphone", "telephone"),
        ("Actif", "actif"),
    ]
    url_creer = "flotte:chauffeur_creer"
    url_modifier = "flotte:chauffeur_modifier"
    url_supprimer = "flotte:chauffeur_supprimer"


class ChauffeurCreer(BaseCreer):
    model = Chauffeur
    form_class = ChauffeurForm
    success_url = reverse_lazy("flotte:chauffeur_liste")
    titre = "Ajouter un chauffeur"


class ChauffeurModifier(BaseModifier):
    model = Chauffeur
    form_class = ChauffeurForm
    success_url = reverse_lazy("flotte:chauffeur_liste")
    titre = "Modifier le chauffeur"


class ChauffeurSupprimer(BaseSupprimer):
    model = Chauffeur
    success_url = reverse_lazy("flotte:chauffeur_liste")


# --- Véhicules -----------------------------------------------------------
class VehiculeListe(BaseListe):
    permission_edition = "referentiel"
    model = Vehicule
    titre = "Véhicules"
    colonnes = [
        ("Immatriculation", "immatriculation"),
        ("Marque", "marque"),
        ("Type", "type_vehicule"),
        ("Capacité", "get_capacite_tonnes_display"),
        ("Chauffeurs", "noms_chauffeurs"),
        ("N° de châssis", "numero_chassis"),
        ("Documents", "etat_documents"),
        ("En service", "actif"),
    ]
    url_creer = "flotte:vehicule_creer"
    url_modifier = "flotte:vehicule_modifier"
    url_supprimer = "flotte:vehicule_supprimer"
    url_detail = "flotte:vehicule_detail"
    libelle_detail = "Documents"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("marque", "chauffeur_actuel", "chauffeur_secondaire")
            .prefetch_related("documents")
        )


class VehiculeCreer(BaseCreer):
    model = Vehicule
    form_class = VehiculeForm
    success_url = reverse_lazy("flotte:vehicule_liste")
    titre = "Ajouter un véhicule"


class VehiculeModifier(BaseModifier):
    model = Vehicule
    form_class = VehiculeForm
    success_url = reverse_lazy("flotte:vehicule_liste")
    titre = "Modifier le véhicule"


class VehiculeSupprimer(BaseSupprimer):
    model = Vehicule
    success_url = reverse_lazy("flotte:vehicule_liste")


@login_required
def vehicule_detail(request, pk):
    """Fiche du véhicule avec ses documents (carte grise, assurance, …)."""
    vehicule = get_object_or_404(Vehicule.objects.select_related("marque", "chauffeur_actuel", "chauffeur_secondaire"), pk=pk
    )
    return render(request, "flotte/referentiel/vehicule_detail.html", {
        "titre": f"Véhicule {vehicule.immatriculation}",
        "vehicule": vehicule,
        "documents": vehicule.documents.order_by("type_document", "-date_expiration"),
        "peut_editer": peut_gerer_referentiel(request.user),
    })


# --- Documents des véhicules ---------------------------------------------
@login_required
def document_liste(request):
    """Tous les documents, filtrables par état (alertes d'expiration)."""
    filtre = request.GET.get("statut", "")
    documents = DocumentVehicule.objects.filter(vehicule__is_deleted=False).select_related("vehicule")
    if filtre == "alerte":
        documents = DocumentVehicule.en_alerte()
    documents = list(documents)
    if filtre in (DocumentVehicule.EXPIRE, DocumentVehicule.BIENTOT):
        documents = [d for d in documents if d.statut == filtre]
    return render(request, "flotte/referentiel/document_liste.html", {
        "titre": "Documents des véhicules",
        "documents": documents,
        "filtre": filtre,
        "delai": DocumentVehicule.delai_alerte().days,
        "peut_editer": peut_gerer_referentiel(request.user),
    })


class _DocumentRetourVehicule:
    """Après enregistrement/suppression, revient sur la fiche du véhicule."""

    def get_success_url(self):
        return reverse("flotte:vehicule_detail", args=[self.object.vehicule_id])


class DocumentCreer(_DocumentRetourVehicule, BaseCreer):
    model = DocumentVehicule
    form_class = DocumentVehiculeForm
    titre = "Joindre un document"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("vehicule"):
            initial["vehicule"] = self.request.GET["vehicule"]
        return initial


class DocumentModifier(_DocumentRetourVehicule, BaseModifier):
    model = DocumentVehicule
    form_class = DocumentVehiculeForm
    titre = "Modifier le document"


class DocumentSupprimer(_DocumentRetourVehicule, BaseSupprimer):
    model = DocumentVehicule


@login_required
def document_fichier(request, pk):
    """Sert la pièce jointe aux seuls utilisateurs connectés."""
    document = get_object_or_404(DocumentVehicule, pk=pk)
    if not document.fichier:
        raise Http404("Aucun fichier joint.")
    try:
        fichier = document.fichier.open("rb")
    except (FileNotFoundError, OSError):
        messages.warning(
            request,
            "Le fichier n'est pas disponible sur ce poste (joint depuis un autre poste).",
        )
        return redirect("flotte:vehicule_detail", pk=document.vehicule_id)
    return FileResponse(fichier, filename=os.path.basename(document.fichier.name))


# --- Engins --------------------------------------------------------------
class EnginListe(BaseListe):
    permission_edition = "referentiel"
    model = Engin
    titre = "Engins"
    colonnes = [
        ("Nom", "nom"),
        ("Type", "get_type_engin_display"),
        ("Capacité", "capacite"),
        ("En service", "actif"),
    ]
    url_creer = "flotte:engin_creer"
    url_modifier = "flotte:engin_modifier"
    url_supprimer = "flotte:engin_supprimer"


class EnginCreer(BaseCreer):
    model = Engin
    form_class = EnginForm
    success_url = reverse_lazy("flotte:engin_liste")
    titre = "Ajouter un engin"


class EnginModifier(BaseModifier):
    model = Engin
    form_class = EnginForm
    success_url = reverse_lazy("flotte:engin_liste")
    titre = "Modifier l'engin"


class EnginSupprimer(BaseSupprimer):
    model = Engin
    success_url = reverse_lazy("flotte:engin_liste")
