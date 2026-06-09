"""
Module Secrétariat — Vues
Dashboard, gestion du courrier, rendez-vous, visiteurs, appels, documents,
tâches, contacts, réunions, rapports et paramètres.
"""
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone

from core.decorators import reauth_required

from .models import (
    Courrier, RendezVous, Visiteur, Appel, Document, Tache,
    Contact, Reunion, ActionReunion, ModeleDocument,
)
from .forms import (
    CourrierForm, RendezVousForm, VisiteurForm, AppelForm, DocumentForm,
    TacheForm, ContactForm, ReunionForm, ActionReunionForm, ModeleDocumentForm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def secretariat_required(view_func):
    """Vérifie que l'utilisateur est rattaché à une entreprise active."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:login')
        if not getattr(request.user, 'entreprise', None):
            messages.error(request, "Vous devez être associé à une entreprise.")
            return redirect('dashboard:index')
        return view_func(request, *args, **kwargs)
    return wrapper


def generer_numero_courrier(entreprise):
    """Génère un numéro d'ordre automatique : COUR-AAAA-0001 par entreprise."""
    annee = datetime.now().year
    prefixe = f"COUR-{annee}-"
    for _ in range(10):
        with transaction.atomic():
            dernier = (Courrier.objects
                       .select_for_update()
                       .filter(entreprise=entreprise, numero_ordre__startswith=prefixe)
                       .order_by('-numero_ordre')
                       .first())
            if dernier:
                try:
                    numero = int(dernier.numero_ordre.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    numero = 1
            else:
                numero = 1
            nouveau = f"{prefixe}{numero:04d}"
            if not Courrier.objects.filter(entreprise=entreprise, numero_ordre=nouveau).exists():
                return nouveau
    import time
    return f"{prefixe}{int(time.time()) % 10000:04d}"


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def dashboard(request):
    entreprise = request.user.entreprise
    today = timezone.now().date()
    debut_jour = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    fin_jour = debut_jour + timedelta(days=1)

    rdv_jour = (RendezVous.objects
                .filter(entreprise=entreprise, date_rdv__gte=debut_jour, date_rdv__lt=fin_jour)
                .exclude(statut='annule')
                .order_by('date_rdv'))

    courriers_a_traiter = Courrier.objects.filter(
        entreprise=entreprise, statut__in=['recu', 'en_attente']
    ).order_by('-date_courrier')[:8]

    taches_urgentes = Tache.objects.filter(
        entreprise=entreprise, etat__in=['a_faire', 'en_cours']
    ).filter(Q(priorite='urgente') | Q(date_limite__lte=today)).order_by('date_limite')[:8]

    appels_manques = Appel.objects.filter(
        entreprise=entreprise, type_appel='manque'
    ).order_by('-date_appel')[:8]

    documents_attente = Document.objects.filter(entreprise=entreprise).order_by('-date_creation')[:5]

    visiteurs_presents = Visiteur.objects.filter(
        entreprise=entreprise, heure_sortie__isnull=True
    ).order_by('-heure_arrivee')

    stats = {
        'rdv_jour': rdv_jour.count(),
        'courriers_a_traiter': Courrier.objects.filter(entreprise=entreprise, statut__in=['recu', 'en_attente']).count(),
        'taches_urgentes': Tache.objects.filter(entreprise=entreprise, etat__in=['a_faire', 'en_cours'], priorite='urgente').count(),
        'appels_manques': Appel.objects.filter(entreprise=entreprise, type_appel='manque').count(),
        'visiteurs_presents': visiteurs_presents.count(),
        'total_courriers': Courrier.objects.filter(entreprise=entreprise).count(),
        'total_documents': Document.objects.filter(entreprise=entreprise).count(),
        'total_contacts': Contact.objects.filter(entreprise=entreprise).count(),
        'reunions_planifiees': Reunion.objects.filter(entreprise=entreprise, statut='planifiee').count(),
    }

    return render(request, 'secretariat/dashboard.html', {
        'stats': stats,
        'rdv_jour': rdv_jour,
        'courriers_a_traiter': courriers_a_traiter,
        'taches_urgentes': taches_urgentes,
        'appels_manques': appels_manques,
        'documents_attente': documents_attente,
        'visiteurs_presents': visiteurs_presents,
    })


# ---------------------------------------------------------------------------
# Courrier
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def courrier_list(request):
    entreprise = request.user.entreprise
    courriers = Courrier.objects.filter(entreprise=entreprise)

    type_filter = request.GET.get('type', '')
    statut = request.GET.get('statut', '')
    recherche = request.GET.get('q', '')
    if type_filter:
        courriers = courriers.filter(type_courrier=type_filter)
    if statut:
        courriers = courriers.filter(statut=statut)
    if recherche:
        courriers = courriers.filter(
            Q(objet__icontains=recherche) | Q(expediteur__icontains=recherche) |
            Q(destinataire__icontains=recherche) | Q(numero_ordre__icontains=recherche)
        )

    return render(request, 'secretariat/courrier_list.html', {
        'courriers': courriers,
        'types': Courrier.TYPES,
        'statuts': Courrier.STATUTS,
        'type_filter': type_filter,
        'statut_filter': statut,
        'recherche': recherche,
    })


@reauth_required
@login_required
@secretariat_required
def courrier_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = CourrierForm(request.POST, request.FILES)
        if form.is_valid():
            courrier = form.save(commit=False)
            courrier.entreprise = entreprise
            courrier.numero_ordre = generer_numero_courrier(entreprise)
            courrier.cree_par = request.user
            courrier.save()
            messages.success(request, f"Courrier {courrier.numero_ordre} enregistré.")
            return redirect('secretariat:courrier_list')
    else:
        form = CourrierForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Enregistrer un courrier', 'retour': 'secretariat:courrier_list',
    })


