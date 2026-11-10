/* Run: node --test tests/plural-runtime.test.cjs (IV-3BC4: Arabic counts agree in the browser) */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load(table) {
  const window = { LIGHTNING_UI: table, LIGHTNING_COUNTED: { 'معاملة': ['معاملة واحدة', 'معاملتين', 'معاملات'], 'فئة': ['فئة واحدة', 'فئتين', 'فئات'] } };
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../lightning/ui/static/lightning-t.js'), 'utf8'), context);
  return window.lightningT;
}
const t = load({ 'Delete {count} transactions?': 'تحذف {count} معاملات؟', 'Delete 1 transaction?': 'تحذف معاملة واحدة؟' });

test('Arabic noun agrees with the count: one, two, three to ten, eleven and more', () => {
  assert.equal(t('Delete {count} transactions?', { count: 1 }), 'تحذف معاملة واحدة؟');
  assert.equal(t('Delete {count} transactions?', { count: 2 }), 'تحذف معاملتين؟');
  assert.equal(t('Delete {count} transactions?', { count: 5 }), 'تحذف 5 معاملات؟');
  assert.equal(t('Delete {count} transactions?', { count: 11 }), 'تحذف 11 معاملة؟');
});

test('the singular English key has its own Arabic', () => {
  assert.equal(t('Delete 1 transaction?'), 'تحذف معاملة واحدة؟');
});

test('without a table (English) text is only filled in', () => {
  const english = load({});
  assert.equal(english('Delete {count} transactions?', { count: 3 }), 'Delete 3 transactions?');
});

test('a count already written in Arabic digits still agrees', () => {
  assert.equal(t('Delete {count} transactions?', { count: '٢' }), 'تحذف معاملتين؟');
  assert.equal(t('Delete {count} transactions?', { count: '٣' }), 'تحذف ٣ معاملات؟');
});
