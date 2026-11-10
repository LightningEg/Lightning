from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from lightning.workflows.ai_analysis import AIAnalysisService
from lightning.ui.periods import parse_period
from lightning.core.dates import today


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _sheet_rows(archive: ZipFile, path: str) -> list[list[str]]:
    root = ET.fromstring(archive.read(path))
    result = []
    for row in root.findall(f".//{{{NS}}}row"):
        values = []
        for cell in row.findall(f"{{{NS}}}c"):
            inline = cell.find(f"{{{NS}}}is/{{{NS}}}t")
            values.append(inline.text if inline is not None else cell.findtext(f"{{{NS}}}v"))
        result.append(values)
    return result


def test_workbook_preserves_ownership_and_marks_all_finance_events(c):
    bank = c.account_flows.open_account("CIB", "BANK", "2026-08-01", "5000")
    wallet = c.account_flows.open_account("Wallet", "CASH", "2026-08-01", "0")
    broker = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-08-01", "5000")
    dad_id = c.counterparties.create("Dad")
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")

    stock = c.assets.create_investment("Test company", "STOCK", "TEST")
    missing_fund = c.assets.create_investment("No price fund", "FUND.EQUITY", "NOFEED")
    c.investments.buy("2026-08-15", broker.id, stock.id, "10", "100")
    c.assets.set_price(stock.id, "2026-08-31", "105")
    assert c.reevaluations.process_date("2026-08-31", "MONTH_END")

    c.transactions.record_inflow("2026-09-03", bank.id, "300", salary.id)
    c.transactions.record_outflow("2026-09-04", bank.id, "100", food.id)
    c.transactions.record_refund("2026-09-05", bank.id, "20", food.id)
    c.transactions.record_transfer("2026-09-06", bank.id, wallet.id, "100")
    assignment = c.transactions.change_cash_ownership("2026-09-07", bank.id, "50", None, dad_id)
    externally_paid = c.transactions.record_expense_paid_by_person("2026-09-08", bank.id, "25", dad_id, food.id)

    c.investments.buy("2026-09-10", broker.id, stock.id, "2", "110")
    c.investments.buy("2026-09-11", broker.id, missing_fund.id, "2", "25")
    c.investments.dividend("2026-09-12", broker.id, stock.id, "20")
    c.investments.sell("2026-09-20", broker.id, stock.id, "2", "120")
    c.assets.set_price(stock.id, "2026-09-30", "115")
    assert not c.reevaluations.process_date("2026-09-30", "MONTH_END")

    period = parse_period({"period": "custom", "date_from": "2026-09", "date_to": "2026-09"},
                          today(), "2026-08-01")
    service = AIAnalysisService(c)
    workbook, filename, snapshot = service.build(period)
    prompt = service.prompt(period, filename, snapshot)
    assert filename == "lightning-analysis-2026-09-01-to-2026-09-30.xlsx"
    assert "2026-09-01 to 2026-09-30 inclusive" in prompt
    assert "Categories used in the exported activity" in prompt
    assert "Do not count a reevaluation checkpoint and its aggregated VAL journal twice" in prompt
    assert "Do not calculate XIRR" in prompt and "Report missing prices" in prompt

    with ZipFile(BytesIO(workbook)) as archive:
        sheets = ET.fromstring(archive.read("xl/workbook.xml"))
        assert [sheet.attrib["name"] for sheet in sheets.findall(f".//{{{NS}}}sheet")] == [
            "Summary", "Transactions", "Investment history", "Categories"]
        transactions = _sheet_rows(archive, "xl/worksheets/sheet2.xml")
        columns = {name: index for index, name in enumerate(transactions[0])}
        roles = [row[columns["Analysis role"]] for row in transactions[1:]]
        assert {"transfer", "refund", "investment contribution", "investment sale", "dividend",
                "ownership change", "expense paid externally", "valuation journal"} <= set(roles)
        assert "custody entry" not in roles
        ownership_rows = [row for row in transactions[1:] if row[columns["Analysis role"]] == "ownership change"]
        assert len(ownership_rows) == 1
        assert len([row for row in transactions[1:] if row[columns["Transaction ID"]] == str(assignment.id)]) == 1
        assert len([row for row in transactions[1:] if row[columns["Transaction ID"]] == str(externally_paid.id)]) == 1
        assert [row for row in transactions[1:] if row[columns["Transaction ID"]] == str(externally_paid.id)][0][
            columns["Analysis role"]] == "expense paid externally"
        investment = _sheet_rows(archive, "xl/worksheets/sheet3.xml")
        assert any(row[1] == "OPENING_CONTEXT" for row in investment[1:])
        investment_columns = {name: index for index, name in enumerate(investment[0])}
        assert any(row[investment_columns["Missing price"]] == "yes" for row in investment[1:])
        summary = _sheet_rows(archive, "xl/worksheets/sheet1.xml")
        assert any(row[0] == "Investment period result" and row[1] is None for row in summary[1:])
