---
title: Run the one-time security setup on your own computer
type: owner
area: tools
status: ready
created: 2026-10-19
by: Claude
---

## Report
`python tools/security_setup.py` (preview), then `--apply`. It turns on the no-bypass pull-request rule for `main`, auto-merge, deleting merged branches (about 156 old ones are waiting), release-tag protection, secret scanning and the release environments. Until then the rule that nobody pushes to `main` is not confirmed active. Deploy the website receiver before its dashboard.

**Read:** [CONTRIBUTING.md](../../CONTRIBUTING.md) › Owner: once; [1E](1E-public-repository-security-audit.md).
