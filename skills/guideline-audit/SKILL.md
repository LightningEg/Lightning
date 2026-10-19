---
name: guideline-audit
description: Check Lightning's screens against the brand guideline (PC Part A, website Part B, phone Part C), automatically and by eye, and report each rule that is broken with the page and element. Use after any visual change, before a release, or when a screen "looks off".
---

# Guideline audit

Tool-neutral. The brand guideline is strict: CSS that differs from it is wrong. If a rule is missing, use the closest one and ask the owner in a GitHub issue;
never invent a style. The guideline is three large HTML files in `guideline/` (about 95,000 tokens, mostly drawings): **never open one whole.**

- `app.html` is **Part A**, the app on a PC (A01–A16). `phone.html` is **Part C**, the phone (C01…); on a phone Part C wins over Part A and the PC layout is never reused.
- `website.html` is **Part B**, the website (B01–B12), used for `Lightning_website`.
- Read one section as text: `python tools/guideline.py` lists sections with sizes, `python tools/guideline.py A12` prints one.
  In the website repo: `python ../Lightning/tools/guideline.py --dir guideline B05`.
- Voice: `guideline/brand-voice.md` (identical in both repos).

## Token rules

Print only the sections that apply to what you are checking. Use the automatic audits first; look at screenshots only for what they cannot judge (balance, hierarchy, charts).
One screenshot per page and width, no re-takes. Report findings, not the guideline.

## Steps

1. **Pick the scope.** PC pages, phone pages, or website pages, and the changed screens if the audit follows a change.
2. **Run the automatic audits.**
   - **PC:** `python -m pytest -q tests/test_brand_audit.py`. It drives Chromium (`/opt/pw-browsers/chromium`; skipped if Playwright or Chromium is missing) over the main pages with the sample household at 1366 × 768 and
     checks A03, A05, A10.3 and A16: nothing upper-case, text only in the A03 colours, plain links Ink and underlined, H1–H3 Ink, no white or boxed field, spending in the register Ink, the register fits its card.
   - **Phone:** `python tools/phone_check.py` (add `--shots folder` to keep screenshots). It loads each main page in the phone frame at 360 and 320 px and prints every page that scrolls sideways with its widest element (C12).
   - **Rule lists:** `python -m pytest -q tests/test_docs_structure.py` (the A16 list in `AGENTS.md` equals the guideline's; the app's and website's guideline copies are identical).
3. **Check A16 by hand** on every screen you touched (it is the shipping list; a screen with any of these is not done):
   | A16 rule | How to see it |
   |---|---|
   | All caps: anywhere | computed `text-transform: uppercase`, or typed capitals, on any text |
   | Coloured headers: headers are Ink | H1–H3 colour must be `#0D2233` |
   | A colour off its meaning: check A03 | money out soft rose, strong rose only for "needs you", good = Meadow, info = Azure; read `A03` for the full table |
   | Vivid gradient card: brand only | a gradient card anywhere except the brand surfaces |
   | KPI by position: tone by meaning | a KPI coloured because of where it sits, not because it is good or bad |
   | Chip by direction: good or bad | a chip coloured up/down rather than good/bad |
   | Decimals on big figures: whole EGP | cents on a headline or card figure (rows may show them) |
   | "L1 › L2" | a breadcrumb-style title; use a header then a list |
   | Five or more names: four, then Other | a legend, chart or list with five or more named slices |
   | White or boxed fields: soft wells | an input with a white fill or visible box |
   | Dropdown for your data: type and pick | a `<select>` listing the user's own accounts, categories or names |
   | Card in a card: never | a card element inside another card |
   | A line that repeats its label: cut it | a sentence that restates the heading above it |
   | A figure alone: compare it | a KPI card with no comparison line (last month, same days, usual, plan, target or today) |
   | A card alone in its row: pair it | one card in a KPI row, or a key note stretched across the page on its own |
4. **Section by section.** For the screen type, read only its sections: headers A05 / B02, type and numbers A06 / B04, cards A07, KPI A08, controls A10, lists A11, charts A12, words A14 / B10,
   spacing A15; phone C01–C12; website B01–B12. Compare spacing, hierarchy, chart style and wording by eye against the text.
5. **Arabic and dark mode.** Repeat the pages in Arabic (`arabic-check`) and, on the website, dark mode (B09): the `*.rtl.css` files must mirror, not just flip text.
6. **Fix only what is broken, in the one stylesheet that owns it** (`lightning/ui/static/style.css`, `phone.css`, `style.rtl.css`, `phone.rtl.css`; website `css/`). No inline styles, no new colours. After editing `style.css`, `phone.css` or `profiles.css`, regenerate the Arabic mirrors or `tests/test_arabic_no_english.py` fails: `cd <scratch> && npm i rtlcss postcss && NODE_PATH=<scratch>/node_modules node tools/build_rtl_css.js`, and commit the `*.rtl.css` files.
   Visible change = run Mohab (`tests/test_mohab_year.py`) and the brand audit again. One branch per feature, changelog line, merge.

## Report

**Where findings go.** Read `issues/README.md` once. Fix a small finding now (branch, test, changelog line) and file **no** item. File anything bigger as one item in
the milestone it belongs to, `issues/<n>-<name>/<code>-<what>.md` (code from `python tools/issues.py next <n>`; this skill's name in `skills`, your model in `by`, `app_version`
from `pyproject.toml`, `commit` from `git rev-parse --short HEAD`), then run `python tools/issues.py`. Finishing an item means deleting its file in the same commit and adding its code to the milestone's `done:`. Never leave a finding only in chat.

Per finding: rule id, page, element or selector, what it is, what it should be. Then what you checked and found fine, and the owner questions (as one GitHub issue).
