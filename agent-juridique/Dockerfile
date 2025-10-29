# Utiliser une image Python 3.11 officielle
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les dépendances
COPY requirements.txt .

# --- AJOUTEZ CETTE LIGNE ---
RUN pip install --upgrade pip

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY . .

# Exposer le port (8080 est le port par défaut pour Cloud Run)
EXPOSE 8080

# Commande pour lancer l'application avec Gunicorn (timeout 120s pour les appels RAG)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "120", "main:app"]
