import test from "node:test";
import assert from "node:assert/strict";
import {
  TYPES,
  LAYOUTS,
  migrate,
  defaultRect,
  resizeRect,
  overlap,
  validRect,
  defaults,
  widget,
  setPreset,
  snapRect,
} from "../irboard/static/model.mjs";

test("legacy maps convert to learned maps with safe appearance settings", () => {
  const state = migrate({
    pages: [
      {
        name: "Track map",
        widgets: [
          {
            type: "map",
            title: "Track map",
            colors: { track: "#123456", player: "url(x)" },
            hidden: ["player", "start"],
          },
        ],
      },
    ],
  });
  assert.equal(state.pages[0].widgets[0].type, "learnedmap");
  assert.equal(state.pages[0].widgets[0].title, "Learned track map (Experimental)");
  assert.equal(state.pages[0].name, "Track progress");
  assert.equal(state.pages[0].widgets[0].colors.track, "#123456");
  assert.equal(state.pages[0].widgets[0].colors.player, undefined);
  assert.deepEqual(state.pages[0].widgets[0].hidden, ["player", "start"]);
  assert.equal(Object.hasOwn(TYPES, "map"), false);
});
test("no widget count limit or automatic pagination during migration and template changes", () => {
  const state = migrate({
    version: 3,
    active: 0,
    pages: [
      {
        name: "Large page",
        preset: "full",
        widgets: Array.from({ length: 120 }, () => widget("tachometer")),
      },
    ],
  });
  assert.equal(state.pages.length, 1);
  assert.equal(state.pages[0].widgets.length, 120);
  setPreset(state, 0, "grid-4x4");
  assert.equal(state.pages.length, 1);
  assert.equal(state.pages[0].widgets.length, 120);
  const restored = migrate(JSON.parse(JSON.stringify(state)));
  assert.equal(restored.pages[0].widgets.length, 120);
});
test("all templates expand to dense grids in bounds without overlap", () => {
  for (const preset of Object.keys(LAYOUTS))
    for (const axis of ["portrait", "landscape"])
      for (const count of [1, 2, 3, 5, 9, 16, 25, 60]) {
        const total = Math.max(count, LAYOUTS[preset].slots || 0),
          rects = Array.from({ length: total }, (_, i) =>
            defaultRect(i, total, axis, preset),
          );
        assert.ok(rects.every(validRect), preset + " " + count);
        for (let i = 0; i < rects.length; i++)
          for (let j = i + 1; j < rects.length; j++)
            assert.equal(
              overlap(rects[i], rects[j]),
              false,
              preset + " " + count,
            );
      }
});
test("every edge and corner resizes within the canvas", () => {
  const r = { x: 0.2, y: 0.2, w: 0.5, h: 0.5 };
  for (const edge of ["n", "ne", "e", "se", "s", "sw", "w", "nw"])
    for (const delta of [-5, -0.1, 0.1, 5])
      assert.ok(validRect(resizeRect(r, edge, delta, delta)));
});
test("snapping aligns grid, widget edges and centers with actual guide coordinates", () => {
  let result = snapRect({ x: 0.244, y: 0.203, w: 0.2, h: 0.2 }, [], 1000, 600);
  assert.ok(Math.abs(result.rect.x - 0.25) < 1e-9);
  assert.ok(result.guides.some((g) => g.axis === "x" && g.value === 0.25));
  result = snapRect(
    { x: 0.344, y: 0.2, w: 0.2, h: 0.2 },
    [{ x: 0.55, y: 0.4, w: 0.2, h: 0.2 }],
    1000,
    600,
  );
  assert.ok(Math.abs(result.rect.x + 0.2 - 0.55) < 1e-9);
  assert.ok(result.guides.some((g) => g.value === 0.55));
  const raw = { x: 0.244, y: 0.203, w: 0.2, h: 0.2 };
  assert.deepEqual(snapRect(raw, [], 1000, 600, { disabled: true }), {
    rect: raw,
    guides: [],
  });
});
test("resize snapping only changes the dragged edge and stays valid", () => {
  const r = { x: 0.1, y: 0.1, w: 0.395, h: 0.4 },
    snapped = snapRect(r, [], 1000, 600, { edge: "e" });
  assert.ok(Math.abs(snapped.rect.w - 0.4) < 1e-9);
  assert.equal(snapped.rect.x, r.x);
  assert.equal(snapped.rect.h, r.h);
  assert.ok(validRect(snapped.rect));
});
test("visibility and custom names survive export and defaults remain available", () => {
  const state = migrate({
    pages: [
      {
        name: "Obrotomierz",
        widgets: [
          {
            type: "tachometer",
            title: "Obrotomierz",
            hidden: ["water", "oil", "bad"],
          },
          { type: "inputs", title: "My inputs" },
        ],
      },
    ],
  });
  assert.equal(state.pages[0].name, "Tachometer");
  assert.equal(state.pages[0].widgets[0].title, "Tachometer");
  assert.equal(state.pages[0].widgets[1].title, "My inputs");
  assert.deepEqual(state.pages[0].widgets[0].hidden, ["water", "oil"]);
  assert.ok(
    defaults().pages.some((p) => p.widgets.some((w) => w.type === "pit")),
  );
});
test("custom names cannot resolve inherited migration object properties", () => {
  const s = migrate({
    version: 4,
    pages: [{ name: "__proto__", widgets: [widget("inputs")] }],
  });
  assert.equal(s.pages[0].name, "__proto__");
  assert.throws(() =>
    migrate({ pages: [{ name: "Test", widgets: [{ type: "__proto__" }] }] }),
  );
});

