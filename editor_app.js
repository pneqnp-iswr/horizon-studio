/* The editor application: state, rendering, persistence and wiring of the workbench controls.
 * Loaded as a classic script after the modules it uses (index.html); an external file so the
 * page's Content-Security-Policy can forbid inline scripts (script-src 'self'). */
'use strict';
const $=id=>document.getElementById(id);
const t = (key, values={}) => window.HorizonI18n.t(key, values);
const B={'minecraft:iron_block':'Iron Block','minecraft:amethyst_block':'Amethyst Block','minecraft:glass':'Glass','minecraft:stone':'Stone','minecraft:oak_planks':'Oak Planks'};
const I={'minecraft:diamond':'Diamond','minecraft:emerald':'Emerald','minecraft:stick':'Stick','minecraft:amethyst_shard':'Amethyst Shard','minecraft:iron_ingot':'Iron Ingot'};
const ING={...B,...I,'minecraft:glowstone_dust':'Glowstone Dust','minecraft:gold_ingot':'Gold Ingot','minecraft:cobblestone':'Cobblestone','minecraft:coal':'Coal','minecraft:redstone':'Redstone'};
const META=['modId','modName','version','author','description'];
const state={blocks:[],items:[],recipes:[],structures:[],effects:[],source_overrides:{},tab:'recipe',editing:-1};
const VALID=/^[a-z][a-z0-9_]{0,63}$/;
function esc(s){return HorizonStudioRender.escapeHtml(s);}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function meta(){return {id:$('modId').value.trim(),name:$('modName').value.trim(),version:$('version').value.trim(),author:$('author').value.trim(),description:$('description').value};}
function localId(ref){return HorizonStudioModel.localRef(ref,meta().id);}
function payload(){return HorizonStudioModel.generatorPayload(meta(),state);}
function editorState(){return HorizonStudioModel.editorSnapshot(meta(),state);}
function newUid(){return globalThis.crypto?.randomUUID?.();}
const editJournal=new window.HorizonStudioHistory.Journal();
const studioPost=window.HorizonStudioApi.post;
// HS-020: the core owns the project's revision and history; the editor sends one transaction per action.
const workspaceSync=window.HorizonStudioWorkspace.createWorkspaceSync({
  post:studioPost,snapshot:editorState,projectId:()=>meta().id,isValidId:id=>VALID.test(id),
  apply:state=>{applyProject(state,{preserveHistory:true,skipWorkspaceCheck:true});editJournal.reset(editorState());historyButtons();},
  notify:workspaceNotice,onHistory:()=>{historyButtons();document.dispatchEvent(new Event('studio:history-changed'));},
});
const workbench=window.HorizonWorkbench.init({t,post:studioPost,snapshot:editorState,chooseTab,
  getTarget:()=>state.target||null,
  setTarget:target=>{if(target)state.target=target;else delete state.target;persist();workbench.update({meta:meta(),tab:state.tab,counts:counts()});}});
