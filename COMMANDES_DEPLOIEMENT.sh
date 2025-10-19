#!/bin/bash
# Script de déploiement rapide pour les deux Cloud Functions
# À exécuter dans Google Cloud Shell

set -e  # Arrêter en cas d'erreur

echo "=========================================="
echo "DÉPLOIEMENT AGENT FISCAL - SYSTÈME COMPLET"
echo "=========================================="
echo ""

# Configuration
PROJECT_ID="agent-gcp-f6005"
REGION="us-west1"

# Vérifier le projet
echo "📋 Configuration du projet..."
gcloud config set project $PROJECT_ID
echo "✅ Projet configuré: $PROJECT_ID"
echo ""

# Déployer le pipeline
echo "=========================================="
echo "1️⃣  DÉPLOIEMENT DU PIPELINE DE VEILLE"
echo "=========================================="
cd pipeline-veille

gcloud functions deploy surveiller-sites \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=. \
  --entry-point=surveiller_sites \
  --trigger-http \
  --allow-unauthenticated \
  --memory=1GB \
  --timeout=540s \
  --set-env-vars=PROJECT_ID=$PROJECT_ID

echo ""
echo "✅ Pipeline déployé avec succès !"
echo ""

# Récupérer l'URL du pipeline
PIPELINE_URL=$(gcloud functions describe surveiller-sites \
  --region=$REGION \
  --gen2 \
  --format='value(serviceConfig.uri)')

echo "📍 URL du pipeline: $PIPELINE_URL"
echo ""

# Déployer l'agent
echo "=========================================="
echo "2️⃣  DÉPLOIEMENT DE L'AGENT FISCAL"
echo "=========================================="
cd ../agent-fiscal

gcloud functions deploy agent-fiscal-v2 \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=. \
  --entry-point=agent_fiscal \
  --trigger-http \
  --allow-unauthenticated \
  --memory=512MB \
  --timeout=60s \
  --set-env-vars=PROJECT_ID=$PROJECT_ID

echo ""
echo "✅ Agent déployé avec succès !"
echo ""

# Récupérer l'URL de l'agent
AGENT_URL=$(gcloud functions describe agent-fiscal-v2 \
  --region=$REGION \
  --gen2 \
  --format='value(serviceConfig.uri)')

echo "📍 URL de l'agent: $AGENT_URL"
echo ""

# Résumé
echo "=========================================="
echo "✅ DÉPLOIEMENT TERMINÉ"
echo "=========================================="
echo ""
echo "📦 Fonctions déployées:"
echo "  1. surveiller-sites (Pipeline ETL)"
echo "     $PIPELINE_URL"
echo ""
echo "  2. agent-fiscal-v2 (Agent conversationnel)"
echo "     $AGENT_URL"
echo ""
echo "=========================================="
echo "🧪 TESTS"
echo "=========================================="
echo ""
echo "Pour tester le pipeline:"
echo "  curl -X POST \"$PIPELINE_URL\""
echo ""
echo "Pour tester l'agent:"
echo "  curl -X POST \"$AGENT_URL\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"question\": \"C'\\''est quoi la TVA ?\"}'"
echo ""
echo "=========================================="
echo "📋 PROCHAINES ÉTAPES"
echo "=========================================="
echo ""
echo "1. Ajouter les sources dans Firestore:"
echo "   cd .. && python3 ajouter_sources_firestore.py"
echo ""
echo "2. Exécuter le pipeline pour créer les chunks:"
echo "   curl -X POST \"$PIPELINE_URL\""
echo ""
echo "3. Connecter votre frontend à l'URL de l'agent"
echo ""
echo "🎉 Votre agent fiscal est prêt !"

