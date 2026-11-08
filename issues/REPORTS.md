# Reports

Audits and reviews of a specific source snapshot. Active work lives in
[issues](INDEX.md); current behavior lives in [Architecture](../ai/ARCHITECTURE.md).

| Code | Report | Review date | Kind | Open follow-ups |
| --- | --- | --- | --- | --- |
| r1 | [Audit 1: is Lightning ready to demo?](12-desktop-ux/r1-demo-readiness/report.md) | 2026-10-20 | audit | 3H |
| r2 | [Audit 2: backend efficiency and loose ends](2-safe-for-real-money/r2-backend-efficiency/report.md) | 2026-10-21 | audit | 2A, 2C, 4A |
| r3 | [Audit 5: is the backend engine efficient and streamlined?](4-edit-journal-and-devices/r3-backend-streamlining/report.md) | 2026-10-21 | audit | 4A, 9K |
| r4 | [Audit 3: is the edit journal (multi-device sync) solid?](4-edit-journal-and-devices/r4-edit-journal/report.md) | 2026-10-21 | audit | 4A |
| r5 | [Audit 4: backend correctness and failure boundaries](2-safe-for-real-money/r5-backend-correctness/report.md) | 2026-10-23 | audit | 2A, 2C, 4A |
| r7 | [Audit 6: open pull request cleanup](1-easy-to-contribute/r7-pull-request-cleanup/report.md) | 2026-10-23 | review | 1H |
| r11 | [Pairing backend hardening and security review](4-edit-journal-and-devices/r11-pairing-hardening/report.md) | 2026-10-26 | review | 4A |
| r12 | [v1.5.0 PR review, theme switching and package preparation](10-looks-and-store/r12-v150-release/report.md) | 2026-10-26 | release | 1H, 10A, 10C |
| r13 | [Store and community: unlocking themes, the market, rewards and staying in Lightning](10-looks-and-store/r13-store-and-community/report.md) | 2026-10-27 | research | 10C, 10D |
| r14 | [Users' main questions: what each screen must answer, with known gaps](3-polish-and-arabic/r14-users-main-questions/report.md) | 2026-10-27 | reference | none |
| r17 | [Audit 10: the phone, tab by tab - quick actions and the answer first](11-phone-ux/r17-phone-tab-audit/report.md) | 2026-10-29 | audit | 3AN |
| r19 | [Audit 12: the PC app, tab by tab - clutter, hierarchy and flow](12-desktop-ux/r19-desktop-tab-audit/report.md) | 2026-10-30 | audit | 3AM |
| r20 | [Audit 13: the phone for quick jobs - convenience, taps and the look](11-phone-ux/r20-phone-convenience-audit/report.md) | 2026-11-01 | audit | 3AN |
| r22 | [Code audit: refactoring, loose ends and smart features](9-later/r22-code-quality-and-smart-features/report.md) | 2026-11-03 | audit | 1H, 2A, 2C, 4A, 4B, 7C, 9A, 9K |
| r23 | [CSV import stress test: where it breaks and how to rebuild it](7-planning-import-and-search/r23-csv-import-stress/report.md) | 2026-11-05 | audit | 7AB, 7C |
| r24 | [Desktop and phone UX: logic, visuals, simpler tasks and connected features](12-desktop-ux/r24-desktop-phone-ux/report.md) | 2026-11-05 | audit | 3H, 3AM, 3AN, 3AZ, 4A, 4B |
| r25 | [The phone, redesigned: a phone-first architecture, tab by tab](11-phone-ux/r25-phone-ux-architecture/report.md) | 2026-11-06 | research | 3AY, 3AN, 3F |
| r26 | [Audit 14: using Lightning as a user, on the PC and the phone](12-desktop-ux/r26-user-test-pc-and-phone/report.md) | 2026-11-06 | audit | 12D, 12G, 11A, 3H |


## Create and maintain a report

Use `issues/<big picture>/r<N>-subject/report.md`, in the folder of the big picture whose items it starts (a new
big picture is a new numbered folder with a README), with an adjacent `evidence/` directory when there is evidence
beyond the text. **Every report has a code, `r1`, `r2`, ... in the order it was written** (like an
issue code: never reused, never renumbered; `python tools/docs_check.py next-report` prints the next one).
The folder starts with the code, the catalogue's first column repeats it and the report's `Code:` header line
names it. Write the code wherever you mention the report (`r24`).
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
**Open follow-ups** are the open items in [the plan](INDEX.md) that the report links or
that link back to it; when you finish an item, drop its code here too.

Folders were named by date until 2026-11-06, when each report got its `r` code in date order (date, then subject);
the date stays in the report's header, and the old audit IDs stay in its `Historical ID:` line. Use Git history for the
earlier layouts. Existing assessments and evidence are
preserved; a folder migration does not revalidate their findings.

[Website reports](https://github.com/LightningEg/Lightning_website/blob/main/reports/README.md) cover website-specific audits.

