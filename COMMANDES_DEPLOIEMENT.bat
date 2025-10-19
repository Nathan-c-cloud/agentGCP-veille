@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
REM Script de déploiement pour Windows
REM À exécuter dans Google Cloud Shell ou sur Windows avec gcloud CLI installé

echo ==========================================
echo DEPLOIEMENT AGENT FISCAL - SYSTEME COMPLET
echo ==========================================
echo.

REM Configuration
set PROJECT_ID=agent-gcp-f6005
set REGION=us-west1

REM Vérifier le projet
echo Configuration du projet...
call gcloud config set project %PROJECT_ID%
echo Projet configure: %PROJECT_ID%
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
call gcloud functions deploy surveiller-sites --gen2 --runtime=python311 --region=%REGION% --source=. --entry-point=surveiller_sites --trigger-http --allow-unauthenticated --memory=1GB --timeout=540s --set-env-vars=PROJECT_ID=%PROJECT_ID%

echo.
echo Pipeline deploye avec succes !
echo.

REM Déployer l'agent
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
call gcloud functions deploy agent-fiscal-v2 --gen2 --runtime=python311 --region=%REGION% --source=. --entry-point=agent_fiscal --trigger-http --allow-unauthenticated --memory=512MB --timeout=60s --set-env-vars=PROJECT_ID=%PROJECT_ID%

echo.
echo Agent deploye avec succes !
echo.

cd ..

echo ==========================================
echo DEPLOIEMENT TERMINE
echo ==========================================
echo.
echo Fonctions deployees:
echo   1. surveiller-sites (Pipeline ETL )
echo   2. agent-fiscal-v2 (Agent conversationnel)
echo.
echo Pour obtenir les URLs:
echo   gcloud functions describe surveiller-sites --region=%REGION% --gen2
echo   gcloud functions describe agent-fiscal-v2 --region=%REGION% --gen2
echo.
echo PROCHAINES ETAPES:
echo   1. Ajouter les sources: python ajouter_sources_firestore.py
echo   2. Executer le pipeline pour creer les chunks
echo   3. Connecter votre frontend
echo.
pause
ENDLOCAL
