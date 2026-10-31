'use strict';
/* HS-025: the editor's VFX engine agrees with the core (studio_core/vfx.py) particle by particle. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const Vfx = require('../vfx_engine.js');

const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'vfx_impact_spark.json'), 'utf8'));
const close = (a, b, label) => assert.ok(Math.abs(a - b) <= 1e-9, `${label}: ${a} vs ${b}`);

test('the preset is the one the core uses and is valid', () => {
  assert.deepEqual(Vfx.impactSpark(), FIXTURE.effect);
  assert.deepEqual(Vfx.validate(Vfx.impactSpark()), []);
});

test('every particle matches the core simulation for the same seed', () => {
  for (const [time, alive] of Object.entries(FIXTURE.alive)) {
    assert.equal(Vfx.simulate(FIXTURE.effect, Number(time)).length, alive, `alive at ${time}`);
  }
  for (const [time, frame] of Object.entries(FIXTURE.frames)) {
    const now = Vfx.simulate(FIXTURE.effect, Number(time));
    assert.equal(now.length, frame.length);
    now.forEach((p, i) => {
      const q = frame[i];
      assert.equal(p.emitter, q.emitter);
      for (const key of ['position', 'trail']) p[key].forEach((v, c) => close(v, q[key][c], `${time} #${i} ${key}`));
      close(p.size, q.size, 'size');
      close(p.alpha, q.alpha, 'alpha');
      p.color.forEach((v, c) => assert.ok(Math.abs(v - q.color[c]) <= 1, 'colour'));
    });
  }
});

test('the PRNG is the 32-bit mulberry32 stream', () => {
  const a = Vfx.mulberry32(1337), b = Vfx.mulberry32(1337);
  const first = [a(), a(), a()];
  assert.deepEqual(first, [b(), b(), b()]);
  assert.ok(first.every(x => x >= 0 && x < 1));
  assert.notDeepEqual(first, [Vfx.mulberry32(1338)(), 0, 0].slice(0, 1).concat(first.slice(1)));
});

test('validation names each problem', () => {
  const broken = mutate => { const e = Vfx.impactSpark(); mutate(e); return Vfx.validate(e).map(p => p.code); };
  assert.ok(broken(e => { e.emitters[0].bursts[0].count = 9999; }).includes('COUNT'));
  assert.ok(broken(e => { e.emitters[0].speed = [8, 2]; }).includes('ORDER'));
  assert.ok(broken(e => { e.emitters[0].color[0][1] = 'orange'; }).includes('COLOR'));
  assert.ok(broken(e => { e.emitters[0].size[0][0] = 0.2; }).includes('KEY_START'));
  assert.ok(broken(e => { e.seed = -1; }).includes('SEED'));
  assert.ok(broken(e => { e.emitters[1].id = 'sparks'; }).includes('DUPLICATE'));
  assert.ok(broken(e => { e.emitters = Array.from({ length: 5 }, (_, i) => ({ ...e.emitters[0], id: 'e' + i, bursts: [{ time: 0, count: 500 }] })); }).includes('BUDGET'));
});

test('render draws every live particle and reports the count', () => {
  const calls = { fillRect: 0, stroke: 0 };
  const ctx = {
    canvas: { width: 320, height: 200 }, save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {},
    fillRect() { calls.fillRect++; }, stroke() { calls.stroke++; },
  };
  const alive = Vfx.render(ctx, FIXTURE.effect, 0.2);
  assert.equal(alive, FIXTURE.alive['0.2']);
  assert.ok(calls.fillRect >= alive && calls.stroke > 0);
});

test('engine notes never promise in-game rendering', () => {
  const pin = Vfx.engineNotes(FIXTURE.effect, { 'native.particles': { status: 'unsupported' } }).map(n => n.code);
  assert.deepEqual(pin, ['STUDIO_PREVIEW', 'NO_CUSTOM_PARTICLES', 'NO_NATIVE_PARTICLES']);
  const upstream = Vfx.engineNotes(FIXTURE.effect, { 'native.particles': { status: 'engine-only', api: 'native hooks 11+' } });
  assert.equal(upstream.find(n => n.code === 'NATIVE_PARTICLES').api, 'native hooks 11+');
  assert.ok(upstream.some(n => n.code === 'NO_CUSTOM_PARTICLES'));
});
