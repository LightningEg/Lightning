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

## Design (to write first, then show the owner)

Starting point, not a decision; the designer may change it with reasons:

| Topic | Pages it gathers |
|---|---|
| Budget your salary | budget-app-egypt, blog-budget-20000-egp, blog-salary-runs-out, blog-irregular-income-budget, cash-flow-planner, blog-emergency-fund |
| See where it goes | expense-tracker-egypt, blog-track-expenses, bank-statement-budgeting |
| Know what you own | net-worth-tracker, investment-tracker-egypt, dollar-savings-tracker-egypt, track-money-you-hold-for-others, net-worth-budget-expense-tracker |
| Your data and devices | offline-personal-finance-app, sync-phone-and-pc-without-cloud |

1. **Guides becomes the map.** Four topic sections, each leading with its answer (B: lead first) and one picture of
   how the pieces connect (e.g. salary → bills → budget → safe to spend → emergency fund, with Mohab's figures), then its
   pages as short answer cards, not bare questions. Guideline A16: four names then Other; header, then list.
2. **Each topic gets one pillar page** that tells the whole story in sections with anchors (`#split-20000`), and links
   down to the deep pages. Decide per topic whether the pillar is a new page or an existing one grown (the all-in-one
   page already is one for "Know what you own").
3. **Keep every URL that owns a distinct search query** (20,000 EGP split, emergency fund, irregular income, salary runs
   out, dollar savings, sync without cloud...). Each page links up to its pillar and across to its two nearest siblings.
4. **Merge only true duplicates.** A merged page keeps its address as a redirect with canonical to the survivor (the
   `blog.html` pattern; GitHub Pages cannot send 301s), leaves the sitemap, and its best questions move to the survivor.
5. **One home per FAQ question** (A16 "one figure on two pages"): count the 85, keep each answer on the page it belongs
   to, link to it elsewhere. FAQPage JSON-LD lists only the visible questions of that page.
6. Breadcrumbs become Home > Guides > Topic > page.

Before deleting or merging any page, ask the owner for Search Console's per-page impressions (owner action); never
merge a page that earns impressions without saying so in the design.

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
