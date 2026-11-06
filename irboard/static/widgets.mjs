import { buttonboxContent } from "./buttonbox.mjs";
import { shiftSettings } from "./model.mjs";
import { raceFlag } from "./alerts.mjs";
import { EXPERIMENTAL_TYPES, experimentalContent } from "./experimental.mjs";
import { esc, n, time, colored, scaled } from "./format.mjs";
import { raceTable } from "./race-view.mjs";
import { inputsView, lapsView, fuelView, systemsView, inspectorView, engineWarnings } from "./driving-view.mjs";
export { esc, n, colored };
const metric = (k, v, role = "text") =>
  `<div class="metric" data-element="${role}"><span class="label" data-role="label">${k}</span>${colored(role, v, "strong")}</div>`;
function plot(points, key, role, dashed = false) {
  const pts = points.filter((p) => typeof p[key] === "number");
  return `<polyline data-element="${role}" data-role="${role}" style="stroke:var(--c-${role});${dashed ? "stroke-dasharray:5 4;opacity:.65" : ""}" points="${pts.map((p) => `${(p.pct ?? 0) * 600},${100 - p[key] * 90}`).join(" ")}"/>`;
}
const MAP_CLASSES = {
  GTP:['diamond','#e85d75'], LMP2:['square','#5ca9ff'], LMP3:['triangle','#ffb347'],
  GT3:['circle','#58d68d'], GT4:['pentagon','#b694ff'], TCR:['hexagon','#4dd6cf'],
};
const MAP_SHAPES=['circle','diamond','square','triangle','pentagon','hexagon'];
export function classMarker(driver) {
  const raw=String(driver.class_name||'').trim();
  const normalized=raw.toUpperCase().replace(/[^A-Z0-9]/g,'');
  const family=Object.keys(MAP_CLASSES).find(name=>normalized.includes(name));
  const key=String(driver.class_id??(raw||'unknown'));
  const hash=[...key].reduce((h,c)=>(h*31+c.charCodeAt(0))>>>0,0);
  const preset=MAP_CLASSES[family]||Object.values(MAP_CLASSES)[hash%MAP_SHAPES.length];
  const color=/^#[0-9a-f]{6}$/i.test(driver.class_color||'')?driver.class_color:preset[1];
  return {key,name:raw?(/^\d+$/.test(raw)?'Class '+raw:raw):driver.class_id!=null?'Class '+driver.class_id:'Unknown class',color,shape:family?preset[0]:MAP_SHAPES[hash%MAP_SHAPES.length]};
}
export function markerShape(shape,attributes='') {
  if (shape==='circle') return `<circle r="10" ${attributes}/>`;
  if (shape==='square') return `<rect x="-9" y="-9" width="18" height="18" rx="1" ${attributes}/>`;
  const points={diamond:'0,-12 12,0 0,12 -12,0',triangle:'0,-12 11,9 -11,9',
    pentagon:'0,-11 10.5,-3.4 6.5,8.9 -6.5,8.9 -10.5,-3.4',hexagon:'10,0 5,8.7 -5,8.7 -10,0 -5,-8.7 5,-8.7'};
  return `<polygon points="${points[shape]||points.diamond}" ${attributes}/>`;
}
export function learnedMap(data) {
  const map = data.track_map || {},
    points = map.points || [];
  const experimental = '<span class="map-experimental" title="Approximate driving line. Requires a complete continuous lap from start/finish; live accuracy is not yet verified.">Experimental</span>';
  if (map.status !== "ready" || points.length < 3)
    return `<div class="map-learning">${experimental}<div class="map-learning-symbol">◎</div><strong>${map.status === "learning" ? "Recording driving line" : "Waiting for a full lap"}</strong><p>${esc(map.message || "Cross start/finish, then drive one complete on-track lap.")}</p><div class="gauge"><i style="width:${Math.max(0, Math.min(100, (map.progress || 0) * 100))}%"></i></div><span>${n((map.progress || 0) * 100, 0)}% · ${map.source==='sdk-motion'?'SDK motion · approximate':'SDK GPS'}</span></div>`;
  const classes=[...new Map((data.drivers||[]).map(d=>{const marker=classMarker(d);return [marker.key,marker];})).values()].sort((a,b)=>a.name.localeCompare(b.name));
  const legend=`<div class="map-class-legend" data-element="classLegend">${classes.map(c=>`<span><svg viewBox="-13 -13 26 26" aria-hidden="true">${markerShape(c.shape,`fill="${c.color}"`)}</svg>${esc(c.name)}</span>`).join('')}</div>`;
  const xs = points.map((p) => p[0]),
    ys = points.map((p) => p[1]),
    minX = Math.min(...xs),
    minY = Math.min(...ys),
    scale = 480 / Math.max(Math.max(...xs) - minX, Math.max(...ys) - minY, 1);
  const project = (p) => [
      25 + (p[0] - minX) * scale,
      25 + (p[1] - minY) * scale,
    ],
    width = (Math.max(...xs) - minX) * scale + 50,
    height = (Math.max(...ys) - minY) * scale + 50;
  const pointAt = (pct) => {
    const at = (((pct % 1) + 1) % 1) * points.length,
      a = Math.floor(at),
      b = (a + 1) % points.length,
      t = at - a;
    return [
      points[a][0] * (1 - t) + points[b][0] * t,
      points[a][1] * (1 - t) + points[b][1] * t,
    ];
  };
  const line =
    points.map((p, i) => `${i ? "L" : "M"}${project(p).join(",")}`).join(" ") +
    " Z";
  const start = project(points[0]),
    next = project(points[1]),
    angle =
      (Math.atan2(next[1] - start[1], next[0] - start[0]) * 180) / Math.PI;
  return `<div class="learned-map-wrap">${experimental}<svg class="learned-map" viewBox="0 0 ${width} ${height}" role="img" aria-label="Driving line learned from local SDK telemetry"><path data-element="track" data-role="track" d="${line}" style="stroke:var(--c-track)"/><path data-element="start" data-role="start" transform="translate(${start}) rotate(${angle})" d="M0 -10V10" style="stroke:var(--c-start)"/>${[
    ...data.drivers,
  ]
    .filter((d) => Number.isFinite(d.pct) && d.pct >= 0 && d.surface!==-1)
    .sort((a, b) => Number(a.player) - Number(b.player))
    .map((d) => {
      const role = d.player ? "player" : d.pit ? "pitCar" : "rival",
        xy = project(pointAt(d.pct));
      const marker=classMarker(d);
      const label=`${d.number??''} · ${marker.name}${d.player?' · Your car':''}${d.pit?' · PIT':''}`;
      return `<g data-element="${role}" data-car-idx="${esc(d.id)}" data-class-key="${esc(marker.key)}" transform="translate(${xy})" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>${d.player?'<circle class="map-state-ring" r="14" data-role="player" style="fill:none;stroke:var(--c-player);stroke-width:2.5"/>':''}${d.pit?`<circle class="map-state-ring" data-element="pitCar" r="${d.player?18:13}" data-role="pitCar" style="fill:none;stroke:var(--c-pitCar);stroke-width:2.5;stroke-dasharray:3 2"/>`:''}${markerShape(marker.shape,`class="map-marker-body" data-map-marker="${marker.shape}" style="fill:${marker.color}"`)}<text data-element="carNumber" data-role="carNumber" style="fill:var(--c-map-number,${contrastColor(marker.color)})">${esc(d.number)}</text></g>`;
    })
    .join(
      "",
    )}</svg>${legend}<p class="learned-map-caption" data-element="caption" data-role="label">${esc(map.message)} · approximate car positions</p></div>`;
}
export function pitForm(preview = false) {
  const tire = (key, name) =>
    `<div class="tire-card"><label class="tire-option" data-role="selected"><input type="checkbox" name="${key}" aria-label="Change ${name.toLowerCase()} tire"><svg class="tire-drawing" viewBox="0 0 56 76" aria-hidden="true"><rect class="tire-rubber" x="9" y="3" width="38" height="70" rx="12"/><path class="tire-grooves" d="M20 7V69 M36 7V69 M11 17L20 22 M11 31L20 36 M11 45L20 50 M11 59L20 64 M36 22L45 17 M36 36L45 31 M36 50L45 45 M36 64L45 59"/></svg><span class="tire-name">${name}</span><span class="tire-state" aria-hidden="true"></span></label></div>`;
  const pressure = (key, name) =>
    `<label class="tire-pressure"><span>${name} · kPa</span><input type="number" name="${key}_pressure" min="70" max="500" step="1" placeholder="Keep current" aria-label="${name} pressure kPa"></label>`;
  const html = `<form class="pit-form ${preview ? "preview-pit" : ""}"><div class="pit-grid"><fieldset data-element="tires"><legend data-role="label">Tires to change</legend><div class="tire-grid">${tire("lf", "Left front")}${tire("rf", "Right front")}${tire("lr", "Left rear")}${tire("rr", "Right rear")}</div><div class="pit-row"><button type="button" class="button secondary" data-tires="all">All</button><button type="button" class="button secondary" data-tires="none">None</button></div><details class="pressure-settings" data-element="pressures"><summary>Tire pressures · kPa</summary><div class="pressure-grid">${pressure("lf", "Left front")}${pressure("rf", "Right front")}${pressure("lr", "Left rear")}${pressure("rr", "Right rear")}</div></details></fieldset><div class="pit-services"><label data-element="fuel" data-role="label">Fuel to add (liters)<input name="fuel" type="hidden" value="0"><output class="calculated-fuel" data-role="input">Waiting for a clean lap</output></label><section class="fuel-planner" data-element="fuelPlanner"><strong>Fuel calculator</strong><input type="hidden" name="fuel_target" value="finish"><div class="fuel-targets" role="group" aria-label="Fuel target"><button type="button" class="fuel-target" data-fuel-target="finish" aria-pressed="true"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M10 42V7M12 8C22 2 28 15 40 7V29C28 37 22 24 12 30" fill="none" stroke="currentColor" stroke-width="3"/><path d="M14 10h8v8h-8zm9 10h8v8h-8zm9-10h7v8h-7z" fill="currentColor"/></svg><strong>Race finish</strong><span>Fuel to the chequered flag</span></button><button type="button" class="fuel-target" data-fuel-target="stint" aria-pressed="false"><svg viewBox="0 0 48 48" aria-hidden="true"><rect x="7" y="9" width="23" height="31" rx="3" fill="none" stroke="currentColor" stroke-width="3"/><path d="M11 14H26V23H11ZM30 18L36 24V34Q36 39 41 36V16L36 11M5 41H33" fill="none" stroke="currentColor" stroke-width="3"/></svg><strong>Next stint</strong><span>Choose laps or minutes</span></button></div><div class="stint-length" hidden><input type="hidden" name="fuel_stint_unit" value="laps"><div class="stint-units" role="group" aria-label="Stint unit"><button type="button" data-stint-unit="laps" aria-pressed="true">Laps</button><button type="button" data-stint-unit="minutes" aria-pressed="false">Minutes</button></div><label>Stint length<input name="stint_length" type="number" min="1" max="1000" step="1" value="10"></label></div><div class="planner-fields"><label>Reserve · laps<input name="fuel_reserve" type="number" min="0" max="10" step="0.1" value="0.5"></label></div><p class="fuel-estimate" role="status" data-role="status"></p><button type="button" class="button secondary fuel-calculate">Calculate fuel</button></section><label data-element="compound" data-role="label">Compound<select name="compound"><option value="">Keep current</option></select></label><label class="check" data-element="windshield" data-role="selected"><input name="windshield" type="checkbox">Windshield / tear-off</label><label class="check" data-element="fast_repair" data-role="selected"><input name="fast_repair" type="checkbox">Fast repair</label></div></div><div class="pit-actions"><button class="button pit-apply" data-role="button" ${preview ? "disabled" : ""}>Apply pit plan</button></div><p class="pit-result" role="status" data-role="status"></p><div class="pit-readback" data-element="readback" data-role="status"></div></form>`;
  return html.replace(/<input\b[^>]*type="number"[^>]*>/g, input => {
    const name = input.match(/name="([^"]+)"/)?.[1];
    if (name === 'fuel') return input;
    const label = ({stint_length:'stint length',fuel_reserve:'reserve',fuel_consumption:'consumption'})[name] || name.replace('_pressure',' tire pressure').toUpperCase();
    return `<div class="pit-number-stepper"><button type="button" data-number-field="${name}" data-direction="-1" aria-label="Decrease ${label}">−</button>${input}<button type="button" data-number-field="${name}" data-direction="1" aria-label="Increase ${label}">+</button></div>`;
  });
}
export function pitReadback(pit) {
  if (!pit?.available) return "No pit-service data is available from the SDK.";
  const flags = pit.flags ?? 0,
    names = ["LF", "RF", "LR", "RR"];
  const status = {
    0: "Waiting",
    1: "Service in progress",
    2: "Service complete",
    100: "Too far left",
    101: "Too far right",
    102: "Too far forward",
    103: "Too far back",
    104: "Bad angle",
    105: "Cannot repair",
  };
  return `Tires: ${names.filter((_, i) => flags & (1 << i)).join(", ") || "none"} · fuel: ${flags & 16 ? n(pit.fuel, 0) + " L" : "no"} · windshield: ${flags & 32 ? "yes" : "no"} · fast repair: ${flags & 64 ? "yes" : "no"} · ${esc(status[pit.status] ?? "Unknown service status")} · compound: ${esc(pit.compounds?.find(c=>c.index===pit.compound)?.name ?? (pit.compound===null||pit.compound===undefined?"—":pit.compound))} · pressures: ${["lf","rf","lr","rr"].map(t=>t.toUpperCase()+" "+n(pit.pressures?.[t],0)).join(" / ")} kPa · fast repairs available: ${n(pit.fast_repairs,0)}`;
}
export function safetyColor(driver) {
  if (/^#[0-9a-f]{6}$/i.test(driver.license_color || '')) return driver.license_color;
  const license=(driver.license || '').toUpperCase().trim();
  if (license.startsWith('PRO') || license.startsWith('WC') || license.startsWith('P ')) return '#434851';
  return ({R:'#d43838',D:'#e57721',C:'#e4b925',B:'#269b4a',A:'#287be0'})[license[0]] || '#8c929f';
}
export function contrastColor(hex) {
  const channels=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
  return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722>.179?'#101216':'#ffffff';
}
function safetyBadge(driver) {
  const color=safetyColor(driver);
  const license=esc((driver.license || '').replace(/\s*[0-9]+\.[0-9]+\s*$/, ''));
  const value=typeof driver.safety_rating === 'number' ? license+' '+n(driver.safety_rating,2) : '—';
  return `<span class="safety-rating" data-role="safetyRating" data-element="safetyRating" style="color:var(--c-safetyTextOverride,${contrastColor(color)});border-color:var(--c-safetyOverride,${color});background:var(--c-safetyOverride,${color})">SR ${value}</span>`;
}
export function content(type, data) {
  if(type==='buttonbox')return buttonboxContent();
  if(EXPERIMENTAL_TYPES.includes(type))return experimentalContent(type);
  const c = data.car,
    s = data.session,
    f = data.fuel,
    ds = data.drivers;
  if (["standings", "relative"].includes(type)) return raceTable(type, data, safetyBadge);
  if (type === "inputs") return inputsView(data, speedReading);
  if (type === "tachometer")
    return `<div class="tachometer-panel"><div class="leds" data-element="leds">${Array.from({length:15}, () => '<i data-role="rpmOff" style="background:var(--c-rpmOff)"></i>').join("")}</div><div class="tach-readouts"><div class="big center" data-element="rpm">${colored("rpm", n(c.rpm,0))}<span class="unit" data-role="label">RPM</span></div><div class="big center" data-element="speed">${colored("speed", n(speedReading(c).value,0))}<span class="unit speed-unit" data-role="label">${speedReading(c).unit}</span></div></div><div class="divider" data-role="border"></div>${pitLimiterMarkup(c,s)}<div class="metrics tach-temperatures">${metric("Water",n(c.water)+" °C","water")}${metric("Oil",n(c.oil)+" °C","oil")}</div><div class="engine-alerts" data-element="engineWarnings"></div><div class="powertrain-status" data-element="powertrain"></div></div>`;
  if (type === "laps") return lapsView(data);
  if (type === "fuel") return fuelView(data);
  if (type === "systems") return systemsView(data);
  if (type === "radar")
    return `<div class="spotter"><i data-element="left" data-role="${[2, 4, 5].includes(c.left_right) ? "occupied" : "clear"}" style="background:var(--c-${[2, 4, 5].includes(c.left_right) ? "occupied" : "clear"})"></i>${colored("car", "▣", "span")}<i data-element="right" data-role="${[3, 4, 6].includes(c.left_right) ? "occupied" : "clear"}" style="background:var(--c-${[3, 4, 6].includes(c.left_right) ? "occupied" : "clear"})"></i></div><p class="center hint" data-element="hint" data-role="label">${esc(({0:'SPOTTER OFF',1:'CLEAR',2:'CAR LEFT',3:'CAR RIGHT',4:'BOTH SIDES',5:'TWO CARS LEFT',6:'TWO CARS RIGHT'})[c.left_right]||'Spotter unavailable')}</p>`;
  if (type === "learnedmap") return learnedMap(data);
  if (type === "inspector") return inspectorView(data);
  if (type === "pit") return pitForm();
  return "—";
}

// Keep the tachometer nodes alive so fast updates do not restart CSS blinking.
export function speedReading(car) {
  const unit = car.speed_unit === 'mph' ? 'mph' : 'km/h';
  return {unit, value:scaled(car.speed, unit === 'mph' ? 2.2369362920544 : 3.6)};
}
export function pitLimiterState(car, session = {}) {
  const known = Number.isFinite(session.pit_limit) && session.pit_limit > 0;
  const speed = speedReading({...car, speed: known ? session.pit_limit : null});
  const state = car.pit_limiter === true ? 'on' : car.pit_limiter === false ? 'off' : 'unknown';
  return {available: known && state !== 'unknown' && (car.pit === true || car.surface === 2), limit: speed.value, unit: speed.unit, state,
    label: state === 'on' ? 'LIMITER ON' : state === 'off' ? 'LIMITER OFF' : 'LIMITER —',
    speeding: !!(car.pit && known && Number.isFinite(car.speed) && car.speed > session.pit_limit)};
}
function pitLimiterMarkup(car, session) {
  const pit = pitLimiterState(car, session);
  return `<div class="pit-limiter" data-element="pitLimiter" data-state="${pit.state}" data-speeding="${pit.speeding}" data-available="${pit.available}"><div class="pit-limit-sign" role="group" aria-label="Pit lane speed limit"><strong class="pit-limit-number">${n(pit.limit,0)}</strong><span class="pit-limit-unit">${pit.unit}</span></div><div class="pit-limiter-caption"><span class="pit-limiter-title">PIT SPEED LIMIT</span><strong class="pit-limiter-status">${pit.label}</strong></div></div>`;
}
export function shiftState(car, count = 15) {
  const rpm = Number.isFinite(car.rpm) ? car.rpm : 0;
  const shift = car.shift_rpm > 0 ? car.shift_rpm : car.max_rpm > 0 ? car.max_rpm * .95 : null;
  const first = car.shift_first_rpm > 0 ? car.shift_first_rpm : shift ? shift * .65 : null;
  const last = car.shift_last_rpm > first ? car.shift_last_rpm : shift;
  const blink = car.blink_rpm > 0 ? car.blink_rpm : shift;
  return { lit: first && last > first ? Math.max(0, Math.min(count, Math.floor((rpm-first)/(last-first)*(count-1))+1)) : 0,
    flashing: !!(blink && rpm >= blink && car.gear > 0) };
}
export function updateTachometer(body, car, settings = {}, session = {}) {
  const panel = body.querySelector('.tachometer-panel');
  if (!panel) return;
  settings = shiftSettings(settings);
  const count = settings.style === 'dots' ? settings.dots : settings.segments;
  const leds = panel.querySelector('.leds');
  const signature = `${settings.style}/${count}`;
  if (leds.dataset.configuration !== signature) {
    leds.dataset.configuration = signature;
    leds.dataset.style = settings.style;
    leds.innerHTML = settings.style === 'bar' ? '<span class="rpm-fill"></span>' :
      Array.from({length:count}, () => '<i data-role="rpmOff"></i>').join('');
  }
  const state = shiftState(settings.blinkRpm ? {...car, blink_rpm:settings.blinkRpm} : car, count);
  panel.classList.toggle('shift-now', state.flashing);
  panel.style.setProperty('--shift-blink-duration', `${1/settings.hz}s`);
  panel.querySelector('[data-role="rpm"]').textContent = n(car.rpm, 0);
  const speed = speedReading(car);
  panel.querySelector('[data-role="speed"]').textContent = n(speed.value, 0);
  panel.querySelector('.speed-unit').textContent = speed.unit;
  panel.querySelector('[data-role="water"]').textContent = n(car.water) + ' °C';
  panel.querySelector('[data-role="oil"]').textContent = n(car.oil) + ' °C';
  panel.dataset.waterWarning = String(!!(car.engine_warnings & 1));
  panel.dataset.oilWarning = String(!!(car.engine_warnings & 0x40));
  panel.querySelector('.engine-alerts').textContent = engineWarnings(car.engine_warnings).join(' · ');
  const powertrain=[];
  if (car.replay) powertrain.push('REPLAY');
  else if (car.in_car===false) powertrain.push('NOT IN CAR');
  if (Number.isFinite(car.oil_pressure)) powertrain.push(`Oil ${n(car.oil_pressure,1)} bar`);
  if (Number.isFinite(car.fuel_pressure)) powertrain.push(`Fuel ${n(car.fuel_pressure,1)} bar`);
  if (Number.isFinite(car.voltage)) powertrain.push(`${n(car.voltage,1)} V`);
  if (Number.isFinite(car.drs_status) && car.drs_status>=0) powertrain.push(`DRS ${n(car.drs_status,0)}${Number.isFinite(car.drs_count)?' · '+n(car.drs_count,0)+' remaining':''}`);
  if (typeof car.p2p_active === 'boolean') powertrain.push(`P2P ${car.p2p_active?'ON':'OFF'}${Number.isFinite(car.p2p_count)?' · '+n(car.p2p_count,0):''}`);
  panel.querySelector('.powertrain-status').textContent = powertrain.join(' · ');
  const pit = pitLimiterState(car, session);
  const indicator = panel.querySelector('.pit-limiter');
  indicator.dataset.state = pit.state;
  indicator.dataset.available = String(pit.available);
  indicator.dataset.speeding = String(pit.speeding);
  indicator.querySelector('.pit-limit-number').textContent = n(pit.limit, 0);
  indicator.querySelector('.pit-limit-unit').textContent = pit.unit;
  indicator.querySelector('.pit-limiter-status').textContent = pit.label;
  if (settings.style === 'bar') {
    const maximum = car.shift_rpm > 0 ? car.shift_rpm : car.max_rpm > 0 ? car.max_rpm * .95 : null;
    const progress = maximum && Number.isFinite(car.rpm) ? Math.max(0, Math.min(1, car.rpm/maximum)) : 0;
    const fill = leds.querySelector('.rpm-fill');
    fill.style.width = `${progress * 100}%`;
    fill.style.background = `color-mix(in srgb, var(--c-rpmLow) ${(1-progress)*100}%, var(--c-rpmHigh))`;
  } else panel.querySelectorAll('.leds i').forEach((led, i) => {
    const role = state.flashing || i < state.lit ? i/count >= .8 ? 'rpmHigh' : i/count >= .53 ? 'rpmMid' : 'rpmLow' : 'rpmOff';
    if (led.dataset.role !== role || !led.style.background) {
      led.dataset.role = role;
      led.style.background = `var(--c-${role})`;
    }
  });
}

// Higher-priority race-control flags win when several SDK bits are set.
export function dashboardFlag(flags = 0) { return raceFlag(flags); }
