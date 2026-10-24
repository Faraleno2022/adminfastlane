"""Menus façon Odoo : lanceur d'applications + menus de la barre supérieure.

Chaque application est décrite ici une seule fois. Le context processor
``odoo_shell`` résout les URLs, filtre selon les droits de l'entreprise et
détermine l'application courante à partir du chemin de la requête.

Format d'un menu :
    ('Libellé', 'ns:url_name')                      -> lien direct
    ('Libellé', 'ns:url_name', ('arg',))            -> lien avec arguments
    ('Libellé', [ <entrées> ])                      -> menu déroulant
    '-'                                             -> séparateur
    '= Titre de section'                            -> titre de section
"""
from django.conf import settings
from django.urls import reverse, NoReverseMatch

# --------------------------------------------------------------------------
# Définition des applications
#   requires : None | 'rh' | 'compta'   (drapeaux de l'entreprise)
#   prefixes : préfixes d'URL appartenant à l'application
#   gradient : couleurs (haut, bas) du fond de l'icône
# --------------------------------------------------------------------------
APPS = [
    {
        'key': 'rh', 'name': 'Employés', 'icon': 'bi-people-fill',
        'gradient': ('#00a09d', '#007f7d'), 'requires': 'rh',
        'home': 'dashboard:index',
        'prefixes': ['/dashboard/', '/employes/', '/contrats/'],
        'menus': [
            ('Tableau de bord', 'dashboard:index'),
            ('Employés', [
                ('Tous les employés', 'employes:list'),
                ('Nouvel employé', 'employes:create'),
                ('Importer des employés', 'employes:import_page'),
            ]),
            ('Dossiers', [
                ('Contrats', 'employes:liste_contrats'),
                ('Carrières', 'employes:liste_carrieres'),
                ('Documents', 'employes:liste_documents_global'),
                ('Sanctions', 'employes:liste_sanctions_global'),
                ('Accidents du travail', 'employes:liste_accidents'),
            ]),
            ('Suivi', [
                ('Évaluations', 'employes:liste_campagnes'),
                ('Missions', 'employes:liste_missions'),
                ('Réclamations', 'employes:liste_reclamations'),
                ('Visites médicales', 'employes:liste_visites_medicales'),
            ]),
            ('Rapports', [
                ('Statistiques', 'dashboard:rapports'),
                ('Tableau de bord des absences', 'employes:tableau_bord_absences'),
            ]),
        ],
    },
    {
        'key': 'temps', 'name': 'Temps de travail', 'icon': 'bi-clock-history',
        'gradient': ('#f0a30a', '#d18400'), 'requires': 'rh',
        'home': 'temps_travail:home',
        'prefixes': ['/temps/', '/conges/'],
        'menus': [
            ('Tableau de bord', 'temps_travail:home'),
            ('Présences', [
                ('Pointages', 'temps_travail:pointages'),
                ('Absences', 'temps_travail:absences'),
                ('Heures supplémentaires', 'temps_travail:liste_heures_supplementaires'),
            ]),
            ('Congés', [
                ('Congés', 'temps_travail:conges'),
                ('Demandes de congé', 'conges:liste'),
                ('Soldes de congés', 'conges:soldes'),
            ]),
            ('Rapports', [
                ('Rapport de présence', 'temps_travail:rapport_presence'),
                ('Rapport des heures supplémentaires', 'temps_travail:rapport_heures_supplementaires'),
            ]),
            ('Configuration', [
                ('Jours fériés', 'temps_travail:liste_jours_feries'),
            ]),
        ],
    },
    {
        'key': 'paie', 'name': 'Paie', 'icon': 'bi-cash-coin',
        'gradient': ('#28a745', '#1e7e34'), 'requires': 'rh',
        'home': 'paie:home',
        'prefixes': ['/paie/'],
        'menus': [
            ('Tableau de bord', 'paie:home'),
            ('Paie', [
                ('Périodes de paie', 'paie:liste_periodes'),
                ('Bulletins de paie', 'paie:liste_bulletins'),
                ('Livre de paie', 'paie:livre_paie'),
            ]),
            ('Éléments', [
                ('Éléments de salaire', 'paie:liste_elements_salaire'),
                ('Rubriques de paie', 'paie:liste_rubriques'),
                ('Prêts', 'paie:liste_prets'),
                ('Notes de frais', 'paie:liste_notes_frais'),
            ]),
            ('Déclarations', [
                ('Déclarations sociales', 'paie:declarations_sociales'),
                ('eTax', 'paie:declaration_etax'),
                ('CNSS', 'core:cnss_dashboard'),
            ]),
            ('Rapports', [
                ('Masse salariale', 'paie:rapport_masse_salariale'),
                ('État de paie', 'paie:rapport_etat_paie'),
                ('Feuille de présence', 'paie:rapport_feuille_presence'),
                '-',
                ('Simulation RTS', 'paie:simulation_comparative'),
                ('Historique des simulations', 'paie:historique_simulations'),
            ]),
            ('Configuration', [
                ('Configuration de la paie', 'paie:config_entreprise'),
                ('Paramètres de calcul', 'paie:parametres_calcul'),
            ]),
        ],
    },
    {
        'key': 'recrutement', 'name': 'Recrutement', 'icon': 'bi-briefcase-fill',
        'gradient': ('#875a7b', '#6a4660'), 'requires': 'rh',
        'home': 'recrutement:home',
        'prefixes': ['/recrutement/'],
        'menus': [
            ('Tableau de bord', 'recrutement:home'),
            ('Offres', [
                ('Offres d\'emploi', 'recrutement:offres'),
                ('Nouvelle offre', 'recrutement:creer_offre'),
            ]),
            ('Candidatures', [
                ('Candidatures', 'recrutement:candidatures'),
            ]),
        ],
    },
    {
        'key': 'formation', 'name': 'Formation', 'icon': 'bi-mortarboard-fill',
        'gradient': ('#e8590c', '#c2410c'), 'requires': 'rh',
        'home': 'formation:home',
        'prefixes': ['/formation/'],
        'menus': [
            ('Tableau de bord', 'formation:home'),
            ('Catalogue', [
                ('Catalogue des formations', 'formation:catalogue'),
                ('Nouvelle formation', 'formation:creer_formation'),
            ]),
            ('Sessions', [
                ('Sessions', 'formation:sessions'),
                ('Planifier une session', 'formation:planifier_session'),
                ('Candidatures', 'formation:liste_candidatures'),
            ]),
        ],
    },
    {
        'key': 'compta', 'name': 'Comptabilité', 'icon': 'bi-calculator-fill',
        'gradient': ('#2f80ed', '#1c5fba'), 'requires': 'compta',
        'home': 'comptabilite:dashboard',
        'prefixes': ['/comptabilite/'],
        'menus': [
            ('Tableau de bord', 'comptabilite:dashboard'),
            ('Clients', [
                ('Factures', 'comptabilite:facture_list'),
                ('Règlements', 'comptabilite:reglement_list'),
                ('Comptes clients', 'comptabilite:compte_client_list'),
                ('Échéancier clients', 'comptabilite:echeancier_tiers', ('clients',)),
            ]),
            ('Fournisseurs', [
                ('Comptes fournisseurs', 'comptabilite:compte_fournisseur_list'),
                ('Échéancier fournisseurs', 'comptabilite:echeancier_tiers', ('fournisseurs',)),
            ]),
            ('Comptabilité', [
                ('Nouvelle opération', 'comptabilite:nouvelle_operation'),
                ('Écritures comptables', 'comptabilite:ecriture_list'),
                ('Journaux', 'comptabilite:journal_list'),
                ('Tiers', 'comptabilite:tiers_list'),
                '-',
                ('Clôture de période', 'comptabilite:cloture_periode'),
                ('Clôture d\'exercice', 'comptabilite:cloture_exercice'),
                ('Approbations', 'comptabilite:approbations'),
            ]),
            ('Caisse & banque', [
                ('Pièces de caisse', 'comptabilite:piece_caisse_list'),
                ('Livre de caisse', 'comptabilite:livre_caisse'),
                ('Situation de caisse', 'comptabilite:situation_caisse'),
                ('Arrêtés de caisse', 'comptabilite:arrete_caisse_list'),
                '-',
                ('Comptes bancaires', 'comptabilite:compte-bancaire-list'),
                ('Rapprochements bancaires', 'comptabilite:rapprochement-list'),
                ('Bordereaux', 'comptabilite:bordereau_list'),
                ('Chèques émis', 'comptabilite:cheque_list'),
                ('Situation bancaire', 'comptabilite:situation_bancaire'),
                ('Emprunts', 'comptabilite:emprunt_list'),
            ]),
            ('Rapports', [
                ('= États comptables'),
                ('Grand livre', 'comptabilite:grand_livre'),
                ('Balance', 'comptabilite:balance'),
                ('Journal général', 'comptabilite:journal_general'),
                ('Journaux (achats, ventes…)', 'comptabilite:journal_par_type', ('AC',)),
                ('Balance auxiliaire', 'comptabilite:balance_auxiliaire', ('clients',)),
                '-',
                ('= États financiers'),
                ('Bilan', 'comptabilite:bilan'),
                ('Compte de résultat', 'comptabilite:compte_resultat'),
                ('Flux de trésorerie (TFT)', 'comptabilite:flux_tresorerie'),
                ('Variation des capitaux', 'comptabilite:variation_capitaux'),
                ('Analyse charges/produits', 'comptabilite:analyse_charges_produits'),
                ('Notes annexes', 'comptabilite:notes_annexes'),
                '-',
                ('= Fiscalité & immobilisations'),
                ('Journal de TVA', 'comptabilite:journal_tva'),
                ('Situation fiscale', 'comptabilite:situation_fiscale'),
                ('Déclaration de patente', 'comptabilite:patente_list'),
                ('Journal des immobilisations', 'comptabilite:journal_immobilisations'),
                ('Livre des amortissements', 'comptabilite:livre_amortissements'),
                ('Registre des immobilisations', 'comptabilite:registre_immobilisations'),
            ]),
            ('Modules', [
                ('Trésorerie', 'comptabilite:tresorerie_dashboard'),
                ('Consolidation', 'comptabilite:consolidation_dashboard'),
                ('Analytique', 'comptabilite:analytique_dashboard'),
                ('Fiscalité', 'comptabilite:fiscalite_dashboard'),
                ('Contrôle interne', 'comptabilite:controle_dashboard'),
                ('Contrats', 'comptabilite:contrats_dashboard'),
                ('Archivage', 'comptabilite:archivage_dashboard'),
            ]),
            ('Configuration', [
                ('Plan comptable', 'comptabilite:plan_comptable_list'),
                ('Journaux', 'comptabilite:journal_list'),
                ('Exercices comptables', 'comptabilite:exercice_list'),
            ]),
        ],
    },
    {
        'key': 'stock', 'name': 'Stock', 'icon': 'bi-boxes',
        'gradient': ('#20a36a', '#146c43'), 'requires': None,
        'home': 'stock:dashboard',
        'prefixes': ['/stock/'],
        'menus': [
            ('Tableau de bord', 'stock:dashboard'),
            ('Opérations', [
                ('Mouvements de stock', 'stock:mouvement_list'),
                ('Transferts', 'stock:transfert_list'),
                ('Inventaires', 'stock:inventaire_list'),
                ('Réapprovisionnement', 'stock:reapprovisionnement'),
            ]),
            ('Achats', [
                ('Besoins d\'achat', 'stock:besoin_achat_list'),
                ('Commandes fournisseur', 'stock:commande_list'),
                ('Factures fournisseur', 'stock:facture_list'),
                ('Fournisseurs', 'stock:fournisseur_list'),
            ]),
            ('Ventes', [
                ('Demandes clients', 'stock:demande_vente_list'),
                ('Devis & factures', 'stock:vente_list'),
                ('Clients', 'stock:client_list'),
            ]),
            ('Produits', [
                ('Articles', 'stock:article_list'),
                ('Catégories', 'stock:categorie_list'),
                ('Lots', 'stock:lot_list'),
                ('Numéros de série', 'stock:serie_list'),
                ('Péremptions', 'stock:peremptions'),
            ]),
            ('Rapports', [
                ('Rapports & exports', 'stock:rapports'),
                ('Journal d\'audit', 'stock:journal_audit'),
            ]),
            ('Configuration', [
                ('Dépôts', 'stock:depot_list'),
                ('Paramètres commerciaux', 'stock:parametres_commerciaux'),
                ('Rôles utilisateurs', 'stock:roles_list'),
                ('API REST', 'stock:api_info'),
            ]),
        ],
    },
    {
        'key': 'ventes', 'name': 'Ventes & caisse', 'icon': 'bi-cart-check-fill',
        'gradient': ('#e8590c', '#c2410c'), 'requires': None,
        'home': 'ventes:tableau_de_bord',
        'prefixes': ['/ventes/'],
        'menus': [
            ('Tableau de bord', 'ventes:tableau_de_bord'),
            ('Opérations', [
                ('Nouveau dépôt', 'ventes:depot_nouveau'),
                ('Retrait / vente', 'ventes:retrait_nouveau'),
                '-',
                ('Dépôts et retraits', 'ventes:operations'),
                ('Ventes', 'ventes:ventes'),
            ]),
            ('Clients', [
                ('Clients et soldes', 'ventes:clients'),
                ('Nouveau client', 'ventes:client_nouveau'),
            ]),
            ('Caisse', 'ventes:caisse'),
            ('Stock', [
                ('Produits', 'ventes:produits'),
                ('Mouvements de stock', 'ventes:mouvements'),
                ('Inventaire', 'ventes:inventaire', None, 'admin'),
                ('Validations', 'ventes:validations', None, 'admin'),
            ]),
            ('Rapports', [
                ('Rapports', 'ventes:rapports'),
                ('Journal d\'audit', 'ventes:journal', None, 'admin'),
            ]),
            ('Configuration', [
                ('Paramètres', 'ventes:parametres', None, 'admin'),
                ('Corbeille', 'ventes:corbeille', None, 'admin'),
            ]),
        ],
    },
    {
        'key': 'prets', 'name': 'Suivi des prêts', 'icon': 'bi-piggy-bank-fill',
        'gradient': ('#6f42c1', '#59359a'), 'requires': None,
        'home': 'prets:tableau_de_bord',
        'prefixes': ['/prets/'],
        'menus': [
            ('Tableau de bord', 'prets:tableau_de_bord'),
            ('Prêts', [
                ('Liste des prêts', 'prets:liste'),
                ('Nouveau prêt', 'prets:nouveau'),
            ]),
        ],
    },
    {
        'key': 'agence', 'name': 'Agence de voyage', 'icon': 'bi-airplane-fill',
        'gradient': ('#0aa2c0', '#087990'), 'requires': None,
        'home': 'agence:tableau_de_bord',
        'prefixes': ['/agence/'],
        'menus': [
            ('Tableau de bord', 'agence:tableau_de_bord'),
            ('Dossiers', [
                ('Nouveau dossier', 'agence:dossier_nouveau'),
                ('Tous les dossiers', 'agence:dossiers'),
            ]),
            ('Clients', [
                ('Clients', 'agence:clients'),
                ('Nouveau client', 'agence:client_nouveau'),
            ]),
            ('Fournisseurs', [
                ('Fournisseurs', 'agence:fournisseurs'),
                ('Nouveau fournisseur', 'agence:fournisseur_nouveau'),
            ]),
            ('Rapports', 'agence:rapports'),
        ],
    },
    {
        'key': 'projets', 'name': 'Gestion de projet', 'icon': 'bi-kanban-fill',
        'gradient': ('#d6336c', '#a61e4d'), 'requires': None,
        'home': 'projets:tableau_de_bord',
        'prefixes': ['/projets/'],
        'menus': [
            ('Tableau de bord', 'projets:tableau_de_bord'),
            ('Projets', [
                ('Nouveau projet', 'projets:projet_nouveau'),
                ('Tous les projets', 'projets:projets'),
            ]),
            ('Planning', 'projets:taches'),
            ('Finances', [
                ('Mouvements financiers', 'projets:mouvements'),
                ('Rapports', 'projets:rapports'),
            ]),
            ('Clients', [
                ('Clients', 'projets:clients'),
                ('Nouveau client', 'projets:client_nouveau'),
            ]),
        ],
    },
    {
        'key': 'carburant', 'name': 'Transport de carburant', 'icon': 'bi-fuel-pump-fill',
        'gradient': ('#f59f00', '#d9480f'), 'requires': None,
        'home': 'carburant:tableau_de_bord',
        'prefixes': ['/carburant/'],
        'menus': [
            ('Tableau de bord', 'carburant:tableau_de_bord'),
            ('Voyages', [
                ('Nouveau voyage', 'carburant:voyage_nouveau'),
                ('Tous les voyages', 'carburant:voyages'),
            ]),
            ('Citernes', [
                ('Citernes', 'carburant:citernes'),
                ('Nouvelle citerne', 'carburant:citerne_nouvelle'),
            ]),
            ('Clients', [
                ('Clients', 'carburant:clients'),
                ('Nouveau client', 'carburant:client_nouveau'),
            ]),
            ('Rapports', 'carburant:rapports'),
        ],
    },
    {
        'key': 'flotte', 'name': 'Flotte', 'icon': 'bi-truck',
        'gradient': ('#0d6efd', '#0a58ca'), 'requires': None,
        'home': 'flotte:accueil',
        'prefixes': ['/flotte/'],
        'menus': [
            ('Tableau de bord', 'flotte:accueil'),
            ('Saisie', [
                ('Entretien & réparations', 'flotte:entretien_liste'),
                ('Carburant', 'flotte:carburant_liste'),
                ('Voyages', 'flotte:voyage_liste'),
                ('Poclain', 'flotte:poclain_liste'),
                ('Porte-char', 'flotte:portechar_liste'),
                ('Autres dépenses', 'flotte:depense_liste'),
            ]),
            ('Pointage', [
                ('Présence', 'flotte:grille'),
                ('Employés', 'flotte:employe_liste'),
            ]),
            ('Stock', [
                ('Inventaire', 'flotte:inventaire'),
                ('Mouvements', 'flotte:mouvement_liste'),
                ('Synthèse', 'flotte:synthese'),
            ]),
            ('Rapports', [
                ('Analyses par véhicule', 'flotte:analyses'),
                ('Rapport mensuel', 'flotte:rapport_mensuel'),
                ('Charges d\'entretien', 'flotte:rapport_charges_entretien'),
                ('Consommation de carburant', 'flotte:rapport_carburant'),
                ('Analyse Poclain', 'flotte:rapport_poclain'),
                '-',
                ('Export Excel', 'flotte:export_excel'),
                ('Export PDF', 'flotte:export_pdf'),
            ]),
            ('Référentiel', [
                ('Véhicules', 'flotte:vehicule_liste'),
                ('Documents', 'flotte:document_liste'),
                ('Marques', 'flotte:marque_liste'),
                ('Chauffeurs', 'flotte:chauffeur_liste'),
                ('Catégories de roues', 'flotte:categorie_liste'),
                ('Engins', 'flotte:engin_liste'),
            ]),
        ],
    },
    {
        'key': 'secretariat', 'name': 'Secrétariat', 'icon': 'bi-folder-fill',
        'gradient': ('#e5588b', '#b8386a'), 'requires': None,
        'home': 'secretariat:dashboard',
        'prefixes': ['/secretariat/'],
        'menus': [
            ('Tableau de bord', 'secretariat:dashboard'),
            ('Courrier & documents', [
                ('Courrier', 'secretariat:courrier_list'),
                ('Documents', 'secretariat:document_list'),
            ]),
            ('Agenda', [
                ('Rendez-vous', 'secretariat:rdv_list'),
                ('Réunions', 'secretariat:reunion_list'),
                ('Tâches', 'secretariat:tache_list'),
            ]),
            ('Accueil', [
                ('Visiteurs', 'secretariat:visiteur_list'),
                ('Appels', 'secretariat:appel_list'),
                ('Contacts', 'secretariat:contact_list'),
            ]),
            ('Rapports', [
                ('Rapports', 'secretariat:rapports'),
            ]),
            ('Configuration', [
                ('Paramètres', 'secretariat:parametres'),
            ]),
        ],
    },
    {
        'key': 'conformite', 'name': 'Conformité', 'icon': 'bi-shield-check',
        'gradient': ('#5b6bbf', '#3f4d99'), 'requires': 'rh',
        'home': 'core:inspection_dashboard',
        'prefixes': ['/cnss/', '/expatries/', '/inspection/'],
        'menus': [
            ('CNSS', [
                ('Tableau de bord CNSS', 'core:cnss_dashboard'),
                ('Configuration CNSS', 'core:cnss_configuration'),
                ('Générer une déclaration', 'core:cnss_generer'),
                ('Historique', 'core:cnss_historique'),
            ]),
            ('Expatriés', [
                ('Expatriés', 'core:expatries_liste'),
                ('Ajouter un expatrié', 'core:expatrie_ajouter'),
                ('Alertes permis', 'core:alertes_expatries'),
            ]),
            ('Inspection du travail', [
                ('Tableau de bord', 'core:inspection_dashboard'),
                ('Registres', 'core:registres_liste'),
                ('Visites', 'core:visites_liste'),
                ('Checklist de conformité', 'core:checklist_conformite'),
                ('Rapport de conformité', 'core:generer_rapport'),
            ]),
        ],
    },
    {
        'key': 'portail', 'name': 'Portail employé', 'icon': 'bi-person-workspace',
        'gradient': ('#17a2b8', '#117a8b'), 'requires': 'rh',
        'home': 'portail:accueil',
        'prefixes': ['/portail/'],
        'menus': [
            ('Accueil', 'portail:accueil'),
            ('Mes demandes', [
                ('Mes congés', 'portail:mes_conges'),
                ('Mes absences', 'portail:mes_absences'),
                ('Mes prêts', 'portail:mes_prets'),
                ('Mes heures supplémentaires', 'portail:mes_heures_sup'),
            ]),
            ('Mes bulletins', 'portail:mes_bulletins'),
            ('Mon profil', 'portail:mon_profil'),
        ],
    },
    {
        'key': 'abonnement', 'name': 'Abonnements', 'icon': 'bi-gem',
        'gradient': ('#9b59b6', '#7d3c98'), 'requires': None,
        'home': 'payments:plans',
        'prefixes': ['/payments/'],
        'menus': [
            ('Plans & tarifs', 'payments:plans'),
            ('Mon abonnement', 'payments:mon_abonnement'),
            ('Historique des paiements', 'payments:historique'),
        ],
    },
    {
        'key': 'parametres', 'name': 'Paramètres', 'icon': 'bi-gear-fill',
        'gradient': ('#6c757d', '#495057'), 'requires': None,
        'home': 'core:profile',
        'prefixes': [
            '/profile/', '/users/', '/parametres/', '/manage-users/', '/structure/',
            '/entreprise-settings/', '/admin-dashboard/', '/changer-societe/',
            '/send-invitation/', '/licence/', '/guide-utilisateur/',
            '/documentation-legale/', '/documentation/', '/dashboard-rh/', '/partenariat/',
            '/superuser/',
        ],
        'menus': [
            ('Général', [
                ('Mon profil', 'core:profile'),
                ('Paramètres de l\'entreprise', 'core:entreprise_settings', None, 'admin'),
                ('Applications', 'core:applications', None, 'admin'),
                ('Changer de société', 'core:changer_societe'),
            ]),
            ('Utilisateurs', [
                ('Gérer les utilisateurs', 'core:manage_users', None, 'admin'),
                ('Inviter un utilisateur', 'core:send_invitation', None, 'admin'),
                ('Tableau de bord admin', 'core:admin_dashboard', None, 'admin'),
            ]),
            ('Structure', [
                ('Établissements, services & postes', 'core:gestion_structure'),
            ]),
            ('Licence', [
                ('Statut de la licence', 'core:licence_statut'),
                ('Renouveler la licence', 'core:licence_renouveler'),
            ]),
            ('Aide', [
                ('Guide utilisateur', 'core:guide_utilisateur'),
                ('Documentation légale', 'core:documentation_legale'),
                ('Documentation CGI 2022', 'core:telecharger_documentation'),
            ]),
        ],
    },
]


