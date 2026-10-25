# Lightning app theme creator kit

Give this folder, `guideline/themes.md`, the app's `guideline/app.html` and `guideline/phone.html`, and `lightning/ui/static/cosmetics/slots.json` to the external creator. This kit covers PC and phone. A store theme must also supply the website versions described in the guideline.

## Brief to complete before design

- Theme ID (lowercase letters, numbers and hyphens), display name, creator, version and contact:
- Mood and reference images:
- Light or dark ground; four seed colours (ground, text, quiet, accent):
- Requested tier: palette / textured / animated:
- Asset ownership and licence allowing Lightning to distribute it:
- Delivery date and reviewer:

Current app support is palette-only. `pattern`, `motion` and hero `decoration` must be `none`. Textured and animated proposals require a separately reviewed app implementation before acceptance; arbitrary CSS, scripts, SVG fragments and remote URLs cannot be imported. Do not promise a textured release using this template alone.

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
| Decoration | Pattern and motion `none` | App-owned inert decoration hooks |

The compiler exposes `--theme-chart-grid` and `--theme-chart-accent` for nonfinancial chart components. Existing financial charts keep their series. New components must consume their compartment variables; never add per-theme markup.

## Submission package

Return `your-theme.json`, this completed brief, a short rationale for each compartment, licence/credits, and labelled screenshots:

- PC: 1366×768 and 1920×1080; phone: 320, 360 and 390 px wide.
- English and Arabic (RTL) for Overview, Budget, Investments, Accounts and Settings.
- Navigation, hero, table/list, positive/negative/held amounts, input focus, disabled control, validation error, empty state, menu and open dialog.
- Default and new theme in the same position for geometry comparison.

## Acceptance checklist and sign-off

- [ ] Validator passes; generated files are current (`python tools/build_themes.py --check`).
- [ ] Primary text on ground ≥7:1; all ordinary text ≥4.5:1; large text and control/focus indicators ≥3:1, including actual financial colours on proposed surfaces.
- [ ] No layout, font, spacing, radius, border width, target size, wording or route changes. No additional page HTML.
- [ ] Every compartment checked on PC/phone and English/Arabic; long labels and large balances remain readable.
- [ ] Switching preserves scroll, current page, open dialog and an unsaved form. Reload and a fresh launch restore the theme before content paints.
- [ ] Invalid/stale saved ID returns to default. Blocked storage still allows a session switch. Reset means selecting Lightning default.
- [ ] Keyboard, screen reader labels, forced colours and reduced motion checked; no decorative animation.
- [ ] Windows WebView2 and Android wrapper checked on devices, offline after installation.
- [ ] Creator licence and maintainer review recorded. Preview status does not authorize marketplace sale.

Reviewer / date / app version / theme version / evidence links / remaining issues:

## Runtime contract for maintainers

Both existing PC and phone shells load the bundled registry and parser-blocking runtime before their body. CSS loads before content; generated root attribute rules follow the layout stylesheets. No asynchronous theme fetch is involved. `LightningTheme.set('your-theme')` updates only `document.documentElement.dataset.theme`; `LightningTheme.list()` lists registered themes. A `lightning:themechange` window event reports `{id, saved}` for future canvas renderers; read the new computed tokens and redraw on this event. Unknown IDs resolve to `lightning-default`.

In the app, `/settings/theme` saves the allowlisted choice as the profile preference `appearance_theme`, through the existing session and write guards. The server puts it in a head meta tag, which takes precedence over browser storage, so native launches with a new loopback port and profile changes restore correctly. This preference travels with the profile settings; it grants no ownership. The workbench uses only `lightning_theme` localStorage per browser origin/device. Storage failure still permits an in-memory switch; profile-save failures are reported in Settings. Other tabs on the same origin follow storage updates. This is not account sync or an entitlement check. Only free/default and explicitly labelled bundled previews are registered; paid versions must use verified ownership before they can enter the registry. After a generated asset changes, bump the theme asset query versions in the shells. Switching cost depends on device and page complexity; there is no guaranteed 16 ms repaint.
