"""The server and browser share the generated bundled theme allowlist."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _registry() -> tuple[dict, ...]:
    """The generated registry, read once per process (it only changes with a build)."""
    path = Path(__file__).parent / "static/themes.generated.json"
    return tuple(json.loads(path.read_text()))


def theme_ids() -> frozenset[str]:
    return frozenset(theme["id"] for theme in _registry())


def theme_id(value: str) -> str:
    """The theme to wear: a bundled one, and a paid one only with its licence here (lightning/ui/entitlements.py)."""
    from lightning.ui.entitlements import wearable
    return value if value in theme_ids() and wearable(value) else "lightning-default"


def theme_name(value: str) -> str:
    """The registry's display name for a theme id (its own id when unknown)."""
    return next((t["name"] for t in _registry() if t["id"] == value), value)
