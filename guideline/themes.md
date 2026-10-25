# Lightning themes: how to make one

A theme is something a member buys **once** that dresses **every surface Lightning has**: the main website (guideline Part B), For Geeks (Part D) and, when app themes ship, the PC app and the phone (Parts A and C). It is one item with one name and one price. Each surface draws its **own version** of it in its own guideline: Nile on For Geeks is a terminal at night, and Nile on the main site is a Part B page with a light and a dark side. A theme that works on one surface only is not finished.

A theme is built from **parts**. Each part is a compartment, such as buttons, cards or the header. A part may change only the colours listed for it below, and every theme fills the parts the same way. That is what lets a new theme ship without breaking a page, and lets someone change one part (say, buttons) across every theme at once.

This file sits beside the four guideline documents and is copied to both repositories, like `brand-voice.md`. Change both copies in the same session.

## 1. What is on sale now

Owner, 2026-10-25: five palettes on sale while each is proven on both sites, and no more until they are.

| Theme | Seed: ground · text · quiet · accent | Side | Price |
|---|---|---|---|
| Mono | `#0a0a0a` `#f2f2f2` `#b8b8b8` `#ffffff` | dark | free, the default |
| Paper | `#f4f1ea` `#161616` `#45413a` `#a8401c` | light | 100 |
| Frost | `#eef2f7` `#0f1722` `#3b475a` `#3340c4` | light | 250 |
| Meadow | `#08192A` `#EAF4F1` `#B8CAD2` `#3FCB93` | dark | 100 |
| Nile | `#070b16` `#e9edf7` `#b7c0d8` `#e6b450` | dark | 100 |
| Garnet | `#1a0608` `#fbeee4` `#e0b9ab` `#ff6b57` | dark | 200 |

**Archived:** Ocean, Tokyo, Dracula, Rose, Synthwave, Phosphor, Amber, Solarized and Moss. They are not sold and not shown, but a member who owns one keeps it, sees it and can wear it. Their seeds stay in `js/forgeeks.js` marked `archived:true` and their tokens stay in `css/forgeeks.css`. To bring one back, take it through section 5 like a new theme, then set `active = true` in a migration and drop `archived:true`.

The two app themes in testing, Nile Nocturne and Royal Obsidian & Gold (`cosmetics/*.json`), have no price until the app can wear them.

## 2. The seed

Every theme starts from four colours and a name:

- **ground**: the page.
- **text**: headlines and values.
- **quiet**: body text, labels, notes.
- **accent**: the one voice. It is used for buttons, links, focus and the current state.

The seed also has a **side**, light or dark, which is the side the theme was drawn on. The seed is the only place the theme's colours are invented. Everything else is worked out from the seed, by rule or by hand, inside the parts.

The seed must pass these before anything else:

- text on ground is 7:1 or more;
- quiet on ground is 4.5:1;
- accent on ground is 3:1;
- the accent's label (ground or text, whichever reads better) is 4.5:1 on the accent.

## 3. The parts

Eleven parts, the same eleven on every surface. A part not listed for a surface does not exist there yet, and it keeps that surface's default.

| # | Part | What it covers | Main site (Part B tokens) | For Geeks (Part D tokens) | App (`cosmetics/slots.json`) |
|---|---|---|---|---|---|
| 1 | **Colours** | Ground, text, quiet text | `--paper` `--ink` `--ink2` `--muted` `--canvas` | `--bg` `--ink` `--dim` `--faint` | `palette` |
| 2 | **Header and top bar** | The bar and its seam | `--bar-bg` | the bar reads `--bg` at 94% | `header` |
| 3 | **Navigation** | Active tab, section strip | the active pill reads part 7 | `--accent` (rail, current) | `navigation` |
| 4 | **Hero** | The lead card or the field behind the hero | `--lead` | `--particle` `--glow` | `hero` |
| 5 | **Cards and lists** | Panels, rows, hairlines | `--white` `--panel` `--line` `--track` | `--panel` `--well` `--line` `--line-strong` | `cards` |
| 6 | **Charts and progress** | Lines, meters, grids | the site's charts keep their meaning colours | `--accent2` | `charts` |
| 7 | **Buttons and inputs** | Primary and secondary buttons, links, focus, fields | `--nile` `--nile-2` `--on-nile` `--azure` `--line-ctl` `--field` `--field-focus` | `--btn` `--btn-ink` `--accent` | `controls` |
| 8 | **Sheets and dialogs** | Windows, the buy window, overlays | reads part 5 | `--panel` | `overlays` |
| 9 | **Settings and menus** | Menus, dropdowns, dividers | reads part 5 | reads part 5 | `menus` |
| 10 | **Texture and motion** | Pattern, ambient motion | none: fixed | the field's colour only (part 4) | `decoration`: `none` for now |
| 11 | **Brand mark** | The two-leaf logo | the light or dark mark, never recoloured | `geeks-mark-light` / `-dark` | `brand`: `on-light` / `on-dark` |

