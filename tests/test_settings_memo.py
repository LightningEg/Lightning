"""A page reads dozens of settings: inside one request the table is read once, and a write is seen at once."""
from lightning.core.memo import request_cache


def test_settings_are_read_once_per_request_and_writes_show_at_once(c):
    reads = []
    originals = {name: getattr(c.db, name) for name in ("scalar", "all")}

    def counting(name):
        def read(sql, *args, **kwargs):
            if "FROM settings" in sql:
                reads.append(sql)
            return originals[name](sql, *args, **kwargs)
        return read

    for name in originals:
        setattr(c.db, name, counting(name))
    try:
        with request_cache(c.db):
            first = [c.settings.get("base_currency") for _ in range(5)]
            c.settings.get("zakat_enabled")  # another key, never saved: the same one read (IT-3AO4)
            assert len(reads) == 1 and set(first) == {"EGP"}
            c.settings.set("budget_income_months", "6")
            assert c.budgets._average_months() == 6  # a write inside the request is read fresh
        reads.clear()
        c.settings.get("base_currency")
        c.settings.get("base_currency")
        assert len(reads) == 2  # outside a request nothing is remembered
    finally:
        for name, original in originals.items():
            setattr(c.db, name, original)
