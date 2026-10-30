/* Local Studio API client: one per-server session token, then authorized POSTs. */
(function(root){
  'use strict';
  let pending=null;
  function session(){
    if(!pending){
      pending=fetch('/api/session',{cache:'no-store'})
        .then(async response=>{
          if(!response.ok)throw Error('Could not authorize Studio session');
          const data=await response.json();
          if(!data.token)throw Error('Missing Studio session token');
          return data.token;
        })
        .catch(error=>{pending=null;throw error;});
    }
    return pending;
  }
  async function post(path,body,contentType='application/json'){
    const token=await session();
    return fetch(path,{method:'POST',headers:{'Content-Type':contentType,'X-Studio-Token':token},body});
  }
  root.HorizonStudioApi=Object.freeze({session,post});
  root.HorizonStudioPost=post; // used by source_workbench_ui.js
})(window);