function counts(){return {block:state.blocks.length,item:state.items.length,recipe:state.recipes.length,structure:state.structures.length};}
// Attached to a workspace, undo and redo are the core's (shared by people and AI, kept across restarts);
// detached (invalid ID, no core, an open conflict), the editor keeps a local history.
function historyButtons(){const core=workspaceSync.tracking;$('undoEdit').disabled=!(core?workspaceSync.canUndo:editJournal.canUndo);$('redoEdit').disabled=!(core?workspaceSync.canRedo:editJournal.canRedo);}
function workspaceNotice(key,values={},mode=workspaceSync.mode){
  if(mode==='ready'&&workspaceSync.id&&(key==='workspaceSaved'||key==='workspaceRecovered'))
    document.dispatchEvent(new CustomEvent('studio:workspace-ready',{detail:{id:workspaceSync.id}}));
  const label=$('workspaceSaveStatus');
  label.textContent=t(key,values);label.dataset.key=key;
  $('restoreWorkspace').hidden=mode!=='conflict';
  $('keepEditor').hidden=mode!=='conflict';
}
function persist({record=true,disk=true,label=null}={}){
  const snapshot=editorState();
  const committed=disk&&workspaceSync.record(label);
  if(record){if(committed)editJournal.reset(snapshot);else editJournal.record(snapshot);}
  historyButtons();
  try{localStorage.setItem('horizonStudio_v02',JSON.stringify(snapshot));}
  catch(e){status(t('storageFull'),true);}
}
const beginWorkspaceSession=()=>workspaceSync.begin();
const acceptDiskWorkspace=()=>workspaceSync.restoreDisk();
const keepEditorWorkspace=()=>workspaceSync.keepEditor();
function localStep(snapshot){
  if(!snapshot)return;
  applyProject(snapshot,{preserveHistory:true,skipWorkspaceCheck:true});
  historyButtons();if(workspaceSync.id!==meta().id)beginWorkspaceSession();
}
function undoProject(){if(workspaceSync.tracking){workspaceSync.undo();return;}localStep(editJournal.undo());}
function redoProject(){if(workspaceSync.tracking){workspaceSync.redo();return;}localStep(editJournal.redo());}
function allEntries(){return [...state.blocks,...state.items];}
function ingredientChoices(){return {...ING,...Object.fromEntries(allEntries().map(e=>['@'+e.id,e.name+t('modSuffix')]))};}
function fillOptions(select, values, selected=''){select.innerHTML=Object.entries(values).map(([value,label])=>`<option value="${esc(value)}" ${selected===value?'selected':''}>${esc(label)}</option>`).join('');}
function chooseTab(tab){state.tab=tab;state.editing=-1;for(const kind of ['block','item','recipe','structure'])$(kind+'Tab').classList.toggle('selected',kind===tab);$('objectEditor').hidden=tab==='recipe'||tab==='structure';$('recipeEditor').hidden=tab!=='recipe';$('structureEditor').hidden=tab!=='structure';$('blockControls').hidden=tab!=='block';$('itemControls').hidden=tab!=='item';if(tab==='recipe')resetRecipe();else if(tab==='structure')resetStructure();else resetObject();updateWorkspaceMeta();render();}
function resetObject(){state.editing=-1;$('editorTitle').textContent=t(state.tab==='block'?'newBlock':'newItem');$('addObject').textContent=t('add');$('cancelObject').hidden=true;$('entryId').value=state.tab==='block'?'ruby_block':'ruby';$('entryName').value=state.tab==='block'?'Ruby Block':'Ruby';$('entryNameRu').value='';$('miningTool').value='none';$('toolTier').value='none';fillOptions($('template'),state.tab==='block'?B:I);fillOptions($('sounds'),{'':t('fromTemplate'),...B});$('hardness').value=5;$('light').value=0;$('explosion').value='';$('friction').value='';$('mapColor').value='';$('requiresTool').checked=false;$('rarity').value='common';$('maxStack').value=64;$('texture').value='';$('textureHint').textContent=t('textureTemplate');}
function resetRecipe(){state.editing=-1;$('recipeEditorTitle').textContent=t('newRecipe');$('addRecipe').textContent=t('addRecipe');$('cancelRecipe').hidden=true;$('recipeId').value='new_recipe';$('recipeType').value='shaped';$('recipeCount').value=1;fillOptions($('recipeResult'),Object.fromEntries(allEntries().map(e=>['@'+e.id,e.name])));renderGrid();}
function renderGrid(values=Array(9).fill('')){const options={'':t('emptyIngredient'),...ingredientChoices()};$('recipeGrid').innerHTML='';for(let i=0;i<9;i++){let sel=document.createElement('select');sel.id='slot'+i;sel.setAttribute('aria-label',t('ingredient',{num:i+1}));fillOptions(sel,options,values[i]||'');$('recipeGrid').appendChild(sel);}}
function displayName(ref){return HorizonStudioModel.displayName(ref,allEntries());}

function currentSearch(){return $('entrySearch') ? $('entrySearch').value.trim().toLowerCase() : '';}

function matchesSearch(entry){return HorizonStudioModel.matchesSearch(entry,currentSearch(),state.tab,allEntries());}
function renderContext(){return {entries:allEntries(),packTextures:window.HorizonPackTextures,t};}

function recipeCardMarkup(e,i){return HorizonStudioRender.recipeCardMarkup(e,i,renderContext());}
function entryCardMarkup(e,i){return HorizonStudioRender.entryCardMarkup(e,i,state.tab,renderContext());}
function updateWorkspaceMeta(){
  const kind={recipe:t('recipes'),block:t('blocks'),item:t('items'),structure:t('structures')}[state.tab]||'';
  const m=meta();
  $('workspaceMode').textContent=(m.name||m.id).toUpperCase();
  $('workspaceTitle').textContent=kind.toUpperCase();
  $('workspaceSubtitle').textContent=t('counter',{blocks:state.blocks.length,items:state.items.length,recipes:state.recipes.length});
  workbench.update({meta:m,tab:state.tab,counts:counts()});
}
function emptyState(){$('entries').innerHTML=HorizonWorkbench.emptyStateMarkup(state.tab,t);if($('emptyDemo'))$('emptyDemo').onclick=example;}

