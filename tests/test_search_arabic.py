"""Search folds both sides of a compare the same way (`_fold_search_text`), so Arabic spelling variants,
tashkeel and tatweel, Arabic-Indic and Persian digits and Latin case and accents read equal (7J); the
fold is for comparing only — the original text stays for display, links and stored data, and
`counterparties.normalize` is untouched."""
from __future__ import annotations

import unicodedata

from fastapi.testclient import TestClient

from lightning.ui.routes.search import _fold_search_text, _score, matches
from lightning.ui.web import create_app

fold = _fold_search_text  # readability in the assertions


# --- Arabic letters and orthography ---------------------------------------------------------

def test_alef_variants_fold_to_plain_alef():
    assert fold("أ إ آ ٱ") == "ا ا ا ا"


def test_taa_marbuta_and_alef_maqsura_fold():
    assert fold("مدرسة") == fold("مدرسه")
    assert fold("مستشفى") == fold("مستشفي")
    assert _score("مدرسه", "مدرسة") == 1.0
    assert _score("مستشفي", "مستشفى") == 1.0


def test_hamza_on_waw_and_ya_folds_through_its_mark():
    assert fold("مؤمن") == fold("مومن")
    assert fold("رؤية") == fold("روية")
    assert fold("ؤ") == "و" and fold("ئ") == "ي"


def test_the_standalone_hamza_stays_its_own_letter():
    assert fold("قرأ") == "قرا"
    assert fold("قرء") == "قرء"
    assert fold("ء") != fold("و")


def test_tashkeel_shadda_tanween_and_quran_marks_are_dropped():
    assert fold("كِتَابٌ") == "كتاب"          # marks only
    assert fold("شَدَّةً") == "شده"            # marks and the marbuta fold, as typed ة does
    assert fold("ض\u06D6ط") == "ضط"  # a Quranic annotation mark


def test_tatweel_and_zero_width_joiners_do_not_block_a_match():
    assert fold("تكـوين") == "تكوين"
    assert fold("أح\u200dمد") == fold("احمد")
    assert fold("أحـمد") == "احمد"
    assert _score("احمد", "أحـمد") == 1.0
    assert _score("احمد", "أحـمد عادل") == 0.95


def test_presentation_forms_fold_like_their_ordinary_letters():
    assert fold("ﺃهﻻ") == "اهلا"          # FE8x presentation forms
    assert fold("ﻣﺪرسة") == fold("مدرسه")  # the lam-alef and shaded forms too


def test_arabic_punctuation_folds_to_its_ascii_form_and_splits_words():
    assert fold("عادل، كريم؛ آه؟") == "عادل, كريم; اه?"
    assert _score("كريم", "عادل، كريم") == 0.9  # a word after an Arabic comma is a word


# --- digits ----------------------------------------------------------------------------------

def test_arabic_indic_and_persian_digits_fold_to_ascii():
    assert fold("٠١٢٣٤٥٦٧٨٩") == "0123456789"
    assert fold("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert fold("٢٠٢٦ ۳۴") == "2026 34"


def test_amount_queries_match_the_way_the_app_prints_them():
    assert _score("٢٠٢٦", "2026 rent") == 0.95
    assert _score("۲۰۲۶", "2026 rent") == 0.95
    assert _score("٣.٥٠", "3.50") == 1.0  # the Arabic decimal mark folds with the digits


def test_numbers_keep_the_no_fuzzy_rule_across_scripts():
    assert _score("٤٥.٦", "٣٤,٦", fuzzy=True) == 0.0     # near-spelling is never tried on numbers
    assert _score("12", "345.9", fuzzy=True) == 0.0      # and that holds for plain digits


# --- Latin and unicode variants ---------------------------------------------------------------

def test_case_and_accents_are_insensitive():
    assert fold("Straße") == fold("STRASSE")
    assert _score("STRASSE", "Straße") == 1.0
    assert fold("Café") == "cafe"
    assert _score("cafe", "Café") == 1.0


def test_full_width_and_presentation_letters_and_digits_fold():
    assert fold("Ｃ２Ｂ") == "c2b"
    assert _score("２０２６", "2026 rent") == 0.95


def test_quotes_and_dashes_fold_to_their_ascii_forms():
    assert fold("O’Brien") == fold("O'Brien")
    assert fold("e‑mail") == "e-mail"
    assert _score("well‑being", "well-being") == 1.0  # both fold to one string
    assert _score("being", "well-being") == 0.9  # a dash separates words for the word-prefix rank


def test_spaces_even_unicode_ones_collapse():
    assert fold("\u00a0a\u00a0b\u00a0") == "a b"


# --- safety -----------------------------------------------------------------------------------

def test_empty_and_meaningless_input_never_matches():
    assert fold("") == ""
    assert _score("", "أحمد عادل") == 0.0
    assert _score("احمد", "") == 0.0
    assert _score("   ", "أحمد عادل") == 0.0
    assert _score("احمد", "   ") == 0.0


def test_distinct_letters_stay_distinct():
    assert fold("ح") != fold("خ") and fold("د") != fold("ذ") and fold("ه") != fold("خ")
    assert _score("احمد", "محمود عادل") == 0.0  # similar first letters are not a match
    assert _score("مدرسه", "مدرسة 2026") == 0.95  # only starts-with, folding did not fabricate equality


def test_mixed_script_text_folds_on_both_sides():
    assert fold("مكتبة CIB عادل") == fold("مكتـبة cib عادل")
    assert _score("مكتبة", "مكتبة CIB") == 0.95  # each script matches by its own spelling
    assert _score("Cib", "مكتبة CIB عادل") == 0.9  # and the Latin word inside an Arabic name too
    assert _score("Ahmed", "أحمد عادل") == 0.0  # no cross-script transliteration


def test_the_fold_is_its_own_fixed_point():
    once = fold("أحمد صاحب، ٢٠٢٦ — O’Brien")
    assert fold(once) == once


def test_folded_text_is_a_plain_ikhlas_form():
    assert unicodedata.is_normalized("NFC", fold("أحمد عادل"))


# --- the matcher and the routes fold, stored data does not -------------------------------------

def _household(c):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    account = c.account_flows.open_account("NBE Current", "BANK", "2026-09-01", "5,000")
    c.transactions.record_outflow("2026-09-11", account.id, "200", food.id, counterparty="أحمد عادل",
                                  notes="2026 rent")


def test_matches_ranks_arabic_variants_and_keeps_original_text(c):
    _household(c)
    rows = matches(c, "احمد")
    party = next(row for row in rows if row["kind"] == "Counterparty")
    assert party["label"] == "أحمد عادل" and "q=" in party["href"]  # the stored spelling, for display
    assert next(row for row in rows if row["kind"] == "Search")["label"] == "Find transactions with “احمد”"
    assert c.counterparties.list_active()[0]["name"] == "أحمد عادل"  # stored data is untouched


def test_ctrl_k_folds_digits_and_arabic_through_the_json_route(c):
    _household(c)
    client = TestClient(create_app(c))
    for query, want in (("احمد", {"Counterparty"}), ("٢٠٢٦ rent", {"Search"}), ("۲۰۲۶", {"Search"})):
        rows = client.get("/search", params={"q": query, "format": "json"}).json()["results"]
        assert {row["kind"] for row in rows} & want, (query, [row["kind"] for row in rows])


def test_empty_command_bar_still_opens_the_launcher(c):
    client = TestClient(create_app(c))
    rows = client.get("/search", params={"format": "json"}).json()["results"]
    assert {row["kind"] for row in rows} >= {"Page", "Action"}
