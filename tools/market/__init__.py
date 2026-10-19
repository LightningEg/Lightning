"""The price collector: runs daily in GitHub Actions as the backup behind each app's own fetching
(issues/6-market-data/6A-price-packs.md).

    python -m tools.market collect --root market --packs egx,fx   # today's prices, one folder per pack
    python -m tools.market backfill --root market EG:COMI         # whole history for some instruments
    python -m tools.market pack --root market --out market.zip    # the default packs, for a release

Packs and their schedules are in lightning/market/packs.py. Each source is an adapter in
lightning/market/sources with pure parse functions tested on recorded samples (tests/fixtures/market). A run
checks every answer before it reaches the file and keeps the last good price when a source fails; each
pack's health.json says what happened, and index.json describes every pack.
"""
