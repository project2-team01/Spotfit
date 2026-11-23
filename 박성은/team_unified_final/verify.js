const fs=require('fs'),assert=require('assert'),path=require('path');
const P=require('./data/payload.json'),O=require('./data/oracle.json'),C=require('./web/core.js');
let rows=0,topCases=0,maxError=0;
for(const code of Object.keys(O)){
  const got=C.industryRows(P,code,P.defaultWeights);
  assert.strictEqual(got.length,Object.keys(O[code].all).length);
  for(const r of got){const diff=Math.abs(r.total-O[code].all[r.code]);maxError=Math.max(maxError,diff);assert(diff<1e-9);rows++;}
  const T=C.typeCompare(P,code,null,5);
  for(const t of Object.keys(T)){assert.deepStrictEqual(T[t].top.map(r=>r.code),O[code].types[t]);topCases++;}
}
let quizCases=0;
for(let mask=0;mask<32768;mask++){
  const answers={};P.step5.questions.forEach((q,i)=>answers[q['번호']]=(mask>>i)&1?'A':'B');
  const result=C.scoreAnswers(answers,P.step5.questions,P.step5.axes),pattern=C.matchedTypes(result).pattern;
  P.step5.axes.forEach((a,j)=>{const qs=P.step5.questions.filter(q=>q['기준']===a['기준']);const letters=qs.map(q=>q[answers[q['번호']]+' 글자']);const n=letters.filter(v=>v===a['왼쪽']).length;assert.strictEqual(pattern[j],n>=4?a['왼쪽']:n<=1?a['오른쪽']:null);});
  quizCases++;
}
assert.strictEqual(C.matchLabel('LE?',{pattern:['L','E',null]}),C.MATCH);
assert.strictEqual(C.matchLabel('LE?',{pattern:['L','E','S']}),C.UNKNOWN);
assert.strictEqual(C.matchLabel('VPS',{pattern:['L',null,null]}),C.OTHER);
assert.strictEqual(C.composite({sales:0,competition:null,stability:null,demand:null},{sales:1}).total,0);
assert.strictEqual(C.composite({sales:50},{sales:0}).total,null);
const html=fs.readFileSync('./dist/index.html','utf8');
assert(!/<script\b[^>]*\bsrc=|<link\b[^>]*rel=['"]stylesheet/.test(html));
for(let n=1;n<=10;n++)assert(html.includes('id="p-s'+n+'"'));
const report={passed:true,rows,maxError,pythonTypeTop5Cases:topCases,quizCases,standaloneHtml:true};
fs.writeFileSync('./report/validation.json',JSON.stringify(report,null,2)+'\n');console.log(report);
