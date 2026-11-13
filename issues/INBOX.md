# Inbox

Things seen, not yet planned. One line each: date, pillar, what and where (a page, a file, a test). Rules:
[AGENTS.md](../AGENTS.md) section 3.

- A line costs nothing and promises nothing. It becomes an item only when someone starts it or the owner picks it.
- Fixed in the same sitting? Fix it and delete the line; it never needs an item.
- Wrong money or lost data is never a line: it gets an item at once.
- Lines older than 30 days that nobody picked are deleted in the next plan sweep.

## Lines
- **C2 (from IV-3AM, 2026-11-12):** Cash planning's *What you owe* card stands alone in its row with one loan; pair it or make it a row (IV-12Q gave the unfinished Budget and Cash pages their pattern but left this page alone). Report: r19 C2.
- **Rose on dark cards (from NF-10C3, 2026-11-12):** the app's rose `#C93D72` (`--rose`, `--neg`) reads about 3.8:1 on every dark theme card; give it a `--theme-rose` the way `--theme-positive` and `--theme-held` are made in `tools/build_themes.py`.
- **Popup fields at 15px on the phone (Add sheet review, 2026-11-12, capture):** inside the phone's sheets (outside `.main`) Who, Date, Notes and the account select are 15px, not the 16px C05.1 asks for so the phone does not zoom; the `.main`-scoped field rule in phone.css never reaches them.
- **Phone themes repaint every frame (feel, 2026-11-13, phone smoothness check):** Papyrus and Dendera (and Dendera night, same recipe) never let the phone rest: the header's endless `m-thread` / `m-pigment` animations move `background-position` on the sticky `.phone-appbar`, so it is restyled, repainted and rasterised on every frame, even while idle (150 raster tasks per 2.5 s against none on Default, Cotton, Nile, Royal; about 3.5x the idle CPU at a 4x slowed CPU), and more frames drop while scrolling; Papyrus adds `backdrop-filter: blur(14px)` on that sticky bar (`theme-materials.css` header recipes). Fix after PR #611 lands (same file). Owner picked (2026-11-13): same look, cheap motion: draw each moving light on its own layer moved by `transform` (compositor only), and decide the blur from a real-phone measurement.
