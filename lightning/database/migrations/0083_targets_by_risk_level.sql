-- Target allocation by risk level, not asset class (owner, 2026-11-14, NF-12AM). Each holding counts toward Low,
-- Medium or High risk: its class's level unless the user moved it, kept in financial_assets.allocation_bucket
-- (empty = its class's level). The class levels below match lightning/assets/risk.py DEFAULT_RISK.
-- 1. A holding moved to another class keeps that intent: it takes that class's level, or none if that is its own.
-- 2. Class targets are added up into their level (Fixed income 30% + Money market 10% = Low risk 40%).
WITH lvl(class_id, level) AS (
    SELECT id, CASE
        WHEN code || '.' GLOB 'STOCK.*' THEN 'High risk'
        WHEN code || '.' GLOB 'FUND.FIXED_INCOME.*' OR code || '.' GLOB 'FUND.MONEY_MARKET.*'
             OR code || '.' GLOB 'FUND.CLOUD.*' OR code || '.' GLOB 'DEPOSIT.*' OR code || '.' GLOB 'GAMEYA.*' THEN 'Low risk'
        ELSE 'Medium risk' END
    FROM asset_classes)
UPDATE financial_assets
SET allocation_bucket = (SELECT lvl.level FROM asset_classes ac JOIN lvl ON lvl.class_id = ac.id
                         WHERE ac.name = financial_assets.allocation_bucket ORDER BY ac.id LIMIT 1)
WHERE allocation_bucket IS NOT NULL AND allocation_bucket NOT IN ('Low risk', 'Medium risk', 'High risk');

WITH lvl(class_id, level) AS (
    SELECT id, CASE
        WHEN code || '.' GLOB 'STOCK.*' THEN 'High risk'
        WHEN code || '.' GLOB 'FUND.FIXED_INCOME.*' OR code || '.' GLOB 'FUND.MONEY_MARKET.*'
             OR code || '.' GLOB 'FUND.CLOUD.*' OR code || '.' GLOB 'DEPOSIT.*' OR code || '.' GLOB 'GAMEYA.*' THEN 'Low risk'
        ELSE 'Medium risk' END
    FROM asset_classes)
UPDATE financial_assets SET allocation_bucket = NULL
WHERE allocation_bucket = (SELECT level FROM lvl WHERE lvl.class_id = financial_assets.asset_class_id);

WITH lvl(class_id, level) AS (
    SELECT id, CASE
        WHEN code || '.' GLOB 'STOCK.*' THEN 'High risk'
        WHEN code || '.' GLOB 'FUND.FIXED_INCOME.*' OR code || '.' GLOB 'FUND.MONEY_MARKET.*'
             OR code || '.' GLOB 'FUND.CLOUD.*' OR code || '.' GLOB 'DEPOSIT.*' OR code || '.' GLOB 'GAMEYA.*' THEN 'Low risk'
        ELSE 'Medium risk' END
    FROM asset_classes),
old(weight, updated_at, class_id) AS (
    SELECT target_weight, updated_at, COALESCE(asset_class_id, (SELECT MIN(id) FROM asset_classes WHERE name = bucket))
    FROM investment_targets WHERE bucket NOT IN ('Low risk', 'Medium risk', 'High risk'))
INSERT INTO investment_targets(bucket, target_weight, updated_at, asset_class_id)
SELECT COALESCE(lvl.level, 'Medium risk'), MIN(100, SUM(old.weight)), MAX(old.updated_at), NULL
FROM old LEFT JOIN lvl ON lvl.class_id = old.class_id
WHERE true
GROUP BY COALESCE(lvl.level, 'Medium risk')
ON CONFLICT(bucket) DO NOTHING;

DELETE FROM investment_targets WHERE bucket NOT IN ('Low risk', 'Medium risk', 'High risk');
