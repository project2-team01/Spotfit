(() => {
  'use strict';
  const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const valid=x=>typeof x==='number'&&Number.isFinite(x);
  const n=(x,d=0)=>valid(x)?x.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'자료 없음';
  const table=(id,headers,rows)=>$(id).innerHTML='<thead><tr>'+headers.map(h=>`<th>${esc(h)}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>`<td>${esc(c)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  let state,onDetail,code='LES',inspected=null,matches=[];
  const selected=()=>state.scope.find(r=>r.trdar_code===inspected);
  function evidence(){
    const r=selected();$('step5-detail').disabled=!r;
    if(!r){$('step5-evidence-title').textContent='조건에 맞는 상권이 없습니다. 필터를 넓혀 주세요.';$('step5-evidence').innerHTML='';return;}
    $('step5-area').value=r.trdar_code;
    $('step5-evidence-title').textContent=`${r.trdar_name} · ${r.candidate_type??r.type_status} · 판정 ${r.known_axes}/3축`+(r.candidate_type?' · 분석용 대리분류 후보':' · '+(r.hold_reason||r.score_status));
    table('step5-evidence',['축','판정','원값 / 같은 업종 내 상대 위치','판정 / 보류 사유'],[
      ['주요 고객 L/V',r.LV??'보류',`상주/(상주+직장) ${valid(r.resident_share_proxy)?n(r.resident_share_proxy*100,1)+'%':'자료 없음'}`,r.LV_reason||'—'],
      ['소비 성향 E/P',r.EP??'보류',`건당 추정매출 ${valid(r.ticket)?n(r.ticket)+'원':'자료 없음'} · 백분위 ${n(r.ticket_pct,1)} · 유효 비교 ${n(r.ep_peers)}곳`,r.EP_reason||'—'],
      ['상권 변화 S/D',r.SD??'보류',`매출 CV ${n(r.sales_month_cv,3)} / 유동 CV ${n(r.floating_cv,3)} · 변동성 지수 ${n(r.dynamism_index,1)} · 유효 비교 ${n(r.sd_peers)}곳`,r.SD_reason||'—']]);
  }
  function render(s,detail){
    state=s;onDetail=detail;
    const meta=state.meta.step5,scope=state.scope,target=scope.filter(r=>r.score_status==='점수 대상'),full=target.filter(r=>r.candidate_type),type=meta.config.types.find(r=>r.code===code);
    if(!scope.some(r=>r.trdar_code===inspected))inspected=state.selected??scope[0]?.trdar_code??null;
    $('step5-stats').innerHTML=[['전체 유형 후보',n(meta.full_candidates)+'개','점수 대상의 '+n(meta.full_candidates/meta.target_cells*100,1)+'% · 53개 업종'],['전체 판정 보류',n(meta.held)+'개','STEP 4 점수 대상 '+n(meta.target_cells)+'개 중'],['현재 조건의 유형 후보',n(full.length)+'곳','현재 업종에서 세 축 모두 판정'],['현재 조건의 판정 보류',n(target.length-full.length)+'곳','점수 대상 '+n(target.length)+'곳 중']].map(([a,b,c])=>`<div class="stat"><span>${esc(a)}</span><strong>${esc(b)}</strong><small>${esc(c)}</small></div>`).join('');
    $('step5-scope').textContent=`${state.meta.industries.find(r=>r['업종_코드']===state.code)['업종명']} · 조건 안 ${n(scope.length)}곳`;
    $('type-cards').innerHTML=meta.config.types.map(t=>`<button class="type-card ${t.code===code?'selected':''}" data-type-code="${t.code}" aria-pressed="${t.code===code}"><span class="type-code">${esc(t.code)}</span><span>${esc(t.name)}</span><strong>${n(full.filter(r=>r.candidate_type===t.code).length)}<small>곳</small></strong><small>전체 ${n(meta.types[t.code])}개 조합</small></button>`).join('');
    const partial=$('step5-partial').checked,linked=$('step5-linked').checked;
    matches=Step5.explore(scope,code,partial,linked,Infinity);
    $('step5-score-note').textContent=`${code} ${type.name} · ${code[0]==='L'?'생활형':'방문형'} / ${code[1]==='E'?'실속형':'프리미엄형'} / ${code[2]==='S'?'안정형':'역동형'} · 탐색 수요: ${linked?(code[0]==='L'?'상주인구':'유동인구'):'세 수요 값 평균'}. 공통 가중치 매출 30·경쟁 25·안정성 15·수요 30, 유효 영역만 재배분합니다. 원래 STEP 4 기본 점수도 함께 표시합니다.`;
    const exact=matches.filter(r=>r.candidate_type===code).length;
    $('step5-results-title').textContent=`${code} ${type.name} · 탐색 후보`;
    $('step5-result-note').textContent=matches.length?`${n(matches.length)}곳 일치 (세 축 일치 ${n(exact)}곳${partial?', 부분 일치 '+n(matches.length-exact)+'곳':''}) · 최대 상위 20곳 표시. CSV는 전체 일치 결과를 담습니다.`:'일치하는 후보가 없습니다. 다른 유형 또는 더 넓은 지역을 선택해 보세요. 판정 보류 상권은 아래 근거 조회에서 확인할 수 있습니다.';
    $('step5-results').innerHTML='<thead><tr>'+['상권','자치구','후보 유형 / 판정 축','일치 상태','탐색 점수','STEP 4 기본 점수','평균 점포'].map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+matches.slice(0,20).map(r=>`<tr data-inspect="${r.trdar_code}" tabindex="0" aria-label="${esc(r.trdar_name)} 판정 근거 보기"><td>${esc(r.trdar_name)}</td><td>${esc(r.gu_name)}</td><td>${esc(r.candidate_type??'유형 보류')} · ${r.known_axes}/3</td><td>${esc(r.match_status)}</td><td>${n(r.exploration_score,1)}</td><td>${n(r.score_total_default,1)}</td><td>${n(r.stores,1)}개</td></tr>`).join('')+'</tbody>';
    $('step5-download').disabled=!matches.length;
    $('step5-area').innerHTML=scope.map(r=>`<option value="${r.trdar_code}">${esc(r.trdar_name)} · ${esc(r.candidate_type??r.type_status)}</option>`).join('');evidence();
    table('step5-method',['축','사용한 대리지표','분류 / 보류','해석 한계'],[
      ['L/V','상주인구/(상주인구+직장인구)','55% 초과 L · 45% 미만 V · 45~55% 보류','인구 구성 대리값이며 실제 방문객 구성 아님'],
      ['E/P','연간 추정매출/연간 추정거래건수의 업종 내 백분위','45 미만 E · 55 초과 P · 45~55 보류','객단가 상대 수준이며 실속·고급 성향을 검증하지 않음'],
      ['S/D','점포당 월매출 CV와 유동인구 CV의 업종 내 백분위 평균','45 미만 S · 55 초과 D · 45~55 보류','CV=4분기 모표준편차/평균. 변동성이지 성장률 아님']]);
    table('step5-sensitivity',['설정','유형 후보','점수 대상 중 보류','동시 판정 중 유형 변경','판정 가능 여부 변경'],meta.sensitivity.map(r=>[r['설정'],n(r['유형후보_수']),n(r['점수대상중_보류']),n(r['동시판정중_유형변경']),n(r['판정가능여부_변경'])]));
    table('step5-holds',['축','보류 사유','상권 × 업종 수'],meta.hold_reasons.map(r=>[r['축'],r['보류_사유'],n(r['조합_수'])]));
  }
  $('type-cards').addEventListener('click',e=>{const b=e.target.closest('[data-type-code]');if(b){code=b.dataset.typeCode;render(state,onDetail);}});
  ['step5-partial','step5-linked'].forEach(id=>$(id).addEventListener('change',()=>render(state,onDetail)));
  $('step5-area').addEventListener('change',()=>{inspected=$('step5-area').value;evidence();});
  $('step5-results').addEventListener('click',e=>{const r=e.target.closest('[data-inspect]');if(r){inspected=r.dataset.inspect;evidence();$('step5-evidence-title').scrollIntoView({behavior:'smooth',block:'center'});}});
  $('step5-results').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('[data-inspect]'))e.target.click();});
  $('step5-detail').addEventListener('click',()=>{if(selected())onDetail(inspected);});
  $('step5-download').addEventListener('click',()=>{
    const keys=['trdar_code','trdar_name','gu_name','candidate_type','LV','EP','SD','known_axes','match_status','exploration_score','score_total_default','demand_mode_assumption','stores','resident_share_proxy','ticket','ticket_pct','sales_month_cv','floating_cv','dynamism_index','hold_reason'];
    const safe=x=>{let v=String(x??'');if(/^[=+@\-]/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"';};
    const headers=['industry_code','requested_type','budget_fit','user_financial_profile',...keys];
    const rows=matches.map(r=>[state.code,code,'비용 자료 없어 판단 불가','사용자 응답 없음: 추론하지 않음',...keys.map(k=>r[k])]);
    const blob=new Blob(['\ufeff'+[headers,...rows].map(r=>r.map(safe).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8;'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`SpotFit_STEP5_${state.code}_${code}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  window.Step5UI={render};
})();
