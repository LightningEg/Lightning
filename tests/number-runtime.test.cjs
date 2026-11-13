/* Run: LANG=de_DE.UTF-8 node --test tests/number-runtime.test.cjs */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const document = {
  documentElement: { lang: 'en', dataset: { weekStart: '6' }, classList: { contains: () => false, toggle() {} } },
  querySelectorAll: () => [], querySelector: () => null, getElementById: () => null,
  addEventListener() {}, createTreeWalker: () => ({ nextNode: () => false }),
};
const window = { addEventListener() {}, matchMedia: () => ({ matches: true }) };
const context = vm.createContext({
  window, document, location: { pathname: '/' },
  localStorage: { getItem: () => null, setItem() {} },
  sessionStorage: { getItem: () => null, setItem() {} },
  MutationObserver: class { observe() {} },
  NodeFilter: { SHOW_TEXT: 4 },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../lightning/ui/static/app.js'), 'utf8'), context);

test('numbers use English grouping and a true minus under the host locale', () => {
  assert.equal(window.lightningNumber(-1234.5, { min: 2 }), '−1,234.50');
  assert.equal(window.lightningNumber(1234.5, { min: 2 }), '1,234.50');
  assert.equal(window.lightningNumber(0, { min: 2 }), '0.00');
});

test('unit prices keep their precision and money keeps two decimals', () => {
  assert.equal(window.lightningNumber(1234.567891, { min: 2, max: 6 }), '1,234.567891');
  assert.equal(window.lightningNumber(12, { min: 2, max: 2 }), '12.00');
  assert.equal(window.lightningNumber(12, { min: 0, max: 0 }), '12');
});

test('signed values include a plus only when the displayed value is positive', () => {
  assert.equal(window.lightningNumber(12.5, { signed: true }), '+12.5');
  assert.equal(window.lightningNumber(-12.5, { signed: true }), '−12.5');
  assert.equal(window.lightningNumber(0, { signed: true }), '0');
  assert.equal(window.lightningNumber(0.001, { signed: true }), '0');
});
