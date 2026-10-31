'use strict';
/* IDE-003: actual browser -> local registry -> migrated project -> editor UI. */
const assert = require('node:assert/strict');
const {e2e,t,waitStatus,editorState} = require('./harness.cjs');

e2e('the built-in starter gallery loads real vetted projects and labels in-game status',async ({page})=>{
  await page.waitForFunction(()=>document.querySelectorAll('#ideTemplate option').length===3
    && !document.querySelector('#ideUseStarter').disabled);
  assert.deepEqual(await page.$$eval('#ideTemplate option',items=>items.map(i=>i.value)),['ruby','voxel','workshop']);
  assert.match(await page.textContent('#ideStarterDescription'),/not tested in the game/i);
  await page.selectOption('#ideTemplate','voxel');
  assert.match(await page.textContent('#ideStarterDescription'),/structure × 3/);
  page.once('dialog',dialog=>dialog.accept());
  await page.click('#ideUseStarter');
  await waitStatus(page,await t(page,'ideStarterLoaded'));
  const voxel=await editorState(page);
  assert.equal(voxel.metadata.id,'voxel_showcase');
  assert.equal(voxel.structures.length,3);
  assert.equal(await page.textContent('#countStructure'),'3');

  await page.click('#lang-ru');
  assert.match(await page.textContent('#ideStarterDescription'),/в игре не испытано/);
  await page.selectOption('#ideTemplate','workshop');
  page.once('dialog',dialog=>dialog.dismiss());
  await page.click('#ideUseStarter');
  assert.equal((await editorState(page)).metadata.id,'voxel_showcase','cancel keeps original');
  page.once('dialog',dialog=>dialog.accept());
  await page.click('#ideUseStarter');
  await waitStatus(page,await t(page,'ideStarterLoaded'));
  assert.equal((await editorState(page)).metadata.id,'workshop_showcase');
  assert.equal((await editorState(page)).structures.length,6);
});
