FROM python:3.12-slim

# Sicherheit: kein Root-User im Container
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Abhängigkeiten zuerst (Docker-Cache nutzen)
COPY pyproject.toml .

# app-Verzeichnis muss für hatchling existieren
RUN mkdir -p app && touch app/__init__.py

RUN pip install --no-cache-dir --root-user-action=ignore --upgrade pip && \
    pip install --no-cache-dir --root-user-action=ignore .

# App-Code (überschreibt den leeren Platzhalter)
COPY app/ app/

# Verzeichnisse für statische Dateien und Templates
RUN mkdir -p app/static app/templates

# Ownership
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