@reauth_required
@login_required
@secretariat_required
def courrier_edit(request, pk):
    entreprise = request.user.entreprise
    courrier = get_object_or_404(Courrier, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        form = CourrierForm(request.POST, request.FILES, instance=courrier)
        if form.is_valid():
            form.save()
            messages.success(request, "Courrier mis à jour.")
            return redirect('secretariat:courrier_list')
    else:
        form = CourrierForm(instance=courrier)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': f'Modifier le courrier {courrier.numero_ordre}',
        'retour': 'secretariat:courrier_list',
    })


@reauth_required
@login_required
@secretariat_required
def courrier_delete(request, pk):
    courrier = get_object_or_404(Courrier, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        courrier.delete()
        messages.success(request, "Courrier supprimé.")
        return redirect('secretariat:courrier_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': courrier.numero_ordre, 'retour': 'secretariat:courrier_list',
    })


# ---------------------------------------------------------------------------
# Rendez-vous
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def rdv_list(request):
    entreprise = request.user.entreprise
    rdvs = RendezVous.objects.filter(entreprise=entreprise)

    statut = request.GET.get('statut', '')
    periode = request.GET.get('periode', '')
    if statut:
        rdvs = rdvs.filter(statut=statut)

    today = timezone.now().date()
    if periode == 'jour':
        rdvs = rdvs.filter(date_rdv__date=today)
    elif periode == 'semaine':
        debut = today - timedelta(days=today.weekday())
        rdvs = rdvs.filter(date_rdv__date__gte=debut, date_rdv__date__lt=debut + timedelta(days=7))
    elif periode == 'mois':
        rdvs = rdvs.filter(date_rdv__year=today.year, date_rdv__month=today.month)

    return render(request, 'secretariat/rdv_list.html', {
        'rdvs': rdvs, 'statuts': RendezVous.STATUTS,
        'statut_filter': statut, 'periode_filter': periode,
    })


