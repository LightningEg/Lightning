"""The PC's borrowing screens and Lock: connecting to a phone, opening a borrowed ledger, receiving or moving a
profile's home, and handing a borrowed ledger back (IT-9K). Moved out of `profile_app` unchanged; Lock calls
`hand_back` while a ledger is borrowed, so both live here. A route here sees the session, the devices, the profile
screens' `page` and `action`, staying signed in (`kept`) and `open_profile_id` only through `BorrowScreens`."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse

from lightning.sync.state import ProtocolError

from .devices import move_to_phone, open_move
from .paths import discover_profiles
from .session import AttemptGuard, ProfileError


@dataclass
class BorrowScreens:
    """What the borrowing screens and Lock need from `profile_app`."""
    session: Any
    devices: Any
    page: Callable[..., Any]
    action: Callable[..., Any]
    kept: Any                              # staying signed in on the phone, or None
    open_profile_id: Callable[[], str]


def register(app, screens: BorrowScreens) -> None:
    session, devices, page, action = screens.session, screens.devices, screens.page, screens.action
    kept, open_profile_id = screens.kept, screens.open_profile_id

    @app.post("/profiles/lock")
    async def lock(request: Request):
        if session.borrowed is not None:
            return await hand_back(request)
        if kept is not None and open_profile_id():
            kept.disable(open_profile_id())  # Lock is signing out: the next open asks for the password
        return await action(request, "manage", session.close)

    # ------------------------------------------------------------ multiple devices: the PC's side
    @app.get("/profiles/connect")
    async def connect_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        import socket as _socket
        return page(request, "connect", pc_name=_socket.gethostname()[:60] or "This PC")

    @app.post("/profiles/connect")
    async def connect(request: Request):
        from lightning.sync.identity import normalize_code
        from lightning.sync.service import LinkDown
        from lightning.runtime.paths import borrowed_profile
        from lightning.sync.transport import join_home, pair
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        address, code = str(form.get("address", "")).strip(), str(form.get("code", ""))
        pc_name = " ".join(str(form.get("pc_name", "")).split())[:60]
        values = dict(address=address, pc_name=pc_name)
        try:
            normalize_code(code)
            if not pc_name:
                raise ValueError("Name this PC, so the phone can show it.")
            identity = devices.identity(pc_name)
            paired = await asyncio.to_thread(pair, address, code, identity)
            node = await asyncio.to_thread(join_home, paired, endpoint=address, identity=identity,
                                          borrowed_profile=borrowed_profile, root=devices.root)
        except (ProfileError, ValueError) as exc:
            return page(request, "connect", error=str(exc), status=400, **values)
        except (LinkDown, ProtocolError) as exc:
            return page(request, "connect", error=str(exc), status=400, **values)
        return page(request, "connected", digits=paired.digits, profile_name=paired.reply.profile_name,
                    home_name=paired.reply.home_name, profile_id=node.model.profile_id)

    @app.get("/profiles/borrowed")
    async def borrowed_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        found = devices.find_borrowed(request.query_params.get("id", ""))
        if found is None:
            return RedirectResponse("/profiles", 303)
        return page(request, "borrowed", item=found)

    @app.post("/profiles/borrowed")
    async def open_borrowed(request: Request):
        import json as _json
        from lightning.security.keys import unwrap_key
        from lightning.sync.copies import CopyRejected
        from lightning.sync.service import LinkDown
        from lightning.sync.state import BorrowerState
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        found = devices.find_borrowed(str(form.get("id", "")))
        if found is None:
            return RedirectResponse("/profiles", 303)
        node = found.node
        attempts = AttemptGuard(node.paths.keys_path.with_name("attempts.json"))
        try:
            attempts.check()
            try:
                key = unwrap_key(_json.loads(node.paths.keys_path.read_text(encoding="utf-8")),
                                 str(form.get("password", "")))
            except ValueError as exc:
                attempts.failed()
                raise ProfileError("The password is incorrect. It is the profile's password, the same as on "
                                   "the phone.") from exc
            attempts.succeeded()
            state = node.model.state
            notice = ""
            if state is BorrowerState.SEALED:
                if await asyncio.to_thread(devices.taken_back, node):
                    notice = "The phone took the ledger back. This copy is kept here, read only."
                else:
                    node.reopen()
            elif state is BorrowerState.RETURNING:
                result = await asyncio.to_thread(devices.hand_back_or_seal, node)
                if result in ("accepted", "handed_back"):
                    return page(request, "choose", notice=f"{found.name} is home on {found.home_name}. Open it "
                                                          "again to borrow it.", profiles=discover_profiles(session.root),
                                borrowed=devices.borrowed())
                notice = "The phone has not taken the ledger back yet. This copy is read only until it does."
            elif state is BorrowerState.NEEDS_REPAIR and form.get("start_over") == "yes":
                kept = await asyncio.to_thread(node.start_over)
                link = devices.link(node)
                await asyncio.to_thread(node.fetch, link, key)
                await asyncio.to_thread(node.borrow, link, key)
                notice = (f"You now edit the phone's ledger. This PC's earlier copy is kept as {kept.name}."
                          if kept is not None else "")
            elif state is BorrowerState.NEEDS_REPAIR:
                notice = "The phone took the ledger back. This copy is kept here, read only."
            elif state is not BorrowerState.BORROWING:
                link = devices.link(node)
                if state is not BorrowerState.BORROW_PREPARED:
                    await asyncio.to_thread(node.fetch, link, key)
                await asyncio.to_thread(node.borrow, link, key)
            session.open_borrowed(node, key, name=found.name, writable=node.writable)
            session.borrowed_home = found.home_name
            app.state.container = session.container
            if notice:
                return page(request, "manage", notice=notice)
            return RedirectResponse("/", 303)
        except ProfileError as exc:
            return page(request, "borrowed", item=found, error=str(exc), status=400)
        except LinkDown:
            return page(request, "borrowed", item=found, status=400,
                        error=f"{found.home_name} did not answer. Open Lightning on it, on the same Wi-Fi, and try "
                              "again.")
        except ProtocolError as exc:
            return page(request, "borrowed", item=found, error=str(exc), status=400)
        except CopyRejected as exc:
            return page(request, "borrowed", item=found, error=str(exc), status=400)

    # ------------------------------------------------------------ moving a profile's home to the phone
    @app.get("/profiles/receive")
    async def receive_page(request: Request):
        pending = devices.desk.pending if devices.desk is not None else None
        if pending is not None and pending.receive is None:
            pending = None
        return page(request, "receive", pending=pending, arrived=devices.arrived(),
                    address=devices.address() if devices.server is not None else "",
                    phone_name=devices.identity().name if devices.has_identity() else "My phone")

    @app.post("/profiles/receive")
    async def open_receive(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        name = " ".join(str(form.get("phone_name", "")).split())[:60]
        if not name:
            return page(request, "receive", error="Name this phone, so the PC can show it.", status=400,
                        phone_name="", pending=None, address="")
        try:
            open_move(devices, session.root, name)
        except OSError:
            return page(request, "receive", error="Another app is using the port Lightning listens on. Close it "
                                                  "and try again.", status=400, phone_name=name, pending=None,
                        address="")
        return RedirectResponse("/profiles/receive", 303)

    @app.post("/profiles/move")
    async def move(request: Request):
        from lightning.security.keys import key_id
        from lightning.sync.copies import ensure_profile_id, schema_version
        from lightning.sync.identity import normalize_code
        from lightning.sync.service import LinkDown
        if session.container is None or session.borrowed is not None or not session.role.writable:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        address, code = str(form.get("address", "")).strip(), str(form.get("code", ""))
        pc_name = " ".join(str(form.get("pc_name", "")).split())[:60] or "This PC"
        try:
            normalize_code(code)
        except ValueError as exc:
            return page(request, "manage", error=str(exc), status=400)
        db = session.container.db
        profile_id = ensure_profile_id(db)
        schema, kid, name, paths = schema_version(db), key_id(session.sync_key), session.name, session.paths
        session.close()  # the file is closed before it moves; this request holds the gate, so nothing reopens it
        app.state.container = None
        try:
            moved = await asyncio.to_thread(move_to_phone, devices, paths=paths, profile_id=profile_id, name=name,
                                            key_id=kid, schema=schema, address=address, code=code, pc_name=pc_name)
        except (LinkDown, ProtocolError, ValueError) as exc:
            return page(request, "unlock", selected=str(paths.db_path), status=400,
                        error=f"{exc} {name} stays on this PC; unlock it to try again.")
        return page(request, "choose", profiles=discover_profiles(session.root), borrowed=devices.borrowed(),
                    notice=f"{name} now lives on {moved.done.home_name}. Check that it shows {moved.digits[:3]} "
                           f"{moved.digits[3:]}. Borrow it here under From your phone; the PC's old copy is kept "
                           "as a backup.")

    @app.post("/profiles/hand-back")
    @app.post("/sync/hand-back")  # the finance pages' banner, which carries the session token
    async def hand_back(request: Request):
        node = session.borrowed
        if node is None:
            return RedirectResponse("/profiles", 303)
        name, home_name = session.name, session.borrowed_home or "your phone"
        session.close()  # the working copy closes before it is frozen and sent
        session.borrowed_home = ""
        app.state.container = None
        result = await asyncio.to_thread(devices.hand_back_or_seal, node)
        notices = {
            "accepted": f"{name} is back on {home_name}, with your changes.",
            "received": f"{home_name} has your changes and takes them in when it is unlocked. Until then this PC "
                        "keeps a read-only copy.",
            "sealed": f"{home_name} did not answer. Your changes are saved on this PC; open {name} here to keep "
                      "working, or hand it back when the phone is near.",
            "returning": f"Sending to {home_name} stopped halfway. Open {name} here near the phone to finish.",
            "unpaired": f"{home_name} no longer knows this PC. Your changes are saved here; pair this PC again on "
                        f"the phone (Devices), then open {name} here.",
            "refused": f"{home_name} took the ledger back, so this copy stays on this PC, read only. Open {name} "
                       "here to borrow again; the copy is kept as a backup.",
        }
        return page(request, "choose", notice=notices.get(result, ""), profiles=discover_profiles(session.root),
                    borrowed=devices.borrowed())
