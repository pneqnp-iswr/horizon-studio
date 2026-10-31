/* The editor's side of HS-020 transactions. The core owns each project's revision and history;
 * the editor holds a view of it and sends commands: one commit per user action, undo, redo, and
 * approval of AI proposals. Every command names the revision it was made against, so another tab
 * or an AI change can never be silently overwritten (409 opens an explicit choice instead).
 * Browser and Node-compatible; all IO is injected. Protocol: docs/architecture/TRANSACTIONS.md */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonStudioWorkspace=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const EMPTY=Object.freeze({undo:[],redo:[]});

  class TransactionError extends Error{
    constructor(message,code,status){super(message);this.code=code||'ERROR';this.status=status||0;}
  }

  /**
   * deps.post(path, body) -> fetch-like Response; deps.snapshot() -> editor state;
   * deps.projectId() -> current mod id; deps.isValidId(id); deps.apply(state) loads the core's
   * state into the editor; deps.notify(key, values, mode) shows status; deps.onHistory(history)
   * receives {undo:[...], redo:[...]} (newest first) whenever it changes.
   */
  function createWorkspaceSync(deps){
    const {post,snapshot,projectId,isValidId,apply,notify}=deps;
    const onHistory=deps.onHistory||(()=>{});
    const disk={id:null,revision:null,mode:'checking',generation:0,history:EMPTY,pending:0};
    let queue=Promise.resolve();
    const notice=(key,values={})=>notify(key,values,disk.mode);

    async function call(path,body){
      const response=await post(path,JSON.stringify(body));
      let data={};
      try{data=await response.json();}catch(error){data={};}
      return {status:response.status,ok:response.ok,data};
    }
    const failure=r=>new TransactionError(r.data.error||'Workspace request failed',r.data.code,r.status);
    const isConflict=r=>r.status===409&&(r.data.code==='REVISION_CONFLICT'||!r.data.code);
    function setHistory(history){disk.history=history||EMPTY;onHistory(disk.history);}
    function conflict(){disk.mode='conflict';setHistory(EMPTY);notice('workspaceRecoverable');}
    const current=(generation,id)=>disk.generation===generation&&disk.id===id;

    /** Commands run one at a time, in order; a project switch cancels the ones still waiting. */
    function enqueue(task){
      const generation=disk.generation,id=disk.id;
      disk.pending++;
      const run=queue.then(()=>current(generation,id)?task(generation,id):undefined)
        .catch(error=>{
          if(current(generation,id))notice('workspaceError',{error:error.message});
          if(error instanceof TransactionError)return {error};
          return {error:new TransactionError(error.message)};
        })
        .finally(()=>{disk.pending--;});
      queue=run;
      return run;
    }
    /** The core's state after undo, redo or an approved proposal; skipped if newer edits wait. */
    function adopt(data){
      disk.revision=data.revision;setHistory(data.history);
      if(disk.pending<=1)apply(data.state);
    }

    async function open(id,state){
      const r=await call('/api/tx/open',state===undefined?{project_id:id}:{project_id:id,state});
      if(r.status===404)return null;
      if(!r.ok)throw failure(r);
      return r.data;
    }
    async function commit(state,label,generation,id){
      if(disk.mode!=='ready')return {skipped:true};
      notice('workspacePending');
      const r=await call('/api/tx/commit',{state,base_revision:disk.revision,label:label||null});
      if(!current(generation,id))return {skipped:true};
      if(isConflict(r)){conflict();return {conflict:true};}
      if(!r.ok)throw failure(r);
      disk.revision=r.data.revision;setHistory(r.data.history);
      notice('workspaceSaved');
      return {entry:r.data.entry};
    }

    /** One user action is one transaction. Returns false when the editor is not attached to a
     * workspace (invalid ID, core unavailable, unresolved conflict): the caller keeps local history. */
    function record(label){
      if(disk.mode!=='ready'||disk.id!==projectId())return false;
      const state=snapshot();
      enqueue((generation,id)=>commit(state,label,generation,id));
      return true;
    }
    function step(kind){
      if(disk.mode!=='ready')return false;
      enqueue(async(generation,id)=>{
        const r=await call('/api/tx/'+kind,{project_id:id,expected_revision:disk.revision});
        if(!current(generation,id))return;
        if(isConflict(r)){conflict();return;}
        if(r.status===409&&(r.data.code==='NOTHING_TO_UNDO'||r.data.code==='NOTHING_TO_REDO'))return;
        if(!r.ok)throw failure(r);
        adopt(r.data);
        notice('workspaceSaved');
      });
      return true;
    }

    /** Start following the current project: adopt it, create it, or ask when disk and editor differ. */
    async function begin(){
      const id=projectId(),generation=++disk.generation;
      disk.id=id;disk.revision=null;disk.mode='checking';setHistory(EMPTY);
      if(!isValidId(id)){disk.mode='invalid';notice('workspaceInvalidId');return;}
      notice('workspaceChecking');
      try{
        const sent=snapshot();
        const data=await open(id,sent);
        if(generation!==disk.generation)return;
        disk.mode='ready';
        if(!data){  // a new project: its first commit creates the workspace (no history entry)
          enqueue((g,i)=>commit(sent,null,g,i));
          if(JSON.stringify(snapshot())!==JSON.stringify(sent))record();  // edited while checking
          return;
        }
        disk.revision=data.revision;
        if(data.matches){
          setHistory(data.history);notice('workspaceSaved');
          if(JSON.stringify(snapshot())!==JSON.stringify(sent))record();  // edited while checking
        }else{conflict();}
      }catch(error){
        if(generation===disk.generation){disk.mode='unavailable';notice('workspaceError',{error:error.message});}
      }
    }
    /** Another tab or process may have changed the project: look before the next edit does. */
    async function check(){
      if(disk.mode!=='ready'||disk.pending||disk.revision===null)return;
      const id=disk.id,generation=disk.generation;
      try{
        const data=await open(id,snapshot());
        if(!current(generation,id)||disk.pending||disk.mode!=='ready')return;
        if(!data){conflict();return;}
        if(data.revision===disk.revision||data.matches){disk.revision=data.revision;setHistory(data.history);}
        else conflict();
      }catch(error){/* the next command reports it */}
    }
    /** Conflict choice: load the core's copy into the editor. */
    async function restoreDisk(){
      if(disk.mode!=='conflict')return;
      const id=disk.id,generation=disk.generation;
      try{
        const data=await open(id);
        if(!data)throw Error('Workspace disappeared');
        if(generation!==disk.generation)return;
        disk.generation++; // Cancel queued commands from the old editor snapshot.
        apply(data.state);
        disk.id=id;disk.revision=data.revision;disk.mode='ready';setHistory(data.history);
        notice(data.recovered_from_backup?'workspaceBackupRecovered':'workspaceRecovered');
      }catch(error){notice('workspaceError',{error:error.message});}
    }
    /** Conflict choice: commit the editor's state on top of the current revision (undoable). */
    async function keepEditor(){
      if(disk.mode!=='conflict')return;
      const id=disk.id,generation=disk.generation;
      try{
        const data=await open(id);
        if(generation!==disk.generation)return;
        disk.generation++; // Drop queued commands made against the old revision.
        disk.revision=data?data.revision:null;disk.mode='ready';setHistory(data?data.history:EMPTY);
        record("Keep this editor's version");
      }catch(error){notice('workspaceError',{error:error.message});}
    }

    // -- AI proposals: the core plans and validates; a person approves or rejects. -------------
    async function propose(request,provider='fixture',requestId=null){
      await queue;
      if(disk.mode!=='ready'||disk.revision===null)
        throw new TransactionError('The project is not attached to a workspace','DETACHED');
      const r=await call('/api/ai/propose',{project_id:disk.id,base_revision:disk.revision,provider,request,
        ...(requestId?{request_id:requestId}:{})});
      if(isConflict(r)){conflict();throw failure(r);}
      if(!r.ok)throw failure(r);
      return r.data;
    }
    function approve(proposalId){
      if(disk.mode!=='ready')return Promise.resolve({error:new TransactionError('Not attached','DETACHED')});
      return enqueue(async(generation,id)=>{
        const r=await call('/api/ai/commit',{project_id:id,proposal_id:proposalId,expected_revision:disk.revision});
        if(!current(generation,id))return {skipped:true};
        if(r.status===409&&r.data.code==='STALE_PROPOSAL')return {error:failure(r)};
        if(isConflict(r)){conflict();return {error:failure(r)};}
        if(!r.ok)return {error:failure(r)};
        adopt(r.data);
        notice('workspaceSaved');
        return {entry:r.data.entry};
      });
    }
    async function reject(proposalId){
      const r=await call('/api/ai/reject',{project_id:disk.id,proposal_id:proposalId});
      if(!r.ok&&r.status!==404)throw failure(r);
      return r.data;
    }

    return {
      get id(){return disk.id;}, get mode(){return disk.mode;}, get revision(){return disk.revision;},
      /** True while the core's history is the editor's history. */
      get tracking(){return disk.mode==='ready';},
      get history(){return disk.history;},
      get canUndo(){return disk.mode==='ready'&&disk.history.undo.length>0;},
      get canRedo(){return disk.mode==='ready'&&disk.history.redo.length>0;},
      get busy(){return disk.pending>0;},
      begin, check, record, undo:()=>step('undo'), redo:()=>step('redo'), restoreDisk, keepEditor,
      propose, approve, reject,
      /** Resolves when every queued command has finished (tests and shutdown). */
      idle:()=>queue,
    };
  }
  return {createWorkspaceSync,TransactionError};
});
