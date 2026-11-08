---
title: Page speed: a CSS trim
type: tech
pillar: reach
size: M
model: sonnet
status: new
created: 2026-10-19
by: Claude
---

## Report
**Read:** Architecture › Figures layer and speed (`grep -n 'Page speed' ai/ARCHITECTURE.md`).

Measured 2026-11-06 on demo data in Chromium over loopback (commit bbc768c7 on branch `claude/folder-9-doable-issues-1zngh8`, never merged; its numbers are carried here):
- **The cache already works.** `lightning/runtime/http.py:149` sends `private, max-age=86400` for `/static/`; every CSS file loads in 0 ms on a repeat page. A stable origin would add nothing within a session and would weaken the random per-launch port and launch-code checks. **Owner decision (2026-11-06): the stable-origin half is dropped.**
- A repeat page takes about 70 ms, about 40 ms of it after the HTML arrives (style parse and layout, then script).
- `lightning/ui/static/style.css` is 380 KB (76 KB gzipped). Across 16 pages only **30%** of it is used; `visual-flow.css` 32%. `themes.generated.css`, `theme-surfaces.css` and `theme-materials.css` count 0% only because the default theme was on.

2026-11-08: still true on main: `style.css` 380,405 bytes, `style.rtl.css` 380,575 bytes; the cache header is unchanged.

## Fix
Find the `style.css` rules that no template, script or Python string can reach, delete them, rebuild the RTL sheet, measure again. Coverage alone misses hover, focus, dialogs, themes and unvisited pages, so a rule is removed only when its class names appear nowhere in the source. Expect a few milliseconds, not a rewrite.

Not in this item: Architecture's "routes are `async def` with synchronous database work" (step 9F3 only checks whether it matters).

## How to work on this item

Each step below is one pull request. Read only the files a step names; never open `guideline/*.html` whole. Run the step's test command, then `python -m pytest tests/test_issues.py -q`; delete the step's heading in the same commit.

## 9F1 A tool that lists unreachable CSS rules · S · sonnet
Files: new `tools/css_unused.py`; new `tests/test_css_unused.py`. Read for style: `tools/perf_check.py` lines 1-40 (docstring and argparse shape).
Do: a pure-Python tool (no browser). (1) Read `lightning/ui/static/style.css` (or the file given with `--file`) and split it into top-level rules, descending into `@media`/`@supports` blocks; skip `@font-face`, `@keyframes` and `:root`. (2) For each selector in a rule's selector list, collect its class tokens with `re.findall(r"\.(-?[A-Za-z_][\w-]*)", selector)`. (3) Build one text corpus from every file under `lightning/` with suffix `.html`, `.js`, `.py` (not `.css`). A class token is *seen* when it occurs in the corpus as a whole word (`re.search(rf"(?<![\w-]){re.escape(tok)}(?![\w-])", corpus)`). A token is *dynamic* when a prefix of it up to and including a `-` appears in the corpus followed by a quote, `{`, `$` or `+` (e.g. `"tone-" + x`, `f"is-{state}"`, `` `chip-${k}` ``): count dynamic tokens as seen. (4) A selector is dead when at least one of its class tokens is not seen; a rule is dead when every selector in it is dead. (5) Print `file:line selector` for each dead rule and a last line `dead rules: N of M, about K bytes`; `--json` prints the same as a list of `{"line", "selector", "bytes"}`. Exit 0 always.
Done when: `tests/test_css_unused.py` runs the tool's functions on a small CSS string and corpus written to `tmp_path` and asserts: a rule whose class is in a template is kept; a rule whose class appears nowhere is dead; `.a, .b` with only `.b` seen is kept; `.tone-good` with `"tone-" + x` in a JS string is kept; a rule inside `@media` is found with its line. `python -m pytest tests/test_css_unused.py -q`, and `python tools/css_unused.py | tail -1` prints a count on the real `style.css`.

## 9F2 Delete the unreachable rules from style.css · M · sonnet
Needs 9F1 merged first.
Files: `lightning/ui/static/style.css`; regenerated `lightning/ui/static/style.rtl.css` (by `tools/build_rtl_css.js`, read its header lines 1-5 for the command).
Verify first: run `python tools/css_unused.py`; if it reports under 20 KB, write the number in this item under Report and delete this step instead.
Do: delete exactly the rules `python tools/css_unused.py` lists, and nothing else. Before deleting, for each listed class token run `grep -rn "<token>" lightning --include=*.py --include=*.js --include=*.html` once more; keep any rule whose token is built in a way the tool did not catch (string join, `classList.add(variable)`, a Jinja `~` concatenation) and add that case to `tests/test_css_unused.py` as a kept rule. Then rebuild the RTL sheet (`cd /tmp && npm i rtlcss postcss && NODE_PATH=/tmp/node_modules node /home/user/Lightning/tools/build_rtl_css.js`). Record bytes before and after in the commit's `Detail:` line.
Done when: `python tools/css_unused.py | tail -1` says `dead rules: 0`; `python -m pytest tests/test_theme_build.py tests/test_brand_audit.py tests/test_page_header.py tests/test_arabic_no_english.py tests/test_pc_layout_browser.py tests/test_mohab_year.py -q` has no new failure against main; `python tools/phone_check.py` reports nothing new; screenshots of `/`, `/budget` and `/transactions` before and after look the same.

## 9F3 Do async routes with synchronous database work slow anything? · S · opus
Files: `lightning/runtime/http.py`, `lightning/ui/web.py`, one route file to sample (`lightning/ui/routes/zakat.py`); `ai/ARCHITECTURE.md` (the **Page speed** paragraph).
Do: measure, do not convert. With the sample profile (`python tools/perf_check.py` shows how to build one), time a slow page (`/` or `/budget`) alone, then the same page while a second request for `/static/style.css` and a second `/transactions` start 10 ms later (threads, `httpx`). If the second requests wait for the first to finish by more than 50 ms, file a new item in `issues/9-later/` (skill add-plan-item) for turning the slowest read-only routes into `def` routes, naming the SQLite connection's thread rules (`check_same_thread`, the request cache in `lightning/core/memo.py`) as the risk. If they do not, replace "Open: routes are `async def` with synchronous database work." in Architecture with one sentence giving the measurement and "left as is".
Done when: Architecture's Page speed paragraph states the measured wait, or a new item exists with it; `python -m pytest tests/test_docs_structure.py -q`.
