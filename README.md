# Système de Veille Réglementaire Fiscale - Agent IA

Cette structure est prête pour le déploiement sur Google Cloud Functions.

## 📁 Contenu

```
agent-veille/
│
├── pipeline-veille/              # 📦 Cloud Function 1 - Collecte des données
│   ├── main.py                   # Point d'entrée
│   ├── extract.py                # Extraction (Custom Search API)
│   ├── transform.py              # Nettoyage
│   ├── load.py                   # Stockage Cloud Storage
│   └── requirements.txt
│
├── agent-fiscal/                 # 📦 Cloud Function 2 - Réponses fiscales
│   ├── main.py                   # Point d'entrée
│   ├── agent_fiscal_v2.py        # Recherche sémantique + Gemini
│   └── requirements.txt
│
├── Agent-client/                 # 📦 Cloud Function 3 - Orchestrateur
│   ├── main.py                   # Point d'entrée
│   ├── agent_client.py           # Classification et routage
│   └── requirements.txt
│
├── GUIDE_DEPLOIEMENT_SEPARE.md   # 📖 Guide de déploiement complet
├── PIPELINE_COMPLETE.md          # 📊 Architecture détaillée
└── README.md                     # 📄 Ce fichier
```

## 🏗️ Architecture

```
┌─────────────┐
│ Utilisateur │
└──────┬──────┘
       │ Question
       ▼
┌──────────────────┐
│ Agent Client     │ ← Classification avec Gemini
│ (Orchestrateur)  │
└──────┬───────────┘
       │ Route vers agent spécialisé
       ▼
┌──────────────────┐
│ Agent Fiscal     │ ← Recherche sémantique (embeddings)
│ (Spécialisé)     │   + Génération réponse (Gemini)
└──────┬───────────┘
       │ Charge documents depuis
       ▼
┌──────────────────┐
│ Cloud Storage    │ ← Documents JSON complets
│ (documents/)     │
└──────────────────┘
```

## 💾 Stockage des Données

- **Firestore** : Configuration des sources à surveiller (URLs, mots-clés)
- **Cloud Storage** : Documents fiscaux complets au format JSON


## 🚀 Déploiement Rapide

### Prérequis
```bash
gcloud config set project agent-gcp-f6005
```

### 1. Pipeline de Veille (Collecte des documents)

```bash
cd pipeline-veille

gcloud functions deploy surveiller-sites ^
  --gen2 --runtime=python311 --region=us-west1 ^
  --source=. --entry-point=surveiller_sites ^
  --trigger-http --allow-unauthenticated ^
  --memory=1GB --timeout=540s ^
  --set-env-vars=PROJECT_ID=agent-gcp-f6005,BUCKET_NAME=documents-fiscaux-bucket
```

### 2. Agent Fiscal (Réponses intelligentes)

```bash
cd ..\agent-fiscal

gcloud functions deploy agent-fiscal-v2 ^
  --gen2 --runtime=python311 --region=us-west1 ^
  --source=. --entry-point=agent_fiscal ^
  --trigger-http --allow-unauthenticated ^
  --memory=512MB --timeout=60s ^
  --set-env-vars=PROJECT_ID=agent-gcp-f6005,BUCKET_NAME=documents-fiscaux-bucket
```

### 3. Agent Client (Orchestrateur)

```bash
cd ..\Agent-client

gcloud functions deploy agent-client ^
  --gen2 --runtime=python311 --region=us-west1 ^
  --source=. --entry-point=agent_client ^
  --trigger-http --allow-unauthenticated ^
  --memory=256MB --timeout=30s ^
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

## 🔧 Configuration Initiale

### 1. Créer le bucket Cloud Storage
```bash
gsutil mb -l us-west1 gs://documents-fiscaux-bucket
```

### 2. Ajouter les sources à surveiller
```bash
python ajouter_sources_firestore.py
```

### 3. Lancer la première collecte
```bash
curl -X POST https://us-west1-agent-gcp-f6005.cloudfunctions.net/surveiller-sites
```

## ⚡ Commandes Utiles

```bash
# Voir les logs du pipeline
gcloud functions logs read surveiller-sites --region=us-west1 --limit=50

# Voir les logs de l'agent fiscal
gcloud functions logs read agent-fiscal-v2 --region=us-west1 --limit=50

# Voir les logs de l'agent client
gcloud functions logs read agent-client --region=us-west1 --limit=50

# Lister vos fonctions
gcloud functions list --region=us-west1

# Vérifier le contenu du bucket
gsutil ls gs://documents-fiscaux-bucket/documents/
```

## 🧪 Test de l'Agent

```bash
curl -X POST https://us-west1-agent-gcp-f6005.cloudfunctions.net/agent-client ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"C'est quoi la TVA ?\"}"
```

## 📖 Documentation Complète

- **GUIDE_DEPLOIEMENT_SEPARE.md** : Instructions détaillées de déploiement
- **PIPELINE_COMPLETE.md** : Architecture et flux de données complets

---

**Prêt pour le déploiement ! 🎉**

