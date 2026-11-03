// Retire the old optional PWA worker without registering a replacement.
if ('serviceWorker' in navigator) navigator.serviceWorker.getRegistrations().then(registrations => {
  const oldWorker = new URL('/sw.js', location.href).href;
  return Promise.all(registrations.filter(registration =>
    [registration.active, registration.waiting, registration.installing].some(worker => worker?.scriptURL === oldWorker)
  ).map(registration => registration.unregister()));
}).catch(() => {});
import { THEMES, activeTheme, themeColor, applyTheme, customTheme, CUSTOM_THEME_COLORS } from "./themes.mjs";
import { fuelEstimate } from "./fuel.mjs";
import { refreshInputs } from "./driving-view.mjs";
import { refreshRaceTable } from "./race-view.mjs";
import { RACE_FLAGS, alertSettings, DrivingAlerts } from "./alerts.mjs";
import { EXPERIMENTAL_TYPES, REFERENCE_NAMES, referenceMode, refreshExperimental } from "./experimental.mjs";
import {
  TYPES,
  LAYOUTS,
  templateSlots,
  snapRect,
  setPreset,
  visibilityElements,
  colorRoles,
  validColor,
  widget,
  defaults,
  migrate,
  defaultRect,
  overlap,
  clamp,
  resizeRect,
} from "./model.mjs";
import { esc, n, content, pitForm, pitReadback, updateTachometer, contrastColor } from "./widgets.mjs";
const $ = (s) => document.querySelector(s);
const drivingAlerts = new DrivingAlerts(document);
let state;
try {
  const saved = localStorage.getItem("irboard");
  state = saved ? migrate(JSON.parse(saved)) : defaults();
} catch {
  state = defaults();
}
let edit = false,
  data = null,
  receivedAt = performance.now(),
  gesture = null,
  colorDraft = null,
  polling = true;
const page = () => state.pages[state.active];
const canvas = $("#dashboard");
const orientation = () =>
  canvas.clientWidth > canvas.clientHeight * 1.15 ? "landscape" : "portrait";
