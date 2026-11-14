const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const core=require('./dist/step5.js'),root=path.join(__dirname,'dist/data');
const meta=JSON.parse(fs.readFileSync(path.join(root,'meta.json'),'utf8'));
const byIndustry=new Map(),counts=Object.fromEntries(core.CODES.map(k=>[k,0]));
let rows=0,target=0,held=0;
for(const industry of meta.industries){
  const code=industry['업종_코드'],p=JSON.parse(fs.readFileSync(path.join(root,code+'.json'),'utf8'));
  const types=new Map(p.step5_rows.map(a=>{const r=Object.fromEntries(p.step5_columns.map((k,i)=>[k,a[i]]));return [r.trdar_code,r];}));
  assert.equal(types.size,p.rows.length);
  const merged=p.rows.map(a=>{const r=Object.fromEntries(p.columns.map((k,i)=>[k,a[i]]));assert(types.has(r.trdar_code));return {...r,...types.get(r.trdar_code)};});
  byIndustry.set(code,merged);
  for(const r of merged){rows++;assert.equal(r.known_axes,['LV','EP','SD'].filter(k=>r[k]!==null).length);
    if(r.score_status==='점수 대상'){target++;if(!r.candidate_type){held++;assert(r.hold_reason);}}
    else{assert.equal(r.known_axes,0);assert.equal(r.candidate_type,null);}
    if(r.candidate_type){assert.equal(r.LV+r.EP+r.SD,r.candidate_type);counts[r.candidate_type]++;assert.equal(r.known_axes,3);assert.equal(r.score_status,'점수 대상');}
    if(!industry['매출_제공_업종']){assert.equal(r.EP,null);assert.equal(r.SD,null);assert.equal(r.candidate_type,null);}
  }
}
assert.equal(rows,76591);assert.equal(target,20522);assert.equal(held,11255);assert.deepEqual(counts,meta.step5.types);
assert.equal(Object.values(counts).reduce((a,b)=>a+b,0),9267);
const fixtures=JSON.parse(fs.readFileSync(path.join(__dirname,'step5-fixtures.json'),'utf8'));
let compared=0,maxDifference=0,emptyCases=0;
for(const f of fixtures){
  const actual=core.explore(byIndustry.get(f.industry),f.code,f.partial,f.linked);
  assert.deepEqual(actual.map(r=>r.trdar_code),f.expected.map(r=>r.trdar_code),JSON.stringify(f));
  if(!actual.length)emptyCases++;
  actual.forEach((r,i)=>{const e=f.expected[i];for(const k of ['candidate_type','LV','EP','SD','known_axes','match_status','demand_mode_assumption'])assert.equal(r[k],e[k]);
    for(const k of ['exploration_score','score_total_default']){if(e[k]===null)assert.equal(r[k],null);else{const delta=Math.abs(r[k]-e[k]);assert(delta<1e-8,k);maxDifference=Math.max(delta,maxDifference);}}compared++;
  });
}
assert.equal(core.normalize('LEG'),'LED');assert.equal(core.normalize('VPG'),'VPD');assert.throws(()=>core.explore([],'XXX'));
// 부분 일치가 다른 축과 충돌하거나 미판정 축을 완전 판정으로 바꾸면 안 된다.
for(const code of core.CODES){const list=core.explore(byIndustry.get('CS100010'),code,true,true,Infinity);for(const r of list){assert(r.known_axes>0);['LV','EP','SD'].forEach((k,i)=>assert(r[k]===null||r[k]===code[i]));if(r.known_axes<3)assert.equal(r.candidate_type,null);}}
assert(emptyCases>0);
const report={passed:true,rows,target,fullCandidates:9267,held,typeCounts:counts,pythonCases:fixtures.length,comparedRows:compared,emptyCases,maxDifference,checks:['전체 100업종 STEP4와 STEP5 키 완전 일치','기존 Python 탐색기와 순서·점수·수요 연결·부분 일치 일치','미판정 보존 및 미제공 업종 분류 차단','기본 후보 수·보류 수·8유형별 수 일치','구 G 코드의 D 정규화','후보 없는 업종의 빈 결과 보존']};
fs.writeFileSync(path.join(__dirname,'validation-step5.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
