'use strict';
/* Lists every browser E2E scenario without running it: loads tests/e2e/*.e2e.cjs with the test
 * runner, Playwright and the harness replaced by recorders. Prints JSON [{file, name}]. */
const Module = require('node:module');
const fs = require('node:fs');
const path = require('node:path');

const dir = path.join(__dirname, '..', 'tests', 'e2e');
const scenarios = [];
let current = null;
const record = name => scenarios.push({ file: current, name });
const original = Module._load;
Module._load = function load(request, parent, isMain) {
  if (request === 'node:test') return { test: record, before() {}, after() {}, describe() {}, it: record };
  if (request === 'playwright') return { chromium: {} };
  if (request.endsWith('harness.cjs')) return new Proxy({ e2e: record }, { get: (target, key) => (key in target ? target[key] : () => {}) });
  return original.call(this, request, parent, isMain);
};
for (const file of fs.readdirSync(dir).filter(name => name.endsWith('.e2e.cjs')).sort()) {
  current = file;
  require(path.join(dir, file));
}
process.stdout.write(JSON.stringify(scenarios, null, 1) + '\n');
