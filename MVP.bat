@echo off
chcp 65001 >nul
title Orchestra - MVP
cd /d "%~dp0"
if not exist "%~dp0mvp.ps1" goto :nozip
if not exist "%~dp0platform\orchestra\__init__.py" goto :nozip
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mvp.ps1" %*
echo.
pause
exit /b

:nozip
echo.
echo  ============================================================
echo   Le dossier Orchestra est incomplet.
echo.
echo   Vous avez probablement lance MVP.bat DEPUIS le fichier ZIP.
echo   1. Fermez cette fenetre.
echo   2. Clic droit sur Orchestra-MVP.zip, puis "Extraire tout...".
echo   3. Ouvrez le dossier extrait (Orchestra) et double-cliquez
echo      sur MVP.bat.
echo  ============================================================
echo.
pause
exit /b 1
