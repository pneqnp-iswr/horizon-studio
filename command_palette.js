/* HS-033: the command palette (Ctrl+K). Every command is a control that already exists in the
 * workbench; the palette runs it by clicking that control, so it behaves exactly like the UI and its
 * label is the control's own, already translated, label. Browser and Node-compatible: the ranking is
 * pure and tested in Node; mount() needs a DOM. */
(function(root,factory){
  const api=factory(root);
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonPalette=api;
})(typeof window!=='undefined'?window:null,function(root){
  'use strict';
  const fold=s=>String(s||'').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g,'');

  /** How well `query` matches `text`: 0 for no match; prefix > word start > substring > in-order letters. */
  function score(text,query){
    const t=fold(text),q=fold(query).trim();
    if(!q)return 1;
    if(t.startsWith(q))return 100-Math.min(50,t.length-q.length)/100;
    const word=t.split(/[\s/&().,:-]+/).findIndex(w=>w.startsWith(q));
    if(word>=0)return 80-word;
    const at=t.indexOf(q);
    if(at>=0)return 60-Math.min(40,at);
    let i=0,gaps=0,last=-1;
    for(const ch of q){
      const found=t.indexOf(ch,last+1);
      if(found<0)return 0;
      if(last>=0)gaps+=found-last-1;
      last=found;i++;
    }
    return Math.max(1,30-gaps);
  }

  /** Commands matching `query`, best first; ties keep the declared order. Searches labels and keywords. */
  function rank(commands,query){
    return commands
      .map((command,index)=>({command,index,score:Math.max(score(command.label,query),...(command.keywords||[]).map(k=>score(k,query)*0.9))}))
      .filter(entry=>entry.score>0)
      .sort((a,b)=>b.score-a.score||a.index-b.index)
      .map(entry=>entry.command);
  }

  function mount({commands,t,document:doc=root.document}){
    const $=id=>doc.getElementById(id);
    const dialog=$('paletteDialog'),input=$('paletteInput'),list=$('paletteList'),empty=$('paletteEmpty');
    const state={open:false,items:[],active:0,returnTo:null};
    const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function render(){
      state.items=rank(commands().filter(c=>c.available()),input.value);
      state.active=Math.min(state.active,Math.max(0,state.items.length-1));
      list.innerHTML=state.items.map((c,i)=>`<li id="palette-${esc(c.id)}" role="option" aria-selected="${i===state.active}" data-command="${esc(c.id)}"`+
        `${i===state.active?' class="active"':''}><span>${esc(c.label)}</span><small>${esc(c.group)}${c.shortcut?` · <kbd>${esc(c.shortcut)}</kbd>`:''}</small></li>`).join('');
      empty.hidden=state.items.length>0;
      input.setAttribute('aria-activedescendant',state.items.length?`palette-${state.items[state.active].id}`:'');
      list.querySelector('.active')?.scrollIntoView?.({block:'nearest'});
    }

    function open(){
      if(state.open)return;
      state.open=true;state.returnTo=doc.activeElement;state.active=0;
      input.value='';dialog.hidden=false;input.setAttribute('aria-expanded','true');render();input.focus();
    }
    function close({restore=true}={}){
      if(!state.open)return;
      state.open=false;dialog.hidden=true;input.setAttribute('aria-expanded','false');
      if(restore&&state.returnTo?.isConnected)state.returnTo.focus();
    }
    function run(command){
      if(!command)return;
      const back=state.returnTo;
      close({restore:false});
      command.run();
      // A command that opens a dialog moves focus itself; otherwise keyboard users return where they were.
      setTimeout(()=>{const now=doc.activeElement;if((!now||now===doc.body||now===input)&&back?.isConnected)back.focus();},0);
    }

    input.addEventListener('input',()=>{state.active=0;render();});
    input.addEventListener('keydown',event=>{
      const n=state.items.length;
      if(event.key==='ArrowDown'){event.preventDefault();if(n){state.active=(state.active+1)%n;render();}}
      else if(event.key==='ArrowUp'){event.preventDefault();if(n){state.active=(state.active-1+n)%n;render();}}
      else if(event.key==='Home'&&n){event.preventDefault();state.active=0;render();}
      else if(event.key==='End'&&n){event.preventDefault();state.active=n-1;render();}
      else if(event.key==='Enter'){event.preventDefault();run(state.items[state.active]);}
      else if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}
      else if(event.key==='Tab'){event.preventDefault();}  // focus stays in the palette while it is open
    });
    list.addEventListener('mousedown',event=>event.preventDefault());  // keep focus in the input
    list.addEventListener('click',event=>{
      const id=event.target.closest('[data-command]')?.dataset.command;
      run(state.items.find(c=>c.id===id));
    });
    dialog.addEventListener('mousedown',event=>{if(event.target===dialog)close();});
    root.addEventListener('keydown',event=>{
      const key=event.key.toLowerCase();
      if((event.ctrlKey||event.metaKey)&&!event.altKey&&(key==='k'||(key==='p'&&event.shiftKey))){
        event.preventDefault();state.open?close():open();
      }
    });
    return {open,close,render,state:()=>({open:state.open,items:state.items.map(c=>c.id),active:state.active})};
  }

  return Object.freeze({score,rank,mount});
});
