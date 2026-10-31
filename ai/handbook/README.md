# Lightning handbook

A plain-language guide to what Lightning is, how it is built, and where it falls short.
Written from the code at version **1.5.2** (schema migration **0068**), 2026-10-30.

> **How this relates to the other docs.** People read the plain pages in `docs/`:
> [product](../../docs/product.md), [how it is built](../../docs/how-it-is-built.md) and
> [journeys](../../docs/journeys.md). This folder holds the formal, ID-bearing material (requirements,
> data model, API list, traceability, gaps, decisions) for AI sessions. `ai/ARCHITECTURE.md`,
> `PROJECT_OVERVIEW.md` and `GLOSSARY.md` stay the detailed, authoritative references. Where they
> disagree with this folder, the code wins, then the references, then this folder.
> Findings that contradict the references are listed in [GAP_ANALYSIS](analysis/GAP_ANALYSIS.md).

## Read in this order

| If you want to… | Read |
|---|---|
| Understand the product in five minutes | [product/PRD.md](../../docs/product.md) |
| See how the pieces fit | [architecture/SDD.md](../../docs/how-it-is-built.md) |
| Know where data lives and what the tables mean | [architecture/DATA_MODEL.md](architecture/DATA_MODEL.md) |
| Follow a real journey end to end | [architecture/WORKFLOWS.md](../../docs/journeys.md) |
| Find a library, command or test | [architecture/TECHNICAL_DESIGN.md](architecture/TECHNICAL_DESIGN.md) |
| Check what the system must do | [requirements/FUNCTIONAL_REQUIREMENTS.md](requirements/FUNCTIONAL_REQUIREMENTS.md) |
| Check how well it must do it | [requirements/NON_FUNCTIONAL_REQUIREMENTS.md](requirements/NON_FUNCTIONAL_REQUIREMENTS.md) |
| Find a URL the app serves | [api/API_REFERENCE.md](api/API_REFERENCE.md) |
| Trace a feature to code and tests | [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) |
| See what is missing or risky | [analysis/GAP_ANALYSIS.md](analysis/GAP_ANALYSIS.md) |
| See what is decided and what is open | [analysis/DECISIONS.md](analysis/DECISIONS.md) |

## Conventions used here

- **Status words:** *Implemented* (found in code and covered by a test), *Partial*, *Planned* (an open item in `issues/`), *Unknown* (could not be verified from the repository).
- **IDs:** `FR-###` functional, `NFR-###` non-functional, `GAP-###` findings, `D-###` decisions, `WF-#` workflows, `US-#` stories. They are the same in every file.
- **Decisions** are in [analysis/DECISIONS.md](analysis/DECISIONS.md); anything unknown is marked *Unknown*, never guessed.
- File references are relative to the repository root, e.g. `lightning/bootstrap.py`.
- Application code was **not** changed to produce this handbook.

## The system in one paragraph

Lightning is a local-first personal wealth app for salaried people in Egypt. One Python process
(FastAPI + Jinja) serves a browser UI on `127.0.0.1` over a single SQLite (SQLCipher-encrypted)
database. It ships as a Windows app (a thin WebView2 window), an Android app, and a Linux browser
mode. Money is recorded in one ledger; plans (budgets, reserves, bills, loans) move no money;
reports read both.
