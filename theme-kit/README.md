# Lightning app theme creator kit

Give this folder, `guideline/themes.md`, the app's `guideline/app.html` and `guideline/phone.html`, and `lightning/ui/static/cosmetics/slots.json` to the external creator. This kit covers PC and phone. A store theme must also supply the website versions described in the guideline.

For an AI creator, copy [AI-PROMPT.md](AI-PROMPT.md), complete its fields, and provide this kit or repository access.

## Brief to complete before design

- Theme ID (lowercase letters, numbers and hyphens), display name, creator, version and contact:
- Mood and reference images:
- Mode: [Dark | Light | Both] (required; specify OLED black explicitly if wanted):
- Light or dark ground; four seed colours (ground, text, quiet, accent):
- Requested tier: palette / textured / animated:
- Asset ownership and licence allowing Lightning to distribute it:
- Delivery date and reviewer:

Confirm the requested mode before choosing colours; do not infer it from a theme name or reference image. Each app manifest contains one palette. For **Both**, deliver two complete manifests with distinct IDs such as `your-theme-dark` and `your-theme-light`, and validate/capture each independently. Users select each variant explicitly; the current runtime does not automatically switch between them. Mode belongs in this brief, not an invented JSON field.

## Tiers: what you build and what it sells for

Every look climbs three steps, and the highest tier has all three: **recolour**, **texture** and **animation**. Decide the tier in the brief; it sets which layers you fill. Prices are in coins (5 coins = 1 EGP), one price per theme tier, set by the owner in the console. Full tables, with what each tier changes: `guideline/themes.md` section 7.

| Kind | Recolour | + Texture | + Animation (highest) |
|---|---|---|---|
| **Theme** (both sites, PC, phone) | Palette: every colour on every screen · 300 coins, 60 EGP | Textured: plus the material (ground texture, card grain, edge light, depth, watermark, finishes) · 600 coins, 120 EGP | Animated: plus one slow signature motion and motions that answer you · 1,000 coins, 200 EGP |
| **Banner** | One colour field · 100 coins, 20 EGP | A drawn scene or pattern · 120–200 coins, 24–40 EGP | The scene with one slow motion · 300–350 coins, 60–70 EGP |
| **Frame** | A ring in one colour · 80 coins, 16 EGP | A metal or double ring · 100 coins, 20 EGP | One slow glint · 200 coins, 40 EGP |
| **Badge** | A simple mark · 60 coins, 12 EGP | A drawn, detailed mark · 80–120 coins, 16–24 EGP | One slow motion · 200 coins, 40 EGP |
| **Name** | One colour · 150 coins, 30 EGP | A gradient · 300 coins, 60 EGP | One slow shimmer · 500 coins, 100 EGP |

For a theme, the tier maps to the layers below: a **Palette** theme fills paint only and leaves every material `flat`/`none` and every motion `none`; a **Textured** theme adds material (ground texture, grain, edge light, depth, finishes, artwork) with no continuous motion; an **Animated** theme adds exactly one continuous motion (`ground.ambient`, `header.thread` or `hero.sheen`) and may add the motions that answer the user (hover, press, enter, equip). Cotton is the Textured reference and Papyrus the Animated one.

## How a theme is built: elements × layers

A Lightning theme is not a palette swap. It is a **complete specification**: every element in the inventory below states three layers, and nothing is left to the default by chance (the validator refuses a manifest with a missing layer).

- **Paint**: which of the theme's fourteen palette colours the element wears. Values are palette keys (`"surface"`), never hex.
- **Material**: how the surface is made: finish, grain, edge light, depth, artwork. Values come from the recipe library.
- **Motion**: how it moves: one continuous (ambient) motion at most per theme; hover, press and enter answer the user; equip plays once when the theme is put on.

Creators choose recipes; they never write CSS. A recipe is app code in `lightning/ui/static/theme-materials.css` (grain and artwork are drawn per theme, in its own colours, by `tools/build_themes.py`). A new recipe is proposed to the maintainers, reviewed once, and then every theme can use it.

## Element inventory

Every element, where it appears, and what each layer may be. `slots.json` is the machine copy of this table; the template fills every cell.

