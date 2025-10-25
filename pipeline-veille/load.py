import json
import os
from typing import List, Dict, Optional

from google.cloud import firestore, storage


class GoogleCloudStorageLoader:
    """Charge et supprime les documents (format JSON) dans Google Cloud Storage."""

    def __init__(self, bucket_name: str):
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(bucket_name)

    def charger_document(self, document_data: Dict) -> str:
        """
        Charge un document complet (métadonnées + contenu) en JSON sur GCS.

        Args:
            document_data: Dictionnaire contenant toutes les données du document.

        Returns:
            Le chemin GCS du fichier chargé.
        """
        document_id = document_data.get("document_id")
        if not document_id:
            raise ValueError("document_data doit contenir un 'document_id'")

        blob_name = f"documents/{document_id}.json"
        blob = self.bucket.blob(blob_name)

        # Convertir en JSON et uploader
        json_content = json.dumps(document_data, ensure_ascii=False, indent=2)
        blob.upload_from_string(json_content, content_type="application/json")

        print(f"  ✅ Document '{document_id}' chargé sur GCS: gs://{self.bucket.name}/{blob_name}")
        return f"gs://{self.bucket.name}/{blob_name}"

    def supprimer_document(self, document_id: str):
        """
        Supprime un document JSON de GCS.

        Args:
            document_id: L'ID du document à supprimer.
        """
        blob_name = f"documents/{document_id}.json"
        blob = self.bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
            print(f"  🗑️ Document '{document_id}' supprimé de GCS.")
        else:
            print(f"  ⚠️ Document '{document_id}' non trouvé sur GCS pour suppression.")

    def lire_document(self, document_id: str) -> Optional[Dict]:
        """
        Lit un document JSON complet depuis GCS.

        Args:
            document_id: L'ID du document à lire.

        Returns:
            Le dictionnaire du document ou None si non trouvé.
        """
        blob_name = f"documents/{document_id}.json"
        blob = self.bucket.blob(blob_name)
        if blob.exists():
            json_content = blob.download_as_text()
            return json.loads(json_content)
        return None


class PipelineLoader:
    """Charge les documents complets (métadonnées + contenu) dans Cloud Storage au format JSON."""

    def __init__(self, project_id: str = None, gcs_bucket_name: str = "documents-fiscaux-bucket"):
        if project_id:
            self.db = firestore.Client(project=project_id)
        else:
            self.db = firestore.Client()
        self.gcs_loader = GoogleCloudStorageLoader(bucket_name=gcs_bucket_name)
        self.gcs_bucket_name = gcs_bucket_name

    def charger_documents(self, documents: List[Dict]) -> int:
        """
        Charge les documents complets (métadonnées + contenu) en JSON dans GCS uniquement.
        Plus besoin de Firestore pour les métadonnées, tout est dans le JSON.

        Args:
            documents: Liste de dictionnaires représentant les documents complets.

        Returns:
            Nombre de documents chargés avec succès.
        """
        if not documents:
            print("  ⚠️ Aucun document à charger")
            return 0

        total = len(documents)
        print(f"\n💾 Chargement de {total} documents en JSON...")

        documents_charges = 0
        for i, doc_data in enumerate(documents):
            document_id = doc_data.get("document_id")

            if not document_id:
                print(f"  ⚠️ Document sans ID ignoré: {doc_data.get('source_url', 'URL inconnue')}")
                continue

            try:
                # Charger le document complet en JSON sur GCS
                gcs_path = self.gcs_loader.charger_document(doc_data)
                documents_charges += 1

            except Exception as e:
                print(f"  ❌ Erreur lors du chargement du document '{document_id}': {e}")
                continue

        print(f"\n✅ Chargement terminé : {documents_charges}/{total} documents traités avec succès")
        return documents_charges

    def supprimer_anciens_documents(self, source_url: str) -> int:
        """
        Supprime tous les documents JSON d'une source URL spécifique de GCS.
        Parcourt tous les fichiers JSON et supprime ceux qui correspondent à l'URL.
        """
        print(f"\n🗑️ Suppression des anciens documents de {source_url}...")

        bucket = self.gcs_loader.bucket
        blobs = bucket.list_blobs(prefix="documents/")

        count = 0
        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue

            try:
                # Lire le JSON pour vérifier l'URL source
                json_content = blob.download_as_text()
                doc_data = json.loads(json_content)

                if doc_data.get('source_url') == source_url:
                    blob.delete()
                    count += 1
                    print(f"  🗑️ Supprimé: {blob.name}")

            except Exception as e:
                print(f"  ⚠️ Erreur lors de la vérification de {blob.name}: {e}")
                continue

        print(f"  ✅ {count} anciens documents supprimés de GCS.")
        return count

    def obtenir_statistiques(self) -> Dict:
        """
        Obtient des statistiques en lisant tous les fichiers JSON dans GCS.
        """
        print("\n📊 Calcul des statistiques depuis Cloud Storage...")

        bucket = self.gcs_loader.bucket
        blobs = bucket.list_blobs(prefix="documents/")

        total_documents = 0
        sources_uniques = set()
        taille_totale = 0

        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue

            try:
                json_content = blob.download_as_text()
                doc_data = json.loads(json_content)

                total_documents += 1
                sources_uniques.add(doc_data.get("source_url", ""))
                taille_totale += len(doc_data.get("contenu", ""))

            except Exception as e:
                print(f"  ⚠️ Erreur lecture de {blob.name}: {e}")
                continue

        stats = {
            "total_documents": total_documents,
            "sources_uniques": len(sources_uniques),
            "taille_moyenne_document": taille_totale // total_documents if total_documents > 0 else 0,
            "taille_totale_caracteres": taille_totale
        }

        print(f"  Total de documents: {stats['total_documents']}")
        print(f"  Sources uniques: {stats['sources_uniques']}")
        print(f"  Taille moyenne par document: {stats['taille_moyenne_document']} caractères")

        return stats


