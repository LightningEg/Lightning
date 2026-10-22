"""Opt-in experimental journal screens; receives a service, never a database.

The runtime supplies a per-unlock cookie and a pinned local-sync callback. This
factory is deliberately separate from the production/v1 application.
"""
from __future__ import annotations

import hmac
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.formparsers import MultiPartParser, MultiPartException

from lightning.core.errors import LightningError
from lightning.core.money import fmt
from lightning.core.dates import today
from lightning.sync.journal.capture import JournalCapture
from lightning.sync.journal.codec import JournalError


def _command_label(name):
    from lightning.ui.journal_i18n import action_name
    return action_name(name)


def _looks_like_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        from uuid import UUID
        UUID(value)
        return True
    except ValueError:
        return False


def _reference_name(device, entity, value):
    if device is None or not isinstance(value, str):
        return None
    try:
        local_id = device.adapter.local(entity, value)
        service_name, getter_name = {
            "accounts": ("accounts", "get"), "categories": ("categories", "get"),
            "financial_assets": ("assets", "get_asset"), "transactions": ("transactions", "get"),
            "counterparties": ("counterparties", "get"), "cash_reserves": ("reserves", "get"),
            "planned_items": ("planning", "get"), "cd_certificates": ("deposits", "get_certificate"),
        }.get(entity, (None, None))
        if service_name is None:
            return None
        obj = getattr(getattr(device.c, service_name), getter_name)(local_id)
        for attr in ("name", "counterparty", "description"):
            shown = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
            if shown:
                return str(shown)
    except Exception:
        return None
    return None


def _command_summary(device, kind, args):
    from lightning.ui.journal_i18n import FIELD_NAMES
    from lightning.sync.journal.commands import COMMANDS

    entry = COMMANDS.get(kind)
    specs = entry.args if entry is not None else {}
    hidden = {"password", "secret", "token", "recovery", "answer", "fingerprint", "job_key",
              "messages", "data", "mapping", "decisions", "selected_ids", "txn_ids", "notes",
              "expected_remaining", "ending", "cursor_ms"}
    rows = []
    for key, value in args.items():
        if key.lower() in hidden or value is None:
            continue
        spec = specs.get(key, "")
        entity = spec.lstrip("?")[len("ref:"):] if isinstance(spec, str) and spec.lstrip("?").startswith("ref:") else None
        label = FIELD_NAMES.get(key)
        if entity:
            shown = _reference_name(device, entity, value)
            label = label or {"accounts": "Account", "categories": "Category", "financial_assets": "Investment",
                              "transactions": "Transaction", "counterparties": "Payee"}.get(entity)
            if not shown:
                shown = {"accounts": "Selected account", "categories": "Selected category",
                         "financial_assets": "Selected investment", "transactions": "Selected transaction"}.get(entity, "Details provided")
        elif isinstance(value, list):
            shown = f"{len(value)} selected"
        elif isinstance(value, dict):
            shown = "Details provided"
        elif isinstance(value, bool):
            shown = "Yes" if value else "No"
        elif _looks_like_uuid(value) or (key.endswith("_id") and not key.endswith("account_id")):
            continue
        elif key in {"account_type", "class_code", "kind", "direction", "frequency", "interest_method",
                     "payout_frequency", "compounding_frequency", "bucket", "choice", "action"}:
            if key in {"class_code"}:
                continue
            shown = value.replace("_", " ").title() if isinstance(value, str) else str(value)
        else:
            shown = str(value)
        label = label or key.replace("_", " ").capitalize()
        rows.append((label, shown))
        if len(rows) == 5:
            break
    return rows


