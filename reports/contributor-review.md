# Yusuf contribution review · 2026-10-23

Scope: all four open PRs from `@yoreva-01`, reviewed against main `9f56edc`. The owner requested corrections, a security audit and integration into main. Original contributor commits remain in the review branch; the maintainer corrections are separate. This is a review of these changes and their surrounding trust boundaries, not a claim that the whole application has no vulnerabilities.

| PR and original commit | Result of review | Correction |
|---|---|---|
| [105](https://github.com/LightningEg/Lightning/pull/105), `c2472fb` · 2O | Chromium reproduced the missing numeric count: its own new test failed on “Delete these transactions?”. | Confirm unique submitted IDs with localized count, keep the actual Delete submitter, and suppress queued repeated confirmations. Real browser coverage exercises Cancel, Confirm, Undo and category changes in English and Arabic. |
| [108](https://github.com/LightningEg/Lightning/pull/108), `c6d608d` · 3D | Excluding device status from timeout is correct, but source-text tests did not establish behavior. A later toast rule still positioned it as a floating notice. Popup feedback could also overwrite its text and Hand back form, or remove Undo from an ordinary phone notice. | Keep banners in normal page flow and exclude them from popup-success reuse; preserve the phone notice's Undo form while updating its message. Browser checks advance time past the notice timeout and verify the action remains after popup feedback. |
| [109](https://github.com/LightningEg/Lightning/pull/109), `0b1e879` · 3E | Template plus values and the compatible translation filter are sound. Lent/return/repair messages were incomplete, and long device names could overflow. | Add missing status translations, wrap long names and test both rendered templates with literal HTML, braces and a name matching a system label (“Settings”). Explicit peer values stay literal; system fallback text still translates. |
| [110](https://github.com/LightningEg/Lightning/pull/110), `d713dd3` · 2K | Moving routing inside the outer transaction is the right fix. Both original new tests pass zero payment and fail during conversion validation. | Add cases that observe a successfully posted conversion, then fail the buy. Every persisted table must match its earlier snapshot, with both a new and an existing pocket. The existing successful conversion/purchase cases remain. |

The Arabic Delete/Undo sequence additionally reproduced an unreachable Undo button: RTL mirrored `left:50%` into `right:50%` but retained the negative transform. Notices now centre with direction-independent insets and automatic margins; the same real browser sequence reaches Undo normally. RTL CSS is regenerated from its source, and both template asset versions are updated.

## Security assessment

- **Untrusted names and messages:** inspected the runtime-to-template path and shared translation filter. HTML uses Jinja escaping; browser dialog titles/messages use `textContent`. English and Arabic render tests supply an image event handler, formatting braces and a device name matching a translated system label and verify escaped output, preserved literal content and the current session token. No `safe`/HTML bypass is introduced.
- **Authorization and CSRF:** the banner remains behind the existing `Guard` and `SessionGate`; Hand back remains POST with the active profile token. Missing and stale tokens are refused. Existing exact-origin, launch-cookie, session-role and real two-device round-trip tests cover the production boundaries.
- **Financial integrity:** routing, pocket creation, conversion, executed-rate updates, purchase and undo/audit rows share the existing nested SQLite transaction. The new whole-database comparisons verify rollback after a successful conversion and a refused purchase; ordinary successful buys are covered by existing tests. No external file mutation was added to this path.
- **Browser workflow:** confirmation preserves the submitter's `formaction`; Cancel does not mutate financial state or selection. Repeated submit events cannot queue an extra destructive prompt. Category change continues through its own destination.
- **Supply chain and privilege:** all changed files and surrounding workflow paths were inspected. These contributions change no dependencies, CI workflows, release/signing files or permissions and add no network/execution endpoint. The integration PR must pass the existing CI checks; contributor fork runs being held is not test evidence.

No new exploitable security defect was demonstrated in the reviewed changes. The reproduced UI defects and financial atomicity gap are corrected. Native Windows/Android acceptance, a human Arabic voice review and an exhaustive audit of unrelated modules are outside this verification. Existing audit-4 findings outside 2K/2O remain tracked in [PR 101](https://github.com/LightningEg/Lightning/pull/101).

## Validation

- Full local suite: **2,366 passed, 10 skipped, 6 warnings** in 545.60 s; it includes the existing profile/guard, device round-trip, Arabic, number-audit and Mohab acceptance checks.
- Final focused and device set after retaining Undo and literal peer names: **65 passed** in 45.92 s, with Chromium installed; none of these cases skipped. The popup regression makes a real guarded HTTP edit and clicks Undo after feedback; other cases cover name/fallback rendering, read-only refusals and the existing live two-device paths.
- All **4** import contracts kept; issue-index and diff checks pass. The sibling website guideline comparison also passes separately.
- Real encrypted phone/PC pairing and captures succeeded in English and Arabic. The new Arabic [PC](contributor-review/sync-pc-ar.webp) and [phone](contributor-review/sync-phone-ar.webp) captures are ready for the website's existing recapture batch (8F). Separate 1280 px PC and 320 px phone checks show device actions in flow without horizontal overflow.
- The exact final head must also pass the normal integration PR's test, CodeQL, dependency-review and journal-security jobs before merge; their results are recorded on that PR.

Screens and profiles use disposable dummy data. No personal financial data or real user credentials were used. The claim checker flags Claude’s `style.css` claim; the owner-authorized review corrections touch only the shared banner/notice rules required by 3D/3E and reachable Undo. The other claimed screen styles are preserved.

Our earlier [PR 107](https://github.com/LightningEg/Lightning/pull/107) also fixes phone Delete alongside mass-edit recovery. This integration selects one phone Delete implementation for main; the earlier stack must be rebased to retain its remaining work without reintroducing the duplicate patch.
