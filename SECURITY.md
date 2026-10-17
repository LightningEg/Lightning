# Security

Lightning handles personal financial data, so we take reports seriously.

**Report a vulnerability privately:** use [Report a vulnerability](https://github.com/LightningEg/Lightning/security/advisories/new)
on this repository. Do not open a public issue or pull request for it. We aim to answer within 7 days.

**In scope:** profile encryption, backup/restore, the sync journal, the local web server, the Windows and Android builds,
and the CI workflows. **Out of scope:** attacks that need the user's unlocked device or profile password.

**Never** put real financial data, passwords, keys or tokens in an issue, a pull request or a commit.
If you committed one by mistake, tell us at once so it can be revoked.

## How changes reach `main`

Nobody pushes to `main`. Every change comes as a pull request, passes the automatic checks, is approved by the owner or by a
second (AI) reviewer outside owner-only paths, and is merged by the owner or an AI under those rules. Pull requests from first-time contributors do not run CI until the owner
approves the run. See [.github/MAINTAINERS.md](.github/MAINTAINERS.md).
