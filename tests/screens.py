"""A small browser for driving Lightning through its screens in tests.

It opens pages, follows links by their visible text, fills in the forms that are on the page (keeping
their hidden fields and defaults) and reads what the page shows, the way a person would.
"""
from __future__ import annotations

import html
import re
import asyncio
import functools
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx


class _ScreenClient:
    """Synchronous screen-test facade over HTTPX's ASGI transport.

    Starlette's TestClient blocks against the Python 3.14 / HTTPX runtime in the project preview; the
    in-process ASGI transport exercises the same routes without opening a socket.
    """

    def __init__(self, app, base_url: str):
        self.app = app
        self.base_url = base_url
        self.cookies = httpx.Cookies()

    async def _request(self, method, url, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=self.base_url,
                                     cookies=self.cookies, follow_redirects=True) as client:
            response = await client.request(method, url, **kwargs)
            self.cookies.update(client.cookies)
            return response

    def get(self, url, **kwargs):
        return asyncio.run(self._request("GET", url, **kwargs))

    def post(self, url, **kwargs):
        return asyncio.run(self._request("POST", url, **kwargs))


def visible_text(markup: str) -> str:
    """What a person reads on the page: no tags, scripts or styles, single spaces."""
    markup = re.sub(r"(?is)<(script|style|template)\b.*?</\1>", " ", markup)
    markup = re.sub(r"(?s)<[^>]+>", " ", markup)
    return " ".join(html.unescape(markup).split())


def error_message(markup: str) -> str:
    """The error the page shows the user, if any."""
    found = re.findall(r'(?s)class="[^"]*\b(?:flash error|field-error|error-text)\b[^"]*"[^>]*>(.*?)</', markup)
    return " | ".join(visible_text(f) for f in found if visible_text(f))


@dataclass
class Link:
    href: str
    text: str
    attrs: dict


@dataclass
class Form:
    action: str
    method: str
    fields: dict = field(default_factory=dict)      # name -> value (last wins, like a browser for one value)
    multi: dict = field(default_factory=dict)       # name -> list of checked values (checkboxes)
    buttons: list = field(default_factory=list)     # (text, name, value)
    options: dict = field(default_factory=dict)     # select name -> [(value, label)]
    boxes: dict = field(default_factory=dict)       # checkbox name -> [values it can send]
    text: str = ""
    attrs: dict = field(default_factory=dict)


