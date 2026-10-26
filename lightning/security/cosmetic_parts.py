"""Data-only cosmetic compartments. Validates the entire theme before application."""
from __future__ import annotations

import re
from copy import deepcopy


class InvalidCosmeticParts(ValueError):
    pass


def slot_keys(spec: dict) -> dict[str, list[str] | None]:
    """Each property of a slot: None for a paint key (a palette reference), else its approved values."""
    keys: dict[str, list[str] | None] = {key: None for key in spec.get("paint", [])}
    for layer in ("material", "motion"):
        keys.update(spec.get(layer, {}))
    return keys


def validate_parts(manifest: dict, contract: dict) -> dict:
    if (not isinstance(manifest, dict) or type(manifest.get("schemaVersion")) is not int
            or manifest.get("schemaVersion") != contract["schemaVersion"]
            or not isinstance(manifest.get("id"), str) or not re.fullmatch(r"[a-z0-9-]{2,60}", manifest["id"])
            or type(manifest.get("version")) is not int or manifest["version"] < 1):
        raise InvalidCosmeticParts("Unsupported theme manifest")
    parts = manifest.get("parts")
    if not isinstance(parts, dict):
        raise InvalidCosmeticParts("Parts required")
    tokens = contract["slots"]["palette"]["paint"]
    for slot, values in parts.items():
        if slot not in contract["slots"] or not isinstance(values, dict):
            raise InvalidCosmeticParts("Unknown or malformed part")
        keys = slot_keys(contract["slots"][slot])
        for key, value in values.items():
            if key not in keys or not isinstance(value, str):
                raise InvalidCosmeticParts("Unsupported part property")
            if slot == "palette":
                valid = re.fullmatch(r"#[a-fA-F0-9]{6}", value)
            elif keys[key] is None:
                valid = value in tokens
            else:
                valid = value in keys[key]
            if not valid:
                raise InvalidCosmeticParts("Unsupported part value")
    return manifest


def require_complete(manifest: dict, contract: dict) -> dict:
    """A delivered theme states every layer of every element: nothing is left to the default by chance."""
    validate_parts(manifest, contract)
    for slot, spec in contract["slots"].items():
        missing = set(slot_keys(spec)) - set(manifest["parts"].get(slot, {}))
        if missing:
            raise InvalidCosmeticParts(f"{slot} needs {', '.join(sorted(missing))}")
    check_motion(manifest["parts"], contract)
    return manifest


def check_motion(parts: dict, contract: dict) -> None:
    """One continuous motion at most; hover, press, enter and equip only answer the user."""
    running = [name for name in contract["limits"]["continuous"]
               if parts.get(name.split(".")[0], {}).get(name.split(".")[1], "none") != "none"]
    if len(running) > 1:
        raise InvalidCosmeticParts(f"One continuous motion at most, not {', '.join(running)}")


def resolve_parts(manifest: dict, default: dict, contract: dict) -> tuple[dict, bool]:
    """Merge valid partial parts over the built-in default; invalid themes roll back wholly."""
    try:
        require_complete(default, contract)
    except InvalidCosmeticParts as error:
        raise InvalidCosmeticParts('Incomplete built-in fallback') from error
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
    check_motion(result, contract)
    return result
