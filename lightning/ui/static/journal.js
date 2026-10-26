/* Display acknowledgements are separate from durable delivery acknowledgements. */
'use strict';
const token = document.querySelector('input[name="__session"]')?.value;
const seen = new Set();
let sending = false;
async function acknowledgeVisible() {
  if (sending || !token || !seen.size || document.visibilityState !== 'visible') return;
  sending = true;
  const ids = [...seen].slice(0, 20);
  const data = new URLSearchParams({__session: token});
  ids.forEach(id => data.append('proposal', id));
  try {
    const response = await fetch('/seen', {method: 'POST', body: data, credentials: 'same-origin'});
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
    if (document.querySelector('[data-pairing-pending]') && !document.querySelector('[data-pairing-poll]') && token) {
      const paired = await fetch('/devices/check', {method:'POST', credentials:'same-origin',
        body:new URLSearchParams({__session:token, automatic:'1'})});
      if (paired.ok && (await paired.json()).paired) { location.href='/devices'; return; }
    }
    const response = await fetch('/status', {credentials: 'same-origin', cache: 'no-store'});
    if (response.ok && (await response.json()).version !== initialVersion && !dirty) location.reload();
  } catch (_) { /* An unavailable local app leaves the current view intact. */ }
}, 5000);
