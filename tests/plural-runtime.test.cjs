/* Run: node tests/plural-runtime.test.cjs  (or node --test tests/plural-runtime.test.cjs) */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../lightning/ui/static/lightning-t.js'), 'utf8');
function boot(table, counted) {
  const window = { LIGHTNING_UI: table, LIGHTNING_COUNTED: counted };
  const context = vm.createContext({ window, document: { documentElement: { lang: 'ar' } } });
  vm.runInContext(source, context);
  return window.lightningT;
}
const COUNTED = { 'معاملة': ['معاملة واحدة', 'معاملتين', 'معاملات'], 'فئة': ['فئة واحدة', 'فئتين', 'فئات'] };
const TABLE = {
  'Delete {count} transactions?': 'تحذف {count} معاملات؟',
  'Combined for {count} categories.': 'لـ {count} فئات.',
  'Across {n} categories': 'في {n} فئات',
};
test('Delete {count} transactions? agrees in Arabic for 1, 2, 5 and 11', () => {
  const t = boot(TABLE, COUNTED);
  const ask = count => t('Delete {count} transactions?', { count });
  assert.equal(ask(1), 'تحذف معاملة واحدة؟');
  assert.equal(ask(2), 'تحذف معاملتين؟');
  assert.equal(ask(5), `تحذف ${(5).toLocaleString('ar')} معاملات؟`);
  assert.equal(ask(11), `تحذف ${(11).toLocaleString('ar')} معاملة؟`);
});
test('a count read from the English text agrees too, and a key without a counted noun is untouched', () => {
  const t = boot(TABLE, COUNTED);
  assert.equal(t('Across 2 categories'), 'في فئتين');
  assert.equal(t('Across 4 categories'), 'في 4 فئات');
  assert.equal(t('Combined for {count} categories.', { count: 1 }), 'لـ فئة واحدة.');
  assert.equal(t('Not in the table {n}', { n: 3 }), 'Not in the table 3');
});
test('without the table the text is only filled in', () => {
  assert.equal(boot(TABLE, undefined)('Delete {count} transactions?', { count: 1 }), `تحذف ${(1).toLocaleString('ar')} معاملات؟`);
});