function render(){if(state.tab==='structure'){renderStructures();updateWorkspaceMeta();return;}const group=state[state.tab==='block'?'blocks':state.tab==='item'?'items':'recipes'];const visible=group.map((e,i)=>[e,i]).filter(([e])=>matchesSearch(e));$('counter').textContent=String(group.length);updateWorkspaceMeta();$('entries').className=state.tab==='recipe'?'entries recipe-gallery':'entries card-gallery';if(!group.length)return emptyState();$('entries').innerHTML=visible.length?visible.map(([e,i])=>state.tab==='recipe'?recipeCardMarkup(e,i):entryCardMarkup(e,i)).join(''):`<p class="empty-hint">${esc(t('searchNothing'))}</p>`;for(const b of $('entries').querySelectorAll('[data-edit]'))b.onclick=()=>editEntry(Number(b.dataset.edit));for(const b of $('entries').querySelectorAll('[data-remove]'))b.onclick=()=>removeEntry(Number(b.dataset.remove));}
function editEntry(i){state.editing=i;const e=state[state.tab==='block'?'blocks':state.tab==='item'?'items':'recipes'][i];if(state.tab==='recipe'){$('recipeEditorTitle').textContent=t('editRecipe');$('recipeId').value=e.id;$('recipeType').value=e.type;$('recipeCount').value=e.count;fillOptions($('recipeResult'),Object.fromEntries(allEntries().map(x=>['@'+x.id,x.name])),e.result);renderGrid(e.grid);$('addRecipe').textContent=t('saveChanges');$('cancelRecipe').hidden=false;}else{$('editorTitle').textContent=t(state.tab==='block'?'editBlock':'editItem');$('entryId').value=e.id;$('entryName').value=e.name;$('entryNameRu').value=e.name_ru||'';$('template').value=e.template;$('miningTool').value=e.mining_tool||(e.requires_tool?'pickaxe':'none');$('toolTier').value=e.tool_tier||'none';$('hardness').value=e.hardness??5;$('light').value=e.light??0;$('explosion').value=e.explosion_resistance??'';$('friction').value=e.friction??'';$('mapColor').value=e.map_color??'';$('sounds').value=e.sounds||'';$('requiresTool').checked=!!e.requires_tool;$('rarity').value=e.rarity||'common';$('maxStack').value=e.max_stack_size||64;$('texture').value='';$('textureHint').textContent=t(e.texture?'textureKeep':'textureTemplate');$('addObject').textContent=t('saveChanges');$('cancelObject').hidden=false;}}
function removeEntry(i){const collection=state[state.tab==='block'?'blocks':state.tab==='item'?'items':'recipes'];const entry=collection[i];if(state.tab!=='recipe'){const affected=HorizonStudioModel.recipesUsing(state.recipes,entry.id);if(affected.length&&!confirm(t('deleteReferences',{count:affected.length})))return;state.recipes=state.recipes.filter(r=>!affected.includes(r));}collection.splice(i,1);if(state.tab==='recipe')resetRecipe();else resetObject();persist();render();}
async function addObject(){const id=$('entryId').value.trim(),name=$('entryName').value.trim(),collection=state[state.tab==='block'?'blocks':'items'];if(!VALID.test(id)||!name){status(t('invalidEntry'),true);return;}if(allEntries().some(e=>e.id===id&&e!==collection[state.editing])){status(t('duplicateId'),true);return;}if(state.editing<0&&collection.length>=32){status(t('entryLimit'),true);return;}
const e={id,name,template:$('template').value};if($('entryNameRu').value.trim())e.name_ru=$('entryNameRu').value.trim();if(state.tab==='block'){e.hardness=Number($('hardness').value);e.light=Number($('light').value);if($('explosion').value!=='')e.explosion_resistance=Number($('explosion').value);if($('friction').value!=='')e.friction=Number($('friction').value);if($('mapColor').value!=='')e.map_color=Number($('mapColor').value);if($('sounds').value)e.sounds=$('sounds').value;if($('requiresTool').checked)e.requires_tool=true;e.mining_tool=$('miningTool').value==='none'&&e.requires_tool?'pickaxe':$('miningTool').value;e.tool_tier=$('toolTier').value;}else{e.rarity=$('rarity').value;e.max_stack_size=Number($('maxStack').value);}
const file=$('texture').files[0];if(file){if(file.size>1024*1024||file.type!=='image/png'){status(t('invalidTexture'),true);return;}try{e.texture=await new Promise((resolve,reject)=>{const reader=new FileReader;reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});}catch(_){status(t('readTexture'),true);return;}}else if(state.editing>=0&&collection[state.editing].texture){e.texture=collection[state.editing].texture;}
e.uid=state.editing>=0?collection[state.editing].uid:newUid();if(state.editing<0)collection.push(e);else{const old=collection[state.editing];collection[state.editing]=e;if(old.id!==id)HorizonStudioModel.renameReferences(state.recipes,old.id,id);}resetObject();persist();render();status(t('savedEntry'));}
function addRecipe(){const e={id:$('recipeId').value.trim(),type:$('recipeType').value,result:$('recipeResult').value,count:Number($('recipeCount').value),grid:Array.from({length:9},(_,i)=>$('slot'+i).value)};if(!VALID.test(e.id)||!e.result||!Number.isInteger(e.count)||e.count<1||e.count>64||!e.grid.some(Boolean)){status(t('invalidRecipe'),true);return;}if(state.recipes.some((x,i)=>x.id===e.id&&i!==state.editing)){status(t('duplicateRecipe'),true);return;}if(state.editing<0&&state.recipes.length>=64){status(t('recipeLimit'),true);return;}e.uid=state.editing>=0?state.recipes[state.editing].uid:newUid();if(state.editing<0)state.recipes.push(e);else state.recipes[state.editing]=e;resetRecipe();render();persist();status(t('savedRecipe'));}
const desktop=window.HorizonDesktop;
/** Resolves false when a native "Save as" dialog was cancelled. */
async function download(blob,name){
  if(desktop.available())return (await desktop.saveFile(blob,name)).saved;
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
  return true;
}

