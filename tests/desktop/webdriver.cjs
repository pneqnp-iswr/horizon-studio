'use strict';
/* A small W3C WebDriver client for driving the real Horizon Studio desktop window through
 * tauri-driver (WebKitWebDriver on Linux, msedgedriver for WebView2 on Windows). No
 * dependencies: plain HTTP JSON against the driver. */
const { spawn } = require('node:child_process');
const http = require('node:http');
const net = require('node:net');

const ELEMENT = 'element-6066-11e4-a52e-4f735466cecf';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

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

/** Starts tauri-driver (and through it the app) and opens a session on the real window. */
async function launch({ app, env = {}, args = [], driver = process.env.TAURI_DRIVER || 'tauri-driver', nativeDriver = process.env.NATIVE_DRIVER }) {
  const port = await freePort();
  const nativePort = await freePort();
  const driverArgs = ['--port', String(port), '--native-port', String(nativePort)];
  if (nativeDriver) driverArgs.push('--native-driver', nativeDriver);
  const child = spawn(driver, driverArgs, { env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  child.stdout.on('data', chunk => { log += chunk; });
  child.stderr.on('data', chunk => { log += chunk; });
  const deadline = Date.now() + 30000;
  for (;;) {
    try { await request(port, 'GET', '/status'); break; } catch (error) {
      if (Date.now() > deadline || child.exitCode !== null) throw new Error(`tauri-driver did not start: ${log}`);
      await sleep(200);
    }
  }
  const session = await request(port, 'POST', '/session', {
    capabilities: { alwaysMatch: { 'tauri:options': { application: app, args } } },
  });
  return new Window(port, session.sessionId, child, () => log);
}

class Window {
  constructor(port, id, child, log) { Object.assign(this, { port, id, child, log }); }
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
      if (Date.now() > deadline) throw new Error(`Timed out waiting for ${message} (last: ${JSON.stringify(last)})`);
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
    if (this.child.exitCode === null) {
      const exited = new Promise(resolve => this.child.once('exit', resolve));
      this.child.kill();
      await Promise.race([exited, sleep(5000)]);
    }
  }
}

module.exports = { launch, sleep };
