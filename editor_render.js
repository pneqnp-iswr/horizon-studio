/* HTML for entry and recipe cards. Pure functions of their inputs; every user-controlled
 * value is escaped. Browser and Node-compatible. */
(function(root,factory){
  const api=factory(root&&root.HorizonStudioModel||(typeof require==='function'?require('./editor_model.js'):null));
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonStudioRender=api;
})(typeof window!=='undefined'?window:null,function(model){
  'use strict';
  const ESCAPES={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  const escapeHtml=s=>String(s).replace(/[&<>"']/g,x=>ESCAPES[x]);
  const PNG='data:image/png;base64,';
  const SPRITES=['diamond','emerald','amethyst','gold','iron','copper','prismarine','redstone','coal','glowstone','stick','furnace','crafting','block'];

  /** CSS sprite class for a vanilla name or '@local' reference. */
  function spriteKey(ref,entries){
    let key=ref||'';
    if(key.startsWith('@')){const obj=entries.find(e=>e.id===key.slice(1));key=obj?.template||obj?.id||key.slice(1);}
    key=String(key).toLowerCase();
    return SPRITES.find(name=>key.includes(name))||'generic';
  }

  /** ctx: {entries, packTextures, t} */
  function slotMarkup(ref,ctx){
    if(!ref)return '<div class="recipe-slot empty"></div>';
    const pack=ctx.packTextures?.[ref];
    if(pack)return `<div class="recipe-slot custom"><img src="${escapeHtml(pack)}" alt="${escapeHtml(ref)}"></div>`;
    if(ref.startsWith('@')){
      const obj=ctx.entries.find(e=>e.id===ref.slice(1));
      if(obj?.texture?.startsWith(PNG))return `<div class="recipe-slot custom"><img src="${escapeHtml(obj.texture)}" alt="${escapeHtml(obj.name||ref)}"></div>`;
    }
    const title=model.displayName(ref,ctx.entries)||ref;
    return `<div class="recipe-slot"><span class="sprite ${spriteKey(ref,ctx.entries)}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></span></div>`;
  }

  function recipeCardMarkup(e,i,ctx){
    const t=ctx.t;
    const grid=(e.grid||Array(9).fill('')).map(ref=>slotMarkup(ref,ctx)).join('');
    const count=e.count>1?`<span class="count-badge">${escapeHtml(e.count)}</span>`:'';
    return `<article class="recipe-card"><div class="recipe-visual"><div class="recipe-grid-card">${grid}</div><div class="recipe-arrow">→</div><div class="recipe-output">${slotMarkup(e.result,ctx)}${count}</div></div><div class="recipe-card-footer"><div class="recipe-text"><b>${escapeHtml(model.displayName(e.result,ctx.entries))}</b><small>${escapeHtml(t('craftingTable'))} · ${escapeHtml(e.type)}</small></div><button class="config-button" data-edit="${i}">${escapeHtml(t('configure'))}</button><button class="danger ghost" data-remove="${i}" aria-label="${escapeHtml(t('remove'))}">✕</button></div></article>`;
  }

  function entryCardMarkup(e,i,tab,ctx){
    const t=ctx.t;
    const visual=e.texture?.startsWith(PNG)
      ?`<img src="${escapeHtml(e.texture)}" class="preview-image large" alt="${escapeHtml(t('textureAlt'))}">`
      :`<span class="preview-image large symbol"><span class="sprite ${spriteKey(e.template||e.id,ctx.entries)}"></span></span>`;
    const details=tab==='block'
      ?`${escapeHtml(e.template)} · ${escapeHtml(t('light'))}: ${escapeHtml(e.light??0)}`
      :`${escapeHtml(e.template)} · ${escapeHtml(t('rarity'))}: ${escapeHtml(e.rarity||'common')}`;
    return `<article class="entry-card"><div class="entry-visual">${visual}</div><div class="entry-copy"><b>${escapeHtml(e.name)}</b><small>${escapeHtml(e.id)}</small><small>${details}</small></div><div class="entry-actions"><button data-edit="${i}">${escapeHtml(t('configure'))}</button><button class="danger ghost" data-remove="${i}">${escapeHtml(t('remove'))}</button></div></article>`;
  }

  return {escapeHtml,spriteKey,slotMarkup,recipeCardMarkup,entryCardMarkup};
});