@reauth_required
@login_required
@secretariat_required
def rdv_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = RendezVousForm(request.POST)
        if form.is_valid():
            rdv = form.save(commit=False)
            rdv.entreprise = entreprise
            rdv.cree_par = request.user
            rdv.save()
            messages.success(request, "Rendez-vous ajouté.")
            return redirect('secretariat:rdv_list')
    else:
        form = RendezVousForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Ajouter un rendez-vous', 'retour': 'secretariat:rdv_list',
    })


@reauth_required
@login_required
@secretariat_required
def rdv_edit(request, pk):
    rdv = get_object_or_404(RendezVous, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            form.save()
            messages.success(request, "Rendez-vous mis à jour.")
            return redirect('secretariat:rdv_list')
    else:
        form = RendezVousForm(instance=rdv)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier le rendez-vous', 'retour': 'secretariat:rdv_list',
    })


@reauth_required
@login_required
@secretariat_required
def rdv_delete(request, pk):
    rdv = get_object_or_404(RendezVous, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        rdv.delete()
        messages.success(request, "Rendez-vous supprimé.")
        return redirect('secretariat:rdv_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': str(rdv), 'retour': 'secretariat:rdv_list',
    })


# ---------------------------------------------------------------------------
# Visiteurs
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def visiteur_list(request):
    entreprise = request.user.entreprise
    visiteurs = Visiteur.objects.filter(entreprise=entreprise)
    recherche = request.GET.get('q', '')
    if recherche:
        visiteurs = visiteurs.filter(
            Q(nom__icontains=recherche) | Q(structure__icontains=recherche) | Q(motif__icontains=recherche)
        )
    return render(request, 'secretariat/visiteur_list.html', {
        'visiteurs': visiteurs, 'recherche': recherche,
    })


@reauth_required
@login_required
@secretariat_required
def visiteur_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = VisiteurForm(request.POST)
        if form.is_valid():
            v = form.save(commit=False)
            v.entreprise = entreprise
            v.cree_par = request.user
            v.save()
            messages.success(request, "Visiteur enregistré.")
            return redirect('secretariat:visiteur_list')
    else:
        form = VisiteurForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Enregistrer un visiteur', 'retour': 'secretariat:visiteur_list',
    })


@reauth_required
@login_required
@secretariat_required
def visiteur_edit(request, pk):
    v = get_object_or_404(Visiteur, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = VisiteurForm(request.POST, instance=v)
        if form.is_valid():
            form.save()
            messages.success(request, "Visiteur mis à jour.")
            return redirect('secretariat:visiteur_list')
    else:
        form = VisiteurForm(instance=v)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier le visiteur', 'retour': 'secretariat:visiteur_list',
    })


@reauth_required
@login_required
@secretariat_required
def visiteur_sortie(request, pk):
    """Marque l'heure de sortie d'un visiteur présent."""
    v = get_object_or_404(Visiteur, pk=pk, entreprise=request.user.entreprise)
    v.heure_sortie = timezone.now()
    v.save(update_fields=['heure_sortie'])
    messages.success(request, f"Sortie enregistrée pour {v.nom}.")
    return redirect('secretariat:visiteur_list')


@reauth_required
@login_required
@secretariat_required
def visiteur_badge(request, pk):
    """Fiche / badge visiteur imprimable."""
    v = get_object_or_404(Visiteur, pk=pk, entreprise=request.user.entreprise)
    return render(request, 'secretariat/visiteur_badge.html', {'v': v})


@reauth_required
@login_required
@secretariat_required
def visiteur_delete(request, pk):
    v = get_object_or_404(Visiteur, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        v.delete()
        messages.success(request, "Visiteur supprimé.")
        return redirect('secretariat:visiteur_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': v.nom, 'retour': 'secretariat:visiteur_list',
    })


# ---------------------------------------------------------------------------
# Appels
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def appel_list(request):
    entreprise = request.user.entreprise
    appels = Appel.objects.filter(entreprise=entreprise)
    type_filter = request.GET.get('type', '')
    if type_filter:
        appels = appels.filter(type_appel=type_filter)
    return render(request, 'secretariat/appel_list.html', {
        'appels': appels, 'types': Appel.TYPES, 'type_filter': type_filter,
    })


