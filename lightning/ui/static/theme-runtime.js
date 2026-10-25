/* Synchronous head boot: no requests, no reload, no financial state. */
(() => {
  'use strict';
  const key = 'lightning_theme';
  const themes = window.LIGHTNING_THEMES || [];
  const fallback = 'lightning-default';
  const root = document.documentElement;
  const profile = document.querySelector('meta[name=lightning-theme]');
  let writes = Promise.resolve();
  let writeVersion = 0;
  const known = id => themes.some(theme => theme.id === id);
  const normalize = id => known(id) ? id : fallback;
  const read = () => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const syncControls = () => document.querySelectorAll('[data-theme-select]').forEach(select => {
    select.value = root.dataset.theme;
  });
  function apply(id, persist = true) {
    const next = normalize(id);
    root.dataset.theme = next;
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
        if (!response.ok) throw new Error('Could not save theme');
      }).catch(() => {
        if (version !== writeVersion) return;
        const status = document.querySelector('[data-theme-status]');
        const message = 'Theme applied for this session; could not save on this device.';
        if (status) status.textContent = window.lightningT ? window.lightningT(message) : message;
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
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-theme-select]').forEach(select => {
      themes.forEach(theme => {
        const option = document.createElement('option');
        option.value = theme.id;
        const name = theme.name + (theme.preview ? ' (preview)' : '');
        option.textContent = window.lightningT ? window.lightningT(name) : name;
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
