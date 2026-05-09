// 한 CSV 에서 XL 사탕 우선순위 Top 30 + 20km 파트너 Top 20
const fs = require('fs');
const path = require('path');
const ROOT = path.dirname(path.dirname(__filename));

const csvPath = process.argv[2] || path.join(ROOT, 'scripts', 'calcy_adb', 'history.csv');
const html = fs.readFileSync(path.join(ROOT, 'out', 'index.html'), 'utf8');
const dataMatch = html.match(/<script id="data" type="application\/json">([\s\S]+?)<\/script>/);
const DATA = JSON.parse(dataMatch[1].replace(/<\\\//g, '</'));
const scripts = [...html.matchAll(/<script>([\s\S]+?)<\/script>/g)];
const mainJs = scripts[scripts.length - 1][1];

function extract(name) {
  const re = new RegExp(`function ${name}\\s*\\([^)]*\\)\\s*\\{`, 'g');
  const m = re.exec(mainJs); if (!m) return null;
  let depth = 1, i = m.index + m[0].length, start = m.index;
  while (depth && i < mainJs.length) { const c = mainJs[i]; if (c === '{') depth++; else if (c === '}') depth--; i++; }
  return mainJs.slice(start, i);
}

global.DATA = DATA;
global.GL_KEYS = new Set(['all_1500','premier_1500','classic_1500']);
global.UL_KEYS = new Set(['all_2500','premier_2500','classic_2500']);
global.ML_KEYS = new Set(['all_10000','premier_10000','classic_10000']);
global.LC_KEYS = new Set(['all_500','little_500','premier_500','classic_500']);
global.ACTIVE_CUPS = new Set();

const need = ['statProductAt','maxLevelForCP','leagueScore','bestRankIn','bestRaidRank'];
const code = need.map(n => extract(n)).filter(Boolean).join('\n\n');
eval(code.replace(/^function (\w+)\s*\(/gm, 'global.$1 = function ('));

// 20km 종 — HTML 안에 정의된 const 추출 (regex 로)
const tkmMatch = mainJs.match(/const TWENTY_KM_SIDS = new Set\(\[([\s\S]+?)\]\)/);
const TWENTY_KM_SIDS = new Set();
if (tkmMatch) {
  const sids = [...tkmMatch[1].matchAll(/'([^']+)'/g)].map(m => m[1]);
  for (const s of sids) TWENTY_KM_SIDS.add(s);
}

// CSV 파싱
const text = fs.readFileSync(csvPath, 'utf8');
const lines = text.replace(/﻿/g,'').split(/\r?\n/);
function splitCsv(line) {
  const out = []; let cur=''; let q=false;
  for (let i=0;i<line.length;i++){const c=line[i];
    if (c==='"') q=!q;
    else if (c===',' && !q){out.push(cur.trim());cur='';}
    else cur+=c;}
  out.push(cur.trim()); return out;
}
const headers = splitCsv(lines[0]);
const norm = headers.map(h => h.toLowerCase().replace(/ø/g,'avg ').replace(/\s+/g,' ').trim());
function find(aliases){
  for (const a of aliases){const i = norm.indexOf(a.toLowerCase()); if (i>=0) return i;}
  for (let i=0;i<norm.length;i++) for (const a of aliases){const al=a.toLowerCase();
    if (norm[i] === al || (norm[i].includes(al) && norm[i].length < al.length+8)) return i;}
  return -1;
}
const cols = {
  name: find(['name','이름']), form: find(['form']),
  atk: find(['avg att iv','avg att']), def: find(['avg def iv','avg def']),
  sta: find(['avg hp iv','avg hp','sta iv']),
  level: find(['lvl','level']), shadow: find(['shadowform','shadow']),
  lucky: find(['lucky?','lucky']),
};

// matchSpecies 단순 버전
const NAME_INDEX = {};
function add(k, sid){if (!k) return; const lk=String(k).toLowerCase().trim();
  if (!NAME_INDEX[lk]) NAME_INDEX[lk]=sid;
  const np=lk.replace(/[()]/g,' ').replace(/\s+/g,' ').trim(); if (!NAME_INDEX[np]) NAME_INDEX[np]=sid;}
for (const sp of Object.values(DATA.species)) {
  add(sp.ko, sp.id); add(sp.en, sp.id); add(sp.id, sp.id);
  for (const k of (sp.chain_ko||[])) add(k, sp.id);
  for (const e of (sp.chain_en||[])) add(e, sp.id);
}
for (const gk of ['transfer_groups','mega_keep_groups','mega_possible_groups']) {
  for (const g of (DATA[gk]||[])) for (const m of (g.members||[])) {
    add(m.ko, m.sid); add(m.en, m.sid); add(m.sid, m.sid);
  }
}

const results = [];
let unmatched = 0;
for (let i=1;i<lines.length;i++) {
  const line = lines[i]; if (!line.trim()) continue;
  const r = splitCsv(line);
  if (r.length <= cols.name) continue;
  let name = r[cols.name];
  if (!name) continue;
  name = name.replace(/\s*[♀♂]\s*/g,' ').replace(/\s+(XXL|XXS|XL|XS|M|S|L)\s*$/i,'').replace(/[★☆"']/g,'').replace(/\s+/g,' ').trim();
  const cleaned = name.replace(/\s*\([^)]*\)/g,'').trim();
  const sid = NAME_INDEX[name.toLowerCase()] || NAME_INDEX[cleaned.toLowerCase()];
  if (!sid) { unmatched++; continue; }
  const sp = DATA.species[sid];
  if (!sp) { unmatched++; continue; }
  const ivA = parseInt(r[cols.atk]), ivD = parseInt(r[cols.def]), ivS = parseInt(r[cols.sta]);
  if (isNaN(ivA)||isNaN(ivD)||isNaN(ivS)) continue;
  const lv = parseFloat(r[cols.level]) || 30;
  const lucky = cols.lucky>=0 && /^(yes|true|1|y|럭키)$/i.test(r[cols.lucky]||'');
  const isHundo = ivA===15 && ivD===15 && ivS===15;
  const ml = bestRankIn(sp, ML_KEYS);
  const raid = bestRaidRank(sp);
  let xl = 0; const why = [];
  if (isHundo) { xl += 100; why.push('🏆 백개체'); }
  if (ivA === 15) { xl += 30; why.push('ATK15'); }
  if (ml && ml.rank <= 5) { xl += 80 - ml.rank * 5; why.push(`ML #${ml.rank}`); }
  else if (ml && ml.rank <= 15) { xl += 40 - ml.rank * 2; why.push(`ML #${ml.rank}`); }
  if (raid && raid.rank <= 3) { xl += 50 - raid.rank * 5; why.push(`vs ${raid.boss_ko}#${raid.rank}`); }
  else if (raid && raid.rank <= 8) { xl += 25; why.push(`레이드 #${raid.rank}`); }
  if (lucky) { xl += 20; why.push('🍀 Lucky'); }
  const is20km = TWENTY_KM_SIDS.has(sid) || sp.is_legendary;
  if (xl > 0 || is20km) {
    results.push({sid, ko: sp.ko, en: sp.en, ivA, ivD, ivS, lv, lucky, isHundo,
      mlRank: ml?.rank, raidRank: raid?.rank, raidBossKo: raid?.boss_ko, xl, why, is20km});
  }
}

console.log(`\n=== ${csvPath.split(/[\\/]/).pop()} — 분석 ${results.length}/${lines.length-1} (실패 ${unmatched}) ===\n`);

const top = [...results].filter(r => r.xl >= 30).sort((a,b) => b.xl - a.xl).slice(0, 30);
console.log(`🍬 XL 사탕 우선순위 Top 30:`);
console.log(`${'#'.padStart(3)} ${'점수'.padStart(4)} ${'포켓몬'.padEnd(28)} ${'IV'.padEnd(11)} 20km  이유`);
top.forEach((r, i) => {
  const km = r.is20km ? '🚶 ' : '   ';
  const iv = `${r.ivA}/${r.ivD}/${r.ivS}`;
  console.log(`${String(i+1).padStart(3)} ${String(r.xl).padStart(4)} ${r.ko.padEnd(28)} ${iv.padEnd(11)} ${km}  ${r.why.join(' · ')}`);
});

const km20 = results.filter(r => r.is20km).sort((a,b) => b.xl - a.xl).slice(0, 30);
console.log(`\n🚶 박스 20km 파트너 후보 Top 30 (걸으면 XL 사탕):`);
console.log(`${'#'.padStart(3)} ${'점수'.padStart(4)} ${'포켓몬'.padEnd(28)} ${'IV'.padEnd(11)} ML  레이드`);
km20.forEach((r, i) => {
  const iv = `${r.ivA}/${r.ivD}/${r.ivS}`;
  const ml = r.mlRank ? '#'+r.mlRank : '—';
  const raid = r.raidRank ? '#'+r.raidRank : '—';
  console.log(`${String(i+1).padStart(3)} ${String(r.xl).padStart(4)} ${r.ko.padEnd(28)} ${iv.padEnd(11)} ${ml.padEnd(4)} ${raid}`);
});
