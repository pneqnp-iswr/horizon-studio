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
  const GROUPS=[['official-static','capAvailable','i-check','cap-ok'],['engine-only','capEngineOnly','i-lock','cap-engine'],
    ['unsupported','capUnsupported','i-warning','cap-missing']];
  function esc(value){
    return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  const localized=(obj,key,lang)=>lang==='ru'&&obj[key+'_ru']?obj[key+'_ru']:obj[key];

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
        `<span>${esc(capability)}</span><span class="tiny-badge" title="${esc(users.join(', '))}">${users.length}</span>`+
        `<span class="sr-only">${esc(t(ok?'capAvailable':'capMissing'))}</span></li>`;
    }).join('');
  }

  /** Why an export must not happen, or '' when the target engine can load everything. */
  function exportBlockReason(result,t){
    const errors=(result.diagnostics||[]).filter(d=>d.level==='error');
    return errors.length?t('exportBlocked',{details:errors.map(d=>d.message).join('; ')}):'';
  }

  function journeyMarkup(view,lang,t){
    const status=s=>esc(t('status_'+s));
    const milestone=m=>`<li><span class="marker ${esc(m.status)}" aria-hidden="true"></span><div><b>${esc(m.id)} · ${esc(localized(m,'title',lang))}</b><small>${status(m.status)}</small></div></li>`;
    const phases=view.phases.map(p=>`<li class="${p.id===view.current_phase?'current':''}"><span class="marker ${esc(p.status)}" aria-hidden="true"></span>`+
      `<div><b>${esc(p.id)} · ${esc(localized(p,'name',lang))}</b><small>${status(p.status)} — ${esc(localized(p,'summary',lang))}</small></div></li>`).join('');
    const ladder=view.verification.map(v=>`<li><span class="marker ${esc(v.status)}" aria-hidden="true"></span><div><b>${esc(localized(v,'name',lang))}</b><small>${status(v.status)} — ${esc(localized(v,'detail',lang))}</small></div></li>`).join('');
    const build=view.build;
    const groups=GROUPS.map(([key,label,icon,cls])=>{
      const items=build.groups[key]||[];
      if(!items.length)return '';
      return `<h3>${esc(t(label))}</h3><ul class="capability-list">`+items.map(c=>`<li class="${cls}"><span class="ico ${icon}" aria-hidden="true"></span><span><b>${esc(c.capability)}</b>${c.note?`<small> — ${esc(c.note)}</small>`:''}</span></li>`).join('')+'</ul>';
    }).join('');
    return `<section aria-labelledby="journeyPlanHeading"><h3 id="journeyPlanHeading">${esc(t('journeyPlan'))}</h3>`+
      `<p class="journey-note">${esc(t('journeyPlanNote'))}</p>`+
      `<img class="journey-map" src="/assets/roadmap/roadmap-overview.svg" alt="${esc(t('journeyMapAlt'))}">`+
      `<ol class="phase-list">${phases}</ol>`+
      `<h3>${esc(t('journeyNow'))}</h3><ul class="phase-list">${view.active_milestone?milestone(view.active_milestone):''}${view.next_milestones.map(milestone).join('')}</ul>`+
      `<h3>${esc(t('journeyEvidence'))}</h3><ul class="ladder">${ladder}</ul></section>`+
      `<section id="journeyBuild" aria-labelledby="journeyBuildHeading"><h3 id="journeyBuildHeading">${esc(t('journeyBuild'))}</h3>`+
      `<p class="journey-note">${esc(t('journeyBuildNote',{label:build.label,api:build.content_api}))}</p>${groups}</section>`;
  }

  function init(ctx){
    const $=id=>document.getElementById(id);
    const {t,post,snapshot}=ctx;
    let journey=null,lastCheck=null,timer=null,returnFocus=null;

    for(const button of document.querySelectorAll('.outline-btn[data-kind]'))button.onclick=()=>ctx.chooseTab(button.dataset.kind);

    async function check(){
      const response=await post('/api/capabilities/check',JSON.stringify(snapshot()));
      if(!response.ok)return null;
      return response.json();
    }
    function showEngine(result){
      if(!result)return;
      lastCheck=result;
      const profile=result.profile;
      $('engineProfile').textContent=profile?t('engineProfile',{label:profile.label,api:profile.content_api}):t('capUnknownProfile');
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
    function renderJourney(){
      if($('journeyDialog').hidden||!journey)return;
      $('journeyBody').innerHTML=journeyMarkup(journey,window.HorizonI18n.language,t);
    }
    async function openJourney(focusBuild=false){
      returnFocus=document.activeElement;
      $('journeyDialog').hidden=false;
      $('closeJourney').focus();
      try{await loadJourney();renderJourney();if(focusBuild)$('journeyBuild')?.scrollIntoView({block:'start'});}
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

    function update({meta,counts,tab}){
      $('topProjectName').textContent=meta.name||meta.id||'—';
      $('topProjectId').textContent=meta.id||'';
      for(const kind of KINDS){
        $('count'+kind[0].toUpperCase()+kind.slice(1)).textContent=String(counts[kind]);
        const button=document.querySelector(`.outline-btn[data-kind="${kind}"]`);
        button.classList.toggle('selected',kind===tab);
        button.setAttribute('aria-current',kind===tab?'true':'false');
        $(kind+'Tab').setAttribute('aria-selected',String(kind===tab));
      }
      document.body.dataset.tab=tab;
      refreshEngine();
    }
    function shell(info){
      $('shellStatus').textContent=info?t('desktopMode',{version:info.shell}):t('browserMode');
      $('shellStatus').dataset.version=info?info.shell:'';
    }
    function refreshLanguage(){
      if(lastCheck)showEngine(lastCheck);
      shell($('shellStatus').dataset.version?{shell:$('shellStatus').dataset.version}:null);
      renderJourney();
    }
    return {update,shell,exportGate,refreshEngine,refreshLanguage,openJourney,closeJourney};
  }

  return {KINDS,esc,emptyStateMarkup,capabilityMarkup,exportBlockReason,journeyMarkup,init};
});
