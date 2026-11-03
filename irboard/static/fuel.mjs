// Original fuel planning math. All estimates remain proposals until Apply.
const finite = v => typeof v === 'number' && Number.isFinite(v);
export function fuelEstimate(data, {target='finish', amount=10, reserve=.5}={}) {
  const fail = reason => ({available:false, reason});
  const car=data?.car || {}, session=data?.session || {};
  if (target==='finish' && session.type?.toLowerCase()!=='race') return fail('Finish estimate requires a Race session. Choose Next stint for Practice.');
  const perLap=data?.fuel?.average;
  if (!finite(perLap) || perLap<=0 || perLap>100) return fail(data?.fuel?.message || 'Complete one full clean on-track lap to measure fuel consumption.');
  if (!finite(car.fuel) || car.fuel<0) return fail('Current fuel level is unavailable.');
  if (!finite(reserve) || reserve<0 || reserve>10) return fail('Reserve must be between 0 and 10 laps.');
  const times=(data?.history || []).filter(l=>l.clean && finite(l.time) && l.time>0).slice(0,8).map(l=>l.time);
  const lapTime=times.length ? times.reduce((a,b)=>a+b,0)/times.length :
    car.last_lap>0 ? car.last_lap : car.best_lap>0 ? car.best_lap : null;
  let laps, basis;
  if (target==='finish') {
    if (session.type?.toLowerCase()!=='race') return fail('Finish estimate is available during a race.');
    const remaining=session.laps_remaining;
    const lapBound=finite(remaining) && remaining>=0 && remaining<10000 ?
      Math.max(0,remaining-(finite(car.lap_pct) ? Math.max(0,Math.min(1,car.lap_pct)) : 0)) : null;
    const seconds=session.remaining;
    const timeBound=finite(seconds) && seconds>=0 && seconds<604800 && lapTime ? Math.ceil(seconds/lapTime)+1 : null;
    if (car.finished === true || session.state>=6) { laps=0; basis='Race finished'; }
    else if (lapBound!==null && (timeBound===null || lapBound<=timeBound)) { laps=lapBound; basis='Remaining laps'; }
    else if (timeBound!==null) { laps=timeBound; basis='Timed race + final lap'; }
    else return fail('Race distance or a measured lap time is unavailable.');
  } else {
    if (!finite(amount) || amount<=0 || amount>1000) return fail('Enter a positive stint length (maximum 1000).');
    if (target==='minutes') {
      if (!lapTime) return fail('Complete a timed lap to calculate a stint in minutes.');
      laps=amount*60/lapTime; basis=`${amount} minute stint`;
    } else if (target==='laps') { laps=amount; basis=`${amount} lap stint`; }
    else return fail('Choose a fuel target.');
  }
  const required=laps>0 ? (laps+reserve)*perLap : 0;
  const deficit=Math.max(0,required-car.fuel);
  const capacity=data?.pit?.fuel_max;
  const room=finite(capacity) && capacity>0 ? Math.max(0,capacity-car.fuel) : null;
  const add=Math.min(500,Math.ceil(deficit),room===null ? 500 : Math.floor(room));
  const shortfall=Math.max(0,required-(car.fuel+add));
  return {available:true, add, required, laps, perLap, basis:data?.fuel?.historical?`${basis} · historical consumption`:basis, shortfall,
    limited:shortfall>.01, capacityKnown:room!==null, manual:false};
}
