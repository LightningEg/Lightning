"""3AY4a: the phone's own layer. Its router answers before the shared routes, it renders only templates/phone/,
and it never imports the PC's routes."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone, phone_router, render_phone
from lightning.ui.web import create_app

PHONE = Path(__file__).resolve().parents[1] / "lightning" / "ui" / "phone"


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-04")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("shell") / "t.db")
        load_mohab_2026(c)
        yield c
        c.db.close()


def test_the_phone_layer_never_imports_the_pc_routes():
    for path in PHONE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n == "lightning.ui.routes" or n.startswith("lightning.ui.routes.") for n in names), path


def test_a_phone_route_wins_over_an_older_shared_route_of_the_same_path(sample):
    app = create_app(sample)
    assert TestClient(app).get("/transactions").status_code == 200   # the shared register answers this path
    probe = APIRouter()

    @probe.get("/transactions")
    async def more(request: Request):
        return render_phone(request, "phone/validation_error.html", message="from the phone router")

    mount_phone(app, probe)
    response = TestClient(app).get("/transactions")
    assert response.status_code == 200 and "from the phone router" in response.text


def test_a_phone_screen_renders_only_phone_templates(sample):
    app = create_app(sample)
    probe = APIRouter()

    @probe.get("/probe-pc")
    async def pc(request: Request):
        return render_phone(request, "dashboard/index.html")
    mount_phone(app, probe)
    with pytest.raises(ValueError, match="only templates/phone/"):
        TestClient(app).get("/probe-pc")


def test_the_empty_router_changes_nothing(sample):
    app = create_app(sample)
    before = list(app.router.routes)
    mount_phone(app, phone_router())
    assert len(app.router.routes) >= len(before) and app.router.routes[-len(before):] == before
