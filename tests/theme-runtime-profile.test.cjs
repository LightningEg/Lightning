/* Run: node --test tests/theme-runtime-profile.test.cjs — theme audit 2026-10-28: profile mode rules. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const staticDir = path.join(__dirname, '../lightning/ui/static');

function boot({ theme = 'lightning-default', owned = '', status = 204 } = {}) {
  const windowEvents = {}, events = {}, memory = new Map(), posts = [];
  const attrs = new Map();
  const root = { dataset: {}, setAttribute(k, v) { attrs.set(k, String(v)); }, getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
    removeAttribute(k) { attrs.delete(k); }, get attributes() { return [...attrs].map(([name, value]) => ({ name, value })); } };
  const metas = { 'meta[name=lightning-theme]': { content: theme }, 'meta[name=lightning-owned]': { content: owned } };
  const statusEl = { textContent: '' };
  const document = { documentElement: root, querySelectorAll: () => [],
    querySelector: s => metas[s] || (s === '[data-theme-status]' ? statusEl : null),
    createElement: () => ({}), addEventListener(type, fn) { events[type] = fn; } };
  const window = { addEventListener(type, fn) { windowEvents[type] = fn; }, dispatchEvent(e) { windowEvents[e.type]?.(e); } };
  const localStorage = { getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v) };
  const fetch = async (url, opts) => { posts.push(String(opts.body)); return { ok: status < 300, status }; };
  class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } }
  const context = vm.createContext({ document, window, localStorage, fetch, CustomEvent, setTimeout: fn => fn(),
    URLSearchParams });
  vm.runInContext(fs.readFileSync(path.join(staticDir, 'themes.generated.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(staticDir, 'theme-runtime.js'), 'utf8'), context);
  return { window, root, memory, posts, windowEvents, statusEl };
}
const settle = () => new Promise(r => setImmediate(r));

test('a paid theme being tried is never written to the browser store', async () => {
  const app = boot({ status: 402 });
  app.window.LightningTheme.set('nile');
  await settle(); await settle();
  assert.equal(app.root.dataset.theme, 'nile');
  assert.equal(app.memory.get('lightning_theme'), undefined);
});

test('a kept theme is written to the browser store only after the profile saved it', async () => {
  const app = boot();
  app.window.LightningTheme.set('royal-obsidian-gold');
  assert.equal(app.memory.get('lightning_theme'), undefined);
  await settle(); await settle();
  assert.equal(app.memory.get('lightning_theme'), 'royal-obsidian-gold');
});

test('quick changes send one save, for the last theme', async () => {
  const app = boot();
  app.window.LightningTheme.set('royal-obsidian-gold');
  app.window.LightningTheme.set('lightning-default');
  app.window.LightningTheme.set('royal-obsidian-gold');
  await settle(); await settle(); await settle();
  assert.equal(app.posts.length, 1);
  assert.match(app.posts[0], /theme=royal-obsidian-gold/);
});

test('another tab cannot put an unowned paid theme on this profile', () => {
  const app = boot();
  app.windowEvents.storage({ key: 'lightning_theme', newValue: 'nile' });
  assert.equal(app.root.dataset.theme, 'lightning-default');
  const owner = boot({ owned: 'nile' });
  owner.windowEvents.storage({ key: 'lightning_theme', newValue: 'nile' });
  assert.equal(owner.root.dataset.theme, 'nile');
});
