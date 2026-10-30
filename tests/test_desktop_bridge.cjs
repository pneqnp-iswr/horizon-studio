'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const bridge = require('../desktop_bridge.js');

function fakeShell(reply) {
  const calls = [];
  return { calls, __TAURI_INTERNALS__: { invoke: async (...args) => { calls.push(args); return reply; } } };
}

test('a plain browser is not the desktop shell and calls fail visibly', async () => {
  assert.equal(bridge.available({}), false);
  await assert.rejects(bridge.ready({}, {}), /desktop shell/);
  await assert.rejects(bridge.saveFile(new Blob(['x']), 'a.hmod', {}), /desktop shell/);
});

test('saveFile sends raw bytes and an encoded file name to the save_file command', async () => {
  const shell = fakeShell({ saved: true, name: 'my mod.hmod' });
  assert.equal(bridge.available(shell), true);
  const result = await bridge.saveFile(new Blob([new Uint8Array([80, 75, 3, 4])]), 'my mod.hmod', shell);
  assert.deepEqual(result, { saved: true, name: 'my mod.hmod' });
  const [[command, body, options]] = shell.calls;
  assert.equal(command, 'save_file');
  assert.ok(body instanceof Uint8Array);
  assert.deepEqual([...body], [80, 75, 3, 4]);
  assert.deepEqual(options, { headers: { 'x-file-name': 'my%20mod.hmod' } });
});

test('ready passes the editor info to desktop_ready', async () => {
  const shell = fakeShell({ shell: '0.7.0' });
  assert.deepEqual(await bridge.ready({ lang: 'ru' }, shell), { shell: '0.7.0' });
  assert.deepEqual(shell.calls[0].slice(0, 2), ['desktop_ready', { info: { lang: 'ru' } }]);
});