test("shift LEDs use the current car limits and flash only in a forward gear", async () => {
  const {shiftState} = await import('../irboard/static/widgets.mjs');
  const car = {rpm:14000,max_rpm:15000,shift_first_rpm:10000,shift_last_rpm:13500,blink_rpm:14000,gear:4};
  assert.deepEqual(shiftState(car),{lit:15,flashing:true});
  assert.equal(shiftState({...car,rpm:13999}).flashing,false);
  assert.equal(shiftState({...car,gear:0}).flashing,false);
  assert.equal(shiftState({...car,gear:-1}).flashing,false);
  assert.deepEqual(shiftState({...car,rpm:9000}),{lit:0,flashing:false});
  assert.deepEqual(shiftState({rpm:9000,gear:3}),{lit:0,flashing:false});
  assert.equal(shiftState({rpm:5700,max_rpm:6000,gear:3}).flashing,true);
});

test('fuel calculator subtracts existing fuel, rounds up and obeys tank restrictions', async () => {
  const {fuelEstimate} = await import('../irboard/static/fuel.mjs');
  const d={car:{fuel:5,lap_pct:.25,last_lap:100},fuel:{average:2},pit:{fuel_max:50},session:{type:'Race',laps_remaining:10,remaining:2000,state:4},history:[]};
  assert.equal(fuelEstimate(d).add,16); // (9.75 + 0.5) * 2 - 5 = 15.5
  assert.equal(fuelEstimate(d,{target:'laps',amount:10,reserve:0}).add,15);
  assert.equal(fuelEstimate(d,{target:'minutes',amount:10,reserve:0}).add,7);
  const limited=fuelEstimate({...d,pit:{fuel_max:12}});
  assert.equal(limited.add,7); assert.equal(limited.limited,true);
  assert.equal(fuelEstimate({...d,car:{...d.car,fuel:40}}).add,0);
  assert.equal(fuelEstimate({...d,fuel:{}}).available,false);
  assert.equal(fuelEstimate({...d,fuel:{}},{consumption:3}).available,false);
  assert.equal(fuelEstimate({...d,session:{type:'Practice'}}).available,false);
  assert.equal(fuelEstimate({...d,session:{type:'Race',laps_remaining:32767,remaining:600,state:4}}).laps,7);
  assert.equal(fuelEstimate({...d,session:{...d.session,state:5}}).add,16);
  assert.equal(fuelEstimate({...d,car:{...d.car,finished:true},session:{...d.session,state:5}}).add,0);
  assert.equal(fuelEstimate({...d,session:{...d.session,state:6}}).add,0);
  assert.equal(fuelEstimate(d,{target:'laps',amount:-1}).available,false);
});

test('shift blink settings survive migration and reject unsupported speeds', async () => {
  const {shiftSettings} = await import('../irboard/static/model.mjs');
  const settings={style:'dots',segments:24,dots:12,hz:10,blinkRpm:6500};
  const state=migrate({pages:[{name:'RPM',widgets:[{type:'tachometer',shiftLights:settings}]}]});
  assert.deepEqual(state.pages[0].widgets[0].shiftLights,settings);
  assert.deepEqual(migrate(state).pages[0].widgets[0].shiftLights,settings);
  assert.equal(shiftSettings({hz:100}).hz,8);
  assert.equal(shiftSettings(null).hz,8);
});

