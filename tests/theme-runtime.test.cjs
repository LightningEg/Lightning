/* Run: node --test tests/theme-runtime.test.cjs */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const staticDir = path.join(__dirname, '../lightning/ui/static');
function boot(saved, blocked = false) {
  const events = {}, windowEvents = {}, memory = new Map([['lightning_theme', saved]]);
  const select = { value: '', options: [], append(option) { this.options.push(option); }, addEventListener(type, fn) { this[type] = fn; } };
  const attrs = new Map();
  const root = { dataset: {}, scrollTop: 340, setAttribute(k, v) { attrs.set(k, String(v)); }, getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
    removeAttribute(k) { attrs.delete(k); }, get attributes() { return [...attrs].map(([name, value]) => ({ name, value })); } };
  const input = { value: 'unsaved note' };
  const status = { textContent: '' };
  const document = { documentElement: root,
    querySelectorAll: () => [select], querySelector: selector => selector.startsWith("meta") ? null : status,
    createElement: () => ({}), addEventListener(type, fn) { events[type] = fn; } };
  const window = { addEventListener(type, fn) { windowEvents[type] = fn; }, dispatchEvent() {} };
  const storage = { getItem(key) { if (blocked) throw Error(); return memory.get(key); },
    setItem(key, value) { if (blocked) throw Error(); memory.set(key, value); } };
  const context = vm.createContext({ document, window, localStorage: storage, CustomEvent: class {} });
  vm.runInContext(fs.readFileSync(path.join(staticDir, 'themes.generated.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(staticDir, 'theme-runtime.js'), 'utf8'), context);
  return { window, root, select, events, windowEvents, memory, input, status };
}
test('boot restores before DOMContentLoaded and rejects stale IDs', () => {
  assert.equal(boot('royal-obsidian-gold').root.dataset.theme, 'royal-obsidian-gold');
  for (const id of [null, 'removed-theme', '"><script>']) assert.equal(boot(id).root.dataset.theme, 'lightning-default');
});
test('a material theme sets its recipes, and switching away clears them', () => {
  const app = boot('papyrus');
  assert.equal(app.root.getAttribute('data-m-ground-texture'), 'papyrus');
  assert.equal(app.root.getAttribute('data-m-hero-edge-style'), 'foil');
  app.events.DOMContentLoaded();
  app.select.value = 'royal-obsidian-gold'; app.select.change();
  assert.equal(app.root.getAttribute('data-m-ground-texture'), 'none');
  assert.equal(app.root.getAttribute('data-m-hero-edge-style'), 'hairline');
  app.window.LightningTheme.set('lightning-default');
  assert.equal(app.root.attributes.filter(a => a.name.startsWith('data-m-')).length, 0);
});
test('switch persists with the existing root and unsaved input untouched', () => {
  const app = boot(null), root = app.root;
  app.events.DOMContentLoaded();
  app.select.value = 'royal-obsidian-gold'; app.select.change();
  assert.equal(app.root, root); assert.equal(root.scrollTop, 340);
  assert.equal(app.input.value, 'unsaved note');
  assert.equal(app.memory.get('lightning_theme'), 'royal-obsidian-gold');
  assert.equal(boot(app.memory.get('lightning_theme')).root.dataset.theme, 'royal-obsidian-gold');
});
test('blocked storage remains usable and reports unsaved preference', () => {
  const app = boot(null, true); app.events.DOMContentLoaded();
  app.select.value = 'royal-obsidian-gold'; app.select.change();
  assert.equal(app.root.dataset.theme, 'royal-obsidian-gold');
  assert.match(app.status.textContent, /could not save/);
});
test('storage change, reset and clear synchronize an existing selector', () => {
  const app = boot('papyrus'); app.events.DOMContentLoaded();
  app.windowEvents.storage({ key: 'lightning_theme', newValue: 'royal-obsidian-gold' });
  assert.equal(app.select.value, 'royal-obsidian-gold');
  app.windowEvents.storage({ key: null, newValue: null });
  assert.equal(app.select.value, 'lightning-default');
  app.window.LightningTheme.set('unknown');
  assert.equal(app.memory.get('lightning_theme'), 'lightning-default');
});
test('public list returns copies and preview names are explicit', () => {
  const app = boot(null); app.events.DOMContentLoaded();
  const list = app.window.LightningTheme.list(); list[0].id = 'changed';
  assert.notEqual(app.window.LightningTheme.list()[0].id, 'changed');
  assert.ok(app.select.options.some(o => o.textContent.includes('(preview)')));
});
