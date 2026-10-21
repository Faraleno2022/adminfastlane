import calendar
import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from .mixins import BaseCreer, BaseListe, BaseModifier, BaseSupprimer
from .permissions import peut_saisir

from .forms import EmployeFlotteForm
from .models import EmployeFlotte, Pointage

JOURS_ABBR = ["L", "M", "M", "J", "V", "S", "D"]  # lundi..dimanche
MOIS_NOMS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


# ---------------------------------------------------------------- Employés
class EmployeListe(BaseListe):
    model = EmployeFlotte
    titre = "Employés"
    colonnes = [
        ("Nom complet", "nom_complet"),
        ("Matricule", "matricule"),
        ("Fonction", "fonction"),
        ("Service", "service"),
        ("Téléphone", "telephone"),
        ("N° de permis", "numero_permis"),
        ("Actif", "actif"),
    ]
    url_creer = "flotte:employe_creer"
    url_modifier = "flotte:employe_modifier"
    url_supprimer = "flotte:employe_supprimer"


class EmployeCreer(BaseCreer):
    model = EmployeFlotte
    form_class = EmployeFlotteForm
    success_url = reverse_lazy("flotte:employe_liste")
    titre = "Ajouter un employé"


class EmployeModifier(BaseModifier):
    model = EmployeFlotte
    form_class = EmployeFlotteForm
    success_url = reverse_lazy("flotte:employe_liste")
    titre = "Modifier l'employé"


class EmployeSupprimer(BaseSupprimer):
    model = EmployeFlotte
    success_url = reverse_lazy("flotte:employe_liste")


# ------------------------------------------------------------ Calcul totaux
def totaux_employe(emp, annee, mois) -> dict:
    """Comptage des statuts d'un employé pour un mois donné."""
    compteur = {code: 0 for code, _ in Pointage.STATUTS}
    qs = Pointage.objects.filter(employe=emp, date__year=annee, date__month=mois)
    for p in qs.values_list("statut", flat=True):
        if p in compteur:
            compteur[p] += 1
    nb_presence = sum(compteur[c] for c in Pointage.STATUTS_PRESENCE)
    nb_absence = compteur[Pointage.ABSENT]
    return {
        "compteur": compteur,
        "nb_presence": nb_presence,
        "nb_absence": nb_absence,
        "nb_conge": compteur[Pointage.CONGE],
        "nb_mission": compteur[Pointage.MISSION],
        "nb_repos": compteur[Pointage.REPOS],
        "nb_maladie": compteur[Pointage.MALADIE],
        "nb_retard": compteur[Pointage.RETARD],
        "nb_sanction": compteur[Pointage.SANCTION],
    }


# -------------------------------------------------------------- Grille mois
@login_required
def grille(request):
    aujourdhui = timezone.localdate()
    mois_param = request.GET.get("mois")  # format AAAA-MM
    try:
        annee, mois = map(int, mois_param.split("-"))
        datetime.date(annee, mois, 1)
    except (AttributeError, ValueError):
        annee, mois = aujourdhui.year, aujourdhui.month

    nb_jours = calendar.monthrange(annee, mois)[1]
    jours = []
    for d in range(1, nb_jours + 1):
        dt = datetime.date(annee, mois, d)
        wd = dt.weekday()  # 0 = lundi
        jours.append({
            "num": d,
            "iso": dt.isoformat(),
            "abbr": JOURS_ABBR[wd],
            "weekend": wd >= 5,
        })

    employes = list(EmployeFlotte.objects.filter(actif=True))

    # Chargement de tous les pointages du mois en une requête.
    existants = {}
    for p in Pointage.objects.filter(
        employe__in=employes, date__year=annee, date__month=mois
    ).values_list("employe_id", "date", "statut"):
        existants[(p[0], p[1].day)] = p[2]

    lignes = []
    for emp in employes:
        cellules = []
        for j in jours:
            cellules.append({
                "iso": j["iso"],
                "statut": existants.get((emp.id, j["num"]), ""),
                "weekend": j["weekend"],
            })
        lignes.append({
            "employe": emp,
            "cellules": cellules,
            "totaux": totaux_employe(emp, annee, mois),
        })

    # Mois précédent / suivant
    prem = datetime.date(annee, mois, 1)
    mois_prec = (prem - datetime.timedelta(days=1)).strftime("%Y-%m")
    mois_suiv = (datetime.date(annee, mois, nb_jours) + datetime.timedelta(days=1)).strftime("%Y-%m")

    contexte = {
        "titre": "Pointage de présence",
        "annee": annee,
        "mois": mois,
        "mois_param": f"{annee:04d}-{mois:02d}",
        "mois_libelle": f"{MOIS_NOMS[mois - 1].capitalize()} {annee}",
        "jours": jours,
        "lignes": lignes,
        "statuts": Pointage.STATUTS,
        "mois_prec": mois_prec,
        "mois_suiv": mois_suiv,
        "peut_saisir": peut_saisir(request.user),
    }
    return render(request, "flotte/pointage/grille.html", contexte)


# --------------------------------------------------- Enregistrement (AJAX)
@login_required
@require_POST
def enregistrer(request):
    if not peut_saisir(request.user):
        return JsonResponse({"ok": False, "erreur": "Droit insuffisant."}, status=403)

    employe_id = request.POST.get("employe")
    date_str = request.POST.get("date")
    statut = (request.POST.get("statut") or "").strip()

    try:
        emp = EmployeFlotte.objects.get(pk=employe_id)
        date = datetime.date.fromisoformat(date_str)
    except (EmployeFlotte.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"ok": False, "erreur": "Données invalides."}, status=400)

    codes_valides = {c for c, _ in Pointage.STATUTS}
    pk = Pointage.pk_for(emp.id, date)
    existant = Pointage.all_objects.filter(pk=pk).first()

    if statut == "":
        # Cellule vidée : suppression logique du pointage éventuel.
        if existant and not existant.is_deleted:
            existant.delete()
    elif statut in codes_valides:
        if existant:
            existant.statut = statut
            existant.is_deleted = False
            existant.deleted_at = None
            existant.save()
        else:
            p = Pointage(id=pk, employe=emp, date=date, statut=statut)
            p.save()
    else:
        return JsonResponse({"ok": False, "erreur": "Statut inconnu."}, status=400)

    t = totaux_employe(emp, date.year, date.month)
    return JsonResponse({
        "ok": True,
        "nb_presence": t["nb_presence"],
        "nb_absence": t["nb_absence"],
        "nb_conge": t["nb_conge"],
        "nb_mission": t["nb_mission"],
        "nb_repos": t["nb_repos"],
        "nb_maladie": t["nb_maladie"],
        "nb_retard": t["nb_retard"],
        "nb_sanction": t["nb_sanction"],
    })
