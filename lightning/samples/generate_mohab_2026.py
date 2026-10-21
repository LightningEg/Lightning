"""Write Mohab's 2026 sample: one CSV per account, 1 January to 2 October 2026.

    python -m lightning.samples.generate_mohab_2026

The numbers are fixed (a seeded random generator), so the files only change when this script does.
Bank, cash and wallet accounts use Lightning's bank CSV format (Date, Amount, Counterparty, Category,
Notes), so they also go through Import CSV with nothing to review. A transfer says "Internal transfer"
in Category and names the other account in Counterparty. It is listed once, in the account the money
left; the account it went to gets it from that row, so import CIB Payroll first.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).parent / "mohab_2026"
FIRST, LAST = date(2026, 1, 1), date(2026, 10, 2)
MONTHS = [date(2026, m, 1) for m in range(1, 10)]

FOOD = "Personal › Food & Groceries"
OUT = "Personal › Eating Out"
MOVE = "Personal › Transportation"
HOME = "Personal › Housing & Rent"
BILLS = "Personal › Utilities & Bills"
GIFTS = "Personal › Gifts & Donations"
HEALTH = "Personal › Health"
FUN = "Personal › Entertainment"
SHOP = "Personal › Shopping"
OTHER = "Personal › Other Personal"
TRAVEL = FUN  # the Sahel weekend is entertainment (no Travel category by default)
FEES = "Personal › Fees & Charges"
LOAN = "System Categories › Loan payments"
HELD = "System Categories › Money Held for Others"
ZAKAT = "System Categories › Zakat"
INTERNAL = "Internal transfer"   # money moving between Mohab's own accounts


def money(value) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"


class Book:
    """Rows for one account; refuses a second row with the same date and amount (the importer
    would hold it back as a possible duplicate)."""

    def __init__(self):
        self.rows, self.seen = [], set()

    def add(self, day: date, amount, party: str, category: str = "", notes: str = ""):
        if day > LAST:
            return
        key = (day, money(amount))
        while key in self.seen:   # nudge by a piastre-free pound so every row stays importable
            amount = Decimal(str(amount)) + (-1 if Decimal(str(amount)) < 0 else 1)
            key = (day, money(amount))
        self.seen.add(key)
        self.rows.append((day.isoformat(), money(amount), party, category, notes))

    def write(self, name: str):
        with open(HERE / name, "w", newline="", encoding="utf-8") as f:
            out = csv.writer(f)
            out.writerow(("Date", "Amount", "Counterparty", "Category", "Notes"))
            out.writerows(sorted(self.rows))


def on(month: date, day: int) -> date:
    return month.replace(day=day)


def build() -> None:
    rnd = random.Random(2026)
    HERE.mkdir(exist_ok=True)
    cib, wallet, vodafone = Book(), Book(), Book()

    for i, m in enumerate(MONTHS):
        n = m.month
        salary = 45000 if n < 7 else 50000
        cib.add(on(m, 1), salary, "ACME Egypt", "Work › Salary", "Salary" if n != 7 else "Salary · new amount after the raise")
        cib.add(on(m, 2), -rnd.randint(2900, 3600) - rnd.choice((0, .25, .5, .75)), "Carrefour", FOOD)
        cib.add(on(m, 3), -12000, "Landlord", HOME, "Rent")
        cib.add(on(m, 5), -2500, "Toyota Finance", LOAN, f"Car loan · payment {n} of 24")
        cib.add(on(m, 5), -3000, "Cash wallet", INTERNAL, "ATM withdrawal")
        cib.add(on(m, 6), -1000, "Vodafone Cash", INTERNAL, "Top-up")
        cib.add(on(m, 8), -900, "Gold's Gym", HEALTH, "Membership")
        cib.add(on(m, 10), -rnd.randint(350, 650), "Talabat", OUT)
        cib.add(on(m, 12), -240, "Netflix", FUN)
        cib.add(on(m, 15), "1833.33", "NBE", "Investment › Interest", "Certificate interest")
        cib.add(on(m, 18), -rnd.randint(250, 500), "Talabat", OUT)
        cib.add(on(m, 20), -650, "WE Internet", BILLS)
        cib.add(on(m, 22), -rnd.randint(1200, 1600), "Seoudi", FOOD)
        cib.add(on(m, 24), -(420, 410, 440, 520, 640, 780, 910, 960, 720)[i], "North Cairo Electricity", BILLS)
        cib.add(on(m, 25), -2000, "Mom", GIFTS, "Monthly help")
        cib.add(on(m, 27), -rnd.randint(300, 700), "Uber", MOVE)
        cib.add(on(m, 28), -15, "CIB", FEES, "Monthly account fee")

        # Cash: the small things.
        for day in (4, 13, 23):
            wallet.add(on(m, day + 1), -rnd.randint(150, 220), "Koshary El Tahrir", OUT)
        for day in (7, 11, 16, 26):
            wallet.add(on(m, day), -rnd.randint(40, 90), "Microbus", MOVE)
        wallet.add(on(m, 9), -rnd.randint(300, 500), "Souq El Obour", FOOD, "Fruit and vegetables")
        wallet.add(on(m, 19), -rnd.randint(60, 150), "Kiosk", FOOD)
        wallet.add(on(m, 21), -150, "Barber", OTHER)
        wallet.add(on(m, 28), -200, "Bawab", GIFTS, "Building doorman")

        # Vodafone Cash: phone, a streaming plan and splitting dinners.
        vodafone.add(on(m, 9), -350, "Vodafone", BILLS, "Mobile bill")
        vodafone.add(on(m, 14), -99, "Shahid", FUN)
        vodafone.add(on(m, 17), -rnd.randint(200, 420), "Instapay · Karim", OUT, "Dinner split")

    # One-offs through the year.
    cib.add(date(2026, 1, 14), -2450, "Noon", SHOP, "Winter jacket")
    cib.add(date(2026, 2, 10), -20000, "THNDR", INTERNAL, "Transfer to THNDR")
    for day, amount in ((19, -780), (24, -1150), (3, -960)):   # Ramadan iftars out
        cib.add(date(2026, 2 if day > 15 else 3, day), amount, "Abou El Sid", OUT, "Iftar")
    cib.add(date(2026, 3, 17), -3200, "Zara", SHOP, "Eid clothes #eid")
    cib.add(date(2026, 3, 26), 90000, "ACME Egypt", "Work › Bonus", "Annual bonus")
    cib.add(date(2026, 4, 9), 10000, "Mom", HELD, "Mom's savings, kept for her")
    cib.add(date(2026, 4, 15), -1299, "Amazon", SHOP, "Headphones")
    cib.add(date(2026, 5, 3), 1299, "Amazon", SHOP, "Headphones returned")
    cib.add(date(2026, 5, 12), -15000, "THNDR", INTERNAL, "Transfer to THNDR")
    cib.add(date(2026, 5, 26), -6500, "Al Orman", GIFTS, "Eid al-Adha udhiya share")
    cib.add(date(2026, 6, 8), -1200, "Uber", "Work › Transportation", "Client visit")
    cib.add(date(2026, 6, 21), 1200, "ACME Egypt", "Work › Transportation", "Client visit reimbursed")
    cib.add(date(2026, 7, 20), -6500, "Al Mansour Service", MOVE, "Car service")
    cib.add(date(2026, 8, 5), -10000, "THNDR", INTERNAL, "Transfer to THNDR")
    cib.add(date(2026, 8, 12), -14200, "Hacienda Bay", TRAVEL, "Sahel weekend")
    cib.add(date(2026, 8, 20), -4000, "Mom", HELD, "Mom took back part of her savings")
    cib.add(date(2026, 9, 10), -1800, "Smile Dental", HEALTH, "Dentist")
    cib.add(date(2026, 10, 1), 50000, "ACME Egypt", "Work › Salary", "Salary")
    cib.add(date(2026, 10, 2), -rnd.randint(2900, 3600), "Carrefour", FOOD)
    wallet.add(date(2026, 3, 20), -2000, "Eidiya", GIFTS, "Eid al-Fitr #eid")
    wallet.add(date(2026, 3, 21), 1000, "Uncle Hassan", "Personal › Gifts Received", "Eidiya #eid")
    wallet.add(date(2026, 5, 27), -1500, "Eidiya", GIFTS, "Eid al-Adha #eid")
    # Features beyond the monthly routine. The phone has no category: the rule the loader saves files it.
    cib.add(date(2026, 6, 15), -12000, "Vodafone", "", "New phone")
    cib.add(date(2026, 8, 5), -25, "CIB", FEES, "ATM fee")
    cib.add(date(2026, 9, 20), -1000, "Charity", ZAKAT, "Zakat on gold")
    for n, month in enumerate((7, 8, 9), start=1):   # a laptop on 12 instalments of 2,000 from valU
        cib.add(date(2026, month, 28), -2000, "valU", LOAN, f"Laptop instalments · payment {n} of 12")

    cib.write("cib-payroll.csv")
    wallet.write("cash-wallet.csv")
    vodafone.write("vodafone-cash.csv")

    with open(HERE / "accounts.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Name", "Type", "Institution", "Opening balance", "Opening date", "File", "Currency"))
        # CIB opens with the 100,000 that buys the NBE certificate on the first day.
        out.writerows((("CIB Payroll", "BANK", "CIB", "152000.00", FIRST.isoformat(), "cib-payroll.csv", ""),
                       ("Cash wallet", "CASH", "", "1500.00", FIRST.isoformat(), "cash-wallet.csv", ""),
                       ("Vodafone Cash", "CASH", "", "400.00", FIRST.isoformat(), "vodafone-cash.csv", ""),
                       ("THNDR", "BROKERAGE", "THNDR", "0.00", FIRST.isoformat(), "thndr.csv", ""),
                       ("NBE 3-year certificate", "DEPOSIT", "NBE", "0.00", FIRST.isoformat(),
                        "nbe-3-year-certificate.csv", ""),
                       ("Gold at home", "PHYSICAL_ASSET", "", "0.00", FIRST.isoformat(), "gold-at-home.csv", ""),
                       # Dollars he already had: the account opens with them. TODO(package B): fund it by converting
                       # pounds (CNV) once conversion exists; until then the dollars arrive as an opening balance.
                       ("Dollar brokerage", "BROKERAGE", "", "2000.00", FIRST.isoformat(), "usd-brokerage.csv", "USD")))

    # A Nasdaq ETF bought with those dollars (Exchange is the ISO 10383 code, so the asset is in USD).
    with open(HERE / "usd-brokerage.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Date", "Action", "Investment", "Ticker", "Class", "Exchange", "Units", "Total", "Fees", "Notes"))
        out.writerow(("2026-03-12", "Buy", "Invesco NASDAQ 100 ETF", "QQQM", "FUND.EQUITY", "XNAS", "8", "1765.00",
                      "5.00", "In dollars"))

    # What a dollar cost in pounds on each month-end (typed rates; the sample has no live source).
    with open(HERE / "fx.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Date", "Currency", "Rate"))
        out.writerow(("2026-01-01", "USD", "49.80"))
        for m, rate in zip(MONTHS, ("50.10", "50.35", "50.60", "50.85", "51.00", "51.20", "51.30", "51.45", "51.60")):
            out.writerow(((m + timedelta(days=32)).replace(day=1) - timedelta(days=1), "USD", rate))

    # A CD portfolio holds certificates, not cash: one bought from CIB, paying 22% a year monthly into
    # CIB (the 1,833.33 "Certificate interest" rows in cib-payroll.csv).
    with open(HERE / "nbe-3-year-certificate.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Date", "Certificate", "Principal", "Annual rate", "Interest", "Payout", "Earliest withdrawal",
                      "Maturity", "Paid from", "Interest to"))
        out.writerow(("2026-01-01", "NBE 3-year certificate · 22%", "100000.00", "22", "SIMPLE", "MONTHLY",
                      "2027-01-01", "2029-01-01", "CIB Payroll", "CIB Payroll"))

    with open(HERE / "thndr.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Date", "Action", "Investment", "Ticker", "Class", "Units", "Total", "Fees", "Notes"))
        out.writerows((
            ("2026-02-11", "Buy", "Commercial International Bank (COMI)", "COMI", "STOCK", "120", "9840.00", "30.00", ""),
            ("2026-02-11", "Buy", "Fawry for Banking Technology", "FWRY", "STOCK", "600", "5100.00", "20.00", ""),
            ("2026-02-12", "Buy", "Azimut money market fund", "AZMM", "FUND.MONEY_MARKET", "40", "4800.00", "0.00", ""),
            ("2026-05-13", "Buy", "Talaat Moustafa Group", "TMGH", "STOCK", "150", "9300.00", "28.00", ""),
            ("2026-05-13", "Buy", "Azimut money market fund", "AZMM", "FUND.MONEY_MARKET", "40", "5000.00", "0.00", ""),
            ("2026-06-20", "Dividend", "Commercial International Bank (COMI)", "COMI", "STOCK", "", "360.00", "", "Cash dividend"),
            ("2026-08-06", "Buy", "Commercial International Bank (COMI)", "COMI", "STOCK", "60", "5280.00", "18.00", ""),
            ("2026-09-14", "Sell", "Fawry for Banking Technology", "FWRY", "STOCK", "300", "2850.00", "12.00", "Took some profit"),
        ))

    with open(HERE / "gold-at-home.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Date", "Action", "Piece", "Kind", "Grams", "Karat", "Total", "Workmanship", "Paid from", "Notes"))
        out.writerows((
            ("2026-01-01", "Already owned", "Gold pound (from grandma)", "Coin", "8", "21", "29000.00", "0.00", "", "Inherited"),
            ("2026-02-14", "Buy", "L'Azurde ring", "Ring", "4.3", "21", "18450.00", "1950.00", "CIB Payroll", "Paid by card"),
            ("2026-06-10", "Buy", "BTC 10 g bar", "Bar", "10", "24", "52000.00", "600.00", "CIB Payroll", "Savings in gold"),
        ))

    # Month-end prices, and the price on each trade date. Gold is per gram for its karat.
    gold21 = (3600, 3680, 3800, 3950, 3900, 4050, 4200, 4350, 4650)
    series = {"COMI": (80.5, 82.4, 84.1, 83.0, 86.2, 88.0, 87.1, 90.4, 92.0),
              "FWRY": (8.40, 8.62, 8.90, 9.10, 9.02, 9.31, 9.60, 9.44, 9.80),
              "TMGH": (None, None, None, None, 62.0, 64.1, 61.5, 66.0, 68.2),
              "AZMM": (None, 120.6, 121.7, 122.8, 125.2, 126.3, 127.4, 128.6, 129.7),
              "QQQM": (None, None, 220.5, 218.1, 226.4, 231.0, 238.2, 241.7, 247.3),   # dollars
              "GOLD21": gold21,
              "GOLD24": tuple(round(p * 24 / 21, -1) for p in gold21)}
    with open(HERE / "prices.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(("Date", "Ticker", "Price"))
        for i, m in enumerate(MONTHS):
            month_end = (m + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            for ticker, prices in series.items():
                if prices[i] is not None:
                    out.writerow((month_end.isoformat(), ticker, f"{prices[i]}"))


if __name__ == "__main__":
    build()
    print(f"Wrote {sorted(p.name for p in HERE.glob('*.csv'))}")
