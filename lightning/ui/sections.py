"""Two levels: a section in the sidebar, then a tab in the bar under the title (owner, 2026-10-06).

At most eight sections (six until 2026-10-28, when the menu was regrouped by question) and five tabs in a section; nothing opens a third page level. A tab's settings sit
behind the gear at the end of its bar. Addresses do not change: a page joins a tab by its path (and, for
Settings pages that belong to another tab, by its ``section``), so old links keep working.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

MAX_SECTIONS = 8
MAX_TABS = 5


@dataclass(frozen=True)
class Tab:
    key: str
    label: str
    href: str
    icon: str                                   # an SVG path, 24 × 24, drawn with a stroke
    paths: tuple[str, ...] = ()                 # path prefixes that belong to the tab ("=/x" means exactly /x)
    settings: tuple[str, ...] = ()              # Settings ?section= values whose page belongs to the tab
    gear: str = ""                              # the tab's settings, opened in the app's dialog
    gear_label: str = ""


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    icon: str                                   # the sidebar icon's name in base.html
    tabs: tuple[Tab, ...] = field(default_factory=tuple)

    @property
    def href(self) -> str:
        return self.tabs[0].href


_I = {  # tab icons
    "summary": "m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zM9 21v-7h6v7",
    "spending": "M5 3h14v18l-3-2-4 2-4-2-3 2zM8 8h8M8 12h8M8 16h5",
    "health": "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21.2l8.8-8.8a5.5 5.5 0 0 0 0-7.8z",
    "budget": "M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 9h18M16 14h3",
    "plan": "M3 3v16a2 2 0 0 0 2 2h16M7 15l4-4 3 3 6-6",
    "recurring": "M17 2l4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3",
    "loans": "M3 21h18M5 21V10l7-5 7 5v11M9 21v-6h6v6",
    "reserves": "M20 13c0 5-3.5 7.5-7.7 9a1 1 0 0 1-.6 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.2 1.2 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z",
    "holdings": "M3 20V4M3 20h18M6 16l5-5 4 3 5-8M16 6h4v4",
    "planner": "M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8",
    "prices": "M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8zM7.5 7.5h.01",
    "accounts": "M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 21h18M12 3l9 5H3z",
    "currencies": "M4 7h14l-3-3M20 17H6l3 3M4 7l3-3M20 17l-3 3",
    "transactions": "M4 6h16M4 12h16M4 18h10",
    "people": "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3 2.5-5 6-5s6 2 6 5M17 5a3 3 0 0 1 0 6M18 15c2 .4 3 2 3 5",
    "data": "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    "categories": "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    "counterparties": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9",
    "checks": "M9 12l2 2 4-4M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z",
    "rules": "M3 4h18l-7 8v6l-4 2v-8z",
    "zakat": "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z",
}

SECTIONS: tuple[Section, ...] = (
    # Question-led (owner, 2026-10-28): each section answers one of the users' main questions, in the order
    # they ask them (docs/reports/2026-10-27-users-main-questions).
    Section("overview", "Overview", "overview", (       # Where do I stand?
        Tab("summary", "Summary", "/", _I["summary"], ("=/", "=/birdview", "/explain", "/birdview/class", "/review", "/activity", "/reimbursements"),
            settings=("valuations", "assets-valuations"), gear="/settings?section=valuations", gear_label="Sale factors"),
    )),
    Section("spending", "Spending", "expenses", (       # Where did my money go?
        Tab("spending", "Spending", "/birdview/expenses", _I["spending"], ("/birdview/expenses",)),
        Tab("compare", "Compare periods", "/spending/compare", _I["plan"], ("/spending/compare", "/analysis")),
        Tab("reports", "Reports", "/reports", _I["data"], ("/reports",)),
    )),
    Section("budget", "Budget", "budget", (             # Am I on plan?
        Tab("budget", "Budget", "/budget", _I["budget"], ("/budget", "/payday"), settings=("budget",),
            gear="/settings?section=budget", gear_label="Budget settings"),
    )),
    Section("plan", "Cash planning", "cash", (          # How much can I spend?
        Tab("plan", "Plan", "/plan", _I["plan"], ("=/plan", "/plan/items")),
        Tab("recurring", "Recurring", "/plan/recurring", _I["recurring"], ("/plan/recurring", "/setup/salary", "/plan/from-transaction")),
        Tab("loans", "Loans", "/plan/loans", _I["loans"], ("/plan/loans", "/plan/purchases")),
    )),
    Section("safety", "Safety", "reserves", (           # Am I safe if something goes wrong?
        Tab("reserves", "Reserves", "/plan/reserves", _I["reserves"], ("/plan/reserves", "/reserves")),
        Tab("health", "Limits", "/financial-health", _I["health"], ("/financial-health",),
            settings=("financial-health",), gear="/settings?section=financial-health", gear_label="Financial health limits"),
    )),
    Section("investments", "Investments", "investments", (   # What do I hold, and how did it do?
        Tab("holdings", "Holdings", "/investments", _I["holdings"],
            ("=/investments", "/investments/holding", "/investments/new", "/investments/report-detail", "/deposits",
             "/investments/assets"), gear="/investments/assets", gear_label="Financial assets"),
        Tab("planner", "Planner", "/investments/planner", _I["planner"], ("/investments/planner", "/investments/targets"),
            settings=("targets",), gear="/settings?section=targets", gear_label="Target allocation"),
        Tab("prices", "Prices", "/investments/prices", _I["prices"], ("/investments/prices", "/investments/reevaluations"),
            gear="/investments/prices/markets", gear_label="Price files"),
        Tab("currencies", "Currencies", "/accounts/currencies", _I["currencies"], ("=/accounts/currencies",)),
    )),
    Section("accounts", "Transactions", "accounts", (   # What happened?
        Tab("transactions", "Transactions", "/transactions", _I["transactions"], ("/transactions", "/t/")),
        Tab("import", "Import", "/import", _I["data"], ("/import", "/sms")),
        Tab("accounts", "Accounts", "/accounts", _I["accounts"], ("/accounts",)),
        Tab("others", "Held for others", "/money-from-others", _I["people"], ("/money-from-others",)),
        Tab("zakat", "Zakat", "/zakat", _I["zakat"], ("/zakat",), settings=("zakat",),
            gear="/settings?section=zakat", gear_label="Zakat settings"),
    )),
    Section("settings", "Settings", "settings", (       # Is my data right?
        Tab("checks", "Data checks", "/checks", _I["checks"], ("/checks",)),
        Tab("rules", "Rules", "/rules", _I["rules"], ("/rules",)),
        Tab("categories", "Categories", "/categories", _I["categories"], ("/categories",)),
        Tab("counterparties", "Counterparties", "/counterparties", _I["counterparties"], ("/counterparties",)),
        Tab("data", "Your data", "/settings", _I["data"], ("/settings", "/profiles", "/exports/all"), settings=("general",)),
    )),
)


def _matches(prefix: str, path: str) -> bool:
    if prefix.startswith("="):
        return path == prefix[1:]
    return path == prefix or path.startswith(prefix.rstrip("/") + "/") or (prefix.endswith("/") and path.startswith(prefix))


def locate(path: str, settings_section: str = "") -> tuple[Section | None, Tab | None]:
    """The section and tab a page belongs to. A Settings page with ``?section=`` belongs to the tab whose
    settings it holds (Budget settings open under Budget); the longest matching path wins otherwise."""
    if path == "/settings" and settings_section:
        for section in SECTIONS:
            for tab in section.tabs:
                if settings_section in tab.settings:
                    return section, tab
    best: tuple[int, Section | None, Tab | None] = (-1, None, None)
    for section in SECTIONS:
        for tab in section.tabs:
            for prefix in tab.paths:
                if _matches(prefix, path) and len(prefix) > best[0]:
                    best = (len(prefix), section, tab)
    return best[1], best[2]


def for_request(request) -> dict:
    """What base.html needs: every section, the current one and its tab (the bar shows only with two tabs
    or more, or with a gear)."""
    path = request.url.path
    if path.startswith('/plan/items/') and path.endswith('/early-payment'):
        path = '/plan/loans'
    section, tab = locate(path, str(request.query_params.get("section", "") or ""))
    hidden = hidden_tabs(request)
    if not hidden:
        return {"sections": SECTIONS, "section": section, "tab": tab}
    def keep(s: Section) -> Section:
        return replace(s, tabs=tuple(t for t in s.tabs if t.key not in hidden))
    return {"sections": tuple(keep(s) for s in SECTIONS), "section": keep(section) if section else None, "tab": tab}


def hidden_tabs(request) -> set[str]:
    """Tabs the user has switched off: Zakat until it is turned on in Settings."""
    current = getattr(request.app.state, "container", None)
    return set() if current is None or current.zakat.enabled() else {"zakat"}
