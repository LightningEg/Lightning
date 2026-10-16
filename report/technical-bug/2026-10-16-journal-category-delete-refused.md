---
title: Experimental journal refuses permanent deletion of an unused category
category: technical-bug
area: journal
status: reported
created: 2026-10-16
reporter: Codex
skills: number-audit
app_version: 1.1.0b1
commit: 2c636d6
repo: app
---

## Report

Severity: medium. The operation refuses safely without deleting financial data.
Using encrypted full-domain journal fixtures, create an unused category under EXP.PERSONAL, then submit categories.delete_or_archive. The home records rejected / financial-validation. Executing the same action through preview.changes raises SQLCipher DatabaseError: not authorized at lightning/categories/service.py:355, translated by the journal writing guard to ValidationError. Archiving a referenced category is a separate path.

Observed during the render-time form-baseline regression tests on codex/edit-journal, 2026-10-16. Evidence: /workspace/journal-category-delete-debug.log (local test output, dummy profiles). Investigate the write authorizer and SQLite foreign-key side effects before claiming complete native category routing. Preserve the local-only data boundary; do not broadly permit arbitrary extra-table writes.
