-- A property's instalments and its rent and running costs (NF-12M3, NF-12M4).
-- property_contracts: the planned bill that schedules what is still to pay the developer for a flat bought off plan.
-- property_flows: a money in (rent) or money out (maintenance, tax, a broker's fee) that belongs to a property.
-- Two categories under Investment for them: Rent received and Property costs.
CREATE TABLE property_contracts (
    account_id      INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    planned_item_id INTEGER NOT NULL UNIQUE REFERENCES planned_items(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE property_flows (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    account_id     INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at     TEXT NOT NULL
);
CREATE INDEX ix_property_flows_account ON property_flows(account_id);

-- Rent received counts as investment income (beside dividends and interest); Property costs is an investment-family
-- outflow, so it is never budget spending or household Money out.
INSERT INTO categories(code,name,parent_id,movement,scope,income_class,family,default_reimbursable,is_system,active,sort_order,created_at,updated_at)
SELECT 'EXP.INVEST.RENT','Rent received',id,'INFLOW',NULL,'INVESTMENT','INVESTMENT',0,0,1,6,datetime('now'),datetime('now')
FROM categories WHERE code='EXP.INVEST'
  AND NOT EXISTS (SELECT 1 FROM categories WHERE code='EXP.INVEST.RENT');
INSERT INTO categories(code,name,parent_id,movement,scope,income_class,family,default_reimbursable,is_system,active,sort_order,created_at,updated_at)
SELECT 'EXP.INVEST.PROPERTY','Property costs',id,'OUTFLOW',NULL,NULL,'INVESTMENT',0,0,1,7,datetime('now'),datetime('now')
FROM categories WHERE code='EXP.INVEST'
  AND NOT EXISTS (SELECT 1 FROM categories WHERE code='EXP.INVEST.PROPERTY');
