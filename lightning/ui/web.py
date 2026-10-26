"""FastAPI app factory. The UI only calls services/workflows — no SQL, no financial math."""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
from datetime import timedelta

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup, escape
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler
from starlette.middleware.trustedhost import TrustedHostMiddleware

from lightning import DISPLAY_VERSION
from lightning.bootstrap import Container
from lightning.core.dates import fmt_date, month_of, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.figures import FIGURES
from lightning.core.memo import request_cache
from lightning.core.money import ZERO, fmt, quantize, to_decimal
from lightning.workflows import live_prices
from lightning.ui import charts, sections
from lightning.ui.themes import theme_id
from lightning.ui.i18n import BROWSER_UI, localize_html, localized_figures, translate

UI_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))


def _minus(text: str) -> str:
    """Screens show a true minus (−5,000.00); exports keep the ASCII hyphen."""
    return "\u2212" + text[1:] if text.startswith("-") else text


# Reporting pages show money rounded to the nearest unit; stored values, entry fields and registers
# keep their decimals. A template that asks for places explicitly (an input's value) gets them.
_ROUND_MONEY: contextvars.ContextVar[bool] = contextvars.ContextVar("round_money", default=False)
REPORTING_TEMPLATES = ("dashboard/", "budget.html", "birdview/", "investments/index.html", "investments/holding.html", "financial_health.html",
                       "investments/_targets.html", "investments/targets.html", "investments/report_detail.html",
                       "planning/plan.html", "reserves.html", "settings/index.html", "accounts/currencies.html", "zakat.html",
                       "accounts/list.html")


def _money(value, signed: bool = False, places: int | None = None) -> str:
    if places is None:
        places = 0 if _ROUND_MONEY.get() else 2
    if value is None or isinstance(value, Decimal):
        return _minus(fmt(value, places, signed))
    # Re-rendered forms hand back what the user typed ("45,000.00", "−450");
    # show it as typed instead of failing the whole page.
    text = str(value).strip().replace(",", "").replace("\u2212", "-")
    try:
        return _minus(fmt(Decimal(text), places, signed))
    except InvalidOperation:
        return str(value)


def _amount_role(value, role: str, signed: bool = False) -> str:
    """Format a displayed amount by its job: totals are whole, rows have cents, fields keep what was typed."""
    if role == "field":
        # Entry values are already strings in the UI; leave them exactly as entered (including blank values).
        return str(value) if isinstance(value, str) else _money(value, signed, 2)
    if role == "total":
        return _money(value, signed, 0)
    if role == "row":
        # The phone drops ".00" from a whole amount (phone overhaul 2026-10-22); piastres still show when there are any.
        whole = False
        if phone_mode() and value is not None:
            try:
                number = Decimal(str(value).replace(",", "").replace("\u2212", "-"))
                whole = number == number.to_integral_value()
            except InvalidOperation:
                pass
        return _money(value, signed, 0 if whole else 2)
    raise ValueError(f"Unknown amount role: {role}")


def _rate(value) -> str:
    """A currency rate as it is quoted: two decimals (A06), four when it is under 1 (1 JPY = 0.3412 EGP), so a
    small rate never rounds to nothing. Display only; the rate itself is stored and used as entered."""
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    return fmt(number, 2 if abs(number) >= 1 else 4)


def _tone(value) -> str:
    if value is None:
        return ""
    return "neg" if value < ZERO else ("pos" if value > ZERO else "zero")


def _keep_dates(text) -> Markup:
    """Dates never break across lines (a narrow key note would split 2026-10-03 at a hyphen)."""
    return Markup(re.sub(r"\b(\d{4}-\d{2}(?:-\d{2})?)\b", r'<span class="nowrap">\1</span>', str(escape(text))))


def _tr_filter(text, locale="en", values=None, **kwargs):
    # Explicit mappings carry user data (device names), which must stay literal.
    # Existing keyword-only calls retain translation of system labels.
    if values:
        merged = dict(values)
        merged.update(kwargs)
        return translate(text, locale).format(**merged)
    merged = dict(values or {})
    merged.update(kwargs)
    return translate(text, locale, **merged)


