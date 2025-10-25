# GUIDE DE CONFIGURATION - CUSTOM SEARCH API (PIPELINE)
==================================================

Ce guide vous aide à configurer Google Custom Search API pour le **pipeline de collecte**
de documents fiscaux.

⚠️ **IMPORTANT** : L'agent fiscal utilise maintenant la **recherche sémantique pure** 
et ne nécessite PAS cette API pour fonctionner !

---

## QUAND UTILISER CUSTOM SEARCH API ?

**✅ OUI** : Pour le **pipeline de collecte** (`surveiller-sites`)
- Collecte automatique de nouveaux documents
- Remplace le scraping web fragile
- 100 requêtes/jour gratuites

**❌ NON** : Pour l'**agent fiscal** (`agent-fiscal-v2`)
- L'agent utilise la recherche sémantique par embeddings
- Charge les documents depuis Cloud Storage
- Pas besoin d'API externe

---

## ÉTAPE 1 : CRÉER UNE CLÉ API GOOGLE

1. Allez sur : https://console.cloud.google.com/apis/credentials
2. Sélectionnez votre projet : `agent-gcp-f6005`
3. Cliquez sur "Créer des identifiants" > "Clé API"
4. Copiez la clé générée (format: AIzaSy...)
5. (Recommandé) Restreignez la clé à l'API "Custom Search API"

6. Activez l'API Custom Search :
   - Allez sur : https://console.cloud.google.com/apis/library
   - Recherchez "Custom Search API"
   - Cliquez sur "Activer"

---

## ÉTAPE 2 : CRÉER UN MOTEUR DE RECHERCHE PERSONNALISÉ

1. Allez sur : https://programmablesearchengine.google.com/controlpanel/all
2. Cliquez sur "Ajouter" pour créer un nouveau moteur
3. Configuration :
   - Sites à explorer : 
     * *.service-public.fr
     * *.impots.gouv.fr
     * *.economie.gouv.fr
     * *.legifrance.gouv.fr
   - Langue : Français
   - Nom : "Recherche Fiscale France"
   
4. Options avancées :
   - **Ne pas** activer "Rechercher sur l'ensemble du Web"
   - Gardez "Résultats d'images" désactivé
   
5. Copiez l'ID du moteur de recherche (Search Engine ID)
   Format: 0123456789abcdef:xxxxxxxxx

---

## ÉTAPE 3 : CONFIGURER LE PIPELINE

### Option A - Déploiement du pipeline avec Custom Search :

```cmd
cd pipeline-veille

gcloud functions deploy surveiller-sites ^
  --gen2 ^
  --runtime=python311 ^
  --region=us-west1 ^
  --source=. ^
  --entry-point=surveiller_sites ^
  --trigger-http ^
  --allow-unauthenticated ^
  --memory=1GB ^
  --timeout=540s ^
  --set-env-vars=PROJECT_ID=agent-gcp-f6005,BUCKET_NAME=documents-fiscaux-bucket,GOOGLE_API_KEY=VOTRE_CLE_API,SEARCH_ENGINE_ID=VOTRE_SEARCH_ENGINE_ID
```

### Option B - Mise à jour d'une fonction existante :

```cmd
gcloud functions deploy surveiller-sites ^
  --region=us-west1 ^
  --update-env-vars=GOOGLE_API_KEY=VOTRE_CLE_API,SEARCH_ENGINE_ID=VOTRE_SEARCH_ENGINE_ID
```

### Option C - Variables d'environnement locales (test) :

```cmd
set GOOGLE_API_KEY=VOTRE_CLE_API
set SEARCH_ENGINE_ID=VOTRE_SEARCH_ENGINE_ID
set PROJECT_ID=agent-gcp-f6005
set BUCKET_NAME=documents-fiscaux-bucket
```

---

## ÉTAPE 4 : CONFIGURATION INITIALE

### 1. Créer le bucket Cloud Storage

```cmd
gsutil mb -l us-west1 gs://documents-fiscaux-bucket
```

### 2. Ajouter les sources à surveiller dans Firestore

```cmd
python ajouter_sources_firestore.py
```

### 3. Lancer la première collecte

