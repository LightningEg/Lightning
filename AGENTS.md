# Lightning: rules for every AI here

Codex, Luna and Claude sessions cannot talk to each other: **the repository is the only channel.** What is not written below and pushed does not exist for the next AI.

## 1. Files that carry the project

Each fact lives in one file; link to it, never copy it. No other files under `docs/`.

| File | Holds | Update when |
|---|---|---|
| [NOW.md](NOW.md) | Hand-off: claims, messages, next steps (each with a **Read:** line) | You claim/finish long work, message another AI, or change what's next |
| [Project Overview](docs/PROJECT_OVERVIEW.md) | Product, owner decisions, screen questions, Mohab, UX plan, gaps, roadmap | The owner decides, or the product/plan changes |
| [Architecture](docs/ARCHITECTURE.md) | Modules, financial rules, data model, UI contract, desktop app, encrypted profiles | How something is built or calculated changes |
| [Glossary](docs/GLOSSARY.md) | One name and meaning per term and figure | You add or rename one |
| [Competition](docs/COMPETITION.md) | Competitors, what users love/hate, where we win/lose | You learn something, or choose between designs |
| [guideline/](guideline/) | Brand: [app.html](guideline/app.html) (A, PC), [website.html](guideline/website.html) (B), [phone.html](guideline/phone.html) (C), [brand-voice.md](guideline/brand-voice.md) (voice) | The owner gives a new version; change the website repo's copy too |
| [report/](report/README.md) | Findings not yet fixed: bugs and improvements, visual or technical; read `report/INDEX.md` only | You find something (add one); you fix it (delete it in the same commit) |
| [CHANGELOG.md](CHANGELOG.md) | Every change, newest first under `Unreleased` | Every push |
| `docs/proposals/` | Unbuilt designs, one file each | Once built, move what holds into Architecture and delete it |

**The brand guideline is strict.** CSS that differs from it is wrong. Missing a rule? Use the closest one and ask the owner in a GitHub issue; never invent a style. On a phone Part C wins over Part A, and never reuse the PC layout.

**Before it ships (guideline A16).** A screen with any of these is not done: All caps: Anywhere. · Coloured headers: Headers are Ink. · A colour off its meaning: Check A03. · Vivid gradient card: Brand only. · KPI by position: Tone by meaning. · Chip by direction: Good or bad. · Decimals on big figures: Whole EGP. · "L1 › L2": Header, then list. · Five or more names: Four, then Other. · White or boxed fields: Soft wells. · Dropdown for your data: Type and pick. · Card in a card: Never. · A line that repeats its label: Cut it. `tests/test_docs_structure.py` keeps this list the same as the guideline's.

## 2. Spend tokens like they are yours

Never at the cost of a test, a required check, or a read you need.

- **Start:** `NOW.md` + `git log --oneline -15`. A *Next* item's **Read:** line names the rest.
- **Read sections, not files:** `grep -n '^## ' <file>`, then read that range. Guideline: never open whole; `python tools/guideline.py` lists sections, `python tools/guideline.py A12` prints one.
- **Grep before reading.** Don't re-read what you just edited or read code you aren't changing.
- **Skip unless needed:** `CHANGELOG-archive.md` (0.5.0b1 and older), `docs/proposals/`, `Claude outputs/`, the Glossary's figures table.
- **Tests:** changed areas with `-q`, failures only; full suite once before pushing: `-n auto --dist loadfile`.
- **Write short:** changelog entry ≤ 3 lines; `NOW.md` < 4,500 bytes.
- **CI minutes cost money** (2,000/month, Windows ×2): pushes run Linux only; run Windows/Android workflows by hand only when your change needs that evidence now. Push finished steps, not every edit.
- **The owner reviews milestones, not steps:** ask for a phone/PC check only when a milestone works end to end.
- **Tell the owner only what helps:** results, decisions, actions, real risks. No narration.

## 3. Every task

