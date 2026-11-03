import {esc,n,time,colored} from './format.mjs';
import {COUNTRY_CODES} from './countries.mjs';

const known = v => typeof v === 'number' && Number.isFinite(v);
const signed = (v,d=1) => known(v) ? `${v>0?'+':''}${v.toFixed(d)}` : '—';
const seconds = v => known(v) && v>=0 ? `${n(v,1)} s` : '—';
const paint = c => /^#[0-9a-f]{6}$/i.test(c||'') ? c : '#8c929f';
const chip = (role,text,title='') => `<span class="race-chip" data-element="${role}" data-role="${role}" title="${esc(title)}" style="color:var(--c-${role},var(--c-label))">${esc(text)}</span>`;

// Keep the scroll container, table and driver rows alive across telemetry ticks.
// Replacing the whole table interrupts native touch scrolling and scroll anchoring.
export function refreshRaceTable(body, markup) {
  const template=document.createElement('template');
  template.innerHTML=markup;
  const next=template.content.querySelector('.race-table');
  const table=body.querySelector('.race-table');
  if (!table || !next) {
    body.replaceChildren(template.content);
    return ()=>{};
  }
  const scroll=body.scrollTop;
  const top=body.getBoundingClientRect().top+table.tHead.offsetHeight;
  const anchor=[...table.tBodies[0].rows].find(row=>row.getBoundingClientRect().bottom>top);
  const anchorTop=anchor?.getBoundingClientRect().top;
  const tbody=table.tBodies[0];
  const existing=new Map([...tbody.rows].map(row=>[row.dataset.carIdx,row]));
  let cursor=tbody.firstElementChild;
  for (const nextRow of [...next.tBodies[0].rows]) {
    const row=existing.get(nextRow.dataset.carIdx)||nextRow.cloneNode(true);
    if (existing.has(nextRow.dataset.carIdx)) patchElement(row,nextRow);
    existing.delete(nextRow.dataset.carIdx);
    if (row!==cursor) tbody.insertBefore(row,cursor);
    cursor=row.nextElementSibling;
  }
  for (const row of existing.values()) row.remove();
  // Apply after visibility settings so hidden details cannot shift the anchor.
  return ()=>{
    if (anchor?.isConnected) {
      const shift=anchor.getBoundingClientRect().top-anchorTop;
      if (Math.abs(shift)>.5) body.scrollTop+=shift;
    } else if (body.scrollTop!==scroll) body.scrollTop=scroll;
  };
}
export function clock(seconds) {
  if (!known(seconds) || seconds<0 || seconds>=604800) return '—';
  const t=Math.floor(seconds);
  return t>=3600 ? `${Math.floor(t/3600)}:${String(Math.floor(t/60)%60).padStart(2,'0')}:${String(t%60).padStart(2,'0')}` : `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`;
}
export function raceGap(value,laps,estimated=false) {
  if (known(laps) && laps>0) return `+${laps}L`;
  return known(value) ? `${estimated?'≈ ':''}${signed(value)}` : '—';
}
export function driverStatuses(d) {
  const result=[];
  if (d.ai) result.push(chip('status','AI'));
  if (d.disqualified) result.push(chip('status','DQ','Disqualified'));
  if (d.penalty) result.push(chip('status','BLACK FLAG','Penalty instruction'));
  if (d.slowdown) result.push(chip('status','SLOW DOWN'));
  if (d.repair) result.push(chip('status','REPAIR'));
  if (d.finished) result.push(chip('status','FINISHED'));
  if (d.result_status) result.push(chip('status',d.result_status,'Session result status'));
  if (known(d.tow_time) && d.tow_time>0) result.push(chip('pitStatus',`TOW ${seconds(d.tow_time)}`));
  else if (d.pit===true) result.push(`<span class="race-chip pit-badge" data-element="pitStatus" data-status="pit">PIT${known(d.pit_elapsed)?' '+seconds(d.pit_elapsed):''}${d.surface===1?' · STALL':''}</span>`);
  else if (d.out_lap) result.push(chip('pitStatus','OUT LAP'));
  else if (d.surface===1) result.push(chip('pitStatus','IN STALL'));
  if (d.surface===0) result.push(chip('status','OFF TRACK'));
  if (d.surface===-1) result.push(chip('status','NOT ON TRACK'));
  if (d.radio_recent||d.radio) result.push(chip('radio','RADIO'));
  if (!(d.focus??d.player) && known(d.lap_difference) && d.lap_difference!==0) {
    const ahead=d.lap_difference>0;
    result.push(chip(ahead?'lapping':'lapped',`${d.relation_is_focus?(ahead?'AHEAD OF FOCUS':'BEHIND FOCUS'):(ahead?'LAPPING YOU':'LAPPED')} ${ahead?'+':'−'}${Math.abs(d.lap_difference)}L`,ahead?'Ahead of you by a lap or more':'Behind you by a lap or more'));
  }
  return result.join('');
}
export function raceTable(type,data,safetyBadge) {
  const ds=data.drivers||[];
  const rows=ds.filter(d=>type!=='relative'||known(d.pct)&&d.pct>=0&&d.surface!==-1).sort((a,b)=>
    type==='standings'?(a.position||10000)-(b.position||10000):(b.relative??-10000)-(a.relative??-10000));
  return     `<table class="race-table ${type==='standings'?'standings-table':'relative-table'}"><thead><tr><th data-element="position">P</th><th data-element="number">#</th><th data-element="driver">DRIVER</th><th data-element="timing" title="${type==='relative'?'+ ahead of you, − behind you':'Last completed lap'}">${type==='relative'?'GAP ≈':'LAST LAP'}</th>${type==='standings'?`<th data-element="gap" title="Gap to class leader">GAP</th><th data-element="bestTime">BEST</th><th data-element="interval">INT</th><th data-element="averageLap">AVG</th><th data-element="lapDeltas">Δ</th><th data-element="carBrand">CAR</th><th data-element="lapCount">LAPS</th><th data-element="stint">STINT</th><th data-element="iratingChange">≈ ΔiR</th>`:''}</tr></thead><tbody>${rows.map(d=>{
      const relation=(d.focus??d.player)?'self':d.lap_difference>0?'ahead':d.lap_difference<0?'behind':'same';
      const flag=COUNTRY_CODES.has(d.country)?`<img class="driver-flag" data-element="flag" src="/flags/${d.country.toLowerCase()}.svg" alt="${d.country}" title="${d.country}" width="24" height="18">`:'<img class="driver-flag" data-element="flag" src="/flags/iracing.svg" alt="iRacing" title="Country unavailable" width="24" height="18">';
      const team=d.team&&d.team!==d.name?colored('team',esc(d.team),'span','driver-team'):'';
      const compound=d.compound||(known(d.compound_index)?'C'+d.compound_index:null);
      const change=known(d.position_change)?chip('positionChange',`${d.position_change>0?'↑':d.position_change<0?'↓':'='}${Math.abs(d.position_change)}`,'Positions gained/lost from the grid'):'';
      const rating=!d.ai?colored('irating',known(d.rating)&&d.rating>0?'iR '+n(d.rating,0):'iR —'):'';
      const prediction=known(d.irating_change)?chip('iratingChange','≈ ΔiR '+signed(d.irating_change,0),'Provisional estimate if current positions become the final result; not an official rating update'):'';
      const pitHistory=known(d.last_pit_lap)?chip('pitHistory',`Last PIT L${n(d.last_pit_lap,0)}${known(d.pit_duration)?' · lane '+seconds(d.pit_duration):''}${known(d.pit_stop_duration)?' · stop '+seconds(d.pit_stop_duration):''}`):'';
      const p2p=known(d.p2p_count)||d.p2p_active===true?chip('pushToPass',`P2P ${d.p2p_active?'ON':'OFF'}${known(d.p2p_count)?' · '+n(d.p2p_count,0):''}`,'SDK push-to-pass activation and counter; counter meaning depends on the car/session'):'';
      return `<tr class="${(d.focus??d.player)?'me':''}" data-car-idx="${esc(d.id)}" data-lap-state="${relation}"><td data-element="position">${colored('position',esc(d.position))}${known(d.class_position)?`<small data-element="classPosition" title="Class position">C${n(d.class_position,0)}</small>`:''}${change}</td><td data-element="number">${colored('number',esc(d.number))}</td><td class="name"><span class="driver-name-line">${flag}${colored('driver',esc(d.name))}</span>${team}<span class="driver-statuses">${driverStatuses(d)}</span><span class="driver-details"><span data-element="class" class="driver-class" style="border-color:${paint(d.class_color)}">${colored('class',esc(d.class_name))}</span>${type==='relative'?colored('carBrand',esc(d.car_brand)):''}${rating}${!d.ai?safetyBadge(d):''}${type==='relative'?prediction:''}${compound?chip('compound',compound):''}${p2p}</span><span class="driver-extra">${pitHistory}${type==='relative'&&known(d.laps)?chip('lapCount','L'+n(d.laps,0),'Completed laps'):''}${type==='relative'&&known(d.stint_lap)?chip('stint','STINT L'+n(d.stint_lap,0)):''}</span></td><td class="race-timing" data-element="timing"><span data-element="timing">${colored('timing',type==='relative'?signed(d.relative,2):time(d.last_lap))}</span></td>${type==='standings'?`<td class="race-gap" data-element="gap" data-gap-trend="${d.gap_trend==='closing'?'closing':d.gap_trend==='opening'?'opening':'steady'}">${raceGap(d.gap,d.gap_laps,d.gap_estimated)}</td><td data-element="bestTime" class="${d.class_fastest?'class-fastest':''}">${time(d.best_lap)}</td><td data-element="interval">${raceGap(d.interval,d.interval_laps,d.interval_estimated)}</td><td data-element="averageLap">${time(d.average_lap)}</td><td data-element="lapDeltas">${d.lap_deltas?.length?d.lap_deltas.map(v=>signed(v,1)).join(' / '):'—'}</td><td data-element="carBrand">${colored('carBrand',esc(d.car_brand))}</td><td data-element="lapCount">${n(d.laps,0)}</td><td data-element="stint">${n(d.stint_lap,0)}</td><td data-element="iratingChange">${prediction||'—'}</td>`:''}</tr>`;
    }).join('')}</tbody></table>`;
}

export function patchElement(target, source) {
    if (target.nodeType===3) {
      if (target.nodeValue!==source.nodeValue) target.nodeValue=source.nodeValue;
      return;
    }
    for (const attribute of [...target.attributes]) if (!source.hasAttribute(attribute.name)) target.removeAttribute(attribute.name);
    for (const attribute of source.attributes) if (target.getAttribute(attribute.name)!==attribute.value) target.setAttribute(attribute.name,attribute.value);
    let index=0;
    for (const child of [...source.childNodes]) {
      const old=target.childNodes[index];
      if (!old) target.append(child.cloneNode(true));
      else if (old.nodeType!==child.nodeType || old.nodeName!==child.nodeName) old.replaceWith(child.cloneNode(true));
      else patchElement(old,child);
      index++;
    }
    while (target.childNodes.length>index) target.lastChild.remove();
  }
