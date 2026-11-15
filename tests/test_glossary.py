"""The in-app glossary (Settings › Glossary): every term is explained, in both languages, on the PC and the phone."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.core.figures import FIGURES
from lightning.ui.glossary import glossary_terms
from lightning.ui.web import create_app


def test_every_term_has_a_plain_meaning_in_english_and_arabic():
    terms = glossary_terms()
    assert len(terms) >= 20
    for term in terms:
        assert term.meaning.strip() and term.meaning_ar.strip() and term.name_ar.strip(), term.key
    assert len({t.key for t in terms}) == len(terms)


def test_figure_terms_use_the_figures_table_names():
    names = {t.name for t in glossary_terms()}
    for key in ("free_cash", "safe_to_spend", "left_in_plan", "savings_rate", "what_you_own", "what_you_owe"):
        assert FIGURES[key].label in names


def test_the_glossary_page_opens_from_settings(c):
    client = TestClient(create_app(c))
    page = client.get("/settings/glossary").text
    for words in ("Free cash", "Safe to spend", "Savings rate", "Needs you", "Where you see it"):
        assert words in page, words
    assert 'href="/settings/glossary"' in client.get("/settings").text
