"""
Module de chargement dans Firestore - Phase LOAD du pipeline ETL
Sauvegarde les chunks dans une collection optimisée pour la recherche RAG.
"""

from google.cloud import firestore
from typing import List, Dict
import os


class FirestoreLoader:
    """Charge les chunks dans Firestore de manière optimisée."""
    
    def __init__(self, project_id: str = None):
        """
        Args:
            project_id: ID du projet GCP (optionnel, utilise la variable d'environnement par défaut)
        """
        if project_id:
            self.db = firestore.Client(project=project_id)
        else:
            self.db = firestore.Client()
        
        # Nom de la collection où seront stockés les chunks
        self.collection_name = "documents_fiscaux_chunks"
    
    def charger_chunks(self, chunks: List[Dict], batch_size: int = 500) -> int:
        """
        Charge une liste de chunks dans Firestore.
        
        Args:
            chunks: Liste de dictionnaires représentant les chunks
            batch_size: Nombre de documents par batch (max 500 pour Firestore)
            
        Returns:
            Nombre de chunks chargés avec succès
        """
        if not chunks:
            print("⚠️  Aucun chunk à charger")
            return 0
        
        total = len(chunks)
        print(f"\n💾 Chargement de {total} chunks dans Firestore...")
        print(f"   Collection: {self.collection_name}")
        
        collection_ref = self.db.collection(self.collection_name)
        chunks_charges = 0
        
        # Traiter par batches pour respecter les limites de Firestore
        for i in range(0, total, batch_size):
            batch = self.db.batch()
            batch_chunks = chunks[i:i + batch_size]
            
            for chunk in batch_chunks:
                # Utiliser chunk_id comme ID du document Firestore
                chunk_id = chunk.get('chunk_id')
                if not chunk_id:
                    print(f"  ⚠️  Chunk sans ID ignoré")
                    continue
                
                doc_ref = collection_ref.document(chunk_id)
                
                # Ajouter un timestamp de dernière mise à jour
                chunk_avec_timestamp = {
                    **chunk,
                    "derniere_verification": firestore.SERVER_TIMESTAMP
                }
                
                # merge=True permet de mettre à jour sans écraser les champs non mentionnés
                batch.set(doc_ref, chunk_avec_timestamp, merge=True)
                chunks_charges += 1
            
            # Commit du batch
            try:
                batch.commit()
                print(f"  ✅ Batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size} chargé ({len(batch_chunks)} chunks)")
            except Exception as e:
                print(f"  ❌ Erreur lors du commit du batch {i//batch_size + 1}: {e}")
                chunks_charges -= len(batch_chunks)
        
        print(f"\n✅ Chargement terminé : {chunks_charges}/{total} chunks chargés avec succès")
        return chunks_charges
    
    def supprimer_anciens_chunks(self, source_url: str) -> int:
        """
        Supprime tous les chunks d'une source URL spécifique.
        Utile pour rafraîchir le contenu d'une page qui a été mise à jour.
        
        Args:
            source_url: L'URL source dont il faut supprimer les chunks
            
        Returns:
            Nombre de chunks supprimés
        """
        print(f"\n🗑️  Suppression des anciens chunks de {source_url}...")
        
        collection_ref = self.db.collection(self.collection_name)
        
        # Requête pour trouver tous les chunks de cette source
        query = collection_ref.where('source_url', '==', source_url)
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
        
        print(f"  ✅ {count} anciens chunks supprimés")
        return count
    
    def compter_chunks(self) -> int:
        """
        Compte le nombre total de chunks dans la collection.
        
        Returns:
            Nombre total de chunks
        """
        collection_ref = self.db.collection(self.collection_name)
        
        # Firestore n'a pas de count() direct, on doit itérer
        # Pour une vraie production, utiliser un compteur séparé ou Cloud Functions
        docs = collection_ref.stream()
        count = sum(1 for _ in docs)
        
        return count
    
    def obtenir_statistiques(self) -> Dict:
        """
        Obtient des statistiques sur la collection de chunks.
        
        Returns:
            Dictionnaire avec des statistiques
        """
        print("\n📊 Calcul des statistiques...")
        
        collection_ref = self.db.collection(self.collection_name)
        docs = collection_ref.stream()
        
        total_chunks = 0
        sources_uniques = set()
        taille_totale = 0
        
        for doc in docs:
            total_chunks += 1
            data = doc.to_dict()
            sources_uniques.add(data.get('source_url', ''))
            taille_totale += data.get('taille_caracteres', 0)
        
        stats = {
            "total_chunks": total_chunks,
            "sources_uniques": len(sources_uniques),
            "taille_moyenne_chunk": taille_totale // total_chunks if total_chunks > 0 else 0,
            "taille_totale_caracteres": taille_totale
        }
        
        print(f"  Total de chunks: {stats['total_chunks']}")
        print(f"  Sources uniques: {stats['sources_uniques']}")
        print(f"  Taille moyenne par chunk: {stats['taille_moyenne_chunk']} caractères")
        
        return stats


# Fonction utilitaire pour usage direct
def charger_dans_firestore(chunks: List[Dict], project_id: str = None) -> int:
    """
    Fonction utilitaire pour charger des chunks rapidement.
    
    Args:
        chunks: Liste de chunks à charger
        project_id: ID du projet GCP (optionnel)
        
    Returns:
        Nombre de chunks chargés
    """
    loader = FirestoreLoader(project_id=project_id)
    return loader.charger_chunks(chunks)


if __name__ == "__main__":
    # Test du module (nécessite des credentials GCP configurés)
    print("Test du module de chargement Firestore...")
    print("Note: Ce test nécessite des credentials GCP valides")
    
    # Créer un chunk de test
    chunk_test = {
        "chunk_id": "TEST-chunk-0",
        "chunk_index": 0,
        "contenu": "Ceci est un chunk de test pour vérifier le chargement dans Firestore.",
        "titre_source": "Document de Test",
        "source_url": "https://example.com/test",
        "taille_caracteres": 70
    }
    
    try:
        loader = FirestoreLoader()
        
        # Charger le chunk de test
        resultat = loader.charger_chunks([chunk_test])
        print(f"\n✅ Test réussi : {resultat} chunk chargé")
        
        # Obtenir les statistiques
        stats = loader.obtenir_statistiques()
        
        # Nettoyer (supprimer le chunk de test)
        print("\n🧹 Nettoyage...")
        loader.supprimer_anciens_chunks("https://example.com/test")
        
    except Exception as e:
        print(f"\n❌ Erreur lors du test : {e}")
        print("Assurez-vous que les credentials GCP sont configurés correctement")

