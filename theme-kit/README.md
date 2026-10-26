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

The app supports palettes plus the approved decoration in `slots.json`: `pattern` and `motion` are `none` or a name on its `patterns` and `motions` lists (drawn by `theme-decor.css`), and hero `decoration` stays `none`. A new texture or motion needs a separately reviewed app implementation before acceptance; arbitrary CSS, scripts, SVG fragments and remote URLs cannot be imported. Do not promise a textured release using this template alone.

## Create and validate

1. Copy `theme.template.json` to `your-theme.json`, change its ID/name, and edit `parts.palette`. The sample is a complete valid dark palette. Keep the metadata fields, including `status: test-preview` and a null price; release and pricing are handled by Lightning.
2. Fill the eleven compartments from `slots.json`. Each paint value outside the palette is a **palette key**, for example `cards.surface: "raised"`, not a hex colour. All palette colours are six-digit hex. Omitted part properties inherit the free default; prefer complete delivery so the intended result is explicit.
3. Keep money meanings: Green in, Rose out and Azure held. Current app adapters leave financial tokens and financial series unchanged. The manifest's income/expense/transfer/warning fields are reserved; they do not recolour money. Check those existing colours against every proposed surface.
4. From the repository root, run `python tools/build_themes.py --validate theme-kit/your-theme.json`. This checks schema, allowed values and key text/control contrast combinations. It does not establish that every real screen is accessible.
5. For integration, the Lightning maintainer copies the reviewed JSON into `lightning/ui/static/cosmetics/` and runs `python tools/build_themes.py`. Commit all generated files. No HTML, layout or app logic should need changing for a palette.
6. Launch the app normally, open Settings → Appearance and choose the new preview on PC and phone. `theme-kit/preview.html` is a static component workbench; serve the repository root with `python -m http.server 8765`, then open `http://localhost:8765/theme-kit/preview.html`. It uses the same generated tokens and switcher. Inspect actual app screens before signing off.

## Eleven compartments

| Part | Creator supplies | Fixed by the application |
|---|---|---|
| Palette | Background, text, quiet text, surfaces, accent, focus | Money meanings and financial series |
| Brand | `on-light` or `on-dark` | Approved mark and dimensions |
| Header | Surface and seam colour references | Height, controls, labels |
| Navigation | Surface and active mark references | Routes, order, targets |
| Hero | Surface and edge references; decoration `none` | Amounts and placement |
| Cards | Surface and border references | Border width, padding, radii |
| Charts | Grid and nonfinancial accent references | Financial series, axes, labels |
| Controls | Fill, label and focus references | Behaviour, sizes, validation |
| Overlays | Surface and backdrop references | Focus containment and stacking |
| Menus | Surface and divider references | Contents and keyboard access |
| Decoration | Pattern and motion: `none` or an approved name from `slots.json` | What the pattern and motion draw (`theme-decor.css`) |

The compiler exposes `--theme-chart-grid` and `--theme-chart-accent` for nonfinancial chart components. Existing financial charts keep their series. New components must consume their compartment variables; never add per-theme markup.

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
- [ ] Keyboard, screen reader labels, forced colours and reduced motion checked; no decorative animation.
- [ ] Windows WebView2 and Android wrapper checked on devices, offline after installation.
- [ ] Creator licence and maintainer review recorded. Preview status does not authorize marketplace sale.

Reviewer / date / app version / theme version / evidence links / remaining issues:

## Runtime contract for maintainers

Both existing PC and phone shells load the bundled registry and parser-blocking runtime before their body. CSS loads before content; generated root attribute rules follow the layout stylesheets. No asynchronous theme fetch is involved. `LightningTheme.set('your-theme')` updates only `document.documentElement.dataset.theme`; `LightningTheme.list()` lists registered themes. A `lightning:themechange` window event reports `{id, saved}` for future canvas renderers; read the new computed tokens and redraw on this event. Unknown IDs resolve to `lightning-default`.

In the app, `/settings/theme` saves the allowlisted choice as the profile preference `appearance_theme`, through the existing session and write guards. The server puts it in a head meta tag, which takes precedence over browser storage, so native launches with a new loopback port and profile changes restore correctly. This preference travels with the profile settings; it grants no ownership. The workbench uses only `lightning_theme` localStorage per browser origin/device. Storage failure still permits an in-memory switch; profile-save failures are reported in Settings. Other tabs on the same origin follow storage updates. This is not account sync or an entitlement check. Only free/default and explicitly labelled bundled previews are registered; paid versions must use verified ownership before they can enter the registry. After a generated asset changes, bump the theme asset query versions in the shells. Switching cost depends on device and page complexity; there is no guaranteed 16 ms repaint.
