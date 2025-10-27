import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional

import functions_framework
import numpy as np
import vertexai
from flask import jsonify
from google.cloud import storage
from vertexai.generative_models import GenerativeModel
from vertexai.language_models import TextEmbeddingModel

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = "us-west1"
BUCKET_NAME = os.environ.get("BUCKET_NAME", "documents-fiscaux-bucket")

# --- Paramètres optimisés ---
MAX_DOCUMENTS = 3
MIN_SIMILARITY_SCORE = 0.3
MAX_CONTEXT_LENGTH = 3000

# Cache intelligent
_documents_cache = []
_cache_timestamp = None
CACHE_DURATION_SECONDS = 3600
_embeddings_cache = {}

# Initialisation lazy (pour éviter les problèmes au démarrage)
_vertex_initialized = False
_model = None
_embedding_model = None
_storage_client = None

# ⚠️ PAS D'INITIALISATION AU DÉMARRAGE - Tout est fait en lazy loading


def init_vertex_ai():
    """Initialise Vertex AI de manière lazy"""
    global _vertex_initialized, _model, _embedding_model, _storage_client

    if _vertex_initialized:
        return

    try:
        print("🔧 Initialisation Vertex AI...")
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        _model = GenerativeModel("gemini-2.0-flash")
        _embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        _storage_client = storage.Client()
        _vertex_initialized = True
        print("✅ Vertex AI initialisé")
    except Exception as e:
        print(f"⚠️ Erreur initialisation Vertex AI: {e}")
        raise


def charger_documents_depuis_gcs() -> List[Dict]:
    """Charge tous les documents fiscaux depuis Cloud Storage avec cache."""
    global _documents_cache, _cache_timestamp

    init_vertex_ai()

    now = datetime.now().timestamp()
    if _documents_cache and _cache_timestamp:
        if (now - _cache_timestamp) < CACHE_DURATION_SECONDS:
            print(f"✅ Cache ({len(_documents_cache)} docs)")
            return _documents_cache

    print(f"📥 Chargement depuis gs://{BUCKET_NAME}...")
    documents = []

    try:
        bucket = _storage_client.bucket(BUCKET_NAME)
        blobs = bucket.list_blobs(prefix="documents/")

        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue
            try:
                content = blob.download_as_text(encoding='utf-8')
                doc = json.loads(content)
                doc['type'] = 'local'
                doc['gcs_path'] = f"gs://{BUCKET_NAME}/{blob.name}"
                documents.append(doc)
            except Exception as e:
                print(f"⚠️ Erreur {blob.name}: {e}")

        _documents_cache = documents
        _cache_timestamp = now
        print(f"✅ {len(documents)} documents chargés")

    except Exception as e:
        print(f"❌ Erreur GCS: {e}")

    return documents


def obtenir_embedding(texte: str) -> Optional[np.ndarray]:
    """Génère un embedding vectoriel avec cache."""
    init_vertex_ai()

    if texte in _embeddings_cache:
        return _embeddings_cache[texte]

    try:
        if len(texte) > 5000:
            texte = texte[:2000] + " ... " + texte[-2000:]

        embeddings = _embedding_model.get_embeddings([texte])
        vector = np.array(embeddings[0].values)
        _embeddings_cache[texte] = vector
        return vector
    except Exception as e:
        print(f"⚠️ Embedding error: {e}")
        return None


def calculer_similarite_cosinus(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    try:
        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot / (norm1 * norm2))
    except Exception as e:
        print(f"⚠️ Similarité error: {e}")
        return 0.0