templates.env.filters["money"] = _money
templates.env.filters["amount_role"] = _amount_role
templates.env.filters["rate"] = _rate
templates.env.filters["whole"] = lambda value: fmt(Decimal(value), 0)  # half-up like money, never banker's
templates.env.filters["tr"] = _tr_filter


def _tagged(text) -> Markup:
    """A note with each #tag a link to every transaction that carries it."""
    from lightning.transactions.tags import split
    link = Markup('<a class="note-tag" href="/transactions?tag={}">{}</a>')
    return Markup("").join(link.format(quote(tag), piece) if tag else escape(piece)
                           for piece, tag in split(str(text or "")))


templates.env.filters["tagged"] = _tagged


def _phone_chip(text) -> str:
    """A KPI chip on a phone says its period in a few characters (guideline C06.1) and is never cut (C12):
    "until 2026-11-01" -> "2026-11-01", "2026-07 to 2026-09" -> "3 months". Text that would still be cut
    returns "", so the tile shows no chip rather than half a word."""
    import re as _re
    value = str(text or "").strip()
    if value.endswith(" so far"):
        return "So far"
    if found := _re.fullmatch(r"(?:until |to )(\d{4}-\d{2}-\d{2})", value):
        return found.group(1)
    if found := _re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})? to (\d{4})-(\d{2})(?:-\d{2})?", value):
        months = (int(found.group(3)) - int(found.group(1))) * 12 + int(found.group(4)) - int(found.group(2)) + 1
        return f"{months} months" if months > 1 else f"{found.group(1)}-{found.group(2)}"
    return value if len(value) <= 10 and not (" " in value and len(value) > 8) else ""


templates.env.filters["phone_chip"] = _phone_chip


def _signed_pct(value, places: int = 1) -> str:
    """A signed percentage to one decimal ("+6.2", "−1.5"); a value that rounds to zero reads "0.0",
    never "−0.0" or "+0.0" (audit 2026-10-05: a certificate's XIRR showed −0.0%)."""
    text = f"{value:+.{places}f}"
    return text[1:] if float(text) == 0 else text.replace("-", "\u2212")


templates.env.filters["signed_pct"] = _signed_pct
templates.env.filters["tone"] = _tone


def _day_label(date_text, locale: str = "en") -> str:
    """A day header on a phone list (guideline C08.1): Today, Yesterday, then the date as yyyy-mm-dd (A06.1)."""
    now = today()
    text = str(date_text)
    if text == fmt_date(now):
        return translate("Today", locale)
    if text == fmt_date(now - timedelta(days=1)):
        return translate("Yesterday", locale)
    return text


templates.env.filters["day_label"] = _day_label


def _day_nets(rows) -> dict[str, Decimal]:
    """Each day's net on a phone list (phone overhaul 2026-10-22): money in less money out, in the base currency.
    Transfers, investment rows and value updates move nothing in or out, so they are left out."""
    nets: dict[str, Decimal] = {}
    for r in rows:
        if getattr(r, "type", "") in ("IN", "OUT"):
            nets[r.date] = nets.get(r.date, ZERO) + (r.amount_base or r.amount)
    return nets


def _group_value_updates(rows) -> list:
    """A day's value updates (revaluations) become one "Investments moved" row on a phone list, so a month-end
    re-pricing never crowds out the money that moved. Other rows pass through unchanged."""
    from types import SimpleNamespace
    out: list = []
    for r in rows:
        if r.type != "VAL":
            out.append(r)
            continue
        last = out[-1] if out else None
        if last is not None and last.type == "VALS" and last.date == r.date:
            last.count += 1
            last.amount += r.amount_base or r.amount
        else:
            out.append(SimpleNamespace(type="VALS", date=r.date, txn_id=r.txn_id, count=1, amount=r.amount_base or r.amount,
                                       balance=None))
    return out


def _shift_month(month: str, months: int) -> str:
    """yyyy-mm moved by a number of months: the phone's period sheet names last month."""
    year, number = (int(part) for part in str(month)[:7].split("-"))
    index = year * 12 + number - 1 + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


