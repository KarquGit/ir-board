import {time} from './format.mjs';

const known=v=>typeof v==='number' && Number.isFinite(v);
const signed=(v,d=2)=>known(v)?`${v>0?'+':''}${v.toFixed(d)}`:'—';
export const EXPERIMENTAL_TYPES=['irlogic'];
export const REFERENCE_NAMES={session:'Session best clean lap',personal:'Recorded personal best',last:'Previous clean lap'};
export const referenceMode=value=>Object.hasOwn(REFERENCE_NAMES,value)?value:'session';

export function referenceLap(data,widget={}) {
  const mode=referenceMode(widget.coachReference), refs=data.coaching?.references || {};
  return data.coaching?.laps?.[refs[mode] || (mode==='session'?refs.personal:null)] || null;
}

export function interpolate(samples,pct,field='time') {
  if (!Array.isArray(samples) || samples.length<2 || !known(pct) || pct<samples[0].pct || pct>samples.at(-1).pct) return null;
  let low=0,high=samples.length-1;
  while (high-low>1) {const mid=(low+high)>>1;if(samples[mid].pct<=pct)low=mid;else high=mid;}
  const a=samples[low],b=samples[high];
  if (!known(a[field]) || !known(b[field]) || !(b.pct>a.pct)) return null;
  return a[field]+(b[field]-a[field])*(pct-a.pct)/(b.pct-a.pct);
}

export function sectorComparison(data,widget={}) {
  const sectors=Array.isArray(data.sectors)?data.sectors:[];
  const pct=data.car?.lap_pct,ref=referenceLap(data,widget),trace=data.coaching?.trace || [];
  const current=known(pct)?sectors.findIndex(s=>pct>=s.start && pct<s.end):-1;
  return {current,sectors:sectors.map((sector,index)=>{
    const start=interpolate(ref?.samples,sector.start),end=interpolate(ref?.samples,sector.end);
    const from=interpolate(trace,sector.start),to=interpolate(trace,sector.end);
    let delta=null;
    if (known(start) && known(end) && known(from)) {
      if (index===current && known(data.coaching?.current_time)) {
        const progress=interpolate(ref.samples,pct);
        if(known(progress))delta=data.coaching.current_time-from-(progress-start);
      } else if (known(to)) delta=to-from-(end-start);
    }
    return {...sector,reference:known(start)&&known(end)?end-start:null,delta};
  })};
}

export function sectorState(sector,index,current) {
  if(index===current)return 'current';
  if(current<0 || index>current || !known(sector.delta))return 'pending';
  return sector.delta<0?'gain':sector.delta>0?'loss':'even';
}

const metric=(label,field,role=field)=>`<div class="experiment-metric" data-element="${field}"><small data-role="label">${label}</small><strong data-field="${field}" data-role="${role}" style="color:var(--c-${role},var(--c-text))">—</strong><small data-field="${field}-ref" data-role="label"></small></div>`;

export function experimentalContent(type) {
  if(type==='irlogic')return `<div class="experimental-widget logic-widget"><header class="coach-heading"><span>iR-logic</span><small>LAP COACH</small></header><span class="experiment-eyebrow" data-role="label">DELTA TO REFERENCE</span><div class="logic-delta-wrap" data-element="delta"><strong class="logic-delta" data-field="delta">—</strong><span>s</span></div><div class="logic-gauge" data-element="gauge"><i></i><span></span></div><div class="logic-gauge-labels" data-element="gauge"><span>−1.0</span><span>0</span><span>+1.0</span></div><div class="logic-times">${metric('PREDICTED LAP','predicted')}${metric('REFERENCE LAP','reference')}</div><div class="sector-window" data-element="sectors"><div class="sector-strip"></div></div><p class="experiment-note" data-field="note" data-role="label"></p></div>`;
  return "";
}

