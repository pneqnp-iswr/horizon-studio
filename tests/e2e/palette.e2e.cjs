'use strict';
/* HS-033: the command palette in a real browser: every workbench command is reachable from the
 * keyboard, runs the real control, and the palette is translated and accessible. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { e2e, t, waitStatus } = require('./harness.cjs');

const options = page => page.$$eval('#paletteList [role=option]', items => items.map(li => li.dataset.command));

e2e('Ctrl+K opens the palette and runs the chosen command', async ({ page }) => {
  await page.keyboard.press('Control+k');
  assert.equal(await page.isVisible('#paletteDialog'), true);
  assert.equal(await page.evaluate(() => document.activeElement.id), 'paletteInput');
  await page.keyboard.type('vfx');
  assert.equal((await options(page))[0], 'openVfx');
  await page.keyboard.press('Enter');
  assert.equal(await page.isVisible('#paletteDialog'), false);
  await page.waitForSelector('#vfxDialog:not([hidden])');
  await page.click('#closeVfx');
  // Arrow keys move the active option; Escape closes and returns focus.
  await page.focus('#openJourney');
  await page.keyboard.press('Control+k');
  await page.keyboard.type('demo');
  await page.keyboard.press('Enter');
  await waitStatus(page, await t(page, 'demoLoaded'));
  await page.waitForFunction(() => document.activeElement.id === 'openJourney');  // an in-place command keeps focus
  await page.keyboard.press('Control+k');
  const first = await page.getAttribute('#paletteInput', 'aria-activedescendant');
  await page.keyboard.press('ArrowDown');
  assert.notEqual(await page.getAttribute('#paletteInput', 'aria-activedescendant'), first);
  assert.equal(await page.$$eval('#paletteList [aria-selected=true]', items => items.length), 1);
  await page.keyboard.press('Escape');
  assert.equal(await page.isVisible('#paletteDialog'), false);
  assert.equal(await page.evaluate(() => document.activeElement.id), 'openJourney', 'focus returns where it was');
  await page.keyboard.press('Control+k');
  await page.keyboard.type('zzz-no-command');
  assert.equal(await page.isVisible('#paletteEmpty'), true);
});

e2e('every top-bar and rail command is reachable from the palette', async ({ page }) => {
  const controls = await page.$$eval('header button[id], nav button[id], .rail-bottom button[id]', buttons =>
    buttons.filter(b => b.id !== 'openPalette' && b.id !== 'quickExport').map(b => ({ id: b.id, disabled: b.disabled })));
  // Every control has a palette command (quickExport is a shortcut for exportHmod, which has one).
  const declared = new Set(await page.evaluate(() => PALETTE.map(([id]) => id)));
  assert.deepEqual(controls.filter(c => !declared.has(c.id)).map(c => c.id), []);
  // The palette offers exactly the enabled ones: disabled controls (undo/redo with no history) are left out.
  await page.click('#openPalette');
  const offered = new Set(await options(page));
  assert.deepEqual(controls.filter(c => !c.disabled && !offered.has(c.id)).map(c => c.id), []);
  assert.deepEqual(controls.filter(c => c.disabled && offered.has(c.id)).map(c => c.id), []);
  await page.keyboard.press('Escape');
});

e2e('the palette is translated and passes automated accessibility rules', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.click('#lang-ru');
  await page.keyboard.press('Control+k');
  assert.equal(await page.getAttribute('#paletteInput', 'placeholder'), 'Введите команду…');
  await page.keyboard.type('экспорт');
  const labels = await page.$$eval('#paletteList [role=option] span', spans => spans.map(s => s.textContent));
  assert.ok(labels.length && labels.every(label => /[А-Яа-яЁё]/.test(label)), labels.join(' | '));
  let axe;
  try { axe = require.resolve('axe-core/axe.min.js'); } catch (_) {
    if (process.env.CI) throw new Error('axe-core must be installed in CI');
    return;
  }
  // The page's CSP refuses inline scripts, which is what addScriptTag inserts; DevTools evaluation is not a page script.
  await page.evaluate(fs.readFileSync(axe, 'utf8'));
  const result = await page.evaluate(() => window.axe.run(document.querySelector('#paletteDialog'), { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }));
  assert.deepEqual(result.violations.map(v => `${v.id} (${v.nodes.map(n => n.target.join(' ')).join(', ')})`), []);
});
