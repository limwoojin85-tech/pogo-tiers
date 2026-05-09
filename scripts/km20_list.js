// 20km 버디 종 명단 — 그룹별로 한글 이름 출력
const fs = require('fs');
const path = require('path');
const ROOT = path.dirname(path.dirname(__filename));
const html = fs.readFileSync(path.join(ROOT, 'out', 'index.html'), 'utf8');
const dataMatch = html.match(/<script id="data" type="application\/json">([\s\S]+?)<\/script>/);
const DATA = JSON.parse(dataMatch[1].replace(/<\\\//g, '</'));

// gamemaster 의 한글 번역 사용 (translations.json)
const trans = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'translations.json'), 'utf8'));
const koByDex = {};
for (const [dex, v] of Object.entries(trans.species || {})) {
  koByDex[parseInt(dex)] = v.ko || '';
}

// pvpoke gamemaster 로 sid → dex 매핑
const gm = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'pvpoke', '_gamemaster.json'), 'utf8'));
const dexBySid = {};
for (const p of gm.pokemon) dexBySid[p.speciesId] = p.dex;

// HTML 에서 TWENTY_KM_SIDS 추출
const tkmMatch = html.match(/const TWENTY_KM_SIDS = new Set\(\[([\s\S]+?)\]\)/);
const sids = [...tkmMatch[1].matchAll(/'([^']+)'/g)].map(m => m[1]);

// 그룹 분류
const GROUPS = {
  '🔮 환상 (Mythical)': new Set([
    'mew','celebi','jirachi','deoxys','deoxys_attack','deoxys_defense','deoxys_speed',
    'phione','manaphy','darkrai','shaymin','shaymin_sky','arceus',
    'victini','keldeo','meloetta','meloetta_aria','meloetta_pirouette','genesect',
    'diancie','hoopa','volcanion','magearna','marshadow','zeraora','meltan','melmetal','zarude',
    'pecharunt',
  ]),
  '🐦 새 트리오': new Set([
    'articuno','zapdos','moltres','articuno_galarian','zapdos_galarian','moltres_galarian',
  ]),
  '🐺 짐승 트리오 (성도)': new Set(['raikou','entei','suicune']),
  '🌍 박스 전설 (커버)': new Set([
    'lugia','ho_oh',
    'kyogre','kyogre_primal','groudon','groudon_primal','rayquaza','rayquaza_mega',
    'dialga','dialga_origin','palkia','palkia_origin','giratina','giratina_origin','giratina_altered',
    'reshiram','zekrom','kyurem','kyurem_white','kyurem_black',
    'xerneas','yveltal','zygarde',
    'solgaleo','lunala','necrozma','necrozma_dawn_wings','necrozma_dusk_mane','necrozma_ultra',
    'zacian','zacian_hero','zacian_crowned_sword','zamazenta','zamazenta_hero','zamazenta_crowned_shield',
    'eternatus','eternatus_eternamax',
    'koraidon','miraidon','terapagos',
  ]),
  '🪨 레지 + 호연 호수': new Set([
    'regirock','regice','registeel','regigigas','regieleki','regidrago',
    'uxie','mesprit','azelf',
  ]),
  '🐉 라티 + 호연 + 신오': new Set([
    'latias','latios','heatran','cresselia',
  ]),
  '⚔️ 신오 4신검 + 신오풍': new Set([
    'cobalion','terrakion','virizion',
    'tornadus','tornadus_therian','tornadus_incarnate',
    'thundurus','thundurus_therian','thundurus_incarnate',
    'landorus','landorus_therian','landorus_incarnate',
  ]),
  '🌺 알로라 카푸 + 코스모그': new Set([
    'tapu_koko','tapu_lele','tapu_bulu','tapu_fini',
    'type_null','silvally','cosmog','cosmoem',
  ]),
  '👽 울트라비스트': new Set([
    'nihilego','buzzwole','pheromosa','xurkitree','celesteela','kartana','guzzlord',
    'poipole','naganadel','stakataka','blacephalon',
  ]),
  '🛡️ 갈라르': new Set([
    'kubfu','urshifu','urshifu_single_strike','urshifu_rapid_strike',
    'glastrier','spectrier','calyrex','calyrex_ice_rider','calyrex_shadow_rider',
  ]),
  '🌋 팔데아': new Set([
    'walking_wake','iron_leaves','ogerpon','fezandipiti','okidogi','munkidori',
  ]),
};