async function api(path){const response=await studioPost(path,JSON.stringify(payload()));if(!response.ok){const data=await response.json();throw new Error(data.error||t('apiError'));}return response;}
async function exportFile(path,extension){const b=$(extension==='hmod'?'exportHmod':'exportSource');b.disabled=true;try{const blocked=await workbench.exportGate();if(blocked){status(blocked,true);return;}status(t('exporting'));const result=await api(path);if(!await download(await result.blob(),meta().id+(extension==='hmod'?'.hmod':'-source.zip'))){status(t('saveCancelled'));return;}status(extension==='hmod'?t('hmodExported'):t('zipExported'));}catch(e){status(e.message,true);}finally{b.disabled=false;}}
async function inspect(){try{const result=await (await api('/api/preview')).json();$('inspectPanel').hidden=false;$('manifestPreview').textContent=result.manifest;$('filePreview').textContent=result.files.join('\n');status(t('inspectSuccess',{count:result.file_count,bytes:result.bytes_raw}));}catch(e){status(e.message,true);}}
async function saveProject(){try{const response=await studioPost('/api/project/save',JSON.stringify(editorState()));if(!response.ok){const data=await response.json();throw new Error(data.error||t('apiError'));}if(!await download(await response.blob(),(meta().id||'project')+'.hstudio.json')){status(t('saveCancelled'));return;}status(t('projectSaved'));}catch(e){status(e.message,true);}}
function applyProject(data,{preserveHistory=false,skipWorkspaceCheck=false}={}){const problem=HorizonStudioModel.projectProblem(data);if(problem)throw new Error(t(problem));const m=data.metadata;for(const [target,key] of [['modId','id'],['modName','name'],['version','version'],['author','author'],['description','description']])$(target).value=m[key]??'';state.blocks=data.blocks;state.items=data.items;state.recipes=data.recipes;state.structures=data.structures||[];state.effects=data.effects||[];state.source_overrides=data.source_overrides||{};state.carry=data.carry||{};if(data.target)state.target=data.target;else delete state.target;HorizonStudioModel.assignMissingUids(state,newUid);chooseTab(preserveHistory?state.tab:'block');persist({record:false,disk:false});if(!preserveHistory)editJournal.reset(editorState());historyButtons();render();if(!skipWorkspaceCheck)beginWorkspaceSession();document.dispatchEvent(new Event('studio:state-changed'));}
function example(){const d={metadata:{id:'ruby_demo',name:'Ruby Demo',version:'0.1.0',author:'Creator',description:'Example with two recipes, a block and a gem'},blocks:[{id:'ruby_block',name:'Block of Ruby',template:'minecraft:iron_block',hardness:4,light:3}],items:[{id:'ruby',name:'Ruby',template:'minecraft:diamond',rarity:'rare',max_stack_size:64}],recipes:[{id:'ruby_block',type:'shaped',result:'@ruby_block',count:1,grid:Array(9).fill('@ruby')},{id:'ruby_from_block',type:'shapeless',result:'@ruby',count:9,grid:['@ruby_block',...Array(8).fill('')]}]};applyProject(d);status(t('demoLoaded'));}
function refreshLanguage(){
  if(state.tab==='structure'){$('structureEditorTitle').textContent=t(state.editing>=0?'editStructure':'newStructure');$('addStructure').textContent=t(state.editing>=0?'saveChanges':'addStructure');}
  // Preserve in-progress editing and user selections while translating the UI.
  const editing=state.editing>=0;
  $('editorTitle').textContent=t(editing?(state.tab==='block'?'editBlock':'editItem'):(state.tab==='block'?'newBlock':'newItem'));
  $('addObject').textContent=t(editing?'saveChanges':'add');
  $('recipeEditorTitle').textContent=t(editing?'editRecipe':'newRecipe');
  $('addRecipe').textContent=t(editing?'saveRecipe':'addRecipe');
  $('textureHint').textContent=t(editing&&state.tab!=='recipe'&&state[state.tab==='block'?'blocks':'items'][state.editing]?.texture?'textureKeep':'textureTemplate');
  const template=$('template').value,sound=$('sounds').value;
  fillOptions($('sounds'),{'':t('fromTemplate'),...B},sound);
  $('template').value=template;
  if(state.tab==='recipe'){
    const grid=Array.from({length:9},(_,i)=>$('slot'+i)?.value||'');
    renderGrid(grid);
  }
  render();if($('workspaceSaveStatus').dataset.key)workspaceNotice($('workspaceSaveStatus').dataset.key);status('');
  workbench.refreshLanguage();
}
window.HorizonStudioRefreshLanguage=refreshLanguage;
async function runDoctor(){
  const button=$('doctor');button.disabled=true;
  try {
    const report=await (await api('/api/doctor')).json();
    const summary=t('doctorSummary',{errors:report.issues.filter(e=>e.level==='error').length,warnings:report.issues.filter(e=>e.level==='warning').length,files:report.stats.files});
    const lines=[summary,'',...report.issues.map(e=>`[${e.level.toUpperCase()}] ${e.code}: ${window.HorizonI18n.language==='ru'?(t('doctor_'+e.code,{subject:e.subject})+(e.level==='error'?' '+e.message:'')):e.message}`)];
    $('doctorPanel').textContent=lines.join('\n');$('doctorPanel').hidden=false;
    status(report.ok?t('doctorDone'):t('doctorFailed'),!report.ok);
  } catch(e){status(e.message,true);} finally{button.disabled=false;}
}
let isoRotation=0, lastStructurePreview=null;
function structureSpec(){return {id:$('structureId').value.trim(),kind:$('structureKind').value,theme:$('structureTheme').value,size:Number($('structureSize').value),seed:Number($('structureSeed').value),rotation:Number($('structureRotation').value),mirror:$('structureMirror').value};}
function resetStructure(){state.editing=-1;$('structureEditorTitle').textContent=t('newStructure');$('addStructure').textContent=t('addStructure');$('cancelStructure').hidden=true;$('structureId').value='my_sky_dome';$('structureKind').value='sky_dome';$('structureTheme').value='stone';$('structureSize').value=19;$('structureSeed').value=42;$('structureRotation').value='0';$('structureMirror').value='none';}
function renderStructures(){ $('counter').textContent=String(state.structures.length);updateWorkspaceMeta();const visible=state.structures.map((e,i)=>[e,i]).filter(([e])=>matchesSearch({id:e.id,name:e.kind+' '+e.theme,name_ru:'',template:e.kind}));$('entries').className='entries card-gallery';if(!state.structures.length)return emptyState();$('entries').innerHTML=visible.length?visible.map(([e,i])=>`<article class="entry-card structure"><div class="entry-visual"><span class="preview-image large symbol structure-badge">⬡</span></div><div class="entry-copy"><b>${esc(e.id)}</b><small>${esc(e.kind)} · ${esc(e.size)}³</small><small>${esc(e.theme)} · ${esc(e.rotation||0)}° · ${esc(e.mirror||'none')}</small></div><div class="entry-actions"><button data-edit="${i}">${esc(t('configure'))}</button><button data-remove="${i}" class="danger ghost">${esc(t('remove'))}</button></div></article>`).join(''):`<p class="empty-hint">${esc(t('emptyStructures'))}</p>`;for(const b of $('entries').querySelectorAll('[data-edit]'))b.onclick=()=>{const e=state.structures[Number(b.dataset.edit)];state.editing=Number(b.dataset.edit);$('structureId').value=e.id;$('structureKind').value=e.kind;$('structureTheme').value=e.theme;$('structureSize').value=e.size;$('structureSeed').value=e.seed;$('structureRotation').value=String(e.rotation||0);$('structureMirror').value=e.mirror||'none';$('structureEditorTitle').textContent=t('editStructure');$('addStructure').textContent=t('saveChanges');$('cancelStructure').hidden=false;};for(const b of $('entries').querySelectorAll('[data-remove]'))b.onclick=()=>{state.structures.splice(Number(b.dataset.remove),1);resetStructure();renderStructures();persist();};}
function addStructure(){const e=structureSpec();if(!VALID.test(e.id)||!Number.isInteger(e.size)||e.size<7||e.size>29||e.size%2!==1||!Number.isInteger(e.seed)||e.seed<0||e.seed>2147483647){status(t('badStructure'),true);return;}if(state.structures.some((x,i)=>x.id===e.id&&i!==state.editing)){status(t('duplicateId'),true);return;}if(state.editing===-1&&state.structures.length>=8){status(t('structureLimit'),true);return;}e.uid=state.editing>=0?state.structures[state.editing].uid:newUid();if(state.editing===-1)state.structures.push(e);else state.structures[state.editing]=e;resetStructure();renderStructures();persist();status(t('savedStructure'));}
async function previewStructure(){try{const response=await studioPost('/api/structure-preview',JSON.stringify({structure:structureSpec(),layer:Number($('sliceY').value)}));const info=await response.json();if(!response.ok)throw new Error(info.error);$('structureCanvas').hidden=false;$('structureStats').textContent=t('previewStats',{blocks:info.blocks,dimensions:info.size.join(' × ')});$('structureAscii').textContent=info.top_down;lastStructurePreview=info;drawIsometric(info);status(t('previewReady'));}catch(e){status(e.message,true);}}
function drawIsometric(info){
  const canvas=$('structureIso'), ctx=canvas.getContext('2d'); if(!ctx)return;
  const w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#0b1725';ctx.fillRect(0,0,w,h);
  const dim=info.size,scale=Math.min(15,425/Math.max(dim[0],dim[2]),370/(dim[1]+.52*(dim[0]+dim[2])));
  const centerX=w/2,groundY=h-85;
  const colors=['#738b9c','#b0c3cb','#86b69b','#e3b36b','#b19ac8','#81b4d6'];
  const xyz=(x,z)=>{
    if(isoRotation===1)return [z,dim[0]-1-x];
    if(isoRotation===2)return [dim[0]-1-x,dim[2]-1-z];
    if(isoRotation===3)return [dim[2]-1-z,x];
    return [x,z];
  };
  const pixels=(x,y,z)=>[centerX+(x-z)*scale,groundY+(x+z)*scale*.52-y*scale];
  const face=(vertices,fill)=>{ctx.beginPath();ctx.moveTo(...vertices[0]);for(const vertex of vertices.slice(1))ctx.lineTo(...vertex);ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.lineWidth=.35;ctx.strokeStyle='rgba(2,9,18,.3)';ctx.stroke();};
  const sorted=info.voxels.map(([x,y,z,k])=>{const [a,b]=xyz(x,z);return [a,y,b,k];})
    .sort((a,b)=>(a[0]+a[2]-a[1])-(b[0]+b[2]-b[1]));
  const tint=(hex,amount)=>{const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);return `rgb(${Math.round(r*amount)},${Math.round(g*amount)},${Math.round(b*amount)})`;};
  for(const [x,y,z,k] of sorted){
    const top=[pixels(x,y+1,z),pixels(x+1,y+1,z),pixels(x+1,y+1,z+1),pixels(x,y+1,z+1)];
    const right=[pixels(x+1,y+1,z),pixels(x+1,y,z),pixels(x+1,y,z+1),pixels(x+1,y+1,z+1)];
    const left=[pixels(x,y+1,z+1),pixels(x+1,y+1,z+1),pixels(x+1,y,z+1),pixels(x,y,z+1)];
    const color=colors[k%colors.length];face(right,tint(color,.62));face(left,tint(color,.79));face(top,color);
  }
  ctx.fillStyle='#a7b7c6';ctx.font='14px system-ui';ctx.fillText(info.kind.replaceAll('_',' ')+' · '+info.blocks+' blocks · '+info.size.join('×'),16,28);
}
$('rotateStructure').onclick=()=>{isoRotation=(isoRotation+1)%4;if(lastStructurePreview)drawIsometric(lastStructurePreview);};
$('addStructure').onclick=addStructure;$('cancelStructure').onclick=resetStructure;$('previewStructure').onclick=previewStructure;$('sliceY').addEventListener('change',previewStructure);
$('blockTab').onclick=()=>chooseTab('block');$('itemTab').onclick=()=>chooseTab('item');$('recipeTab').onclick=()=>chooseTab('recipe');$('structureTab').onclick=()=>chooseTab('structure');$('addObject').onclick=addObject;$('cancelObject').onclick=resetObject;$('addRecipe').onclick=addRecipe;$('cancelRecipe').onclick=resetRecipe;$('exportHmod').onclick=()=>exportFile('/api/hmod','hmod');$('exportSource').onclick=()=>exportFile('/api/export','zip');$('preview').onclick=inspect;$('doctor').onclick=runDoctor;$('closeInspect').onclick=()=>$('inspectPanel').hidden=true;$('saveProject').onclick=saveProject;$('undoEdit').onclick=undoProject;$('redoEdit').onclick=redoProject;$('restoreWorkspace').onclick=acceptDiskWorkspace;$('keepEditor').onclick=keepEditorWorkspace;$('demo').onclick=example;$('loadProject').onclick=()=>$('projectFile').click();
$('projectFile').onchange=async()=>{const file=$('projectFile').files[0];if(!file)return;try{if(file.size>6*1024*1024)throw new Error(t('fileTooBig'));const response=await studioPost('/api/project/open',await file.text());const opened=await response.json();if(!response.ok)throw new Error(opened.error||t('badProject'));applyProject(opened.state);const problems=opened.diagnostics.filter(d=>d.level==='error').length;await api('/api/preview');status(opened.migrated_from!=null?t('projectMigrated',{schema:opened.migrated_from}):problems?t('projectProblems',{count:problems}):t('projectOpened'));}catch(e){status(e.message,true);}finally{$('projectFile').value='';}};
const compactLayout=window.matchMedia('(max-width:1100px)');
function sidebarVisible(){return compactLayout.matches?document.body.classList.contains('sidebar-open'):!document.body.classList.contains('sidebar-collapsed');}
function toggleExplorer(){document.body.classList.toggle(compactLayout.matches?'sidebar-open':'sidebar-collapsed');$('toggleExplorer').setAttribute('aria-expanded',String(sidebarVisible()));}
$('toggleExplorer').onclick=toggleExplorer;
compactLayout.addEventListener('change',()=>{document.body.classList.remove('sidebar-open');$('toggleExplorer').setAttribute('aria-expanded',String(sidebarVisible()));});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('sidebar-open')){document.body.classList.remove('sidebar-open');$('toggleExplorer').setAttribute('aria-expanded','false');$('toggleExplorer').focus();}});
$('toggleExplorer').setAttribute('aria-expanded',String(sidebarVisible()));$('quickExport').onclick=()=>exportFile('/api/hmod','hmod');
window.addEventListener('keydown',event=>{if(!(event.ctrlKey||event.metaKey)||event.altKey)return;const tag=event.target?.tagName;if(['INPUT','TEXTAREA','SELECT'].includes(tag)||event.target?.isContentEditable||!$('sourceWorkbench').hidden)return;const key=event.key.toLowerCase();if(key==='z'&&!event.shiftKey){event.preventDefault();undoProject();}else if(key==='y'||(key==='z'&&event.shiftKey)){event.preventDefault();redoProject();}});
for(const id of META)$(id).addEventListener('change',()=>{persist();if(workspaceSync.id!==meta().id)beginWorkspaceSession();});
// Another tab (or an AI change approved elsewhere) may have moved the project on: look on return.
window.addEventListener('focus',()=>workspaceSync.check());document.addEventListener('visibilitychange',()=>{if(!document.hidden)workspaceSync.check();});
for(const id of ['modId','modName'])$(id).addEventListener('input',updateWorkspaceMeta); if($('entrySearch'))$('entrySearch').addEventListener('input',render);
// Preferences kept by the core (~/.horizon-studio/prefs.json): the desktop window's page storage starts empty at
// every launch (its core gets a new local port), so the language and the last project come back from there.
const prefs={remembered:{lang:null,last_project:null}};
async function readPrefs(){
  try{const r=await studioPost('/api/prefs',JSON.stringify({}));if(r.ok)prefs.remembered=await r.json();}catch(_){}
  return prefs.remembered;
}
function rememberPrefs(update){
  const changed=Object.entries(update).some(([k,v])=>prefs.remembered[k]!==v);
  if(!changed)return;
  Object.assign(prefs.remembered,update);
  studioPost('/api/prefs',JSON.stringify({set:update})).catch(()=>{});
}
async function reopenLastProject(remembered){
  if(!remembered.last_project||!VALID.test(remembered.last_project))return false;
  try{
    const r=await studioPost('/api/tx/open',JSON.stringify({project_id:remembered.last_project}));
    if(!r.ok)return false;
    applyProject((await r.json()).state);
    status(t('lastProjectReopened',{id:remembered.last_project}));
    return true;
  }catch(_){return false;}
}
function startEmpty(){chooseTab('recipe');editJournal.reset(editorState());beginWorkspaceSession();}
(async()=>{
  let cached=null;
  try{cached=JSON.parse(localStorage.getItem('horizonStudio_v02')||'null');}catch(_){cached=null;}
  let storedLanguage=null;
  try{storedLanguage=localStorage.getItem('horizonStudio.language');}catch(_){}
  const remembered=await readPrefs();
  if(!storedLanguage&&remembered.lang&&remembered.lang!==window.HorizonI18n.language)window.HorizonI18n.select(remembered.lang);
  try{if(cached){applyProject(cached);return;}}catch(_){}
  if(!(await reopenLastProject(remembered)))startEmpty();
})();
for(const lang of ['en','ru'])$('lang-'+lang).addEventListener('click',()=>rememberPrefs({lang}));
document.addEventListener('studio:workspace-ready',event=>rememberPrefs({last_project:event.detail.id}));
// HS-025: effects are part of the editor state, so save, autosave, undo and reopen cover them.
const vfxStudio=window.HorizonVfxStudio.mount({effects:()=>state.effects,commit:list=>{state.effects=list;persist();document.dispatchEvent(new Event('studio:state-changed'));},
  newUid,t,status,target:()=>state.target});
