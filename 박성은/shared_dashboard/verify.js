const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const c=require('./dist/dashboard.js');
const meta=JSON.parse(fs.readFileSync(path.join(__dirname,'dist/data/meta.json'),'utf8'));
let count=0,scored=0,maxDifference=0;
for(const industry of meta.industries){
  const p=JSON.parse(fs.readFileSync(path.join(__dirname,'dist/data',industry['업종_코드']+'.json'),'utf8'));
  for(const a of p.rows){
    const row=Object.fromEntries(p.columns.map((k,i)=>[k,a[i]])),r=c.score(row);count++;
    if(c.valid(row.score_total_default)){scored++;assert(c.valid(r.score_total));maxDifference=Math.max(maxDifference,Math.abs(row.score_total_default-r.score_total));assert(Math.abs(row.score_total_default-r.score_total)<1e-8);}
    else assert.equal(r.score_total,null);
    if(!industry['매출_제공_업종'])assert.equal(row.score_sales,null);
    for(const mode of ['avg','floating','worker','resident']){
      const alt=c.score(row,c.DEFAULT,mode);if(c.valid(alt.score_total))assert(alt.score_total>0&&alt.score_total<=100.000000001);
      assert.equal(c.score(row,{sales:0,comp:0,stab:0,dem:0},mode).score_total,null);
    }
    if(row.stores<5)assert.equal(r.score_total,null);
  }
}
assert.equal(count,76591);assert.equal(scored,20522);assert.equal(meta.industries.length,100);
assert.equal(c.median([null,1,3]),2);assert.equal(c.spearman([{a:1,b:3},{a:2,b:2},{a:3,b:1}],'a','b'),-1);
const output={passed:true,rows:count,scored,industries:100,maxDifference,checks:['전체 기본 종합 점수 Python 결과와 일치','4개 고객층 점수 범위','전 가중치 0이면 결측','미제공 업종 매출 결측','소표본 점수 없음']};
fs.writeFileSync(path.join(__dirname,'validation.json'),JSON.stringify(output,null,2)+'\n');
console.log(JSON.stringify(output,null,2));