1. **Start fresh:** `git pull` on `main`, create your branch (§6), read per §2.
2. **Claim** work longer than one sitting in `NOW.md` *Claimed* and push that first. Stay out of others' claimed files.
3. **Small finished steps:** commit and push each once its tests pass.
4. **Test.** For visible changes also run Mohab (`tests/test_mohab_year.py`) and check A16.
5. **Record:** changelog entry atop `Unreleased` (`2026-10-03 · Claude:` / `· Codex:`, date from `date`); update the §1 files you touched.
6. **Check claims:** `python tools/claims.py --me <Claude|Codex|Luna>` lists changed files someone else claimed; leave them or ask the owner.
7. **Hand off:** update/remove your claim, drop finished *Next* items, add new ones with **Read:**. Messages only for what your commit doesn't say; owner questions as GitHub issues. Push.

- **Claims and messages belong to their author.** Never edit another AI's, except deleting a message to you once handled (to all: keep seven days). Make each claim's *Work* distinguish parallel sessions. A helper (Codex's Luna) gets its own rows, written by its AI.
- **Push rejected?** `git pull --rebase`, keep both sides in changelog and `NOW.md`, retest, push.
- **Findings:** every bug or improvement found goes in `report/` (one file each, front matter says who, which skills, which version); fixing it deletes the file. Read `report/INDEX.md` before anything else there.
- **Skills:** `skills/README.md` lists them: feedback-review, bug-hunt, number-audit, guideline-audit, arabic-check, perf-check, stale-check, release-check, website-sync. Read the one that fits and follow it.
- **Never undo another AI's work** without the owner; disagree in a GitHub issue for the owner.

## 4. Product rules

- Local-first personal finance for salaried people in Egypt. One ledger records real money; plans move none; reports read both.
- Financial calculations live in Python services, never templates or JavaScript.
- Ships mainly as a Windows app (WebView2, encrypted profiles): no Back, address bar or tabs, so every page has its own way forward and back. Linux `--profiles` shares the pages; `python -m lightning` is separate legacy mode.
- Profile data and backups live in Documents/Lightning, never in Git or the ZIP. Dummy data only until ordinary-PC acceptance, legacy import and backup restore are done.

## 5. Mohab's test is acceptance

`tests/test_mohab_year.py`: a 31-year-old salaried Cairo user lives a year through the screens. Its docstring says what it checks; read only that. A wrong screen is a strict `known_gap`; when fixed, remove the marker and update the Overview. User feedback becomes Mohab steps.

## 6. Git and ownership of merges (owner rule; overrides any session default)

- **Only @elfekimuhammed merges into `main`.** No AI agent (Codex, Claude, Luna or other), bot, internal developer, or external contributor may merge a PR, push directly to `main`, or bypass branch rules. This remains true if GitHub credentials technically allow it. Green tests or an AI recommendation do not authorize a merge.
- **Always use a pull request, including for AI-authored and documentation changes.** Work on one descriptive `who/feature` branch per change (for example, `claude/arabic-type-and-numbers` or `codex/restore-safety`). Internal collaborators may branch in the repo; outside contributors work in forks. Never use a random suffix or vague branch name.
- Push tested steps to your **feature branch only**. Before requesting review, update the branch from `main`, rerun relevant tests, open/update a PR to `main`, and report the PR URL, test results, outstanding risks, and any owner decision needed. **Stop before merging**; the owner performs the final merge.
- **Review:** CI results and independent AI analysis are evidence, not approval. AI agents may inspect diffs and submit review comments; they must not approve on behalf of the owner. The owner decides product fit and approves the merge. High-risk changes (ledger/financial calculations, migrations, encrypted profiles, sync, authentication, release signing) require explicit risk and regression-test notes.
- **Code ownership:** `.github/CODEOWNERS` on `main` must keep `@elfekimuhammed` as the sole owner of all paths, including `.github/CODEOWNERS` itself, unless the owner explicitly orders otherwise. No agent may add itself or collaborators as code owners or change branch rules, bypass exceptions, token privileges, workflow publishing permissions, or release controls without an explicit owner instruction. Any authorized change still goes through a PR.
- **Untrusted PRs:** do not expose credentials, signing keys, publish tokens, or production data to fork PR code. Flag workflows that would run untrusted code with elevated permissions; never enable such execution as a shortcut.
