// Run from repo root: node reports/r22-code-quality-and-smart-features/evidence/search-race.cjs
// Executes the actual live-search initializer with a small DOM/fetch double.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const source = fs.readFileSync(path.join(root, 'lightning/ui/static/phone-capture.js'), 'utf8');
const begin = source.indexOf('  const live = (root) => {');
const end = source.indexOf('  document.addEventListener("DOMContentLoaded", () => live(document));', begin);
assert(begin >= 0 && end > begin);
let completeOld;
const oldBody = new Promise(resolve => { completeOld = resolve; });
const listeners = {};
const field = { value: 'old', hasAttribute: () => false, addEventListener: () => {} };
const target = { innerHTML: '' };
const form = { dataset: {liveSearch: '#results'}, querySelector: () => field,
  getAttribute: () => '/search', addEventListener: (name, callback) => {listeners[name] = callback;} };
let address = '';
const context = { root: { querySelectorAll: () => [form] }, document: {querySelector: () => target},
  window: {}, location: {href: 'http://localhost/search'}, URL, URLSearchParams, clearTimeout, setTimeout,
  history: {state: {}, replaceState: (_state, _title, value) => { address = value; }},
  fetch: async url => ({ok: true, text: () => url.includes('q=old') ? oldBody : Promise.resolve('NEW RESULTS')}) };
vm.runInNewContext(source.slice(begin, end) + '\nlive(root);', context);
(async () => {
  const submit = () => listeners.submit({preventDefault() {}});
  submit();
  await new Promise(setImmediate); // old response headers arrived, body still pending
  field.value = 'new';
  submit();
  await new Promise(setImmediate);
  assert.equal(target.innerHTML, 'NEW RESULTS');
  completeOld('OLD RESULTS');
  await new Promise(setImmediate);
  assert.equal(target.innerHTML, 'OLD RESULTS');
  assert.equal(address, '/search?q=old');
  console.log('F2: field=new; results=OLD RESULTS; URL=/search?q=old (old response body overwrites newer search).');
})().catch(error => { console.error(error); process.exitCode = 1; });
