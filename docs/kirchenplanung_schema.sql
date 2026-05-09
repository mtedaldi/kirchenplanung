-- =============================================================================
-- Kirchliches Planungs- und Reservationssystem
-- Datenbankschema Version 1.2
-- Datenbank: PostgreSQL 15+
-- Erstellt mit KI-Unterstützung (Claude, Anthropic)
-- =============================================================================

-- Konventionen:
--   - Primärschlüssel: UUID (gen_random_uuid())
--   - Zeitstempel: TIMESTAMPTZ (mit Zeitzone, immer UTC speichern)
--   - Soft Delete: deleted_at TIMESTAMPTZ (NULL = aktiv)
--   - Physisches Löschen: ausschliesslich durch Archivierungsjob
--   - Alle Schreiboperationen sind transaktional

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gist"; -- GiST-Index für Zeitraum-Konflikte

-- =============================================================================
-- ENUMS
-- =============================================================================

CREATE TYPE event_status AS ENUM (
    'requested',   -- Neu eingereicht, wartet auf Freigabe
    'approved',    -- Freigegeben, noch nicht final bestätigt
    'confirmed',   -- Final bestätigt, ggf. öffentlich sichtbar
    'rejected',    -- Abgelehnt, kann überarbeitet und neu eingereicht werden
    'cancelled'    -- Abgebrochen (Endzustand, keine Weiterbearbeitung)
);

CREATE TYPE location_type AS ENUM (
    'building',    -- Gebäude (z.B. Kirche, Pfarreiheim)
    'room',        -- Raum innerhalb eines Gebäudes
    'outdoor',     -- Aussenbereich
    'other'
);

CREATE TYPE dependency_type AS ENUM (
    'exclusive',   -- Wenn A belegt, ist B automatisch auch belegt (z.B. Kirchenschiff → Sakristei)
    'shared'       -- A und B teilen eine gemeinsame Ressource
);

-- =============================================================================
-- 1. PERSON
-- Stammdaten für alle Personen (User und Externe)
-- =============================================================================

