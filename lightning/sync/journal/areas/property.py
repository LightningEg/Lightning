"""Property (NF-12M): the instalment schedule of a flat bought off plan, and the rent and costs that belong to it.

`property.save_contract` creates or changes the planned bill behind the schedule in the same command; paying an
instalment posts the transfer and marks that due date paid; rent and costs post the money row and link it.
"""
from .spec import AMOUNT, DATE, TEXT, Command, choice, optional, ref

TABLES = ("property_contracts", "property_flows")

PROPERTY = dict(account_id=ref("accounts"))
COMMANDS = {
    "property.save_contract": Command("property.save_contract", dict(
        PROPERTY, instalment=AMOUNT, frequency=choice("MONTHLY", "QUARTERLY", "YEARLY"), first_date=DATE,
        payment_count=TEXT, funding_account_id=ref("accounts")), creates="planned_items"),
    "property.pay_instalment": Command("property.pay_instalment", dict(
        PROPERTY, due_date=DATE, date_paid=optional(DATE), amount=optional(AMOUNT),
        from_account_id=optional(ref("accounts"))), creates="transactions"),
    "property.record_flow": Command("property.record_flow", dict(
        PROPERTY, kind=choice("rent", "cost"), date_value=optional(DATE), amount=AMOUNT,
        cash_account_id=ref("accounts"), notes=TEXT), creates="transactions"),
}
