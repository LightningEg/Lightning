---
name: owner-console-view
description: Add a view or a metric to the website's owner console (admin.html): an admin-only database function, a view in the generator, a script that draws it, and the tests. Use when the owner asks for a new count, chart or analysis on the site. Work happens in the Lightning_website repository.
---

# Add an owner-console view

Tool-neutral. Website repository. The console is one page with a menu and one view at a time. Read `js/owner-sales.js` and `supabase/migrations/20261031120000_admin_signups.sql` as the worked example (a Sign-ups view, built the same way).

## Steps

1. **Question first.** State the number the owner wants and its definition (member or account, which period, what counts as done). Counts only: nobody is named; no email, id, token or login leaves the database.
2. **Function** in a migration (skill `supabase-migration`): `public.admin_<name>(p_days integer default 90) returns jsonb`, `security definer set search_path = ''`, first line `perform private.require_mfa_admin();`, then `revoke all ... from public, anon; grant execute ... to authenticated, service_role;`. Bound every list (`limit 15`) and every period (`least(greatest(...), 365)`).
3. **Script** `js/owner-<name>.js`: copy the shape of `owner-sales.js` (verify event `lightning:owner-access`, view event `lightning:owner-view`, `FG.sb.rpc`, period buttons, refresh). Set every value with `textContent`; no `innerHTML`.
4. **Generator** `tools/store_admin.py`: add the name to `MENU`, an icon to `ICON`, a `view(...)`, `{name}` in the fieldset string, the script to the `scripts` tuple, and **bump `VERSION`** (the cache version; without it browsers keep the old dashboard script). Add the view id to `VIEWS` in `js/owner-dashboard.js`. Then `python tools/store_admin.py` and `python tools/footer.py`.
5. **Tests**: a database test against Postgres (pglite) that builds users and rows, calls the function as the admin, a member, anon and a weaker session, and asserts no email or id in the answer (`supabase/tests/admin-signups.test.mjs`); a page test in jsdom (`owner-signups-pages.test.mjs`); update `owner-dashboard-pages.test.mjs` (it pins the list of views). Install `jsdom` and `@electric-sql/pglite` outside the repo; run with `JSDOM_PATH=` and `PGLITE_PATH=`/a temporary `node_modules` link you remove before committing.
6. **Apply** the migration to the live project and verify privileges (skill `supabase-migration`); `python tools/site_check.py`; README › Owner dashboard names the view.
7. Open the pull request (skill `ship-pr`). The website has no CI: say what you ran.
