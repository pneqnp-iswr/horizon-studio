'use strict';
/* Desktop workbench chrome in a real browser: empty states, the development journey,
 * the engine-target card and its export gate, and a fully translated Russian UI. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { e2e, t, waitStatus, editorState, download } = require('./harness.cjs');

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
  await page.waitForSelector('.jr-card');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'closeJourney');
  const view = await page.evaluate(() => fetch('/api/journey').then(response => response.json()));
  assert.equal(await page.getAttribute('[data-tab="roadmap"]', 'aria-selected'), 'true');
  // The current phase and the active milestone open first, straight from roadmap.json.
  assert.equal(await page.getAttribute(`.jr-phase[data-phase="${view.current_phase}"]`, 'aria-pressed'), 'true');
  assert.ok((await page.textContent('#milestoneHeading')).startsWith(view.active_milestone));
  await page.click('[data-tab="build"]');
  const build = await page.textContent('#journeyBuild');
  for (const expected of ['content.block', 'content.recipe', 'native.hook_mod', 'entity.custom', 'd2186eb']) {
    assert.ok(build.includes(expected), `${expected} missing from the build section`);
  }
  const capabilities = await page.$$eval('#journeyBuild li b', items => items.map(b => b.textContent));
  assert.ok(capabilities.length >= 10 && capabilities.every(name => /^[a-z_]+\.[a-z_]+$/.test(name)),
    `the build lists engine capabilities only, never roadmap milestones: ${capabilities}`);
  assert.ok(build.includes(await t(page, 'capEngineOnly')) && build.includes(await t(page, 'capUnsupported')));
  await page.keyboard.press('Escape');
  await page.waitForSelector('#journeyDialog', { state: 'hidden' });
  assert.equal(await page.evaluate(() => document.activeElement.id), 'openJourney');
  // Russian re-renders the open journey from the same data.
  await page.click('#lang-ru');
  await page.click('#openJourney');
  await page.waitForSelector('.jr-card');
  const current = view.phases.find(phase => phase.id === view.current_phase);
  assert.ok((await page.textContent('#jrPhases')).includes(current.name_ru), current.name_ru);
  const active = view.milestones.find(m => m.id === view.active_milestone);
  assert.ok((await page.textContent('#milestoneDetail')).includes(active.summary_ru));
  assert.equal(await page.textContent('#journeyHeading'), 'Путь разработки');
});

e2e('every phase and milestone of the roadmap can be explored, with dependencies', async ({ page }) => {
  const view = await page.evaluate(() => fetch('/api/journey').then(response => response.json()));
  await page.click('#openJourney');
  await page.waitForSelector('.jr-card');
  for (const phase of view.phases) {
    await page.click(`.jr-phase[data-phase="${phase.id}"]`);
    const listed = await page.$$eval('#milestoneList .jr-card', cards => cards.map(card => card.dataset.milestone));
    assert.deepEqual(listed, phase.milestones, `phase ${phase.id}`);
  }
  await page.click('.jr-phase[data-phase="all"]');
  assert.equal(await page.locator('#milestoneList .jr-card').count(), view.milestones.length);
  // HS-024 depends on HS-022 and HS-023; following a dependency opens it.
  await page.click('.jr-card[data-milestone="HS-024"]');
  const deps = await page.$$eval('[data-kind="depends"] .jr-ref', refs => refs.map(r => r.dataset.milestone));
  assert.deepEqual(deps, view.milestones.find(m => m.id === 'HS-024').depends_on);
  await page.click('[data-kind="depends"] .jr-ref[data-milestone="HS-023"]');
  assert.ok((await page.textContent('#milestoneHeading')).startsWith('HS-023'));
  assert.ok((await page.textContent('[data-kind="dependents"]')).includes('HS-024'));
  // Blocked work stays blocked, with its blocker.
  await page.fill('#roadmapSearch', 'real-game content-load');
  await page.click('.jr-card[data-milestone="HS-002"]');
  const detail = await page.textContent('#milestoneDetail');
  assert.ok(detail.includes(await t(page, 'status_blocked')) && detail.includes(await t(page, 'jrBlocker')));
  // Status and track filters.
  await page.fill('#roadmapSearch', '');
  await page.click('.jr-phase[data-phase="all"]');
  for (const status of ['done', 'partial', 'in_progress', 'planned']) await page.click(`[data-status="${status}"]`);
  const blocked = await page.$$eval('#milestoneList .jr-card', cards => cards.map(card => card.dataset.milestone));
  assert.deepEqual(blocked, view.milestones.filter(m => m.status === 'blocked').map(m => m.id));
  for (const status of ['done', 'partial', 'in_progress', 'planned']) await page.click(`[data-status="${status}"]`);
  await page.selectOption('#roadmapTrack', 'pixelchat');
  const pixelchat = await page.$$eval('#milestoneList .jr-card', cards => cards.map(card => card.dataset.milestone));
  assert.deepEqual(pixelchat, ['PC-001', 'PC-002', 'PC-003', 'PC-004', 'PC-005']);
  // Evidence and design links are GitHub links that open outside the app.
  const links = await page.$$eval('#milestoneDetail a', anchors => anchors.map(a => [a.href, a.target]));
  assert.ok(links.length && links.every(([href, target]) => href.startsWith('https://github.com/pneqnp-iswr/horizon-studio/') && target === '_blank'));
});

e2e('the roadmap explorer works from the keyboard', async ({ page }) => {
  await page.click('#openJourney');
  await page.waitForSelector('.jr-card');
  await page.focus('[data-tab="roadmap"]');
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.tab), 'build');
  assert.equal(await page.isVisible('#journeyBuild'), true);
  await page.keyboard.press('ArrowLeft');
  await page.focus('.jr-phase[data-phase="F0"]');
  await page.keyboard.press('ArrowDown');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.phase), 'F1');
  await page.keyboard.press('Enter');
  assert.equal(await page.getAttribute('.jr-phase[data-phase="F1"]', 'aria-pressed'), 'true');
  await page.focus('#milestoneList .jr-card');
  await page.keyboard.press('ArrowDown');
  const second = await page.evaluate(() => document.activeElement.dataset.milestone);
  await page.keyboard.press('Enter');
  assert.ok((await page.textContent('#milestoneHeading')).startsWith(second));
  assert.equal(await page.evaluate(() => document.activeElement.id), 'milestoneDetail');
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
  // The engine card fills in after a debounced check; scan it in its final state.
  await page.waitForFunction(() => document.querySelector('#engineCapabilities li') && document.querySelector('#engineProfile').textContent !== '—');
  // Product, format and engine names stay as they are; everything else must be translated.
  const allowed = new Set(['Horizon', 'Studio', 'Mod', 'Doctor', 'Ruby', 'Demo', 'hmod', 'API', 'PNG', 'JSON', 'VFX', 'NBT', 'zip',
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
        // Identifiers (code, lists of object ids) are data, not interface text.
        if (!element || element.closest('option, code, [data-ids], .project-chip, #workspaceMode, [hidden]') || !element.getClientRects().length) continue;
        for (const word of node.textContent.match(/[A-Za-z][A-Za-z_]{2,}/g) || []) {
          if (!allowedWords.includes(word)) found.add(`${word} (${element.tagName.toLowerCase()}#${element.id || element.className})`);
        }
      }
      for (const element of root.querySelectorAll('[aria-label], [placeholder], [title]')) {
        if (element.closest('[hidden], [data-ids]')) continue;
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

e2e('the rail is keyboard operable and the journey dialog keeps focus inside', async ({ page }) => {
  await page.focus('#recipeTab');
  await page.keyboard.press('ArrowDown');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'structureTab');
  assert.equal(await page.getAttribute('body', 'data-tab'), 'structure');
  await page.keyboard.press('Home');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'blockTab');
  assert.deepEqual(await page.$$eval('.rail-group [role=tab]', tabs => tabs.map(t => t.tabIndex)), [0, -1, -1, -1]);
  await page.click('#openJourney');
  await page.waitForSelector('.jr-card');
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press('Tab');
    assert.ok(await page.evaluate(() => document.querySelector('#journeyDialog').contains(document.activeElement)),
      'focus must stay in the modal dialog');
  }
});

e2e('automated WCAG 2.1 AA rules pass on the main workbench states (axe-core)', async ({ page }) => {
  let axe;
  try { axe = require.resolve('axe-core/axe.min.js'); } catch (_) {
    if (process.env.CI) throw new Error('axe-core must be installed in CI');
    return;  // local runs without axe-core skip this check
  }
  // Entry cards fade in; with reduced motion they render final colours at once, so contrast is measured as seen.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const audit = async label => {
    // The page's CSP refuses inline scripts, which is what addScriptTag inserts; DevTools evaluation is not a page script.
    await page.evaluate(fs.readFileSync(axe, 'utf8'));
    const result = await page.evaluate(() => window.axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }));
    assert.deepEqual(result.violations.map(v => `${label}: ${v.id} (${v.nodes.map(n => n.target.join(' ')).join(', ')})`), []);
  };
  await audit('empty project');
  await showExplorer(page);
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
  assert.equal(await page.$eval('.entry-card', card => getComputedStyle(card).animationName), 'none', 'reduced motion stops the fade-in');
  await audit('demo');
  await page.click('#lang-ru');
  await page.click('#openJourney');
  await page.waitForSelector('.jr-card');
  await audit('journey in Russian');
});

e2e('a project chooses its engine target, sees the differences and keeps the choice (HS-008)', async ({ page }) => {
  const NEW = '3c1d4b39c6823dca9751118a0b13e6084d019d64';
  await showExplorer(page);
  await page.click('#demo');
  await waitStatus(page, await t(page, 'demoLoaded'));
  await page.waitForFunction(() => document.querySelectorAll('#engineTargetSelect option').length >= 3);
  assert.equal(await page.inputValue('#engineTargetSelect'), '');
  await page.selectOption('#engineTargetSelect', NEW);
  await page.waitForFunction(() => document.querySelector('#engineStatus').textContent.startsWith('Horizon 3c1d4b3'));
  assert.equal((await editorState(page)).target.revision, NEW);
  assert.equal(await page.isVisible('#engineDiff'), true);
  await page.click('#engineDiffTitle');
  const diff = await page.textContent('#engineDiffList');
  assert.ok(diff.includes('native.particles') && diff.includes(await t(page, 'capStatus_engine-only')), diff);
  // Undo returns to the default engine; redo brings the choice back.
  await page.click('#undoEdit');
  await page.waitForFunction(() => document.querySelector('#engineStatus').textContent.startsWith('Horizon d2186eb'));
  assert.equal(await page.inputValue('#engineTargetSelect'), '');
  await page.click('#redoEdit');
  await page.waitForFunction(rev => document.querySelector('#engineTargetSelect').value === rev, NEW);
  // The saved studio.project/1 file records the target, and opening it restores the selection.
  const saved = JSON.parse((await download(page, '#saveProject')).toString('utf8'));
  assert.deepEqual(saved.target, { engine: 'horizon', revision: NEW });
  saved.target.revision = 'f'.repeat(40);
  await page.setInputFiles('#projectFile', { name: 'future.hstudio.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(saved)) });
  await page.waitForFunction(() => /ffffff/.test(document.querySelector('#engineTargetSelect').selectedOptions[0]?.textContent || ''));
  // An unknown revision promises nothing: export is refused with the reason and the project is kept.
  const before = await editorState(page);
  let downloaded = false;
  page.on('download', () => { downloaded = true; });
  await page.click('#exportHmod');
  await page.waitForFunction(() => document.querySelector('#status').classList.contains('error'));
  assert.match(await page.textContent('#status'), /ffffffff/);
  assert.equal(downloaded, false);
  assert.deepEqual(await editorState(page), before);
});
