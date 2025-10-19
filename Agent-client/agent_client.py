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
AGENTS_DISPONIBLES = [
    "fiscalite",
    "comptabilite",
    "ressources_humaines",
    "support_technique"
]

# --- Prompt système ---
PROMPT_SYSTEME = """
Tu es l'Agent Client, un LLM central jouant le rôle d'orchestrateur intelligent entre plusieurs agents spécialisés 
(fiscal, comptable, administratif, juridique, intégrateur, conseiller, etc.).

TA MISSION :
- Comprendre la demande du client.
- Identifier quel(s) agent(s) spécialisé(s) sont les plus pertinents pour y répondre.
- Formuler des requêtes claires et contextualisées à ces agents.
- Synthétiser et restituer la réponse finale au client de manière cohérente, fluide et professionnelle.

RÈGLES STRICTES :
1. Ne formule pas toi-même une réponse d'expert (fiscalité, comptabilité, etc.) si elle doit provenir d’un autre agent.
2. Si une demande nécessite plusieurs agents, coordonne leur exécution et fusionne leurs résultats.
3. Si aucune information n’est disponible ou si aucun agent n’est compétent, réponds :
   "Je n’ai pas trouvé cette information dans ma base de connaissances actuelle."
4. Cite toujours la ou les sources des informations (titre et URL) lorsque tu t’appuies sur des documents de contexte.
5. Sois précis, clair, professionnel et structuré dans tes réponses au client.
6. Si plusieurs agents te transmettent des informations complémentaires, synthétise-les avec cohérence et logique métier.
7. Maintiens un ton empathique et humain — tu es le point de contact principal du client, pas un simple relais technique.

BUT FINAL :
Assurer une expérience fluide, fiable et transparente entre le client et les différents agents, 
tout en garantissant la qualité et la traçabilité des informations.

---

CONTEXTE DOCUMENTAIRE :
{contexte}


QUESTION DE L'UTILISATEUR :
{question}

LISTE DES AGENTS DISPONIBLES :
{AGENTS_DISPONIBLES}

RÉPONSE :
"""

def classifier_intention(question: str) -> str:
    """
    Classifie la question pour déterminer l'agent de destination.
    
    Args:
        question: La question de l'utilisateur
        
    Returns:
        Le nom de l'agent de destination (e.g., 'fiscalite', 'non_pertinent')
    """
    print(f"\n🧠 Classification de l'intention pour : '{question}'")
    
    # Construire le prompt complet
    prompt = PROMPT_SYSTEME.format(question=question)
    
    try:
        # Appeler le modèle
        # Utiliser un modèle rapide pour la classification
        response = model.generate_content(prompt) 
        
        # Nettoyer la réponse (le modèle ne devrait répondre que par le nom de l'agent)
        agent_cible = response.text.strip().lower()
        
        # Vérifier si l'agent cible fait partie de la liste ou est 'non_pertinent'
        if agent_cible not in AGENTS_DISPONIBLES and agent_cible != 'non_pertinent':
             # Si le modèle hallucine, forcer une valeur de sécurité
             return "non_pertinent"
        
        print(f"   ✅ Agent cible identifié : {agent_cible}")
        return agent_cible
        
    except Exception as e:
        print(f"   ❌ Erreur lors de la classification : {e}")
        return "erreur_interne"


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
def agent_client(request):
    """
    Point d'entrée de l'agent client.
    Reçoit une question et retourne la question à l'agent apte à répondre et retourne la réponse de cette agent.
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
        
        # ÉTAPE 1: Identifier le thème 
        
        
        # ÉTAPE 2: Rediriger la question au bon agent 
        
        # ÉTAPE 3: Générer la réponse de l'agent 
        
        # Etape 4 : Retourner la réponse de l'agent avec les sources
        
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        return jsonify({
            "erreur": "Erreur lors de la génération de la réponse.",
            "details": str(e)
        }), 500, headers


if __name__ == "__main__":
    # Test local
    print("Test local de l'agent client V2...")
    
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

