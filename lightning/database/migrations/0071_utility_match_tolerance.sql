-- Preserve the original checked column and all foreign-key relationships.
-- New utility bills may opt into a larger tolerance; existing policies are unchanged.
ALTER TABLE planned_items ADD COLUMN match_tolerance_override_pct INTEGER
    CHECK (match_tolerance_override_pct IS NULL OR
           (match_tolerance_pct = 25 AND match_tolerance_override_pct BETWEEN 26 AND 50));
