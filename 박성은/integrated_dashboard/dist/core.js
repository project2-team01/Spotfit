/* Python model.py와 같은 통합 규칙. 네트워크·DOM 의존 없이 검증 가능. */
(() => {
  'use strict';
  const KEYS=['sales','comp','stab','dem'],DEFAULT={sales:30,comp:25,stab:15,dem:30};
  const AXES={LV:['L','V'],EP:['E','P'],SD:['S','D']};
  const valid=x=>typeof x==='number'&&Number.isFinite(x);
  const median=a=>{a=a.filter(valid).sort((a,b)=>a-b);return a.length?(a[Math.floor((a.length-1)/2)]+a[Math.floor(a.length/2)])/2:null;};
  function score(row,weights=DEFAULT,mode='avg'){
    if(!['avg','available','floating','worker','resident'].includes(mode))throw new Error('없는 수요 모드');
    let num=0,den=0,n=0;
    for(const k of KEYS){const w=Number(weights[k]??0),v=row[k==='dem'?'score_dem_'+mode:'score_'+k];if(!Number.isFinite(w)||w<0)throw new Error('잘못된 가중치');if(valid(v)&&w>0){num+=w*v;den+=w;n++;}}
    const target=row.score_status==='점수 대상';
    return {...row,score_dem:row['score_dem_'+mode],score_total:target&&den>0?num/den:null,n_areas:target&&den>0?n:0,demand_mode:mode};
  }
  function matches(row,choices={}){
    const chosen=Object.entries(choices).filter(([,v])=>v);
    for(const [a,v] of chosen)if(!AXES[a]?.includes(v))throw new Error('없는 선호 축');
    return !chosen.length||(row.score_status==='점수 대상'&&chosen.every(([a,v])=>row[a]===v));
  }
  const descending=(a,b)=>(valid(b.score_total)?b.score_total:-Infinity)-(valid(a.score_total)?a.score_total:-Infinity)||b.stores-a.stores||a.trdar_code.localeCompare(b.trdar_code);
  function explore(rows,choices={},weights=DEFAULT,mode='avg',linked=false,limit=Infinity){
    const actual=linked&&choices.LV?(choices.LV==='L'?'resident':'floating'):mode;
    return rows.filter(r=>r.score_status==='점수 대상'&&matches(r,choices)).map(r=>score(r,weights,actual)).sort(descending).slice(0,limit);
  }
  function ranks(values){const s=values.map((v,i)=>({v,i})).sort((a,b)=>a.v-b.v),out=[];for(let i=0;i<s.length;){let j=i+1;while(j<s.length&&s[j].v===s[i].v)j++;for(let k=i;k<j;k++)out[s[k].i]=(i+1+j)/2;i=j;}return out;}
  function spearman(rows,a,b){const p=rows.filter(r=>valid(r[a])&&valid(r[b]));if(p.length<2)return null;const x=ranks(p.map(r=>r[a])),y=ranks(p.map(r=>r[b])),mx=x.reduce((a,b)=>a+b,0)/x.length,my=y.reduce((a,b)=>a+b,0)/y.length;let c=0,vx=0,vy=0;x.forEach((v,i)=>{c+=(v-mx)*(y[i]-my);vx+=(v-mx)**2;vy+=(y[i]-my)**2;});return vx&&vy?c/Math.sqrt(vx*vy):null;}
  function quizResult(questions,answers){
    const result={axes:{},choices:{},answered:0,code:null};
    for(const [axis,letters] of Object.entries(AXES)){
      const qs=questions.filter(q=>q.axis===axis),counts=Object.fromEntries(letters.map(x=>[x,0]));
      for(const q of qs){const a=answers[q.id];if(!a)continue;if(!q.options.some(o=>o.value===a))throw new Error('문항에 없는 응답');counts[a]++;}
      const n=Object.values(counts).reduce((a,b)=>a+b,0),letter=n===5?letters.reduce((a,b)=>counts[a]>=counts[b]?a:b):null,status=n<5?'미완료':counts[letter]>=4?'뚜렷':'경계';
      result.axes[axis]={counts,answered:n,letter,status};result.choices[axis]=status==='뚜렷'?letter:'';result.answered+=n;
    }
    if(result.answered===15)result.code=Object.keys(AXES).map(a=>result.axes[a].letter).join('');
    return result;
  }
  const core={KEYS,DEFAULT,AXES,valid,median,score,matches,descending,explore,spearman,quizResult};
  if(typeof module!=='undefined'&&module.exports)module.exports=core;
  if(typeof window!=='undefined')window.SpotFit=core;
})();
