// Palettes are defaults; explicit per-widget colors always take precedence.
const palette = (name,bg,background,text,label,border,accent,light=false) => ({name,bg,background,text,label,border,accent,light,title:text});
export const THEMES = {
  original: palette('Original','#101216','#191c22','#f1f3f7','#8c929f','#2a2e36','#c3f35c'),
  carbon: palette('Carbon','#08090b','#141619','#f4f4f5','#9c9ca5','#303237','#ededed'),
  blue: palette('Circuit Blue','#080f1d','#121f35','#e7f1ff','#91a9ca','#294463','#52adff'),
  scarlet: palette('Scarlet','#160b0e','#26151b','#fff0f3','#c59ca6','#512b36','#ff657b'),
  violet: palette('Violet','#100d1d','#201a33','#f3edff','#ada0cb','#44365f','#bc96ff'),
  teal: palette('Teal','#081714','#122a25','#e8fff7','#91baae','#2a5047','#5ee6bc'),
  amber: palette('Amber','#191309','#2b2214','#fff5e0','#c4ae81','#544326','#ffc44a'),
  ice: palette('Ice','#0b151c','#182933','#ecfbff','#92b2c2','#304f61','#8ee5ff'),
  midnight: palette('Midnight','#070a14','#11172a','#e7edff','#879ac2','#28375b','#739bff'),
  light: palette('Daylight','#e7ecf2','#ffffff','#172338','#5b6b80','#cbd4e0','#286b21',true),
  forest: palette('Forest','#07140d','#12251a','#eaffef','#9db5a4','#2b4936','#70db8c'),
  copper: palette('Copper','#17100c','#2b2019','#fff1e8','#c3a58f','#593e2b','#e99d64'),
  ocean: palette('Ocean','#05151c','#0c2934','#e0faff','#88b5c2','#23515e','#30cfeb'),
  rose: palette('Rose','#1d1017','#311e29','#ffedf6','#c69bb2','#604054','#ff9acb'),
  lime: palette('Lime','#111608','#232c14','#f2ffe0','#aabd87','#455a2b','#b7ee41'),
  sunset: palette('Sunset','#1a0b15','#30182b','#ffeefa','#c39bb9','#60304e','#ff995d'),
  cobalt: palette('Cobalt','#080e2a','#141e43','#ebefff','#9aa9d0','#30477c','#7095ff'),
  sand: palette('Sand','#eee5d4','#fff9eb','#342c1e','#76664a','#d1bf9f','#8c5f12',true),
  paper: palette('Paper','#f1f1ed','#ffffff','#242821','#687063','#cdd1c7','#437c31',true),
  arctic: palette('Arctic','#e6f4fa','#fbfeff','#132e3b','#4c7081','#bed8e5','#126c9c',true),
  plum: palette('Plum','#180d22','#2c193b','#f8eaff','#baa0ca','#533465','#d299ef'),
  mint: palette('Mint','#e2f4ed','#f7fffa','#163a2b','#527966','#b6d7c6','#147b52',true),
  racingRed: palette('Racing Red','#150607','#290e11','#fff1f1','#c29396','#63262e','#ff3e4c'),
  gold: palette('Gold','#15120a','#292316','#fff6d9','#c3b287','#594c2c','#eec65b'),
  graphite: palette('Graphite','#121416','#24272b','#f1f3f5','#a3aab2','#454c55','#9bb4cf'),
  lavender: palette('Lavender','#eee9fa','#fbf8ff','#302547','#78658e','#d2c5e5','#7852bc',true),
  turbo: palette('Turbo','#080f0d','#13221b','#edfff5','#8fad9a','#2f4f3c','#00ed96'),
  neon: palette('Neon','#10091a','#21132e','#faecff','#b69ac7','#523268','#f049ed'),
  steel: palette('Steel','#0f1720','#202d3b','#edf5ff','#9baebf','#40566c','#7ab9ed'),
  espresso: palette('Espresso','#160f0b','#2b211b','#fff4e8','#bfa792','#544134','#d9ac7a'),
};
THEMES.original.title = '#b2b8c5';
export const CUSTOM_THEME_COLORS = ['bg','background','text','label','title','border','accent','positive','negative'];
export function customTheme(value = {}) {
  const result = {...THEMES.original, positive:'#72df9b', negative:'#ff747b', name:'Custom', light:!!value?.light};
  for (const key of CUSTOM_THEME_COLORS)
    if (/^#[0-9a-f]{6}$/i.test(value?.[key] || '')) result[key] = value[key];
  return result;
}
export const activeTheme = (id, custom) => id === 'custom' ? customTheme(custom) : Object.hasOwn(THEMES,id) ? THEMES[id] : THEMES.original;
export function themeColor(palette, key, fallback) {
  if (key in palette) return palette[key];
  if (palette.light && key === 'irating') return '#1c5fab';
  if (palette.light && key === 'buttonText') return '#ffffff';
  if (palette.light && fallback === '#72df9b') return '#18763e';
  if (palette.light && fallback === '#ff747b') return '#b52c39';
  const aliases={'#c3f35c':'accent','#f1f3f7':'text','#8c929f':'label','#191c22':'background','#2a2e36':'border'};
  return palette[aliases[fallback]] || fallback;
}
export function applyTheme(id, custom) {
  const p=activeTheme(id, custom),root=document.documentElement;
  root.dataset.theme=id === 'custom' || Object.hasOwn(THEMES,id)?id:'original';
  root.style.colorScheme=p.light?'light':'dark';
  for (const [css,key] of Object.entries({bg:'bg',panel:'background',line:'border',muted:'label',text:'text',accent:'accent'}))
    root.style.setProperty('--'+css,p[key]);
}
