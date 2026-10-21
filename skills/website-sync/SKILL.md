---
name: website-sync
description: Keep the Lightning app repo and the Lightning_website repo consistent: identical guideline and brand-voice copies, current release and download data, matching English and Arabic pages, working links, version IDs, and nothing private published. Use after a release, a guideline change, a site change, or when the guideline-copy test fails.
---

# Website sync

Tool-neutral. Two public repos sit side by side: the app, `elfekimuhammed/Lightning` (folder `Lightning`), and the site, `elfekimuhammed/Lightning_website` (folder `Lightning_website`, published with GitHub Pages).
Check both out next to each other (`/home/user/Lightning` and `/home/user/Lightning_website`); use the repo-add tool if one is missing.

The site's own rules are in its `README.md`. List its sections with `grep -n '^## ' README.md` and read only what you need: *Structure* and *Version identity and archive* matter for almost every change.
The hand-off for website tasks is `NOW.md` in the **app** repo.

## Token rules

Compare with `cmp` and `diff -q`, not by reading. Never open a guideline file whole (about 95,000 tokens): print a section with `python tools/guideline.py <ID>` (`--dir guideline` in the site repo).
Read a site page only around the line you change.

## Steps

1. **Guideline copies identical.** `guideline/app.html`, `website.html`, `phone.html` and `brand-voice.md` must be byte-identical in both repos
   (`for f in app.html website.html phone.html brand-voice.md; do cmp Lightning/guideline/$f Lightning_website/guideline/$f; done`). The app repo's test
   `tests/test_docs_structure.py::test_the_app_and_website_guidelines_are_the_same_three_files` checks the three HTML files. If they differ, the one with the higher version number in its title
   ("Lightning guideline 3.30") or the newer commit wins: copy it over the other, commit and push **both repos** (a branch each, AGENTS.md §6 and the site's `CLAUDE.md`). Never edit one copy alone.
2. **Release data.** After a release, the site must show the current version, matched Windows ZIP and Android APK links, SHA-256 checksums and build record, in English and Arabic, on the Downloads page and in the Version Archive
   (`versions.html`, `version-registry.json`). Keep at least the three newest app versions permanently and add a row per release. The README's "Current app release" line names the version, date and commit.
3. **English and Arabic parity.** Every English page in the root has an Arabic counterpart in `ar/` with the same sections, links and forms. List the root `*.html` files and the `ar/*.html` files and diff the names; for
   each pair compare headings and link targets. Arabic pages use the Egyptian voice (skill `arabic-check`) and do not use English UX test release IDs.
4. **Links.** In `Lightning_website`, `python tools/site_check.py` checks every relative `href`, `src` and `data-zoom`, that each JSON-LD block parses, that every `archive/` snapshot carries noindex and `<base href="../">`,
   that each row on `versions.html` says what `version-registry.json` says, and English titles (60) and descriptions (160). Then check by hand that anchors exist, `sitemap.xml` and `llms.txt`
   list the real pages and `CNAME` and `robots.txt` are intact. Report broken ones with page and link. Do not fetch third-party links.
   `python tools/geeks_stats.py ../Lightning --check` says whether For Geeks' code counts still match the app's main; without `--check` it rewrites them (D10).
5. **Version IDs.** Every testable web experience carries one immutable ID, `UX-YYYY.MM.DD.NN`, shown in the Testing panel and on the Version Archive. A change to a live page means a new ID and an archived copy first
   (the README's *Version identity and archive* section gives the exact rule). `python tools/release.py <spec.json>` in the site does it before you edit: snapshot, registry, new ID, version list.
   Check that the `data-ux-version` on the pages you changed matches `version-registry.json` and the archive folder has the previous copy.
6. **Forms and receivers.** The signup, survey and feedback forms post to the Apps Script receiver URL, which is public by necessity. All pages must use the **same** URL; when it changes, change it everywhere
   (`grep -rn "script.google.com/macros" . | cut -d: -f1 | sort -u` shows every file) and confirm a test submission reaches the sheet (ask the owner to check the sheet).
7. **Nothing private published.** The site is public: no analytics data, visitor lists, dashboard keys, owner emails or tokens in any file (README *Analytics and consent*: "Nothing analytical is committed").
   Scan with `git grep -n -I -E "ghp_|github_pat_|api[_-]?key|@gmail\.com"`; only the receiver URL and public contact lines may appear.
8. **Licence and voice.** `LICENSE` (PolyForm Noncommercial 1.0.0) and the README licence section exist; copy follows `brand-voice.md` and B10 (no comparisons with named apps; describe only what the app does today).
   "Today" means the released build on Downloads: a feature only on `main` (or built but blocked, like Gulf and European price files) is not claimed; check `CHANGELOG.md` against the release section before writing it up.
   If the app changed a screen or figure the site quotes, run the site-recapture skill.
9. **Merge.** One branch per kind of fix (`claude/<feature>`), changelog line in the app repo (the site has no changelog), push the branch, merge to `main`, push both repos.

## Report

**Where findings go.** Read `issues/README.md` once. Fix a small finding now (branch, test, changelog line) and file **no** item. File anything bigger as one item in
the milestone it belongs to, `issues/<n>-<name>/<code>-<what>.md` (code from `python tools/issues.py next <n>`; this skill's name in `skills`, your model in `by`, `app_version`
from `pyproject.toml`, `commit` from `git rev-parse --short HEAD`), then run `python tools/issues.py`. Finishing an item means deleting its file in the same commit and adding its code to the milestone's `done:`. Never leave a finding only in chat.

Which of the nine checks passed; each mismatch (file, expected, found) and what you changed; what needs the owner (a sheet check, a release approval). List the commits pushed in each repo.
