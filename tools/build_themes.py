"""Validate bundled data-only themes and generate CSS plus the boot registry.

Run from the repository root: python tools/build_themes.py [--check]
External packages: python tools/build_themes.py --validate path/to/theme.json
"""
from __future__ import annotations
import argparse
import json
import re
from urllib.parse import quote
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lightning.security.cosmetic_parts import require_complete, resolve_parts, slot_keys
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "lightning/ui/static"
SOURCE = STATIC / "cosmetics"
ALIASES = {
    "background": "bg paper paper-end canvas-start canvas-mid canvas-end",
    "surface": "surface white", "raised": "surface-2 field field-focus track hover accent-soft",
    "text": "text ink ink-900 c-ink c-nile on-focal",
    "muted": "muted ink-2 ink-700 ink-500 c-muted c-ink-2",
    "border": "border line edge c-line c-track",
    "accent": "accent", "focus": "focus line-control",
}
PARTS = {
    "header": {"surface": "theme-header topbar", "seam": "theme-header-seam"},
    "navigation": {"surface": "theme-nav", "activeMark": "theme-active"},
    "hero": {"surface": "theme-hero focal-1 focal-2 focal-3", "edge": "theme-hero-edge"},
    "cards": {"surface": "theme-card c-surface", "border": "theme-card-border"},
    "charts": {"grid": "theme-chart-grid", "accent": "theme-chart-accent"},
    "controls": {"fill": "action action-hover", "label": "on-action", "focus": "focus"},
    "overlays": {"surface": "theme-overlay", "backdrop": "theme-backdrop"},
    "menus": {"surface": "theme-menu", "divider": "theme-divider"},
    "buttons": {"surface": "theme-button", "label": "theme-button-label", "border": "theme-button-border"},
    "tabs": {"surface": "theme-tab", "chosen": "theme-tab-chosen", "chosenLabel": "theme-tab-chosen-label"},
    "fields": {"surface": "field field-focus theme-field", "border": "theme-field-border"},
    "progress": {"track": "track theme-track"},
}
def contrast(a, b):
    def luminance(h):
        rgb = [int(h[i:i+2], 16) / 255 for i in (1,3,5)]
        return sum(w * (v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)
                   for w,v in zip((.2126,.7152,.0722), rgb))
    x,y = sorted((luminance(a), luminance(b)))
    return (y+.05)/(x+.05)

def mix(a, b, percent):
    """b laid over a at percent, as CSS color-mix(in srgb, b percent, a) does."""
    return "#" + "".join(f"{round(int(a[i:i+2], 16) * (100 - percent) / 100 + int(b[i:i+2], 16) * percent / 100):02X}"
                         for i in (1,3,5))

def worst(p, parts, slot, surface, limits):
    """The surface at its most text-tinted point: the finish's lift plus the grain, from slots.json limits."""
    material = parts.get(slot, {})
    lift = limits["lift"].get(material.get("finish", "flat"), 0) + limits["grain"].get(material.get("grain", "none"), 0)
    shaded = mix(surface, p["text"], lift)
    return mix(shaded, p["accent"], ARTWORK_ALPHA) if material.get("artwork", "none") != "none" else shaded

