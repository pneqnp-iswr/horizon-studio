/* Disk workspace sync for the editor: debounced autosave with optimistic revisions and
 * an explicit choice on conflicts. Browser and Node-compatible; all IO is injected. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonStudioWorkspace=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  /**
   * deps.post(path, body) -> fetch-like Response; deps.snapshot() -> editor state;
   * deps.projectId() -> current mod id; deps.isValidId(id); deps.apply(state) loads a
   * recovered state into the editor; deps.notify(key, values, mode) shows status.
   */
  function createWorkspaceSync(deps){
    const {post,snapshot,projectId,isValidId,apply,notify}=deps;
    const delay=deps.delay??850, schedule=deps.schedule||setTimeout, cancel=deps.cancel||clearTimeout;
    const disk={id:null,revision:null,mode:'checking',generation:0};
    let timer=null, queue=Promise.resolve();
    const notice=(key,values={})=>notify(key,values,disk.mode);
    const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

    async function read(id){
      const response=await post('/api/workspace/recover',JSON.stringify({project_id:id}));
      if(response.status===404)return null;
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Workspace request failed');
      return data;
    }
    async function flush(state,id,generation){
      if(disk.id!==id||disk.generation!==generation||disk.mode!=='ready')return;
      notice('workspacePending');
      const response=await post('/api/workspace/write',JSON.stringify({state,expected_revision:disk.revision}));
      if(disk.id!==id||disk.generation!==generation)return;
      if(response.status===409){disk.mode='conflict';notice('workspaceRecoverable');return;}
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Workspace request failed');
      disk.revision=data.revision;
      notice('workspaceSaved');
    }
    function scheduleSave(){
      cancel(timer);
      if(disk.mode!=='ready'||disk.id!==projectId())return;
      timer=schedule(()=>{
        const state=snapshot(),id=projectId(),generation=disk.generation;
        queue=queue.then(()=>flush(state,id,generation)).catch(error=>{
          if(disk.id===id&&disk.generation===generation)notice('workspaceError',{error:error.message});
        });
      },delay);
    }
    /** Start syncing the current project: adopt, save, or ask when disk and editor differ. */
    async function begin(){
      cancel(timer);
      const id=projectId(),generation=++disk.generation;
      disk.id=id;disk.revision=null;disk.mode='checking';
      if(!isValidId(id)){disk.mode='invalid';notice('workspaceInvalidId');return;}
      notice('workspaceChecking');
      try{
        const data=await read(id);
        if(generation!==disk.generation)return;
        if(!data){disk.mode='ready';notice('workspacePending');scheduleSave();return;}
        disk.revision=data.revision;
        if(same(data.state,snapshot())){disk.mode='ready';notice('workspaceSaved');}
        else{disk.mode='conflict';notice('workspaceRecoverable');}
      }catch(error){
        if(generation===disk.generation){disk.mode='unavailable';notice('workspaceError',{error:error.message});}
      }
    }
    /** Conflict choice: load the disk copy into the editor. */
    async function restoreDisk(){
      if(disk.mode!=='conflict')return;
      const id=disk.id,generation=disk.generation;
      try{
        const data=await read(id);
        if(!data)throw Error('Workspace disappeared');
        if(generation!==disk.generation)return;
        disk.generation++; // Cancel queued writes from the old editor snapshot.
        apply(data.state);
        disk.id=id;disk.revision=data.revision;disk.mode='ready';
        notice(data.recovered_from_backup?'workspaceBackupRecovered':'workspaceRecovered');
        if(data.recovered_from_backup)scheduleSave();
      }catch(error){notice('workspaceError',{error:error.message});}
    }
    /** Conflict choice: overwrite the disk copy with the editor's state. */
    async function keepEditor(){
      if(disk.mode!=='conflict')return;
      const id=disk.id,generation=disk.generation;
      try{
        const data=await read(id);
        if(generation!==disk.generation)return;
        disk.generation++; // Invalidate queued stale writes before the explicit overwrite.
        disk.revision=data?data.revision:null;disk.mode='ready';
        scheduleSave();
      }catch(error){notice('workspaceError',{error:error.message});}
    }
    return {
      get id(){return disk.id;}, get mode(){return disk.mode;}, get revision(){return disk.revision;},
      begin, scheduleSave, restoreDisk, keepEditor,
      /** Resolves when every queued write has finished (tests and shutdown). */
      idle:()=>queue,
    };
  }
  return {createWorkspaceSync};
});