def command_status_rows(device):
    """Return terminal and pending command outcomes using the service's durable receipts."""
    from lightning.sync.journal.codec import unpack

    rows, seen = [], set()
    for item in device.pending_commands():
        rows.append(dict(proposal_id=item["proposal_id"],
                         name=_command_label(item["name"]), state=item["state"],
                         reason="Waiting for the home" if item["state"] == "Pending" else "The home needs to review this action",
                         summary=_command_summary(device, "command." + item["name"], item.get("args", {}))))
        seen.add(item["proposal_id"])
    for decision in device.command_decisions():
        proposal = unpack(decision["proposal"])["body"]
        receipt = unpack(decision["decision"])["body"]
        identifier = proposal["origin"]
        # The receipt's stable id is the index used by the outbox and display marker.
        from lightning.sync.journal.codec import origin_id
        identifier = origin_id(identifier)
        if identifier in seen:
            continue
        if not proposal["kind"].startswith("command."):
            continue
        if receipt["outcome"] == "rejected":
            if decision["first_display_at"]:
                continue
            state = "Not taken"
            reason = {"cancelled": "The home kept the confirmed value",
                      "dependency-rejected": "An earlier action was not taken",
                      "financial-validation": "The home could not apply this action"}.get(receipt["reason"], "The home could not apply this action")
        else:
            state, reason = "Confirmed", "Applied on the home"
        rows.append(dict(proposal_id=identifier,
                         name=_command_label(proposal["kind"][len("command."):]),
                         state=state, reason=reason,
                         summary=_command_summary(device, proposal["kind"], proposal["groups"].get("args", {}))))
    return rows


def command_values(kind, args, device=None):
    return [("Action", _command_label(kind[len("command."):]))] + _command_summary(device, kind, args)