function nameOf(sid) {
  const dex = dexBySid[sid];
  const baseKo = koByDex[dex] || '';
  // 폼 라벨
  if (sid.includes('_galarian')) return `${baseKo} (갈라르)`;
  if (sid.includes('_alolan')) return `${baseKo} (알로라)`;
  if (sid.includes('_hisuian')) return `${baseKo} (히스이)`;
  if (sid.includes('_paldean')) return `${baseKo} (팔데아)`;
  if (sid.includes('_origin')) return `${baseKo} (오리진)`;
  if (sid.includes('_altered')) return `${baseKo} (어나더)`;
  if (sid.includes('_therian')) return `${baseKo} (영물)`;
  if (sid.includes('_incarnate')) return `${baseKo} (화신)`;
  if (sid.includes('_primal')) return `${baseKo} (원시)`;
  if (sid.includes('_attack')) return `${baseKo} (어택)`;
  if (sid.includes('_defense')) return `${baseKo} (디펜스)`;
  if (sid.includes('_speed')) return `${baseKo} (스피드)`;
  if (sid.includes('_sky')) return `${baseKo} (스카이)`;
  if (sid.includes('_aria')) return `${baseKo} (보이스)`;
  if (sid.includes('_pirouette')) return `${baseKo} (스텝)`;
  if (sid.includes('_dawn_wings')) return `${baseKo} (새벽날개)`;
  if (sid.includes('_dusk_mane')) return `${baseKo} (황혼갈기)`;
  if (sid.includes('_ultra')) return `${baseKo} (울트라)`;
  if (sid.includes('_mega_x')) return `${baseKo} (메가 X)`;
  if (sid.includes('_mega_y')) return `${baseKo} (메가 Y)`;
  if (sid.includes('_mega')) return `${baseKo} (메가)`;
  if (sid.includes('_eternamax')) return `${baseKo} (Eternamax)`;
  if (sid.includes('_white')) return `${baseKo} (블랙)`;
  if (sid.includes('_black')) return `${baseKo} (화이트)`;
  if (sid.includes('_hero')) return `${baseKo} (영웅)`;
  if (sid.includes('_crowned_sword')) return `${baseKo} (검의 왕)`;
  if (sid.includes('_crowned_shield')) return `${baseKo} (방패의 왕)`;
  if (sid.includes('_ice_rider')) return `${baseKo} (백마)`;
  if (sid.includes('_shadow_rider')) return `${baseKo} (흑마)`;
  if (sid.includes('_single_strike')) return `${baseKo} (일격의 일족)`;
  if (sid.includes('_rapid_strike')) return `${baseKo} (연격의 일족)`;
  return baseKo || sid;
}

// 출력
console.log(`\n=== 20km 파트너 종 명단 (${sids.length}종) ===\n`);

let covered = new Set();
for (const [groupName, groupSids] of Object.entries(GROUPS)) {
  const inGroup = sids.filter(s => groupSids.has(s));
  if (!inGroup.length) continue;
  console.log(`\n${groupName} (${inGroup.length}종)`);
  // dex 정렬
  const sorted = [...inGroup].sort((a, b) => (dexBySid[a]||999) - (dexBySid[b]||999));
  for (const sid of sorted) {
    const dex = dexBySid[sid];
    const ko = nameOf(sid);
    console.log(`  ${String(dex||'?').padStart(4)}  ${ko.padEnd(24)} ${sid}`);
    covered.add(sid);
  }
}

const uncategorized = sids.filter(s => !covered.has(s));
if (uncategorized.length) {
  console.log(`\n📦 분류 안 된 종 (${uncategorized.length}종)`);
  for (const sid of uncategorized) {
    console.log(`  ${String(dexBySid[sid]||'?').padStart(4)}  ${(nameOf(sid)||'?').padEnd(24)} ${sid}`);
  }
}
