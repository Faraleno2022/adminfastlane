"""
Vues pour le portail employé - Demande de congés.
Interface simplifiée pour les employés.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from decimal import Decimal
from datetime import date, timedelta

from .models import Conge, SoldeConge
from employes.models import Employe


@login_required
def mes_conges(request):
    """Liste des congés de l'employé connecté"""
    # Récupérer l'employé lié à l'utilisateur
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        messages.error(request, "Votre compte n'est pas lié à un employé")
        return redirect('core:home')
    
    # Congés de l'employé
    conges = Conge.objects.filter(employe=employe).order_by('-date_demande')
    
    # Solde de congés
    annee = date.today().year
    solde, created = SoldeConge.objects.get_or_create(
        employe=employe,
        annee=annee,
        defaults={
            'conges_acquis': Decimal('30'),
            'conges_pris': Decimal('0'),
            'conges_restants': Decimal('30'),
            'conges_reports': Decimal('0'),
        }
    )
    
    # Statistiques
    stats = {
        'en_attente': conges.filter(statut_demande='en_attente').count(),
        'approuves': conges.filter(statut_demande='approuve').count(),
        'refuses': conges.filter(statut_demande='rejete').count(),
        'jours_pris': solde.conges_pris,
        'jours_restants': solde.conges_restants,
    }
    
    return render(request, 'temps_travail/portail/mes_conges.html', {
        'conges': conges[:20],
        'solde': solde,
        'stats': stats,
        'employe': employe,
    })


@login_required
def demander_conge(request):
    """Formulaire de demande de congé pour l'employé"""
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        messages.error(request, "Votre compte n'est pas lié à un employé")
        return redirect('core:home')
    
    # Solde actuel
    annee = date.today().year
    solde, _ = SoldeConge.objects.get_or_create(
        employe=employe,
        annee=annee,
        defaults={
            'conges_acquis': Decimal('30'),
            'conges_pris': Decimal('0'),
            'conges_restants': Decimal('30'),
        }
    )
    
    if request.method == 'POST':
        type_conge = request.POST.get('type_conge')
        date_debut = request.POST.get('date_debut')
        date_fin = request.POST.get('date_fin')
        motif = request.POST.get('motif', '')
        
        try:
            from datetime import datetime
            d_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
            d_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
            
            # Validation
            if d_debut > d_fin:
                messages.error(request, "La date de fin doit être après la date de début")
                return redirect('temps_travail:demander_conge')
            
            if d_debut < date.today():
                messages.error(request, "La date de début ne peut pas être dans le passé")
                return redirect('temps_travail:demander_conge')
            
            # Calculer le nombre de jours (hors weekends)
            nombre_jours = Decimal('0')
            current = d_debut
            while current <= d_fin:
                if current.weekday() < 5:  # Lundi à Vendredi
                    nombre_jours += 1
                current += timedelta(days=1)
            
            # Vérifier le solde pour les congés payés
            if type_conge == 'annuel' and nombre_jours > solde.conges_restants:
                messages.error(request, f"Solde insuffisant. Vous avez {solde.conges_restants} jours disponibles.")
                return redirect('temps_travail:demander_conge')
            
            # Créer la demande
            conge = Conge.objects.create(
                employe=employe,
                type_conge=type_conge,
                date_debut=d_debut,
                date_fin=d_fin,
                nombre_jours=nombre_jours,
                motif=motif,
                statut_demande='en_attente',
                annee_reference=annee,
            )
            
            messages.success(request, f"Demande de congé soumise ({nombre_jours} jours du {d_debut.strftime('%d/%m/%Y')} au {d_fin.strftime('%d/%m/%Y')})")
            return redirect('temps_travail:mes_conges')
            
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return render(request, 'temps_travail/portail/demander_conge.html', {
        'employe': employe,
        'solde': solde,
        'types_conge': Conge.TYPES,
    })


@login_required
def detail_ma_demande(request, pk):
    """Détail d'une demande de congé de l'employé"""
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        messages.error(request, "Votre compte n'est pas lié à un employé")
        return redirect('core:home')
    
    conge = get_object_or_404(Conge, pk=pk, employe=employe)
    
    return render(request, 'temps_travail/portail/detail_demande.html', {
        'conge': conge,
        'employe': employe,
    })


@login_required
def annuler_ma_demande(request, pk):
    """Annuler une demande de congé en attente"""
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        messages.error(request, "Votre compte n'est pas lié à un employé")
        return redirect('core:home')
    
    conge = get_object_or_404(Conge, pk=pk, employe=employe)
    
    if conge.statut_demande == 'en_attente':
        conge.statut_demande = 'annule'
        conge.save()
        messages.success(request, "Demande annulée")
    else:
        messages.error(request, "Seules les demandes en attente peuvent être annulées")
    
    return redirect('temps_travail:mes_conges')


@login_required
def mon_solde_conges(request):
    """Afficher le solde de congés de l'employé"""
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        messages.error(request, "Votre compte n'est pas lié à un employé")
        return redirect('core:home')
    
    # Soldes par année
    soldes = SoldeConge.objects.filter(employe=employe).order_by('-annee')
    
    # Historique des congés pris
    conges_pris = Conge.objects.filter(
        employe=employe,
        statut_demande='approuve'
    ).order_by('-date_debut')[:10]
    
    return render(request, 'temps_travail/portail/mon_solde.html', {
        'soldes': soldes,
        'conges_pris': conges_pris,
        'employe': employe,
    })