templates.env.globals["day_nets"] = _day_nets
templates.env.filters["group_value_updates"] = _group_value_updates
templates.env.globals["shift_month"] = _shift_month
templates.env.filters["keep_dates"] = _keep_dates


def _units(value) -> str:
    """A quantity with no trailing zeros: 25 units, 1 piece, 12.5 g, 1,250 shares."""
    if value is None:
        return ""
    text = f"{Decimal(value):,.4f}".rstrip("0").rstrip(".")
    return text


templates.env.filters["units"] = _units


def _units_of(value, unit: str) -> str:
    """A quantity with its unit, singular for exactly one: 75 shares, 1 piece, 12.5 grams."""
    if value is None:
        return ""
    unit = (unit or "").strip()
    plural = unit and Decimal(value) != 1 and not unit.endswith("s") and unit.upper() != unit
    return f"{_units(value)} {unit}{'s' if plural else ''}".strip()


templates.env.filters["units_of"] = _units_of


def _compact(value) -> str:
    """A short whole number for tight cells: 950, 9.7k, 12k, 1.2M (signed values keep a −)."""
    if value is None:
        return "—"
    v = Decimal(value)
    sign, v = ("−" if v < 0 else ""), abs(v)
    if v >= 1_000_000:
        text = f"{v / 1_000_000:.1f}M"
    elif v >= 10_000:
        text = f"{quantize(v / 1000, 0):.0f}k"
    elif v >= 1000:
        text = f"{v / 1000:.1f}k"
    else:
        text = f"{quantize(v, 0):.0f}"
    return sign + text.replace(".0k", "k").replace(".0M", "M")


templates.env.filters["compact"] = _compact
templates.env.globals["abs"] = abs
from lightning.accounts.institutions import tile as _institution_tile  # noqa: E402
templates.env.globals["institution_tile"] = _institution_tile


# Pages reached from many places with no Back of their own; the main tabs are left out on purpose.
_REFERER_BACK_PAGES = ("/transactions", "/investments/holding", "/investments/planner", "/investments/prices")


def _back_url(request) -> str:
    """Where a full page's Back button goes: the page it was opened from (``return_to``), only if
    it is a page of this app. Empty when there is nowhere to go back to."""
    raw = str(request.query_params.get("return_to", "") or "")
    if not raw and request.url.path.startswith(_REFERER_BACK_PAGES):
        # The desktop window has no browser Back: detail pages opened from a chart, a row or a
        # report fall back to the in-app page that linked here (same origin only, checked below).
        raw = str(request.headers.get("referer", "") or "")
    parts = urlsplit(raw)
    if parts.netloc and parts.netloc != request.url.netloc:
        return ""
    path = parts.path or ""
    if not path.startswith("/") or path.startswith("//") or path == request.url.path:
        return ""
    query = "&".join(q for q in parts.query.split("&") if q and not q.startswith("popup="))
    return path + (f"?{query}" if query else "")


templates.env.globals["back_url"] = _back_url
templates.env.globals["sections_for"] = sections.for_request
templates.env.globals["fig"] = FIGURES
def build_version(identity: Path = Path(__file__).resolve().parents[1] / "build_identity.txt") -> str:
    """The version Settings shows: the build's own name when the build wrote one (the phone test build
    writes `<version>-test.<commits>+<commit>`), else the source version."""
    try:
        return identity.read_text(encoding="utf-8").strip() or DISPLAY_VERSION
    except OSError:
        return DISPLAY_VERSION


templates.env.globals["app_version"] = build_version()


def container(request: Request) -> Container:
    current = request.app.state.container
    if current is None:
        raise RuntimeError("Financial routes require an unlocked profile")
    return current


PRIVACY_COOKIE = "lightning_privacy"


def privacy_on(request: Request) -> bool:
    """Privacy mode: the window's choice for this sitting, else what the profile remembers. The window
    runs in private mode, so its cookie ends with it; a reader session, which cannot save, keeps the cookie."""
    cookie = request.cookies.get(PRIVACY_COOKIE)
    if cookie in ("0", "1"):
        return cookie == "1"
    current = request.app.state.container
    return current is not None and current.settings.get("privacy_mode") == "1"


