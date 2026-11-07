-- The asset class a balance fund is held under (IT-2AJ; a new profile gets it from the seed). A balance fund has no
-- share price: 1 unit is 1 pound, its balance grows by interest posted as units.
INSERT OR IGNORE INTO asset_classes(code, name, parent_id, sort_order, created_at, updated_at)
SELECT 'FUND.BALANCE', 'Balance Fund', (SELECT id FROM asset_classes WHERE code = 'FUND'),
       COALESCE((SELECT MAX(sort_order) FROM asset_classes), 0) + 1,
       strftime('%Y-%m-%dT%H:%M:%S', 'now'), strftime('%Y-%m-%dT%H:%M:%S', 'now');
