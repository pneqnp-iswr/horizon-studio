/* HS-025: the VFX Studio panel. Effects live in the editor state (`state.effects`), so saving,
 * autosave, undo/redo and reopening go through the same canonical project as every other asset.
 * The preview is a Studio preview and says so; it never claims in-game rendering. */
(function(root){
  'use strict';
  const $=id=>document.getElementById(id);
  const clone=value=>JSON.parse(JSON.stringify(value));
  // Effect fields: [input id, path in the effect, kind].
  const FIELDS=[['vfxName',['name'],'text'],['vfxSeed',['seed'],'int'],['vfxDuration',['duration'],'num'],['vfxLoop',['loop'],'bool']];
  // Fields of the selected emitter: [input id, path inside the emitter, kind].
  const EMITTER=[['vfxEmitterId',['id'],'text'],['vfxShape',['shape','type'],'text'],['vfxRadius',['shape','radius'],'num'],
    ['vfxAxisX',['direction','axis',0],'num'],['vfxAxisY',['direction','axis',1],'num'],['vfxAxisZ',['direction','axis',2],'num'],
    ['vfxSpeedMin',['speed',0],'num'],['vfxSpeedMax',['speed',1],'num'],['vfxLifeMin',['lifetime',0],'num'],
    ['vfxLifeMax',['lifetime',1],'num'],['vfxSpread',['direction','spread'],'num'],['vfxGravity',['gravity'],'num'],
    ['vfxDrag',['drag'],'num'],['vfxStretch',['stretch'],'num'],['vfxBlend',['blend'],'text']];
  // Starting points for new emitters (Studio data only; every one is validated like any other).
  const TEMPLATES={
    sparks:()=>clone(root.HorizonVfx.impactSpark().emitters[0]),
    flash:()=>clone(root.HorizonVfx.impactSpark().emitters[1]),
    smoke:()=>({id:'smoke',bursts:[{time:0,count:12}],shape:{type:'sphere',radius:0.2},direction:{axis:[0,1,0],spread:35},
      speed:[0.4,1.2],lifetime:[0.5,1],gravity:-0.8,drag:1.2,stretch:0,blend:'alpha',size:[[0,0.15],[1,0.6]],
      color:[[0,'#9a9aa6'],[1,'#3b3b45']],alpha:[[0,0.6],[1,0]]}),
  };
  // Particle budgets per quality profile; the effect's own limit is the highest.
  const PROFILES=[['low',256],['medium',1024],['high',2048]];
  const get=(obj,path)=>path.reduce((o,k)=>o==null?o:o[k===-1?o.length-1:k],obj);
  function set(obj,path,value){
    const parent=get(obj,path.slice(0,-1));const key=path[path.length-1];
    if(parent==null)return false;parent[key===-1?parent.length-1:key]=value;return true;
  }

  function mount(ctx){
    const Vfx=root.HorizonVfx;
    const ui={selected:null,emitter:0,time:0,playing:false,last:0,frame:0,caps:null,spawned:null,spawnedFor:''};
    const canvas=$('vfxCanvas'),draw=canvas.getContext('2d');
    draw.imageSmoothingEnabled=false;
    // Read when needed: the preference can change while the editor is open.
    const reduced=()=>Boolean(root.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

    const effects=()=>ctx.effects();
    const current=()=>effects().find(e=>e.uid===ui.selected)||null;
    const model=e=>{const {id,uid,...rest}=e;return rest;};

    function uniqueId(base){const used=new Set(effects().map(e=>e.id));let id=base,n=2;while(used.has(id))id=`${base}_${n++}`;return id;}

    function list(){
      const items=effects();
      $('vfxEffects').innerHTML=items.length?items.map(e=>`<li><button type="button" data-vfx="${esc(e.uid)}" aria-pressed="${e.uid===ui.selected}"${e.uid===ui.selected?' class="selected"':''}>`+
        `<b>${esc(e.name)}</b><small>${esc(e.id)}</small></button></li>`).join(''):`<li class="empty-hint">${esc(ctx.t('vfxEmpty'))}</li>`;
      for(const b of $('vfxEffects').querySelectorAll('[data-vfx]'))b.onclick=()=>{select(b.dataset.vfx);};
      $('vfxDelete').disabled=!current();
      $('vfxInspector').hidden=!current();
    }
    const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    const emitterOf=e=>e.emitters[Math.min(ui.emitter,e.emitters.length-1)];
    const particles=e=>e.emitters.reduce((sum,em)=>sum+em.bursts.reduce((n,b)=>n+(Number(b.count)||0),0),0);

    function inspector(){
      const e=current();if(!e)return;
      ui.emitter=Math.max(0,Math.min(ui.emitter,e.emitters.length-1));
      $('vfxId').value=e.id;
      for(const [id,path,kind] of FIELDS){
        const input=$(id),value=get(e,path);
        if(kind==='bool')input.checked=Boolean(value);else input.value=value??'';
        input.removeAttribute('aria-invalid');
      }
      const em=emitterOf(e);
      for(const [id,path] of EMITTER){$(id).value=get(em,path)??'';$(id).removeAttribute('aria-invalid');}
      $('vfxRadius').disabled=em.shape.type!=='sphere';
      $('vfxEmitterList').innerHTML=e.emitters.map((x,i)=>`<li><button type="button" data-emitter="${i}" aria-pressed="${i===ui.emitter}"${i===ui.emitter?' class="selected"':''}>`+
        `<b>${esc(x.id)}</b><small>${esc(ctx.t('vfxEmitterSummary',{count:x.bursts.reduce((n,b)=>n+b.count,0),blend:ctx.t('vfxBlend_'+x.blend)}))}</small></button></li>`).join('');
      for(const b of $('vfxEmitterList').querySelectorAll('[data-emitter]'))b.onclick=()=>{ui.emitter=Number(b.dataset.emitter);inspector();};
      $('vfxEmitterLegend').textContent=ctx.t('vfxEmitterNamed',{id:em.id});
      $('vfxDeleteEmitter').disabled=e.emitters.length<2;$('vfxAddEmitter').disabled=$('vfxDuplicateEmitter').disabled=e.emitters.length>=Vfx.LIMITS.emitters;
      $('vfxEmitterUp').disabled=ui.emitter===0;$('vfxEmitterDown').disabled=ui.emitter===e.emitters.length-1;
      bursts(em);for(const curve of ['size','alpha','color'])keys(curve,em[curve]);
      budget(e);
      $('vfxTime').max=String(e.duration);
      $('vfxMarks').innerHTML=e.emitters.flatMap(x=>x.bursts.map(b=>`<i style="left:${Math.max(0,Math.min(100,b.time/e.duration*100)).toFixed(2)}%"></i>`)).join('');
    }
    // Bursts: when and how many. The first burst's count keeps the id the rest of the editor knows.
    function bursts(em){
      $('vfxBursts').innerHTML=`<div class="vfx-keys-head"><span>${esc(ctx.t('vfxBursts'))}</span><button type="button" data-add="burst"${em.bursts.length>=Vfx.LIMITS.bursts?' disabled':''}>${esc(ctx.t('vfxAddBurst'))}</button></div>`+
        em.bursts.map((b,i)=>`<div class="vfx-key"><label><span>${esc(ctx.t('vfxBurstTime'))}</span><input type="number" min="0" max="10" step="0.01" data-burst="${i}" data-field="time" value="${esc(b.time)}"/></label>`+
          `<label><span>${esc(ctx.t('vfxFieldCount'))}</span><input type="number" min="1" max="512" step="1" data-burst="${i}" data-field="count" value="${esc(b.count)}"${i===0?' id="vfxSparkCount"':''}/></label>`+
          `<button type="button" class="ghost" data-remove-burst="${i}" aria-label="${esc(ctx.t('vfxRemoveRow'))}"${em.bursts.length<2?' disabled':''}>✕</button></div>`).join('');
    }
    // Curves over a particle's life: time from 0 (birth) to 1 (death) and a value; colours as #rrggbb.
    function keys(curve,list){
      const box=document.querySelector(`.vfx-keys[data-curve="${curve}"]`);
      const color=curve==='color';
      const swatch=color?`<span class="vfx-gradient" style="background:linear-gradient(90deg,${list.map(([t,c])=>`${/^#[0-9a-f]{6}$/.test(c)?c:'#000000'} ${(Math.max(0,Math.min(1,t))*100).toFixed(1)}%`).join(',')})"></span>`:'';
      box.innerHTML=`<div class="vfx-keys-head"><span>${esc(ctx.t('vfxCurve_'+curve))}</span>${swatch}<button type="button" data-add="${curve}"${list.length>=Vfx.LIMITS.keys?' disabled':''}>${esc(ctx.t('vfxAddKey'))}</button></div>`+
        list.map(([t,v],i)=>`<div class="vfx-key"><label><span>${esc(ctx.t('vfxKeyTime'))}</span><input type="number" min="0" max="1" step="0.01" data-key="${i}" data-field="0" value="${esc(t)}"/></label>`+
          `<label><span>${esc(ctx.t(color?'vfxKeyColor':'vfxKeyValue'))}</span><input type="${color?'color':'number'}"${color?'':' step="0.01" min="0"'} data-key="${i}" data-field="1" value="${esc(v)}"/></label>`+
          `<button type="button" class="ghost" data-remove-key="${i}" aria-label="${esc(ctx.t('vfxRemoveRow'))}"${list.length<3?' disabled':''}>✕</button></div>`).join('');
    }
    function budget(e){
      const total=particles(e);
      $('vfxBudget').textContent=ctx.t('vfxBudget',{count:total,profiles:PROFILES.map(([name,max])=>`${ctx.t('vfxProfile_'+name)} ${total<=max?'✓':'✗'}`).join(' · ')});
      $('vfxBudget').classList.toggle('over',total>Vfx.LIMITS.particles);
    }

    async function capabilities(){
      if(ui.caps)return ui.caps;
      try{
        const data=await (await fetch('/api/engine-profiles',{cache:'no-store'})).json();
        const revision=ctx.target()?.revision||data.default;
        const profile=data.profiles.find(p=>p.revision===revision);
        ui.caps={known:Boolean(profile),capabilities:profile?.capabilities||{}};
      }catch(_){ui.caps={known:false,capabilities:{}};}
      return ui.caps;
    }

    async function diagnostics(problems){
      const e=current();
      if(!e){$('vfxDiagnostics').innerHTML='';return;}
      const caps=await capabilities();
      const notes=Vfx.engineNotes(model(e),caps.capabilities);
      const rows=[...(problems||[]).map(p=>({level:'error',code:p.code,text:ctx.t('vfxProblem',{path:p.path,message:p.message})})),
        ...notes.map(n=>({...n,text:ctx.t('vfxNote_'+n.code,{api:n.api??'?'})}))];
      $('vfxDiagnostics').innerHTML=rows.map(r=>`<li class="vfx-${esc(r.level)}" data-code="${esc(r.code)}">${esc(r.text)}</li>`).join('');
    }

    function frame(){
      const e=current();
      if(!e){draw.fillStyle='#0d1020';draw.fillRect(0,0,canvas.width,canvas.height);canvas.dataset.particles='0';return;}
      const effect=model(e);
      const key=JSON.stringify(effect);
      if(ui.spawnedFor!==key){ui.spawned=Vfx.spawn(effect);ui.spawnedFor=key;}
      const alive=Vfx.render(draw,effect,ui.time,{spawned:ui.spawned});
      canvas.dataset.time=ui.time.toFixed(3);canvas.dataset.particles=String(alive);
      $('vfxTime').value=String(ui.time);
      $('vfxTimeLabel').textContent=ctx.t('vfxTimeLabel',{time:ui.time.toFixed(2)});
      $('vfxCount').textContent=ctx.t('vfxCount',{count:alive});
    }

    function tick(now){
      if(!ui.playing)return;
      const e=current();if(!e){ui.playing=false;return;}
      const dt=Math.min(0.05,(now-ui.last)/1000);ui.last=now;
      ui.time+=dt;
      if(ui.time>=e.duration){
        if(e.loop)ui.time%=e.duration;else{ui.time=e.duration;ui.playing=false;}
      }
      frame();transport();
      if(ui.playing)ui.frame=requestAnimationFrame(tick);
    }

    function play(from){
      const e=current();if(!e)return;
      if(from!==undefined)ui.time=from;
      if(ui.time>=e.duration&&!e.loop)ui.time=0;
      ui.playing=true;ui.last=performance.now();cancelAnimationFrame(ui.frame);ui.frame=requestAnimationFrame(tick);transport();
    }
    function pause(){ui.playing=false;cancelAnimationFrame(ui.frame);transport();}
    function transport(){
      $('vfxPlay').textContent=ctx.t(ui.playing?'vfxPause':'vfxPlay');
      $('vfxPlay').setAttribute('aria-pressed',String(ui.playing));
    }

    function select(uid){
      ui.selected=uid;ui.emitter=0;ui.time=0;pause();list();inspector();frame();diagnostics();
    }

    function render(){
      if(!effects().some(e=>e.uid===ui.selected))ui.selected=effects()[0]?.uid||null;
      list();inspector();frame();diagnostics();transport();
    }

    /** One change to the selected effect: validated first, then one undoable step. */
    function change(mutate,input){
      const e=current();if(!e)return false;
      const next=clone(e);
      if(mutate(next)===false)return false;
      const problems=Vfx.validate(model(next));
      if(problems.length){
        if(input)input.setAttribute('aria-invalid','true');
        diagnostics(problems);
        ctx.status(ctx.t('vfxInvalid'),true);
        return false;
      }
      if(input)input.removeAttribute('aria-invalid');
      ctx.commit(effects().map(x=>x.uid===e.uid?next:x));
      ctx.status(ctx.t('vfxSaved'));
      return true;
    }
    function read(input,kind){
      if(kind==='bool')return input.checked;
      if(kind==='text'||kind==='color')return input.value;
      const value=input.value.trim()===''?NaN:Number(input.value);
      return kind==='int'&&Number.isFinite(value)&&!Number.isInteger(value)?NaN:value;
    }
    function commitField(input,path,kind){change(next=>set(next,path,read(input,kind)),input);}
    function commitEmitter(input,path,kind){change(next=>set(emitterOf(next),path,read(input,kind)),input);}
    function emitters(edit,select){
      if(change(next=>{const r=edit(next.emitters);if(r===false)return false;})&&select!==undefined){ui.emitter=select;inspector();}
    }
    function freshId(list,base){const used=new Set(list.map(x=>x.id));let id=base,n=2;while(used.has(id))id=`${base}_${n++}`;return id;}
    function addEmitter(){
      const e=current();if(!e)return;
      emitters(list=>{const em=TEMPLATES[$('vfxEmitterTemplate').value]();em.id=freshId(list,em.id);list.push(em);},e.emitters.length);
    }
    function duplicateEmitter(){
      const e=current();if(!e)return;const i=ui.emitter;
      emitters(list=>{const em=clone(list[i]);em.id=freshId(list,em.id);list.splice(i+1,0,em);},i+1);
    }
    function moveEmitter(step){
      const e=current();if(!e)return;const i=ui.emitter,j=i+step;
      if(j<0||j>=e.emitters.length)return;
      emitters(list=>{[list[i],list[j]]=[list[j],list[i]];},j);
    }
    function deleteEmitter(){
      const e=current();if(!e||e.emitters.length<2)return;const i=ui.emitter;
      emitters(list=>{list.splice(i,1);},Math.max(0,i-1));
    }
    function onTable(event){
      const target=event.target,curve=target.closest('.vfx-keys')?.dataset.curve;
      if(event.type==='change'&&target.matches('input[data-burst]')){
        const i=Number(target.dataset.burst),field=target.dataset.field;
        change(next=>{emitterOf(next).bursts[i][field]=read(target,field==='count'?'int':'num');},target);
      }else if(event.type==='change'&&target.matches('input[data-key]')){
        const i=Number(target.dataset.key),field=Number(target.dataset.field);
        change(next=>{emitterOf(next)[curve][i][field]=read(target,curve==='color'&&field===1?'color':'num');},target);
      }else if(event.type==='click'&&target.matches('[data-add]')){
        const what=target.dataset.add;
        change(next=>{
          const em=emitterOf(next);
          if(what==='burst'){const last=em.bursts[em.bursts.length-1];em.bursts.push({time:Math.min(next.duration,+(last.time+0.1).toFixed(2)),count:last.count});return;}
          const list=em[what],last=list[list.length-1],prev=list[list.length-2];
          list.splice(list.length-1,0,[+((prev[0]+last[0])/2).toFixed(3),what==='color'?last[1]:+(((prev[1]+last[1])/2).toFixed(3))]);
        });
      }else if(event.type==='click'&&target.matches('[data-remove-burst]')){
        const i=Number(target.dataset.removeBurst);change(next=>{emitterOf(next).bursts.splice(i,1);});
      }else if(event.type==='click'&&target.matches('[data-remove-key]')){
        const i=Number(target.dataset.removeKey);change(next=>{emitterOf(next)[curve].splice(i,1);});
      }
    }

    function rename(){
      const e=current();if(!e)return;
      const id=$('vfxId').value.trim();
      if(!/^[a-z][a-z0-9_]{0,63}$/.test(id)||effects().some(x=>x.id===id&&x.uid!==e.uid)){
        $('vfxId').setAttribute('aria-invalid','true');ctx.status(ctx.t('vfxBadId'),true);return;
      }
      $('vfxId').removeAttribute('aria-invalid');
      if(id!==e.id)ctx.commit(effects().map(x=>x.uid===e.uid?{...clone(x),id}:x));
    }

    function create(){
      const effect={id:uniqueId('impact_spark'),uid:ctx.newUid(),...Vfx.impactSpark(),name:ctx.t('vfxPresetSpark')};
      ctx.commit([...effects(),effect]);
      select(effect.uid);
      ctx.status(ctx.t('vfxCreated'));
      if(!reduced())play(0);
    }

    function remove(){
      const e=current();if(!e)return;
      ctx.commit(effects().filter(x=>x.uid!==e.uid));
      ui.selected=null;render();
    }

    function open(){
      $('vfxDialog').hidden=false;ui.caps=null;render();
      (current()?$('vfxPlay'):$('vfxNewSpark')).focus();
      if(current()&&!reduced())play(0);
    }
    function close(){pause();$('vfxDialog').hidden=true;$('openVfx').focus();}

    $('vfxInspector').addEventListener('submit',event=>event.preventDefault());  // fields commit on change, never submit
    for(const [id,path,kind] of FIELDS)$(id).addEventListener('change',()=>commitField($(id),path,kind));
    for(const [id,path,kind] of EMITTER)$(id).addEventListener('change',()=>commitEmitter($(id),path,kind));
    for(const box of document.querySelectorAll('#vfxEmitterInspector .vfx-keys')){box.addEventListener('change',onTable);box.addEventListener('click',onTable);}
    $('vfxAddEmitter').onclick=addEmitter;$('vfxDuplicateEmitter').onclick=duplicateEmitter;
    $('vfxEmitterUp').onclick=()=>moveEmitter(-1);$('vfxEmitterDown').onclick=()=>moveEmitter(1);$('vfxDeleteEmitter').onclick=deleteEmitter;
    $('vfxId').addEventListener('change',rename);
    $('vfxNewSpark').onclick=create;
    $('vfxDelete').onclick=remove;
    $('vfxPlay').onclick=()=>ui.playing?pause():play();
    $('vfxRestart').onclick=()=>play(0);
    $('vfxTime').addEventListener('input',()=>{pause();ui.time=Number($('vfxTime').value);frame();});
    $('openVfx').onclick=open;
    $('closeVfx').onclick=close;
    $('vfxDialog').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}});
    document.addEventListener('studio:state-changed',()=>{ui.caps=null;if(!$('vfxDialog').hidden)render();});
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
    const refresh=root.HorizonStudioRefreshLanguage;
    root.HorizonStudioRefreshLanguage=function(){refresh?.();if(!$('vfxDialog').hidden)render();};
    return {open,close,render,select,play,pause,frame,state:()=>({...ui,spawned:undefined})};
  }

  root.HorizonVfxStudio={mount};
})(window);
