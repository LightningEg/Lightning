# Contributing

Lightning is a free, local-first money app for salaried people in Egypt. Help is welcome, and it takes three steps.

## 1. Pick an issue

Open the [good first issues](https://github.com/LightningEg/Lightning/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22+no%3Aassignee).
Each one says what's wrong, when it's done and which file to look at. That's all you need to read.

## 2. Comment `/take`

A bot assigns it to you straight away. One issue at a time; `/drop` gives it back. After 14 days without activity it is
freed for someone else.

## 3. Build it and send a pull request

**Fastest, nothing to install:** [open Lightning in Codespaces](https://codespaces.new/LightningEg/Lightning?quickstart=1).
It installs everything and opens Mohab's demo household (fictional data) in a preview tab.

**On your own computer** (Python 3.11+ and Git), from your fork:

```
pip install -r requirements-dev.txt
python -m lightning --demo          # opens at http://127.0.0.1:8766
python -m pytest -q                 # the tests
```

Then open a pull request with `Closes #123` in the description, and one line on how you checked it. We take care of the
changelog, docs and brand-guideline details before merging.

**Stuck or curious?** Ask on the issue, or in `#help` on [Discord](https://discord.gg/fukkUs263W).

---

**Ground rules.** Never put real financial data, passwords or keys in a commit or issue. Security problems go to
[SECURITY.md](SECURITY.md), never a public issue. The owner reviews and merges outside pull requests; nobody pushes to `main`.
Regular contributors can join the `internal` team ([.github/MAINTAINERS.md](.github/MAINTAINERS.md)). Going deeper:
[Project overview](docs/PROJECT_OVERVIEW.md), [Architecture](docs/ARCHITECTURE.md), and [AGENTS.md](AGENTS.md) for the AIs' rules.

**Licence.** Lightning is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE). By sending a pull
request you confirm that the work is yours to give, and you grant the owner the right to use, change and relicense it,
including commercially, as part of Lightning. You keep the copyright in what you wrote.
