---
name: post-contributor-issues
description: Choose which plan items and steps are ready for outside contributors, post them as GitHub issues with coin labels (which also puts them on the website's Tasks board), and record the issue numbers back in the plan. Use when asked to post, publish or add issues for contributors, or when python tools/issues.py github lists candidates.
---

# Post contributor issues

Tool-neutral. Posting is public, and a `coins:<n>` label also publishes the issue as an offer on the website's For Geeks Tasks board (the rewards workflow writes it to `public.reward_offers`; checked on 2026-10-31: 19 of 19 new issues became offers). Do not post what you would not want a stranger to take.

## Is it ready? (all must be yes)

1. Understood: status `ready` (not `new`, `blocked` or `building`).
2. Unclaimed: not in `NOW.md` Claimed, not under a person's `/take`, and not inside code another AI is changing.
3. Self-contained: one pull request proves it, with a done-when a reviewer can run or read.
4. No owner action: not an owner task, no key, deploy, account or decision needed first.
5. No hidden dependency: if it needs another step, the text says `Needs <step> merged first` (the tool holds it) or only the first step of a chain is posted.
6. Still true: reproduce or grep it; a stale or deferred item (owner said "later") stays off. Sensitive items (security, restore, payments) carry `post: no`.

## Steps

1. `git pull`, then `python tools/issues.py github`: a dry run that lists what would be posted, with sizes and coins, and what is held and why. It sends nothing.
2. **Read every body** it would send (`issue_text` in `tools/issues.py`): links absolute, context present, no private data, a done-when. Fix the item file, not the issue.
3. **Hold what fails** the test: add `post: no` to its front matter and a last line `**Not posted to contributors (<date>):** <reason>.`
4. **Coins** follow size (S 200, M 500, L 800). Raise with `coins: 800` in the item's front matter (a multiple of 100, never below the size's) for work that is risky, needs a device, or is money logic.
5. **Owner approval** for the list unless the owner has already named the groups. State the count and total coins first.
6. **Post** each with the GitHub issue tool: title `[BT-5J] ...`, the generated body, labels `coins:<n>`, `pillar:<p>`, `kind:<k>` (and `good first issue` for S). Independent issues can go in one batch.
7. **Write the numbers back:** `github: <n>` in the front matter of an item with no steps; ` · #<n>` at the end of each step heading. `python tools/issues.py` and `python tools/status.py`; the dry run no longer lists them.
8. Commit with the trailers, open the pull request, merge when CI is green (skill `ship-pr`).

Item 1N stays open until every contributor-safe item is posted.
