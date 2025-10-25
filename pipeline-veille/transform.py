from typing import List, Dict
from urllib.parse import urlparse
import re
import hashlib


class ContentProcessor:
    """Simule le découpage mais retourne le document complet comme un seul 'chunk'."""

    def __init__(
            self,
            chunk_size: int = 1500,
            chunk_overlap: int = 200,
            min_chunk_size: int = 100
    ):
        """
        Args:
            chunk_size: Taille cible d'un chunk en caractères (non utilisé ici)
            chunk_overlap: Chevauchement entre chunks (non utilisé ici)
            min_chunk_size: Taille minimale d'un chunk (non utilisé ici)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def _generer_document_id(self, source_url: str) -> str:
        """
        Génère un ID unique et stable pour le document complet.
        
        Args:
            source_url: URL source du document
            
        Returns:
            Un ID unique (ex: "F23570")
        """
        url_path = urlparse(source_url).path
        page_id = url_path.split('/')[-1] if url_path else "unknown"

        if not page_id or page_id == "unknown":
            page_id = hashlib.md5(source_url.encode()).hexdigest()[:8]

        return page_id

    def _nettoyer_texte(self, texte: str) -> str:
        """
        Nettoie le texte en retirant les espaces multiples et lignes vides excessives.
        
        Args:
            texte: Le texte à nettoyer
            
        Returns:
            Le texte nettoyé
        """
        texte = re.sub(r' +', ' ', texte)
        texte = re.sub(r'\n{3,}', '\n\n', texte)
        return texte.strip()

    def traiter_document(self, document: Dict) -> List[Dict]:
        """
        Ne découpe plus le document, mais le retourne comme un seul 'chunk' avec un ID de document.
        
        Args:
            document: Dictionnaire contenant au minimum:
                - contenu_brut: Le texte à traiter
                - source_url: L'URL source
                - titre: Le titre du document
                Et optionnellement d'autres métadonnées
                
        Returns:
            Liste d'un seul dictionnaire, représentant le document complet avec ses métadonnées.
        """
        contenu = document.get('contenu_brut', '')
        if not contenu:
            print(f"  Pas de contenu à traiter pour {document.get('source_url', 'URL inconnue')}")
            return []

        # Nettoyer le texte
        contenu_propre = self._nettoyer_texte(contenu)

        source_url = document.get('source_url', '')
        document_id = self._generer_document_id(source_url)

        # Créer un document unique qui contient tout le contenu
        document_complet = {
            "document_id": document_id,  # Nouvel ID pour le document complet
            "contenu": contenu_propre,
            "titre_source": document.get('titre', 'Sans titre'),
            "source_url": source_url,
            "date_publication_source": document.get('date_publication'),
            "auteur_source": document.get('auteur'),
            "hostname": document.get('hostname'),
            "taille_caracteres": len(contenu_propre),
        }

        print(f" Document traité : '{document_complet['titre_source'][:60]}...' ({len(contenu_propre)} caractères)")

        return [document_complet]  # Retourne une liste contenant un seul document

    def traiter_plusieurs_documents(self, documents: List[Dict]) -> List[Dict]:
        """
        Traite plusieurs documents en les retournant comme des documents complets (non découpés).
        
        Args:
            documents: Liste de documents à traiter
            
        Returns:
            Liste de tous les documents complets.
        """
        tous_les_documents_complets = []
        total = len(documents)

        print(f"\n  Traitement de {total} documents...")

        for i, document in enumerate(documents, 1):
            print(f"\n[{i}/{total}] {document.get('titre', 'Sans titre')[:60]}...")
            document_complet = self.decouper_document(document)
            tous_les_documents_complets.extend(document_complet)

        print(f"\n Traitement terminé : {len(tous_les_documents_complets)} documents complets créés au total")
        print(
            f"   Taille moyenne : {sum(d['taille_caracteres'] for d in tous_les_documents_complets) // len(tous_les_documents_complets) if tous_les_documents_complets else 0} caractères")

        return tous_les_documents_complets


# Fonction utilitaire pour usage direct
def traiter_document(document: Dict) -> List[Dict]:
    """
    Fonction utilitaire pour traiter un seul document rapidement sans découpage.
    
    Args:
        document: Le document à traiter
        
    Returns:
        Liste d'un seul document complet
    """
    processor = ContentProcessor()
    return processor.traiter_document(document)


if __name__ == "__main__":
    # Test du module avec un document fictif
    document_test = {
        "titre": "La Taxe sur la Valeur Ajoutée (TVA)",
        "contenu_brut": """La TVA est un impôt indirect sur la consommation. Elle est payée par le consommateur final mais collectée par les entreprises.\n\nLe taux normal de TVA est de 20%. Il s'applique à la majorité des ventes de biens et des prestations de services.\n\nLe taux réduit de 10% s'applique notamment à la restauration, aux travaux dans les logements anciens, et aux transports de voyageurs.\n\nLe taux super-réduit de 5,5% concerne les produits alimentaires de première nécessité, l'énergie, les livres, et les équipements pour personnes handicapées.\n\nEnfin, le taux particulier de 2,1% s'applique aux médicaments remboursables par la Sécurité sociale et à la presse.""",
        "source_url": "https://entreprendre.service-public.fr/vosdroits/F23570",
        "date_publication": "2024-01-15",
    }

    print("Test de traitement sur un document fictif (sans découpage)...")
    documents_complets = traiter_document(document_test)

    print("\n" + "=" * 80)
    print("RÉSULTAT DU TEST")
    print("=" * 80)
    for doc in documents_complets:
        print(f"\n Document ID: {doc['document_id']}")
        print(f"   Taille: {doc['taille_caracteres']} caractères")
        print(f"   Contenu (début): {doc['contenu'][:150]}...")
        print("-" * 80)
