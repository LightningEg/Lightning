# For the owner

What only the owner can do or decide. Any AI adds an item here, and removes it once it is done or decided; a decision is first recorded where it belongs (usually Project Overview › Product decisions). AIs read this file only when their task is one of its items.

## To do

- **Windows restore acceptance (02d/03a), deferred 2026-10-12:** engineering work is complete; run the [dummy-data P0–P5 drill](tools/windows_restore_reboot_drill.md) on an ordinary Windows PC before accepting restore for real profile data. Keep its `drill.json` as device/filesystem/reboot evidence. Abrupt power-loss behavior remains unverified; the release-risk decision is below.

- **Before the edit-journal mailbox ships:** create its dedicated Cloudflare account, arrange a card that pays in dollars, and update the website privacy note. Building remains for later; [revised proposal](docs/proposals/edit_journal.md).

- **Before the first tagged release (one-time):** turn on release immutability in `Lightning-downloads` › Settings. The `LIGHTNING_DOWNLOADS_TOKEN` secret is configured. Codex handles the `v1.0.0-beta.1` tag after the paired PC and phone checks pass.
- **Price pack:** the `LIGHTNING_MARKET_TOKEN` secret and `MARKET_PUBLISH` variable are configured. The FX collector now uses Banque Misr because CBE rejected requests; publish and verify the first FX pack before tagging, because the Windows ZIP requires it.
- **Review milestones 1 and 2 together, dummy data only:**
  1. Phone: install `lightning-android` from [Android run 37527282826](https://github.com/elfekimuhammed/Lightning/actions/runs/37527282826) (a new app called Lightning). PC: install the ZIP from [Windows run 37519503375](https://github.com/elfekimuhammed/Lightning/actions/runs/37519503375). Same Wi-Fi.
  2. PC: create a dummy profile and add an account. Phone: Bring a profile from your PC, Show a code. PC: Profile settings › Move to your phone, type the address and code. Both show the same six digits. (A profile made on the phone instead: Settings, the gear, › This phone › Pair a PC; on the PC, Connect to your phone.)
  3. Phone: unlock the profile with its password (the same one as on the PC; there is no other password). Look at Overview, Accounts, an account (add a transaction with the + button) and the other sections: does it feel like a phone app?
  4. PC: open it under From your phone and add something; the phone says "Lent to … · read only". Hand back; the phone has it.
  5. Borrow again, turn the phone's Wi-Fi off, Hand back on the PC: the PC keeps your edits; hand back later.
  6. Phone: Accounts › From SMS › Allow reading SMS, then open Overview: your recent bank messages wait under Needs you. Say which account each ending is, then post them on the review. Or share one message from your SMS app to Lightning.
  7. Optional: on the phone, Settings (the gear) › This phone › Pair a PC, then Take the ledger back while the PC holds it; the PC then offers Borrow again and keeps its copy as a backup.
  Known gaps: you type the phone's address; on the phone, a holding's horizon is still changed on the PC; the phone reads bank SMS itself, but only CIB and NBE so far.
- **Phone beta signing key:** the owner has configured `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD` in GitHub Actions. Its public SHA-256 fingerprint is pinned in `packaging/android-test-certificate.sha256`; keep the keystore and passwords safe, and never share them in chat. Each subsequent Lightning Test APK must use the same key to install over the last one. At each milestone: Actions › *PC and phone app* › *Run workflow* on `main`; download `…-PC` on the PC and `…-Phone` on the phone. The first time, uninstall the old Lightning app before installing Lightning Test: both use the same network port. Matched build downloads last seven days.
- **For milestone 2: review the phone brand guideline.** Part C of the brand guideline (3.25, 2026-10-06) is the phone's own: bottom tab bar, 2 × 2 KPIs, phone forms of every chart. Check it, especially the five bottom sections (C03.1), then say it is final. Until then phone screens follow it as a draft.
- **Before Google Play: the SMS declaration.** Reading SMS needs Google's approval under *SMS-based money management*. When the beta is near I draft the Play Console declaration, the privacy policy page and a short screen video; you submit them from your developer account.
- **For milestone 3: more bank SMS.** CIB and NBE are in `tests/fixtures/bank_sms.json` (details changed). Send other banks, and from these two a refund, a declined payment and a purchase in English if you get them; paste them in chat and I change the details before they go in.
- **GitHub spending limit (your choice, 2026-10-06):** GitHub › Settings › Billing and licensing › Budgets and alerts: set Actions to $0 (or the most you accept). CI then pauses until next month instead of charging you.
- **Website search:** add `lightningeg.com` to Google Search Console and Bing Webmaster Tools; submit `/sitemap.xml`.
- **Activate website feedback screenshots:** in the existing Apps Script receiver, replace or add `apps-script/AppFeedbackReceiverPatch.gs` from `Lightning_website`, route `form_type=app_feedback` to `saveAppFeedback_`, run `setupAppFeedbackDrive()` from the editor as the deployment owner and grant Drive access, then deploy a new version. This creates a private folder in the deployment owner's Drive; the feedback Sheet stores links to those files. The website form code is pushed, but screenshot storage stays inactive until this deployment is done.
- **Retest:** on the PC whose window failed to start, try a ZIP downloaded in a browser. Builds from `f4e1603` on include the fix.


## To decide

1. *Multiple devices — two choices:* offer optional fingerprint unlock on Android, or retain password-only? Keep two-PC lending as a test harness (recommended), or authorize a separately accepted PC-home interim product? Defaults remain password-only and phone-home. Windows in-app updates are already requested in the Overview; the first beta uses a manual-update path. Bank samples and platform evidence are engineering gates in the plan.
2. *Review of Mohab's year:* which of these suggestions should be built? None has been started.
   1. Say *to* or *from* on transfer rows.
   2. Needs you lists expected income not yet received.
   3. Early in the month, Change in net worth gets a note naming the expected income.
   4. The Investments sparkline marks sales.
   5. Reserves offers to complete a goal once its payment is linked.
   6. Check against bank offers "mark all checked up to this date" when the balances match.
   7. At phone width, the top menu and the accounts fit on screen.
   8. Loans still to pay and Check against bank show without opening a folded row.
3. *Competition:* should Lightning get gam'eya (rotating savings) and zakat, as Qershnat has them? (Trial decided: 7 days free, never a lock; Project Overview › Product decisions.)
4. *Routine audit (2026-10-05):* pain points to decide: Housing 22% vs 45%, "Kept 0", "Split · 0 categories", a certificate named twice, Reserves dropdowns (A16: type and pick).
5. *Upcoming projects* (Project Overview): 17 ideas, each naming its source app. Financial health (#3) and the entry helpers (#9: sums, Ctrl-K, privacy mode, #tags) are built. New from you: multi-currency and FX revaluation (#15), US stocks (#16), reading PDF and Excel files (#17). Which enter *Next*, and where do US stock prices come from?
6. *Restore, from Claude's review of 03a:* unlock re-verifies every retained copy (2.7 s for three 23.5 MB restores). Keep that, or drop it?
7. *Ratios (2026-10-05):* when should a ratio turn strong rose (needs you)? Suggested: loan payments over 35% of income, fixed costs over 50% of it. Until then the four ratio cards on Loans and Recurring stay soft rose (Project Overview › Upcoming projects #3).
8. *Restore release risk:* after the ordinary Windows dummy-data reboot drill passes, accept real-data restore with abrupt power-loss durability still unverified, or defer it until a controlled power-cut drill passes? The precise failure and fail-closed behavior are in Architecture › Promotion durability risk and release gate. No process-kill or normal-reboot result should be described as power-cut evidence.
9. *Additional sample profiles:* resolved 2026-10-10. The published fictional briefs for Amr, Abdelrahman, Menna and Fatma now load into an empty profile; their definitions live together in `lightning/samples/profiles/`.
10. *Import link window (2026-10-05, [proposal](docs/proposals/import_matching.md)):* keep 3 days either side, or widen to 7 like Actual? 7 catches slow card postings; 3 avoids offering last week's equal payment (a café, a class) as this week's. Default: keep 3.
11. *Stale remote branches:* delete these on GitHub? Nothing was deleted. arabic-guideline-alignment, ccr-e204629c-57eq11, claude/{app-ux-ui-audit-if1fld, arabic-guideline-alignment, brand-guideline-split-2muzab, dreamy-cori-aug9vj, funny-hopper-gjm53x, gallant-feynman-sl624z, great-pascal-kex9vy, modest-pasteur-vldhf6, peaceful-hamilton-5s6qbx, sweet-bohr-05v24c, test-suite-audit-cleanup-2z39r0, vibrant-cori-04ujxo, vigilant-thompson-kcfc0x, wizardly-gauss-7wkcbq}, codex-exec, codex/exec. Cloud sessions get random branch names by default (`ccr-*`, `claude/<random>`); AGENTS.md section 6 asks for `who/feature`, so such branches should be renamed or deleted after merging.
