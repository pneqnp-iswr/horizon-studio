/* Workbench chrome around the editor: project chip, explorer outline, empty states, the
 * engine-target card (HS-008 capability check, export gate) and the in-app development
 * journey. Markup builders are pure and Node-testable; init() wires them to the page. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonWorkbench=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const KINDS=['block','item','recipe','structure'];
  function esc(value){
    return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function emptyStateMarkup(kind,t){
    return `<div class="empty-state"><span class="ico empty-art i-${esc(kind)}" aria-hidden="true"></span>`+
      `<h2>${esc(t('empty_'+kind+'_title'))}</h2><p>${esc(t('empty_'+kind+'_hint'))}</p>`+
      // The Ruby demo has blocks, items and recipes; structures start from the form instead.
      (kind==='structure'?'':`<button type="button" class="primary" id="emptyDemo">${esc(t('loadDemo'))}</button>`)+'</div>';
  }

  /** Engine card: every capability the project needs, and whether the target can load it. */
  function capabilityMarkup(result,t){
    const missing=new Set((result.diagnostics||[]).map(d=>d.capability).filter(Boolean));
    const needs=Object.entries(result.requirements||{}).sort(([a],[b])=>a.localeCompare(b));
    if(!needs.length)return `<li class="cap-engine">${esc(t('capNone'))}</li>`;
    return needs.map(([capability,users])=>{
      const ok=!missing.has(capability);
      return `<li class="${ok?'cap-ok':'cap-missing'}"><span class="ico ${ok?'i-check':'i-lock'}" aria-hidden="true"></span>`+
        `<code>${esc(capability)}</code><span class="tiny-badge" data-ids title="${esc(users.join(', '))}">${users.length}</span>`+
        `<span class="sr-only">${esc(t(ok?'capAvailable':'capMissing'))}</span></li>`;
    }).join('');
  }

  /** Why an export must not happen, or '' when the target engine can load everything. */
  function exportBlockReason(result,t){
    const errors=(result.diagnostics||[]).filter(d=>d.level==='error');
    return errors.length?t('exportBlocked',{details:errors.map(d=>d.message).join('; ')}):'';
  }

  /** Capabilities whose status differs between two engine profiles (HS-008). */
  function profileDiff(base,other){
    const names=[...new Set([...Object.keys(base.capabilities),...Object.keys(other.capabilities)])].sort();
    return names.map(capability=>({capability,from:base.capabilities[capability]?.status||'absent',
      to:other.capabilities[capability]?.status||'absent',note:other.capabilities[capability]?.note,note_ru:other.capabilities[capability]?.note_ru}))
      .filter(d=>d.from!==d.to);
  }

  function targetOptionsMarkup(data,target,lang,t){
    const label=p=>lang==='ru'&&p.label_ru||p.label;
    const fallback=data.profiles.find(p=>p.revision===data.default);
    const options=[`<option value=""${target?'':' selected'}>${esc(t('engineDefaultOption',{label:label(fallback)}))}</option>`,
      ...data.profiles.map(p=>`<option value="${esc(p.revision)}"${target?.revision===p.revision?' selected':''}>${esc(label(p))}</option>`)];
    if(target&&!data.profiles.some(p=>p.revision===target.revision))
      options.push(`<option value="${esc(target.revision)}" selected>${esc(t('engineUnknownOption',{revision:target.revision.slice(0,7)}))}</option>`);
    return options.join('');
  }

  function diffMarkup(diff,lang,t){
    return diff.map(d=>`<li class="${d.to==='official-static'?'cap-ok':d.to==='engine-only'?'cap-engine':'cap-missing'}">`+
      `<code>${esc(d.capability)}</code> ${esc(t('capStatus_'+d.from))} → ${esc(t('capStatus_'+d.to))}`+
      `${d.note?`<small> — ${esc(lang==='ru'&&d.note_ru||d.note)}</small>`:''}</li>`).join('');
  }

  function init(ctx){
    const $=id=>document.getElementById(id);
    const {t,post,snapshot}=ctx;
    let journey=null,lastCheck=null,timer=null,returnFocus=null;

    for(const button of document.querySelectorAll('.outline-btn[data-kind]'))button.onclick=()=>ctx.chooseTab(button.dataset.kind);
    // Rail kinds follow the ARIA tabs pattern: one tab stop, arrows/Home/End move and select.
    const tabs=KINDS.map(kind=>$(kind+'Tab'));
    for(const tab of tabs){
      tab.setAttribute('aria-controls','canvas');
      tab.addEventListener('keydown',event=>{
        const index=tabs.indexOf(tab),last=tabs.length-1;
        const next={ArrowDown:index+1,ArrowRight:index+1,ArrowUp:index-1,ArrowLeft:index-1,Home:0,End:last}[event.key];
        if(next===undefined)return;
        event.preventDefault();
        const target=tabs[(next+tabs.length)%tabs.length];
        target.focus();
        target.click();
      });
    }

    async function check(){
      const response=await post('/api/capabilities/check',JSON.stringify(snapshot()));
      if(!response.ok)return null;
      return response.json();
    }
    function showEngine(result){
      if(!result)return;
      lastCheck=result;
      const profile=result.profile;
      const label=profile&&(window.HorizonI18n.language==='ru'&&profile.label_ru||profile.label);
      $('engineProfile').textContent=profile?t('engineProfile',{label,api:profile.content_api}):t('capUnknownProfile');
      $('engineCapabilities').innerHTML=capabilityMarkup(result,t);
      const missing=(result.diagnostics||[]).length;
      $('engineStatus').textContent=profile?`Horizon ${profile.revision.slice(0,7)} · API ${profile.content_api}${missing?' · '+t('capMissingCount',{count:missing}):''}`:t('capUnknownProfile');
      $('engineStatus').classList.toggle('cap-missing',Boolean(missing));
    }
    function refreshEngine(){
      clearTimeout(timer);
      timer=setTimeout(()=>check().then(showEngine).catch(()=>{}),250);
    }
    async function exportGate(){
      let result;
      try{result=await check();}catch(_){return '';}
      if(!result)return '';  // an invalid project fails the export itself, with its own message
      showEngine(result);
      return exportBlockReason(result,t);
    }

    async function loadJourney(){
      if(!journey){
        const response=await fetch('/api/journey',{cache:'no-store'});
        if(!response.ok)throw new Error(t('journeyFailed'));
        journey=await response.json();
      }
      return journey;
    }
    let explorer=null;
    function renderJourney(){
      if($('journeyDialog').hidden||!journey)return;
      if(explorer)explorer.render();
      else explorer=window.HorizonRoadmap.mount($('journeyBody'),journey,{t,lang:()=>window.HorizonI18n.language});
    }
    async function openJourney(focusBuild=false){
      returnFocus=document.activeElement;
      $('journeyDialog').hidden=false;
      $('closeJourney').focus();
      try{await loadJourney();renderJourney();explorer.selectTab(focusBuild?'build':'roadmap',false);}
      catch(error){$('journeyBody').textContent=error.message;}
    }
    function closeJourney(){
      if($('journeyDialog').hidden)return;
      $('journeyDialog').hidden=true;
      returnFocus?.focus?.();
    }
    $('openJourney').onclick=()=>openJourney(false);
    $('openCapabilities').onclick=()=>openJourney(true);
    $('closeJourney').onclick=closeJourney;
    document.addEventListener('keydown',event=>{if(event.key==='Escape')closeJourney();});
    // aria-modal: keep Tab inside the open dialog.
    $('journeyDialog').addEventListener('keydown',event=>{
      if(event.key!=='Tab')return;
      const focusable=[...$('journeyDialog').querySelectorAll('button,[href],[tabindex]:not([tabindex="-1"])')].filter(el=>!el.disabled&&el.getClientRects().length);
      const first=focusable[0],last=focusable[focusable.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    });

    let profiles=null;
    async function renderTarget(){
      try{
        if(!profiles){const response=await fetch('/api/engine-profiles',{cache:'no-store'});if(!response.ok)return;profiles=await response.json();}
      }catch(_){return;}
      const lang=window.HorizonI18n.language,target=ctx.getTarget?.()||null;
      $('engineTargetSelect').innerHTML=targetOptionsMarkup(profiles,target,lang,t);
      const base=profiles.profiles.find(p=>p.revision===profiles.default);
      const chosen=target&&profiles.profiles.find(p=>p.revision===target.revision);
      const diff=chosen&&chosen!==base?profileDiff(base,chosen):[];
      $('engineDiff').hidden=!diff.length;
      $('engineDiffTitle').textContent=t('engineDiffTitle',{count:diff.length});
      $('engineDiffList').innerHTML=diffMarkup(diff,lang,t);
    }
    $('engineTargetSelect').addEventListener('change',event=>{
      const revision=event.target.value;
      ctx.setTarget?.(revision?{engine:'horizon',revision}:null);
    });

    function update({meta,counts,tab}){
      $('topProjectName').textContent=meta.name||meta.id||'—';
      $('topProjectId').textContent=meta.id||'';
      for(const kind of KINDS){
        $('count'+kind[0].toUpperCase()+kind.slice(1)).textContent=String(counts[kind]);
        const button=document.querySelector(`.outline-btn[data-kind="${kind}"]`);
        button.classList.toggle('selected',kind===tab);
        button.setAttribute('aria-current',kind===tab?'true':'false');
        $(kind+'Tab').setAttribute('aria-selected',String(kind===tab));
        $(kind+'Tab').tabIndex=kind===tab?0:-1;
      }
      document.body.dataset.tab=tab;
      refreshEngine();
      renderTarget();
    }
    function shell(info){
      $('shellStatus').textContent=info?t('desktopMode',{version:info.shell}):t('browserMode');
      $('shellStatus').dataset.version=info?info.shell:'';
    }
    function refreshLanguage(){
      if(lastCheck)showEngine(lastCheck);
      renderTarget();
      shell($('shellStatus').dataset.version?{shell:$('shellStatus').dataset.version}:null);
      renderJourney();
    }
    return {update,shell,exportGate,refreshEngine,refreshLanguage,openJourney,closeJourney};
  }

  return {KINDS,esc,emptyStateMarkup,capabilityMarkup,exportBlockReason,profileDiff,targetOptionsMarkup,diffMarkup,init};
});
