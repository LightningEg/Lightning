/* Pairing discovery runs only on a visible pairing screen; typing is preserved. */
'use strict';
(() => {
  const screen = document.querySelector('[data-pairing-poll]');
  if (!screen) return;
  let busy = false;
  let dirty = false;
  document.addEventListener('input', () => { dirty = true; });
  async function poll() {
    if (busy || dirty || document.visibilityState !== 'visible') return;
    busy = true;
    try {
      const response = await fetch(screen.dataset.pairingPoll, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        body: new URLSearchParams({[screen.dataset.tokenName]: screen.dataset.token})
      });
      if (response.ok && (await response.json()).version !== screen.dataset.version && !dirty) location.reload();
    } catch (_) { /* Leave the current screen intact and retry while visible. */ }
    finally { busy = false; }
  }
  setInterval(poll, 3000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  poll();
})();
