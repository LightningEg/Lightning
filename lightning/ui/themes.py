"""The server and browser share the generated bundled theme allowlist."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def theme_ids() -> frozenset[str]:
    path = Path(__file__).parent / "static/themes.generated.json"
    return frozenset(theme["id"] for theme in json.loads(path.read_text()))


def theme_id(value: str) -> str:
    """The theme to wear: a bundled one, and a paid one only with its licence here (lightning/ui/entitlements.py)."""
    from lightning.ui.entitlements import wearable
    return value if value in theme_ids() and wearable(value) else "lightning-default"
