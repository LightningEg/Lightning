"""Data-only cosmetic compartments. Validates the entire theme before application."""
from __future__ import annotations

import re
from copy import deepcopy


class InvalidCosmeticParts(ValueError):
    pass


def validate_parts(manifest: dict, contract: dict) -> dict:
    if (not isinstance(manifest, dict) or type(manifest.get("schemaVersion")) is not int or manifest.get("schemaVersion") != 1
            or not isinstance(manifest.get("id"), str) or not re.fullmatch(r"[a-z0-9-]{2,60}", manifest["id"])
            or type(manifest.get("version")) is not int or manifest["version"] < 1):
        raise InvalidCosmeticParts("Unsupported theme manifest")
    parts = manifest.get("parts")
    if not isinstance(parts, dict):
        raise InvalidCosmeticParts("Parts required")
    tokens = contract["slots"]["palette"]["allowed"]
    for slot, values in parts.items():
        if slot not in contract["slots"] or not isinstance(values, dict):
            raise InvalidCosmeticParts("Unknown or malformed part")
        for key, value in values.items():
            if key not in contract["slots"][slot]["allowed"] or not isinstance(value, str):
                raise InvalidCosmeticParts("Unsupported part property")
            if slot == "palette":
                valid = re.fullmatch(r"#[a-fA-F0-9]{6}", value)
            elif key == "logoVariant":
                valid = value in ("on-dark", "on-light")
            elif key == "pattern" and slot == "decoration":
                valid = value in contract["slots"]["decoration"].get("patterns", ["none"])
            elif key == "motion" and slot == "decoration":
                valid = value in contract["slots"]["decoration"].get("motions", ["none"])
            elif key in ("pattern", "motion", "decoration"):
                valid = value == "none"
            else:
                valid = value in tokens
            if not valid:
                raise InvalidCosmeticParts("Unsupported part value")
    return manifest


def resolve_parts(manifest: dict, default: dict, contract: dict) -> tuple[dict, bool]:
    """Merge valid partial parts over the built-in default; invalid themes roll back wholly."""
    validate_parts(default, contract)
    for slot, spec in contract['slots'].items():
        if set(default['parts'].get(slot, {})) != set(spec['allowed']):
            raise InvalidCosmeticParts('Incomplete built-in fallback')
    result = deepcopy(default['parts'])
    try:
        validate_parts(manifest, contract)
    except InvalidCosmeticParts:
        return result, True
    for slot, values in manifest['parts'].items():
        result[slot].update(values)
    return result, False


def compose_parts(selection: dict[str, str], baseline: dict, catalog: dict[str, dict],
                  owned_versions: dict[str, int], contract: dict) -> dict:
    """Choose each compartment from an owned, bundled theme or the free default.

    owned_versions must come from verified licenses, not editable preferences. References
    remain semantic tokens: mixing paint cannot introduce layout or executable content.
    Validate the composed visual states/contrast before the renderer saves a selection.
    """
    result, _ = resolve_parts(baseline, baseline, contract)
    for slot, source in selection.items():
        if slot not in contract['slots']:
            raise InvalidCosmeticParts('Unknown part slot')
        if source == baseline['id']:
            continue
        manifest = catalog.get(source)
        if not manifest or owned_versions.get(source) != manifest.get('version'):
            raise InvalidCosmeticParts('Part source is not owned at this bundled version')
        validate_parts(manifest, contract)
        result[slot].update(manifest['parts'].get(slot, {}))
    return result