def load(path):
    contract = json.loads((SOURCE / "slots.json").read_text())
    default = json.loads((SOURCE / "lightning-default.json").read_text())
    manifest = json.loads(path.read_text())
    require_complete(manifest, contract)
    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        raise ValueError("A theme name is required")
    parts, _ = resolve_parts(manifest, default, contract)
    p, limits = parts["palette"], contract["limits"]
    checks = [(p["text"], p["background"], 7), (p["muted"], p["background"], 4.5)]
    # the ground's texture is drawn in the text colour at most at its strength: text still reads on it
    ground = mix(p["background"], p["text"], {"whisper": 2, "subtle": 4, "rich": 6}[parts["ground"]["textureStrength"]]
                 if parts["ground"]["texture"] != "none" else 0)
    if parts["ground"]["artwork"] != "none":
        ground = mix(ground, p["accent"], ARTWORK_ALPHA)
    checks += [(p["text"], ground, 7), (p["muted"], ground, 4.5)]
    surfaces = [(slot, p[parts[slot]["surface"]]) for slot in ("header", "navigation", "hero", "cards", "overlays", "menus")]
    surfaces += [("", p[key]) for key in ("background", "surface", "raised")]
    surfaces += [("fields", p[parts["fields"]["surface"]]), ("buttons", p[parts["buttons"]["surface"]])]
    for slot, surface in surfaces:
        shaded = worst(p, parts, slot, surface, limits)
        checks.extend((p[t], shaded, 4.5) for t in ("text", "muted"))
        checks.append((p[parts["controls"]["focus"]], surface, 3))
    fill, label = p[parts["controls"]["fill"]], p[parts["controls"]["label"]]
    fills = [fill, worst(p, parts, "controls", fill, limits)]
    if parts["controls"]["finish"] == "foil":
        light, light_pct, dark, dark_pct = limits["foilStops"]
        fills += [mix(fill, light, light_pct), mix(fill, dark, dark_pct)]
    tab, tab_label = p[parts["tabs"]["chosen"]], p[parts["tabs"]["chosenLabel"]]
    tabs = [tab] + ([mix(tab, limits["foilStops"][0], limits["foilStops"][1]), mix(tab, limits["foilStops"][2], limits["foilStops"][3])]
                    if parts["tabs"]["finish"] == "foil" else [])
    checks += [(label, f, 4.5) for f in fills] + [(tab_label, t, 4.5) for t in tabs]
    checks += [(p[parts["buttons"]["label"]], p[parts["buttons"]["surface"]], 4.5),
               (p[parts["navigation"]["activeMark"]], p[parts["navigation"]["surface"]], 3)]
    for a,b,minimum in checks:
        if contrast(a,b) < minimum:
            raise ValueError(f"{manifest['id']}: {a} on {b} needs {minimum}:1 contrast")
    return manifest, parts

def materials(parts, contract):
    """Every material and motion choice, as the root attributes theme-runtime.js sets (data-m-cards-finish="satin")."""
    chosen = {}
    for slot, spec in contract["slots"].items():
        for key, values in slot_keys(spec).items():
            if values is not None and slot != "brand":
                chosen[f"{slot}-" + re.sub(r"([A-Z])", r"-\1", key).lower()] = parts[slot][key]
    return chosen

