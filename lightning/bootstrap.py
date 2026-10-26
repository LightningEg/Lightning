"""Composition root: builds the database and wires every service together.

This is the only place that knows how modules connect. The UI receives a ready Container.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from lightning.accounts.service import AccountService
from lightning.assets.service import AssetService
from lightning.budgeting.service import BudgetService
from lightning.planning.forecast import CashForecaster
from lightning.planning.health import HealthService
from lightning.planning.position import PositionService
from lightning.planning.service import PlanningService
from lightning.bank_imports import BankImportService
from lightning.sms_imports import SmsImportService
from lightning.rules.service import RuleService
from lightning.categories.service import CategoryService
from lightning.counterparties import CounterpartyService
from lightning.database.audit import AuditLog
from lightning.database.backup import backed_up_today, backup, list_backups
from lightning.database.connection import Database
from lightning.database.currencies import CurrencyRegistry
from lightning.database.seed import CASH_ASSETS
from lightning.database.migrator import inspect_schema, migrate
from lightning.database.seed import seed
from lightning.database.settings import SettingsStore
from lightning.deposits import DepositService, GameyaService
from lightning.fx import CurrencyRates
from lightning.investments.service import InvestmentService
from lightning.integrity import IntegrityService
from lightning.money_from_others import MoneyFromOthersService
from lightning.ownership_migration import migrate_legacy_ownership
from lightning.physical_items import PhysicalItemService
from lightning.zakat import ZakatService
from lightning.reporting.service import ReportingService
from lightning.reconciliation import ReconciliationService
from lightning.reserves import CashReserveService
from lightning.reevaluations import ReevaluationService
from lightning.transactions.history_check import validate_replay
from lightning.transactions.service import TransactionService
from lightning.workflows.accounts import AccountWorkflows
from lightning.undo import UndoService
from lightning.saved_views import SavedViewService
from lightning.reimbursements import ReimbursementService
from lightning.planning.funding import CashFundingService
from lightning.deposits.receipts import DepositReceiptService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class Container:
    db: Database
    data_dir: Path
    settings: SettingsStore
    fx: CurrencyRates
    audit: AuditLog
    assets: AssetService
    categories: CategoryService
    counterparties: CounterpartyService
    bank_imports: BankImportService
    sms_imports: SmsImportService
    rules: RuleService
    accounts: AccountService
    transactions: TransactionService
    reporting: ReportingService
    reconciliation: ReconciliationService
    reserves: CashReserveService
    reevaluations: ReevaluationService
    money_from_others: MoneyFromOthersService
    physical_items: PhysicalItemService
    budgets: BudgetService
    investments: InvestmentService
    deposits: DepositService
    gameya: GameyaService
    account_flows: AccountWorkflows
    integrity: IntegrityService
    planning: PlanningService
    forecaster: CashForecaster
    position: PositionService
    health: HealthService
    zakat: ZakatService
    backup_dir: Path | None = None
    undo: UndoService | None = None
    saved_views: SavedViewService | None = None
    reimbursements: ReimbursementService | None = None
    funding: CashFundingService | None = None
    deposit_receipts: DepositReceiptService | None = None

    @property
    def base_currency(self) -> str:
        return self.settings.base_currency

    @property
    def currencies(self) -> CurrencyRegistry:
        """The profile's currency registry, so the UI need not import the database layer."""
        return CurrencyRegistry(self.db)

    @property
    def institutions(self):
        """Egypt's institutions plus the ones this profile added."""
        from lightning.accounts.institutions import InstitutionService
        return InstitutionService(self.db)

    @property
    def profile_currencies(self) -> list[tuple[str, str]]:
        """Currencies a profile may start in, as (code, name)."""
        return CASH_ASSETS

    def set_profile_currency(self, code: str) -> None:
        """Change an unused profile's base and refresh the live service graph."""
        CurrencyRegistry(self.db).set_base_currency(code)
        self.refresh_profile_currency()

    def refresh_profile_currency(self) -> None:
        """Point every service that keeps a copy of the profile currency at the stored one.

        The one place that lists those copies: anything that changes `settings.base_currency` (this container,
        a replica applying settings rows) calls it. Reporting's setter also moves its valuer and FX positions."""
        base = self.settings.base_currency
        for service in (self.assets, self.accounts, self.transactions, self.reporting):
            service.base_currency = base
        self.fx.profile_currency = base

    @property
    def activity_review(self):
        from lightning.workflows.activity import ActivityReview
        return ActivityReview(self)

    @property
    def salary_setup(self):
        from functools import partial
        from types import SimpleNamespace
        from lightning.workflows.salary_setup import set_up_salary
        return SimpleNamespace(set_up_salary=partial(set_up_salary, self))

    @property
    def journal_workflows(self):
        from lightning.sync.journal.areas.workflows import JournalWorkflowService
        return JournalWorkflowService(self)

    def backup_now(self) -> Path | None:
        return backup(self.db, self.backup_dir or self.data_dir / "backups")

    def backup_files(self) -> list[Path]:
        folder = self.backup_dir or self.data_dir / "backups"
        current = [entry.path for entry in list_backups(folder, self.db.path)]
        # Preserve visibility of old-format files; never automatically prune or
        # restore legacy copies whose profile identity is not in their filename.
        import re
        legacy = [p for p in folder.iterdir() if p.is_file() and re.fullmatch(
            r"lightning_\d{4}-\d{2}-\d{2}_\d{4}(?:_\d+)?\.db", p.name
        )] if folder.is_dir() else []
        return current + sorted(legacy, key=lambda p: p.name, reverse=True)


