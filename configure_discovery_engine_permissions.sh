#!/bin/bash

# ============================================
# SCRIPT DE CONFIGURATION DES PERMISSIONS DISCOVERY ENGINE
# ============================================

set -e

echo "🔧 Configuration des permissions Discovery Engine (Vertex AI Search)"
echo ""

# --- Configuration ---
PROJECT_ID="agent-gcp-f6005"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
REGION="us-west1"

echo "📋 Projet : $PROJECT_ID"
echo "📋 Project Number : $PROJECT_NUMBER"
echo ""

# --- Étape 1 : Obtenir le service account de agent-juridique ---
echo "============================================"
echo "📋 Étape 1/3 : Récupération du service account de agent-juridique"
echo "============================================"
echo ""

JURIDIQUE_SA=$(gcloud run services describe agent-juridique \
  --region=$REGION \
  --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null)

if [ -z "$JURIDIQUE_SA" ]; then
  # Si pas de service account custom, utiliser le default
  JURIDIQUE_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
  echo "⚠️  Pas de service account custom, utilisation du default"
fi

echo "✅ Service account de agent-juridique : $JURIDIQUE_SA"
echo ""

# --- Étape 2 : Obtenir le service account de agent-aides ---
echo "============================================"
echo "📋 Étape 2/3 : Récupération du service account de agent-aides"
echo "============================================"
echo ""

AIDES_SA=$(gcloud run services describe agent-aides \
  --region=$REGION \
  --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null)

if [ -z "$AIDES_SA" ]; then
  # Si pas de service account custom, utiliser le default
  AIDES_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
  echo "⚠️  Pas de service account custom, utilisation du default"
fi

echo "✅ Service account de agent-aides : $AIDES_SA"
echo ""

# --- Étape 3 : Donner les permissions Discovery Engine ---
echo "============================================"
echo "📋 Étape 3/3 : Configuration des permissions Discovery Engine"
echo "============================================"
echo ""

echo "🔑 Attribution du rôle Discovery Engine Viewer..."

# Pour agent-juridique
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$JURIDIQUE_SA" \
  --role="roles/discoveryengine.viewer" \
  --condition=None \
  --quiet

echo "✅ Rôle accordé à $JURIDIQUE_SA"
echo ""

# Pour agent-aides (si différent)
if [ "$AIDES_SA" != "$JURIDIQUE_SA" ]; then
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$AIDES_SA" \
    --role="roles/discoveryengine.viewer" \
    --condition=None \
    --quiet
  echo "✅ Rôle accordé à $AIDES_SA"
else
  echo "ℹ️  Même service account, pas besoin de dupliquer"
fi

echo ""

# --- Résumé ---
echo "============================================"
echo "✅ CONFIGURATION TERMINÉE !"
echo "============================================"
echo ""
echo "📊 Résumé :"
echo "  - Service account agent-juridique : $JURIDIQUE_SA"
echo "  - Service account agent-aides : $AIDES_SA"
echo "  - Rôle accordé : roles/discoveryengine.viewer"
echo ""
echo "⏳ IMPORTANT : Les permissions peuvent prendre 1-2 minutes pour se propager."
echo ""
echo "🧪 Test de vérification (attendre 2 minutes) :"
echo ""
echo "# Test agent-juridique"
echo "JURIDIQUE_URL=\$(gcloud run services describe agent-juridique --region=$REGION --format='value(status.url)')"
echo "curl -X POST \"\$JURIDIQUE_URL/query\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"user_query\":\"C'\\''est quoi une SARL ?\"}' | jq"
echo ""
echo "# Test agent-aides"
echo "AIDES_URL=\$(gcloud run services describe agent-aides --region=$REGION --format='value(status.url)')"
echo "curl -X POST \"\$AIDES_URL/query\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"user_query\":\"Quelles aides pour une PME ?\"}' | jq"
echo ""
echo "============================================"

