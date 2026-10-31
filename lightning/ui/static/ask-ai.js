// Ask an AI (Settings > Your data): the server builds one file from this profile's own figures; this script copies it or
// saves it. The text is never put on the page, and nothing is sent anywhere but this device's own server.
(() => {
  const card = document.querySelector('[data-ask-ai]');
  const form = card?.querySelector('[data-ask-form]');
  if (!form) return;
  const status = card.querySelector('[data-ask-status]');
  const buttons = [...form.querySelectorAll('[data-ask-copy],[data-ask-save]')];
  const say = (text) => { status.textContent = text; };
  const t = (text, values) => window.lightningT(text, values);

  async function prepare() {
    say(t('Preparing…'));
    buttons.forEach((b) => { b.disabled = true; });
    try {
      const response = await fetch(form.action, { method: 'POST', body: new URLSearchParams(new FormData(form)), headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok) throw new Error(await response.text());
      const disposition = response.headers.get('Content-Disposition') || '';
      return {
        text: await response.text(),
        name: (disposition.match(/filename="?([^";]+)"?/i) || [])[1] || 'lightning-brief.md',
        tokens: Number(response.headers.get('X-Brief-Tokens') || 0).toLocaleString('en-US'),
        shown: response.headers.get('X-Brief-Rows') || '0',
        total: response.headers.get('X-Brief-Rows-Total') || '0',
      };
    } finally {
      buttons.forEach((b) => { b.disabled = false; });
    }
  }

  // The clipboard needs a secure page; where it is missing the text goes through a temporary box that is removed at once.
  async function copy(text) {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return; }
    const box = document.createElement('textarea');
    box.value = text; box.setAttribute('aria-hidden', 'true'); box.style.position = 'fixed'; box.style.opacity = '0';
    document.body.appendChild(box); box.select();
    try { if (!document.execCommand('copy')) throw new Error('Copy unavailable'); } finally { box.remove(); }
  }

  function save(brief) {
    const url = URL.createObjectURL(new Blob([brief.text], { type: 'text/markdown;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url; link.download = brief.name; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  form.querySelector('[data-ask-copy]').addEventListener('click', async () => {
    try {
      const brief = await prepare();
      try {
        await copy(brief.text);
        say(t('Copied. About {tokens} tokens, {shown} of {total} rows. Paste it into your AI tool.', brief));
      } catch (_) {
        save(brief);
        say(t('Copying was blocked, so the file was saved instead: {name}.', brief));
      }
    } catch (error) { say(t(error.message || 'Could not prepare the file.')); }
  });

  form.querySelector('[data-ask-save]').addEventListener('click', async () => {
    try {
      const brief = await prepare();
      save(brief);
      say(t('Saved {name}. About {tokens} tokens, {shown} of {total} rows.', brief));
    } catch (error) { say(t(error.message || 'Could not prepare the file.')); }
  });
})();
