"""Phone presenters: what a phone page adds to a page the PC routes still build (3AY11).

A PC route works out its page and calls ``render``; it does not know the phone exists. When the request is the phone
app's, ``lightning.ui.web.render`` hands the template name and the context to ``present`` here, which

1. runs the page's presenter, if it has one: a function ``(request, c, context) -> dict`` that reads the page's own
   context and the services and returns the extra context the phone template needs, and
2. swaps in the page's phone template (``templates/phone/<name>``) when there is one.

A page moves out of this module when the phone router owns its URL with a screen of its own
(``lightning.ui.phone.screens``); the list in ``tests/test_phone_decoupled.py`` of PC templates the phone still draws
only ever shrinks."""
from __future__ import annotations

from importlib import import_module

PHONE_TEMPLATES = "phone/"

# PC template -> the module here whose ``present`` adds the phone's context. Imported on first use.
PRESENTERS: dict[str, str] = {
    "budget.html": "budget",
    "register.html": "register",
    "dashboard/index.html": "home",
    "search.html": "search",
    "planning/plan.html": "cash_planning",
    "planning/upcoming.html": "upcoming",
    "financial_health.html": "health",
    "transactions/form_popup.html": "capture",
    "investments/index.html": "investments",
}

_templates: set[str] | None = None


def phone_template(name: str) -> str:
    """A page with its own phone screen has it under templates/phone/; every other page keeps its own."""
    global _templates
    if _templates is None:
        from lightning.ui.web import templates
        _templates = {t for t in templates.env.list_templates() if t.startswith(PHONE_TEMPLATES)}
    return name if name.startswith(PHONE_TEMPLATES) or f"{PHONE_TEMPLATES}{name}" not in _templates else f"{PHONE_TEMPLATES}{name}"


def present(request, c, name: str, context: dict) -> tuple[str, dict]:
    """The template and context the phone draws for a page a shared route rendered."""
    module = PRESENTERS.get(name)
    if module is not None:
        context = {**context, **import_module(f"{__name__}.{module}").present(request, c, context)}
        name = context.pop("__template__", name)   # a presenter may draw another of the page's phone templates
    return phone_template(name), context
