const fs = require('fs');
const path = require('path');
const ROOT = path.dirname(path.dirname(__filename));
const html = fs.readFileSync(path.join(ROOT,'out','index.html'),'utf8');
const dataMatch = html.match(/<script id="data" type="application\/json">([\s\S]+?)<\/script>/);
const DATA = JSON.parse(dataMatch[1].replace(/<\\\//g, '</'));

// 리자드, 리자몽, 래비풋, 에이스번 species 검사
for (const sid of ['charmander','charmeleon','charizard','scorbunny','raboot','cinderace']) {
  const sp = DATA.species[sid];
  if (!sp) { console.log(`${sid}: NOT IN DATA`); continue; }
  console.log(`${sid} = ${sp.ko}/${sp.en}`);
  console.log(`  is_final=${sp.is_final}`);
  console.log(`  chain_ko=${JSON.stringify(sp.chain_ko)}`);
  console.log(`  raid=${(sp.raid||[]).length}건 (${(sp.raid||[]).slice(0,3).map(r=>r.boss_ko+'#'+r.rank).join(', ')})`);
  console.log('');
}

// NAME_INDEX 에서 '리자드' 가 어디로 가는지
const NAME_INDEX = {};
for (const sp of Object.values(DATA.species)) {
  if (sp.ko) NAME_INDEX[sp.ko.toLowerCase()] = NAME_INDEX[sp.ko.toLowerCase()] || sp.id;
  for (const k of (sp.chain_ko || [])) {
    const lk = k.toLowerCase();
    if (!NAME_INDEX[lk]) NAME_INDEX[lk] = sp.id;
  }
}
console.log('리자드 NAME_INDEX →', NAME_INDEX['리자드']);
console.log('래비풋 NAME_INDEX →', NAME_INDEX['래비풋']);