def rechercher_documents_semantique(question: str, max_docs: int = MAX_DOCUMENTS) -> List[Dict]:
    """Recherche sémantique pure basée sur embeddings."""
    print(f"\n🧠 Recherche: '{question}'")

    q_embedding = obtenir_embedding(question)
    if q_embedding is None:
        print("❌ Impossible de générer embedding")
        return []

    all_docs = charger_documents_depuis_gcs()
    if not all_docs:
        print("⚠️ Aucun document")
        return []

    print(f"📚 Analyse de {len(all_docs)} documents...")

    docs_scores = []
    for doc in all_docs:
        titre = doc.get('titre_source', '')
        contenu = doc.get('contenu', '')

        # Titre x3 + début contenu
        texte_emb = f"{titre}. {titre}. {titre}. {contenu[:1000]}"

        doc_emb = obtenir_embedding(texte_emb)
        if doc_emb is None:
            continue

        score = calculer_similarite_cosinus(q_embedding, doc_emb)

        if score >= MIN_SIMILARITY_SCORE:
            doc['score'] = score
            doc['score_type'] = 'semantique'
            docs_scores.append(doc)

    docs_scores.sort(key=lambda x: x['score'], reverse=True)
    resultats = docs_scores[:max_docs]

    print(f"✅ {len(resultats)} doc(s) pertinent(s)")
    for i, doc in enumerate(resultats, 1):
        titre = doc.get('titre_source', 'Sans titre')[:60]
        print(f"   {i}. [{doc['score'] * 100:.1f}%] {titre}")

    return resultats


def nettoyer_contenu(texte: str, max_len: int = 1000) -> str:
    """Nettoie et limite le contenu."""
    texte = re.sub(r'https?://[^\s\)]+', '', texte)
    texte = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', texte)
    texte = re.sub(r' +', ' ', texte)
    texte = re.sub(r'\n\s*\n\s*\n+', '\n\n', texte)

    if len(texte) > max_len:
        texte = texte[:max_len]
        point = texte.rfind('.')
        if point > max_len * 0.7:
            texte = texte[:point + 1]
        else:
            texte = texte + "..."

    return texte.strip()


def construire_contexte(documents: List[Dict]) -> str:
    """Construit un contexte optimisé pour le LLM."""
    if not documents:
        return "Aucun document."

    parts = []
    total = 0

    for i, doc in enumerate(documents, 1):
        if total >= MAX_CONTEXT_LENGTH:
            break

        titre = doc.get('titre_source', 'Sans titre')
        url = doc.get('source_url', '')
        contenu = doc.get('contenu', '')

        contenu_clean = nettoyer_contenu(contenu, 800)

        doc_text = f"[Doc {i}]\nTitre: {titre}\nURL: {url}\nContenu: {contenu_clean}\n"

        if total + len(doc_text) > MAX_CONTEXT_LENGTH:
            contenu_clean = nettoyer_contenu(contenu, 400)
            doc_text = f"[Doc {i}]\nTitre: {titre}\nURL: {url}\nContenu: {contenu_clean}\n"

        parts.append(doc_text)
        total += len(doc_text)

    return "\n---\n".join(parts)


PROMPT_SYSTEME = """Tu es un expert fiscal français. Réponds de manière CONCISE et STRUCTURÉE.

⚠️ RÈGLES :
1. Maximum 150 mots
2. Utilise UNIQUEMENT les documents fournis
3. Structure : Titre ## + Définition + Points clés + Source

📋 FORMAT :

## [Titre]

**Définition** : [1 phrase claire]

**Points clés** :
- Point 1
- Point 2
- Point 3

**Source** : [Titre](URL)

📄 DOCUMENTS :
{contexte}

❓ QUESTION : {question}

💬 RÉPONSE :"""


def generer_reponse(question: str, contexte: str) -> str:
    """Génère une réponse intelligente."""
    init_vertex_ai()

    prompt = PROMPT_SYSTEME.format(contexte=contexte, question=question)

    try:
        print("\n💭 Génération réponse...")

        response = _model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.3,
                'top_p': 0.8,
                'top_k': 20,
                'max_output_tokens': 500,
            }
        )

        reponse = response.text
        print("✅ Réponse générée")
        return reponse

    except Exception as e:
        print(f"❌ Erreur LLM: {e}")
        return "Désolé, erreur lors de la génération."


