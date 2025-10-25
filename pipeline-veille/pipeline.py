import os
from typing import List, Dict

import functions_framework
from google.cloud import firestore

# Import des modules ETL
from extract import ContentExtractor
from load import PipelineLoader
from transform import ContentProcessor


class VeillePipeline:
    """Pipeline complet de veille réglementaire avec architecture ETL."""

    def __init__(self, project_id: str = None):
        """
        Args:
            project_id: ID du projet GCP (optionnel)
        """
        self.project_id = project_id or os.environ.get("PROJECT_ID")

        # Initialiser les composants du pipeline
        self.extractor = ContentExtractor()  # Utilise Custom Search API uniquement
        self.processor = ContentProcessor()
        # Utilise le PipelineLoader qui stocke en JSON dans Cloud Storage
        self.loader = PipelineLoader(project_id=self.project_id, gcs_bucket_name="documents-fiscaux-bucket")

        # Client Firestore pour lire les sources à surveiller
        if self.project_id:
            self.db = firestore.Client(project=self.project_id)
        else:
            self.db = firestore.Client()

    def obtenir_sources_a_surveiller(self) -> List[Dict]:
        """
        Lit la collection 'sources_a_surveiller' dans Firestore.

        Returns:
            Liste de dictionnaires contenant les sources à surveiller
        """
        print("\n Lecture des sources à surveiller...")

        sources_ref = self.db.collection("sources_a_surveiller")
        sources_docs = sources_ref.stream()

        sources = []
        for doc in sources_docs:
            source_data = doc.to_dict()
            source_data["id"] = doc.id
            sources.append(source_data)

        print(f" {len(sources)} source(s) trouvée(s)")
        return sources

    def traiter_source(self, source: Dict) -> int:
        """
        Traite une source complète : extraction via Custom Search API, transformation et chargement.

        Args:
            source: Dictionnaire contenant les informations de la source
                    Doit contenir : id, keywords (ou description), url_base (optionnel), categorie

        Returns:
            Nombre de documents créés et chargés
        """
        source_id = source.get("id", "unknown")

        print("\n" + "=" * 80)
        print(f"📋 TRAITEMENT DE LA SOURCE: {source_id}")
        print("=" * 80)

        # PHASE 1: EXTRACT - Extraire via Custom Search API
        print("\n🔍 PHASE 1: EXTRACTION (Custom Search API)")
        documents_extraits = self.extractor.extraire_pour_source(source)

        if not documents_extraits:
            print(f"⚠️ Aucun document extrait pour {source_id}")
            return 0

        print(f"✅ {len(documents_extraits)} document(s) extrait(s)")

        # PHASE 2: TRANSFORM - Traiter les documents
        print("\n🔄 PHASE 2: TRANSFORMATION")
        documents_traites = []
        for doc_extrait in documents_extraits:
            docs_transformes = self.processor.traiter_document(doc_extrait)
            if docs_transformes:
                documents_traites.extend(docs_transformes)

        if not documents_traites:
            print(f"⚠️ Aucun document traité pour {source_id}")
            return 0

        print(f"✅ {len(documents_traites)} document(s) traité(s)")

        # PHASE 3: LOAD - Charger en JSON dans Cloud Storage
        print("\n💾 PHASE 3: CHARGEMENT (Cloud Storage JSON)")

        # Supprimer les anciens documents de cette source
        url_base = source.get("url_base", "")
        if url_base:
            self.loader.supprimer_anciens_documents(url_base)

        documents_charges = self.loader.charger_documents(documents_traites)

        print("\n" + "=" * 80)
        print(f"✅ SOURCE {source_id} TRAITÉE: {documents_charges} document(s) chargé(s)")
        print("=" * 80)

        return documents_charges

    def executer(self) -> Dict:
        """
        Exécute le pipeline complet pour toutes les sources.

        Returns:
            Dictionnaire avec les statistiques d'exécution
        """
        print("\n" + "🚀" * 40)
        print("DÉMARRAGE DU PIPELINE DE VEILLE RÉGLEMENTAIRE")
        print("🚀" * 40)

        # Obtenir les sources à surveiller
        sources = self.obtenir_sources_a_surveiller()

        if not sources:
            print("\n  Aucune source à surveiller trouvée dans Firestore")
            return {
                "status": "warning",
                "message": "Aucune source à surveiller",
                "sources_traitees": 0,
                "documents_crees": 0
            }

        # Traiter chaque source
        total_documents = 0
        sources_reussies = 0

        for i, source in enumerate(sources, 1):
            print(f"\n\n{'=' * 80}")
            print(f"SOURCE {i}/{len(sources)}")
            print(f"{'=' * 80}")

            try:
                documents_count = self.traiter_source(source)
                total_documents += documents_count
                if documents_count > 0:
                    sources_reussies += 1
            except Exception as e:
                print(f"\n Erreur lors du traitement de la source {source.get('id')}: {e}")
                continue

        # Résumé final
        print("\n\n" + "🎉" * 40)
        print("PIPELINE TERMINÉ")
        print("🎉" * 40)
        print(f"\n RÉSUMÉ:")
        print(f"   Sources traitées avec succès: {sources_reussies}/{len(sources)}")
        print(f"   Total de documents créés: {total_documents}")

        # Obtenir les statistiques finales de la base
        stats_finales = self.loader.obtenir_statistiques()

        return {
            "status": "success",
            "message": "Pipeline exécuté avec succès",
            "sources_traitees": sources_reussies,
            "sources_total": len(sources),
            "documents_crees": total_documents,
            "statistiques_base": stats_finales
        }


# Fonction Cloud Function pour déploiement
@functions_framework.http
def surveiller_sites(request):
    """
    Point d'entrée pour Cloud Functions.
    Exécute le pipeline de veille réglementaire.
    """
    try:
        # Créer et exécuter le pipeline
        pipeline = VeillePipeline()
        resultat = pipeline.executer()

        return resultat, 200

    except Exception as e:
        print(f"\n ERREUR CRITIQUE: {e}")
        return {
            "status": "error",
            "message": f"Erreur lors de l'exécution du pipeline: {str(e)}"
        }, 500


# Fonction pour exécution locale
def executer_pipeline_local():
    """
    Exécute le pipeline localement pour tests.
    """
    pipeline = VeillePipeline()
    resultat = pipeline.executer()
    return resultat


if __name__ == "__main__":
    print("Exécution locale du pipeline...")
    print("Note: Nécessite des credentials GCP configurés et une collection 'sources_a_surveiller' dans Firestore")

    try:
        resultat = executer_pipeline_local()
        print("\n Exécution terminée")
        print(f"Résultat: {resultat}")
    except Exception as e:
        print(f"\n Erreur: {e}")
