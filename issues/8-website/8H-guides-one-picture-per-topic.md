---
title: Guides as four topics with one big picture each, instead of 16 scattered questions
type: feature
area: website
status: ready
created: 2026-10-21
by: Claude
skills: guideline-audit, website-sync, arabic-check
repo: website
---

## Report

The owner (2026-10-21): the Guides section feels like "30 questions scattered around". A visitor clicks question after
question to understand one big picture. It should be tighter and organized, one page conveying several things, **without
losing search**: pages such as "How to split a 20,000 EGP salary" must stay.

Today (site `main`, 2026-10-21): `guides.html` is a flat list of 16 questions in two groups ("Using Lightning" 11,
"Budgeting basics" 5). Each links to its own page (~17 KB, hero, worked example, three cards, 4–7 FAQ, keep reading),
English and Arabic: 32 pages, **85 FAQ questions**, many repeating across pages (bank login, where data lives, gold).
Two pairs answer the same query: `expense-tracker-egypt.html` ("where did my salary go?") and `blog-track-expenses.html`
("where does my money go each month?"); `budget-app-egypt.html` and `blog-budget-20000-egp.html` overlap on the monthly split.

## Design

Written by Claude, 2026-10-21 (8H1). The owner said "build now", so 8H2 and 8H3 were built from this on branch
`claude/guides-four-topics` of the website repo; the design stands until the owner changes it.

### Topic map

| Topic (EN / AR) | Pillar page (new) | Deep pages under it |
|---|---|---|
| Budget your salary / ميزانية المرتب | `budget-your-salary.html` | budget-app-egypt, blog-budget-20000-egp, blog-salary-runs-out, blog-irregular-income-budget, cash-flow-planner, blog-emergency-fund |
| See where it goes / فلوسك بتروح فين | `see-where-your-money-goes.html` | expense-tracker-egypt (grown: absorbs blog-track-expenses), bank-statement-budgeting |
| Know what you own / إنت تملك إيه | `know-what-you-own.html` | net-worth-tracker, investment-tracker-egypt, dollar-savings-tracker-egypt, track-money-you-hold-for-others |
| Your data and devices / بياناتك وأجهزتك | `your-data-and-devices.html` | offline-personal-finance-app, sync-phone-and-pc-without-cloud |

`net-worth-budget-expense-tracker.html` (the all-in-one answer) belongs to no one topic: it is the "Start here" card at
the top of Guides and is linked from every pillar's closing. Arabic mirrors use the same file names under `ar/`.

### Why new pillar pages (not a grown page)

Every existing page owns a distinct query ("budget app Egypt", "split a 20,000 EGP salary", "net worth tracker"...).
Growing one of them into the hub would dilute its query and make it long. A pillar is a hub with its own
query ("budget your salary in Egypt", "where does my money go", "what do I own", "private finance app"), so it is new.
Each pillar: hero that leads with the answer, **the picture** (one card of how the pieces connect, with Mohab's
figures and the real screen, or three numbered steps when there is no single sum), then one anchored section per deep
page (answer first, one link down), a short FAQ of questions only the whole topic answers (the data pillar has none:
its questions already live on the two deep pages), and "Keep reading" to the other topics.
Figures on a pillar are signposts: each is the same figure and screen as its deep page, and the deep page owns the working.

### Pillar sections and anchors

- **Budget your salary:** picture = Mohab's safe to spend, line by line (each row links to the guide that owns it);
  `#split-20000` (20,000 EGP example), `#plan` (budget-app-egypt), `#runs-out` (salary runs out), `#irregular`,
  `#safe-to-spend`, `#emergency-fund`.
- **See where it goes:** picture = three steps (download, import and match, review); `#month` (September: 28,818 out, 42%
  rent), `#statement` (no bank login), `#start` (where to start with no records).
- **Know what you own:** picture = Mohab's net worth sum beside the Overview; `#net-worth`, `#investments`, `#dollars`,
  `#held-for-others`.
- **Your data and devices:** picture = three steps (the phone holds the ledger, the PC borrows it, nothing in between);
  `#stays-with-you` (offline), `#sync`.

### Fate of every page

