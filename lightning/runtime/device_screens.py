"""The phone's device screens: Devices, pairing a PC, keeping this copy as the ledger, revoking a PC and taking the
ledger back (IT-9K). Moved out of `profile_app` unchanged. A route here sees the session, the devices, the gate and
the profile screens' `page` only through `DeviceScreens`; the routes that reopen the ledger set
`app.state.container` on the `app` they are registered on."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse

from lightning.sync.state import ProtocolError

from .devices import home_state_line


@dataclass
class DeviceScreens:
    """What the device screens need from `profile_app`."""
    session: Any
    devices: Any
    gate: Any
    page: Callable[..., Any]


def register(app, screens: DeviceScreens) -> None:
    session, devices, gate, page = screens.session, screens.devices, screens.gate, screens.page

    # ------------------------------------------------------------ multiple devices: the phone's side
    def device_page(request, **context):
        if session.journal is not None:
            return RedirectResponse("/journal/devices", 303)
        if gate.phone and session.container is not None and session.borrowed is None:
            return phone_device_page(request, **context)
        return pc_device_page(request, **context)

    def phone_device_page(request, *, status=200, error="", notice="", **context):
        """Inside the phone frame (review, 2026-10-06): the same figures as below, the phone's own layout."""
        from lightning.ui import web
        response = pc_device_page(request, status=status, error=error, notice=notice, **context)
        keys = ("csrf", "error", "notice", "state_line", "lending", "pending", "peers", "lent_to", "address",
                "phone_name")
        return web.render(request, "phone/devices.html", status,
                          **{key: response.context.get(key) for key in keys})

    def pc_device_page(request, **context):
        lending = devices.lending_state(session.paths) if session.paths is not None else "none"
        if lending in ("missing", "damaged"):
            return page(request, "devices", node=None, peers=[], lent_to="", pending=None, address="",
                        state_line=home_state_line(None, lending), lending=lending,
                        phone_name=devices.identity().name if devices.has_identity() else "", **context)
        node = devices.home_node(session.paths) if session.paths is not None else None
        pending = devices.desk.pending if devices.desk is not None else None
        if pending is not None and (node is None or pending.node is not node):
            pending = None
        peers = node.store.peers() if node is not None else []
        home = node.model if node is not None else None
        lent_to = home.active.grant.borrower_id if home is not None and home.active is not None else ""
        return page(request, "devices", node=node, peers=peers, lent_to=lent_to, pending=pending,
                    address=devices.address() if devices.server is not None else "",
                    state_line=home_state_line(node), lending=lending, phone_name=devices.identity().name
                    if devices.has_identity() else "", **context)

    def home_only():
        if session.journal is not None:
            return RedirectResponse("/journal/devices", 303)
        if session.container is None:
            return RedirectResponse("/profiles", 303)
        if devices.lending_state(session.paths) in ("missing", "damaged"):
            return RedirectResponse("/profiles/devices", 303)
        if session.borrowed is not None:
            return RedirectResponse("/profiles", 303)
        return None

    @app.get("/profiles/devices")
    async def devices_page(request: Request):
        if session.container is not None and session.borrowed is None:
            return device_page(request)  # also where a missing or damaged lending record is repaired
        return home_only() or device_page(request)

    @app.post("/profiles/devices/pair")
    async def open_pairing(request: Request):
        if (refused := home_only()) is not None:
            return refused
        form = await request.form()
        name = " ".join(str(form.get("phone_name", "")).split())[:60]
        if not name:
            return device_page(request, error="Name this phone, so the PC can show it.", status=400)
        try:
            node = devices.home_node(session.paths) or devices.enable_home(session, name)
            devices.identity(name)
            devices.ensure_listener()
        except OSError:
            return device_page(request, error="Another app is using the port Lightning listens on. Close it and "
                                              "try again.", status=400)
        except (ProtocolError, ValueError) as exc:
            return device_page(request, error=str(exc), status=400)
        devices.desk.open(node, home_name=name, profile_name=session.name)
        return RedirectResponse("/profiles/devices", 303)

    @app.post("/profiles/devices/keep-home")
    async def keep_home(request: Request):
        if session.container is None or session.borrowed is not None:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        if form.get("confirm") != "yes":
            return device_page(request, error="Tick the box to confirm that a PC's copy from before will not "
                                              "come back.", status=400)
        try:
            devices.keep_as_home(session, devices.identity().name if devices.has_identity() else "My phone")
            session.set_mode("home")
            app.state.container = session.container
        except (ProtocolError, OSError, ValueError) as exc:
            return device_page(request, error=str(exc), status=400)
        return device_page(request, notice="This copy is the ledger again and opens for editing. Pair your PC "
                                           "again; its copy from before stays on it, read only.")

    @app.post("/profiles/devices/stop-pairing")
    async def stop_pairing(request: Request):
        if devices.desk is not None:
            devices.desk.close()
        return RedirectResponse("/profiles/devices", 303)

    @app.post("/profiles/devices/revoke")
    async def revoke(request: Request):
        if (refused := home_only()) is not None:
            return refused
        form = await request.form()
        node = devices.home_node(session.paths)
        if node is not None:
            try:
                node.revoke(str(form.get("device", "")))
            except ProtocolError as exc:
                return device_page(request, error=str(exc), status=400)
        return RedirectResponse("/profiles/devices", 303)

    @app.post("/profiles/devices/take-back")
    async def take_back(request: Request):
        if (refused := home_only()) is not None:
            return refused
        form = await request.form()
        node = devices.home_node(session.paths)
        if node is None:
            return RedirectResponse("/profiles/devices", 303)
        if form.get("confirm") != "yes":
            return device_page(request, error="Tick the box to confirm that the PC's edits since it borrowed "
                                              "the ledger will not come back.", status=400)
        try:
            node.take_back(reopen=False)  # this request holds the gate: reopen here, not through it
            session.set_mode("home")
            app.state.container = session.container
        except ProtocolError as exc:
            return device_page(request, error=str(exc), status=400)
        return device_page(request, notice="The ledger is back on this phone. That PC's copy can no longer be "
                                           "handed back; it stays on the PC, read only.")
