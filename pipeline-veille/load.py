from google.cloud import firestore
from typing import List, Dict
import os


class FirestoreLoader:
    """Charge les documents complets dans Firestore de manière optimisée."""

    def __init__(self, project_id: str = None):
        """
        Args:
            project_id: ID du projet GCP (optionnel, utilise la variable d'environnement par défaut)
        """
        if project_id:
            self.db = firestore.Client(project=project_id)
        else:
            self.db = firestore.Client()

        # Nom de la collection où seront stockés les documents complets
        self.collection_name = "documents_fiscaux_complets"

    def charger_documents(self, documents: List[Dict], batch_size: int = 500) -> int:
        """
        Charge une liste de documents complets dans Firestore.

        Args:
            documents: Liste de dictionnaires représentant les documents complets
            batch_size: Nombre de documents par batch (max 500 pour Firestore)

        Returns:
            Nombre de documents chargés avec succès
        """
        if not documents:
            print("  Aucun document à charger")
            return 0

        total = len(documents)
        print(f"\n Chargement de {total} documents dans Firestore...")
        print(f"   Collection: {self.collection_name}")

        collection_ref = self.db.collection(self.collection_name)
        documents_charges = 0

        # Traiter par batches pour respecter les limites de Firestore
        for i in range(0, total, batch_size):
            batch = self.db.batch()
            batch_docs = documents[i:i + batch_size]

            for doc_data in batch_docs:
                # Utiliser document_id comme ID du document Firestore
                document_id = doc_data.get("document_id")
                if not document_id:
                    print(f"  Document sans ID ignoré")
                    continue

                doc_ref = collection_ref.document(document_id)

                # Ajouter un timestamp de dernière mise à jour
                doc_avec_timestamp = {
                    **doc_data,
                    "derniere_verification": firestore.SERVER_TIMESTAMP
                }

                # merge=True permet de mettre à jour sans écraser les champs non mentionnés
                batch.set(doc_ref, doc_avec_timestamp, merge=True)
                documents_charges += 1

            # Commit du batch
            try:
                batch.commit()
                print(
                    f" Batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} chargé ({len(batch_docs)} documents)")
            except Exception as e:
                print(f"  Erreur lors du commit du batch {i // batch_size + 1}: {e}")
                documents_charges -= len(batch_docs)

        print(f"\n Chargement terminé : {documents_charges}/{total} documents chargés avec succès")
        return documents_charges

    def supprimer_anciens_documents(self, source_url: str) -> int:
        """
        Supprime tous les documents d'une source URL spécifique.
        Utile pour rafraîchir le contenu d'une page qui a été mise à jour.

        Args:
            source_url: L'URL source dont il faut supprimer les documents

        Returns:
            Nombre de documents supprimés
        """
        print(f"\n  Suppression des anciens documents de {source_url}...")

        collection_ref = self.db.collection(self.collection_name)

        # Requête pour trouver tous les documents de cette source
        query = collection_ref.where("source_url", "==", source_url)
        docs = query.stream()

        # Supprimer par batch
        batch = self.db.batch()
        count = 0

        for doc in docs:
            batch.delete(doc.reference)
            count += 1

            # Commit tous les 500 documents (limite Firestore)
            if count % 500 == 0:
                batch.commit()
                batch = self.db.batch()

        # Commit final
        if count % 500 != 0:
            batch.commit()

        print(f" {count} anciens documents supprimés")
        return count

    def compter_documents(self) -> int:
        """
        Compte le nombre total de documents dans la collection.

        Returns:
            Nombre total de documents
        """
        collection_ref = self.db.collection(self.collection_name)

        # Firestore n'a pas de count() direct, on doit itérer
        # Pour une vraie production, utiliser un compteur séparé ou Cloud Functions
        docs = collection_ref.stream()
        count = sum(1 for _ in docs)

        return count

    def obtenir_statistiques(self) -> Dict:
        """
        Obtient des statistiques sur la collection de documents.

        Returns:
            Dictionnaire avec des statistiques
        """
        print("\n Calcul des statistiques...")

        collection_ref = self.db.collection(self.collection_name)
        docs = collection_ref.stream()

        total_documents = 0
        sources_uniques = set()
        taille_totale = 0

        for doc in docs:
            total_documents += 1
            data = doc.to_dict()
            sources_uniques.add(data.get("source_url", ""))
            taille_totale += data.get("taille_caracteres", 0)

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
def charger_dans_firestore(documents: List[Dict], project_id: str = None) -> int:
    """
    Fonction utilitaire pour charger des documents rapidement.

    Args:
        documents: Liste de documents à charger
        project_id: ID du projet GCP (optionnel)

    Returns:
        Nombre de documents chargés
    """
    loader = FirestoreLoader(project_id=project_id)
    return loader.charger_documents(documents)


if __name__ == "__main__":
    # Test du module (nécessite des credentials GCP configurés)
    print("Test du module de chargement Firestore...")
    print("Note: Ce test nécessite des credentials GCP valides")

    # Créer un document de test
    document_test = {
        "document_id": "TEST-DOC-0",
        "contenu": "Ceci est un document de test pour vérifier le chargement dans Firestore.",
        "titre_source": "Document de Test",
        "source_url": "https://example.com/test",
        "taille_caracteres": 70
    }

    try:
        loader = FirestoreLoader()

        # Charger le document de test
        resultat = loader.charger_documents([document_test])
        print(f"\n Test réussi : {resultat} document chargé")

        # Obtenir les statistiques
        stats = loader.obtenir_statistiques()

        # Nettoyer (supprimer le document de test)
        print("\n Nettoyage...")
        loader.supprimer_anciens_documents("https://example.com/test")

    except Exception as e:
        print(f"\n Erreur lors du test : {e}")
        print("Assurez-vous que les credentials GCP sont configurés correctement")
