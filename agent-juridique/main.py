import os
import json
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# --- 1. Initialisation du Client (depuis VOTRE script) ---
try:
    client = genai.Client(vertexai=True)
except Exception as e:
    print(f"Erreur init client genai: {e}")

# --- 2. Définition du Prompt (Votre prompt, CORRIGÉ) ---
# J'ai retiré {retrieved_context} et {user_query} car ils
# sont gérés automatiquement par les 'tools' et 'contents'.
SI_TEXT_JURIDIQUE = """Rôle : Assistant juridique d’information générale (France) pour PME et indépendants.
Vous êtes un assistant juridique spécialisé pour les PME françaises.
Votre mission est de répondre à la question de l'utilisateur en vous basant **exclusivement** sur les extraits de la doctrine (CNIL, Service-Public, bpi, etc) qui vous seront fournis par vos outils de recherche.

**Instructions strictes :**
1. Analysez la question de l'utilisateur.
2. Fondez votre réponse **uniquement** sur les informations présentes dans le contexte récupéré.
3. Si le contexte ne contient pas la réponse, ne tentez pas d'y répondre et indiquez "Je ne trouve pas cette information dans ma base de connaissances (CNIL, Service-Public, bpi, etc)."
4. Ne jamais utiliser vos connaissances générales.
5. Citez vos sources si possible en vous basant sur le contexte.
6. Répondez au format JSON structuré.

Tu FOURNIS : (1) une CHECKLIST opérationnelle , (2) la LISTE DES PIÈCES,
(3) les SOURCES OFFICIELLES listées dans les sources d'ancrage (titre + URL), (4) un DISCLAIMER final, (5) les fichiers utilisés dans sources d'ancrage

Contraintes :
- Ne pas donner de conseil personnalisé ni d’interprétation juridique.
- Si la demande n’est PAS du périmètre juridique (TVA, URSSAF, paie, aides),
 renvoie handoff.needed=true, target_agent ∈ {\"fiscal\",\"social\",\"aides\",\"rh\"},
 reason explicite, et laisse steps/docs/sources vides.
- Toujours répondre en JSON valide selon le schéma."""

# --- 3. Définition des Outils (depuis VOTRE script) ---
DATASTORE_JURIDIQUE = "projects/agent-gcp-f6005/locations/global/collections/default_collection/dataStores/datastore-juridique_1760818540958_gcs_store"
tools = [
    types.Tool(retrieval=types.Retrieval(vertex_ai_search=types.VertexAISearch(datastore=DATASTORE_JURIDIQUE))),
]

# --- 4. Définition de la Config (depuis VOTRE script) ---
generate_content_config = types.GenerateContentConfig(
    temperature=0.2,
    top_p=0.95,
    seed=0,
    max_output_tokens=65535,
    safety_settings=[types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="OFF"
    ), types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="OFF"
    ), types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="OFF"
    ), types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="OFF"
    )],
    tools=tools,
    system_instruction=[types.Part.from_text(text=SI_TEXT_JURIDIQUE)],
    thinking_config=types.ThinkingConfig(
        thinking_budget=-1,
    ),
)


# --- 5. L'endpoint API que votre Orchestrateur appellera ---
@app.route("/query", methods=["POST"])
def handle_query():
    data = request.get_json()
    if "user_query" not in data:
        return jsonify({"error": "Missing 'user_query' in JSON payload"}), 400

    user_query = data["user_query"]
    print(f"Agent Juridique: Requête reçue: {user_query}")

    # Le `contents` est maintenant dynamique, basé sur l'input de l'utilisateur
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_query)  # Utiliser la query de l'utilisateur
            ]
        ),
    ]

    try:
        # Nous utilisons generate_content (pas stream) pour une réponse API
        print(f"Agent Juridique: Appel de Gemini avec RAG...")
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=generate_content_config,
        )

        print(f"Agent Juridique: Réponse reçue de Gemini.")
        # Nettoyer la sortie de Gemini pour s'assurer que c'est du JSON valide
        json_response_text = response.text.strip().lstrip("```json").rstrip("```")

        # Renvoyer le JSON à l'Orchestrateur
        return json_response_text, 200, {'Content-Type': 'application/json'}

    except Exception as e:
        print(f"Erreur lors de la génération de contenu: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# Point d'entrée pour Gunicorn (utilisé par Cloud Run)
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))