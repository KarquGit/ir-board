import { DEFAULT_LAYOUT } from "./default-layout.mjs";
import { alertSettings } from "./alerts.mjs";
import { referenceMode } from "./experimental.mjs";
import { THEMES, customTheme } from "./themes.mjs";
import { COUNTRY_CODES } from "./countries.mjs";
// Versioned, device-local layout. Positions are fractions of the canvas.
export const TYPES = {
  standings: "Standings",
  relative: "Relative",
  inputs: "Inputs and gear",
  tachometer: "Tachometer",
  laps: "Lap timing",
  fuel: "Fuel",
  systems: "Car systems",
  learnedmap: "Learned track map (Experimental)",
  irlogic: "iR-logic",
  radar: "Spotter",
  inspector: "SDK inspector",
  pit: "Pit stop",
};
export const BASE_COLORS = {
  background: ["Background", "#191c22"],
  text: ["Text / values", "#f1f3f7"],
  label: ["Labels", "#8c929f"],
  title: ["Title", "#b2b8c5"],
  border: ["Lines / borders", "#2a2e36"],
  accent: ["Accent", "#c3f35c"],
  positive: ["Gain / improvement", "#72df9b"],
  negative: ["Loss / error", "#ff747b"],
};
export const ELEMENT_COLORS = {
  tachometer: {
    rpm: ["RPM", "#f1f3f7"],
    speed: ["Speed", "#f1f3f7"],
    rpmLow: ["Low RPM LEDs", "#72df9b"],
    rpmMid: ["Mid RPM LEDs", "#f2c967"],
    rpmHigh: ["High RPM LEDs", "#ff747b"],
    rpmOff: ["Unlit LEDs", "#2a2f37"],
    water: ["Water temperature", "#f1f3f7"],
    oil: ["Oil temperature", "#f1f3f7"],
  },
  inputs: {
    gear: ["Gear", "#c3f35c"],
    speed: ["Speed", "#f1f3f7"],
    throttle: ["Throttle", "#72df9b"],
    brake: ["Brake", "#ff747b"],
    clutch: ["Clutch", "#7bb5ff"],
    pedalOff: ["Pedal background", "#2b3038"],
  },
  standings: {
    player: ["Your row", "#c3f35c"],
    position: ["Position", "#f1f3f7"],
    number: ["Car number", "#8c929f"],
    driver: ["Driver", "#f1f3f7"],
    class: ["Class", "#c3f35c"],
    carBrand: ["Car brand", "#b2b8c5"],
    timing: ["Times", "#f1f3f7"],
    irating: ["iRating", "#7bb5ff"],
    safetyRating: ["Safety Rating badge", "#72df9b"],
  },
  relative: {
    player: ["Your row", "#c3f35c"],
    position: ["Position", "#f1f3f7"],
    number: ["Car number", "#8c929f"],
    driver: ["Driver", "#f1f3f7"],
    class: ["Class", "#c3f35c"],
    carBrand: ["Car brand", "#b2b8c5"],
    timing: ["Gap", "#f1f3f7"],
    irating: ["iRating", "#7bb5ff"],
    safetyRating: ["Safety Rating badge", "#72df9b"],
  },
  laps: {
    current: ["Current lap time", "#f1f3f7"],
    best: ["Best lap", "#bc9cff"],
    last: ["Last lap", "#f1f3f7"],
    history: ["History", "#f1f3f7"],
  },
  fuel: {
    gauge: ["Fuel cylinder", "#72df9b"],
    level: ["Fuel level", "#c3f35c"],
    average: ["Average consumption", "#f1f3f7"],
    remaining: ["Laps", "#f1f3f7"],
    last: ["Last consumption", "#f1f3f7"],
    needed: ["Fuel to add", "#f2c967"],
  },
  systems: {
    bias: ["Brake bias", "#f1f3f7"],
    abs: ["ABS", "#f1f3f7"],
    tc: ["TC", "#f1f3f7"],
    engine: ["Engine map", "#f1f3f7"],
  },
  learnedmap: {
    track: ["Driving line", "#737d8e"],
    start: ["Start / finish", "#f1f3f7"],
    player: ["Your car outline", "#c3f35c"],
    rival: ["Other cars", "#8e96a7"],
    pitCar: ["PIT outline", "#f2c967"],
    carNumber: ["Car numbers", "#101216"],
  },
  radar: {
    clear: ["Clear side", "#2a2f37"],
    occupied: ["Car alongside", "#f2c967"],
    car: ["Your car", "#8e96a7"],
  },
  irlogic:{reference:['Reference time','#f2c967'],predicted:['Predicted time','#f2c967']},
  inspector: {
    key: ["Variable name", "#8c929f"],
    value: ["Value", "#f1f3f7"],
  },
  pit: {
    selected: ["Selected service", "#c3f35c"],
    button: ["Apply button", "#c3f35c"],
    buttonText: ["Button text", "#162006"],
    input: ["Fields / values", "#f1f3f7"],
    status: ["Service status", "#7bb5ff"],
  },
};