test('thirty themes and member countries persist without changing custom widget colors', async () => {
  const {THEMES,themeColor,activeTheme}=await import('../irboard/static/themes.mjs');
  assert.equal(Object.keys(THEMES).length,30);
  assert.equal(migrate({pages:[{name:'Page',widgets:[]}]}).theme,'original');
  const state=migrate({theme:'blue',driverCountries:{'123':'PL','456':'ZZ','__proto__':'DE'},pages:[{name:'Page',widgets:[{type:'standings',colors:{driver:'#ff00aa'},hidden:['flag','safetyRating']}]}]});
  assert.equal(state.theme,'blue');
  assert.deepEqual(state.driverCountries,{'123':'PL'});
  assert.equal(state.pages[0].widgets[0].colors.driver,'#ff00aa');
  assert.deepEqual(migrate(state).pages[0].widgets[0].hidden,['flag','safetyRating']);
  assert.equal(themeColor(activeTheme('blue'),'accent','#c3f35c'),'#52adff');
  assert.equal(migrate({...state,theme:'__proto__'}).theme,'original');
});

test('standings and relative render separate ratings and local fallback flags', async () => {
  const {content}=await import('../irboard/static/widgets.mjs');
  const data={car:{},session:{},fuel:{},drivers:[{name:'Example',pct:.25,country:'PL',rating:2500,license:'A 3.42',safety_rating:3.42}]};
  for (const type of ['standings','relative']) {
    const markup=content(type,data);
    assert.ok(markup.includes('/flags/pl.svg'));
    assert.ok(markup.includes('data-element="irating"'));
    assert.ok(markup.includes('SR A 3.42'));
    assert.ok(content(type,{...data,drivers:[{name:'Unknown',pct:.25}]}).includes('/flags/iracing.svg'));
  }
});

test('license colors and text contrast are correct and iRating defaults to blue', async () => {
  const {safetyColor,contrastColor}=await import('../irboard/static/widgets.mjs');
  const {colorRoles}=await import('../irboard/static/model.mjs');
  assert.equal(colorRoles('standings').irating[1],'#7bb5ff');
  assert.equal(colorRoles('relative').irating[1],'#7bb5ff');
  assert.equal(safetyColor({license:'A 3.42',license_color:'#0153db'}),'#0153db');
  assert.equal(safetyColor({license:'R 2.50'}),'#d43838');
  assert.equal(safetyColor({license:'C 3.10'}),'#e4b925');
  assert.equal(safetyColor({license:'Pro 4.99'}),'#434851');
  assert.equal(contrastColor('#ffffff'),'#101216');
  assert.equal(contrastColor('#000000'),'#ffffff');
});

test('PIT has calculated fuel only and driver rows expose a separately hideable car brand', async () => {
  const {pitForm,content}=await import('../irboard/static/widgets.mjs');
  const html=pitForm();
  assert.ok(html.includes('name="fuel" type="hidden"'));
  assert.ok(!html.includes('name="fuel_consumption"'));
  assert.ok(!html.includes('data-step='));
  for (const type of ['standings','relative']) {
    const markup=content(type,{car:{},session:{},fuel:{},drivers:[{name:'Driver',pct:.25,car_brand:'Mercedes-Benz'}]});
    assert.ok(markup.includes('data-element="carBrand"'));
    assert.ok(markup.includes('Mercedes-Benz'));
  }
});


test('removed widgets migrate safely and remaining widgets keep their appearance', () => {
  const state=migrate({pages:[{name:'Old',widgets:[{type:'weather'},{type:'flag'},{type:'trace'},{type:'flatmap'}, {type:'systems',colors:{bias:'#123456'}}]}]});
  assert.deepEqual(state.pages[0].widgets.map(w=>w.type),['learnedmap','systems']);
  for (const type of ['weather','flag','trace','flatmap']) assert.equal(Object.hasOwn(TYPES,type),false);
  assert.equal(state.pages[0].widgets[1].colors.bias,'#123456');
});

test('custom theme is sanitized and survives export/import', async () => {
  const {customTheme,activeTheme}=await import('../irboard/static/themes.mjs');
  const state=migrate({theme:'custom',customTheme:{bg:'#010203',accent:'#abcdef',text:'url(x)',light:true},pages:[{name:'Custom',widgets:[]}]});
  const restored=migrate(JSON.parse(JSON.stringify(state)));
  assert.equal(restored.theme,'custom');
  assert.equal(restored.customTheme.bg,'#010203');
  assert.equal(activeTheme('custom',restored.customTheme).accent,'#abcdef');
  assert.equal(restored.customTheme.light,true);
  assert.equal(customTheme({text:'url(x)'}).text,'#f1f3f7');
});