@reauth_required
@login_required
@secretariat_required
def appel_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = AppelForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.entreprise = entreprise
            a.cree_par = request.user
            a.save()
            messages.success(request, "Appel enregistré.")
            return redirect('secretariat:appel_list')
    else:
        form = AppelForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Enregistrer un appel', 'retour': 'secretariat:appel_list',
    })


@reauth_required
@login_required
@secretariat_required
def appel_edit(request, pk):
    a = get_object_or_404(Appel, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = AppelForm(request.POST, instance=a)
        if form.is_valid():
            form.save()
            messages.success(request, "Appel mis à jour.")
            return redirect('secretariat:appel_list')
    else:
        form = AppelForm(instance=a)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': "Modifier l'appel", 'retour': 'secretariat:appel_list',
    })


@reauth_required
@login_required
@secretariat_required
def appel_delete(request, pk):
    a = get_object_or_404(Appel, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        a.delete()
        messages.success(request, "Appel supprimé.")
        return redirect('secretariat:appel_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': str(a), 'retour': 'secretariat:appel_list',
    })


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def document_list(request):
    entreprise = request.user.entreprise
    documents = Document.objects.filter(entreprise=entreprise)
    categorie = request.GET.get('categorie', '')
    recherche = request.GET.get('q', '')
    if categorie:
        documents = documents.filter(categorie=categorie)
    if recherche:
        documents = documents.filter(
            Q(titre__icontains=recherche) | Q(reference__icontains=recherche) | Q(description__icontains=recherche)
        )
    return render(request, 'secretariat/document_list.html', {
        'documents': documents, 'categories': Document.CATEGORIES,
        'categorie_filter': categorie, 'recherche': recherche,
    })


@reauth_required
@login_required
@secretariat_required
def document_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            d = form.save(commit=False)
            d.entreprise = entreprise
            d.cree_par = request.user
            d.modifie_par = request.user
            d.save()
            messages.success(request, "Document ajouté.")
            return redirect('secretariat:document_list')
    else:
        form = DocumentForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Ajouter un document', 'retour': 'secretariat:document_list',
    })


@reauth_required
@login_required
@secretariat_required
def document_edit(request, pk):
    d = get_object_or_404(Document, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=d)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.modifie_par = request.user
            doc.save()
            messages.success(request, "Document mis à jour.")
            return redirect('secretariat:document_list')
    else:
        form = DocumentForm(instance=d)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier le document', 'retour': 'secretariat:document_list',
    })


@reauth_required
@login_required
@secretariat_required
def document_delete(request, pk):
    d = get_object_or_404(Document, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        d.delete()
        messages.success(request, "Document supprimé.")
        return redirect('secretariat:document_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': d.titre, 'retour': 'secretariat:document_list',
    })


# ---------------------------------------------------------------------------
# Tâches
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def tache_list(request):
    entreprise = request.user.entreprise
    taches = Tache.objects.filter(entreprise=entreprise)
    etat = request.GET.get('etat', '')
    priorite = request.GET.get('priorite', '')
    if etat:
        taches = taches.filter(etat=etat)
    if priorite:
        taches = taches.filter(priorite=priorite)
    return render(request, 'secretariat/tache_list.html', {
        'taches': taches, 'etats': Tache.ETATS, 'priorites': Tache.PRIORITES,
        'etat_filter': etat, 'priorite_filter': priorite,
    })


@reauth_required
@login_required
@secretariat_required
def tache_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = TacheForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.entreprise = entreprise
            t.cree_par = request.user
            t.save()
            messages.success(request, "Tâche créée.")
            return redirect('secretariat:tache_list')
    else:
        form = TacheForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Nouvelle tâche', 'retour': 'secretariat:tache_list',
    })


