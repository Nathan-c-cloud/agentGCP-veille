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
from google.cloud import firestore

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = "us-west1"
BUCKET_NAME = os.environ.get("BUCKET_NAME", "documents-fiscaux-bucket")

# Initialisation Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Clients Google Cloud
storage_client = storage.Client()
db = firestore.Client(project=PROJECT_ID)

# Modèles IA
model = GenerativeModel("gemini-2.0-flash")
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")

# --- Paramètres optimisés ---
MAX_DOCUMENTS = 3
MIN_SIMILARITY_SCORE = 0.3
MAX_CONTEXT_LENGTH = 3000

# Cache intelligent
_documents_cache = []
_cache_timestamp = None
CACHE_DURATION_SECONDS = 3600
_embeddings_cache = {}


def charger_documents_depuis_gcs() -> List[Dict]:
    """Charge tous les documents fiscaux depuis Cloud Storage avec cache."""
    global _documents_cache, _cache_timestamp

    now = datetime.now().timestamp()
    if _documents_cache and _cache_timestamp:
        if (now - _cache_timestamp) < CACHE_DURATION_SECONDS:
            print(f"✅ Cache ({len(_documents_cache)} docs)")
            return _documents_cache

    print(f"📥 Chargement depuis gs://{BUCKET_NAME}...")
    documents = []

    try:
        bucket = storage_client.bucket(BUCKET_NAME)
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
    if texte in _embeddings_cache:
        return _embeddings_cache[texte]

    try:
        if len(texte) > 5000:
            texte = texte[:2000] + " ... " + texte[-2000:]

        embeddings = embedding_model.get_embeddings([texte])
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
    prompt = PROMPT_SYSTEME.format(contexte=contexte, question=question)

    try:
        print("\n💭 Génération réponse...")

        response = model.generate_content(
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


# ==========================================
# FONCTIONS VEILLE RÉGLEMENTAIRE
# ==========================================

def determiner_categorie(document: Dict, domaines_prioritaires: List[str]) -> str:
    """Détermine la catégorie selon la structure alerts."""
    titre = document.get('titre_source', '').lower()
    contenu = document.get('contenu', '')[:800].lower()
    texte = f"{titre} {contenu}"

    # Mapping catégories
    if any(mot in texte for mot in ['tva', 'taxe sur la valeur']):
        return "fiscal"
    elif any(mot in texte for mot in ['rh', 'salarié', 'charges sociales', 'urssaf']):
        return "rh"
    elif any(mot in texte for mot in ['loi', 'obligation', 'réglementation']):
        return "juridique"
    elif any(mot in texte for mot in ['aide', 'subvention', 'crédit impôt']):
        return "aides"
    else:
        # Utilise domaines prioritaires
        for domaine in domaines_prioritaires:
            if domaine.lower() in texte:
                return domaine.lower()
        return "fiscal"


def generer_analyse_ia(document: Dict, settings: Dict) -> str:
    """Génère analyse IA via Gemini."""
    company_info = settings.get('company_info', {})
    ai_prefs = settings.get('ai_preferences', {})

    ton = ai_prefs.get('tonCommunication', 'professionnel')
    niveau = ai_prefs.get('niveauDetail', 'standard')

    prompt = f"""Analyse cette nouvelle réglementation pour l'entreprise.

TON: {ton}
NIVEAU: {niveau}

ENTREPRISE:
- Nom: {company_info.get('nom')}
- Secteur: {company_info.get('secteurActivite')}
- Régime fiscal: {company_info.get('regimeFiscal')}
- Régime TVA: {company_info.get('regimeTVA')}
- Forme: {company_info.get('formeJuridique')}
- Effectif: {company_info.get('effectif')}

DOCUMENT:
- Titre: {document.get('titre_source')}
- Extrait: {document.get('contenu', '')[:600]}

CONSIGNE: En 2-3 phrases courtes, explique :
1. Ce que change cette réglementation
2. L'impact concret pour cette entreprise
3. Les actions à prévoir

RÉPONSE (max 120 mots, {ton}):"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.3,
                'max_output_tokens': 200
            }
        )
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ Erreur analyse IA: {e}")
        return f"Nouvelle réglementation {determiner_categorie(document, [])} détectée. Analyse de l'impact recommandée."


def generer_actions(categorie: str, document: Dict) -> List[str]:
    """Génère actions possibles selon catégorie."""
    actions_map = {
        "fiscal": [
            "Consulter votre expert-comptable",
            "Vérifier la conformité de vos déclarations",
            "Mettre à jour votre logiciel de comptabilité"
        ],
        "rh": [
            "Informer le service RH",
            "Vérifier les contrats de travail",
            "Mettre à jour les procédures internes"
        ],
        "juridique": [
            "Consulter un avocat spécialisé",
            "Auditer la conformité juridique",
            "Mettre à jour les mentions légales"
        ],
        "aides": [
            "Vérifier l'éligibilité de votre entreprise",
            "Préparer le dossier de demande",
            "Contacter l'organisme compétent"
        ]
    }

    return actions_map.get(categorie, [
        "Consulter un professionnel",
        "Analyser l'impact pour votre entreprise",
        "Suivre l'évolution de la réglementation"
    ])


def generer_tags(categorie: str, document: Dict) -> List[str]:
    """Génère tags prédéfinis selon la catégorie du document."""
    # Tags prédéfinis par catégorie
    tags_map = {
        "fiscal": ["TVA", "IS", "Fiscal", "Déclaration", "Impôts"],
        "rh": ["DSN", "RH", "Paie", "Formation", "Social"],
        "juridique": ["Juridique", "Conformité", "Réglementation", "Obligations", "Droit"],
        "aides": ["Aides", "Subventions", "Financement", "Crédit d'impôt", "Dispositifs"]
    }

    # Retourne les tags correspondant à la catégorie
    return tags_map.get(categorie, ["Fiscal", "Réglementation", "Général"])


def analyser_pertinence_entreprise(settings: Dict) -> Dict:
    """Analyse documents GCS et CRÉE alertes Firestore."""
    print(f"\n🏢 Analyse pour: {settings['company_info'].get('nom')}")

    company_id = settings.get('companyId')
    user_id = settings.get('userId')

    if not company_id:
        raise ValueError("settings.companyId manquant")

    # Construction profil textuel
    company_info = settings.get('company_info', {})
    ai_prefs = settings.get('ai_preferences', {})

    profil_texte = f"""
    Entreprise: {company_info.get('nom')}
    Secteur: {company_info.get('secteurActivite')}
    Forme juridique: {company_info.get('formeJuridique')}
    Régime fiscal: {company_info.get('regimeFiscal')}
    Régime TVA: {company_info.get('regimeTVA')}
    Effectif: {company_info.get('effectif')}
    Domaines prioritaires: {', '.join(ai_prefs.get('domainesPrioritaires', []))}
    """

    # Chargement documents
    all_docs = charger_documents_depuis_gcs()
    if not all_docs:
        print(" Aucun document disponible")
        return {"nb_alertes_creees": 0, "alertes": []}

    # Embedding profil
    profil_embedding = obtenir_embedding(profil_texte)
    if profil_embedding is None:
        print(" Impossible de générer embedding profil")
        return {"nb_alertes_creees": 0, "alertes": []}

    print(f" Analyse de {len(all_docs)} documents...")
    docs_pertinents = []

    # Analyse chaque document
    for doc in all_docs:
        titre = doc.get('titre_source', '')
        contenu = doc.get('contenu', '')

        # Texte pour comparaison
        doc_texte = f"{titre}. {titre}. {contenu[:2000]}"
        doc_embedding = obtenir_embedding(doc_texte)

        if doc_embedding is None:
            continue

        # Calcul similarité
        score_base = calculer_similarite_cosinus(profil_embedding, doc_embedding)

        if score_base >= MIN_SIMILARITY_SCORE:
            # Bonus domaines prioritaires
            domaines = ai_prefs.get('domainesPrioritaires', [])
            bonus_domaine = sum(0.10 for d in domaines
                                if d.lower() in titre.lower() or d.lower() in contenu[:500].lower())

            # Bonus régime spécifique
            bonus_regime = 0
            regime_fiscal = company_info.get('regimeFiscal', '').lower()
            regime_tva = company_info.get('regimeTVA', '').lower()
            texte_complet = f"{titre} {contenu[:1000]}".lower()

            if regime_fiscal and regime_fiscal.replace('_', ' ') in texte_complet:
                bonus_regime += 0.15
            if regime_tva and regime_tva.replace('_', ' ') in texte_complet:
                bonus_regime += 0.15

            score_final = min(score_base + bonus_domaine + bonus_regime, 1.0)

            doc['score'] = score_final
            doc['score_base'] = score_base
            docs_pertinents.append(doc)

    # Tri par pertinence
    docs_pertinents.sort(key=lambda x: x['score'], reverse=True)
    docs_pertinents = docs_pertinents[:MAX_DOCUMENTS]

    print(f" {len(docs_pertinents)} documents pertinents trouvés")

    # CRÉATION ALERTES FIRESTORE
    alertes_creees = []
    date_maintenant = datetime.now()

    for doc in docs_pertinents:
        # Détermination type urgence
        score = doc['score']
        if score > 0.75:
            type_urgence = "urgent"
            priorite = 1
        elif score > 0.55:
            type_urgence = "info"
            priorite = 2
        else:
            type_urgence = "normal"
            priorite = 3

        # Catégorisation
        categorie = determiner_categorie(doc, ai_prefs.get('domainesPrioritaires', []))

        # Génération analyse IA
        ai_analysis = generer_analyse_ia(doc, settings)

        # Génération des tags selon la catégorie
        tags = generer_tags(categorie, doc)

        # Construction alerte selon structure EXACTE
        alerte_data = {
            "companyId": company_id,
            "userId": user_id,
            "title": doc.get('titre_source', 'Nouvelle réglementation'),
            "summary": doc.get('contenu', '')[:200] + "...",
            "type": type_urgence,
            "category": categorie,
            "aiAnalysis": ai_analysis,
            "sourceUrl": doc.get('source_url', ''),
            "detectedDate": date_maintenant.isoformat(),
            "processedDate": None,
            "status": "nouveau",
            "priority": priorite,
            "actions": generer_actions(categorie, doc),
            "timeline": [
                {
                    "date": date_maintenant.isoformat(),
                    "event": "Détection automatique",
                    "actor": "Agent Fiscal IA"
                }
            ],
            "pertinence": {
                "score": round(score, 3),
                "score_base": round(doc['score_base'], 3),
                "raisons": [
                    f"Correspondance avec régime {company_info.get('regimeFiscal')}",
                    f"Pertinent pour secteur {company_info.get('secteurActivite')}"
                ]
            },
            "tags": tags
        }

        # Écriture Firestore
        try:
            alerte_ref = db.collection('info_alerts').add(alerte_data)
            alerte_id = alerte_ref[1].id
            alerte_data['id'] = alerte_id
            alertes_creees.append(alerte_data)
            print(f"  Alerte créée: {alerte_id} [{type_urgence}] {doc.get('titre_source', '')[:50]}")
        except Exception as e:
            print(f"   Erreur création alerte: {e}")

    return {
        "nb_alertes_creees": len(alertes_creees),
        "alertes": alertes_creees,
        "date_analyse": date_maintenant.isoformat(),
        "company_id": company_id
    }


@functions_framework.http
def agent_fiscal(request):
    """Point d'entrée HTTP pour l'agent fiscal - Support 2 modes."""
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}

    request_json = request.get_json(silent=True)
    if not request_json:
        return jsonify({"erreur": "Format JSON invalide"}), 400, headers

    # MODE 1: Analyse entreprise → Création alertes Firestore
    if 'settings' in request_json:
        print("\n🏢 MODE: Analyse Entreprise → Firestore alerts")
        settings = request_json['settings']

        try:
            resultat = analyser_pertinence_entreprise(settings)

            return jsonify({
                "succes": True,
                "companyId": resultat['company_id'],
                "companyName": settings['company_info'].get('nom'),
                "nbAlertesCreees": resultat['nb_alertes_creees'],
                "dateAnalyse": resultat['date_analyse']
            }), 200, headers

        except Exception as e:
            print(f" Erreur analyse: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"erreur": str(e)}), 500, headers

    # MODE 2: Question classique (existant)
    elif 'question' in request_json:
        question = request_json['question']

        print(f"\n{'=' * 80}")
        print(f" Question: {question}")
        print(f"{'=' * 80}")

        try:
            # Recherche sémantique
            docs = rechercher_documents_semantique(question, MAX_DOCUMENTS)

            if not docs:
                return jsonify({
                    "question": question,
                    "reponse": "## Aucun document\n\nDésolé, aucune information pertinente trouvée.",
                    "sources": [],
                    "documents_trouves": 0
                }), 200, headers

            # Construire contexte
            contexte = construire_contexte(docs)
            print(f"\n Contexte: {len(contexte)} chars")

            # Générer réponse
            reponse = generer_reponse(question, contexte)

            # Extraire sources
            sources = extraire_sources(docs)

            # Réponse finale
            response_data = {
                "question": question,
                "reponse": reponse,
                "sources": sources,
                "documents_trouves": len(docs),
                "methode_recherche": "semantique",
                "score_moyen": round(sum(d['score'] for d in docs) / len(docs), 2),
                "meilleur_score": round(docs[0]['score'], 2)
            }

            print(f"\n Succès")
            print(f"  Documents: {len(docs)}")
            print(f"  Score: {response_data['meilleur_score'] * 100:.1f}%")
            print(f"{'=' * 80}\n")

            return jsonify(response_data), 200, headers

        except Exception as e:
            print(f"\n ERREUR: {e}")
            import traceback
            traceback.print_exc()

            return jsonify({
                "erreur": "Erreur serveur",
                "details": str(e),
                "question": question
            }), 500, headers

    else:
        return jsonify({
            "erreur": "Manque 'settings' (analyse) ou 'question' (chat)"
        }), 400, headers


if __name__ == "__main__":
    print("\n TEST LOCAL\n")

    questions = [
        "C'est quoi la TVA ?",
        "Quel est le taux de l'impôt sur les sociétés ?",
    ]

    for i, q in enumerate(questions, 1):
        print(f"\n{'=' * 80}")
        print(f"TEST {i}: {q}")
        print(f"{'=' * 80}")


        class MockRequest:
            def get_json(self, silent):
                return {'question': q}

            method = 'POST'


        try:
            resp, status, headers = agent_fiscal(MockRequest())
            data = resp.json

            print(f"\n Status: {status}")
            print(f"   Docs: {data.get('documents_trouves', 0)}")
            print(f"\n RÉPONSE:\n{data.get('reponse', 'N/A')}")

            if data.get('sources'):
                print(f"\n SOURCES:")
                for j, src in enumerate(data['sources'], 1):
                    print(f"   {j}. {src.get('titre', 'N/A')} ({src.get('score', 0)})")

        except Exception as e:
            print(f"\n Erreur: {e}")
            import traceback

            traceback.print_exc()

    print(f"\n{'=' * 80}")
    print(" Tests terminés")
    print(f"{'=' * 80}\n")
