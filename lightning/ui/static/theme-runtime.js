/* Synchronous head boot: no requests, no reload, no financial state. */
(() => {
  'use strict';
  const key = 'lightning_theme';
  const themes = window.LIGHTNING_THEMES || [];
  const fallback = 'lightning-default';
  const root = document.documentElement;
  const profile = document.querySelector('meta[name=lightning-theme]');
  // Paid themes this computer holds a licence for (server-verified, lightning/ui/entitlements.py). Without a profile
  // (the theme workbench) nothing is sold, so every theme counts as owned there.
  const ownedMeta = document.querySelector('meta[name=lightning-owned]');
  const owned = id => !ownedMeta || (ownedMeta.content || '').split(' ').includes(id);
  const tr = text => window.lightningT ? window.lightningT(text) : text;
  let writes = Promise.resolve();
  let writeVersion = 0;
  const known = id => themes.some(theme => theme.id === id);
  const normalize = id => known(id) ? id : fallback;
  const read = () => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const syncControls = () => document.querySelectorAll('[data-theme-select]').forEach(select => {
    select.value = root.dataset.theme;
  });
  const still = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  // Materials and motions (theme-materials.css) are root attributes: data-m-cards-finish="satin". Only approved
  // values from the generated registry reach them; switching clears the last theme's set first.
  function wearMaterials(meta) {
    [...root.attributes].forEach(a => { if (a.name.startsWith('data-m-')) root.removeAttribute(a.name); });
    Object.entries(meta.materials || {}).forEach(([key, value]) => root.setAttribute('data-m-' + key, value));
  }
  // The equip moment: one light sweep when someone puts a theme on, never at boot or under reduced motion.
  function unveil() {
    if (root.getAttribute('data-m-ground-equip') !== 'unveil' || still() || !document.body) return;
    const sweep = document.createElement('div');
    sweep.className = 'theme-unveil'; sweep.setAttribute('aria-hidden', 'true');
    sweep.addEventListener('animationend', () => sweep.remove());
    document.body.append(sweep);
    setTimeout(() => sweep.remove(), 2000);
  }
  // A theme being tried opens the unlock panel and points "See prices" at that theme (an id from the registry only).
  function showUnlock(id) {
    const meta = themes.find(theme => theme.id === id);
    const details = document.querySelector('details.theme-unlock');
    if (!meta || !details) return;
    details.open = true;
    const link = details.querySelector('[data-theme-prices]');
    if (link) link.href = 'https://lightningeg.com/marketplace.html?item=' + encodeURIComponent(meta.item || meta.id) + '&from=app#themes';
  }
  function apply(id, persist = true) {
    const next = normalize(id);
    const changed = root.dataset.theme !== next;
    root.dataset.theme = next;
    const meta = themes.find(theme => theme.id === next) || {};
    wearMaterials(meta);
    if (persist && changed) unveil();
    let saved = true;
    // Without a profile (theme workbench) the browser is the store. With one, the profile database is, and the
    // browser copy is written only after the server kept it: a paid theme being tried, or a save that failed,
    // never outlives the session (2026-10-28 theme audit).
    if (persist && !profile) {
      try { localStorage.setItem(key, next); } catch (_) { saved = false; }
    }
    if (persist && profile) {
      const version = ++writeVersion;
      const token = document.querySelector('meta[name=lightning-session]')?.content
        || document.querySelector('input[name=__session]')?.value || '';
      const status = document.querySelector('[data-theme-status]');
      if (status) status.textContent = tr('Saving…');
      // Coalesce: scrolling through the list with the arrow keys sends one save, for the last theme.
      writes = writes.then(() => new Promise(resolve => setTimeout(resolve, 250))).then(async () => {
        if (version !== writeVersion) return;
        const response = await fetch('/settings/theme', { method: 'POST', credentials: 'same-origin',
          keepalive: true, body: new URLSearchParams({ theme: next, __session: token }) });
        if (response.status === 402) throw Object.assign(new Error('try'), { trying: true });
        if (!response.ok) throw new Error('Could not save theme');
        try { localStorage.setItem(key, next); } catch (_) { /* other tabs follow on their next load */ }
        if (version === writeVersion) {
          const status = document.querySelector('[data-theme-status]');
          if (status) status.textContent = tr('Theme saved.');
        }
      }).catch(error => {
        if (version !== writeVersion) return;
        const status = document.querySelector('[data-theme-status]');
        const message = error && error.trying
          ? 'Trying it for this session. Unlock it below to keep it.'
          : 'Theme applied for this session; could not save on this device.';
        if (status) status.textContent = tr(message);
        if (error && error.trying) showUnlock(next);
        window.dispatchEvent(new CustomEvent('lightning:themechange', { detail: { id: next, saved: false } }));
      });
    }
    syncControls();
    window.dispatchEvent(new CustomEvent('lightning:themechange', { detail: { id: next, saved } }));
    return { id: next, saved };
  }
  apply(profile ? profile.content : read(), false);
  window.LightningTheme = Object.freeze({ set: apply, list: () => themes.map(theme => ({ ...theme })) });
  // Another tab changed the theme. A paid theme follows only where this profile owns it, so a theme kept in
  // one profile never shows up unlicensed in another profile's open tab.
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    const meta = themes.find(theme => theme.id === event.newValue);
    if (profile && meta && meta.paid && !owned(meta.item || meta.id)) return;
    apply(event.newValue, false);
  });
  // Night version: a theme with an "-night" twin (dendera / dendera-night) can follow the computer's light or
  // dark setting. A device choice, so it lives in this browser; the profile keeps the day theme.
  const nightKey = 'lightning_theme_follow_night';
  const twin = id => known(id + '-night') ? id + '-night' : null;
  const follows = () => { try { return localStorage.getItem(nightKey) === '1'; } catch (_) { return false; } };
  const dark = window.matchMedia ? matchMedia('(prefers-color-scheme: dark)') : null;
  let dayTheme = root.dataset.theme;
  function wearForScheme() {
    const night = twin(dayTheme);
    if (!night || !follows()) return;
    const want = dark && dark.matches ? night : dayTheme;
    if (root.dataset.theme !== want) apply(want, false);
  }
  window.addEventListener('lightning:themechange', event => {
    const id = event.detail && event.detail.id;
    if (id && !id.endsWith('-night')) dayTheme = id;
    document.querySelectorAll('[data-theme-night]').forEach(row => { row.hidden = !twin(dayTheme); });
  });
  if (dark && dark.addEventListener) dark.addEventListener('change', wearForScheme);
  wearForScheme();
  // Pointer light (cards hover "light"): the card under the pointer gets --lt-x/--lt-y; CSS draws the light.
  document.addEventListener('pointermove', event => {
    if (root.getAttribute('data-m-cards-hover') !== 'light' || event.pointerType === 'touch' || still()) return;
    const card = event.target.closest && event.target.closest('.card, .kpi-card, .overview-block, .data-panel, .metric-card');
    if (!card) return;
    const box = card.getBoundingClientRect();
    card.style.setProperty('--lt-x', (event.clientX - box.left) + 'px');
    card.style.setProperty('--lt-y', (event.clientY - box.top) + 'px');
  }, { passive: true });
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-theme-select]').forEach(select => {
      themes.forEach(theme => {
        const option = document.createElement('option');
        option.value = theme.id;
        option.textContent = theme.paid && !owned(theme.item || theme.id) ? tr(theme.name) + ' ' + tr('(try it)')
          : tr(theme.name + (theme.preview ? ' (preview)' : ''));
        select.append(option);
      });
      select.addEventListener('change', () => {
        const result = apply(select.value);
        const status = document.querySelector('[data-theme-status]');
        if (status) status.textContent = result.saved ? '' : (window.lightningT ? window.lightningT('Theme applied for this session; could not save on this device.') : 'Theme applied for this session; could not save on this device.');
      });
    });
    document.querySelectorAll('[data-theme-night]').forEach(row => {
      row.hidden = !twin(dayTheme);
      const box = row.querySelector && row.querySelector('input');
      if (!box) return;
      box.checked = follows();
      box.addEventListener('change', () => {
        try { localStorage.setItem(nightKey, box.checked ? '1' : '0'); } catch (_) { /* session only */ }
        if (box.checked) wearForScheme(); else if (root.dataset.theme !== dayTheme) apply(dayTheme, false);
      });
    });
    syncControls();
  });
})();
