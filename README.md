# Structure de Déploiement - Agent Fiscal

Cette structure est prête pour le déploiement sur Google Cloud Functions.

## 📁 Contenu

```
deploiement-veille/
│
├── pipeline-veille/              # 📦 Cloud Function 1
│   ├── pipeline.py               # Point d'entrée
│   ├── extract.py
│   ├── transform.py
│   ├── load.py
│   └── requirements.txt
│
├── agent-fiscal/                 # 📦 Cloud Function 2
│   ├── agent_fiscal_v2.py        # Point d'entrée
│   └── requirements.txt
│
├── GUIDE_DEPLOIEMENT_SEPARE.md   # 📖 Guide de déploiement
└── README.md                     # 📄 Ce fichier
```

## 🚀 Déploiement Rapide

### 1. Pipeline de Veille

```bash
cd pipeline-veille

gcloud functions deploy surveiller-sites \
  --gen2 --runtime=python311 --region=us-west1 \
  --source=. --entry-point=surveiller_sites \
  --trigger-http --allow-unauthenticated \
  --memory=1GB --timeout=540s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

### 2. Agent Fiscal

```bash
cd ../agent-fiscal

gcloud functions deploy agent-fiscal-v2 \
  --gen2 --runtime=python311 --region=us-west1 \
  --source=. --entry-point=agent_fiscal \
  --trigger-http --allow-unauthenticated \
  --memory=512MB --timeout=60s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

## 📖 Documentation Complète

Consultez `GUIDE_DEPLOIEMENT_SEPARE.md` pour :
- Instructions détaillées
- Vérification et tests
- Dépannage
- Mise à jour

## ⚡ Commandes Utiles

```bash
# Voir les logs du pipeline
gcloud functions logs read surveiller-sites --region=us-west1 --gen2

# Voir les logs de l'agent
gcloud functions logs read agent-fiscal-v2 --region=us-west1 --gen2

# Lister vos fonctions
gcloud functions list --region=us-west1 --gen2
```

---

**Prêt pour le déploiement ! 🎉**

