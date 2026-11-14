"""The phone's register (templates/phone/register.html): the filter chips, the month stepper with its sheet and the two
tiles, shaped from what the register page already worked out (3AY11)."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

from lightning.core.dates import fmt_date, parse_month, today
from lightning.core.money import ZERO
from lightning.ui.web import _shift_month as shift_month

FAR_PAST, FAR_FUTURE = "1900-01-01", "9999-12-31"


def _phone_register(c, account_id, base_url, keep, kind, month, preset, from_query, to_query,
                    matched_flows, unsorted_ids, date_from, date_to) -> dict:
    """What the phone's register shows above its list (phone overhaul 2026-10-22): the filter chips, the month
    stepper with its sheet, and the two tiles. Money in and Money out are the period's own (cash_flow for every
    account), or those of the rows a search, tag or category found. Every link keeps the other choices."""
    keep = {k: v for k, v in keep.items() if k != "page"}
    if month or preset not in ("", "custom"):   # a month or a preset says its own days: they need not ride along
        keep = {k: v for k, v in keep.items() if k not in ("date_from", "date_to")}

    def href(changes: dict) -> str:
        params = {k: v for k, v in {**keep, **changes}.items() if v not in ("", None)}
        return base_url + ("?" + urlencode(params) if params else "")  # not money

    now = fmt_date(today())[:7]
    last = shift_month(now, -1)
    ranged = {"month": "", "preset": "", "date_from": "", "date_to": ""}
    chosen = month or (now if preset == "this_month" else last if preset == "last_month" else "")
    if chosen:
        shown = "month"
    elif preset == "year_to_date":
        shown = "ytd"
    elif preset == "custom" and from_query and to_query:
        shown = "custom"
    else:
        shown = "all"
    # An account's page leads with its balance and its list: the two tiles come once a period or a search narrows it.
    tiles = account_id is None or shown != "all" or matched_flows is not None
    money_in, money_out = (matched_flows if matched_flows is not None else
                           c.reporting.register_flows(account_id, date_from, date_to)) if tiles else (ZERO, ZERO)
    # An empty month offers the month before with its figure instead of a wall of zeros (3AN9).
    earlier = None
    if shown == "month" and tiles and matched_flows is None and not kind and money_in == ZERO and money_out == ZERO:
        before = shift_month(chosen, -1)
        start, end = parse_month(before)
        was_in, was_out = c.reporting.register_flows(account_id, start, end)
        if was_in or was_out:
            earlier = {"month": before, "out": -was_out, "in": was_in, "href": href({**ranged, "month": before})}
    # IV-11M8: an account's hero always shows its In / Out; with no period chosen they are this month's.
    hero_in, hero_out, hero_month = money_in, money_out, shown == "month"
    if account_id is not None and shown == "all" and matched_flows is None:
        hero_in, hero_out = c.reporting.register_flows(account_id, *parse_month(now))
        hero_month = True
    return {
        "hero_in": hero_in, "hero_out": -hero_out, "hero_month": hero_month, "hero_wells": tiles or hero_month,
        "earlier": earlier,
        "chips": [{"key": key, "label": label, "href": href({"kind": "" if key == "all" else key}),
                   "chosen": kind == ("" if key == "all" else key), "count": len(unsorted_ids) if key == "unsorted" else 0}
                  for key, label in (("all", "All"), ("in", "In"), ("out", "Out"), ("transfer", "Transfers"), ("unsorted", "To sort"))],
        "period": shown, "month": chosen, "this": now, "last": last,
        "prev": href({**ranged, "month": shift_month(chosen, -1)}) if chosen else "",
        "next": href({**ranged, "month": shift_month(chosen, 1)}) if chosen and chosen < now else "",
        "this_href": href({**ranged, "month": now}), "last_href": href({**ranged, "month": last}),
        "ytd_href": href({**ranged, "preset": "year_to_date"}), "all_href": href({**ranged, "preset": "all_time"}),
        "ytd_from": f"{now[:4]}-01",
        # taking a tag or a category off again
        "clear_tag": href({"tag": "", **({"q": ""} if keep.get("q", "").startswith("#") else {})}),
        "clear_category": href({"category_id": ""}),
        "tiles": tiles, "money_in": money_in, "money_out": -money_out,
        # a row opened from To sort walks that list: its account and days ride along (3AN3)
        "sort_qs": urlencode({"sort": 1, "sa": account_id or "", "sf": "" if date_from == FAR_PAST else date_from,
                              "st": "" if date_to == FAR_FUTURE else date_to}) if kind == "unsorted" else "",
        # what a form that adds one choice must send along: every other choice already made
        "keep_for_search": [(k, v) for k, v in keep.items() if k != "q"],
        "keep_for_dates": [(k, v) for k, v in keep.items() if k not in ranged],
    }


def present(request, c, context: dict) -> dict:
    """The page's own choices (its kept query, kind, month, preset and dates) are in its context; "To sort" is counted
    here, since only the phone's chip shows it."""
    account_id = context["view_account_id"] or None
    date_from, date_to = context["span"]
    kind = context["chosen_kind"]
    unsorted = context["unsorted_ids"] if kind == "unsorted" else c.reporting.register_unsorted(account_id, date_from, date_to)
    return {"reg": _phone_register(c, account_id, context["base_url"], dict(parse_qsl(context["keep_qs"])), kind,
                                   context["month"], context["preset"], context["date_from"], context["date_to"],
                                   context["matched_flows"], unsorted, date_from, date_to),
            "matching_ids": None, "import_accounts": [],
            # 3AY10: an account's page asks first whether the bank agrees (r25 › Money › An account)
            "checked_through": c.reconciliation.checked_through(account_id) if account_id else None,
            "today_iso": fmt_date(today())}
