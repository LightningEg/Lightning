"""Rules that file transactions by their counterparty, notes or amount, and their one-step "apply to the past".

A rule's account condition stores the account's local id as text inside the rule, which another device cannot read
back, so a rule that names an account is refused on a synchronized profile. The preview token of "apply to the
past" is computed from local ids: the home refuses it if the rows are not as the device saw them.
"""
from .spec import TEXT, Command, listof, mapping, optional, ref

# Keep this portable spec independent of the application-layer rules service.
MAX_PARTS = 3
TABLES = ("rules", "rule_conditions", "rule_actions")

PARTS = {f"part_{kind}_{i}": spec for i in range(1, MAX_PARTS + 1)
         for kind, spec in (("category", optional(ref("categories"))), ("value", TEXT))}
RULE = mapping(match=TEXT, counterparty_op=TEXT, counterparty=TEXT, notes=TEXT, amount_op=TEXT, amount=TEXT,
               amount_to=TEXT, account_id=optional(ref("accounts")), direction=TEXT,
               category_id=optional(ref("categories")), tag=TEXT, **PARTS)
TARGET = ("rules", "rule_id")


def _form(values):
    """The service reads the form's text: a chosen category arrives as its id's digits."""
    return values | dict(values={key: str(item) if type(item) is int else item for key, item in values["values"].items()})


def _portable_account(c, values):
    fields = dict(values["values"])
    local_id = fields.get("account_id")
    if type(local_id) is int or type(local_id) is str and local_id.isdigit():
        fields["account_id"] = c.db.scalar("SELECT code FROM accounts WHERE id=?", (int(local_id),)) or ""
    return values | dict(values=fields)


COMMANDS = {
    # A new rule has no rule_id; an edit names the rule, which keeps its identity.
    "rules.save": Command("rules.save", dict(values=RULE, rule_id=optional(ref("rules"))), target=TARGET, creates="rules",
                          adapt=_form, prepare=_portable_account),
    "rules.delete": Command("rules.delete", dict(rule_id=ref("rules")), target=TARGET),
    "rules.apply_past": Command("rules.apply_past", dict(
        rule_id=ref("rules"), selected_ids=listof(ref("transactions")), fingerprint=TEXT), target=TARGET),
    # The token names the last application, which sits in the settings.
    "rules.undo": Command("rules.undo", dict(token=TEXT)),
}
