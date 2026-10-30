'use strict';
/* Desktop workbench chrome in a real browser: empty states, the development journey,
 * the engine-target card and its export gate, and a fully translated Russian UI. */
const assert = require('node:assert/strict');
const { e2e, t, waitStatus, editorState } = require('./harness.cjs');

async function showExplorer(page) {
  if (!(await page.isVisible('#demo'))) {
    await page.click('#toggleExplorer');
    await page.waitForSelector('#demo', { state: 'visible' });
  }
}

e2e('a new project shows an empty state per kind that leads to real work', async ({ page }) => {
  for (const kind of ['block', 'item', 'recipe', 'structure']) {
    await page.click(`#${kind}Tab`);
    assert.equal(await page.textContent('#entries .empty-state h2'), await t(page, `empty_${kind}_title`));
    assert.equal(await page.getAttribute('body', 'data-tab'), kind);
    assert.equal(await page.getAttribute(`#${kind}Tab`, 'aria-selected'), 'true');
    assert.equal(await page.isVisible('#emptyDemo'), kind !== 'structure', 'only kinds the demo fills offer it');
  }
  await page.click('#recipeTab');
  await page.click('#emptyDemo');
  await waitStatus(page, await t(page, 'demoLoaded'));
  assert.equal(await page.locator('#entries .empty-state').count(), 0);
  await page.click('#recipeTab');
  assert.equal(await page.locator('#entries .recipe-card').count(), 2);
  assert.equal(await page.textContent('#countRecipe'), '2');
  assert.equal(await page.textContent('#topProjectName'), 'Ruby Demo');
  assert.equal(await page.textContent('#shellStatus'), await t(page, 'browserMode'));
});

e2e('the development journey separates the plan from what this build can do', async ({ page }) => {
  await page.click('#openJourney');
  await page.waitForSelector('#journeyBuild');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'closeJourney');
  const phases = await page.$$eval('#journeyBody section:first-child ol.phase-list li', items => items.map(li => li.textContent));
  assert.ok(phases.length >= 9 && phases.some(text => text.startsWith('F3')), phases.join('\n'));
  assert.ok(await page.isVisible('#journeyBody img.journey-map'));
  const build = await page.textContent('#journeyBuild');
  for (const expected of ['content.block', 'content.recipe', 'native.hook_mod', 'entity.custom', 'd2186eb']) {
    assert.ok(build.includes(expected), `${expected} missing from the build section`);
  }
  assert.ok(build.includes(await t(page, 'capEngineOnly')) && build.includes(await t(page, 'capUnsupported')));
  await page.keyboard.press('Escape');
  await page.waitForSelector('#journeyDialog', { state: 'hidden' });
  assert.equal(await page.evaluate(() => document.activeElement.id), 'openJourney');
  // Russian re-renders an open journey from the same data.
  await page.click('#lang-ru');
  await page.click('#openJourney');
  await page.waitForSelector('#journeyBuild');
  const view = await page.evaluate(() => fetch('/api/journey').then(response => response.json()));
  const current = view.phases.find(phase => phase.id === view.current_phase);
  assert.ok((await page.textContent('#journeyBody')).includes(current.name_ru), current.name_ru);
  assert.equal(await page.textContent('#journeyHeading'), 'Путь разработки');
});

e2e('the engine card lists what the project needs and the target can load', async ({ page }) => {
  await showExplorer(page);
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
  await page.waitForFunction(() => document.querySelectorAll('#engineCapabilities li.cap-ok').length >= 5);
  const listed = await page.$$eval('#engineCapabilities li', items => items.map(li => li.textContent));
  for (const capability of ['content.block', 'content.item', 'content.recipe', 'content.lang', 'content.loot_table']) {
    assert.ok(listed.some(text => text.startsWith(capability)), `${capability} not listed: ${listed}`);
  }
  assert.match(await page.textContent('#engineStatus'), /^Horizon d2186eb · API 0\.2$/);
});

e2e('export is blocked, with the reason and without data loss, when the engine cannot load the project', async ({ page }) => {
  await showExplorer(page);
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
  const before = await editorState(page);
  await page.route('**/api/capabilities/check', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      profile: { revision: 'd2186eb9aa022a64a8b26e6989a04e44fba99ee7', label: 'Horizon d2186eb', content_api: '0.2' },
      requirements: { 'content.block': ['block ruby_block'], 'entity.custom': ['entity wisp'] },
      diagnostics: [{ level: 'error', code: 'ENGINE_CAPABILITY_MISSING', capability: 'entity.custom',
        message: 'entity.custom (entity wisp): no content-mod registry at this revision' }],
    }),
  }));
  let downloaded = false;
  page.on('download', () => { downloaded = true; });
  await page.click('#exportHmod');
  await page.waitForFunction(() => document.querySelector('#status').classList.contains('error'));
  const message = await page.textContent('#status');
  assert.ok(message.includes('entity.custom'), message);
  assert.ok(message.startsWith((await t(page, 'exportBlocked', { details: '' })).trim().slice(0, 20)), message);
  assert.equal(downloaded, false);
  assert.deepEqual(await editorState(page), before, 'a blocked export keeps the project unchanged');
  assert.equal(await page.locator('#engineCapabilities li.cap-missing').count(), 1);
  assert.match(await page.textContent('#engineStatus'), /1/);
});

e2e('the Russian workbench has no leftover English interface text', async ({ page }) => {
  await showExplorer(page);
  await page.click('#demo');
  await page.click('#lang-ru');
  await page.click('#blockTab');
  // Product, format and engine names stay as they are; everything else must be translated.
  const allowed = new Set(['Horizon', 'Studio', 'Mod', 'Doctor', 'Ruby', 'Demo', 'hmod', 'API', 'PNG', 'JSON', 'NBT', 'zip',
    'WebGL', 'd2186eb', 'project', 'studio', 'Iron', 'Block', 'minecraft', 'iron_block', 'ruby_block', 'of',
    // proper names, the official command, an example identifier and the language's own name
    'Mojang', 'Microsoft', 'cargo', 'horizon', 'mod', 'check', 'my_first_mod', 'English']);
  const leftovers = await page.evaluate(allowedWords => {
    const roots = ['.topbar', '.rail', '#projectSidebar', '#inspector', '.workspace-head', '.statusbar']
      .map(selector => document.querySelector(selector));
    const found = new Set();
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const element = node.parentElement;
        if (!element || element.closest('option, code, .project-chip, #workspaceMode, [hidden]') || !element.getClientRects().length) continue;
        for (const word of node.textContent.match(/[A-Za-z][A-Za-z_]{2,}/g) || []) {
          if (!allowedWords.includes(word)) found.add(`${word} (${element.tagName.toLowerCase()}#${element.id || element.className})`);
        }
      }
      for (const element of root.querySelectorAll('[aria-label], [placeholder], [title]')) {
        if (element.closest('[hidden]')) continue;
        for (const attribute of ['aria-label', 'placeholder', 'title']) {
          for (const word of (element.getAttribute(attribute) || '').match(/[A-Za-z][A-Za-z_]{2,}/g) || []) {
            if (!allowedWords.includes(word)) found.add(`${word} [${attribute} of #${element.id || element.className}]`);
          }
        }
      }
    }
    return [...found];
  }, [...allowed]);
  assert.deepEqual(leftovers, []);
});