let lastOrientation = "";
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 3500);
}
// Keep page navigation device-local; synchronize the complete reusable appearance.
let sharedBase = null, sharedRevision = null, sharedSignature = null, syncBusy = false, syncApplying = false, syncTimer;
function sharedLayout(value = state) {
  const layout = structuredClone(value);
  layout.active = 0;
  for (const p of layout.pages) for (const w of p.widgets) delete w.id;
  return layout;
}
function acceptShared(value) {
  const active = state.active;
  state = migrate(value.layout);
  state.active = Math.min(active, state.pages.length - 1);
  sharedRevision = value.revision;
  sharedBase = sharedLayout();
  sharedSignature = JSON.stringify(sharedBase);
  syncApplying = true;
  render();
  syncApplying = false;
}
async function syncLayout() {
  if (syncBusy || gesture || edit || $('#modal').open) return;
  syncBusy = true;
  try {
    const response = await fetch('/api/layout', {headers: authHeaders(), signal: AbortSignal.timeout(3000)});
    if (response.status === 401) { location.replace('/auth'); return; }
    if (!response.ok) throw Error('Shared layout unavailable');
    const remote = await response.json();
    if (gesture || edit || $('#modal').open) return;
    const signature = JSON.stringify(sharedLayout());
    if (sharedRevision === null) {
      if (remote.layout) {
        if (signature !== JSON.stringify(remote.layout))
          localStorage.setItem('irboard-conflict-backup', JSON.stringify(state));
        acceptShared(remote);
        return;
      }
      sharedRevision = remote.revision;
    } else if (remote.revision !== sharedRevision) {
      if (sharedBase && signature !== sharedSignature) {
        const local = sharedLayout(), incoming = sharedLayout(migrate(remote.layout));
        const merged = structuredClone(incoming);
        let conflict = false;
        for (const key of Object.keys(local)) {
          if (JSON.stringify(local[key]) === JSON.stringify(sharedBase[key])) continue;
          if (JSON.stringify(incoming[key]) === JSON.stringify(sharedBase[key]) ||
              JSON.stringify(incoming[key]) === JSON.stringify(local[key])) merged[key] = local[key];
          else conflict = true;
        }
        if (conflict) {
          localStorage.setItem('irboard-conflict-backup', JSON.stringify(state));
          toast('Another device changed the same settings. Your local changes are backed up.');
        }
        acceptShared({...remote, layout:merged});
        sharedBase = incoming;
        sharedSignature = JSON.stringify(incoming);
      } else acceptShared(remote);
      return;
    }
    if (signature !== sharedSignature) {
      if (data?.access?.can_control === false) {
        $('#save-state').textContent = 'Pair this device to synchronize changes';
        return;
      }
      const result = await fetch('/api/layout', {
        method:'POST', headers:{...authHeaders(), 'Content-Type':'application/json'},
        body:JSON.stringify({revision:sharedRevision, layout:sharedLayout()}),
        signal:AbortSignal.timeout(3000),
      });
      if (result.status === 409) return; // Pull the winning revision next time.
      if (!result.ok) throw Error('Shared layout save failed');
      const saved = await result.json();
      sharedRevision = saved.revision;
      sharedSignature = signature;
      sharedBase = JSON.parse(signature);
    }
    $('#save-state').textContent = 'Appearance synchronized across devices';
  } catch {
    $('#save-state').textContent = 'Saved locally · synchronization pending';
  } finally {
    syncBusy = false;
  }
}
function save() {
  try {
    localStorage.setItem("irboard", JSON.stringify(state));
    if (!syncApplying && sharedRevision !== null) {
      clearTimeout(syncTimer);
      syncTimer = setTimeout(syncLayout, 100);
    }
    $("#save-state").textContent = syncApplying ? "Appearance synchronized across devices" : "Saved locally · synchronizing";
  } catch {
    $("#save-state").textContent = "Storage full — export your layout";
  }
}
function modal(title, html) {
  $("#modal-title").textContent = title;
  $("#modal-content").innerHTML = html;
  $("#modal").showModal();
}
$("#modal-close").onclick = () => $("#modal").close();
$("#modal").addEventListener("close", () => {
  colorDraft = null;
  $("#modal-content").replaceChildren();
  paint();
  applyLayouts();
  syncLayout();
});
function getRect(w, index, axis = orientation()) {
  if (w.layouts?.[axis]) return w.layouts[axis];
  const rect = defaultRect(index, Math.max(page().widgets.length, templateSlots(page())), axis, page().preset);
  // Compact defaults; explicitly chosen templates and saved dimensions stay authoritative.
  const compact = {systems:.28, fuel:.45, laps:.5}[w.type];
  if ((!page().preset || page().preset === 'auto') && compact) rect.h = Math.min(rect.h, compact);
  return rect;
}
function setRect(el, r) {
  el.style.left = r.x * 100 + "%";
  el.style.top = r.y * 100 + "%";
  el.style.width = r.w * 100 + "%";
  el.style.height = r.h * 100 + "%";
}
function applyLayouts() {
  lastOrientation = orientation();
  page().widgets.forEach((w, i) => {
    const el = canvas.querySelector(`[data-id="${w.id}"]`);
    if (el) setRect(el, getRect(w, i));
  });
  canvas
    .querySelectorAll("[data-slot]")
    .forEach((el) =>
      setRect(
        el,
        defaultRect(
          +el.dataset.slot,
          templateSlots(page()),
          lastOrientation,
          page().preset,
        ),
      ),
    );
}
function theme(el, w) {
  if (w.type==='learnedmap') {
    if (validColor(w.colors?.carNumber)) el.style.setProperty('--c-map-number',w.colors.carNumber);
    else el.style.removeProperty('--c-map-number');
  }
  el.dataset.driverColorOverride = String(validColor(w.colors?.driver));
  if (validColor(w.colors?.safetyRating)) {
    el.style.setProperty('--c-safetyOverride',w.colors.safetyRating);
    el.style.setProperty('--c-safetyTextOverride',contrastColor(w.colors.safetyRating));
  } else {
    el.style.removeProperty('--c-safetyOverride');
    el.style.removeProperty('--c-safetyTextOverride');
  }
  for (const [key, [, fallback]] of Object.entries(colorRoles(w.type)))
    el.style.setProperty(
      "--c-" + key,
      validColor(w.colors?.[key]) ? w.colors[key] : themeColor(activeTheme(state.theme, state.customTheme), key, fallback),
    );
}
function applyVisibility(el, w) {
  const hidden = new Set(w.hidden || []);
  for (const node of el.querySelectorAll("[data-element]")) {
    const invisible = hidden.has(node.dataset.element);
    node.toggleAttribute("hidden", invisible);
    node.style.display = invisible ? "none" : "";
  }
  const title = el.querySelector(".widget-title");
  if (title) title.hidden = hidden.has("title");
  for (const node of el.querySelectorAll(
    'span[data-role="label"],p[data-role="label"],legend[data-role="label"]',
  )) {
    node.hidden = hidden.has("labels") || hidden.has(node.dataset.element);
  }
  // Hidden pit inputs must not block browser validation or receive focus.
  // Their services are merged from the live readback before submission.
  for (const control of el.querySelectorAll(".pit-form input,.pit-form select"))
    control.disabled = !!control.closest("[hidden]") || control.dataset.unavailable === "1";
  // Empty metric grids and decorative separators must not leave gaps.
  for (const grid of el.querySelectorAll(".metrics,.driver-details,.driver-name-line,.tach-readouts"))
    grid.hidden = ![...grid.children].some((child) => !child.hidden);
  for (const line of el.querySelectorAll(".divider")) {
    const before = line.previousElementSibling,
      after = line.nextElementSibling;
    line.hidden = !before || before.hidden || !after || after.hidden;
  }
}
const handles = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
const edgeName = {
  n: "top edge",
  ne: "top-right corner",
  e: "right edge",
  se: "bottom-right corner",
  s: "bottom edge",
  sw: "bottom-left corner",
  w: "left edge",
  nw: "top-left corner",
};
function render() {
  applyTheme(state.theme, state.customTheme);
  save();
  $("#page-name").textContent = page().name;
  $("#layout-title").textContent = page().name;
  $("#widget-count").textContent =
    `${page().widgets.length} widget${page().widgets.length === 1 ? "" : "s"}`;
  $("#page-nav").innerHTML = state.pages
    .map(
      (p, i) =>
        `<button class="rail-button ${i === state.active ? "active" : ""}" data-page="${i}" title="${esc(p.name)}">${i + 1}</button>`,
    )
    .join("");
  $("#page-dots").innerHTML = state.pages
    .map(
      (_, i) =>
        `<button data-page="${i}" class="${i === state.active ? "active" : ""}" aria-label="Page ${i + 1}"><i></i></button>`,
    )
    .join("");
  document
    .querySelectorAll("[data-page]")
    .forEach((b) => (b.onclick = () => go(+b.dataset.page)));
  canvas.classList.toggle("editing", edit);
  $("#edit-banner").hidden = !edit;
  $("#edit").classList.toggle("active", edit);
  $("#edit span").textContent = edit ? "Finish editing" : "Edit layout";
  canvas.innerHTML =
    page()
      .widgets.map(
        (w) =>
          `<article class="widget" data-id="${w.id}" data-type="${w.type}" data-role="background"><header class="widget-head"><button class="drag-handle" aria-label="Move widget" title="Drag to move or swap widgets">⠿</button><span class="widget-title" data-role="title">${esc(w.title || TYPES[w.type])}</span><button class="icon-button configure" aria-label="Configure widget" title="Colors and visibility">⚙</button></header><div class="widget-body"></div>${handles.map((edge) => `<button class="resize-edge edge-${edge}" data-edge="${edge}" aria-label="Resize: ${edgeName[edge]}" title="Drag: ${edgeName[edge]}"></button>`).join("")}</article>`,
      )
      .join("") ||
    '<div class="empty-state">Add a widget using ＋<br>Choose a layout or keep adding widgets to this page</div>';
  for (const el of canvas.querySelectorAll(".widget")) {
    const w = page().widgets.find((w) => w.id === el.dataset.id);
    theme(el, w);
    el.onpointerdown = (e) => {
      if (!edit || e.target.closest("button,input,select,label,form")) return;
      beginManipulation(e, w, "move");
    };
    el.querySelector(".configure").onclick = () => configure(w.id);
    el.querySelector(".drag-handle").onpointerdown = (e) =>
      beginManipulation(e, w, "move");
    el.querySelector(".drag-handle").onkeydown = (e) => keyboardMove(e, w);
    el.querySelectorAll("[data-edge]").forEach((handle) => {
      handle.onpointerdown = (e) =>
        beginManipulation(e, w, handle.dataset.edge);
      handle.onkeydown = (e) => keyboardResize(e, w, handle.dataset.edge);
    });
  }
  if (page().preset !== "auto" && page().preset && page().widgets.length) {
    for (let i = page().widgets.length; i < templateSlots(page()); i++) {
      const slot = document.createElement("button");
      slot.className = "layout-slot";
      slot.dataset.slot = i;
      slot.innerHTML = "<span>＋</span>Add widget";
      slot.onclick = () => $("#add-widget").click();
      canvas.append(slot);
    }
  }
  const guides = document.createElement("div");
  guides.className = "alignment-layer";
  guides.setAttribute("aria-hidden", "true");
  canvas.append(guides);
  applyLayouts();
  paint();
}
function go(index) {
  if (gesture) return;
  state.active = (index + state.pages.length) % state.pages.length;
  render();
}
function drawGuides(guides) {
  const layer = canvas.querySelector(".alignment-layer");
  if (!layer) return;
  layer.innerHTML = guides
    .map(
      (g) =>
        `<i class="alignment-guide axis-${g.axis}" style="${g.axis === "x" ? "left" : "top"}:${g.value * 100}%"></i>`,
    )
    .join("");
}
function beginManipulation(e, w, edge) {
  if (!edit || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  const bounds = canvas.getBoundingClientRect(),
    index = page().widgets.indexOf(w),
    axis = orientation();
  const original = { ...getRect(w, index, axis) };
  gesture = {
    kind: "layout",
    id: w.id,
    pointerId: e.pointerId,
    target: e.currentTarget,
    edge,
    x: e.clientX,
    y: e.clientY,
    bounds,
    axis,
    original,
    last: original,
    moved: false,
  };
  e.currentTarget.setPointerCapture(e.pointerId);
  canvas.classList.add("manipulating");
}
function rectAllowed(w, r, axis) {
  return page().widgets.every(
    (other, i) => other === w || !overlap(r, getRect(other, i, axis)),
  );
}
function keyboardMove(e, w) {
  if (
    !edit ||
    !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)
  )
    return;
  e.preventDefault();
  const axis = orientation(),
    r = getRect(w, page().widgets.indexOf(w), axis),
    step = e.shiftKey ? 0.05 : 0.01;
  const next = {
    ...r,
    x: clamp(
      r.x + (e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0),
      0,
      1 - r.w,
    ),
    y: clamp(
      r.y + (e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0),
      0,
      1 - r.h,
    ),
  };
  if (rectAllowed(w, next, axis)) {
    w.layouts[axis] = next;
    applyLayouts();
    save();
  }
}
function swapTarget(e, id) {
  const r = canvas.getBoundingClientRect(),
    x = (e.clientX - r.left) / r.width,
    y = (e.clientY - r.top) / r.height;
  return page().widgets.find((w, i) => {
    const box = getRect(w, i);
    return (
      w.id !== id &&
      x >= box.x &&
      x <= box.x + box.w &&
      y >= box.y &&
      y <= box.y + box.h
    );
  });
}
function keyboardResize(e, w, edge) {
  if (
    !edit ||
    !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)
  )
    return;
  e.preventDefault();
  const axis = orientation(),
    r = getRect(w, page().widgets.indexOf(w), axis),
    step = e.shiftKey ? 0.05 : 0.01;
  const dx = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0,
    dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
  const next = resizeRect(
    r,
    edge,
    dx,
    dy,
    Math.min(0.08, r.w),
    Math.min(0.08, r.h),
  );
  if (rectAllowed(w, next, axis)) {
    w.layouts[axis] = next;
    applyLayouts();
    save();
  }
}
window.addEventListener("pointermove", (e) => {
  if (gesture?.kind !== "layout" || e.pointerId !== gesture.pointerId) return;
  const g = gesture,
    w = page().widgets.find((w) => w.id === g.id),
    dx = (e.clientX - g.x) / g.bounds.width,
    dy = (e.clientY - g.y) / g.bounds.height;
  g.moved ||= Math.hypot(e.clientX - g.x, e.clientY - g.y) > 5;
  let next;
  if (g.edge === "move")
    next = {
      ...g.original,
      x: clamp(g.original.x + dx, 0, 1 - g.original.w),
      y: clamp(g.original.y + dy, 0, 1 - g.original.h),
    };
  else
    next = resizeRect(
      g.original,
      g.edge,
      dx,
      dy,
      Math.min(g.original.w, 0.15, Math.max(0.01, 100 / g.bounds.width)),
      Math.min(g.original.h, 0.15, Math.max(0.01, 80 / g.bounds.height)),
    );
  const others = page()
    .widgets.filter((other) => other !== w)
    .map((other) => getRect(other, page().widgets.indexOf(other), g.axis));
  const snapped = snapRect(next, others, g.bounds.width, g.bounds.height, {
    edge: g.edge,
    disabled: e.shiftKey,
  });
  if (rectAllowed(w, snapped.rect, g.axis)) {
    g.last = snapped.rect;
    setRect(canvas.querySelector(`[data-id="${w.id}"]`), g.last);
    drawGuides(snapped.guides);
  } else if (rectAllowed(w, next, g.axis)) {
    g.last = next;
    setRect(canvas.querySelector(`[data-id="${w.id}"]`), next);
    drawGuides([]);
  } else drawGuides([]);
  canvas
    .querySelectorAll(".drop-target")
    .forEach((el) => el.classList.remove("drop-target"));
  if (g.edge === "move" && g.moved) {
    const target = swapTarget(e, g.id);
    if (target)
      canvas
        .querySelector(`[data-id="${target.id}"]`)
        .classList.add("drop-target");
  }
});
function endManipulation(e, cancel = false) {
  if (gesture?.kind !== "layout" || gesture.pointerId !== e.pointerId) return;
  const g = gesture,
    w = page().widgets.find((w) => w.id === g.id);
  if (!cancel) {
    const target = swapTarget(e, g.id);
    if (g.edge === "move" && g.moved && target) {
      const other = target,
        i = page().widgets.indexOf(other);
      const theirRect = { ...getRect(other, i, g.axis) };
      other.layouts[g.axis] = { ...g.original };
      w.layouts[g.axis] = theirRect;
    } else w.layouts[g.axis] = { ...g.last };
  }
  if (g.target.hasPointerCapture?.(e.pointerId))
    g.target.releasePointerCapture(e.pointerId);
  gesture = null;
  canvas.classList.remove("manipulating");
  drawGuides([]);
  canvas
    .querySelectorAll(".drop-target")
    .forEach((el) => el.classList.remove("drop-target"));
  applyLayouts();
  save();
}
window.addEventListener("pointerup", (e) => endManipulation(e));
window.addEventListener("pointercancel", (e) => {
  endManipulation(e, true);
  swipe = null;
});
let resizeObserver = new ResizeObserver(() => {
  if (lastOrientation !== orientation()) {
    if (gesture) {
      const g = gesture;
      endManipulation({ pointerId: g.pointerId }, true);
    }
    applyLayouts();
  }
});
resizeObserver.observe(canvas);

