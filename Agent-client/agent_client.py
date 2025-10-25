"""
Agent Client - Orchestrateur intelligent pour routage vers agents spécialisés
"""

import functions_framework
from flask import jsonify
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel
import os
import requests
from typing import List, Dict, Tuple


# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = "us-west1"

# --- Initialisation ---
vertexai.init(project=PROJECT_ID, location=LOCATION)
db = firestore.Client()
model = GenerativeModel("gemini-2.0-flash-exp")  # Modèle rapide pour classification

# --- Configuration des agents spécialisés ---
AGENTS_CONFIG = {
    "fiscalite": {
        "url": "https://us-west1-agent-gcp-f6005.cloudfunctions.net/agent-fiscal-v2",
        "description": "Questions sur la fiscalité (TVA, IS, IR, CFE, taxes, impôts)"
    },
    "comptabilite": {
        "url": None,  # À implémenter
        "description": "Questions sur la comptabilité, bilans, comptes"
    },
    "ressources_humaines": {
        "url": None,  # À implémenter
        "description": "Questions sur les RH, contrats, paie, social"
    },
    "juridique": {
        "url": None,  # À implémenter
        "description": "Questions juridiques, droit des sociétés"
    }
}

# --- Prompt de classification ---
PROMPT_CLASSIFICATION = """Tu es un classificateur de questions pour un système multi-agents.

Analyse la question de l'utilisateur et identifie quel agent spécialisé doit y répondre.

AGENTS DISPONIBLES :
- fiscalite : TVA, impôts, IS, IR, CFE, taxes, déclarations fiscales
- comptabilite : Comptabilité, bilans, comptes, écritures comptables
- ressources_humaines : RH, contrats, paie, congés, droit du travail
- juridique : Droit des sociétés, contrats commerciaux, aspects juridiques

RÈGLES :
1. Réponds UNIQUEMENT par le nom de l'agent (ex: "fiscalite")
2. Si la question n'est pas pertinente, réponds "non_pertinent"
3. Ne donne AUCUNE explication, juste le nom de l'agent

QUESTION : {question}

AGENT :"""


def classifier_question(question: str) -> Tuple[str, float]:
    """
    Classifie la question pour identifier l'agent cible.

    Returns:
        Tuple (nom_agent, confiance) où confiance est un score 0-1
    """
    print(f"\n🧠 Classification de la question...")

    prompt = PROMPT_CLASSIFICATION.format(question=question)

    try:
        response = model.generate_content(prompt)
        agent_cible = response.text.strip().lower()
        
        # Validation
        if agent_cible in AGENTS_CONFIG:
            print(f"   ✅ Agent identifié : {agent_cible}")
            return agent_cible, 0.9
        elif agent_cible == "non_pertinent":
            print(f"   ⚠️ Question non pertinente")
            return "non_pertinent", 0.8
        else:
            print(f"   ⚠️ Classification incertaine : {agent_cible}")
            # Par défaut, essayer l'agent fiscal
            return "fiscalite", 0.5

    except Exception as e:
        print(f"   ❌ Erreur lors de la classification : {e}")
        return "fiscalite", 0.3  # Fallback vers fiscal


def appeler_agent_specialise(agent_name: str, question: str) -> Dict:
    """
    Appelle un agent spécialisé via HTTP.

    Args:
        agent_name: Nom de l'agent (ex: 'fiscalite')
        question: Question de l'utilisateur

    Returns:
        Réponse de l'agent sous forme de dict
    """
    print(f"\n Appel de l'agent '{agent_name}'...")

    agent_config = AGENTS_CONFIG.get(agent_name)

    if not agent_config or not agent_config["url"]:
        return {
            "erreur": f"L'agent '{agent_name}' n'est pas encore disponible.",
            "reponse": "Désolé, cette fonctionnalité n'est pas encore implémentée."
        }

    try:
        # Appel HTTP POST à l'agent
        response = requests.post(
            agent_config["url"],
            json={"question": question},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Réponse reçue de l'agent ({len(data.get('reponse', ''))} caractères)")
            return data
        else:
            print(f"   ❌ Erreur HTTP {response.status_code}")
            return {
                "erreur": f"Erreur de l'agent : {response.status_code}",
                "reponse": "Désolé, une erreur est survenue lors du traitement de votre demande."
            }

    except requests.exceptions.Timeout:
        print(f"  Timeout de l'agent")
        return {
            "erreur": "Timeout",
            "reponse": "La requête a pris trop de temps. Veuillez réessayer."
        }
    except Exception as e:
        print(f"   Erreur lors de l'appel : {e}")
        return {
            "erreur": str(e),
            "reponse": "Désolé, une erreur technique est survenue."
        }


def synthese_reponse(question: str, agent_name: str, reponse_agent: str) -> str:
    """
    Optionnel : Améliore/synthétise la réponse de l'agent si nécessaire.
    Pour l'instant, on retourne directement la réponse de l'agent.
    """
    return reponse_agent


@functions_framework.http
def agent_client(request):
    """
    Point d'entrée de l'agent client orchestrateur.
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
                "erreur": "Aucune question fournie. Format attendu: {\"question\": \"votre question\"}"
            }), 400, headers
        
        question = request_json['question']
        print(f"\n{'='*80}")
        print(f" Question reçue : {question}")
        print(f"{'='*80}")
        
        # ÉTAPE 1: Classifier la question
        agent_cible, confiance = classifier_question(question)

        if agent_cible == "non_pertinent":
            return jsonify({
                "question": question,
                "agent_utilise": "aucun",
                "reponse": "Je ne suis pas sûr de comprendre votre question. Pourriez-vous reformuler ou préciser votre demande concernant la fiscalité, la comptabilité ou les ressources humaines ?",
                "confiance": confiance
            }), 200, headers

        # ÉTAPE 2: Appeler l'agent spécialisé
        reponse_agent = appeler_agent_specialise(agent_cible, question)

        # ÉTAPE 3: Préparer la réponse finale
        if "erreur" in reponse_agent and reponse_agent.get("reponse") == "Désolé, cette fonctionnalité n'est pas encore implémentée.":
            # Agent pas encore disponible
            return jsonify({
                "question": question,
                "agent_utilise": agent_cible,
                "reponse": f"Je comprends que votre question concerne le domaine '{agent_cible}', mais cet agent n'est pas encore disponible. Pour l'instant, seul l'agent fiscal est opérationnel.",
                "agent_disponible": False
            }), 200, headers

        # ÉTAPE 4: Retourner la réponse complète
        return jsonify({
            "question": question,
            "agent_utilise": agent_cible,
            "reponse": reponse_agent.get("reponse", "Aucune réponse générée"),
            "sources": reponse_agent.get("sources", []),
            "documents_trouves": reponse_agent.get("documents_trouves", 0),
            "confiance": confiance
        }), 200, headers

    except Exception as e:
        print(f"\n❌ ERREUR GLOBALE: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "erreur": "Erreur interne du serveur",
            "details": str(e)
        }), 500, headers


if __name__ == "__main__":
    # Test local
    print("🧪 Test local de l'agent client orchestrateur...\n")

    questions_test = [
        "C'est quoi la TVA ?",
        "Comment calculer l'impôt sur les sociétés ?",
        "Quel est le taux de la CFE ?"
    ]

    for question in questions_test:
        print(f"\n{'='*80}")
        print(f"Test : {question}")
        print(f"{'='*80}")

        agent, confiance = classifier_question(question)
        print(f"Résultat : {agent} (confiance: {confiance})")
