"""Setup on the phone, steps 3 to 6 (IV-11N2): after the profile and its recovery key, one screen each for the first
account, the salary, the cash wallet and this phone's helpers (bank SMS, fingerprint). Then Home's first day.

Owner decisions, 2026-11-20: the first account comes before the salary and can be skipped; a cash wallet is made by
default and its weekly count is explained; SMS and fingerprint are offered, never required. Each step writes through
the same services as the screens that do the job later (accounts, salary setup), so nothing here is a second way to
make an account. ``phone_start`` is "open" while the steps run (a closed app comes back to them) and "done" after.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request

from lightning.core.errors import LightningError, ValidationError
from lightning.planning.domain import PlanKind
from lightning.ui.i18n import translate
from lightning.ui.web import container, redirect, settled_save

STEPS = ("account", "salary", "cash", "phone")   # setup steps 3, 4, 5 and 6 (1 and 2 are the profile and its key)
TOTAL = 6
OPEN, DONE = "open", "done"
KEY = "phone_start"
PENDING_SALARY = "phone_start_salary"   # a salary paid in cash waits here until step 5 makes the wallet
FIRST_DAY = "first_day_bills"           # "open" after setup: Home's first day asks for bills; "none": no regular bills
ACCOUNT_KINDS = (("BANK", "Bank account", "Current or savings, like CIB or NBE"),
                 ("CASH", "Mobile wallet", "Like Vodafone Cash or InstaPay"))


def running(c) -> bool:
    return c.settings.get(KEY) == OPEN


def _step_of(c) -> str:
    """The first step not yet passed: what /start resumes."""
    passed = json.loads(c.settings.get("phone_start_passed") or "[]")
    return next((s for s in STEPS if s not in passed), "phone")


def _pass(c, step: str) -> None:
    passed = json.loads(c.settings.get("phone_start_passed") or "[]")
    if step not in passed:
        c.settings.set("phone_start_passed", json.dumps(passed + [step]))  # not money: steps


def _next(step: str) -> str:
    i = STEPS.index(step)
    return f"/start/{STEPS[i + 1]}" if i + 1 < len(STEPS) else "/"  # not money: steps


def _cash_wallet(c):
    return next((a for a in c.accounts.list(active_only=True) if a.cash_at_hand and a.currency == c.base_currency), None)


def _salary_accounts(c):
    return [a for a in c.accounts.list(active_only=True)
            if a.account_type.value in ("BANK", "CASH") and a.currency == c.base_currency]


def _page(request: Request, step: str, status_code: int = 200, **context):
    from lightning.ui.phone.router import render_phone
    n = STEPS.index(step) + 3  # not money: steps
    back = f"/start/{STEPS[STEPS.index(step) - 1]}" if step != STEPS[0] else ""  # not money: steps
    return render_phone(request, f"phone/start/{step}.html", status_code, step=step, n=n, total=TOTAL, back=back,
                        **context)


def start_router() -> APIRouter:
    router = APIRouter()

    @router.get("/start")
    async def resume(request: Request):
        c = container(request)
        if c.settings.get(KEY) == DONE:
            return redirect("/")
        if not running(c):
            with settled_save(request, c):
                c.settings.set(KEY, OPEN)
                # A new profile speaks the language chosen on Welcome (the gate's cookie); before this it opened in
                # English whatever Welcome had shown.
                chosen = request.cookies.get("lightning_ui_locale", "")
                if chosen in ("en", "ar") and not c.settings.get("locale"):
                    c.settings.set("locale", chosen)
        return redirect(f"/start/{_step_of(c)}")

    @router.post("/start/skip")
    async def skip(request: Request):
        form = await request.form()
        step = str(form.get("step", ""))
        if step not in STEPS:
            return redirect("/start")
        c = container(request)
        with settled_save(request, c):
            _pass(c, step)
        if step == "phone":
            return await _finish(request, c)
        return redirect(_next(step))

    # ---- 3. Your first account
    def account_page(request, values=None, error="", error_field="", status_code=200):
        c = container(request)
        values = values or {"name": "", "institution": "", "account_type": "BANK", "opening_balance": ""}
        return _page(request, "account", status_code, values=values, kinds=ACCOUNT_KINDS, error=error,
                     error_field=error_field, base=c.base_currency,
                     institutions=[row["value"] for row in c.institutions.options()
                                   if row["group"] in ("Used before", "Institutions")][:60],
                     made=[a for a in c.accounts.list(active_only=True) if not a.cash_at_hand])

    @router.get("/start/account")
    async def account(request: Request):
        return account_page(request)

    @router.post("/start/account")
    async def save_account(request: Request):
        c = container(request)
        form = await request.form()
        values = {k: str(form.get(k, "")).strip() for k in ("name", "institution", "account_type", "opening_balance")}
        kind = values["account_type"] if values["account_type"] in dict((k, k) for k, _, _ in ACCOUNT_KINDS) else "BANK"
        locale = request.cookies.get("lightning_ui_locale", "en")
        default = translate(dict((k, label) for k, label, _ in ACCOUNT_KINDS)[kind], locale)
        name = values["name"] or (f"{values['institution']} · {default}" if values["institution"] else default)
        try:
            with settled_save(request, c):
                c.account_flows.open_account(
                    name=name, account_type=kind, opening_date="1900-01-01",
                    opening_balance=values["opening_balance"], currency=c.base_currency,
                    opening_balance_date=_today(), institution=values["institution"], last4="", notes="",
                    owner_id=None)
                _pass(c, "account")
        except LightningError as exc:
            return account_page(request, values, exc.message, exc.field or "", 400)
        return redirect("/start/salary", f"{name} is ready.")

    # ---- 4. Your salary
    def salary_page(request, values=None, error="", error_field="", status_code=200):
        c = container(request)
        accounts = [a for a in _salary_accounts(c) if not a.cash_at_hand]
        values = values or {"amount": "", "payday": "", "account_id": str(accounts[0].id) if accounts else "cash"}
        return _page(request, "salary", status_code, values=values, accounts=accounts, error=error,
                     error_field=error_field, base=c.base_currency,
                     already=bool(c.planning.items((PlanKind.INCOME,))))

    @router.get("/start/salary")
    async def salary(request: Request):
        return salary_page(request)

    @router.post("/start/salary")
    async def save_salary(request: Request):
        c = container(request)
        form = await request.form()
        values = {k: str(form.get(k, "")).strip() for k in ("amount", "payday", "account_id")}
        try:
            with settled_save(request, c):
                if values["account_id"] == "cash":   # paid in cash: the wallet is step 5's, so the salary waits for it
                    _check_salary(values)
                    c.settings.set(PENDING_SALARY, json.dumps({"amount": values["amount"], "payday": values["payday"]}))
                else:
                    c.salary_setup.set_up_salary(**values)
                _pass(c, "salary")
        except LightningError as exc:
            return salary_page(request, values, exc.message, exc.field or "", 400)
        return redirect("/start/cash", "Salary saved." if values["account_id"] != "cash" else "")

    # ---- 5. Your cash wallet
    def cash_page(request, values=None, error="", error_field="", status_code=200):
        c = container(request)
        return _page(request, "cash", status_code, values=values or {"opening_balance": ""}, error=error,
                     error_field=error_field, base=c.base_currency, wallet=_cash_wallet(c),
                     salary_in_cash=bool(c.settings.get(PENDING_SALARY)))

    @router.get("/start/cash")
    async def cash(request: Request):
        return cash_page(request)

    @router.post("/start/cash")
    async def save_cash(request: Request):
        c = container(request)
        form = await request.form()
        values = {"opening_balance": str(form.get("opening_balance", "")).strip()}
        locale = request.cookies.get("lightning_ui_locale", "en")
        try:
            with settled_save(request, c):
                wallet = _cash_wallet(c)
                if wallet is None:
                    wallet = c.account_flows.open_account(
                        name=translate("Cash wallet", locale), account_type="CASH_AT_HAND", opening_date="1900-01-01",
                        opening_balance=values["opening_balance"], currency=c.base_currency,
                        opening_balance_date=_today(), institution="", last4="", notes="", owner_id=None)
                pending = c.settings.get(PENDING_SALARY)
                if pending:
                    c.salary_setup.set_up_salary(account_id=wallet.id, **json.loads(pending))
                    c.settings.set(PENDING_SALARY, "")
                _pass(c, "cash")
        except LightningError as exc:
            return cash_page(request, values, exc.message, exc.field or "", 400)
        return redirect("/start/phone", "Your cash wallet is ready.")

    # ---- 6. This phone: bank SMS and fingerprint
    @router.get("/start/phone")
    async def phone(request: Request):
        source = getattr(request.app.state, "sms_source", None)   # the phone's SMS bridge; none where it cannot read
        if getattr(request.state, "read_only", False):
            source = None
        try:
            permission = source.permission() if source is not None else "unavailable"
        except Exception:  # noqa: BLE001 - a bridge that cannot answer offers the paste instead
            permission = "unavailable"
        return _page(request, "phone", sms=permission, fingerprint=getattr(request.state, "fingerprint_row", ""),
                     csrf=_csrf(request))

    @router.post("/start/finish")
    async def finish(request: Request):
        return await _finish(request, container(request))

    async def _finish(request, c):
        with settled_save(request, c):
            _pass(c, "phone")
            c.settings.set(KEY, DONE)
            if c.settings.get(FIRST_DAY) != "none":
                c.settings.set(FIRST_DAY, OPEN)
        return redirect("/")

    @router.post("/start/no-bills")
    async def no_bills(request: Request):
        """Home's first day: "I have no regular bills" passes the bills step."""
        c = container(request)
        with settled_save(request, c):
            c.settings.set(FIRST_DAY, "none")
        return redirect("/")

    @router.get("/start/samples")
    async def samples(request: Request):
        """A sample instead of setup: the steps end and the empty profile's sample list opens."""
        c = container(request)
        with settled_save(request, c):
            c.settings.set(KEY, DONE)
        return redirect("/#samples")

    return router


def _check_salary(values: dict) -> None:
    from lightning.core.money import to_decimal
    amount = to_decimal(values["amount"], "amount")
    if amount <= 0:
        raise ValidationError("Enter the salary as a number, like 30,000.", "amount")  # Arabic: i18n_onboarding
    if not values["payday"].isdigit() or not 1 <= int(values["payday"]) <= 31:
        raise ValidationError("Choose a payday from 1 to 31.", "payday")


def _today() -> str:
    from lightning.core.dates import today
    return today().isoformat()


def _csrf(request: Request) -> str:
    """The profile pages' own form token: the fingerprint form posts to /profiles/fingerprint."""
    return getattr(request.state, "csrf", "") or ""
