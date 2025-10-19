"""
Module d'extraction de contenu web - Phase EXTRACT du pipeline ETL
Utilise trafilatura pour une extraction robuste et fiable du contenu principal.
"""

import requests
import trafilatura
import json
from typing import Dict, Optional
from urllib.parse import urlparse
import time


class ContentExtractor:
    """Extracteur de contenu web robuste et indépendant du design."""
    
    def __init__(self, timeout: int = 10, delay_between_requests: float = 0.2):
        """
        Args:
            timeout: Timeout pour les requêtes HTTP en secondes
            delay_between_requests: Délai entre chaque requête pour être poli
        """
        self.timeout = timeout
        self.delay_between_requests = delay_between_requests
        self.last_request_time = 0
    
    def _respecter_delai(self):
        """Respecte le délai minimum entre les requêtes."""
        temps_ecoule = time.time() - self.last_request_time
        if temps_ecoule < self.delay_between_requests:
            time.sleep(self.delay_between_requests - temps_ecoule)
        self.last_request_time = time.time()
    
    def extraire_contenu(self, url: str) -> Optional[Dict]:
        """
        Extrait le contenu principal d'une URL de manière robuste.
        
        Args:
            url: L'URL de la page à extraire
            
        Returns:
            Un dictionnaire avec les champs suivants ou None si échec:
            - titre: Le titre de la page
            - contenu_brut: Le texte principal nettoyé
            - source_url: L'URL source
            - date_publication: La date de publication si disponible
            - auteur: L'auteur si disponible
            - description: La description/résumé si disponible
        """
        self._respecter_delai()
        
        try:
            print(f"  📥 Extraction de : {url}")
            
            # Télécharger la page
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Utiliser trafilatura pour extraire le contenu
            # output_format='json' nous donne accès à toutes les métadonnées
            json_output = trafilatura.extract(
                response.content,
                include_comments=False,  # Ignorer les commentaires
                include_tables=True,     # Inclure les tableaux (important pour les données fiscales)
                output_format='json',
                url=url
            )
            
            if not json_output:
                print(f"  ⚠️  Trafilatura n'a pas pu extraire de contenu de {url}")
                return None
            
            # Parser le JSON retourné
            data = json.loads(json_output)
            
            # Vérifier qu'on a bien du contenu substantiel
            contenu = data.get('text', '')
            if not contenu or len(contenu) < 100:
                print(f"  ⚠️  Contenu trop court ({len(contenu)} caractères) pour {url}")
                return None
            
            # Construire le document structuré
            document = {
                "titre": data.get('title', 'Sans titre'),
                "contenu_brut": contenu,
                "source_url": data.get('source', url),
                "date_publication": data.get('date'),
                "auteur": data.get('author'),
                "description": data.get('description'),
                "hostname": data.get('hostname', urlparse(url).netloc),
            }
            
            print(f"  ✅ Extrait : '{document['titre'][:60]}...' ({len(contenu)} caractères)")
            return document
            
        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout lors de la requête vers {url}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Erreur HTTP pour {url}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"  ❌ Erreur de parsing JSON pour {url}: {e}")
            return None
        except Exception as e:
            print(f"  ❌ Erreur inattendue pour {url}: {e}")
            return None
    
    def extraire_plusieurs_urls(self, urls: list) -> list:
        """
        Extrait le contenu de plusieurs URLs.
        
        Args:
            urls: Liste d'URLs à extraire
            
        Returns:
            Liste de dictionnaires de contenu (les échecs sont omis)
        """
        documents = []
        total = len(urls)
        
        print(f"\n🚀 Extraction de {total} URLs...")
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{total}]")
            document = self.extraire_contenu(url)
            if document:
                documents.append(document)
        
        print(f"\n✅ Extraction terminée : {len(documents)}/{total} documents extraits avec succès")
        return documents


# Fonction utilitaire pour usage direct
def extraire_url(url: str) -> Optional[Dict]:
    """
    Fonction utilitaire pour extraire une seule URL rapidement.
    
    Args:
        url: L'URL à extraire
        
    Returns:
        Dictionnaire de contenu ou None
    """
    extractor = ContentExtractor()
    return extractor.extraire_contenu(url)


if __name__ == "__main__":
    # Test du module
    test_url = "https://entreprendre.service-public.fr/vosdroits/F23570"
    print("Test d'extraction sur une page service-public.fr...")
    resultat = extraire_url(test_url)
    
    if resultat:
        print("\n" + "="*80)
        print("RÉSULTAT DU TEST")
        print("="*80)
        print(f"Titre: {resultat['titre']}")
        print(f"Source: {resultat['source_url']}")
        print(f"Longueur du contenu: {len(resultat['contenu_brut'])} caractères")
        print(f"\nPremiers 500 caractères du contenu:")
        print("-"*80)
        print(resultat['contenu_brut'][:500])
        print("="*80)
    else:
        print("❌ Échec de l'extraction")

