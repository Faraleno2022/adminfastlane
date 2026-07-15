# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file pour GestionnaireRH
Génère un exécutable Windows standalone avec icône
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Répertoire du projet
PROJECT_DIR = Path(r'C:\Users\LENO\Desktop\GestionnaireRHofline')

block_cipher = None

# ── Localiser les paquets installés pour collecter les fichiers de migration ──
import django
import axes
DJANGO_DIR = Path(django.__file__).parent
AXES_DIR = Path(axes.__file__).parent

# ── pywebview + pythonnet (fenêtre native WebView2) ──────────────────────────
# Collecte complète : binaires .NET (Python.Runtime.dll), data et sous-modules.
_webview_datas, _webview_binaries, _webview_hidden = collect_all('webview')
_clr_datas, _clr_binaries, _clr_hidden = collect_all('clr_loader')
_pythonnet_datas, _pythonnet_binaries, _pythonnet_hidden = collect_all('pythonnet')

# Collecter tous les fichiers de données
datas = [
    # Templates Django
    (str(PROJECT_DIR / 'templates'), 'templates'),
    # Fichiers statiques
    (str(PROJECT_DIR / 'static'), 'static'),
    (str(PROJECT_DIR / 'staticfiles'), 'staticfiles'),
    # Applications Django
    (str(PROJECT_DIR / 'core'), 'core'),
    (str(PROJECT_DIR / 'employes'), 'employes'),
    (str(PROJECT_DIR / 'paie'), 'paie'),
    (str(PROJECT_DIR / 'temps_travail'), 'temps_travail'),
    (str(PROJECT_DIR / 'recrutement'), 'recrutement'),
    (str(PROJECT_DIR / 'formation'), 'formation'),
    (str(PROJECT_DIR / 'dashboard'), 'dashboard'),
    (str(PROJECT_DIR / 'payments'), 'payments'),
    (str(PROJECT_DIR / 'conges'), 'conges'),
    (str(PROJECT_DIR / 'contrats'), 'contrats'),
    (str(PROJECT_DIR / 'portail'), 'portail'),
    (str(PROJECT_DIR / 'comptabilite'), 'comptabilite'),
    (str(PROJECT_DIR / 'secretariat'), 'secretariat'),
    (str(PROJECT_DIR / 'stock'), 'stock'),
    # Configuration Django
    (str(PROJECT_DIR / 'gestionnaire_rh'), 'gestionnaire_rh'),
    # Fichiers de configuration
    (str(PROJECT_DIR / 'manage.py'), '.'),
    # Protection anti-vol et anti-falsification (ICG Guinea)
    # NOTE: project_guardian.py et runtime_shield.py ne sont PAS inclus ici.
    # Seuls les .pyd Nuitka sont dans binaries[] — les .py sources déclencheraient
    # le blocage du runtime_shield dans _internal.
    (str(PROJECT_DIR / '.integrity_manifest.json'), '.'),
    # ── Migrations Django built-in (chargées dynamiquement, absentes du PYZ) ──
    (str(DJANGO_DIR / 'contrib' / 'admin' / 'migrations'), 'django/contrib/admin/migrations'),
    (str(DJANGO_DIR / 'contrib' / 'auth' / 'migrations'), 'django/contrib/auth/migrations'),
    (str(DJANGO_DIR / 'contrib' / 'contenttypes' / 'migrations'), 'django/contrib/contenttypes/migrations'),
    (str(DJANGO_DIR / 'contrib' / 'sessions' / 'migrations'), 'django/contrib/sessions/migrations'),
    # ── Migrations axes (django-axes) ──
    (str(AXES_DIR / 'migrations'), 'axes/migrations'),
]

# Ajouter les données de pywebview / pythonnet
datas += _webview_datas + _clr_datas + _pythonnet_datas

# Modules cachés nécessaires pour Django
hiddenimports = [
    'django',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.template.backends.django',
    'django.template.loader_tags',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_filters',
    'widget_tweaks',
    'import_export',
    'rest_framework',
    'corsheaders',
    'corsheaders.middleware',
    'axes',
    'axes.middleware',
    'csp',
    'csp.middleware',
    'whitenoise',
    'whitenoise.middleware',
    'whitenoise.storage',
    'reportlab',
    'reportlab.lib',
    'reportlab.pdfgen',
    'reportlab.platypus',
    'reportlab.graphics',
    'openpyxl',
    'PIL',
    'decouple',
    'core',
    'core.models',
    'core.views',
    'core.middleware',
    'core.middleware_licence',
    'core.middleware_guardian',
    'project_guardian',
    'runtime_shield',
    'employes',
    'employes.models',
    'employes.views',
    'paie',
    'paie.models',
    'paie.views',
    'paie.services',
    'temps_travail',
    'temps_travail.models',
    'temps_travail.views',
    'recrutement',
    'recrutement.models',
    'recrutement.views',
    'formation',
    'formation.models',
    'formation.views',
    'dashboard',
    'dashboard.views',
    'payments',
    'payments.models',
    'payments.views',
    'conges',
    'conges.models',
    'conges.views',
    'contrats',
    'contrats.models',
    'contrats.views',
    'portail',
    'portail.views',
    'comptabilite',
    'comptabilite.models',
    'comptabilite.views',
    'secretariat',
    'secretariat.models',
    'secretariat.views',
    'stock',
    'stock.models',
    'stock.views',
    'stock.audit',
    'stock.api',
    'stock.serializers',
    'gestionnaire_rh.settings',
    'gestionnaire_rh.settings_portable',
    'gestionnaire_rh.urls',
    'gestionnaire_rh.wsgi',
    # Tkinter (fenetre d'activation de licence)
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    '_tkinter',
    # Stdlib
    'winreg',
    'hmac',
    'hashlib',
    'base64',
    'uuid',
    'socket',
    'platform',
    # Fenêtre native (pywebview + backend Edge WebView2 via pythonnet)
    'webview',
    'webview.platforms.edgechromium',
    'webview.platforms.winforms',
    'clr',
    'clr_loader',
    'bottle',
    'proxy_tools',
]

