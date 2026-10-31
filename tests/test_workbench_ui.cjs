'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const workbench = require('../workbench_ui.js');

// The real catalogs, so every key the workbench builds dynamically must exist in EN and RU.
const source = fs.readFileSync(path.join(__dirname, '..', 'i18n.js'), 'utf8');
const catalog = JSON.parse(source.match(/const catalog = (\{.*?\});\n {2}let locale/s)[1]);
const translator = lang => (key, values = {}) => {
  const template = catalog[lang][key];
  assert.equal(typeof template, 'string', `missing ${lang} translation for ${key}`);
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in values ? String(values[name]) : match));
};

test('the engine card marks missing capabilities and the export gate explains them', () => {
  const t = translator('en');
  const ok = { requirements: { 'content.recipe': ['recipe a'], 'content.block': ['block b', 'block c'] }, diagnostics: [] };
  const html = workbench.capabilityMarkup(ok, t);
  assert.ok(html.indexOf('content.block') < html.indexOf('content.recipe'), 'sorted');
  assert.equal((html.match(/cap-ok/g) || []).length, 2);
  assert.equal(workbench.exportBlockReason(ok, t), '');
  const missing = { requirements: { 'entity.custom': ['entity x'] },
    diagnostics: [{ level: 'error', capability: 'entity.custom', message: 'entity.custom (entity x): no registry' }] };
  assert.match(workbench.capabilityMarkup(missing, t), /cap-missing/);
  assert.match(workbench.exportBlockReason(missing, t), /^Export blocked.*entity\.custom \(entity x\): no registry$/);
  assert.equal(workbench.capabilityMarkup({ requirements: {}, diagnostics: [] }, t).includes(t('capNone')), true);
});

test('every empty state exists in both languages and only the demo kinds offer the demo', () => {
  for (const lang of ['en', 'ru']) {
    for (const kind of workbench.KINDS) {
      const html = workbench.emptyStateMarkup(kind, translator(lang));
      assert.equal(html.includes('id="emptyDemo"'), kind !== 'structure');
    }
  }
});
