# Dendera audit: why it does not feel animated, and how to make it premium

Date: 2026-11-02 · Author/reviewer: Claude (owner-requested audit)
Repository: app · Reviewed commit: 3d5f26577ec4c4041a4670525ccabf208aa9d6be

## Scope and method

The owner reported that the animated themes do not animate and asked for a full audit of Dendera (day and night,
animated tier, 1,000 coins): what is broken, and how to make it better and more premium.

- **Promise:** `guideline/themes.md` §7 (animated tier: one slow signature motion and motions that answer you),
  `theme-kit/plans/dendera.html`, `lightning/ui/static/cosmetics/dendera*.json`.
- **Screens:** `tools/theme_shots.py` (PC and phone, English and Arabic, day; Lightning default beside it), plus a
  probe for night mode, which `theme_shots.py` cannot reach (F9). Sample data only.
- **Motion:** each declared motion was checked for changed pixels over time in Chromium with motion on
  (`evidence/motion_probe.py`). Then the code was read to find why.
- **Not checked:** WebView2 and Android devices, forced colours, the website's Dendera (only the app was audited).

## Findings

### Broken: the motions that were promised did not paint (fixed in this branch)

| ID | Severity | Observation and expected behaviour | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | **Dendera's signature motion never showed.** The pigment thread (four-pigment seam under the header, one light travelling it every 14 s) used `var(--hero)` and `var(--warning)`. No stylesheet defines either, so the browser dropped the whole background. The animation ran on an empty layer. Day and night were both affected. | `evidence/seam-before-fix.png`, `seam-after-fix.png`; probe: 1 distinct frame in 15 s before the fix, 3 in 8 s after | Fixed: the build emits `--m-pigment-hero` and `--m-pigment-warning` from the palette; test `test_material_layer_names_only_defined_colours` |
| F2 | medium | **The card pointer light never showed (Dendera and Papyrus).** The cards' finish rule outranks the hover rule, so `--lt-x/--lt-y` were set but the light layer never won. | probe `hover_light` false → true | Fixed in `theme-materials.css` (the import review keeps its plain paint) |
| F3 | medium | **The button press sheen did nothing on Dendera day.** The sheen moves the background position, but satin's light is a vertical gradient at full size, so moving it changes nothing. | probe `press_sheen` `0px 0px` → moving | Fixed: on satin the sheen is its own band |
| F4 | medium | **Papyrus's gold edge glint was frozen** (same family; found while answering the owner). `--m-foil-ring` was declared on `html`, so its `var(--m-glint)` resolved there once and never followed the animation on the card. | probe `hero_edge_moves` false → true | Fixed: the ring is declared on each element that wears it |

All four fixes were rechecked with `tools/theme_check.py --themes dendera,dendera-night,papyrus`: 0 elements moved on
any roster screen and 0 frames over 34 ms. Reduced motion still stops each one.

### Why it still will not feel premium (open)

| ID | Severity | Observation | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F5 | high | **The signature motion is too small to notice.** Fixed, it is a 1 px line, and the travelling light is 30% gold mixed into white. On day papyrus that is nearly the ground's own colour, and the light is in view only about a third of each 14 s cycle (the 300% gradient travels 150%). A buyer paying for the animated tier sees nothing move on a still screen. | `seam-after-fix.png` | 10F1 |
| F6 | medium | **The lotus frieze reads as a dotted line.** At 16.8 × 7 px (PC) and 12 × 5 px (phone), the buds become coloured dots. Temple friezes read because they are banded: a register line above and below, with alternating bud and flower. | `day-pc-overview.png` (under the title) | 10F2 |
| F7 | medium | **The hero carries two watermarks.** Lightning's own mark (7%, blue and green, every theme) sits bottom right and Dendera's winged disc bottom left. The winged disc is barely visible, and the blue-green mark is off-palette on papyrus. In Egyptian use the winged sun sits over the doorway lintel, across the top. | `day-pc-overview.png`, `night-pc-overview.png` | 10F3 |
| F8 | medium | **Charts do not wear the theme.** `charts.grid` and `charts.accent` are generated as `--theme-chart-grid/--theme-chart-accent`, but nothing reads them, so in every theme the net-worth line is the default azure with a cool grey fill. On papyrus it looks pasted in. Only nonfinancial lines and fills would change; money colours stay. | `day-pc-overview.png`, `night-pc-overview.png` | 10F4 |
| F9 | medium | **Night: the "gold-leaf" tabs are lavender, and the hero is a mesh.** The plan sells "night gold-leaf tabs", but the foil finish is drawn from the accent (`#8FA8F2`), so the chosen tab and primary button are lavender-blue. The night hero's `fibre` grain reads as a woven screen behind the figure. The star ceiling is barely visible. | `night-pc-overview.png`, `night-pc-transactions.png` | 10F5 |
| F10 | low | **Phone: shadows are heavy, and the zodiac ring sits under the Latest list.** Cards at depth `mid` look puffy at 360 px, and the ring (320 px) sits behind rows of text ("never under a reading", themes.md §6). | `day-phone-overview.png` | 10F6 |
| F11 | low | **Night can only follow the computer.** Settings offers "Follows this computer's light or dark setting". A buyer cannot choose Dendera night on a light-mode PC, although they paid for two modes. | Settings › Appearance | 10F7 (owner decides) |
| F12 | low | **The checks could not see this.** `theme_check.py` measures geometry and frame time, not whether a motion paints, which is how F1-F4 shipped. `theme_shots.py --themes dendera-night` stops ("did not take") because night is reached only through the follow-night switch. | this audit | 10F8 |

### What is already good

The palette is warm and readable, and contrast passes at every worst point. Nothing moves the layout (0 elements moved
on 12 screens). The papyrus ground, cartouche navigation, satin cards and dialog rise all work. The equip sweep plays
once, and reduced motion is honoured everywhere.

## How to make it premium (proposal, for the owner)

Within the guideline's limits (one continuous motion of 8 s or more, nothing on a number, no layout change), in order
of effect per unit of work:

1. **A signature motion people notice (10F1).** Keep the thread, which is Dendera's own, but make it 2 px of gold
   leaf (the hero pigment, not white). The light should always be somewhere on the bar and carry a soft glow under the
   seam. Same 14 s and same repaint cost (one strip).
2. **A real frieze (10F2).** Alternate lotus bud and open flower between two register lines, at about twice the size
   (it still fits the header's bottom padding).
3. **The winged disc as a lintel (10F3).** Draw it centred across the hero's top edge, faint, and hide Lightning's
   watermark mark on any theme that brings its own hero artwork.
4. **Charts in the theme's ink (10F4).** Wire the existing chart paint, which helps every paid theme.
5. **True gold leaf at night (10F5).** Add a `gold-leaf` finish (foil drawn from the hero pigment). Swap the night
   hero's fibre grain for paper, and lift the star ceiling to a visible strength.
6. **Phone calm (10F6),** **a Night choice (10F7),** and **checks that catch a dead motion (10F8).**

## Validation and limits

- `python -m pytest -q tests/test_theme_build.py tests/test_theme_entitlements.py`: pass.
- `python tools/theme_check.py --themes dendera,dendera-night,papyrus`: passed (geometry and frames).
- `evidence/motion_probe.py`: Dendera thread 3 distinct frames in 8 s, hover light and press sheen move; Papyrus edge,
  hover and press move.
- Headless Chromium on Linux only. WebView2 and Android still need 10C1.

## Dated follow-ups

None yet.
