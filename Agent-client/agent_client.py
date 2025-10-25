"""
Agent Client V2 - Routeur d'agents
Version optimisée pour le routage + génération avec contexte.
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
db = firestore.Client()  # (optionnel, non utilisé ici)
model = GenerativeModel("gemini-2.0-flash")



# --- Agents disponibles ---
AGENTS_DISPONIBLES = [
    "fiscalite",
    "comptabilite",
    "ressources_humaines",
    "support_technique",
    "non_pertinent"
]

# --- Prompts ---
PROMPT_CLASSIF = """
Tu es un classificateur.
Parmi la liste suivante: {agents}
Pour la question: "{q}"
Réponds STRICTEMENT par un seul mot, exactement égal à l’un des éléments de la liste ci-dessus.
Si aucun ne convient, réponds: non_pertinent
"""

PROMPT_SYSTEME = """
Tu es l'Agent Client, un LLM central jouant le rôle d'orchestrateur intelligent entre plusieurs agents spécialisés
(fiscal, comptable, administratif, juridique, intégrateur, conseiller, etc.).

TA MISSION :
- Comprendre la demande du client.
- Identifier quel(s) agent(s) spécialisé(s) sont les plus pertinents pour y répondre.
- Formuler des requêtes claires et contextualisées à ces agents.
- Synthétiser et restituer la réponse finale au client de manière cohérente, fluide et professionnelle.

RÈGLES STRICTES :
1. Ne formule pas toi-même une réponse d'expert si elle doit provenir d’un autre agent.
2. Si une demande nécessite plusieurs agents, coordonne leur exécution et fusionne leurs résultats.
3. Si aucune information n’est disponible ou si aucun agent n’est compétent, réponds :
   "Je n’ai pas trouvé cette information dans ma base de connaissances actuelle."
4. Cite toujours la ou les sources des informations (titre et URL) lorsque tu t’appuies sur des documents de contexte.
5. Sois précis, clair, professionnel et structuré dans tes réponses au client.
6. Si plusieurs agents te transmettent des informations complémentaires, synthétise-les avec cohérence et logique métier.
7. Maintiens un ton empathique et humain.

BUT FINAL :
Assurer une expérience fluide, fiable et transparente.

---

CONTEXTE DOCUMENTAIRE :
{contexte}

QUESTION DE L'UTILISATEUR :
{question}

LISTE DES AGENTS DISPONIBLES :
{agents}

RÉPONSE :
"""

def classifier_intention(question: str) -> str:
    print(f"\n🧠 Classification de l'intention pour : '{question}'")
    prompt = PROMPT_CLASSIF.format(
        agents=", ".join(AGENTS_DISPONIBLES),
        q=question.replace('"', "'")
    )
    try:
        response = model.generate_content(prompt)
        agent_cible = (response.text or "").strip().lower()
        if agent_cible not in AGENTS_DISPONIBLES:
            return "non_pertinent"
        print(f"✅ Agent cible identifié : {agent_cible}")
        return agent_cible
    except Exception as e:
        print(f"❌ Erreur lors de la classification : {e}")
        return "erreur_interne"


def llm_route(question: str, registry: Dict[str, Dict]) -> Tuple[Optional[str], float, str]:
    """
    Classement LLM : demande à Gemini de choisir l'agent. Renvoie (agent, confidence, reason).
    """
    labels = [
        {"id": a, "name": meta["display_name"], "desc": meta.get("description", "")}
        for a, meta in registry.items()
    ]
    if not labels:
        return None, 0.0, "Aucun agent disponible dans le registre."

    sys = (
        "Tu es un routeur d'intentions. Choisis **un seul** agent parmi la liste.\n"
        "Réponds **exclusivement** en JSON strict: {\"agent\":\"id\",\"confidence\":0-1,\"reason\":\"...\"}.\n"
        "Si aucun ne convient, utilise agent=\"none\" et confidence proche de 0."
    )
    catalog = "\n".join([f"- id={x['id']} | {x['name']}: {x['desc']}" for x in labels])
    prompt = f"""{sys}

Catalogue:
{catalog}

