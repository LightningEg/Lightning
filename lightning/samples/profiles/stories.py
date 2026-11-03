"""Four rich fictional Egyptian sample stories for the empty-profile welcome screen."""
from __future__ import annotations

from datetime import date

from lightning.core.dates import fmt_date, today


# Published personas and the analysis case each is meant to make visible.  Values cover Jan–Oct 2026.
STORY_PROFILES = {
    "amr": {"name": "Amr", "label": "Cash flow", "title": "The resourceful side hustler",
              "opening": "28000", "income": [14500] * 10, "income_category": "EXP.WORK.SALARY",
              "income_counterparty": "Engineering salary", "income_days": [25] * 10,
              "extra_category": "EXP.WORK.BUSINESS",
              "extra_counterparty": "Side project commission",
              "extra": [0, 7000, 0, 12000, 0, 22000, 0, 9000, 0, 16000],
              "expenses": [
                  ("EXP.PERSONAL.HOUSING", "Landlord", [6200] * 10, 3),
                  ("EXP.PERSONAL.FOOD", "Carrefour Market", [2200, 2300, 2250, 2400, 2450, 2300, 2350, 2300, 2500, 2400], 6),
                  ("EXP.PERSONAL.FOOD", "Local bakery and groceries", [900, 950, 1000, 950, 1050, 1000, 1050, 1000, 1100, 1050], 19),
                  ("EXP.PERSONAL.TRANSPORT", "Metro and microbus", [1000, 1050, 1100, 1000, 1100, 1150, 1050, 1100, 1150, 1100], 8),
                  ("EXP.PERSONAL.UTILITIES", "North Cairo Electricity", [350, 380, 360, 400, 390, 420, 380, 400, 420, 410], 12),
                  ("EXP.PERSONAL.UTILITIES", "WE internet", [450] * 10, 14),
                  ("EXP.PERSONAL.UTILITIES", "Vodafone mobile", [300] * 10, 16),
                  ("EXP.PERSONAL.GIFTS", "Family support", [800, 800, 1000, 800, 900, 800, 1000, 800, 900, 900], 25),
                  ("EXP.PERSONAL.HEALTH", "El Ezaby Pharmacy", [0, 250, 0, 350, 0, 300, 0, 250, 0, 400], 10),
                  ("EXP.PERSONAL.DINING", "Local café", [300, 350, 300, 400, 350, 400, 350, 300, 450, 400], 23),
                  ("EXP.WORK.OTHER", "Resale stock supplier", [0, 0, 5200, 0, 0, 0, 4800, 0, 0, 0], 21),
              ],
              "question": "Which months did resale-stock costs push cash flow below zero?"},
    "abdelrahman": {"name": "Abdelrahman", "label": "Consistency", "title": "The steady engineer",
                      "opening": "60000", "income": [32000] * 5 + [34000] * 3 + [36000] * 2,
                      "income_category": "EXP.WORK.SALARY", "income_counterparty": "Engineering salary",
                      "income_days": [25] * 10,
                      "extra_category": "EXP.WORK.BONUS", "extra_counterparty": "Performance bonus",
                      "extra": [0, 0, 0, 0, 12000, 0, 0, 0, 0, 0],
                      "investment": [6000] * 5 + [7000] * 3 + [8500] * 2,
                      # Modest Cairo/Giza costs with locally familiar billers, plus the June laptop
                      # and weekend outing from the published brief. June spending exceeds income.
                      "expenses": [
                          ("EXP.PERSONAL.HOUSING", "Landlord", [9000] * 10, 3),
                          ("EXP.PERSONAL.FOOD", "Carrefour Market", [3200, 3400, 3300, 3500, 3600, 3400, 3500, 3450, 3650, 3500], 6),
                          ("EXP.PERSONAL.FOOD", "Seoudi groceries", [1500, 1650, 1600, 1550, 1700, 1650, 1750, 1600, 1800, 1700], 20),
                          ("EXP.PERSONAL.DINING", "Local café and takeaway", [550, 500, 650, 600, 550, 700, 550, 500, 650, 600], 23),
                          ("EXP.PERSONAL.TRANSPORT", "Metro and microbus", [1400, 1450, 1500, 1450, 1550, 1550, 1500, 1600, 1550, 1600], 8),
                          ("EXP.PERSONAL.UTILITIES", "North Cairo Electricity", [450, 500, 470, 520, 480, 550, 500, 510, 530, 520], 12),
                          ("EXP.PERSONAL.UTILITIES", "WE home internet", [600] * 10, 14),
                          ("EXP.PERSONAL.UTILITIES", "Vodafone mobile", [350] * 10, 16),
                          ("EXP.PERSONAL.UTILITIES", "Natural gas", [220, 230, 210, 240, 230, 210, 220, 230, 240, 230], 18),
                          ("EXP.PERSONAL.HEALTH", "El Ezaby Pharmacy", [250, 0, 420, 0, 300, 650, 0, 350, 0, 300], 10),
                          ("EXP.PERSONAL.HEALTH", "Local clinic", [0, 0, 0, 0, 0, 0, 0, 0, 450, 0], 11),
                          ("EXP.PERSONAL.SHOPPING", "Personal care and household items", [500, 650, 550, 600, 750, 700, 550, 650, 800, 650], 21),
                          ("EXP.PERSONAL.GIFTS", "Family support and Eid visits", [900, 1100, 1500, 1200, 1000, 900, 1200, 900, 1500, 1000], 25),
                          ("EXP.PERSONAL.EDUCATION", "Online technical course", [0, 450, 0, 450, 0, 450, 0, 450, 0, 450], 26),
                          ("EXP.PERSONAL.ENTERTAINMENT", "Weekend with friends", [450, 500, 500, 550, 550, 3000, 500, 500, 600, 550], 27),
                          ("EXP.PERSONAL.FEES", "CIB account fees", [100] * 10, 28),
                          ("EXP.PERSONAL.SHOPPING", "Laptop replacement", [0, 0, 0, 0, 0, 14500, 0, 0, 0, 0], 24),
                      ],
                      "question": "Did June's laptop and weekend erase his surplus, and did he keep investing?"},
    "menna": {"name": "Menna", "label": "Safety", "title": "The freelance artist",
                "opening": "60000", "income": [12000, 26000, 0, 33000, 8000, 0, 28000, 15000, 0, 24000],
                "income_category": "EXP.WORK.BUSINESS", "income_counterparty": "Illustration client invoice",
                "income_days": [12, 23, 0, 26, 28, 0, 22, 14, 0, 25],
                "income_counterparties": ["Alexandria design studio", "Cairo advertising agency", "",
                                          "Local restaurant branding", "Small business illustration", "",
                                          "Cairo advertising agency", "Alexandria design studio", "",
                                          "Local restaurant branding"],
                "extra": [0] * 10,
                "expenses": [
                    ("EXP.PERSONAL.HOUSING", "Alexandria landlord", [6500] * 10, 3),
                    ("EXP.PERSONAL.FOOD", "Carrefour Market", [2500, 2700, 2400, 2800, 2600, 2450, 2750, 2600, 2500, 2700], 6),
                    ("EXP.PERSONAL.FOOD", "Local produce and bakery", [900, 950, 850, 1000, 950, 900, 1000, 950, 900, 1000], 19),
                    ("EXP.PERSONAL.TRANSPORT", "Tram and microbus", [950, 1000, 900, 1100, 1000, 950, 1100, 1000, 950, 1050], 8),
                    ("EXP.PERSONAL.UTILITIES", "Alexandria Electricity", [400, 450, 420, 480, 460, 430, 480, 450, 430, 470], 12),
                    ("EXP.PERSONAL.UTILITIES", "WE internet", [600] * 10, 14),
                    ("EXP.PERSONAL.UTILITIES", "Vodafone mobile", [350] * 10, 16),
                    ("EXP.PERSONAL.HEALTH", "Pharmacy", [250, 0, 300, 0, 450, 0, 250, 0, 350, 0], 10),
                    ("EXP.PERSONAL.DINING", "Coffee with a client", [250, 350, 0, 400, 250, 0, 450, 300, 0, 400], 23),
                    ("EXP.PERSONAL.GIFTS", "Family visits", [500, 500, 600, 500, 500, 500, 600, 500, 500, 600], 25),
                    ("EXP.WORK.OFFICE", "Art supplies", [1200, 1800, 900, 2400, 1500, 1100, 2100, 1700, 1000, 1900], 21),
                    ("EXP.WORK.SOFTWARE", "Design software", [450] * 10, 26),
                ],
                "question": "How do zero-invoice months affect cash flow, and how far is her EGP 4,000 reserve from its EGP 60,000 goal?"},
    "fatma": {"name": "Fatma", "label": "Emergency reserve", "title": "The household organiser",
                "opening": "30000", "income": [18000] * 10, "income_category": "EXP.WORK.SALARY",
                "income_counterparty": "Monthly salary", "income_days": [25] * 10, "extra": [0] * 10,
                "expenses": [
                    ("EXP.PERSONAL.HOUSING", "Landlord", [6000] * 10, 3),
                    ("EXP.PERSONAL.FOOD", "Carrefour Market", [3000, 3100, 3000, 3200, 3100, 3000, 3200, 3100, 3000, 3150], 6),
                    ("EXP.PERSONAL.FOOD", "Local groceries and bakery", [1200, 1250, 1300, 1200, 1250, 1300, 1250, 1300, 1250, 1300], 19),
                    ("EXP.PERSONAL.TRANSPORT", "Metro and microbus", [800, 850, 850, 900, 850, 900, 850, 900, 850, 900], 8),
                    ("EXP.PERSONAL.UTILITIES", "North Cairo Electricity", [500, 550, 520, 580, 560, 600, 550, 580, 600, 580], 12),
                    ("EXP.PERSONAL.UTILITIES", "WE internet and landline", [650] * 10, 14),
                    ("EXP.PERSONAL.UTILITIES", "Gas and water", [350, 360, 350, 380, 370, 360, 380, 370, 360, 380], 16),
                    ("EXP.PERSONAL.HEALTH", "Pharmacy and clinic", [400, 450, 400, 500, 450, 500, 450, 500, 450, 500], 10),
                    ("EXP.PERSONAL.EDUCATION", "School supplies and activities", [1100, 900, 900, 1100, 1000, 900, 1100, 900, 900, 1100], 21),
                    ("EXP.PERSONAL.SHOPPING", "Household supplies", [500, 550, 500, 550, 600, 550, 500, 600, 550, 600], 23),
                    ("EXP.PERSONAL.GIFTS", "Family support and visits", [700, 700, 900, 700, 700, 700, 900, 700, 700, 800], 25),
                    ("EXP.PERSONAL.FOOD", "Neighborhood market top-ups", [1700, 1700, 1800, 1700, 1800, 1800, 1700, 1800, 1700, 1800], 26),
                    ("EXP.PERSONAL.UTILITIES", "Vodafone mobile", [350] * 10, 18),
                    ("EXP.PERSONAL.OTHER", "Refrigerator repair", [0, 0, 0, 0, 0, 7800, 0, 0, 0, 0], 24),
                ],
                "question": "What does a EGP 7,800 refrigerator repair do to a near-balanced household budget?"},
}


