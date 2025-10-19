"""
Agent Fiscal V2 - Adapté pour utiliser la nouvelle collection de chunks
Version optimisée pour le RAG avec recherche sur chunks sémantiques.
"""

import functions_framework
from flask import jsonify
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel
import os
from typing import List, Dict


# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = "us-west1"

# --- Initialisation ---
vertexai.init(project=PROJECT_ID, location=LOCATION)
db = firestore.Client()
model = GenerativeModel("gemini-2.0-flash")

# --- Paramètres de recherche ---
MAX_CHUNKS = 10  # Nombre maximum de chunks à récupérer (réduit car les chunks sont plus petits et ciblés)

# --- Prompt système ---
PROMPT_SYSTEME = """Tu es un assistant fiscal expert spécialisé dans la fiscalité des PME françaises.

RÈGLES STRICTES :
1. Tu dois baser tes réponses EXCLUSIVEMENT sur les documents de contexte fournis ci-dessous.
2. Ne réponds JAMAIS à une question si la réponse n'est pas dans le contexte.
3. Si l'information n'est pas disponible, dis clairement : "Je n'ai pas trouvé cette information dans ma base de connaissances."
4. Cite toujours la source (titre et URL) des informations que tu utilises.
5. Sois précis, professionnel et structuré dans tes réponses.
6. Si plusieurs sources donnent des informations complémentaires, synthétise-les de manière cohérente.

CONTEXTE DOCUMENTAIRE :
{contexte}

QUESTION DE L'UTILISATEUR :
{question}

RÉPONSE :"""


def extraire_mots_cles(question: str) -> List[str]:
    """
    Extrait les mots-clés pertinents d'une question.
    Version améliorée avec normalisation et filtrage.
    
    Args:
        question: La question de l'utilisateur
        
    Returns:
        Liste de mots-clés normalisés
    """
    # Mots vides français à ignorer
    mots_vides = {
        'le', 'la', 'les', 'un', 'une', 'des', 'de', 'du', 'au', 'aux',
        'et', 'ou', 'mais', 'donc', 'or', 'ni', 'car',
        'je', 'tu', 'il', 'elle', 'nous', 'vous', 'ils', 'elles',
        'mon', 'ma', 'mes', 'ton', 'ta', 'tes', 'son', 'sa', 'ses',
        'ce', 'cet', 'cette', 'ces',
        'qui', 'que', 'quoi', 'dont', 'où',
        'est', 'sont', 'être', 'avoir', 'faire',
        'pour', 'dans', 'sur', 'avec', 'sans', 'sous', 'par',
        'quoi', 'quel', 'quelle', 'quels', 'quelles',
        'comment', 'combien', 'pourquoi', 'quand',
        'c', 'qu', 'd', 'l', 's', 't', 'n', 'm'
    }
    
    # Normaliser et découper
    question_lower = question.lower()
    mots = question_lower.split()
    
    # Filtrer et nettoyer
    mots_cles = []
    for mot in mots:
        # Retirer la ponctuation
        mot_clean = ''.join(c for c in mot if c.isalnum() or c in ['é', 'è', 'ê', 'à', 'â', 'ù', 'û', 'ô', 'î', 'ç'])
        
        # Garder seulement si pas un mot vide et assez long
        if mot_clean and mot_clean not in mots_vides and len(mot_clean) >= 3:
            mots_cles.append(mot_clean)
    
    return mots_cles


def rechercher_chunks(question: str, max_chunks: int = MAX_CHUNKS) -> List[Dict]:
    """
    Recherche les chunks les plus pertinents pour une question.
    Version optimisée pour la nouvelle structure de données.
    
    Args:
        question: La question de l'utilisateur
        max_chunks: Nombre maximum de chunks à retourner
        
    Returns:
        Liste de chunks pertinents avec leurs métadonnées
    """
    print(f"\n🔍 Recherche de chunks pour : '{question}'")
    
    # Extraire les mots-clés
    mots_cles = extraire_mots_cles(question)
    print(f"   Mots-clés extraits : {mots_cles}")
    
    if not mots_cles:
        print("   ⚠️  Aucun mot-clé pertinent trouvé")
        return []
    
    # Recherche dans Firestore
    collection_ref = db.collection("documents_fiscaux_chunks")
    
    # Stratégie de recherche : on cherche les chunks qui contiennent les mots-clés
    # Note: Pour une vraie production, utiliser Vector Search ou Algolia
    chunks_trouves = []
    chunks_scores = {}  # Pour scorer les chunks
    
    # Récupérer tous les chunks (pour une vraie prod, utiliser une recherche vectorielle)
    # Ici on fait simple pour la démo
    all_chunks = collection_ref.limit(500).stream()  # Limiter pour éviter les timeouts
    
    for chunk_doc in all_chunks:
        chunk_data = chunk_doc.to_dict()
        contenu = chunk_data.get('contenu', '').lower()
        titre = chunk_data.get('titre_source', '').lower()
        
        # Calculer un score basé sur la présence des mots-clés
        score = 0
        for mot_cle in mots_cles:
            # Bonus si le mot-clé est dans le titre
            if mot_cle in titre:
                score += 3
            # Points pour chaque occurrence dans le contenu
            score += contenu.count(mot_cle)
        
        if score > 0:
            chunk_data['score'] = score
            chunks_scores[chunk_doc.id] = score
            chunks_trouves.append(chunk_data)
    
    # Trier par score décroissant
    chunks_trouves.sort(key=lambda x: x['score'], reverse=True)
    
    # Limiter au nombre demandé
    chunks_pertinents = chunks_trouves[:max_chunks]
    
    print(f"   ✅ {len(chunks_pertinents)} chunk(s) trouvé(s)")
    for i, chunk in enumerate(chunks_pertinents[:3], 1):  # Afficher les 3 premiers
        print(f"      {i}. Score {chunk['score']}: {chunk.get('titre_source', 'Sans titre')[:60]}...")
    
    return chunks_pertinents


