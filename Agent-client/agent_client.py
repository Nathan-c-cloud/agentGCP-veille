"""
Agent Client - Orchestrateur intelligent pour routage vers agents spécialisés
VERSION CORRIGÉE avec authentification service-to-service
"""

import functions_framework
from flask import jsonify
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel
import os
import requests
from typing import List, Dict, Tuple
import google.auth
from google.auth.transport.requests import AuthorizedSession
import json

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = "us-west1"

# --- Initialisation ---
vertexai.init(project=PROJECT_ID, location=LOCATION)
db = firestore.Client()
model = GenerativeModel("gemini-2.5-pro")

# Initialiser les credentials pour l'authentification service-to-service
try:
    credentials, project = google.auth.default()
    authed_session = AuthorizedSession(credentials)
    print("✅ Credentials initialisés pour l'authentification service-to-service")
except Exception as e:
    print(f"⚠️ Erreur d'initialisation des credentials: {e}")
    authed_session = None

# --- Configuration des agents spécialisés ---
AGENTS_CONFIG = {
    "fiscalite": {
        "url": "https://us-west1-agent-gcp-f6005.cloudfunctions.net/agent-fiscal-v2",
        "description": "Questions sur la fiscalité (TVA, IS, IR, CFE, taxes, impôts)",
        "requires_auth": False  # Cloud Function publique
    },
    "comptabilite": {
        "url": None,
        "description": "Questions sur la comptabilité, bilans, comptes",
        "requires_auth": False
    },
    "ressources_humaines": {
        "url": None,
        "description": "Questions sur les RH, contrats, paie, social",
        "requires_auth": False
    },
    "juridique": {
        "url": "https://agent-juridique-478570587937.us-west1.run.app",
        "description": "Questions juridiques, droit des sociétés",
        "requires_auth": True  # Cloud Run avec authentification
    },
    "aides": {
        "url": "https://agent-aides-478570587937.us-west1.run.app",
        "description": "Questions sur les aides publiques et subventions",
        "requires_auth": True,  # Cloud Run avec authentification
        "needs_company_info": True  # Nécessite les infos de l'entreprise
    }
}


def recuperer_infos_entreprise() -> Dict:
    """
    Récupère les informations de l'entreprise depuis Firestore.
    Collection: settings, Document: demo_company

    Returns:
        Dict contenant les informations de l'entreprise
    """
    print(f"\n📊 Récupération des informations de l'entreprise...")

    try:
        doc_ref = db.collection('settings').document('demo_company')
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            print(f"   ✅ Document récupéré avec succès")

            # Le document peut avoir deux structures possibles:
            # 1. Champs directement à la racine (nom, ville, codePostal, etc.)
            # 2. Champs imbriqués dans company_info

            # Vérifier si company_info existe (structure imbriquée)
            if 'company_info' in data and isinstance(data['company_info'], dict):
                company_data = data['company_info']
                print(f"   📋 Structure imbriquée détectée (company_info)")
            else:
                company_data = data
                print(f"   📋 Structure plate détectée")

            # Extraire les informations pertinentes pour les aides
            infos_pour_aides = {
                "nom": company_data.get('nom', 'Non spécifié'),
                "localisation": {
                    "ville": company_data.get('ville', 'Non spécifié'),
                    "code_postal": company_data.get('codePostal', 'Non spécifié'),
                    "adresse": company_data.get('adresse', 'Non spécifié')
                },
                "taille": company_data.get('effectif', 'Non spécifié'),
                "secteur_activite": company_data.get('secteurActivite', 'Non spécifié'),
                "forme_juridique": company_data.get('formeJuridique', 'Non spécifié'),
                "date_creation": company_data.get('dateCreation', 'Non spécifié'),
                "siret": company_data.get('siret', 'Non spécifié')
            }

            print(f"   📍 Localisation: {infos_pour_aides['localisation']['ville']} ({infos_pour_aides['localisation']['code_postal']})")
            print(f"   👥 Effectif: {infos_pour_aides['taille']}")
            print(f"   🏭 Secteur: {infos_pour_aides['secteur_activite']}")

            return infos_pour_aides
        else:
            print(f"   ⚠️ Document demo_company non trouvé dans la collection settings")
            return {}

    except Exception as e:
        print(f"   ❌ Erreur lors de la récupération des infos entreprise: {e}")
        import traceback
        traceback.print_exc()
        return {}


