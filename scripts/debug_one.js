// 파이어로 15/9/13 분류 추적
const fs = require('fs');
const path = require('path');
const ROOT = path.dirname(path.dirname(__filename));
const html = fs.readFileSync(path.join(ROOT,'out','index.html'),'utf8');
const dataMatch = html.match(/<script id="data" type="application\/json">([\s\S]+?)<\/script>/);
const DATA = JSON.parse(dataMatch[1].replace(/<\\\//g, '</'));
const scripts = [...html.matchAll(/<script>([\s\S]+?)<\/script>/g)];
const mainJs = scripts[scripts.length - 1][1];
function extract(name) {
  const re = new RegExp(`function ${name}\\s*\\([^)]*\\)\\s*\\{`,'g');
  const m = re.exec(mainJs); if (!m) return null;
  let depth=1, i=m.index+m[0].length, start=m.index;
  while (depth && i<mainJs.length){const c=mainJs[i]; if (c==='{')depth++; else if(c==='}')depth--; i++;}
  return mainJs.slice(start,i);
}
global.DATA=DATA;
global.GL_KEYS=new Set(['all_1500','premier_1500','classic_1500']);
global.UL_KEYS=new Set(['all_2500','premier_2500','classic_2500']);
global.ML_KEYS=new Set(['all_10000','premier_10000','classic_10000']);
global.LC_KEYS=new Set(['all_500','little_500','premier_500','classic_500']);
global._myTeams=null;
const need=['statProductAt','maxLevelForCP','leagueScore','bestRankIn','bestRaidRank','analyzeOne','classifyBucket','buildUserTeams'];
const code = need.map(n => extract(n)).filter(Boolean).join('\n\n');
eval(code.replace(/^function (\w+)\s*\(/gm, 'global.$1 = function ('));

const sp = DATA.species.talonflame;
console.log('talonflame:', sp.ko, sp.en);
console.log('rank1_iv:', JSON.stringify(sp.rank1_iv));
console.log('pvp keys:', sp.pvp.map(p=>p.league_key+'#'+p.rank).join(', '));

const r = analyzeOne(sp, 15, 9, 13, 30, false);
console.log('\n=== 파이어로 15/9/13 ===');
for (const d of r.decisions) {
  console.log('  pri='+d.pri+': '+d.text + (d.why?' /// '+d.why:''));
}
buildUserTeams([r]);
const bucket = classifyBucket(r);
console.log('bucket:', bucket);
console.log('allTxt:', r.decisions.map(d=>d.text||'').join(' '));
