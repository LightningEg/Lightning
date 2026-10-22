"""Master data: accounts and categories."""
from .spec import AMOUNT, DATE, FLAG, LONG, TEXT, Command, choice, optional, ref

TABLES = ("asset_classes", "financial_assets", "accounts", "categories", "institutions",
          "other_asset_valuations")

# Every type; a type whose tables are not synchronized yet is refused by the home.
ACCOUNT_TYPES = choice("BANK", "CASH", "CASH_AT_HAND", "DEPOSIT", "BROKERAGE", "PHYSICAL_ASSET", "OTHER_ASSET", "GAMEYA")


def _valuation_account(c, values):
    return values | {"account": c.accounts.get(values["account"])}


def _account_institution(c, values):
    """Keep a newly typed institution in the same atomic command as its account."""
    name = " ".join(str(values.get("institution") or "").split())
    if name:
        c.institutions.add(name)
    return values


COMMANDS = {
    # A free-text institution is saved before the account. Built-in matches are a no-op.
    "institutions.add": Command("institutions.add", dict(name=TEXT)),
    "reporting.other_asset_values.save": Command("reporting.other_asset_values.save", dict(
        account=ref("accounts"), effective_date=DATE, amount=AMOUNT, notes=TEXT),
        target=("other_asset_valuations", ("account", "effective_date")), prepare=_valuation_account),
    "accounts.open": Command("account_flows.open_account", dict(
        name=TEXT, account_type=ACCOUNT_TYPES, opening_date=DATE, opening_balance=AMOUNT, institution=TEXT,
        currency=optional(TEXT), last4=optional(TEXT), notes=LONG, opening_balance_date=optional(DATE),
        owner_id=optional(ref("counterparties"))), creates="accounts", prepare=_account_institution),
    "accounts.update": Command("accounts.update", dict(
        account_id=ref("accounts"), name=TEXT, institution=TEXT, account_type=ACCOUNT_TYPES, opening_date=DATE,
        last4=optional(TEXT), notes=LONG), target=("accounts", "account_id")),
    "accounts.set_active": Command("accounts.set_active", dict(account_id=ref("accounts"), active=FLAG),
                                   target=("accounts", "account_id")),
    # The account screens call the workflow layer.
    "account_flows.update_account": Command("account_flows.update_account", dict(
        account_id=ref("accounts"), name=TEXT, account_type=ACCOUNT_TYPES, opening_date=DATE, opening_balance=AMOUNT,
        institution=TEXT, last4=optional(TEXT), notes=LONG, opening_balance_date=optional(DATE),
        owner_id=optional(ref("counterparties"))), target=("accounts", "account_id"), prepare=_account_institution),
    "account_flows.deactivate": Command("account_flows.deactivate", dict(account_id=ref("accounts")),
                                        target=("accounts", "account_id")),
    "account_flows.reactivate": Command("account_flows.reactivate", dict(account_id=ref("accounts")),
                                        target=("accounts", "account_id")),
    "categories.create": Command("categories.create", dict(
        parent_id=ref("categories"), name=TEXT, default_reimbursable=optional(FLAG)), creates="categories"),
    "categories.update": Command("categories.update", dict(
        category_id=ref("categories"), name=TEXT, active=FLAG, default_reimbursable=optional(FLAG)),
        target=("categories", "category_id")),
    "categories.set_direction": Command("categories.set_direction", dict(
        category_id=ref("categories"), direction=choice("IN", "OUT", "BOTH")), target=("categories", "category_id")),
    # Deletes an unused category, else archives it (and what is under it): the result says which.
    "categories.delete_or_archive": Command("categories.delete_or_archive", dict(category_id=ref("categories")),
                                            target=("categories", "category_id")),
    "accounts.set_spendable": Command("accounts.set_spendable", dict(account_id=ref("accounts"), choice=optional(FLAG)),
                                      target=("accounts", "account_id")),
}