Question:
{question}
"""

    try:
        resp = llm.generate_content(prompt)
        txt = (resp.text or "").strip()
        # Rattrapage: extraire JSON
        start = txt.find("{")
        end = txt.rfind("}")
        if start >= 0 and end > start:
            txt = txt[start:end+1]
        data = json.loads(txt)
        agent = data.get("agent")
        conf = float(data.get("confidence", 0.0))
        reason = data.get("reason", "")
        if agent == "none":
            return None, conf, reason
        if agent not in registry:
            return None, conf, f"Agent '{agent}' inconnu. {reason}"
        return agent, conf, reason
    except Exception as e:
        return None, 0.0, f"Erreur LLM: {e}"

def choose_agent(question: str, registry: Dict[str, Dict]) -> Dict:
    """
    Choix final de l'agent : règles d'abord, LLM ensuite si nécessaire.
    Retourne un dict avec agent_id, confidence, method, debug.
    """
    # 1) Règles rapides
    rules_agent, rules_conf, rules_detail = rules_score(question, registry)

    # Si assez bon, on route tout de suite
    if rules_agent and rules_conf >= ROUTING_CONFIDENCE_GOOD:
        return {
            "agent_id": rules_agent,
            "confidence": round(rules_conf, 3),
            "method": "rules",
            "debug": {"rules_points": rules_detail}
        }

    # 2) LLM pour départager / sauver un cas ambigü
    llm_agent, llm_conf, llm_reason = llm_route(question, registry)

    # Fusion simple : on garde le meilleur score
    cand = []
    if rules_agent:
        cand.append(("rules", rules_agent, rules_conf))
    if llm_agent:
        cand.append(("llm", llm_agent, llm_conf))

    if not cand:
        # Rien trouvé
        return {
            "agent_id": None,
            "confidence": 0.0,
            "method": "none",
            "debug": {"rules_points": rules_detail, "llm_reason": llm_reason}
        }

    best = max(cand, key=lambda x: x[2])
    method, agent_id, conf = best

    return {
        "agent_id": agent_id,
        "confidence": round(conf, 3),
        "method": method,
        "debug": {
            "rules_points": rules_detail,
            "llm_reason": llm_reason
        }
    }

def forward_to_agent(endpoint_url: str, question: str, routing_meta: Dict]) -> Tuple[int, Dict]:
    """
    Appelle l'agent cible en POST JSON.
    Retourne (status_code, payload_json)
    """
    payload = {
        "question": question,
        "router": {
            "selected_agent": routing_meta.get("agent_id"),
            "confidence": routing_meta.get("confidence"),
            "method": routing_meta.get("method"),
            "debug": routing_meta.get("debug", {})
        }
    }
    r = requests.post(
        endpoint_url,
        json=payload,
        timeout=ROUTING_TIMEOUT_SEC,
        headers={"Content-Type": "application/json"}
    )
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text}

def extraire_mots_cles(question: str) -> List[str]:
    mots_vides = {
        'le','la','les','un','une','des','de','du','au','aux',
        'et','ou','mais','donc','or','ni','car',
        'je','tu','il','elle','nous','vous','ils','elles',
        'mon','ma','mes','ton','ta','tes','son','sa','ses',
        'ce','cet','cette','ces','qui','que','quoi','dont','où',
        'est','sont','être','avoir','faire',
        'pour','dans','sur','avec','sans','sous','par',
        'quel','quelle','quels','quelles','comment','combien','pourquoi','quand',
        'c','qu','d','l','s','t','n','m'
    }
    question_lower = question.lower()
    mots = question_lower.split()
    mots_cles = []
    for mot in mots:
        mot_clean = ''.join(
            c for c in mot
            if c.isalnum() or c in ['é','è','ê','à','â','ù','û','ô','î','ç']
        )
        if mot_clean and mot_clean not in mots_vides and len(mot_clean) >= 3:
            mots_cles.append(mot_clean)
    return mots_cles

def generer_reponse(question: str, contexte: str) -> str:
    print(f"\n🤖 Génération de la réponse avec le modèle LLM...")
    prompt = PROMPT_SYSTEME.format(
        contexte=contexte,
        question=question,
        agents=", ".join(AGENTS_DISPONIBLES)
    )
    response = model.generate_content(prompt)
    return (response.text or "").strip()

def rechercher_chunks(question: str):
    """Stub local pour tests."""
    return [{
        "id": "chunk-1",
        "texte": "La TVA est une taxe sur la valeur ajoutée appliquée aux biens et services en France.",
        "source": "Guide TVA",
        "url": "https://example.com/guide-tva"
    }]

def construire_contexte(chunks):
    parts = []
    for c in chunks:
        texte = c.get("texte", "")
        source = c.get("source", "inconnue")
        url = c.get("url", "")
        parts.append(f"Source: {source} - URL: {url}\n{texte}")
    return "\n\n".join(parts)

@functions_framework.http
def agent_routeur(request):
    """Point d'entrée HTTP de l'Agent Routeur."""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

    if request.method == "OPTIONS":
        return ("", 204, headers)

    try:
        request_json = request.get_json(silent=True) or {}
        question = request_json.get('question')
        if not question:
            return jsonify({"error": "Missing 'question' in request body"}), 400, headers

        print("\n" + "="*80)
        print(f"📨 Question reçue par le Routeur : {question}")
        print("="*80)

        # ÉTAPE 1: Classifier l'intention
        agent_cible = classifier_intention(question)
        
        # ÉTAPE 2: Retourner le résultat de la redirection
        
        # L'URL/nom de l'agent réel (à adapter à votre architecture de déploiement)
        # Ex: Remplacer "fiscalite" par l'URL de l'Agent Fiscal
        

        routes = {
            "fiscalite": "/cloud-function-url/agent_fiscal",
            "comptabilite": "/cloud-function-url/agent_comptable",
            "ressources_humaines": "/cloud-function-url/agent_rh",
            "support_technique": "/cloud-function-url/agent_support",
            "non_pertinent": "N/A",
            "erreur_interne": "N/A"
        }
        destination_url = routes.get(agent_cible, "N/A")

        # (Optionnel) construire un contexte minimal depuis une recherche
        chunks = rechercher_chunks(question)
        contexte = construire_contexte(chunks) if chunks else ""

        return jsonify({
            "question": question,
            "agent": agent_cible,
            "destination_url": destination_url,
            "mots_cles": extraire_mots_cles(question),
            "contexte_extrait": contexte[:500]  # aperçu
        }), 200, headers

    except Exception as e:
        print(f"❌ Erreur serveur: {e}")
        return jsonify({"error": "internal_error", "details": str(e)}), 500, headers

if __name__ == "__main__":
    # Test local
    print("Test local de l'agent client V2...")
    question_test = "C'est quoi la TVA ?"
    chunks = rechercher_chunks(question_test)
    contexte = construire_contexte(chunks) if chunks else ""
    print("Agent prédit:", classifier_intention(question_test))
    print("Contexte aperçu:\n", contexte[:200])
