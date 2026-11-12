-- The asset class for a fund whose units grow daily as interest, like a compounding bank account (OW-12AD, named
-- Cloud by the owner; a new profile gets it from the seed). Nothing existing is moved: pick it on the investment.
INSERT OR IGNORE INTO asset_classes(code, name, parent_id, sort_order, created_at, updated_at)
SELECT 'FUND.CLOUD', 'Cloud', (SELECT id FROM asset_classes WHERE code = 'FUND'),
       COALESCE((SELECT MAX(sort_order) FROM asset_classes), 0) + 1,
       strftime('%Y-%m-%dT%H:%M:%S', 'now'), strftime('%Y-%m-%dT%H:%M:%S', 'now');
