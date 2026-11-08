---
name: add-screen
description: Build a new page or tab in the app end to end so it fits: a thin route over services, the PC and phone templates, its place in the sections registry, the answer-first header, Arabic, the brand guideline and A16, a way forward and back, and Mohab's steps. Use when adding a page, a tab, a popup with its own route, or moving a page between sections.
---

# Add a screen

Tool-neutral. Read `ai/ARCHITECTURE.md` › UI contract (`grep -n '^## ' ai/ARCHITECTURE.md`) and the guideline sections the page uses (`python tools/guideline.py` lists them; `python tools/guideline.py A09` prints one). On a phone Part C wins over Part A; never reuse the PC layout there.

## Steps

1. **Question first.** Which question does the page answer for a salaried person, and is there already a page that answers it? One figure has one home; another page links to it. Write the question in the item.
2. **Figures in services.** Every number comes from a Python service, by its name in `lightning/core/figures.py`. The route parses, calls services and renders; no SQL, no arithmetic on money in the route, the template or JavaScript. A new figure gets a registry entry and a Glossary line.
3. **Route** in the matching module under `lightning/ui/routes/`. A POST declares its save boundary (`settled_save`, `tests/test_atomic_write_routes.py`) and takes the one-time `submission` token if it adds something. On a journal profile, a write is a journal command or is listed in `tools/journal_coverage_allow.txt` with a reason.
4. **Place it.** Add the tab to `lightning/ui/sections.py` (at most eight sections and five tabs each, `tests/test_two_levels.py`); never add a link to the sidebar by hand. Lightning has no Back button or address bar: the page needs its own way back to where it came from and a way forward to what you do next.
5. **PC template.** Header then the page's answer: `page_title` with its status sentence from `lightning/ui/status.py`, the Lead, Needs you, KPI row (`lightning/ui/kpis.py`: two to four cards, each with a comparison), then details. Use the existing partials and guideline classes; no new colours, fonts or one-off CSS.
6. **Phone template** in `lightning/ui/templates/phone/` when the layout differs (it usually does): Part C, nothing scrolls sideways at 360 or 320 px (`python tools/phone_check.py`). A page script that runs only at load goes in `LOADS_WHOLE` in `lightning/ui/static/phone-nav.js`, or its set-up listens to `lightning:page`.
7. **Words.** Every visible string through `|tr(locale)` with its Arabic in `lightning/ui/i18n.py`, in the voice of `guideline/brand-voice.md`; skill `arabic-check`. Empty data reads as a helpful first step, not a blank table.
8. **A16** (`AGENTS.md`): run through every line before calling it done.
9. **Tests.** The route with populated and empty data; the figures against the service; `tests/test_brand_audit.py`, `tests/test_two_levels.py`, `tests/test_arabic_no_english.py`, `tests/test_phone_check.py`. Add Mohab's step that reaches the page from the Overview and checks what it tells him (`tests/test_mohab_year.py`, `tests/test_mohab_phone.py`). Then skill `guideline-audit` by eye at 1280 and 390 px, and skill `perf-check` if the page reads a year of data.
10. **Record.** The UI contract in Architecture if the page adds a rule; `ai/PROJECT_OVERVIEW.md` if it answers an open screen question. Commit with the item code and a `Release-note:` a person would understand.
