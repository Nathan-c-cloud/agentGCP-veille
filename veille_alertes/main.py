"""
Fonction Cloud automatique pour la veille réglementaire.
Version ultra-légère pour démarrage rapide.
"""
import functions_framework
from flask import jsonify


@functions_framework.http
def veille_automatique(request):
    """Analyse toutes les entreprises dans settings et crée des alertes."""

    # Support CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}

    # Imports lourds après le démarrage
    import os
    import requests
    from google.cloud import firestore

    PROJECT_ID = os.environ.get("PROJECT_ID", "agent-gcp-f6005")
    AGENT_FISCAL_URL = "https://us-west1-agent-gcp-f6005.cloudfunctions.net/agent-fiscal-v2"

    print("\n" + "=" * 80)
    print("🔍 LANCEMENT VEILLE AUTOMATIQUE")
    print("=" * 80)

    resultats = []
    total_alertes = 0

    try:
        # Connexion Firestore
        db = firestore.Client(project=PROJECT_ID)

        # Récupère toutes les entreprises
        settings_docs = db.collection('settings').stream()

        entreprises = list(settings_docs)
        nb_entreprises = len(entreprises)

        if nb_entreprises == 0:
            print("⚠️ Aucune entreprise trouvée")
            return jsonify({
                "succes": True,
                "message": "Aucune entreprise à analyser",
                "nbEntreprises": 0,
                "nbAlertesTotales": 0,
                "resultats": []
            }), 200, headers

        print(f"\n📊 {nb_entreprises} entreprise(s) à analyser\n")

        # Analyse chaque entreprise
        for i, doc in enumerate(entreprises, 1):
            company_id = doc.id
            settings = doc.to_dict()
            company_name = settings.get('company_info', {}).get('nom', 'N/A')

            print(f"\n[{i}/{nb_entreprises}] 🏢 {company_name} ({company_id})")

            try:
                # Appel de l'agent fiscal via HTTP
                print(f"📡 Appel API agent fiscal...")

                response = requests.post(
                    AGENT_FISCAL_URL,
                    json={"settings": settings},
                    timeout=90,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    resultat = response.json()
                    nb_alertes = resultat.get('nbAlertesCreees', 0)
                    total_alertes += nb_alertes

                    resultats.append({
                        "companyId": company_id,
                        "companyName": company_name,
                        "nbAlertes": nb_alertes,
                        "dateAnalyse": resultat.get('dateAnalyse'),
                        "status": "ok"
                    })

                    print(f"✅ {nb_alertes} alerte(s) créée(s)")
                else:
                    error_msg = f"HTTP {response.status_code}"
                    print(f"❌ Erreur API: {error_msg}")

                    resultats.append({
                        "companyId": company_id,
                        "companyName": company_name,
                        "nbAlertes": 0,
                        "status": "erreur",
                        "erreur": error_msg
                    })

            except requests.Timeout:
                print(f"❌ Timeout")
                resultats.append({
                    "companyId": company_id,
                    "companyName": company_name,
                    "nbAlertes": 0,
                    "status": "erreur",
                    "erreur": "Timeout API"
                })

            except Exception as e:
                print(f"❌ Erreur: {e}")
                resultats.append({
                    "companyId": company_id,
                    "companyName": company_name,
                    "nbAlertes": 0,
                    "status": "erreur",
                    "erreur": str(e)
                })

        # Résumé
        print(f"\n✅ TERMINÉ: {nb_entreprises} entreprises, {total_alertes} alertes")

        return jsonify({
            "succes": True,
            "message": f"Veille terminée pour {nb_entreprises} entreprise(s)",
            "nbEntreprises": nb_entreprises,
            "nbAlertesTotales": total_alertes,
            "resultats": resultats
        }), 200, headers

    except Exception as e:
        print(f"\n❌ ERREUR GLOBALE: {e}")

        return jsonify({
            "succes": False,
            "erreur": str(e),
            "nbEntreprises": 0,
            "nbAlertesTotales": 0,
            "resultats": []
        }), 500, headers

