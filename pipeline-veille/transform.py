"""
Module de transformation de contenu - Phase TRANSFORM du pipeline ETL
Découpe le contenu en chunks sémantiques optimisés pour le RAG.
"""

from typing import List, Dict
from urllib.parse import urlparse
import re
import hashlib


class ContentChunker:
    """Découpe le contenu en morceaux sémantiques optimisés pour la recherche."""
    
    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100
    ):
        """
        Args:
            chunk_size: Taille cible d'un chunk en caractères
            chunk_overlap: Chevauchement entre chunks pour préserver le contexte
            min_chunk_size: Taille minimale d'un chunk (les plus petits sont ignorés)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def _generer_chunk_id(self, source_url: str, index: int) -> str:
        """
        Génère un ID unique et stable pour un chunk.
        
        Args:
            source_url: URL source du document
            index: Index du chunk dans le document
            
        Returns:
            Un ID unique (ex: "F23570-chunk-0")
        """
        # Extraire l'identifiant de la page (ex: F23570, N24265)
        url_path = urlparse(source_url).path
        page_id = url_path.split('/')[-1] if url_path else "unknown"
        
        # Si pas d'ID clair, utiliser un hash de l'URL
        if not page_id or page_id == "unknown":
            page_id = hashlib.md5(source_url.encode()).hexdigest()[:8]
        
        return f"{page_id}-chunk-{index}"
    
    def _nettoyer_texte(self, texte: str) -> str:
        """
        Nettoie le texte en retirant les espaces multiples et lignes vides excessives.
        
        Args:
            texte: Le texte à nettoyer
            
        Returns:
            Le texte nettoyé
        """
        # Remplacer les espaces multiples par un seul espace
        texte = re.sub(r' +', ' ', texte)
        
        # Remplacer les sauts de ligne multiples par maximum 2
        texte = re.sub(r'\n{3,}', '\n\n', texte)
        
        return texte.strip()
    
    def _decouper_par_separateurs(self, texte: str) -> List[str]:
        """
        Découpe le texte en utilisant une hiérarchie de séparateurs.
        Essaie d'abord les paragraphes, puis les phrases, puis les caractères.
        
        Args:
            texte: Le texte à découper
            
        Returns:
            Liste de chunks de texte
        """
        # Hiérarchie de séparateurs (du plus sémantique au plus basique)
        separateurs = [
            "\n\n",      # Paragraphes
            "\n",        # Lignes
            ". ",        # Phrases
            "! ",        # Phrases exclamatives
            "? ",        # Phrases interrogatives
            "; ",        # Clauses
            ", ",        # Clauses courtes
            " ",         # Mots
        ]
        
        chunks = [texte]
        
        # Appliquer chaque séparateur jusqu'à ce que tous les chunks soient assez petits
        for separateur in separateurs:
            nouveaux_chunks = []
            
            for chunk in chunks:
                if len(chunk) <= self.chunk_size:
                    # Ce chunk est déjà assez petit
                    nouveaux_chunks.append(chunk)
                else:
                    # Découper ce chunk
                    parties = chunk.split(separateur)
                    
                    chunk_actuel = ""
                    for partie in parties:
                        # Ajouter le séparateur sauf pour le dernier élément
                        partie_avec_sep = partie + separateur if partie != parties[-1] else partie
                        
                        if len(chunk_actuel) + len(partie_avec_sep) <= self.chunk_size:
                            chunk_actuel += partie_avec_sep
                        else:
                            if chunk_actuel:
                                nouveaux_chunks.append(chunk_actuel)
                            chunk_actuel = partie_avec_sep
                    
                    if chunk_actuel:
                        nouveaux_chunks.append(chunk_actuel)
            
            chunks = nouveaux_chunks
            
            # Si tous les chunks sont assez petits, on peut arrêter
            if all(len(c) <= self.chunk_size for c in chunks):
                break
        
        return chunks
    
    def _ajouter_chevauchement(self, chunks: List[str]) -> List[str]:
        """
        Ajoute un chevauchement entre les chunks pour préserver le contexte.
        
        Args:
            chunks: Liste de chunks sans chevauchement
            
        Returns:
            Liste de chunks avec chevauchement
        """
        if len(chunks) <= 1:
            return chunks
        
        chunks_avec_overlap = []
        
        for i, chunk in enumerate(chunks):
            chunk_final = chunk
            
            # Ajouter le contexte du chunk précédent (fin)
            if i > 0 and self.chunk_overlap > 0:
                chunk_precedent = chunks[i - 1]
                overlap_debut = chunk_precedent[-self.chunk_overlap:]
                chunk_final = overlap_debut + chunk_final
            
            chunks_avec_overlap.append(chunk_final)
        
        return chunks_avec_overlap
    
    def decouper_document(self, document: Dict) -> List[Dict]:
        """
        Découpe un document en chunks sémantiques.
        
        Args:
            document: Dictionnaire contenant au minimum:
                - contenu_brut: Le texte à découper
                - source_url: L'URL source
                - titre: Le titre du document
                Et optionnellement d'autres métadonnées
                
        Returns:
            Liste de dictionnaires, chacun représentant un chunk avec ses métadonnées
        """
        contenu = document.get('contenu_brut', '')
        if not contenu:
            print(f"  ⚠️  Pas de contenu à découper pour {document.get('source_url', 'URL inconnue')}")
            return []
        
        # Nettoyer le texte
        contenu_propre = self._nettoyer_texte(contenu)
        
        # Découper en chunks
        chunks_texte = self._decouper_par_separateurs(contenu_propre)
        
        # Ajouter le chevauchement
        chunks_texte = self._ajouter_chevauchement(chunks_texte)
        
        # Filtrer les chunks trop petits
        chunks_texte = [c for c in chunks_texte if len(c.strip()) >= self.min_chunk_size]
        
        # Créer les documents de chunks avec métadonnées
        chunks_documents = []
        source_url = document.get('source_url', '')
        
        for i, chunk_texte in enumerate(chunks_texte):
            chunk_doc = {
                "chunk_id": self._generer_chunk_id(source_url, i),
                "chunk_index": i,
                "contenu": chunk_texte.strip(),
                "titre_source": document.get('titre', 'Sans titre'),
                "source_url": source_url,
                "date_publication_source": document.get('date_publication'),
                "auteur_source": document.get('auteur'),
                "hostname": document.get('hostname'),
                "taille_caracteres": len(chunk_texte.strip()),
            }
            chunks_documents.append(chunk_doc)
        
        print(f"  ✂️  Document découpé en {len(chunks_documents)} chunks (taille moyenne: {sum(len(c['contenu']) for c in chunks_documents) // len(chunks_documents) if chunks_documents else 0} caractères)")
        
        return chunks_documents
    
    def decouper_plusieurs_documents(self, documents: List[Dict]) -> List[Dict]:
        """
        Découpe plusieurs documents en chunks.
        
        Args:
            documents: Liste de documents à découper
            
        Returns:
            Liste de tous les chunks de tous les documents
        """
        tous_les_chunks = []
        total = len(documents)
        
        print(f"\n✂️  Découpage de {total} documents en chunks...")
        
        for i, document in enumerate(documents, 1):
            print(f"\n[{i}/{total}] {document.get('titre', 'Sans titre')[:60]}...")
            chunks = self.decouper_document(document)
            tous_les_chunks.extend(chunks)
        
        print(f"\n✅ Découpage terminé : {len(tous_les_chunks)} chunks créés au total")
        print(f"   Taille moyenne : {sum(c['taille_caracteres'] for c in tous_les_chunks) // len(tous_les_chunks) if tous_les_chunks else 0} caractères")
        
        return tous_les_chunks


# Fonction utilitaire pour usage direct
def decouper_document(document: Dict, chunk_size: int = 1500) -> List[Dict]:
    """
    Fonction utilitaire pour découper un seul document rapidement.
    
    Args:
        document: Le document à découper
        chunk_size: Taille cible des chunks
        
    Returns:
        Liste de chunks
    """
    chunker = ContentChunker(chunk_size=chunk_size)
    return chunker.decouper_document(document)


if __name__ == "__main__":
    # Test du module avec un document fictif
    document_test = {
        "titre": "La Taxe sur la Valeur Ajoutée (TVA)",
        "contenu_brut": """La TVA est un impôt indirect sur la consommation. Elle est payée par le consommateur final mais collectée par les entreprises.

Le taux normal de TVA est de 20%. Il s'applique à la majorité des ventes de biens et des prestations de services.

Le taux réduit de 10% s'applique notamment à la restauration, aux travaux dans les logements anciens, et aux transports de voyageurs.

Le taux super-réduit de 5,5% concerne les produits alimentaires de première nécessité, l'énergie, les livres, et les équipements pour personnes handicapées.

Enfin, le taux particulier de 2,1% s'applique aux médicaments remboursables par la Sécurité sociale et à la presse.""",
        "source_url": "https://entreprendre.service-public.fr/vosdroits/F23570",
        "date_publication": "2024-01-15",
    }
    
    print("Test de découpage sur un document fictif...")
    chunks = decouper_document(document_test, chunk_size=200)
    
    print("\n" + "="*80)
    print("RÉSULTAT DU TEST")
    print("="*80)
    for chunk in chunks:
        print(f"\n📄 Chunk {chunk['chunk_index']} (ID: {chunk['chunk_id']})")
        print(f"   Taille: {chunk['taille_caracteres']} caractères")
        print(f"   Contenu: {chunk['contenu'][:150]}...")
        print("-"*80)