class _PageParser(HTMLParser):
    """Links and forms. A control with form="id" belongs to that form wherever it sits, as in a browser."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self.forms: list[Form] = []
        self._by_id: dict[str, Form] = {}
        self._for_later_form: list[tuple[str, str, dict, str]] = []   # (form id, tag, attrs, text) seen before their form
        self._link: list | None = None
        self._form: Form | None = None
        self._button: list | None = None
        self._select: list | None = None      # [owner, name]
        self._textarea: list | None = None    # [owner, name]
        self._option: list | None = None      # [owner, name, value, label parts]

    def _owner(self, a: dict):
        if a.get("form"):
            return self._by_id.get(a["form"]) or a["form"]
        return self._form

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "a" and "href" in a:
            self._link = [a["href"], [], a]
        elif tag == "form":
            self._form = Form(a.get("action", ""), a.get("method", "get").lower(), attrs=a)
            self.forms.append(self._form)
            if a.get("id"):
                self._by_id[a["id"]] = self._form
        elif tag == "input":
            self._control(self._owner(a), "input", a)
        elif tag == "button":
            self._button = [self._owner(a), a, []]
        elif tag == "select" and a.get("name"):
            self._select = [self._owner(a), a["name"], False]
            self._control(self._select[0], "select", a)
        elif tag == "option" and self._select:
            owner, name, chosen = self._select
            value = a.get("value", "")
            if not chosen or "selected" in a:
                self._set(owner, name, value)
                self._select[2] = True
            self._option = [owner, name, value, []]
        elif tag == "textarea" and a.get("name"):
            self._textarea = [self._owner(a), a["name"]]
            self._set(self._textarea[0], a["name"], "")

    def _set(self, owner, name, value):
        if isinstance(owner, Form):
            owner.fields[name] = value
        elif isinstance(owner, str):
            self._for_later_form.append((owner, "set", {"name": name}, value))

    def _control(self, owner, tag, a):
        if owner is None:
            return
        if isinstance(owner, str):
            self._for_later_form.append((owner, tag, a, ""))
            return
        name, kind = a.get("name"), a.get("type", "text").lower()
        if tag == "select":
            owner.fields.setdefault(name, "")
        elif kind in ("submit", "image"):
            owner.buttons.append((a.get("value", ""), name, a.get("value", "")))
        elif kind == "button" or not name:
            return
        elif kind == "checkbox":
            owner.boxes.setdefault(name, []).append(a.get("value", "on"))
            owner.multi.setdefault(name, [])
            if "checked" in a:
                owner.multi[name].append(a.get("value", "on"))
        elif kind == "radio":
            if "checked" in a:
                owner.fields[name] = a.get("value", "on")
            else:
                owner.fields.setdefault(name, "")
        else:
            owner.fields[name] = a.get("value", "")

    def handle_endtag(self, tag):
        if tag == "a" and self._link:
            href, parts, attrs = self._link
            self.links.append(Link(href, " ".join(" ".join(parts).split()), attrs))
            self._link = None
        elif tag == "button" and self._button is not None:
            owner, a, parts = self._button
            if a.get("type", "submit").lower() == "submit":
                # An icon button is named by its tooltip, as the user sees it on hover
                text = " ".join(" ".join(parts).split()) or a.get("title") or a.get("aria-label") or ""
                entry = (text, a.get("name"), a.get("value", ""))
                if isinstance(owner, Form):
                    owner.buttons.append(entry)
                elif isinstance(owner, str):
                    self._for_later_form.append((owner, "button", a, entry[0]))
            self._button = None
        elif tag in ("option", "select") and self._option is not None:
            self._end_option()
            if tag == "select":
                self._select = None
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None
        elif tag == "form":
            self._form = None

    def _end_option(self):
        owner, name, value, parts = self._option
        label = " ".join(" ".join(parts).split())
        if isinstance(owner, Form):
            owner.options.setdefault(name, []).append((value, label))
        elif isinstance(owner, str):
            self._for_later_form.append((owner, "option", {"name": name, "value": value}, label))
        self._option = None

    def handle_data(self, data):
        if self._option is not None:
            self._option[3].append(data)
        if self._link is not None:
            self._link[1].append(data)
        if self._button is not None:
            self._button[2].append(data)
        if self._form is not None:
            self._form.text += data
        if self._textarea and isinstance(self._textarea[0], Form):
            self._textarea[0].fields[self._textarea[1]] += data

    def close(self):
        super().close()
        for form_id, tag, a, text in self._for_later_form:
            owner = self._by_id.get(form_id)
            if owner is None:
                continue
            if tag == "set":
                owner.fields[a["name"]] = text
            elif tag == "option":
                owner.options.setdefault(a["name"], []).append((a["value"], text))
            elif tag == "button":
                owner.buttons.append((text, a.get("name"), a.get("value", "")))
            else:
                self._control(owner, tag, a)


TICK = object()   # tick a checkbox: send what the browser would send for it


class Choose(str):
    """A value picked from a dropdown by the label the user reads, e.g. Choose("CIB Payroll")."""


class Screen:
    """One page as the user sees it."""

    def __init__(self, response):
        self.response = response
        self.url = str(response.url)
        self.path = urlsplit(self.url).path + (f"?{urlsplit(self.url).query}" if urlsplit(self.url).query else "")
        self.html = response.text
        # The day the screen was drawn: an expectation's yyyy-mm-dd reads as the screen says it (A06.1, IV-3BK).
        from lightning.core.dates import today
        self.today = today()
        self.locale = "ar" if '<html lang="ar"' in self.html[:400] else "en"

    def said(self, text: str) -> str:
        """``text`` with its dates as this screen says them: "Due 2026-10-03" -> "Due 3 Oct"."""
        from lightning.ui.date_text import human_text
        return human_text(" ".join(text.split()), self.locale, self.today)

    # Parsed when first read: most pages after a save are never looked at.
    @functools.cached_property
    def text(self) -> str:
        return visible_text(self.html)

    @functools.cached_property
    def _parsed(self) -> _PageParser:
        parser = _PageParser()
        parser.feed(self.html)
        parser.close()
        return parser

    @property
    def links(self) -> list:
        return self._parsed.links

    @property
    def forms(self) -> list:
        return self._parsed.forms

    def shows(self, *texts: str) -> bool:
        return all(" ".join(t.split()) in self.text or self.said(t).casefold() in self.text.casefold() for t in texts)

    def after(self, label: str, length: int = 120) -> str:
        """The text that follows ``label`` on the page: where its figure is."""
        at = self.text.find(label)
        if at < 0:
            label = self.said(label)
            at = self.text.find(label)
        assert at >= 0, f"{label!r} is not on {self.path}"
        return self.text[at + len(label): at + len(label) + length].strip()

    def field_in_row(self, text: str, tag: str = "tr") -> str:
        """The name of the input in the table row (or other block) that shows ``text``."""
        for block in re.findall(rf"(?s)<{tag}\b.*?</{tag}>", self.html):
            if text.casefold() in visible_text(block).casefold():
                names = re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', block)
                names = [n for n in names if n != "__session"]
                if names:
                    return names[0]
        raise AssertionError(f"No row showing {text!r} with a field on {self.path}")

    def action_after(self, text: str, pattern: str) -> str:
        """The action of the first form matching ``pattern`` that comes after ``text`` on the page."""
        spellings = {text, html.escape(text, quote=False), html.escape(text), text.replace("'", "&#39;")}
        at = min((i for i in (self.html.find(t) for t in spellings) if i >= 0), default=-1)
        assert at >= 0, f"{text!r} is not on {self.path}"
        found = re.search(rf'<form\b[^>]*action="([^"]*{pattern}[^"]*)"', self.html[at:])
        assert found, f"No form {pattern!r} after {text!r} on {self.path}"
        return html.unescape(found.group(1))

    def catalogue(self, script_id: str) -> list:
        """The JSON a search box on the page looks things up in."""
        import json
        found = re.search(rf'<script[^>]*id="{script_id}"[^>]*>(.*?)</script>', self.html, re.S)
        assert found, f"No {script_id} on {self.path}"
        return json.loads(html.unescape(found.group(1)))

    def link(self, text: str) -> Link:
        wanted = " ".join(text.split()).casefold()
        if not any(wanted in l.text.casefold() for l in self.links):
            wanted = self.said(text).casefold()
        # An icon link (the gear, a row's delete) is found by its accessible name, as a screen reader would.
        found = [l for l in self.links if l.text.casefold() == wanted] or \
                [l for l in self.links if not l.text and str(l.attrs.get("aria-label", "")).casefold() == wanted] or \
                [l for l in self.links if wanted in l.text.casefold()]
        assert found, f"No link {text!r} on {self.path}. Links: {sorted({l.text for l in self.links if l.text})}"
        return found[0]

    def form(self, button: str | None = None, action: str | None = None) -> Form:
        candidates = [f for f in self.forms if action is None or re.search(action, f.action)]
        if button is None:
            if candidates:
                return candidates[0]
            raise AssertionError(f"No form with action {action!r} on {self.path}")
        exact = [f for f in candidates if any((b[0] or "").casefold() == button.casefold() for b in f.buttons)]
        loose = [f for f in candidates if any(button.casefold() in (b[0] or "").casefold() for b in f.buttons)]
        if exact or loose:
            return (exact or loose)[0]
        raise AssertionError(f"No form with button {button!r} / action {action!r} on {self.path}. Forms: "
                             f"{[(f.action, [b[0] for b in f.buttons]) for f in self.forms]}")


class Browser:
    """Opens pages and keeps the current one, like a tab."""

    def __init__(self, app):
        self.client = _ScreenClient(app, base_url="http://127.0.0.1")
        self.page: Screen | None = None
        self.trail: list[str] = []

    def open(self, path: str) -> Screen:
        response = self.client.get(path)
        assert response.status_code == 200, f"{path} answered {response.status_code}"
        self.page = Screen(response)
        self.trail = [self.page.path]
        return self.page

    def click(self, text: str) -> Screen:
        assert self.page is not None, "Open a page first"
        target = urljoin(self.page.url, self.page.link(text).href)
        response = self.client.get(target)
        assert response.status_code == 200, f"{text!r} on {self.page.path} led to {response.status_code}"
        self.page = Screen(response)
        self.trail.append(self.page.path)
        return self.page

    def go(self, *texts: str, start: str = "/") -> Screen:
        """Find a screen the way a user would: start at the Overview and click through."""
        self.open(start)
        for text in texts:
            self.click(text)
        return self.page

    def submit(self, values: dict | None = None, button: str | None = None, action: str | None = None,
               expect: int = 200, page: Screen | None = None, files: dict | None = None) -> Screen:
        """Fill in the form on the page and press its button."""
        screen = page or self.page
        form = screen.form(button, action)
        if button is None and action is None and values:
            # A profile's language selector is a separate form before its main
            # unlock/borrow form. Choose the form containing the entered fields.
            wanted = set(values)
            matching = [candidate for candidate in screen.forms
                        if wanted <= (set(candidate.fields) | set(candidate.options) |
                                      set(candidate.boxes) | set(candidate.multi))]
            if matching:
                form = matching[0]
        data: dict = dict(form.fields)
        for name, checked in form.multi.items():
            data[name] = list(checked)
        if button:
            pressed = next((b for b in form.buttons if (b[0] or "").casefold() == button.casefold()), None) or \
                next(b for b in form.buttons if button.casefold() in (b[0] or "").casefold())
            if pressed[1]:
                data[pressed[1]] = pressed[2]
        for name, value in (values or {}).items():
            if value is TICK:
                assert name in form.boxes, f"No checkbox {name!r} on {screen.path}"
                value = form.boxes[name][0]
            if isinstance(value, Choose):
                options = form.options.get(name, [])
                picked = [v for v, label in options if label == value] or \
                         [v for v, label in options if label.casefold().startswith(value.casefold())] or \
                         [v for v, label in options if value.casefold() in label.casefold()]
                assert picked, f"{value!r} is not a choice for {name} on {screen.path}: {[l for _, l in options]}"
                value = picked[0]
            data[name] = value
        data = {k: v for k, v in data.items() if v is not None}
        target = urljoin(screen.url, form.action or screen.url)
        if form.method == "post":
            response = self.client.post(target, data=data, files=files) if files else self.client.post(target, data=data)
        else:
            response = self.client.get(target, params=data)
        assert response.status_code == expect, (
            f"{button or form.action} on {screen.path} answered {response.status_code}: "
            f"{error_message(response.text) or visible_text(response.text)[:400]} · typed {values}")
        self.page = Screen(response)
        return self.page


def said(text: str, locale: str = "en") -> str:
    """``text`` with its dates as a screen drawn today says them (A06.1, IV-3BK): "until 2026-11-01" -> "until 1 Nov".
    For a test that looks in a page's HTML rather than through a Screen."""
    from lightning.core.dates import today
    from lightning.ui.date_text import human_dates
    return human_dates(text, locale, today())
