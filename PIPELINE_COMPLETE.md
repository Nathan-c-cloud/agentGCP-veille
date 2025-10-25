# 🚀 PIPELINE COMPLÈTE DU SYSTÈME DE VEILLE RÉGLEMENTAIRE

## Vue d'ensemble
Votre système est une **architecture multi-agents intelligente** pour la veille réglementaire fiscale avec **recherche sémantique par embeddings**.

---

## 📊 ARCHITECTURE GLOBALE

```
┌─────────────────────────────────────────────────────────────────┐
│                    UTILISATEUR (Frontend)                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ Question
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              🧠 AGENT CLIENT (Orchestrateur)                     │
│  - Classifie la question avec Gemini                            │
│  - Route vers l'agent spécialisé approprié                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
        ┌──────────────────┐    ┌──────────────────┐
        │ 💼 AGENT FISCAL  │    │ 📊 AGENT COMPTA  │
        │    (Actif)       │    │  (À venir)       │
        └──────────────────┘    └──────────────────┘
```

---

## 🔄 PARTIE 1 : PIPELINE ETL (Collecte des données)

### **Déclencheur** : Cloud Function `surveiller-sites` (exécution périodique ou manuelle)

### **ÉTAPE 1 : EXTRACT** (`extract.py`)
**🎯 Objectif** : Collecter les documents réglementaires depuis le web

**Méthode** : **Custom Search JSON API** (remplace le scraping classique)

**Comment ça marche** :
1. Lit les sources à surveiller depuis **Firestore** (collection `sources_a_surveiller`)
2. Pour chaque source (ex: TVA, IS, CFE) :
   - Utilise les **keywords** définis (ex: "TVA déclaration 2025")
   - Appelle l'API Custom Search avec ces mots-clés
   - Restreint la recherche aux sites officiels (service-public.fr, impots.gouv.fr)
3. Retourne des documents structurés avec :
   ```json
   {
     "titre": "TVA - Déclaration",
     "contenu_brut": "La TVA est...",
     "source_url": "https://...",
     "hostname": "service-public.fr",
     "methode_extraction": "custom_search_api"
   }
   ```

**✅ Avantages** :
- Plus robuste que le scraping (pas de problème de structure HTML)
- Respecte les quotas API (100 requêtes/jour gratuites)
- Résultats toujours à jour

---

### **ÉTAPE 2 : TRANSFORM** (`transform.py`)
**🎯 Objectif** : Nettoyer et préparer les documents

**Comment ça marche** :
1. Reçoit les documents bruts de l'extraction
2. **Nettoie le texte** :
   - Supprime espaces multiples
   - Retire lignes vides excessives
   - Normalise les sauts de ligne
3. **Génère un ID unique** pour chaque document (ex: "F23570")
4. **Garde le document complet** (pas de chunking)
5. Retourne un document structuré :
   ```json
   {
     "document_id": "F23570",
     "contenu": "Texte propre complet...",
     "titre_source": "TVA - Déclaration",
     "source_url": "https://...",
     "taille_caracteres": 5432
   }
   ```

**✅ Pourquoi pas de chunking** : La recherche sémantique fonctionne sur documents complets

---

### **ÉTAPE 3 : LOAD** (`load.py`)
**🎯 Objectif** : Stocker les documents dans Cloud Storage

**Comment ça marche** :
1. Prend les documents transformés
2. Les convertit en **JSON complet** (métadonnées + contenu)
3. Les stocke dans **Cloud Storage** :
   - Bucket : `documents-fiscaux-bucket`
   - Chemin : `documents/{document_id}.json`
   - Exemple : `gs://documents-fiscaux-bucket/documents/F23570.json`

**Structure JSON stockée** :
```json
{
  "document_id": "F23570",
  "contenu": "La TVA est un impôt...",
  "titre_source": "TVA - Déclaration",
  "source_url": "https://entreprendre.service-public.fr/...",
  "hostname": "service-public.fr",
  "taille_caracteres": 5432,
  "type": "local"
}
```

**✅ Pourquoi Cloud Storage et pas Firestore** :
- **Cloud Storage** : Documents longs (contenu complet), stockage économique
- **Firestore** : Uniquement config des sources à surveiller

---

## 💬 PARTIE 2 : AGENT CONVERSATIONNEL (Réponse aux questions)

### **Point d'entrée** : Cloud Function `agent-client`

### **FLUX DE TRAITEMENT** :

