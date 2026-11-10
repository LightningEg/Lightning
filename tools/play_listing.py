"""Make the Google Play store graphics from Mohab's sample year (NF-11B7): eight phone slides and a feature graphic per
language, and the 512 px icon, in the website's look (guideline Part B: canvas, Ink headings, the punch line, label
ticks, real screens only). The words live in SLIDES below; the listing text is in docs/google-play.md › Store listing.

    python tools/play_listing.py OUT [--lang en|ar]     # both languages unless --lang

Needs Playwright, Chromium and sqlcipher3 (a real encrypted phone profile, as tools/phone_check.py). The date is pinned
to 2026-10-04 and prices are offline, so figures match the website's screens. Retake after the phone screens change
(IV-11E, IV-11D). Files: OUT/<lang>-<n>-<screen>.png 1080 x 1920 (24-bit PNG, Play's 9:16 phone screenshot),
OUT/<lang>-feature-graphic.png 1024 x 500, OUT/icon-512.png (full square: Play rounds the corners itself).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.update(LIGHTNING_TODAY="2026-10-04", LIGHTNING_PRICES_OFFLINE="1")  # before lightning reads them
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (screen path, label, headline with one <span> punch phrase, one support line). Play's metadata policy: no "free",
# "best" or other promotional words in the graphics; facts only, true in the app as built.
SLIDES = {
    "en": [
        ("/home", "Safe to spend", "Know what you can <span>spend today.</span>", "About 195 a day until payday, after bills."),
        ("/money", "Net worth", "All your money. <span>One clear picture.</span>", "Banks, cash, certificates, gold and shares."),
        ("/budget/flexible", "Budget", "A budget that <span>keeps pace.</span>", "See each day whether the month is on plan."),
        ("/sms", "Bank SMS", "Bank SMS, <span>ready to check.</span>", "Read on your phone. Messages from people are never read."),
        ("/plan", "Cash planning", "Every bill, <span>before payday.</span>", "Loans, subscriptions and bills, with dates."),
        ("/activity", "Activity", "Every pound, <span>in and out.</span>", "By day, with the account and the category."),
        ("/investments", "Investments", "Shares, funds and gold. <span>One portfolio.</span>", "What changed this month, and why."),
        ("/money/accounts", "Private", "No account. <span>Your data stays yours.</span>", "Encrypted on your phone. No ads, no trackers."),
    ],
    "ar": [
        ("/home", "المتاح للصرف", "اعرف تقدر تصرف <span>كام النهارده.</span>", "حوالي ١٩٥ في اليوم لحد القبض، بعد الفواتير."),
        ("/money", "صافي ثروتك", "فلوسك كلها. <span>في صورة واحدة.</span>", "البنوك والكاش والشهادات والدهب والأسهم، بالجنيه."),
        ("/budget/flexible", "الميزانية", "ميزانية <span>ماشية مع الشهر.</span>", "كل يوم تعرف الشهر ماشي على الخطة ولا لأ."),
        ("/sms", "رسائل البنك", "رسائل البنك تبقى <span>حركات تراجعها.</span>", "بتتقري على موبايلك. رسائل الناس عمرها ما بتتقري."),
        ("/plan", "تخطيط النقدية", "كل فاتورة، <span>قبل القبض.</span>", "القروض والاشتراكات والفواتير، بالتاريخ والمبلغ."),
        ("/activity", "النشاط", "كل جنيه، <span>داخل وخارج.</span>", "يوم بيوم، بالحساب والفئة."),
        ("/investments", "الاستثمارات", "كل استثماراتك <span>في محفظة واحدة.</span>", "إيه اللي اتغير الشهر ده، وليه."),
        ("/money/accounts", "خصوصية", "من غير حساب. <span>بياناتك ليك.</span>", "متشفّرة على موبايلك. من غير إعلانات ولا تتبّع."),
    ],
}
FEATURE = {
    "en": ("All Your Money.", "One Clear Picture.", "Budget, spending and net worth for Egypt. On your phone, not a server."),
    "ar": ("فلوسك كلها.", "في صورة واحدة.", "ميزانيتك ومصاريفك وصافي ثروتك، على موبايلك ومش على أي سيرفر."),
}
SMS = ("تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 2093 عند Uber يوم 03/10/26 الساعه 11:13 "
       "المتاح 3512.40EGP للمزيد إتصل ب ١٩٦٢٣")  # one waiting message, so From SMS shows its question
FONTS = ROOT / "lightning" / "ui" / "static" / "fonts"
STYLE = f"""<style>
@font-face{{font-family:"Bricolage Grotesque";src:url({(FONTS / 'BricolageGrotesque-600-800-latin.woff2').as_uri()});font-weight:600 800}}
@font-face{{font-family:Manrope;src:url({(FONTS / 'Manrope-400-800-latin.woff2').as_uri()});font-weight:400 800}}
@font-face{{font-family:"Readex Pro";src:url({(FONTS / 'ReadexPro-400-700-arabic.woff2').as_uri()});font-weight:400 700}}
@font-face{{font-family:"Noto Sans Arabic";src:url({(FONTS / 'NotoSansArabic-400-700-arabic.woff2').as_uri()});font-weight:400 700}}
:root{{--ink:#0D2233;--ink2:#304A5C;--muted:#566E7E;--line:#DDE9E6;
--canvas:linear-gradient(160deg,#E3F6EC 0%,#E6F4F1 50%,#E1EEFB 100%);--punch:linear-gradient(90deg,#00995C 0%,#0B6DD6 100%);
--display:"Bricolage Grotesque","Readex Pro",sans-serif;--body:Manrope,"Noto Sans Arabic",sans-serif}}
[dir=rtl]{{--punch:linear-gradient(270deg,#00995C 0%,#0B6DD6 100%)}}
*{{margin:0;box-sizing:border-box}}body{{background:var(--canvas);color:var(--ink);font-family:var(--body);overflow:hidden}}
.label{{display:inline-flex;align-items:center;gap:20px;color:var(--muted);font:800 34px/1.2 var(--body)}}
.label::before{{content:"";width:46px;height:9px;border-radius:99px;background:var(--punch)}}
h1{{font:800 92px/1.04 var(--display);letter-spacing:-.035em}}[dir=rtl] h1{{letter-spacing:0;line-height:1.3;font-weight:700}}
h1 span{{display:block;width:fit-content;background:var(--punch);-webkit-background-clip:text;background-clip:text;color:transparent;padding-bottom:.06em}}
p.line{{color:var(--ink2);font:600 38px/1.45 var(--body)}}
.phone{{border:1px solid var(--line);background:#fff;padding:16px;border-radius:78px;box-shadow:0 60px 110px -60px rgba(10,36,66,.55)}}
.phone img{{display:block;width:100%;border-radius:62px}}
</style>"""
SLIDE = """<!doctype html><html dir="{dir}"><head><meta charset="utf-8">{style}<style>
body{{width:1080px;height:1920px;padding:110px 84px 0}} .text{{height:600px}} h1{{margin-top:34px}} p.line{{margin-top:30px;max-width:880px}}
.phone{{width:820px;margin:0 auto}}</style></head><body><div class="text"><div class="label">{label}</div><h1>{h}</h1>
<p class="line">{line}</p></div><div class="phone"><img src="{img}"></div></body></html>"""
GRAPHIC = """<!doctype html><html dir="{dir}"><head><meta charset="utf-8">{style}<style>
body{{width:1024px;height:500px;display:flex;align-items:center;gap:20px;padding-inline:64px 0}}
.text{{flex:1}} .mark{{height:58px}} h1{{font-size:56px;margin-top:26px}} [dir=rtl] h1{{font-size:54px}}
p.line{{font-size:21px;margin-top:18px;max-width:470px}} .phones{{position:relative;width:420px;height:500px;flex:none}}
.phone{{position:absolute;width:236px;padding:9px;border-radius:40px}} .phone img{{border-radius:32px}}
.p1{{top:52px;inset-inline-start:12px}} .p2{{top:112px;inset-inline-start:186px}}</style></head><body>
<div class="text"><img class="mark" src="{mark}"><h1>{a}<span>{b}</span></h1><p class="line">{line}</p></div>
<div class="phones"><div class="phone p1"><img src="{one}"></div><div class="phone p2"><img src="{two}"></div></div></body></html>"""


def screen_name(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.strip("/").lower())


def capture(browser, lang: str, out: Path) -> None:
    """Mohab's year on a new encrypted phone profile, 360 x 780 at 3x (1080 px wide), one PNG per slide's screen."""
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
        page = browser.new_page(viewport={"width": 360, "height": 780}, device_scale_factor=3, is_mobile=True, has_touch=True)
        page.goto(host.launch_url)
        page.goto(host.origin + "/profiles/new")
        page.fill("input[name=name]", "Mohab")
        for field in ("password", "confirm"):
            page.fill(f"input[name={field}]", "a dummy phone password")
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
        page.evaluate("""async ([sms, lang]) => { const t = document.querySelector('meta[name=lightning-session]').content;
            const post = (to, data) => fetch(to, {method: 'POST', body: new URLSearchParams({__session: t, ...data})});
            await post('/demo', {}); await post('/sms/paste', {messages: sms});
            if (lang === 'ar') await post('/settings/locale', {locale: 'ar'}); }""", [SMS, lang])
        for path, *_ in SLIDES[lang]:
            page.goto(host.origin + path)
            page.wait_for_timeout(700)
            page.screenshot(path=str(out / f"{screen_name(path)}.png"))
        page.close()


def render(browser, html: str, size: tuple[int, int], target: Path, work: Path) -> None:
    from PIL import Image

    source = work / "page.html"
    source.write_text(html, encoding="utf-8")
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    page.goto(source.as_uri())
    page.wait_for_timeout(600)
    page.screenshot(path=str(target))
    page.close()
    Image.open(target).convert("RGB").save(target)  # Play takes 24-bit PNG without alpha


def main(args: list[str]) -> None:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    langs = [args[args.index("--lang") + 1]] if "--lang" in args else ["en", "ar"]
    chromium = Path("/opt/pw-browsers/chromium")
    with tempfile.TemporaryDirectory() as folder, sync_playwright() as p:
        work = Path(folder)
        browser = p.chromium.launch(executable_path=str(chromium) if chromium.exists() else shutil.which("chromium"))
        for lang in langs:
            shots = work / lang
            shots.mkdir()
            capture(browser, lang, shots)
            direction = "rtl" if lang == "ar" else "ltr"
            for n, (path, label, headline, line) in enumerate(SLIDES[lang], 1):
                img = (shots / f"{screen_name(path)}.png").as_uri()
                html = SLIDE.format(dir=direction, style=STYLE, label=label, h=headline, line=line, img=img)
                render(browser, html, (1080, 1920), out / f"{lang}-{n}-{screen_name(path)}.png", work)
            a, b, line = FEATURE[lang]
            html = GRAPHIC.format(dir=direction, style=STYLE, a=a, b=b, line=line,
                                  mark=(ROOT / "assets" / "logos" / "lightning-lockup.svg").as_uri(),
                                  one=(shots / "home.png").as_uri(), two=(shots / "money.png").as_uri())
            render(browser, html, (1024, 500), out / f"{lang}-feature-graphic.png", work)
        browser.close()
    icon = Image.open(ROOT / "assets" / "logos" / "lightning-app-icon-512.png").convert("RGBA")
    square = Image.new("RGBA", icon.size, icon.getpixel((60, icon.height // 2))[:3] + (255,))
    square.alpha_composite(icon)
    square.convert("RGB").save(out / "icon-512.png")
    print("\n".join(sorted(f.name for f in out.iterdir())))


if __name__ == "__main__":
    main(sys.argv[1:])
