// Every AI hand-off prompt is two buttons, Copy and Edit; the text lives in the edit window, never open on the page.
const aiKept = new WeakMap();
const aiParts = (block) => ({
  area: block.querySelector('[data-prompt-text]'),
  status: block.querySelector('[data-prompt-status]'),
  dialog: block.querySelector('[data-ai-dialog]'),
});
const aiText = (block) => { if (!aiKept.has(block)) aiKept.set(block, aiParts(block).area.value); return aiKept.get(block); };
const aiEdit = (block) => {
  const { area, dialog } = aiParts(block);
  area.value = aiText(block);
  dialog.showModal();
  area.focus();
};

document.addEventListener('click', async (event) => {
  const block = event.target.closest('[data-ai-block]');
  if (!block) return;
  const { area, status, dialog } = aiParts(block);
  if (event.target.closest('[data-ai-edit]')) { aiEdit(block); return; }
  if (event.target.closest('[data-ai-save]')) { aiKept.set(block, area.value); dialog.close(); return; }
  if (event.target.closest('[data-ai-cancel]')) { area.value = aiText(block); dialog.close(); return; }
  if (!event.target.closest('[data-ai-copy]')) return;
  const text = aiText(block);
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      area.value = text;
      dialog.show();
      area.select();
      if (!document.execCommand('copy')) throw new Error('Copy unavailable');
      dialog.close();
    }
    status.textContent = window.lightningT('Prompt copied.');
  } catch (_) {
    aiEdit(block);
    area.select();
    status.textContent = window.lightningT('Clipboard access failed. The prompt is selected; copy it manually.');
  }
});

// Escape closes the window without keeping edits.
document.addEventListener('cancel', (event) => {
  const block = event.target.closest?.('[data-ai-block]');
  if (block) aiParts(block).area.value = aiText(block);
}, true);
