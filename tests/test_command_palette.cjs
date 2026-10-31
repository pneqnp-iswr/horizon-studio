'use strict';
/* HS-033: command palette ranking (pure; the DOM part is covered by tests/e2e/palette.e2e.cjs). */
const assert = require('node:assert/strict');
const test = require('node:test');
const { score, rank } = require('../command_palette.js');

const commands = ['Open project', 'Save project', 'Undo', 'Redo', 'VFX Studio', 'Source & 3D', 'Export .hmod',
  'Download source ZIP', 'Development journey', 'Блоки', 'Экспорт .hmod'].map((label, i) => ({ id: 'c' + i, label, keywords: [] }));
const labels = list => list.map(c => c.label);

test('an empty query lists every command in order', () => {
  assert.deepEqual(labels(rank(commands, '')), labels(commands));
});

test('prefix beats word start beats substring beats scattered letters', () => {
  assert.ok(score('Save project', 'sav') > score('Open project', 'proj'));
  assert.ok(score('Open project', 'proj') > score('Development journey', 'opm'));
  assert.equal(score('Undo', 'xyz'), 0);
  assert.equal(labels(rank(commands, 'export'))[0], 'Export .hmod');
  assert.equal(labels(rank(commands, 'vfx'))[0], 'VFX Studio');
  assert.equal(labels(rank(commands, 'dj'))[0], 'Development journey');
});

test('matching ignores case and accents and works in Russian', () => {
  assert.equal(labels(rank(commands, 'ЭКСП'))[0], 'Экспорт .hmod');
  assert.equal(labels(rank(commands, 'бло'))[0], 'Блоки');
  assert.ok(score('Café', 'cafe') > 0);
});

test('keywords find a command whose label does not match', () => {
  const list = [{ id: 'openVfx', label: 'Студия VFX', keywords: ['particles', 'effects'] }, { id: 'x', label: 'Other', keywords: [] }];
  assert.equal(rank(list, 'particles')[0].id, 'openVfx');
  assert.deepEqual(rank(list, 'zzz'), []);
});