test('SDK speed units, configurable LED counts and flag priorities', async () => {
  const {speedReading,shiftState,dashboardFlag}=await import('../irboard/static/widgets.mjs');
  assert.equal(speedReading({speed:10,speed_unit:'km/h'}).value,36);
  assert.ok(Math.abs(speedReading({speed:10,speed_unit:'mph'}).value-22.36936)<.00001);
  assert.equal(speedReading({speed:null,speed_unit:'mph'}).value,null);
  assert.equal(shiftState({rpm:6000,shift_rpm:6000,gear:3},24).lit,24);
  assert.equal(dashboardFlag(0),null);
  assert.equal(dashboardFlag(0x10|0x8).name,'red');
  assert.equal(dashboardFlag(0x8).name,'yellow');
});

test('fuel cylinder uses capacity and never invents a level when capacity is absent', async () => {
  const {content}=await import('../irboard/static/widgets.mjs');
  const d={car:{fuel:25},session:{},fuel:{},pit:{fuel_max:100}};
  assert.ok(content('fuel',d).includes('height:25%'));
  assert.ok(content('fuel',{...d,pit:{}}).includes('Tank capacity unavailable'));
});

test('driving panel uses selected speed units and only relative hides unlocated drivers', async () => {
  const {content} = await import('../irboard/static/widgets.mjs');
  const data={car:{speed:10,speed_unit:'mph',clutch:0},session:{},fuel:{},drivers:[
    {name:'Retired driver',position:7,pct:null},
    {name:'Active driver',position:1,pct:.3,relative:0},
  ]};
  assert.match(content('inputs',data),/22 mph/);
  assert.match(content('standings',data),/Retired driver/);
  assert.doesNotMatch(content('relative',data),/Retired driver/);
  assert.match(content('relative',data),/Active driver/);
});

test('pit sign separates limiter activation from speed and handles missing SDK data', async () => {
  const {pitLimiterState}=await import('../irboard/static/widgets.mjs');
  let state=pitLimiterState({speed:20,speed_unit:'km/h',pit:true,pit_limiter:true},{pit_limit:60/3.6});
  assert.equal(Math.round(state.limit),60);
  assert.equal(state.state,'on');
  assert.equal(state.available,true);
  assert.equal(state.speeding,true);
  state=pitLimiterState({speed:20,speed_unit:'mph',pit:false,pit_limiter:false},{pit_limit:40*.44704});
  assert.equal(Math.round(state.limit),40);
  assert.equal(state.speeding,false);
  assert.equal(state.state,'off');
  state=pitLimiterState({},{});
  assert.equal(state.limit,null);
  assert.equal(state.state,'unknown');
  assert.equal(state.available,false);
  assert.equal(pitLimiterState({pit_limiter:true},{}).available,false);
  assert.equal(pitLimiterState({},{pit_limit:20}).available,false);
  assert.equal(state.speeding,false);
});

test('race rows distinguish lapping, pit stops, class timing, flags and radio without inferring DNF', async () => {
  const {content}=await import('../irboard/static/widgets.mjs');
  const base={car:{},fuel:{},history:[],session:{type:'Race',remaining:120,classes:[{id:1,name:'GT3',drivers:3,sof:2000,best_lap:100}]},drivers:[
    {id:0,name:'Me',player:true,pct:.9,relative:0,position:2,class_position:2,lap_difference:0,laps:10},
    {id:1,name:'Ahead',pct:.91,relative:1,position:1,class_position:1,lap_difference:1,pit:true,pit_elapsed:12,radio_recent:true,compound:'Wet',penalty:true,repair:true,best_lap:100,gap:0,gap_laps:0,irating_change:50},
    {id:2,name:'Behind',pct:.89,relative:-1,position:3,lap_difference:-1,out_lap:true,last_pit_lap:9,pit_duration:24,pit_stop_duration:10,stint_lap:1,finished:true},
    {id:3,name:'Garage',pct:null,surface:-1,position:4},
  ]};
  for (const type of ['standings','relative']) {
    const html=content(type,base);
    for (const text of ['LAPPING YOU +1L','LAPPED −1L','PIT 12.0 s','RADIO','BLACK FLAG','REPAIR','Wet','OUT LAP','Last PIT L9','stop 10.0 s','≈ ΔiR +50']) assert.ok(html.includes(text),text);
    assert.ok(html.includes(type==='relative'?'STINT L1':'data-element="stint"'));
    assert.ok(html.includes('data-lap-state="ahead"'));
    assert.ok(html.includes('data-lap-state="behind"'));
    assert.ok(!html.includes('DNF'));
    if (type==='relative') for (const key of ['lastTime','bestTime','gap','interval','averageLap','lapDeltas']) assert.ok(!html.includes('data-element="'+key+'"'));
  }
  assert.ok(content('standings',base).includes('Garage'));
  assert.ok(!content('relative',base).includes('Garage'));
  assert.ok(content('standings',{...base,drivers:[{name:'<script>alert(1)</script>',pct:.2,team:'<svg/onload=1>'}]}).includes('&lt;script&gt;'));
});