The footer and the consent bar are part 1 plus part 5 (`--sf-*` and `--lc-*` on the main site).

**Never a part, on any surface:** layout, sizes, spacing, border widths, radii, fonts, words, routes, the order of things, touch targets, what a number means, and the money colours. Green in, Rose out and Azure held belong to the main site and the app, and no theme moves them. For Geeks has no money colours at all (D02).

In code, each surface keeps the same compartments:

- main site: `skinParts()` in `js/theme.js` returns `colours`, `header`, `hero`, `cards`, `controls`, `footer` and `consent`;
- For Geeks: the fourteen tokens of D03, one rule per theme in `css/forgeeks.css`;
- app: the parts of a manifest in `cosmetics/`.

To change how one part looks in every theme (say, buttons), change that part's rule on each surface and nothing else.

## 4. Each surface draws its own version

**For Geeks (Part D).** The fourteen D03 tokens are set by hand from the seed: `--bg` is ground, `--ink` is text, `--dim` is quiet, and `--accent` and `--btn` are the accent. A light theme also joins the light lists in `css/forgeeks.css`: the scanlines, and the dark and light marks.

**Main site (Part B).** Nothing is written by hand. `variant()` in `js/theme.js` turns the seed into a **light side and a dark side**, so the light/dark switch keeps working while the theme is worn.

- The theme's own side keeps its seed.
- The other side is turned over: the seed's ground becomes the text, on a ground tinted 5% (light) or 7% (dark) with the accent.
- Quiet text and the accent then move toward the text until each reads at 4.5:1.

`js/theme-preview.js` holds the same rule for the previews, and a test keeps the two copies equal.

**App (Parts A and C).** A manifest in `cosmetics/` fills the app's fourteen palette tokens and its parts. It is validated by `js/cosmetic-parts.js` against `cosmetics/slots.json`. The app wears it only when its own registry and acceptance allow; until then the market shows it on drawn PC and phone screens.

## 5. Making a theme, step by step

1. **Seed.** Add `{id, name, note, c:[ground, text, quiet, accent]}` to `THEMES` in `js/forgeeks.js`. Add `light:true` for a light side, and `paid:true, price:n`.
2. **For Geeks part values.** Add one `:root[data-theme="id"]{…}` rule with all fourteen tokens to `css/forgeeks.css`. For a light theme, also add it to the light lists.
3. **Lists.** Add the id to `THEME_IDS` in `tools/geeks_shell.py`, bump its `VERSION`, and run it. Run `python tools/site_accounts.py` so the main site reads the new seed.
4. **Catalogue.** Add a migration that inserts the `catalog_items` row (type `theme`, name, note, price). The price in `js/forgeeks.js` must match it.
5. **Check every part on every surface.**
   - `python tools/theme_contrast.py` checks For Geeks.
   - `supabase/tests/market-ui-pages.test.mjs` checks both main-site sides at 4.5:1 and the app mix.
   - Then open the market's Details for the theme and look at every view: Website (light and dark), For Geeks, Computer, Phone. Use Try it on both sites.
6. **Record.** Add the theme to the table in section 1 and to D03.1, in both repositories, and add a changelog entry.

To archive a theme: add a migration setting `active = false` (owners keep it), mark it `archived:true` in `js/forgeeks.js`, and move it to the archived line in section 1 and D03.1.

## 6. Before a theme ships

A theme with any of these is not done:

- A surface it does not work on: both sites, both main-site sides.
- Text under 4.5:1 anywhere, or a control or focus ring under 3:1.
- A colour outside its part: a button colour in a card, an accent in body text.
- Money colours moved on the main site or in the app, or any money colour on For Geeks.
- A layout shift: put screenshots against the default theme side by side, and nothing may move.
- Motion that ignores reduced motion. For now there is no motion at all.
- A seed edited without rechecking every part.
