@echo off
REM Script de déploiement : Veille Automatique + Cloud Scheduler

echo ========================================
echo DEPLOIEMENT VEILLE AUTOMATIQUE
echo ========================================

cd /d %~dp0

echo.
echo 1. Deploiement de la Cloud Function...
echo.

gcloud functions deploy veille-automatique --gen2 --runtime=python311 --region=us-west1 --source=. --entry-point=veille_automatique --trigger-http --allow-unauthenticated --timeout=540 --memory=1024M --set-env-vars=PROJECT_ID=agent-gcp-f6005

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERREUR lors du deploiement
    pause
    exit /b 1
)

echo.
echo ========================================
echo 2. Configuration Cloud Scheduler
echo ========================================
echo.

echo Suppression de l'ancien job s'il existe...
gcloud scheduler jobs delete veille-fiscale-automatique --location=us-west1 --quiet 2>nul

echo Creation du job scheduler (2x par jour: 9h et 17h)...
gcloud scheduler jobs create http veille-fiscale-automatique --location=us-west1 --schedule="0 9,17 * * *" --uri="https://us-west1-agent-gcp-f6005.cloudfunctions.net/veille-automatique" --http-method=POST --headers="Content-Type=application/json" --time-zone="Europe/Paris"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERREUR lors de la creation du scheduler
    pause
    exit /b 1
)

echo.
echo ========================================
echo DEPLOIEMENT TERMINE
echo ========================================
echo.
echo Fonction deployee: veille-automatique
echo URL: https://us-west1-agent-gcp-f6005.cloudfunctions.net/veille-automatique
echo.
echo Scheduler: veille-fiscale-automatique
echo Frequence: 2 fois par jour (9h et 17h, heure de Paris)
echo.
echo COMMANDES UTILES:
echo   Tester: curl -X POST https://us-west1-agent-gcp-f6005.cloudfunctions.net/veille-automatique
echo   Forcer: gcloud scheduler jobs run veille-fiscale-automatique --location=us-west1
echo   Logs: gcloud functions logs read veille-automatique --region us-west1 --limit 50
echo.
pause