def _resolve(spec):
    """Résout une entrée de menu en dict ; renvoie None si l'URL n'existe pas."""
    if isinstance(spec, str):
        if spec == '-':
            return {'type': 'sep'}
        if spec.startswith('='):
            return {'type': 'section', 'label': spec.lstrip('= ').strip()}
        return None
    label, target = spec[0], spec[1]
    if isinstance(target, list):
        children = [c for c in (_resolve(s) for s in target) if c]
        # Nettoie les séparateurs en tête / en queue / doublons
        while children and children[0]['type'] == 'sep':
            children.pop(0)
        while children and children[-1]['type'] == 'sep':
            children.pop()
        if not any(c['type'] == 'link' for c in children):
            return None
        return {'type': 'dropdown', 'label': label, 'children': children}
    args = spec[2] if len(spec) > 2 and spec[2] else ()
    try:
        url = reverse(target, args=args)
    except NoReverseMatch:
        return None
    return {'type': 'link', 'label': label, 'url': url,
            'admin': len(spec) > 3 and spec[3] == 'admin'}


# --------------------------------------------------------------------------
# Catalogue proposé à l'inscription et dans Paramètres > Applications
# (façon « essai » Odoo : l'entreprise coche les applications qu'elle utilise)
# --------------------------------------------------------------------------
CATEGORIES = [
    ('Ressources humaines', [
        ('rh', "Dossiers du personnel, contrats et organigramme"),
        ('temps', "Présences, congés, absences et heures supplémentaires"),
        ('paie', "Bulletins, cotisations CNSS, RTS et déclarations"),
        ('recrutement', "Offres d'emploi, candidatures et entretiens"),
        ('formation', "Catalogue, sessions et évaluations des formations"),
        ('conformite', "CNSS, inspection du travail et obligations légales"),
        ('portail', "Espace en libre-service pour les salariés"),
    ]),
    ('Finance', [
        ('compta', "Plan SYSCOHADA, journaux, TVA et états financiers"),
        ('prets', "Prêts accordés, échéanciers et remboursements"),
    ]),
    ('Ventes & stock', [
        ('ventes', "Caisse, factures et encaissements clients"),
        ('stock', "Articles, dépôts, inventaires et fournisseurs"),
    ]),
    ('Services', [
        ('projets', "Projets, tâches, équipe et budget"),
        ('agence', "Dossiers de voyage, billets, hôtels et visas"),
        ('secretariat', "Courrier, rendez-vous, visiteurs et documents"),
    ]),
    ('Logistique', [
        ('flotte', "Véhicules, chauffeurs, entretiens et carburant"),
        ('carburant', "Citernes, chargements, livraisons et manquants"),
    ]),
]
# Toujours disponibles, quelle que soit la sélection.
APPLICATIONS_SOCLE = ('abonnement', 'parametres')
CLES_RH = ('rh', 'temps', 'paie', 'recrutement', 'formation', 'conformite', 'portail')
_PAR_CLE = {app['key']: app for app in APPS}


