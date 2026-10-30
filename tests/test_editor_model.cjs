'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const model = require('../editor_model.js');
const render = require('../editor_render.js');

const demo = () => ({
  blocks: [{ id: 'ruby_block', uid: 'b-1', name: 'Block of Ruby', template: 'minecraft:iron_block', light: 3 }],
  items: [{ id: 'ruby', uid: 'i-1', name: 'Ruby', template: 'minecraft:diamond', rarity: 'rare' }],
  recipes: [
    { id: 'ruby_block', uid: 'r-1', type: 'shaped', result: '@ruby_block', count: 1, grid: Array(9).fill('@ruby') },
    { id: 'from_block', uid: 'r-2', type: 'shapeless', result: '@ruby', count: 9, grid: ['@ruby_block', ...Array(8).fill('')] },
  ],
  structures: [], source_overrides: {}, carry: { extensions: { 'plugin.x': { keep: true } } },
});
const meta = { id: 'ruby_demo', name: 'Ruby Demo', version: '0.1.0', author: 'A', description: '' };
const t = key => ({ configure: 'Configure', remove: 'Remove', craftingTable: 'Crafting Table', light: 'Light',
  rarity: 'Rarity', textureAlt: 'Texture' }[key] || key);

test('generator payload namespaces local references and keeps vanilla ones', () => {
  const state = demo();
  state.recipes[1].grid[1] = 'minecraft:stick';
  const payload = model.generatorPayload(meta, state);
  assert.equal(payload.id, 'ruby_demo');
  assert.deepEqual(payload.recipes[0].grid, Array(9).fill('ruby_demo:ruby'));
  assert.equal(payload.recipes[1].result, 'ruby_demo:ruby');
  assert.equal(payload.recipes[1].grid[1], 'minecraft:stick');
  assert.equal(payload.recipes[1].grid[2], '');
  assert.equal(state.recipes[0].grid[0], '@ruby', 'the editor state itself is not rewritten');
});

test('editor snapshot keeps uids and opaque plugin data', () => {
  const snapshot = model.editorSnapshot(meta, demo());
  assert.equal(snapshot.items[0].uid, 'i-1');
  assert.deepEqual(snapshot.carry, { extensions: { 'plugin.x': { keep: true } } });
  assert.deepEqual(model.editorSnapshot(meta, { ...demo(), carry: undefined, source_overrides: undefined }).carry, {});
});

test('project shape problems map to translated messages', () => {
  const ok = { metadata: meta, ...demo() };
  assert.equal(model.projectProblem(ok), null);
  assert.equal(model.projectProblem(null), 'badProject');
  assert.equal(model.projectProblem({ ...ok, items: {} }), 'badProject');
  assert.equal(model.projectProblem({ ...ok, structures: 'x' }), 'badProject');
  assert.equal(model.projectProblem({ ...ok, items: Array(33).fill({ id: 'a' }) }), 'projectLimit');
  assert.equal(model.projectProblem({ ...ok, items: [{ id: 'Bad Id' }] }), 'badId');
});

test('missing uids are assigned and existing ones are never changed', () => {
  const state = demo();
  state.items.push({ id: 'gem', name: 'Gem' });
  let n = 0;
  model.assignMissingUids(state, () => `new-${++n}`);
  assert.equal(state.items[0].uid, 'i-1');
  assert.equal(state.items[1].uid, 'new-1');
  assert.equal(n, 1);
});

test('renaming rewrites recipe references; usage lookup finds them', () => {
  const state = demo();
  assert.equal(model.recipesUsing(state.recipes, 'ruby').length, 2);
  model.renameReferences(state.recipes, 'ruby', 'gem');
  assert.deepEqual(state.recipes[0].grid, Array(9).fill('@gem'));
  assert.equal(state.recipes[1].result, '@gem');
  assert.equal(model.recipesUsing(state.recipes, 'ruby').length, 0);
});

test('search covers names, translations, templates and recipe results', () => {
  const state = demo();
  const entries = [...state.blocks, ...state.items];
  assert.ok(model.matchesSearch(state.items[0], 'DIAM', 'item', entries));
  assert.ok(!model.matchesSearch(state.items[0], 'emerald', 'item', entries));
  assert.ok(model.matchesSearch(state.recipes[1], 'ruby', 'recipe', entries));
  assert.ok(model.matchesSearch(state.recipes[1], '  ', 'recipe', entries));
});

test('cards escape user text and only embed PNG data textures', () => {
  const state = demo();
  state.items[0].name = '<img src=x onerror=alert(1)>';
  state.items[0].texture = 'javascript:alert(1)';
  const ctx = { entries: [...state.blocks, ...state.items], packTextures: {}, t };
  const card = render.entryCardMarkup(state.items[0], 0, 'item', ctx);
  assert.ok(!card.includes('<img src=x'));
  assert.ok(card.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!card.includes('javascript:'));
  assert.match(card, /data-edit="0"/);
  const recipe = render.recipeCardMarkup(state.recipes[0], 3, ctx);
  assert.equal((recipe.match(/class="recipe-slot"/g) || []).length, 10);
  assert.match(recipe, /data-remove="3"/);
  assert.equal(render.spriteKey('@ruby', ctx.entries), 'diamond');
  assert.equal(render.spriteKey('minecraft:unknown_thing', ctx.entries), 'generic');
});
