@echo off
title Build Auto GestionnaireRH_Setup_v1.2.5
chcp 65001 >nul 2>nul
cd /d "%~dp0"

echo ============================================================
echo   BUILD AUTO — GestionnaireRH_Setup_v1.2.5
echo   Etapes: Nuitka → PyInstaller → Inno Setup
echo ============================================================
echo.

:: ─── ETAPE 1 : Nuitka recompile project_guardian + runtime_shield ────────────
echo [1/4] Compilation Nuitka (project_guardian + runtime_shield)...
if not exist dist_nuitka mkdir dist_nuitka

python -m nuitka --module --output-dir=dist_nuitka --remove-output --no-pyi-file --python-flag=no_docstrings --python-flag=no_asserts --zig project_guardian.py
if errorlevel 1 (
    echo [ERREUR] Echec Nuitka project_guardian.py
    exit /b 1
)
echo   project_guardian.pyd OK

python -m nuitka --module --output-dir=dist_nuitka --remove-output --no-pyi-file --python-flag=no_docstrings --python-flag=no_asserts --zig runtime_shield.py
if errorlevel 1 (
    echo [ERREUR] Echec Nuitka runtime_shield.py
    exit /b 1
)
echo   runtime_shield.pyd OK
echo.

:: ─── ETAPE 2 : Resign manifest ───────────────────────────────────────────────
echo [2/4] Regeneration manifest integrite...
python project_guardian.py sign
echo.

:: ─── ETAPE 3 : PyInstaller ───────────────────────────────────────────────────
echo [3/4] Build PyInstaller...
python manage.py collectstatic --noinput >nul 2>nul

if exist dist\GestionnaireRH rmdir /s /q dist\GestionnaireRH
if exist build\GestionnaireRH_build rmdir /s /q build\GestionnaireRH_build

pyinstaller --clean --noconfirm --distpath dist --workpath build GestionnaireRH_build.spec
if errorlevel 1 (
    echo [ERREUR] Build PyInstaller echoue!
    exit /b 1
)

:: Copie manifest uniquement (pas les .py)
copy /Y .integrity_manifest.json dist\GestionnaireRH\_internal\.integrity_manifest.json >nul

:: Base de donnees template
if exist dist\GestionnaireRH\db_template.sqlite3 del dist\GestionnaireRH\db_template.sqlite3
python create_db_template.py "dist\GestionnaireRH\db_template.sqlite3" >nul 2>nul

:: Suppression manuelle des .py critiques si presents dans _internal
if exist dist\GestionnaireRH\_internal\project_guardian.py del dist\GestionnaireRH\_internal\project_guardian.py
if exist dist\GestionnaireRH\_internal\runtime_shield.py del dist\GestionnaireRH\_internal\runtime_shield.py
if exist dist\GestionnaireRH\_internal\license_manager.py del dist\GestionnaireRH\_internal\license_manager.py

:: Verification .pyd presents
if not exist dist\GestionnaireRH\_internal\project_guardian*.pyd (
    echo [ERREUR] project_guardian.pyd manquant dans _internal!
    exit /b 1
)
if not exist dist\GestionnaireRH\_internal\runtime_shield*.pyd (
    echo [ERREUR] runtime_shield.pyd manquant dans _internal!
    exit /b 1
)

:: Protection distribution
python protect_distribution.py dist\GestionnaireRH
echo   PyInstaller + protection OK
echo.

:: ─── ETAPE 4 : Inno Setup ────────────────────────────────────────────────────
echo [4/4] Compilation Inno Setup...
if not exist Output mkdir Output

"C:\InnoSetup6\ISCC.exe" /Q installer_guineerh.iss
if errorlevel 1 (
    echo [ERREUR] Compilation Inno Setup echouee!
    exit /b 1
)

echo.
echo ============================================================
echo   SETUP COMPILE AVEC SUCCES!
echo ============================================================
if exist Output\GestionnaireRH_Setup_v1.2.5.exe (
    echo   Fichier: Output\GestionnaireRH_Setup_v1.2.5.exe
    for %%A in (Output\GestionnaireRH_Setup_v1.2.5.exe) do echo   Taille : %%~zA octets
)
echo.
