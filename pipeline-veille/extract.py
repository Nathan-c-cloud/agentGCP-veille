"""
Module d'extraction de contenu web - Phase EXTRACT du pipeline ETL
Utilise uniquement Custom Search JSON API (méthode robuste et fiable)
"""

import os
import time
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


class CustomSearchExtractor:
    """
    Extracteur utilisant Google Custom Search JSON API.
    RECOMMANDÉ : Plus robuste et fiable que le scraping classique.
    """

    def __init__(self, api_key: str = None, search_engine_id: str = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.search_engine_id = search_engine_id or os.environ.get("SEARCH_ENGINE_ID")

        if not self.api_key or not self.search_engine_id:
            print("⚠️ Custom Search API non configurée (GOOGLE_API_KEY et SEARCH_ENGINE_ID manquants)")
            self.enabled = False
        else:
            self.enabled = True

        self.base_url = "https://www.googleapis.com/customsearch/v1"
        self.last_request_time = 0
        self.delay_between_requests = 1.0

    def _respecter_delai(self):
        temps_ecoule = time.time() - self.last_request_time
        if temps_ecoule < self.delay_between_requests:
            time.sleep(self.delay_between_requests - temps_ecoule)
        self.last_request_time = time.time()

    def _telecharger_contenu_complet(self, url: str) -> str:
        """
        Télécharge le contenu complet d'une page web.

        Args:
            url: URL de la page à télécharger

        Returns:
            Contenu texte complet de la page
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            # Parser le HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Supprimer les scripts, styles, etc.
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Extraire le texte
            text = soup.get_text(separator=' ', strip=True)

            # Nettoyer les espaces multiples
            text = ' '.join(text.split())

            print(f"    ✅ Contenu téléchargé: {len(text)} caractères")
            return text

        except Exception as e:
            print(f"    ⚠️ Erreur téléchargement {url}: {e}")
            return ""

    def rechercher_documents(self, keywords: List[str], site_url: str = None, max_results: int = 5) -> List[Dict]:
        """
        Recherche via Custom Search API sur sites officiels.
        Alternative ROBUSTE au scraping classique.
        """
        if not self.enabled:
            return []

        self._respecter_delai()

        query = " ".join(keywords)
        if site_url:
            query = f"{query} site:{site_url}"

        print(f"  🔍 Custom Search API: '{query}'")

        params = {
            "key": self.api_key,
            "cx": self.search_engine_id,
            "q": query,
            "num": min(max_results, 10),
            "lr": "lang_fr",
            "gl": "fr"
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            documents = []
            for item in data.get("items", []):
                url = item.get("link", "")
                print(f"    📄 Traitement: {item.get('title', 'Sans titre')[:60]}...")

                # Télécharger le contenu COMPLET de la page
                contenu_complet = self._telecharger_contenu_complet(url)

                doc = {
                    "titre": item.get("title", "Sans titre"),
                    "contenu_brut": contenu_complet if contenu_complet else item.get("snippet", ""),
                    "source_url": url,
                    "description": item.get("snippet", ""),
                    "date_publication": None,
                    "auteur": None,
                    "hostname": urlparse(url).netloc,
                    "methode_extraction": "custom_search_api_full_content"
                }
                documents.append(doc)

                # Respecter un délai entre les téléchargements
                self._respecter_delai()

            print(f"  ✅ {len(documents)} résultat(s) avec contenu complet")
            return documents

        except Exception as e:
            print(f"  ❌ Erreur Custom Search API: {e}")
            return []


class ContentExtractor:
    """
    Extracteur de contenu web utilisant UNIQUEMENT Custom Search API.
    Plus de scraping classique - méthode robuste et fiable.
    """

    def __init__(self):
        """Initialise l'extracteur avec Custom Search API."""
        self.custom_search = CustomSearchExtractor()

        if not self.custom_search.enabled:
            raise ValueError(
                "❌ Custom Search API non configurée!\n"
                "Variables d'environnement requises:\n"
                "  - GOOGLE_API_KEY\n"
                "  - SEARCH_ENGINE_ID\n"
                "Voir GUIDE_GOOGLE_SEARCH_API.md pour configuration"
            )

    def extraire_pour_source(self, source: Dict) -> List[Dict]:
        """
        Extrait des documents pour une source de veille via Custom Search API.

        Args:
            source: Dictionnaire de configuration de la source contenant:
                    - id: Identifiant de la source
                    - keywords: Mots-clés de recherche (liste ou string)
                    - url_base: URL du site à cibler (optionnel)
                    - categorie: Catégorie fiscale

        Returns:
            Liste de documents extraits
        """
        source_id = source.get("id", "unknown")
        keywords = source.get("keywords", [])

        # Convertir keywords en liste si c'est un string
        if isinstance(keywords, str):
            keywords = [keywords]

        # Si pas de keywords, utiliser la description ou l'ID
        if not keywords:
            description = source.get("description", "")
            if description:
                keywords = description.split()[:5]  # Prendre les 5 premiers mots
            else:
                keywords = [source_id.replace("_", " ")]

        # Extraire le domaine si url_base fournie
        site_url = None
        url_base = source.get("url_base")
        if url_base:
            parsed = urlparse(url_base)
            site_url = parsed.netloc

        print(f"\n{'=' * 80}")
        print(f"🔍 EXTRACTION CUSTOM SEARCH - Source: {source_id}")
        print(f"   Mots-clés: {keywords}")
        if site_url:
            print(f"   Site ciblé: {site_url}")
        print(f"{'=' * 80}")

        # Rechercher via Custom Search API
        documents = self.custom_search.rechercher_documents(
            keywords=keywords,
            site_url=site_url,
            max_results=5
        )

        # Enrichir avec les métadonnées de la source
        categorie = source.get("categorie", "fiscalite")
        for doc in documents:
            doc["categorie"] = categorie
            doc["source_id"] = source_id
            # Créer un document_id unique
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            doc_hash = hash(doc['source_url']) % 100000
            doc["document_id"] = f"{source_id}_{timestamp}_{doc_hash}"

        print(f"✅ {len(documents)} document(s) extrait(s) pour {source_id}")
        return documents

    def extraire_plusieurs_sources(self, sources: List[Dict]) -> List[Dict]:
        """
        Extrait des documents pour plusieurs sources.

        Args:
            sources: Liste de dictionnaires de configuration des sources

        Returns:
            Liste consolidée de tous les documents extraits
        """
        all_documents = []
        total = len(sources)

        print(f"\n🚀 Extraction de {total} source(s)...")

        for i, source in enumerate(sources, 1):
            print(f"\n[{i}/{total}]")
            try:
                documents = self.extraire_pour_source(source)
                all_documents.extend(documents)
            except Exception as e:
                print(f"  ❌ Erreur pour source {source.get('id')}: {e}")
                continue

        print(f"\n✅ Extraction terminée : {len(all_documents)} document(s) au total")
        return all_documents


if __name__ == "__main__":
    """Test du module Custom Search"""
    print("🧪 Test du Custom Search Extractor\n")

    # Vérifier les variables d'environnement
    api_key = os.environ.get("GOOGLE_API_KEY")
    engine_id = os.environ.get("SEARCH_ENGINE_ID")

    if not api_key or not engine_id:
        print("❌ Variables d'environnement manquantes:")
        print("   - GOOGLE_API_KEY")
        print("   - SEARCH_ENGINE_ID")
        print("\nConfigurez-les selon GUIDE_GOOGLE_SEARCH_API.md")
        exit(1)

    try:
        extractor = ContentExtractor()

        # Test avec une source fictive
        source_test = {
            "id": "test_tva",
            "keywords": ["TVA", "taux réduits"],
            "url_base": "https://entreprendre.service-public.fr",
            "categorie": "fiscalite_tva"
        }

        print("--- Test: Extraction pour source TVA ---")
        documents = extractor.extraire_pour_source(source_test)

        for i, doc in enumerate(documents, 1):
            print(f"\n{i}. {doc['titre']}")
            print(f"   URL: {doc['source_url']}")
            print(f"   Extrait: {doc['contenu_brut'][:100]}...")

        print("\n✅ Test terminé avec succès!")

    except Exception as e:
        print(f"\n❌ Erreur lors du test: {e}")
