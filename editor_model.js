/* Editor state logic without DOM access: generator payloads, project checks, stable IDs,
 * reference rewrites and search. Browser and Node-compatible. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonStudioModel=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const VALID=/^[a-z][a-z0-9_]{0,63}$/;
  const LIMITS={blocks:32,items:32,recipes:64,structures:8,effects:16};

  /** '@ruby' -> 'mod:ruby'; vanilla names and empty slots are unchanged. */
  function localRef(ref,modId){return ref&&ref.startsWith('@')?`${modId}:${ref.slice(1)}`:ref;}

  /** The request the local packager builds a .hmod from. */
  function generatorPayload(meta,state){
    return {...meta,blocks:state.blocks,items:state.items,structures:state.structures,
      source_overrides:state.source_overrides||{},
      recipes:state.recipes.map(r=>({...r,grid:r.grid.map(x=>localRef(x,meta.id)),result:localRef(r.result,meta.id)}))};
  }

  /** What the editor saves, autosaves and keeps in history (carry holds opaque plugin data). */
  function editorSnapshot(meta,state){
    const snapshot={metadata:meta,blocks:state.blocks,items:state.items,recipes:state.recipes,structures:state.structures,
      source_overrides:state.source_overrides||{},carry:state.carry||{}};
    if(state.target)snapshot.target=state.target;  // HS-008: the engine revision the project is built for
    if(state.effects?.length)snapshot.effects=state.effects;  // HS-025: Studio-only VFX, never exported
    return snapshot;
  }

  /** The i18n key describing why ``data`` cannot be opened, or null. */
  function projectProblem(data){
    if(typeof data!=='object'||!data||!data.metadata||!Array.isArray(data.blocks)||!Array.isArray(data.items)||!Array.isArray(data.recipes))return 'badProject';
    if(data.structures!==undefined&&!Array.isArray(data.structures))return 'badProject';
    if(data.effects!==undefined&&!Array.isArray(data.effects))return 'badProject';
    for(const [group,limit] of Object.entries(LIMITS))if((data[group]||[]).length>limit)return 'projectLimit';
    for(const e of [...data.blocks,...data.items,...data.recipes,...(data.structures||[]),...(data.effects||[])])
      if(typeof e!=='object'||!e||!VALID.test(e.id))return 'badId';
    return null;
  }

  /** Give every object without one a uid; existing uids are never changed. */
  function assignMissingUids(state,newUid){
    for(const e of [...state.blocks,...state.items,...state.recipes,...state.structures,...(state.effects||[])])
      if(!e.uid){const uid=newUid();if(uid)e.uid=uid;}
    return state;
  }

  /** After renaming a block or item, point recipes at the new id. */
  function renameReferences(recipes,oldId,newId){
    const from='@'+oldId,to='@'+newId;
    for(const r of recipes){r.result=r.result===from?to:r.result;r.grid=r.grid.map(x=>x===from?to:x);}
    return recipes;
  }

  /** Recipes that use a block or item as result or ingredient. */
  function recipesUsing(recipes,id){const ref='@'+id;return recipes.filter(r=>r.result===ref||r.grid.includes(ref));}

  function displayName(ref,entries){return ref?.startsWith('@')?entries.find(e=>e.id===ref.slice(1))?.name||ref:ref;}

  function matchesSearch(entry,query,tab,entries){
    const q=String(query||'').trim().toLowerCase();if(!q)return true;
    const hay=tab==='recipe'
      ?[entry.id,displayName(entry.result,entries),entry.type,entry.station||'crafting_table']
      :[entry.id,entry.name,entry.name_ru||'',entry.template||''];
    return hay.join(' ').toLowerCase().includes(q);
  }

  return {VALID,LIMITS,localRef,generatorPayload,editorSnapshot,projectProblem,assignMissingUids,renameReferences,
    recipesUsing,displayName,matchesSearch};
});
