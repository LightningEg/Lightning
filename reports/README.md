# Reports

Audits and reviews of a specific source snapshot. Active work lives in
[issues](../issues/INDEX.md); current behavior lives in [Architecture](../docs/ARCHITECTURE.md).

| Historical ID | Report | Review date |
| --- | --- | --- |
| audit-1 | [Audit 1: is Lightning ready to demo?](2026-10-20-demo-readiness/report.md) | 2026-10-20 |
| audit-2 | [Audit 2: backend efficiency and loose ends](2026-10-21-backend-efficiency/report.md) | 2026-10-21 |
| audit-3 | [Audit 3: is the edit journal (multi-device sync) solid?](2026-10-21-edit-journal/report.md) | 2026-10-21 |
| audit-4 | [Audit 4: backend correctness and failure boundaries](2026-10-23-backend-correctness/report.md) | 2026-10-23 |
| audit-5 | [Audit 5: is the backend engine efficient and streamlined?](2026-10-21-backend-streamlining/report.md) | 2026-10-21 |
| audit-6 | [Audit 6: open pull request cleanup](2026-10-23-pull-request-cleanup/report.md) | 2026-10-23 |
| audit-7 | [Audit 7 — app visual flow](2026-10-25-app-visual-flow/report.md) | 2026-10-25 |
| pairing-hardening | [Pairing backend hardening and security review](2026-10-26-pairing-hardening/report.md) | 2026-10-26 |
| contributor-review | [Yusuf contribution review · 2026-10-23](2026-10-23-contributor-review/report.md) | 2026-10-23 |

## Create and maintain a report

Use `reports/YYYY-MM-DD-subject/report.md` and an adjacent `evidence/` directory.
Start from [the report template](../templates/report.md). Record the reviewed
commit, scope, method, findings, evidence, limits and follow-up issue codes.
Evidence contains only dummy/sample data. Reproduction scripts find the repo root
from their own location and document the command to run from the repo root.

Preserve the original assessment. Append dated follow-ups with verification
references; do not silently turn an old verdict into a current-status claim.
Every actionable finding links to an active issue. Before deleting a finished
issue, replace report/feedback links with a commit-pinned copy of the issue,
resolution commit or regression test. Keep issue codes and old audit IDs so
history remains searchable. Register each new report in this catalogue.

Old paths were migrated on 2026-10-26; the IDs below identify the same reports.
Use Git history for the original layout. Existing assessments and evidence are
preserved; a folder migration does not revalidate their findings.

[Website reports](https://github.com/LightningEg/Lightning_website/blob/main/reports/README.md) cover website-specific audits.