// Templates are preferred arrangements, never limits on widget counts.
export const LAYOUTS = {
  auto: { name: "Automatic", slots: 0 },
  full: { name: "Single panel", slots: 1, columns: 1 },
  "top-bottom": { name: "Top / bottom", slots: 2, columns: 1, rows: 2 },
  "left-right": { name: "Left / right", slots: 2, columns: 2, rows: 1 },
  "left-right-bottom": {
    name: "Two above + wide bottom",
    slots: 3,
    columns: 2,
  },
  "left-right-top": { name: "Wide top + two below", slots: 3, columns: 2 },
  "grid-2x2": { name: "Grid 2 × 2", slots: 4, columns: 2, rows: 2 },
  "grid-3x2": { name: "Grid 3 × 2", slots: 6, columns: 3, rows: 2 },
  "grid-3x3": { name: "Grid 3 × 3", slots: 9, columns: 3, rows: 3 },
  "grid-4x3": { name: "Compact 4 × 3", slots: 12, columns: 4, rows: 3 },
  "grid-4x4": { name: "Compact 4 × 4", slots: 16, columns: 4, rows: 4 },
  "main-left": { name: "Main panel + four tiles", slots: 5, columns: 3 },
  "main-top": { name: "Wide top + three tiles", slots: 4, columns: 3 },
  "two-top-four-bottom": { name: "Two top + four tiles", slots: 6, columns: 4 },
};
export const templateSlots = (p) => LAYOUTS[p.preset]?.slots || 0;
export const ELEMENTS = {
  irlogic:{delta:'Lap delta',gauge:'Delta bar',predicted:'Predicted lap',reference:'Reference time',sectors:'Automatic sector carousel'},
  learnedmap: {
    track: "Driving line",
    start: "Start / finish",
    player: "Your car",
    rival: "Other cars",
    pitCar: "Cars in pit",
    carNumber: "Car numbers",
    caption: "Map status",
    classLegend: "Class color and shape legend",
  },

  tachometer: {
    leds: "Shift LEDs",
    rpm: "RPM readout",
    speed: "Speed readout",
    pitLimiter: "Pit speed limit / limiter status",
    water: "Water temperature",
    oil: "Oil temperature",
  },
  inputs: {
    gear: "Gear",
    speed: "Speed",
    throttle: "Throttle pedal",
    brake: "Brake pedal",
    clutch: "Clutch pedal",
  },
  standings: {
    position: "Position column",
    number: "Car number column",
    driver: "Driver name",
    class: "Car class",
    timing: "Last lap column",
    flag: "Country flag",
    carBrand: "Car brand",
    irating: "iRating",
    safetyRating: "Safety Rating",
  },
  relative: {
    position: "Position column",
    number: "Car number column",
    driver: "Driver name",
    class: "Car class",
    timing: "Gap column",
    flag: "Country flag",
    carBrand: "Car brand",
    irating: "iRating",
    safetyRating: "Safety Rating",
  },
  laps: {
    current: "Current lap",
    delta: "Lap delta",
    best: "Best lap",
    last: "Last lap",
    history: "Lap history",
  },
  fuel: {
    gauge: "Fuel cylinder",
    level: "Fuel level",
    average: "Average consumption",
    remaining: "Laps remaining",
    last: "Last consumption",
    needed: "Fuel to finish",
    hint: "Estimate note",
  },
  systems: {
    bias: "Brake bias",
    abs: "ABS",
    tc: "Traction control",
    engine: "Engine map",
  },
  radar: {
    left: "Left indicator",
    car: "Your car",
    right: "Right indicator",
    hint: "Spotter note",
  },
  inspector: { key: "Variable names", value: "Values" },
  pit: {
    tires: "Tire selection",
    pressures: "Tire pressures",
    fuel: "Fuel controls",
    compound: "Compound selector",
    fuelPlanner: "Fuel calculator",
    windshield: "Windshield service",
    fast_repair: "Fast repair",
    readback: "Current pit plan",
  },
};
const raceElements = {
  classPosition:'Class position', positionChange:'Positions gained / lost', team:'Team name',
  pitStatus:'PIT / out-lap status', pitHistory:'Previous pit stop and duration',
  lapped:'Lapped opponents', lapping:'Opponents lapping you', status:'Penalties and track status',
  radio:'Radio transmission', compound:'Tire compound', pushToPass:'Push-to-pass',
  lapCount:'Completed laps', stint:'Stint lap', iratingChange:'Estimated iRating change',
  lastTime:'Last lap detail', bestTime:'Best lap', gap:'Gap to class leader', interval:'Class interval',
  averageLap:'Average observed lap', lapDeltas:'Recent lap deltas',
};
for (const type of ['standings','relative']) {
  Object.assign(ELEMENTS[type],raceElements);
  if (type==='relative') for (const key of ['lastTime','bestTime','gap','interval','averageLap','lapDeltas']) delete ELEMENTS[type][key];
  Object.assign(ELEMENT_COLORS[type],{
    lapped:['Lapped opponent','#7bb5ff'], lapping:['Lapping opponent','#ff747b'],
    pitStatus:['PIT status','#f2c967'], status:['Race status','#f2c967'], radio:['Radio','#72df9b'],
    compound:['Tire compound','#bc9cff'], team:['Team name','#8c929f'],
    iratingChange:['Estimated iRating change','#b2b8c5'],
  });
}
Object.assign(ELEMENTS.inputs,{trace:'Recent input trace'});
Object.assign(ELEMENTS.laps,{references:'Best / optimal / previous-lap deltas',predicted:'Predicted lap',recordedBest:'Local recorded personal best'});
Object.assign(ELEMENTS.fuel,{minimum:'Minimum measured consumption',maximum:'Maximum measured consumption',
  fuelTime:'Estimated driving time',capacity:'Tank capacity',flow:'Instantaneous consumption'});
