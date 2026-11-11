"""NF-7V: more AI prompt buttons that carry Lightning's context.

Every hand-off is the shared Copy / Edit pair (partials/ai_prompt.html): the text sits in the edit window only, is built from
names and words, never an amount, and each button says why it helps (with an Arabic string).
"""
from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.i18n import ARABIC_UI
from lightning.ui.web import create_app
from lightning.workflows import ai_prompts

BAD_CSV = (b"Date,Amount,Counterparty\n2026-09-10,-250.75,Secret Merchant 9981\n"
           b"not a date,-7777.77,Other Merchant 5512\n2026-09-11,no amount,Zero Row\n")


def _outside_dialogs(page: str) -> str:
    return re.sub(r"<dialog.*?</dialog>", "", page, flags=re.S)


def _dialogs(page: str) -> list[str]:
    return re.findall(r"<dialog.*?</dialog>", page, flags=re.S)


def _is_hand_off(page: str, opening: str, why: str) -> str:
    """The prompt is two buttons and a closed window; the sentence that starts the prompt appears nowhere else."""
    assert "data-ai-copy" in page and "data-ai-edit" in page and "Edit prompt" in page
    assert why in page
    assert opening not in _outside_dialogs(page)
    held = [d for d in _dialogs(page) if opening in d]
    assert len(held) == 1 and "<dialog class=\"review-dialog ai-prompt-dialog\"" in held[0]
    return html.unescape(held[0])


def test_a_rejected_csv_hands_over_its_header_and_error_lines_never_the_values(c, setup):
    accounts, _ = setup
    client = TestClient(create_app(c))
    account_id = accounts["cib"].id
    response = client.post(f"/accounts/{account_id}/import", files={"file": ("bad.csv", BAD_CSV, "text/csv")},
                           follow_redirects=True)
    assert response.status_code == 200
    window = _is_hand_off(response.text, "Help me fix the file", "what Lightning rejected on each line")
    assert "Date, Amount, Counterparty" in window and "- line 3:" in window and "- line 4:" in window
    assert "Date,Inflow,Outflow" in window
    for value in ("Secret Merchant 9981", "Other Merchant 5512", "250.75", "7777.77", "Zero Row"):
        assert value not in window
    # A statement with nothing rejected carries no such prompt.
    clean = client.post(f"/accounts/{account_id}/import",
                        files={"file": ("ok.csv", b"Date,Amount,Counterparty\n2026-09-10,-250.75,Shop\n", "text/csv")},
                        follow_redirects=True)
    assert "Help me fix the file" not in clean.text


def test_a_failed_column_match_hands_over_the_header_and_the_message(c, setup):
    accounts, _ = setup
    client = TestClient(create_app(c))
    data = b"When,Net\n2026-09-10,-250.75\n"
    first = client.post(f"/accounts/{accounts['cib'].id}/import", files={"file": ("x.csv", data, "text/csv")})
    assert "Match your columns" in first.text and "Help me fix the file" not in first.text
    payload = re.search(r'name="payload" value="([^"]+)"', first.text).group(1)
    failed = client.post(f"/accounts/{accounts['cib'].id}/import/map",
                         data={"payload": payload, "filename": "x.csv", "amount_model": "SINGLE", "map_Date": "When"})
    assert failed.status_code == 400
    window = _is_hand_off(failed.text, "Help me fix the file", "your file’s header")
    assert "When, Net" in window and "- line 1:" in window and "250.75" not in window


def test_the_first_import_into_an_account_offers_the_category_mapping_prompt(c, setup):
    accounts, cats = setup
    client = TestClient(create_app(c))
    page = client.get(f"/accounts/{accounts['cib'].id}/import").text
    window = _is_hand_off(page, "I am importing my first bank statement from CIB", "First import into this account?")
    label = c.categories.display_name(cats["EXP.PERSONAL.FOOD"].id)
    assert label in window and "(leave blank)" in window
    # Once a statement was posted into the account it is no longer the first import.
    c.db.execute("INSERT INTO bank_import_batches(account_id,file_hash,file_name,status,created_at) VALUES (?,?,?,?,?)",
                 (accounts["cib"].id, "h", "old.csv", "POSTED", "2026-09-01T00:00:00"))
    again = client.get(f"/accounts/{accounts['cib'].id}/import").text
    assert "I am importing my first bank statement" not in again and "First import into this account?" not in again
    other = client.get(f"/accounts/{accounts['wallet'].id}/import").text
    assert "I am importing my first bank statement from Wallet" in other