test('missing and signed controls, input trace, structured SDK fields and pressure units remain readable', async () => {
  const {content}=await import('../irboard/static/widgets.mjs');
  const data={car:{speed:10,speed_unit:'mph',gear:3,steering:Math.PI/2,throttle:.5,brake:0,clutch:0,abs_active:true,
    systems:[{label:'ABS',role:'abs',value:-3},{label:'TC',role:'tc',value:0}]},session:{},fuel:{},history:[],drivers:[],
    input_trace:[{throttle:0,brake:1,clutch:0},{throttle:1,brake:0,clutch:0}],raw:{Speed:10,Custom:[1,2],Missing:null,Text:'<script>'}};
  const input=content('inputs',data);
  assert.ok(!input.includes('STEERING'));
  assert.ok(!input.includes('RAW ·'));
  assert.ok(input.includes('data-abs-active="true"'));
  assert.ok(input.includes('Input trace'));
  assert.ok(input.includes('22 mph'));
  const systems=content('systems',data);
  assert.ok(systems.includes('>-3<'));
  assert.ok(systems.includes('>0<'));
  const raw=content('inspector',data);
  assert.ok(raw.includes('m/s'));
  assert.ok(raw.includes('[1,2]'));
  assert.ok(raw.includes('&lt;script&gt;'));
  for (const [value,label] of [[0,'SPOTTER OFF'],[1,'CLEAR'],[5,'TWO CARS LEFT'],[6,'TWO CARS RIGHT'],[null,'Spotter unavailable']]) {
    assert.ok(content('radar',{...data,car:{left_right:value}}).includes(label));
  }
});

test('lap time formatting carries rounded milliseconds across minute boundaries', async () => {
  const {time}=await import('../irboard/static/format.mjs');
  assert.equal(time(119.9999),'2:00.000');
  assert.equal(time(59.9999),'1:00.000');
  assert.equal(time(null),'—');
  assert.equal(time(-1),'—');
});

test('new race data visibility and semantic colors survive layout migration', () => {
  const state=migrate({pages:[{name:'Race',widgets:[{type:'relative',hidden:['pitStatus','lapped','gap','session'],colors:{lapped:'#112233',lapping:'#ff0000'}}]}]});
  const w=state.pages[0].widgets[0];
  assert.deepEqual(w.hidden,['pitStatus','lapped']);
  assert.equal(w.colors.lapped,'#112233');
  assert.equal(w.colors.lapping,'#ff0000');
});

test('race tables omit session and weather headers and tachometer places PIT above centered temperatures', async () => {
  const {content}=await import('../irboard/static/widgets.mjs');
  for (const type of ['relative','standings']) {
    const html=content(type,{car:{},session:{track:'Example',air:20,classes:[{name:'GT3',drivers:2,sof:2000}]},drivers:[]});
    for (const name of ['race-session','race-conditions','race-class-list','race-flags']) assert.ok(!html.includes(name));
  }
  const html=content('tachometer',{car:{},session:{}});
  assert.ok(html.indexOf('pit-limiter')<html.indexOf('tach-temperatures'));
});

test('multicolor flags flash their spatial patterns simultaneously', async () => {
  const {dashboardFlag}=await import('../irboard/static/widgets.mjs');
  const debris=dashboardFlag(0x40);
  assert.equal(debris.name,'debris');
  assert.ok(debris.color.includes('#ffcf24')&&debris.color.includes('#d82032'));
  const finish=dashboardFlag(1);
  assert.ok(finish.color.includes('conic-gradient'));
  assert.ok(finish.color.includes('#ffffff')&&finish.color.includes('#171717'));
  assert.equal(dashboardFlag(0x10|0x40).name,'red');
  assert.equal(dashboardFlag(0x8).color,'#ffcf24');
});

test('default dashboard preserves the supplied seven-page layout and appearance', () => {
  const state=defaults();
  assert.equal(state.active,0);
  assert.equal(state.theme,'original');
  assert.deepEqual(state.pages.map(p=>p.widgets.map(w=>w.type)),[
    ['tachometer'],['relative','learnedmap'],['fuel','systems','inputs','laps'],['standings'],['learnedmap'],['pit'],['irlogic'],
  ]);
  assert.ok(state.pages[1].widgets[0].hidden.includes('irating'));
  assert.ok(state.pages[1].widgets[0].hidden.includes('pitHistory'));
  const tach=state.pages[0].widgets[0];
  assert.deepEqual(tach.hidden,['water','oil','engineWarnings','powertrain']);
  assert.deepEqual(tach.layouts,{});
  assert.equal(tach.shiftLights.segments,10);
  assert.equal(tach.shiftLights.hz,10);
  assert.equal(state.pages[2].preset,'auto');
  assert.equal(state.pages[2].widgets[2].layouts.landscape.h,.495);
  assert.ok(state.pages[3].widgets[0].hidden.includes('iratingChange'));
  state.pages[0].widgets[0].hidden.push('speed');
  assert.ok(!defaults().pages[0].widgets[0].hidden.includes('speed'));
});

