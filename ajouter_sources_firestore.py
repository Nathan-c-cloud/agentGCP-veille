#!/usr/bin/env python3
"""
Script pour ajouter automatiquement les sources fiscales dans Firestore.
À exécuter dans Google Cloud Shell.

Usage:
    python3 ajouter_sources_firestore.py
"""

from google.cloud import firestore
from datetime import datetime


def ajouter_sources():
    """Ajoute les 10 sources fiscales essentielles dans Firestore."""

    # Initialiser le client Firestore
    # Dans Cloud Shell, les credentials sont automatiquement configurés
    db = firestore.Client()

    # Définir les 10 sources à ajouter
    sources = [
        {
            "id": "tva_taux_reduits",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23567",
            "description": "TVA - Taux réduits",
            "actif": True,
            "categorie": "fiscalite_tva",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "tva_declaration",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23566",
            "description": "TVA - Déclaration",
            "actif": True,
            "categorie": "fiscalite_tva",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "impot_societes",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23575",
            "description": "Impôt sur les sociétés (IS)",
            "actif": True,
            "categorie": "fiscalite_is",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "micro_entreprise_regime",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23267",
            "description": "Micro-entreprise - Régime fiscal",
            "actif": True,
            "categorie": "fiscalite_micro",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "cfe_cotisation",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23547",
            "description": "Cotisation foncière des entreprises (CFE)",
            "actif": True,
            "categorie": "fiscalite_locale",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "credit_impot_recherche",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23533",
            "description": "Crédit d'impôt recherche (CIR)",
            "actif": True,
            "categorie": "fiscalite_credits",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "exonerations_zones_franches",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F31149",
            "description": "Exonérations fiscales zones franches",
            "actif": True,
            "categorie": "fiscalite_exonerations",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "amortissement_materiel",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F31963",
            "description": "Amortissement du matériel",
            "actif": True,
            "categorie": "fiscalite_comptabilite",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "declaration_resultats",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F23570",
            "description": "Déclaration de résultats",
            "actif": True,
            "categorie": "fiscalite_declarations",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "regime_reel_imposition",
            "parseur": "service_public",
            "url_base": "https://entreprendre.service-public.fr/vosdroits/F32353",
            "description": "Régime réel d'imposition",
            "actif": True,
            "categorie": "fiscalite_regimes",
            "date_ajout": datetime.now().strftime("%Y-%m-%d")
        }
    ]

    # Référence à la collection
    collection_ref = db.collection("sources_a_surveiller")

    print("=" * 80)
    print("AJOUT DES SOURCES FISCALES DANS FIRESTORE")
    print("=" * 80)
    print(f"\nProjet: {db.project}")
    print(f"Collection: sources_a_surveiller")
    print(f"Nombre de sources à ajouter: {len(sources)}")
    print("\n" + "-" * 80)

    # Ajouter chaque source
    sources_ajoutees = 0
    sources_existantes = 0

    for i, source in enumerate(sources, 1):
        source_id = source.pop("id")  # Retirer l'ID des données

        try:
            # Vérifier si la source existe déjà
            doc_ref = collection_ref.document(source_id)
            doc = doc_ref.get()

            if doc.exists:
                print(f"\n[{i}/{len(sources)}] ⚠️  Source '{source_id}' existe déjà")
                print(f"         URL: {source['url_base']}")
                print(f"         Action: Ignorée (utilisez merge=True pour mettre à jour)")
                sources_existantes += 1
            else:
                # Ajouter la nouvelle source
                doc_ref.set(source)
                print(f"\n[{i}/{len(sources)}] ✅ Source '{source_id}' ajoutée avec succès")
                print(f"         Description: {source['description']}")
                print(f"         URL: {source['url_base']}")
                print(f"         Catégorie: {source['categorie']}")
                sources_ajoutees += 1

        except Exception as e:
            print(f"\n[{i}/{len(sources)}] ❌ Erreur pour '{source_id}': {e}")

    # Résumé
    print("\n" + "=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"✅ Sources ajoutées avec succès: {sources_ajoutees}")
    print(f"⚠️  Sources déjà existantes: {sources_existantes}")
    print(f"📊 Total dans la collection: {sources_ajoutees + sources_existantes}")

    if sources_ajoutees > 0:
        print("\n" + "=" * 80)
        print("PROCHAINE ÉTAPE")
        print("=" * 80)
        print("\nPour extraire le contenu de ces sources, exécutez le pipeline de veille:")
        print("\n  curl -X POST \"https://surveiller-sites-VOTRE_ID.us-west1.run.app\"")
        print("\nOu si vous l'avez déployé :")
        print("\n  gcloud functions call surveiller-sites --region=us-west1 --gen2")
        print("\nCela créera environ 70 chunks dans la collection 'documents_fiscaux_chunks'.")

    print("\n" + "=" * 80)
    print("✅ SCRIPT TERMINÉ")
    print("=" * 80)


if __name__ == "__main__":
    try:
        ajouter_sources()
    except Exception as e:
        print(f"\n❌ ERREUR CRITIQUE: {e}")
        print("\nAssurez-vous que :")
        print("  1. Vous êtes dans Google Cloud Shell")
        print("  2. Le projet est bien configuré (gcloud config set project VOTRE_PROJECT_ID)")
        print("  3. L'API Firestore est activée")
        print("  4. Vous avez les permissions nécessaires")
        import traceback

        traceback.print_exc()
