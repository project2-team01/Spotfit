    // 승희 픽셀 지오메트리·차이 구간을 지영 SVG 렌더러와 공통 점수에 연결한다.
    function drawDiagnostics(c) {
      const baseline=C.rankRows(C.industryRows(P,state.industry,P.defaultWeights)).filter(r=>r.total!==null);
      const rank0=new Map(baseline.map((r,i)=>[r.code,i+1]));
      const top=new Set(baseline.slice(0,10).map(r=>r.code));
      const scenarios=[['기본',P.defaultWeights],['안정성 제외',{sales:30,competition:25,stability:0,demand:30}],['경쟁 제외',{sales:30,competition:0,stability:15,demand:30}],['영역 동일',{sales:25,competition:25,stability:25,demand:25}],['현재',state.weights]];
      const results=scenarios.map(([n,w])=>{const rs=C.rankRows(C.industryRows(P,state.industry,w)).filter(r=>r.total!==null);return {n,keep:rs.slice(0,10).filter(r=>top.has(r.code)).length,rho:C.spearman(rs.map(r=>rank0.get(r.code)),rs.map((_,i)=>i+1))};});
      $('sensitivity').innerHTML=table([{k:'n',l:'비중 시나리오'},{k:'keep',l:'기본 상위 10곳 유지 수'},{k:'rho',l:'기본과 순위 상관',f:v=>v===null?'자료 없음':v.toFixed(3)}],results);
      const current=c.rows.filter(r=>(!state.gu||A.gu[r.i]===state.gu)&&(!state.profile||!state.onlyMatch||C.matchLabel(A.type2[r.i],state.profile.matched)===C.MATCH));
      $('downloadCsv').disabled=!current.length;
      $('downloadCsv').onclick=()=>{
        const header=['상권','자치구','유형','점수','매출','경쟁','안정성','수요','계산영역수','적용비중','선호패턴','버전'];
        const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
        const values=current.map(r=>[A.name[r.i],A.gu[r.i],A.type2[r.i],r.total,r.sales,r.competition,r.stability,r.demand,r.used,JSON.stringify(state.weights),state.profile&&state.onlyMatch?state.profile.matched.pattern.join('/'):"제한 없음",P.version]);
        const blob=new Blob(['\ufeff'+[header,...values].map(row=>row.map(quote).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
        const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='SpotFit_팀통합_'+state.industry+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);
      };
    }
    function drawGuMap(c) {
      const host=$('guMap'),metric=state.guMetric;
      const all=c.rows.filter(r=>r.total!==null);
      const rows=state.profile&&state.onlyMatch ? all.filter(r=>C.matchLabel(A.type2[r.i],state.profile.matched)===C.MATCH) : all;
      const base=C.median(all.map(r=>r[metric]));
      const ranked=C.rankRows(all),n10=Math.ceil(ranked.length*.1),cut=n10?ranked[n10-1].total:null;
      const groups=[...new Set(A.gu)].sort();
      const colors=['#ad7b00','#f2d680','#f5f0df','#9ec4f3','#1f5fc4'];
      const bucket=d=>d < -5?0:d < -2?1:d<=2?2:d<=5?3:4;
      const summaries=groups.map(name=>{
        const rs=rows.filter(r=>A.gu[r.i]===name&&isNum(r[metric==='top'?'total':metric]));
        const med=C.median(rs.map(r=>r[metric]));
        return {name,n:rs.length,median:med,delta:isNum(med)&&isNum(base)?med-base:null,
          top:rows.filter(r=>A.gu[r.i]===name&&cut!==null&&r.total>=cut).length};
      });
      $('guControls').innerHTML=`<div class="seg">${[['total','종합'],...KEYS.map(k=>[k,SHORT[k]]),['top','상위 10% 상권 수']].map(([v,n])=>`<button data-gmetric="${v}" aria-pressed="${metric===v}">${n}</button>`).join('')}</div>
      <div class="actions"><label>탐색 자치구 <select id="guSelect"><option value="">서울 전체</option>${groups.map(n=>`<option ${n===state.gu?'selected':''}>${esc(n)}</option>`).join('')}</select></label><button id="guReset" class="ghost">서울 전체로 돌아가기</button></div>`;
      $('guControls').onclick=e=>{const b=e.target.closest('[data-gmetric]');if(b){state.guMetric=b.dataset.gmetric;drawGuMap(c);}};
      const pick=name=>{state.gu=name;state.selected=null;renderS6();};
      $('guSelect').onchange=e=>pick(e.target.value);$('guReset').onclick=()=>pick('');
      const m=P.map;
      let svg=`<svg viewBox="0 0 ${m.w} ${m.h}" role="img" aria-label="자치구 픽셀 지도. 구 선택은 아래 자치구 선택 메뉴로도 가능합니다.">`;
      P.guPixel.forEach(f=>{
        if(f.kind!=='gu'){svg+=`<path d="${f.path}" fill="#a9d7ed"/>`;return;}
        const r=summaries.find(g=>g.name===f.name),empty=metric==='top'?false:!isNum(r.delta);
        const color=empty?'#c4c0b6':metric==='top'?colors[Math.min(4,Math.floor(r.top/Math.max(1,n10)*20))]:colors[bucket(r.delta)];
        const note=metric==='top'?`${r.top}곳`:`${isNum(r.delta)?(r.delta>=0?'+':'')+r.delta.toFixed(2):'자료 없음'}점`;
        const title=`${f.name} · ${note} · 비교 ${r.n}곳${r.n<10?' · 참고용(10곳 미만)':''}`;
        svg+=`<path data-gu="${f.name}" d="${f.path}" fill="${color}" stroke="${state.gu===f.name?'#282720':'#ffffff'}" stroke-width="${state.gu===f.name?5:2}" ${r.n<10?'stroke-dasharray="6 3" fill-opacity=".45"':''}><title>${esc(title)}</title></path>`;
      });
      P.guPixel.filter(f=>f.kind==='gu'&&f.label).forEach(f=>{
        const r=summaries.find(g=>g.name===f.name),[x,y]=f.label;
        const text=metric==='top'?r.top+'곳':isNum(r.delta)?(r.delta>=0?'+':'')+r.delta.toFixed(1):'—';
        svg+=`<g pointer-events="none"><rect x="${x-53}" y="${y-11}" width="106" height="24" fill="#fffaf0" stroke="#282720" stroke-width="2"/><text x="${x}" y="${y+6}" text-anchor="middle" fill="#282720" font-size="13" font-weight="700">${esc(f.name)} ${text}${r.n<10?'*':''}</text></g>`;
      });
      host.innerHTML=svg+'</svg>';
      host.onclick=e=>{const path=e.target.closest('[data-gu]');if(path)pick(path.dataset.gu);};
      const sparse=summaries.filter(g=>g.n<10).length;
      $('guLegend').innerHTML=metric==='top'
        ?`서울 같은 업종 현재 종합 점수의 상위 ceil(10%) 경계 이상(동점 포함, 기준 ${cut===null?'없음':cut.toFixed(3)}점)의 구별 개수입니다. 구 면적·상권 수가 클수록 많아지기 쉽습니다. 표시는 ${rows.length}개 후보 기준입니다.`
        :`<div class="legend">${colors.map((col,j)=>`<span><span class="sw" style="background:${col}"></span>${['−5점 미만','−5 이상 ~ −2 미만','−2 ~ +2 포함','+2 초과 ~ +5 포함','+5 초과'][j]}</span>`).join('')}</div>서울 같은 업종 전체 유효 점수 중앙값 ${base===null?'자료 없음':base.toFixed(3)}점 대비 차이입니다. 원 정밀도로 색을 정하고 이름표는 소수 1자리로 표시합니다. *·흐린색·점선은 해당 지표 10곳 미만 참고용. ${sparse>12?'절반 넘는 구가 참고용이므로 구끼리 비교하기 어렵습니다.':''}`;
      $('guLegend').innerHTML+='<p>구 선택은 6장 지도·목록의 탐색 범위입니다. 점수·서울 순위와 7장·8장의 서울 전체 비교 기준은 바꾸지 않습니다. ±2·±5점과 10곳은 표시 가정입니다.</p>';
      // 원입력 대조 결과를 보고서 10장에서 직접 확인할 수 있게 한다.
      $('auditSummary').innerHTML=`<h3>원입력 재계산 검증</h3><p>입력 ${P.audit.source_commit} · 상권×업종 점수 대상 ${P.audit.counts.scored_cells.toLocaleString()}개.</p><p>김지영 원패널 재계산, 최신 이승희 점수와 통합 점수 차이 0개. 최신 이승희 유형과 차이 ${P.audit.checks.latest_seunghee_type_differences}개. 예전 박성은 기본 점수는 ${P.audit.checks.canonical_vs_old_park.score_total_default.different}개가 다릅니다.</p><p>세 축 완전 판정 ${P.audit.counts.full_types.toLocaleString()}개 / 보류 ${P.audit.counts.held_types.toLocaleString()}개. 공식 S/D에 대응하지 않는 구역은 ${P.audit.counts.sd_unmapped_areas}/${P.audit.counts.sd_area_denominator}곳입니다. 서로 다른 분모를 섞지 않습니다.</p>`;
    }
