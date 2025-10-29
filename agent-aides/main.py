import os
import json
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = os.environ.get("LOCATION", "us-west1")

# --- CORRECTION: Initialiser le client GenAI globalement (une seule fois au démarrage) ---
print("Agent Aides: Initialisation du client GenAI au démarrage du conteneur...")
try:
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION
    )
    print("Agent Aides: Client GenAI initialisé avec succès.")
except Exception as e:
    print(f"ERREUR FATALE: Impossible d'initialiser le client GenAI: {e}")
    import traceback
    traceback.print_exc()
    client = None  # Gérer l'échec d'initialisation

# --- Définition du Prompt ---
SI_TEXT_AIDES = """Tu es un Agent_Aides. Ta mission : identifier et résumer les aides publiques pertinentes pour une entreprise française (nationales, régionales, européennes), et fournir une sortie JSON strictement conforme au schéma.

**Instructions strictes :**
1. Analysez la question de l'utilisateur ET le contexte de l'entreprise fourni (localisation, taille, secteur d'activité).
2. Fondez votre réponse **uniquement** sur les informations présentes dans le contexte récupéré via RAG.
3. **IMPORTANT**: Si un contexte d'entreprise est fourni (ville, département, taille, secteur), utilisez-le pour filtrer et cibler les aides les PLUS PERTINENTES pour ce profil spécifique.
4. Mentionnez explicitement dans votre réponse comment le profil de l'entreprise correspond aux critères des aides identifiées.
5. Si le contexte ne contient pas d'aides correspondant au profil spécifique, indiquez "Je ne trouve pas d'aides correspondantes pour [profil] dans ma base de connaissances."
6. Ne jamais utiliser vos connaissances générales, utilisez l'ancrage pour fiabiliser votre réponse.
7. Citez vos sources en vous basant sur le contexte.
8. Répondez au format JSON structuré.

**Profil de recherche:**
- Localisation (région/département) → Aides régionales et départementales ciblées
- Taille (TPE/PME/ETI) → Aides adaptées à la taille
- Secteur d'activité → Aides sectorielles spécifiques
- Nature du projet → Aides thématiques (innovation, export, transition écologique, etc.)

Tu FOURNIS : (1) une liste des AIDES IDENTIFIÉES adaptées au profil, (2) les CRITÈRES D'ÉLIGIBILITÉ avec mention du profil,
(3) les MONTANTS et MODALITÉS, (4) les SOURCES OFFICIELLES (titre + URL), (5) un DISCLAIMER final

Contraintes :
- Ne pas donner de conseil personnalisé.
- Si la demande n'est PAS du périmètre des aides publiques,
 renvoie handoff.needed=true, target_agent ∈ {"fiscal","juridique","social","rh"},
 reason explicite, et laisse aides_identifiees/sources vides.
- Toujours répondre en JSON valide selon le schéma."""

# --- Définition des Outils ---
DATASTORE_AIDES = "projects/agent-gcp-f6005/locations/global/collections/default_collection/dataStores/datastore-aides_1761090553437_gcs_store"

# --- Configuration de génération ---
generate_content_config = types.GenerateContentConfig(
    temperature=0.2,
    top_p=0.95,
    seed=0,
    max_output_tokens=65535,
    safety_settings=[
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
    ],
    tools=[
        types.Tool(
            retrieval=types.Retrieval(
                vertex_ai_search=types.VertexAISearch(
                    datastore=DATASTORE_AIDES
                )
            )
        )
    ],
    system_instruction=types.Content(
        role="user",
        parts=[types.Part.from_text(text=SI_TEXT_AIDES)]
    )
)


@app.route("/query", methods=["POST"])
def query():
    """
    Endpoint pour traiter les requêtes utilisateur.
    """
    # Vérifier que le client est initialisé
    if client is None:
        print("Agent Aides: ERREUR - Client GenAI non initialisé")
        return jsonify({
            "error": "Erreur serveur: Client IA non initialisé"
        }), 500

    data = request.get_json()
    if not data or "user_query" not in data:
        return jsonify({"error": "Missing 'user_query' in JSON payload"}), 400

    user_query = data["user_query"]
    company_info = data.get("company_info", {})

    print(f"Agent Aides: Requête reçue: {user_query}")

    # Si des infos entreprise sont fournies, les afficher
    if company_info:
        print(f"Agent Aides: Informations entreprise reçues:")
        print(f"  - Nom: {company_info.get('nom', 'N/A')}")
        print(f"  - Localisation: {company_info.get('localisation', {}).get('ville', 'N/A')}")
        print(f"  - Taille: {company_info.get('taille', 'N/A')}")
        print(f"  - Secteur: {company_info.get('secteur_activite', 'N/A')}")

    # Enrichir la requête utilisateur avec les infos de l'entreprise
    enriched_query = user_query
    if company_info:
        context_entreprise = f"""
CONTEXTE DE L'ENTREPRISE :
- Nom: {company_info.get('nom', 'Non spécifié')}
- Localisation: {company_info.get('localisation', {}).get('ville', 'Non spécifié')} ({company_info.get('localisation', {}).get('code_postal', 'N/A')})
- Région/Département: Déterminé par le code postal
- Taille de l'entreprise: {company_info.get('taille', 'Non spécifié')}
- Secteur d'activité: {company_info.get('secteur_activite', 'Non spécifié')}
- Forme juridique: {company_info.get('forme_juridique', 'Non spécifié')}
- Date de création: {company_info.get('date_creation', 'Non spécifié')}

QUESTION DE L'UTILISATEUR :
{user_query}

INSTRUCTIONS :
Utilisez ces informations pour identifier les aides publiques les plus pertinentes pour cette entreprise.
Considérez la localisation (région, département), la taille (TPE/PME/ETI), le secteur d'activité et la nature du projet mentionné dans la question.
"""
        enriched_query = context_entreprise

    # Préparer le contenu de la requête
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=enriched_query)]
        ),
    ]

    try:
        # Appel de Gemini avec RAG
        print(f"Agent Aides: Appel de Gemini avec RAG...")
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=generate_content_config,
        )

        print(f"Agent Aides: Réponse reçue de Gemini.")

        # Nettoyer la sortie de Gemini pour s'assurer que c'est du JSON valide
        json_response_text = response.text.strip()

        # Retirer les balises markdown si présentes
        if json_response_text.startswith("```json"):
            json_response_text = json_response_text[7:]
        if json_response_text.startswith("```"):
            json_response_text = json_response_text[3:]
        if json_response_text.endswith("```"):
            json_response_text = json_response_text[:-3]

        json_response_text = json_response_text.strip()

        # Vérifier que c'est du JSON valide
        try:
            json_data = json.loads(json_response_text)
            print(f"Agent Aides: Réponse JSON valide")
        except json.JSONDecodeError as e:
            print(f"Agent Aides: Réponse n'est pas du JSON valide: {e}")
            print(f"Agent Aides: Réponse brute: {json_response_text[:200]}...")
            # Retourner quand même la réponse brute
            json_data = {"reponse_brute": json_response_text}

        # Renvoyer le JSON à l'Orchestrateur
        return jsonify(json_data), 200

    except Exception as e:
        print(f"Erreur lors de la génération de contenu: {e}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500


@app.route("/health", methods=["GET"])
def health():
    """
    Endpoint de santé pour Cloud Run.
    """
    return jsonify({"status": "healthy"}), 200


# Point d'entrée pour Gunicorn (utilisé par Cloud Run)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
