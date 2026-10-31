'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const { createWorkspaceSync } = require('../editor_workspace.js');

/** In-memory stand-in for the core's transaction commands (/api/tx/*, /api/ai/*) with its
 * revision rules: every command names its base revision; anything else is a 409. The real core is
 * covered by tests/test_transactions.py and the browser suite. */
function fakeCore() {
  const core = { projects: new Map(), requests: [], gate: null, fail: null, proposals: new Map(), seq: 0 };
  const reply = (status, body) => ({ status, ok: status < 400, json: async () => body });
  const view = p => ({ undo: p.entries.slice(0, p.cursor).reverse().map(e => ({ label: e.label })),
    redo: p.entries.slice(p.cursor).map(e => ({ label: e.label })) });
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const conflict = p => reply(409, { error: 'conflict', code: 'REVISION_CONFLICT', revision: p ? p.revision : null });
  core.put = (id, state) => {
    const revision = `r${++core.seq}`;
    core.projects.set(id, { state: structuredClone(state), revision, entries: [], cursor: 0 });
    return revision;
  };
  core.post = async (path, raw) => {
    const body = JSON.parse(raw);
    core.requests.push({ path, body });
    if (core.gate) await core.gate;
    if (core.fail) return reply(500, { error: core.fail });
    const id = body.project_id ?? body.state?.metadata?.id;
    const p = core.projects.get(id);
    if (path === '/api/tx/open') {
      if (!p) return reply(404, { error: 'missing', code: 'NOT_FOUND' });
      return reply(200, { state: p.state, revision: p.revision, history: view(p), recovered_from_backup: false,
        ...('state' in body ? { matches: same(body.state, p.state) } : {}) });
    }
    if (path === '/api/tx/commit') {
      if (!p) {
        if (body.base_revision !== null) return conflict(null);
        core.put(id, body.state);
        const made = core.projects.get(id);
        return reply(200, { state: made.state, revision: made.revision, history: view(made), entry: null });
      }
      if (body.base_revision !== p.revision) return conflict(p);
      if (same(body.state, p.state)) return reply(200, { state: p.state, revision: p.revision, history: view(p), entry: null });
      p.entries.splice(p.cursor);
      p.entries.push({ label: body.label || 'edit', before: p.state, after: structuredClone(body.state) });
      p.cursor = p.entries.length;
      p.state = structuredClone(body.state);
      p.revision = `r${++core.seq}`;
      return reply(200, { state: p.state, revision: p.revision, history: view(p), entry: { label: body.label || 'edit' } });
    }
    if (path === '/api/tx/undo' || path === '/api/tx/redo') {
      if (body.expected_revision !== p.revision) return conflict(p);
      const back = path.endsWith('undo');
      if (back ? p.cursor === 0 : p.cursor === p.entries.length) {
        return reply(409, { error: 'nothing', code: back ? 'NOTHING_TO_UNDO' : 'NOTHING_TO_REDO' });
      }
      const entry = p.entries[back ? p.cursor - 1 : p.cursor];
      p.cursor += back ? -1 : 1;
      p.state = structuredClone(back ? entry.before : entry.after);
      p.revision = `r${++core.seq}`;
      return reply(200, { state: p.state, revision: p.revision, history: view(p), step: { label: entry.label } });
    }
    if (path === '/api/ai/propose') {
      if (body.base_revision !== p.revision) return conflict(p);
      const key = `p${++core.seq}`;
      const after = structuredClone(p.state);
      after.items.push(body.request.add);
      core.proposals.set(key, { base: p.revision, after });
      return reply(200, { id: key, simulated: true, base_revision: p.revision, diff: { assets: [{ change: 'created' }] } });
    }
    if (path === '/api/ai/commit') {
      const proposal = core.proposals.get(body.proposal_id);
      if (!proposal) return reply(404, { error: 'unknown', code: 'UNKNOWN_PROPOSAL' });
      core.proposals.delete(body.proposal_id);
      if (proposal.base !== p.revision) return reply(409, { error: 'stale', code: 'STALE_PROPOSAL' });
      if (body.expected_revision !== p.revision) return conflict(p);
      p.entries.splice(p.cursor);
      p.entries.push({ label: 'AI', before: p.state, after: proposal.after });
      p.cursor = p.entries.length;
      p.state = structuredClone(proposal.after);
      p.revision = `r${++core.seq}`;
      return reply(200, { state: p.state, revision: p.revision, history: view(p), entry: { label: 'AI' } });
    }
    if (path === '/api/ai/reject') {
      return core.proposals.delete(body.proposal_id) ? reply(200, { rejected: body.proposal_id }) : reply(404, { code: 'UNKNOWN_PROPOSAL' });
    }
    return reply(404, { error: 'no such command' });
  };
  return core;
}

