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
const { launch, sleep } = require('./webdriver.cjs');

const APP = process.env.DESKTOP_APP;
const OFFICIAL_RUBY_SHA256 = 'ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2';
const scenario = (name, body) => test(name, { skip: !APP && 'set DESKTOP_APP to an e2e build of the shell', timeout: 240000 }, body);

function scratch() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'hs-desktop-e2e-'));
  const saves = path.join(home, 'saves');
  fs.mkdirSync(saves);
  return { home, saves, env: { HOME: home, USERPROFILE: home, HORIZON_STUDIO_E2E_SAVE_DIR: saves } };
}

function coreProcesses() {
  if (process.platform === 'win32') {
    return execFileSync('tasklist', ['/FO', 'CSV', '/NH'], { encoding: 'utf8' })
      .split(/\r?\n/).filter(line => /horizon-studio-core\.exe/i.test(line)).length;
  }
  return execFileSync('ps', ['-eo', 'args'], { encoding: 'utf8' })
    .split('\n').filter(line => /horizon-studio-core|launcher\.py --serve/.test(line)).length;
}

async function open(env, extra = {}) {
  const win = await launch({ app: APP, env, ...extra });
  return win;
}

async function editorReady(win) {
  await win.waitFor(() => Boolean(window.HorizonDesktop && window.HorizonDesktop.available()
    && document.querySelector('#workspaceSaveStatus')?.dataset.key && document.body.dataset.shell),
  { message: 'the editor inside the desktop shell' });
}

async function fresh(win) {
  // WebView storage can outlive a test on Windows (it lives in the user's profile); start clean.
  await win.run(() => { localStorage.clear(); setTimeout(() => location.reload(), 0); return true; });
  await sleep(800);
  await editorReady(win);
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
    return entry.isDirectory() ? diskHas(full, text) : fs.readFileSync(full, 'utf8').includes(text);
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
    await win.click('#undoEdit');
    await win.waitFor(() => JSON.parse(localStorage.getItem('horizonStudio_v02')).items[0].id === 'opal', { message: 'undo' });
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

scenario('a restarted window recovers the disk workspace', async () => {
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
  } finally {
    await win.close();
  }
  win = await open(box.env);
  try {
    await editorReady(win);
    await fresh(win);  // only the disk workspace may remain
    await win.type('#modId', 'ruby_demo');
    await win.run(() => { document.querySelector('#modId').dispatchEvent(new Event('change')); return true; });
    await win.waitFor(() => document.querySelector('#workspaceSaveStatus').dataset.key === 'workspaceRecoverable', { message: 'restore offer' });
    await win.click('#restoreWorkspace');
    await win.waitFor(() => document.querySelector('#workspaceSaveStatus').dataset.key === 'workspaceRecovered', { message: 'recovered' });
    assert.equal((await state(win)).items[0].name, 'Restart Ruby');
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
