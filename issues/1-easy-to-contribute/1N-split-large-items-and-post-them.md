---
title: Split the large items into steps and post every contributor-safe step on GitHub with its coins
type: tech
pillar: build
size: M
status: ready
created: 2026-10-31
by: Claude Sonnet 5.5
---
## Report
Only 4 of the 72 open items have a GitHub issue. `python tools/issues.py --check` now warns about every size L item that has no steps (29 today). Owner decision, 2026-10-31: big features are cut into smaller steps, and every step that outside contributors can safely take is posted with a coin label (S 200, M 500, L 800 or more).

## Fix
1. Split each warned L item into `## <code>1`, `<code>2` … steps, each a size S or M, in the item file (investments 5A-5E and 5G, the journal and devices 4A and 4B, price packs 6A, PC and phone declutter, import 7B-7D, and the rest of the `--check` list).
2. Add `python tools/issues.py github` (dry run by default): for each open step or item that is not an owner task, not security- or restore-sensitive and not claimed in `NOW.md`, create or update a GitHub issue titled `[BT-5J] …` with labels `pillar:*`, `kind:*`, `coins:<n>` and, for a step, a sub-issue of its parent; write the number back as `github:` in the front matter.
3. The owner approves the list and the coin amounts before anything is posted; it is public and cannot be fully taken back.
4. Keep the existing `rewards.yml` offer flow (a `coins:<n>` label publishes the offer).
