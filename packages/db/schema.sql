-- RACEJUDGE Phase 1 schema
-- PostgreSQL 16 + pgvector + TimescaleDB
-- Run against Neon DB: psql $DATABASE_URL -f packages/db/schema.sql

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector

-- ---------------------------------------------------------------------------
-- decisions
-- ---------------------------------------------------------------------------
-- Core table. One row per unique stewards' decision PDF (deduped by sha256).

CREATE TABLE IF NOT EXISTS decisions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id          TEXT        NOT NULL UNIQUE,          -- first 16 hex chars of sha256
    sha256_hash     TEXT        NOT NULL UNIQUE,
    title           TEXT        NOT NULL,
    pdf_url         TEXT        NOT NULL,
    r2_key          TEXT,                                  -- Cloudflare R2 object key
    season          SMALLINT    NOT NULL CHECK (season >= 2018),
    published_at    TEXT,                                  -- raw string from FIA page
    raw_text        TEXT        NOT NULL DEFAULT '',
    char_count      INTEGER     NOT NULL DEFAULT 0,
    needs_ocr       BOOLEAN     NOT NULL DEFAULT FALSE,
    parser_version  TEXT        NOT NULL DEFAULT 'v1.0-pdfplumber',
    parsed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_season     ON decisions (season);
CREATE INDEX IF NOT EXISTS idx_decisions_parsed_at  ON decisions (parsed_at DESC);

-- ---------------------------------------------------------------------------
-- incidents
-- ---------------------------------------------------------------------------
-- Structured extraction from decision text (Phase 2).
-- One row per incident mentioned in a decision document.

CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    decision_id     UUID        NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    car_number      SMALLINT,
    driver_name     TEXT,
    infraction_type TEXT,                                  -- e.g. "collision", "track limits"
    outcome         TEXT,                                  -- e.g. "5s penalty", "reprimand"
    penalty_points  SMALLINT,
    lap_number      SMALLINT,
    session_type    TEXT,                                  -- "race", "qualifying", "sprint"
    incident_text   TEXT,                                  -- extracted verbatim incident description
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_decision_id   ON incidents (decision_id);
CREATE INDEX IF NOT EXISTS idx_incidents_infraction    ON incidents (infraction_type);
CREATE INDEX IF NOT EXISTS idx_incidents_outcome       ON incidents (outcome);

-- ---------------------------------------------------------------------------
-- embeddings
-- ---------------------------------------------------------------------------
-- BGE-M3 embeddings for precedent search (Phase 4).
-- Stored separately so the decisions table stays lean.

CREATE TABLE IF NOT EXISTS embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    decision_id     UUID        NOT NULL REFERENCES decisions(id) ON DELETE CASCADE UNIQUE,
    embedding       vector(1024),                          -- BGE-M3 output dimension
    model_version   TEXT        NOT NULL DEFAULT 'bge-m3-v1',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index for ANN search — created after bulk load (Phase 4)
-- CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- annotation_pairs
-- ---------------------------------------------------------------------------
-- Labelled incident pairs for BGE-M3 fine-tuning (Pre-Work / Phase 4).

CREATE TABLE IF NOT EXISTS annotation_pairs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anchor_id       TEXT        NOT NULL,                  -- doc_id
    positive_id     TEXT,                                  -- similar doc_id (triplet positive)
    negative_id     TEXT,                                  -- dissimilar doc_id (triplet negative)
    label           TEXT        NOT NULL CHECK (label IN ('similar', 'dissimilar')),
    annotator       TEXT        NOT NULL DEFAULT 'human',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- ingested_hashes
-- ---------------------------------------------------------------------------
-- Mirrors the local JSON dedup file for the Phase 1 pipeline.
-- Allows the scraper to check dedup without reading the full decisions table.

CREATE TABLE IF NOT EXISTS ingested_hashes (
    sha256_hash     TEXT PRIMARY KEY,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- guidelines
-- ---------------------------------------------------------------------------
-- FIA Penalty Guidelines + Driving Standards Guidelines (Phase 1 seed).
-- Used for article_cited feature in Model 4A and LLM context in Model 4B.

CREATE TABLE IF NOT EXISTS guidelines (
    article_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_name       TEXT        NOT NULL,
    section             TEXT,
    article_number      TEXT        NOT NULL,
    article_text        TEXT        NOT NULL,
    recommended_penalty TEXT,
    effective_date      DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_name, article_number)
);

CREATE INDEX IF NOT EXISTS idx_guidelines_document   ON guidelines (document_name);
CREATE INDEX IF NOT EXISTS idx_guidelines_article    ON guidelines (article_number);

-- ---------------------------------------------------------------------------
-- team_radio_clips
-- ---------------------------------------------------------------------------
-- Downloaded and transcribed team radio clips (Phase 3).