@reauth_required
@login_required
@secretariat_required
def tache_edit(request, pk):
    t = get_object_or_404(Tache, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = TacheForm(request.POST, instance=t)
        if form.is_valid():
            form.save()
            messages.success(request, "Tâche mise à jour.")
            return redirect('secretariat:tache_list')
    else:
        form = TacheForm(instance=t)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier la tâche', 'retour': 'secretariat:tache_list',
    })


@reauth_required
@login_required
@secretariat_required
def tache_delete(request, pk):
    t = get_object_or_404(Tache, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        t.delete()
        messages.success(request, "Tâche supprimée.")
        return redirect('secretariat:tache_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': t.titre, 'retour': 'secretariat:tache_list',
    })


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def contact_list(request):
    entreprise = request.user.entreprise
    contacts = Contact.objects.filter(entreprise=entreprise)
    type_filter = request.GET.get('type', '')
    recherche = request.GET.get('q', '')
    if type_filter:
        contacts = contacts.filter(type_contact=type_filter)
    if recherche:
        contacts = contacts.filter(
            Q(nom__icontains=recherche) | Q(organisation__icontains=recherche) |
            Q(email__icontains=recherche) | Q(telephone__icontains=recherche)
        )
    return render(request, 'secretariat/contact_list.html', {
        'contacts': contacts, 'types': Contact.TYPES,
        'type_filter': type_filter, 'recherche': recherche,
    })


@reauth_required
@login_required
@secretariat_required
def contact_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.entreprise = entreprise
            c.save()
            messages.success(request, "Contact ajouté.")
            return redirect('secretariat:contact_list')
    else:
        form = ContactForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Ajouter un contact', 'retour': 'secretariat:contact_list',
    })


@reauth_required
@login_required
@secretariat_required
def contact_edit(request, pk):
    c = get_object_or_404(Contact, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = ContactForm(request.POST, instance=c)
        if form.is_valid():
            form.save()
            messages.success(request, "Contact mis à jour.")
            return redirect('secretariat:contact_list')
    else:
        form = ContactForm(instance=c)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier le contact', 'retour': 'secretariat:contact_list',
    })


@reauth_required
@login_required
@secretariat_required
def contact_delete(request, pk):
    c = get_object_or_404(Contact, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        c.delete()
        messages.success(request, "Contact supprimé.")
        return redirect('secretariat:contact_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': c.nom, 'retour': 'secretariat:contact_list',
    })


# ---------------------------------------------------------------------------
# Réunions
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def reunion_list(request):
    entreprise = request.user.entreprise
    reunions = Reunion.objects.filter(entreprise=entreprise)
    statut = request.GET.get('statut', '')
    if statut:
        reunions = reunions.filter(statut=statut)
    return render(request, 'secretariat/reunion_list.html', {
        'reunions': reunions, 'statuts': Reunion.STATUTS, 'statut_filter': statut,
    })


@reauth_required
@login_required
@secretariat_required
def reunion_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = ReunionForm(request.POST)
        if form.is_valid():
            r = form.save(commit=False)
            r.entreprise = entreprise
            r.cree_par = request.user
            r.save()
            messages.success(request, "Réunion planifiée.")
            return redirect('secretariat:reunion_detail', pk=r.pk)
    else:
        form = ReunionForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Planifier une réunion', 'retour': 'secretariat:reunion_list',
    })


@reauth_required
@login_required
@secretariat_required
def reunion_detail(request, pk):
    r = get_object_or_404(Reunion, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = ActionReunionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False)
            action.reunion = r
            action.save()
            messages.success(request, "Action ajoutée.")
            return redirect('secretariat:reunion_detail', pk=r.pk)
    else:
        form = ActionReunionForm()
    return render(request, 'secretariat/reunion_detail.html', {
        'reunion': r, 'actions': r.actions.all(), 'form': form,
    })