function configure(id) {
  const w = page().widgets.find((x) => x.id === id),
    draft = structuredClone(w);
  colorDraft = draft;
  modal(
    "Widget appearance",
    `<form id="widget-form"><label class="title-field">Title<input name="title" value="${esc(draft.title)}" maxlength="80"></label>${w.type==='irlogic'?`<label>Reference lap<select name="coach-reference">${Object.entries(REFERENCE_NAMES).map(([key,label])=>`<option value="${key}" ${referenceMode(draft.coachReference)===key?'selected':''}>${label}</option>`).join('')}</select></label>`:''}<p class="help">Tap an element in the preview or choose it from the list. Colors and visibility update live. Resize outside this dialog using the edges and corners.</p><div class="appearance-editor"><div class="preview widget" data-role="background" data-type="${w.type}"><div class="widget-head"><span class="widget-title" data-role="title">${esc(w.title)}</span></div><div class="widget-body"></div></div><div class="color-list">${Object.entries(
      colorRoles(w.type),
    )
      .map(
        ([key, [label, value]]) =>
          `<label class="color-row" data-color-row="${key}"><span>${label}</span><input type="color" name="color-${key}" data-color="${key}" value="${w.colors[key] || themeColor(activeTheme(state.theme, state.customTheme),key,value)}" aria-label="Color: ${label}"></label>`,
      )
      .join(
        "",
      )}</div></div><section class="visibility-panel"><h3>Visible elements</h3><p class="help">Uncheck an element to hide it in this widget only.</p><div class="visibility-list">${Object.entries(
      visibilityElements(w.type),
    )
      .map(
        ([key, label]) =>
          `<label class="visibility-row"><input type="checkbox" data-visible="${key}" ${draft.hidden.includes(key) ? "" : "checked"}><span>${label}</span></label>`,
      )
      .join(
        "",
      )}</div></section>${w.type === 'tachometer' ? `<section class="shift-settings"><h3>RPM indicator</h3><label>Style<select name="led-style">${[['segments','Segments'],['dots','Dots'],['bar','Continuous filling bar']].map(([key,label])=>`<option value="${key}" ${draft.shiftLights.style===key?'selected':''}>${label}</option>`).join('')}</select></label><label>Segment count<input name="led-segments" type="number" min="4" max="40" step="1" value="${draft.shiftLights.segments}"></label><label>Dot count<input name="led-dots" type="number" min="4" max="40" step="1" value="${draft.shiftLights.dots}"></label><label>Fast blink<select name="blink-speed">${[6,8,10].map(hz=>`<option value="${hz}" ${draft.shiftLights.hz===hz?'selected':''}>${hz} Hz</option>`).join('')}</select></label><label>Blink threshold · RPM<input name="blink-rpm" type="number" min="500" max="30000" step="1" placeholder="Automatic from SDK" value="${draft.shiftLights.blinkRpm ?? ''}"></label><p class="help">Only the graphical indicator blinks. Low / high RPM colors control the continuous bar gradient.</p></section>` : ''}<div class="form-actions"><button type="button" class="button danger" id="remove">Remove widget</button><button type="button" class="button secondary" id="reset-colors">Default colors</button><button type="button" class="button secondary" id="cancel-colors">Cancel</button><button class="button primary">Save</button></div></form>`,
  );
  if(w.type==='irlogic') $('#widget-form [name=coach-reference]').onchange=event=>{
    draft.coachReference=referenceMode(event.target.value);paint();
  };
  const preview = $(".preview");
  theme(preview, draft);
  preview.addEventListener("click", (e) => {
    e.preventDefault();
    const role = e.target.closest("[data-role]")?.dataset.role || "background";
    document
      .querySelectorAll(".color-row")
      .forEach((row) =>
        row.classList.toggle("selected", row.dataset.colorRow === role),
      );
    const row = $(`[data-color-row="${role}"]`);
    row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    row?.querySelector("input").focus({ preventScroll: true });
  });
  document.querySelectorAll("[data-color]").forEach(
    (input) =>
      (input.oninput = () => {
        draft.colors[input.dataset.color] = input.value;
        theme(preview, draft);
        theme(canvas.querySelector(`[data-id="${w.id}"]`), draft);
      }),
  );
  document.querySelectorAll("[data-visible]").forEach(
    (input) =>
      (input.onchange = () => {
        draft.hidden = [...document.querySelectorAll("[data-visible]")]
          .filter((input) => !input.checked)
          .map((input) => input.dataset.visible);
        applyVisibility(preview, draft);
        applyVisibility(canvas.querySelector(`[data-id="${w.id}"]`), draft);
      }),
  );
  if (w.type === 'tachometer') {
    const updateBlink = () => {
      draft.shiftLights = {
        style: $('#widget-form [name="led-style"]').value,
        segments: Number($('#widget-form [name="led-segments"]').value),
        dots: Number($('#widget-form [name="led-dots"]').value),
        hz: Number($('#widget-form [name="blink-speed"]').value),
        blinkRpm: $('#widget-form [name="blink-rpm"]').value === '' ? null : Number($('#widget-form [name="blink-rpm"]').value),
      };
      paint();
    };
    $('#widget-form [name="blink-speed"]').onchange = updateBlink;
    for (const name of ['led-style','led-segments','led-dots','blink-rpm'])
      $(`#widget-form [name="${name}"]`).oninput = updateBlink;
  }
  $("#widget-form [name=title]").oninput = (e) => {
    draft.title = e.target.value;
    preview.querySelector(".widget-title").textContent = draft.title;
  };
  $("#widget-form").onsubmit = (e) => {
    e.preventDefault();
    if (w.type === 'tachometer') {
      const removed = ['water', 'oil'].every(k => draft.hidden.includes(k));
      const wasRemoved = ['water', 'oil'].every(k => w.hidden.includes(k));
      if (removed !== wasRemoved) {
        for (const axis of ['landscape', 'portrait']) {
          const r = {...getRect(w, page().widgets.indexOf(w), axis)};
          r.h = Math.min(1-r.y, removed ? r.h * .78 : r.h / .78);
          if (rectAllowed(w, r, axis)) w.layouts[axis] = r;
        }
      }
    }
    Object.assign(w, {
      title: draft.title,
      colors: { ...draft.colors },
      hidden: [...draft.hidden],
      shiftLights: { ...draft.shiftLights },
      ...(w.type==='irlogic'?{coachReference:referenceMode(draft.coachReference)}:{}),
    });
    $("#modal").close();
    render();
  };
  $("#cancel-colors").onclick = () => $("#modal").close();
  $("#reset-colors").onclick = () => {
    draft.colors = {};
    for (const input of document.querySelectorAll("[data-color]"))
      input.value = themeColor(activeTheme(state.theme, state.customTheme),input.dataset.color,colorRoles(w.type)[input.dataset.color][1]);
    theme(preview, draft);
    theme(canvas.querySelector(`[data-id="${w.id}"]`), draft);
  };
  $("#remove").onclick = () => {
    page().widgets = page().widgets.filter((x) => x.id !== id);
    page().widgets.forEach((w) => (w.layouts = {}));
    $("#modal").close();
    render();
  };
  paint();
}
$("#add-widget").onclick = () => {
  modal(
    "Add widget",
    `<p class="help">Add to this page. There is no widget-count limit; the selected template expands as needed.</p><div class="catalog">${Object.entries(
      TYPES,
    )
      .map(
        ([key, title]) =>
          `<button class="catalog-card" data-kind="${key}"><strong>${title}</strong><span>Add to current page ＋</span></button>`,
      )
      .join("")}</div>`,
  );
  document.querySelectorAll("[data-kind]").forEach(
    (b) =>
      (b.onclick = () => {
        page().widgets.push(widget(b.dataset.kind));
        page().widgets.forEach((w) => (w.layouts = {}));
        $("#modal").close();
        render();
      }),
  );
};
$("#edit").onclick = () => {
  edit = !edit;
  render();
};
$("#new-page").onclick = () => {
  state.pages.push({
    name: "Page " + (state.pages.length + 1),
    preset: "auto",
    widgets: [],
  });
  state.active = state.pages.length - 1;
  render();
};
function layoutIcon(key) {
  const count = key === "auto" ? 6 : LAYOUTS[key].slots;
  return `<svg viewBox="0 0 100 72" aria-hidden="true">${Array.from(
    { length: count },
    (_, i) => {
      const r = defaultRect(i, count, "landscape", key);
      return `<rect x="${r.x * 94 + 3}" y="${r.y * 66 + 3}" width="${r.w * 94 - 2}" height="${r.h * 66 - 2}" rx="3"/>`;
    },
  ).join("")}</svg>`;
}
function showLayouts() {
  modal(
    "Page layout",
    `<p class="help">Choose a starting arrangement. Every template expands for additional widgets; all widgets stay on this page. Adding widgets reflows the page.</p><div class="layout-gallery">${Object.entries(
      LAYOUTS,
    )
      .map(
        ([key, layout]) =>
          `<button class="layout-choice ${page().preset === key ? "selected" : ""}" data-preset="${key}">${layoutIcon(key)}<strong>${layout.name}</strong><span>${key === "auto" ? "Adapts to orientation" : layout.slots + " starting tile" + (layout.slots === 1 ? "" : "s")}</span></button>`,
      )
      .join("")}</div>`,
  );
  document.querySelectorAll("[data-preset]").forEach(
    (b) =>
      (b.onclick = () => {
        setPreset(state, state.active, b.dataset.preset);
        $("#modal").close();
        render();
        toast("Layout applied. All widgets remain on this page.");
      }),
  );
}
$("#layouts").onclick = showLayouts;
$("#page-options").onclick = () => {
  modal(
    "Page",
    `<form id="page-form"><label>Page name<input name="name" maxlength="80" value="${esc(page().name)}"></label><div class="form-actions"><button type="button" class="button secondary" id="choose-layout">Choose layout</button><button type="button" class="button danger" id="delete-page">Delete page</button><button type="button" class="button secondary" id="reset-layout">Fit widgets to screen</button><button class="button primary">Save</button></div></form>`,
  );
  $("#page-form").onsubmit = (e) => {
    e.preventDefault();
    page().name = new FormData(e.target).get("name") || "Dashboard";
    $("#modal").close();
    render();
  };
  $("#choose-layout").onclick = () => {
    $("#modal").close();
    setTimeout(showLayouts, 0);
  };
  $("#delete-page").disabled = state.pages.length === 1;
  $("#delete-page").onclick = () => {
    state.pages.splice(state.active, 1);
    state.active = 0;
    $("#modal").close();
    render();
  };
  $("#reset-layout").onclick = () => {
    page().widgets.forEach((w) => (w.layouts = {}));
    $("#modal").close();
    render();
  };
};
async function exitFocus() {
  document.body.classList.remove("focus");
  if (document.fullscreenElement)
    await document.exitFullscreen?.().catch(() => {});
  applyLayouts();
}
$("#fullscreen").onclick = () => {
  edit = false;
  render();
  document.body.classList.add("focus");
  applyLayouts();
  try {
    document.documentElement
      .requestFullscreen?.()
      .catch(() =>
        toast(
          "Clean view enabled. This browser does not support native fullscreen.",
        ),
      );
  } catch {}
};
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) exitFocus();
});
document.addEventListener("dblclick", (e) => {
  if (
    document.body.classList.contains("focus") &&
    !e.target.closest("button,input,select,label")
  ) {
    e.preventDefault();
    exitFocus();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.body.classList.contains("focus"))
    exitFocus();
  if ($("#modal").open || e.target.closest("input,select,button") || edit)
    return;
  if (e.key === "ArrowRight") go(state.active + 1);
  if (e.key === "ArrowLeft") go(state.active - 1);
});
let swipe = null,
  lastTap = null;
