# Decision log

Decisions already made by the owner live in `docs/PROJECT_OVERVIEW.md` §2 (the authoritative list, ~40 rows).
Not repeated here. This log holds only **decisions about this handbook and open questions**. Status:
Confirmed / Proposed / Pending / Superseded. On 2026-10-30 the owner delegated the open handbook decisions to Claude; they are marked *Confirmed (delegated)*. Product-wide owner decisions in the Overview are untouched.

| ID | Title | Context | Options | Recommendation | Status |
|---|---|---|---|---|---|
| D-001 | Product success metrics | PRD §11 has no KPIs in the repo | (a) none; (b) opt-in counts; (c) manual surveys via `feedback/` | (c) matches the local-only decision | **Confirmed (delegated):** (c); acceptance measure stays Mohab's test with no `known_gap` |
| D-002 | Handbook lives in `docs/handbook/` | Requested by owner (this task) | Under `docs/`, or `reports/` | Keep under `docs/`; link from the docs map | **Confirmed** (owner request) |
| D-003 | Handbook is a view, not a source | Existing refs are authoritative and tested | Duplicate vs link | Link; code wins | **Confirmed (delegated)** |
| D-004 | Full column dictionary | 63 tables | Hand-write vs generate in CI | Generate from schema | **Confirmed (delegated):** generate later from `PRAGMA table_info`; not hand-written (avoids drift); tracked as GAP-008 |
| D-005 | MoSCoW priorities on requirements | Inferred here | Owner assigns | Keep inferred values, revise on owner objection | **Confirmed (delegated):** keep as written |
| D-006 | Network disclosure list | Relay + price fetch use network | Publish a table in app and docs | Publish | **Confirmed (delegated):** docs table now (below); in-app wording left to a future issue |
| D-007 | Performance targets | None exist | Define per page on phone | Define targets | **Confirmed (delegated):** *targets, not measured guarantees*: a page opens under 1 s on a mid-range phone and 300 ms on PC with the demo profile; Add form saves under 500 ms. To be measured with `perf-check` before being quoted |
| D-008 | Compliance/disclaimer position (zakat, CD estimates) | Not stated | Owner/legal | Label as estimates | **Confirmed (delegated):** both stay labelled "estimate"; no regulatory claim is made anywhere in the docs |
| D-009 | Is any HTTP route an external API? | Affects API docs | UI-only vs documented API | UI-only | **Confirmed (delegated):** internal UI surface, no stability promise |
| D-010 | Exception to "docs holds only five files" | `test_docs_structure.py` blocked a folder | Allow `handbook/` only | Allow only this folder | **Confirmed (delegated)** |
| D-011 | Push to `main` | Request said main; repo rule (AGENTS.md §6) forbids direct pushes | PR from the session branch | PR then squash merge | **Confirmed:** PR, merged after checks |

Revisit this file when the owner answers a Pending row, and update affected handbook pages.

## Network disclosure (D-006)

| What | When | Sends | Optional |
|---|---|---|---|
| Price and FX packs / live quotes | Profile open, Update prices | Instrument codes requested; no ledger data | Yes |
| Device sync, local network | Paired devices | Encrypted signed proposals, pinned TLS | Yes |
| Cloud relay (free tier) | Only if enabled | Encrypted journal messages | Yes |
| Store / cosmetic claim | Only on purchase or claim | Purchase identifiers | Yes |
