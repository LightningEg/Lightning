# Skills

Step-by-step procedures for any AI tool working here (Claude, Codex, others). One folder per skill, each with a `SKILL.md`.
Tool-specific folders only point here: `.claude/skills/<name>/SKILL.md` is a one-line stub so Claude Code finds the skill.
Every skill files its findings as items in `issues/` (see `issues/README.md`), each with a code like `BV-3C` (bug or improvement, visual or technical), and deletes an item when it is finished.
A new skill is written once, here, in plain words with no tool-only commands.

| Skill | Use it when |
|---|---|
| [dispatch](dispatch/SKILL.md) | The owner says "go", or you are about to take an issue: the board (`tools/board.py`), the claim and hand-off rules for people and AIs, merging first, what to start and on which model |
| [feedback-review](feedback-review/SKILL.md) | New user feedback arrives: preserve sanitized observations, investigate and link implementation work |
| [bug-hunt](bug-hunt/SKILL.md) | Test the whole app on demo data: pages, forms, figures across tabs (`tools/bug_crawl.py`) |
| [stale-check](stale-check/SKILL.md) | Find and clean stale notes, links, proposals and branches (`tools/stale_check.py`) |
| [release-check](release-check/SKILL.md) | Before tagging a release (`tools/release_check.py`) |
| [guideline-audit](guideline-audit/SKILL.md) | Check screens against the brand guideline (`tests/test_brand_audit.py`, `tools/phone_check.py`) |
| [number-audit](number-audit/SKILL.md) | Prove figures match the ledger and each other, before and after money code changes |
| [perf-check](perf-check/SKILL.md) | Time pages, count queries, fix waste (`tools/perf_check.py`) |
| [arabic-check](arabic-check/SKILL.md) | Find and add untranslated Arabic strings, check RTL, digits and voice |
| [website-sync](website-sync/SKILL.md) | Keep the app and website repos consistent after a release or guideline change |
| [site-recapture](site-recapture/SKILL.md) | The app changed a screen or figure the website shows: recapture and update the site (`tools/site_shots.py`) |
| [organise-repo](organise-repo/SKILL.md) | Decide where a document or fact belongs; keep docs/ and ai/ small and the generated pages current |
| [add-plan-item](add-plan-item/SKILL.md) | File a bug, improvement, feature or owner decision as a coded item in `issues/` |
| [split-large-item](split-large-item/SKILL.md) | Split a size L item into sized, ordered steps (`tools/issues.py --check` warns) |
| [post-contributor-issues](post-contributor-issues/SKILL.md) | Choose what is ready for contributors and post it as GitHub issues with coins (`tools/issues.py github`) |
| [write-release-notes](write-release-notes/SKILL.md) | Write the `Release-note:` and `Detail:` trailers; cut and check release notes (`tools/release_notes.py`) |
| [add-migration](add-migration/SKILL.md) | Add an app SQLite migration: numbered, no transaction statements, version bumped, seed, export, journal and undo in step, upgrade tests |
| [add-screen](add-screen/SKILL.md) | Build a page or tab end to end: thin route, PC and phone templates, sections registry, answer first, Arabic, A16, Mohab |
| [fix-ci](fix-ci/SKILL.md) | A check is red or flaky: read the log, reproduce, fix the cause without skipping tests, spend Windows and Android minutes only when needed |
| [security-sweep](security-sweep/SKILL.md) | Audit the whole app's security surface by surface before a release or on a schedule; file findings privately |
| [ship-pr](ship-pr/SKILL.md) | From a finished branch to merged: checks, trailers, pull request, CI, verified merge, hand-off |
| [review-outside-code](review-outside-code/SKILL.md) | Any code not written in this session (contributor or bot pull request, fork, copied file): adopt, improve, rewrite or reject it after provenance, licence, security, architecture and test checks |
| [dependency-change](dependency-change/SKILL.md) | Add, update or remove a package or GitHub Action, Dependabot included: need, licence, wheels, locks regenerated together, pinned actions |
| [owner-console-view](owner-console-view/SKILL.md) | Add a count or analysis view to the website's owner console (website repo) |
| [supabase-migration](supabase-migration/SKILL.md) | Write, test and apply a Supabase migration safely (website repo) |
| [usage-question](usage-question/SKILL.md) | Answer a question about users or traffic from Supabase and GoatCounter without exposing anyone |

Order for a release: write-release-notes (`cut`), stale-check, security-sweep, release-check (which calls bug-hunt, number-audit, guideline-audit, arabic-check and perf-check), then website-sync, then site-recapture if the release changed what the site shows.