function setup({ id = 'demo', items = ['a'] } = {}) {
  const core = fakeCore();
  const editor = { state: { metadata: { id }, items: [...items] } };
  const notices = [];
  const histories = [];
  const sync = createWorkspaceSync({
    post: core.post,
    snapshot: () => structuredClone(editor.state),
    projectId: () => editor.state.metadata.id,
    isValidId: value => /^[a-z][a-z0-9_]*$/.test(value),
    apply: state => { editor.state = structuredClone(state); },
    notify: (key, values) => notices.push(values.error ? `${key}:${values.error}` : key),
    onHistory: history => histories.push(history),
  });
  const edit = change => { change(editor.state); return sync.record(); };
  return { core, editor, notices, histories, sync, edit };
}

test('a new project is created by its first commit, without a history entry', async () => {
  const { core, editor, notices, sync } = setup();
  await sync.begin();
  await sync.idle();
  assert.equal(sync.mode, 'ready');
  assert.deepEqual(core.projects.get('demo').state, editor.state);
  assert.equal(sync.revision, core.projects.get('demo').revision);
  assert.deepEqual(notices, ['workspaceChecking', 'workspacePending', 'workspaceSaved']);
  assert.equal(sync.canUndo, false);
  assert.equal(core.requests.find(r => r.path === '/api/tx/commit').body.base_revision, null);
});

test('each action is one transaction against the revision the editor holds', async () => {
  const { core, sync, edit, histories } = setup();
  await sync.begin();
  await sync.idle();
  assert.equal(edit(s => s.items.push('b')), true);
  assert.equal(edit(s => s.items.push('c')), true);
  await sync.idle();
  const commits = core.requests.filter(r => r.path === '/api/tx/commit');
  assert.equal(commits.length, 3);
  assert.equal(commits[1].body.base_revision, commits[0].body.base_revision === null ? 'r1' : null);
  assert.equal(commits[2].body.base_revision, 'r2', 'queued commands chain their revisions');
  assert.deepEqual(core.projects.get('demo').state.items, ['a', 'b', 'c']);
  assert.equal(sync.canUndo, true);
  assert.deepEqual(histories.at(-1).undo.map(e => e.label), ['edit', 'edit']);
});

test('undo and redo are the core\'s and load its state into the editor', async () => {
  const { editor, sync, edit, core } = setup();
  await sync.begin();
  edit(s => s.items.push('b'));
  await sync.idle();
  assert.equal(sync.undo(), true);
  await sync.idle();
  assert.deepEqual(editor.state.items, ['a']);
  assert.equal(sync.canRedo, true);
  assert.equal(sync.redo(), true);
  await sync.idle();
  assert.deepEqual(editor.state.items, ['a', 'b']);
  assert.equal(sync.revision, core.projects.get('demo').revision);
  // Asking for more than there is changes nothing and is not a conflict.
  sync.redo();
  await sync.idle();
  assert.equal(sync.mode, 'ready');
});

test('an undo answered after a newer edit does not overwrite that edit', async () => {
  const { editor, sync, edit, core } = setup();
  await sync.begin();
  edit(s => s.items.push('b'));
  await sync.idle();
  let release;
  core.gate = new Promise(resolve => { release = resolve; });
  sync.undo();
  edit(s => s.items.push('typed meanwhile'));
  release();
  core.gate = null;
  await sync.idle();
  assert.deepEqual(editor.state.items, ['a', 'b', 'typed meanwhile'], 'the editor shows what the person did last');
  assert.deepEqual(core.projects.get('demo').state.items, ['a', 'b', 'typed meanwhile'], 'and the core ends there too');
});

test('an identical stored project is adopted without a write', async () => {
  const { core, editor, notices, sync } = setup();
  core.put('demo', editor.state);
  await sync.begin();
  assert.equal(sync.mode, 'ready');
  assert.equal(sync.revision, 'r1');
  assert.equal(notices.at(-1), 'workspaceSaved');
  assert.ok(core.requests.every(r => r.path === '/api/tx/open'));
});

test('a different stored project waits for an explicit choice; restore loads it', async () => {
  const { core, editor, notices, sync, edit } = setup();
  core.put('demo', { metadata: { id: 'demo' }, items: ['disk'] });
  await sync.begin();
  assert.equal(sync.mode, 'conflict');
  assert.equal(notices.at(-1), 'workspaceRecoverable');
  assert.equal(edit(s => s.items.push('local')), false, 'no commit while the conflict is open: local history');
  await sync.restoreDisk();
  assert.deepEqual(editor.state.items, ['disk']);
  assert.equal(sync.mode, 'ready');
  assert.equal(notices.at(-1), 'workspaceRecovered');
  await sync.idle();
  assert.equal(core.projects.get('demo').revision, 'r1', 'restoring must not rewrite the stored copy');
});