CREATE TABLE person (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    -- DSG: Anonymisierung auf Antrag (Recht auf Vergessenwerden)
    -- Bei Anonymisierung: name → '[anonymisiert]', email/phone → NULL
    anonymized_at   TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE person IS
    'Stammdaten aller Personen. Kann User-Account haben oder nicht (z.B. externe Gastredner).';
COMMENT ON COLUMN person.anonymized_at IS
    'Gesetzt bei Anonymisierung auf Antrag (DSG Art. 32). Name wird auf [anonymisiert] gesetzt, Kontaktfelder auf NULL.';

-- =============================================================================
-- 2. APP_USER
-- Login-Entitäten; immer mit einer Person verknüpft
-- =============================================================================

CREATE TABLE app_user (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id       UUID NOT NULL UNIQUE REFERENCES person(id),
    email           TEXT NOT NULL UNIQUE,  -- Login-Email (kann von person.email abweichen)
    password_hash   TEXT NOT NULL,         -- bcrypt oder Argon2, nie Klartext
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE app_user IS
    'Login-Entität. Jeder User ist mit genau einer Person verknüpft.';
COMMENT ON COLUMN app_user.password_hash IS
    'Gehashtes Passwort (bcrypt oder Argon2). Klartext wird niemals gespeichert.';

-- =============================================================================
-- 3. ROLE
-- Feste Rollen: requester, approver, admin
-- =============================================================================

CREATE TABLE role (
    id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name    TEXT NOT NULL UNIQUE  -- 'requester', 'approver', 'admin'
);

COMMENT ON TABLE role IS
    'Systemrollen. Werte: requester, approver, admin.';

-- Grunddaten einfügen
INSERT INTO role (id, name) VALUES
    (gen_random_uuid(), 'requester'),
    (gen_random_uuid(), 'approver'),
    (gen_random_uuid(), 'admin');

-- =============================================================================
-- 4. USER_ROLE
-- Many-to-Many: User kann mehrere Rollen haben
-- =============================================================================

CREATE TABLE user_role (
    user_id     UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    role_id     UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    granted_by  UUID REFERENCES app_user(id),  -- Wer hat die Rolle vergeben? (Admin)
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id)
);

COMMENT ON TABLE user_role IS
    'Rollenzuweisung. Nur Admins dürfen Rollen vergeben (granted_by).';

-- =============================================================================
-- 5. LOCATION
-- Räume und Gebäude, hierarchisch (parent_id für Gebäude → Raum)
-- =============================================================================

CREATE TABLE location (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    type        location_type NOT NULL,
    parent_id   UUID REFERENCES location(id),  -- NULL = oberste Ebene (Gebäude)
    capacity    INTEGER CHECK (capacity > 0),
    notes       TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE location IS
    'Räume und Gebäude. Hierarchisch: Gebäude → Räume via parent_id.';

-- =============================================================================
-- 6. LOCATION_DEPENDENCY
-- Abhängigkeiten zwischen Räumen (z.B. Kirchenschiff belegt → Sakristei auch)
-- =============================================================================

CREATE TABLE location_dependency (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id             UUID NOT NULL REFERENCES location(id),
    depends_on_location_id  UUID NOT NULL REFERENCES location(id),
    type                    dependency_type NOT NULL,
    CHECK (location_id <> depends_on_location_id)
);

COMMENT ON TABLE location_dependency IS
    'Wenn location_id belegt ist, gilt depends_on_location_id ebenfalls als belegt (exclusive) oder eingeschränkt (shared).';

-- =============================================================================
-- 7. RESOURCE
-- Begrenzte Ressourcen (z.B. Mikrofone, Stühle)
-- =============================================================================

CREATE TABLE resource (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    total_quantity  INTEGER NOT NULL CHECK (total_quantity > 0),
    notes           TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE resource IS
    'Begrenzte Ressourcen mit Gesamtmenge. Konfliktprüfung erfolgt bei Buchung.';

-- =============================================================================
-- 8. BLACKOUT
-- Sperrzeiten (keine Anlässe möglich, ausser Admin-Override)
-- =============================================================================

CREATE TABLE blackout (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ NOT NULL,
    reason      TEXT,
    created_by  UUID NOT NULL REFERENCES app_user(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_time > start_time)
);

COMMENT ON TABLE blackout IS
    'Sperrzeiten. Nur Admin kann Override genehmigen (blackout_override).';

-- =============================================================================
-- 9. BLACKOUT_LOCATION
-- Sperrzeit gilt für spezifische Räume (NULL-Einträge = systemweit, via fehlendem Eintrag)
-- =============================================================================

CREATE TABLE blackout_location (
    blackout_id     UUID NOT NULL REFERENCES blackout(id) ON DELETE CASCADE,
    location_id     UUID NOT NULL REFERENCES location(id),
    PRIMARY KEY (blackout_id, location_id)
);

COMMENT ON TABLE blackout_location IS
    'Räume die von einer Sperrzeit betroffen sind. Ohne Einträge gilt die Sperrzeit systemweit.';

-- =============================================================================
-- 10. EVENT
-- Anlass als zentrales Objekt
-- =============================================================================

CREATE TABLE event (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    status          event_status NOT NULL DEFAULT 'requested',
    is_public       BOOLEAN NOT NULL DEFAULT FALSE,  -- Sichtbar im öffentlichen Kalender?
    category        TEXT,                            -- Freitext-Kategorie (MVP)
    -- Workflow
    created_by      UUID NOT NULL REFERENCES app_user(id),
    approved_by     UUID REFERENCES app_user(id),   -- Wer hat freigegeben?
    approved_at     TIMESTAMPTZ,
    rejection_reason TEXT,                           -- Begründung bei rejected
    -- Soft Delete
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Self-Approval-Sperre: approved_by darf nicht gleich created_by sein
    CHECK (approved_by IS NULL OR approved_by <> created_by)
);

COMMENT ON TABLE event IS
    'Zentrales Objekt. Ein Event hat einen oder mehrere Occurrences (Termine).';
COMMENT ON COLUMN event.is_public IS
    'Setzbar durch Requester bei Erstellung; Approver kann ändern. Nur confirmed + is_public = true ist öffentlich sichtbar.';
COMMENT ON COLUMN event.approved_by IS
    'Darf nicht gleich created_by sein (Self-Approval-Verbot, auch per CHECK-Constraint).';

-- =============================================================================
-- 11. EVENT_OCCURRENCE
-- Konkrete Termine eines Anlasses
-- =============================================================================

CREATE TABLE event_occurrence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    -- Konflikt-Flags (persistiert, nicht nur berechnet)
    has_conflict    BOOLEAN NOT NULL DEFAULT FALSE,
    is_tentative    BOOLEAN NOT NULL DEFAULT FALSE,
    -- Einzelner Termin storniert (ohne ganzen Anlass zu canceln)
    is_cancelled    BOOLEAN NOT NULL DEFAULT FALSE,
    -- Für wiederkehrende Anlässe (Future Scope): parent_id
    parent_id       UUID REFERENCES event_occurrence(id),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_time > start_time)
);

-- Generierter Zeitraum für effiziente Konfliktprüfung
ALTER TABLE event_occurrence
    ADD COLUMN time_range tstzrange
    GENERATED ALWAYS AS (tstzrange(start_time, end_time, '[)')) STORED;

COMMENT ON TABLE event_occurrence IS
    'Konkrete Termine (Instanzen) eines Events. time_range wird automatisch berechnet.';
COMMENT ON COLUMN event_occurrence.has_conflict IS
    'Wird bei jeder Buchungsänderung neu berechnet und persistiert.';
COMMENT ON COLUMN event_occurrence.parent_id IS
    'Für künftige wiederkehrende Anlässe (Future Scope). Im MVP nicht verwendet.';

-- =============================================================================
-- 12. OCCURRENCE_LOCATION
-- Welche Räume sind für einen Termin gebucht?
-- =============================================================================

CREATE TABLE occurrence_location (
    occurrence_id   UUID NOT NULL REFERENCES event_occurrence(id) ON DELETE CASCADE,
    location_id     UUID NOT NULL REFERENCES location(id),
    PRIMARY KEY (occurrence_id, location_id)
);

-- =============================================================================
-- 13. OCCURRENCE_RESOURCE
-- Welche Ressourcen sind für einen Termin gebucht?
-- =============================================================================

CREATE TABLE occurrence_resource (
    occurrence_id   UUID NOT NULL REFERENCES event_occurrence(id) ON DELETE CASCADE,
    resource_id     UUID NOT NULL REFERENCES resource(id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (occurrence_id, resource_id)
);

-- =============================================================================
-- 14. OCCURRENCE_PARTICIPANT
-- Beteiligte Personen pro Termin — als Snapshot (DSG-konform)
-- =============================================================================

CREATE TABLE occurrence_participant (
    occurrence_id   UUID NOT NULL REFERENCES event_occurrence(id) ON DELETE CASCADE,
    person_id       UUID NOT NULL REFERENCES person(id),
    role            TEXT,           -- Funktion beim Anlass (z.B. "Organist", "Lektorin")
    -- Snapshot zum Zeitpunkt der Buchung
    -- Bei Anonymisierung auf Antrag: name_snapshot → '[anonymisiert]', Kontaktfelder → NULL
    name_snapshot   TEXT NOT NULL,
    email_snapshot  TEXT,
    phone_snapshot  TEXT,
    PRIMARY KEY (occurrence_id, person_id)
);

COMMENT ON TABLE occurrence_participant IS
    'Snapshot-Tabelle: Personendaten werden zum Buchungszeitpunkt kopiert. Spätere Änderungen an person wirken nicht rückwirkend.';

-- =============================================================================
-- 15. BLACKOUT_OVERRIDE
-- Admin-Override für Anlässe trotz Sperrzeit (wird geloggt)
-- =============================================================================

CREATE TABLE blackout_override (
    occurrence_id   UUID NOT NULL REFERENCES event_occurrence(id),
    blackout_id     UUID NOT NULL REFERENCES blackout(id),
    approved_by     UUID NOT NULL REFERENCES app_user(id),  -- Muss Admin sein
    reason          TEXT NOT NULL,                          -- Begründung verpflichtend
    approved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (occurrence_id, blackout_id)
);

COMMENT ON TABLE blackout_override IS
    'Jeder Override durch Admin wird hier protokolliert. reason ist verpflichtend.';

-- =============================================================================
-- 16. CHANGE_LOG (Audit Log)
-- Jede schreibende Operation wird hier protokolliert
-- =============================================================================

CREATE TABLE change_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,          -- z.B. 'event', 'event_occurrence', 'person'
    entity_id       UUID NOT NULL,
    field_name      TEXT,                   -- NULL bei Erstellung/Löschung des ganzen Datensatzes
    old_value       TEXT,
    new_value       TEXT,
    action          TEXT NOT NULL,          -- 'INSERT', 'UPDATE', 'DELETE'
    changed_by      UUID REFERENCES app_user(id),
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Optionales Begründungsfeld (verpflichtend bei Konflikt-Override)
    reason          TEXT
);

COMMENT ON TABLE change_log IS
    'Audit Log für alle schreibenden Operationen. Wird zusammen mit den Anlässen archiviert und physisch gelöscht (Archivierungsjob).';
COMMENT ON COLUMN change_log.old_value IS
    'Kann Personendaten enthalten. Wird bei Anonymisierung auf Antrag bereinigt.';

-- =============================================================================
-- INDIZES
-- =============================================================================

-- Konfliktprüfung (Kernindex des Systems)
CREATE INDEX idx_occurrence_time_range
    ON event_occurrence USING GIST (time_range);

-- Raumkonflikt: Welche Termine überschneiden sich in einem Raum?
CREATE INDEX idx_occurrence_location_location
    ON occurrence_location (location_id);

-- Ressourcenkonflikt
CREATE INDEX idx_occurrence_resource_resource
    ON occurrence_resource (resource_id);

-- Event-Lookup
CREATE INDEX idx_occurrence_event
    ON event_occurrence (event_id);

-- Konflikt-Flag (für Dashboard/Admin-Übersicht)
CREATE INDEX idx_occurrence_conflict
    ON event_occurrence (has_conflict, is_tentative)
    WHERE has_conflict = TRUE;

-- Audit Log: häufigste Query ist nach entity_id
CREATE INDEX idx_change_log_entity
    ON change_log (entity_id, entity_type);

CREATE INDEX idx_change_log_changed_at
    ON change_log (changed_at);

-- Event-Status (für Workflow-Queries)
CREATE INDEX idx_event_status
    ON event (status)
    WHERE deleted_at IS NULL;

-- Archivierungsjob: findet alte Datensätze effizient
CREATE INDEX idx_event_created_at
    ON event (created_at)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_occurrence_start_time
    ON event_occurrence (start_time);

-- =============================================================================
-- HILFSFUNKTION: Konfliktprüfung für einen Raum
-- Gibt TRUE zurück wenn der Zeitraum in diesem Raum bereits belegt ist
-- =============================================================================

CREATE OR REPLACE FUNCTION check_location_conflict(
    p_location_id   UUID,
    p_start_time    TIMESTAMPTZ,
    p_end_time      TIMESTAMPTZ,
    p_exclude_id    UUID DEFAULT NULL  -- Eigene occurrence_id bei Updates ausschliessen
)
RETURNS TABLE (
    occurrence_id   UUID,
    event_id        UUID,
    event_title     TEXT,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ
)
LANGUAGE sql STABLE AS $$
    SELECT
        eo.id,
        e.id,
        e.title,
        eo.start_time,
        eo.end_time
    FROM event_occurrence eo
    JOIN event e ON e.id = eo.event_id
    JOIN occurrence_location ol ON ol.occurrence_id = eo.id
    WHERE ol.location_id = p_location_id
      AND eo.is_cancelled = FALSE
      AND e.status NOT IN ('cancelled', 'rejected')
      AND e.deleted_at IS NULL
      AND eo.time_range && tstzrange(p_start_time, p_end_time, '[)')
      AND (p_exclude_id IS NULL OR eo.id <> p_exclude_id);
$$;

COMMENT ON FUNCTION check_location_conflict IS
    'Gibt alle kollidierenden Termine für einen Raum zurück. Verwendung: innerhalb einer Transaktion vor INSERT/UPDATE aufrufen.';

-- =============================================================================
-- HILFSFUNKTION: Ressourcen-Verfügbarkeit prüfen
-- Gibt verfügbare Menge zurück (negativ = Überbuchung)
-- =============================================================================

CREATE OR REPLACE FUNCTION check_resource_availability(
    p_resource_id   UUID,
    p_start_time    TIMESTAMPTZ,
    p_end_time      TIMESTAMPTZ,
    p_exclude_id    UUID DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT
        r.total_quantity - COALESCE(SUM(orr.quantity), 0)
    FROM resource r
    LEFT JOIN occurrence_resource orr ON orr.resource_id = r.id
    LEFT JOIN event_occurrence eo ON eo.id = orr.occurrence_id
    LEFT JOIN event e ON e.id = eo.event_id
    WHERE r.id = p_resource_id
      AND (eo.id IS NULL OR (
          eo.is_cancelled = FALSE
          AND e.status NOT IN ('cancelled', 'rejected')
          AND e.deleted_at IS NULL
          AND eo.time_range && tstzrange(p_start_time, p_end_time, '[)')
          AND (p_exclude_id IS NULL OR eo.id <> p_exclude_id)
      ))
    GROUP BY r.total_quantity;
$$;

COMMENT ON FUNCTION check_resource_availability IS
    'Gibt verfügbare Restmenge zurück. Negatives Ergebnis = Überbuchung.';

-- =============================================================================
-- HILFSFUNKTION: Sperrzeit-Prüfung
-- =============================================================================

CREATE OR REPLACE FUNCTION check_blackout(
    p_location_id   UUID,
    p_start_time    TIMESTAMPTZ,
    p_end_time      TIMESTAMPTZ
)
RETURNS TABLE (
    blackout_id     UUID,
    reason          TEXT,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ
)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT
        b.id,
        b.reason,
        b.start_time,
        b.end_time
    FROM blackout b
    LEFT JOIN blackout_location bl ON bl.blackout_id = b.id
    WHERE tstzrange(b.start_time, b.end_time, '[)') && tstzrange(p_start_time, p_end_time, '[)')
      AND (
          bl.location_id = p_location_id  -- Raumspezifische Sperrzeit
          OR NOT EXISTS (                  -- ODER systemweite Sperrzeit (keine Raum-Einschränkung)
              SELECT 1 FROM blackout_location bl2 WHERE bl2.blackout_id = b.id
          )
      );
$$;

-- =============================================================================
-- ARCHIVIERUNGSJOB: Anonymisierungs-Funktion (Sofort-Anonymisierung auf Antrag)
-- Wird verwendet für: Recht auf Vergessenwerden (DSG Art. 32)
-- NICHT für den regulären Archivierungszyklus (der löscht physisch)
-- =============================================================================

CREATE OR REPLACE FUNCTION anonymize_person(p_person_id UUID)
RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
    -- Stammdaten anonymisieren
    UPDATE person SET
        name            = '[anonymisiert]',
        email           = NULL,
        phone           = NULL,
        anonymized_at   = NOW(),
        updated_at      = NOW()
    WHERE id = p_person_id;

    -- Snapshots in Terminen anonymisieren
    UPDATE occurrence_participant SET
        name_snapshot   = '[anonymisiert]',
        email_snapshot  = NULL,
        phone_snapshot  = NULL
    WHERE person_id = p_person_id;

    -- Audit Log: lesbare Felder bereinigen (UUIDs bleiben für Systemintegrität)
    UPDATE change_log SET
        old_value = '[anonymisiert]',
        new_value = '[anonymisiert]'
    WHERE entity_type = 'person'
      AND entity_id = p_person_id
      AND (old_value IS NOT NULL OR new_value IS NOT NULL);

    -- Änderung selbst im Audit Log festhalten
    INSERT INTO change_log (entity_type, entity_id, action, new_value, changed_at)
    VALUES ('person', p_person_id, 'ANONYMIZE', 'Anonymisierung auf Antrag (DSG)', NOW());
END;
$$;

COMMENT ON FUNCTION anonymize_person IS
    'Sofort-Anonymisierung auf Antrag (DSG Recht auf Vergessenwerden). Bereinigt person, occurrence_participant und change_log. NICHT für den regulären Archivierungszyklus.';

-- =============================================================================
-- 17. DUTY_SCHEDULE
-- Dienstplan: wer hat an welchem Tag Dienst (rein informativ)
-- Keine Workflow-Logik, keine automatische Verknüpfung mit Anlässen.
-- Dient der Sichtbarkeit im Kalender: Seelsorger sehen wer ansprechbar ist.
-- =============================================================================

CREATE TABLE duty_schedule (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    person_id       UUID NOT NULL REFERENCES person(id),
    is_full_day     BOOLEAN NOT NULL DEFAULT TRUE,
    start_time      TIME,       -- NULL wenn ganzer Tag
    end_time        TIME,       -- NULL wenn ganzer Tag
    note            TEXT,       -- Freitext, z.B. "nur für Probe, kein Volldienst"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Wenn nicht ganzer Tag, müssen Zeiten gesetzt sein
    CHECK (is_full_day = TRUE OR (start_time IS NOT NULL AND end_time IS NOT NULL)),
    CHECK (start_time IS NULL OR end_time IS NULL OR end_time > start_time)
);

COMMENT ON TABLE duty_schedule IS
    'Informatives Dienstplan-Journal. Zeigt wer an welchem Tag anwesend/erreichbar ist. '
    'Keine automatische Verknüpfung mit Anlässen — Interpretation bleibt Menschensache. '
    'Spezialfall: is_full_day=FALSE für Teilpräsenz (z.B. Mesmer an freiem Tag für Probe).';

COMMENT ON COLUMN duty_schedule.note IS
    'Freitext für Spezialfälle, z.B. "nur für Probe 14-16h, danach nicht erreichbar".';

-- Index: typischste Query ist "wer hat diese Woche Dienst?"
CREATE INDEX idx_duty_schedule_date
    ON duty_schedule (date, person_id);

-- =============================================================================
-- ENDE SCHEMA
-- =============================================================================