# Sous-modules + imports cachés collectés pour pywebview / pythonnet
hiddenimports += _webview_hidden + _clr_hidden + _pythonnet_hidden

a = Analysis(
    [str(PROJECT_DIR / 'run_server.py')],
    pathex=[str(PROJECT_DIR)],
    binaries=[
        # Nuitka-compiled modules (native binary — non-decompilable)
        (str(PROJECT_DIR / 'dist_nuitka' / 'license_manager.cp313-win_amd64.pyd'), '.'),
        (str(PROJECT_DIR / 'dist_nuitka' / 'project_guardian.cp313-win_amd64.pyd'), '.'),
        (str(PROJECT_DIR / 'dist_nuitka' / 'runtime_shield.cp313-win_amd64.pyd'), '.'),
    ] + _webview_binaries + _clr_binaries + _pythonnet_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PROJECT_DIR / 'runtime_hooks' / 'hook_no_numpy.py')],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'license_manager',   # excluded: native .pyd is in binaries instead
        # project_guardian et runtime_shield inclus normalement dans PYZ
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=1,   # strip assert statements UNIQUEMENT — garder les docstrings
                  # (pycparser, via cffi/pythonnet pour WebView2, en a besoin)
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GestionnaireRH',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # False : pas de fenetre noire — l'app s'ouvre dans sa propre fenetre
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_DIR / 'static' / 'img' / 'logo.ico') if (PROJECT_DIR / 'static' / 'img' / 'logo.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GestionnaireRH',
)

# ─── Post-build: remove license_manager.py source, keep only the .pyd ─────────
import shutil as _shutil, os as _os
_internal = str(PROJECT_DIR / 'dist' / 'GestionnaireRH' / '_internal')
_py_src = _os.path.join(_internal, 'license_manager.py')
_pyc_dir = _os.path.join(_internal, '__pycache__')
_pyd_src = str(PROJECT_DIR / 'dist_nuitka' / 'license_manager.cp313-win_amd64.pyd')
_pyd_dst = _os.path.join(_internal, 'license_manager.cp313-win_amd64.pyd')

if _os.path.exists(_py_src):
    _os.remove(_py_src)
    print('[Protection] Removed license_manager.py from dist')
if _os.path.exists(_pyc_dir):
    for _f in _os.listdir(_pyc_dir):
        if 'license_manager' in _f:
            _os.remove(_os.path.join(_pyc_dir, _f))
if _os.path.exists(_pyd_src) and not _os.path.exists(_pyd_dst):
    _shutil.copy2(_pyd_src, _pyd_dst)
    print('[Protection] Installed license_manager.pyd in dist')
print('[Protection] license_manager protection applied.')

# ─── Post-build: install Nuitka-compiled project_guardian.pyd & runtime_shield.pyd ───
for _mod_name in ['project_guardian', 'runtime_shield']:
    # Find the .pyd in dist_nuitka/
    _pyd_found = None
    _nuitka_dir = str(PROJECT_DIR / 'dist_nuitka')
    if _os.path.exists(_nuitka_dir):
        for _f in _os.listdir(_nuitka_dir):
            if _f.startswith(_mod_name) and _f.endswith('.pyd'):
                _pyd_found = _os.path.join(_nuitka_dir, _f)
                break
    if _pyd_found:
        # Copy .pyd to _internal
        _dst = _os.path.join(_internal, _os.path.basename(_pyd_found))
        if not _os.path.exists(_dst):
            _shutil.copy2(_pyd_found, _dst)
        # Remove .py source from _internal
        _py = _os.path.join(_internal, _mod_name + '.py')
        if _os.path.exists(_py):
            _os.remove(_py)
            print(f'[Protection] Replaced {_mod_name}.py with native .pyd')
        # Remove .pyc
        if _os.path.exists(_pyc_dir):
            for _f in _os.listdir(_pyc_dir):
                if _mod_name in _f:
                    _os.remove(_os.path.join(_pyc_dir, _f))
        print(f'[Protection] {_mod_name} Nuitka protection applied.')
    else:
        print(f'[Protection] WARNING: {_mod_name}.pyd not found in dist_nuitka/')
        print(f'[Protection] {_mod_name}.py will be kept (run compile_nuitka.bat first!)')

# ─── Post-build: remove project_guardian.py source from dist (keep only in _internal) ──
_guardian_src = _os.path.join(_internal, 'project_guardian.py')
_guardian_pyc = _os.path.join(_pyc_dir)
if _os.path.exists(_guardian_src):
    # If we have a .pyd, remove the .py; otherwise keep .py (fallback)
    _has_guardian_pyd = any(
        f.startswith('project_guardian') and f.endswith('.pyd')
        for f in _os.listdir(_internal)
    )
    if _has_guardian_pyd:
        _os.remove(_guardian_src)
        print('[Protection] Removed project_guardian.py (using .pyd)')
if _os.path.exists(_pyc_dir):
    for _f in _os.listdir(_pyc_dir):
        if 'project_guardian' in _f:
            _os.remove(_os.path.join(_pyc_dir, _f))
            print('[Protection] Removed project_guardian .pyc from dist')
print('[Protection] project_guardian protection applied.')
