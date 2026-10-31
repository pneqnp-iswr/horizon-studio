/* Horizon IDE starter gallery. Only local, schema-validated examples; no external code.
 * This is a first functional IDE slice, not an embedded/playing game viewport. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonIdeStarters=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const ID=/^[a-z][a-z0-9_-]{0,63}$/;
  const SCHEMA='horizon-studio.ide-templates/1';

  function validCatalog(value){
    return !!(value&&value.schema===SCHEMA&&Array.isArray(value.templates)
      &&value.templates.length>0&&value.templates.length<=32
      &&value.templates.every(item=>item&&typeof item.id==='string'&&ID.test(item.id)
        &&typeof item.name==='string'&&typeof item.name_ru==='string'
        &&typeof item.description==='string'&&typeof item.description_ru==='string'
        &&typeof item.sha256==='string'&&/^[a-f0-9]{64}$/.test(item.sha256)
        &&item.verification==='project-schema-only'&&item.in_game_verified===false));
  }
  function summary(item,lang){
    const kindsRu={block:'Блоки',item:'Предметы',recipe:'Рецепты',structure:'Структуры',vfx:'Эффекты'};
    const kinds=Object.entries(item.counts||{}).filter(([name,num])=>typeof name==='string'&&Number.isInteger(num)&&num>0)
      .map(([name,num])=>(lang==='ru'?(kindsRu[name]||name):name)+' × '+num).join(' · ');
    const desc=lang==='ru'?item.description_ru:item.description;
    return desc+'\n'+kinds+'\n'+(lang==='ru'?'Проверено как проект; в игре не испытано.':'Project schema validated; not tested in the game.');
  }
  function mount(ctx){
    const select=document.getElementById('ideTemplate');
    const create=document.getElementById('ideUseStarter');
    const description=document.getElementById('ideStarterDescription');
    if(!select||!create||!description)throw Error('IDE starter UI is missing');
    const language=()=>ctx.language()==='ru'?'ru':'en';
    let catalog=[],busy=false;
    const selected=()=>catalog.find(x=>x.id===select.value);
    function show(){
      const item=selected();
      description.textContent=item?summary(item,language()):ctx.t('ideStarterNotReady');
    }
    function render(){
      const current=select.value;
      select.replaceChildren();
      for(const item of catalog){
        const option=document.createElement('option');
        option.value=item.id;
        option.textContent=language()==='ru'?item.name_ru:item.name;
        select.appendChild(option);
      }
      if(catalog.some(x=>x.id===current))select.value=current;
      select.disabled=create.disabled=busy||!catalog.length;
      show();
    }
    async function request(url){
      const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Request failed ('+response.status+')');
      return data;
    }
    async function refresh(){
      busy=true;render();
      try{
        const data=await request('/api/ide/templates');
        if(!validCatalog(data))throw Error('Unsupported starter template catalog');
        catalog=data.templates;render();
      }catch(err){
        catalog=[];render();description.textContent=ctx.t('ideStarterError')+': '+err.message;
      }finally{busy=false;render();}
    }
    async function createProject(){
      const item=selected();
      if(!item||busy)return;
      if(!window.confirm(ctx.t('ideStarterConfirm')))return;
      busy=true;render();
      try{
        const data=await request('/api/ide/template/'+encodeURIComponent(item.id));
        if(data.schema!==SCHEMA||data.template_id!==item.id||data.sha256!==item.sha256
          ||data.verification!=='project-schema-only'||data.in_game_verified!==false
          ||!data.state||typeof data.state!=='object')
          throw Error('Starter project changed; refresh the catalog');
        ctx.apply(data.state);
        ctx.status(ctx.t('ideStarterLoaded'));
      }catch(err){
        ctx.status(ctx.t('ideStarterError')+': '+err.message,true);
      }finally{busy=false;render();}
    }
    select.addEventListener('change',show);
    create.addEventListener('click',createProject);
    for(const lang of ['en','ru']){
      document.getElementById('lang-'+lang)?.addEventListener('click',()=>queueMicrotask(render));
    }
    refresh();
    return {refresh,render};
  }
  return {SCHEMA,validCatalog,summary,mount};
});
