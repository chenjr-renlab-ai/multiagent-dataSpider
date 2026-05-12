-- MultiAgent DataSpider -- Database Schema Initialisation
-- PostgreSQL 16+

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -------------------------------------------------------------------
-- Missions
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS missions (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         TEXT NOT NULL,
    description  TEXT,
    config       JSONB NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    job_total    INT DEFAULT 0,
    job_done     INT DEFAULT 0,
    job_failed   INT DEFAULT 0
);

-- -------------------------------------------------------------------
-- Raw events (one row per crawled URL before extraction)
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id  UUID REFERENCES missions(id) ON DELETE SET NULL,
    target_url  TEXT,
    source_type TEXT,
    raw_content TEXT,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------------------
-- Scraped data (extracted + validated fields)
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scraped_data (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id       UUID REFERENCES missions(id) ON DELETE SET NULL,
    target_url       TEXT,
    extracted_fields JSONB,
    confidence       FLOAT DEFAULT 1.0,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_scraped_mission   ON scraped_data(mission_id);
CREATE INDEX IF NOT EXISTS idx_scraped_created   ON scraped_data(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_mission       ON raw_events(mission_id);
CREATE INDEX IF NOT EXISTS idx_raw_captured      ON raw_events(captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_missions_status   ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_created  ON missions(created_at DESC);
