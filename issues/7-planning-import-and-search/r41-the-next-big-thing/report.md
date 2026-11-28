# The next big thing for Lightning: the payday plan that fills itself

Date: 2026-11-27 · Author/reviewer: Claude, at the owner's request ("what is the next big thing for us")
Repository: app · Reviewed commit: e1426e498134b91ca0b4a298350b0d0cc51fa455
Code: r41 · App version: 2.3.3 · Builds on: [r40](../r40-one-money-plan/report.md) (screens and findings)

## The answer

**Make Lightning the app that, every payday, tells a salaried Egyptian where this month's salary goes, fills
itself in from their bank and wallet messages, and shows at month end whether they got richer, in pounds and in
gold.** That is one release with three legs, in this order:

1. **The payday plan** (r40's one money plan): every screen tells the same story. Money with no job gets one. Payday
   opens the month and a review closes it. This is the habit and the moment people will love.
2. **It fills itself**: read payment notifications from InstaPay, wallets and bank apps, read SMS from more banks,
   and let people say a cash spend in Egyptian Arabic. A plan is only as good as the ledger behind it, and money in
   Egypt now moves through InstaPay and wallets as much as through bank SMS.
3. **"Did I get richer?"**: the month-end review shows what changed (saving, prices, new money) in pounds and in
   grams of 21K gold, against inflation. No Egyptian app can say this, because none of them knows your gold,
   certificates, shares and gam'eya. It is the screenshot people will share.

Alongside it, a **growth engine** from the 1 December Play launch, because today almost nobody knows Lightning
exists (below). Household sharing is the next big thing after this one.

## Where Lightning stands

### The product

Deep and correct, not yet one story. r40 found seven different "what is left" figures on one day, and a headline
that reads "You can spend 51,420 today and stay on plan" four days before payday, because money the plan never
assigned piles into Safe to spend. The engines already exist: the payday step, reserves and goals, Refill, the
investing planner, reminders, bank SMS (CIB and NBE in Arabic), net worth in grams of 21K gold, Change in what you own,
and the monthly review (NF-12AL, ready on the board). The next big thing joins them; it builds few new engines.

### The audience

Measured 2026-10-28 to 2026-11-27. These are **page views from visitors who accepted counting**, not people; ad
blockers and declined consent are not counted.

| Signal | Figure | Source |
| --- | --- | --- |
| Website page views | 501 (497 in the three months before) | GoatCounter |
| Arabic page views | 9 | GoatCounter, `/ar/` paths in the top 100 |
| Download events | 11 or more | GoatCounter events in the top 100 paths |
| Where visitors came from | Direct 235, LinkedIn 51, ChatGPT 14, Google 8 | GoatCounter referrers |
| Website member accounts | 4 (1 created in the last 30 days); administrators excluded; test accounts may be among them | Supabase, counts only |

**Lightning is unknown, and the visitors it has are English-reading people from the owner's professional network.**
The Arabic, phone-first, mass market that Say and Masareef reach is not arriving yet. A big hit needs a reason to
talk about Lightning, not only a better app. ChatGPT already sends more visitors than Google: answers in AI search
are worth writing for (Competition › How AI search finds us).

### What users told us

Sanitized feedback (`feedback/`, six records since 2026-10-26) clusters into three themes:

- **Getting their history in:** a 377-row CSV from another tracker, multi-sheet Excel files, spreadsheet dates and
  non-UTF-8 files. People arrive with years of data from another app.
- **Trusting the devices:** pairing still needed typing; a phone update lost its book and the PC could not send it
  back.
- **Money that comes back:** reimbursements recorded in the original category, with pairing suggested.

None asked for more reports. They ask for less typing and more trust.

### The market (Egypt, 2026)

| Fact | Figure | Why it matters |
| --- | --- | --- |
| Android's share of mobile web use | 88-91% (May-Aug 2026) | The phone app is the front door; iPhone can wait |
| Adults with an active transaction account | 79% (56.4 million of 71.4 million), June 2026 | Most salaried people have a bank, wallet or card |
| Mobile wallets | 57 million, +23%; wallet transactions +62% (H1 2026) | Wallet and InstaPay notifications are where spending shows up |
| InstaPay registered users | more than 24 million; about EGP 7 trillion through September 2026 | Transfers and payments leave InstaPay traces, not always bank SMS |
| Urban inflation | 12.7% in October 2026, down from 25.5% in November 2024 | After two years of high inflation, people hold gold, certificates and dollars; "am I keeping up?" is a live question |

Sources are listed at the end. Registered is not active, and wallet counts differ by definition.

### The competition

Details and sources: [Competition › Field check, 2026-11-27](../../../ai/COMPETITION.md#field-check-2026-11-27).

| | Say | Masareef | Qershnat | Pockito | Lightning |
| --- | --- | --- | --- | --- | --- |
| Rating, reviews, downloads | 4.8, 2.75K, 50K+ | 4.7, 32.4K, 1M+ | 4.8, 696, 10K+ | new, 100+ | Play launch 1 Dec |
| Bank SMS | yes | yes | yes | yes | CIB and NBE (Arabic) |
| App and wallet notifications | yes | not listed | not listed | yes | **no** |
| Voice entry | yes, mixed Arabic and English | not listed | voice notes only | yes | **no** |
| Receipt scan | not listed | not listed | attachments | yes | **no** |
| AI questions | "Ask Say AI" | not listed | not listed | AI helper | offline typed questions, no AI |
| Household or partner | **shared budget** | not listed | shared records | not listed | no |
| Safe to spend | not listed | not listed | not listed | **its main pitch** | yes, with its working |
| Gold, certificates, shares, gam'eya, zakat | gold only | not listed | gold, silver, valuables | not listed | **all, with returns** |
| Data lives | cloud account | phone | offline-first | phone first | **your devices, encrypted, no account** |
| Ads or paywall | paid Pro | ads | ads | paid tier | **none; free** |
| PC | no | no | no | no | **Windows app** |

"Not listed" means the store listing does not mention it, not that the app lacks it.

**Capture is table stakes now.** Every Egyptian competitor reads bank SMS; Say and Pockito also read notifications,
and both take voice. **Safe to spend is being copied** (Pockito). What no one has is a plan that adds up across
bills, budget, savings and wealth, privately, with a PC for the deep work. That is Lightning's ground. Lightning has
to match capture so that people stay long enough to see it.

## What makes a money app a hit

From the reviews in Competition and the evidence above, the loved apps have five things:

1. **It fills itself.** Logging is the chore that kills every tracker ("I resorted to my notes" before Say).
2. **One moment people love.** Say's is the instant log; YNAB's is giving every pound a job.
3. **A number they trust.** Reviews punish numbers that drift more than missing features.
4. **Something to show a friend.** A figure or a screen worth a screenshot; Say grew from TikTok.
5. **No catch.** No paywall before trying, no ads in the paid version, no lost data.

Lightning has 3 and 5. The next big thing adds 1, 2 and 4.

## Options weighed

| Option | Pull (evidence) | Unique to Lightning | Fits the rules (local, free, no AI in the figures) | Effort | Verdict |
| --- | --- | --- | --- | --- | --- |
| **A. Payday plan** (one money plan, money gets a job, payday ritual, month review) | High: r40, users' questions ("where should the rest of my income go?") | High: it needs the whole picture | Yes | M: mostly joins what exists | **Now: the core** |
| **B. It fills itself** (notifications, more banks' SMS, voice in Egyptian Arabic) | High: compass rule 1, every loved app, feedback ("less typing") | Low: catch-up | Yes, if read on the phone and reviewed before posting | M to L | **Now: needed for A to last** |
| **C. Did I get richer?** (month review in pounds and gold grams, against inflation) | Medium-high: two years of inflation; gold is how Egyptians save | **Highest**: no competitor can compute it | Yes | S to M: the figures exist | **Now: the shareable leg** |
| D. Household (two phones, one family plan) | Medium: Say's new feature, Qershnat's shared records, Monarch | Medium | Yes, over the existing pairing (NF-4B) | L | **Next** |
| E. AI assistant | Medium: Say, Pockito, Copilot, Monarch | Low | Partly: figures must stay ordinary code; optional and local only | M | Later; extend the offline typed questions (NF-7AQ) first |
| F. iPhone app | Low in Egypt (9-12% of mobile use) | Low | Yes | L | Later |
| G. Import from other apps (Masareef, Say, Wallet, Money Manager files) | Medium: feedback FB1 (377 rows) | Low | Yes | S to M | **Now, small: switching is how users arrive** |
| H. Visual restyle, more asset kinds, Europe and Gulf shares | Low | Low | Yes | M to L | Not now |

## The plan

Each phase ends in something a person notices. Items are filed when work starts (AGENTS.md §3), and the board is
already above its 20 open items, so each phase should replace parked items, not add to them.

| Phase | When | What | Done when |
| --- | --- | --- | --- |
| 0. Launch hygiene | now to mid-December | Merge the r40 clean-up; finish the launch checklist (#579); Play listing and screenshots in Arabic first; after a person's first payday plan, ask once for a review | Play is public; first reviews arrive |
| 1. The payday plan | December to January | r40 M1 to M3: one flow and one name per figure, the "no job yet" nudge (owner, 2026-11-27), payday opens the month on both surfaces | A new user gets their first payday plan in under ten minutes, tested like Mohab |
| 2. It fills itself | January to February | Payment notifications from InstaPay, Vodafone Cash and bank apps (read on the phone, reviewed before posting, like SMS); the three or four next-largest banks' SMS; voice entry for cash ("١٥٠ بنزين"), parsed by ordinary code; import files from the most used other apps | A week of Mohab's spending arrives with fewer than five typed entries |
| 3. Did I get richer? | February to March | The monthly review (NF-12AL, r40 M5) with what changed (saving, prices, new money), in pounds and in grams of 21K gold, against inflation; a share card with no amounts, only directions and percentages | The review answers "did I get richer?" in one sentence, and the card shows no private figure |
| Next | after March | Household: two phones, one family plan, over the existing pairing | Planned when phase 3 ships |

**The growth engine runs through every phase:** Arabic first on Play and the site; a short video per phase (the
payday plan in 30 seconds; "my net worth in gold"); answer the questions people ask AI search (ChatGPT already
sends more visitors than Google); reply to every review; a visible changelog. Say grew from TikTok and an Egyptian
maker who answers. Lightning can do both.

## How we will know it is working

Lightning sends nothing home, so every measure must come from Play, the site or a test, never from inside a profile:

- **Play Console:** installs, 30-day retained installers, uninstalls, rating and review count. Aim for 4.7 or more
  from 100 or more reviews by the end of phase 3.
- **Reviews that name the payday plan or gold:** read by hand each month; that is word of mouth starting.
- **Website:** Arabic page views and download events (GoatCounter), and AI-search referrals.
- **Acceptance tests:** the first payday plan in under ten minutes, a week with fewer than five typed entries,
  the review's sentence, all as steps in Mohab's year.

## Risks

| Risk | Why | Mitigation |
| --- | --- | --- |
| Play policy on SMS and notification access | Both need declared, narrow use | Read on the phone only, for money management, reviewed before posting; keep the declaration current |
| Reading notifications feels invasive | It is a broad permission | Opt-in per app, list what was read, nothing leaves the phone; say so on the permission screen |
| Arabic speech accuracy | Mixed Arabic and English, dialect | Android's on-device recognizer; the amount and category parsed by tested rules; the entry sheet stays editable |
| Scope creep | 25 open items, above the cap | Each phase replaces parked items; one phase at a time |
| Competitors copy Safe to spend | Pockito already has | Win on what they cannot copy fast: the whole picture, gold, privacy, the PC |
| Owner time | Checks are held for milestones | Ask for one phone check per phase, end to end |

## What not to do now

A visual restyle; more asset kinds; Europe and Gulf shares; cloud sync or an account; AI in the figures; an iPhone
app before Android traction.

## Decisions for the owner

1. Adopt **the payday plan that fills itself** as the next milestone, with phases 1 to 3 as above?
2. Reading **payment notifications** (InstaPay, wallets, bank apps) on the phone: yes, opt-in per app?
3. **Voice entry** for cash in Egyptian Arabic, on the device: yes?
4. **A share card** for the month review that shows directions and percentages, never amounts: yes?
5. Which parked items make room (the board is at 25 open, cap 20)?

## Sources

Market: [Statcounter, mobile OS in Egypt](https://gs.statcounter.com/os-market-share/mobile/egypt);
[CBE financial inclusion 79% (Ahram)](https://english.ahram.org.eg/News/574144.aspx);
[mobile wallets +62% in H1 2026 (Zawya)](https://www.zawya.com/en/business/fintech/egypts-mobile-wallet-transactions-rise-62-in-h1-2026-ntra-513794);
[InstaPay through September 2026 (Ahram)](https://english.ahram.org.eg/News/581997.aspx);
[urban inflation 12.7% in October 2026 (Enterprise)](https://enterpriseam.com/egypt/2026/11/10/egypts-urban-inflation-slowed-to-12-7-in-october-despite-non-food-momentum/).
Competitors: Google Play listings rendered 2026-11-27 and the sources in
[Competition › Field check, 2026-11-27](../../../ai/COMPETITION.md#field-check-2026-11-27).
Audience: GoatCounter and Supabase aggregates as defined above (skill `usage-question`).

## Validation and limits

- Market figures come from news reports of official statistics; registered users are not active users.
- Competitor figures are Play listings on one day; ratings drift.
- Website figures are consented page views, not people; there is no sign-up or install funnel to measure conversion.
- No user interviews were run; the feedback records are few. Talking to ten salaried users after the first payday
  plan would test this report better than anything here.

## Dated follow-ups

Append dated decisions and results here; keep the recommendation above as written.

- **2026-11-27, owner decisions (asked in this session):** **adopted** the payday plan that fills itself, all three
  phases in order. Phase 2 **without reading payment notifications for now** (not yet): more banks' SMS, voice entry
  and imports from other apps carry it. **Voice entry yes**, on the device, amount and category read by ordinary
  tested rules. **No share card**: phase 3's review stays inside the app. Still open: which parked items make room on
  the board (decision 5).

- **2026-11-28, owner picks (all the recommended options):** on payday the salary row leads To do (guideline C13,
  #778); the five "someday" items were closed to make room (#431, #573, #574, #576, #577); To do gets two groups with
  the count unchanged (IV-11P); #777 and #778 merged when green; the next work is one name per figure (IT-7BB). The
  Everyday budget relabel waits for the website repo to be attached to a session. Items filed: phase 1 IT-7BB and
  IV-11P (on the board); phase 2 NF-7BC (more banks' SMS), NF-7BD (voice entry, three steps) and NF-7BE (imports from
  other apps), posted to the board when phase 1 closes; phase 3 is the monthly review, NF-12AL (#638).
- **2026-11-28, owner pick (board limit):** phase 1's two items (IT-7BB #779, IV-11P #780) may keep the board above
  AGENTS.md's 20 open items until phase 1 closes; phase 2 items are posted only then.
- **2026-11-28, phase 3 built as NF-7BF (#790):** NF-12AL (#638), named above for phase 3, had delivered Budget's
  "what changed" card. The phone's Report now says whether the period left you richer, the change in grams of 21K
  gold, and why (Kept + Investing result + Other changes); `tests/test_did_i_get_richer.py`. Inflation waits for the
  owner's pick of a source.
- **2026-11-28, owner picks on the month review:** the phone Report leads with Change in net worth, as the PC Overview
  does, so the lead, the verdict and Why it changed are one figure (1A); inflation is left out (2B); #638 closed as
  completed (3A); #775 is brought up to date with main, keeping only what main lacks (4A).
