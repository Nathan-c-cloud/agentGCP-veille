#!/bin/bash

# Script de déploiement pour agent-aides sur Cloud Run

set -e

echo "=== Déploiement de agent-aides sur Cloud Run ==="
echo ""

# Variables
PROJECT_ID="agent-gcp-f6005"
REGION="us-west1"
SERVICE_NAME="agent-aides"

echo "Projet: $PROJECT_ID"
echo "Région: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Configurer le projet
echo "Configuration du projet..."
gcloud config set project $PROJECT_ID

# Déployer sur Cloud Run
echo "Déploiement en cours..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --project $PROJECT_ID \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars PROJECT_ID=$PROJECT_ID,LOCATION=$REGION \
  --platform managed

echo ""
echo "=== Déploiement terminé ==="
echo ""

# Afficher l'URL du service
echo "Récupération de l'URL du service..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --project $PROJECT_ID \
  --format="value(status.url)")

echo ""
echo "✅ Service déployé avec succès!"
echo "URL: $SERVICE_URL"
echo ""

# Vérifier la santé du service
echo "Test du endpoint /health..."
curl -s "$SERVICE_URL/health" | jq .

echo ""
echo "=== Affichage des logs récents ==="
gcloud run services logs read $SERVICE_NAME \
  --region $REGION \
  --project $PROJECT_ID \
  --limit 50

echo ""
echo "Pour voir les logs en temps réel, utilisez:"
echo "gcloud run services logs tail $SERVICE_NAME --region $REGION --project $PROJECT_ID"