def catalogue():
    """Catégories d'applications sélectionnables, avec nom, icône et description."""
    return [
        (titre, [dict(_PAR_CLE[cle], description=desc) for cle, desc in apps if cle in _PAR_CLE])
        for titre, apps in CATEGORIES
    ]


def cles_selectionnables():
    return [cle for _, apps in CATEGORIES for cle, _ in apps if cle in _PAR_CLE]


def applications_actives(entreprise):
    """Clés des applications affichées pour l'entreprise (règles historiques si aucun choix)."""
    return [a['key'] for a in APPS if a['key'] not in APPLICATIONS_SOCLE and _visible(a, entreprise)]


def _visible(app, entreprise):
    if app['key'] == 'abonnement' and not getattr(settings, 'ABONNEMENTS_ACTIFS', True):
        return False
    if entreprise is not None and getattr(entreprise, 'applications', None):
        return app['key'] in APPLICATIONS_SOCLE or app['key'] in entreprise.applications
    req = app['requires']
    if req is None:
        return True
    if entreprise is None:
        return False
    if req == 'rh':
        return bool(getattr(entreprise, 'has_rh', False))
    if req == 'compta':
        return bool(getattr(entreprise, 'has_compta', False))
    return True


def _filter_admin(entry, is_admin):
    """Retire les liens réservés aux administrateurs si besoin."""
    if entry['type'] == 'link':
        return entry if (is_admin or not entry.get('admin')) else None
    if entry['type'] == 'dropdown':
        kids = [k for k in (_filter_admin(c, is_admin) for c in entry['children']) if k]
        if not any(k['type'] == 'link' for k in kids):
            return None
        return dict(entry, children=kids)
    return entry


