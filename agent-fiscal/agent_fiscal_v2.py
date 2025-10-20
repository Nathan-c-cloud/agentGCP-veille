"""
Agent Fiscal V2 - Adapté pour utiliser la nouvelle collection de documents complets.
Version optimisée pour le RAG avec recherche sur documents sémantiques.
"""

import functions_framework
from flask import jsonify
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel
import os
from typing import List, Dict
import re  # Importation pour le nettoyage du contenu

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
LOCATION = "us-west1"

# --- Initialisation ---
vertexai.init(project=PROJECT_ID, location=LOCATION)
db = firestore.Client()
model = GenerativeModel("gemini-2.0-flash")

# --- Paramètres de recherche ---
MAX_DOCUMENTS = 4  # Nombre maximum de documents à récupérer

# --- Prompt système ---
PROMPT_SYSTEME = """Tu es un assistant fiscal expert spécialisé dans la fiscalité des PME françaises.

OBJECTIF : Fournir des réponses COURTES, CLAIRES et BIEN STRUCTURÉES.

RÈGLES STRICTES :
1. Base tes réponses EXCLUSIVEMENT sur les documents fournis.
2. Sois CONCIS : maximum 200 mots pour la réponse principale.
3. Structure ta réponse avec :
   - Un titre principal (##)
   - Une définition courte et claire
   - Des points clés en gras (**texte**)
   - Des listes à puces (-) pour les éléments multiples
4. Ne répète JAMAIS le contenu brut du contexte.
5. Synthétise intelligemment les informations.
6. À la fin, cite 1-2 sources maximum : [Titre](URL)

EXEMPLE DE BONNE RÉPONSE (COURTE ET STRUCTURÉE) :

## La TVA (Taxe sur la Valeur Ajoutée)

**Définition** : La TVA est un impôt indirect sur la consommation.

**Taux en France** :
- **20%** : Taux normal
- **10%** : Taux intermédiaire (restauration, travaux)
- **5,5%** : Taux réduit (produits de première nécessité)

**Qui est concerné** : Toutes les entreprises réalisant des ventes de biens ou services, sauf régime micro-entreprise sous certains seuils.

**Source** : [TVA - Service Public](https://entreprendre.service-public.fr/vosdroits/F23566)

---

CONTEXTE DOCUMENTAIRE :
{contexte}

QUESTION : {question}

RÉPONSE (COURTE ET STRUCTURÉE) :"""


def extraire_mots_cles(question: str) -> List[str]:
    """
    Extrait les mots-clés pertinents avec normalisation améliorée.
    """
    # Mots vides français
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

    # Normaliser
    question_lower = question.lower()

    # Remplacer les abréviations courantes
    question_lower = question_lower.replace("qw", "quoi").replace("qqw", "quoi")

    mots = question_lower.split()

    # Filtrer
    mots_cles = []
    for mot in mots:
        mot_clean = ''.join(c for c in mot if c.isalnum() or c in ['é', 'è', 'ê', 'à', 'â', 'ù', 'û', 'ô', 'î', 'ç'])

        # Garder les mots de 2 caractères ou plus (pour "is", "ir", "tva")
        if mot_clean and mot_clean not in mots_vides and len(mot_clean) >= 2:
            mots_cles.append(mot_clean)

    return mots_cles


def rechercher_documents(question: str, max_documents: int = MAX_DOCUMENTS) -> List[Dict]:
    """
    Recherche améliorée avec scoring plus flexible.
    """
    print(f"\n🔍 Recherche de documents pour : '{question}'")

    # Extraire les mots-clés
    mots_cles = extraire_mots_cles(question)
    print(f"   📋 Mots-clés extraits : {mots_cles}")

    if not mots_cles:
        print("    ⚠️ Aucun mot-clé pertinent trouvé")
        return []

    # Recherche dans Firestore
    collection_ref = db.collection("documents_fiscaux_complets")

    documents_trouves = []

    # Récupérer tous les documents
    all_documents = collection_ref.limit(500).stream()

    for doc in all_documents:
        doc_data = doc.to_dict()
        contenu = doc_data.get('contenu', '').lower()
        titre = doc_data.get('titre_source', '').lower()

        # Calculer un score avec pondération intelligente
        score = 0
        for mot_cle in mots_cles:
            # Super bonus si dans le titre
            if mot_cle in titre:
                score += 10

            # Bonus pour occurrences dans le contenu
            occurrences = contenu.count(mot_cle)
            score += min(occurrences, 5)  # Limiter à 5 points max par mot

        if score > 0:
            doc_data['score'] = score
            documents_trouves.append(doc_data)

    # Trier par score
    documents_trouves.sort(key=lambda x: x['score'], reverse=True)

    # Limiter au nombre demandé
    documents_pertinents = documents_trouves[:max_documents]

    print(f"   ✅ {len(documents_pertinents)} document(s) trouvé(s)")
    for i, doc in enumerate(documents_pertinents, 1):
        print(f"      {i}. Score {doc['score']}: {doc.get('titre_source', 'Sans titre')[:60]}...")

    return documents_pertinents


