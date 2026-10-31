/* AI Creator panel (HS-020/HS-022): ask a provider for a change, review exactly what it does, and
 * apply it as one step of the project's shared history (the core's transaction protocol, see
 * docs/architecture/TRANSACTIONS.md). Nothing here edits the project directly: proposals are
 * planned and validated by the core, and only an explicit Apply commits one.
 * This build has one provider, the deterministic fixture. It is labelled as simulated everywhere,
 * and it never sends anything off this computer. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonAiCreator=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  /** A value as short readable text: uid references by name, long values cut. */
  function show(value,labels){
    if(value===undefined)return '—';
    if(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===1&&typeof value.ref==='string')
      return '→ '+(labels[value.ref]||value.ref);
    const text=typeof value==='string'?value:JSON.stringify(value,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===1&&typeof v.ref==='string'?'→ '+(labels[v.ref]||v.ref):v);
    return text.length>140?text.slice(0,139)+'…':text;
  }

  /** One line per operation of the plan. */
  function planLines(operations){
    return operations.map(op=>{
      const target=op.asset||(op.kind&&op.id?`${op.kind}:${op.id}`:op.id||op.uid||'');
      const fields=Object.keys(op.set||op.props||{});
      return {tool:op.tool,target,fields};
    });
  }

  function diffMarkup(diff,t){
    if(!diff.assets.length&&!diff.document.length)return `<p class="ai-empty">${esc(t('aiNoChange'))}</p>`;
    const rows=diff.assets.map(a=>`<article class="ai-asset ai-${esc(a.change)}"><header><span class="tiny-badge">${esc(t('aiChange_'+a.change))}</span>`+
      `<b>${esc(a.kind)}:${esc(a.id)}</b></header><table><thead><tr><th>${esc(t('aiField'))}</th><th>${esc(t('aiBefore'))}</th><th>${esc(t('aiAfter'))}</th></tr></thead><tbody>`+
      a.fields.map(f=>`<tr><th scope="row">${esc(f.path)}</th><td>${esc('before' in f?show(f.before,diff.labels):'—')}</td><td>${esc('after' in f?show(f.after,diff.labels):'—')}</td></tr>`).join('')+
      '</tbody></table></article>');
    if(diff.document.length)rows.push(`<p class="ai-doc">${esc(t('aiDocumentFields',{fields:diff.document.join(', ')}))}</p>`);
    return rows.join('');
  }

  /**
   * ctx: {t, sync (the editor's transaction client), snapshot() -> editor state, status(text,error),
   *       undo(), assets() -> [{kind,id,name}]}
   */
  function mount(ctx){
    const $=id=>document.getElementById(id);
    const t=(key,values)=>ctx.t(key,values);
    const ui={proposal:null,asking:0,cancelled:new Set(),applied:null};

    function setError(message){$('aiError').hidden=!message;$('aiError').textContent=message||'';}
    function busy(on){
      $('aiPropose').disabled=on;$('aiCancel').hidden=!on;
      $('aiProgress').textContent=on?t('aiAsking'):'';
    }
    function intent(){return $('aiIntent').value;}
    function showFields(){for(const name of ['material_set','update','impact_effect'])$('aiFields_'+name).hidden=name!==intent();}

    function assetOptions(){
      const current=$('aiAsset').value;
      $('aiAsset').innerHTML=ctx.assets().filter(a=>a.kind==='block'||a.kind==='item')
        .map(a=>`<option value="${esc(a.kind+':'+a.id)}">${esc(a.kind+':'+a.id)}${a.name?' — '+esc(a.name):''}</option>`).join('');
      if([...$('aiAsset').options].some(o=>o.value===current))$('aiAsset').value=current;
    }
    function request(){
      if(intent()==='material_set'){
        return {intent:'material_set',material:$('aiMaterial').value.trim(),name:$('aiMaterialName').value.trim()||undefined,
          rarity:$('aiRarity').value};
      }
      if(intent()==='update'){
        const field=$('aiField').value,raw=$('aiValue').value.trim();
        const numeric=field==='hardness'||field==='light';
        return {intent:'update',asset:$('aiAsset').value,set:{[field]:numeric?Number(raw):raw}};
      }
      const seed=$('aiSeed').value.trim();
      return {intent:'impact_effect',id:$('aiEffectId').value.trim(),name:$('aiEffectName').value.trim()||undefined,
        ...(seed?{seed:Number(seed)}:{})};
    }
    /** What the provider receives: the core gives it inspect_project (metadata, target, counts, revision). */
    function context(){
      const s=ctx.snapshot();
      const counts={blocks:s.blocks.length,items:s.items.length,recipes:s.recipes.length,structures:s.structures.length,effects:(s.effects||[]).length};
      $('aiContextView').textContent=JSON.stringify({project:{id:s.metadata.id,name:s.metadata.name,version:s.metadata.version},
        target:s.target||null,counts,revision:ctx.sync.revision?ctx.sync.revision.slice(0,12)+'…':null},null,2);
    }

    function render(){
      const p=ui.proposal;
      $('aiApply').disabled=!p||p.errors>0;$('aiReject').disabled=!p;
      if(!p){
        $('aiSummary').textContent=t('aiNoProposal');$('aiPlan').innerHTML='';$('aiDiff').innerHTML='';$('aiDiagnostics').innerHTML='';
        return;
      }
      $('aiSummary').textContent=t('aiProposalSummary',{summary:p.summary,count:p.operations.length});
      $('aiPlan').innerHTML=planLines(p.operations).map(l=>`<li><code>${esc(l.tool)}</code> ${esc(l.target)}${l.fields.length?` <small>(${esc(l.fields.join(', '))})</small>`:''}</li>`).join('');
      $('aiDiff').innerHTML=diffMarkup(p.diff,t);
      $('aiDiagnostics').innerHTML=p.diagnostics.length?p.diagnostics.map(d=>`<li class="vfx-${esc(d.level)}" data-code="${esc(d.code)}">${esc(d.message)}</li>`).join('')
        :`<li>${esc(t('aiValid'))}</li>`;
    }
    function renderHistory(){
      const history=ctx.sync.history||{undo:[],redo:[]};
      const item=(e,state)=>`<li class="ai-step ${state}"><span class="tiny-badge">${esc(e.actor&&e.actor.startsWith('ai:')?t('aiActorAi'):t('aiActorPerson'))}</span>`+
        `${esc(e.label)}${e.approved_by?` <small>${esc(t('aiApprovedBy'))}</small>`:''}${state==='redo'?` <small>${esc(t('aiUndone'))}</small>`:''}</li>`;
      const rows=[...history.redo.slice().reverse().map(e=>item(e,'redo')),...history.undo.map(e=>item(e,'done'))];
      $('aiHistory').innerHTML=rows.length?rows.join(''):`<li class="ai-empty">${esc(ctx.sync.tracking?t('aiHistoryEmpty'):t('aiDetached'))}</li>`;
    }

    async function propose(event){
      event.preventDefault();
      setError('');ui.applied=null;$('aiUndo').hidden=true;
      if(ui.proposal){await discard();}
      const ticket=++ui.asking;
      busy(true);
      try{
        const proposal=await ctx.sync.propose(request(),$('aiProvider').value);
        if(ui.cancelled.has(ticket)){await ctx.sync.reject(proposal.id).catch(()=>{});return;}  // asked, then cancelled
        proposal.errors=proposal.diagnostics.filter(d=>d.level==='error').length;
        ui.proposal=proposal;render();
        ctx.status(t('aiProposed'));
      }catch(error){
        if(!ui.cancelled.has(ticket))setError(explain(error));
      }finally{
        if(ticket===ui.asking)busy(false);
      }
    }
    function cancel(){ui.cancelled.add(ui.asking);busy(false);$('aiProgress').textContent=t('aiCancelled');}
    function explain(error){
      const known={STALE_PROPOSAL:'aiStale',REVISION_CONFLICT:'aiConflict',DETACHED:'aiDetached',UNKNOWN_PROPOSAL:'aiExpired',
        UNKNOWN_ASSET:'aiUnknownAsset',INVALID_RESULT:'aiInvalid',UNSUPPORTED_REQUEST:'aiUnsupported',BAD_REQUEST:'aiBadRequest'};
      return known[error.code]?t(known[error.code],{error:error.message}):error.message;
    }
    async function apply(){
      const p=ui.proposal;if(!p)return;
      $('aiApply').disabled=true;
      const outcome=await ctx.sync.approve(p.id);
      ui.proposal=null;render();
      if(outcome&&outcome.entry){
        ui.applied=outcome.entry;$('aiUndo').hidden=false;
        ctx.status(t('aiApplied',{label:outcome.entry.label}));setError('');
      }else if(outcome&&outcome.error){
        setError(explain(outcome.error));
      }
      renderHistory();
    }
    async function discard(){
      const p=ui.proposal;if(!p)return;
      ui.proposal=null;render();
      try{await ctx.sync.reject(p.id);}catch(error){/* already gone: nothing to reject */}
    }
    async function reject(){await discard();ctx.status(t('aiRejected'));}

    function open(){
      $('aiDialog').hidden=false;assetOptions();context();render();renderHistory();showFields();
      $('aiIntent').focus();
    }
    function close(){$('aiDialog').hidden=true;$('openAi').focus();}

    $('openAi').addEventListener('click',open);
    $('closeAi').addEventListener('click',close);
    $('aiDialog').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}});
    $('aiRequest').addEventListener('submit',propose);
    $('aiIntent').addEventListener('change',showFields);
    $('aiCancel').addEventListener('click',cancel);
    $('aiApply').addEventListener('click',apply);
    $('aiReject').addEventListener('click',reject);
    $('aiUndo').addEventListener('click',()=>{ctx.undo();$('aiUndo').hidden=true;});
    document.addEventListener('studio:history-changed',()=>{if(!$('aiDialog').hidden){renderHistory();context();}});
    document.addEventListener('studio:state-changed',()=>{if(!$('aiDialog').hidden){assetOptions();context();}});
    return {open,close,get proposal(){return ui.proposal;}};
  }
  return {mount,show,planLines,diffMarkup};
});
