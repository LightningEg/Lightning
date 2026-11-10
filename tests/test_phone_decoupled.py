"""The phone is decoupled from the PC (IV-3AY11, report r25 › Technical architecture).

The PC routes do not know the phone exists: no route asks whether the request is the phone's. What the phone shows
differently is decided in ``lightning/ui/phone/`` only: its router owns the phone's own URLs, and for a page a shared
route still builds, a presenter there adds the phone's context and picks the phone's template.

The pages the phone still draws from a PC template (inside the phone frame) are listed in
``tests/phone_pc_templates.txt``. That list only shrinks: giving a page its own phone template removes its line, and a
new PC page may not join it without a phone template or a place on the "This is on your PC" list."""
import re
from pathlib import Path

from lightning.ui.phone import presenters
from lightning.ui.web import templates

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "lightning" / "ui" / "routes"
ALLOWED = Path(__file__).with_name("phone_pc_templates.txt")
# How a route would ask who is looking. `phone_mode()` is the same question from a macro.
SWITCH = re.compile(r"state\.phone|state,\s*[\"']phone[\"']|\bon_phone\b|\blazy_folds\b|phone_mode\(|_phone_template")
# Parts other templates include or extend, emails and pages no phone can reach: they are not pages of their own.
NOT_PAGES = ("partials/", "macros", "base.html", "profiles", "journal/", "errors/")


def test_no_pc_route_asks_whether_the_phone_is_looking():
    found = [f"{path.name}:{number}: {line.strip()}" for path in sorted(ROUTES.glob("*.py"))
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if SWITCH.search(line)]
    assert not found, "A PC route may not switch on the phone; shape it in lightning/ui/phone/ instead:\n" + "\n".join(found)


def test_no_pc_route_names_a_phone_template():
    found = [f"{path.name}:{number}" for path in sorted(ROUTES.glob("*.py"))
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"[\"']phone/[\w/]+\.html[\"']", line)]
    allowed = set(_lines(Path(__file__).with_name("phone_routes_in_pc_files.txt")))
    files = sorted({entry.split(":")[0] for entry in found})
    assert set(files) <= allowed, f"Only the phone router renders templates/phone/: {sorted(set(files) - allowed)}"


def test_every_presenter_is_for_a_page_a_pc_route_renders():
    names = set(templates.env.list_templates())
    for name, module in presenters.PRESENTERS.items():
        assert name in names, name
        assert hasattr(__import__(f"lightning.ui.phone.presenters.{module}", fromlist=["present"]), "present")


def _lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def pc_pages_without_a_phone_template() -> list[str]:
    names = set(templates.env.list_templates())
    return sorted(name for name in names if name.endswith(".html") and not name.startswith("phone/")
                  and f"phone/{name}" not in names and not any(part in name for part in NOT_PAGES))


def test_the_pc_templates_the_phone_still_draws_only_shrink():
    allowed, now = set(_lines(ALLOWED)), set(pc_pages_without_a_phone_template())
    assert not now - allowed, ("A new PC page needs a phone template (templates/phone/<same name>), or the phone "
                               f"shows PC markup: {sorted(now - allowed)}")
    assert not allowed - now, f"Done: remove these lines from {ALLOWED.name}: {sorted(allowed - now)}"
