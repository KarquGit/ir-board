import {esc,n,time,colored} from './format.mjs';
import {fuelEstimate} from './fuel.mjs';
import {clock,patchElement} from './race-view.mjs';

const known=v=>typeof v==='number'&&Number.isFinite(v);
const metric=(label,value,role)=>`<div class="metric" data-element="${esc(role)}"><span class="label" data-role="label">${esc(label)}</span>${colored(String(role).replace(/[^a-zA-Z0-9_-]/g,''),value,'strong')}</div>`;
const percent=v=>known(v)?`${n(Math.max(0,Math.min(1,v))*100,0)}%`:'—';
export function engineWarnings(value) {
  return [[1,'WATER TEMP'],[2,'FUEL PRESSURE'],[4,'OIL PRESSURE'],[8,'ENGINE STALLED'],[32,'REV LIMIT'],[64,'OIL TEMP']]
    .filter(([bit])=>(value||0)&bit).map(([,label])=>label);
}
export function inputsView(data,speedReading) {
  const c=data.car||{},speed=speedReading(c),samples=data.input_trace||[];
  const bars=['throttle','brake','clutch'].map((key,i)=>`<div class="pedal" data-element="${key}"><div class="pedal-track" data-role="pedalOff"><i data-role="${key}" style="background:var(--c-${key});height:${known(c[key])?Math.max(0,Math.min(100,c[key]*100)):0}%"></i></div><span data-role="label">${['THR','BRK','CLT'][i]} ${percent(c[key])}</span></div>`).join('');
  const traces=['throttle','brake','clutch'].map(key=>{
    const points=samples.flatMap((sample,index)=>known(sample[key])?[`${index/Math.max(1,samples.length-1)*600},${95-Math.max(0,Math.min(1,sample[key]))*90}`]:[]);
    return `<polyline data-role="${key}" style="stroke:var(--c-${key})" points="${points.join(' ')}"/>`;
  }).join('');
  return `<div class="inputs-panel" data-abs-active="${c.abs_active===true}"><div class="gear-row"><div class="center">${colored('gear',c.gear===0?'N':c.gear===-1?'R':esc(c.gear),'div','hero')}${colored('speed',`${n(speed.value,0)} ${speed.unit}`)}</div><div class="pedals">${bars}</div></div><div class="input-trace" data-element="trace"><span class="label" data-role="label">Input trace</span>${samples.length>1?`<svg viewBox="0 0 600 100" preserveAspectRatio="none" aria-label="Recent throttle, brake and clutch inputs">${traces}</svg>`:'<span data-role="label">Waiting for input samples</span>'}</div></div>`;
}
export function refreshInputs(body,markup) {
  const template=document.createElement('template');
  template.innerHTML=markup;
  const current=body.querySelector('.inputs-panel');
  if (current) patchElement(current,template.content.firstElementChild);
  else body.replaceChildren(template.content);
}
export function lapsView(data) {
  const c=data.car||{};
  const signed=v=>known(v)?`${v>0?'+':''}${n(v,3)} s`:'—';
  const deltas=[['Personal best',c.delta_best],['Personal optimal',c.delta_optimal],['Session optimal',c.delta_session_optimal],['Previous lap',c.delta_last]];
  return `<span class="label" data-element="current" data-role="label">Current lap</span>${colored('current',time(c.current_lap),'div','big')}<div data-element="delta">${colored(known(c.delta)&&c.delta<=0?'positive':'negative',signed(c.delta),'p')}</div><div class="divider" data-role="border"></div><div class="metrics">${metric('Best',time(c.best_lap),'best')}${metric('Last',time(c.last_lap),'last')}${metric('Predicted',time(c.predicted_lap),'predicted')}${metric('Recorded PB',time(c.recorded_best),'recordedBest')}</div><div class="lap-deltas" data-element="references">${deltas.map(([label,value])=>`<span><small data-role="label">${label}</small><strong data-role="${known(value)&&value<=0?'positive':'negative'}">${signed(value)}</strong></span>`).join('')}</div>${(data.history||[]).slice(0,12).map(h=>`<div class="history-row ${h.clean===false?'unclean-lap':''}" data-element="history"><span data-role="label">L${esc(h.lap)}${h.clean===false?' · invalid/pit':''}</span>${colored('history',time(h.time))}</div>`).join('')}`;
}
export function fuelView(data) {
  const c=data.car||{},f=data.fuel||{},capacity=data.pit?.fuel_max;
  const pct=known(capacity)&&capacity>0&&known(c.fuel)?Math.max(0,Math.min(100,c.fuel/capacity*100)):null;
  const proposal=fuelEstimate(data),cleanTimes=(data.history||[]).filter(h=>h.clean&&known(h.time)&&h.time>0).slice(0,8);
  const lapTime=cleanTimes.length?cleanTimes.reduce((sum,h)=>sum+h.time,0)/cleanTimes.length:c.last_lap>0?c.last_lap:null;
  const remainingTime=known(f.laps_left)&&known(lapTime)?f.laps_left*lapTime:null;
  return `<div class="fuel-compact"><div class="fuel-cylinder" data-element="gauge" role="img" aria-label="${pct===null?'Tank capacity unavailable':n(pct,0)+'% fuel remaining'}"><div class="fuel-cylinder-fill" style="height:${pct??0}%"></div><span>${pct===null?'—':n(pct,0)+'%'}</span></div><div class="fuel-values"><span class="label" data-element="level" data-role="label">Fuel</span><div class="big" data-element="level">${colored('level',n(c.fuel))}<span class="unit" data-role="label">L</span></div><div class="divider" data-role="border"></div><div class="metrics">${metric('Average / lap',n(f.average,2)+' L','average')}${metric('Remaining',n(f.laps_left)+' laps','remaining')}${metric('Last',n(f.last,2)+' L','last')}${metric('Fuel to add',n(proposal.available?proposal.add:null,0)+' L','needed')}${metric('Minimum / lap',n(f.minimum,2)+' L','minimum')}${metric('Maximum / lap',n(f.maximum,2)+' L','maximum')}${metric('Time remaining',clock(remainingTime),'fuelTime')}${metric('Tank capacity',n(capacity,1)+' L','capacity')}${metric('Instantaneous use',known(c.fuel_rate)?n(c.fuel_rate,1)+' kg/h':'—','flow')}</div><p class="hint" data-element="hint" data-role="label">${f.historical?'Historical measurement · ':''}${f.samples?.length||0} measured clean laps. ${esc(proposal.available?proposal.limited?`Plan shortfall ${n(proposal.shortfall,1)} L; another stop may be needed.`:proposal.basis:proposal.reason)}</p></div></div>`;
}
export function systemsView(data) {
  const c=data.car||{},systems=c.systems?.length?c.systems:[{label:'Brake bias',role:'bias',value:c.bias,unit:'%'},{label:'ABS',role:'abs',value:c.abs},{label:'TC',role:'tc',value:c.tc},{label:'Engine map',role:'engine',value:c.map}];
  return `<div class="metrics systems-grid">${systems.map(s=>metric(s.label,n(s.value,s.unit==='%'?1:0)+(known(s.value)&&s.unit?' '+esc(s.unit):''),s.role)).join('')}</div>`;
}
const UNITS={Speed:'m/s',RPM:'rpm',FuelLevel:'L',FuelUsePerHour:'kg/h',WaterTemp:'°C',OilTemp:'°C',AirTemp:'°C',TrackTempCrew:'°C',WindVel:'m/s',WindDir:'rad',RelativeHumidity:'fraction',Precipitation:'fraction',SteeringWheelAngle:'rad',SteeringWheelAngleMax:'rad',Throttle:'fraction',Brake:'fraction',Clutch:'fraction',Lat:'°',Lon:'°',SessionTime:'s',SessionTimeRemain:'s',LapCurrentLapTime:'s',LapLastLapTime:'s',LapBestLapTime:'s',LapDistPct:'fraction',OilPress:'bar',FuelPress:'bar',Voltage:'V'};
export function inspectorView(data) {
  return `<table class="inspector-table"><thead><tr><th>SDK field</th><th>Value</th><th>Unit</th></tr></thead><tbody>${Object.entries(data.raw||{}).map(([key,value])=>`<tr><td>${colored('key',esc(key))}</td><td><pre data-role="value" data-element="value">${esc(value===null||value===undefined?'—':typeof value==='number'?n(value,Number.isInteger(value)?0:4):JSON.stringify(value))}</pre></td><td data-role="label">${esc(UNITS[key]||'')}</td></tr>`).join('')}</tbody></table>`;
}
