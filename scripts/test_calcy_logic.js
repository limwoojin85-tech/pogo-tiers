// HTML 안의 JS 분석 로직을 추출해서 merged CSV 로 직접 테스트
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(path.dirname(__filename));
const html = fs.readFileSync(path.join(ROOT, 'out', 'index.html'), 'utf8');

// embedded data 추출
const dataMatch = html.match(/<script id="data" type="application\/json">([\s\S]+?)<\/script>/);
const DATA = JSON.parse(dataMatch[1].replace(/<\\\//g, '</'));

// 메인 JS 추출 — 마지막 <script> 블록
const scripts = [...html.matchAll(/<script>([\s\S]+?)<\/script>/g)];
const mainJs = scripts[scripts.length - 1][1];

// 헬퍼 — Set 처럼 보이는 KEYS 도 사용 가능하게
global.DATA = DATA;
global.GL_KEYS = new Set(['all_1500', 'premier_1500', 'classic_1500']);
global.UL_KEYS = new Set(['all_2500', 'premier_2500', 'classic_2500']);
global.ML_KEYS = new Set(['all_10000', 'premier_10000', 'classic_10000']);
global.LC_KEYS = new Set(['all_500', 'little_500', 'premier_500', 'classic_500']);

// JS 안의 함수들이 DOM 의존이 좀 있어서 직접 실행은 위험.
// 대신 핵심 함수만 추출해서 평가.
// analyzeOne, classifyBucket, leagueScore, maxLevelForCP, bestRankIn, statProductAt 만 필요.

const fns = {};
function extract(name) {
  const re = new RegExp(`function ${name}\\s*\\([^)]*\\)\\s*\\{`, 'g');
  const m = re.exec(mainJs);
  if (!m) return null;
  let depth = 1, i = m.index + m[0].length;
  const start = m.index;
  while (depth && i < mainJs.length) {
    const c = mainJs[i];
    if (c === '{') depth++;
    else if (c === '}') depth--;
    i++;
  }
  return mainJs.slice(start, i);
}

const need = ['statProductAt','maxLevelForCP','leagueScore','bestRankIn','bestRaidRank','analyzeOne','classifyBucket'];
const code = need.map(n => extract(n)).filter(Boolean).join('\n\n');
// eval 에서 함수 정의를 글로벌에 노출
// 함수를 global 에 노출 — `function NAME(args){...}` → `global.NAME = function(args){...}`
const exposed = code.replace(/^function (\w+)\s*\(/gm, 'global.$1 = function (');
eval(exposed);

// CSV 파서
const csvText = fs.readFileSync(path.join(ROOT, 'scripts', 'calcy_adb', 'history_merged.csv'), 'utf8');
const lines = csvText.replace(/﻿/g,'').split(/\r?\n/);
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
  name: find(['name','이름']), form: find(['form']), cp: find(['cp']),
  atk: find(['avg att iv','avg att']), def: find(['avg def iv','avg def']),
  sta: find(['avg hp iv','avg hp','sta iv']),
  level: find(['lvl','level']), shadow: find(['shadowform','shadow']),
  lucky: find(['lucky?','lucky']), account: find(['account']),
};

// matchSpecies — 단순 한글/영문/sid 매칭만 (정확도 낮아도 통계 보기엔 OK)
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

let buckets = {}, total=0, unmatched=0;
const sample = {};
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
  const ivA = parseInt(r[cols.atk]), ivD = parseInt(r[cols.def]), ivS = parseInt(r[cols.sta]);
  if (isNaN(ivA)||isNaN(ivD)||isNaN(ivS)) continue;
  const lv = parseFloat(r[cols.level])||30;
  const lucky = cols.lucky>=0 && /^(yes|true|1|y|럭키)$/i.test(r[cols.lucky]||'');
  if (!sp) { unmatched++; continue; }  // 가족 그룹 등은 스킵 (단순 통계 목적)
  const result = analyzeOne(sp, ivA, ivD, ivS, lv, lucky);
  if (!result) continue;
  result.bucket = classifyBucket(result);
  buckets[result.bucket] = (buckets[result.bucket]||0)+1;
  total++;
  if (!sample[result.bucket]) sample[result.bucket] = [];
  if (sample[result.bucket].length < 3) {
    sample[result.bucket].push(`${result.ko} ${ivA}/${ivD}/${ivS} → ${result.decisions[0].text}`);
  }
}

console.log(`총 ${total} 분석 / ${unmatched} unmatched`);
console.log();
console.log('bucket 분포:');
const order = ['hundo','gl_perfect','ul_perfect','cup_perfect','raid','pvp','mega','keep','cup','doubt','transfer'];
for (const b of order) {
  if (!buckets[b]) continue;
  console.log(`  ${b.padEnd(14)} ${String(buckets[b]).padStart(4)}`);
  for (const s of (sample[b]||[])) console.log(`     · ${s}`);
}