def _mark_active(entries, path):
    """Marque l'entrée la plus spécifique correspondant au chemin courant."""
    best = {'len': -1, 'entry': None}

    def walk(items):
        for e in items:
            if e['type'] == 'link':
                u = e['url']
                if path == u or (len(u) > 1 and path.startswith(u.rstrip('/') + '/')):
                    if len(u) > best['len']:
                        best['len'], best['entry'] = len(u), e
            elif e['type'] == 'dropdown':
                walk(e['children'])
    walk(entries)
    if best['entry'] is not None:
        best['entry']['active'] = True

    def propagate(items):
        for e in items:
            if e['type'] == 'dropdown':
                e['active'] = propagate(e['children'])
                if e['active']:
                    pass
        return any(e.get('active') for e in items)
    propagate(entries)
    return best['entry']


def build_shell(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    entreprise = getattr(user, 'entreprise', None)
    is_admin = bool(getattr(user, 'est_admin_entreprise', False)) or user.is_superuser
    path = request.path

    visible = [a for a in APPS if _visible(a, entreprise)]

    launcher = []
    current = None
    longest = -1
    for app in visible:
        try:
            home = reverse(app['home'])
        except NoReverseMatch:
            continue
        item = {
            'key': app['key'], 'name': app['name'], 'icon': app['icon'],
            'g1': app['gradient'][0], 'g2': app['gradient'][1], 'url': home,
        }
        launcher.append(item)
        for p in app['prefixes']:
            if path.startswith(p) and len(p) > longest:
                longest, current = len(p), app

    context = {'odoo_apps': launcher, 'odoo_app': None, 'odoo_menus': [],
               'odoo_active_label': ''}
    if current is not None:
        menus = [m for m in (_resolve(s) for s in current['menus']) if m]
        menus = [m for m in (_filter_admin(m, is_admin) for m in menus) if m]
        if not getattr(settings, 'ABONNEMENTS_ACTIFS', True):
            menus = [m for m in menus if m.get('label') != 'Licence']
        active = _mark_active(menus, path)
        context['odoo_app'] = {
            'key': current['key'], 'name': current['name'], 'icon': current['icon'],
            'g1': current['gradient'][0], 'g2': current['gradient'][1],
            'url': reverse(current['home']),
        }
        context['odoo_menus'] = menus
        context['odoo_active_label'] = active['label'] if active else ''
    return context
