-- Which purchases a sale takes its cost from, per brokerage account (NF-5B3). 'average' is one blended cost per
-- holding, the way Egyptian brokers show it and what every account used until now; 'fifo' sells the oldest purchase
-- first. Lots themselves are never stored: they are derived from the ledger every time.
ALTER TABLE accounts ADD COLUMN cost_method TEXT NOT NULL DEFAULT 'average' CHECK (cost_method IN ('average', 'fifo'));