def nettoyer_contenu(texte: str) -> str:
    """
    Nettoie le contenu en gardant SEULEMENT le texte utile et le formatage Markdown.
    """
    # Supprimer les références de citation entre crochets [Source](URL)
    texte = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', texte)

    # Supprimer les URLs complètes qui restent
    texte = re.sub(r'https?://[^\s\)]+', '', texte)

    # Supprimer les ### multiples (nettoyer les titres mal formés)
    texte = re.sub(r'#{4,}', '###', texte)

    # Limiter le contenu à 2000 caractères pour éviter les contextes trop longs
    if len(texte) > 2000:
        texte = texte[:2000] + "..."

    # Nettoyer les espaces multiples
    texte = re.sub(r'\s+', ' ', texte).strip()

    return texte


def construire_contexte(documents: List[Dict]) -> str:
    """
    Construit le contexte textuel à partir des documents trouvés.

    Args:
        documents: Liste de documents pertinents

    Returns:
        Texte formaté du contexte
    """
    if not documents:
        return "Aucun document pertinent trouvé."

    contexte_parts = []

    for i, doc in enumerate(documents, 1):
        titre = doc.get('titre_source', 'Sans titre')
        url = doc.get('source_url', 'URL non disponible')
        contenu = doc.get('contenu', '')

        # Nettoyer le contenu avant de l'ajouter au contexte
        contenu_nettoye = nettoyer_contenu(contenu)

        contexte_parts.append(f"""
--- Document {i} ---
Titre: {titre}
Source: {url}
Contenu:
{contenu_nettoye}
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
    print(f"\n Génération de la réponse avec le modèle LLM...")

    # Construire le prompt complet
    prompt = PROMPT_SYSTEME.format(
        contexte=contexte,
        question=question
    )

    try:
        # Appeler le modèle
        response = model.generate_content(prompt)
        reponse_text = response.text

        print(f"   Réponse générée ({len(reponse_text)} caractères)")
        return reponse_text

    except Exception as e:
        print(f" Erreur lors de la génération : {e}")
        raise


@functions_framework.http
def agent_fiscal(request):
    """
    Point d'entrée de la Cloud Function.
    Reçoit une question et retourne une réponse basée sur les documents de la base de connaissances.
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
        print(f"\n{'=' * 80}")
        print(f" Question reçue : {question}")
        print(f"{'=' * 80}")

        # ÉTAPE 1: Rechercher les documents pertinents
        documents = rechercher_documents(question)

        if not documents:
            return jsonify({
                "question": question,
                "reponse": "Je n'ai pas trouvé d'information pertinente dans ma base de connaissances pour répondre à cette question.",
                "documents_trouves": 0
            }), 200, headers

        # ÉTAPE 2: Construire le contexte
        contexte = construire_contexte(documents)

        # ÉTAPE 3: Générer la réponse
        reponse = generer_reponse(question, contexte)

        # Retourner la réponse
        return jsonify({
            "question": question,
            "reponse": reponse,
            "documents_trouves": len(documents),
            "sources": [
                {
                    "titre": doc.get('titre_source'),
                    "url": doc.get('source_url')
                }
                for doc in documents[:3]  # Retourner les 3 sources principales
            ]
        }), 200, headers

    except Exception as e:
        print(f"\n ERREUR: {e}")
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
    documents = rechercher_documents(question_test)

    if documents:
        contexte = construire_contexte(documents)
        print(f"\nContexte construit ({len(contexte)} caractères)")
        print("\nPremiers 500 caractères du contexte:")
        print("-" * 80)
        print(contexte[:500])
        print("-" * 80)
    else:
        print("\n  Aucun document trouvé")
