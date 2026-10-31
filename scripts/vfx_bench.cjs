#!/usr/bin/env node
/* HS-026: measure the VFX Studio preview in real Chromium (Playwright): particles alive, simulation
 * and frame time, seek latency, JS heap, for the Impact Spark, a four-emitter effect and an effect
 * at the full 2,048-particle budget. Writes docs/architecture/vfx-performance.json.
 *
 *   node scripts/vfx_bench.cjs [--out PATH]
 *
 * These are Studio-preview numbers on the machine that runs the script (recorded with it); they say
 * nothing about how Horizon would render an effect. */
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const out = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1]
  : path.join(ROOT, 'docs', 'architecture', 'vfx-performance.json');

const Vfx = require(path.join(ROOT, 'vfx_engine.js'));
const ember = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'vfx_ember_storm.json'), 'utf8')).effect;
function maxBudget() {
  const base = Vfx.impactSpark();
  const sparks = base.emitters[0];
  return { ...base, name: 'Budget 2048', duration: 2, emitters: Array.from({ length: 8 }, (_, i) => ({
    ...JSON.parse(JSON.stringify(sparks)), id: `e${i}`, bursts: [{ time: 0, count: 256 }], lifetime: [1.5, 2] })) };
}
const EFFECTS = { impact_spark: Vfx.impactSpark(), ember_storm: ember, budget_2048: maxBudget() };
for (const [name, effect] of Object.entries(EFFECTS)) {
  const problems = Vfx.validate(effect);
  if (problems.length) throw new Error(`${name}: ${JSON.stringify(problems)}`);
}

(async () => {
  const browser = await chromium.launch({ args: ['--enable-precise-memory-info', '--js-flags=--expose-gc'] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent('<canvas id="c" width="960" height="600"></canvas>');
  await page.addScriptTag({ content: fs.readFileSync(path.join(ROOT, 'vfx_engine.js'), 'utf8') });
  const results = {};
  for (const [name, effect] of Object.entries(EFFECTS)) {
    results[name] = await page.evaluate(effect => {
      const Vfx = window.HorizonVfx, draw = document.getElementById('c').getContext('2d');
      // Collect garbage around the measurement so the difference is what the spawned particles keep.
      const heap = () => { window.gc?.(); return performance.memory ? performance.memory.usedJSHeapSize : null; };
      window.keep = null;  // release the previous effect before measuring this one
      const before = heap();
      let t0 = performance.now();
      const spawned = Vfx.spawn(effect);
      const spawnMs = performance.now() - t0;
      const delta = before !== null ? heap() - before : null;
      const heapSpawn = delta !== null && delta > 0 ? delta : null;  // a few dozen particles are below GC noise
      window.keep = spawned;
      const frames = 120, step = effect.duration / frames;
      let simulate = 0, render = 0, maxAlive = 0;
      for (let i = 0; i < frames; i++) {
        t0 = performance.now(); const alive = Vfx.simulate(effect, i * step, spawned).length; simulate += performance.now() - t0;
        t0 = performance.now(); Vfx.render(draw, effect, i * step, { spawned }); render += performance.now() - t0;
        maxAlive = Math.max(maxAlive, alive);
      }
      // Seeking: jump to pseudo-random times (fixed sequence) and draw the frame.
      const seeks = [];
      let x = 12345;
      for (let i = 0; i < 60; i++) {
        x = (x * 1103515245 + 12345) % 2147483648;
        const time = (x / 2147483648) * effect.duration;
        t0 = performance.now(); Vfx.render(draw, effect, time, { spawned }); seeks.push(performance.now() - t0);
      }
      seeks.sort((a, b) => a - b);
      const round = v => Math.round(v * 1000) / 1000;
      return { spawned: spawned.length, max_alive: maxAlive, spawn_ms: round(spawnMs), simulate_ms_avg: round(simulate / frames),
        frame_ms_avg: round(render / frames), seek_ms_p50: round(seeks[30]), seek_ms_p95: round(seeks[56]),
        heap_after_spawn_bytes: heapSpawn };
    }, effect);
  }
  // Reduced motion: the editor never starts playback on its own (checked in tests/e2e/vfx.e2e.cjs).
  const report = { schema: 'horizon-studio.vfx-performance/1', generated_by: 'scripts/vfx_bench.cjs',
    machine: { platform: process.platform, arch: process.arch, cpus: os.cpus().length, cpu: os.cpus()[0]?.model,
      browser: `Chromium ${browser.version()}` },
    canvas: '960x600 2D', frames: 120, seeks: 60, effects: results,
    note: 'Studio preview in Chromium on the machine above; not a measurement of in-game rendering. ' +
      'heap_after_spawn_bytes is null where the difference is below garbage-collector noise.' };
  await browser.close();
  fs.writeFileSync(out, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
})();
