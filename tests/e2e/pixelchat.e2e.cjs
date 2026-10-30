'use strict';
/* Real two-Chromium-context PixelChat integration check in GitHub CI. */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const path = require('node:path');
const crypto = require('node:crypto');
const { test } = require('node:test');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const ANIMATED_GIF = Buffer.from(
  'R0lGODlhCAAIAIEAAPUjWgAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQAFAAAACwAAAAACAAIAAAIDwABCBxIsKDBgwgTKkwYEAAh+QQAFAAAACwAAAAACAAIAIEg3IoAAAAAAAAAAAAIDwABCBxIsKDBgwgTKkwYEAA7',
  'base64',
);

async function boot() {
  const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const proc = spawn(python, ['-u', '-m', 'pixelchat.demo_server', '--port', '0'], {
    cwd: ROOT, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  const base = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('PixelChat startup timeout: ' + output)), 15000);
    const listener = chunk => {
      output += chunk.toString();
      const port = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (port) { clearTimeout(timeout); resolve('http://127.0.0.1:' + port[1]); }
    };
    proc.stdout.on('data', listener);
    proc.stderr.on('data', listener);
    proc.on('exit', code => { clearTimeout(timeout); reject(new Error('PixelChat server quit with ' + code + ': ' + output)); });
  });
  return { proc, base, output: () => output };
}

async function join(page, name) {
  await page.fill('#name', name);
  await page.click('#join');
  await page.waitForSelector('#shell:not(.hidden)');
}

test('two real Chromium clients share animated GIF and pixel emoji with auth and reduced-motion fallback', { timeout: 45000 }, async () => {
  const server = await boot();
  let browser;
  let alice;
  let bob;
  try {
    browser = await chromium.launch();
    alice = await browser.newContext();
    bob = await browser.newContext();
    const pageA = await alice.newPage();
    const pageB = await bob.newPage();
    const errors = [];
    for (const page of [pageA, pageB]) page.on('pageerror', error => errors.push(error.message));
    await Promise.all([pageA.goto(server.base), pageB.goto(server.base)]);
    await Promise.all([join(pageA, 'Alice'), join(pageB, 'Bob')]);

    await pageA.setInputFiles('#file', { name: 'original-2frame.gif', mimeType: 'image/gif', buffer: ANIMATED_GIF });
    await pageA.waitForFunction(() => document.querySelector('#preview').textContent.includes('2 frame(s)'));
    await pageA.fill('#text', 'Hi, Bob! :heart:');
    await pageA.locator('#composer button[type="submit"]').click();
    await pageB.waitForFunction(() => {
      const bubble = document.querySelector('.bubble');
      const img = bubble?.querySelector('img');
      return bubble?.textContent.includes('Alice') && img?.src.startsWith('blob:') && img.complete && img.naturalWidth === 8;
    }, null, { timeout: 15000 });
    assert.equal(await pageB.locator('.bubble').count(), 1);
    assert.equal(await pageB.locator('.content canvas').count(), 1);
    assert.equal(await pageB.locator('.bubble img').getAttribute('alt'), 'Shared GIF/image');

    await pageB.bringToFront();
    const hashes = new Set();
    const gifImage = pageB.locator('.bubble img');
    for (let i = 0; i < 32; i++) {
      // Screenshot the actually painted GIF, not drawImage's possibly static source snapshot.
      const png = await gifImage.screenshot({ animations: 'allow' });
      hashes.add(crypto.createHash('sha256').update(png).digest('hex'));
      if (hashes.size > 1) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(hashes.size > 1, 'The browser must paint more than one GIF frame in 3.2 seconds');

    await pageB.locator('#reduce').check();
    await pageB.waitForFunction(() => document.querySelector('.bubble')?.textContent.includes('[image paused:'));
    assert.equal(await pageB.locator('.bubble img').count(), 0);
    assert.deepEqual(errors, [], 'browser JavaScript must not throw');
  } catch (error) {
    throw new Error(error.message + '\nPixelChat output:\n' + server.output());
  } finally {
    await alice?.close().catch(() => {});
    await bob?.close().catch(() => {});
    await browser?.close().catch(() => {});
    server.proc.kill();
  }
});
