"""
Script de test complet pour l'agent client orchestrateur
"""
import os
os.environ["PROJECT_ID"] = "agent-gcp-f6005"

from agent_client import classifier_question, appeler_agent_specialise

def test_classification_et_appel():
    """
    Test complet : classification + appel de chaque agent
    """

    questions_test = [
        ("C'est quoi la TVA ?", "fiscalite"),
        ("Comment calculer l'impôt sur les sociétés ?", "fiscalite"),
        ("Quelles sont les aides pour une PME innovante ?", "aides"),
        ("Comment créer une SAS ?", "juridique"),
        ("Quels sont les statuts juridiques pour une startup ?", "juridique"),
        ("Subventions pour l'innovation en France", "aides"),
    ]

    print("🧪 TEST COMPLET DE L'AGENT CLIENT ORCHESTRATEUR")
    print("=" * 100)

    resultats = []

    for question, agent_attendu in questions_test:
        print(f"\n{'='*100}")
        print(f"📝 Question : {question}")
        print(f"🎯 Agent attendu : {agent_attendu}")
        print(f"{'='*100}")

        # ÉTAPE 1: Classification
        agent_obtenu, confiance = classifier_question(question)

        classification_ok = agent_obtenu == agent_attendu
        print(f"\n{'✅' if classification_ok else '❌'} Classification : {agent_obtenu} (confiance: {confiance:.2f})")
        if not classification_ok:
            print(f"   ⚠️ Attendu: {agent_attendu}, Obtenu: {agent_obtenu}")

        # ÉTAPE 2: Appel de l'agent spécialisé
        reponse = appeler_agent_specialise(agent_obtenu, question)

        # Vérifier la réponse
        appel_ok = "reponse" in reponse and len(reponse["reponse"]) > 0
        erreur = "erreur" in reponse

        print(f"\n{'✅' if appel_ok else '❌'} Appel agent : {'OK' if appel_ok else 'ÉCHEC'}")

        if erreur:
            print(f"   ❌ Erreur: {reponse['erreur']}")
        if "reponse" in reponse:
            reponse_text = reponse['reponse']
            print(f"   💬 Réponse ({len(reponse_text)} caractères) : {reponse_text[:150]}...")
        if "sources" in reponse:
            print(f"   📚 Sources: {len(reponse['sources'])} document(s)")

        resultats.append({
            "question": question,
            "agent_attendu": agent_attendu,
            "agent_obtenu": agent_obtenu,
            "classification_ok": classification_ok,
            "appel_ok": appel_ok,
            "erreur": erreur
        })

    # RÉSUMÉ FINAL
    print("\n" + "="*100)
    print("📊 RÉSUMÉ DES TESTS")
    print("="*100)

    total = len(resultats)
    classifications_ok = sum(1 for r in resultats if r["classification_ok"])
    appels_ok = sum(1 for r in resultats if r["appel_ok"])
    erreurs = sum(1 for r in resultats if r["erreur"])

    print(f"\n✅ Classifications correctes : {classifications_ok}/{total} ({100*classifications_ok/total:.0f}%)")
    print(f"✅ Appels réussis : {appels_ok}/{total} ({100*appels_ok/total:.0f}%)")
    print(f"❌ Erreurs : {erreurs}/{total}")

    print("\n📋 Détails par question :")
    for r in resultats:
        status = "✅" if r["classification_ok"] and r["appel_ok"] else "❌"
        print(f"  {status} {r['question'][:60]:60} -> {r['agent_obtenu']:15} {'(erreur)' if r['erreur'] else ''}")

    if classifications_ok == total and appels_ok == total and erreurs == 0:
        print("\n🎉 TOUS LES TESTS SONT PASSÉS !")
    else:
        print("\n⚠️ Certains tests ont échoué, voir les détails ci-dessus.")

if __name__ == "__main__":
    test_classification_et_appel()