# --- Prompt de classification ---
PROMPT_CLASSIFICATION = """Tu es un classificateur de questions pour un système multi-agents.

Analyse la question de l'utilisateur et identifie quel agent spécialisé doit y répondre.

AGENTS DISPONIBLES :
- fiscalite : TVA, impôts, IS, IR, CFE, taxes, déclarations fiscales
- comptabilite : Comptabilité, bilans, comptes, écritures comptables
- ressources_humaines : RH, contrats, paie, congés, droit du travail
- juridique : Droit des sociétés, contrats commerciaux, aspects juridiques
- aides : Aides publiques, subventions, financements

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
            return "fiscalite", 0.5

    except Exception as e:
        print(f"   ❌ Erreur lors de la classification : {e}")
        return "fiscalite", 0.3


def appeler_agent_specialise(agent_name: str, question: str) -> Dict:
    """
    Appelle un agent spécialisé via HTTP avec authentification si nécessaire.

    CORRECTION PRINCIPALE : Utilise AuthorizedSession pour les services Cloud Run authentifiés.
    """
    print(f"\n📞 Appel de l'agent '{agent_name}'...")

    agent_config = AGENTS_CONFIG.get(agent_name)

    if not agent_config or not agent_config["url"]:
        return {
            "erreur": f"L'agent '{agent_name}' n'est pas encore disponible.",
            "reponse": "Désolé, cette fonctionnalité n'est pas encore implémentée."
        }

    try:
        base_url = agent_config["url"]
        requires_auth = agent_config.get("requires_auth", False)
        needs_company_info = agent_config.get("needs_company_info", False)

        # Préparer l'URL et le payload selon le type d'agent
        if agent_name in ["juridique", "aides"]:
            # Agents Flask sur Cloud Run
            url = f"{base_url}/query" if not base_url.endswith("/query") else base_url
            payload = {"user_query": question}

            # Si l'agent nécessite les infos de l'entreprise, les ajouter
            if needs_company_info and agent_name == "aides":
                company_info = recuperer_infos_entreprise()
                if company_info:
                    payload["company_info"] = company_info
                    print(f"   📊 Infos entreprise ajoutées au payload")
        else:
            # Agent fiscal (Cloud Function)
            url = base_url
            payload = {"question": question}

        print(f"   🌐 URL: {url}")
        print(f"   📦 Payload: {list(payload.keys())}")
        print(f"   🔒 Authentification requise: {requires_auth}")

        # Faire la requête avec ou sans authentification
        if requires_auth:
            # Utiliser la session authentifiée pour Cloud Run
            if authed_session is None:
                print(f"   ❌ Session authentifiée non disponible")
                return {
                    "erreur": "Authentification non disponible",
                    "reponse": "Impossible d'authentifier l'appel à l'agent sécurisé."
                }

            print(f"   🔑 Utilisation de l'authentification service-to-service...")
            response = authed_session.post(url, json=payload, timeout=60)
        else:
            # Requête simple pour les services publics
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, json=payload, headers=headers, timeout=60)

        print(f"   📡 Status code: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()

                # Traiter la réponse selon le type d'agent
                if agent_name in ["juridique", "aides"]:
                    if isinstance(data, dict):
                        # Nettoyer les données: supprimer les champs handoff si non nécessaires
                        cleaned_data = data.copy()

                        # Supprimer les informations de handoff si handoff.needed = false
                        if isinstance(cleaned_data.get("handoff"), dict):
                            handoff = cleaned_data.get("handoff", {})
                            if not handoff.get("needed", False):
                                # Supprimer complètement la section handoff si elle n'est pas nécessaire
                                cleaned_data.pop("handoff", None)

                        # Extraire les informations pertinentes
                        sources = cleaned_data.get("sources", []) or cleaned_data.get("sources_officielles", [])

                        return {
                            "reponse": json.dumps(cleaned_data, indent=2, ensure_ascii=False),
                            "sources": sources,
                            "data_complete": cleaned_data
                        }
                    else:
                        return {"reponse": str(data), "sources": []}
                else:
                    # Agent fiscal
                    if isinstance(data, dict) and "reponse" in data:
                        print(f"   ✅ Réponse reçue ({len(data.get('reponse', ''))} caractères)")
                        return data
                    else:
                        return {"reponse": str(data), "sources": []}

            except ValueError as e:
                print(f"   ⚠️ Réponse non-JSON: {e}")
                return {"reponse": response.text, "sources": []}

        elif response.status_code == 403:
            print(f"   ❌ Erreur 403 Forbidden - Problème de permissions IAM")
            print(f"   💡 Solution: Vérifiez que le service account a le rôle 'roles/run.invoker'")
            return {
                "erreur": "Accès refusé (403)",
                "reponse": "L'agent client n'a pas les permissions pour accéder à cet agent. Vérifiez les permissions IAM."
            }
        elif response.status_code == 401:
            print(f"   ❌ Erreur 401 Unauthorized - Problème d'authentification")
            return {
                "erreur": "Non autorisé (401)",
                "reponse": "Erreur d'authentification lors de l'appel à l'agent."
            }
        else:
            print(f"   ❌ Erreur HTTP {response.status_code}")
            print(f"   📄 Réponse: {response.text[:200]}")
            return {
                "erreur": f"Erreur de l'agent : {response.status_code}",
                "reponse": "Désolé, une erreur est survenue lors du traitement de votre demande."
            }

    except requests.exceptions.Timeout:
        print(f"   ⏱️ Timeout de l'agent")
        return {
            "erreur": "Timeout",
            "reponse": "La requête a pris trop de temps. Veuillez réessayer."
        }
    except Exception as e:
        print(f"   ❌ Erreur lors de l'appel : {e}")
        import traceback
        traceback.print_exc()
        return {
            "erreur": str(e),
            "reponse": "Désolé, une erreur technique est survenue."
        }


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
                "reponse": "Je ne suis pas sûr de comprendre votre question. Pourriez-vous reformuler ou préciser votre demande concernant la fiscalité, la comptabilité, les ressources humaines, le juridique ou les aides ?",
                "confiance": confiance
            }), 200, headers

        # ÉTAPE 2: Appeler l'agent spécialisé
        reponse_agent = appeler_agent_specialise(agent_cible, question)

        # ÉTAPE 3: Préparer la réponse finale
        if "erreur" in reponse_agent and reponse_agent.get("reponse") == "Désolé, cette fonctionnalité n'est pas encore implémentée.":
            return jsonify({
                "question": question,
                "agent_utilise": agent_cible,
                "reponse": f"Je comprends que votre question concerne le domaine '{agent_cible}', mais cet agent n'est pas encore disponible.",
                "agent_disponible": False
            }), 200, headers

        # ÉTAPE 4: Retourner la réponse complète
        return jsonify({
            "question": question,
            "agent_utilise": agent_cible,
            "reponse": reponse_agent.get("reponse", "Aucune réponse générée"),
            "sources": reponse_agent.get("sources", []),
            "documents_trouves": reponse_agent.get("documents_trouves", 0),
            "confiance": confiance,
            "data_complete": reponse_agent.get("data_complete")
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
        "Quelles sont les aides pour une PME innovante ?",
        "Comment créer une SAS ?"
    ]

    for question in questions_test:
        print(f"\n{'='*80}")
        print(f"Test : {question}")
        print(f"{'='*80}")

        # ÉTAPE 1: Classification
        agent, confiance = classifier_question(question)
        print(f"Classification : {agent} (confiance: {confiance})")

        # ÉTAPE 2: Appel de l'agent spécialisé
        reponse = appeler_agent_specialise(agent, question)
        print(f"\n📝 Réponse de l'agent '{agent}':")
        if "erreur" in reponse:
            print(f"   ❌ Erreur: {reponse['erreur']}")
        if "reponse" in reponse:
            print(f"   💬 {reponse['reponse'][:200]}...")
        if "sources" in reponse:
            print(f"   📚 Sources: {len(reponse['sources'])} document(s)")
