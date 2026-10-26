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
  function apply(id, persist = true) {
    const next = normalize(id);
    const changed = root.dataset.theme !== next;
    root.dataset.theme = next;
    const meta = themes.find(theme => theme.id === next) || {};
    wearMaterials(meta);
    if (persist && changed) unveil();
    let saved = true;
    if (persist) {
      try { localStorage.setItem(key, next); } catch (_) { saved = Boolean(profile); }
    }
    if (persist && profile) {
      const version = ++writeVersion;
      const token = document.querySelector('meta[name=lightning-session]')?.content
        || document.querySelector('input[name=__session]')?.value || '';
      writes = writes.then(async () => {
        const response = await fetch('/settings/theme', { method: 'POST', credentials: 'same-origin',
          keepalive: true, body: new URLSearchParams({ theme: next, __session: token }) });
        if (response.status === 402) throw Object.assign(new Error('try'), { trying: true });
        if (!response.ok) throw new Error('Could not save theme');
        if (version === writeVersion) {
          const status = document.querySelector('[data-theme-status]');
          if (status) status.textContent = tr('Theme saved.');
        }
      }).catch(error => {
        if (version !== writeVersion) return;
        const status = document.querySelector('[data-theme-status]');
        const message = error && error.trying
          ? 'Trying it for this session. Buy it on lightningeg.com, then unlock it below to keep it.'
          : 'Theme applied for this session; could not save on this device.';
        if (status) status.textContent = tr(message);
        window.dispatchEvent(new CustomEvent('lightning:themechange', { detail: { id: next, saved: false } }));
      });
    }
    syncControls();
    window.dispatchEvent(new CustomEvent('lightning:themechange', { detail: { id: next, saved } }));
    return { id: next, saved };
  }
  apply(profile ? profile.content : read(), false);
  window.LightningTheme = Object.freeze({ set: apply, list: () => themes.map(theme => ({ ...theme })) });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) apply(event.newValue, false);
  });
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
    syncControls();
  });
})();
