# Changelog

Alle wesentlichen Änderungen am Projekt werden hier dokumentiert.  
Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [Unveröffentlicht]

### Geplant
- FastAPI-Applikation (Grundgerüst)
- Alembic-Migrationen
- Docker Compose Setup
- API-Spezifikation

---

## [0.7.0] — Lastenheft V6.7 / Schema V1.3 / Architektur V1.2

### Geändert
- Lastenheft: Technische Rahmenbedingungen konkretisiert (VPS Infomaniak, Docker Compose, FastAPI + Jinja2 + HTMX)
- Architektur: Backup-Strategie 3-2-1 dokumentiert (VPS lokal → Infomaniak kDrive via Rclone → lokaler Rechner via kDrive-Sync)
- Architektur: Getroffene Entscheide von offenen Punkten getrennt

### Hinzugefügt
- Schema V1.3: `password_hash` nullable + `CONSTRAINT at_least_one_auth_method` für OAuth/Passkey-Erweiterbarkeit
- Schema V1.3: Auskommentierte `passkey_credential`-Tabelle (WebAuthn, Phase 2)
- Schema V1.3: Abschnitt ZUKUNFTSSICHERHEIT mit 6 expliziten Designentscheiden ([AUTH-1/2], [ROLE-1], [EVENT-1], [LOCATION-1], [OCCURRENCE-1], [DUTY-1])

---

## [0.6.0] — Lastenheft V6.6 / Schema V1.2 / Architektur V1.1

### Hinzugefügt
- Lastenheft: Abschnitt 13 "Dienstplan" (informatives Journal, passive Sichtbarkeit, keine Workflow-Logik)
- Schema V1.2: Tabelle `duty_schedule` mit Teilpräsenz-Unterstützung (`is_full_day`, `start_time`, `end_time`, `note`)
- Architektur V1.1: Docker Compose als Deployment-Methode (3 Container: nginx, app, db)
- Architektur V1.1: Infomaniak (CH) als VPS-Anbieter festgelegt

### Geändert
- Lastenheft: Abschnitt 12 (Nicht im MVP) um Dienstplan-Generator und aktive Verknüpfung ergänzt
- Lastenheft: Future Scope um Dienstplan-Rotationslogik ergänzt

---

## [0.5.0] — Lastenheft V6.5 / Schema V1.1

### Hinzugefügt
- Lastenheft: Archivierungsstrategie (Abschnitt 9.6): 3-Schritte-Job (Export anonym → Verifizieren → Löschen)
- Lastenheft: Rollendes 2-Jahres-Fenster für Produktions-DB
- Schema V1.1: Tabelle `duty_schedule` (Vorläufer, später überarbeitet)

### Geändert
- Lastenheft: DSG-Abschnitt überarbeitet — Anonymisierungs-Job ersetzt durch Archivierungsjob
- Lastenheft: Backup-Rotation auf 90 Tage festgelegt

---

## [0.4.0] — Lastenheft V6.4 / Schema V1.0

### Hinzugefügt
- Lastenheft: Abschnitt 9 DSG vollständig neu (Verantwortlichkeit, Datenminimierung, Aufbewahrung, Auskunftsrecht, technische Massnahmen)
- Schema V1.0: Vollständiges PostgreSQL-Schema (16 Tabellen)
- Schema V1.0: GiST-Index für Zeitraum-Konfliktprüfung (`tstzrange`)
- Schema V1.0: DB-Funktionen `check_location_conflict()`, `check_resource_availability()`, `check_blackout()`, `anonymize_person()`
- Schema V1.0: `event.is_public`, `approved_by`, `approved_at`, `rejection_reason`
- Schema V1.0: `CHECK (approved_by <> created_by)` — Self-Approval-Sperre auf DB-Ebene

### Geändert
- Lastenheft: Technologieentscheid Python + FastAPI festgehalten
- Lastenheft: Self-Approval technisch unterbunden als Erfolgskriterium

---

## [0.3.0] — Lastenheft V6.3

### Behoben
- Konflikt-Governance: Admin-Override für Sperrzeiten explizit geregelt
- Workflow: `rejected → requested` Rückfluss im Statusfluss dokumentiert
- `is_public`-Feld: klare Regel wer setzt (Requester) und wer ändert (Approver)
- Rollentabelle: Einschränkungsspalte ergänzt, Admin-als-Requester-Fall geregelt

---

## [0.2.0] — Lastenheft V6.2 (MVP)

### Hinzugefügt
- Initiales Lastenheft: Zielsetzung, Rollenmodell, Workflow, Konflikt-Governance, Personenmodell, Kalenderlogik, Datenprinzipien, Erfolgskriterien

---

## Versionsschema

`MAJOR.MINOR.PATCH`

- **MAJOR**: Grundlegende Architekturänderungen
- **MINOR**: Neue Features oder Dokumente
- **PATCH**: Korrekturen, Präzisierungen

Bis zur ersten produktiven Version (`1.0.0`) bleibt die Major-Version `0`.
