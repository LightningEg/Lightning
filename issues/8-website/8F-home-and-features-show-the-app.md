---
title: Home and Features show the app, not only words
type: polish
area: website
status: ready
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

Do it after the site recapture (`claude/site-recapture`), which changes the home figures. Check A16/B rules before each change; figures stay those of the screens beside them.

## Done when

The first screen shows the app on PC and phone, the home page offers a download within one screen after every major
section group, and Features shows a screen per highlight. Guideline audit passes; new release ID.
