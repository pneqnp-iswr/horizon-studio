/* HS-025: the VFX Studio panel. Effects live in the editor state (`state.effects`), so saving,
 * autosave, undo/redo and reopening go through the same canonical project as every other asset.
 * The preview is a Studio preview and says so; it never claims in-game rendering. */
(function(root){
  'use strict';
  const $=id=>document.getElementById(id);
  const clone=value=>JSON.parse(JSON.stringify(value));
  const FIELDS=[
    // [input id, path in the effect, kind]
    ['vfxName',['name'],'text'],['vfxSeed',['seed'],'int'],['vfxDuration',['duration'],'num'],['vfxLoop',['loop'],'bool'],
    ['vfxSparkCount',['emitters',0,'bursts',0,'count'],'int'],['vfxSpeedMin',['emitters',0,'speed',0],'num'],
    ['vfxSpeedMax',['emitters',0,'speed',1],'num'],['vfxLifeMin',['emitters',0,'lifetime',0],'num'],
    ['vfxLifeMax',['emitters',0,'lifetime',1],'num'],['vfxSpread',['emitters',0,'direction','spread'],'num'],
    ['vfxGravity',['emitters',0,'gravity'],'num'],['vfxDrag',['emitters',0,'drag'],'num'],
    ['vfxStretch',['emitters',0,'stretch'],'num'],['vfxColorStart',['emitters',0,'color',0,1],'color'],
    ['vfxColorMid',['emitters',0,'color',1,1],'color'],['vfxColorEnd',['emitters',0,'color',-1,1],'color'],
  ];
  const get=(obj,path)=>path.reduce((o,k)=>o==null?o:o[k===-1?o.length-1:k],obj);
  function set(obj,path,value){
    const parent=get(obj,path.slice(0,-1));const key=path[path.length-1];
    if(parent==null)return false;parent[key===-1?parent.length-1:key]=value;return true;
  }

  function mount(ctx){
    const Vfx=root.HorizonVfx;
    const ui={selected:null,time:0,playing:false,last:0,frame:0,caps:null,spawned:null,spawnedFor:''};
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
      $('vfxEffects').innerHTML=items.length?items.map(e=>`<li><button type="button" data-vfx="${e.uid}" aria-pressed="${e.uid===ui.selected}"${e.uid===ui.selected?' class="selected"':''}>`+
        `<b>${esc(e.name)}</b><small>${esc(e.id)}</small></button></li>`).join(''):`<li class="empty-hint">${esc(ctx.t('vfxEmpty'))}</li>`;
      for(const b of $('vfxEffects').querySelectorAll('[data-vfx]'))b.onclick=()=>{select(b.dataset.vfx);};
      $('vfxDelete').disabled=!current();
      $('vfxInspector').hidden=!current();
    }
    const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function inspector(){
      const e=current();if(!e)return;
      $('vfxId').value=e.id;
      for(const [id,path,kind] of FIELDS){
        const input=$(id),value=get(e,path);
        if(kind==='bool')input.checked=Boolean(value);else input.value=value??'';
        input.removeAttribute('aria-invalid');
      }
      $('vfxTime').max=String(e.duration);
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
      $('vfxDiagnostics').innerHTML=rows.map(r=>`<li class="vfx-${r.level}" data-code="${esc(r.code)}">${esc(r.text)}</li>`).join('');
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
      ui.selected=uid;ui.time=0;pause();list();inspector();frame();diagnostics();
    }

    function render(){
      if(!effects().some(e=>e.uid===ui.selected))ui.selected=effects()[0]?.uid||null;
      list();inspector();frame();diagnostics();transport();
    }

    function commitField(input,path,kind){
      const e=current();if(!e)return;
      let value;
      if(kind==='bool')value=input.checked;
      else if(kind==='text'||kind==='color')value=input.value;
      else value=input.value.trim()===''?NaN:Number(input.value);
      if(kind==='int'&&Number.isFinite(value)&&!Number.isInteger(value))value=NaN;
      const next=clone(e);
      if(!set(next,path,value))return;
      const problems=Vfx.validate(model(next));
      if(problems.length){
        input.setAttribute('aria-invalid','true');
        diagnostics(problems);
        ctx.status(ctx.t('vfxInvalid'),true);
        return;
      }
      input.removeAttribute('aria-invalid');
      ctx.commit(effects().map(x=>x.uid===e.uid?next:x));
      ctx.status(ctx.t('vfxSaved'));
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

    for(const [id,path,kind] of FIELDS)$(id).addEventListener('change',()=>commitField($(id),path,kind));
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
    return {open,close,render,select,play,pause,state:()=>({...ui,spawned:undefined})};
  }

  root.HorizonVfxStudio={mount};
})(window);
