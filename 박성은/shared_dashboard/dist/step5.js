/* STEP5 Python 탐색기의 조건과 기본 점수를 그대로 사용한다. */
(() => {
  'use strict';
  const WEIGHTS={sales:30,comp:25,stab:15,dem:30};
  const CODES=['LES','LED','LPS','LPD','VES','VED','VPS','VPD'];
  const normalize=code=>code?.replace(/G$/,'D');
  function explore(rows,type,partial=false,linked=true,limit=10){
    const code=normalize(type);if(!CODES.includes(code))throw new Error('지원하지 않는 유형입니다.');
    const mode=linked?(code[0]==='L'?'resident':'floating'):'avg';
    return rows.filter(r=>r.score_status==='점수 대상'&&(partial
      ?r.known_axes>0&&['LV','EP','SD'].every((axis,i)=>r[axis]==null||r[axis]===code[i])
      :r.candidate_type===code)).map(r=>{
      let num=0,den=0;['sales','comp','stab','dem'].forEach(k=>{const v=r[k==='dem'?'score_dem_'+mode:'score_'+k];if(typeof v==='number'&&Number.isFinite(v)){num+=v*WEIGHTS[k];den+=WEIGHTS[k];}});
      return {...r,exploration_score:den?num/den:null,demand_mode_assumption:mode,
        match_status:r.candidate_type===code?'세 축 일치 후보':'부분 일치: 미판정 축 있음'};
    }).sort((a,b)=>b.known_axes-a.known_axes||(b.exploration_score??-Infinity)-(a.exploration_score??-Infinity)||b.stores-a.stores||a.trdar_code.localeCompare(b.trdar_code)).slice(0,limit);
  }
  const core={explore,normalize,CODES,WEIGHTS};
  if(typeof module!=='undefined'&&module.exports)module.exports=core;
  if(typeof document==='undefined')return;
  window.Step5=core;
})();