test('driving-alert settings migrate safely and survive exports without changing pages', async () => {
  const {alertSettings}=await import('../irboard/static/alerts.mjs');
  const original=defaults();
  assert.equal(original.alerts.flags.mode,'off');
  assert.equal(original.alerts.spotter.mode,'halves');
  const edited=migrate({...original,alerts:{flags:{mode:'center',duration:5,opacity:.65,blink:true,untilClear:true,enabled:{red:false}},spotter:{mode:'bars',opacity:.4}}});
  const restored=migrate(JSON.parse(JSON.stringify(edited)));
  assert.deepEqual(restored.alerts,edited.alerts);
  const appearance=pages=>JSON.parse(JSON.stringify(pages,(key,value)=>key==='id'?undefined:value));
  assert.deepEqual(appearance(restored.pages),appearance(original.pages));
  assert.equal(restored.alerts.flags.enabled.red,false);
  assert.equal(restored.alerts.flags.enabled.yellow,true);
  assert.equal(restored.alerts.flags.blink,true);
  assert.equal(restored.alerts.flags.untilClear,true);
  const invalid=alertSettings({flags:{mode:'javascript:bad',duration:Infinity,opacity:-5},spotter:{mode:'bad',opacity:10}});
  assert.equal(invalid.flags.mode,'center');
  assert.equal(invalid.flags.duration,3);
  assert.equal(invalid.flags.opacity,.1);
  assert.equal(invalid.spotter.mode,'off');
  assert.equal(invalid.spotter.opacity,1);
});

test('individual race flags can be disabled without suppressing other active flags', async () => {
  const {RACE_FLAGS,raceFlag}=await import('../irboard/static/alerts.mjs');
  for (const flag of RACE_FLAGS) {
    assert.equal(raceFlag(flag.mask).name,flag.name);
    assert.equal(raceFlag(flag.mask,{[flag.name]:false}),null);
  }
  assert.equal(raceFlag(0x10|0x8,{red:false}).name,'yellow');
  assert.equal(raceFlag(0x10|0x8,{red:false,yellow:false}),null);
  assert.equal(raceFlag(null),null);
});

test('flag notices expire instead of restarting on every telemetry frame', async () => {
  const {FlagNotice,raceFlag,alertSettings}=await import('../irboard/static/alerts.mjs');
  const notice=new FlagNotice(),settings=alertSettings({flags:{duration:3}}).flags;
  assert.equal(notice.update(raceFlag(8),settings,'session',0).changed,true);
  assert.equal(notice.update(raceFlag(8),settings,'session',2000).changed,false);
  assert.equal(notice.update(raceFlag(8),settings,'session',2999).visible,true);
  assert.equal(notice.update(raceFlag(8),settings,'session',3000).visible,false);
  assert.equal(notice.update(raceFlag(8),settings,'session',9000).visible,false);
  assert.equal(notice.update(null,settings,'session',9001),null);
  assert.equal(notice.update(raceFlag(8),settings,'session',9002).visible,true);
  assert.equal(notice.update(raceFlag(8),settings,'another session',9010).changed,true);
  assert.equal(notice.update(raceFlag(8),{...settings,mode:'off'},'session',9011),null);
  const held={...settings,mode:'center',untilClear:true,blink:true};
  assert.equal(notice.update(raceFlag(8),held,'session',10000).visible,true);
  assert.equal(notice.update(raceFlag(8),held,'session',90000).visible,true);
  assert.equal(notice.update(null,held,'session',90001),null);
});

test('on-screen spotter follows every SDK CarLeftRight value without guessing', async () => {
  const {spotterSides}=await import('../irboard/static/alerts.mjs');
  for (const value of [null,undefined,0,1,-1,99,'2']) assert.deepEqual(spotterSides(value),{left:false,right:false});
  for (const value of [2,5]) assert.deepEqual(spotterSides(value),{left:true,right:false});
  for (const value of [3,6]) assert.deepEqual(spotterSides(value),{left:false,right:true});
  assert.deepEqual(spotterSides(4),{left:true,right:true});
});

