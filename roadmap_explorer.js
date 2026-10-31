/* Development journey explorer: every phase and milestone of docs/roadmap/roadmap.json
 * (served as /api/journey), with search, filters, dependencies and evidence, kept apart from
 * what the installed build can do. Markup builders are pure and Node-testable; mount() wires
 * one explorer into a container. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonRoadmap=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const STATUSES=['done','partial','in_progress','planned','blocked'];
  const GROUPS=[['official-static','capAvailable','i-check','cap-ok'],['engine-only','capEngineOnly','i-lock','cap-engine'],
    ['unsupported','capUnsupported','i-warning','cap-missing']];
  function esc(value){
    return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  const pick=(obj,key,lang)=>lang==='ru'&&obj[key+'_ru']?obj[key+'_ru']:obj[key];
  const byId=view=>new Map(view.milestones.map(m=>[m.id,m]));
  // Only https links and repository-relative paths become links; anything else (javascript:, data:, …) is text.
  const safeUrl=url=>typeof url==='string'&&(/^https:\/\//i.test(url)||/^(?![a-z][a-z0-9+.-]*:|\/\/)[\w./#-]+$/i.test(url));
  const link=(url,text)=>safeUrl(url)?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`:esc(text);

  function phaseProgress(view,phase){
    const items=view.milestones.filter(m=>m.phase===phase.id&&m.track==='studio');
    return {done:items.filter(m=>m.status==='done').length,total:items.length};
  }

  /** Milestones matching a filter, in roadmap order. */
  function filterMilestones(view,{phase='all',query='',statuses=STATUSES,track='all'}={}){
    const words=query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const allowed=new Set(statuses);
    return view.milestones.filter(m=>{
      if(phase!=='all'&&m.phase!==phase)return false;
      if(track!=='all'&&m.track!==track)return false;
      if(!allowed.has(m.status))return false;
      const text=[m.id,m.title,m.title_ru,m.summary,m.summary_ru].join(' ').toLowerCase();
      return words.every(word=>text.includes(word));
    });
  }

  function phaseStripMarkup(view,selected,lang,t){
    const all=`<button type="button" class="jr-phase${selected==='all'?' selected':''}" data-phase="all" aria-pressed="${selected==='all'}">`+
      `<b>${esc(t('jrAllPhases'))}</b><small>${esc(view.milestones.length)}</small></button>`;
    return all+view.phases.map(p=>{
      const progress=phaseProgress(view,p);
      const icon=`/assets/roadmap/icons/${encodeURIComponent(p.icon)}${p.status==='planned'?'-dim':''}.svg`;
      return `<button type="button" class="jr-phase${p.id===selected?' selected':''}${p.id===view.current_phase?' current':''}" data-phase="${esc(p.id)}" aria-pressed="${p.id===selected}" title="${esc(pick(p,'summary',lang))}">`+
        `<img class="jr-phase-icon" src="${esc(icon)}" width="32" height="32" alt=""><b>${esc(p.id)}</b><span>${esc(pick(p,'name',lang))}</span>`+
        `<small><span class="marker ${esc(p.status)}" aria-hidden="true"></span>${esc(t('status_'+p.status))} · ${esc(t('jrMilestones',progress))}</small></button>`;
    }).join('');
  }

  function milestoneListMarkup(view,items,selected,lang,t){
    if(!items.length)return `<li class="jr-empty">${esc(t('jrNoResults'))}</li>`;
    return items.map(m=>`<li><button type="button" class="jr-card${m.id===selected?' selected':''}" data-milestone="${esc(m.id)}" aria-current="${m.id===selected}">`+
      `<span class="marker ${esc(m.status)}" aria-hidden="true"></span><span class="jr-card-id">${esc(m.id)}</span>`+
      `<span class="jr-card-title">${esc(pick(m,'title',lang))}</span>`+
      `<span class="jr-card-meta">${esc(t('status_'+m.status))}${m.track!=='studio'?' · '+esc(t('track_'+m.track)):''}`+
      `${m.id===view.active_milestone?' · <b>'+esc(t('jrActive'))+'</b>':''}</span></button></li>`).join('');
  }

  function milestoneDetailMarkup(view,id,lang,t){
    const m=byId(view).get(id);
    if(!m)return `<p class="journey-note">${esc(t('jrPick'))}</p>`;
    const refs=ids=>ids.length?ids.map(dep=>{
      const target=byId(view).get(dep);
      return `<button type="button" class="jr-ref" data-milestone="${esc(dep)}"><span class="marker ${esc(target?.status||'planned')}" aria-hidden="true"></span>${esc(dep)}</button>`;
    }).join(' '):`<span class="journey-note">${esc(t('jrNone'))}</span>`;
    const reqs=m.requirements.length?'<ul class="jr-reqs">'+m.requirements.map(r=>
      `<li class="req-${esc(r.state)}"><code>${esc(r.id)}</code> — ${esc(t('req_'+r.state))}</li>`).join('')+'</ul>'
      :`<p class="journey-note">${esc(t('jrNone'))}</p>`;
    const evidence=m.evidence.length?'<ul class="jr-evidence">'+m.evidence.map(e=>
      `<li><span class="tiny-badge">${esc(e.level)}</span> ${link(e.url,e.ref)}</li>`).join('')+'</ul>'
      :`<p class="journey-note">${esc(t('jrNoEvidence'))}</p>`;
    const phase=view.phases.find(p=>p.id===m.phase);
    const note=m.blocker?`<p class="notice warn"><b>${esc(t('jrBlocker'))}:</b> ${esc(m.blocker)}</p>`
      :m.missing?`<p class="notice"><b>${esc(t('jrMissing'))}:</b> ${esc(m.missing)}</p>`:'';
    return `<header class="jr-detail-head"><span class="marker ${esc(m.status)}" aria-hidden="true"></span>`+
      `<div><h3 id="milestoneHeading">${esc(m.id)} · ${esc(pick(m,'title',lang))}</h3>`+
      `<small>${esc(t('status_'+m.status))} · ${esc(t('jrPhase'))} ${esc(m.phase)}${phase?' '+esc(pick(phase,'name',lang)):''}`+
      ` · ${esc(t('track_'+m.track))}${m.id===view.active_milestone?' · <b>'+esc(t('jrActive'))+'</b>':''}</small></div></header>`+
      `<p>${esc(pick(m,'summary',lang))}</p>${note}`+
      `<h4>${esc(t('jrDeliverable'))}</h4><p>${esc(pick(m,'deliverable',lang))}</p>`+
      `<h4>${esc(t('jrAcceptance'))}</h4><ul class="jr-acceptance">${m.acceptance.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>`+
      `<h4>${esc(t('jrDependsOn'))}</h4><p class="jr-refs" data-kind="depends">${refs(m.depends_on)}</p>`+
      `<h4>${esc(t('jrDependents'))}</h4><p class="jr-refs" data-kind="dependents">${refs(m.dependents)}</p>`+
      `<h4>${esc(t('jrRequirements'))}</h4>${reqs}`+
      `<h4>${esc(t('jrTarget'))}</h4><p><span class="tiny-badge">${esc(m.validation_target)}</span></p>`+
      `<h4>${esc(t('jrEvidence'))}</h4>${evidence}`+
      `<p class="jr-links">${link(m.design,t('jrDesign'))}${m.issue?' · '+link(m.issue,t('jrIssue')):''}</p>`;
  }

  function buildMarkup(view,lang,t){
    const build=view.build;
    const groups=GROUPS.map(([key,label,icon,cls])=>{
      const items=build.groups[key]||[];
      if(!items.length)return '';
      const facts=c=>[c.backend&&'.'+c.backend,c.api,c.stability&&t('stability_'+c.stability.replace('-','_'))].filter(Boolean)
        .map(fact=>`<span class="tiny-badge">${esc(fact)}</span>`).join(' ');
      const warning=c=>c.backend==='hnmod'?`<small class="cap-missing"> ${esc(t('nativeTrustWarning'))}</small>`:'';
      return `<h3>${esc(t(label))}</h3><ul class="capability-list">`+items.map(c=>`<li class="${cls}"><span class="ico ${icon}" aria-hidden="true"></span>`+
        `<span><b>${esc(c.capability)}</b> ${facts(c)}${c.note?`<small> — ${esc(pick(c,'note',lang))}</small>`:''}${warning(c)}</span></li>`).join('')+'</ul>';
    }).join('');
    return `<p class="journey-note">${esc(t('journeyBuildNote',{label:pick(build,'label',lang),api:build.content_api}))}</p>`+
      `<p class="journey-note">${esc(t('jrBuildVersion',{version:build.studio_version}))}</p>${groups}`;
  }

  function showcaseMarkup(view,lang,t){
    return view.showcases.map(s=>`<article class="jr-showcase"><h3>${esc(s.id)} · ${esc(pick(s,'name',lang))}</h3>`+
      `<p>${esc(pick(s,'summary',lang))}</p><h4>${esc(t('jrLevels'))}</h4><ol class="ladder jr-levels">`+
      s.levels.map(l=>`<li><span class="marker ${esc(l.status)}" aria-hidden="true"></span><div><b>${esc(l.level)}. ${esc(pick(l,'name',lang))}</b>`+
        `<small>${esc(t('status_'+l.status))}</small></div></li>`).join('')+'</ol>'+
      `<h4>${esc(t('jrSequence'))}</h4><ol class="jr-sequence">${(lang==='ru'?s.sequence_ru:s.sequence).map(step=>`<li>${esc(step)}</li>`).join('')}</ol>`+
      `<h4>${esc(t('jrShowcaseMilestones'))}</h4><p class="jr-refs">${s.milestones.map(id=>`<button type="button" class="jr-ref" data-milestone="${esc(id)}">${esc(id)}</button>`).join(' ')}</p></article>`).join('');
  }

  /** The whole explorer; tab and filter state survive re-renders (language changes). */
  function mount(container,view,{t,lang=()=>'en'}){
    const state={tab:'roadmap',phase:view.current_phase,query:'',statuses:new Set(STATUSES),track:'all',selected:view.active_milestone};
    container.innerHTML=
      `<div class="jr-tabs" role="tablist" aria-label="${esc(t('journeyTitle'))}">`+
      ['roadmap','build','showcase'].map(tab=>`<button type="button" role="tab" id="jrTab-${tab}" data-tab="${tab}" aria-controls="jrPanel-${tab}"></button>`).join('')+
      `</div><section class="jr-panel" role="tabpanel" id="jrPanel-roadmap" aria-labelledby="jrTab-roadmap">`+
      `<p class="journey-note" id="jrNote"></p>`+
      `<details class="jr-map"><summary id="jrMapLabel"></summary><img class="journey-map" src="/assets/roadmap/roadmap-overview.svg" alt=""></details>`+
      `<div class="jr-layout"><div class="jr-phases" role="toolbar" aria-orientation="vertical" id="jrPhases"></div>`+
      `<div class="jr-middle"><div class="jr-tools"><input type="search" id="roadmapSearch"><select id="roadmapTrack"></select></div>`+
      `<div class="jr-status-filters" id="jrStatuses"></div><ul class="jr-list" id="milestoneList"></ul></div>`+
      `<article class="jr-detail" id="milestoneDetail" aria-live="polite" tabindex="-1"></article></div></section>`+
      `<section class="jr-panel" role="tabpanel" id="jrPanel-build" aria-labelledby="jrTab-build" hidden><div id="journeyBuild"></div></section>`+
      `<section class="jr-panel" role="tabpanel" id="jrPanel-showcase" aria-labelledby="jrTab-showcase" hidden></section>`;
    const $=selector=>container.querySelector(selector);
    const tabs=[...container.querySelectorAll('[role=tab]')];

    function renderList(){
      const items=filterMilestones(view,state);
      $('#milestoneList').innerHTML=milestoneListMarkup(view,items,state.selected,lang(),t);
    }
    function renderDetail(){$('#milestoneDetail').innerHTML=milestoneDetailMarkup(view,state.selected,lang(),t);}
    function render(){
      const l=lang();
      for(const tab of tabs){
        tab.textContent=t({roadmap:'jrRoadmap',build:'journeyBuild',showcase:'jrShowcase'}[tab.dataset.tab]);
        const on=tab.dataset.tab===state.tab;
        tab.setAttribute('aria-selected',String(on));tab.tabIndex=on?0:-1;
        $('#jrPanel-'+tab.dataset.tab).hidden=!on;
      }
      $('#jrNote').textContent=t('journeyPlanNote')+' '+t('jrAsOf',{date:view.updated});
      $('.journey-map').alt=t('journeyMapAlt');
      $('#jrMapLabel').textContent=t('jrMap');
      $('#jrPhases').setAttribute('aria-label',t('jrPhase'));
      $('#jrPhases').innerHTML=phaseStripMarkup(view,state.phase,l,t);
      const search=$('#roadmapSearch');search.placeholder=t('jrSearch');search.setAttribute('aria-label',t('jrSearch'));
      $('#jrStatuses').setAttribute('aria-label',t('jrStatusFilter'));
      $('#jrStatuses').innerHTML=STATUSES.map(s=>`<button type="button" class="filter-btn${state.statuses.has(s)?' active':''}" data-status="${s}" aria-pressed="${state.statuses.has(s)}"><span class="marker ${s}" aria-hidden="true"></span>${esc(t('status_'+s))}</button>`).join('');
      const track=$('#roadmapTrack');track.setAttribute('aria-label',t('jrTrack'));
      track.innerHTML=[['all','jrTrackAll'],...view.tracks.map(tr=>[tr.id,'track_'+tr.id])].map(([value,key])=>`<option value="${value}"${value===state.track?' selected':''}>${esc(t(key))}</option>`).join('');
      renderList();renderDetail();
      $('#journeyBuild').innerHTML=buildMarkup(view,l,t);
      $('#jrPanel-showcase').innerHTML=showcaseMarkup(view,l,t);
    }
    function selectTab(tab,focus){
      state.tab=tab;render();
      if(focus)container.querySelector(`[data-tab="${tab}"]`).focus();
    }
    function select(id,{reveal=false,focusDetail=false}={}){
      const item=byId(view).get(id);if(!item)return;
      state.selected=id;
      if(reveal&&!filterMilestones(view,state).some(m=>m.id===id)){state.phase='all';state.query='';state.statuses=new Set(STATUSES);state.track='all';$('#roadmapSearch').value='';}
      if(state.tab!=='roadmap')state.tab='roadmap';
      render();
      const card=container.querySelector(`.jr-card[data-milestone="${CSS.escape(id)}"]`);
      card?.scrollIntoView?.({block:'nearest'});
      if(focusDetail)$('#milestoneDetail').focus();else card?.focus();
    }
    container.addEventListener('click',event=>{
      const target=event.target.closest('button');if(!target||!container.contains(target))return;
      if(target.dataset.tab)return selectTab(target.dataset.tab,false);
      if(target.dataset.phase){state.phase=target.dataset.phase;render();return container.querySelector(`.jr-phase[data-phase="${state.phase}"]`).focus();}
      if(target.dataset.status){const s=target.dataset.status;state.statuses.has(s)?state.statuses.delete(s):state.statuses.add(s);render();return container.querySelector(`[data-status="${s}"]`).focus();}
      if(target.dataset.milestone)return select(target.dataset.milestone,{reveal:true,focusDetail:target.classList.contains('jr-card')});
    });
    container.addEventListener('keydown',event=>{
      const target=event.target;
      if(target.getAttribute?.('role')==='tab'){
        const index=tabs.indexOf(target);
        const next={ArrowRight:index+1,ArrowLeft:index-1,Home:0,End:tabs.length-1}[event.key];
        if(next!==undefined){event.preventDefault();selectTab(tabs[(next+tabs.length)%tabs.length].dataset.tab,true);}
        return;
      }
      const group=target.classList?.contains('jr-phase')?[...container.querySelectorAll('.jr-phase')]
        :target.classList?.contains('jr-card')?[...container.querySelectorAll('.jr-card')]:null;
      if(!group)return;
      const index=group.indexOf(target);
      const keys=target.classList.contains('jr-phase')?{ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}:{ArrowDown:1,ArrowUp:-1};
      if(event.key in keys){event.preventDefault();group[(index+keys[event.key]+group.length)%group.length].focus();}
      else if(event.key==='Home'){event.preventDefault();group[0].focus();}
      else if(event.key==='End'){event.preventDefault();group[group.length-1].focus();}
    });
    container.addEventListener('input',event=>{if(event.target.id==='roadmapSearch'){state.query=event.target.value;state.phase='all';$('#jrPhases').innerHTML=phaseStripMarkup(view,state.phase,lang(),t);renderList();}});
    container.addEventListener('change',event=>{if(event.target.id==='roadmapTrack'){state.track=event.target.value;renderList();}});
    render();
    return {render,select,selectTab,state};
  }

  return {STATUSES,esc,filterMilestones,phaseProgress,phaseStripMarkup,milestoneListMarkup,milestoneDetailMarkup,buildMarkup,showcaseMarkup,mount};
});
