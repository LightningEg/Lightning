-- The asset class silver is held under (NF-9C1; a new profile gets it from the seed). Priced by hand for now.
INSERT OR IGNORE INTO asset_classes(code, name, parent_id, sort_order, created_at, updated_at)
SELECT 'SILVER', 'Silver', NULL, COALESCE((SELECT MAX(sort_order) FROM asset_classes), 0) + 1,
       strftime('%Y-%m-%dT%H:%M:%S', 'now'), strftime('%Y-%m-%dT%H:%M:%S', 'now');
