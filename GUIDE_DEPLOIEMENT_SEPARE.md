# Guide de Déploiement - Structure Séparée

Ce guide explique comment déployer les deux Cloud Functions à partir de cette structure de dossiers séparés.

## 📁 Structure des Dossiers

```
deploiement-veille/
│
├── pipeline-veille/              # Dossier 1 : Pipeline ETL
│   ├── pipeline.py               # Point d'entrée : surveiller_sites
│   ├── extract.py                # Module d'extraction
│   ├── transform.py              # Module de transformation
│   ├── load.py                   # Module de chargement
│   └── requirements.txt          # Dépendances du pipeline
│
├── agent-fiscal/                 # Dossier 2 : Agent conversationnel
│   ├── agent_fiscal_v2.py        # Point d'entrée : agent_fiscal
│   └── requirements.txt          # Dépendances de l'agent
│
└── GUIDE_DEPLOIEMENT_SEPARE.md   # Ce fichier
```

---

## 🚀 Déploiement

### Prérequis

```bash
# Configurer votre projet
gcloud config set project agent-gcp-f6005

# Vérifier la configuration
gcloud config get-value project
```

---

## 1️⃣ Déployer le Pipeline de Veille

### Commande de Déploiement

```bash
cd deploiement-veille/pipeline-veille

gcloud functions deploy surveiller-sites \
  --gen2 \
  --runtime=python311 \
  --region=us-west1 \
  --source=. \
  --entry-point=surveiller_sites \
  --trigger-http \
  --allow-unauthenticated \
  --memory=1GB \
  --timeout=540s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

### Paramètres Expliqués

- `--source=.` : Utilise le dossier courant (pipeline-veille)
- `--entry-point=surveiller_sites` : Fonction à appeler dans pipeline.py
- `--memory=1GB` : Mémoire nécessaire pour le scraping
- `--timeout=540s` : 9 minutes max (scraping peut être long)

### Vérification

```bash
# Récupérer l'URL de la fonction
gcloud functions describe surveiller-sites \
  --region=us-west1 \
  --gen2 \
  --format='value(serviceConfig.uri)'

# Tester
curl -X POST "https://surveiller-sites-XXX.us-west1.run.app"
```

---

## 2️⃣ Déployer l'Agent Fiscal

### Commande de Déploiement

```bash
cd deploiement-veille/agent-fiscal

gcloud functions deploy agent-fiscal-v2 \
  --gen2 \
  --runtime=python311 \
  --region=us-west1 \
  --source=. \
  --entry-point=agent_fiscal \
  --trigger-http \
  --allow-unauthenticated \
  --memory=512MB \
  --timeout=60s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

### Paramètres Expliqués

- `--source=.` : Utilise le dossier courant (agent-fiscal)
- `--entry-point=agent_fiscal` : Fonction à appeler dans agent_fiscal_v2.py
- `--memory=512MB` : Mémoire suffisante pour l'agent
- `--timeout=60s` : 1 minute max pour répondre

### Vérification

```bash
# Récupérer l'URL de la fonction
gcloud functions describe agent-fiscal-v2 \
  --region=us-west1 \
  --gen2 \
  --format='value(serviceConfig.uri)'

# Tester
curl -X POST "https://agent-fiscal-v2-XXX.us-west1.run.app" \
  -H "Content-Type: application/json" \
  -d '{"question": "Quels sont les taux de TVA en France ?"}'
```

---

## 📊 Workflow Complet

### Étape par Étape

```bash
# 1. Aller dans le dossier du pipeline
cd deploiement-veille/pipeline-veille

# 2. Déployer le pipeline
gcloud functions deploy surveiller-sites \
  --gen2 --runtime=python311 --region=us-west1 \
  --source=. --entry-point=surveiller_sites \
  --trigger-http --allow-unauthenticated \
  --memory=1GB --timeout=540s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005

# 3. Attendre le déploiement (2-3 minutes)

# 4. Aller dans le dossier de l'agent
cd ../agent-fiscal

# 5. Déployer l'agent
gcloud functions deploy agent-fiscal-v2 \
  --gen2 --runtime=python311 --region=us-west1 \
  --source=. --entry-point=agent_fiscal \
  --trigger-http --allow-unauthenticated \
  --memory=512MB --timeout=60s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005

# 6. Attendre le déploiement (2-3 minutes)

# 7. Tester le pipeline
curl -X POST "$(gcloud functions describe surveiller-sites \
  --region=us-west1 --gen2 --format='value(serviceConfig.uri)')"

# 8. Tester l'agent
curl -X POST "$(gcloud functions describe agent-fiscal-v2 \
  --region=us-west1 --gen2 --format='value(serviceConfig.uri)')" \
  -H "Content-Type: application/json" \
  -d '{"question": "C'\''est quoi la TVA ?"}'
```

