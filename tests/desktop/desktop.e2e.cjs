'use strict';
/* Functional E2E on the real desktop window (HS-019): the Tauri shell, its WebView and the
 * bundled core, driven through tauri-driver. Needs a test build with the cargo feature `e2e`
 * (answers the native Save dialog from HORIZON_STUDIO_E2E_SAVE_DIR) in DESKTOP_APP.
 * Without DESKTOP_APP every scenario is skipped; the browser suite (tests/e2e) is separate. */
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { launch, sleep, stopAll } = require('./webdriver.cjs');
const { readZip } = require('../e2e/zip.cjs');

const APP = process.env.DESKTOP_APP;
const OFFICIAL_RUBY_SHA256 = 'ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2';
const scenario = (name, body) => test(name, { skip: !APP && 'set DESKTOP_APP to an e2e build of the shell', timeout: 240000 }, body);
test.after(stopAll);

function scratch() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'hs-desktop-e2e-'));
  const saves = path.join(home, 'saves');
  fs.mkdirSync(saves);
  // The core's data goes to HORIZON_STUDIO_HOME. HOME also isolates WebKitGTK's storage on Linux; Windows keeps
  // its own USERPROFILE (WebView2 and msedgedriver need the real one) and the scenarios clear storage themselves.
  const env = { HORIZON_STUDIO_HOME: path.join(home, '.horizon-studio'), HORIZON_STUDIO_E2E_SAVE_DIR: saves };
  if (process.platform !== 'win32') env.HOME = home;
  return { home, saves, env };
}

function corePids() {
  if (process.platform === 'win32') {
    return execFileSync('tasklist', ['/FO', 'CSV', '/NH'], { encoding: 'utf8' })
      .split(/\r?\n/).filter(line => /horizon-studio-core\.exe/i.test(line)).map(line => Number(line.split('","')[1]));
  }
  return execFileSync('ps', ['-eo', 'pid=,args='], { encoding: 'utf8' })
    .split('\n').filter(line => /horizon-studio-core|launcher\.py --serve/.test(line)).map(line => Number(line.trim().split(/\s+/)[0]));
}
const coreProcesses = () => corePids().length;

async function open(env, extra = {}) {
  const win = await launch({ app: APP, env, ...extra });
  return win;
}

async function editorReady(win) {
  try {
    await win.waitFor(() => Boolean(window.HorizonDesktop && window.HorizonDesktop.available()
      && document.querySelector('#workspaceSaveStatus')?.dataset.key && document.body.dataset.shell),
    { message: 'the editor inside the desktop shell' });
  } catch (error) {
    error.message += `\n${await diagnose(win)}`;
    throw error;
  }
}

/** What a window that never became ready was doing: each readiness condition, the editor's own
 * status, which scripts loaded and whether startup reached its end, and the core's last requests. */
async function diagnose(win) {
  let page;
  try {
    page = await win.run(() => ({
      ipc: Boolean(window.__TAURI_INTERNALS__),
      bridge: Boolean(window.HorizonDesktop && window.HorizonDesktop.available()),
      bridgeAtStartup: document.body.classList.contains('desktop'),
      startupFinished: typeof document.querySelector('#openPalette')?.onclick === 'function',
      key: document.querySelector('#workspaceSaveStatus')?.dataset.key || null,
      shell: document.body.dataset.shell || null,
      status: document.querySelector('#status')?.textContent || '',
      missing: ['HorizonI18n', 'HorizonStudioApi', 'HorizonDesktop', 'HorizonWorkbench', 'HorizonVfxStudio', 'HorizonPalette',
        'HorizonAiCreator'].filter(name => !window[name]),
      navigation: performance.getEntriesByType('navigation').map(entry => entry.type),
      scripts: performance.getEntriesByType('resource').filter(entry => entry.initiatorType === 'script')
        .map(entry => `${new URL(entry.name).pathname} ${entry.responseStatus ?? '?'} ${Math.round(entry.duration)}ms`),
    }));
  } catch (error) { page = error.message; }
  let core = '';
  const dir = process.platform === 'win32'
    ? path.join(process.env.LOCALAPPDATA || '', 'io.github.pneqnp-iswr.horizonstudio', 'logs')
    : path.join(os.homedir(), '.local', 'share', 'io.github.pneqnp-iswr.horizonstudio', 'logs');
  try { core = fs.readFileSync(path.join(dir, 'core.log'), 'utf8').split(/\r?\n/).slice(-25).join('\n'); } catch (error) { core = error.message; }
  return `diagnosis: ${JSON.stringify(page)}\ncore.log (last lines):\n${core}`;
}

