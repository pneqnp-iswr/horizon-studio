'use strict';
/* HS-025: VFX Studio in a real browser — the Impact Spark vertical slice. The preview is a Studio
 * preview: these scenarios check that it is deterministic and labelled as such, never that Horizon
 * renders it. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { OFFICIAL_RUBY_SHA256, e2e, t, waitStatus, editorState, download, sha256 } = require('./harness.cjs');

const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'vfx_impact_spark.json'), 'utf8'));

async function loadDemo(page) {
  if (!(await page.isVisible('#demo'))) {
    await page.click('#toggleExplorer');
    await page.waitForSelector('#demo', { state: 'visible' });
  }
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
}

async function newSpark(page) {
  await page.click('#openVfx');
  await page.waitForSelector('#vfxDialog:not([hidden])');
  await page.click('#vfxNewSpark');
  await waitStatus(page, await t(page, 'vfxCreated'));
}

async function scrub(page, time) {
  await page.$eval('#vfxTime', (input, value) => { input.value = String(value); input.dispatchEvent(new Event('input')); }, time);
  return page.$eval('#vfxCanvas', canvas => ({ particles: Number(canvas.dataset.particles), image: canvas.toDataURL() }));
}

e2e('VFX Studio previews an Impact Spark deterministically and labels it as a Studio preview', async ({ page }) => {
  await loadDemo(page);
  await newSpark(page);
  assert.equal(await page.textContent('#vfxPreviewLabel'), await t(page, 'vfxPreviewLabel'));
  assert.equal(await page.getAttribute('#vfxCanvas', 'aria-label'), await t(page, 'vfxPreviewLabel'));
  // It animates on its own, then the timeline scrubs to exact times.
  await page.waitForFunction(() => Number(document.querySelector('#vfxCanvas').dataset.time) > 0);
  for (const [time, expected] of Object.entries(FIXTURE.alive)) {
    assert.equal((await scrub(page, Number(time))).particles, expected, `alive particles at ${time} s`);
  }
  const first = await scrub(page, 0.2);
  await scrub(page, 0.45);
  const again = await scrub(page, 0.2);
  assert.equal(again.image, first.image, 'the same seed and time draw the same frame');
  assert.equal(await page.textContent('#vfxCount'), await t(page, 'vfxCount', { count: FIXTURE.alive['0.2'] }));
  // Engine diagnostics never promise in-game rendering.
  const codes = await page.$$eval('#vfxDiagnostics li', items => items.map(li => li.dataset.code));
  assert.ok(codes.includes('STUDIO_PREVIEW') && codes.includes('NO_CUSTOM_PARTICLES'), codes.join(','));
  // A different seed is a different effect.
  await page.fill('#vfxSeed', '7');
  await page.dispatchEvent('#vfxSeed', 'change');
  assert.notEqual((await scrub(page, 0.2)).image, first.image);
});

e2e('effect edits are validated, undoable, saved in the project and leave the .hmod unchanged', async ({ page }) => {
  await loadDemo(page);
  await newSpark(page);
  const count = async () => (await editorState(page)).effects[0].emitters[0].bursts[0].count;
  assert.equal(await count(), 28);
  await page.fill('#vfxSparkCount', '9999');
  await page.dispatchEvent('#vfxSparkCount', 'change');
  assert.equal(await page.getAttribute('#vfxSparkCount', 'aria-invalid'), 'true');
  assert.equal(await count(), 28, 'an invalid value changes nothing');
  assert.ok(await page.$eval('#status', el => el.classList.contains('error')));
  await page.fill('#vfxSparkCount', '40');
  await page.dispatchEvent('#vfxSparkCount', 'change');
  assert.equal(await count(), 40);
  await page.click('#closeVfx');
  await page.click('#undoEdit');
  assert.equal(await count(), 28);
  await page.click('#redoEdit');
  assert.equal(await count(), 40);

  const saved = JSON.parse((await download(page, '#saveProject')).toString('utf8'));
  const effect = saved.objects.find(o => o.kind === 'vfx');
  assert.equal(effect.id, 'impact_spark');
  assert.equal(effect.props.schema, 'studio.vfx/1');
  assert.equal(effect.props.emitters[0].bursts[0].count, 40);
  const uid = (await editorState(page)).effects[0].uid;
  assert.equal(effect.uid, uid);

  // Reopening restores the effect; the package is still exactly the officially checked one.
  await page.click('#openVfx');
  await page.click('#vfxDelete');
  assert.deepEqual((await editorState(page)).effects || [], []);
  await page.click('#closeVfx');
  await page.setInputFiles('#projectFile', { name: 'vfx.hstudio.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(saved)) });
  await page.waitForFunction(id => (JSON.parse(localStorage.getItem('horizonStudio_v02')).effects || [])[0]?.uid === id, uid);
  assert.equal(sha256(await download(page, '#exportHmod')), OFFICIAL_RUBY_SHA256);
});

e2e('VFX Studio is translated and passes automated accessibility rules', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.click('#lang-ru');
  await loadDemo(page);
  await newSpark(page);
  assert.equal(await page.textContent('#vfxPreviewLabel'), 'Предпросмотр Studio — не игровая отрисовка');
  assert.equal(await page.$eval('#vfxCanvas', c => c.dataset.time), '0.000', 'reduced motion: no autoplay');
  const texts = await page.$$eval('#vfxDialog label span, #vfxDialog legend, #vfxDialog button, #vfxDiagnostics li',
    nodes => nodes.map(n => n.textContent.trim()).filter(Boolean));
  for (const english of ['Sparks', 'Play', 'Restart', 'Delete effect', 'Studio preview only']) {
    assert.ok(!texts.some(text => text.startsWith(english)), `English left in the Russian UI: ${english}`);
  }
  let axe;
  try { axe = require.resolve('axe-core/axe.min.js'); } catch (_) {
    if (process.env.CI) throw new Error('axe-core must be installed in CI');
    return;
  }
  await page.addScriptTag({ path: axe });
  const result = await page.evaluate(() => window.axe.run(document.querySelector('#vfxDialog'), { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }));
  assert.deepEqual(result.violations.map(v => `${v.id} (${v.nodes.map(n => n.target.join(' ')).join(', ')})`), []);
});
