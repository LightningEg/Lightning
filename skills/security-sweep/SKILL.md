---
name: security-sweep
description: Audit the whole app for security on a schedule or before a release, surface by surface from SECURITY.md (local web server, pages and scripts, imported files, profile encryption and keys, backup and restore, the sync journal, updates and store keys, Windows and Android builds, CI), with a command for each check, and file what is found privately. Use before a release, after a large merge, every few weeks, or when asked whether Lightning is safe. For one pull request use skill review-outside-code.
---

# Security sweep

Tool-neutral. People keep their real money in Lightning. Report only what you reproduced, with the file and line. A real finding is **never** written in a public issue, pull request, commit message or `NOW.md`: it goes to a private security advisory (`SECURITY.md`) and the owner hears of it in the question tool. Out of scope: attacks that need the unlocked device or the profile password.

## Surfaces and checks

1. **Local web server** (`lightning/main.py`, `lightning/ui/web.py`): listens on `127.0.0.1` only; `same_origin_posts` refuses cross-origin POSTs (try one with `curl -X POST -H 'Origin: http://evil.example'`); every POST declares its save boundary (`tests/test_atomic_write_routes.py`); `--profiles` uses a random port. Error pages show no stack trace or file path.
2. **Pages and scripts**: `grep -rn "|safe\|Markup(" lightning/ui` and `grep -rn "innerHTML" lightning/ui/static`: each use renders only text the app wrote, never a name, memo, file or SMS a person or bank supplied. Every inline script carries the CSP nonce; no script, style or font from another host; `SAFE_SRC` in `phone-nav.js` lists only the app's own files.
3. **Imported files** (bank CSV and XLSX, PDF statements, SMS, broker statements, the starter workbook, backups): size and row limits, XML through `defusedxml`, no file name used as a path, malformed input ends in a readable error and writes nothing. Feed each reader an empty file, a 50 MB file, a zip bomb XLSX and a file named `../../x`.
4. **Profiles and keys** (`lightning/security`, `lightning/runtime`): SQLCipher on, the key never logged, written to disk in the clear or put in a URL; a wrong password reveals nothing about the data; the recovery words and device credentials as Architecture › Desktop app and encrypted profiles describes. `grep -rn "print(\|logging\.\|logger\." lightning/security lightning/runtime` for secrets in logs.
5. **Backup and restore** (`lightning/database/backup.py`, `promotion*.py`): backups are encrypted, a restore opens as a read-only copy first and never rewinds a live home, a tampered backup is refused.
6. **Sync journal** (`lightning/sync`, `cloudflare/journal`): signed and verified entries, pinned TLS on the LAN, enrollment needs the owner's proof; `npm ci --ignore-scripts && npm test && npm audit --audit-level=high` in `cloudflare/journal`; the Worker exposes no route without its check.
7. **Updates and store** (`lightning/security/update_keys.json`, `store_keys.json`, `packaging/update_manifest.py`): only public keys in the repo; an update is installed only after its signature checks; a bad signature and an older version are refused.
8. **Builds**: `packaging/android-permissions.txt` matches what the APK asks for (no new permission without the owner); the Windows ZIP holds no test data, `.git` or keys; `packaging/notices/` covers what ships.
9. **CI and repository**: every workflow's `permissions:` is the least it needs, actions pinned to full SHAs, no `pull_request_target`, secrets reach only steps that need them, `persist-credentials: false`; the CodeQL run (`codeql.yml`) has no open alert; `git log -p` and the tree hold no key, token, password or real statement (`git grep -nE "(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"`).
10. **Dependencies**: the `dependency-review` check and `npm audit` are clean; anything older than a year with a known advisory goes through skill `dependency-change`.

## After

Fix what is small and safe on its own branch with a test that proves the hole is closed, but describe it in the commit only as a hardening, without the attack. Everything else: a private advisory plus a plan item with `post: no` and no details beyond a pointer (skill `add-plan-item`). Report to the owner: surfaces checked, findings by severity (high: data readable or changeable by someone without the password; medium: needs a malicious file or a local program; low: hardening), what was not checked and why.