| Page | Fate | Why |
|---|---|---|
| guides.html | **grown** into the map | Start here card, four topic cards (answer line + each page with its one-line answer), no bare questions |
| budget-app-egypt | keep | owns "budget app / monthly budget in EGP"; loses two FAQ that live elsewhere |
| blog-budget-20000-egp | keep | owns "split a 20,000 EGP salary"; the brief names it |
| blog-salary-runs-out | keep | owns "why my salary runs out" |
| blog-irregular-income-budget | keep | owns "irregular income budget" |
| cash-flow-planner | keep | owns "safe to spend before payday" |
| blog-emergency-fund | keep | owns "emergency fund in EGP"; takes the budget page's emergency question |
| expense-tracker-egypt | **grown** | survivor for "where does my money go": has the screen, Mohab's month and the head term; takes the three best questions of the merged page |
| blog-track-expenses | **merged** into expense-tracker-egypt | same query ("where does my money go each month"); address kept as a redirect with canonical to the survivor, out of the sitemap |
| bank-statement-budgeting | keep | owns "budget from a bank statement without a login" |
| net-worth-tracker | keep | owns "calculate net worth" |
| investment-tracker-egypt | keep | owns "track gold, certificates and shares" |
| dollar-savings-tracker-egypt | keep | owns "dollar savings and US shares in EGP" |
| track-money-you-hold-for-others | keep | owns "money I hold for someone else" |
| net-worth-budget-expense-tracker | keep | the all-in-one answer; Start here on Guides |
| offline-personal-finance-app | keep | owns "private / offline finance app" |
| sync-phone-and-pc-without-cloud | keep | owns "sync phone and PC without cloud" |

budget-app-egypt and blog-budget-20000-egp were judged **not** duplicates: one answers "which app plans a budget",
the other "what does a 20,000 EGP split look like", and both are in the brief's keep list.

### FAQ: one home per question (85 before)

Removed because another page is the home (the answer is linked, not repeated): budget "save for a goal or emergency
fund" (home: blog-emergency-fund) and "log every purchase" (expense); expense "which banks" (bank-statement);
bank-statement "category for every row" (expense); net-worth "money held for someone else" (hold-for-others);
investment "US shares and dollars" (dollar); dollar "broker or bank login" and "tell me to buy dollars" (investment,
all-in-one); all-in-one "investments in net worth" (investment), "pounds and dollars" (dollar) and "really free" (home
page FAQ); offline "phone app" (sync, "which phone and PC") and, in Arabic, the same; sync "account to sync" (offline);
blog-track-expenses' four questions: "moving money between accounts" (already on expense), the other three moved to
expense-tracker-egypt. Result: 70 questions on the 16 pages, plus 9 pillar questions that only a whole topic answers
(Budget 3, See where 2, Know what 2; Data 0). FAQPage JSON-LD on every page lists exactly the visible questions.

### Structure around the pages

Breadcrumbs (JSON-LD) read Home > Guides > Topic > page on every deep page, Home > Guides > Topic on a pillar. A deep page
shows "Part of <topic>" at the top and, at the end, three cards: its pillar and its two nearest siblings (the blog
articles use their closing link row the same way). Guides' `CollectionPage`/`ItemList`/`BreadcrumbList` list the four
pillars first, then every page. Hero button on every touched page: **Download free** («نزّل ببلاش») to
`current-status.html` (owner, 2026-10-21: plain address, the hero already holds the files).

### Sketch of Guides

Phone (360): hero; **Start here** card (the all-in-one); then four topic cards stacked, each: topic name (Ink, links to
the pillar), one answer line, the pages as rows (title, one-line answer), and "Read the whole topic". PC (1440): same
content, Start here full width, the four topic cards in a 2 x 2 grid.

### Before it is final (owner)

Search Console impressions per page, to confirm the one merge: if `blog-track-expenses` earns impressions of its own,
the redirect can be undone in one commit (the page is archived under its old release ID).

## Constraints

Website README › Search (SEO), Landing pages and Version identity; guideline Part B (`python tools/guideline.py --dir
../Lightning_website/guideline B05` etc.); `guideline/brand-voice.md`; figures only from Mohab's year beside their screen;
never mention other apps; Arabic mirrors every change (`ar/`, hreflang, its own Egyptian search terms); update sitemap,
`llms.txt`, Guides' `CollectionPage`/`ItemList`/`BreadcrumbList`; new release ID. Uses 8E's single download wording.

## Steps

- **8H1** Design: write it in this file (topic map, each pillar's sections, every page's fate: keep, grow, merge), with a
  phone and PC sketch of Guides. Owner approves.
- **8H2** Build Guides and the pillars, English then Arabic.
- **8H3** Links, merges, FAQ de-duplication, structured data, sitemap, `llms.txt`; guideline audit on PC and phone.

## Done when

A visitor sees the whole picture of a topic on one page, every distinct search query still has its page, no two pages
answer the same query, and the site's tests and guideline audit pass.
