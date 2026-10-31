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

test('profile differences and the target selector (HS-008)', () => {
  const t = translator('en');
  const base = { revision: 'a'.repeat(40), label: 'Old', capabilities: { 'content.block': { status: 'official-static' }, 'native.particles': { status: 'unsupported' } } };
  const next = { revision: 'b'.repeat(40), label: 'New', label_ru: 'Новый', capabilities: { 'content.block': { status: 'official-static' },
    'native.particles': { status: 'engine-only', note: 'vanilla only', note_ru: 'только ванильные' }, 'shader.pack': { status: 'engine-only' } } };
  const diff = workbench.profileDiff(base, next);
  assert.deepEqual(diff.map(d => [d.capability, d.from, d.to]), [['native.particles', 'unsupported', 'engine-only'], ['shader.pack', 'absent', 'engine-only']]);
  assert.match(workbench.diffMarkup(diff, 'ru', translator('ru')), /только ванильные/);
  const data = { default: base.revision, profiles: [base, next] };
  const options = workbench.targetOptionsMarkup(data, { engine: 'horizon', revision: next.revision }, 'ru', translator('ru'));
  assert.match(options, new RegExp(`value="${next.revision}" selected>Новый`));
  const unknown = workbench.targetOptionsMarkup(data, { engine: 'horizon', revision: 'c'.repeat(40) }, 'en', t);
  assert.match(unknown, /Unknown revision ccccccc/);
  assert.match(workbench.targetOptionsMarkup(data, null, 'en', t), /value="" selected>Studio default — Old/);
});
