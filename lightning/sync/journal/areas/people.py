"""People: counterparty names and aliases, money held for others."""
from decimal import Decimal

from .spec import AMOUNT, DATE, FLAG, LONG, RATE, TEXT, Command, optional, ref

TABLES = ("counterparty_aliases", "money_from_others", "owed_to_you_accounts")
PERSON = ("counterparties", "counterparty_id")
CUSTODY = dict(transaction_id=ref("transactions"), day=DATE, owner=optional(TEXT), amount=AMOUNT, notes=LONG)
# NF-12G: money lent to a person. The first lend makes the person's Owed to you account and its link row.
LENT = dict(day=DATE, person_id=ref("counterparties"), amount=AMOUNT, notes=LONG)
COMMANDS = {
    "people_money.lend": Command("people_money.lend", LENT | dict(from_account_id=ref("accounts")),
                                 creates="transactions"),
    "people_money.repay": Command("people_money.repay", LENT | dict(to_account_id=ref("accounts")),
                                  creates="transactions"),
    "people_money.forgive": Command("people_money.forgive", LENT | dict(category_id=ref("categories")),
                                    creates="transactions"),
    "counterparties.add_alias": Command("counterparties.add_alias", dict(counterparty_id=ref("counterparties"), alias=TEXT),
                                        target=("counterparties", "counterparty_id")),
    # Returns an existing person or a new one, so it binds nothing and has no precondition.
    "counterparties.ensure_person": Command("counterparties.ensure_person", dict(name=TEXT)),
    "money_from_others.sync_transaction": Command("money_from_others.sync_transaction",
                                                  CUSTODY | dict(account_id=ref("accounts"))),
    "money_from_others.sync_transfer": Command("money_from_others.sync_transfer",
                                               CUSTODY | dict(source_id=ref("accounts"), target_id=ref("accounts"))),
    "counterparties.rename": Command("counterparties.rename", dict(
        counterparty_id=ref("counterparties"), name=TEXT, default_category_id=optional(ref("categories"))), target=PERSON),
    "counterparties.set_kind": Command("counterparties.set_kind", dict(
        counterparty_id=ref("counterparties"), kind=optional(TEXT)), target=PERSON),
    "counterparties.set_active": Command("counterparties.set_active", dict(
        counterparty_id=ref("counterparties"), active=FLAG), target=PERSON),
    "counterparties.set_default_category": Command("counterparties.set_default_category", dict(
        counterparty_id=ref("counterparties"), category_id=optional(ref("categories"))), target=PERSON),
    "counterparties.delete_or_archive": Command("counterparties.delete_or_archive", dict(
        counterparty_id=ref("counterparties")), target=PERSON),
    "counterparties.rename_alias": Command("counterparties.rename_alias", dict(
        counterparty_id=ref("counterparties"), alias_id=ref("counterparty_aliases"), alias=TEXT), target=PERSON),
    "counterparties.remove_alias": Command("counterparties.remove_alias", dict(
        counterparty_id=ref("counterparties"), alias_id=ref("counterparty_aliases")), target=PERSON),
    # Money held for others: the entry form (a person's name; the service finds or saves the person) and the
    # custody of investment units. Neither is preconditioned on one row.
    "money_from_others.record": Command("money_from_others.record", dict(
        day=DATE, owner=TEXT, account_id=ref("accounts"), amount=AMOUNT, notes=LONG)),
    "money_from_others.sync_investment": Command("money_from_others.sync_investment", dict(
        transaction_id=ref("transactions"), day=DATE, owner=optional(TEXT), account_id=ref("accounts"),
        asset_id=ref("financial_assets"), units=RATE),
        adapt=lambda values: values | dict(units=Decimal(values["units"]))),
}