templates.env.globals["privacy_on"] = privacy_on


def render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    c = container(request)
    context.setdefault("msg", request.query_params.get("msg", ""))
    note = live_prices.apply_finished(c)  # month-end prices fetched in the background since the profile opened
    if note:
        context["msg"] = f"{context['msg']} {note}".strip()
    context.setdefault("error", "")
    context.setdefault("error_field", "")
    total, owned_total, groups = c.reporting.sidebar(today())
    token = _ROUND_MONEY.set(name.startswith(REPORTING_TEMPLATES))
    try:
        return _render(request, name, status_code, c, total, owned_total, groups, context)
    finally:
        _ROUND_MONEY.reset(token)


_BARE_ERROR_PAGE = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                    "<title>Something went wrong</title><body style='font:16px system-ui;margin:12vh auto;max-width:28rem;"
                    "padding:0 24px;color:#0D2233;background:#F5F8F7'><h1>Something went wrong</h1>"
                    "<p>Lightning could not open this page. Your records are safe.</p><p><a href='/'>Back to the dashboard</a></p>")

_PHONE: contextvars.ContextVar[bool] = contextvars.ContextVar("lightning_phone", default=False)
_PHONE_TEMPLATES: set[str] | None = None


def phone_mode() -> bool:
    """Whether this page renders for the phone app (guideline Part C); for macros, which have no request."""
    return _PHONE.get()


templates.env.globals["phone_mode"] = phone_mode
templates.env.globals["trend_end_labels"] = charts.end_labels


@pass_context
def zakat_on(context) -> bool:
    """Zakat shows only once turned on in Settings."""
    request = context.get("request")
    current = getattr(getattr(getattr(request, "app", None), "state", None), "container", None)
    return bool(current is not None and current.zakat.enabled())


templates.env.globals["zakat_on"] = zakat_on

_LOCALE: contextvars.ContextVar[str] = contextvars.ContextVar("lightning_locale", default="en")


def ui_locale() -> str:
    """The page's language, for macros imported without the page's context (en or ar)."""
    return _LOCALE.get()


templates.env.globals["ui_locale"] = ui_locale


def _phone_template(name: str) -> str:
    """A page with its own phone screen has it under templates/phone/; every other page keeps its own."""
    global _PHONE_TEMPLATES
    if _PHONE_TEMPLATES is None:
        _PHONE_TEMPLATES = {t for t in templates.env.list_templates() if t.startswith("phone/")}
    return f"phone/{name}" if f"phone/{name}" in _PHONE_TEMPLATES else name


def _render(request, name, status_code, c, total, owned_total, groups, context) -> HTMLResponse:
    phone = bool(getattr(request.state, "phone", False))
    if phone:
        name = _phone_template(name)
    marker = _PHONE.set(phone)
    try:
        return _render_page(request, name, status_code, c, total, owned_total, groups, context)
    finally:
        _PHONE.reset(marker)


def _render_page(request, name, status_code, c, total, owned_total, groups, context) -> HTMLResponse:
    locale = c.settings.get("locale") if c is not None else "en"
    locale = locale if locale in ("en", "ar") else "en"
    language = _LOCALE.set(locale)
    try:
        response = _template_response(request, name, status_code, c, locale, total, owned_total, groups, context)
    finally:
        _LOCALE.reset(language)
    return response


# The browser half of the Arabic table, served once as a cached script instead of inside every Arabic page (3AC).
_ARABIC_UI_JS = ("window.LIGHTNING_UI=" + json.dumps(BROWSER_UI, ensure_ascii=False, sort_keys=True) + ";").encode("utf-8")
ARABIC_UI_SRC = "/static/ui-ar.js?v=" + hashlib.sha256(_ARABIC_UI_JS).hexdigest()[:12]


