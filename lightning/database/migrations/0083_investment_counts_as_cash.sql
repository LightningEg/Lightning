-- NF-7AU: the owner can mark an investment (a money-market or fixed-income fund that can be sold in days at no
-- loss) to count with cash: its owned value then joins Free cash. Off for every existing investment, so no figure moves.
ALTER TABLE financial_assets ADD COLUMN counts_as_cash INTEGER NOT NULL DEFAULT 0 CHECK (counts_as_cash IN (0, 1));