/** Reloads the window and waits for the new page's editor (never the old page's). */
async function reload(win, { clear = false } = {}) {
  await win.run(wipe => {
    window.__hsOldPage = true;
    if (wipe) localStorage.clear();
    setTimeout(() => location.reload(), 0);
    return true;
  }, clear);
  await win.waitFor(() => !window.__hsOldPage, { message: 'the reloaded page' });
  await editorReady(win);
}

async function fresh(win) {
  // WebView storage can outlive a test on Windows (it lives in the user's profile); start clean.
  await reload(win, { clear: true });
}

async function loadDemo(win) {
  if (!(await win.run(() => Boolean(document.querySelector('#demo').offsetParent)))) await win.click('#toggleExplorer');
  await win.waitFor(() => Boolean(document.querySelector('#demo').offsetParent), { message: 'explorer' });
  await win.click('#demo');
  await waitStatus(win, 'demoLoaded');
}

// Rendered WebDriver text follows CSS (uppercase labels, icon-only toolbars); compare DOM text.
const content = (win, css) => win.run(sel => document.querySelector(sel).textContent, css);

function diskHas(root, text) {
  if (!fs.existsSync(root)) return false;
  return fs.readdirSync(root, { withFileTypes: true }).some(entry => {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) return diskHas(full, text);
    // An atomic save's temporary file can be renamed away between the listing and the read.
    if (entry.name.endsWith('.tmp')) return false;
    try { return fs.readFileSync(full, 'utf8').includes(text); } catch (error) {
      if (error.code === 'ENOENT') return false;
      throw error;
    }
  });
}

async function until(check, message, timeout = 20000) {
  const deadline = Date.now() + timeout;
  while (!check()) {
    if (Date.now() > deadline) throw new Error(`Timed out waiting for ${message}`);
    await sleep(200);
  }
}

const status = win => win.run(() => document.querySelector('#status').textContent);
const state = win => win.run(() => JSON.parse(localStorage.getItem('horizonStudio_v02')));
const t = (win, key) => win.run(k => window.HorizonI18n.t(k), key);

async function waitStatus(win, key) {
  const text = await t(win, key);
  await win.waitFor(expected => document.querySelector('#status').textContent === expected, { message: `status ${key}` }, text);
}

async function openProject(win, document) {
  await win.run(text => {
    const input = window.document.getElementById('projectFile');
    const files = new DataTransfer();
    files.items.add(new File([text], 'project.hstudio.json', { type: 'application/json' }));
    input.files = files.files;
    input.dispatchEvent(new Event('change'));
    return true;
  }, JSON.stringify(document));
}

const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

