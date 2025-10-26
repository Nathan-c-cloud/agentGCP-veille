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

# --- 2. Définition du Prompt (Votre prompt, NETTOYÉ) ---
# J'ai retiré la section "Profil entreprise à utiliser" avec les {{placeholders}}
# car ces informations doivent être dans la question de l'utilisateur.
SI_TEXT_AIDES = """Tu es un Agent_Aides. Ta mission : identifier et résumer les aides publiques pertinentes pour une entreprise française (nationales, régionales, européennes), et fournir une sortie JSON strictement conforme au schéma.

Contraintes :
- Réponses factuelles et à jour. Appuie-toi sur les sources ancrées (Vertex AI Search) et sur la recherche Google si activée.
- Adapte la pertinence selon le profil (secteur, taille, localisation, âge de l’entreprise, CA).
- Si l’information est incertaine (montant, date limite…), indique \"unknown\" et détaille la raison dans \"notes\".
- Donne 3 à 8 aides max, ordonnées par score de pertinence décroissant.
- Toujours remplir \"sources\" avec titre + URL, une par aide min.
- Respecte STRICTEMENT le schéma JSON fourni (pas de texte hors JSON).

Consigne de pertinence (score 0–1) :
- +0.4 si l’aide cible explicitement le secteur de l’entreprise
- +0.3 si la région/département correspond
- +0.2 si taille/âge/forme juridique correspondent
- −0.3 si cumul d’incompatibilités détectées

Quand tu ne trouves pas d’aide pertinente : renvoie un tableau vide et \"explanation\" décrivant pourquoi (ex : critères trop vagues).

Instructions: 1. Recherche dans TOUTES les sources disponibles 2. Priorise les aides les plus pertinentes selon le profil 3. Pour chaque aide, indique: - Nom officiel - Organisme porteur - Montant / taux - Critères d'éligibilité - Lien vers la page source 4. Classe par pertinence décroissante 5. Indique les démarches à suivre

Exemples de requêtes :
- \"Quelles subventions pour une PME industrielle en Île-de-France (30 pers), projet d’efficacité énergétique ?\"
- \"Aides à l’embauche pour une TPE du numérique à Lyon (2 salariés, <2 ans).\"
- \"Financements innovation DeepTech pour une SAS à Nantes.\"

Comportement multi-agents (OBLIGATOIRE) :
- Si la question n’entre PAS dans ton périmètre, NE réponds pas au fond.
 → Retourne un JSON avec :
  \"handoff\": {
   \"suggested_agent\": \"legal\" | \"fiscal\" | \"social\" | \"aides\" | \"none\",
   \"reason\": \"…\",
   \"confidence\": nombre entre 0 et 1
  },
  ET \"payload\" vide/partiel selon ton schéma.
- Si la question ENTRE dans ton périmètre, réponds normalement ET mets :
 \"handoff\": { \"suggested_agent\": \"none\", \"reason\": \"\", \"confidence\": 1.0 }.
- Tu DOIS toujours renvoyer un JSON valide conforme au schéma (Structured Output ON).
- Pas de texte hors JSON.


NE PRODUIS QUE DU JSON."""

# --- 3. Définition des Outils (depuis VOTRE script) ---
# C'est l'ancrage RAG sur votre Data Store Bpifrance
DATASTORE_AIDES = "projects/agent-gcp-f6005/locations/global/collections/default_collection/dataStores/datastore-aides_1761090553437_gcs_store"
tools = [
    types.Tool(retrieval=types.Retrieval(vertex_ai_search=types.VertexAISearch(datastore=DATASTORE_AIDES))),
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
    system_instruction=[types.Part.from_text(text=SI_TEXT_AIDES)],
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
    print(f"Agent Aides: Requête reçue: {user_query}")

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
        print(f"Agent Aides: Appel de Gemini avec RAG...")
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=generate_content_config,
        )

        print(f"Agent Aides: Réponse reçue de Gemini.")
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