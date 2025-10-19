"""
Pipeline ETL principal pour la veille réglementaire
Orchestre les phases Extract, Transform et Load.
"""

import functions_framework
from google.cloud import firestore
from typing import List, Dict
import os

# Import des modules ETL
from extract import ContentExtractor
from transform import ContentChunker
from load import FirestoreLoader


class VeillePipeline:
    """Pipeline complet de veille réglementaire avec architecture ETL."""
    
    def __init__(self, project_id: str = None):
        """
        Args:
            project_id: ID du projet GCP (optionnel)
        """
        self.project_id = project_id or os.environ.get("PROJECT_ID")
        
        # Initialiser les composants du pipeline
        self.extractor = ContentExtractor(timeout=10, delay_between_requests=0.2)
        self.chunker = ContentChunker(chunk_size=1500, chunk_overlap=200)
        self.loader = FirestoreLoader(project_id=self.project_id)
        
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
        print("\n📋 Lecture des sources à surveiller...")
        
        sources_ref = self.db.collection("sources_a_surveiller")
        sources_docs = sources_ref.stream()
        
        sources = []
        for doc in sources_docs:
            source_data = doc.to_dict()
            source_data['id'] = doc.id
            sources.append(source_data)
        
        print(f"  ✅ {len(sources)} source(s) trouvée(s)")
        return sources
    
    def traiter_source(self, source: Dict) -> int:
        """
        Traite une source complète : extraction, transformation et chargement.
        
        Args:
            source: Dictionnaire contenant les informations de la source
                    Doit contenir au minimum 'url_base'
                    
        Returns:
            Nombre de chunks créés et chargés
        """
        url_base = source.get('url_base')
        source_id = source.get('id', 'unknown')
        
        if not url_base:
            print(f"⚠️  Source {source_id} n'a pas d'url_base, ignorée")
            return 0
        
        print("\n" + "="*80)
        print(f"🎯 TRAITEMENT DE LA SOURCE: {source_id}")
        print(f"   URL: {url_base}")
        print("="*80)
        
        # PHASE 1: EXTRACT - Extraire le contenu
        print("\n📥 PHASE 1: EXTRACTION")
        document = self.extractor.extraire_contenu(url_base)
        
        if not document:
            print(f"❌ Échec de l'extraction pour {url_base}")
            return 0
        
        # PHASE 2: TRANSFORM - Découper en chunks
        print("\n✂️  PHASE 2: TRANSFORMATION (Chunking)")
        chunks = self.chunker.decouper_document(document)
        
        if not chunks:
            print(f"❌ Aucun chunk créé pour {url_base}")
            return 0
        
        # PHASE 3: LOAD - Charger dans Firestore
        print("\n💾 PHASE 3: CHARGEMENT")
        
        # Option: Supprimer les anciens chunks de cette URL avant de charger les nouveaux
        # Cela garantit que les données sont toujours à jour
        self.loader.supprimer_anciens_chunks(url_base)
        
        chunks_charges = self.loader.charger_chunks(chunks)
        
        print("\n" + "="*80)
        print(f"✅ SOURCE {source_id} TRAITÉE: {chunks_charges} chunks chargés")
        print("="*80)
        
        return chunks_charges
    
    def executer(self) -> Dict:
        """
        Exécute le pipeline complet pour toutes les sources.
        
        Returns:
            Dictionnaire avec les statistiques d'exécution
        """
        print("\n" + "🚀"*40)
        print("DÉMARRAGE DU PIPELINE DE VEILLE RÉGLEMENTAIRE")
        print("🚀"*40)
        
        # Obtenir les sources à surveiller
        sources = self.obtenir_sources_a_surveiller()
        
        if not sources:
            print("\n⚠️  Aucune source à surveiller trouvée dans Firestore")
            return {
                "status": "warning",
                "message": "Aucune source à surveiller",
                "sources_traitees": 0,
                "chunks_crees": 0
            }
        
        # Traiter chaque source
        total_chunks = 0
        sources_reussies = 0
        
        for i, source in enumerate(sources, 1):
            print(f"\n\n{'='*80}")
            print(f"SOURCE {i}/{len(sources)}")
            print(f"{'='*80}")
            
            try:
                chunks_count = self.traiter_source(source)
                total_chunks += chunks_count
                if chunks_count > 0:
                    sources_reussies += 1
            except Exception as e:
                print(f"\n❌ Erreur lors du traitement de la source {source.get('id')}: {e}")
                continue
        
        # Résumé final
        print("\n\n" + "🎉"*40)
        print("PIPELINE TERMINÉ")
        print("🎉"*40)
        print(f"\n📊 RÉSUMÉ:")
        print(f"   Sources traitées avec succès: {sources_reussies}/{len(sources)}")
        print(f"   Total de chunks créés: {total_chunks}")
        
        # Obtenir les statistiques finales de la base
        stats_finales = self.loader.obtenir_statistiques()
        
        return {
            "status": "success",
            "message": "Pipeline exécuté avec succès",
            "sources_traitees": sources_reussies,
            "sources_total": len(sources),
            "chunks_crees": total_chunks,
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
        print(f"\n❌ ERREUR CRITIQUE: {e}")
        return {
            "status": "error",
            "message": f"Erreur lors de l'exécution du pipeline: {str(e)}"
        }, 500


# Fonction pour exécution locale
def executer_pipeline_local():
    """Exécute le pipeline localement pour tests."""
    pipeline = VeillePipeline()
    resultat = pipeline.executer()
    return resultat


if __name__ == "__main__":
    print("Exécution locale du pipeline...")
    print("Note: Nécessite des credentials GCP configurés et une collection 'sources_a_surveiller' dans Firestore")
    
    try:
        resultat = executer_pipeline_local()
        print("\n✅ Exécution terminée")
        print(f"Résultat: {resultat}")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")

