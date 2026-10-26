# Lightning

Personal finance in one place: accounts, money in and out, transfers, budgets,
investments, cash reserves, and owned wealth. Historical wealth analysis and a dated cash outlook are planned.

## Licence

Lightning is **source-available**, not open source. It is free for personal and other non-commercial use
under the [PolyForm Noncommercial License 1.0.0](LICENSE): you may read, run and change it for yourself.
Commercial use needs the owner's written permission: ask in a
[GitHub issue](https://github.com/elfekimuhammed/Lightning/issues). To change it together, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Source code, desktop app and private data

This GitHub repository contains the **source code** (`lightning/`), tests (`tests/`),
desktop build instructions (`packaging/` and `.github/workflows/`),
and the desktop design and status in [Architecture](docs/ARCHITECTURE.md#desktop-app-and-encrypted-profiles). It does not contain
anyone's financial databases, passwords, recovery keys or installed app.

The source version is **v1.4.4**. The [PC and phone app workflow](https://github.com/elfekimuhammed/Lightning/actions/workflows/desktop-probe.yml)
builds the tested Windows ZIP and matching signed Android APK from one commit (Architecture › Build
and release). A manual run offers both as seven-day artifacts (GitHub sign-in required). A successful
tag publishes both in [Lightning-downloads](https://github.com/elfekimuhammed/Lightning-downloads/releases). The tested [Version 1.1 beta 1 release](https://github.com/elfekimuhammed/Lightning-downloads/releases/tag/v1.1.0-beta.1)
has the Windows ZIP, signed Android APK, checksums and shared build record.
Extract the Windows ZIP into a new folder and launch `Lightning.exe`; no Python installation is
needed, but Microsoft Edge WebView2 Runtime is required.

The desktop preview asks for a profile password and provides a recovery key.
Its encrypted profile databases and backups live under the user's
`Documents/Lightning`, outside the extracted app folder. Close the app before
replacing that entire folder with a newer ZIP; replacing app files does not
replace profile data. Testers may use sample or real data; keep an independent
backup because legacy database import and backup restore in the UI are not finished. Do not sync a live database between running
computers.

On Linux, run `python -m lightning --profiles` from a source checkout for the
same password-protected finance UI in a browser. The original browser workflow
is still available with `python -m lightning`.

## Start the original browser version

**Windows:** double-click `run.bat`. The first run sets everything up (needs Python 3.11+ from
python.org, with "Add python.exe to PATH" ticked). Your browser opens at `http://127.0.0.1:8765`.

**Linux:** launch **Lightning** from the app menu. It starts the local server and keeps a small terminal open; open `http://127.0.0.1:8765` in Firefox and bookmark it. Launching the icon again while Lightning is running reuses the server and opens no new tab. Close the terminal or press Ctrl+C to stop Lightning.

**macOS:** from the project folder, run `./run.sh`.

Options: `python -m lightning --db path\to\file.db --port 9000 --no-browser`

**Try it with sample data:** `python -m lightning --demo` opens Mohab's household (three months of
money in and out, investments, gold, a budget, bills, an emergency fund and a car loan, dated up to
today) at `http://127.0.0.1:8766`. It lives in its own `data/demo.db`, rebuilt on every start, so
your own database is never touched. An empty Lightning also offers it on the welcome page.

## Run the original browser version on another computer (GitHub)

The code lives on GitHub; **your data never does** (`data/` is excluded by `.gitignore`).

```powershell
# on the new computer (needs Git and Python 3.11+)
git clone https://github.com/elfekimuhammed/Lightning.git C:\Code\Lightning
cd C:\Code\Lightning
.\run.bat
```

Get the latest version later with `git pull`. After changing the code on one computer:
`git add .` → `git commit -m "what changed"` → `git push`, then `git pull` on the other.

Each computer keeps its own `data\lightning.db`. If you specify `--db` to use a
different path, do not run the app on two computers against the same database
or sync the live file while the app is running.

## Data in the original browser version

- Everything lives in one file: `data/lightning.db`. Copy it to back it up.
- A backup is made automatically every time the app starts (`data/backups/`, newest 30 kept).
- The app only listens on your own computer (`127.0.0.1`), never on the network.
- Open the file with any SQLite browser: the `v_ledger` and `v_balances` views are readable as-is.

## Using it

1. **Add your accounts** with today's balances.
2. Open an account and type transactions straight into its register (Counterparty · Category · Amount).
3. To import a statement, open the relevant **account** and choose **Import CSV**. Use `Date`, `Counterparty`,
   and signed `Amount` columns (negative = spending); `Category`, `Notes`, and `Reference` are optional. Review
   the preview to map aliases and categories before confirming—the app does not post until you confirm.
4. **Overview** shows today's position and recent activity. The reports under it (Budget, Investments, Expense analysis, Cash planning) explain cash, investments, reserves,
   income, and spending. **Budget** shows the monthly spending plan and its remaining limit.

Global search finds accounts, investments, categories, and counterparties. Search transactions from the account register (or the all-accounts register) using its filters and search field.

## For developers

Want to help? [CONTRIBUTING.md](CONTRIBUTING.md): pick a good first issue, comment `/take`, open it in Codespaces.

```
pip install -r requirements-dev.txt
python -m pytest          # 100+ tests incl. randomized net-worth reconciliation
lint-imports              # architecture contracts
```

- [NOW.md](NOW.md) — the hand-off between the AIs: claimed work, messages, what is next
- [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — start here: what Lightning is, what it answers, the roadmap
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — structure, rules, data model
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — what every term and code means
- [guideline/](guideline/) — the brand guideline (3.26), four documents: `app.html` (Part A, the app on a PC), `website.html` (Part B, Normal: the website), `phone.html` (Part C), `coders.html` (Part D, Coders: the website's For Geeks pages); open one in a browser (AIs: `python tools/guideline.py A03` prints one section)
- [CHANGELOG.md](CHANGELOG.md) — every change, every time
