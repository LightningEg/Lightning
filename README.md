# Lightning

Free personal finance for salaried people in Egypt. One ledger for your accounts, spending, budget, savings, shares, gold and
foreign currency, counted in EGP. It runs on Windows and Android, keeps your data in an encrypted profile on your own devices,
and never asks for a bank login. English and Arabic.

**[Download](https://lightningeg.com/current-status.html)** · [Website](https://lightningeg.com) · [Release notes](RELEASES.md) · [Where it stands](docs/STATUS.md)

## Find your way

| You are | Start with |
|---|---|
| Using Lightning | [lightningeg.com](https://lightningeg.com), then [change the theme](docs/themes.md) and the [release notes](RELEASES.md) |
| Curious how it works | [docs/README.md](docs/README.md): the product, how it is built, a real month, and nine pillars |
| Helping build it | [CONTRIBUTING.md](CONTRIBUTING.md): pick a good first issue, comment `/take`, open it in Codespaces |
| An AI session | [AGENTS.md](AGENTS.md), then [NOW.md](NOW.md) and [ai/INDEX.md](ai/INDEX.md) |

## Run from source

```
pip install -r requirements-dev.txt
python -m lightning --profiles   # the password-protected app, in a browser (Linux)
python -m pytest                 # the tests
lint-imports                     # architecture contracts
```

The Windows ZIP and Android APK are built from one tested commit and published in
[Lightning-downloads](https://github.com/LightningEg/Lightning-downloads/releases). Profiles and backups live in
`Documents/Lightning`, never in this repository: it holds code, tests and sample data only. How the build works:
[ai/ARCHITECTURE.md](ai/ARCHITECTURE.md) › Build and release.

## Licence

Lightning is **source-available**, not open source: free for personal and other non-commercial use under the
[PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use needs the owner's written permission: ask in a
[GitHub issue](https://github.com/LightningEg/Lightning/issues). Security problems go to [SECURITY.md](SECURITY.md).
