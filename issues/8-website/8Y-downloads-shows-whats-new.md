---
title: Downloads shows what is new, from the release notes, in English and Arabic
type: feature
pillar: reach
size: M
status: new
created: 2026-10-31
by: Claude Sonnet 5.5
---
## Report
`current-status.html` and `release-log.html` are hand-written (19 KB and 30 KB; Arabic 20 KB and 37 KB) and each release touched about 15 files by hand. The current release is now one record, `app-release.json`, checked by `tools/app_release.py`. The release notes for people are generated in the app repo (`RELEASES.md`, `ai/changelog/`), in English only.

## Fix
Show the current release's notes on Downloads (five to eight plain bullets) and make the release log read from the same notes. Arabic needs a translation step that keeps the English as the source: store translations beside the English notes, or show English until one exists. Any visible change needs the usual release IDs and archive snapshots (README › Version identity and archive).
