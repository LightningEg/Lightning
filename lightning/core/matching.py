"""Read-only matching shared by search, history and scoped pickers.

Folding is for retrieval only. Identity resolution and every financial selection remain explicit.
"""
from __future__ import annotations

import re
import unicodedata
from rapidfuzz.fuzz import ratio
from lightning.core.money import ascii_digits

# Short account/instrument codes use exact and prefix comparison only.
CUTOFFS = {"Account": 78, "Counterparty": 68, "Person": 78, "Category": 70,
           "Investment": 78, "Reserve": 72, "Page": 72, "Action": 72, "Text": 72}
NUMERIC = re.compile(r"[\d\s,./:+−-]+")

# Letters and signs NFKD alone does not bring together: the taa marbuta typed as heh, the alef
# maqsura typed as ya, the wasla alef (NFKD leaves its superscript alef attached), the tatweel (a
# letter, not a mark), and the punctuation someone may type in either script quoted either way.
# Folded only at compare time; labels, links and stored data keep the original.
_COMPARE_FOLDS = str.maketrans({
    "ة": "ه",
    "ى": "ي",
    "ٱ": "ا",
    "ـ": "",
    "،": ",", "؛": ";", "؟": "?", "٪": "%",
    "`": "'", "‘": "'", "’": "'", "‛": "'", "ʻ": "'", "ʼ": "'", "ʽ": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
})


def fold_search_text(text: str) -> str:
    """The one folding for what search compares; both the query and the text are folded by it (7J).

    In order: NFKD, so full-width Latin, Arabic presentation forms, hamza-carrying letters
    (أ، إ، آ → ا; ؤ → و; ئ → ي, through their marks) and the lam-alef ligature break apart;
    Arabic-Indic and Persian digits through `core.money.ascii_digits`; combining marks and invisible
    format characters dropped, which removes tashkeel, shadda and tanween, Quran annotation marks and
    zero-width joiners; then the explicit folds above (ة → ه, ى → ي, ٱ → ا, the tatweel out, quotes
    and dashes to their ASCII forms) and Latin case and accents (casefold does Straße and STRASSE; the
    marks NFKD separates cover é vs e). A mark never carries an identity of its own here: dropping it
    joins no words that a space or punctuation kept apart. Empty input stays empty, and the fold is its
    own fixed point, so folding twice is folding once.
    """
    s = " ".join(str(text or "").casefold().split())
    s = unicodedata.normalize("NFKD", s)
    s = ascii_digits(s)
    s = "".join(c for c in s if unicodedata.category(c) not in ("Mn", "Cf"))
    return " ".join(s.translate(_COMPARE_FOLDS).split())


def match_score(needle: str, text: str, fuzzy: bool = True, kind: str = "Text") -> float:
    """Exact, prefix, word prefix, substring, then bounded typo similarity; no transliteration."""
    needle, text = fold_search_text(needle), fold_search_text(text)
    if not needle or not text:
        return 0.0
    if needle == text:
        return 1.0
    if text.startswith(needle):
        return 0.95
    if any(word.startswith(needle) for word in re.split(r"[\s›·/&,()-]+", text)):
        return 0.9
    if needle in text:
        return 0.8
    if not fuzzy or len(needle) < 3 or len(text) < 4 or NUMERIC.fullmatch(needle):
        return 0.0
    cutoff = CUTOFFS.get(kind, CUTOFFS["Text"])
    # Near spellings of a word within a longer name also count. Three-letter queries need a near-exact word.
    cutoff = max(cutoff, 84) if len(needle) == 3 else cutoff
    similarity = max(ratio(needle, part, score_cutoff=cutoff)
                     for part in (text, *re.split(r"[\s›·/&,()-]+", text)))
    return similarity / 100 * 0.75


def rank_choices(query: str, choices: list[dict], kind: str = "Text", limit: int = 80) -> list[str]:
    """Return only supplied choice ids, deterministically; never select or create anything."""
    found = []
    for index, row in enumerate(choices):
        score = max(match_score(query, row.get("label", ""), kind=kind),
                    match_score(query, row.get("context", ""), kind=kind),
                    match_score(query, row.get("code", ""), fuzzy=False, kind=kind)) if query.strip() else 1
        if score:
            found.append((-score, fold_search_text(row.get("label", "")), index, row["id"]))
    return [row[-1] for row in sorted(found)[:limit]]
