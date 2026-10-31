const test=require('node:test');
const assert=require('node:assert/strict');
const {Journal}=require('../editor_history.js');
const state=()=>({metadata:{id:'ruby_demo'},objects:[{uid:'a',id:'ruby'}],carry:{preserved_objects:[{kind:'plugin',data:'данные'}]}});
test('history starts without synthetic undo steps',()=>{
  const journal=new Journal();journal.reset(state());
  assert.equal(journal.canUndo,false);assert.equal(journal.canRedo,false);
});
test('undo and redo preserve stable UIDs and unknown fields',()=>{
  const journal=new Journal();const original=state();
  journal.reset(original);
  const edited=state();edited.objects[0].id='ruby_renamed';journal.record(edited);
  original.objects[0].id='mutated outside history';
  assert.equal(journal.undo().objects[0].id,'ruby');
  assert.equal(journal.redo().objects[0].id,'ruby_renamed');
  assert.equal(journal.undo().carry.preserved_objects[0].data,'данные');
});
test('no-op changes are not commands and new branch clears redo',()=>{
  const journal=new Journal();journal.reset(state());
  assert.equal(journal.record(state()),false);
  const newValue=state();newValue.objects[0].id='first';journal.record(newValue);
  journal.undo();
  newValue.objects[0].id='second';journal.record(newValue);
  assert.equal(journal.canRedo,false);
  assert.equal(journal.undo().objects[0].id,'ruby');
});
test('history is bounded',()=>{
  const journal=new Journal(2);
  journal.reset({number:0});
  for(let i=1;i<=10;i++)journal.record({number:i});
  assert.equal(journal.undo().number,9);
  assert.equal(journal.undo().number,8);
  assert.equal(journal.undo(),null);
});
test('project switch discards the prior document history',()=>{
  const journal=new Journal();journal.reset({project:'one'});
  journal.record({project:'changed'});
  journal.reset({project:'two'});
  assert.equal(journal.canUndo,false);
  assert.equal(journal.canRedo,false);
});
test('large snapshots evict old frames rather than corrupt them',()=>{
  const journal=new Journal(25,2000);
  journal.reset({value:'a'.repeat(400)});
  for(let i=0;i<8;i++)journal.record({value:String(i).repeat(400)});
  assert.ok(journal.before.length<8);
  assert.equal(journal.undo().value.length,400);
});

test('the editor application script parses and the page has no inline script (CSP script-src self)',()=>{
  const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
  const html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
  assert.equal(html.split('<script>').length,1,'index.html must not carry an inline script');
  assert.ok(html.includes('<script src="/editor_app.js"></script>'));
  new vm.Script(fs.readFileSync(path.join(__dirname,'..','editor_app.js'),'utf8'),{filename:'editor_app.js'});
});
