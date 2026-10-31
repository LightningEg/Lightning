# Reports

Audits and reviews of a specific source snapshot. Active work lives in
[issues](../issues/INDEX.md); current behavior lives in [Architecture](../ai/ARCHITECTURE.md).

| Historical ID | Report | Review date | Kind | Open follow-ups |
| --- | --- | --- | --- | --- |
| audit-1 | [Audit 1: is Lightning ready to demo?](2026-10-20-demo-readiness/report.md) | 2026-10-20 | audit | 2E, 2F, 3G, 3H, 3Q, 3S, 3T, 5J, 5K, 7L, 7M |
| audit-2 | [Audit 2: backend efficiency and loose ends](2026-10-21-backend-efficiency/report.md) | 2026-10-21 | audit | 2A, 2C, 2E, 4A, 5A |
| audit-3 | [Audit 3: is the edit journal (multi-device sync) solid?](2026-10-21-edit-journal/report.md) | 2026-10-21 | audit | 4A |
| audit-5 | [Audit 5: is the backend engine efficient and streamlined?](2026-10-21-backend-streamlining/report.md) | 2026-10-21 | audit | 4A, 9J, 9K, 2AB |
| audit-4 | [Audit 4: backend correctness and failure boundaries](2026-10-23-backend-correctness/report.md) | 2026-10-23 | audit | 1G, 2A, 2C, 2J, 4A |
| audit-6 | [Audit 6: open pull request cleanup](2026-10-23-pull-request-cleanup/report.md) | 2026-10-23 | review | 1H |
| contributor-review | [Yusuf contribution review · 2026-10-23](2026-10-23-contributor-review/report.md) | 2026-10-23 | review | none |
| audit-7 | [Audit 7 — app visual flow](2026-10-25-app-visual-flow/report.md) | 2026-10-25 | audit | none |
| audit-8 | [Audit 8: backbone engine gaps and loose ends](2026-10-26-engine-audit/report.md) | 2026-10-26 | audit | 2J, 7R, 7S |
| dendera-theme | [Dendera theme: the workflow, and how it compares with the theme flow](2026-10-26-dendera-theme/report.md) | 2026-10-26 | research | none |
| pairing-hardening | [Pairing backend hardening and security review](2026-10-26-pairing-hardening/report.md) | 2026-10-26 | review | 4A |
| v1.5.0-preparation | [v1.5.0 PR review, theme switching and package preparation](2026-10-26-v150-release/report.md) | 2026-10-26 | release | 1H, 10A, 10C |
| store-and-community | [Store and community: unlocking themes, the market, rewards and staying in Lightning](2026-10-27-store-and-community/report.md) | 2026-10-27 | research | 10C, 10D |
| users-main-questions | [Users' main questions: what each screen must answer, with known gaps](2026-10-27-users-main-questions/report.md) | 2026-10-27 | reference | none |
| audit-9 | [Audit 9: loose ends after themes and sync, linking sections, and how the plan is filed](2026-10-28-loose-ends-and-linking/report.md) | 2026-10-28 | audit | 4K, 7T |
| fx-date-boundary | [Backend audit: exchange-rate date boundary](2026-10-29-backend-audit/report.md) | 2026-10-29 | audit | none |
| audit-10 | [Audit 10: the phone, tab by tab - quick actions and the answer first](2026-10-29-phone-tab-audit/report.md) | 2026-10-29 | audit | 3AD, 3AL, 3T |
| audit-11 | [Audit 11: the backend walked through use cases](2026-10-29-use-case-audit/report.md) | 2026-10-29 | audit | 2AD, 2E, 5J, 7U |
| audit-12 | [Audit 12: the PC app, tab by tab - clutter, hierarchy and flow](2026-10-30-desktop-tab-audit/report.md) | 2026-10-30 | audit | 3AM |

## Create and maintain a report

Use `reports/YYYY-MM-DD-subject/report.md`, with an adjacent `evidence/` directory when there is
evidence beyond the text.
Start from [the report template](../templates/report.md). Its header lines `Date:` and
`Reviewed commit:` are required (`tests/test_docs_structure.py`). Record scope, method, findings, evidence, limits and follow-up issue codes.
Evidence contains only dummy/sample data. Reproduction scripts find the repo root
from their own location and document the command to run from the repo root.

Preserve the original assessment. Append dated follow-ups with verification
references; do not silently turn an old verdict into a current-status claim.
Every actionable finding links to an active issue. Before deleting a finished
issue, replace report/feedback links with a commit-pinned copy of the issue,
resolution commit or regression test. Keep issue codes and old audit IDs so
history remains searchable. Register each new report in this catalogue.

**Kind** is audit (an owner-requested check of the app), review (of pull requests or a change),
release, research (a design question answered) or reference (kept to be read, not acted on).
**Open follow-ups** are the open items in [the plan](../issues/INDEX.md) that the report links or
that link back to it; when you finish an item, drop its code here too.

Old paths were migrated on 2026-10-26; the IDs below identify the same reports.
Use Git history for the original layout. Existing assessments and evidence are
preserved; a folder migration does not revalidate their findings.

[Website reports](https://github.com/LightningEg/Lightning_website/blob/main/reports/README.md) cover website-specific audits.
