# Kirchliches Planungs- und Reservationssystem

Digitales System zur Verwaltung von Raumreservationen, Anlässen und Dienstplänen für eine Kirchgemeinde.

## Status

🚧 **In Entwicklung** — Dokumentationsphase abgeschlossen, Implementierung ausstehend.

## Funktionsübersicht

- Raumreservationen mit Konfliktprüfung
- Workflow: Anfrage → Freigabe → Bestätigung
- Rollenbasierte Zugriffskontrolle (Requester, Approver, Admin)
- Öffentlicher Kalender für bestätigte Anlässe
- Informatives Dienstplan-Journal
- DSG-konformes Datenmanagement mit Archivierungsjob

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Rendering | Jinja2 (SSR) + HTMX |
| Datenbank | PostgreSQL 16 |
| Reverse Proxy | nginx |
| Deployment | Docker Compose |
| Hosting | Infomaniak VPS (Schweiz) |

## Projektstruktur

```
kirchenplanung/
├── docs/                        # Projektdokumentation
│   ├── Lastenheft.docx          # Anforderungen
│   ├── Architekturuebersicht.docx
│   └── schema.sql               # Datenbankschema
├── app/                         # FastAPI-Applikation (in Entwicklung)
├── docker-compose.yml           # Container-Orchestrierung
├── .env.example                 # Erforderliche Umgebungsvariablen
├── CHANGELOG.md
└── README.md
```

## Schnellstart (Entwicklung)

> **Voraussetzungen:** Docker, Docker Compose

```bash
# Repository klonen
git clone https://github.com/mtedaldi/kirchenplanung.git
cd kirchenplanung

# Umgebungsvariablen konfigurieren
cp .env.example .env
# .env mit eigenen Werten befüllen

# Container starten
docker compose up -d

# Datenbankschema initialisieren
docker compose exec app alembic upgrade head
```

## Dokumentation

Alle Projektdokumente liegen im Verzeichnis `docs/`:

- **Lastenheft** — Anforderungen, Workflow, DSG-Konzept
- **Architekturübersicht** — Systemkomponenten, Datenflüsse, Deployment
- **schema.sql** — Vollständiges PostgreSQL-Schema mit Kommentaren

## Datenschutz

Das System ist für den Betrieb in der Schweiz ausgelegt und folgt den Anforderungen des Schweizer Datenschutzgesetzes (DSG). Personendaten werden ausschliesslich auf Schweizer Servern (Infomaniak) gespeichert.

## Entwicklung

Dieses Projekt wurde mit Unterstützung von KI-Werkzeugen (Claude, Anthropic) entwickelt. Alle Entscheide zu Architektur, Datenschutz und Anforderungen wurden durch den Projektverantwortlichen getroffen und verantwortet.

## Lizenz

Proprietär — alle Rechte vorbehalten. Nutzung ausschliesslich durch die betreibende Kirchgemeinde.
