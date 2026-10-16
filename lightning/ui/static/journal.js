(() => {
  'use strict';
  const root = document.querySelector('meta[name="journal-root"]')?.content;
  if (root) {
    const original = window.fetch.bind(window);
    window.fetch = async (...arguments_) => {
      const response = await original(...arguments_);
      if (response.headers.get('X-Lightning-Journal') !== 'page') return response;
      const target = new URL(response.url, location.href);
      if (target.origin !== location.origin || !target.pathname.startsWith(root + '/')) return response;
      location.assign(target.href);
      // The old form must not replace a register row with a complete journal
      // page or show a shadow value as confirmed while navigation completes.
      return new Promise(() => {});
    };
  }
  if (!document.querySelector('meta[name="journal-version"]')) return;
/* Display acknowledgements are separate from durable delivery acknowledgements. */
'use strict';
const journalRoot = document.querySelector('meta[name="journal-root"]')?.content || '';
const token = document.querySelector('meta[name="journal-session"]')?.content || document.querySelector('input[name="__session"]')?.value;
const seen = new Set();
let sending = false;
async function acknowledgeVisible() {
  if (sending || !token || !seen.size || document.visibilityState !== 'visible') return;
  sending = true;
  const ids = [...seen].slice(0, 20);
  const data = new URLSearchParams({__session: token});
  ids.forEach(id => data.append('proposal', id));
  try {
    const response = await fetch(journalRoot + '/seen', {method: 'POST', body: data, credentials: 'same-origin'});
    if (response.ok) ids.forEach(id => seen.delete(id));
  } catch (_) { /* Retry when displayed again; never age out an unseen refusal. */ }
  sending = false;
}
const observer = new IntersectionObserver(entries => {
  entries.filter(entry => entry.isIntersecting).forEach(entry => seen.add(entry.target.dataset.seenProposal));
  acknowledgeVisible();
});
document.querySelectorAll('[data-seen-proposal]').forEach(node => observer.observe(node));
let dirty = false;
document.addEventListener('input', () => { dirty = true; });
const initialVersion = document.querySelector('meta[name="journal-version"]')?.content;
setInterval(async () => {
  if (document.visibilityState !== 'visible') return;
  acknowledgeVisible();
  if (dirty || !initialVersion) return;
  try {
    if (document.querySelector('[data-pairing-pending]') && token) {
      const paired = await fetch(journalRoot + '/devices/check', {method:'POST', credentials:'same-origin',
        body:new URLSearchParams({__session:token, automatic:'1'})});
      if (paired.ok && (await paired.json()).paired) { location.href=journalRoot + '/devices'; return; }
    }
    const response = await fetch(journalRoot + '/status', {credentials: 'same-origin', cache: 'no-store'});
    if (response.ok && (await response.json()).version !== initialVersion && !dirty) location.reload();
  } catch (_) { /* An unavailable local app leaves the current view intact. */ }
}, 5000);

})();
