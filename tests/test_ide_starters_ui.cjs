'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const starters = require('../ide_starters_ui.js');

test('catalog requires the exact schema and refuses fabricated in-game verification',()=>{
  const make = overrides => ({id:'ruby',name:'Ruby',name_ru:'Рубин',
    description:'Content',description_ru:'Контент',sha256:'a'.repeat(64),
    verification:'project-schema-only',in_game_verified:false,...overrides});
  const catalog = {schema:starters.SCHEMA,templates:[make()]};
  assert.equal(starters.validCatalog(catalog),true);
  for(const item of [make({id:'../evil'}),make({in_game_verified:true}),
    make({sha256:'x'}),make({verification:'gameplay'})]){
    assert.equal(starters.validCatalog({...catalog,templates:[item]}),false);
  }
  assert.equal(starters.validCatalog({...catalog,schema:'wrong'}),false);
  assert.equal(starters.validCatalog({...catalog,templates:[]}),false);
});

test('summary is localized and truthfully labels project-only checks',()=>{
  const item = {description:'Block template',description_ru:'Шаблон блока',counts:{block:1,item:2}};
  assert.match(starters.summary(item,'en'),/^Block template\nblock × 1 · item × 2\nProject schema validated; not tested in the game\./);
  assert.match(starters.summary(item,'ru'),/^Шаблон блока\nБлоки × 1 · Предметы × 2\nПроверено как проект; в игре не испытано\./);
});

test('UI wiring is part of the bundled editor, without external CDN dependencies',()=>{
  const root=path.resolve(__dirname,'..');
  const index=fs.readFileSync(path.join(root,'index.html'),'utf8');
  const app=fs.readFileSync(path.join(root,'editor_app.js'),'utf8');
  const server=fs.readFileSync(path.join(root,'studio.py'),'utf8');
  for(const id of ['ideTemplate','ideUseStarter','ideStarterDescription'])
    assert.ok(index.includes('id="'+id+'"'),id);
  assert.ok(index.includes('<script src="/ide_starters_ui.js"></script>'));
  assert.ok(app.includes('HorizonIdeStarters.mount('));
  assert.ok(server.includes("'ide_starters_ui.js': b'HorizonIdeStarters'"));
  assert.ok(server.includes("'examples/ruby_demo.hstudio.json'"));
});
