---
name: arabic-check
description: Check that Lightning's Arabic screens are fully Arabic, correctly right-to-left, with correct digits and date order, in the brand voice; find untranslated strings and add them. Use after adding or changing any visible text, before a release, or when Arabic screens look mixed or misordered.
---

# Arabic check

Tool-neutral. Arabic is not a translation layer on top of English: it is Egyptian, written for a salaried person in Egypt (guideline `guideline/brand-voice.md`, A14 and B10). The website keeps English screenshots
(a decision recorded in the hand-off), so website Arabic pages describe the app without Arabic screenshots.

## How it works (read once)

- The profile's `locale` setting is `en` or `ar` (`SettingsStore`, key `locale`). `lightning/ui/web.py` reads it per request and renders the page in that locale.
- Text is translated at render time by `translate(text, locale)` and `localize_html(page)` in `lightning/ui/i18n.py`. The dictionaries are keyed by the **exact English string**:
  `lightning/ui/i18n.py` (page text) and `lightning/ui/i18n_system.py` (system messages, `{a}`/`{cur}`/`{n}` placeholders). A missing key shows English.
- Visible digits and separators in Arabic text are Arabic-Indic (٠١٢٣); inputs, identifiers, codes and dates inside inputs stay Western. Dates are `yyyy-mm-dd` and must not be reordered by right-to-left text.
- Layout mirrors through `lightning/ui/static/style.rtl.css`, `phone.rtl.css`, `profiles.rtl.css`.

## Token rules

Let the tests find untranslated strings; do not read the dictionaries (they are thousands of lines). Grep a single key before adding it. Check pages by extracting text, and take a screenshot only for layout.

## Steps

1. **Run the existing checks.** `python -m pytest -q tests/test_arabic_no_english.py tests/test_arabic_number_display.py`.
   The first draws the key PC pages and phone pages in Arabic with the sample household and fails on any visible text, title, `aria-label` or placeholder with an English word (three or more Latin letters),
   except names a person typed, codes and a short allow-list in the test. The second checks digits and separators. Failures name the page and the string.
2. **Render every page yourself** for what the tests do not reach: crawl with `tools/bug_crawl.py` against an Arabic profile (set the `locale` setting to `ar` on the demo database, restart), or reuse the
   test's helper (`build`, `load_mohab_2026`, `create_app`, set `locale`, `TestClient`). Extract the visible text, list distinct strings containing three or more Latin letters, and drop names, codes and brand words
   (Lightning, CIB, NBE, THNDR, EGP where the guideline keeps them).
3. **Add each missing string** to the right dictionary with the **exact English text** as the key (including placeholders and trailing punctuation) and an Egyptian-Arabic value:
   short, calm, concrete, no exclamation marks, "you" as the second person, whole numbers and EGP as the guideline says. Keep placeholders identical (`{a}`, `{cur}`, `{n}`). Grep the key first to avoid a duplicate.
   For a singular and a plural English string (for example "Held {n} day" and "Held {n} days") add both.
4. **Check by eye** (one screenshot per screen at 1280 and 390 wide, only for changed pages): text aligns right; icons that point (back, forward, chevrons) mirror; tables read right to left; numbers keep their sign next to them;
   dates read as `yyyy-mm-dd` left to right (wrap them in a bidi-isolating element if they scramble); nothing overflows sideways; no half-English labels; charts keep their labels in Arabic.
5. **Voice.** Read `guideline/brand-voice.md` once, and keep to its words list: the same term for the same thing everywhere (use the glossary `docs/GLOSSARY.md` names). No literal word-by-word translations.
6. **Tests and merge.** Re-run step 1, then the changed-area tests and Mohab. Add a test only for logic (a new plural, a new pattern); strings are covered by the no-English test. One branch (`claude/arabic-<what>`), changelog line, merge.

## Report

**Where findings go.** Read `issues/README.md` once. Fix a small finding now (branch, test, changelog line) and file **no** item. File anything bigger as one item in
the milestone it belongs to, `issues/<n>-<name>/<code>-<what>.md` (code from `python tools/issues.py next <n>`; this skill's name in `skills`, your model in `by`, `app_version`
from `pyproject.toml`, `commit` from `git rev-parse --short HEAD`), then run `python tools/issues.py`. Finishing an item means deleting its file in the same commit and adding its code to the milestone's `done:`. Never leave a finding only in chat.

Pages checked, the strings you added (count and 5 examples), layout problems found and fixed, anything left (with page and string) for a native reader to review. Say plainly that a human Arabic reader should check the voice.
