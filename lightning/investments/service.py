"""Public API of the investments module: buy, sell, dividends, holdings you already own, and positions.

It builds ledger lines and hands them to TransactionService.post(), so every rule of the core applies
(internal lines net to zero, no future dates, no holding below zero units).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from dataclasses import replace

from lightning.accounts.domain import INVESTMENT_ACCOUNT_TYPES, Account, AccountType
from lightning.accounts.service import AccountService
from lightning.assets.domain import EXPOSURE_LABELS, FinancialAsset
from lightning.assets.service import AssetService
from lightning.categories.service import CategoryService
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import ConflictError, ValidationError
from lightning.core.ledger import Effect, PostingLine
from lightning.core.money import ZERO, check_places, from_e6, to_decimal
from lightning.core.refs import DocType
from lightning.database.connection import Database
from lightning.reporting.service import ReportingService
from lightning.transactions.domain import Transaction
from lightning.transactions.service import TransactionService

from . import events
from .domain import Portfolio, Position, default_sale_factor
from .lots import SPLIT_MARK, LotLine, build_lots, lot_type
from .xirr import solve_xirr
from .returns import display_return

DIVIDEND_CATEGORY = events.DIVIDEND_CATEGORY
INTEREST_CATEGORY = "EXP.INVEST.INTEREST"
TAX_CATEGORY = events.TAX_CATEGORY
FEE_CATEGORY = "EXP.INVEST.FEES"  # a broker's own charge: custody, data, inactivity
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _num(value: Decimal) -> str:
    """Short number for descriptions: 100, 95.5, 0.125."""
    text = f"{value.normalize():f}"
    return text


PRICE_REFERENCE_CODES = ("GLD:18K", "REF:GLD-21K", "REF:GLD-24K")  # seeded in database/seed.py


class SaleReevaluation(Protocol):
    def process_sale(self, day: str, account_id: int, asset_id: int, price: Decimal,
                     owner_id: int | None = None) -> bool: ...


class InvestmentService:
    def __init__(self, db: Database, accounts: AccountService, assets: AssetService, categories: CategoryService,
                 transactions: TransactionService, reporting: ReportingService, reevaluations: SaleReevaluation):
        if not callable(getattr(reevaluations, "process_sale", None)):
            raise TypeError("reevaluations must provide process_sale")
        self.db = db
        self.accounts = accounts
        self.assets = assets
        self.categories = categories
        self.transactions = transactions
        self.reporting = reporting
        self.reevaluations = reevaluations

    def own_liquidation_factors(self) -> dict[int, Decimal]:
        """Factors set on a class itself, keyed by asset-class ID. A class without one inherits."""
        return {int(row["asset_class_id"]): Decimal(str(row["factor"]))
                for row in self.db.all("SELECT asset_class_id,factor FROM investment_liquidation_factors")}

    def liquidation_factors(self) -> dict[int, Decimal]:
        """The factor each class uses, keyed by asset-class ID: its own, else its nearest parent's,
        else the 95% default. So a value on Funds applies to every fund left empty."""
        return {class_id: factor for class_id, (factor, _) in self.sale_factor_sources().items()}

    def sale_factor_sources(self) -> dict[int, tuple[Decimal, int | None]]:
        """class ID -> (factor used, ID of the class it comes from; None for the default)."""
        own = self.own_liquidation_factors()
        classes = {cls.id: cls for cls in self.assets.list_classes()}
        result = {}
        for cls in classes.values():
            current = cls
            while current is not None and current.id not in own:
                current = classes.get(current.parent_id) if current.parent_id else None
            result[cls.id] = ((own[current.id], current.id) if current is not None
                              else (default_sale_factor(cls.code), None))
        return result

    def set_all_liquidation_factors(self, factor) -> None:
        """Apply one estimate factor to each class with a non-cash asset."""
        value = to_decimal(factor, "factor")
        if not ZERO <= value <= Decimal(100):
            raise ValidationError("Enter a liquidation factor from 0 to 100.", "factor")
        for class_id in {asset.asset_class_id for asset in self.assets.list_assets() if not asset.is_cash}:
            self.set_liquidation_factor(class_id, value)

    def set_liquidation_factor(self, asset_class_id: int, factor) -> None:
        """Set an estimate factor for an active, non-cash investment class."""
        cls = self.assets.get_class(asset_class_id)
        allowed = {item.id for item in self.assets.list_classes()
                   if item.active and item.root_code != "CASH" and item.code != "CUSTODY"}
        if cls.id not in allowed:
            raise ValidationError("Choose an investment asset class.")
        if str(factor or "").strip() == "":  # empty: use the parent class's factor again
            self.db.execute("DELETE FROM investment_liquidation_factors WHERE asset_class_id=?", (asset_class_id,))
            return
        value = to_decimal(factor, "factor")
        if not ZERO <= value <= Decimal(100):
            raise ValidationError("Enter a liquidation factor from 0 to 100.")
        self.db.execute(
            "INSERT INTO investment_liquidation_factors(asset_class_id,factor) VALUES(?,?) "
            "ON CONFLICT(asset_class_id) DO UPDATE SET factor=excluded.factor",
            (asset_class_id, float(value)),
        )

    def target_weights(self) -> dict[str, Decimal]:
        return {row["bucket"]: Decimal(str(row["target_weight"]))
                for row in self.db.all("SELECT bucket,target_weight FROM investment_targets")}

    def set_target_weight(self, bucket: str, weight: Decimal, class_id: int) -> None:
        self.db.execute(
            "INSERT INTO investment_targets(bucket,target_weight,updated_at,asset_class_id) VALUES(?,?,?,?) "
            "ON CONFLICT(bucket) DO UPDATE SET target_weight=excluded.target_weight,"
            "updated_at=excluded.updated_at,asset_class_id=excluded.asset_class_id",
            (bucket, float(weight), fmt_date(today()), class_id),
        )

    def clear_target_weight(self, bucket: str) -> None:
        self.db.execute("DELETE FROM investment_targets WHERE bucket=?", (bucket,))

    def report_transactions(self, kind: str, start: str, end: str):
        """Posted source transactions behind a portfolio report detail."""
        if kind == "flows":
            return self.money_added_transactions(start, end)
        type_filter = ("t.type='DIV'" if kind == "dividends" else
                       "t.type='SEL'" if kind == "sales" else
                       "(t.type IN ('SEL','DIV') OR c.code IN ('EXP.INVEST.DIVIDEND','EXP.INVEST.INTEREST') OR "
                       "(c.code='EXP.INVEST.FEES' AND le.account_id IN (SELECT id FROM accounts "
                       "WHERE account_type='BROKERAGE')))"
                       if kind == "result" else
                       "t.type IN ('BUY','SEL','TRF','IN','OUT','ADJ')")
        return self.db.all(
            "SELECT DISTINCT t.id,t.ref,t.date,t.type,t.description,t.counterparty, "
            "CASE WHEN t.type='DIV' THEN (SELECT COALESCE(SUM(le2.amount_base_e6),0) "
            "FROM ledger_entries le2 WHERE le2.transaction_id=t.id AND le2.amount_base_e6>0) "
            "ELSE NULL END AS amount_base_e6 "
            "FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "LEFT JOIN categories c ON c.id=le.category_id "
            "WHERE t.status='POSTED' AND le.owner_id IS NULL AND t.date BETWEEN ? AND ? AND " + type_filter +
            " ORDER BY t.date,t.id", (start, end),
        )

    def money_added_transactions(self, start: str, end: str) -> list[dict]:
        """The transactions behind Money added: money that crossed into or out of investment accounts.

        The same rule as the figure (lightning/investments/report.py): per transaction, sum only its
        lines in investment accounts; a transfer between two of them nets to zero and is left out, and
        dividends, interest, opening balances and revaluations (VAL) are not money added."""
        # Deposit accounts are inside the portfolio too: buying a certificate from the bank is money
        # added (owner decision 2026-10-04; the same boundary as the figure).
        ids = [a.id for a in self.accounts.list(active_only=False)
               if a.account_type in INVESTMENT_ACCOUNT_TYPES or a.account_type in (AccountType.DEPOSIT, AccountType.GAMEYA)]
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = self.db.all(
            "SELECT t.id,t.ref,t.date,t.type,t.description,t.counterparty,SUM(le.amount_base_e6) AS amount_e6 "
            "FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "LEFT JOIN categories c ON c.id=le.category_id "
            f"WHERE t.status='POSTED' AND le.owner_id IS NULL AND le.account_id IN ({marks}) AND t.date BETWEEN ? AND ? "
            "AND t.type NOT IN ('DIV','OPN','VAL') AND COALESCE(c.code,'') NOT IN ('EXP.INVEST.DIVIDEND','EXP.INVEST.INTEREST','EXP.INVEST.FEES','EXP.INVEST.TAX') "
            "GROUP BY t.id HAVING SUM(le.amount_base_e6) != 0 ORDER BY t.date,t.id", (*ids, start, end))
        return [dict(r) | {"amount": Decimal(r["amount_e6"]) / Decimal(1_000_000)} for r in rows]

    def opening_adjustments(self, account_ids: list[int], start: str, end: str) -> Decimal:
        if not account_ids:
            return ZERO
        marks = ",".join("?" for _ in account_ids)
        amount = self.db.scalar(
            f"SELECT COALESCE(SUM(le.amount_base_e6),0) FROM ledger_entries le "
            f"JOIN transactions t ON t.id=le.transaction_id WHERE t.status='POSTED' AND t.type='OPN' "
            f"AND le.owner_id IS NULL AND le.account_id IN ({marks}) AND le.date BETWEEN ? AND ?",
            (*account_ids, start, end),
        )
        return Decimal(amount or 0) / Decimal(1_000_000)

    def period_interest(self, category_id: int | None, start: str, end: str) -> Decimal:
        if category_id is None:
            return ZERO
        amount = self.db.scalar(
            "SELECT COALESCE(SUM(le.amount_base_e6),0) FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id WHERE t.status='POSTED' "
            "AND le.owner_id IS NULL AND le.category_id=? AND le.effect='INFLOW' AND t.date BETWEEN ? AND ?",
            (category_id, start, end),
        )
        return Decimal(amount or 0) / Decimal(1_000_000)

    # ======================================================================
    # Recording
    # ======================================================================
    # ------------------------------------------------------------------ broker pockets
    def route(self, account_id, asset_id, cash_account_id=None) -> tuple[int, int | None]:
        """One row per broker (owner decision 2026-10-16): a listing in another currency than the broker's is held
        in that currency's pocket, made on demand, and paid from the same pocket unless another account pays."""
        if account_id in (None, "") or asset_id in (None, ""):
            return account_id, cash_account_id
        account = self.accounts.get(int(account_id))
        asset = self.assets.get_asset(int(asset_id))
        if account.account_type != AccountType.BROKERAGE or asset.is_cash or asset.currency == account.currency:
            return account_id, cash_account_id
        pocket = self.accounts.pocket_for(account, asset.currency, create=True)
        broker = self.accounts.broker_of(account)
        same_broker = {broker.id, *(p.id for p in self.accounts.pockets(broker.id))}
        if cash_account_id in (None, "", 0) or int(cash_account_id) in same_broker:
            cash_account_id = None
        return pocket.id, cash_account_id

    def buy_converting(self, date: str, account_id: int, asset_id: int, quantity, total, paid, from_account_id=None,
                       notes: str = "", fees="0", fees_included=True, owner_id: int | None = None) -> Transaction:
        """Convert, then buy (owner decision 2026-10-16): ``paid`` leaves the broker's own cash (or another account)
        and becomes ``total`` in the listing's currency pocket, then the buy spends it. Two linked documents in one
        step: a conversion with its executed rate and spread, and an ordinary buy. No margin: nothing is borrowed."""
        with self.db.transaction():
            # route() may create a currency pocket; keep it in the same transaction so a
            # refused buy leaves no empty pocket behind (2K).
            holding_id, _ = self.route(account_id, asset_id)
            pocket = self.accounts.get(int(holding_id))
            source = self.accounts.require_usable(int(from_account_id) if from_account_id not in (None, "") else
                                                  self.accounts.broker_of(pocket).id, "cash_account")
            if source.currency == pocket.currency:
                raise ValidationError(f"{source.label} is already in {pocket.currency}; record an ordinary buy.",
                                      "cash_account")
            asset = self.assets.get_asset(int(asset_id))
            self.transactions.record_conversion(date, source.id, pocket.id, paid, total,
                                                notes=f"For {asset.name}")
            return self.buy_total(date, pocket.id, asset_id, quantity, total, None, notes, fees, fees_included,
                                  owner_id)

    def buy(self, date: str, account_id: int, asset_id: int, quantity, price, fees="0",
            cash_account_id: int | None = None, notes: str = "", owner_id: int | None = None) -> Transaction:
        """Buy units: cash leaves the paying account, the holding grows at cost (fees included)."""
        return self.record("buy", date, account_id, asset_id, quantity=quantity, price=price, fees=fees,
                           cash_account_id=cash_account_id, notes=notes, owner_id=owner_id)

    def buy_total(self, date, account_id, asset_id, quantity, total, cash_account_id=None, notes="",
                  fees="0", fees_included=True, owner_id: int | None = None):
        """Buy by total cash paid (fees included) or gross trade value (fees additional)."""
        return self.record("buy", date, account_id, asset_id, quantity=quantity, total=total, total_fees=fees,
                           fees_included=fees_included, cash_account_id=cash_account_id, notes=notes,
                           owner_id=owner_id)

    def sell_total(self, date, account_id, asset_id, quantity, total, cash_account_id=None, notes="",
                   fees="0", fees_included=True, owner_id: int | None = None):
        """Sell by net cash received (fees included) or gross trade value (fees additional)."""
        return self.record("sell", date, account_id, asset_id, quantity=quantity, total=total, total_fees=fees,
                           fees_included=fees_included, cash_account_id=cash_account_id, notes=notes,
                           owner_id=owner_id)

    def sell(self, date: str, account_id: int, asset_id: int, quantity, price, fees="0",
             cash_account_id: int | None = None, notes: str = "", owner_id: int | None = None) -> Transaction:
        """Sell units: the holding shrinks, what you receive (after fees) arrives as cash."""
        return self.record("sell", date, account_id, asset_id, quantity=quantity, price=price, fees=fees,
                           cash_account_id=cash_account_id, notes=notes, owner_id=owner_id)

    def dividend(self, date: str, account_id: int, asset_id: int, amount, notes: str = "",
                 owner_id: int | None = None, tax="0") -> Transaction:
        """A cash dividend from an investment, received into the account (money in: Investment Income).

        ``amount`` is what you received, unless ``tax`` is given: then it is the gross dividend and the tax
        withheld leaves the same account in the same transaction (net lands in cash)."""
        return self.record("dividend", date, account_id, asset_id, amount=amount, tax=tax, notes=notes,
                           owner_id=owner_id)

    def return_of_capital(self, date: str, account_id: int, asset_id: int, amount,
                          cash_account_id: int | None = None, notes: str = "",
                          owner_id: int | None = None) -> Transaction:
        """A fund pays part of what you paid in back: the cash arrives (internal, not income), no units change and the
        holding's cost falls by the amount. What is paid back beyond the cost left is a realized gain (NF-5A4)."""
        return self.record("return_of_capital", date, account_id, asset_id, amount=amount,
                           cash_account_id=cash_account_id, notes=notes, owner_id=owner_id)

    def record(self, event: str, date: str, account_id, asset_id, *, owner_id: int | None = None, notes: str = "",
               cash_account_id=None, **typed) -> Transaction:
        """Post one investment event named in ``events.EVENTS``: the one recording path behind buy, sell and
        dividend. ``typed`` holds the figures the event's spec asks for (quantity, price, total, fees, amount, tax)."""
        spec = events.EVENTS.get(event)
        if spec is None:
            raise ValidationError("That investment action is not available.", "event")
        if spec.income_category:
            return self._record_income(event, date, account_id, asset_id, owner_id, notes, typed)
        if spec.units == events.Sign.NEW_BALANCE:
            return self._record_split(event, date, account_id, asset_id, owner_id, notes, typed)
        return self._trade(event, date, account_id, asset_id, cash_account_id, notes, owner_id, typed)

    def bonus_or_split(self, date: str, account_id: int, asset_id: int, units_after, notes: str = "",
                       owner_id: int | None = None) -> Transaction:
        """Bonus shares, a split or a reverse split: the units become ``units_after``, the cost stays, no cash moves
        and no purchase appears (NF-5E). Applies to the units of the chosen owner (yours by default)."""
        return self.record("bonus_or_split", date, account_id, asset_id, quantity=units_after, notes=notes,
                           owner_id=owner_id)

    def _split_lines(self, account_id, asset_id, date, owner_id, quantity, editing: Transaction | None = None):
        account = self._holding_account(account_id)
        asset = self._investment(asset_id)
        self._validate_asset_account(account, asset)
        self._same_currency(asset, account)
        # Editing: the units held without the split being replaced (it is part of today's total).
        own = sum((ln.quantity for ln in editing.lines if ln.asset_id == asset.id), ZERO) \
            if editing is not None and editing.date <= date else ZERO
        values = events.EventValues(
            asset=asset, account=account, holding_rate=self._rate(account, date), quantity=quantity,
            held=self.holding_for_owner(account.id, asset.id, date, owner_id) - own)
        lines = events.lines_for("bonus_or_split", values)
        if owner_id:
            party = self.db.one("SELECT id FROM counterparties WHERE id=? AND active=1", (owner_id,))
            if not party:
                raise ValidationError("Choose an active owner.", "owner")
            lines = [replace(line, owner_id=int(owner_id)) for line in lines]
        return lines, asset.name

    def _record_split(self, event, date, account_id, asset_id, owner_id, notes, typed) -> Transaction:
        lines, counterparty = self._split_lines(account_id, asset_id, date, owner_id, typed.get("quantity"))
        return self.transactions.post(events.EVENTS[event].doc_type, date, lines, SPLIT_MARK, counterparty, notes)

    def _record_income(self, event, date, account_id, asset_id, owner_id, notes, typed) -> Transaction:
        spec = events.EVENTS[event]
        account_id, _ = self.route(account_id, asset_id)
        account = self.accounts.require_usable(account_id)
        if account.account_type != AccountType.BROKERAGE:
            raise ValidationError("Dividends can only be recorded in a brokerage account.", "account")
        if self.holding_for_owner(account_id, asset_id, date, owner_id) <= ZERO:
            raise ValidationError("A dividend requires shares held by the selected owner on that date.", "instrument")
        lines, counterparty = self._event_lines(event, account_id, asset_id, on=date, **typed)
        if owner_id is not None:
            lines = [replace(line, owner_id=owner_id) for line in lines]
        txn = self.transactions.post(spec.doc_type, date, lines, "", counterparty, notes)
        self.db.execute("INSERT INTO investment_dividend_assets(transaction_id,asset_id) VALUES(?,?)",
                        (txn.id, asset_id))
        return txn

    def broker_fee(self, date: str, account_id: int, amount, notes: str = "") -> Transaction:
        """A broker's own charge (custody, data, inactivity), paid from the brokerage's cash. It is an
        investment cost (Investment › Investment Fees): it lowers Net gain, never household spending."""
        account = self._brokerage_cash_account(account_id, "Fees")
        value = check_places(to_decimal(amount, "amount"), 2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter the fee the broker charged.", "total")
        category = self.categories.get_by_code(FEE_CATEGORY)
        cash_asset = self.assets.cash_asset(account.currency)
        line = PostingLine.cash(account.id, cash_asset.id, -value, Effect.OUTFLOW, category.id, memo="Broker fee",
                                fx_rate=self._rate(account, date))
        return self.transactions.post(DocType.OUT, date, [line], "Broker fee", account.label, notes)

    def broker_interest(self, date: str, account_id: int, amount, notes: str = "") -> Transaction:
        """Interest a broker paid on its uninvested cash (Investment › Interest)."""
        account = self._brokerage_cash_account(account_id, "Interest")
        value = check_places(to_decimal(amount, "amount"), 2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter the interest you received.", "total")
        category = self.categories.get_by_code(INTEREST_CATEGORY)
        cash_asset = self.assets.cash_asset(account.currency)
        line = PostingLine.cash(account.id, cash_asset.id, value, Effect.INFLOW, category.id,
                                memo="Interest on cash", fx_rate=self._rate(account, date))
        return self.transactions.post(DocType.IN, date, [line], "Interest on cash", account.label, notes)

    def move_units(self, date: str, from_account_id: int, to_account_id: int, asset_id: int, quantity,
                   notes: str = "") -> Transaction:
        """Move shares from one broker to another: no cash, no gain. The units keep their average cost,
        so the destination holds them at the cost the source held them at.

        Only your own units move (units held for someone else stay put); physical items and
        certificates cannot be moved this way, and both accounts must be brokerages in the asset's currency."""
        source = self._holding_account(from_account_id)
        target = self._holding_account(to_account_id)
        asset = self._investment(asset_id)
        if source.id == target.id:
            raise ValidationError("Choose a different broker to move the shares to.", "to_account")
        if source.account_type != AccountType.BROKERAGE or target.account_type != AccountType.BROKERAGE:
            raise ValidationError("Shares can only be moved between brokerage accounts.", "to_account")
        self._same_currency(asset, source, target)
        self._validate_asset_account(source, asset)
        self._validate_asset_account(target, asset)
        units = self._units(asset, quantity)
        day = parse_date(date).isoformat()
        held = self.holding_for_owner(source.id, asset.id, day)
        if units > held:
            raise ValidationError(f"{source.label} holds {_num(held)} {asset.unit}(s) of {asset.name}; "
                                  f"you cannot move {_num(units)}.", "units")
        position = next((p for p in self.portfolio(day, source.id).positions
                         if p.asset_id == asset.id and p.owned_quantity), None)
        if position is None or position.owned_quantity <= ZERO:
            raise ValidationError(f"{source.label} holds no {asset.name} of yours to move.", "units")
        cost = position.owned_cost_basis if units == position.owned_quantity else _money(
            position.owned_cost_basis * units / position.owned_quantity)
        per_unit = (cost / units).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        memo = f"Move {_num(units)} × {asset.code} to {target.label}"
        back = f"Move {_num(units)} × {asset.code} from {source.label}"
        lines = [PostingLine.units(source.id, asset.id, -units, -cost, Effect.INTERNAL, per_unit, memo,
                                   fx_rate=self._rate(source, date)),
                 PostingLine.units(target.id, asset.id, units, cost, Effect.INTERNAL, per_unit, back,
                                   fx_rate=self._rate(target, date))]
        return self.transactions.post(DocType.TRF, date, lines, f"Move {asset.name}", asset.name, notes)

    def _brokerage_cash_account(self, account_id, what: str) -> Account:
        account = self.accounts.require_usable(account_id)
        if account.account_type != AccountType.BROKERAGE:
            raise ValidationError(f"{what} can only be recorded in a brokerage account.", "account")
        return account

    def holding_for_owner(self, account_id: int, asset_id: int, as_of: str, owner_id: int | None = None) -> Decimal:
        """Return signed investment units held by one owner on a date."""
        day = parse_date(as_of).isoformat()
        owner_clause = "le.owner_id IS NULL" if owner_id is None else "le.owner_id=?"
        params = (account_id, asset_id, day) if owner_id is None else (account_id, asset_id, day, owner_id)
        quantity = self.db.scalar(
            "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id "
            f"WHERE le.account_id=? AND le.asset_id=? AND le.date<=? AND {owner_clause} AND t.status='POSTED'",
            params)
        return from_e6(quantity or 0)

    def add_holding(self, account_id: int, asset_id: int, quantity, total_cost, date: str | None = None,
                    notes: str = "", owner_id: int | None = None) -> Transaction:
        """Units you already owned when you started tracking, with what you paid for them in total."""
        account_id, _ = self.route(account_id, asset_id)
        account = self._holding_account(account_id)
        asset = self._investment(asset_id)
        self._validate_asset_account(account, asset)
        if self.transactions.opening_txn_id(account.id, asset.id):
            raise ConflictError(f"{account.label} already has a starting amount of {asset.name} — edit that one.")
        lines = self._holding_lines(account, asset, quantity, total_cost, on=date or fmt_date(today()))
        if owner_id is not None:
            lines = [replace(line, owner_id=owner_id) for line in lines]
        return self.transactions.post(DocType.OPN, date or fmt_date(today()), lines,
                                      f"Starting holding — {asset.name}", asset.name, notes)

    def update(self, txn_id: int, **values) -> Transaction:
        """Edit a buy, sell, dividend or starting holding in place; the ref stays the same."""
        current = self.transactions.get(txn_id)
        kind = current.type
        date = values.get("date", current.date)
        notes = values.get("notes", current.notes)
        owner_id = values.get("owner_id")
        if self._is_split(current):
            lines, counterparty = self._split_lines(values["account_id"], values["asset_id"], date, owner_id,
                                                    values["quantity"], editing=current)
            return self.transactions.repost(txn_id, date, lines, SPLIT_MARK, counterparty, notes)
        if kind == DocType.SEL and self._is_capital_return(current):
            self._require_capital_held(values["account_id"], values["asset_id"], date, owner_id)
            lines, counterparty = self._event_lines("return_of_capital", values["account_id"], values["asset_id"],
                                                    values.get("cash_account_id"), on=date, amount=values["amount"])
            if owner_id:
                lines = [replace(line, owner_id=int(owner_id)) for line in lines]
            return self.transactions.repost(txn_id, date, lines, "", counterparty, notes)
        if kind in (DocType.BUY, DocType.SEL):
            lines, counterparty = self._event_lines(
                "buy" if kind == DocType.BUY else "sell", values["account_id"], values["asset_id"],
                values.get("cash_account_id"), on=date, quantity=values["quantity"], price=values["price"],
                fees=values.get("fees", "0"), total=values.get("total") or None,
                total_fees=values.get("total_fees", "0"), fees_included=values.get("fees_included", True))
            if owner_id:
                lines = [replace(line, owner_id=int(owner_id)) for line in lines]
            self._require_broker_cash(kind, values["account_id"], lines)  # an edit cannot skip it (audit 2026-10-26)
            updated = self.transactions.repost(txn_id, date, lines, "", counterparty, notes)
            if kind == DocType.SEL:
                unit_line = next(line for line in lines if not self.assets.get_asset(line.asset_id).is_cash)
                self.reevaluations.process_sale(updated.date, values["account_id"], values["asset_id"],
                                                unit_line.unit_price, owner_id=owner_id)
            return updated
        if kind == DocType.DIV:
            if self.holding_for_owner(values["account_id"], values["asset_id"], date, owner_id) <= ZERO:
                raise ValidationError("A dividend requires shares held by the selected owner on that date.", "asset_id")
            tax = values["tax"] if "tax" in values else self.values_of(txn_id).get("tax", "0")
            reinvested = any(not self.assets.get_asset(ln.asset_id).is_cash for ln in current.lines)
            extra = {"quantity": values.get("quantity") or self.values_of(txn_id)["quantity"]} if reinvested else {}
            lines, counterparty = self._event_lines("reinvested_dividend" if reinvested else "dividend",
                                                    values["account_id"], values["asset_id"], on=date,
                                                    amount=values["amount"], tax=tax, **extra)
            if owner_id:
                lines = [replace(line, owner_id=int(owner_id)) for line in lines]
            updated = self.transactions.repost(txn_id, date, lines, "", counterparty, notes)
            self.db.execute("INSERT INTO investment_dividend_assets(transaction_id,asset_id) VALUES(?,?) "
                            "ON CONFLICT(transaction_id) DO UPDATE SET asset_id=excluded.asset_id",
                            (txn_id, values["asset_id"]))
            return updated
        if kind == DocType.OPN and self._is_holding_opening(current):
            account = self._holding_account(values["account_id"])
            asset = self._investment(values["asset_id"])
            self._validate_asset_account(account, asset)
            existing = self.transactions.opening_txn_id(account.id, asset.id, exclude_id=txn_id)
            if existing:
                raise ConflictError(f"{account.label} already has a starting amount of {asset.name}.")
            lines = self._holding_lines(account, asset, values["quantity"], values["total_cost"], on=date)
            if owner_id is not None:
                lines = [replace(line, owner_id=int(owner_id)) for line in lines]
            return self.transactions.repost(txn_id, date, lines, f"Starting holding — {asset.name}", asset.name,
                                            notes)
        raise ValidationError("This is not an investment transaction.")

    def values_of(self, txn_id: int) -> dict:
        """The form values that would recreate a transaction (to prefill the edit form)."""
        t = self.transactions.get(txn_id)
        cash = [ln for ln in t.lines if self.assets.get_asset(ln.asset_id).is_cash]
        units = [ln for ln in t.lines if not self.assets.get_asset(ln.asset_id).is_cash]
        values = {"kind": {DocType.BUY: "buy", DocType.SEL: "sell", DocType.DIV: "dividend",
                           DocType.OPN: "holding"}.get(t.type, ""), "date": t.date, "notes": t.notes,
                  "owner_id": next((line.owner_id for line in t.lines if line.owner_id is not None), None)}
        if self._is_split(t) and units:
            owner = units[0].owner_id
            values.update(kind="bonus_or_split", account_id=units[0].account_id, asset_id=units[0].asset_id,
                          quantity=self.holding_for_owner(units[0].account_id, units[0].asset_id, t.date, owner))
        elif self._is_capital_return(t) and cash:
            values.update(kind="return_of_capital", account_id=units[0].account_id, asset_id=units[0].asset_id,
                          amount=cash[0].quantity, cash_account_id=cash[0].account_id)
        elif t.type in (DocType.BUY, DocType.SEL) and units and cash:
            u, c = units[0], cash[0]
            gross = _money(abs(u.quantity) * u.unit_price)
            fees = abs(u.amount) - gross if t.type == DocType.BUY else gross - abs(u.amount)
            values.update(account_id=u.account_id, asset_id=u.asset_id, quantity=abs(u.quantity),
                          price=u.unit_price, fees=_money(fees), total_fees=_money(fees),
                          fees_included=True, total=abs(c.quantity), cash_account_id=c.account_id)
        elif t.type == DocType.DIV and cash:
            asset_id = self.db.scalar("SELECT asset_id FROM investment_dividend_assets WHERE transaction_id=?", (t.id,))
            income = [ln for ln in cash if ln.effect in (Effect.INFLOW, Effect.OUTFLOW)]  # not a reinvestment's spend
            gross = sum((ln.quantity for ln in income if ln.quantity > ZERO), ZERO)
            tax = -sum((ln.quantity for ln in income if ln.quantity < ZERO), ZERO)
            values.update(account_id=cash[0].account_id, asset_id=asset_id, amount=gross, tax=tax)
            if units:  # a reinvested dividend edits like a dividend; its units stay as they were
                values["quantity"] = units[0].quantity
        elif t.type == DocType.OPN and units:
            values.update(account_id=units[0].account_id, asset_id=units[0].asset_id, quantity=units[0].quantity,
                          total_cost=units[0].amount)
        return values

    # ======================================================================
    # Positions
    # ======================================================================
    def portfolio(self, as_of=None, account_id: int | None = None) -> Portfolio:
        """Every holding (open and closed) with cost basis, value and gains, as of a date (default today)."""
        day = fmt_date(as_of) if as_of and not isinstance(as_of, str) else (as_of or fmt_date(today()))
        state: dict[tuple[int, int], dict[int | None, list[LotLine]]] = {}
        dividends: dict[tuple[int, str], Decimal] = {}
        taxes: dict[tuple[int, str], Decimal] = {}
        owned_dividends: dict[tuple[int, str], Decimal] = {}
        owned_taxes: dict[tuple[int, str], Decimal] = {}
        other_income: set[tuple[int, str]] = set()
        cashflows: list[tuple[str, Decimal]] = []
        holding_flows: dict[tuple[int, int], list[tuple[str, Decimal]]] = {}
        for line in self.reporting.investment_lines(day, account_id):
            if line["type"] == "DIV" and line["effect"] == "INTERNAL" and line["is_cash"]:
                continue  # a reinvested dividend's spend: the units line below carries the purchase
            if line["type"] == "DIV" and line["effect"] != "INTERNAL":
                asset_id = line.get("dividend_asset_id")
                if asset_id is None:
                    continue
                asset_code = self.assets.get_asset(asset_id).code
                key = (line["account_id"], asset_code)
                dividend = from_e6(line["amount_base_e6"])
                if dividend < ZERO:  # tax withheld: the dividend stays gross, the tax is its own figure
                    taxes[key] = taxes.get(key, ZERO) - dividend
                else:
                    dividends[key] = dividends.get(key, ZERO) + dividend
                if line["owner_id"] is None:
                    owned = owned_taxes if dividend < ZERO else owned_dividends
                    owned[key] = owned.get(key, ZERO) + abs(dividend)
                else:
                    other_income.add(key)
                cashflows.append((line["date"], dividend))
                asset = self.assets.get_asset(asset_id)
                holding_flows.setdefault((line["account_id"], asset.id), []).append((line["date"], dividend))
                continue
            flow = -from_e6(line["amount_base_e6"])
            kind = lot_type(line["type"], line.get("description", ""))
            if kind != "SPL":  # a bonus or split moves no money: it is no flow for XIRR
                cashflows.append((line["date"], flow))
                holding_flows.setdefault((line["account_id"], line["asset_id"]), []).append((line["date"], flow))
            # One pool per owner (None is you): a sale by one owner removes units at that owner's own
            # cost, never at a blend of everyone's purchase prices. The lots are built after the loop.
            pools = state.setdefault((line["account_id"], line["asset_id"]), {})
            pools.setdefault(line.get("owner_id"), []).append(LotLine(
                line["date"], kind, line["effect"], from_e6(line["quantity_e6"]), from_e6(line["amount_base_e6"])))
        # A certificate's interest lands on the bank account; it is still the certificate's return.
        for paid in self.reporting.certificate_interest(day):
            if account_id is not None and paid["account_id"] != account_id:
                continue
            key = (paid["account_id"], self.assets.get_asset(paid["asset_id"]).code)
            dividends[key] = dividends.get(key, ZERO) + paid["amount"]
            owned_dividends[key] = owned_dividends.get(key, ZERO) + paid["amount"]
            cashflows.append((paid["date"], paid["amount"]))
            holding_flows.setdefault((paid["account_id"], paid["asset_id"]), []).append((paid["date"], paid["amount"]))
        positions = []
        for (acc_id, asset_id), lines in state.items():
            method = self.accounts.get(acc_id).cost_method
            pools = {owner: build_lots(owner_lines, method, owner) for owner, owner_lines in lines.items()}
            s = {"qty": sum((book.quantity for book in pools.values()), ZERO),
                 "cost": sum((book.cost for book in pools.values()), ZERO),
                 "realized": sum((book.realized for book in pools.values()), ZERO)}
            own = pools.get(None) or build_lots([])
            account, asset = self.accounts.get(acc_id), self.assets.get_asset(asset_id)
            valuation = self.reporting.value_of(asset_id, s["qty"], day) if s["qty"] else None
            holding_cashflows = holding_flows.get((acc_id, asset_id), [])
            if s["qty"] and valuation and valuation.value is not None:
                holding_cashflows = [*holding_cashflows, (day, valuation.value)]
            annual_result = solve_xirr(holding_cashflows, day)
            annual_rate = annual_result.rate
            positions.append(Position(
                account_id=acc_id, account_label=account.label, asset_id=asset_id, asset_code=asset.code,
                asset_name=asset.name, asset_class=self.assets.display_name(asset.asset_class_id),
                exposure=EXPOSURE_LABELS[asset.exposure], unit=asset.unit, quantity=s["qty"],
                cost_basis=_money(s["cost"]), realized=_money(s["realized"]),
                dividends=dividends.pop((acc_id, asset.code), ZERO),
                dividend_tax=taxes.pop((acc_id, asset.code), ZERO),
                price=valuation.price if valuation else None,
                price_date=valuation.price_date if valuation else None,
                price_source=valuation.source if valuation else "",
                value=valuation.value if valuation and valuation.value is not None else (
                    None if s["qty"] else ZERO),  # full precision, like net worth; screens round
                xirr=annual_rate,
                display_return=display_return(holding_cashflows, day, annual_result,
                                              not s["qty"] or bool(valuation and valuation.value is not None)),
                invested=sum((-amount for _, amount in holding_flows.get((acc_id, asset_id), []) if amount < ZERO), ZERO),
                owned_quantity=own.quantity, owned_cost_basis=_money(own.cost),
                owned_realized=_money(own.realized), owned_invested=own.invested,
                owned_dividends=owned_dividends.pop((acc_id, asset.code), ZERO),
                owned_dividend_tax=owned_taxes.pop((acc_id, asset.code), ZERO),
                has_other_owners=any(owner is not None for owner in pools) or (acc_id, asset.code) in other_income,
                lots=[lot for book in pools.values() for lot in book.lots],
                disposals=[piece for book in pools.values() for piece in book.disposals],
                flows=tuple(holding_flows.get((acc_id, asset_id), [])),
            ))
        # dividends from something not (or no longer) held in that account still count
        for (acc_id, code), amount in dividends.items():
            asset = self.assets.get_asset_by_code(code)
            positions.append(Position(acc_id, self.accounts.get(acc_id).label, asset.id, asset.code, asset.name,
                                      self.assets.display_name(asset.asset_class_id), EXPOSURE_LABELS[asset.exposure],
                                      asset.unit, ZERO, ZERO, ZERO, amount, None, None, "", ZERO,
                                      dividend_tax=taxes.get((acc_id, code), ZERO),
                                      owned_dividends=owned_dividends.get((acc_id, code), ZERO),
                                      owned_dividend_tax=owned_taxes.get((acc_id, code), ZERO),
                                      has_other_owners=(acc_id, code) in other_income))
        positions.sort(key=lambda p: (-(p.value or ZERO), p.asset_name))
        cashflows.extend((day, position.value)
                         for position in positions if position.is_open and position.value is not None)
        annual_result = solve_xirr(cashflows, day)
        annual_rate = annual_result.rate
        return Portfolio(day, positions, annual_rate,
                         display_return(cashflows, day, annual_result,
                                        all(p.value is not None for p in positions)))

    def holding(self, account_id: int, asset_id: int, as_of=None) -> Decimal:
        for p in self.portfolio(as_of, account_id).positions:
            if p.asset_id == asset_id:
                return p.quantity
        return ZERO

    def investment_accounts(self) -> list[Account]:
        return [a for a in self.accounts.list(active_only=True) if a.account_type in INVESTMENT_ACCOUNT_TYPES]

    # ======================================================================
    # Building lines
    # ======================================================================
    def _trade(self, event, date, account_id, asset_id, cash_account_id, notes, owner_id, typed):
        # One step: a pocket made for this trade is undone with it when the trade is refused.
        with self.db.transaction():
            asked = account_id
            account_id, cash_account_id = self.route(account_id, asset_id, cash_account_id)
            try:
                return self._trade_in(event, date, account_id, asset_id, cash_account_id, notes, owner_id, typed)
            except ValidationError as error:
                if event != "buy" or account_id == asked or cash_account_id is not None:
                    raise
                broker = self.accounts.get(int(asked))
                asset = self.assets.get_asset(int(asset_id))
                home = self.accounts.broker_of(broker)
                raise ValidationError(
                    f"{asset.name} is priced in {asset.currency}; {home.label} has no {asset.currency} cash for it. "
                    f"Enter what you paid in {home.currency} under Paid in another currency, or move "
                    f"{asset.currency} in first.", "instrument") from error

    def _trade_in(self, event, date, account_id, asset_id, cash_account_id, notes, owner_id, typed):
        spec = events.EVENTS[event]
        kind = spec.doc_type
        if spec.lowers_cost:
            self._require_capital_held(account_id, asset_id, date, owner_id)
        lines, counterparty = self._event_lines(event, account_id, asset_id, cash_account_id, on=date, **typed)
        if owner_id is not None:
            party = self.db.one("SELECT id FROM counterparties WHERE id=? AND active=1", (owner_id,))
            if not party:
                raise ValidationError("Choose an active owner.", "owner")
            lines = [replace(line, owner_id=owner_id) for line in lines]
        self._require_broker_cash(kind, account_id, lines)
        txn = self.transactions.post(kind, date, lines, "", counterparty, notes)
        if kind == DocType.SEL and not spec.lowers_cost:  # no units were sold
            unit_line = next(line for line in lines if not self.assets.get_asset(line.asset_id).is_cash)
            self.reevaluations.process_sale(txn.date, account_id, asset_id, unit_line.unit_price,
                                            owner_id=owner_id)
        return txn

    def _require_capital_held(self, account_id, asset_id, date, owner_id) -> None:
        """A return of capital belongs to a fund held in a brokerage by that owner on that day."""
        account = self.accounts.require_usable(account_id)
        if account.account_type != AccountType.BROKERAGE:
            raise ValidationError("A return of capital can only be recorded in a brokerage account.", "account")
        if self.holding_for_owner(account_id, asset_id, date, owner_id) <= ZERO:
            raise ValidationError("A return of capital requires units held by the selected owner on that date.",
                                  "instrument")

    def _require_broker_cash(self, kind, account_id, lines) -> None:
        holding_account = self.accounts.get(int(account_id))
        if holding_account.account_type == AccountType.BROKERAGE and kind == DocType.BUY:
            cash_line = next(line for line in lines if self.assets.get_asset(line.asset_id).is_cash)
            if cash_line.account_id != holding_account.id:
                raise ValidationError("Brokerage purchases must use cash already in that brokerage account.",
                                      "cash_account")

    def _rate(self, account: Account, on) -> Decimal:
        """The line rate (account currency -> base) on a day: one place for every investment line."""
        return self.transactions._fx(account, on)

    @staticmethod
    def _same_currency(asset: FinancialAsset, *accounts: Account) -> None:
        """An investment is bought, held and paid for in its own currency."""
        for account in accounts:
            if account.currency != asset.currency:
                raise ValidationError(f"{asset.name} is priced in {asset.currency}; {account.label} is in "
                                      f"{account.currency}. Use a {asset.currency} account.", "account")

    def _event_lines(self, event, account_id, asset_id, cash_account_id=None, on=None, **typed):
        """Resolve accounts, asset, currency and rates for an event, then let the table build and check the lines."""
        spec = events.EVENTS[event]
        on = on or fmt_date(today())
        if spec.income_category:
            account = self.accounts.require_usable(account_id)
            if account.account_type != AccountType.BROKERAGE:
                raise ValidationError("Dividends can only be recorded in a brokerage account.", "account")
            asset = self._investment(asset_id)
            self._validate_asset_account(account, asset)
            self._same_currency(asset, account)
            values = events.EventValues(
                asset=asset, account=account, cash_asset_id=self.assets.cash_asset(account.currency).id,
                holding_rate=self._rate(account, on),
                category_ids={code: self.categories.get_by_code(code).id
                              for code in (DIVIDEND_CATEGORY, TAX_CATEGORY)}, **typed)
            return events.lines_for(event, values), asset.name
        account = self._holding_account(account_id)
        asset = self._investment(asset_id)
        self._validate_asset_account(account, asset)
        cash_account = self._cash_account(account, cash_account_id)
        self._same_currency(asset, account, cash_account)
        values = events.EventValues(
            asset=asset, account=account, cash_account=cash_account,
            cash_asset_id=self.assets.cash_asset(cash_account.currency).id,
            holding_rate=self._rate(account, on), cash_rate=self._rate(cash_account, on), **typed)
        return events.lines_for(event, values), asset.name

    def _holding_lines(self, account: Account, asset: FinancialAsset, quantity, total_cost, on=None):
        self._same_currency(asset, account)
        units = self._units(asset, quantity)
        cost = check_places(to_decimal(total_cost if str(total_cost or "").strip() else "0", "total_cost"), 2,
                            "total_cost")
        if cost < ZERO:
            raise ValidationError("What you paid cannot be negative.", "total_cost")
        per_unit = (cost / units).quantize(Decimal("0.000001"))
        return [PostingLine.units(account.id, asset.id, units, cost, Effect.OPENING, per_unit,
                                  f"Starting holding {_num(units)} × {asset.label}",
                                  fx_rate=self._rate(account, on or fmt_date(today())))]

    def _holding_account(self, account_id) -> Account:
        account = self.accounts.require_usable(account_id)
        if account.account_type not in INVESTMENT_ACCOUNT_TYPES:
            raise ValidationError(
                f"{account.label} is a {account.type_label.lower()}. Investments are held in a brokerage, "
                "physical-asset or other account.", "account")
        return account

    def _validate_asset_account(self, account: Account, asset):
        if asset.code in PRICE_REFERENCE_CODES:  # a price series, not something you can own
            raise ValidationError(f"{asset.name} only supplies a price. Record the gold you own as an item "
                                  "in a physical-asset account.", "asset")
        root_code = self.assets.get_class(asset.asset_class_id).root_code
        if root_code in {"STOCK", "FUND"} and account.account_type != AccountType.BROKERAGE:
            raise ValidationError("Stocks and funds can only be traded in a brokerage account.", "account")
        item = self.db.one("SELECT account_id FROM physical_items WHERE asset_id=?", (asset.id,)) \
            if self.db.has_table("physical_items") else None
        if item and (account.account_type != AccountType.PHYSICAL_ASSET or item["account_id"] != account.id):
            raise ValidationError("This physical item can only be traded in its registered physical-asset account.",
                                  "account")
        legacy_gram_gold = asset.exposure.value == "GOLD" and asset.unit == "gram"
        if account.account_type == AccountType.PHYSICAL_ASSET and not item and not legacy_gram_gold:
            raise ValidationError("Choose an item registered in this physical-asset account.", "asset")

    def _cash_account(self, account: Account, cash_account_id) -> Account:
        if cash_account_id in (None, "", 0):
            if account.account_type == AccountType.BROKERAGE:
                return account  # the broker's own cash
            raise ValidationError("Choose which account the money comes from or goes to.", "cash_account")
        return self.accounts.require_usable(int(cash_account_id), "cash_account")

    def _investment(self, asset_id) -> FinancialAsset:
        if asset_id in (None, ""):
            raise ValidationError("Choose the investment.", "asset")
        asset = self.assets.get_asset(int(asset_id))
        if asset.is_cash:
            raise ValidationError("Choose a stock, fund or gold — not a currency.", "asset")
        if not asset.active:
            raise ValidationError(f"{asset.label} is inactive.", "asset")
        return asset

    @staticmethod
    def _units(asset: FinancialAsset, quantity) -> Decimal:
        units = check_places(to_decimal(quantity, "quantity"), asset.quantity_decimals, "quantity")
        if units <= ZERO:
            raise ValidationError(f"Enter how many {asset.unit}s.", "quantity")
        return units

    @staticmethod
    def _is_split(t: Transaction) -> bool:
        """An ADJ document marked as a bonus issue, split or reverse split."""
        return t.type == DocType.ADJ and t.description == SPLIT_MARK

    def _is_capital_return(self, t: Transaction) -> bool:
        """A sell document whose holding line has no units: the fund paid part of the cost back."""
        return t.type == DocType.SEL and any(
            ln.quantity == ZERO and ln.effect == Effect.INTERNAL and not self.assets.get_asset(ln.asset_id).is_cash
            for ln in t.lines)

    def _is_holding_opening(self, t: Transaction) -> bool:
        return any(not self.assets.get_asset(ln.asset_id).is_cash for ln in t.lines)
