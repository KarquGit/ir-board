// SDK race-control flags and CarLeftRight are independent of dashboard widgets.
export const RACE_FLAGS = [
  {mask:0x10, name:'red', label:'Red flag', color:'#d82032'},
  {mask:0x30000, name:'black', label:'Black flag', color:'#171717'},
  {mask:0x100000, name:'repair', label:'Repair flag', color:'radial-gradient(circle at center, #f09020 0% 18%, #171717 18%)'},
  {mask:0x1, name:'checkered', label:'Chequered flag', color:'repeating-conic-gradient(#ffffff 0% 25%, #171717 0% 50%) 0 0 / 96px 96px'},
  {mask:0x40, name:'debris', label:'Debris flag', color:'repeating-linear-gradient(90deg, #ffcf24 0 10%, #d82032 10% 20%)'},
  {mask:0xc108, name:'yellow', label:'Yellow / caution flag', color:'#ffcf24'},
  {mask:0x20, name:'blue', label:'Blue flag', color:'linear-gradient(135deg, #1676f3 0% 42%, #ffcf24 42% 58%, #1676f3 58%)'},
  {mask:0x2, name:'white', label:'White flag', color:'#ffffff'},
  {mask:0x404, name:'green', label:'Green flag', color:'#18bd58'},
];

const numeric = (value, min, max, fallback) =>
  typeof value==='number' && Number.isFinite(value) ? Math.max(min,Math.min(max,value)) : fallback;

export function alertSettings(raw) {
  const flags=raw?.flags, spotter=raw?.spotter;
  return {
    flags:{
      mode:['off','flash','center'].includes(flags?.mode) ? flags.mode : 'center',
      duration:numeric(flags?.duration,1,10,3),
      opacity:numeric(flags?.opacity,.1,1,.65),
      blink:flags?.blink===true,
      untilClear:flags?.untilClear===true,
      enabled:Object.fromEntries(RACE_FLAGS.map(flag=>[flag.name,flags?.enabled?.[flag.name]!==false])),
    },
    spotter:{
      mode:['off','halves','bars'].includes(spotter?.mode) ? spotter.mode : 'off',
      opacity:numeric(spotter?.opacity,.1,1,.3),
    },
  };
}

export function raceFlag(bits=0, enabled={}) {
  if (!Number.isInteger(bits) || bits<0) return null;
  return RACE_FLAGS.find(flag=>(bits & flag.mask) && enabled[flag.name]!==false) || null;
}

export function spotterSides(value) {
  return {left:[2,4,5].includes(value), right:[3,4,6].includes(value)};
}

export class FlagNotice {
  constructor() { this.key=null; this.until=0; }
  update(flag, settings, sessionKey, now) {
    if (!flag || settings.mode==='off') {
      this.key=null; this.until=0;
      return null;
    }
    const key=JSON.stringify([sessionKey,flag.name,settings]);
    const changed=key!==this.key;
    if (changed) { this.key=key; this.until=now+settings.duration*1000; }
    return {flag,changed,visible:settings.untilClear || now<this.until};
  }
}

export class DrivingAlerts {
  constructor(document) {
    this.flag=document.querySelector('#race-flag-overlay');
    this.cloth=this.flag.querySelector('.race-flag-cloth');
    this.label=this.flag.querySelector('.race-flag-label');
    this.spotter=document.querySelector('#screen-spotter');
    this.left=this.spotter.querySelector('[data-side=left]');
    this.right=this.spotter.querySelector('[data-side=right]');
    this.notice=new FlagNotice();
  }

  update(data, raw, fresh) {
    const settings=alertSettings(raw);
    const selected=fresh ? raceFlag(data.session?.flags,settings.flags.enabled) : null;
    const notice=this.notice.update(selected,settings.flags,data.session?.key,performance.now());
    this.flag.hidden=!notice?.visible;
    if (!notice) clearTimeout(this.flagTimeout);
    if (notice?.changed) {
      clearTimeout(this.flagTimeout);
      if (!settings.flags.untilClear) this.flagTimeout=setTimeout(()=>{this.flag.hidden=true;},settings.flags.duration*1000);
      this.flag.dataset.mode=settings.flags.mode;
      this.flag.dataset.blink=String(settings.flags.blink);
      this.flag.dataset.flag=selected.name;
      this.cloth.style.background=selected.color;
      if (selected.name==='checkered') this.cloth.style.backgroundSize=settings.flags.mode==='center' ? '24px 24px' : '96px 96px';
      this.flag.style.setProperty('--race-flag-opacity',settings.flags.opacity);
      this.label.textContent=selected.label;
      this.flag.setAttribute('aria-label',selected.label);
      // Restart once for a new event, never for ordinary telemetry polling.
      this.cloth.style.animation='none';
      void this.cloth.offsetWidth;
      this.cloth.style.animation='';
    }
    const car=data.car || {};
    const available=fresh && car.in_car!==false && !car.replay && !car.garage;
    const sides=available ? spotterSides(car.left_right) : spotterSides(null);
    this.spotter.hidden=settings.spotter.mode==='off' || !(sides.left || sides.right);
    this.spotter.dataset.mode=settings.spotter.mode;
    this.spotter.style.setProperty('--spotter-opacity',settings.spotter.opacity);
    this.left.hidden=!sides.left;
    this.right.hidden=!sides.right;
  }
}
