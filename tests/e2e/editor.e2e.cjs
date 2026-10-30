'use strict';
/* HS-007: editor workflows driven in a real browser against a real local Studio server. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  ROOT, OFFICIAL_RUBY_SHA256, e2e, t, editorState, workspaceKey, waitWorkspace, waitStatus, download, readZip,
  waitDisk, objectIds, sha256,
} = require('./harness.cjs');

async function showSidebar(page) {
  if (!(await page.isVisible('#demo'))) {
    await page.click('#toggleExplorer');
    await page.waitForSelector('#demo', { state: 'visible' });
  }
}

async function loadDemo(page) {
  await showSidebar(page);
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
}

async function addEntry(page, tab, id, name) {
  await page.click(`#${tab}Tab`);
  await page.fill('#entryId', id);
  await page.fill('#entryName', name);
  await page.click('#addObject');
  await waitStatus(page, await t(page, 'savedEntry'));
}

async function setModId(page, id) {
  await page.fill('#modId', id);
  await page.dispatchEvent('#modId', 'change');
}

e2e('boots in English with no errors and loads the demo project', async ({ page }) => {
  assert.equal(await page.evaluate(() => document.documentElement.lang), 'en');
  assert.equal(await page.textContent('#saveProject'), 'Save project');
  await loadDemo(page);
  const state = await editorState(page);
  assert.equal(state.metadata.id, 'ruby_demo');
  assert.deepEqual([state.blocks.length, state.items.length, state.recipes.length], [1, 1, 2]);
  assert.ok([...state.blocks, ...state.items, ...state.recipes].every(e => /^[0-9a-f-]{36}$/.test(e.uid)));
});

e2e('renaming keeps the uid, follows recipe references and saves studio.project/1', async ({ page }) => {
  await loadDemo(page);
  const before = await editorState(page);
  const rubyUid = before.items[0].uid;
  await page.click('#itemTab');
  await page.click('[data-edit="0"]');
  await page.fill('#entryId', 'gem');
  await page.fill('#entryName', 'Gem');
  await page.click('#addObject');
  await waitStatus(page, await t(page, 'savedEntry'));
  const after = await editorState(page);
  assert.equal(after.items[0].id, 'gem');
  assert.equal(after.items[0].uid, rubyUid);
  assert.deepEqual(after.recipes[0].grid, Array(9).fill('@gem'));
  assert.equal(after.recipes[1].result, '@gem');

  await addEntry(page, 'block', 'opal_block', 'Opal Block');
  const saved = JSON.parse((await download(page, '#saveProject')).toString('utf8'));
  assert.equal(saved.schema, 'studio.project/1');
  const gem = saved.objects.find(o => o.id === 'gem');
  assert.equal(gem.uid, rubyUid);
  const recipe = saved.objects.find(o => o.kind === 'recipe' && o.id === 'ruby_block');
  assert.ok(recipe.props.grid.every(cell => cell.ref === rubyUid));
  const opal = saved.objects.find(o => o.id === 'opal_block');
  assert.match(opal.uid, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-/);
});

e2e('undo and redo work from buttons and keyboard shortcuts', async ({ page }) => {
  await loadDemo(page);
  await addEntry(page, 'item', 'shard', 'Shard');
  const count = async () => (await editorState(page)).items.length;
  assert.equal(await count(), 2);
  assert.equal(await page.isDisabled('#redoEdit'), true);
  await page.click('#undoEdit');
  assert.equal(await count(), 1);
  assert.equal(await page.isDisabled('#redoEdit'), false);
  await page.click('#redoEdit');
  assert.equal(await count(), 2);
  await page.click('#entries');  // focus outside text fields: shortcuts are ignored while typing
  await page.keyboard.press('Control+z');
  assert.equal(await count(), 1);
  await page.keyboard.press('Control+Shift+z');
  assert.equal(await count(), 2);
  await page.focus('#entryName');
  await page.keyboard.press('Control+z');
  assert.equal(await count(), 2, 'Ctrl+Z inside a text field must not undo project edits');
});

e2e('autosave writes a recoverable disk workspace that a fresh browser can restore', async ({ page, studio, another }) => {
  await loadDemo(page);
  await addEntry(page, 'item', 'shard', 'Shard');
  const disk = await waitDisk(studio, 'ruby_demo', doc => objectIds(doc).includes('shard'));
  assert.equal(disk.schema, 'studio.project/1');
  await waitWorkspace(page, 'workspaceSaved');

  // A new browser profile has no local copy: the disk snapshot is the only source.
  const fresh = await another();
  await setModId(fresh.page, 'ruby_demo');
  await waitWorkspace(fresh.page, 'workspaceRecoverable');
  assert.equal(await fresh.page.isVisible('#restoreWorkspace'), true);
  await fresh.page.click('#restoreWorkspace');
  await waitWorkspace(fresh.page, 'workspaceRecovered');
  const restored = await editorState(fresh.page);
  assert.deepEqual(restored.items.map(i => i.id), ['ruby', 'shard']);
  assert.equal(restored.items[1].uid, (await editorState(page)).items[1].uid);
});

e2e('a stale tab gets a revision conflict instead of silently overwriting', async ({ page, studio, another }) => {
  await loadDemo(page);
  await waitDisk(studio, 'ruby_demo', doc => objectIds(doc).includes('ruby'));
  await waitWorkspace(page, 'workspaceSaved');

  const other = await another();
  await setModId(other.page, 'ruby_demo');
  await waitWorkspace(other.page, 'workspaceRecoverable');
  await other.page.click('#restoreWorkspace');
  await waitWorkspace(other.page, 'workspaceRecovered');
  await addEntry(other.page, 'item', 'from_other_tab', 'Other');
  await waitDisk(studio, 'ruby_demo', doc => objectIds(doc).includes('from_other_tab'));

  await addEntry(page, 'item', 'from_stale_tab', 'Stale');
  await waitWorkspace(page, 'workspaceRecoverable');
  assert.equal(await page.isVisible('#keepEditor'), true);
  let disk = JSON.parse(fs.readFileSync(studio.workspaceFile('ruby_demo'), 'utf8'));
  assert.ok(objectIds(disk).includes('from_other_tab'));
  assert.ok(!objectIds(disk).includes('from_stale_tab'), 'the stale tab must not overwrite newer work');

  await page.click('#keepEditor');  // an explicit choice to overwrite
  disk = await waitDisk(studio, 'ruby_demo', doc => objectIds(doc).includes('from_stale_tab'));
  assert.ok(!objectIds(disk).includes('from_other_tab'));
  await waitWorkspace(page, 'workspaceSaved');
});

e2e('opens a legacy project with a migration notice and rejects a corrupt file', async ({ page }) => {
  await page.setInputFiles('#projectFile', path.join(ROOT, 'examples', 'workshop_showcase.hstudio.json'));
  await waitStatus(page, await t(page, 'projectMigrated', { schema: 4 }));
  assert.equal(await page.inputValue('#modId'), 'workshop_showcase');
  const state = await editorState(page);
  assert.equal(state.structures.length, 6);
  assert.deepEqual(state.recipes.find(r => r.id === 'beacon_craft').grid, Array(9).fill('@shard'));

  const corrupt = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'hs-e2e-')), 'broken.hstudio.json');
  fs.writeFileSync(corrupt, '{"format": "horizon-studio", "schema": 3, "metadata": ');
  await page.setInputFiles('#projectFile', corrupt);
  await page.waitForFunction(() => document.querySelector('#status').classList.contains('error'));
  assert.equal(await page.inputValue('#modId'), 'workshop_showcase', 'a failed open must keep the current project');
});

e2e('switches to Russian, translates workspace status and remembers the choice', async ({ page }) => {
  await loadDemo(page);
  await page.click('#lang-ru');
  assert.equal(await page.evaluate(() => document.documentElement.lang), 'ru');
  assert.equal(await page.textContent('#saveProject'), await t(page, 'saveProject'));
  assert.notEqual(await page.textContent('#saveProject'), 'Save project');
  const key = await workspaceKey(page);
  assert.equal(await page.textContent('#workspaceSaveStatus'), await t(page, key));
  await page.reload();
  await page.waitForFunction(() => window.HorizonI18n);
  assert.equal(await page.evaluate(() => document.documentElement.lang), 'ru');
});

e2e('Source Workbench validates, applies, undoes and exports JSON overrides', async ({ page }) => {
  await loadDemo(page);
  await page.click('#openWorkbench');
  const target = 'assets/ruby_demo/models/item/ruby.json';
  const labels = await page.$$eval('#sourceFiles button', buttons => buttons.map(b => b.textContent));
  assert.equal(new Set(labels).size, labels.length, `file labels must be unique: ${labels}`);
  assert.ok(labels.includes('models/item/ruby.json'));
  await page.click(`#sourceFiles button[title="${target}"]`);
  await page.fill('#sourceCode', '{"parent": ');
  await page.click('#applySource');
  await page.waitForFunction(() => document.querySelector('#sourceStatus').classList.contains('error'));
  assert.deepEqual((await editorState(page)).source_overrides, {});

  const override = { parent: 'minecraft:item/handheld', textures: { layer0: 'minecraft:item/emerald' } };
  await page.fill('#sourceCode', JSON.stringify(override));
  await page.click('#applySource');
  await page.waitForFunction(p => JSON.parse(localStorage.getItem('horizonStudio_v02')).source_overrides[p], target);
  await page.click('#closeWorkbench');
  const files = readZip(await download(page, '#exportHmod'));
  assert.deepEqual(JSON.parse(files[target].toString('utf8')), override);

  await page.click('#undoEdit');
  assert.deepEqual((await editorState(page)).source_overrides, {});
});

e2e('the unedited demo exports exactly the officially checked .hmod', async ({ page }) => {
  await loadDemo(page);
  const hmod = await download(page, '#exportHmod');
  assert.equal(sha256(hmod), OFFICIAL_RUBY_SHA256);
  assert.ok(readZip(hmod)['horizon-mod.toml'].toString('utf8').includes('id = "ruby_demo"'));
});

e2e('invalid project IDs pause disk autosave and make export fail visibly', async ({ page }) => {
  await loadDemo(page);
  await setModId(page, 'Not A Valid Id');
  await waitWorkspace(page, 'workspaceInvalidId');
  let downloaded = false;
  page.on('download', () => { downloaded = true; });
  await page.click('#exportHmod');
  await page.waitForFunction(() => document.querySelector('#status').classList.contains('error'));
  assert.match(await page.textContent('#status'), /Mod ID/);
  assert.equal(downloaded, false);
});

for (const viewport of [{ width: 1280, height: 720 }, { width: 1024, height: 640 }, { width: 390, height: 844 }]) {
  e2e(`project controls and entries stay reachable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const compact = viewport.width <= 1100;
    assert.equal(await page.isVisible('#saveProject'), !compact, 'the sidebar is a drawer only on narrow windows');
    assert.equal(await page.getAttribute('#toggleExplorer', 'aria-expanded'), String(!compact));
    await loadDemo(page);
    if (compact) {
      assert.equal(await page.getAttribute('#toggleExplorer', 'aria-expanded'), 'true');
      for (const control of ['#saveProject', '#undoEdit', '#exportHmod', '#modId']) {
        assert.equal(await page.isVisible(control), true, `${control} must be reachable in the drawer`);
      }
      await page.keyboard.press('Escape');
      await page.waitForSelector('#saveProject', { state: 'hidden' });
      assert.equal(await page.getAttribute('#toggleExplorer', 'aria-expanded'), 'false');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'toggleExplorer');
    }
    await page.click('#itemTab');
    const button = page.locator('[data-edit="0"]');
    await button.scrollIntoViewIfNeeded();
    const box = await button.boundingBox();
    const hit = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.dataset.edit,
      [box.x + box.width / 2, box.y + box.height / 2]);
    assert.equal(hit, '0', 'the Configure button must not be covered');
    await button.click();
    assert.equal(await page.inputValue('#entryId'), 'ruby');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(overflow <= 0, `page scrolls horizontally by ${overflow}px`);
  }, { viewport });
}
