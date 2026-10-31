/* Bridge to the Horizon Studio desktop shell (desktop/, Tauri 2). In a regular browser
 * every call reports unavailable and the editor keeps its browser behaviour.
 * Browser and Node-compatible; the IPC object is injected for tests. */
(function(root,factory){
  const api=factory(root);
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonDesktop=api;
})(typeof window!=='undefined'?window:null,function(root){
  'use strict';
  function ipc(scope){
    const host=scope||root;
    const internals=host&&host.__TAURI_INTERNALS__;
    return internals&&typeof internals.invoke==='function'?internals:null;
  }
  function available(scope){return Boolean(ipc(scope));}
  function invoke(command,args,options,scope){
    const target=ipc(scope);
    if(!target)return Promise.reject(new Error('Not running in the Horizon Studio desktop shell'));
    return target.invoke(command,args,options);
  }
  /** Native "Save as": resolves {saved:false} when the user cancels the dialog. */
  async function saveFile(blob,name,scope){
    const bytes=new Uint8Array(await blob.arrayBuffer());
    return invoke('save_file',bytes,{headers:{'x-file-name':encodeURIComponent(name)}},scope);
  }
  /** Tells the shell the editor booted; resolves the shell/core versions for the status bar. */
  function ready(info,scope){return invoke('desktop_ready',{info},undefined,scope);}
  /** The core's API session token, which the shell received over its private pipe. */
  function coreSession(scope){return invoke('core_session',undefined,undefined,scope);}
  return Object.freeze({available,invoke,saveFile,ready,coreSession});
});