scenario('launches the real window, completes the core handshake and loads the editor', async () => {
  const box = scratch();
  const before = coreProcesses();
  const win = await open(box.env);
  try {
    await editorReady(win);
    const info = await win.run(() => ({ href: location.href, title: document.title, shell: document.body.dataset.shell,
      ipc: Boolean(window.__TAURI_INTERNALS__), status: document.querySelector('#shellStatus').textContent }));
    assert.match(info.href, /^http:\/\/127\.0\.0\.1:\d+\//);
    assert.match(info.title, /Horizon Studio/);
    assert.ok(info.ipc && info.shell);
    assert.ok(info.status.includes(info.shell));
    assert.equal(coreProcesses(), before + 1, 'one core process per window');
    // The desktop core never hands its session token to HTTP clients; the editor got it from the shell.
    assert.equal(await win.run(() => fetch('/api/session').then(r => r.status)), 403);
    assert.equal(await win.run(() => window.HorizonStudioApi.session().then(token => token.length >= 32)), true);
  } finally {
    await win.close();
  }
  // Closing the window stops the core (stdin EOF).
  await until(() => coreProcesses() === before, 'the core to exit with its window', 15000);
});

scenario('creates a block, an item and a recipe, renames with stable uids, undoes and redoes', async () => {
  const box = scratch();
  const win = await open(box.env);
  try {
    await editorReady(win);
    await fresh(win);
    await win.type('#modId', 'desktop_e2e');
    await win.run(() => { document.querySelector('#modId').dispatchEvent(new Event('change')); return true; });
    await win.click('#blockTab');
    await win.type('#entryId', 'opal_block');
    await win.type('#entryName', 'Opal Block');
    await win.click('#addObject');
    await waitStatus(win, 'savedEntry');
    await win.click('#itemTab');
    await win.type('#entryId', 'opal');
    await win.type('#entryName', 'Opal');
    await win.click('#addObject');
    await waitStatus(win, 'savedEntry');
    await win.click('#recipeTab');
    await win.type('#recipeId', 'opal_block');
    await win.run(() => {
      const set = (id, value) => { const el = document.getElementById(id); el.value = value; el.dispatchEvent(new Event('change')); };
      set('recipeResult', '@opal_block');
      for (let i = 0; i < 9; i++) set('slot' + i, '@opal');
      return true;
    });
    await win.click('#addRecipe');
    const created = await state(win);
    assert.deepEqual([created.blocks.length, created.items.length, created.recipes.length], [1, 1, 1]);
    const uid = created.items[0].uid;
    assert.match(uid, /^[0-9a-f-]{36}$/);
    // Rename the item: the uid stays and the recipe follows the new id.
    await win.click('#itemTab');
    await win.click('[data-edit="0"]');
    await win.type('#entryId', 'fire_opal');
    await win.click('#addObject');
    await waitStatus(win, 'savedEntry');
    const renamed = await state(win);
    assert.equal(renamed.items[0].uid, uid);
    assert.equal(renamed.items[0].id, 'fire_opal');
    assert.ok(renamed.recipes[0].grid.every(cell => cell === '@fire_opal'));
    await win.waitFor(() => !document.querySelector('#undoEdit').disabled, { message: 'the core recorded the step (undoEdit)' });
    await win.click('#undoEdit');
    await win.waitFor(() => JSON.parse(localStorage.getItem('horizonStudio_v02')).items[0].id === 'opal', { message: 'undo' });
    await win.waitFor(() => !document.querySelector('#redoEdit').disabled, { message: 'the core recorded the step (redoEdit)' });
    await win.click('#redoEdit');
    await win.waitFor(() => JSON.parse(localStorage.getItem('horizonStudio_v02')).items[0].id === 'fire_opal', { message: 'redo' });
  } finally {
    await win.close();
  }
});

scenario('saves through the native save path, reopens the project and exports the officially checked .hmod', async () => {
  const box = scratch();
  const win = await open(box.env);
  try {
    await editorReady(win);
    await fresh(win);
    await loadDemo(win);
    await win.click('#exportHmod');
    await waitStatus(win, 'hmodExported');
    assert.equal(sha256(path.join(box.saves, 'ruby_demo.hmod')), OFFICIAL_RUBY_SHA256);
    await win.click('#saveProject');
    await waitStatus(win, 'projectSaved');
    const saved = JSON.parse(fs.readFileSync(path.join(box.saves, 'ruby_demo.hstudio.json'), 'utf8'));
    assert.equal(saved.schema, 'studio.project/1');
    const uids = saved.objects.map(o => o.uid).sort();
    await fresh(win);
    await openProject(win, saved);
    await win.waitFor(() => (JSON.parse(localStorage.getItem('horizonStudio_v02')) || {}).metadata?.id === 'ruby_demo', { message: 'reopened project' });
    const reopened = await state(win);
    assert.deepEqual([...reopened.blocks, ...reopened.items, ...reopened.recipes].map(o => o.uid).sort(), uids);
  } finally {
    await win.close();
  }
});

scenario('edits JSON in the Source Workbench and exports it in the .hmod and the source ZIP', async () => {
  const box = scratch();
  const win = await open(box.env);
  const target = 'assets/ruby_demo/models/item/ruby.json';
  const override = { parent: 'minecraft:item/handheld', textures: { layer0: 'minecraft:item/emerald' } };
  try {
    await editorReady(win);
    await fresh(win);
    await loadDemo(win);
    await win.click('#openWorkbench');
    await win.waitFor(sel => Boolean(document.querySelector(sel)), { message: 'source file list' }, `#sourceFiles button[title="${target}"]`);
    await win.click(`#sourceFiles button[title="${target}"]`);
    await win.type('#sourceCode', '{"parent": ');
    await win.click('#applySource');
    await win.waitFor(() => document.querySelector('#sourceStatus').classList.contains('error'), { message: 'invalid JSON refused' });
    assert.deepEqual((await state(win)).source_overrides, {});
    await win.type('#sourceCode', JSON.stringify(override));
    await win.click('#applySource');
    await win.waitFor(p => Boolean(JSON.parse(localStorage.getItem('horizonStudio_v02')).source_overrides[p]), { message: 'override applied' }, target);
    await win.click('#closeWorkbench');
    await win.click('#exportHmod');
    await waitStatus(win, 'hmodExported');
    assert.deepEqual(JSON.parse(readZip(fs.readFileSync(path.join(box.saves, 'ruby_demo.hmod')))[target].toString('utf8')), override);
    await win.click('#exportSource');
    await waitStatus(win, 'zipExported');
    const source = readZip(fs.readFileSync(path.join(box.saves, 'ruby_demo-source.zip')));
    assert.ok(source['ruby_demo/horizon-mod.toml'].toString('utf8').includes('id = "ruby_demo"'));
    assert.deepEqual(JSON.parse(source[`ruby_demo/${target}`].toString('utf8')), override);
    await win.waitFor(() => !document.querySelector('#undoEdit').disabled, { message: 'the core recorded the step (undoEdit)' });
    await win.click('#undoEdit');
    await win.waitFor(() => Object.keys(JSON.parse(localStorage.getItem('horizonStudio_v02')).source_overrides).length === 0, { message: 'undo' });
  } finally {
    await win.close();
  }
});

scenario('a cancelled save dialog writes nothing', async () => {
  const box = scratch();
  const win = await open({ ...box.env, HORIZON_STUDIO_E2E_CANCEL_SAVE: '1' });
  try {
    await editorReady(win);
    await fresh(win);
    await loadDemo(win);
    await win.click('#exportHmod');
    await waitStatus(win, 'saveCancelled');
    assert.deepEqual(fs.readdirSync(box.saves), []);
  } finally {
    await win.close();
  }
});

scenario('switches EN/RU, explores the development journey and refuses an export the engine cannot load', async () => {
  const box = scratch();
  const win = await open(box.env);
  try {
    await editorReady(win);
    await fresh(win);
    await loadDemo(win);
    await win.waitFor(() => document.querySelectorAll('#engineCapabilities li.cap-ok').length >= 5, { message: 'capability diagnostics' });
    await win.click('#lang-ru');
    assert.equal(await win.run(() => document.documentElement.lang), 'ru');
    assert.equal(await content(win, '#saveProject'), await t(win, 'saveProject'));
    await win.click('#openJourney');
    await win.waitFor(() => document.querySelectorAll('.jr-card').length > 0, { message: 'journey explorer' });
    await win.click('.jr-phase[data-phase="F5"]');
    assert.ok((await content(win, '#milestoneList')).includes('HS-025'));
    await win.click('#closeJourney');
    assert.equal(await win.run(() => document.querySelector('#journeyDialog').hidden), true);
    await win.click('#lang-en');
    // A project targeting a revision without a profile keeps its data but cannot be exported.
    await win.click('#saveProject');
    await waitStatus(win, 'projectSaved');
    const file = path.join(box.saves, 'ruby_demo.hstudio.json');
    const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
    fs.unlinkSync(file);
    saved.target = { engine: 'horizon', revision: 'f'.repeat(40) };
    await openProject(win, saved);
    await win.waitFor(() => /ffffff/.test(document.querySelector('#engineTargetSelect').selectedOptions[0]?.textContent || ''), { message: 'unknown target' });
    const before = await state(win);
    await win.click('#exportHmod');
    await win.waitFor(() => document.querySelector('#status').classList.contains('error'), { message: 'refused export' });
    assert.match(await status(win), /ffffffff/);
    assert.deepEqual(fs.readdirSync(box.saves), []);
    assert.deepEqual(await state(win), before);
  } finally {
    await win.close();
  }
});

scenario('a restarted window reopens the last project and the chosen language from the core', async () => {
  const box = scratch();
  let win = await open(box.env);
  try {
    await editorReady(win);
    await fresh(win);
    await loadDemo(win);
    await win.click('#itemTab');
    await win.click('[data-edit="0"]');
    await win.type('#entryName', 'Restart Ruby');
    await win.click('#addObject');
    await waitStatus(win, 'savedEntry');
    await until(() => diskHas(path.join(box.home, '.horizon-studio', 'workspaces'), 'Restart Ruby'), 'the disk autosave');
    await win.click('#lang-ru');
    await until(() => fs.existsSync(path.join(box.home, '.horizon-studio', 'prefs.json'))
      && JSON.parse(fs.readFileSync(path.join(box.home, '.horizon-studio', 'prefs.json'), 'utf8')).lang === 'ru', 'the language preference');
  } finally {
    await win.close();
  }
  win = await open(box.env);
  try {
    await editorReady(win);
    await fresh(win);  // the window's own storage is gone, as after a real restart (a new core port)
    await win.waitFor(() => document.querySelector('#workspaceSaveStatus').dataset.key === 'workspaceSaved'
      && (JSON.parse(localStorage.getItem('horizonStudio_v02')) || {}).metadata?.id === 'ruby_demo', { message: 'the last project reopened' });
    assert.equal((await state(win)).items[0].name, 'Restart Ruby');
    assert.equal(await win.run(() => document.documentElement.lang), 'ru', 'the chosen language came back');
  } finally {
    await win.close();
  }
});

scenario('reloading the window brings the editor back every time', async () => {
  // People can reload the desktop window (F5); each reload must end in a working editor attached to the core.
  const box = scratch();
  const win = await open(box.env);
  try {
    await editorReady(win);
    for (let i = 0; i < 12; i++) await reload(win);
    // Still attached to the core after the last reload: the demo loads and its workspace is saved.
    await loadDemo(win);
    await win.waitFor(() => document.querySelector('#workspaceSaveStatus').dataset.key === 'workspaceSaved',
      { message: 'the workspace saved after the reloads' });
  } finally {
    await win.close();
  }
});

scenario('a core that dies under the editor takes the window back to the failure screen', async () => {
  const box = scratch();
  const before = new Set(corePids());
  const win = await open(box.env);
  try {
    await editorReady(win);
    const mine = corePids().filter(pid => !before.has(pid));
    assert.equal(mine.length, 1);
    process.kill(mine[0]);
    await win.waitFor(() => document.querySelector('#failure') && !document.querySelector('#failure').hidden, { message: 'failure screen' });
    assert.match(await content(win, '#failureMessage'), /stopped unexpectedly/);
    assert.match(await win.run(() => location.href), /^(tauri:\/\/localhost|http:\/\/tauri\.localhost)(\/|$)/);
  } finally {
    await win.close();
  }
});

scenario('a core that cannot start shows the failure screen instead of a blank window', async () => {
  const box = scratch();
  const win = await open({ ...box.env, HORIZON_STUDIO_E2E_CORE: path.join(box.home, 'missing-core') });
  try {
    await win.waitFor(() => document.querySelector('#failure') && !document.querySelector('#failure').hidden, { message: 'failure screen' });
    const message = await win.text('#failureMessage');
    assert.match(message, /core/i);
    assert.match(await win.run(() => location.href), /^(tauri:\/\/localhost|https?:\/\/tauri\.localhost)(\/|$)/);
  } finally {
    await win.close();
  }
});