def _template_response(request, name, status_code, c, locale, total, owned_total, groups, context):
    response = templates.TemplateResponse(
        request,
        name,
        {
            "base": c.base_currency,
            "app_theme": theme_id(c.settings.get("appearance_theme")),
            "locale": locale,
            "fig": localized_figures(locale),
            "arabic_ui_src": ARABIC_UI_SRC if locale == "ar" else "",
            "today": fmt_date(today()),
            "this_month": month_of(today()),
            "path": request.url.path,
            "sidebar_total": total,
            "sidebar_owned_total": owned_total,
            "sidebar_groups": groups,
            "csrf": getattr(request.state, "csrf", ""),
            "session_epoch": getattr(request.state, "session_epoch", ""),
            "session_token": getattr(request.state, "session_token", ""),
            "category_groups": c.categories.select_groups,
            "prices_running": live_prices.running(c),
            "action_history": c.undo.available() if c.undo else {},
            "checked_history": c.reconciliation.checked_through(context["account"].id)
                if getattr(context.get("account"), "id", None) else None,
            **context,
        },
        status_code=status_code,
    )
    if locale == "ar":
        response.body = localize_html(response.body.decode("utf-8")).encode("utf-8")
        response.headers["content-length"] = str(len(response.body))
    return response


def redirect(url: str, msg: str = "") -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    return RedirectResponse(url, status_code=303)


# Pages whose header has the period control, and what they remember of it.
PERIOD_PAGES = {"/", "/budget", "/birdview/expenses", "/investments"}
PERIOD_KEYS = ("period", "month", "date_from", "date_to")
PERIOD_COOKIE = "lightning_period"


NOT_USER_ACTIONS = frozenset({"history", "demo", "sample", "exports"})
ACTION_LABELS = {"accounts": "Account changes", "transactions": "Transaction changes", "plan": "Payment plan changes",
                 "reserves": "Reserve changes", "budget": "Budget changes", "imports": "Statement import",
                 "bank-imports": "Statement import", "sms": "SMS review", "rules": "Rule changes",
                 "money-from-others": "Money held for others"}


class RequestCache:
    """Each request computes a repeated figure once (``lightning.core.memo``); a write empties it."""

    def __init__(self, app, state):
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        current = getattr(self.state, "container", None) if scope["type"] == "http" else None
        if current is None:
            return await self.app(scope, receive, send)
        with request_cache(current.db):
            root = scope.get("path", "").strip("/").split("/")[0]
            # Every write is one undoable action (2H), except Undo/Redo themselves, the demo and sample loaders
            # (they fill an empty profile) and exports (they only read).
            if scope.get("method") not in ("GET", "HEAD") and root not in NOT_USER_ACTIONS:
                from lightning.undo import user_action
                with user_action(ACTION_LABELS.get(root, "Saved changes")):
                    status = 500
                    async def action_send(message):
                        nonlocal status
                        if message["type"] == "http.response.start":
                            status = message["status"]
                        await send(message)
                    await self.app(scope, receive, action_send)
                    # Settlement links belong to the action that recorded or
                    # changed the cash, rather than a later read-only page visit.
                    if (status < 400 and getattr(self.state, "container", None) is current
                            and not current.db.closed and not current.db.read_only
                            and not getattr(current, "is_journal", False)):
                        current.planning.match_payments(today())
            else:
                await self.app(scope, receive, send)