```
Question utilisateur
        ↓
┌──────────────────────────────────────────┐
│  1. CLASSIFICATION (agent_client.py)     │
│     - Gemini analyse la question         │
│     - Détermine l'agent cible            │
│     - Exemples :                         │
│       * "TVA" → agent-fiscal             │
│       * "Bilan" → agent-comptabilite     │
└──────────────────┬───────────────────────┘
                   ↓
┌──────────────────────────────────────────┐
│  2. ROUTAGE                              │
│     - Appel HTTP vers l'agent choisi     │
└──────────────────┬───────────────────────┘
                   ↓
┌──────────────────────────────────────────┐
│  3. AGENT FISCAL (agent_fiscal_v2.py)    │
│                                          │
│  A. RECHERCHE SÉMANTIQUE PURE            │
│     ┌──────────────────────────────┐    │
│     │ 1. Génère embedding question │    │
│     │    avec text-embedding-004   │    │
│     └──────────────────────────────┘    │
│                                          │
│     ┌──────────────────────────────┐    │
│     │ 2. Charge tous les documents │    │
│     │    depuis Cloud Storage      │    │
│     │    (cache intelligent 1h)    │    │
│     └──────────────────────────────┘    │
│                                          │
│     ┌──────────────────────────────┐    │
│     │ 3. Pour chaque document:     │    │
│     │    - Génère embedding        │    │
│     │      (titre x3 + contenu)    │    │
│     │    - Calcule similarité      │    │
│     │      cosinus                 │    │
│     │    - Filtre si score ≥ 0.3   │    │
│     └──────────────────────────────┘    │
│                                          │
│     ┌──────────────────────────────┐    │
│     │ 4. Trie par score            │    │
│     │    Top 3 documents           │    │
│     └──────────────────────────────┘    │
│                                          │
│  B. GÉNÉRATION RÉPONSE                   │
│     - Contexte = top 3 documents         │
│     - Gemini 2.0 Flash génère            │
│     - Format Markdown structuré          │
│     - Max 150 mots                       │
└──────────────────┬───────────────────────┘
                   ↓
┌──────────────────────────────────────────┐
│  4. RÉPONSE FINALE                       │
│     {                                    │
│       "question": "...",                 │
│       "reponse": "## Titre...",          │
│       "sources": [...],                  │
│       "methode_recherche": "semantique", │
│       "score_moyen": 0.75,               │
│       "meilleur_score": 0.89             │
│     }                                    │
└──────────────────────────────────────────┘
```

---

## 📦 STOCKAGE DES DONNÉES

### **Firestore** (Base de données NoSQL)
```
Collection: sources_a_surveiller
├── Document: tva_taux_reduits
│   ├── url_base: "https://..."
│   ├── keywords: ["TVA", "taux", "réduits"]
│   ├── categorie: "fiscalite_tva"
│   └── actif: true
├── Document: impot_societes
│   └── ...
```
**Usage** : Configuration des sources à surveiller pour le pipeline

---

### **Cloud Storage** (Stockage d'objets)
```
Bucket: documents-fiscaux-bucket
└── documents/
    ├── F23570.json  (TVA - Déclaration)
    ├── F23567.json  (TVA - Taux réduits)
    ├── F23575.json  (Impôt sociétés)
    └── ...
```
**Usage** : Documents fiscaux complets (contenu + métadonnées)

---

## 🔍 RECHERCHE SÉMANTIQUE PAR EMBEDDINGS

### **Comment ça fonctionne** :

1. **Embeddings vectoriels** : 
   - Chaque texte (question + documents) est converti en vecteur de nombres
   - Le modèle `text-embedding-004` comprend le SENS du texte
   - Les textes similaires ont des vecteurs proches

2. **Similarité cosinus** :
   - Mesure l'angle entre deux vecteurs
   - Score entre 0 (pas similaire) et 1 (identique)
   - Seuil minimum : 0.3

3. **Stratégie de pondération** :
   - Titre répété 3 fois pour donner plus de poids
   - + Début du contenu (1000 caractères)
   - Résultat : les titres pertinents sont favorisés

### **Avantages** :
- ✅ Comprend les synonymes ("IS" = "Impôt sur les Sociétés")
- ✅ Comprend les questions mal formulées ("qw" → "quoi")
- ✅ Pas besoin de mots-clés exacts
- ✅ Trouve les documents par le sens, pas juste par les mots

