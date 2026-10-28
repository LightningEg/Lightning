# Lightning themes: how to make one

A theme is something a member buys **once** that dresses **every surface Lightning has**: the main website (guideline Part B), For Geeks (Part D) and, when app themes ship, the PC app and the phone (Parts A and C). It is one item with one name and one price. Each surface draws its **own version** of it in its own guideline: Nile on For Geeks is a terminal at night, and Nile on the main site is a Part B page with a light and a dark side. A theme that works on one surface only is not finished.

A theme is built from **parts**. Each part is a compartment, such as buttons, cards or the header. A part may change only the colours listed for it below, and every theme fills the parts the same way. That is what lets a new theme ship without breaking a page, and lets someone change one part (say, buttons) across every theme at once.

This file sits beside the four guideline documents and is copied to both repositories, like `brand-voice.md`. Change both copies in the same session.

## 1. What is on sale now

Owner, 2026-10-25: five palettes and two textured themes on sale while each is proven on both sites; 2026-10-26: Papyrus moves to the animated tier, and Dendera joins it. Prices are in coins (5 coins = 1 EGP); section 7 explains them.

| Theme | Tier | Seed: ground · text · quiet · accent | Side | Coins |
|---|---|---|---|---|
| Mono | palette | `#0a0a0a` `#f2f2f2` `#b8b8b8` `#ffffff` | dark | free, the default |
| Paper | palette | `#f4f1ea` `#161616` `#45413a` `#a8401c` | light | 300 |
| Frost | palette | `#eef2f7` `#0f1722` `#3b475a` `#3340c4` | light | 300 |
| Meadow | palette | `#08192A` `#EAF4F1` `#B8CAD2` `#3FCB93` | dark | 300 |
| Nile | palette | `#070b16` `#e9edf7` `#b7c0d8` `#e6b450` | dark | 300 |
| Garnet | palette | `#1a0608` `#fbeee4` `#e0b9ab` `#ff6b57` | dark | 300 |
| Papyrus | animated | Nile's seed, texture `papyrus`, one gold thread | dark | 1,000 |
| Cotton | textured | Paper's seed, texture `cotton` | light | 600 |
| Dendera | animated | `#f1e6cc` `#1e1a14` `#54483a` `#1f3f8c`, texture `dendera`, one pigment thread | light | 1,000 |

**Archived:** Ocean, Tokyo, Dracula, Rose, Synthwave, Phosphor, Amber, Solarized and Moss. They are not sold and not shown, but a member who owns one keeps it, sees it and can wear it. Their seeds stay in `js/forgeeks.js` marked `archived:true` and their tokens stay in `css/forgeeks.css`. To bring one back, take it through section 5 like a new theme, then set `active = true` in a migration and drop `archived:true`.

**Ready to sell (owner, 2026-10-26).** One theme is one purchase on every surface, so the app's paid themes take the website's ids: **Nile** (palette), **Cotton** (textured) and **Papyrus** (animated: a lapis lacquer hero with a travelling gold-foil edge in the app, a slow gold thread along the header on the sites). The animated tier is on sale at 1,000 coins with Papyrus and **Dendera** (temple pigments on aged papyrus, a lotus-bud frieze, the zodiac ring and the winged sun disc; one slow pigment thread along the header). Dendera is the first theme with two app modes: `dendera` (day) and `dendera-night`, one purchase, worn with Dendera's one licence. In the app a paid theme is tried by anyone and kept with a licence unlocked by the website's one-time code (`lightning/ui/entitlements.py`); each stays off in the store until the app release that carries it ships. Royal Obsidian & Gold stays a test preview: it has no website version yet.

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
| 10 | **Texture and motion** | Pattern behind the page; later, one motion | textured tier: `:root[data-texture]` (`css/textures.css`) | the same texture, under the field | `ground` (texture, artwork, ambient and equip motion), plus each element's material and motion layer (section 8) |
| 11 | **Brand mark** | The two-leaf logo | the light or dark mark, never recoloured | `geeks-mark-light` / `-dark` | `brand`: `on-light` / `on-dark` |

