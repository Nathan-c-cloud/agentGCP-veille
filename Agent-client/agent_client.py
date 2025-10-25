"""
Agent Client - Orchestrateur intelligent pour routage vers agents spécialisés (v2)
- Classification robuste (JSON), température basse
- Normalisation stricte de la sortie du LLM
- Retries avec backoff sur les appels d'agents
- CORS complet
- (Option) Chargement dynamique des agents depuis Firestore si collection présente
"""

from __future__ import annotations

import os
import json
import time
import logging
import unicodedata
from typing import Dict, Tuple, Optional

import functions_framework
from flask import jsonify, Request
import requests

# --- Google Cloud ---
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

# =============================
# Configuration & initialisation
# =============================
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = os.environ.get("LOCATION", "us-west1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.0-flash-exp")

# Temps d'attente et retries pour appels sortants
HTTP_TIMEOUT_SECS = float(os.environ.get("HTTP_TIMEOUT_SECS", 30))
HTTP_MAX_RETRIES = int(os.environ.get("HTTP_MAX_RETRIES", 3))
HTTP_BACKOFF_BASE = float(os.environ.get("HTTP_BACKOFF_BASE", 0.75))

# CORS
CORS_ALLOW_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")

# Logging
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("agent-client")

# Vertex init (effectué au cold start)
vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel(MODEL_NAME)

# Firestore client (lazy)
_db: Optional[firestore.Client] = None

def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID)
    return _db

# ===================
# Agents (static base)
# ===================
DEFAULT_AGENTS_CONFIG: Dict[str, Dict[str, Optional[str]]] = {
    "fiscalite": {
        "url": "https://us-west1-agent-gcp-f6005.cloudfunctions.net/agent-fiscal-v2",
        "description": "Questions sur la fiscalité (TVA, IS, IR, CFE, taxes, impôts)",
        "enabled": True,
    },
    "comptabilite": {
        "url": None,
        "description": "Questions sur la comptabilité, bilans, comptes",
        "enabled": False,
    },
    "ressources_humaines": {
        "url": None,
        "description": "Questions sur les RH, contrats, paie, social",
        "enabled": False,
    },
    "juridique": {
        "url": None,
        "description": "Questions juridiques, droit des sociétés",
        "enabled": False,
    },
}

# (Optionnel) nom de collection Firestore pour surcharger la config
FIRESTORE_AGENTS_COLLECTION = os.environ.get("FIRESTORE_AGENTS_COLLECTION", "agents")


def load_agents_config() -> Dict[str, Dict[str, Optional[str]]]:
    """Charge la configuration des agents depuis Firestore si dispo, sinon fallback sur DEFAULT_AGENTS_CONFIG.
    Attendu (par doc): doc.id = nom_agent, champs = {url:str, description:str, enabled:bool}
    """
    try:
        db = get_db()
        col = db.collection(FIRESTORE_AGENTS_COLLECTION)
        docs = list(col.stream())
        if not docs:
            return DEFAULT_AGENTS_CONFIG
        cfg: Dict[str, Dict[str, Optional[str]]] = {}
        for d in docs:
            data = d.to_dict() or {}
            cfg[d.id] = {
                "url": data.get("url"),
                "description": data.get("description"),
                "enabled": bool(data.get("enabled", False)),
            }
        # Conserver les clés connues même si non présentes en DB
        for k, v in DEFAULT_AGENTS_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception as e:
        log.warning("Agents config: fallback to default due to: %s", e)
        return DEFAULT_AGENTS_CONFIG


# ======================
# Classification helpers
# ======================
PROMPT_CLASSIFICATION_JSON = (
    """
Tu es un routeur qui classe la question utilisateur vers un agent spécialisé.

AGENTS DISPONIBLES STRICTS (valeurs possibles pour "agent") :
- fiscalite
- comptabilite
- ressources_humaines
- juridique
- non_pertinent

INSTRUCTIONS:
1) Réponds en JSON strict: {"agent": "<une_valeur_ci-dessus>"}
2) Aucune autre clé, pas de commentaire, pas de texte hors JSON.
3) Si la question touche à TVA, impôts, IS/IR, CFE, taxes => "fiscalite".
4) Comptabilité (bilans, écritures, comptes) => "comptabilite".
5) RH (contrats de travail, paie, congés, droit du travail) => "ressources_humaines".
6) Droit des sociétés, contrats commerciaux => "juridique".
7) Sinon => "non_pertinent".

QUESTION: \n\n{question}\n
Réponds maintenant.
"""
)