canvas.addEventListener("pointerdown", (e) => {
  if (edit || gesture || e.target.closest("button,input,select,label")) return;
  swipe = {
    id: e.pointerId,
    x: e.clientX,
    y: e.clientY,
    time: Date.now(),
    type: e.pointerType,
  };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointerup", (e) => {
  if (!swipe || swipe.id !== e.pointerId) return;
  const s = swipe;
  swipe = null;
  if (canvas.hasPointerCapture(e.pointerId))
    canvas.releasePointerCapture(e.pointerId);
  const dx = e.clientX - s.x,
    dy = e.clientY - s.y,
    elapsed = Date.now() - s.time;
  if (
    Math.abs(dx) > 55 &&
    Math.abs(dx) > Math.abs(dy) * 1.6 &&
    elapsed < 1200
  ) {
    lastTap = null;
    go(state.active + (dx < 0 ? 1 : -1));
    return;
  }
  if (
    s.type === "touch" &&
    Math.hypot(dx, dy) < 15 &&
    elapsed < 350 &&
    document.body.classList.contains("focus")
  ) {
    if (
      lastTap &&
      Date.now() - lastTap.time < 380 &&
      Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 40
    ) {
      lastTap = null;
      exitFocus();
    } else lastTap = { x: e.clientX, y: e.clientY, time: Date.now() };
  } else lastTap = null;
});