| Element | Covers (PC · phone) | Paint | Material | Motion |
|---|---|---|---|---|
| `palette` | Every colour. The money colours stay the app's own | 14 hex colours | | |
| `brand` | The two-leaf mark | | `logoVariant` | |
| `ground` | The page behind everything | (palette `background`) | `texture`, `textureStrength`, `artwork`, `vignette` | `ambient`, `equip` |
| `header` | Top bar · app bar | `surface`, `seam` | `finish` | `thread` |
| `navigation` | Sidebar and current page · tab bar and current tab | `surface`, `activeMark` | `finish`, `activeStyle` | |
| `hero` | Lead figure card, focal metrics, portfolio summary · (phone lead sits on the ground) | `surface`, `edge` | `finish`, `grain`, `edgeStyle`, `depth`, `artwork` | `sheen` |
| `cards` | Cards, panels, KPI tiles, overview blocks, list dividers · phone cards and tiles | `surface`, `border` | `finish`, `grain`, `edgeLight`, `depth` | `hover` |
| `charts` | Grid lines, nonfinancial accents | `grid`, `accent` | | |
| `controls` | Primary buttons, chosen chip, Add disc, focus ring | `fill`, `label`, `focus` | `finish`, `depth` | `press` |
| `buttons` | Secondary and small buttons, date picker | `surface`, `label`, `border` | `finish` | |
| `tabs` | Period switch, section tabs, segments, filter chips | `surface`, `chosen`, `chosenLabel` | `finish` | |
| `fields` | Inputs, selects, pickers, search | `surface`, `border` | `well` | |
| `progress` | Budget meters, plan bullets, KPI meters | `track` | `finish` | |
| `overlays` | Dialogs, pop-ups, sheets, period panel, their shade | `surface`, `backdrop` | `finish`, `grain`, `depth`, `shade` | `enter` |
| `menus` | Dropdowns, pick lists, context menus | `surface`, `divider` | `finish`, `depth` | |

## Recipe library

| Recipe | Values | What it is |
|---|---|---|
| finish | `flat` · `satin` · `lacquer` · `glass` · `foil` · `embossed` · `gloss` | satin: light falling from the top; lacquer: deeper corner light and a darker foot; glass: blurred translucent bar (phone app bar); foil: metallic accent gradient (buttons, chosen tab); embossed: pressed paper edges; gloss: a lit meter |
| grain | `none` · `film` · `paper` · `fibre` | fine noise in the text colour, inside the surface |
| texture (ground) | `none` · `film` · `papyrus` · `linen` · `laid`, at `whisper` · `subtle` · `rich` | the page's material, in the text colour at 2, 4 or 6% |
| artwork | `none` · `guilloche-rosette` · `lotus-line` | a fine-line watermark in the accent at 12%: the ground's far corner, the hero's empty corner; mirrored in Arabic |
| edgeLight / depth | `none` · `soft` · `bright` / `none` · `low` · `mid` · `high` | a highlight on the top edge / a shadow under the surface |
| edgeStyle | `hairline` · `foil` | the hero's border as a plain line or a gold foil ring |
| activeStyle | `bar` · `cartouche` · `glow` | how the current page is marked |
| well · shade · vignette | `flat` · `inset` · `deep` · `dim` · `blur` · `none` · `soft` | field depth · what sits behind a dialog · darker page edges |
| ambient | `none` · `glow-drift` (48 s) | continuous |
| thread · sheen | `none` · `security-thread` (12 s) · `edge-glint` (16 s) | continuous: a glint along the header seam / round the hero's foil edge |
| hover · press · enter · equip | `lift`, `light` · `sheen` · `rise` · `unveil` | answer the user: card lifts or a pointer light; foil sheen on hover/press; dialogs rise in; one light sweep when the theme is put on |

**The two references.** `cotton.json` (light: linen ground, paper cards, rosette watermark, embossed buttons, ink tabs) and `papyrus.json` (dark: papyrus ground, lapis lacquer hero with a gold foil edge whose light travels, lotus watermark, foil buttons and tabs, cartouche navigation, pointer light on cards) use most of the library. Start from whichever is closer.

**Hard rules the validator enforces.** Every layer stated. Values only from the library. Text 4.5:1 and primary text 7:1 measured at each surface's worst point: the finish's lift, plus the grain, plus the artwork (limits in `slots.json`); foil labels on both the light and dark ends of the foil. One continuous motion. Never moved by any layer: layout, sizes, spacing, radii, fonts, words, order, money colours; nothing is drawn over a figure; reduced motion stops every motion on a still frame.

## Submission package

Return the theme manifest(s), this completed brief, a short rationale for each compartment, licence/credits, and labelled screenshots. Capture every screen in this roster on **both PC and phone**, in **English and Arabic/RTL**, for **every requested mode**:

