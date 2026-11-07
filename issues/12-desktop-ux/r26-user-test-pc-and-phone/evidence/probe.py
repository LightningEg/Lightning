"""Re-check r26's findings on the sample household, on the PC app and the phone app, in one run.

    python issues/12-desktop-ux/r26-user-test-pc-and-phone/evidence/probe.py   # from the repo root; needs Playwright

Prints one line per finding with what the screens say today. Dummy data only (the built-in sample).
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright  # noqa: E402

from lightning.runtime.app import profile_app  # noqa: E402
from lightning.runtime.devices import Devices  # noqa: E402
from lightning.runtime.http import Host  # noqa: E402

CHROME = "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else shutil.which("chromium")


def flat(page, sel="main"):
    return re.sub(r"\s+", " ", page.inner_text(sel))


def find(text, pattern):
    m = re.search(pattern, text)
    return m.group(0) if m else "(not found)"


def open_profile(page, host):
    page.goto(host.launch_url)
    page.goto(host.origin + "/profiles/new")
    page.fill("input[name=name]", "Mohab")
    for f in ("password", "confirm"):
        page.fill(f"input[name={f}]", "a dummy phone password")
    page.fill("input[name=answer]", "Dummy")
    if page.locator("select[name=question]").count():
        page.select_option("select[name=question]", index=1)
    elif page.locator("input[name=question]").count():
        page.fill("input[name=question]", "Dummy question?")
    page.click("form[action='/profiles/new'] button[type=submit]")
    key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
    if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
        page.fill("input[name=recovery]", key)
    page.click("form[action='/profiles/confirm'] button[type=submit]")
    page.goto(host.origin + "/")
    first_run = flat(page, "body")
    page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
        await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})}); }""")
    return first_run


def run(phone: bool, browser):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=phone)).start()
        size = {"width": 390, "height": 844} if phone else {"width": 1366, "height": 768}
        page = browser.new_page(viewport=size, is_mobile=phone, has_touch=phone)
        first_run = open_profile(page, host)
        go = lambda path: (page.goto(host.origin + path), flat(page))[1]  # noqa: E731
        if phone:
            print("F7 phone first run:", find(first_run, r"Save your currencies first\."))
            print("F1 phone Home:", find(go("/"), r"About [\d,]+ a day[^.]*\."))
            print("F1 phone Budget:", find(go("/budget"), r"About [\d,]+ a day for \d+ days"))
            print("F2 phone Budget:", find(flat(page), r"Health \| ?[\d,]+ of [\d,]+ · [A-Za-z ]+|Health [\d,]+ of [\d,]+ · [A-Za-z ]+"))
        else:
            budget = go("/budget")
            print("F1 PC Budget:", find(budget, r"[\d,]+ for everyday, about [\d,]+ a day"))
            print("F2 PC Budget:", find(budget, r"You are [\d,]+ over your plan.s pace\."), "|",
                  find(budget, r"[−-]?[\d,]+ against \d{4}-\d{2} by day \d+"))
            print("F5 Scenarios:", find(go("/plan/scenarios"), r"Lowest scheduled cash [\d,.]+ EGP"), "|",
                  find(flat(page), r"First shortfall \w+ \w+"))
            plan = go("/plan")
            print("F5 Cash planning:", find(plan, r"Cash you own [\d,]+, less [\d,]+ set aside or due"), "|",
                  find(plan, r"Lowest point ahead (\S+ )?[\d,]{5,}"))
            print("F5 Accounts:", find(go("/accounts"), r"Cash & bank [\d,]+"))
            print("F5 Health:", find(go("/financial-health"), r"of the \d+ figures you set a limit for"))
            inv = go("/investments")
            print("F4 Investments:", find(inv, r"Your holdings grew [\d,]+"), "|",
                  find(inv, r"Money in \+[\d,]+"), "|", find(inv, r"Money Market Fund \+[\d,]+"))
            # F3: the quick-add row's keyboard path after a known counterparty.
            page.goto(host.origin + "/transactions")
            page.click("#counterparty")
            page.keyboard.type("Koshary El Tahrir", delay=20)
            page.wait_for_timeout(400)
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            focus = page.evaluate("document.activeElement.getAttribute('aria-label')")
            account = page.evaluate("document.querySelector('select[name=account_id][form=f-new]').value")
            print(f"F3 PC quick add: focus after Enter = {focus!r}; account filled = {account!r}")
            # F6: the page header's date range in Arabic.
            tok = page.evaluate("document.querySelector('meta[name=lightning-session]').content")
            page.evaluate("""async (t) => { await fetch('/settings/locale', {method: 'POST',
                body: new URLSearchParams({__session: t, csrf: t, locale: 'ar'})}); }""", tok)
            page.goto(host.origin + "/")
            print("F6 Arabic header:", page.evaluate("(document.querySelector('.page-dates b')||{}).outerHTML"))
        page.close()
        host.stop()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    run(False, b)
    run(True, b)
    b.close()