### **Cache intelligent** :
- Documents : 1 heure en mémoire
- Embeddings : Illimité en mémoire (pendant l'exécution)
- Réduit les appels API et améliore la vitesse

---
```json
{
  "document_id": "F23570",
  "contenu": "La TVA est un impôt...",
  "titre_source": "TVA - Déclaration",
  "source_url": "https://entreprendre.service-public.fr/...",
  "hostname": "service-public.fr",
  "taille_caracteres": 5432,
  "type": "local"
}
```

**✅ Pourquoi Cloud Storage et pas Firestore** :
- **Cloud Storage** : Documents longs (contenu complet)
- **Firestore** : Uniquement config des sources à surveiller

---

## 💬 PARTIE 2 : AGENT CONVERSATIONNEL (Réponse aux questions)

### **Point d'entrée** : Cloud Function `agent-client`

### **FLUX DE TRAITEMENT** :

```
Question utilisateur
        ↓
┌──────────────────────────────────────────┐
│  1. CLASSIFICATION (agent_client.py)     │
│     - Gemini analyse la question         │
│     - Détermine l'agent cible            │
│     - Exemples :                         │
│       * "TVA" → agent-fiscal             │
│       * "Bilan" → agent-comptabilite     │
└──────────────────┬───────────────────────┘
                   ↓
┌──────────────────────────────────────────┐
│  2. ROUTAGE                              │
│     - Appel HTTP vers l'agent choisi     │
└──────────────────┬───────────────────────┘
                   ↓
┌──────────────────────────────────────────┐
│  3. AGENT FISCAL (agent_fiscal_v2.py)    │
│                                          │
│  A. RECHERCHE HYBRIDE                    │
│     ┌──────────────────────────────┐    │
│     │ Recherche 1: Cloud Storage   │    │
│     │ - Charge tous les JSON       │    │
│     │ - Extrait mots-clés          │    │
│     │ - Score de pertinence        │    │
│     └──────────────────────────────┘    │
│                                          │
│     ┌──────────────────────────────┐    │
│     │ Recherche 2: Google Search   │    │
│     │ - Complète si pas assez      │    │
│     │ - 2 résultats max            │    │
│     └──────────────────────────────┘    │
│                                          │
│     ┌──────────────────────────────┐    │
│     │ Recherche 3: Vertex AI (opt) │    │
│     │ - Recherche sémantique       │    │
│     │ - Si activé                  │    │
│     └──────────────────────────────┘    │
│                                          │
│  B. GÉNÉRATION RÉPONSE                   │
│     - Contexte = top 4 documents         │
│     - Gemini génère réponse structurée   │
│     - Format Markdown court              │
└──────────────────┬───────────────────────┘
                   ↓
┌──────────────────────────────────────────┐
│  4. RÉPONSE FINALE                       │
│     {                                    │
│       "question": "...",                 │
│       "reponse": "## Titre...",          │
│       "sources": [...],                  │
│       "agent_utilise": "fiscalite"       │
│     }                                    │
└──────────────────────────────────────────┘
```

---

## 📦 STOCKAGE DES DONNÉES

### **Firestore** (Base de données NoSQL)
```
Collection: sources_a_surveiller
├── Document: tva_taux_reduits
│   ├── url_base: "https://..."
│   ├── keywords: ["TVA", "taux", "réduits"]
│   ├── categorie: "fiscalite_tva"
│   └── actif: true
├── Document: impot_societes
│   └── ...
```
**Usage** : Configuration des sources à surveiller pour le pipeline

---

### **Cloud Storage** (Stockage d'objets)
```
Bucket: documents-fiscaux-bucket
└── documents/
    ├── F23570.json  (TVA - Déclaration)
    ├── F23567.json  (TVA - Taux réduits)
    ├── F23575.json  (Impôt sociétés)
    └── ...
```
**Usage** : Documents fiscaux complets (contenu + métadonnées)

---

## 🎯 POINTS CLÉS DE VOTRE ARCHITECTURE

### ✅ **Ce qui est implémenté** :
1. **Séparation des responsabilités** : ETL découplé de l'agent conversationnel
2. **Stockage optimal** : 
   - Firestore = Config des sources
   - Cloud Storage = Contenu des documents
3. **Recherche sémantique pure** : Embeddings vectoriels (pas de mots-clés)
4. **Architecture multi-agents** : Agent client route intelligemment
5. **API robuste** : Custom Search API remplace le scraping fragile
6. **Cache intelligent** : Réduit les appels API et améliore la vitesse

### 🔄 **Flux complet résumé** :

```
1. CONFIGURATION (Manuel, une fois)
   └─> Ajouter sources dans Firestore (ajouter_sources_firestore.py)

2. COLLECTE (Périodique ou manuel)
   └─> Pipeline ETL → Custom Search API → Nettoie → Stocke JSON dans Cloud Storage

3. INTERROGATION (Temps réel)
   └─> Question → Agent Client → Agent Fiscal → Recherche sémantique → Gemini → Réponse
```

---

## 🚀 DÉPLOIEMENT

### **Cloud Functions déployées** :
1. **surveiller-sites** (Pipeline ETL)
   - Trigger : HTTP
   - Rôle : Collecte et stockage des documents
   - Mémoire : 1GB
   - Timeout : 540s (9 min)

2. **agent-client** (Orchestrateur)
   - Trigger : HTTP
   - Rôle : Classification et routage
   - Mémoire : 256MB
   - Timeout : 30s

3. **agent-fiscal-v2** (Agent spécialisé)
   - Trigger : HTTP
   - Rôle : Réponses fiscales intelligentes
   - Mémoire : 512MB
   - Timeout : 60s

---

## 📊 RÉSUMÉ EN CHIFFRES

- **3 Cloud Functions** déployées
- **2 bases de données** (Firestore + Cloud Storage)
- **1 méthode de recherche** : Sémantique par embeddings
- **2 modèles IA** : Gemini 2.0 Flash + text-embedding-004
- **10+ sources fiscales** surveillées
- **Format JSON** pour tous les documents
- **Documents complets** (pas de chunking)
- **Cache 1 heure** pour les documents
- **Seuil similarité** : 0.3 (30%)
- **Top 3 documents** par requête

---

## 🎓 ANALOGIE SIMPLE

Votre système c'est comme une **bibliothèque intelligente** :

1. **Le bibliothécaire collecteur** (Pipeline ETL) :
   - Va chercher les nouveaux livres sur internet (Custom Search)
   - Les nettoie et les étiquette (Transform)
   - Les range dans les étagères (Cloud Storage)

2. **Le réceptionniste** (Agent Client) :
   - Écoute votre question
   - Vous dirige vers le bon expert (Agent Fiscal, Agent Compta...)

3. **L'expert fiscal** (Agent Fiscal) :
   - Comprend vraiment votre question (Embeddings)
   - Trouve les livres les plus pertinents (Similarité cosinus)
   - Vous explique la réponse de façon claire (Gemini)

---

## 💰 COÛTS ESTIMÉS

### **Gratuit / Très faible** :
- Cloud Storage : ~0.02$/GB/mois (quelques MB → presque gratuit)
- Custom Search API : 100 requêtes/jour gratuites
- Firestore : Quota gratuit largement suffisant

### **Payant** :
- Vertex AI (Gemini) : ~0.00025$/1000 caractères
- Embeddings : ~0.00001$/1000 caractères
- Cloud Functions : Temps d'exécution (très faible)

**Estimation mensuelle** : < 5€/mois pour usage normal

---

## 🔧 MAINTENANCE

### **Actions périodiques** :
- ✅ Lancer le pipeline : 1x/semaine ou au besoin
- ✅ Vérifier les logs : Si problème
- ✅ Ajouter nouvelles sources : Au besoin

### **Optimisations possibles** :
- Augmenter le cache (actuellement 1h)
- Ajuster le seuil de similarité (actuellement 0.3)
- Ajouter plus de documents (top 3 → top 5)
- Automatiser le pipeline avec Cloud Scheduler

---

**🎉 Votre système est prêt pour la production !**

2. **Le bibliothécaire accueil** (Agent Client) :
   - Écoute votre question
   - Vous dirige vers le bon expert

3. **L'expert fiscal** (Agent Fiscal) :
   - Cherche dans les étagères (Cloud Storage)
   - Complète avec Google si besoin
   - Vous donne une réponse claire et sourcée

---

## ✨ FORCES DE VOTRE ARCHITECTURE

1. **Scalable** : Ajout facile de nouveaux agents
2. **Robuste** : API officielle (pas de scraping fragile)
3. **Intelligent** : Recherche hybride + IA générative
4. **Structuré** : ETL propre avec séparation des concerns
5. **Économique** : Stockage JSON pas cher, Gemini rapide

---

## 🔧 AMÉLIORATION À VENIR : AGENT FISCAL PLUS INTELLIGENT

### Problèmes actuels identifiés :
1. ❌ Réponses trop longues et non structurées
2. ❌ Recherche par mots-clés trop basique
3. ❌ Pas assez intelligent dans le choix des documents
4. ❌ Prompt système trop verbeux

### Améliorations prévues :
1. ✅ **Recherche sémantique** avec embeddings
2. ✅ **Prompt optimisé** pour réponses courtes
3. ✅ **Scoring intelligent** des documents
4. ✅ **Cache intelligent** pour performances
5. ✅ **Validation des réponses** avant envoi

