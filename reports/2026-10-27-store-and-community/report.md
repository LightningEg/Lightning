# Store and community: unlocking themes, the market, rewards and staying in Lightning

Date: 2026-10-27 · Author/reviewer: Claude (owner-requested audit)
Repository: both · Reviewed commits: app `4c997908eada2944118d5ab6c6369f105444f832`, website `c41d2c78438f33496d13ea0cb2c9b741aa76fb7d`

## Scope and method

The owner's goal (2026-10-27): **people stay in the Lightning ecosystem.** Coders are advertised on the leaderboard and
paid in coins; users post on LinkedIn and Reddit about how they use Lightning, are linked from the blog and rewarded;
the market sells looks that follow people from the website to the PC and the phone.

Checked: the paid-theme unlock path end to end (app code, `redeem-purchase`, `profile_seats` SQL, the live store's
functions and catalogue, read-only); the Marketplace, Collection, cart and owner console in Chromium at 1280 and 390
wide with a stubbed signed-in member and owner (the browser cannot reach Supabase from the review container); the merge
reward workflow (`.github/workflows/rewards.yml`), stories, leaderboard and profile privacy SQL. Live counts were read,
never written.

## What a buyer must do today (before this change)

1. Make a website account. 2. Top up coins with InstaPay and wait for the owner to credit them. 3. Buy the theme.
4. On Marketplace or Collection press *Get app unlock code* (works for ten minutes). 5. In the app, Settings ›
Appearance › *Unlock a theme you bought*: pick the theme again from a list, paste the code, be online.
6. **Repeat 4–5 on every other PC or phone of the same profile.** The app also says "buy it on lightningeg.com" but
cannot open that page: both native shells silently block any outside link.

## Findings

| ID | Severity | Observation and expected behaviour | Follow-up |
| --- | --- | --- | --- |
| F1 | high | Each device of a profile needs its own code (the licence lives only in that computer's `cosmetics/licenses.json`). Settings already sync to all of a profile's devices, so the signed licence belongs there: unlock once per profile. | 8L |
| F2 | medium | The unlock form asks which theme the code is for, though the code was made for one theme. Picking wrong burns nothing but fails. The store should read the theme from the code. | 8L |
| F3 | high | No way from the app to the price: "lightningeg.com" is plain text and outside links are blocked in WebView2 and Android. | 8L |
| F4 | info | One purchase, one profile is built and live: a code claims the theme's seat for one profile and burns; another profile is a seat at 25% of the price (75% off), up to ten. Enforcement happens at the one online moment (redeem); after that the signed licence names the profile and is checked offline. Signatures stop forging, not copying: someone who copies a whole profile copies its ledger too, which is the "same profile" by design. | none |
| F5 | low | The live database has the 2026-10-26 Dendera and 2026-10-27 migrations' objects but its migration history stops at `optional_topup_maximum`: they were run in the SQL editor. Harmless; record future runs through the CLI or MCP so history stays true. | owner |
| M1 | high | **No cart button you can always reach.** The only way in is a *Cart 3* chip inside the wallet card at the top; it scrolls away. | 8M |
| M2 | medium | Five buttons per card (Buy, Add to cart, Gift, Try it, Details) wrap into two rows; the owned card adds two more. | 8M |
| M3 | medium | The same themes appear twice: the theme grid, then *Try these on your PC and phone* (one figure, one home: A16). The *How to use Dendera* block says app unlocking "is not available in 1.5.0 yet" and is the longest text on the page. | 8M |
| M4 | medium | Phone: the hero, *Your look*, the wallet card and the four promises fill the first 1,000 px; the first item for sale is below two screens (lead first). | 8M |
| M5 | low | Cart window labels are lowercase (*your cart*, *buy everything*, *remove*): Part B is sentence case. Lines show no picture or kind. *Empty cart* sits next to the main button. | 8M |
| M6 | low | Free Mono offers *Buy* and *Add to cart*; the server refuses both. | 8M |
| B1 | medium | Sets exist (Dusk, Nile, Cotton at 20% off) but nothing tells a buyer whose cart already holds most of a set that the set is cheaper. No starter bundle (a theme with its matching banner and frame). | 8N |
| H1 | medium | The main site never mentions looks. The sign-up pop-up lists three benefits, none about themes; the home page has no way to the market. | 8O |
| P1 | high | New profiles start private and off the leaderboard; showing up needs two switches and an "I am 18 or older" statement. Live: 4 members, 1 public. The owner wants public by default, leaving the leaderboard as an opt-out, and no age requirement. | 8P |
| C1 | high | **No coder has ever been paid**: 0 reward offers have been published. A merge only counts when it closes an issue the owner priced by hand in the console; any other merged pull request earns nothing, not even leaderboard points. | 8Q |
| C2 | medium | The leaderboard shows a name and a score; it does not say what someone built or link to their GitHub or portfolio, so it does not advertise anyone. | 8Q |
| S1 | high | **No story has ever been submitted.** Sharing needs a public adult profile, a draft, a verify code placed in the post, a link back, rules acceptance and owner review, and published stories are not shown anywhere a visitor of the guides would see them. | 8R |
| O1 | medium | Owner console: Catalogue › App themes shows unlock on/off only; seats claimed, extra profiles sold and codes issued are not shown, and freeing a seat lives in Members. Sales counts seats as a channel but Overview's *What sells* does not. | 8S |
| O2 | low | Owner console layout is sound (one menu, badges, *Ready to sell*); *Ready to sell* sits alone in its row under Overview (pair it or fold it once all six are ticked). | 8S |

## Plan

Built in this order, each a branch and pull request per repository rules:

1. **8L unlock once** (in progress 2026-10-27): licence kept in the profile's synced settings; the code names its theme
   (`redeem-purchase` takes the app's list of themes, migration `20261027140000_code_names_its_theme.sql`); a narrow,
   tested exception lets the app open `lightningeg.com/marketplace.html` in the system browser; Settings shows three
   short steps and *See prices*.
2. **8M market and cart**, **8N bundles**, **8O hints on the main site**: one website pass.
3. **8P public by default**, **8Q coders paid and shown**, **8R stories that bring people in**: one website pass plus the
   app repository's reward workflow.
4. **8S owner console**: seats and advocacy in the console once 2 and 3 exist.

## Validation and limits

Server: `supabase/tests/seats.test.mjs` 11 passed on PGlite with the new migration. Browser: stubbed data only; no real
payment, sign-in or app unlock was performed. Native shells were not run here.

## Dated follow-ups

2026-10-27, built and merged the same day. App: LightningEg/Lightning#156 (8L unlock once per profile, See prices), #157 and #158 (8Q workflows). Website: LightningEg/Lightning_website#107 (owner console MFA one step), #108 (8L code names its theme), #109 (8P), #110 (8M, 8O), #111 (8N), #112 and #113 (8Q), #114 (8R). Each needs its migration run by the owner (see 8L and the website's supabase/README.md). Left: 8S, and Papyrus and Dendera sets (in 8S).

2026-10-27, later: 8S built and merged (LightningEg/Lightning_website#115, migration `20261027210000_owner_console_seats_and_community.sql` run by the owner and checked live): app unlocks per theme and Free a profile in Catalogue, extra profiles in What sells, a folded Ready to sell line, a Community view (story review, merges held for linking, reward settings) and a once-only blog bonus. What remains is 8T (Papyrus and Dendera sets).
