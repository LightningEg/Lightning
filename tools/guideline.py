"""Print one brand guideline section as plain text, so an AI never has to read the whole HTML file.

    python tools/guideline.py            # list the sections: number, title, size as text
    python tools/guideline.py A16        # one section (A01-A16 the PC app, B01-B12 Normal, the website, C01-C12 the phone, D01-D12 Coders, For Geeks)
    python tools/guideline.py A03 A12    # several sections
    python tools/guideline.py --dir ../Lightning_website/guideline B05
    python tools/guideline.py --ar A06    # the Egyptian Arabic copy (app-ar.html, website-ar.html, phone-ar.html)

The guideline is four documents in guideline/: app.html (A01-A16), website.html (B01-B12, Normal), phone.html (C01-C12)
and coders.html (D01-D12, Coders: the website's For Geeks pages, English only). Together they are about 570 KB (roughly 95,000 tokens), mostly inline drawings; the words are about a tenth of that.
A section printed here is a few hundred tokens. The letter picks the file. Standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

GUIDELINE_DIR = Path(__file__).resolve().parent.parent / "guideline"
DOCUMENTS = {"A": "app.html", "B": "website.html", "C": "phone.html", "D": "coders.html"}
_SKIP = {"svg", "style", "script", "head"}
_BREAK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "section", "br", "table", "ul", "ol", "pre"}


class _Text(HTMLParser):
    """Visible words, one line per block element; drawings, styles and scripts left out."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skipping += 1
        elif tag in _BREAK:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" · ")
        else:
            self.parts.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in _BREAK:
            self.parts.append("\n")
        else:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)

    def text(self) -> str:
        lines = (re.sub(r"[ \t\r\f\v]+", " ", line) for line in "".join(self.parts).split("\n"))
        lines = (re.sub(r" ([.,;:)])", r"\1", line).strip(" ·") for line in lines)
        return "\n".join(line for line in lines if line)


def sections(html: str) -> list[tuple[str, str, str]]:
    """(number, title, section HTML) for every guideline section, in page order."""
    found = []
    for block in re.findall(r"<section\b.*?</section>", html, re.S):
        head = re.search(r'<h2><span class="secnum">([^<]*)</span>([^<]*)', block)
        if head:
            found.append((head.group(1).strip(), unescape(head.group(2)).strip(), block))
    return found


def all_sections(folder: Path, arabic: bool = False) -> list[tuple[str, str, str]]:
    """Sections of the four documents, A to D; with arabic, of the Arabic copies that exist (Coders has none)."""
    names = (name.replace(".html", "-ar.html") if arabic else name for name in DOCUMENTS.values())
    paths = (folder / name for name in names)
    return [item for path in paths if path.exists() for item in sections(path.read_text(encoding="utf-8"))]


def as_text(section_html: str) -> str:
    parser = _Text()
    parser.feed(section_html)
    return parser.text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("numbers", nargs="*", help="section numbers such as A16 or B05; none lists them")
    parser.add_argument("--dir", type=Path, default=GUIDELINE_DIR, help="the folder holding the four documents")
    parser.add_argument("--ar", action="store_true", help="read the Egyptian Arabic copies instead")
    args = parser.parse_args(argv)
    found = all_sections(args.dir, args.ar)
    if not args.numbers:
        for number, title, block in found:
            if number:
                print(f"{number:4} {title}  ({len(as_text(block)):,} characters)")
        return 0
    wanted = {number.upper() for number in args.numbers}
    shown = [(number, block) for number, _, block in found if number.upper() in wanted]
    for number, block in shown:
        print(as_text(block).replace("\u2066", "").replace("\u2069", ""), end="\n\n")
    missing = wanted - {number.upper() for number, _ in shown}
    if missing:
        print(f"No section {', '.join(sorted(missing))}. Run without arguments to list them.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
