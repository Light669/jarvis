@echo off
rem Double-cliquez sur ce fichier pour lancer le MVP Orchestra.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mvp.ps1" %*
if errorlevel 1 pause
