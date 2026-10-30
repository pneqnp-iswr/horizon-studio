'use strict';
/* Browser E2E harness: a real Studio server per test, isolated HOME, Playwright Chromium.
 * Failure artifacts (screenshot + trace) go to test-results/e2e/ and contain only
 * the synthetic projects created by the tests. */
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const { test, before, after } = require('node:test');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const ARTIFACTS = process.env.E2E_ARTIFACTS || path.join(ROOT, 'test-results', 'e2e');
// Package accepted by the real cargo-horizon-mod at Horizon d2186eb (docs/COMPATIBILITY_EVIDENCE.md).
const OFFICIAL_RUBY_SHA256 = 'ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2';

async function startStudio() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'horizon-studio-e2e-'));
  const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const child = spawn(python, ['studio.py', '0'], {
    cwd: ROOT,
    env: { ...process.env, HOME: home, USERPROFILE: home, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Studio did not start:\n${log}`)), 20000);
    child.stdout.on('data', chunk => {
      log += chunk;
      const match = log.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(`http://127.0.0.1:${match[1]}`); }
    });
    child.stderr.on('data', chunk => { log += chunk; });
    child.on('exit', code => { clearTimeout(timer); reject(new Error(`Studio exited with ${code}:\n${log}`)); });
  });
  const workspaceDir = path.join(home, '.horizon-studio', 'workspaces');
  return {
    url, home, workspaceDir,
    log: () => log,
    workspaceFile(projectId) {
      return path.join(workspaceDir, crypto.createHash('sha256').update(projectId).digest('hex') + '.hstudio.json');
    },
    async stop() {
      if (child.exitCode === null) {
        const exited = new Promise(resolve => child.once('exit', resolve));
        child.kill();
        await exited;
      }
      fs.rmSync(home, { recursive: true, force: true });
    },
  };
}

let browser;
before(async () => { browser = await chromium.launch(); });
after(async () => { await browser?.close(); });

async function openSession(studio, { viewport = { width: 1440, height: 900 } } = {}) {
  const context = await browser.newContext({ viewport, acceptDownloads: true });
  await context.tracing.start({ screenshots: true, snapshots: true });
  const errors = [];
  const open = async () => {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
    // HTTP failures are judged from responses below; the browser also logs them to the console.
    page.on('console', message => {
      if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) errors.push(`console: ${message.text()}`);
    });
    // API 4xx answers (404 no workspace yet, 409 conflict, 400 validation) are part of the protocol
    // and tests assert how the UI handles them. Static-file failures and server errors are bugs.
    page.on('response', response => {
      const url = new URL(response.url());
      if (response.status() >= 500 || (response.status() >= 400 && !url.pathname.startsWith('/api/'))) {
        errors.push(`http ${response.status()} ${url.pathname}`);
      }
    });
    await page.goto(studio.url + '/');
    await page.waitForFunction(() => window.HorizonI18n && document.querySelector('#workspaceSaveStatus').dataset.key);
    return page;
  };
  return { context, errors, page: await open(), open };
}

/** A test with its own server and browser context; saves artifacts on failure. */
function e2e(name, body, options = {}) {
  test(name, async () => {
    const studio = await startStudio();
    const extra = [];
    const session = await openSession(studio, options);
    const another = async () => {
      const second = await openSession(studio, options);
      extra.push(second);
      return second;
    };
    try {
      await body({ studio, ...session, another });
      const errors = [session, ...extra].flatMap(s => s.errors);
      if (errors.length) throw new Error('Unexpected browser errors:\n' + errors.join('\n'));
      await session.context.tracing.stop();
    } catch (error) {
      const slug = name.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
      fs.mkdirSync(ARTIFACTS, { recursive: true });
      await session.page.screenshot({ path: path.join(ARTIFACTS, `${slug}.png`), fullPage: true }).catch(() => {});
      await session.context.tracing.stop({ path: path.join(ARTIFACTS, `${slug}-trace.zip`) }).catch(() => {});
      fs.writeFileSync(path.join(ARTIFACTS, `${slug}-server.log`), studio.log());
      throw error;
    } finally {
      for (const s of [session, ...extra]) await s.context.close().catch(() => {});
      await studio.stop();
    }
  });
}

// -- page helpers ------------------------------------------------------------

const t = (page, key, values = {}) => page.evaluate(([k, v]) => window.HorizonI18n.t(k, v), [key, values]);
const editorState = page => page.evaluate(() => JSON.parse(localStorage.getItem('horizonStudio_v02')));
const workspaceKey = page => page.$eval('#workspaceSaveStatus', el => el.dataset.key);

async function waitWorkspace(page, key, timeout = 10000) {
  await page.waitForFunction(k => document.querySelector('#workspaceSaveStatus').dataset.key === k, key, { timeout });
}

async function waitStatus(page, text) {
  await page.waitForFunction(expected => document.querySelector('#status').textContent === expected, text);
}

async function download(page, selector) {
  const [file] = await Promise.all([page.waitForEvent('download'), page.click(selector)]);
  return fs.readFileSync(await file.path());
}

/** Read a ZIP archive (stored or deflated entries) into {name: Buffer}. */
function readZip(buffer) {
  const end = buffer.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (end < 0) throw new Error('Not a ZIP archive');
  const count = buffer.readUInt16LE(end + 10);
  let offset = buffer.readUInt32LE(end + 16);
  const files = {};
  for (let i = 0; i < count; i++) {
    const method = buffer.readUInt16LE(offset + 10);
    const size = buffer.readUInt32LE(offset + 20);
    const nameLength = buffer.readUInt16LE(offset + 28);
    const extraLength = buffer.readUInt16LE(offset + 30);
    const commentLength = buffer.readUInt16LE(offset + 32);
    const local = buffer.readUInt32LE(offset + 42);
    const name = buffer.toString('utf8', offset + 46, offset + 46 + nameLength);
    const dataStart = local + 30 + buffer.readUInt16LE(local + 26) + buffer.readUInt16LE(local + 28);
    const raw = buffer.subarray(dataStart, dataStart + size);
    files[name] = method === 8 ? zlib.inflateRawSync(raw) : Buffer.from(raw);
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return files;
}

/** Wait until the on-disk workspace document satisfies ``predicate``. */
async function waitDisk(studio, projectId, predicate, timeout = 10000) {
  const file = studio.workspaceFile(projectId);
  const deadline = Date.now() + timeout;
  let last = null;
  while (Date.now() < deadline) {
    try {
      last = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (predicate(last)) return last;
    } catch (_) { /* not written yet */ }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Disk workspace ${file} did not reach the expected state; last: ${JSON.stringify(last)?.slice(0, 400)}`);
}

const objectIds = doc => doc.objects.map(o => o.id);
const sha256 = buffer => crypto.createHash('sha256').update(buffer).digest('hex');

module.exports = {
  ROOT, OFFICIAL_RUBY_SHA256, e2e, t, editorState, workspaceKey, waitWorkspace, waitStatus, download, readZip,
  waitDisk, objectIds, sha256,
};