```cmd
curl -X POST https://us-west1-agent-gcp-f6005.cloudfunctions.net/surveiller-sites
```

### 4. Vérifier que les fichiers sont créés

```cmd
gsutil ls gs://documents-fiscaux-bucket/documents/
```

Vous devriez voir :
```
gs://documents-fiscaux-bucket/documents/F23570.json
gs://documents-fiscaux-bucket/documents/F23567.json
...
```

---

## ÉTAPE 5 : TESTER

### 1. Tester le pipeline (collecte)

```cmd
curl -X POST https://us-west1-agent-gcp-f6005.cloudfunctions.net/surveiller-sites
```

### 2. Tester l'agent fiscal (réponses)

```cmd
curl -X POST https://us-west1-agent-gcp-f6005.cloudfunctions.net/agent-client ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"C'est quoi la TVA ?\"}"
```

### 3. Vérifier les logs

```cmd
# Logs du pipeline
gcloud functions logs read surveiller-sites --region=us-west1 --limit=50

# Logs de l'agent
gcloud functions logs read agent-fiscal-v2 --region=us-west1 --limit=50
```

---

## ARCHITECTURE ACTUELLE

```
┌─────────────────────────────────────────┐
│  CUSTOM SEARCH API                      │
│  (Utilisée UNIQUEMENT par le pipeline)  │
└───────────────┬─────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  PIPELINE (surveiller-sites)            │
│  - Extract: Custom Search API           │
│  - Transform: Nettoie le texte          │
│  - Load: Stocke dans Cloud Storage      │
└───────────────┬─────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  CLOUD STORAGE                          │
│  documents-fiscaux-bucket/documents/    │
└───────────────┬─────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  AGENT FISCAL (agent-fiscal-v2)         │
│  - Recherche sémantique par embeddings  │
│  - Pas besoin de Custom Search API      │
│  - Utilise les documents stockés        │
└─────────────────────────────────────────┘
```

---

## COÛTS ET LIMITES

### Google Custom Search API :
- **GRATUIT** : 100 requêtes/jour
- **PAYANT** : 5$ pour 1000 requêtes supplémentaires
- **Limite** : 10 000 requêtes/jour maximum

### Cloud Storage :
- **Stockage** : ~0.02$/GB/mois (région us-west1)
- **Opérations de lecture** : Très faible coût
- **Egress** : Gratuit dans la même région

### Vertex AI (pour l'agent) :
- **Gemini 2.0 Flash** : ~0.00025$/1000 caractères
- **text-embedding-004** : ~0.00001$/1000 caractères

**Estimation totale** : < 5€/mois pour usage normal

---

## DÉPANNAGE

### Problème : "API not enabled"
**Solution** : Activez l'API Custom Search dans la console GCP

### Problème : "Invalid API key"
**Solution** : Vérifiez que la clé API n'a pas de restrictions incompatibles

### Problème : "Quota exceeded"
**Solution** : 
- Vérifiez vos quotas (100 requêtes/jour gratuites)
- Réduisez le nombre de sources surveillées
- Ou passez à un plan payant

### Problème : Le pipeline ne collecte rien
**Solution** :
1. Vérifiez que les sources sont dans Firestore
2. Vérifiez les logs : `gcloud functions logs read surveiller-sites --region=us-west1`
3. Testez manuellement une recherche sur programmablesearchengine.google.com

### Problème : L'agent ne trouve pas de documents
**Solution** :
1. Vérifiez que le bucket existe : `gsutil ls gs://documents-fiscaux-bucket/documents/`
2. Lancez le pipeline pour collecter des documents
3. Vérifiez les logs de l'agent

---

## ALTERNATIVE : SANS CUSTOM SEARCH API

Si vous ne voulez pas utiliser Custom Search API, vous pouvez :

1. **Ajouter manuellement des documents JSON** dans Cloud Storage
2. **Utiliser un autre service de collecte**
3. **Copier des documents existants** depuis une autre source

L'agent fiscal fonctionnera tant qu'il y a des documents JSON dans le bucket !

---

**💡 CONSEIL** : Commencez avec la version gratuite (100 requêtes/jour) 
et passez au payant seulement si nécessaire.


