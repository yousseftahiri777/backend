-- LAMÁ Admin Dashboard — page_views table (run if not using Alembic auto-migrate)
-- Safe to run multiple times (IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS page_views (
    id UUID PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    referrer VARCHAR,
    utm_source VARCHAR,
    utm_medium VARCHAR,
    utm_campaign VARCHAR,
    ip_address VARCHAR NOT NULL,
    country_code VARCHAR(10),
    city VARCHAR,
    is_vpn BOOLEAN NOT NULL DEFAULT FALSE,
    is_valid BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_page_views_session_id ON page_views (session_id);
CREATE INDEX IF NOT EXISTS ix_page_views_path ON page_views (path);
CREATE INDEX IF NOT EXISTS ix_page_views_is_valid ON page_views (is_valid);
CREATE INDEX IF NOT EXISTS ix_page_views_created_at ON page_views (created_at);