test('keep editor commits the editor\'s state on top of the current revision, undoably', async () => {
  const { core, editor, sync } = setup();
  core.put('demo', { metadata: { id: 'demo' }, items: ['disk'] });
  await sync.begin();
  await sync.keepEditor();
  await sync.idle();
  assert.deepEqual(core.projects.get('demo').state, editor.state);
  const commit = core.requests.find(r => r.path === '/api/tx/commit');
  assert.equal(commit.body.base_revision, 'r1');
  assert.equal(commit.body.label, "Keep this editor's version");
  sync.undo();
  await sync.idle();
  assert.deepEqual(editor.state.items, ['disk']);
});

test('a commit rejected with 409 opens the conflict instead of retrying', async () => {
  const { core, notices, sync, edit } = setup();
  await sync.begin();
  await sync.idle();
  const p = core.projects.get('demo');
  p.state = { metadata: { id: 'demo' }, items: ['other tab'] };
  p.revision = 'other';
  edit(s => s.items.push('b'));
  await sync.idle();
  assert.equal(sync.mode, 'conflict');
  assert.equal(notices.at(-1), 'workspaceRecoverable');
  assert.deepEqual(core.projects.get('demo').state.items, ['other tab']);
  assert.equal(sync.tracking, false);
});

test('returning to the tab notices a change made elsewhere before the next edit', async () => {
  const { core, sync } = setup();
  await sync.begin();
  await sync.idle();
  await sync.check();
  assert.equal(sync.mode, 'ready', 'nothing changed');
  const p = core.projects.get('demo');
  p.state = { metadata: { id: 'demo' }, items: ['elsewhere'] };
  p.revision = 'moved';
  await sync.check();
  assert.equal(sync.mode, 'conflict');
});

test('an invalid project id never reaches the core', async () => {
  const { core, notices, sync } = setup({ id: 'Bad Id' });
  await sync.begin();
  assert.equal(sync.mode, 'invalid');
  assert.deepEqual(notices, ['workspaceInvalidId']);
  assert.equal(sync.record(), false);
  assert.equal(sync.undo(), false);
  assert.equal(core.requests.length, 0);
});

test('a queued command for a previous project is dropped after switching projects', async () => {
  const { core, editor, sync, edit } = setup();
  await sync.begin();
  await sync.idle();
  let release;
  core.gate = new Promise(resolve => { release = resolve; });
  edit(s => s.items.push('b'));
  await new Promise(resolve => setImmediate(resolve));  // its commit is now in flight, held by the core
  edit(s => s.items.push('c'));  // queued behind it
  editor.state = { metadata: { id: 'second' }, items: [] };
  const switching = sync.begin();
  release();
  core.gate = null;
  await switching;
  await sync.idle();
  assert.equal(sync.id, 'second');
  assert.equal(sync.mode, 'ready');
  assert.deepEqual(core.projects.get('demo').state.items, ['a', 'b'], 'the one in flight finished, the queued one was dropped');
  assert.equal(sync.revision, core.projects.get('second').revision, "the old project's results must not leak");
});

test('AI proposals: preview, approve into the shared history, stale ones refused, reject', async () => {
  const { core, editor, sync, edit } = setup();
  await sync.begin();
  await sync.idle();
  const proposal = await sync.propose({ add: 'from ai' });
  assert.equal(proposal.simulated, true);
  assert.deepEqual(editor.state.items, ['a'], 'a proposal changes nothing');
  const approved = await sync.approve(proposal.id);
  assert.ok(approved.entry);
  assert.deepEqual(editor.state.items, ['a', 'from ai']);
  assert.equal(sync.history.undo[0].label, 'AI');
  sync.undo();
  await sync.idle();
  assert.deepEqual(editor.state.items, ['a'], 'one undo takes back the whole AI transaction');

  const stale = await sync.propose({ add: 'too late' });
  edit(s => s.items.push('human'));
  await sync.idle();
  const refused = await sync.approve(stale.id);
  assert.equal(refused.error.code, 'STALE_PROPOSAL');
  assert.equal(sync.mode, 'ready', 'a stale proposal is not a workspace conflict');
  assert.deepEqual(editor.state.items, ['a', 'human']);

  const unwanted = await sync.propose({ add: 'no thanks' });
  await sync.reject(unwanted.id);
  assert.equal(core.proposals.size, 0);
});

test('core errors are reported with their message', async () => {
  const { core, notices, sync, edit } = setup();
  await sync.begin();
  await sync.idle();
  core.fail = 'disk full';
  edit(s => s.items.push('b'));
  await sync.idle();
  assert.equal(notices.at(-1), 'workspaceError:disk full');
  core.fail = 'unreachable';
  await sync.begin();
  assert.equal(sync.mode, 'unavailable');
  assert.equal(notices.at(-1), 'workspaceError:unreachable');
  await assert.rejects(sync.propose({ add: 'x' }), /not attached/);
});
