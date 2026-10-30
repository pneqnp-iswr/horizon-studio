'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const { createWorkspaceSync } = require('../editor_workspace.js');

/** In-memory stand-in for /api/workspace/{recover,write} with the server's revision rules. */
function fakeServer() {
  const server = { disk: new Map(), requests: [], gate: null, fail: null };
  const reply = (status, body) => ({ status, ok: status < 400, json: async () => body });
  server.post = async (path, raw) => {
    const body = JSON.parse(raw);
    server.requests.push({ path, body });
    if (server.gate) await server.gate;
    if (server.fail) return reply(500, { error: server.fail });
    if (path === '/api/workspace/recover') {
      const entry = server.disk.get(body.project_id);
      return entry ? reply(200, { ...entry, recovered_from_backup: false }) : reply(404, { error: 'missing' });
    }
    const id = body.state.metadata.id;
    const current = server.disk.get(id);
    if ((current ? current.revision : null) !== body.expected_revision) return reply(409, { error: 'conflict' });
    const revision = `r${server.requests.length}`;
    server.disk.set(id, { state: body.state, revision });
    return reply(200, { revision });
  };
  return server;
}

function setup({ id = 'demo', items = ['a'] } = {}) {
  const server = fakeServer();
  const editor = { state: { metadata: { id }, items: [...items] } };
  const notices = [];
  const timers = new Map();
  let next = 0;
  const sync = createWorkspaceSync({
    post: server.post,
    snapshot: () => structuredClone(editor.state),
    projectId: () => editor.state.metadata.id,
    isValidId: value => /^[a-z][a-z0-9_]*$/.test(value),
    apply: state => { editor.state = structuredClone(state); },
    notify: (key, values) => notices.push(values.error ? `${key}:${values.error}` : key),
    schedule: fn => { timers.set(++next, fn); return next; },
    cancel: handle => timers.delete(handle),
  });
  const runTimers = async () => {
    const pending = [...timers.values()];
    timers.clear();
    pending.forEach(fn => fn());
    await sync.idle();
  };
  return { server, editor, notices, sync, timers, runTimers };
}

test('a new project is saved to disk after the debounce', async () => {
  const { server, editor, notices, sync, runTimers } = setup();
  await sync.begin();
  assert.equal(sync.mode, 'ready');
  assert.deepEqual(notices, ['workspaceChecking', 'workspacePending']);
  await runTimers();
  assert.deepEqual(server.disk.get('demo').state, editor.state);
  assert.equal(sync.revision, server.disk.get('demo').revision);
  assert.equal(notices.at(-1), 'workspaceSaved');
});

test('an identical disk copy is adopted without writing', async () => {
  const { server, editor, notices, sync } = setup();
  server.disk.set('demo', { state: structuredClone(editor.state), revision: 'r0' });
  await sync.begin();
  assert.equal(sync.mode, 'ready');
  assert.equal(sync.revision, 'r0');
  assert.equal(notices.at(-1), 'workspaceSaved');
  assert.ok(server.requests.every(r => r.path.endsWith('/recover')));
});

test('a different disk copy waits for an explicit choice; restore loads it', async () => {
  const { server, editor, notices, sync, timers, runTimers } = setup();
  server.disk.set('demo', { state: { metadata: { id: 'demo' }, items: ['disk'] }, revision: 'r0' });
  await sync.begin();
  assert.equal(sync.mode, 'conflict');
  assert.equal(notices.at(-1), 'workspaceRecoverable');
  sync.scheduleSave();
  assert.equal(timers.size, 0, 'no autosave while the conflict is open');
  await sync.restoreDisk();
  assert.deepEqual(editor.state.items, ['disk']);
  assert.equal(sync.mode, 'ready');
  assert.equal(notices.at(-1), 'workspaceRecovered');
  await runTimers();
  assert.equal(server.disk.get('demo').revision, 'r0', 'restoring must not rewrite the disk copy');
});

test('keep editor overwrites the disk copy against its current revision', async () => {
  const { server, editor, sync, runTimers } = setup();
  server.disk.set('demo', { state: { metadata: { id: 'demo' }, items: ['disk'] }, revision: 'r0' });
  await sync.begin();
  await sync.keepEditor();
  await runTimers();
  assert.deepEqual(server.disk.get('demo').state, editor.state);
  const write = server.requests.find(r => r.path.endsWith('/write'));
  assert.equal(write.body.expected_revision, 'r0');
});

test('a write rejected with 409 opens the conflict instead of retrying', async () => {
  const { server, editor, notices, sync, runTimers } = setup();
  await sync.begin();
  await runTimers();
  server.disk.set('demo', { state: { metadata: { id: 'demo' }, items: ['other tab'] }, revision: 'other' });
  editor.state.items.push('b');
  sync.scheduleSave();
  await runTimers();
  assert.equal(sync.mode, 'conflict');
  assert.equal(notices.at(-1), 'workspaceRecoverable');
  assert.deepEqual(server.disk.get('demo').state.items, ['other tab']);
});

test('an invalid project id never touches the disk', async () => {
  const { server, notices, sync } = setup({ id: 'Bad Id' });
  await sync.begin();
  assert.equal(sync.mode, 'invalid');
  assert.deepEqual(notices, ['workspaceInvalidId']);
  assert.equal(server.requests.length, 0);
});

test('a queued write for a previous project is dropped after switching projects', async () => {
  const { server, editor, sync, timers } = setup();
  await sync.begin();
  let release;
  server.gate = new Promise(resolve => { release = resolve; });
  [...timers.values()][0]();  // the debounced write starts and waits on the server
  timers.clear();
  editor.state = { metadata: { id: 'second' }, items: [] };
  const switching = sync.begin();
  release();
  server.gate = null;
  await switching;
  await sync.idle();
  assert.equal(sync.id, 'second');
  assert.equal(sync.mode, 'ready');
  assert.equal(sync.revision, null, "the old project's write result must not leak into the new session");
  assert.ok(!server.disk.has('second'), 'nothing is written for the new project before its own debounce');
});

test('server errors are reported with their message', async () => {
  const { server, notices, sync, runTimers } = setup();
  await sync.begin();
  server.fail = 'disk full';
  await runTimers();
  assert.equal(notices.at(-1), 'workspaceError:disk full');
  server.fail = 'unreachable';
  await sync.begin();
  assert.equal(sync.mode, 'unavailable');
  assert.equal(notices.at(-1), 'workspaceError:unreachable');
});