def construire_contexte(chunks: List[Dict]) -> str:
    """
    Construit le contexte textuel à partir des chunks trouvés.
    
    Args:
        chunks: Liste de chunks pertinents
        
    Returns:
        Texte formaté du contexte
    """
    if not chunks:
        return "Aucun document pertinent trouvé."
    
    contexte_parts = []
    
    for i, chunk in enumerate(chunks, 1):
        titre = chunk.get('titre_source', 'Sans titre')
        url = chunk.get('source_url', 'URL non disponible')
        contenu = chunk.get('contenu', '')
        
        contexte_parts.append(f"""
--- Document {i} ---
Titre: {titre}
Source: {url}
Contenu:
{contenu}
""")
    
    return "\n".join(contexte_parts)


def generer_reponse(question: str, contexte: str) -> str:
    """
    Génère une réponse en utilisant le modèle LLM avec le contexte fourni.
    
    Args:
        question: La question de l'utilisateur
        contexte: Le contexte documentaire
        
    Returns:
        La réponse générée
    """
    print(f"\n🤖 Génération de la réponse avec le modèle LLM...")
    
    # Construire le prompt complet
    prompt = PROMPT_SYSTEME.format(
        contexte=contexte,
        question=question
    )
    
    try:
        # Appeler le modèle
        response = model.generate_content(prompt)
        reponse_text = response.text
        
        print(f"   ✅ Réponse générée ({len(reponse_text)} caractères)")
        return reponse_text
        
    except Exception as e:
        print(f"   ❌ Erreur lors de la génération : {e}")
        raise


@functions_framework.http
def agent_fiscal(request):
    """
    Point d'entrée de la Cloud Function.
    Reçoit une question et retourne une réponse basée sur les chunks de la base de connaissances.
    """
    # Gérer CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    try:
        # Récupérer la question
        request_json = request.get_json(silent=True)
        
        if not request_json or 'question' not in request_json:
            return jsonify({
                "erreur": "Aucune question fournie. Utilisez le format: {\"question\": \"votre question\"}"
            }), 400, headers
        
        question = request_json['question']
        print(f"\n{'='*80}")
        print(f"📨 Question reçue : {question}")
        print(f"{'='*80}")
        
        # ÉTAPE 1: Rechercher les chunks pertinents
        chunks = rechercher_chunks(question)
        
        if not chunks:
            return jsonify({
                "question": question,
                "reponse": "Je n'ai pas trouvé d'information pertinente dans ma base de connaissances pour répondre à cette question.",
                "chunks_trouves": 0
            }), 200, headers
        
        # ÉTAPE 2: Construire le contexte
        contexte = construire_contexte(chunks)
        
        # ÉTAPE 3: Générer la réponse
        reponse = generer_reponse(question, contexte)
        
        # Retourner la réponse
        return jsonify({
            "question": question,
            "reponse": reponse,
            "chunks_trouves": len(chunks),
            "sources": [
                {
                    "titre": chunk.get('titre_source'),
                    "url": chunk.get('source_url')
                }
                for chunk in chunks[:3]  # Retourner les 3 sources principales
            ]
        }), 200, headers
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        return jsonify({
            "erreur": "Erreur lors de la génération de la réponse.",
            "details": str(e)
        }), 500, headers


if __name__ == "__main__":
    # Test local
    print("Test local de l'agent fiscal V2...")
    
    question_test = "C'est quoi la TVA ?"
    
    print(f"\nQuestion de test : {question_test}")
    
    # Simuler la recherche
    chunks = rechercher_chunks(question_test)
    
    if chunks:
        contexte = construire_contexte(chunks)
        print(f"\nContexte construit ({len(contexte)} caractères)")
        print("\nPremiers 500 caractères du contexte:")
        print("-"*80)
        print(contexte[:500])
        print("-"*80)
    else:
        print("\n⚠️  Aucun chunk trouvé")