def create_app(c: Container | None = None) -> FastAPI:
    from .routes import accounts, activity, bank_imports, birdview, budget, categories, counterparties, dashboard, deposits, exports, financial_health, gameya, history, integrity, investments, merge, payday, physical_items, planning, reimbursements, reserves, rules, search, settings, sms, transactions, weekly, zakat

    app = FastAPI(title="Lightning", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.container = c
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next):
        if request.method == "POST":
            host = request.headers.get("host", "").lower()
            for header in ("origin", "referer"):
                value = request.headers.get(header)
                if value and urlsplit(value).netloc.lower() != host:
                    return PlainTextResponse("Cross-origin form submission blocked.", status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def remembered_period(request: Request, call_next):
        """The period picked in a page header carries over to every page that has one."""
        if request.method != "GET" or request.url.path not in PERIOD_PAGES or request.headers.get("x-lightning-popup"):
            return await call_next(request)
        picked = {k: v for k, v in request.query_params.items() if k in PERIOD_KEYS}
        if not picked:
            saved = dict(parse_qsl(request.cookies.get(PERIOD_COOKIE, "")))
            seen_in = saved.pop("seen_in", "")
            now = month_of(today())
            if saved.get("period", "month") == "month" and saved.get("month") == seen_in and seen_in != now:
                saved["month"] = now   # "this month" moves on with the calendar; a month picked from the past stays
            if saved:  # same page, with the remembered period added to whatever else was asked for
                return RedirectResponse(f"{request.url.path}?{urlencode({**dict(request.query_params), **saved})}", status_code=303)
            return await call_next(request)
        response = await call_next(request)
        if response.status_code == 200:  # only a period that worked is remembered
            response.set_cookie(PERIOD_COOKIE, urlencode({**picked, "seen_in": month_of(today())}),
                                httponly=True, samesite="strict")
        return response

    @app.get("/__health", include_in_schema=False)
    async def health():
        return PlainTextResponse("lightning-ok")

    @app.get("/amount-sum", include_in_schema=False)
    async def amount_sum(text: str = ""):
        """A sum typed in an amount field (120+35*2), worked out so the field shows 190 before saving."""
        try:
            value = to_decimal(text)
        except ValidationError as error:
            return JSONResponse({"error": error.message})
        return JSONResponse({"value": format(value.normalize(), "f")})

    @app.get("/static/ui-ar.js", include_in_schema=False)
    async def arabic_ui_script():
        return Response(_ARABIC_UI_JS, media_type="text/javascript; charset=utf-8")

    app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")
    for module in (dashboard, financial_health, accounts, deposits, gameya, bank_imports, birdview, transactions, budget, investments, physical_items, planning, payday, reimbursements, reserves, history, activity, merge, weekly, integrity, counterparties, categories, rules, settings, search, exports, sms, zakat):
        app.include_router(module.router)

    @app.exception_handler(ValidationError)
    async def invalid_request(request: Request, exc: ValidationError):
        if request.url.path.endswith(".json"):
            return JSONResponse({"error": exc.message}, status_code=422)
        return render(request, "validation_error.html", status_code=422, message=exc.message)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return render(request, "not_found.html", status_code=404, message=exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(request: Request, exc: StarletteHTTPException):
        """An unknown address gets the Not found page; other HTTP errors keep their own answer."""
        if exc.status_code == 404 and not request.url.path.startswith("/static/"):
            return render(request, "not_found.html", status_code=404, message="That page does not exist.")
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        """Any other failure: one calm page with a way forward, never the server's plain error text."""
        logging.getLogger("lightning").exception("Unhandled error on %s", request.url.path)
        try:
            return render(request, "error.html", status_code=500)
        except Exception:
            return HTMLResponse(_BARE_ERROR_PAGE, status_code=500)

    from lightning.sync.journal.proxy import PendingOnHome

    @app.exception_handler(PendingOnHome)
    async def saved_pending(request: Request, exc: PendingOnHome):
        """On a synchronized profile a saved change waits for the home: back to the page, saying so."""
        back = urlsplit(request.headers.get("referer", "")).path
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        if request.url.path.endswith(".json"):
            return JSONResponse({"pending": exc.message}, status_code=202)
        return RedirectResponse(f"{back}?{urlencode({'msg': exc.message})}", status_code=303)

    async def not_covered(request: Request, exc: Exception):
        """A write the journal does not cover reaches the connection guard: say so instead of failing."""
        from lightning.sync.journal.proxy import JournalServices
        if not isinstance(request.app.state.container, JournalServices) or "not authorized" not in str(exc):
            raise exc
        message = "This is not available on a synchronized profile yet."
        if request.url.path.endswith(".json"):
            return JSONResponse({"error": message}, status_code=409)
        back = urlsplit(request.headers.get("referer", "")).path
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        return RedirectResponse(f"{back}?{urlencode({'msg': message})}", status_code=303)

    import sqlite3
    for error in {sqlite3.DatabaseError, getattr(getattr(getattr(c, "db", None), "driver", None), "DatabaseError", sqlite3.DatabaseError)}:
        app.add_exception_handler(error, not_covered)

    app.add_middleware(RequestCache, state=app.state)  # outermost, so every page and middleware shares it
    return app
