"""7문항의 전체 무응답/A/B 조합을 독립 Python으로 계산해 Node 채점과 대조."""
from pathlib import Path
import itertools
import json
import subprocess
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/'data/payload.json').read_text(encoding='utf-8'))
ids=[2,6,11,3,8,14,10]
qs={q['번호']:q for q in P['step5']['questions']}
cases=[]
for choices in itertools.product([None,'A','B'],repeat=7):
    answers={str(k):v for k,v in zip(ids,choices) if v}
    patterns=[];letters=[];counts=[]
    for axis in ['LV','EP','SD']:
        relevant=[k for k in ids if qs[k]['기준']==axis]
        picked=[qs[k][answers[str(k)]+' 글자'] for k in relevant if str(k) in answers]
        complete=len(picked)==len(relevant)
        # 短축형은 양방향 모두 같은 기준: 모두 응답하고 전원 일치일 때만 필터.
        patterns.append(picked[0] if complete and len(set(picked))==1 else None)
        cnt={v:picked.count(v) for v in set(picked)}
        letter=next((v for v,n in cnt.items() if n>len(relevant)/2),None) if complete else None
        letters.append(letter)
    cases.append({'answers':answers,'pattern':patterns,'answered':len(answers),'complete':len(answers)==7,'type':''.join(letters) if all(letters) else None})
node="""
const fs=require('fs'),assert=require('assert'),P=JSON.parse(fs.readFileSync('data/payload.json','utf8')),C=require('./web/core.js');
const cases=JSON.parse(fs.readFileSync(0,'utf8')),qs=C.quizQuestions(P.step5.questions,'short7');
assert.deepStrictEqual(qs.map(q=>q['번호']),[2,6,11,3,8,14,10]);
for(const c of cases){const r=C.scoreAnswers(c.answers,qs,P.step5.axes,'short7');assert.deepStrictEqual(C.matchedTypes(r).pattern,c.pattern);assert.strictEqual(r.answered,c.answered);assert.strictEqual(r.complete,c.complete);assert.strictEqual(r.type,c.type);assert.strictEqual(r.source,'7문항 간편 검사');assert.strictEqual(r.total,7);}
console.log(JSON.stringify({passed:true,cases:cases.length,completeCases:cases.filter(c=>c.complete).length,axisQuestionCounts:{LV:2,EP:3,SD:2}}));
"""
r=subprocess.run(['node','-e',node],cwd=HERE,input=json.dumps(cases),text=True,capture_output=True,check=True,encoding='utf-8')
result=json.loads(r.stdout)
(HERE/'report/validation_short.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(r.stdout)
