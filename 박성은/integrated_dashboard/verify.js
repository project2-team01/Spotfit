const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const C=require('./dist/core.js'),data=path.join(__dirname,'dist/data'),meta=JSON.parse(fs.readFileSync(path.join(data,'meta.json'),'utf8'));
const byIndustry=new Map();let rows=0,target=0,full=0,maxDelta=0;const types={};
for(const industry of meta.industries){
  const p=JSON.parse(fs.readFileSync(path.join(data,industry.code+'.json'),'utf8'));
  const group=p.rows.map(a=>Object.fromEntries(p.columns.map((k,i)=>[k,a[i]])));byIndustry.set(industry.code,group);
  for(const r of group){rows++;const scored=C.score(r);if(r.score_status==='점수 대상'){target++;assert(C.valid(scored.score_total));const delta=Math.abs(scored.score_total-r.score_total_default);assert(delta<1e-8);maxDelta=Math.max(maxDelta,delta);}else assert.equal(scored.score_total,null);
    if(r.candidate_type){full++;types[r.candidate_type]=(types[r.candidate_type]||0)+1;assert.equal(r.candidate_type,r.LV+r.EP+r.SD);assert.equal(r.known_axes,3);}
    if(r.chg_code==='LH'||r.chg_code==='HL')assert.equal(r.SD,null);
    assert.equal(C.score(r,{sales:0,comp:0,stab:0,dem:0}).score_total,null);
    if(r.score_dem_avg===null&&r.score_status==='점수 대상')assert(C.valid(r.score_dem_available));
  }
}
assert.equal(rows,76591);assert.equal(target,20522);assert.equal(full,7678);
for(const t of meta.types)assert.equal(types[t.code]||0,t.count);
const fixtures=JSON.parse(fs.readFileSync(path.join(__dirname,'test_fixtures.json'),'utf8'));let compared=0,empty=0;
for(const f of fixtures){const actual=C.explore(byIndustry.get(f.industry),f.choices,C.DEFAULT,'avg',f.linked,10);assert.deepEqual(actual.map(r=>r.trdar_code),f.expected.map(r=>r.trdar_code));if(!actual.length)empty++;actual.forEach((r,i)=>{const e=f.expected[i];assert.equal(r.n_areas,e.n_areas);assert.equal(r.demand_mode,e.demand_mode);assert(Math.abs(r.score_total-e.score_total)<1e-8);compared++;});}
assert.throws(()=>C.matches({},{SD:'G'}));assert.throws(()=>C.score({},{sales:-1}));
let quizCases=0;const qs=meta.questions;
for(let bits=0;bits<32768;bits++){
  const answers={};qs.forEach((q,i)=>answers[q.id]=q.options[(bits>>i)&1].value);const r=C.quizResult(qs,answers);assert.equal(r.answered,15);assert.equal(r.code.length,3);
  for(const [axis,letters] of Object.entries(C.AXES)){const chosen=qs.filter(q=>q.axis===axis).map(q=>answers[q.id]);const left=chosen.filter(x=>x===letters[0]).length,right=5-left;assert.equal(r.choices[axis],left>=4?letters[0]:right>=4?letters[1]:'');assert.equal(r.axes[axis].status,Math.max(left,right)>=4?'뚜렷':'경계');}quizCases++;
}
assert.equal(C.quizResult(qs,{}).code,null);assert.deepEqual(C.quizResult(qs,{}).choices,{LV:'',EP:'',SD:''});assert.throws(()=>C.quizResult(qs,{1:'G'}));
const html=fs.readFileSync(path.join(__dirname,'dist/index.html'),'utf8');const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]);assert.equal(new Set(ids).size,ids.length);
const app=fs.readFileSync(path.join(__dirname,'dist/app.js'),'utf8');for(const [,id] of app.matchAll(/\$\('([^']+)'\)/g)){if(!['compare-search','compare-list'].includes(id))assert(ids.includes(id),'missing element '+id);}
const report={passed:true,version:meta.config.version,rows,target,full,maxDefaultScoreDifference:maxDelta,pythonOracleCases:fixtures.length,comparedRows:compared,emptyCases:empty,quizCases,htmlIds:ids.length};
fs.writeFileSync(path.join(__dirname,'report/validation_browser_core.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