// HS-020/HS-022: AI proposals reviewed and applied through the same transactions as every edit.
const aiCreator=window.HorizonAiCreator.mount({t,sync:workspaceSync,post:studioPost,snapshot:editorState,status,undo:undoProject,
  assets:()=>[...state.blocks.map(e=>({kind:'block',id:e.id,name:e.name})),...state.items.map(e=>({kind:'item',id:e.id,name:e.name}))]});
// HS-033: every workbench command in one keyboard palette (Ctrl+K). Each runs the real control.
const PALETTE=[['loadProject','project'],['saveProject','project'],['demo','project'],['toggleExplorer','view'],
  ['undoEdit','edit','Ctrl+Z'],['redoEdit','edit','Ctrl+Shift+Z'],['blockTab','view'],['itemTab','view'],['recipeTab','view'],
  ['structureTab','view'],['openWorkbench','tools'],['openVfx','tools'],['openAi','tools'],['openJourney','tools'],['openCapabilities','tools'],
  ['doctor','tools'],['preview','export'],['exportHmod','export'],['exportSource','export'],['lang-en','language'],['lang-ru','language']];
// Typing in the palette also finds the project's assets: choosing one opens it for editing (HS-033 asset search).
function openAsset(kind,index){
  if($('entrySearch'))$('entrySearch').value='';
  chooseTab(kind);
  $('entries').querySelector(`[data-edit="${index}"]`)?.click();
}
function assetCommands(){
  const groups=[['block','blocks'],['item','items'],['recipe','recipes'],['structure','structures']];
  const out=groups.flatMap(([kind,key])=>(state[key]||[]).map((e,i)=>({id:`asset-${kind}-${i}`,
    label:`${kind==='recipe'?displayName(e.result)+' ⇐ '+e.id:e.name||e.id} (${kind}:${e.id})`,group:t('paletteGroup_asset'),
    keywords:[e.id,`${kind}:${e.id}`,e.name_ru||''],searchOnly:true,available:()=>true,run:()=>openAsset(kind,i)})));
  for(const e of state.effects||[])out.push({id:`asset-vfx-${e.uid}`,label:`${e.name||e.id} (vfx:${e.id})`,group:t('paletteGroup_asset'),
    keywords:[e.id,`vfx:${e.id}`],searchOnly:true,available:()=>true,run:()=>{$('openVfx').click();vfxStudio.select(e.uid);}});
  return out;
}
const palette=window.HorizonPalette.mount({t,commands:()=>[...PALETTE.map(([id,group,shortcut])=>{const el=$(id);
  const label=(el?.getAttribute('aria-label')||el?.getAttribute('title')||el?.textContent||id).trim();
  return {id,label,group:t('paletteGroup_'+group),shortcut,keywords:[id,el?.dataset.paletteKeywords||''],
    available:()=>Boolean(el&&!el.disabled),run:()=>el.click()};}),...assetCommands()]});
$('openPalette').onclick=()=>palette.open();
window.HorizonI18n.init(); updateWorkspaceMeta();historyButtons();workbench.shell(null);
if(desktop.available()){
  document.body.classList.add('desktop');
  desktop.ready({title:document.title,lang:document.documentElement.lang,scripts:document.scripts.length,
    entries:state.blocks.length+state.items.length+state.recipes.length+state.structures.length})
    .then(info=>{document.body.dataset.shell=info.shell;workbench.shell(info);})
    .catch(error=>status(error.message,true));
}