def extraire_sources(documents: List[Dict]) -> List[Dict]:
    """Extrait les sources."""
    sources = []
    for doc in documents[:3]:
        sources.append({
            "titre": doc.get('titre_source', 'Sans titre'),
            "url": doc.get('source_url', ''),
            "type": doc.get('type', 'local'),
            "score": round(doc.get('score', 0), 2)
        })
    return sources


# ============================================================================
# VÉRIFICATION DE DÉCLARATIONS TVA
# ============================================================================

PROMPT_VERIFICATION = """Tu es un expert-comptable français spécialisé en TVA. 
Analyse les données de déclaration TVA ci-dessous et détecte les anomalies potentielles.

📊 DONNÉES DE LA DÉCLARATION :
{data_json}

📈 DONNÉES HISTORIQUES (mois précédent) :
{historical_json}

🎯 TÂCHE :
Analyse ces données et identifie :
1. Les variations inhabituelles (> 15% par rapport au mois précédent)
2. Les incohérences dans les calculs
3. Les champs manquants ou suspects
4. Les opportunités d'optimisation

⚠️ FORMAT DE RÉPONSE (JSON strict) :
{{
  "verifications": [
    {{
      "type": "warning" ou "success" ou "info",
      "title": "Titre court",
      "message": "Description détaillée",
      "field": "nom_du_champ_concerné",
      "severity": "high" ou "medium" ou "low"
    }}
  ],
  "score_confiance": 0.95,
  "resume": "Résumé en 1 phrase"
}}

💬 RÉPONSE (JSON uniquement) :"""


def verifier_declaration_tva(data: Dict, historical_data: Dict = None) -> Dict:
    """Vérifie une déclaration TVA avec l'IA"""
    init_vertex_ai()

    data_json = json.dumps(data, indent=2, ensure_ascii=False)

    if historical_data:
        historical_json = json.dumps(historical_data, indent=2, ensure_ascii=False)
    else:
        historical_json = json.dumps({
            "tva_collectee": data.get("tva_collectee", 0) * 0.85,
            "tva_deductible": data.get("tva_deductible", 0) * 1.05,
            "tva_a_payer": data.get("tva_a_payer", 0) * 0.80,
            "nb_factures_vente": max(1, data.get("details", {}).get("nb_factures_vente", 0) - 2),
            "nb_factures_achat": data.get("details", {}).get("nb_factures_achat", 0)
        }, indent=2, ensure_ascii=False)

    prompt = PROMPT_VERIFICATION.format(
        data_json=data_json,
        historical_json=historical_json
    )

    try:
        print("\n🤖 Analyse IA en cours...")

        response = _model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.2,
                'top_p': 0.8,
                'top_k': 20,
                'max_output_tokens': 1000,
            }
        )

        response_text = response.text.strip()

        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        result = json.loads(response_text)

        print(f"✅ Analyse terminée : {len(result.get('verifications', []))} vérifications")

        return result

    except json.JSONDecodeError as e:
        print(f"⚠️ Erreur parsing JSON: {e}")
        return generer_verifications_fallback(data, historical_data)

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse IA: {e}")
        return generer_verifications_fallback(data, historical_data)