# Fonction utilitaire pour usage direct
def charger_documents_pipeline(documents: List[Dict], project_id: str = None,
                               gcs_bucket_name: str = "documents-fiscaux-bucket") -> int:
    """
    Fonction utilitaire pour charger des documents rapidement via le pipeline.
    Les documents sont maintenant stockés en JSON uniquement dans Cloud Storage.
    """
    loader = PipelineLoader(project_id=project_id, gcs_bucket_name=gcs_bucket_name)
    return loader.charger_documents(documents)


if __name__ == "__main__":
    # Test du module (nécessite des credentials GCP configurés et un bucket GCS)
    print("Test du module de chargement PipelineLoader (Cloud Storage JSON)...")
    print("Note: Ce test nécessite des credentials GCP valides et un bucket GCS nommé 'documents-fiscaux-bucket'")

    # Créer un document de test
    document_test = {
        "document_id": "TEST-DOC-JSON-0",
        "contenu": "Ceci est un document de test pour vérifier le chargement JSON dans Cloud Storage. Tout est dans un seul fichier JSON.",
        "titre_source": "Document de Test JSON",
        "source_url": "https://example.com/test-json",
        "taille_caracteres": 100  # Cette taille sera dans les métadonnées Firestore
    }

    try:
        # Assurez-vous que le bucket existe ou créez-le manuellement dans GCP
        # loader = PipelineLoader()
        # Pour le test, on peut spécifier un project_id et un bucket_name si besoin
        loader = PipelineLoader(project_id=os.environ.get("PROJECT_ID"),
                                gcs_bucket_name="documents-fiscaux-bucket-test")

        # Charger le document de test
        print("\nChargement du document de test...")
        resultat = loader.charger_documents([document_test])
        print(f"\n✅ Test de chargement réussi : {resultat} document traité")

        # Lire le document depuis GCS (simulé)
        print("\nLecture du document depuis GCS (via loader.gcs_loader)...")
        contenu_lu = loader.gcs_loader.lire_document("TEST-DOC-0")
        print(f"Contenu lu depuis GCS: {contenu_lu[:50]}...")

        # Obtenir les statistiques
        stats = loader.obtenir_statistiques()

        # Nettoyer (supprimer le document de test)
        print("\n🧹 Nettoyage...")
        loader.supprimer_anciens_documents("https://example.com/test-gcs")

    except Exception as e:
        print(f"\n❌ Erreur lors du test : {e}")
        print("Assurez-vous que les credentials GCP sont configurés correctement et que le bucket GCS existe.")
