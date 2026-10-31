'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const explorer = require('../roadmap_explorer.js');

const source = fs.readFileSync(path.join(__dirname, '..', 'i18n.js'), 'utf8');
const catalog = JSON.parse(source.match(/const catalog = (\{.*?\});\n {2}let locale/s)[1]);
const translator = lang => (key, values = {}) => {
  const template = catalog[lang][key];
  assert.equal(typeof template, 'string', `missing ${lang} translation for ${key}`);
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in values ? String(values[name]) : match));
};

const milestone = (id, extra = {}) => ({
  id, track: 'studio', phase: 'F1', status: 'planned', depends_on: [], dependents: [], title: `Title ${id}`, title_ru: `Заголовок ${id}`,
  summary: `Summary ${id}`, summary_ru: `Описание ${id}`, deliverable: 'D', deliverable_ru: 'Р', acceptance: ['works'],
  requirements: [], validation_target: 'unit', design: 'https://github.com/x/y/blob/master/doc.md', evidence: [], ...extra,
});
const view = {
  updated: '2026-10-31', current_phase: 'F1', active_milestone: 'HS-002',
  phases: [{ id: 'F0', name: 'Zero', name_ru: 'Ноль', summary: 's', summary_ru: 'с', icon: 'forge', status: 'done' },
    { id: 'F1', name: 'One <b>', name_ru: 'Один', summary: 's', summary_ru: 'с', icon: 'core', status: 'in_progress' }],
  milestones: [
    milestone('HS-001', { phase: 'F0', status: 'done', dependents: ['HS-002'],
      evidence: [{ level: 'unit', ref: 'tests <x>', url: 'https://github.com/x/y/pull/1' }] }),
    milestone('HS-002', { status: 'in_progress', depends_on: ['HS-001'], summary: 'Crystal sparks', summary_ru: 'Кристальные искры',
      requirements: [{ id: 'native.particles', state: 'engine' }, { id: 'render.custom_particles', state: 'missing' }] }),
    milestone('HS-003', { status: 'blocked', blocker: 'needs a game' }),
    milestone('PC-001', { track: 'pixelchat', phase: 'F1', status: 'partial', missing: 'build', issue: 'https://github.com/x/y/issues/11' }),
  ],
  tracks: [{ id: 'studio' }, { id: 'pixelchat' }],
  showcases: [{ id: 'SC-001', name: 'Crystal Titan', name_ru: 'Кристальный Титан', summary: 's', summary_ru: 'с',
    sequence: ['a'], sequence_ru: ['а'], milestones: ['HS-002'], levels: [{ level: 1, name: 'Editable', name_ru: 'Правка', status: 'planned' }] }],
  build: { label: 'Horizon d2186eb', content_api: '0.2', studio_version: '0.7.0', groups: { 'official-static': [{ capability: 'content.block' }], 'engine-only': [], unsupported: [] } },
};

test('filters combine phase, search in both languages, status and track', () => {
  const ids = filter => explorer.filterMilestones(view, filter).map(m => m.id);
  assert.deepEqual(ids({}), ['HS-001', 'HS-002', 'HS-003', 'PC-001']);
  assert.deepEqual(ids({ phase: 'F0' }), ['HS-001']);
  assert.deepEqual(ids({ query: 'crystal' }), ['HS-002']);
  assert.deepEqual(ids({ query: 'кристальные' }), ['HS-002']);
  assert.deepEqual(ids({ statuses: ['blocked', 'partial'] }), ['HS-003', 'PC-001']);
  assert.deepEqual(ids({ track: 'pixelchat' }), ['PC-001']);
  assert.deepEqual(ids({ phase: 'F0', query: 'crystal' }), []);
});

test('phase progress counts only the studio track', () => {
  assert.deepEqual(explorer.phaseProgress(view, view.phases[1]), { done: 0, total: 2 });
});

for (const lang of ['en', 'ru']) {
  test(`details show dependencies, dependents, engine states and evidence (${lang})`, () => {
    const t = translator(lang);
    const html = explorer.milestoneDetailMarkup(view, 'HS-002', lang, t);
    assert.match(html, /data-kind="depends">.*data-milestone="HS-001"/s);
    assert.match(html, new RegExp(t('jrActive')));
    assert.ok(html.includes(t('req_engine')) && html.includes(t('req_missing')));
    assert.ok(html.includes(lang === 'ru' ? 'Кристальные искры' : 'Crystal sparks'));
    const done = explorer.milestoneDetailMarkup(view, 'HS-001', lang, t);
    assert.ok(done.includes('tests &lt;x&gt;') && done.includes('href="https://github.com/x/y/pull/1"'));
    assert.match(done, /data-kind="dependents">.*data-milestone="HS-002"/s);
    assert.ok(explorer.milestoneDetailMarkup(view, 'HS-003', lang, t).includes('needs a game'));
    assert.ok(explorer.milestoneDetailMarkup(view, 'PC-001', lang, t).includes('/issues/11'));
    const strip = explorer.phaseStripMarkup(view, 'F1', lang, t);
    assert.ok(strip.includes('One &lt;b&gt;') || lang === 'ru');
    assert.ok(strip.includes('/assets/roadmap/icons/core.svg') && strip.includes('aria-pressed="true"'));
    assert.ok(explorer.showcaseMarkup(view, lang, t).includes(lang === 'ru' ? 'Кристальный Титан' : 'Crystal Titan'));
    const build = explorer.buildMarkup(view, lang, t);
    assert.ok(build.includes('content.block') && !build.includes('HS-00'), 'the build panel lists capabilities, never roadmap items');
  });
}

test('an empty filter result says so', () => {
  const t = translator('en');
  assert.ok(explorer.milestoneListMarkup(view, [], null, 'en', t).includes(t('jrNoResults')));
});
