/* Source Workbench: real JSON -> validated .hmod overlays -> WebGL model preview.
   Vanilla textures are loaded only from a user-selected local ZIP/JAR. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let viewer, files={}, selected='', packTextures={}, busy=false;
  window.HorizonPackTextures = packTextures;
  const en={
    title:'SOURCE WORKBENCH',description:'Edit the actual generated JSON. Validated changes are included in your .hmod and source ZIP.',
    source:'Source', preview:'3D Preview', asset:'Import your resource pack (.zip / .jar)',
    open:'Source & 3D',close:'Close',apply:'Validate & Apply',reload:'Reload generated files',
    choose:'Select a file to edit',idle:'Changes stay in the editor until you apply them.',
    pending:'Unsaved changes',saved:'Saved and validated — included in future exports.',
    invalid:'Invalid JSON',fallback:'Model has no cuboid elements — showing a reference cube, not a faithful geometry preview.',
    native:'Rust native mods use .hnmod and horizon-mixins. JSON content cannot be compiled to native Rust. See the official template.',
    drag:'Drag to orbit · Scroll to zoom · GPU WebGL', packReady:'Resource pack loaded locally: {count} PNG textures.', loaded:'{count} generated source files · JSON edits export to .hmod',
    packError:'Could not load resource pack: ',
  };
  const ru={
    title:'РЕДАКТОР ИСХОДНИКОВ',description:'Изменяйте настоящий JSON. После проверки правки войдут в .hmod и исходный ZIP.',
    source:'Исходный код',preview:'3D-просмотр',asset:'Импортировать свой ресурспак (.zip / .jar)',
    open:'Исходники и 3D',close:'Закрыть',apply:'Проверить и применить',reload:'Обновить файлы',
    choose:'Выберите файл',idle:'Правки не применятся до нажатия кнопки.',
    pending:'Есть несохранённые изменения',saved:'Проверено и сохранено — правки войдут в экспорт.',
    invalid:'Неправильный JSON',fallback:'Модель без cuboid elements — показан условный куб, не точная геометрия.',
    native:'Нативные Rust-моды используют .hnmod и horizon-mixins. Контентный JSON не компилируется напрямую в Rust. См. официальный шаблон.',
    drag:'Зажмите и вращайте · Колёсико для масштаба · WebGL',packReady:'Ресурспак обработан локально: {count} PNG.',loaded:'Сгенерировано файлов: {count} · правки JSON попадают в .hmod',
    packError:'Не удалось прочитать ресурспак: ',
  };
  const labels=()=>window.HorizonI18n?.language==='ru'?ru:en;
  const text=(key)=>labels()[key]||en[key]||key;
  const stat=(message,error=false)=>{const s=$('sourceStatus');s.textContent=message;s.classList.toggle('error',error);};
  const entryName=path=>path.split('/').slice(-1)[0];
  // assets/<mod>/models/block/x.json -> models/block/x.json: unique, unlike the bare file name.
  const shortPath=path=>path.split('/').slice(2).join('/')||path;
  function updateLabels(){document.querySelectorAll('[data-source-i18n]').forEach(n=>{n.textContent=text(n.dataset.sourceI18n);});const open=$('openWorkbench');if(open)open.textContent=text('open');}
  function renderFileList(){
    const search=($('sourceFileSearch').value||'').trim().toLowerCase();
    const list=$('sourceFiles');list.innerHTML='';
    for(const path of Object.keys(files).sort()){
      if(!path.endsWith('.json')||!path.toLowerCase().includes(search))continue;
      const button=document.createElement('button');button.type='button';button.className='source-file'+(path===selected?' active':'');
      button.textContent=(state.source_overrides?.[path]?'● ':'')+shortPath(path);
      button.title=path;button.onclick=()=>selectFile(path);list.appendChild(button);
    }
  }
  function modelTexture(path, model){
    const parts=path.split('/');const kind=parts.includes('block')?'block':'item';const id=entryName(path).replace(/\.json$/,'');
    const obj=(kind==='block'?state.blocks:state.items).find(e=>e.id===id);
    return obj?.texture||packTextures[obj?.template]||null;
  }
  function showModel(){
    if(!viewer||!selected)return;
    try {
      const model=JSON.parse($('sourceCode').value);
      if(!model||typeof model!=='object'||Array.isArray(model))throw Error('Expected JSON object');
      viewer.setModel(model);viewer.setTexture(modelTexture(selected,model));
      const proxy= !Array.isArray(model.elements)||!model.elements.length;
      $('modelGeometryNotice').textContent=proxy?text('fallback'):`${model.elements.length} cuboid elements · ${viewer.mesh.triangles/3} triangles`;
      $('modelGeometryNotice').classList.toggle('muted',proxy);
    }catch(e){stat(`${text('invalid')}: ${e.message}`,true);}
  }
  function selectFile(path){
    selected=path;$('sourcePath').textContent=path;
    $('sourceCode').value=state.source_overrides?.[path]??files[path];
    stat(text('idle'));renderFileList();showModel();
  }
  async function reloadFiles(){
    if(busy)return;busy=true;try{
      const response=await window.HorizonStudioPost('/api/source',JSON.stringify(payload()));
      const result=await response.json();if(!response.ok)throw Error(result.error||'Source API failed');
      files=result.files;if(selected&&!files[selected])selected='';
      if(!selected){selected=Object.keys(files).find(p=>p.includes('/models/block/'))||Object.keys(files).find(p=>p.includes('/models/item/'))||Object.keys(files).find(p=>p.endsWith('.json'))||'';}
      renderFileList();if(selected)selectFile(selected);
      stat(text('loaded').replace('{count}',result.count));
    }catch(e){stat(e.message,true);}finally{busy=false;}
  }
  async function applyCode(){
    if(!selected)return;
    const contents=$('sourceCode').value;
    try {const value=JSON.parse(contents);if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Source must be a JSON object');}
    catch(e){stat(`${text('invalid')}: ${e.message}`,true);return;}
    const prev=state.source_overrides||{};
    state.source_overrides={...prev,[selected]:contents};
    try {
      const response=await window.HorizonStudioPost('/api/preview',JSON.stringify(payload()));
      const result=await response.json();if(!response.ok)throw Error(result.error||'Invalid content');
      files[selected]=contents;persist();showModel();renderFileList();stat(text('saved'));
    }catch(e){state.source_overrides=prev;stat(e.message,true);}
  }
  async function loadPack(){
    const file=$('resourcePackInput').files?.[0];if(!file)return;
    try{
      const response=await window.HorizonStudioPost('/api/resourcepack',file,'application/octet-stream');
      const result=await response.json();if(!response.ok)throw Error(result.error||'Invalid pack');
      packTextures=result.textures||{};window.HorizonPackTextures=packTextures;
      render();showModel();stat(text('packReady').replace('{count}',result.count));
    }catch(e){stat(text('packError')+e.message,true);}finally{$('resourcePackInput').value='';}
  }
  function open(){
    $('sourceWorkbench').hidden=false;
    if(!viewer){try{viewer=new window.HorizonModelViewer.Viewer($('modelViewport'));$('viewerHint').textContent=viewer.gl?'WebGL 3D · drag to orbit / wheel to zoom':'Software 3D · drag to orbit / wheel to zoom';}catch(e){stat('3D viewport: '+e.message,true);}}
    updateLabels();reloadFiles();requestAnimationFrame(()=>viewer?.render());
  }
  function close(){$('sourceWorkbench').hidden=true;}
  $('openWorkbench').onclick=open;$('closeWorkbench').onclick=close;
  $('refreshSources').onclick=reloadFiles;$('applySource').onclick=applyCode;
  $('resourcePackInput').onchange=loadPack;
  $('sourceFileSearch').oninput=renderFileList;
  $('sourceCode').oninput=()=>{stat(text('pending'));showModel();};
  document.addEventListener('studio:state-changed',()=>{if(!$('sourceWorkbench').hidden)reloadFiles();});
  window.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('sourceWorkbench').hidden)close();if((e.ctrlKey||e.metaKey)&&e.key==='s'&&!$('sourceWorkbench').hidden){e.preventDefault();applyCode();}});
  updateLabels();
  const oldRefresh=window.HorizonStudioRefreshLanguage;
  window.HorizonStudioRefreshLanguage=function(){oldRefresh?.();updateLabels();};
})();
