-- IV-3BH6: use sentence case for untouched built-in category names.
-- Match both code and exact old name so custom names and codes survive upgrades.
UPDATE categories SET name = 'Unaccounted money found' WHERE code = 'INC.UNACCOUNTED' AND name = 'Unaccounted Money Found' COLLATE BINARY;
UPDATE categories SET name = 'Food & groceries' WHERE code = 'EXP.PERSONAL.FOOD' AND name = 'Food & Groceries' COLLATE BINARY;
UPDATE categories SET name = 'Eating out' WHERE code = 'EXP.PERSONAL.DINING' AND name = 'Eating Out' COLLATE BINARY;
UPDATE categories SET name = 'Housing & rent' WHERE code = 'EXP.PERSONAL.HOUSING' AND name = 'Housing & Rent' COLLATE BINARY;
UPDATE categories SET name = 'Utilities & bills' WHERE code = 'EXP.PERSONAL.UTILITIES' AND name = 'Utilities & Bills' COLLATE BINARY;
UPDATE categories SET name = 'Gifts & donations' WHERE code = 'EXP.PERSONAL.GIFTS' AND name = 'Gifts & Donations' COLLATE BINARY;
UPDATE categories SET name = 'Gifts received' WHERE code = 'EXP.PERSONAL.GIFTS_RECEIVED' AND name = 'Gifts Received' COLLATE BINARY;
UPDATE categories SET name = 'Other income' WHERE code = 'EXP.PERSONAL.OTHER_INCOME' AND name = 'Other Income' COLLATE BINARY;
UPDATE categories SET name = 'Other personal' WHERE code = 'EXP.PERSONAL.OTHER' AND name = 'Other Personal' COLLATE BINARY;
UPDATE categories SET name = 'Fees & charges' WHERE code = 'EXP.PERSONAL.FEES' AND name = 'Fees & Charges' COLLATE BINARY;
UPDATE categories SET name = 'Business & freelance' WHERE code = 'EXP.WORK.BUSINESS' AND name = 'Business & Freelance' COLLATE BINARY;
UPDATE categories SET name = 'Office supplies' WHERE code = 'EXP.WORK.OFFICE' AND name = 'Office Supplies' COLLATE BINARY;
UPDATE categories SET name = 'Other work' WHERE code = 'EXP.WORK.OTHER' AND name = 'Other Work' COLLATE BINARY;
UPDATE categories SET name = 'System categories' WHERE code = 'EXP.SYSTEM' AND name = 'System Categories' COLLATE BINARY;
UPDATE categories SET name = 'Money held for others' WHERE code = 'EXP.SYSTEM.CUSTODY' AND name = 'Money Held for Others' COLLATE BINARY;
UPDATE categories SET name = 'Unaccounted spending' WHERE code = 'EXP.UNACCOUNTED' AND name = 'Unaccounted Spending' COLLATE BINARY;
UPDATE categories SET name = 'Investment fees' WHERE code = 'EXP.INVEST.FEES' AND name = 'Investment Fees' COLLATE BINARY;
UPDATE categories SET name = 'Other investment' WHERE code = 'EXP.INVEST.OTHER' AND name = 'Other Investment' COLLATE BINARY;
