'use strict';
/* HS-020/HS-022: the AI Creator panel in a real browser against the real core, with the
 * deterministic fixture provider (no live model is connected in this build). A person's edit and
 * an AI proposal on the same item share one history: preview, apply, undo, redo, reload. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { e2e, t, editorState, waitWorkspace, waitStatus, waitDisk, download, readZip, objectIds, sha256 } = require('./harness.cjs');

async function loadDemo(page) {
  if (!(await page.isVisible('#demo'))) await page.click('#toggleExplorer');
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
  await waitWorkspace(page, 'workspaceSaved');
}

const disk = (studio, check) => waitDisk(studio, 'ruby_demo', check);
const ruby = doc => doc.objects.find(o => o.kind === 'item' && o.id === 'ruby');
const stored = page => page.evaluate(() => JSON.parse(localStorage.getItem('horizonStudio_v02')));
const waitState = (page, fn, arg) => page.waitForFunction(fn, arg);

async function propose(page, intent, fill) {
  await page.selectOption('#aiIntent', intent);
  await fill();
  await page.click('#aiPropose');
  await waitStatus(page, await t(page, 'aiProposed'));
}

e2e('a person and the AI edit the same item through one history: preview, apply, undo, redo, reload', async ({ page, studio }) => {
  await loadDemo(page);
  // 1. The person renames the ruby.
  await page.click('#itemTab');
  await page.click('[data-edit="0"]');
  await page.fill('#entryName', 'Polished Ruby');
  await page.click('#addObject');
  await disk(studio, doc => ruby(doc).props.name === 'Polished Ruby');

  // 2. The AI proposes a change to the same item; it is labelled as simulated and changes nothing yet.
  await page.click('#openAi');
  await page.waitForSelector('#aiDialog:not([hidden])');
  assert.equal(await page.textContent('#aiProviderBadge'), await t(page, 'aiSimulatedBadge'));
  assert.match(await page.textContent('#aiContextView'), /"id": "ruby_demo"/, 'the person can see what the provider receives');
  await propose(page, 'update', async () => {
    await page.selectOption('#aiAsset', 'item:ruby');
    await page.selectOption('#aiField', 'rarity');
    await page.fill('#aiValue', 'epic');
  });
  // 3. The diff names the item and the field, before and after.
  const diff = await page.$$eval('#aiDiff .ai-asset tbody tr', rows => rows.map(r => [...r.children].map(c => c.textContent)));
  assert.deepEqual(diff, [['rarity', 'rare', 'epic']]);
  assert.match(await page.textContent('#aiDiff'), /item:ruby/);
  assert.equal((await stored(page)).items[0].rarity, 'rare', 'a proposal changes nothing');

  // 4. Apply: one step, the person's name change kept.
  await page.click('#aiApply');
  await waitState(page, () => JSON.parse(localStorage.getItem('horizonStudio_v02')).items[0].rarity === 'epic');
  let doc = await disk(studio, d => ruby(d).props.rarity === 'epic');
  assert.equal(ruby(doc).props.name, 'Polished Ruby');
  const history = await page.$$eval('#aiHistory li', items => items.map(li => li.textContent));
  assert.match(history[0], /AI.*change item ruby.*approved by you/);
  assert.match(history[1], /You/);

  // 5. Undo takes back the AI step only.
  await page.click('#aiUndo');
  await waitState(page, () => JSON.parse(localStorage.getItem('horizonStudio_v02')).items[0].rarity === 'rare');
  doc = await disk(studio, d => ruby(d).props.rarity === 'rare');
  assert.equal(ruby(doc).props.name, 'Polished Ruby');
  // 6. Redo reapplies it.
  await page.click('#closeAi');
  await page.click('#redoEdit');
  await disk(studio, d => ruby(d).props.rarity === 'epic');
  // The core writes the disk before it answers; reloading before the editor has the answer would (rightly)
  // offer Restore disk instead, so wait until the editor holds the redone state too.
  await waitState(page, () => JSON.parse(localStorage.getItem('horizonStudio_v02')).items[0].rarity === 'epic');

  // 7-8. The history is the core's: after a reload the AI step is still there and can be undone.
  await page.reload();
  await waitWorkspace(page, 'workspaceSaved');
  await page.click('#openAi');
  await page.waitForFunction(() => /approved by you/.test(document.querySelector('#aiHistory').textContent));
  await page.click('#closeAi');
  await page.click('#undoEdit');
  await disk(studio, d => ruby(d).props.rarity === 'rare' && ruby(d).props.name === 'Polished Ruby');
});

e2e('a stale proposal is refused, a rejected or cancelled one changes nothing', async ({ page, studio }) => {
  await loadDemo(page);
  await page.click('#openAi');
  await propose(page, 'update', async () => {
    await page.selectOption('#aiAsset', 'item:ruby');
    await page.selectOption('#aiField', 'name');
    await page.fill('#aiValue', 'From the AI');
  });
  // The person edits the project before deciding: the proposal no longer matches it.
  await page.click('#closeAi');
  await page.fill('#modName', 'Changed meanwhile');
  await page.dispatchEvent('#modName', 'change');
  await disk(studio, d => d.project.name === 'Changed meanwhile');
  await page.click('#openAi');
  await page.click('#aiApply');
  await page.waitForSelector('#aiError:not([hidden])');
  assert.equal(await page.textContent('#aiError'), await t(page, 'aiStale'));
  assert.equal((await stored(page)).items[0].name, 'Ruby');
  assert.equal(await page.isDisabled('#aiApply'), true);

  await propose(page, 'material_set', async () => page.fill('#aiMaterial', 'topaz'));
  await page.click('#aiReject');
  await waitStatus(page, await t(page, 'aiRejected'));
  let doc = JSON.parse(fs.readFileSync(studio.workspaceFile('ruby_demo'), 'utf8'));
  assert.ok(!objectIds(doc).includes('topaz'), 'a rejected proposal changes nothing');

  // Cancelling while the provider is still answering: the late answer is rejected, not shown.
  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/ai/propose', async route => { await held; await route.continue(); });
  await page.selectOption('#aiIntent', 'material_set');
  await page.fill('#aiMaterial', 'amber');
  await page.click('#aiPropose');
  await page.waitForSelector('#aiCancel:not([hidden])');
  const proposing = page.waitForResponse('**/api/ai/propose');
  await page.click('#aiCancel');
  assert.equal(await page.textContent('#aiProgress'), await t(page, 'aiCancelled'));
  const rejected = page.waitForResponse('**/api/ai/reject');
  release();
  await proposing;
  await rejected;
  assert.equal(await page.isDisabled('#aiApply'), true);
  assert.equal(await page.textContent('#aiSummary'), await t(page, 'aiNoProposal'));
  doc = JSON.parse(fs.readFileSync(studio.workspaceFile('ruby_demo'), 'utf8'));
  assert.ok(!objectIds(doc).includes('amber'));
});