class BoundedJournalBody:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        limit = 4096 if scope["path"] in ("/pairing/exchange", "/membership/exchange", "/authority/exchange") else 64 * 1024 if scope["path"] in ("/exchange","/enrollment/exchange") else 6 * 1024 * 1024
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            chunk = event.get("body", b"")
            total += len(chunk)
            if total > limit:
                return await PlainTextResponse("The upload is too large.", status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not event.get("more_body"):
                break
        async def buffered():
            nonlocal chunks
            if chunks is not None:
                body, chunks = b"".join(chunks), None
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        await self.app(scope, buffered, send)


def create_journal_app(device, *, session_token, channel=None, synchronize=None, sms_source=None, pairing=None, move=None):
    if not isinstance(session_token, str) or len(session_token) < 32:
        raise ValueError("A per-unlock session token is required")
    sync_task = None
    sync_requested = False
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if sync_task:
                sync_task.cancel()
                await asyncio.gather(sync_task, return_exceptions=True)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    def schedule():
        nonlocal sync_task, sync_requested
        sync_requested = True
        if synchronize and (sync_task is None or sync_task.done()):
            async def catch_up():
                nonlocal sync_requested
                while sync_requested:
                    sync_requested = False
                    await asyncio.sleep(0.2)
                    try:
                        await synchronize()
                    except (OSError, TimeoutError, JournalError):
                        break  # Capture is durable; retries never discard pending edits.
            sync_task = asyncio.create_task(catch_up())
    app.add_middleware(BoundedJournalBody)
    root = Path(__file__).parent
    templates = Jinja2Templates(directory=str(root / "journal_views"))
    app.mount("/static", StaticFiles(directory=root / "static"), name="static")
    capture = JournalCapture(device)

    @app.middleware("http")
    async def guard(request, call_next):
        if not request.url.path.startswith("/static/") and request.url.path not in ("/exchange", "/pairing/exchange", "/membership/exchange", "/enrollment/exchange", "/authority/exchange"):
            token = request.cookies.get("journal_session", "")
            if not hmac.compare_digest(token.encode("utf-8"), session_token.encode("utf-8")):
                return PlainTextResponse("Unlock this experimental profile first.", status_code=401)
            if request.method == "POST" and request.headers.get("origin") != str(request.base_url).rstrip("/"):
                return PlainTextResponse("Open the form again before saving.", status_code=403)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; frame-ancestors 'none'; form-action 'self'"})
        return response

    async def form(request):
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            parser = MultiPartParser(request.headers, request.stream(), max_files=1, max_fields=80,
                                     max_part_size=5 * 1024 * 1024)
            parser.spool_max_size = 6 * 1024 * 1024  # The bounded body can never exceed this.
            try:
                data = await parser.parse()
            except MultiPartException as error:
                raise JournalError("Check the upload and open the form again") from error
        else:
            data = await request.form(max_files=0, max_fields=80)
        if not hmac.compare_digest(str(data.get("__session", "")).encode("utf-8"), session_token.encode("utf-8")):
            raise JournalError("Open the form again before saving")
        return data

    def render(request, *, error="", message="", editing=None, candidate=None, initial=None):
        editing = device.canonical_record(editing) if editing else None
        phone = "Mobile" in request.headers.get("user-agent", "") or "Android" in request.headers.get("user-agent", "")
        path = request.url.path
        page = "devices" if path.startswith("/devices") else "entry" if editing or candidate or initial or path == "/add" else "capture" if path.startswith("/capture") else "review" if path.startswith("/review") else "balances" if path == "/balances" else "register"
        rows = device.view()
        command_rows = command_status_rows(device)
        reviews = []
        if device.home:
            reviews = device.review_items()
            for review in reviews:
                review["command"] = str(uuid4())
                proposed = review["proposed"]
                review["is_command"] = proposed["kind"].startswith("command.")
                if review["is_command"]:
                    review["proposed_shown"] = command_values(proposed["kind"], proposed["groups"].get("args", {}), device)
                    review["current_shown"] = device.describe(review["current"]["groups"]) if review["current"] and review["current"].get("groups") else []
                    review["base_shown"] = []
                else:
                    review["proposed_shown"] = device.describe(proposed["groups"])
                    review["current_shown"] = device.describe(review["current"]["groups"]) if review["current"] else []
                    review["base_shown"] = device.describe(review["base"]) if review["base"] else []
        values = {"date": today().isoformat()}
        if editing:
            selected = next((row for row in rows if row["record"] == editing and row["state"] != "Not taken"), None)
            if selected:
                values = device.form_values(selected["groups"])
        if initial is not None:
            values = device.form_values(initial)
        if candidate:
            values = device.form_values(capture.get(candidate))
        draft = device.draft(editing, initial=initial) if not candidate else ""
        balances = [row | dict(shown=fmt(row["balance"], 0)) for row in device.balances()]
        try:
            sms_permission = sms_source.permission() if sms_source is not None else "unavailable"
        except Exception:
            sms_permission = "unavailable"
        return templates.TemplateResponse(request=request, name="phone.html" if phone else "pc.html",
            context=dict(rows=rows, command_rows=command_rows, reviews=reviews, balances=balances, choices=device.choices(),
                waiting=[item | {"shown": device.form_values(item["groups"])} for item in capture.waiting()], batches=capture.batches(), home=device.home is not None, values=values,
                editing=editing, candidate=candidate, draft=draft, session=session_token, error=error, message=message,
                split_count=max(4, sum(key.startswith("split_category_") for key in values)),
                currency=device.c.base_currency, sms_available=sms_source is not None, sms_permission=sms_permission, phone=phone, page=page,
                pairing=pairing.screen() if pairing is not None else dict(enabled=False),
                version=version(), sync=device.sync_status()), status_code=400 if error else 200)

    def version():
        from lightning.sync.journal.codec import digest
        return digest(dict(ledger=device.view_version(), pairing=pairing.screen() if pairing is not None else None))

    @app.exception_handler(JournalError)
    @app.exception_handler(LightningError)
    async def failure(request, error):
        if request.url.path in ("/exchange", "/pairing/exchange", "/membership/exchange", "/enrollment/exchange", "/authority/exchange"):
            from lightning.sync.journal.local import MembershipUpdateRequired
            if isinstance(error,MembershipUpdateRequired):
                return PlainTextResponse("Membership update required.",status_code=409,headers={"X-Journal-Action":"membership"})
            return PlainTextResponse("Local journal request refused.", status_code=403)
        return render(request, error=str(error))

    @app.get("/", response_class=HTMLResponse)
    @app.get("/add", response_class=HTMLResponse)
    @app.get("/capture", response_class=HTMLResponse)
    @app.get("/review", response_class=HTMLResponse)
    @app.get("/balances", response_class=HTMLResponse)
    @app.get("/devices", response_class=HTMLResponse)
    async def index(request: Request):
        schedule()
        return render(request)

    @app.get("/status")
    async def status(request: Request):
        return JSONResponse({"version": version()})

    @app.post("/pairing/exchange")
    async def pairing_exchange(request: Request):
        if pairing is None:
            return PlainTextResponse("Pairing is not open.",status_code=403)
        body = await request.body()
        if len(body) > 4096:
            return PlainTextResponse("Pairing request refused.",status_code=413)
        return Response(pairing.exchange(body),media_type="application/octet-stream")

    @app.post("/enrollment/exchange")
    async def enrollment_exchange(request: Request):
        if pairing is None or pairing.enrollment is None:
            return PlainTextResponse("Enrollment unavailable.",status_code=403)
        return Response(pairing.enrollment.exchange(await request.body()),media_type="application/octet-stream")

    @app.post("/membership/exchange")
    async def membership_exchange(request: Request):
        if pairing is None:
            return PlainTextResponse("Membership unavailable.",status_code=403)
        return Response(pairing.membership.control(await request.body()),media_type="application/octet-stream")

    @app.post("/authority/exchange")
    async def authority_exchange(request: Request):
        if move is None:
            return PlainTextResponse("Authority handoff unavailable.", status_code=403)
        body = await request.body()
        if len(body) > 4096:
            return PlainTextResponse("Authority request refused.", status_code=413)
        return Response(move.exchange(body), media_type="application/octet-stream")

    @app.post("/devices/{action}")
    async def device_action(request: Request, action: str):
        data = await form(request)
        if pairing is None:
            raise JournalError("Nearby pairing is unavailable in this preview")
        if action == "open":
            pairing.begin(str(data.get("password","")))
        elif action == "stop":
            pairing.stop()
        elif action == "find":
            await pairing.find()
        elif action == "join":
            await pairing.join(str(data.get("candidate","")),str(data.get("code","")))
        elif action == "compare":
            pairing.compare(str(data.get("digits","")))
        elif action == "prove":
            await pairing.prove(str(data.get("password","")))
        elif action == "cancel":
            pairing.cancel()
        elif action == "confirm":
            pairing.confirm(str(data.get("digits","")))
        elif action == "check":
            if data.get("automatic") == "1":
                try:
                    await pairing.finish()
                except (JournalError,OSError,TimeoutError):
                    return JSONResponse(dict(paired=False))
                schedule()
                return JSONResponse(dict(paired=True))
            await pairing.finish()
            schedule()
        else:
            raise JournalError("Unknown device action")
        return RedirectResponse("/devices",status_code=303)

    @app.get("/edit/{record}", response_class=HTMLResponse)
    async def edit(request: Request, record: str):
        return render(request, editing=record)

    @app.post("/save")
    async def save(request: Request):
        data = await form(request)
        groups = device.form_groups(data)
        device.submit_draft(str(data.get("draft", "")), groups)
        schedule()
        return render(request, message="Saved on this device" if device.home else "Saved on this device · Pending")

    @app.post("/delete/{record}")
    async def delete(request: Request, record: str):
        data = await form(request)
        device.submit_draft(str(data.get("draft", "")), {}, delete=True)
        schedule()
        return RedirectResponse("/", status_code=303)

    @app.post("/review")
    @app.post("/review/link")
    async def review(request: Request):
        if device.home is None:
            return PlainTextResponse("Review this edit on the home.", status_code=403)
        data = await form(request)
        device.home.review(command_id=data["command"], proposal_id=data["proposal"], token=data["token"],
                           choice="link" if request.url.path.endswith("/link") else data["choice"], existing=data.get("existing") or None)
        device.home.process()
        return RedirectResponse("/", status_code=303)

    @app.post("/again")
    async def again(request: Request):
        data = await form(request)
        original = device.refused(data["proposal"])
        return render(request, editing=original["record"] if original["kind"] != "transaction.add" else None,
                      initial=None if original["kind"].endswith(".delete") else original["groups"],
                      message="Review this edit before saving it again")

    @app.post("/seen")
    async def seen(request: Request):
        data = await form(request)
        device.displayed(data.getlist("proposal"))
        return Response(status_code=204)

    @app.post("/sync")
    async def sync(request: Request):
        await form(request)
        if synchronize is None:
            if device.home:
                device.flush_home()
                return render(request, message="Local edits checked. Paired devices catch up when they connect")
            return render(request, message="Home unavailable · Your pending edits are saved on this device")
        try:
            await synchronize()
        except (OSError, TimeoutError):
            return render(request, message="Home unavailable · Your pending edits are saved on this device")
        return RedirectResponse("/balances", status_code=303)

    @app.post("/capture/csv")
    async def csv(request: Request):
        data = await form(request)
        choices = device.choices()
        try:
            account, category = choices["accounts"][data["account"]], choices["categories"][data["category"]]
        except KeyError:
            raise JournalError("Type and pick an account and category") from None
        upload = data["file"]
        if not hasattr(upload, "read"):
            raise JournalError("Choose a CSV statement")
        try:
            raw = await upload.read(5 * 1024 * 1024 + 1)
        finally:
            await upload.close()
        try:
            capture.csv(raw, account=account, category=category,
                        mapping={name: str(data[name]) for name in ("date", "amount", "counterparty", "notes", "reference") if data.get(name)})
        except (ValueError, KeyError) as error:
            raise JournalError("Check the statement's column names, dates and amounts") from error
        return RedirectResponse("/capture", status_code=303)

    @app.post("/capture/{candidate}/save")
    async def save_candidate(request: Request, candidate: str):
        data = await form(request)
        capture.save(candidate, groups=device.form_groups(data) if data.get("account") else None)
        schedule()
        return RedirectResponse("/", status_code=303)

    @app.get("/capture/{candidate}/edit")
    async def edit_candidate(request: Request, candidate: str):
        return render(request, candidate=candidate)

    @app.post("/capture/batch/{batch}/undo")
    async def undo_batch(request: Request, batch: str):
        await form(request)
        capture.undo_batch(batch)
        schedule()
        return RedirectResponse("/", status_code=303)

    @app.post("/capture/sms")
    async def sms(request: Request):
        data = await form(request)
        choices = device.choices()
        try:
            account, category = choices["accounts"][data["account"]], choices["categories"][data["category"]]
        except KeyError:
            raise JournalError("Type and pick an account and category") from None
        if data.get("allow_sms"):
            if sms_source is None:
                raise JournalError("SMS reading is only available on the phone")
            try:
                sms_source.request()
            except Exception as error:
                raise JournalError("SMS access is unavailable on this device") from error
            return render(request, message="Review the phone's SMS permission prompt")
        if data.get("read_phone"):
            if sms_source is None:
                raise JournalError("SMS reading is only available on the phone")
            capture.read_source(sms_source, account=account, category=category)
        elif capture.sms(str(data.get("text", "")), sender=str(data.get("sender", "")),
                         received=datetime.now(timezone.utc), account=account, category=category) is None:
            raise JournalError("No payment was found in this message")
        return RedirectResponse("/capture", status_code=303)

    @app.post("/exchange")
    async def exchange(request: Request):
        if channel is None:
            return Response(status_code=404)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 64 * 1024:
                return Response(status_code=413)
            chunks.append(chunk)
        try:
            result = channel.handle(b"".join(chunks))
        except (JournalError, LightningError, ValueError, KeyError, TypeError):
            return PlainTextResponse("Local journal request refused.", status_code=403)
        return Response(result, media_type="application/octet-stream")

    return app