def test_counterparties_hands_over_names_and_aliases_for_clean_up(c):
    c.counterparties.create("Talabat")
    other = c.counterparties.create("Talabat Egypt")
    c.counterparties.add_alias(other, "TLBT*EG")
    client = TestClient(create_app(c))
    page = client.get("/counterparties").text
    window = _is_hand_off(page, "Here are the counterparty names saved", "same shop under two spellings")
    assert "- Talabat\n" in window and "- Talabat Egypt (aliases: TLBT*EG)" in window and "Keep: <the name to keep>" in window


def test_counterparties_with_one_name_has_nothing_to_clean_up(c):
    c.counterparties.create("Only Shop")
    assert "Here are the counterparty names saved" not in TestClient(create_app(c)).get("/counterparties").text


@pytest.fixture
def sample(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    return c


def test_spending_hands_over_its_categories_and_links_to_ask_an_ai(sample):
    client = TestClient(create_app(sample))
    page = client.get("/birdview/expenses?period=month&month=2026-09").text
    window = _is_hand_off(page, "I want to understand my spending from", "Want a second opinion on this period?")
    assert "Money out" in window and "2026-09-01" in window.replace("2026-09-01", "2026-09-01")
    assert "/settings/ask-ai?period=month&amp;month=2026-09" in page
    assert not re.search(r"\d{1,3}(,\d{3})+", window.split("categories my spending fell into", 1)[1].split("I will attach")[0])


def test_budget_hands_over_the_plans_own_words_before_the_question(sample):
    page = TestClient(create_app(sample)).get("/budget?month=2026-10").text
    window = _is_hand_off(page, "here is what its words mean", "pace, rolled over, held for")
    for word in ("- Pace:", "Carryover:", "- Held for:", "Left in plan:", "Everyday spending:"):
        assert word in window
    assert 'href="/settings/ask-ai"' in page


def test_every_prompt_builder_is_free_of_amounts():
    texts = [ai_prompts.rejected_csv_prompt("A", "EGP", ["Date", "Amount"], [("2", "Balance 1,250.50 and 12345 left")]),
             ai_prompts.counterparty_cleanup_prompt([{"id": 1, "name": "X", "active": True}], {}),
             ai_prompts.spending_prompt("2026-09-01", "2026-09-30", ["Food"], "EGP"),
             ai_prompts.budget_prompt(), ai_prompts.bank_category_prompt("CIB", "EGP", ["Food"])]
    for text in texts:
        assert not re.search(r"\d,\d{3}|\d\.\d{2}\b", text.replace("2026", "")), text[:60]


WHY_LINES = (
    "First import into this account? This prompt gives your AI tool what it cannot guess: your category names. It matches the bank’s own category words to them, so the review starts with your categories filled in.",
    "This prompt gives your AI tool what it cannot guess: your file’s header, what Lightning rejected and the columns it accepts. It fixes the file for you instead of you hunting for the problem.",
    "This prompt gives your AI tool what it cannot guess: your file’s header, what Lightning rejected on each line and the columns it accepts. It fixes the file for you instead of you hunting for the problem.",
    "Seen the same shop under two spellings? This prompt gives your AI tool your saved names and aliases, which it cannot guess. It answers with a list to paste into Add alias.",
    "Stuck on how to reach a target? This prompt explains the plan’s own words (pace, rolled over, held for) to your AI tool first, which it cannot guess. Its advice then fits your plan, not a generic budget.",
    "Add your numbers with Ask an AI",
    "Want a second opinion on this period? This prompt gives your AI tool Lightning’s own words and your category names, which it cannot guess. Add the numbers with",
)


def test_every_why_this_helps_line_has_an_arabic_string():
    for line in WHY_LINES:
        assert re.search(r"[؀-ۿ]", ARABIC_UI.get(line, "")), line


def test_the_ai_handoff_waits_below_the_answer_on_spending_and_counterparties(c, setup):  # F9 (r24)
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "120", cats["EXP.PERSONAL.FOOD"].id, counterparty="Spinneys")
    c.transactions.record_outflow("2026-10-06", accounts["cib"].id, "80", cats["EXP.PERSONAL.FOOD"].id, counterparty="Carrefour")
    client = TestClient(create_app(c))
    spending = client.get("/birdview/expenses?period=custom&date_from=2026-10-01&date_to=2026-10-31").text
    assert "Get another analysis" in spending and spending.index("By category") < spending.index("Get another analysis")
    names = client.get("/counterparties").text
    # Collapsed to one line: the explanation and the Copy/Edit buttons only show once it is opened.
    assert '<details class="ai-line ai-more"><summary>Get another analysis</summary>' in names
