@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
REM Script de déploiement pour Windows
REM À exécuter dans Google Cloud Shell ou sur Windows avec gcloud CLI installé

echo ==========================================
echo DEPLOIEMENT SYSTEME COMPLET - AGENT MULTI-SPECIALISE
echo ==========================================
echo.

REM Charger les variables depuis le fichier .env
if not exist ".env" (
    echo ERREUR: Fichier .env introuvable a la racine du projet !
    echo Creez un fichier .env avec vos cles API.
    pause
    exit /b 1
)

echo Chargement des variables depuis .env...
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" (
        set %%a=%%b
    )
)

REM Configuration
set REGION=us-west1

REM Vérifier le projet
echo Configuration du projet...
call gcloud config set project %PROJECT_ID%
echo Projet configure: %PROJECT_ID%
echo.

REM Le bucket documents-fiscaux-bucket existe deja
echo Utilisation du bucket existant: gs://%BUCKET_NAME%
echo.

REM Déployer le pipeline
echo ==========================================
echo 1. DEPLOIEMENT DU PIPELINE DE VEILLE
echo ==========================================

if not exist "pipeline-veille" (
    echo ERREUR: Le repertoire pipeline-veille n'existe pas !
    pause
    exit /b 1
)

echo Changement vers pipeline-veille...
cd pipeline-veille
echo Repertoire actuel: %CD%
echo.

echo Deploiement de surveiller-sites...
call gcloud functions deploy surveiller-sites --gen2 --runtime=python311 --region=%REGION% --source=. --entry-point=surveiller_sites --trigger-http --allow-unauthenticated --memory=1GB --timeout=540s --set-env-vars=PROJECT_ID=%PROJECT_ID%,BUCKET_NAME=%BUCKET_NAME%,GOOGLE_API_KEY=%GOOGLE_API_KEY%,SEARCH_ENGINE_ID=%SEARCH_ENGINE_ID%

echo.
echo Pipeline deploye avec succes !
echo.

REM Déployer l'agent fiscal
echo ==========================================
echo 2. DEPLOIEMENT DE L'AGENT FISCAL
echo ==========================================

cd ..

if not exist "agent-fiscal" (
    echo ERREUR: Le repertoire agent-fiscal n'existe pas !
    pause
    exit /b 1
)

echo Changement vers agent-fiscal...
cd agent-fiscal
echo Repertoire actuel: %CD%
echo.

echo Deploiement de agent-fiscal-v2...

call gcloud functions deploy agent-fiscal-v2 --gen2 --runtime=python311 --region=%REGION% --source=. --entry-point=agent_fiscal --trigger-http --allow-unauthenticated --memory=512MB --timeout=60s --set-env-vars=PROJECT_ID=%PROJECT_ID%,BUCKET_NAME=%BUCKET_NAME%

echo.
echo Agent fiscal deploye avec succes !
echo.

REM Déployer l'agent client orchestrateur
echo ==========================================
echo 3. DEPLOIEMENT DE L'AGENT CLIENT (ORCHESTRATEUR)
echo ==========================================

cd ..

if not exist "Agent-client" (
    echo ERREUR: Le repertoire Agent-client n'existe pas !
    pause
    exit /b 1
)

echo Changement vers Agent-client...
cd Agent-client
echo Repertoire actuel: %CD%
echo.

echo Deploiement de agent-client (orchestrateur intelligent)...
call gcloud functions deploy agent-client --gen2 --runtime=python311 --region=%REGION% --source=. --entry-point=agent_client --trigger-http --allow-unauthenticated --memory=512MB --timeout=60s --set-env-vars=PROJECT_ID=%PROJECT_ID%

echo.
echo Agent client deploye avec succes !
echo.

cd ..

echo ==========================================
echo DEPLOIEMENT TERMINE
echo ==========================================
echo.
echo Fonctions deployees:
echo   1. surveiller-sites (Pipeline ETL)
echo   2. agent-fiscal-v2 (Agent fiscal specialise)
echo   3. agent-client (Orchestrateur intelligent - POINT D'ENTREE)
echo.
echo ARCHITECTURE:
echo   Frontend ---^> agent-client ---^> agent-fiscal-v2
echo                                ---^> [autres agents futurs]
echo.
echo Pour obtenir les URLs:
echo   gcloud functions describe surveiller-sites --region=%REGION% --gen2
echo   gcloud functions describe agent-fiscal-v2 --region=%REGION% --gen2
echo   gcloud functions describe agent-client --region=%REGION% --gen2
echo.
echo PROCHAINES ETAPES:
echo   1. Ajouter les sources: python ajouter_sources_firestore.py
echo   2. Executer le pipeline pour creer les documents
echo   3. Tester l'agent client avec votre frontend
echo.

pause