e2e('a material set and an Impact Spark effect go through the same transactions; effects never reach the .hmod', async ({ page, studio }) => {
  await loadDemo(page);
  await page.click('#openAi');
  await propose(page, 'material_set', async () => {
    await page.fill('#aiMaterial', 'topaz');
    await page.fill('#aiMaterialName', 'Topaz');
  });
  const created = await page.$$eval('#aiDiff .ai-asset header b', bs => bs.map(b => b.textContent));
  assert.deepEqual(created.sort(), ['block:topaz_block', 'item:topaz', 'recipe:topaz_block', 'recipe:topaz_from_block']);
  await page.click('#aiApply');
  await disk(studio, d => objectIds(d).includes('topaz'));
  await page.click('#closeAi');
  const withSet = await download(page, '#exportHmod');
  assert.ok(readZip(withSet)['data/ruby_demo/horizon/item/topaz.json'], 'the material set is in the package');

  await page.click('#openAi');
  await propose(page, 'impact_effect', async () => page.fill('#aiSeed', '7'));
  assert.match(await page.textContent('#aiDiagnostics'), /Studio preview and is not exported/);
  await page.click('#aiApply');
  await waitState(page, () => (JSON.parse(localStorage.getItem('horizonStudio_v02')).effects || []).length === 1);
  const effect = (await stored(page)).effects[0];
  assert.equal((effect.id), 'impact_spark');
  assert.equal(effect.seed, 7);
  await page.click('#closeAi');
  const withEffect = await download(page, '#exportHmod');
  assert.equal(sha256(withEffect), sha256(withSet), 'an effect never changes the package');
  // The effect is an ordinary project object: the VFX Studio opens it, and one undo removes it.
  await page.click('#openVfx');
  await page.waitForFunction(() => document.querySelectorAll('#vfxEffects [data-vfx]').length === 1);
  await page.click('#closeVfx');
  await page.click('#undoEdit');
  await waitState(page, () => !(JSON.parse(localStorage.getItem('horizonStudio_v02')).effects || []).length);
  assert.deepEqual((await editorState(page)).items.map(i => i.id), ['ruby', 'topaz']);
});

