-- IV-12J4: a variable certificate's rate changes are dated, not a rewrite of its whole schedule. Each row is the
-- annual rate (percentage points, as cd_certificates.annual_rate) in force from its date; a period of the bank's
-- schedule earns at the rate in force on its first day. No existing certificate has one, so no figure moves.
CREATE TABLE cd_rate_changes (
    id             INTEGER PRIMARY KEY,
    certificate_id INTEGER NOT NULL REFERENCES cd_certificates(id) ON DELETE CASCADE,
    effective_date TEXT NOT NULL CHECK (effective_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    annual_rate    TEXT NOT NULL CHECK (CAST(annual_rate AS REAL) BETWEEN 0 AND 100),
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (certificate_id, effective_date)
);