class ReadOnlyCopyError(RuntimeError):
    """A copy opened for reading cannot be used as it is (missing, or it needs an upgrade first)."""


def build(db_path: str | Path | None = None, backup_on_start: bool = False, *,
          key: bytes | None = None, backup_dir: Path | None = None, read_only: bool = False,
          experimental_journal: bool = False, source_verified: bool = False) -> Container:
    """Open a ledger and wire its services.

    `backup_on_start` takes an automatic backup at most once a day: none when this ledger already has a
    (non-upgrade) backup dated today (2J). A pending upgrade always takes its own. `source_verified` says the
    caller has just run the integrity checks on this file, so the backup checks only its copy.

    `read_only` opens an actual SQLite read-only connection and skips every startup write: no backup,
    migration, seed or ownership repair. A copy that needs any of them is refused, never upgraded
    (multiple devices plan, section 5, rule 10)."""
    db_path = Path(db_path) if db_path else DEFAULT_DATA_DIR / "lightning.db"
    data_dir = db_path.parent
    existed = db_path.is_file() and db_path.stat().st_size > 0
    if read_only and not existed:
        raise ReadOnlyCopyError("The saved copy is missing or empty.")
    db = Database(db_path, key=key, read_only=read_only)
    try:
        is_journal = bool(db.scalar("SELECT 1 FROM sqlite_master WHERE type='table' AND name GLOB 'journal_*' LIMIT 1"))
        if is_journal and not experimental_journal:
            raise ReadOnlyCopyError("This experimental journal profile requires its journal runtime.")
        inspection = inspect_schema(db)  # Refuse newer schemas before any write.
        if read_only or is_journal:
            if inspection.pending:
                raise ReadOnlyCopyError("This saved copy was made by an older Lightning and needs an upgrade "
                                        "that a read-only copy cannot make.")
        elif existed and (inspection.needs_backup or (
                backup_on_start and not backed_up_today(backup_dir or data_dir / "backups", db_path))):
            saved = backup(db, backup_dir or data_dir / "backups",
                           pre_upgrade=inspection.needs_backup, verify_source=not source_verified)
            if saved is None:
                raise RuntimeError("A verified backup is required before upgrading")
        if not read_only and not is_journal:
            migrate(db)
            seed(db)
            migrate_legacy_ownership(db)
    except BaseException:
        db.close()
        raise
    settings = SettingsStore(db)
    base = settings.base_currency
    fx = CurrencyRates(db, base)
    audit = AuditLog(db)
    assets = AssetService(db, base)
    categories = CategoryService(db)
    accounts = AccountService(db, assets, base)
    transactions = TransactionService(db, accounts, assets, categories, audit, base)
    counterparties = CounterpartyService(db)
    reserves = CashReserveService(db)
    money_from_others = MoneyFromOthersService(db, accounts, transactions, counterparties)
    physical_items = PhysicalItemService(db, accounts, assets, audit)
    rules = RuleService(db, categories, accounts, transactions, settings)
    bank_imports = BankImportService(db, accounts, categories, counterparties, transactions, money_from_others, reserves,
                                     rules)
    reporting = ReportingService(db, accounts, assets, categories, base, money_from_others)
    budgets = BudgetService(db, categories, reporting)
    reevaluations = ReevaluationService(db, accounts, transactions, reporting)
    planning = PlanningService(db, accounts, categories, counterparties, transactions)
    budgets.scheduled_loans = planning.loan_payments_by_category
    budgets.scheduled_bills = planning.budget_fill_schedule
    budgets.scheduled_income = planning.income_a_month
    investments = InvestmentService(db, accounts, assets, categories, transactions, reporting, reevaluations)
    gameya = GameyaService(db, accounts, assets, transactions)
    deposits = DepositService(db, accounts, assets, transactions, gameya)
    position = PositionService(reporting, assets, investments, money_from_others, reserves, planning, deposits)
    forecaster = CashForecaster(planning, reporting, reserves, budgets, categories, position, deposits)
    deposit_receipts = DepositReceiptService(db, deposits, transactions, accounts, reporting)
    forecaster.deposit_receipts = deposit_receipts
    budgets.reserve_goal_needs = forecaster.goal_needs
    health = HealthService(planning, position, budgets)
    forecaster.savings_rate = lambda: health.limit_values()["savings_rate"] or Decimal(0)
    zakat = ZakatService(db, position, reporting, assets, categories, physical_items, audit, gameya)
    result = Container(
        db=db,
        data_dir=data_dir,
        settings=settings,
        fx=fx,
        audit=audit,
        assets=assets,
        categories=categories,
        counterparties=counterparties,
        bank_imports=bank_imports,
        rules=rules,
        sms_imports=SmsImportService(db, settings, accounts, bank_imports),
        accounts=accounts,
        transactions=transactions,
        reporting=reporting,
        reconciliation=ReconciliationService(db, categories, transactions),
        reserves=reserves,
        reevaluations=reevaluations,
        money_from_others=money_from_others,
        physical_items=physical_items,
        budgets=budgets,
        investments=investments,
        deposits=deposits,
        gameya=gameya,
        account_flows=AccountWorkflows(db, accounts, transactions, reporting),
        integrity=IntegrityService(reporting, reserves, budgets, planning, position),
        planning=planning,
        forecaster=forecaster,
        position=position,
        health=health,
        zakat=zakat,
        backup_dir=backup_dir,
        saved_views=SavedViewService(db, categories, transactions, reporting),
        reimbursements=ReimbursementService(db),
        funding=CashFundingService(db, budgets, reporting, reserves, planning, categories, settings),
        deposit_receipts=deposit_receipts,
    )
    if not read_only and not is_journal:
        result.undo = UndoService(db, audit)
        db.undo = result.undo
        result.undo.validate = functools.partial(
            validate_replay, db=db, transactions=transactions, assets=assets, accounts=accounts,
            reconciliation=result.reconciliation)
        def prepare_history_validation(records):
            import json
            ids = set()
            for record in records:
                if record['table_name'] not in {'transactions', 'ledger_entries'}:
                    continue
                for key in ('before_json', 'after_json'):
                    row = json.loads(record[key]) if record[key] else {}
                    value = row.get('transaction_id') if record['table_name'] == 'ledger_entries' else row.get('id')
                    if value is not None:
                        ids.add(value)
            before = [txn for txn_id in ids if (txn := transactions.repo.get(txn_id)) is not None]
            def check_cash():
                after = [txn for txn_id in ids if (txn := transactions.repo.get(txn_id)) is not None]
                dates = [txn.date for txn in before + after]
                if dates:
                    transactions._refuse_cash_below_zero([], min(dates), removed=before, added=after)
            return check_cash
        result.undo.prepare_validation = prepare_history_validation
    return result
