# Gap analysis

Separated into **confirmed** (evidence in repo) and **risks/recommendations**. Severity: Low / Medium / High.
Open product work is tracked in `issues/INDEX.md`; entries here add only what the investigation found.

## A. Confirmed

| ID | Category | Finding | Evidence | Impact | Sev | Recommendation |
|---|---|---|---|---|---|---|
| GAP-001 | Documentation | `docs/ARCHITECTURE.md` says "Last reviewed 2026-10-23 · app 1.4.4"; code is 1.5.2 | `ARCHITECTURE.md` line 3; `lightning/__init__.py` | Readers cannot tell what is current | Low | Re-stamp on review |
| GAP-002 | Documentation | Architecture › Desktop app says "State: v1.1.0-beta.1" | `ARCHITECTURE.md` §Desktop app | Misleads on maturity | Low | Update to current release |
| GAP-003 | Documentation | `PROJECT_OVERVIEW.md` says "source 1.4.4 · latest published beta 1.4.2"; NOW.md says v1.5.2 is public | Overview header; `NOW.md` | Same | Low | Re-stamp |
| GAP-004 | Documentation | `docs/` was restricted to five reference files by a test; this handbook needed an exception | `tests/test_docs_structure.py::test_docs_holds_only_the_carrying_files` | Rule change by owner request | Low | Confirm (D-010) |
| GAP-005 | Observability | Only 3 `logging` usages in over 60,000 lines | `grep logging lightning` | Hard to diagnose field problems | Medium | Local, data-free diagnostic log |
| GAP-006 | Data model | Constraint lists (e.g. `effect`, `price_source`) are widened by later migrations, so no single file shows current truth | `0001` vs `0013` | Reader confusion | Low | Generate a schema snapshot doc in CI |
| GAP-007 | Data model | `ledger_entries.claim_id` began as a bare integer | `0001_initial.sql` | Possible orphan ref | Low | Verify FK in `0006/0059` |
| GAP-008 | Documentation | No column-level dictionary for 63 tables | this handbook | Onboarding cost | Low | Generate from `PRAGMA table_info` |
| GAP-009 | Functional | Not built: PDF/Excel import, lots/ROI, splits, holiday shift, other-app import | `issues/` NF-7B, 5A–5E, 7I, 7C | Feature gaps | Medium | Follow plan |
| GAP-010 | Functional | Bug: converting EGP to USD raises net worth (BT-5J) | `issues/5-investments/5J-*` | Wrong figure | High | Fix per issue |
| GAP-011 | Reliability | Restore safety, power-loss and native phone/PC acceptance still open (2A, 2C, 4A) | `NOW.md` | Data-loss window on crash during restore | High | Finish drills before wider promotion |
| GAP-012 | Security | Windows build unsigned | Architecture › Desktop app | SmartScreen friction, no publisher proof | Medium | Owner: code signing |
| GAP-013 | Supply chain | Dependency refresh (#122) blocked on native wheels | `NOW.md` item 1 | Stale dependencies | Medium | Finish 1H |
| GAP-014 | Accessibility | No accessibility test or audit found | repo search | Unknown barriers | Medium | Add audit |
| GAP-015 | Performance | No numeric performance budget | repo search | Regressions undetected | Low | Define (D-007) |

## B. Risks (not confirmed defects)

| ID | Risk | Why it might matter |
|---|---|---|
| GAP-020 | Large modules (`ui/` ≈ 18.5k lines, `sync/` ≈ 11k) | Review and change cost; no evidence of defects |
| GAP-021 | Process-wide `cipher_memory_security = OFF` | Decrypted fragments could linger; owner accepted for 3× speed |
| GAP-022 | Two PCs opening one synced folder | No cross-PC lock; documented warning only |
| GAP-023 | Behaviour with very large ledgers | Unmeasured |
| GAP-024 | Journal protocol is large and still "building" | Complexity risk until acceptance finishes |

## C. Not a gap

AI contributors communicate through the repo (`NOW.md`) by design; the strict brand guideline is deliberate; free-forever features is an owner decision.
