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

const view = {
  current_phase: 'F3',
  phases: [
    { id: 'F1', name: 'Project Core', name_ru: 'Ядро проекта', summary: 'Done things', summary_ru: 'Готово', status: 'done' },
    { id: 'F3', name: 'Visual <Scripting>', name_ru: 'Визуальное', summary: 's', summary_ru: 'с', status: 'in_progress' },
    { id: 'F4', name: 'Gameplay', name_ru: 'Геймплей', summary: 's', summary_ru: 'с', status: 'planned' },
    { id: 'F0', name: 'Foundation', name_ru: 'Фундамент', summary: 's', summary_ru: 'с', status: 'partial' },
  ],
  active_milestone: { id: 'HS-008', status: 'in_progress', title: 'Registry', title_ru: 'Реестр' },
  next_milestones: [{ id: 'HS-009', status: 'planned', title: 'Next', title_ru: 'Дальше' }],
  verification: ['verified', 'blocked', 'planned', 'partial'].map(status => ({ level: status, name: status, name_ru: status, status, detail: 'd', detail_ru: 'д' })),
  build: { label: 'Horizon d2186eb', content_api: '0.2', revision: 'd2186eb9', groups: {
    'official-static': [{ capability: 'content.block' }],
    'engine-only': [{ capability: 'native.hook_mod', note: 'trusted <native>' }],
    unsupported: [{ capability: 'entity.custom', note: 'none' }],
  } },
};

test('journey markup is localized, escaped and keeps the plan apart from the build', () => {
  for (const lang of ['en', 'ru']) {
    const html = workbench.journeyMarkup(view, lang, translator(lang));
    const [plan, build] = html.split('<section id="journeyBuild"');
    assert.ok(plan.includes(lang === 'ru' ? 'Визуальное' : 'Visual &lt;Scripting&gt;'));
    assert.ok(!html.includes('<Scripting>') && !html.includes('<native>'), 'data is escaped');
    assert.ok(build.includes('content.block') && build.includes('entity.custom'));
    assert.ok(!plan.includes('content.block'), 'capabilities are only in the build section');
    assert.match(plan, /<li class="current">.*F3/);
  }
});

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
