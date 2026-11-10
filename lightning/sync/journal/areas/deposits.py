"""Certificates of deposit and gam'eya circles.

Not covered: the automatic forecast. Purchases and
redemptions post their transactions through the same services as the cash register. A past-instalments batch writes
three rows per instalment, so a circle with more than twenty overdue instalments is refused whole (record fewer at once).
"""
from .spec import AMOUNT, DATE, INT, TEXT, Command, listof, optional, ref

TABLES = ("cd_certificates", "cd_interest_receipt_events", "cd_interest_receipt_links", "cd_redemptions", "gameya_terms", "cd_terms")

CERTIFICATE = ("cd_certificates", "certificate_id")
# Dates and rates arrive as the form's text (a blank maturity with term years is allowed); the service decides.
TERMS = dict(lockup_end_date=TEXT, maturity_date=TEXT, annual_rate=TEXT, interest_method=TEXT, payout_frequency=TEXT,
             compounding_frequency=TEXT, destination_account_id=ref("accounts"), term_years=TEXT)
CIRCLE = dict(account_id=ref("accounts"))

COMMANDS = {
    "deposits.purchase": Command("deposits.purchase", dict(
        account_id=ref("accounts"), name=TEXT, start_date=TEXT, lockup_end_date=TEXT, maturity_date=TEXT, principal=AMOUNT,
        annual_rate=TEXT, interest_method=TEXT, payout_frequency=TEXT, compounding_frequency=TEXT,
        destination_account_id=ref("accounts"), funding_account_id=ref("accounts"), term_years=TEXT)),
    "deposits.record_owned": Command("deposits.record_owned", dict(
        account_id=ref("accounts"), name=TEXT, start_date=TEXT, lockup_end_date=TEXT, maturity_date=TEXT, principal=AMOUNT,
        annual_rate=TEXT, interest_method=TEXT, payout_frequency=TEXT, compounding_frequency=TEXT,
        destination_account_id=ref("accounts"), term_years=TEXT)),
    # The older account-level terms of a CD, one row per account.
    "deposits.save": Command("deposits.save", dict(
        account_id=ref("accounts"), start_date=TEXT, maturity_date=TEXT, principal=TEXT, annual_rate=TEXT,
        interest_method=TEXT, payout_frequency=TEXT, destination_account_id=ref("accounts"), lockup_end_date=TEXT,
        compounding_frequency=TEXT), target=("cd_terms", ("account_id",))),
    "deposits.update_certificate": Command("deposits.update_certificate", dict(
        certificate_id=ref("cd_certificates"), name=TEXT, **TERMS), target=CERTIFICATE),
    "deposits.redeem": Command("deposits.redeem", dict(
        certificate_id=ref("cd_certificates"), date_value=TEXT, proceeds=AMOUNT, destination_account_id=ref("accounts")),
        target=CERTIFICATE, creates="transactions"),
    "deposits.move_legacy_cash": Command("deposits.move_legacy_cash", dict(
        account_id=ref("accounts"), date_value=TEXT, amount=AMOUNT, destination_account_id=ref("accounts")),
        creates="transactions"),
    "deposit_receipts.confirm": Command("deposit_receipts.confirm", dict(
        certificate_id=ref("cd_certificates"), event_date=DATE, transaction_ids=listof(ref("transactions")), as_of=optional(DATE)),
        target=CERTIFICATE),
    "deposit_receipts.confirm_suggested": Command("deposit_receipts.confirm_suggested", dict(
        account_id=ref("accounts"), certificate_id=optional(ref("cd_certificates")), as_of=optional(DATE))),
    "deposit_receipts.remove": Command("deposit_receipts.remove", dict(
        certificate_id=ref("cd_certificates"), event_date=DATE, transaction_id=ref("transactions")), target=CERTIFICATE),
    "gameya.save_terms": Command("gameya.save_terms", dict(
        CIRCLE, organiser=TEXT, members=TEXT, installment=AMOUNT, first_date=DATE, my_turn=TEXT, payout=TEXT,
        annual_rate=TEXT, funding_account_id=ref("accounts"), payout_account_id=ref("accounts"))),
    "gameya.record_instalment": Command("gameya.record_instalment", dict(
        CIRCLE, date_value=TEXT, amount=TEXT, funding_account_id=optional(ref("accounts"))), creates="transactions"),
    "gameya.record_past_instalments": Command("gameya.record_past_instalments", dict(
        CIRCLE, expected_paid=INT, as_of=optional(DATE))),
    "gameya.record_payout": Command("gameya.record_payout", dict(
        CIRCLE, date_value=TEXT, amount=TEXT, payout_account_id=optional(ref("accounts"))), creates="transactions"),
}
