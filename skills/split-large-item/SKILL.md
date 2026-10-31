---
name: split-large-item
description: Split a size L plan item into sized steps that follow its own plan, with done-when lines and the order between them, so contributors can take one at a time. Use when python tools/issues.py --check warns that an item is size L with no steps, or when an item has grown past one sitting.
---

# Split a large item

Tool-neutral. `python tools/issues.py --check` warns `size L with no steps`. A step is what one person can finish and one pull request can prove.

## Steps

1. **Read the item's own plan** (its `## Fix`, build order, phases or numbered list). Steps follow that plan; do not invent a new one. For a long design, find the plan section: `grep -n '^## ' <file>`.
2. **One heading per step**, appended at the end of the item file:

```
## 5A1 The events table and the one validator · L
What to build, in a line or two. Done when: <what a reviewer can run or read to say it is finished>.
```

   The code is the item's code plus a number (`5A1`, `5A2` ...). The size after ` · ` is `S`, `M`, `L` or `owner` (a step only the owner can do, with no coins). Once posted, ` · #123` follows.
3. **Size by the work**, not by the item: S a small self-contained fix (200 coins), M a change across a few files with tests (500), L money logic or a feature (800 or more). A step that is still bigger than one pull request is split again.
4. **Order.** If a step needs another, say so in the step's text in exactly this form: `Needs 5A1 merged first.` or `Needs 7D3 to 7D5 merged first.` The posting tool holds the step until the steps it names are finished (their headings deleted).
5. **Overlap.** If the item overlaps work already built or in progress (another item, an audit), start the step with `Verify first:` and say what to reproduce, and delete the step with the fixing commit's name if it is already fixed.
6. **Do not split work another AI is building** without asking: check `NOW.md` Claimed. Steps may mirror their claim; they must not redirect it.
7. **Finishing a step** deletes its heading and says so in the commit; the item's own `done:` entry waits for the last step.
8. `python tools/issues.py` (INDEX), `python tools/status.py`, `python -m pytest tests/test_issues.py -q`. Then `python tools/issues.py github` shows what the split makes postable (skill `post-contributor-issues`).