const text=(root,field,value)=>{const el=root.querySelector(`[data-field="${field}"]`);if(el && el.textContent!==String(value))el.textContent=value;};
function refreshLogic(root,data,widget) {
  const ref=referenceLap(data,widget),pct=data.car?.lap_pct;
  const car=data.car || {},available=car.in_car!==false && !car.pit && !car.replay && !car.garage;
  const elapsed=available?(data.coaching?.current_time ?? car.current_lap):null;
  const reference=interpolate(ref?.samples,pct),delta=known(elapsed)&&known(reference)?elapsed-reference:null;
  text(root,'delta',signed(delta));
  root.querySelector('[data-field=delta]').dataset.role=known(delta)&&delta<=0?'positive':'negative';
  text(root,'predicted',known(delta)?time(ref.lap_time+delta):'—');text(root,'reference',time(ref?.lap_time));
  const fill=root.querySelector('.logic-gauge i'),size=known(delta)?Math.min(50,Math.abs(delta)*50):0;
  fill.style.width=`${size}%`;fill.style.left=delta<=0?`${50-size}%`:'50%';fill.style.background=delta<=0?'var(--c-positive)':'var(--c-negative)';
  const comparison=sectorComparison(data,widget),sectors=comparison.sectors,count=sectors.length;
  const signature=JSON.stringify(sectors.map(s=>[s.number,s.start,s.end])),strip=root.querySelector('.sector-strip');
  if(root.dataset.sectors!==signature){
    clearTimeout(root.sectorTimer);root.dataset.sectors=signature;root.activeSector=null;
    strip.innerHTML=count?Array.from({length:count+2},(_,i)=>{if(count===1 && i!==1)return '<div class="sector-spacer"></div>';const index=(i-1+count)%count;return `<div class="sector-cell" data-sector-index="${index}"><small data-role="label">S${sectors[index].number}</small><strong></strong><span data-role="label"></span></div>`;}).join(''):'';
  }
  strip.querySelectorAll('.sector-cell').forEach(cell=>{
    const index=Number(cell.dataset.sectorIndex),sector=sectors[index];
    cell.classList.toggle('active',index===comparison.current);
    cell.dataset.state=sectorState(sector,index,comparison.current);
    cell.querySelector('strong').textContent=signed(sector.delta);
    cell.querySelector('strong').removeAttribute('data-role');
    cell.querySelector('span').textContent=index===comparison.current?'CURRENT':time(sector.reference);
  });
  const current=comparison.current;
  if(current>=0 && current!==root.activeSector){
    const previous=root.activeSector;clearTimeout(root.sectorTimer);
    if(previous===count-1 && current===0 && count>1){
      strip.style.transition='';strip.style.transform=`translateX(${-count*100/3}%)`;
      root.sectorTimer=setTimeout(()=>{strip.style.transition='none';strip.style.transform='translateX(0%)';},280);
    } else {
      strip.style.transition=previous===null?'none':'';
      strip.style.transform=`translateX(${-current*100/3}%)`;
    }
    root.activeSector=current;
  }
  text(root,'note',!ref?`Record a complete clean lap for ${REFERENCE_NAMES[referenceMode(widget.coachReference)].toLowerCase()}.`:!count?'Sector metadata unavailable from SDK.':`${referenceMode(widget.coachReference)==='session' && !data.coaching?.references?.session?'Recorded personal best · saved fallback for Session best':REFERENCE_NAMES[referenceMode(widget.coachReference)]} · ${count} ${data.sector_source==='demo-generated'?'synthetic DEMO ':''}sectors · current sector stays centered`);
}

export function refreshExperimental(body,type,data,widget={}) {
  if(body.dataset.experimentalType!==type || !body.querySelector('.experimental-widget')){
    body.innerHTML=experimentalContent(type);body.dataset.experimentalType=type;
  }
  const root=body.querySelector('.experimental-widget');
  if(type==='irlogic')refreshLogic(root,data,widget);
}
