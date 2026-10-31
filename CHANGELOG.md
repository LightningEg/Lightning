# Changelog

The changelog is no longer one shared file: that made every push edit the same lines and every release a wall of text.

- **People:** [RELEASES.md](RELEASES.md) says what changed in each version, in plain words.
- **AI sessions:** [ai/changelog/](ai/changelog/) holds the detail, one file per version. `python tools/release_notes.py recent`
  shows what is unreleased. Older history: [ai/archive/](ai/archive/CHANGELOG-0.5-and-older.md).
- **Writing one:** end your commit with `Release-note:` and `Detail:` lines. AGENTS.md section 3 says how.
