export const esc = (v) =>
  String(v ?? "—").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const n = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";
export const scaled = (v, k) => (typeof v === "number" ? v * k : null);
export const time = (v) => {
  if (typeof v !== 'number' || !Number.isFinite(v) || v<=0 || v>=1e6) return '—';
  const milliseconds=Math.round(v*1000);
  return `${Math.floor(milliseconds/60000)}:${((milliseconds%60000)/1000).toFixed(3).padStart(6,'0')}`;
};
export const colored = (role, value, tag = "span", cls = "") =>
  `<${tag} data-role="${role}" data-element="${role}" class="${cls}" style="color:var(--c-${role},var(--c-text))">${value}</${tag}>`;