---

## 🔄 Mise à Jour

### Pour mettre à jour le pipeline

```bash
cd deploiement-veille/pipeline-veille

# Modifier les fichiers si nécessaire
# Puis redéployer avec la même commande
gcloud functions deploy surveiller-sites \
  --gen2 --runtime=python311 --region=us-west1 \
  --source=. --entry-point=surveiller_sites \
  --trigger-http --allow-unauthenticated \
  --memory=1GB --timeout=540s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

### Pour mettre à jour l'agent

```bash
cd deploiement-veille/agent-fiscal

# Modifier agent_fiscal_v2.py si nécessaire
# Puis redéployer avec la même commande
gcloud functions deploy agent-fiscal-v2 \
  --gen2 --runtime=python311 --region=us-west1 \
  --source=. --entry-point=agent_fiscal \
  --trigger-http --allow-unauthenticated \
  --memory=512MB --timeout=60s \
  --set-env-vars=PROJECT_ID=agent-gcp-f6005
```

---

## 📦 Upload dans Cloud Shell

### Méthode 1 : Upload via l'interface

1. Ouvrez Google Cloud Shell
2. Cliquez sur le bouton **"Upload"** (⋮ > Upload)
3. Sélectionnez le dossier `deploiement-veille` complet
4. Attendez la fin de l'upload
5. Suivez les commandes de déploiement ci-dessus

### Méthode 2 : Via Cloud Storage (pour gros fichiers)

```bash
# Sur votre machine locale
gsutil -m cp -r deploiement-veille gs://VOTRE_BUCKET/

# Dans Cloud Shell
gsutil -m cp -r gs://VOTRE_BUCKET/deploiement-veille .
```

---

## ✅ Checklist de Déploiement

- [ ] Projet GCP configuré (`gcloud config set project`)
- [ ] APIs activées (Cloud Functions, Firestore, Vertex AI)
- [ ] Dossier `pipeline-veille` uploadé
- [ ] Pipeline déployé et testé
- [ ] Dossier `agent-fiscal` uploadé
- [ ] Agent déployé et testé
- [ ] Sources ajoutées dans Firestore (via script)
- [ ] Pipeline exécuté pour créer les chunks
- [ ] Frontend connecté à l'agent

---

## 🐛 Dépannage

### Erreur : "No such file or directory"

**Cause :** Vous n'êtes pas dans le bon dossier.

**Solution :**
```bash
# Vérifier où vous êtes
pwd

# Aller dans le bon dossier
cd deploiement-veille/pipeline-veille  # ou agent-fiscal
```

### Erreur : "Module not found"

**Cause :** Le fichier `requirements.txt` n'est pas dans le même dossier.

**Solution :**
```bash
# Vérifier la présence du fichier
ls -la

# Vous devez voir :
# - pipeline.py (ou agent_fiscal_v2.py)
# - requirements.txt
# - extract.py, transform.py, load.py (pour le pipeline)
```

### Erreur : "Entry point not found"

**Cause :** Le nom de la fonction dans `--entry-point` ne correspond pas.

**Solution :**
- Pour le pipeline : `--entry-point=surveiller_sites` (fonction dans pipeline.py)
- Pour l'agent : `--entry-point=agent_fiscal` (fonction dans agent_fiscal_v2.py)

---

## 📝 Notes Importantes

### Pourquoi Deux Dossiers Séparés ?

Chaque Cloud Function :
- A son propre **point d'entrée** (fonction à appeler)
- A ses propres **dépendances** (requirements.txt)
- Est **déployée indépendamment**
- Peut être **mise à jour séparément**

### Avantages de Cette Structure

✅ **Clarté** : Chaque fonction a son propre dossier  
✅ **Indépendance** : Modifier le pipeline n'affecte pas l'agent  
✅ **Déploiement** : Déployer une fonction ne redéploie pas l'autre  
✅ **Maintenance** : Plus facile de savoir quel code appartient à quelle fonction  

---

**Temps total de déploiement :** ~10 minutes (5 min par fonction)

**Besoin d'aide ?** Consultez les logs avec :
```bash
gcloud functions logs read NOM_FONCTION --region=us-west1 --gen2 --limit=50
```

