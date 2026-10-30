# Decision log

Decisions already made by the owner live in `docs/PROJECT_OVERVIEW.md` §2 (the authoritative list, ~40 rows).
Not repeated here. This log holds only **decisions about this handbook and open questions**. Status:
Confirmed / Proposed / Pending / Superseded. Nothing "Pending" has been guessed.

| ID | Title | Context | Options | Recommendation | Status |
|---|---|---|---|---|---|
| D-001 | Product success metrics | PRD §11 has no KPIs in the repo | (a) none, local-first so no telemetry; (b) opt-in counts; (c) manual surveys via `feedback/` | (c) matches the local-only decision | **Pending** |
| D-002 | Handbook lives in `docs/handbook/` | Requested by owner (this task) | Under `docs/`, or `reports/` | Keep under `docs/`; link from the docs map | **Confirmed** (owner request) |
| D-003 | Handbook is a view, not a source | Existing refs are authoritative and tested | Duplicate vs link | Link; code wins | **Proposed** |
| D-004 | Full column dictionary | 63 tables | Hand-write vs generate in CI | Generate from schema | **Pending** |
| D-005 | MoSCoW priorities on requirements | Inferred here | Owner assigns | Owner review | **Pending** |
| D-006 | Network disclosure list | Relay + price fetch use network | Publish a table in app and docs | Publish | **Pending** |
| D-007 | Performance targets | None exist | Define per page on phone | Define 3 targets | **Pending** |
| D-008 | Compliance/disclaimer position (zakat, CD estimates) | Not stated | Owner/legal | Owner | **Pending** |
| D-009 | Is any HTTP route an external API? | Affects API docs | UI-only vs documented API | UI-only | **Pending** |
| D-010 | Exception to "docs holds only five files" | `test_docs_structure.py` blocked a folder | Allow `handbook/` only | Allow only this folder | **Proposed** (applied in this change; revert if refused) |
| D-011 | Push to `main` | Request said main; repo rule (AGENTS.md §6) forbids direct pushes | PR from the session branch | PR | **Confirmed by repo rule**; owner may override |

Revisit this file when the owner answers a Pending row, and update affected handbook pages.