@reauth_required
@login_required
@secretariat_required
def reunion_edit(request, pk):
    r = get_object_or_404(Reunion, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = ReunionForm(request.POST, instance=r)
        if form.is_valid():
            form.save()
            messages.success(request, "Réunion mise à jour.")
            return redirect('secretariat:reunion_detail', pk=r.pk)
    else:
        form = ReunionForm(instance=r)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier la réunion', 'retour': 'secretariat:reunion_list',
    })


@reauth_required
@login_required
@secretariat_required
def reunion_delete(request, pk):
    r = get_object_or_404(Reunion, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        r.delete()
        messages.success(request, "Réunion supprimée.")
        return redirect('secretariat:reunion_list')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': r.titre, 'retour': 'secretariat:reunion_list',
    })


@reauth_required
@login_required
@secretariat_required
def action_delete(request, pk):
    action = get_object_or_404(ActionReunion, pk=pk, reunion__entreprise=request.user.entreprise)
    reunion_pk = action.reunion.pk
    action.delete()
    messages.success(request, "Action supprimée.")
    return redirect('secretariat:reunion_detail', pk=reunion_pk)


# ---------------------------------------------------------------------------
# Rapports
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def rapports(request):
    entreprise = request.user.entreprise
    stats = {
        'courriers_par_statut': list(
            Courrier.objects.filter(entreprise=entreprise)
            .values('statut').annotate(n=Count('id')).order_by('-n')
        ),
        'courriers_par_type': list(
            Courrier.objects.filter(entreprise=entreprise)
            .values('type_courrier').annotate(n=Count('id'))
        ),
        'rdv_par_statut': list(
            RendezVous.objects.filter(entreprise=entreprise)
            .values('statut').annotate(n=Count('id'))
        ),
        'appels_par_type': list(
            Appel.objects.filter(entreprise=entreprise)
            .values('type_appel').annotate(n=Count('id'))
        ),
        'taches_par_etat': list(
            Tache.objects.filter(entreprise=entreprise)
            .values('etat').annotate(n=Count('id'))
        ),
        'visiteurs_total': Visiteur.objects.filter(entreprise=entreprise).count(),
        'documents_par_categorie': list(
            Document.objects.filter(entreprise=entreprise)
            .values('categorie').annotate(n=Count('id')).order_by('-n')
        ),
    }
    return render(request, 'secretariat/rapports.html', {'stats': stats})


# ---------------------------------------------------------------------------
# Paramètres — Modèles de documents
# ---------------------------------------------------------------------------
@reauth_required
@login_required
@secretariat_required
def parametres(request):
    entreprise = request.user.entreprise
    modeles = ModeleDocument.objects.filter(entreprise=entreprise)
    return render(request, 'secretariat/parametres.html', {'modeles': modeles})


@reauth_required
@login_required
@secretariat_required
def modele_create(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        form = ModeleDocumentForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.entreprise = entreprise
            m.save()
            messages.success(request, "Modèle ajouté.")
            return redirect('secretariat:parametres')
    else:
        form = ModeleDocumentForm()
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Nouveau modèle de document', 'retour': 'secretariat:parametres',
    })


@reauth_required
@login_required
@secretariat_required
def modele_edit(request, pk):
    m = get_object_or_404(ModeleDocument, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = ModeleDocumentForm(request.POST, instance=m)
        if form.is_valid():
            form.save()
            messages.success(request, "Modèle mis à jour.")
            return redirect('secretariat:parametres')
    else:
        form = ModeleDocumentForm(instance=m)
    return render(request, 'secretariat/form.html', {
        'form': form, 'titre': 'Modifier le modèle', 'retour': 'secretariat:parametres',
    })


@reauth_required
@login_required
@secretariat_required
def modele_delete(request, pk):
    m = get_object_or_404(ModeleDocument, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        m.delete()
        messages.success(request, "Modèle supprimé.")
        return redirect('secretariat:parametres')
    return render(request, 'secretariat/confirm_delete.html', {
        'objet': m.nom, 'retour': 'secretariat:parametres',
    })
