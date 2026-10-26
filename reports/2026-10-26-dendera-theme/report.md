# Dendera theme: the workflow, and how it compares with the theme flow

Date: 2026-10-26 · Author/reviewer: Claude (owner request)
Repository: both · Reviewed commit: 671ed5cdd20e8357f32bd3d6c6878cca51a64a9d (app), 3101c21 (website); branches `claude/dendera-polychrome-theme`

## Scope and method

The owner gave two references (a sheet of historical Egyptian banknotes, temple wall photographs and the Knana Goran porcelain set; and a first Dendera plan) and asked for three things: improve and build the whole plan so it feels premium, document the workflow and compare it with the existing theme flow so another AI or person can follow it, then add the theme to the website. Mid-task the owner added two rules: every theme keeps its SVGs in its own asset folder, and function comes first, then clarity and polish, then looks; texture and motion never at the cost of function, speed or clarity.

Method: build the theme end to end on both repositories, write down every step as it happened, then hold each step against `guideline/themes.md` sections 5 to 8 and the creator kit (`theme-kit/README.md`, `AI-PROMPT.md`) as they stood on `claude/theme-materials` (PR #143). The result is the new section 5 of `guideline/themes.md`, which is the process to hand over. The plan the theme was built from is [theme-kit/plans/dendera.html](../../theme-kit/plans/dendera.html).

## The workflow as it ran

| Step | What I did | Output |
|---|---|---|
| 1. Read the references | Read both PDFs page by page; listed what each source *gives* (a colour, a pattern, an edge, a light, a motion), with its source and licence | The references table in the plan |
| 2. Read the current system | `themes.md`, the kit, `slots.json`, `theme-materials.css`, `build_themes.py`, Papyrus and Cotton, the website's theme files; found PR #143 open with schema 2 and built on it | Branches on top of `claude/theme-materials` |
| 3. Judge the first plan | Checked each line against the rules; ten lines broke one (table in the plan): three motions, a fret inside every card, new screen layouts, fonts, its own token names, the rosette (Papyrus's), dark as a table only, blur, flat-surface contrast, no website version | *What changed* table |
| 4. Pigments into palettes | Mapped the four pigments onto the fourteen keys (kenit to `hero`, mefkat to `focus`, desher to `warning`); a day and a night manifest; ran the validator before anything else | `dendera.json`, `dendera-night.json` |
| 5. Recipes: reuse, then add | Reused papyrus texture, satin, foil edge, cartouche, rise, unveil. Added what only Dendera has: `zodiac-ring`, `winged-disc`, `lotus-frieze`, `pigment-thread` | Four recipes, SVGs in `cosmetics/assets/dendera/` |
| 6. Asset folders (owner) | Moved Papyrus's two drawings out of Python into `cosmetics/assets/papyrus/`; the build reads, checks and recolours each file; Papyrus and Cotton screens stayed pixel-identical | `tools/build_themes.py`, tests |
| 7. Real screens | `theme_shots.py` for both modes, PC and phone; looked at every screen | Evidence below |
| 8. Fix what the screens showed | Frieze too close to the date line (made smaller, lower); frieze and seam missing on the phone (selector strength); wide cards light on every dark theme (F1); `--ar` captured English (F2) | Fixes in `theme-materials.css`, `theme_shots.py` |
| 9. Prove nothing moves and nothing stutters | Compared every element box with the default and timed frames with the motion running; turned the scripts into a tool | `tools/theme_check.py` |
| 10. The sites | Seed, For Geeks tokens and light lists, texture and pigment thread, lists, versions, market line, manifest and asset copies, catalogue migration, test lists | Website branch |
| 11. Write it down | The plan, this report, the new `themes.md` section 5, the kit and AI prompt | This folder, `theme-kit/plans/` |

## Compared with the earlier flow

| Earlier flow (themes.md section 5, the kit, AI prompt) | Gap found while building | Now |
|---|---|---|
| Section 5 listed the website steps only; the app steps sat in section 8 and the kit | A maker had to stitch three documents together and could miss the app or the sites | One flow, nine steps, both repositories, each step with its files and the check that closes it |
| No reference or plan step | The first plan skipped the rules; nothing caught it until code review | Steps 1 and 2: a brief with sources and licences, then a plan (`theme-kit/plans/<id>.html`) before code |
| No order of care | The first plan reached for three motions and blur | The owner's order at the top of section 5 and new items in section 6: slows a page, sits under a reading, competes with the figure; workbench-only checks |
| New recipes were "app code, reviewed"; how was unwritten | Drawings were SVG strings inside `build_themes.py` | Step 4 and section 8: an SVG of shapes in `cosmetics/assets/<theme>/<recipe>.svg`, its name in `slots.json`, paint in `theme-materials.css`, a test; the build refuses anything but shapes |
| "Put screenshots side by side, nothing may move" | A look by eye cannot see a 1 px shift | `tools/theme_check.py`: every element box against the default, and frame timing with the motion on |
| `theme_shots.py --ar` documented | It captured English (F2) | `--ar` switches the profile to Arabic and refuses to continue if the page is not right to left |
| The kit spoke of two modes as separate manifests, but one purchase is one store id | A night mode had no way to ride on its item's licence | `"item": "<id>"` on the second mode; the app's licence check, Settings list and picker follow it |
| Section 5 step 6 asked for D03.1 to be updated too | D03.1 never listed the textured themes; the fact had two homes | Section 1 of `themes.md` is the one home; D03 already points there |
| AI prompt: "describe a missing recipe for the maintainers" | An AI maker stopped where it could have built | The prompt follows section 5 and proposes the recipe in the same shape a maintainer reviews |
| Website copy test covered the manifests | Drawings would drift between the repositories | The test now also compares every asset folder, both ways |

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
|---|---|---|---|---|
| F1 | high | On every dark theme (Nile, Papyrus, now Dendera night) the wide cards (Investments › By currency, budget meters, plan cards) kept the default's light green gradient, so their titles were unreadable. The default's rule holds `#budget-meters` inside `:is()`, which outranks every theme rule. Fixed for every theme with one stronger rule in the cards recipe. | `evidence/pc-night-investments.jpg` | Fixed on this branch |
| F2 | medium | `tools/theme_shots.py --ar` was documented but never switched language, so Arabic evidence was English. Now it switches through Settings and checks `dir="rtl"`. | `evidence/pc-ar-day-overview.jpg`, `evidence/phone-ar-night-transactions.jpg` | Fixed on this branch |
| F3 | medium | On the phone the frieze and the pigment seam did not paint: the dark adapter's app-bar rule outranked the recipes. Fixed with the same selector strength the other recipes use, and the same for the `glass` finish and `security-thread`, which had the same weakness (Papyrus's glass app bar). | `evidence/phone-day-overview.jpg` | Fixed on this branch |
| F4 | low | The first plan was a design brief, not a theme: it moved layout, named fonts and ran three motions. The new section 5 asks for a plan that keeps those out, before code. | The plan's *What changed* table | Process change in this branch |

## Validation and limits

- `python tools/build_themes.py --validate` passes for both manifests; `python tools/build_themes.py --check` is current.
- `tests/test_theme_build.py`, `tests/test_theme_entitlements.py`, `tests/test_cosmetic_licenses.py` and the theme, phone, i18n and docs test groups pass. Papyrus and Cotton screens are pixel-identical before and after the asset-folder move.
- `python tools/theme_check.py --themes dendera,dendera-night`: 0 of 3,600 element boxes moved on the six roster screens in each mode; mean frame 16.7 ms, 0 frames over 34 ms with the thread running. Headless desktop Chromium only.
- Website: `python tools/theme_contrast.py` (18 themes, 0 problems), `python tools/site_check.py` (0 errors), `python tools/docs_check.py`, every `supabase/tests/*.test.mjs`.
- Not checked: Windows WebView2 and the Android app on devices, screen readers, forced colours, a low-end phone, the live store (the market captures show its offline notice). Pigment hex values are designed for screens, not measured from the walls.

## Evidence

All captures use Mohab's sample year (PC) or the phone's dummy data. `pc-default-overview.jpg` is the default for geometry comparison; the rest are named by device, mode and screen. Site captures: `site-main-light.jpg`, `site-main-dark.jpg`, `site-forgeeks.jpg`.

## Dated follow-ups

None yet.
