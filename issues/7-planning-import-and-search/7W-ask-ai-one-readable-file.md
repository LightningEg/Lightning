---
title: Ask AI: one readable file with the question, Lightning's own words, the answers and the drivers
type: feature
pillar: understand
size: L
status: new
created: 2026-10-31
by: Claude Sonnet 5.5
---
## Report
Owner, 2026-10-31: users should extract rich data and context in a second and ask an AI, without missing a beat. Today there are two outputs and neither is built for that. *Export all data* (`workflows/data_export.py`) is a round-trip backup: every table, schema columns at the tail, 20-plus sheets. *Export for AI* (`workflows/ai_analysis.py`) is better but is still four Excel sheets, a 27-column Transactions sheet and a rule-heavy prompt.

## Fix
One button gives one self-contained file to paste or upload (Markdown, with a JSON block for exact figures). It leads with a short glossary of Lightning's own terms (safe to spend, reserve, owned position), then the answers (Lightning's calculated totals), then the drivers, then the rows. Extends 7V (the AI prompt buttons); the prompt text is still never open on a page.

## 7W1 Look at what exists · S
Run both exports on the demo profile and write down, with the file open, what a person or an AI cannot read in a second. Evidence for the design below.

## 7W2 The file · L
Glossary header, answers, drivers, rows; period and currency stated once; whole EGP on big figures; Arabic and English.

## 7W3 Presets · M
Monthly review, where did the money go, budget check, net worth: each a question plus the right slice.

## 7W4 Sizes and masking · M
A one-page digest, a month with its top transactions, and the full ledger; an option that replaces names with stable labels.

## 7W5 Separate the machine export · M
Keep the all-tables workbook only for backup, inspection and import round trips; move it out of the main flow.

## 7W6 Tests · S
Mohab-year run, a test that no prompt is open on a page, and Arabic strings.
