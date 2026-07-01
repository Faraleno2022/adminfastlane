#!/usr/bin/env python
"""
Script de lancement du serveur Django pour PyInstaller
GestionnaireRH Guinée - Version Offline avec gestion de licence
"""
import os
import sys
import webbrowser
import threading
import time


# ─── Détection du répertoire de base ──────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    INTERNAL_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INTERNAL_DIR = BASE_DIR

os.chdir(BASE_DIR)

if INTERNAL_DIR not in sys.path:
    sys.path.insert(0, INTERNAL_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


# ─── Mode fenêtre (sans console) : rediriger stdout/stderr vers un fichier ─────
# En build « windowed » (console=False), sys.stdout / sys.stderr valent None :
# le moindre print() planterait. On les redirige vers un journal pour conserver
# les logs tout en supprimant la fenêtre noire au démarrage.
def _setup_console_redirect():
    if sys.stdout is not None and sys.stderr is not None:
        return  # console présente : rien à faire
    log_dir = os.path.join(BASE_DIR, 'logs')
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'launcher.log')
        log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
    except Exception:
        # Dossier non inscriptible : repli sur le dossier temporaire
        import tempfile
        log_file = open(os.path.join(tempfile.gettempdir(),
                                     'GestionnaireRH_launcher.log'),
                        'a', encoding='utf-8', buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file


_setup_console_redirect()


def _safe_pause(message):
    """Remplace input() : affiche une boîte de dialogue si aucune console.

    En mode fenêtre, input() lèverait une exception (pas de stdin). On montre
    alors un message graphique avant de fermer l'application.
    """
    try:
        print(message)
    except Exception:
        pass
    has_console = sys.stdin is not None and getattr(sys.stdin, 'isatty', lambda: False)()
    if has_console:
        try:
            input()
        except Exception:
            pass
        return
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("GestionnaireRH", message)
        r.destroy()
    except Exception:
        pass


# ─── Fenêtre d'activation de licence (tkinter) ────────────────────────────────
def show_activation_window(mid: str, trial_days_left: int = 0) -> bool:
    """
    Affiche une fenêtre graphique d'activation de licence.
    - trial_days_left > 0 : bouton "Continuer l'essai" affiché.
    - trial_days_left <= 0 : l'utilisateur DOIT activer pour continuer.
    Retourne True si l'application peut démarrer.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError:
        return trial_days_left > 0

    result = [False]

    root = tk.Tk()
    root.title("GestionnaireRH — Activation de la Licence")
    root.resizable(False, False)
    root.configure(bg='#ecf0f1')

    W, H = 540, 460
    root.geometry(f"{W}x{H}")
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
    root.lift()
    root.attributes('-topmost', True)
    root.after(200, lambda: root.attributes('-topmost', False))

    # ── En-tête ──
    hdr = tk.Frame(root, bg='#1a5276', height=72)
    hdr.pack(fill='x')
    hdr.pack_propagate(False)
    tk.Label(hdr, text="GestionnaireRH",
             font=('Arial', 22, 'bold'), bg='#1a5276', fg='white').place(
        relx=0.5, rely=0.35, anchor='center')
    tk.Label(hdr, text="Gestionnaire RH Guinée — ICG Guinea",
             font=('Arial', 8), bg='#1a5276', fg='#aed6f1').place(
        relx=0.5, rely=0.75, anchor='center')

    # ── Corps ──
    body = tk.Frame(root, bg='#ecf0f1', padx=24, pady=16)
    body.pack(fill='both', expand=True)

    if trial_days_left <= 0:
        status_txt = ("Votre période d'essai de 30 jours est expirée.\n"
                      "Veuillez activer votre licence pour continuer.")
        status_col = '#c0392b'
    else:
        status_txt = (f"Mode essai : {trial_days_left} jour(s) restant(s).\n"
                      "Activez votre licence pour un accès illimité.")
        status_col = '#d35400'

    tk.Label(body, text=status_txt, font=('Arial', 10), bg='#ecf0f1',
             fg=status_col, justify='left', wraplength=490).pack(
        anchor='w', pady=(0, 12))

    # ── ID Machine ──
    mid_frm = tk.LabelFrame(body, text="  Identifiant Machine  ",
                             bg='#ecf0f1', font=('Arial', 9, 'bold'),
                             fg='#1a5276', padx=10, pady=8, relief='groove')
    mid_frm.pack(fill='x', pady=(0, 10))
    tk.Label(mid_frm,
             text="Communiquez cet identifiant à ICG Guinea pour obtenir votre licence :",
             font=('Arial', 8), bg='#ecf0f1', fg='#555').pack(anchor='w')
    mid_var = tk.StringVar(value=mid)
    tk.Entry(mid_frm, textvariable=mid_var, font=('Courier', 10, 'bold'),
             state='readonly', readonlybackground='#d5e8f7',
             relief='flat', bd=1, fg='#1a5276').pack(
        fill='x', pady=(4, 2), ipady=5)

    cb_btn = tk.Button(mid_frm, text="  Copier l'identifiant  ",
                       font=('Arial', 8), bg='#2980b9', fg='white',
                       relief='flat', padx=8, pady=3, cursor='hand2')
    cb_btn.pack(anchor='e', pady=(3, 0))

    def _copy_mid():
        root.clipboard_clear()
        root.clipboard_append(mid)
        cb_btn.config(text="  Copie !  ")
        root.after(2000, lambda: cb_btn.config(text="  Copier l'identifiant  "))
    cb_btn.config(command=_copy_mid)

    # ── Activation fichier .lic ──
    lic_frm = tk.LabelFrame(body,
                             text="  Activer avec un fichier de licence (.lic)  ",
                             bg='#ecf0f1', font=('Arial', 9, 'bold'),
                             fg='#1a5276', padx=10, pady=8, relief='groove')
    lic_frm.pack(fill='x', pady=(0, 8))

    lic_var = tk.StringVar(value="")
    lic_row = tk.Frame(lic_frm, bg='#ecf0f1')
    lic_row.pack(fill='x')
    tk.Entry(lic_row, textvariable=lic_var, font=('Arial', 9),
             state='readonly', readonlybackground='#f9f9f9',
             relief='flat', bd=1).pack(
        side='left', fill='x', expand=True, ipady=5)

    def _browse():
        p = filedialog.askopenfilename(
            title="Sélectionner votre fichier de licence",
            filetypes=[("Licence GestionnaireRH", "*.lic"),
                       ("Tous les fichiers", "*.*")])
        if p:
            lic_var.set(p)
            status_lbl.config(text="", fg='#27ae60')

    tk.Button(lic_row, text="  Parcourir…  ", command=_browse,
              font=('Arial', 9), bg='#7f8c8d', fg='white',
              relief='flat', padx=6, pady=5, cursor='hand2').pack(
        side='left', padx=(6, 0))

    status_lbl = tk.Label(lic_frm, text="", font=('Arial', 9),
                          bg='#ecf0f1', fg='#27ae60')
    status_lbl.pack(anchor='w', pady=(4, 0))

    def _do_activate():
        p = lic_var.get().strip()
        if not p:
            messagebox.showwarning(
                "Fichier manquant",
                "Veuillez sélectionner un fichier .lic avant d'activer.")
            return
        try:
            import license_manager
            res = license_manager.activate_from_file(p)
        except Exception as ex:
            messagebox.showerror("Erreur", f"Erreur lors de l'activation :\n{ex}")
            return
        if res.get('valid'):
            company = res.get('company', '')
            days = res.get('days_left', 0)
            edition = res.get('edition', 'Standard')
            messagebox.showinfo(
                "Activation réussie",
                f"Licence activée avec succès !\n\n"
                f"Entreprise : {company}\n"
                f"Édition    : {edition}\n"
                f"Validité   : {days} jour(s)")
            result[0] = True
            root.destroy()
        else:
            reason = res.get('reason', 'Erreur inconnue.')
            status_lbl.config(text=f"Erreur : {reason}", fg='#c0392b')
            messagebox.showerror("Activation échouée", reason)

    # ── Boutons ──
    btn_frm = tk.Frame(body, bg='#ecf0f1')
    btn_frm.pack(fill='x', pady=(4, 0))

    tk.Button(btn_frm, text="   Activer la Licence   ",
              command=_do_activate,
              font=('Arial', 11, 'bold'), bg='#27ae60', fg='white',
              relief='flat', padx=10, pady=8, cursor='hand2').pack(side='left')

    if trial_days_left > 0:
        def _continue_trial():
            result[0] = True
            root.destroy()
        tk.Button(btn_frm,
                  text=f"   Continuer l'essai ({trial_days_left}j)   ",
                  command=_continue_trial,
                  font=('Arial', 10), bg='#e67e22', fg='white',
                  relief='flat', padx=10, pady=8, cursor='hand2').pack(
            side='left', padx=(10, 0))

    def _on_close():
        if not result[0]:
            if messagebox.askyesno("Quitter", "Quitter GestionnaireRH ?"):
                root.destroy()
                os._exit(0)   # Fermeture complète : tue tous les threads/processus
        else:
            root.destroy()

    tk.Button(btn_frm, text="  Quitter  ", command=_on_close,
              font=('Arial', 10), bg='#95a5a6', fg='white',
              relief='flat', padx=10, pady=8, cursor='hand2').pack(side='right')

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
    return result[0]


# ─── Vérification de la licence ────────────────────────────────────────────────
def check_license():
    """Vérifie la licence au démarrage. Affiche une fenêtre si activation requise."""
    try:
        import license_manager
        status = license_manager.check_license_or_trial()
    except Exception as e:
        print(f"[Licence] Avertissement : {e}")
        return True

    mid = ''
    try:
        import license_manager as _lm
        mid = _lm.get_machine_id()
    except Exception:
        pass

    if status.get('valid'):
        if status.get('trial'):
            days_left = status.get('days_left', 0)
            if days_left <= 7:
                print(f"  [ESSAI] Il vous reste {days_left} jour(s) d'essai.")
                print(f"  [ESSAI] Contactez ICG Guinea pour acheter une licence.")
                show_activation_window(mid, trial_days_left=days_left)
            else:
                from datetime import datetime, timedelta
                exp = (datetime.utcnow() + timedelta(days=days_left)).strftime('%d/%m/%Y')
                print(f"  [ESSAI GRATUIT] {days_left} jour(s) restant(s) — expire le {exp}")
                print(f"  [ESSAI GRATUIT] Contactez ICG Guinea pour obtenir une licence.")
        else:
            company = status.get('company', '')
            edition = status.get('edition', 'Standard')
            days_left = status.get('days_left', 0)
            if days_left <= 30:
                print(f"  [Licence] Expire dans {days_left} jour(s). "
                      f"Renouvelez auprès d'ICG Guinea.")
            else:
                print(f"  [Licence] Valide — {company} ({edition}) — {days_left}j restant(s).")
    else:
        days_left = status.get('days_left', 0)
        print("")
        print("  [Licence] Activation requise — ouverture de la fenetre d'activation...")
        can_start = show_activation_window(mid, trial_days_left=days_left)
        if not can_start:
            os._exit(0)   # Fermeture totale sans laisser Django démarrer

    return True


APP_URL = 'http://127.0.0.1:8000/'


def _wait_for_server(url=APP_URL, timeout=40):
    """Attend que le serveur Django réponde avant d'ouvrir la fenêtre."""
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError:
            # Le serveur a répondu (redirection/erreur HTTP) → il est prêt
            return True
        except Exception:
            time.sleep(0.3)
    return False


def open_browser_app_mode(url=APP_URL):
    """Repli : ouvre Chrome/Edge en mode application (fenêtre sans barre d'adresse)."""
    candidates = [
        os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
        os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
        os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
        os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
    ]
    import subprocess
    for path in candidates:
        if os.path.isfile(path):
            try:
                subprocess.Popen([path, f'--app={url}',
                                  '--window-size=1280,800'])
                print(f"  Fenetre application ouverte: {os.path.basename(path)}")
                return True
            except Exception:
                continue
    # Dernier recours : navigateur par défaut
    try:
        webbrowser.open(url)
        print("  Navigateur par defaut ouvert")
        return True
    except Exception:
        return False


def open_app_window():
    """Ouvre l'application dans sa propre fenêtre native (pywebview/WebView2).

    Bloque jusqu'à la fermeture de la fenêtre, puis arrête l'application.
    En cas d'échec, repli sur le mode application du navigateur.
    """
    if not _wait_for_server():
        print("  [Fenetre] Le serveur n'a pas demarre a temps.")
    try:
        import webview
        webview.create_window(
            'GestionnaireRH — Gestion RH Guinée',
            APP_URL,
            width=1280,
            height=800,
            min_size=(1024, 700),
            maximized=True,
        )
        print("  Fenetre native ouverte (WebView2)")
        webview.start()
        # La fenêtre a été fermée par l'utilisateur → on quitte l'application
        os._exit(0)
    except Exception as e:
        print(f"  [Fenetre] pywebview indisponible ({e}) — repli navigateur app-mode")
        open_browser_app_mode()
        # IMPORTANT : ne pas rendre la main, sinon main() se termine et le thread
        # serveur (démon) est tué → le navigateur afficherait ERR_CONNECTION_REFUSED.
        # On garde le processus (et donc le serveur) vivant tant que le navigateur tourne.
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


# ─── Patch DB : ajoute les colonnes manquantes (mise à jour sans migration) ──
def _apply_missing_columns():
    """Ajoute les colonnes manquantes si les migrations ne peuvent pas s'appliquer."""
    import sqlite3
    db_path = os.path.join(BASE_DIR, 'db.sqlite3')
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Colonnes à ajouter sur entreprises
    ent_cols = [
        ('max_employes', 'INTEGER DEFAULT 30'),
        ('module_paie', 'BOOLEAN DEFAULT 1'),
        ('module_conges', 'BOOLEAN DEFAULT 1'),
        ('module_recrutement', 'BOOLEAN DEFAULT 0'),
        ('module_formation', 'BOOLEAN DEFAULT 0'),
        ('module_comptabilite', 'BOOLEAN DEFAULT 0'),
        ('module_portail', 'BOOLEAN DEFAULT 0'),
        ('acces_declarations_fiscales', 'BOOLEAN DEFAULT 0'),
        ('acces_export_comptable', 'BOOLEAN DEFAULT 0'),
    ]
    for col_name, col_type in ent_cols:
        try:
            cursor.execute(f'ALTER TABLE entreprises ADD COLUMN {col_name} {col_type}')
        except Exception:
            pass  # colonne existe déjà

    # Colonnes sur plans_abonnement
    plan_cols = [
        ('sous_titre', 'VARCHAR(100) DEFAULT ""'),
        ('prix_installation', 'DECIMAL DEFAULT 0'),
        ('module_comptabilite', 'BOOLEAN DEFAULT 0'),
        ('module_portail', 'BOOLEAN DEFAULT 0'),
        ('support_telephonique', 'BOOLEAN DEFAULT 0'),
        ('formation_incluse', 'BOOLEAN DEFAULT 0'),
        ('personnalisation', 'BOOLEAN DEFAULT 0'),
        ('multi_entreprise', 'BOOLEAN DEFAULT 0'),
        ('declarations_fiscales', 'BOOLEAN DEFAULT 0'),
        ('export_comptable', 'BOOLEAN DEFAULT 0'),
        ('badge', 'VARCHAR(30) DEFAULT ""'),
        ('couleur', 'VARCHAR(7) DEFAULT "#0d6efd"'),
        ('icone', 'VARCHAR(50) DEFAULT "bi-box"'),
    ]
    for col_name, col_type in plan_cols:
        try:
            cursor.execute(f'ALTER TABLE plans_abonnement ADD COLUMN {col_name} {col_type}')
        except Exception:
            pass

    # Colonnes sur employes (conducteur, filiation, formation, visite médicale)
    emp_cols = [
        ('nom_pere', 'VARCHAR(200)'),
        ('nom_mere', 'VARCHAR(200)'),
        ('nombre_femmes', 'INTEGER DEFAULT 0'),
        ('id_conducteur', 'VARCHAR(50)'),
        ('tracteur', 'VARCHAR(100)'),
        ('citerne', 'VARCHAR(100)'),
        ('numero_permis', 'VARCHAR(50)'),
        ('date_obtention_permis', 'DATE'),
        ('date_validite_permis', 'DATE'),
        ('groupe_sanguin', 'VARCHAR(10)'),
        ('base_chauffeur', 'VARCHAR(100)'),
        ('date_formation_apth', 'DATE'),
        ('anciennete_transport_hcl', 'INTEGER'),
        ('date_dernier_recyclage', 'DATE'),
        ('formation_extincteur', 'BOOLEAN DEFAULT 0'),
        ('date_derniere_visite_medicale', 'DATE'),
        ('service_medical_accredite', 'VARCHAR(200)'),
        ('date_prochaine_visite_medicale', 'DATE'),
        ('vehicule_assigne', 'VARCHAR(200)'),
    ]
    for col_name, col_type in emp_cols:
        try:
            cursor.execute(f'ALTER TABLE employes ADD COLUMN {col_name} {col_type}')
        except Exception:
            pass

    # Colonnes sur axes_accesslog (django-axes)
    axes_cols = [
        ('session_hash', 'VARCHAR(256) DEFAULT ""'),
    ]
    for col_name, col_type in axes_cols:
        try:
            cursor.execute(f'ALTER TABLE axes_accesslog ADD COLUMN {col_name} {col_type}')
        except Exception:
            pass

    # Colonnes sur bulletins_paie (fériés nuit séparés)
    bul_cols = [
        ('heures_feries_nuit', 'DECIMAL(6,2) DEFAULT 0'),
        ('prime_feries_nuit', 'DECIMAL(15,2) DEFAULT 0'),
        ('base_onfpp', 'DECIMAL(15,2) DEFAULT 0'),
    ]
    for col_name, col_type in bul_cols:
        try:
            cursor.execute(f'ALTER TABLE bulletins_paie ADD COLUMN {col_name} {col_type}')
        except Exception:
            pass
    try:
        cursor.execute(
            'UPDATE bulletins_paie SET base_onfpp = COALESCE(base_vf, 0) '
            'WHERE COALESCE(contribution_onfpp, 0) > 0 AND COALESCE(base_onfpp, 0) = 0'
        )
    except Exception:
        pass

    # Colonnes sur rubriques_paie (catégorie, mode calcul, exonération)
    rub_cols = [
        ('categorie_rubrique', 'VARCHAR(20) DEFAULT "autre"'),
        ('mode_calcul', 'VARCHAR(20) DEFAULT "fixe"'),
        ('inclus_brut', 'BOOLEAN DEFAULT 1'),
        ('exonere_rts', 'BOOLEAN DEFAULT 0'),
    ]
    for col_name, col_type in rub_cols:
        try:
            cursor.execute(f'ALTER TABLE rubriques_paie ADD COLUMN {col_name} {col_type}')
        except Exception:
            pass

    # Correction barème RTS — CGI Guinée officiel (bornes continues)
    # T1: 0-1M=0%, T2: 1M-3M=5%, T3: 3M-5M=8%, T4: 5M-10M=10%, T5: 10M-20M=15%, T6: +20M=20%
    bareme_cgi = [
        (1, 0, 1000000, 0.00),
        (2, 1000000, 3000000, 5.00),
        (3, 3000000, 5000000, 8.00),
        (4, 5000000, 10000000, 10.00),
        (5, 10000000, 20000000, 15.00),
        (6, 20000000, None, 20.00),
    ]
    try:
        for annee in [2025, 2026]:
            # Supprimer les anciennes tranches de cette année
            cursor.execute('DELETE FROM tranches_irg WHERE annee_validite=?', (annee,))
            debut = '%d-01-01' % annee
            fin = '%d-12-31' % annee
            for num, b_inf, b_sup, taux in bareme_cgi:
                cursor.execute(
                    'INSERT INTO tranches_irg (numero_tranche, borne_inferieure, borne_superieure, taux_irg, '
                    'annee_validite, date_debut_validite, date_fin_validite, actif) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, 1)',
                    (num, b_inf, b_sup, taux, annee, debut, fin)
                )
    except Exception:
        pass  # table n'existe pas encore

    # Table parametres_calcul_paie (moteur de formules personnalisées)
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parametres_calcul_paie (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entreprise_id INTEGER NOT NULL UNIQUE REFERENCES entreprises(id) ON DELETE CASCADE,
                mode_exoneration_indemnites VARCHAR(20) NOT NULL DEFAULT "plafond_pct",
                plafond_exoneration_pct DECIMAL(5,2) NOT NULL DEFAULT 25,
                formule_exoneration TEXT NOT NULL DEFAULT "",
                mode_base_vf VARCHAR(30) NOT NULL DEFAULT "brut_moins_deduction",
                formule_base_vf TEXT NOT NULL DEFAULT "",
                mode_base_onfpp VARCHAR(20) NOT NULL DEFAULT "base_vf",
                utiliser_formule_base_rts BOOLEAN NOT NULL DEFAULT 0,
                formule_base_rts TEXT NOT NULL DEFAULT "",
                date_modification DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    except Exception:
        pass  # table existe déjà

    # Table historique paramètres paie
    try:
        cursor.execute(
            'ALTER TABLE parametres_calcul_paie '
            'ADD COLUMN mode_base_onfpp VARCHAR(20) NOT NULL DEFAULT "base_vf"'
        )
    except Exception:
        pass

    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS historique_parametres_paie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parametres_id INTEGER,
            modifie_par_id INTEGER,
            date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
            champ_modifie VARCHAR(100),
            ancienne_valeur TEXT DEFAULT "",
            nouvelle_valeur TEXT DEFAULT "",
            raison VARCHAR(200) DEFAULT ""
        )''')
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("  Colonnes manquantes ajoutees + bareme RTS corrige (patch direct)")


# ─── Point d'entrée principal ──────────────────────────────────────────────────
def main():
    # Configurer Django
    os.environ['DJANGO_SETTINGS_MODULE'] = 'gestionnaire_rh.settings'

    # Marqueur « application de bureau » : active le bouton « Quitter l'application »
    # dans l'interface. Absent quand on lance un simple `manage.py runserver` (web).
    os.environ['GESTIONNAIRE_RH_DESKTOP'] = '1'

    if getattr(sys, 'frozen', False):
        os.environ['PYINSTALLER_BASE_DIR'] = BASE_DIR
        os.environ['PYINSTALLER_INTERNAL_DIR'] = INTERNAL_DIR

    # ── Vérification licence AVANT tout démarrage de Django ──────────────────
    print("=" * 50)
    print("  GESTIONNAIRE RH GUINEE - VERSION OFFLINE")
    print("=" * 50)
    print()

    # ── Vérifications de protection au démarrage ───────────────────────────────
    if getattr(sys, 'frozen', False):
        try:
            import project_guardian
            report = project_guardian.full_security_check()
            if report.get('blocked'):
                print()
                print("  [SECURITE] Application bloquee !")
                print(f"  [SECURITE] Raison : {report.get('reason', 'Violation detectee')}")
                print()
                print("  Ce logiciel a ete modifie ou copie de maniere non autorisee.")
                print("  Contactez ICG Guinea pour obtenir une copie legale.")
                print()
                _safe_pause("Ce logiciel a ete modifie ou copie de maniere non "
                            "autorisee.\nContactez ICG Guinea pour obtenir une "
                            "copie legale.")
                sys.exit(1)
        except ImportError:
            print("  [SECURITE] Module de protection manquant — blocage.")
            _safe_pause("Module de protection manquant. Contactez ICG Guinea.")
            sys.exit(1)
        except Exception:
            pass  # En cas d'erreur inattendue, ne pas bloquer le propriétaire

        try:
            import runtime_shield
            shield_result = runtime_shield.full_shield_check()
            if shield_result.get('blocked'):
                print()
                print("  [SECURITE] Falsification detectee !")
                print(f"  [SECURITE] {shield_result.get('reason', 'Environnement compromis')}")
                print()
                _safe_pause("Falsification detectee. Environnement compromis.\n"
                            "Contactez ICG Guinea.")
                sys.exit(1)
        except ImportError:
            print("  [SECURITE] Bouclier runtime manquant — blocage.")
            _safe_pause("Bouclier runtime manquant. Contactez ICG Guinea.")
            sys.exit(1)
        except Exception:
            pass

    check_license()   # Bloque ou ferme l'app si essai/licence expiré

    try:
        import django
        django.setup()

        from django.core.management import call_command

        # Base de données
        db_path = os.path.join(BASE_DIR, 'db.sqlite3')
        if os.path.exists(db_path):
            print("  Base de donnees OK")
        else:
            print("  Base de donnees absente - creation en cours...")
            # Copier le template pre-migre si disponible
            template_path = os.path.join(BASE_DIR, 'db_template.sqlite3')
            if os.path.exists(template_path):
                import shutil
                shutil.copy2(template_path, db_path)
                print("  Base de donnees initialisee depuis le template")

        # Migrations — applique les nouvelles migrations sur la DB existante
        try:
            call_command('migrate', '--run-syncdb', verbosity=0)
            print("  Migrations appliquees avec succes")
        except Exception as e:
            # Si erreur "table already exists", tenter avec --fake-initial
            if 'already exists' in str(e):
                try:
                    call_command('migrate', '--fake-initial', verbosity=0)
                    print("  Migrations appliquees (fake-initial)")
                except Exception as e2:
                    print(f"  Erreur migration fake-initial: {e2}")
            else:
                print(f"  Erreur migration: {e}")
                # Fallback: appliquer colonnes manquantes directement
                try:
                    _apply_missing_columns()
                except Exception:
                    pass

        # Vérifier que les tables critiques existent
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                existing = {row[0] for row in cursor.fetchall()}
            critical = [
                'django_session', 'django_content_type',
                'auth_user', 'auth_permission', 'auth_group',
                'django_admin_log', 'django_migrations',
            ]
            missing = [t for t in critical if t not in existing]
            if missing:
                print(f"  [!] Tables manquantes: {', '.join(missing)}")
                print("  [!] Tentative de creation forcee...")
                for app_label in ['contenttypes', 'auth', 'sessions', 'admin']:
                    try:
                        call_command('migrate', app_label, verbosity=1)
                    except Exception:
                        pass
                # Re-vérifier
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    existing = {row[0] for row in cursor.fetchall()}
                still_missing = [t for t in critical if t not in existing]
                if still_missing:
                    print(f"  [!!] Tables encore manquantes: {', '.join(still_missing)}")
                    print("  [!!] Tentative syncdb...")
                    try:
                        from django.core.management.commands.migrate import Command as MigrateCommand
                        from django.apps import apps
                        from django.db import connection as db_conn
                        with db_conn.schema_editor() as editor:
                            for app_config in apps.get_app_configs():
                                for model in app_config.get_models():
                                    if model._meta.db_table not in existing:
                                        try:
                                            editor.create_model(model)
                                        except Exception:
                                            pass
                    except Exception as e2:
                        print(f"  [!!] Erreur syncdb manuelle: {e2}")
                else:
                    print("  Tables creees avec succes")
        except Exception as e:
            print(f"  Verification tables: {e}")

        print()
        print("  Serveur demarre sur: http://127.0.0.1:8000/")
        print("  Ouverture dans la fenetre de l'application...")
        print("=" * 50)
        print()

        # Désactiver check_migrations : les migrations sont déjà appliquées mais
        # l'archive PYZ peut contenir une version obsolète du graphe de dépendances.
        try:
            from django.core.management.commands import runserver as _rs
            _rs.Command.check_migrations = lambda self: None
        except Exception:
            pass

        # Lancer le serveur Django en arrière-plan (thread démon : il s'arrête
        # automatiquement à la fermeture de la fenêtre / de l'application).
        def _run_django_server():
            try:
                call_command('runserver', '--noreload', '127.0.0.1:8000')
            except Exception as exc:
                print(f"  [Serveur] Arret: {exc}")

        server_thread = threading.Thread(target=_run_django_server, daemon=True)
        server_thread.start()

        # Ouvrir l'application dans sa propre fenêtre (thread principal).
        # Bloque jusqu'à la fermeture de la fenêtre.
        open_app_window()

    except KeyboardInterrupt:
        print("\nServeur arrete.")
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"Erreur: {e}")
        print()
        traceback.print_exc()
        print()
        _safe_pause("Une erreur est survenue au demarrage de GestionnaireRH.\n\n"
                    f"{e}\n\nConsultez logs/launcher.log pour plus de details.")
        sys.exit(1)


if __name__ == '__main__':
    main()
