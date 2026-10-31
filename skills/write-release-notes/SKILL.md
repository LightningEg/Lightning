---
name: write-release-notes
description: Write the Release-note and Detail trailers that end every commit, and cut, preview and check the release notes they produce (RELEASES.md for people, ai/changelog/ for AI sessions). Use when committing a change, when CI's release-notes check fails, or when cutting a version.
---

# Write release notes

Tool-neutral. There is no shared changelog file. Each commit ends with two trailers; tools build `RELEASES.md` (plain words, for people) and `ai/changelog/<version>.md` (detail, for AI sessions) from them.

## The two trailers

```
Release-note: own: Converting EGP to dollars asks first when the rate looks wrong.
Detail: BT-5J. Convert refuses a rate 20% off the market unless pressed twice; routes/accounts.py save_conversion; test_convert.
```

- **Release-note**: one sentence a user would understand, prefixed with the pillar (`capture plan understand own protect everywhere feel build reach`). No item codes, file names or jargon. Say what is different for the person. `Release-note: none` for a change nobody would notice (tests, plan, docs).
- **Detail**: one line an AI needs to continue: what changed, where, why, the item code.
- Any commit in the pull request may carry them; the squash keeps every commit's trailers. CI (`python tools/release_notes.py check-pr origin/main`) needs at least one of each and a valid pillar. A fork's contributor is not asked: the maintainer writes them at merge.

## Tools

- `python tools/release_notes.py recent`: what is unreleased since the last tag (or `--from <ref>`).
- `python tools/release_notes.py`: rewrite `RELEASES.md` from `ai/changelog/*.md`; `--check` fails if it is stale.
- `python tools/release_notes.py cut 1.5.5 --from <last release commit>`: writes `ai/changelog/1.5.5.md` from the trailers (and the migrations added since), rebuilds `RELEASES.md`. Read the notes once; fix a bad sentence in the version file, then run the tool with no arguments.
- Never hand-edit `RELEASES.md`. A released version's file is never rewritten.
- `ai/changelog/UNRELEASED.md` holds entries written before trailers existed; the next `cut` takes them in.

Arabic release notes do not exist yet; the website shows English until one is translated.