def _normalize_label(label: str) -> str:
    # lower, strip, remove accents & quotes
    s = label.strip().lower().replace('\n', ' ').replace('"', '').replace("'", "")
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s


def classifier_question(question: str) -> Tuple[str, float]:
    """Classifie la question -> (agent, confiance 0..1)."""
    log.info("Classify question: %s", question[:400])
    try:
        resp = model.generate_content(
            PROMPT_CLASSIFICATION_JSON.format(question=question),
            generation_config=GenerationConfig(
                temperature=0.0,
                max_output_tokens=64,
            ),
            # Sur les modèles Gemini 1.5/2.0, on peut aussi fixer response_mime_type="application/json"
        )
        raw = (resp.text or "").strip()
        # Tente un parse JSON strict; si échec, extraire la première accolade
        agent = "non_pertinent"
        try:
            data = json.loads(raw)
            agent = _normalize_label(str(data.get("agent", "non_pertinent")))
        except Exception:
            # fallback minimaliste
            agent = _normalize_label(raw)
        allowed = {"fiscalite", "comptabilite", "ressources_humaines", "juridique", "non_pertinent"}
        if agent not in allowed:
            log.warning("LLM label out of set: %s", agent)
            # heuristique simple (mots-clés) en secours
            ql = _normalize_label(question)
            if any(k in ql for k in ["tva", "impot", "impôts", "is ", "ir ", "cfe", "tax"]):
                agent = "fiscalite"
            elif any(k in ql for k in ["bilans", "comptab", "ecriture", "grand livre", "pcg"]):
                agent = "comptabilite"
            elif any(k in ql for k in ["contrat", "paie", "conge", "droit du travail", "rh "]):
                agent = "ressources_humaines"
            elif any(k in ql for k in ["statuts", "greffe", "bsa", "pacte", "cession parts", "juridique"]):
                agent = "juridique"
            else:
                agent = "non_pertinent"
        # Confiance: haute si pas de fallback + label dans allowed et pas non_pertinent
        confidence = 0.9 if agent in {"fiscalite", "comptabilite", "ressources_humaines", "juridique"} else 0.7
        log.info("Agent identifié: %s (%.2f)", agent, confidence)
        return agent, confidence
    except Exception as e:
        log.exception("Classification error: %s", e)
        return "fiscalite", 0.3  # fallback vers fiscalité


# =============================
# HTTP utils & appels d'agent
# =============================

def _http_post_with_retries(url: str, payload: dict) -> requests.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            return requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=HTTP_TIMEOUT_SECS,
            )
        except requests.exceptions.Timeout as e:
            last_exc = e
            sleep_s = HTTP_BACKOFF_BASE * (2 ** (attempt - 1))
            log.warning("Timeout calling %s (attempt %d/%d) -> sleep %.2fs", url, attempt, HTTP_MAX_RETRIES, sleep_s)
            time.sleep(sleep_s)
        except Exception as e:
            last_exc = e
            log.warning("HTTP error calling %s (attempt %d/%d): %s", url, attempt, HTTP_MAX_RETRIES, e)
            sleep_s = HTTP_BACKOFF_BASE * (2 ** (attempt - 1))
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc


def appeler_agent_specialise(agent_name: str, question: str, agents_cfg: Dict[str, Dict[str, Optional[str]]]) -> Dict:
    cfg = agents_cfg.get(agent_name) or {}
    url = cfg.get("url")
    enabled = bool(cfg.get("enabled", False))

    if not enabled or not url:
        return {
            "erreur": f"L'agent '{agent_name}' n'est pas encore disponible.",
            "reponse": "Désolé, cette fonctionnalité n'est pas encore implémentée.",
        }

    try:
        resp = _http_post_with_retries(url, {"question": question})
        if resp.status_code == 200:
            data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
            # Normalise payload attendu
            return {
                "reponse": data.get("reponse") or data.get("answer") or "Aucune réponse générée",
                "sources": data.get("sources", []),
                "documents_trouves": data.get("documents_trouves", 0),
            }
        else:
            log.error("Agent %s -> HTTP %s: %s", agent_name, resp.status_code, resp.text[:500])
            return {
                "erreur": f"Erreur de l'agent : {resp.status_code}",
                "reponse": "Désolé, une erreur est survenue lors du traitement de votre demande.",
            }
    except Exception as e:
        log.exception("Erreur appel agent %s: %s", agent_name, e)
        return {"erreur": str(e), "reponse": "Désolé, une erreur technique est survenue."}


# ==================
# Flask entrypoint CF
# ==================
@functions_framework.http
def agent_client(request: Request):
    # CORS preflight
    if request.method == "OPTIONS":
        return (
            "",
            204,
            {
                "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "3600",
            },
        )

    headers = {"Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN}

    try:
        # Healthcheck basique
        if request.args and request.args.get("health", "").lower() in {"1", "true", "ok"}:
            return jsonify({"status": "ok", "model": MODEL_NAME}), 200, headers

        req_json = request.get_json(silent=True) or {}
        question = (req_json.get("question") or "").strip()
        if not question:
            return jsonify({"erreur": "Aucune question fournie. Format attendu: {\"question\": \"...\"}"}), 400, headers

        log.info("Question reçue: %s", question[:400])

        # 1) Charger la configuration des agents (DB -> fallback default)
        agents_cfg = load_agents_config()

        # 2) Classifier
        agent_cible, confiance = classifier_question(question)
        if agent_cible == "non_pertinent":
            return (
                jsonify(
                    {
                        "question": question,
                        "agent_utilise": "aucun",
                        "reponse": (
                            "Je ne suis pas sûr de comprendre votre question. "
                            "Pouvez-vous la reformuler en lien avec la fiscalité, la comptabilité, les RH ou le juridique ?"
                        ),
                        "confiance": confiance,
                    }
                ),
                200,
                headers,
            )

        # 3) Appeler l'agent
        reponse_agent = appeler_agent_specialise(agent_cible, question, agents_cfg)

        # Si non implémenté
        if reponse_agent.get("erreur") and reponse_agent.get("reponse") == "Désolé, cette fonctionnalité n'est pas encore implémentée.":
            # Indiquer l'agent fiscal comme dispo s'il l'est
            fiscal_enabled = bool(agents_cfg.get("fiscalite", {}).get("enabled", False) and agents_cfg.get("fiscalite", {}).get("url"))
            msg = (
                f"Je comprends que votre question concerne le domaine '{agent_cible}', "
                "mais cet agent n'est pas encore disponible. "
                + ("L'agent fiscal est opérationnel." if fiscal_enabled else "")
            )
            return jsonify({"question": question, "agent_utilise": agent_cible, "reponse": msg, "agent_disponible": False}), 200, headers

        # 4) Réponse finale
        return (
            jsonify(
                {
                    "question": question,
                    "agent_utilise": agent_cible,
                    "reponse": reponse_agent.get("reponse", "Aucune réponse générée"),
                    "sources": reponse_agent.get("sources", []),
                    "documents_trouves": reponse_agent.get("documents_trouves", 0),
                    "confiance": confiance,
                }
            ),
            200,
            headers,
        )

    except Exception as e:
        log.exception("Erreur globale: %s", e)
        return jsonify({"erreur": "Erreur interne du serveur", "details": str(e)}), 500, headers


# ======================
# Test local minimaliste
# ======================
if __name__ == "__main__":
    tests = [
        "C'est quoi la TVA ?",
        "Comment passer une écriture d'amortissement ?",
        "Puis-je licencier pendant une période d'essai ?",
        "Comment modifier les statuts d'une SAS ?",
        "Quel est votre couleur préférée ?",
    ]
    for q in tests:
        ag, conf = classifier_question(q)
        print(f"{q} -> {ag} ({conf:.2f})")