The footer and the consent bar are part 1 plus part 5 (`--sf-*` and `--lc-*` on the main site).

**Never a part, on any surface:** layout, sizes, spacing, border widths, radii, fonts, words, routes, the order of things, touch targets, what a number means, and the money colours. Green in, Rose out and Azure held belong to the main site and the app, and no theme moves them. For Geeks has no money colours at all (D02).

In code, each surface keeps the same compartments:

- main site: `skinParts()` in `js/theme.js` returns `colours`, `header`, `hero`, `cards`, `controls`, `footer` and `consent`;
- For Geeks: the fourteen tokens of D03, one rule per theme in `css/forgeeks.css`;
- app: the elements of a manifest in `cosmetics/`, finer than the eleven (ground, buttons, tabs, fields and progress are their own), each with paint, material and motion (`theme-kit/README.md` › Element inventory).

To change how one part looks in every theme (say, buttons), change that part's rule on each surface and nothing else.

## 4. Each surface draws its own version

**For Geeks (Part D).** The fourteen D03 tokens are set by hand from the seed: `--bg` is ground, `--ink` is text, `--dim` is quiet, and `--accent` and `--btn` are the accent. A light theme also joins the light lists in `css/forgeeks.css`: the scanlines, and the dark and light marks.

**Main site (Part B).** Nothing is written by hand. `variant()` in `js/theme.js` turns the seed into a **light side and a dark side**, so the light/dark switch keeps working while the theme is worn.

- The theme's own side keeps its seed.
- The other side is turned over: the seed's ground becomes the text, on a ground tinted 5% (light) or 7% (dark) with the accent.
- Quiet text and the accent then move toward the text until each reads at 4.5:1.
- **Dark mode is the visitor's.** A light theme (Cotton, Papyrus) never recolours dark mode: the switch shows the plain dark site, and the theme stays worn for when light mode returns. A dark theme still shows in both modes (`paintsOn()` in `js/theme.js`).

`js/theme-preview.js` holds the same rule for the previews, and a test keeps the two copies equal.

**App (Parts A and C).** A manifest in `cosmetics/` fills the app's fourteen palette tokens and its parts. It is validated by `js/cosmetic-parts.js` against `cosmetics/slots.json`. The app wears it only when its own registry and acceptance allow; until then the market shows it on drawn PC and phone screens.

## 5. Making a theme, step by step

One flow for every theme and every maker, person or AI. Each step names its files and the check that closes it. A worked example, with what each step found, is the Dendera report (app repository, `reports/2026-10-26-dendera-theme/report.md`).

**The order of care (owner, 2026-10-26): function first, then clarity and polish, then looks.** Texture and motion are welcome, never at the cost of a working screen, speed or a clear reading. When a look and a reading disagree, the reading wins.

1. **Brief.** Fill the brief in the app's `theme-kit/README.md`: id, name, mode (day, night or both), tier, and one sentence on what the theme says. List each reference with its source and licence. References are studied, never shipped: only drawings made for Lightning ship.
2. **Plan.** Write the plan in `theme-kit/plans/<id>.html` before any code: what each reference gives (a colour, a pattern, an edge, a light, a motion); the seed and each mode's fourteen colours with their contrast; every element's paint, material and motion (the inventory in the kit); which motifs the recipe library already draws and which need a new recipe; the one continuous motion and why it is cheap. Keep layout, sizes, fonts, words and money colours out of the plan: a theme never moves them.
3. **Seed and palettes.** The seed passes section 2. Each mode's fourteen app colours pass `python tools/build_themes.py --validate <manifest>`, run as soon as the palette exists, not at the end.
4. **Recipes: reuse first.** Use the library in the kit. A motif it lacks becomes a new recipe, reviewed once, then free for every theme:
   - its drawing is an SVG in `lightning/ui/static/cosmetics/assets/<id>/<recipe>.svg`, in the folder of the theme that introduces it: shapes only, lines in `currentColor` (the accent), a part in another palette colour by `class="p-<key>"`; the build recolours it per theme and inlines it, so nothing is fetched;
   - its name goes on its list in `cosmetics/slots.json` (a finish also gets its lift in `limits`);
   - its paint goes in `theme-materials.css`, with its still frame under reduced motion;
   - a test in `tests/test_theme_build.py`.
