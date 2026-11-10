"""IT-9F1: the unreachable-CSS tool keeps what a template or script can reach and finds the rest."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("css_unused", Path(__file__).resolve().parents[1] / "tools" / "css_unused.py")
css_unused = importlib.util.module_from_spec(spec)
spec.loader.exec_module(css_unused)


def _dead(tmp_path, css: str, **files) -> list[dict]:
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    dead, _ = css_unused.dead_rules(css, css_unused.corpus(tmp_path))
    return dead


def test_a_class_in_a_template_is_kept_and_one_nowhere_is_dead(tmp_path):
    dead = _dead(tmp_path, ".used { color: red }\n.gone { color: blue }\n", **{"a.html": '<div class="used">'})
    assert [d["selector"] for d in dead] == [".gone"] and dead[0]["line"] == 2


def test_a_selector_list_is_kept_while_one_of_its_selectors_is_seen(tmp_path):
    assert _dead(tmp_path, ".a, .b { x: y }\n", **{"a.html": '<i class="b">'}) == []
    assert len(_dead(tmp_path, ".a, .b { x: y }\n", **{"a.html": "nothing"})) == 1


def test_a_class_built_at_run_time_counts_as_seen(tmp_path):
    css = ".tone-good { x: y }\n.is-open { x: y }\n.chip-red { x: y }\n.plain-miss { x: y }\n"
    files = {"a.js": 'el.className = "tone-" + x;', "b.py": 'f"is-{state}"', "c.js": "`chip-${k}`"}
    assert [d["selector"] for d in _dead(tmp_path, css, **files)] == [".plain-miss"]


def test_rules_inside_media_are_found_with_their_line_and_keyframes_are_skipped(tmp_path):
    css = "@keyframes spin { from { a: b } }\n@media (max-width: 600px) {\n  .ghost { x: y }\n  .live { x: y }\n}\n"
    dead = _dead(tmp_path, css, **{"a.html": "live"})
    assert [(d["selector"], d["line"]) for d in dead] == [(".ghost", 3)]


def test_a_class_inside_not_does_not_make_a_rule_dead(tmp_path):
    assert _dead(tmp_path, "input:not(.x_)::file-selector-button { a: b }\n", **{"a.html": "<input>"}) == []