function driverView() { return data; }
function themeSettings() {
  const palettes = {...THEMES, custom:customTheme(state.customTheme)};
  return `<section class="theme-settings"><h3>Appearance</h3><div class="theme-grid">${Object.entries(palettes).map(([id,p]) => `<button type="button" class="theme-tile" data-theme-choice="${id}" aria-pressed="${state.theme===id}" style="--theme-bg:${p.background};--theme-accent:${p.accent};--theme-text:${p.text}"><span class="theme-swatch"><i></i><i></i><i></i></span><strong>${p.name}</strong></button>`).join('')}</div><details class="custom-theme-editor"><summary>Create your own theme</summary><p class="help">Colors apply to all widgets. Individual widget color overrides take priority.</p>${CUSTOM_THEME_COLORS.map(key=>`<label>${esc(key)}<input type="color" data-custom-color="${key}" value="${customTheme(state.customTheme)[key]}"></label>`).join('')}<label><input type="checkbox" id="custom-light" ${state.customTheme?.light?'checked':''}> Light theme</label><button type="button" class="button secondary" id="custom-from-current">Copy current theme</button></details></section>`;
}
function drivingAlertSettings() {
  const settings=alertSettings(state.alerts);
  const options=(values,current)=>values.map(([value,label])=>`<option value="${value}" ${value===current?'selected':''}>${label}</option>`).join('');
  return `<section id="driving-alert-settings" class="driving-alert-settings"><h3>Race flags</h3>
    <label>Flag display<select id="alert-flag-mode">${options([['off','Off'],['flash','Full-screen flashing'],['center','Small flag in the center']],settings.flags.mode)}</select></label>
    <label>Small flag animation<select id="alert-flag-animation" ${settings.flags.mode!=='center'?'disabled':''}>${options([['steady','Steady'],['blink','Blinking']],settings.flags.blink?'blink':'steady')}</select></label>
    <label>Show flag<select id="alert-flag-visibility">${options([['timed','For the selected number of seconds'],['active','While the flag is active in game']],settings.flags.untilClear?'active':'timed')}</select></label>
    <label>Display time · seconds<input id="alert-flag-duration" type="number" min="1" max="10" step="1" value="${settings.flags.duration}" ${settings.flags.untilClear?'disabled':''}></label>
    <label>Flag opacity <output id="alert-flag-opacity-value">${Math.round(settings.flags.opacity*100)}%</output><input id="alert-flag-opacity" type="range" min="10" max="100" step="5" value="${settings.flags.opacity*100}"></label>
    <p class="help">Timed alerts appear once when the active flag changes. Choose which race-control flags to display:</p>
    <fieldset class="race-flag-options"><legend>Flags to show</legend>${RACE_FLAGS.map(flag=>`<label><input type="checkbox" data-race-flag="${flag.name}" ${settings.flags.enabled[flag.name]?'checked':''}>${flag.label}</label>`).join('')}</fieldset>
    <h3>On-screen spotter</h3><label>Spotter display<select id="alert-spotter-mode">${options([['off','Off'],['halves','Orange screen halves'],['bars','Narrow orange side bars']],settings.spotter.mode)}</select></label>
    <label>Spotter opacity <output id="alert-spotter-opacity-value">${Math.round(settings.spotter.opacity*100)}%</output><input id="alert-spotter-opacity" type="range" min="10" max="100" step="5" value="${settings.spotter.opacity*100}"></label>
    <p class="help">The left or right side lights up while iRacing reports a car alongside. Both sides can be active. Works without adding a radar widget.</p></section>`;
}
function wireDrivingAlertSettings() {
  $('#driving-alert-settings').querySelectorAll('input,select').forEach(input=>input.addEventListener('input',()=>{
    state.alerts=alertSettings({
      flags:{mode:$('#alert-flag-mode').value,duration:$('#alert-flag-duration').valueAsNumber,
        opacity:$('#alert-flag-opacity').valueAsNumber/100,
        blink:$('#alert-flag-animation').value==='blink',untilClear:$('#alert-flag-visibility').value==='active',
        enabled:Object.fromEntries(RACE_FLAGS.map(flag=>[flag.name,$(`[data-race-flag="${flag.name}"]`).checked]))},
      spotter:{mode:$('#alert-spotter-mode').value,opacity:$('#alert-spotter-opacity').valueAsNumber/100},
    });
    $('#alert-flag-opacity-value').textContent=`${Math.round(state.alerts.flags.opacity*100)}%`;
    $('#alert-spotter-opacity-value').textContent=`${Math.round(state.alerts.spotter.opacity*100)}%`;
    $('#alert-flag-animation').disabled=state.alerts.flags.mode!=='center';
    $('#alert-flag-duration').disabled=state.alerts.flags.untilClear;
    save();paint();
  }));
}
$("#settings").onclick = () => {
  const layoutHelp = 'Layouts, sizes, colors and visibility synchronize automatically between paired devices. Pair another device using the QR or six-digit code shown on the server computer.';
  modal(
    "Settings and backup",
    '<p class="help">' + layoutHelp + ' Use ⛶ for fullscreen; double-tap a free area or press Escape to exit. Swipe left or right to switch pages.</p><div class="form-actions"><button class="button secondary" id="export">Export layout</button><button class="button secondary" id="export-conflict">Export conflict backup</button><label class="button secondary">Import<input id="import" type="file" accept="application/json" hidden></label></div>' + drivingAlertSettings() + themeSettings(),
  );
  wireDrivingAlertSettings();
  document.querySelectorAll('[data-theme-choice]').forEach(button => button.onclick = () => {
    state.theme=button.dataset.themeChoice;
    applyTheme(state.theme, state.customTheme); save(); paint();
    document.querySelectorAll('[data-theme-choice]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
  });
  const refreshCustom = () => {
    state.customTheme = customTheme(state.customTheme);
    state.theme = 'custom';
    applyTheme(state.theme, state.customTheme); save(); paint();
    document.querySelectorAll('[data-theme-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.themeChoice==='custom')));
    const tile = $('[data-theme-choice=custom]');
    tile.style.setProperty('--theme-bg',state.customTheme.background);
    tile.style.setProperty('--theme-accent',state.customTheme.accent);
    tile.style.setProperty('--theme-text',state.customTheme.text);
  };
  document.querySelectorAll('[data-custom-color]').forEach(input=>input.oninput=()=>{
    state.customTheme ||= customTheme();
    state.customTheme[input.dataset.customColor]=input.value; refreshCustom();
  });
  $('#custom-light').onchange=()=>{state.customTheme ||= customTheme(); state.customTheme.light=$('#custom-light').checked; refreshCustom();};
  $('#custom-from-current').onclick=()=>{
    state.customTheme=customTheme(activeTheme(state.theme,state.customTheme));
    document.querySelectorAll('[data-custom-color]').forEach(input=>input.value=state.customTheme[input.dataset.customColor]);
    $('#custom-light').checked=state.customTheme.light; refreshCustom();
  };
  $("#export").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(
      new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }),
    );
    a.download = "irboard.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  $('#export-conflict').disabled = !localStorage.getItem('irboard-conflict-backup');
  $('#export-conflict').onclick = () => {
    const backup = localStorage.getItem('irboard-conflict-backup');
    if (!backup) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([backup], {type:'application/json'}));
    a.download = 'irboard-conflict-backup.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  $("#import").onchange = async (e) => {
    try {
      const file = e.target.files[0];
      if (file.size > 1024 * 1024) throw Error("File too large");
      state = migrate(JSON.parse(await file.text()));
      $("#modal").close();
      render();
      toast("Layout imported");
    } catch {
      toast("Invalid layout file");
    }
  };
};
function authHeaders() {
  return {}; // Browser authorization uses the HttpOnly paired-device cookie.
}
function loadPitForm(form) {
  const p = data?.pit;
  if (!p?.available) return;
  ["lf", "rf", "lr", "rr"].forEach((k, i) => {
    form.elements[k].checked = !!(p.flags & (1 << i));
    form.elements[k + "_pressure"].value = p.pressures?.[k]
      ? Math.round(p.pressures[k])
      : "";
  });
  // Fuel is always derived from current telemetry, never copied from a manual selection.
  form.elements.windshield.checked = !!(p.flags & 32);
  form.elements.fast_repair.checked = !!(p.flags & 64);
  updatePitCompounds(form, p);
  form.elements.compound.value = p.compounds?.some(c => c.index === p.compound) ? String(p.compound) : "";
}
function updatePitCompounds(form, pit) {
  const select = form.elements.compound;
  const compounds = Array.isArray(pit?.compounds) ? pit.compounds : [];
  const signature = JSON.stringify(compounds);
  if (select.dataset.compounds !== signature) {
    const selected = select.value;
    select.replaceChildren();
    const keep = document.createElement("option");
    keep.value = "";
    keep.textContent = compounds.length ? "Keep current" : "Compound selection unavailable";
    select.append(keep);
    for (const compound of compounds) {
      const option = document.createElement("option");
      option.value = String(compound.index);
      option.textContent = compound.name;
      select.append(option);
    }
    select.value = compounds.some(c => String(c.index) === selected) ? selected : "";
    select.dataset.compounds = signature;
  }
  select.disabled = compounds.length === 0;
  select.dataset.unavailable = compounds.length === 0 ? "1" : "0";
}
function updateFuelEstimate(form) {
  const selectedTarget = form.elements.fuel_target.value;
  const target = selectedTarget === 'stint' ? form.elements.fuel_stint_unit.value : 'finish';
  form.querySelector('.stint-length').hidden = selectedTarget !== 'stint';
  const estimate = fuelEstimate(data, {target, amount:Number(form.elements.stint_length.value),
    reserve:Number(form.elements.fuel_reserve.value)});
  form.elements.fuel.value = estimate.available ? estimate.add : 0;
  form.querySelector('.calculated-fuel').textContent = estimate.available ? `${estimate.add} L · calculated` : 'Fuel estimate unavailable';
  const status = form.querySelector('.fuel-estimate');
  status.textContent = estimate.available ?
    `${estimate.basis} · Add ${estimate.add} L · ${estimate.perLap.toFixed(2)} L/lap` +
    (estimate.limited ? ` · Another stop needed: ${estimate.shortfall.toFixed(1)} L short` : '') +
    (!estimate.capacityKnown ? ' · Tank capacity unavailable' : '') : estimate.reason;
  form.querySelector('.fuel-calculate').disabled = !estimate.available || !data?.connected;
  return estimate;
}
function wirePit(form) {
  let editRevision = 0;
  const markEdited = () => { form.dataset.dirty = "1"; editRevision++; };
  form.addEventListener("input", markEdited);
  form.addEventListener("change", markEdited);
  for (const [attribute, field] of [['fuelTarget','fuel_target'],['stintUnit','fuel_stint_unit']]) {
    const selector = attribute === 'fuelTarget' ? '[data-fuel-target]' : '[data-stint-unit]';
    form.querySelectorAll(selector).forEach(button => button.onclick = () => {
      form.elements[field].value = button.dataset[attribute];
      form.querySelectorAll(selector).forEach(other => other.setAttribute('aria-pressed', String(other === button)));
      markEdited();
      updateFuelEstimate(form);
    });
  }
  form.querySelectorAll('[data-number-field]').forEach(button => button.onclick = () => {
    const field = form.elements[button.dataset.numberField];
    if (field.disabled) return;
    let current = field.value === '' ? NaN : Number(field.value);
    if (!Number.isFinite(current)) {
      current = data?.pit?.pressures?.[field.name.split('_')[0]];
    }
    const minimum = Number(field.min || 0), maximum = Number(field.max || 1000);
    const step = Number(field.step || 1);
    const base = Number.isFinite(current) ? current : minimum;
    field.value = Number(clamp(base + Number(button.dataset.direction) * step, minimum, maximum).toFixed(2));
    markEdited();
    updateFuelEstimate(form);
  });
  form
    .querySelectorAll("[data-tires]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          markEdited();
          ["lf", "rf", "lr", "rr"].forEach(
            (k) => (form.elements[k].checked = b.dataset.tires === "all"),
          );
        }),
    );
  form.querySelector('.fuel-calculate').onclick = () => {
    const estimate = updateFuelEstimate(form);
    if (!estimate.available) return;
    form.elements.fuel.value = estimate.add;
    markEdited();
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (form.dataset.busy) return;
    const estimate = updateFuelEstimate(form);
    const f = new FormData(form),
      tires = {};
    for (const k of ["lf", "rf", "lr", "rr"])
      if (f.has(k))
        tires[k] =
          f.get(k + "_pressure") === "" ? 0 : Number(f.get(k + "_pressure"));
    const plan = {
      tires,
      fuel: estimate.available ? estimate.add : 0,
      windshield: f.has("windshield"),
      fast_repair: f.has("fast_repair"),
      compound: !f.has("compound") || f.get("compound") === "" ? null : Number(f.get("compound")),
    };
    const current = data?.pit,
      hidden = new Set(
        page().widgets.find(
          (w) => w.id === form.closest("[data-id]").dataset.id,
        )?.hidden || [],
      );
    if (current?.available) {
      if (hidden.has("tires")) {
        plan.tires = {};
        ["lf", "rf", "lr", "rr"].forEach((k, i) => {
          if (current.flags & (1 << i)) plan.tires[k] = 0;
        });
      }
      if (hidden.has("pressures"))
        for (const k of Object.keys(plan.tires)) plan.tires[k] = 0;
      if (hidden.has("compound")) plan.compound = current.compound ?? null;
      if (hidden.has("windshield")) plan.windshield = !!(current.flags & 32);
      if (hidden.has("fast_repair")) plan.fast_repair = !!(current.flags & 64);
    }
    const status = form.querySelector(".pit-result");
    const submittedRevision = editRevision;
    form.dataset.busy = "1";
    form.querySelector(".pit-apply").disabled = true;
    status.textContent = "Sending plan…";
    try {
      const r = await fetch("/api/pit", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(plan),
        signal: AbortSignal.timeout(6500),
      });
      const response = await r.json();
      if (!r.ok) throw Error(response.error || "SDK error");
      status.textContent = response.status === "sent" ? "Pit plan sent. Waiting for game updates." : response.message;
      if (response.status === "sent" && editRevision === submittedRevision) {
        delete form.dataset.dirty;
        form.dataset.followAfter = String(data.timestamp);
        form.dataset.following = "1";
      }
    } catch (error) {
      status.textContent =
        error.name === "TimeoutError"
          ? "Outcome unknown. Check the plan in the game; requests are not retried automatically."
          : error.message;
    } finally {
      delete form.dataset.busy;
      form.querySelector(".pit-apply").disabled =
        !data?.pit?.can_control || data.access?.can_control === false;
    }
  };
}
function paint() {
  if (!data) return;
  const fresh = data.connected && (data.sample_age || 0) + (performance.now() - receivedAt) / 1000 < 4;
  $("#source-status").textContent = !fresh
    ? "OFFLINE"
    : data.mode === "demo"
      ? "DEMO"
      : "SDK LIVE";
  $("#source-status").className =
    "badge " + (!fresh ? "waiting" : data.mode === "demo" ? "demo" : "live");
  $("#focus-status").textContent = !fresh
    ? "NO TELEMETRY"
    : data.mode === "demo"
      ? "DEMO · SIMULATION"
      : "";
  $("#focus-status").classList.toggle("offline", !fresh);
  drivingAlerts.update(data,state.alerts,fresh);
  $("#connection-banner").hidden = fresh;
  $("#connection-banner").textContent = data.message;
  for (const el of canvas.querySelectorAll(".widget")) {
    const w = page().widgets.find((w) => w.id === el.dataset.id),
      body = el.querySelector(".widget-body");
    let restoreRaceScroll=null;
    theme(el, colorDraft?.id === w.id ? colorDraft : w);
    if (w.type === "pit") {
      if (!body.querySelector("form")) {
        body.innerHTML = pitForm();
        const form = body.querySelector("form");
        wirePit(form);
        loadPitForm(form);
      }
      const form = body.querySelector("form");
      updatePitCompounds(form, data.pit);
      // Follow actual SDK selections after Apply and after service completion.
      // Unsaved edits remain untouched until Apply or Read from game.
      if (!form.dataset.busy && !form.dataset.dirty && fresh && data.pit?.available &&
          (!form.dataset.followAfter || data.timestamp > Number(form.dataset.followAfter))) {
        loadPitForm(form);
        delete form.dataset.followAfter;
        if (form.dataset.following && data.mode !== "demo") {
          const result = form.querySelector(".pit-result");
          if (data.pit.status === 1) result.textContent = "Pit service in progress. Selections follow the game.";
          else if (data.pit.status === 2) result.textContent = "Pit service completed. Selections updated from the game.";
          else result.textContent = "Live pit plan loaded from the game. Check the service readback.";
        }
      }
      form.querySelector(".pit-readback").innerHTML = pitReadback({
        ...data.pit,
        demo: data.mode === "demo",
      });
      form.querySelector(".pit-apply").disabled =
        !!form.dataset.busy ||
        !fresh ||
        !data.pit?.can_control ||
        data.access?.can_control === false;
      updateFuelEstimate(form);
      if (data.access?.can_control === false && !form.dataset.busy)
        form.querySelector(".pit-result").textContent =
          "Pair this device using the QR or six-digit code on the server computer.";
    } else if (EXPERIMENTAL_TYPES.includes(w.type) && fresh && !gesture) {
      refreshExperimental(body,w.type,driverView(),colorDraft?.id===w.id?colorDraft:w);
    } else if (w.type === "tachometer" && fresh && !gesture) {
      if (!body.querySelector('.tachometer-panel')) body.innerHTML = content(w.type, driverView());
      updateTachometer(body, data.car, colorDraft?.id === w.id ? colorDraft.shiftLights : w.shiftLights, data.session);
    } else if (fresh && !gesture && w.type === 'inputs') {
      refreshInputs(body,content(w.type,driverView()));
    } else if (fresh && !gesture && ['standings','relative'].includes(w.type)) {
      restoreRaceScroll=refreshRaceTable(body,content(w.type,driverView()));
    } else if (!gesture) {
      const scroll = body.scrollTop;
      body.innerHTML = fresh
        ? content(w.type, driverView())
        : '<p class="hint" data-role="label">No current telemetry. ' +
          esc(data.message) +
          "</p>";
      body.scrollTop = scroll;

    }
    applyVisibility(el, colorDraft?.id === w.id ? colorDraft : w);
    restoreRaceScroll?.();
    if (['standings','relative'].includes(w.type) && !gesture) {
      if (!body.dataset.raceFollowEvents) {
        body.dataset.raceFollowEvents='1';
        const pauseFollow=()=>{body.dataset.followPausedUntil=String(performance.now()+15000);};
        for (const event of ['wheel','touchstart','touchmove','touchend','pointerdown']) body.addEventListener(event,pauseFollow,{passive:true});
      }
      const centerKey=String(data.session?.key||data.mode||'live')+'/'+String(data.session?.focus_idx??'player');
      if (!fresh) delete body.dataset.raceCentered;
      else {
        if (body.dataset.raceCentered!==centerKey) {
          body.dataset.raceCentered=centerKey;
          delete body.dataset.followPausedUntil;
        }
        const own=body.querySelector('tr.me');
        if (own && performance.now()>=Number(body.dataset.followPausedUntil||0)) {
          const offset=own.getBoundingClientRect().top-body.getBoundingClientRect().top+body.scrollTop;
          body.scrollTop=Math.max(0,offset-body.clientHeight/2+own.offsetHeight/2);
        }
      }
    }
  }
  if (colorDraft) {
    const preview = $(".preview");
    if (preview) {
      theme(preview, colorDraft);
      const previewBody = preview.querySelector('.widget-body');
      if (colorDraft.type === 'tachometer') {
        if (!previewBody.querySelector('.tachometer-panel')) previewBody.innerHTML = content(colorDraft.type, driverView());
        updateTachometer(previewBody, data.car, colorDraft.shiftLights, data.session);
      } else if(EXPERIMENTAL_TYPES.includes(colorDraft.type)) refreshExperimental(previewBody,colorDraft.type,driverView(),colorDraft);
      else previewBody.innerHTML = colorDraft.type === 'pit' ? pitForm(true) : content(colorDraft.type, driverView());
      applyVisibility(preview, colorDraft);
    }
  }
}
async function poll() {
  const started = performance.now();
  let interval=50;
  try {
    const types = new Set(page().widgets.map(w => w.type));
    if (colorDraft) types.add(colorDraft.type);
    const sections = [];
    if (types.has("inputs")) sections.push("trace");
    if (types.has("inspector")) sections.push("raw");
    if (types.has("inspector")) interval=250;
    if (types.has("learnedmap")) sections.push("track_map");
    if (types.has('irlogic')) { sections.push('coaching'); if(interval<100)interval=100; }
    const r = await fetch("/api/telemetry", {
      headers: { ...authHeaders(), "X-IRBOARD-Sections": sections.join(",") },
      signal: AbortSignal.timeout(3000),
    });
    if (r.status === 401) { polling = false; location.replace('/auth'); return; }
    if (!r.ok) throw Error('Server error');
    data = await r.json();
    receivedAt = performance.now();
    paint();
  } catch (error) {
    data = {
      mode: data?.mode || "live",
      connected: false,
      message: error.message,
      timestamp: Date.now() / 1000,
      car: {},
      session: {},
      drivers: [],
      fuel: {},
      history: [],
      trace: [],
      reference: [],
      raw: {},
      pit: {},
    };
    paint();
  }
  // One request at a time: no queue of stale frames on a slow Wi-Fi link.
  if (polling) setTimeout(poll, document.hidden ? 1500 : Math.max(0, interval - (performance.now() - started)));
}
// Persist final browser edits even when its tab closes before the next poll.
window.addEventListener('pagehide', () => {
  if (sharedRevision === null || syncApplying) return;
  const layout = sharedLayout();
  if (JSON.stringify(layout) === sharedSignature) return;
  fetch('/api/layout', {
    method:'POST', headers:{...authHeaders(), 'Content-Type':'application/json'},
    body:JSON.stringify({revision:sharedRevision, layout}), keepalive:true,
  }).catch(() => {}); // The local browser copy remains available if the server has stopped.
});
render();
syncLayout().finally(() => {
  poll();
  setInterval(syncLayout, 1000);
});