| Screen | Required evidence |
|---|---|
| Overview | Hero, KPI cards, comparisons and navigation |
| Transactions | Populated list, income/expense/transfer rows, transaction pills, and an open transaction dialog or phone sheet |
| Budget | Progress, remaining/overspent states and category chips |
| Investments | Holdings table/list, chart and legend |
| Accounts | Balances and account list |
| Settings | Theme selector, input focus, disabled control, validation error and an open menu |

Use dummy data and identify any state that cannot be reached. A workbench screenshot alone does not satisfy this roster.

- PC: 1366×768 and 1920×1080; phone: 320, 360 and 390 px wide.
- Navigation, hero, table/list, positive/negative/held amounts, input focus, disabled control, validation error, empty state, menu and open dialog.
- Default and new theme in the same position for geometry comparison.

## Contrast and RTL rules

Meet **WCAG AA: at least 4.5:1 for body text, labels and numbers, including text inside chips; at least 3:1 for meaningful control borders, chip indicators and focus rings against adjacent backgrounds**. A 3:1 chip outline does not permit 3:1 chip text. Purely decorative hairlines need not meet the control-border threshold. Keep Lightning's stricter primary-text-on-ground requirement of 7:1. Check real financial colours and interactive states on their actual surfaces; the validator covers only the pairs described above.

In Arabic, layout and text mirror, but each complete amount remains **left-to-right**, for example `EGP 14,250.00`. Preserve the app's existing `dir="ltr"`/`bdi` isolation around amounts, including currency, sign, grouping and decimal separators. This example specifies direction, not a new number format: keep the existing locale's digits, precision and currency labels. Do not reverse strings, change financial formatting, or force the whole page left-to-right. Capture positive, negative and decimal amounts in transaction rows and the open dialog/sheet; report missing isolation as an app issue rather than introducing per-theme markup.

## Acceptance checklist and sign-off

- [ ] Validator passes; generated files are current (`python tools/build_themes.py --check`).
- [ ] Requested mode is recorded; Both supplies two independently validated and captured manifests.
- [ ] WCAG AA: body text, labels, numbers and chip text ≥4.5:1; meaningful borders, chip indicators and focus rings ≥3:1; primary text on ground ≥7:1, including actual financial colours on proposed surfaces.
- [ ] No layout, font, spacing, radius, border width, target size, wording or route changes. No additional page HTML.
- [ ] Every screen in the roster captured on PC/phone, English/Arabic and every requested mode; long labels and large balances remain readable.
- [ ] Arabic layout/text mirror while complete amounts remain LTR, with existing digits, signs, separators, precision and currency labels preserved.
- [ ] Switching preserves scroll, current page, open dialog and an unsaved form. Reload and a fresh launch restore the theme before content paints.
- [ ] Invalid/stale saved ID returns to default. Blocked storage still allows a session switch. Reset means selecting Lightning default.
- [ ] Keyboard, screen reader labels, forced colours and reduced motion checked; every motion stops on a still frame under reduced motion.
- [ ] Windows WebView2 and Android wrapper checked on devices, offline after installation.
- [ ] Creator licence and maintainer review recorded. Preview status does not authorize marketplace sale.

Reviewer / date / app version / theme version / evidence links / remaining issues:

## Runtime contract for maintainers

Both existing PC and phone shells load the bundled registry and parser-blocking runtime before their body. CSS loads before content; generated root attribute rules follow the layout stylesheets. No asynchronous theme fetch is involved. `LightningTheme.set('your-theme')` updates only `document.documentElement.dataset.theme`; `LightningTheme.list()` lists registered themes. A `lightning:themechange` window event reports `{id, saved}` for future canvas renderers; read the new computed tokens and redraw on this event. Unknown IDs resolve to `lightning-default`.

In the app, `/settings/theme` saves the allowlisted choice as the profile preference `appearance_theme`, through the existing session and write guards. The server puts it in a head meta tag, which takes precedence over browser storage, so native launches with a new loopback port and profile changes restore correctly. This preference travels with the profile settings; it grants no ownership. The workbench uses only `lightning_theme` localStorage per browser origin/device. Storage failure still permits an in-memory switch; profile-save failures are reported in Settings. Other tabs on the same origin follow storage updates. This is not account sync or an entitlement check. Only free/default and explicitly labelled bundled previews are registered; paid versions must use verified ownership before they can enter the registry. After a generated asset changes, bump the theme asset query versions in the shells. Switching cost depends on device and page complexity; there is no guaranteed 16 ms repaint.
