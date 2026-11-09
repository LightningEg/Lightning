---
title: Delete one profile from the phone's Settings, not only by clearing Android's storage
type: feature
pillar: protect
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

IV-11H built the phone's Settings with a "Delete your data" section that can only point to Android's route (Settings ›
Apps › Lightning › Storage › Clear, or uninstall), which wipes every profile on the phone. Owner, 2026-11-09: plan an
in-app delete. Play's Data safety answers and the privacy notice (NF-11B4, NF-11B5) say how to delete data.

## Fix

Files: `lightning/runtime/profile_screens.py` (a confirm page and the post), the profile store that lists profiles,
`lightning/ui/templates/phone/settings/index.html` (the row replaces the explanation), `lightning/ui/i18n*.py`.
- "Delete this profile": names the profile, offers "Save a copy" first, then asks for its password; it locks the
  profile, removes its database, its backups and its device keys, and opens the profile chooser.
- A paired device keeps nothing it cannot open; a journal home is handed back or ends first (stay out of the journal
  claim's files; ask its owner).
- The PC keeps its own route; the same post serves both when the PC wants it.
Done when: a test creates two profiles, deletes one with its password (a wrong password deletes nothing), and the other
still opens; the deleted profile's files are gone from the documents folder.