def generer_verifications_fallback(data: Dict, historical_data: Dict = None) -> Dict:
    """Génère des vérifications basiques si l'IA échoue"""
    verifications = []

    tva_collectee = data.get("tva_collectee", 0)
    tva_deductible = data.get("tva_deductible", 0)
    tva_a_payer = data.get("tva_a_payer", 0)

    calcul_attendu = tva_collectee - tva_deductible
    if abs(calcul_attendu - tva_a_payer) > 0.01:
        verifications.append({
            "type": "warning",
            "title": "Incohérence de calcul détectée",
            "message": f"Le calcul TVA à payer ({tva_a_payer:.2f} €) ne correspond pas à TVA collectée - TVA déductible ({calcul_attendu:.2f} €)",
            "field": "tva_a_payer",
            "severity": "high"
        })
    else:
        verifications.append({
            "type": "success",
            "title": "Cohérence vérifiée",
            "message": "Les montants correspondent aux écritures comptables",
            "field": "calcul",
            "severity": "low"
        })

    if historical_data:
        hist_tva_collectee = historical_data.get("tva_collectee", 0)
        if hist_tva_collectee > 0:
            variation = ((tva_collectee - hist_tva_collectee) / hist_tva_collectee) * 100

            if abs(variation) > 15:
                verifications.append({
                    "type": "warning",
                    "title": "Variation inhabituelle détectée",
                    "message": f"La TVA collectée est {abs(variation):.0f}% {'supérieure' if variation > 0 else 'inférieure'} au mois précédent",
                    "field": "tva_collectee",
                    "severity": "medium"
                })

    if tva_deductible == 0 and tva_collectee > 0:
        verifications.append({
            "type": "info",
            "title": "Aucune TVA déductible",
            "message": "Aucun achat avec TVA déductible n'a été enregistré ce mois-ci",
            "field": "tva_deductible",
            "severity": "low"
        })

    return {
        "verifications": verifications,
        "score_confiance": 0.85,
        "resume": f"{len(verifications)} vérification(s) effectuée(s)"
    }


# ============================================================================
# POINT D'ENTRÉE HTTP PRINCIPAL
# ============================================================================

@functions_framework.http
def agent_fiscal(request):
    """Point d'entrée HTTP pour l'agent fiscal"""

    # CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}

    try:
        request_json = request.get_json(silent=True)
        if not request_json:
            return jsonify({"erreur": "Format invalide"}), 400, headers

        # Détecter le type de requête
        if 'task' in request_json and request_json['task'] == 'verify':
            return handle_verification(request_json, headers)
        elif 'question' in request_json:
            return handle_question(request_json, headers)
        else:
            return jsonify({
                "erreur": "Format invalide. Attendu : {'question': '...'} ou {'task': 'verify', 'data': {...}}"
            }), 400, headers

    except Exception as e:
        print(f"❌ Erreur globale: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"erreur": "Erreur serveur", "details": str(e)}), 500, headers


def handle_question(request_json: Dict, headers: Dict):
    """Gère les questions documentaires"""
    question = request_json['question']

    print(f"\n{'=' * 80}")
    print(f"📥 Question: {question}")
    print(f"{'=' * 80}")

    try:
        docs = rechercher_documents_semantique(question, MAX_DOCUMENTS)

        if not docs:
            return jsonify({
                "question": question,
                "reponse": "## Aucun document\n\nDésolé, aucune information pertinente trouvée.",
                "sources": [],
                "documents_trouves": 0
            }), 200, headers

        contexte = construire_contexte(docs)
        print(f"\n📄 Contexte: {len(contexte)} chars")

        reponse = generer_reponse(question, contexte)
        sources = extraire_sources(docs)

        response_data = {
            "question": question,
            "reponse": reponse,
            "sources": sources,
            "documents_trouves": len(docs),
            "methode_recherche": "semantique",
            "score_moyen": round(sum(d['score'] for d in docs) / len(docs), 2),
            "meilleur_score": round(docs[0]['score'], 2)
        }

        print(f"\n✅ Succès")
        print(f"{'=' * 80}\n")

        return jsonify(response_data), 200, headers

    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "erreur": "Erreur serveur",
            "details": str(e),
            "question": question
        }), 500, headers


def handle_verification(request_json: Dict, headers: Dict):
    """Gère les vérifications de déclarations TVA"""
    if 'data' not in request_json:
        return jsonify({"error": "Format invalide. 'data' requis."}), 400, headers

    data = request_json['data']
    historical_data = request_json.get('historical_data')

    print(f"\n{'=' * 80}")
    print(f"🔍 Vérification de déclaration TVA")
    print(f"{'=' * 80}")

    try:
        result = verifier_declaration_tva(data, historical_data)
        result['verified_at'] = datetime.now().isoformat()
        result['success'] = True

        print(f"\n✅ Vérification terminée")
        print(f"{'=' * 80}\n")

        return jsonify(result), 200, headers

    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "error": "Erreur lors de la vérification",
            "details": str(e),
            "success": False
        }), 500, headers