Object.assign(ELEMENTS.tachometer,{engineWarnings:'Engine warnings',powertrain:'Pressure, voltage, DRS and P2P'});
for (const [key,label] of Object.entries({tc2:'Traction control 2',throttleShape:'Throttle shape',mixture:'Fuel mixture',
 brakeFine:'Brake fine adjustment',brakeMisc:'Brake adjustment',peakBrake:'Peak brake setting',antiRollFront:'Front anti-roll',
 antiRollRear:'Rear anti-roll',weightJacker:'Weight jacker',diffEntry:'Differential entry',diffMiddle:'Differential middle',
 diffExit:'Differential exit',deployment:'Hybrid deployment',regeneration:'Hybrid regeneration'})) ELEMENTS.systems[key]=label;
export const visibilityElements = (type) => ({
  title: "Widget title",
  labels: "Labels",
  ...ELEMENTS[type],
});

export const colorRoles = (type) => ({
  ...BASE_COLORS,
  ...ELEMENT_COLORS[type],
});
export const validColor = (v) =>
  typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v);
export function uid() {
  return (
    globalThis.crypto?.randomUUID?.() ||
    `rd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  );
}
export const shiftSettings = (value = {}) => ({
  style: ['segments', 'dots', 'bar'].includes(value?.style) ? value.style : 'segments',
  segments: Number.isInteger(value?.segments) && value.segments >= 4 && value.segments <= 40 ? value.segments : 15,
  dots: Number.isInteger(value?.dots) && value.dots >= 4 && value.dots <= 40 ? value.dots : 15,
  hz: [6, 8, 10].includes(Number(value?.hz)) ? Number(value.hz) : 8,
  blinkRpm: Number.isFinite(value?.blinkRpm) && value.blinkRpm >= 500 && value.blinkRpm <= 30000 ? value.blinkRpm : null,
});
export function widget(type) {
  return {
    id: uid(),
    type,
    title: TYPES[type],
    colors: {},
    hidden: type==='standings'?['carBrand','lapCount','stint','iratingChange','bestTime','interval','averageLap','lapDeltas']:[],
    layouts: {},
    shiftLights: shiftSettings(),
    ...(type==='irlogic'?{coachReference:'session'}:{}),
  };
}
export function defaults() {
  return migrate(DEFAULT_LAYOUT);
}
export function validRect(r) {
  return (
    r &&
    ["x", "y", "w", "h"].every((k) => Number.isFinite(r[k])) &&
    r.x >= 0 &&
    r.y >= 0 &&
    r.w > 0 &&
    r.h > 0 &&
    r.x + r.w <= 1.001 &&
    r.y + r.h <= 1.001
  );
}
const LEGACY_TITLES = {
  standings: "Klasyfikacja",
  relative: "Relative",
  inputs: "Peda\u0142y i bieg",
  tachometer: "Obrotomierz",
  laps: "Czasy okr\u0105\u017ce\u0144",
  fuel: "Paliwo",
  systems: "Systemy auta",
  map: "Pe\u0142na mapa toru",
  radar: "Spotter",
  inspector: "Telemetria SDK",
  pit: "Pit stop",
};
const LEGACY_PAGES = {
  Obrotomierz: "Tachometer",
  "Wy\u015bcig": "Race",
  Jazda: "Driving",
  Strategia: "Strategy",
  "Mapa toru": "Track map",
  Warunki: "Conditions",
  Telemetria: "Telemetry",
};
export function migrate(raw) {
  if (
    !raw ||
    !Array.isArray(raw.pages) ||
    !raw.pages.length ||
    raw.pages.length > 100
  )
    throw Error("Invalid pages");
  const pages = [];
  let active = 0;
  raw.pages.forEach((p, index) => {
    if (typeof p.name !== "string" || !Array.isArray(p.widgets))
      throw Error("Invalid widgets");
    if (index === raw.active) active = pages.length;
    const clean = p.widgets.filter(w => !w || !['weather','flag','trace','navigator','brakecoach'].includes(w.type)).map((w) => {
      if (!w) throw Error("Unknown widget");
      const replaced = ["map", "flatmap"].includes(w.type);
      if (replaced)
        w = {
          ...w,
          type: "learnedmap",
          title:
            !w.title || w.title === LEGACY_TITLES.map || w.title === "Track map" || w.title === "Flat map"
              ? TYPES.learnedmap
              : w.title,
        };
      if (!Object.hasOwn(TYPES, w.type)) throw Error("Unknown widget");
      const colors = {};
      for (const k of Object.keys(colorRoles(w.type)))
        if (validColor(w.colors?.[k])) colors[k] = w.colors[k];
      const layouts = {};
      for (const o of ["portrait", "landscape"])
        if (validRect(w.layouts?.[o])) layouts[o] = { ...w.layouts[o] };
      return {
        ...widget(w.type),
        title:
          typeof w.title === "string" && w.title !== LEGACY_TITLES[w.type] && !(w.type === "irlogic" && w.title === "iR-logic (Experimental)") && !(w.type === "learnedmap" && w.title === "Learned track map")
            ? w.title.slice(0, 80)
            : TYPES[w.type],
        hidden: Array.isArray(w.hidden)
          ? w.hidden.filter((k) => Object.hasOwn(visibilityElements(w.type), k))
          : widget(w.type).hidden,
        colors,
        layouts,
        shiftLights: shiftSettings(w.shiftLights),
        ...(w.type==='irlogic'?{coachReference:referenceMode(w.coachReference)}:{}),
      };
    });
    const preset = Object.hasOwn(LAYOUTS, p.preset) ? p.preset : "auto";
    const name = Object.hasOwn(LEGACY_PAGES, p.name)
      ? LEGACY_PAGES[p.name]
      : p.name.replace(/^Strona (?=\d)/, "Page ");
    pages.push({
      name: (name === "Track map" ? "Track progress" : name).slice(0, 80),
      preset,
      widgets: clean,
    });
  });
  const driverCountries = {};
  for (const [id, code] of Object.entries(raw.driverCountries || {}))
    if (/^[0-9]{1,12}$/.test(id) && COUNTRY_CODES.has(code)) driverCountries[id] = code;
  return { version: 4, pages, active: Math.min(active, pages.length - 1),
    theme: raw.theme === 'custom' || Object.hasOwn(THEMES,raw.theme) ? raw.theme : 'original', customTheme:customTheme(raw.customTheme), driverCountries,
    alerts:alertSettings(raw.alerts) };
}
function gridRect(index, columns, rows) {
  const gap = Math.min(0.01, 0.06 / columns, 0.06 / rows),
    w = (1 - gap * (columns - 1)) / columns,
    h = (1 - gap * (rows - 1)) / rows;
  return {
    x: (index % columns) * (w + gap),
    y: Math.floor(index / columns) * (h + gap),
    w,
    h,
  };
}
export function defaultRect(index, count, orientation, preset = "auto") {
  const total = Math.max(1, count),
    spec = LAYOUTS[preset] || LAYOUTS.auto;
  const mode =
    preset === "auto"
      ? total === 1
        ? "full"
        : total === 2
          ? orientation === "landscape"
            ? "left-right"
            : "top-bottom"
          : total === 3
            ? "left-right-bottom"
            : "grid"
      : preset;
  const h = 0.495,
    o = 0.505;
  const fixed = {
    full: [{ x: 0, y: 0, w: 1, h: 1 }],
    "left-right": [
      { x: 0, y: 0, w: h, h: 1 },
      { x: o, y: 0, w: h, h: 1 },
    ],
    "top-bottom": [
      { x: 0, y: 0, w: 1, h },
      { x: 0, y: o, w: 1, h },
    ],
    "left-right-bottom": [
      { x: 0, y: 0, w: h, h },
      { x: o, y: 0, w: h, h },
      { x: 0, y: o, w: 1, h },
    ],
    "left-right-top": [
      { x: 0, y: 0, w: 1, h },
      { x: 0, y: o, w: h, h },
      { x: o, y: o, w: h, h },
    ],
    "main-left": [
      { x: 0, y: 0, w: 0.59, h: 1 },
      { x: 0.6, y: 0, w: 0.195, h },
      { x: 0.805, y: 0, w: 0.195, h },
      { x: 0.6, y: o, w: 0.195, h },
      { x: 0.805, y: o, w: 0.195, h },
    ],
    "main-top": [
      { x: 0, y: 0, w: 1, h },
      ...Array.from({ length: 3 }, (_, i) => ({
        x: i * 0.337,
        y: o,
        w: 0.326,
        h,
      })),
    ],
    "two-top-four-bottom": [
      { x: 0, y: 0, w: h, h },
      { x: o, y: 0, w: h, h },
      ...Array.from({ length: 4 }, (_, i) => ({
        x: i * 0.2525,
        y: o,
        w: 0.2425,
        h,
      })),
    ],
  };
  if (fixed[mode] && total <= fixed[mode].length)
    return { ...fixed[mode][index] };
  const columns =
    spec.columns ||
    Math.max(
      1,
      Math.ceil(Math.sqrt(total * (orientation === "landscape" ? 1.5 : 0.7))),
    );
  return gridRect(
    index,
    columns,
    Math.max(spec.rows || 1, Math.ceil(total / columns)),
  );
}
export function setPreset(state, index, preset) {
  if (!Object.hasOwn(LAYOUTS, preset)) throw Error("Unknown page layout");
  const p = state.pages[index];
  p.preset = preset;
  p.widgets.forEach((w) => (w.layouts = {}));
}
// Snap all moving edges/centers to canvas, grid and nearby widgets, in CSS pixels.
export function snapRect(
  rect,
  others,
  width,
  height,
  { edge = "move", disabled = false, threshold = 7 } = {},
) {
  if (disabled) return { rect: { ...rect }, guides: [] };
  const xs = Array.from({ length: 13 }, (_, i) => ({
    value: i / 12,
    source: "grid",
  }));
  const ys = Array.from({ length: 13 }, (_, i) => ({
    value: i / 12,
    source: "grid",
  }));
  for (const r of others) {
    for (const v of [r.x, r.x + r.w / 2, r.x + r.w])
      xs.push({ value: v, source: "widget" });
    for (const v of [r.y, r.y + r.h / 2, r.y + r.h])
      ys.push({ value: v, source: "widget" });
  }
  const result = { ...rect },
    guides = [];
  function closest(axis, targets, size) {
    const pos = axis === "x" ? rect.x : rect.y,
      span = axis === "x" ? rect.w : rect.h;
    const anchors =
      edge === "move"
        ? [pos, pos + span / 2, pos + span]
        : [edge.includes(axis === "x" ? "w" : "n") ? pos : pos + span];
    let best = null;
    for (const target of targets)
      for (const anchor of anchors) {
        const delta = target.value - anchor,
          dist = Math.abs(delta) * size;
        if (
          dist <= threshold &&
          (!best ||
            dist < best.dist - 1e-6 ||
            (Math.abs(dist - best.dist) < 1e-6 && target.source === "widget"))
        )
          best = { delta, dist, value: target.value };
      }
    return best;
  }
  for (const [axis, targets, size, low, high] of [
    ["x", xs, width, "w", "e"],
    ["y", ys, height, "n", "s"],
  ]) {
    if (edge !== "move" && !edge.includes(low) && !edge.includes(high))
      continue;
    const hit = closest(axis, targets, size);
    if (!hit) continue;
    const span = axis === "x" ? "w" : "h";
    if (edge === "move") {
      const next = result[axis] + hit.delta;
      if (next < 0 || next + result[span] > 1) continue;
      result[axis] = next;
    } else if (edge.includes(low)) {
      if (result[span] - hit.delta <= 0 || result[axis] + hit.delta < 0)
        continue;
      result[axis] += hit.delta;
      result[span] -= hit.delta;
    } else {
      if (
        result[span] + hit.delta <= 0 ||
        result[axis] + result[span] + hit.delta > 1
      )
        continue;
      result[span] += hit.delta;
    }
    guides.push({ axis, value: hit.value });
  }
  return { rect: result, guides };
}
export const overlap = (a, b) =>
  a.x < b.x + b.w - 0.002 &&
  a.x + a.w > b.x + 0.002 &&
  a.y < b.y + b.h - 0.002 &&
  a.y + a.h > b.y + 0.002;
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export function resizeRect(r, edge, dx, dy, minW = 0.2, minH = 0.2) {
  let x = r.x,
    y = r.y,
    right = x + r.w,
    bottom = y + r.h;
  if (edge.includes("w")) x = clamp(x + dx, 0, right - minW);
  if (edge.includes("e")) right = clamp(right + dx, x + minW, 1);
  if (edge.includes("n")) y = clamp(y + dy, 0, bottom - minH);
  if (edge.includes("s")) bottom = clamp(bottom + dy, y + minH, 1);
  return { x, y, w: right - x, h: bottom - y };
}
