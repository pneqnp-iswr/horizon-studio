'use strict';
/* A small W3C WebDriver client for driving the real Horizon Studio desktop window. No
 * dependencies: plain HTTP JSON against the driver.
 *  - Linux: tauri-driver, which starts the app through WebKitWebDriver.
 *  - Windows: the app is started here with a WebView2 DevTools port (test builds only, cargo
 *    feature `e2e`) and msedgedriver attaches to it (`debuggerAddress`). Letting msedgedriver
 *    start the app failed in CI ("DevToolsActivePort file doesn't exist"), most likely because
 *    the app's own WebView2 arguments take the place of WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS. */
const { execFile, spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const net = require('node:net');

const ELEMENT = 'element-6066-11e4-a52e-4f735466cecf';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
// Every driver started, so a scenario that times out cannot leave one running (and keep Node alive).
const drivers = new Set();

function stopAll() {
  for (const child of drivers) {
    if (child.exitCode === null) child.kill();
    drivers.delete(child);
  }
}
process.on('exit', stopAll);

function request(port, method, path, body) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? undefined : Buffer.from(JSON.stringify(body));
    const req = http.request({ host: '127.0.0.1', port, method, path,
      headers: data ? { 'Content-Type': 'application/json', 'Content-Length': data.length } : {} }, res => {
      let raw = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { raw += chunk; });
      res.on('end', () => {
        let parsed = {};
        try { parsed = raw ? JSON.parse(raw) : {}; } catch (_) { parsed = { value: { error: 'invalid json', message: raw } }; }
        if (res.statusCode >= 400) {
          const error = new Error(`${method} ${path}: ${parsed.value?.error || res.statusCode} ${parsed.value?.message || ''}`.trim());
          error.status = res.statusCode;
          return reject(error);
        }
        resolve(parsed.value);
      });
    });
    req.on('error', reject);
    req.setTimeout(120000, () => req.destroy(new Error(`${method} ${path} timed out`)));
    if (data) req.write(data);
    req.end();
  });
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => { const { port } = server.address(); server.close(() => resolve(port)); });
    server.on('error', reject);
  });
}

async function waitHttp(port, route, child, what, log, timeout = 60000) {
  const deadline = Date.now() + timeout;
  for (;;) {
    try { await request(port, 'GET', route); return; } catch (error) {
      if (Date.now() > deadline || child.exitCode !== null) throw new Error(`${what} did not start: ${log()}`);
      await sleep(200);
    }
  }
}

function track(child) {
  drivers.add(child);
  child.once('exit', () => drivers.delete(child));
  return child;
}

/** Windows: start the app with a DevTools port and attach msedgedriver to its WebView2. */
async function launchWebView2({ app, env, args, nativeDriver }) {
  let log = '';
  const collect = chunk => { log += chunk; };
  const devtools = await freePort();
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'hs-webview-'));
  const program = track(spawn(app, args, {
    env: { ...process.env, ...env, HORIZON_STUDIO_E2E_DEVTOOLS_PORT: String(devtools), HORIZON_STUDIO_E2E_WEBVIEW_DATA: data },
    stdio: 'ignore',
  }));
  await waitHttp(devtools, '/json/version', program, 'The WebView2 DevTools port', () => log);
  const port = await freePort();
  const driver = track(spawn(nativeDriver || 'msedgedriver', [`--port=${port}`], { stdio: ['ignore', 'pipe', 'pipe'] }));
  driver.stdout.on('data', collect);
  driver.stderr.on('data', collect);
  try {
    await waitHttp(port, '/status', driver, 'msedgedriver', () => log, 30000);
    const session = await request(port, 'POST', '/session', {
      capabilities: { alwaysMatch: { browserName: 'webview2', 'ms:edgeOptions': { debuggerAddress: `127.0.0.1:${devtools}` } } },
    });
    return new Window(port, session.sessionId, driver, () => log, program);
  } catch (error) {
    driver.kill();
    program.kill();
    throw new Error(`${error.message}\n${log}`);
  }
}

