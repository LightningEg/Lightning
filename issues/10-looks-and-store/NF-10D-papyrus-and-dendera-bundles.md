---
was: 8T
title: Papyrus and Dendera bundles need a banner, frame and name designed first
type: feature
pillar: feel
size: M
model: opus
status: ready
post: no
created: 2026-10-27
by: Claude
repo: website
---

## Report

The cart offers the cheaper set (8N), and Nile, Dusk and Cotton have one. Papyrus and Dendera have none: the catalogue has no matching banner, frame or name for either, so there is nothing to bundle. See the store and community audit: `issues/10-looks-and-store/r13-store-and-community/report.md` (B1).

2026-11-08, checked: still true as far as this repository shows. `guideline/themes.md` §7 lists no Papyrus or Dendera banner, frame or name on sale (banners: Halo, Blueprint, Dusk, Circuit, Dunes, Borealis, Drifting stars, Nile at night, Felucca, Sand wind; frames: Halo, Nile, Gold, Double; names: Gold, Nile, Sunset, Shimmer). The catalogue (`catalog_items`) and the sets (`set_parts`) live only in the website repository (LightningEg/Lightning_website, built by its PR #111 for 8N and #115 for 8S), which was not reachable from this session: the website step below starts with a `Verify first:` that names the files there.

## Decided

- 2026-11-08, owner (10D1): option 1, new matching pieces: Papyrus "Gold thread" banner, "Gold foil" frame, "Papyrus gold" name (set 1,320); Dendera "Zodiac ceiling" banner, "Lotus" frame, "Pigment blue" name (set 1,280); §7's set price line is updated with them. Still open: which set the cart suggests first when a buyer owns neither (default until asked: Papyrus, the cheaper theme's set).

## Fix

The owner approves one banner, one frame and one name colour per theme (10D1), drawn to `guideline/themes.md` §7's texture and motion rules; then one website pull request adds them and the two sets (10D2). A look never changes a number or a rank.

## How to work on this item

Each step is one pull request in the **website** repository (`LightningEg/Lightning_website`; add it to the session first). Read only the files a step names; read `guideline/themes.md` §7 by range (`grep -n '^## ' guideline/themes.md`), never the guideline HTML whole. Run the step's test commands; delete the step's heading here in the same session (a small app-repo PR, or the owner's next plan PR).

## 10D2 Add the pieces and the two sets to the catalogue · M · opus
Needs 10D1 merged first.
Verify first: in the website repository, `grep -rln "set_parts" supabase/migrations` names the migration that created sets (8N) and `grep -rn "Cotton" supabase/migrations/*.sql | grep -i set` its Cotton set rows; `grep -rn "Nile at night\|'Gold'" js css | head` shows where a banner, frame and name are drawn. If Papyrus or Dendera sets already exist, delete this step.
Files (website repository): a new `supabase/migrations/<timestamp>_papyrus_and_dendera_sets.sql` (copy the shape of the Cotton set rows: `catalog_items` rows for each new banner, frame and name with type, tier and the §7 price, then the set's `catalog_items` row and its `set_parts` rows); the banner and frame drawings where the existing ones live (from the grep above; drawn by code from the theme's colours, no image files, per §7 texture rules); `guideline/themes.md` §7 tables in both repositories (`cmp` must pass, AGENTS.md §1).
Do: follow skill `supabase-migration` for the migration (the owner runs it on the live project). Add the pieces chosen in 10D1, at their tier prices, each with reduced-motion still frames; add one set per theme whose parts are the theme and its three pieces, priced by the existing 80% rule (do not hard-code a set price if the 8N code computes it). Nothing a look draws may sit on a figure or change a rank.
Done when: in the website repository every `supabase/tests/*.test.mjs` passes (`node --test supabase/tests/`), with a new case in the sets test that a buyer owning Papyrus is offered the Papyrus set at 80% of the three pieces, and `python tools/theme_contrast.py` passes; in this repository `python -m pytest tests/test_docs_structure.py -q` passes with the sibling repo present.