test('iR-logic preserves settings and migrates only its old default title', async () => {
  const {content}=await import('../irboard/static/widgets.mjs');
  const original=defaults();
  for(const type of ['irlogic']) {
    assert.equal(TYPES[type],'iR-logic');
    assert.ok(!content(type,{}).includes('Experimental'));
    for(const [title,expected] of [['iR-logic (Experimental)','iR-logic'],['My reference','My reference']]) {
      assert.equal(migrate({pages:[{name:'Keep',widgets:[{type,title}]}]}).pages[0].widgets[0].title,expected);
    }
    const custom=migrate({pages:[{name:'Experimental',widgets:[{type,coachReference:'personal'}]}]});
    assert.equal(custom.pages[0].widgets[0].type,type);
    if(type==='irlogic')assert.equal(custom.pages[0].widgets[0].coachReference,'personal');
  }
  assert.equal(defaults().pages.length,original.pages.length);
  assert.equal(TYPES.navigator,undefined);
  assert.equal(TYPES.brakecoach,undefined);
  const upgraded=migrate({pages:[{name:'Custom',widgets:[{type:'navigator'},{type:'tachometer',title:'Keep me',layouts:{landscape:{x:0,y:0,w:.5,h:.5}}},{type:'brakecoach'},{type:'irlogic',coachReference:'personal'}]}]});
  assert.deepEqual(upgraded.pages[0].widgets.map(w=>w.type),['tachometer','irlogic']);
  assert.equal(upgraded.pages[0].widgets[0].title,'Keep me');
  assert.equal(upgraded.pages[0].widgets[0].layouts.landscape.w,.5);
  assert.equal(upgraded.pages[0].widgets[1].coachReference,'personal');
});


test('iR-logic handles seven sectors and compares actual boundary times', async () => {
  const {sectorComparison}=await import('../irboard/static/experimental.mjs');
  const samples=Array.from({length:101},(_,i)=>({pct:i/100,time:i}));
  const data={car:{lap_pct:.5},sectors:Array.from({length:7},(_,i)=>({number:i+1,start:i/7,end:(i+1)/7})),
    coaching:{current_time:50,trace:samples.filter(s=>s.pct<=.5),references:{session:'ref'},laps:{ref:{lap_time:100,samples}}}};
  const result=sectorComparison(data);
  assert.equal(result.sectors.length,7);assert.equal(result.current,3);
  assert.ok(Math.abs(result.sectors[3].delta)<1e-8);
  assert.equal(sectorComparison({...data,sectors:[]}).sectors.length,0);
});


