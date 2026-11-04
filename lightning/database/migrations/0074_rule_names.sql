-- A label never changes a rule's matching or category actions.
ALTER TABLE rules ADD COLUMN name TEXT NOT NULL DEFAULT '' CHECK(length(name)<=120);