e2e('Claude is used only after a stored key, consent and online mode; the key never reaches the page (HS-021)', async ({ page }) => {
  const KEY = 'sk-ant-e2e-NEVER-IN-THE-PAGE-0123456789';
  const seen = [];
  page.on('response', async response => {
    if (response.url().includes('/api/ai/')) seen.push(await response.text().catch(() => ''));
  });
  await loadDemo(page);
  await page.click('#openAi');
  await page.selectOption('#aiProvider', 'claude');
  assert.equal(await page.textContent('#aiProviderBadge'), await t(page, 'aiRemoteBadge'));
  await page.waitForFunction(() => document.querySelectorAll('#aiRemoteStatus li').length === 5);
  const status = await page.textContent('#aiRemoteStatus');
  assert.ok(status.includes(await t(page, 'aiNotExercised')), 'the panel says the live API was not exercised');
  assert.ok(status.includes(await t(page, 'aiConsentMissing')));
  // The exact payload is visible before anything can be sent; it carries no texture, override or plugin data.
  await page.fill('#aiText', 'Add a sapphire material set');
  await page.waitForFunction(() => document.querySelector('#aiContextView').textContent.includes('Request: Add a sapphire'));
  const sent = await page.textContent('#aiContextView');
  assert.ok(sent.includes('item:ruby') && !sent.includes('data:image') && !sent.includes('source_overrides'));

  const tryPropose = async key => {
    await page.click('#aiPropose');
    await page.waitForSelector('#aiError:not([hidden])');
    const text = await page.textContent('#aiError');
    await page.$eval('#aiError', el => { el.hidden = true; });
    return text;
  };
  assert.equal(await tryPropose(), await t(page, 'aiErrConsent'));
  await page.fill('#aiKey', KEY);
  await page.click('#aiSaveKey');
  await page.waitForFunction(k => document.querySelector('#aiRemoteStatus').textContent.includes(k), await t(page, 'aiKeyStored', { store: 'memory' }));
  assert.equal(await page.inputValue('#aiKey'), '', 'the field does not keep the key');
  await page.check('#aiConsent');
  await page.waitForFunction(k => document.querySelector('#aiRemoteStatus').textContent.includes(k), await t(page, 'aiConsentGiven'));
  // This test environment has no Anthropic SDK and no network: the core says so instead of pretending.
  const unavailable = await tryPropose();
  assert.ok(unavailable.startsWith((await t(page, 'aiErrSdk', { error: '' })).trim()) ||
            unavailable.startsWith((await t(page, 'aiErrProvider', { error: '' })).trim()), unavailable);
  await page.check('#aiOffline');
  await page.waitForFunction(k => document.querySelector('#aiRemoteStatus').textContent.includes(k), await t(page, 'aiOfflineOn'));
  assert.equal(await tryPropose(), await t(page, 'aiErrOffline'));
  await page.click('#aiForgetKey');
  await page.waitForFunction(() => document.querySelector('#aiForgetKey').disabled);

  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  assert.ok(!stored.includes(KEY), 'never in browser storage');
  assert.ok(!(await page.content()).includes(KEY), 'never in the page');
  assert.ok(seen.length > 0 && seen.every(body => !body.includes(KEY)), 'never in a response');
});

e2e('the AI Creator is translated, says it is simulated and passes automated accessibility rules', async ({ page }) => {
  await loadDemo(page);
  await page.click('#lang-ru');
  await page.click('#openAi');
  assert.equal(await page.textContent('#aiProviderBadge'), 'Симуляция · тестовый провайдер');
  assert.equal(await page.textContent('#aiApply'), await t(page, 'aiApply'));
  await propose(page, 'material_set', async () => page.fill('#aiMaterial', 'opal'));
  let axe;
  try { axe = require.resolve('axe-core/axe.min.js'); } catch (_) {
    if (process.env.CI) throw new Error('axe-core must be installed in CI');
    return;
  }
  // The page's CSP refuses inline scripts, which is what addScriptTag inserts; DevTools evaluation is not a page script.
  await page.evaluate(fs.readFileSync(axe, 'utf8'));
  const result = await page.evaluate(() => window.axe.run(document.querySelector('#aiDialog'), { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }));
  assert.deepEqual(result.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(', ')}`), []);
});
