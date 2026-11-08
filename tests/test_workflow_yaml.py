"""Every workflow file must load: GitHub silently skips a file it cannot parse (zero jobs, red run)."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PLAIN_ONE_LINE_RUN = re.compile(r"^\s*(?:-\s+)?run:\s+(?![|>'\"])(.*)$")


def test_no_one_line_run_holds_an_unquoted_colon_space():
    # In a plain YAML scalar, ": " starts a mapping, so `run: pip ... :all: -r x` breaks the whole file.
    bad = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = PLAIN_ONE_LINE_RUN.match(line)
            if match and ": " in match.group(1).split(" #")[0]:
                bad.append(f"{path.name}:{number}")
    assert not bad, "quote these run: lines or use a | block: " + ", ".join(bad)