CREATE TABLE IF NOT EXISTS team_radio_clips (
    clip_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_key     INTEGER         NOT NULL,
    driver_number   SMALLINT        NOT NULL,
    date            TIMESTAMPTZ     NOT NULL,
    recording_url   TEXT            NOT NULL UNIQUE,
    r2_key          TEXT,                                  -- Cloudflare R2 key after upload
    transcript      TEXT,                                  -- Whisper output
    speaker_label   TEXT,                                  -- 'driver'/'engineer'/'other'
    sentiment_score REAL,                                  -- Phase 5
    urgency_score   REAL,                                  -- Phase 5
    incident_id     UUID REFERENCES incidents(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_radio_session    ON team_radio_clips (session_key);
CREATE INDEX IF NOT EXISTS idx_radio_driver     ON team_radio_clips (driver_number);
CREATE INDEX IF NOT EXISTS idx_radio_date       ON team_radio_clips (date DESC);

-- ---------------------------------------------------------------------------
-- annotations
-- ---------------------------------------------------------------------------
-- Human annotation labels (Phase 2 labelling UI).

CREATE TABLE IF NOT EXISTS annotations (
    annotation_id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id          TEXT        NOT NULL,
    annotator       TEXT        NOT NULL DEFAULT 'anonymous',
    infraction_type TEXT,
    outcome         TEXT,
    penalty_class   TEXT        CHECK (penalty_class IN ('NFA','REP','5s','10s','DT','GRID','DSQ')),
    penalty_points  SMALLINT,
    article_cited   TEXT,
    notes           TEXT,
    positive_doc_id TEXT,                                  -- triplet positive
    negative_doc_id TEXT,                                  -- triplet negative
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_annotations_doc_id    ON annotations (doc_id);
CREATE INDEX IF NOT EXISTS idx_annotations_annotator ON annotations (annotator);

-- ---------------------------------------------------------------------------
-- events
-- ---------------------------------------------------------------------------
-- One row per Grand Prix weekend (round).

CREATE TABLE IF NOT EXISTS events (
    event_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    season          SMALLINT    NOT NULL CHECK (season >= 2018),
    round_number    SMALLINT    NOT NULL,
    circuit         TEXT        NOT NULL,
    country         TEXT        NOT NULL,
    event_name      TEXT        NOT NULL,
    event_date      DATE,
    openf1_meeting_key INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (season, round_number)
);

CREATE INDEX IF NOT EXISTS idx_events_season ON events (season);

-- ---------------------------------------------------------------------------
-- sessions
-- ---------------------------------------------------------------------------
-- One row per session within an event (FP1/FP2/FP3/Q/Sprint/Race).

CREATE TABLE IF NOT EXISTS sessions (
    session_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id        UUID        NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    session_type    TEXT        NOT NULL CHECK (session_type IN
                        ('practice_1','practice_2','practice_3',
                         'qualifying','sprint_qualifying','sprint','race')),
    session_key     INTEGER     UNIQUE,                    -- OpenF1 session_key
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_event_id    ON sessions (event_id);
CREATE INDEX IF NOT EXISTS idx_sessions_session_key ON sessions (session_key);

-- ---------------------------------------------------------------------------
-- race_control_messages
-- ---------------------------------------------------------------------------
-- OpenF1 race control messages (flags, investigations, VSC, SC, etc.).

CREATE TABLE IF NOT EXISTS race_control_messages (
    message_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_key     INTEGER     NOT NULL,
    date            TIMESTAMPTZ NOT NULL,
    category        TEXT,                                  -- 'Flag', 'SafetyCar', 'Drs', etc.
    message         TEXT        NOT NULL,
    flag            TEXT,                                  -- 'GREEN', 'YELLOW', 'RED', 'CHEQUERED'
    scope           TEXT,                                  -- 'Track', 'Sector', 'Driver'
    sector          SMALLINT,
    driver_number   SMALLINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rcm_session_key ON race_control_messages (session_key);
CREATE INDEX IF NOT EXISTS idx_rcm_date        ON race_control_messages (date DESC);
CREATE INDEX IF NOT EXISTS idx_rcm_category    ON race_control_messages (category);

-- ---------------------------------------------------------------------------
-- lap_features
-- ---------------------------------------------------------------------------
-- Per-lap telemetry features for incidents (Phase 3 + 5).
-- Designed as a TimescaleDB hypertable on the 'time' column.

CREATE TABLE IF NOT EXISTS lap_features (
    id              UUID        NOT NULL DEFAULT uuid_generate_v4(),
    time            TIMESTAMPTZ NOT NULL,                  -- hypertable partition key
    session_key     INTEGER     NOT NULL,
    driver_number   SMALLINT    NOT NULL,
    lap_number      SMALLINT    NOT NULL,
    lap_time_ms     INTEGER,                               -- lap time in milliseconds
    sector1_ms      INTEGER,
    sector2_ms      INTEGER,
    sector3_ms      INTEGER,
    speed_i1        REAL,                                  -- speed trap km/h
    speed_i2        REAL,
    speed_fl        REAL,
    speed_st        REAL,
    compound        TEXT,                                  -- 'SOFT','MEDIUM','HARD','INTER','WET'
    tyre_life_laps  SMALLINT,
    is_personal_best BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, time)
);

-- TimescaleDB hypertable (run after CREATE TABLE if TimescaleDB is enabled):
-- SELECT create_hypertable('lap_features', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_lap_features_session  ON lap_features (session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_lap_features_time     ON lap_features (time DESC);

-- ---------------------------------------------------------------------------
-- Full-text search on decisions
-- ---------------------------------------------------------------------------
-- GIN index for fast Postgres FTS (Phase 2 upgrade from BM25 in-memory).
-- The tsvector combines title (weight A) + raw_text (weight B).

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(raw_text, '')), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_decisions_fts
    ON decisions USING gin(search_vector);
