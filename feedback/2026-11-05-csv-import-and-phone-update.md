# CSV import and phone update

Date received: 2026-11-05 · Reviewed: 2026-11-05
Product/build/surface: 2.0.x; PC import review and Android phone app
Source: owner, in a Claude Code session, with one real bank CSV (kept private; not committed)

Two observations from one respondent (the owner).

## Observations and themes

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | A 377-row CSV from another tracker (Account, Date, Counterparty, Notes, Category_Group, Category, Amount, Split_Amount, Cleared) was hard to import. | The import understands such a file and asks far less. | Capture | **Defect + Request.** The file reads with no errors, but 142 rows stopped for review: the group column was not read, so 30 Work/Personal Transportation rows were ambiguous; 4 opening-balance and adjustment rows would have posted as money; about 110 rows carried 12 category names of the other app, each to be set row by row. | IT-7Z (import branch) |
| FB2 | Updating the phone app lost its book, and the PC had no way to send it back. | An update never loses data; the PC can always restore a phone. | Protect | **Defect.** 2.0.0 changed the application ID (`org.lightning.app.test` → `org.lightning.app`), so Android installed a second, empty app. Phone data is only in app storage and Android backup is off; nothing on the phone opens a file from the PC. | BT-2AI: identity pinned by test (2AI1, built); recovery steps 2AI2–2AI4 planned |

## Dated follow-ups

- 2026-11-05: investigated by running the CSV through a throwaway test profile (counts above) and reading the
  2.0.0 packaging diff. Use cases weighed for FB1: bank statements (no categories; rules and history fill them),
  other apps' exports (this file: group, balance rows, foreign category names, several accounts) and Lightning's own
  export. The three fixes built target the second, the case the owner hit; remembering a name's category for the
  next file and splitting by an Account column are the next steps in IV-7Z.
