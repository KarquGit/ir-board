export const BUTTON_ACTIONS = Object.freeze(Object.fromEntries([
  ['ignition','Ignition'], ['starter','Starter'], ['pit_limiter','Pit limiter'],
  ['flash','Flash lights'], ['wipers','Wipers'], ['radio','Radio'],
  ['bias_down','Brake bias −'], ['bias_up','Brake bias +'],
  ['tc_down','Traction control −'], ['tc_up','Traction control +'],
  ['abs_down','ABS −'], ['abs_up','ABS +'],
].map(([action,label],index)=>[action,Object.freeze({label,defaultKey:`F${index+13}`,hold:['starter','radio'].includes(action)})])));
export const BUTTON_KEYS = Object.freeze(['',...Array.from({length:24},(_,i)=>`F${i+1}`),...'ABCDEFGHIJKLMNOPQRSTUVWXYZ',...'0123456789']);
export function buttonBindings(raw) {
  return Object.fromEntries(Object.entries(BUTTON_ACTIONS).map(([action,meta])=>{
    const value=raw && Object.hasOwn(raw,action)?raw[action]:meta.defaultKey;
    return [action,typeof value==='string' && BUTTON_KEYS.includes(value)?value:meta.defaultKey];
  }));
}
export function buttonboxBindingsEditor(raw) {
  const bindings=buttonBindings(raw);
  return `<details class="buttonbox-bindings"><summary>Button box keyboard bindings</summary><p class="help">Choose the same keys in iRacing → Options → Controls. iRacing must be the active window on the PC. Choose Unassigned to disable a button. Starter and Radio operate while held.</p><div class="buttonbox-binding-grid">${Object.entries(BUTTON_ACTIONS).map(([action,meta])=>`<label>${meta.label}<select data-button-binding="${action}" aria-label="${meta.label} key">${BUTTON_KEYS.map(key=>`<option value="${key}" ${bindings[action]===key?'selected':''}>${key || 'Unassigned'}</option>`).join('')}</select></label>`).join('')}</div></details>`;
}
const drawings={
  ignition:'<path d="M24 5v19M14 10a18 18 0 1 0 20 0"/>',
  starter:'<path d="M11 13h25v5h6v17h-6v5H12l-6-8V20h5zm5-6h15M24 7v6M3 22v9"/><path d="m27 18-9 11h8l-4 9 12-14h-9z" fill="currentColor" stroke="none"/>',
  pit_limiter:'<path d="M8 38a20 20 0 1 1 32 0M24 5v5M10 11l4 4m24-4-4 4M5 25h6m26 0h6M24 30l10-13"/><circle cx="24" cy="30" r="4"/>',
  flash:'<path d="M23 10c13 0 19 7 19 14s-6 14-19 14V10zM6 13h11M4 24h13M6 35h11"/>',
  wipers:'<path d="M4 12Q24-2 44 12l-6 25Q24 29 10 37zM25 33l12-17M21 37l4-4"/><circle cx="21" cy="37" r="3"/>',
  radio:'<rect x="17" y="4" width="14" height="26" rx="7"/><path d="M10 22v3a14 14 0 0 0 28 0v-3M24 39v6M16 45h16"/>',
  bias:'<circle cx="24" cy="24" r="18"/><circle cx="24" cy="24" r="6"/><path d="M24 6v6m18 12h-6M24 42v-6M6 24h6m2-14 3 5m17 22-3-5M10 34l5-3m22-17-5 3"/>',
  tc:'<path d="m10 10 5-6h18l5 6 3 3v13H7V13zm-3 9h34M12 26v4m24-4v4M15 33c-12 3 11 6-1 11m19-11c-12 3 11 6-1 11"/>',
  abs:'<path d="M8 6a25 25 0 0 0 0 36M40 6a25 25 0 0 1 0 36"/><circle cx="24" cy="24" r="17"/><text x="24" y="28" text-anchor="middle" fill="currentColor" stroke="none" font-family="Arial,sans-serif" font-size="12" font-weight="700">ABS</text>',
};
const icon=name=>`<svg viewBox="0 0 48 48" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${drawings[name]}</svg>`;
const tile=(action,label,note)=>`<button type="button" class="box-button box-tile" data-action="${action}" data-element="${action}" aria-label="${label}">${icon(action)}<span class="box-copy"><strong>${label}</strong><small data-role="label" data-box-state="${action}">${note}</small></span></button>`;
const adjust=(name,label,suffix)=>`<section class="box-adjust" data-element="${name}" aria-label="${label}"><header>${icon(name)}<strong>${label}</strong></header><div class="box-adjust-controls"><button type="button" class="box-button box-step" data-action="${name}_down" aria-label="Decrease ${label}">−</button><div class="box-reading"><output data-box-value="${name}">—</output><small data-role="label">${suffix}</small></div><button type="button" class="box-button box-step" data-action="${name}_up" aria-label="Increase ${label}">+</button></div></section>`;
export function buttonboxContent() {
  return `<div class="buttonbox"><div class="box-source" data-element="status"><i></i><span>Waiting for telemetry</span></div><div class="box-grid">${tile('ignition','Ignition','—')}${tile('starter','Starter','Hold to start')}${tile('pit_limiter','Pit limiter','—')}${adjust('bias','Brake bias','Front')}${tile('flash','Flash lights','Tap')}${adjust('tc','Traction control','Level')}${tile('wipers','Wipers','—')}${adjust('abs','ABS','Level')}${tile('radio','Radio','Hold to talk')}</div><div class="box-legend" data-element="status"><span><i class="box-on-dot"></i>ON</span><span><i class="box-off-dot"></i>OFF</span><span><i class="box-press-dot"></i>PRESS / HOLD</span><span class="box-unknown">— unavailable</span></div><p class="box-result" role="status" aria-live="polite" data-element="status">Match keyboard bindings in widget settings to iRacing controls.</p></div>`;
}
const controllers=new Map();
let watching=false;
function uuid() {
  const bytes=new Uint8Array(16);
  if(globalThis.crypto?.getRandomValues)globalThis.crypto.getRandomValues(bytes);
  else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(v=>v.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
const setText=(el,value)=>{if(el.textContent!==String(value))el.textContent=value;};
function result(c,message,error=false) {
  setText(c.root.querySelector('.box-result'),message);
  c.root.querySelector('.box-result').classList.toggle('box-error',error);
}
function clearPress(c,press) {
  clearInterval(press.timer);press.released=true;
  press.button.classList.remove('box-pressed');press.button.setAttribute('aria-pressed','false');
  if(c.presses.get(press.action)===press)c.presses.delete(press.action);
}
function release(c,press) {
  if(!press || press.released)return;
  clearPress(c,press);
  // Queue the release after the original down request, even if its response was
  // lost. A matching up is harmless after a timeout, and prevents request races.
  press.done.then(()=>c.send?.({...press.payload,phase:'up'}),()=>c.send?.({...press.payload,phase:'up'})).catch(()=>{});
}
function releaseAll(c) { for(const press of [...c.presses.values()])release(c,press); }
export function releaseButtonboxes() { for(const c of controllers.values())releaseAll(c); }
function watch() {
  if(watching || typeof window==='undefined')return;
  watching=true;
  window.addEventListener('blur',releaseButtonboxes);
  window.addEventListener('pagehide',releaseButtonboxes);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseButtonboxes();});
  new MutationObserver(()=>{
    for(const [body,c] of controllers)if(!body.isConnected || !body.contains(c.root)){
      releaseAll(c);controllers.delete(body);
    }
  }).observe(document.documentElement,{childList:true,subtree:true});
}
function hold(c,button,input) {
  const action=button.dataset.action;
  if(button.disabled || c.presses.has(action) || !c.send)return;
  const payload={action,key:c.bindings[action],press_id:uuid()},press={action,button,input,payload,released:false,timer:null,done:null};
  c.presses.set(action,press);button.classList.add('box-pressed');button.setAttribute('aria-pressed','true');
  press.done=Promise.resolve().then(()=>c.send({...payload,phase:'down'}));
  press.done.then(response=>{
    if(press.released)return;
    result(c,response?.message || `${BUTTON_ACTIONS[action].label} held. Release to stop.`);
    let waiting=false;
    press.timer=setInterval(()=>{
      if(press.released || waiting)return;
      waiting=true;
      Promise.resolve().then(()=>c.send({...payload,phase:'keepalive'})).catch(error=>{
        result(c,error.message || 'Connection lost; held button released.',true);release(c,press);
      }).finally(()=>{waiting=false;});
    },250);
  }).catch(error=>{
    result(c,error.message || 'Unable to send button command.',true);release(c,press);
  });
}
function bind(c) {
  c.root.querySelectorAll('[data-action]').forEach(button=>{
    const action=button.dataset.action,held=BUTTON_ACTIONS[action].hold;
    button.addEventListener('contextmenu',event=>event.preventDefault());
    if(held){
      button.addEventListener('pointerdown',event=>{
        if(event.button!==0 || button.disabled)return;
        event.preventDefault();
        hold(c,button,event.pointerId);
        try {button.setPointerCapture(event.pointerId);}catch{}
      });
      const end=event=>{const press=c.presses.get(action);if(press?.input===event.pointerId)release(c,press);};
      for(const name of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(name,end);
      button.addEventListener('keydown',event=>{
        if(![' ','Enter'].includes(event.key))return;
        event.preventDefault();if(!event.repeat)hold(c,button,'keyboard');
      });
      button.addEventListener('keyup',event=>{
        if(![' ','Enter'].includes(event.key))return;
        event.preventDefault();const press=c.presses.get(action);if(press?.input==='keyboard')release(c,press);
      });
      button.addEventListener('blur',()=>release(c,c.presses.get(action)));
      button.addEventListener('click',event=>event.preventDefault());
    } else button.addEventListener('click',async()=>{
      if(button.disabled || c.busy.has(action) || !c.send)return;
      c.busy.add(action);button.classList.add('box-pressed');
      setTimeout(()=>button.classList.remove('box-pressed'),180);
      try {
        const response=await c.send({action,key:c.bindings[action],phase:'tap',press_id:uuid()});
        result(c,response?.message || 'Key sent. State updates from iRacing telemetry.');
      } catch(error) {result(c,error.message || 'Unable to send button command.',true);}
      finally {c.busy.delete(action);}
    });
  });
}
export function refreshButtonbox(body,data={},widget={},options={}) {
  let c=controllers.get(body);
  if(!c || !body.contains(c.root)){
    if(c)releaseAll(c);
    body.innerHTML=buttonboxContent();
    c={root:body.firstElementChild,send:options.send,bindings:buttonBindings(widget.buttonBindings),presses:new Map(),busy:new Set()};
    controllers.set(body,c);bind(c);watch();
  }
  c.send=options.send;c.bindings=buttonBindings(widget.buttonBindings);
  const state=data.buttonbox || {},preview=!!options.preview;
  const unavailable=!!options.disabled || preview || data.access?.can_control===false || !data.connected || state.available===false || !c.send;
  if(unavailable)releaseAll(c);
  c.root.querySelectorAll('[data-action]').forEach(button=>{
    const action=button.dataset.action;
    button.disabled=unavailable || !c.bindings[action];
    button.title=c.bindings[action]?`${BUTTON_ACTIONS[action].label} · ${c.bindings[action]}`:'Unassigned — configure this widget';
  });
  for(const action of ['ignition','pit_limiter','wipers']){
    const button=c.root.querySelector(`[data-action="${action}"]`),value=state[action];
    const known=typeof value==='boolean';
    button.dataset.state=known?(value?'on':'off'):'unknown';
    if(known)button.setAttribute('aria-pressed',String(value));else button.removeAttribute('aria-pressed');
    setText(button.querySelector('[data-box-state]'),known?(value?'ON':'OFF'):'—');
  }
  for(const name of ['bias','tc','abs']){
    const value=state[name];
    setText(c.root.querySelector(`[data-box-value="${name}"]`),typeof value==='number' && Number.isFinite(value)?(name==='bias'?`${value.toFixed(1)}%`:String(value)):'—');
  }
  const source=c.root.querySelector('.box-source');
  source.dataset.mode=!data.connected?'offline':state.source==='demo' || data.mode==='demo'?'demo':'live';
  setText(source.querySelector('span'),preview?'PREVIEW · buttons disabled':!data.connected?'OFFLINE · controls unavailable':`${source.dataset.mode==='demo'?'DEMO · simulated controls':'LIVE'}${data.car?.name?' · '+data.car.name:''}`);
  if(unavailable && !preview)result(c,options.disabled?'Controls unavailable while editing or telemetry is stale.':state.message || 'Controls unavailable. Connect iRacing and focus its window on the PC.');
  c.root.classList.toggle('box-preview',preview);
}
