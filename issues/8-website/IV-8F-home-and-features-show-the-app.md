---
title: Home and Features show the app, not only words
type: polish
pillar: reach
size: M
model: sonnet
status: ready
post: no
created: 2026-10-21
by: Claude
skills: guideline-audit, site-recapture
repo: website
---

## Report

From the owner's website audit (2026-10-21). Scores: visual 7, clarity 6, download path 5, features shown 6. The proof (real
figures from Mohab's year) is strong; the breadth is described, not shown.

- **Hero is three generic lines and no screen** (`index.html:96–113`, Arabic mirror says «الشامل»). One sentence (audit's
  draft: "Every pound you own, owe and plan, in one app."), then the real Overview shot
  (`assets/app/mohab-year-2026-10-15/overview.webp`) under the buttons, cut at the fold, phone shot overlapping. Arabic
  hero gets the same line and its four proof pills back.
- **"Seven places" cards float at random sizes** with an empty left half: a grid of seven equal tiles flowing into the
  390,895 total.
- **One download button after the hero in ~9,850 px.** Add a download band after "Every Number Shows Its Working"; fold
  "Help shape this page" and "Contact Us" (thin H2s) into the footer.
- **Features:** headline "What It Does. Today." undersells; the page's own "101 features in twelve groups" says it. Give
  each of the five highlight cards a 16:10 thumbnail of its real screen (zoom images exist). On phones (14,600 px) show
  each group's title and three lines with a "Show all" toggle.

- **Home FAQ repeats three guide questions** (bank login, SMS, dollars) that now live on the Guides pages (8H): keep
  a one-line answer and link to the guide, or drop them.

Do it after the site recapture (`claude/site-recapture`, NOW.md *Next* item 7), which changes the home figures and
the screenshot folder. Check A16/B rules before each change; figures stay those of the screens beside them.

2026-11-08: this checkout has no Lightning_website repo, so the line numbers above (`index.html:96–113`) and the
asset folder are the audit's (2026-10-21) and are not re-verified here; each step says what to check first. The FAQ
point is settled for the step: keep one line and a link to the guide (it keeps the question searchable on Home).

## Fix

The first screen shows the app on PC and phone, the home page offers a download within one screen after every major
section group, and Features shows a screen per highlight. Guideline audit passes; new release ID.

## How to work on this item

All work is in the Lightning_website repo (clone it beside this one as `../Lightning_website`). Each step is one pull
request there. Before editing, run that repo's `python tools/release.py <spec.json>` for the pages the step changes
(README › Version identity and archive). Read guideline sections only with `python tools/guideline.py --dir
../Lightning_website/guideline B05` (B05 layout, B06 blocks, B07 screens, B12 before it ships). Done when for every
step includes `python tools/site_check.py` passing in the site and the changed section seen at 1280 and 390 px with no
sideways scroll. English and Arabic (`ar/`) change together. Delete the step's heading here in a commit to this repo.

## 8F1 Hero: one sentence and the real Overview · S · sonnet
Verify first: the site recapture (NOW.md *Next* item 7, skill `site-recapture`) is merged in the Lightning_website
repo; take the screenshot folder it made (`grep -oh 'assets/app/mohab-year-[0-9-]*/overview.webp' index.html`), not
`mohab-year-2026-10-15`.
Files (in the Lightning_website repo): `index.html` (the hero, `grep -n 'class="hero' index.html`), `ar/index.html`
(same block), the hero rules in the site's stylesheet (`grep -rn '\.hero' assets/*.css`).
Do: the hero is B05's Label · H1 · line · buttons · product: H1 "Every pound you own, owe and plan, in one app."; drop
the three generic lines; under the buttons the Overview screenshot inside the browser frame B07 names
("Lightning · Overview"), cropped at the fold, with the phone Overview screenshot overlapping its lower right on
widths ≥ 900px and below it in one column on phones (a plain screenshot, no device mockup, B07). Arabic: the same
sentence in the Egyptian voice (skill `arabic-check`; drop «الشامل») and its four proof pills back.
Done when: `grep -c 'overview.webp' index.html ar/index.html` is ≥ 1 each, `python tools/site_check.py` passes, and
screenshots at 1280 and 390 px show the screen above the fold.

## 8F2 "Seven places" as seven equal tiles · S · sonnet
Files (in the Lightning_website repo): `index.html` and `ar/index.html` (the "Seven places" section,
`grep -n -i 'seven places' index.html`), the section's CSS.
Verify first: the total under the tiles is the figure the recaptured screens show (it was 390,895).
Do: a grid of seven equal money tiles (B06 "Money tiles", A08 KPI card look), 4 + 3 on PC and 2 per row on phones,
with the total as one Lead card (B06 "Result card") under them; remove the random sizes and the empty left half.
Done when: `python tools/site_check.py` passes and the 1280/390 px screenshots show equal tiles and the total.

## 8F3 A download band after "Every Number Shows Its Working" · S · sonnet
Files (in the Lightning_website repo): `index.html`, `ar/index.html` (after the section titled "Every Number Shows
Its Working"; the "Help shape this page" and "Contact Us" sections; the footer).
Do: after that section, a band with the B06 "Download" and "Get early access" buttons; move "Help shape this page"
and "Contact Us" into the footer as links (their H2 sections go). The signup band still ends the page (B01).
Done when: from any section heading of `index.html` the next download button is within one screen (check at 1280 and
390 px), and `python tools/site_check.py` passes.

## 8F4 Features: the headline and a screen per highlight · S · sonnet
Verify first: the recaptured folder holds a screen for each of the five highlights (`ls assets/app/mohab-year-*/`);
the zoom images the audit names are `data-zoom` targets in `features.html`.
Files (in the Lightning_website repo): `features.html`, `ar/features.html`.
Do: the H1 says the page's own count ("101 features in twelve groups"; read the current count from the page, do not
type a new one) instead of "What It Does. Today."; each of the five highlight cards gets a 16:10 thumbnail of its
real screen from the recaptured folder, with the same `data-zoom` the page already uses.
Done when: five `<img` with the new folder inside the highlight cards (`grep -c`), `python tools/site_check.py` passes.

## 8F5 Features on phones: three lines and "Show all" · S · sonnet
Needs 8F4 merged first.
Files (in the Lightning_website repo): `features.html`, `ar/features.html`, the page's CSS and its small script.
Do: under 700px each group shows its title and its first three features; a "Show all" button (Arabic «اعرض الكل»)
opens the rest (a `<details>` per group, no script if possible). PC shows everything as today.
Done when: at 390 px the page is under half its old height (it was ~14,600 px), every feature is still in the HTML,
and `python tools/site_check.py` passes.

## 8F6 Home FAQ: one line and a link to the guide · S · sonnet
Files (in the Lightning_website repo): `index.html`, `ar/index.html` (the FAQ; the bank login, SMS and dollars
questions), `guides.html` (the guide pages' names).
Do: each of the three answers becomes one sentence plus a link to its guide page; the FAQ's JSON-LD (if the page has
one) carries the same shorter answer.
Done when: `python tools/site_check.py` passes (it parses JSON-LD and checks links) and the three links resolve.