def sample_stories(keys: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    """The stories to offer, in the order of `keys` (all of them when none is given)."""
    chosen = keys if keys is not None else tuple(STORY_PROFILES)
    return [{"key": key, "name": STORY_PROFILES[key]["name"], "label": STORY_PROFILES[key]["label"],
             "title": STORY_PROFILES[key]["title"], "question": STORY_PROFILES[key]["question"]}
            for key in chosen if key in STORY_PROFILES]


def load_story(c, key: str, as_of: date | None = None) -> dict:
    """Load a rich fictional 2026 story into an empty profile; no external test/CSV files needed."""
    if c.accounts.list():
        raise ValueError("A sample story can only be added to an empty Lightning.")
    story = STORY_PROFILES.get(key)
    if story is None:
        raise ValueError("There is no such sample story.")
    day = min(as_of or today(), date(2026, 10, 31))
    day = max(day, date(2026, 1, 1))
    used_categories = {code for code, _, _, _ in story.get("expenses", [])}
    used_categories.update(("EXP.WORK.SALARY", "EXP.WORK.BONUS", "EXP.WORK.BUSINESS", "EXP.PERSONAL.HOUSING",
                            "EXP.PERSONAL.FOOD", "EXP.PERSONAL.UTILITIES", "EXP.PERSONAL.SHOPPING",
                            "EXP.INVEST.INTEREST"))
    category = {code: c.categories.get_by_code(code).id for code in used_categories}
    with c.db.transaction():
        account_name = {"amr": "NBE Current Account", "abdelrahman": "CIB Current Account",
                        "menna": "AlexBank Current Account", "fatma": "Banque Misr Current Account"}[key]
        bank = c.account_flows.open_account(account_name, "BANK", "2026-01-01", story["opening"],
                                            institution={"amr": "NBE", "abdelrahman": "CIB",
                                                         "menna": "AlexBank", "fatma": "Banque Misr"}[key])
        brokerage = equity_fund = None
        if key == "abdelrahman":
            brokerage = c.account_flows.open_account("THNDR Portfolio", "BROKERAGE", "2026-01-01", "0",
                                                     institution="THNDR")
            equity_fund = c.assets.create_investment("Illustrative Egyptian Equity Fund", "FUND.EQUITY", "SAMPLEEQ")
        posted = 0
        for month in range(1, 11):
            if date(2026, month, 1) > day:
                break
            income_day = story.get("income_days", [1] * 10)[month - 1]
            income_date = date(2026, month, income_day) if income_day else None
            income = story["income"][month - 1]
            if income and income_date and income_date <= day:
                c.transactions.record_inflow(fmt_date(income_date), bank.id, str(income),
                                             category[story.get("income_category", "EXP.WORK.SALARY")],
                                             counterparty=(story.get("income_counterparties", [])[month - 1]
                                                           if story.get("income_counterparties") else
                                                           story.get("income_counterparty", "Salary or client payment")))
                posted += 1
            extra = story["extra"][month - 1]
            extra_date = date(2026, month, 15)
            if extra and extra_date <= day:
                c.transactions.record_inflow(fmt_date(extra_date), bank.id, str(extra),
                                             category[story.get("extra_category", "EXP.WORK.BUSINESS")],
                                             counterparty=story.get("extra_counterparty", "Side project"))
                posted += 1
            for category_code, counterparty, amounts, day_of_month in story["expenses"]:
                when = date(2026, month, day_of_month)
                amount = amounts[month - 1]
                if amount and when <= day:
                    c.transactions.record_outflow(fmt_date(when), bank.id, str(amount), category[category_code],
                                                  counterparty=counterparty)
                    posted += 1
            invest_date = date(2026, month, 25)
            if brokerage is not None and equity_fund is not None and invest_date <= day:
                contribution = story["investment"][month - 1]
                c.transactions.record_transfer(fmt_date(invest_date), bank.id, brokerage.id, str(contribution))
                c.investments.buy_total(fmt_date(invest_date), brokerage.id, equity_fund.id,
                                        str(contribution / 100), str(contribution), notes="Monthly investment")
                c.assets.set_price(equity_fund.id, fmt_date(invest_date), str(100 + month * 2))
                posted += 2
        month = fmt_date(day)[:7]
        suggested = c.budgets.suggested_plan(month)
        if suggested:
            c.budgets.save_month(month, suggested, schedule=c.schedules.view())
        if key == "menna":
            c.reserves.set_emergency_fund("4000", "60000")
        elif key == "fatma":
            c.reserves.set_emergency_fund("7800", "54000")
    return {"name": story["name"], "accounts": len(c.accounts.list()), "rows": posted,
            "from": "2026-01-01", "to": fmt_date(day)}
