-- The asset class a flat, a house or land is held under (NF-12M1; a new profile gets it from the seed). An Other
-- account whose kind is flat, house or land counts here instead of Other Investments; its cost is what you paid.
INSERT OR IGNORE INTO asset_classes(code, name, parent_id, sort_order, created_at, updated_at)
SELECT 'REAL_ESTATE', 'Real estate', NULL, COALESCE((SELECT MAX(sort_order) FROM asset_classes), 0) + 1,
       strftime('%Y-%m-%dT%H:%M:%S', 'now'), strftime('%Y-%m-%dT%H:%M:%S', 'now');