5. **App manifests.** Start from `theme-kit/theme.template.json`, one manifest per mode; a second mode names its store item (`"item": "<id>"`), so one licence wears both. A paid manifest names its store tier (`"tier"`: `palette`, `texture` or `motion`), and the build refuses one that does not fill exactly that tier. Run `python tools/build_themes.py` and `tests/test_theme_build.py tests/test_theme_entitlements.py`; the shells link each file by its content hash, so no asset version is bumped by hand.
   - **Versions.** A licence covers the version it names and every later one (app `security/cosmetic_license.py`), so a look buyers already own keeps working when it changes. Once a version has reached buyers, raise `version` whenever a delivered asset changes (a colour, a recipe, a drawing): the store's `bundled_item_versions` row follows it. A second mode's manifest keeps its item's version and tier.
6. **Real screens.** `python tools/theme_shots.py OUT --themes <id>` captures the six roster screens on PC and phone (`--ar` for Arabic). Put each beside the default. A spot that is unreadable is fixed once in the app's CSS for every theme, never with theme markup. Then `python tools/theme_check.py --themes <id>`: no element may move against the default on any roster screen, and no frame may run long while the motion plays.
7. **The sites.** In the website repository:
   - seed in `THEMES` in `js/forgeeks.js` (`light:true`, `tex:'<id>'`, `paid:true, price:n` at the tier price);
   - the fourteen For Geeks tokens in `css/forgeeks.css`, and the light lists for a light theme;
   - its texture and motion in `css/textures.css`, with the id in `TEXTURES` (`js/theme.js`) and `TEX` (`js/theme-preview.js`);
   - the id in `THEME_IDS` and a new `VERSION` in `tools/geeks_shell.py`, then run it and `python tools/site_accounts.py` (bump its `SHOP` version when the market's files change);
   - when it dresses the app, its line in `APP` in `js/market-ui.js`, and copies of the app's manifests and asset folder in `cosmetics/`;
   - a migration with the `catalog_items` row (type `theme`, tier, the tier's price) and a disabled `bundled_item_versions` row;
   - `python tools/theme_contrast.py` and every `supabase/tests/*.test.mjs`.
8. **Check.** Section 6, on every surface, both modes, PC and phone.
9. **Record and hand over.** The table in section 1 (D03 points here), the plan and the report with its evidence, a changelog line in each repository, and one pull request in each.

To archive a theme: add a migration setting `active = false` (owners keep it), mark it `archived:true` in `js/forgeeks.js`, and move it to the archived line in section 1.

## 6. Before a theme ships

A theme with any of these is not done:

- A surface it does not work on: both sites, both main-site sides.
- Text under 4.5:1 anywhere, or a control or focus ring under 3:1.
- A colour outside its part: a button colour in a card, an accent in body text.
- Money colours moved on the main site or in the app, or any money colour on For Geeks.
- A layout shift: put screenshots against the default theme side by side, and nothing may move.
- Motion that ignores reduced motion, or more than one continuous motion in a theme.
- A seed edited without rechecking every part.
- A texture or motion that slows a page, sits under a reading, or competes with the figure for the eye. One continuous motion, cheap to draw (a 1px seam or a transform); no pointer-following light or blur where the phone has to keep up.
- A screen checked only in a workbench: every roster screen, both modes, PC and phone, English and Arabic.

## 7. Tiers and prices

Every look climbs the same three steps, and each step keeps everything below it. The highest tier of anything has all three: recolour, texture and animation. Prices are in coins (5 coins = 1 EGP); the console sets them (Catalogue), and a theme tier keeps one price.

1. **Recolour**: new colours only.
2. **Texture**: the colours plus a material: a woven ground, grain, edge light, depth, a pattern or a drawn scene.
3. **Animation**: the texture plus one slow signature motion (8 seconds or more, still under reduced motion).

**Themes**: one purchase dresses both sites, the PC and the phone.

| Tier | What changes | Coins | EGP | On sale |
|---|---|---|---|---|
| **Palette** (recolour) | Every colour on every screen: page, header, menu, cards, buttons, tabs, fields, charts, dialogs; a light and a dark side on the main site | 300 | 60 | Paper, Frost, Meadow, Nile, Garnet |
| **Textured** (recolour + texture) | Plus the material: a texture behind every page, grain and a lit edge on cards, depth, a watermark, finishes on buttons, tabs and fields | 600 | 120 | Cotton |
| **Animated** (all three) | Plus one slow signature motion (Papyrus: gold-foil light travelling the lead card's edge in the app, a gold thread along the site's header) and motions that answer you: a light following the pointer on cards, a sheen on buttons, dialogs rising in, one light sweep when you put it on | 1,000 | 200 | Papyrus, Dendera |

**Banners**: the strip on your profile, leaderboard row and account.

| Tier | What changes | Coins | EGP | On sale |
|---|---|---|---|---|
| Recolour | One colour field or glow | 100 | 20 | Halo |
| Texture | A drawn scene or pattern | 120–200 | 24–40 | Blueprint, Dusk, Circuit, Dunes, Borealis; seasonal 200–250 |
| Animation | The scene with one slow motion | 300–350 | 60–70 | Drifting stars, Nile at night |

**Frames**: the ring round your picture.

| Tier | What changes | Coins | EGP | On sale |
|---|---|---|---|---|
| Recolour | A ring in one colour | 80 | 16 | Halo, Nile |
| Texture | A metal or double ring | 100 | 20 | Gold, Double |
| Animation | The ring with one slow glint | 200 | 40 | none yet |

**Badges**: the mark beside your name. Earned badges (supporter, Founding, contribution) are never sold.

| Tier | What changes | Coins | EGP | On sale |
|---|---|---|---|---|
| Recolour | A simple mark in one colour | 60 | 12 | Lightning mark (the two-leaf logo, in its own colours), Coin |
| Texture | A drawn, detailed mark | 80–120 | 16–24 | Pen, Star; seasonal Cotton boll, Fanous |
| Animation | The mark with one slow motion | 200 | 40 | none yet |

**Names**: your display name wherever it shows.

| Tier | What changes | Coins | EGP | On sale |
|---|---|---|---|---|
| Recolour | One colour | 150 | 30 | Gold, Nile |
| Texture | A gradient | 300 | 60 | Sunset |
| Animation | One slow shimmer | 500 | 100 | Shimmer |

**Sets** cost 80% of the parts you do not own yet (a theme, a banner, a frame and a fourth piece: 680 to 890 coins new). **Seasonal** items keep their tier's price and are sold only inside their window; owners keep them after.

**Texture rules:**
- Drawn by code: gradients, or inline SVG generated from the theme's own colours. No image files, requests or scripts.
- On the ground: the text colour at 2 to 7%, behind all content.
- In the app, a surface may carry its own grain (text colour, 3 to 4%) and one fine-line watermark (accent, 12%) in an empty corner, never under a figure. Text keeps 4.5:1 because contrast is checked at each surface's worst point: finish, grain and watermark together.
- One texture serves every surface: `css/textures.css` styles the page (`:root[data-texture]`) and the previews (`.pv[data-tex]`).
- A texture's id is listed in `js/theme.js` (`TEXTURES`) and `js/theme-preview.js`, and set by `tex:` in the seed.

**Motion rules:**
- One continuous motion per theme, slow (8 seconds or more), behind content or along an edge.
- Motions that answer the user (a card's hover light or lift, a button's sheen, a dialog rising in) and one equip moment when the theme is put on may join it. None loops.
- Never on a number, and never anything that blinks.
- Under reduced motion every motion stops and shows one still frame.
- On For Geeks a theme also brings its own field scene (Part D, D08), in its `--particle` and `--glow`, with one event every 6–12 seconds: ink contours (Paper, Cotton), a river at night (Nile, Papyrus), embers (Garnet), snow and an aurora (Frost), a star ceiling (Dendera), grass and fireflies (Meadow). A theme without one keeps Mono's terrain and lightning.

**Prices:**
- Prices live in the catalogue (`catalog_items.price`, `tier`). The market shows coins and the EGP they cost (`coin_rate()`).
- A tier keeps one price. A sale is a new seasonal item, not a cut on an old one.
- Why these prices: buyers pay once, not monthly. The arithmetic against fixed costs is in the website repository's `docs/payment-operations.md` › Pricing and operational economics.

**Beyond themes (the supporter release, website, 2026-10-25).** The same rules hold for every look sold beside themes:
- **Names** (type and slot `name`, tiers above): each hue is mixed 60% with the page's text colour, so a styled name keeps 4.5:1 on every theme, light and dark.
- **Animated banners** (tier `motion`): one slow motion each, behind content, still under reduced motion.
- **Seasonal items** carry a window (`available_from`, `available_until`): sold and shown only inside it; owners keep them after.
- **Sets** cost 80% of the parts not owned yet. A set is never a fifth slot: buying it delivers its parts.
- **Earned badges** (supporter, founding) are never sold, and contribution badges stay earned by work.

**What comes next:**
- One textured theme a month (the drop), so earlier buyers have something new to buy. Supporters vote on which one.
- Seasonal items at tier prices.
- An animated theme only once one passes section 6 with its motion. Papyrus is the first.

## 8. PC and phone creator handoff

The app's [`theme-kit/README.md`](https://github.com/LightningEg/Lightning/blob/main/theme-kit/README.md) is the external creator brief, delivery checklist and acceptance process. `theme-kit/theme.template.json` is the complete starting manifest, and `theme-kit/preview.html` exercises components using the real app tokens. Give creators this guideline, Parts A and C, and `lightning/ui/static/cosmetics/slots.json` together.

`python tools/build_themes.py --validate path/to/theme.json` checks the existing data-only contract and text/control contrast pairs. Reviewed app previews are bundled under `lightning/ui/static/cosmetics/`; `python tools/build_themes.py` generates the root `data-theme` CSS and boot registry. Both app frames load the same switcher before content paints. Settings → Appearance switches paint without navigating and remembers it with the profile across native launches; an unknown saved ID returns to Lightning default. The exact default paint stays in the existing guideline stylesheets.

**The app's material system.** An app theme is every element times three layers, all stated: **paint** (palette keys), **material** (finish, grain, edge light, depth, artwork) and **motion**. The element inventory and the recipe library are in `theme-kit/README.md`; `slots.json` is their machine copy and `lightning/ui/static/theme-materials.css` draws the recipes. A manifest only picks recipes; a new recipe is app code, reviewed like any other, and then serves every theme. Its drawing lives in the asset folder of the theme that introduced it (`cosmetics/assets/<theme>/<recipe>.svg`), and the website keeps a copy of every folder. The validator refuses a missing layer, a value off the list, more than one continuous motion, and text under 4.5:1 at a surface's worst point. `python tools/theme_shots.py OUT --themes id` captures the six roster screens on PC and phone. Financial tokens and series retain their existing meanings. Actual Windows/Android screens, English/Arabic, contrast and geometry still require the kit's acceptance checks. Bundling a preview does not enable sale or prove paid ownership; verified claiming remains a separate release prerequisite.