# Material recipes drawn per theme in the theme's own colours (theme-materials.css picks them by attribute). Inline
# SVG only: no file, request or script. Grain is the text colour at the grain limit in slots.json; artwork the accent.
def svg(body, w=240, h=240):
    return 'url("data:image/svg+xml,' + quote(f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>{body}</svg>", safe=" ='/:;,.()-") + '")'

def noise(colour, percent, frequency, seed=3, octaves=2, w=240, h=240):
    r, g, b = (int(colour[i:i+2], 16) / 255 for i in (1,3,5))
    k = round(percent / 50, 3)  # fractal noise averages half alpha: k doubles it back to the stated strength
    return svg(f"<filter id='n' x='0' y='0' width='100%' height='100%'><feTurbulence type='fractalNoise' baseFrequency='{frequency}' "
               f"numOctaves='{octaves}' seed='{seed}' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 {r:.3f} 0 0 0 0 {g:.3f} "
               f"0 0 0 0 {b:.3f} 0 0 0 {k} 0'/></filter><rect width='100%' height='100%' filter='url(#n)'/>", w, h)

TEXTURES = {  # each is a list of layers; percent is the strength
    "film": lambda c, pc: [noise(c, pc, ".9", octaves=3, w=200, h=200)],
    "paper": lambda c, pc: [noise(c, pc * .6, ".035 .05", seed=7, octaves=4, w=320, h=320), noise(c, pc * .5, ".9", w=200, h=200)],
    "fibre": lambda c, pc: [noise(c, pc * .6, ".004 .22", seed=11, octaves=3, w=480, h=240),
                             noise(c, pc * .45, ".2 .006", seed=5, octaves=3, w=240, h=480)],
    "papyrus": lambda c, pc: [noise(c, pc * .55, ".003 .18", seed=11, octaves=3, w=600, h=300),
                               noise(c, pc * .35, ".16 .004", seed=5, octaves=3, w=300, h=600),
                               noise(c, pc * .3, ".9", w=200, h=200)],
    "linen": lambda c, pc: [noise(c, pc * .5, ".8 .03", seed=2, w=200, h=200), noise(c, pc * .5, ".03 .8", seed=9, w=200, h=200)],
    "laid": lambda c, pc: [svg(f"<path d='M0 .5H6' stroke='{c}' stroke-opacity='{pc / 100 * 1.4:.3f}'/>", 6, 5),
                            noise(c, pc * .6, ".05 .4", seed=4, octaves=3, w=320, h=320)],
}
ROSETTE = "".join(f"<ellipse rx='92' ry='30' transform='rotate({a})'/>" for a in range(0, 180, 15)) + \
    "<circle r='96'/><circle r='60'/><circle r='18'/>" + \
    "".join(f"<ellipse rx='46' ry='14' transform='rotate({a})'/>" for a in range(0, 180, 30))
LOTUS = ("<path d='M0 40C-10 10-6-30 0-60C6-30 10 10 0 40Z'/><path d='M0 40C-24 18-34-14-30-46C-14-24-4 6 0 40Z'/>"
         "<path d='M0 40C24 18 34-14 30-46C14-24 4 6 0 40Z'/><path d='M0 40C-38 28-58 2-66-26C-40-14-16 10 0 40Z'/>"
         "<path d='M0 40C38 28 58 2 66-26C40-14 16 10 0 40Z'/>"
         + "".join(f"<path d='M-96 {y}c16-8 32-8 48 0s32 8 48 0 32-8 48 0 32 8 48 0'/>" for y in (58, 70, 82)))
ARTWORK = {
    "guilloche-rosette": lambda c, op: svg(f"<g transform='translate(100 100)' fill='none' stroke='{c}' stroke-opacity='{op}' stroke-width='.6'>{ROSETTE}</g>", 200, 200),
    "lotus-line": lambda c, op: svg(f"<g transform='translate(100 96)' fill='none' stroke='{c}' stroke-opacity='{op}' stroke-width='1' stroke-linejoin='round'>{LOTUS}</g>", 200, 200),
}
STRENGTH = {"whisper": 2, "subtle": 4, "rich": 6}
ARTWORK_ALPHA = 12  # artwork is a watermark: fine accent lines at 12%, like the guilloché behind a banknote's text

def material_values(parts, contract, scheme):
    p, limits = parts["palette"], contract["limits"]
    def alpha(colour, a):
        return f"rgb({int(colour[1:3], 16)} {int(colour[3:5], 16)} {int(colour[5:7], 16)} / {a})"
    # light falls from above: on a dark theme it is the text colour, on a light one white paper catching it
    light, (hi, edge, strong) = (p["text"], (.06, .09, .16)) if scheme == "dark" else ("#FFFFFF", (.6, .85, 1))
    values = {"m-shadow": "#000000" if scheme == "dark" else p["text"],
              "m-hi": alpha(light, hi), "m-hi-edge": alpha(light, edge), "m-hi-strong": alpha(light, strong)}
    for kind in sorted({parts[s]["grain"] for s in ("hero", "cards", "overlays")} - {"none"}):
        values[f"m-grain-{kind}"] = ", ".join(TEXTURES[kind](p["text"], limits["grain"][kind]))
    ground = parts["ground"]
    if ground["texture"] != "none":
        values["m-ground-texture"] = ", ".join(TEXTURES[ground["texture"]](p["text"], STRENGTH[ground["textureStrength"]]))
    if ground["artwork"] != "none":
        values["m-ground-artwork"] = ARTWORK[ground["artwork"]](p["accent"], ARTWORK_ALPHA / 100)
    if parts["hero"]["artwork"] != "none":
        values["m-hero-artwork"] = ARTWORK[parts["hero"]["artwork"]](p["accent"], ARTWORK_ALPHA / 100)
    return values

def compile_theme(manifest, parts, contract):
    if manifest["id"] == "lightning-default":
        return ""  # Preserve the exact approved default paint.
    p = parts["palette"]
    values = {}
    for key,names in ALIASES.items():
        values.update((name,p[key]) for name in names.split())
    for slot,fields in PARTS.items():
        for field,names in fields.items():
            values.update((name,p[parts[slot][field]]) for name in names.split())
    values["c-well"] = p["raised"]
    values["theme-on-accent"] = p[parts["controls"]["label"]]
    # The manifest's own money colours, for tints on its dark surfaces (theme-surfaces.css); the default keeps its paint.
    values.update({"theme-income": p["income"], "theme-expense": p["expense"]})
    values["theme-logo"] = "url(/static/lightning-mark-on-dark.svg)" if parts["brand"]["logoVariant"] == "on-dark" else "url(/static/lightning-mark.svg)"
    scheme = "dark" if contrast(p["background"], "#FFFFFF") > contrast(p["background"], "#000000") else "light"
    values.update(material_values(parts, contract, scheme))
    return ':root[data-theme="'+manifest["id"]+'"] {\n  '+"\n  ".join('--'+k+': '+v+';' for k,v in values.items())+'\n  color-scheme: '+scheme+';\n}\n'

def build(check=False):
    registry = []
    seen = set()
    css = "/* Generated by tools/build_themes.py. Do not edit. */\n"
    contract = json.loads((SOURCE / "slots.json").read_text())
    for path in sorted(SOURCE.glob("*.json")):
        if path.name == "slots.json":
            continue
        manifest,parts = load(path)
        if manifest['id'] in seen:
            raise ValueError(f"Duplicate theme ID: {manifest['id']}")
        seen.add(manifest['id'])
        if manifest.get('priceCoins') is not None:
            raise ValueError("Preview themes must not have a price")
        if manifest.get('status') == 'built-in-default' and manifest['id'] != 'lightning-default':
            raise ValueError("Only lightning-default is the built-in default")
        if manifest.get("status") not in ("built-in-default", "test-preview", "paid"):
            raise ValueError("A theme is the built-in default, a test preview or paid")
        # A paid theme shares its id with the store's catalogue item (one purchase on every surface) and is worn only
        # with a verified licence for this exact version (lightning/ui/entitlements.py); anyone may try it for a session.
        entry = {"id": manifest["id"], "name": manifest["name"], "preview": manifest["status"] == "test-preview"}
        if manifest["status"] == "paid":
            entry.update(paid=True, version=manifest["version"])
        if manifest["id"] != "lightning-default":  # the default keeps its exact approved paint
            entry["materials"] = materials(parts, contract)
        registry.append(entry)
        css += compile_theme(manifest,parts,contract)
    outputs = {STATIC / "themes.generated.css": css,
               STATIC / "themes.generated.json": json.dumps(registry, indent=2) + "\n",
               STATIC / "themes.generated.js": "/* Generated. */\nwindow.LIGHTNING_THEMES = "+json.dumps(registry)+";\n"}
    for path,content in outputs.items():
        if check:
            if not path.exists() or path.read_text() != content:
                raise ValueError(f"Stale generated file: {path.name}")
        else:
            path.write_text(content)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.validate:
        load(args.validate)
        print("Theme contract and contrast checks passed")
    else:
        build(args.check)