/** Starts the app and opens a WebDriver session on its real window. */
async function launch({ app, env = {}, args = [], driver = process.env.TAURI_DRIVER || 'tauri-driver', nativeDriver = process.env.NATIVE_DRIVER }) {
  if (process.platform === 'win32') return launchWebView2({ app, env, args, nativeDriver });
  const port = await freePort();
  const nativePort = await freePort();
  const driverArgs = ['--port', String(port), '--native-port', String(nativePort)];
  if (nativeDriver) driverArgs.push('--native-driver', nativeDriver);
  const child = spawn(driver, driverArgs, { env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe'] });
  drivers.add(child);
  child.once('exit', () => drivers.delete(child));
  let log = '';
  child.stdout.on('data', chunk => { log += chunk; });
  child.stderr.on('data', chunk => { log += chunk; });
  const deadline = Date.now() + 30000;
  for (;;) {
    try { await request(port, 'GET', '/status'); break; } catch (error) {
      if (Date.now() > deadline || child.exitCode !== null) {
        child.kill();
        throw new Error(`tauri-driver did not start: ${log}`);
      }
      await sleep(200);
    }
  }
  let session;
  try {
    session = await request(port, 'POST', '/session', {
      capabilities: { alwaysMatch: { 'tauri:options': { application: app, args } } },
    });
  } catch (error) {
    child.kill();
    throw new Error(`${error.message}\n${log}`);
  }
  return new Window(port, session.sessionId, child, () => log);
}

class Window {
  constructor(port, id, child, log, program = null) { Object.assign(this, { port, id, child, log, program }); }
  call(method, path, body) { return request(this.port, method, `/session/${this.id}${path}`, body); }

  /** Runs a function in the page; `fn` is serialized, so it must be self-contained. */
  async run(fn, ...args) {
    return this.call('POST', '/execute/sync', { script: `return (${fn}).apply(null, arguments);`, args });
  }

  async waitFor(fn, { timeout = 60000, interval = 150, message = 'condition' } = {}, ...args) {
    const deadline = Date.now() + timeout;
    let last;
    for (;;) {
      try {
        last = await this.run(fn, ...args);
        if (last) return last;
      } catch (error) { last = error.message; }
      if (Date.now() > deadline) {
        let page = 'unknown';
        try { page = JSON.stringify(await this.run(() => ({ href: location.href, ready: document.readyState, title: document.title }))); } catch (error) { page = error.message; }
        throw new Error(`Timed out waiting for ${message} (last: ${JSON.stringify(last)}; page: ${page})\n${this.log().slice(-2000)}`);
      }
      await sleep(interval);
    }
  }

  async element(css) {
    const found = await this.call('POST', '/element', { using: 'css selector', value: css });
    return found[ELEMENT];
  }

  async click(css) { await this.call('POST', `/element/${await this.element(css)}/click`, {}); }

  async type(css, text) {
    const id = await this.element(css);
    await this.call('POST', `/element/${id}/clear`, {});
    await this.call('POST', `/element/${id}/value`, { text });
  }

  async text(css) { return this.call('GET', `/element/${await this.element(css)}/text`); }

  async close() {
    try { await this.call('DELETE', ''); } catch (_) { /* the window may already be gone */ }
    if (this.program && this.program.exitCode === null) {
      // Close the window the way a person would (WM_CLOSE), so the shell stops its core itself.
      const exited = new Promise(resolve => this.program.once('exit', resolve));
      execFile('taskkill', ['/PID', String(this.program.pid)], () => {});
      if (await Promise.race([exited.then(() => true), sleep(15000).then(() => false)]) === false) {
        execFile('taskkill', ['/PID', String(this.program.pid), '/T', '/F'], () => {});
      }
    }
    if (this.child.exitCode === null) {
      const exited = new Promise(resolve => this.child.once('exit', resolve));
      this.child.kill();
      await Promise.race([exited, sleep(5000)]);
    }
  }
}

module.exports = { launch, sleep, stopAll };