test('map classes use SDK colors, distinct known shapes and safe metadata', async () => {
  const {classMarker,learnedMap}=await import('../irboard/static/widgets.mjs');
  const classes=['GT3','GTP','LMP2','LMP3','GT4','TCR'];
  const markers=classes.map((name,i)=>classMarker({class_name:name,class_id:i,class_color:'#123456'}));
  assert.equal(new Set(markers.map(m=>m.shape)).size,6);
  assert.ok(markers.every(m=>m.color==='#123456'));
  assert.equal(markers[0].shape,'circle');
  assert.equal(markers[1].shape,'diamond');
  assert.equal(classMarker({class_name:'Custom',class_id:999}).shape,classMarker({class_name:'Custom',class_id:999}).shape);
  assert.match(classMarker({class_color:'url(javascript:1)'}).color,/^#[0-9a-f]{6}$/i);
  const html=learnedMap({track_map:{status:'ready',points:[[0,0],[100,0],[100,100],[0,100]],message:'Local line'},drivers:[{id:0,pct:.1,number:7,player:true,pit:true,class_name:'<script>x</script>',class_id:1,class_color:'#123456'}]});
  assert.ok(html.includes('fill:#123456'));
  assert.ok(html.includes('data-role="player"'));
  assert.ok(html.includes('data-role="pitCar"'));
  assert.ok(html.includes('data-element="classLegend"'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
});


test('practice separates measured stint fuel from race finish and unmeasured laps', async () => {
  const {fuelEstimate}=await import('../irboard/static/fuel.mjs');
  const data={session:{type:'Practice'},car:{fuel:5,last_lap:100},fuel:{average:3},history:[]};
  assert.match(fuelEstimate(data).reason,/Race.*Next stint/);
  assert.equal(fuelEstimate(data,{target:'laps',amount:5,reserve:0}).add,10);
  assert.equal(fuelEstimate(data,{target:'minutes',amount:5,reserve:0}).add,4);
  assert.match(fuelEstimate({...data,fuel:{}},{target:'laps'}).reason,/clean/);
  assert.match(fuelEstimate({...data,fuel:{}}).reason,/Race/);
});

test('pit sign follows SDK approach and pit road and disappears on exit', async () => {
  const {pitLimiterState}=await import('../irboard/static/widgets.mjs');
  const session={pit_limit:20};
  for (const pit_limiter of [true,false]) {
    assert.equal(pitLimiterState({surface:2,pit:false,pit_limiter},session).available,true);
    assert.equal(pitLimiterState({surface:1,pit:true,pit_limiter},session).available,true);
    for (const surface of [3,0,-1,null])
      assert.equal(pitLimiterState({surface,pit:false,pit_limiter,lap_pct:.99},session).available,false);
  }
});



test('sector colors distinguish completed gains, losses and the current sector',async()=>{
  const {sectorState}=await import('../irboard/static/experimental.mjs');
  assert.equal(sectorState({delta:-.12},0,2),'gain');
  assert.equal(sectorState({delta:.12},1,2),'loss');
  for(const delta of [-.12,.12,0,null])assert.equal(sectorState({delta},2,2),'current');
  assert.equal(sectorState({delta:0},0,2),'even');
  assert.equal(sectorState({delta:null},0,2),'pending');
  assert.equal(sectorState({delta:-.12},3,2),'pending');
  assert.equal(sectorState({delta:-.12},0,-1),'pending');
});

test('default coaching uses saved personal best until a clean session reference exists',async()=>{
  const {referenceLap}=await import('../irboard/static/experimental.mjs');
  const saved={lap_time:100,samples:[]},session={lap_time:110,samples:[]};
  const data={coaching:{references:{personal:'pb',session:null},laps:{pb:saved,session}}};
  assert.equal(referenceLap(data),saved);
  assert.equal(referenceLap(data,{coachReference:'last'}),null);
  data.coaching.references.session='session';
  assert.equal(referenceLap(data),session);
});


test('bundled layout matches the importable JSON and retains alert settings', async () => {
  const {readFile}=await import('node:fs/promises');
  const {DEFAULT_LAYOUT}=await import('../irboard/static/default-layout.mjs');
  const exported=JSON.parse(await readFile(new URL('../docs/default-layout.json',import.meta.url),'utf8'));
  assert.deepEqual(DEFAULT_LAYOUT,exported);
  const state=defaults();
  const withoutIds=value=>JSON.parse(JSON.stringify(value,(key,v)=>key==='id'?undefined:v));
  assert.deepEqual(withoutIds(state),withoutIds(exported));
  assert.equal(state.alerts.flags.enabled.red,false);
  assert.equal(state.alerts.flags.untilClear,true);
  assert.equal(state.alerts.spotter.opacity,.25);
});


test('button box bindings and appearance survive migration without changing saved pages', async () => {
  const {buttonBindings,BUTTON_ACTIONS,buttonboxContent}=await import('../irboard/static/buttonbox.mjs');
  const original=defaults();
  assert.equal(original.pages.length,7);
  assert.ok(original.pages.every(p=>p.widgets.every(w=>w.type!=='buttonbox')));
  assert.equal(TYPES.buttonbox,'Button box');
  const bindings=buttonBindings({ignition:'A',starter:'F24',radio:'',abs_up:'<script>',evil:'F1'});
  assert.equal(bindings.ignition,'A');
  assert.equal(bindings.starter,'F24');
  assert.equal(bindings.radio,'');
  assert.equal(bindings.abs_up,BUTTON_ACTIONS.abs_up.defaultKey);
  assert.ok(!Object.hasOwn(bindings,'evil'));
  const state=migrate({...original,pages:[...original.pages,{name:'My controls',widgets:[{
    type:'buttonbox',title:'GT3 controls',buttonBindings:bindings,colors:{on:'#123456',press:'#abcdef'},hidden:['radio'],
    layouts:{landscape:{x:0,y:0,w:1,h:1}},
  }]}]});
  assert.equal(state.pages.length,8);
  const box=state.pages.at(-1).widgets[0];
  assert.deepEqual(box.buttonBindings,bindings);
  assert.equal(box.title,'GT3 controls');
  assert.equal(box.colors.press,'#abcdef');
  assert.deepEqual(box.hidden,['radio']);
  assert.deepEqual(migrate(JSON.parse(JSON.stringify(state))).pages.at(-1).widgets[0].buttonBindings,bindings);
  const markup=buttonboxContent();
  for(const action of Object.keys(BUTTON_ACTIONS))assert.ok(markup.includes(`data-action="${action}"`),action);
  assert.ok(markup.includes('<svg'));
  const keys=Object.values(buttonBindings());
  assert.equal(new Set(keys).size,12);
});
