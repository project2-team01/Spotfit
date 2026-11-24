"""지영 화면 원본을 보존한 채 팀 통합 어댑터를 생성한다. 재실행 후 build.py 실행."""
from pathlib import Path
import re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=ROOT/'김지영/step6_final/web'
WEB=HERE/'web'
def replace_function(s,name,new):
    start=s.index('    function '+name+'(')
    end=s.index('\n    }',start)+6
    return s[:start]+new.rstrip()+ '\n'+s[end:]

core=(SOURCE/'core.js').read_text(encoding='utf-8')
core=core.replace('  var api = {', '''
  // 통합 규칙: 세 축은 후보 필터, 가중치는 직접 고른 값. 일부 축 보류도 원코드로 보존한다.
  function unifiedMatched(result) {
    return {pattern: result.axes.map(a=>a.clear ? a.letter : null)};
  }
  function unifiedLabel(code, matched) {
    if (!code) return UNKNOWN;
    if (!matched) return OTHER;
    for (var j=0;j<3;j++) {
      if (!matched.pattern[j]) continue;
      if (code[j]==='?') return UNKNOWN;
      if (code[j]!==matched.pattern[j]) return OTHER;
    }
    return MATCH;
  }
  function unifiedCompare(payload, code, weightTable, n, weights) {
    var all=industryRows(payload,code,weights||payload.defaultWeights), out={};
    var ax=payload.unified[code]||[];
    payload.step5.types.forEach(t=>{
      var key=t['유형'];var rows=all.filter(r=>ax[r.i]&&ax[r.i].type===key&&r.total!==null);
      out[key]={pool:rows.length,top:rankRows(rows).slice(0,n)};
    });return out;
  }
  var api = {''')
core=core.replace('matchedTypes: matchedTypes, sgWeights: sgWeights,','matchedTypes: unifiedMatched, sgWeights: sgWeights,')
core=core.replace('matchLabel: matchLabel, axisText: axisText, typeCompare: typeCompare,','matchLabel: unifiedLabel, axisText: axisText, typeCompare: unifiedCompare,')
(WEB/'core.js').write_text(core,encoding='utf-8')

app=(SOURCE/'app.js').read_text(encoding='utf-8')
app=app.replace('["LES", "LEG", "LPS", "LPG", "VES", "VEG", "VPS", "VPG"]','["LES", "LED", "LPS", "LPD", "VES", "VED", "VPS", "VPD"]')
app=app.replace('theme: store.get("theme") || "auto", page: "s1",','theme: store.get("theme") || "light", page: "s1", gu: "", guMetric:"total",')
app=app.replace('spotfit6:','spotfit-team:')
app=app.replace('"K05", "K06", "K07"]','"K05", "K06", "K07", "K08"]')
app=app.replace('const key = state.industry + JSON.stringify(w);','syncAxes();\n      const key = state.industry + JSON.stringify(w);')
app=app.replace('const typeText = (i) => (A.type2[i] ? A.type2[i] : "판정 불가");','''
    function syncAxes() {
      const axes=P.unified[state.industry]||[];
      A.type2=A.code.map((_,i)=>axes[i]?axes[i].type:null);
      A.lvs=A.code.map((_,i)=>axes[i]?axes[i].lv:null);
      A.eps=A.code.map((_,i)=>axes[i]?axes[i].ep:null);
    }
    const typeText = (i) => (A.type2[i] ? A.type2[i]+(A.type2[i].includes('?')?' · 部分 보류'.replace('部分','일부'):'') : "점수 대상 아님");
    ''')
app=replace_function(app,'makeProfile','''    function makeProfile(result) {
      const type=result.type||result.axes.map(a=>a.letter||'?').join('');
      const info=TYPES[type]||{'이름':'일부 축 선호','이모지':'','상권 특징':'완료한 축 중 4:1 이상인 축만 적용','창업 아이템 예시':'희망 업종을 직접 고르세요.'};
      return {type,info,result,text:C.axisText(result),matched:C.matchedTypes(result),weights:Object.assign({},state.weights),weightLabel:'현재 공통 비중 유지'};
    }''')
app=app.replace('return r.complete ? makeProfile(r) : null;','return r.answered>0 ? makeProfile(r) : null;')
app=app.replace('state.weights = p ? Object.assign({}, p.weights) : Object.assign({}, P.defaultWeights);','// 선호 검사로 점수의 비중을 자동 변경하지 않는다.')
app=app.replace('if (state.profile) return { p: state.profile, weights: state.weights, applied: true };','if (state.profile) return { p: state.profile, weights: state.weights, applied: true };')
app=app.replace('return p ? { p: p, weights: p.weights, applied: false } : null;','return p ? { p: p, weights: state.weights, applied: false } : null;')
app=app.replace('state.selected = null; state.compare = null; state.rankLimit = 15;','state.selected = null; state.compare = null; state.rankLimit = 15; state.gu=""; syncAxes();')
app=app.replace('[nf(k.type2Areas), "곳", "금융 MBTI 유형 판정 상권", "L/V · E/P 두 글자 모두"]','[nf(k.type2Areas), "칸", "세 축 유형 확정", "상권×업종 · 일부 축 보류 12,844칸"]')
app=app.replace('s5: "L/V · E/P · 1,644곳"','s5: "업종 E/P · 공식 S/D · 7,678칸"')
app=app.replace('const p = state.profile;\n      $("weightText")','const p = state.profile;\n      drawGuMap(scoreRows());\n      $("weightText")')
app=app.replace('drawGuMap(scoreRows());','drawGuMap(scoreRows());\n      drawDiagnostics(scoreRows());')
app=app.replace('state.rankLimit = 15; drawRankTable(c);','state.rankLimit = 15; renderS6();')
app=app.replace('drawScoreMap(c);\n      drawRankTable(c);', '''const visible=c.rows.filter(r=>(!state.gu||A.gu[r.i]===state.gu)&&(!state.profile||!state.onlyMatch||C.matchLabel(A.type2[r.i],state.profile.matched)===C.MATCH));
      if(!visible.some(r=>r.i===state.selected))state.selected=visible.length?visible[0].i:null;
      drawScoreMap(c);
      drawRankTable(c);''')
app=app.replace('if (r) return r.total === null ? miss : s[bin5(r.total)];', 'if (r) return (state.gu&&A.gu[i]!==state.gu)||(state.profile&&state.onlyMatch&&C.matchLabel(A.type2[i],state.profile.matched)!==C.MATCH)?out:r.total === null ? miss : s[bin5(r.total)];')
app=app.replace('$("scoreLegend").innerHTML = rampLegend', '''if(state.gu){const pts=A.c.filter((_,i)=>A.gu[i]===state.gu);if(pts.length){const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);$('scoreMap').querySelector('svg').setAttribute('viewBox',`${Math.min(...xs)-40} ${Math.min(...ys)-40} ${Math.max(...xs)-Math.min(...xs)+80} ${Math.max(...ys)-Math.min(...ys)+80}`);}}
      $("scoreLegend").innerHTML = rampLegend''')
app=app.replace('let rows = c.rows;','let rows = c.rows;\n      if(state.gu) rows=rows.filter(r=>A.gu[r.i]===state.gu);')
app=app.replace('C.matchLabel(A.type2[r.i], p.matched) !== C.OTHER && A.type2[r.i]','C.matchLabel(A.type2[r.i], p.matched) === C.MATCH')
app=app.replace('if (p) cols.splice(4, 0,','cols.splice(4, 0,')
app=app.replace('html: (v) => matchBadge(v, p.matched)','html: (v) => p ? matchBadge(v,p.matched) : esc(v||"판정 보류")')
app=app.replace('const hit = c.rows.filter((x) => A.type2[x.i] && matched[A.type2[x.i]]);','const hit = c.rows.filter(x=>x.total!==null && C.matchLabel(A.type2[x.i],matched)===C.MATCH);')
app=app.replace('const nm = hit.filter((x) => matched[A.type2[x.i]] === C.MATCH).length;','const nm=hit.length;')
app=app.replace('if (e.target.closest("#clearAnswers")) { state.answers = {}; renderS7(); return; }','if (e.target.closest("#clearAnswers")) { state.answers={}; if(state.profile&&state.profile.result.source!=="직접 고르기")applyProfile(null); renderS7(); return; }')
app=app.replace('P.step5.medians','{lv_score:50,ep_score:50}')
app=app.replace('let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="상권 L/V 점수와 E/P 점수 산점도">`;', '''let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="상권 L/V 점수와 E/P 점수 산점도"><rect x="${x(45)}" y="${m.t}" width="${x(55)-x(45)}" height="${Hh-m.t-m.b}" fill="${gray}" opacity=".18"/><rect x="${m.l}" y="${y(55)}" width="${W-m.l-m.r}" height="${y(45)-y(55)}" fill="${gray}" opacity=".18"/>`;''')
app=app.replace('동점 순위', '동점 순위')
app=app.replace('const info = TYPES[result.type], w = C.sgWeights(result, P.step5.weights);','const info = TYPES[result.type];')
app=app.replace('["salesMonth", "comp", "close", "pf", "pw", "pr", "stores"].forEach((k) => { med[k] = C.median(rows.map((r) => r[k])); });','["salesMonth", "comp", "close", "pf", "pw", "pr", "stores"].forEach(k=>{ med[k]=C.median(rows.filter(r=>k!=="salesMonth"||r.sales!==null).map(r=>r[k])); });')
app=app.replace('host.innerHTML = `<div class="detail-head">','host.innerHTML = `<p class="note">${esc((P.unified[state.industry]||[])[i]?.official||"공식 지표 없음")} · ${esc((P.unified[state.industry]||[])[i]?.note||"세 축 판정 가능")} · 검사 결과는 성공·저위험 예측이 아닙니다.</p><div class="detail-head">')
app=replace_function(app,'drawMbtiResult','''    function drawMbtiResult() {
      const host=$('mbtiResult'),p=pendingProfile();
      if(!p){host.innerHTML='<h3>운영 선호</h3><p>문항에 답하거나 유형을 직접 고르세요.</p>';return;}
      const choices=p.matched.pattern.filter(Boolean).length;
      host.innerHTML=`<h3>${esc(p.type)} · ${esc(p.info['이름'])}</h3><p>${esc(p.text)}</p>
      <p>필터로 적용할 선호: <b>${p.matched.pattern.map((v,j)=>v||['L/V 제한 없음','E/P 제한 없음','S/D 제한 없음'][j]).join(' · ')}</b></p>
      <p class="note">4:1·5:0만 적용합니다. 3:2·미완료 축은 제한하지 않습니다. 현재 비중 ${weightText(state.weights)}를 그대로 씁니다.</p>
      <div class="actions"><button class="primary" data-act="on" ${choices?'':'disabled'}>선호 조건 적용</button><button class="ghost" data-act="off">선호 해제</button></div>`;
      host.onclick=e=>{const b=e.target.closest('[data-act]');if(b)applyProfile(b.dataset.act==='on'?pendingProfile():null);};
    }''')
app=replace_function(app,'drawV7','''    function drawV7() {
      const g=$('v7g'),T=C.typeCompare(P,state.industry,null,5,state.weights);
      $('v7c').innerHTML='<p class="note">現在'.replace('現在','현재')+' 공통 비중으로 세 축이 모두 일치하는 후보를 비교합니다. 서울 전체 같은 업종 기준이며 구 선택은 적용하지 않습니다.</p>';
      g.innerHTML='<div class="mini-grid">'+TYPE_ORDER.map(t=>`<div class="mini"><h4>${t} ${esc(TYPES[t]['이름'])}</h4><p>후보 ${T[t].pool}곳</p><ol>${T[t].top.map(r=>`<li>${esc(A.name[r.i])}<span class="sc">${s1f(r.total)}</span></li>`).join('')||'<li>조건에 맞는 후보 없음</li>'}</ol></div>`).join('')+'</div>';
      $('v7l').textContent='S는 저위험, D는 성장·수익을 뜻하지 않습니다. 유형별로 가중치를 바꾸지 않습니다.';
      found('v7',`${IND[state.industry].name}: 세 축 판정 후보 ${TYPE_ORDER.reduce((n,t)=>n+T[t].pool,0)}곳. 후보가 없는 유형을 다른 유형으로 채우지 않았습니다.`);
      $('v7t').innerHTML=table([{k:'t',l:'유형'},{k:'name',l:'상권'},{k:'total',l:'현재 점수',f:s1f}],TYPE_ORDER.flatMap(t=>T[t].top.map(r=>({t,name:A.name[r.i],total:r.total}))));
    }''')
# 직전 함수 교체는 이동 주석 전까지이므로 다른 렌더러는 보존된다.
gu=(HERE/'gu_map.js').read_text(encoding='utf-8')
app=app.replace('    // ------------------------------------------------------------ 이동',gu+'\n    // ------------------------------------------------------------ 이동')
app=app.replace('    initHeader();','    syncAxes();\n    initHeader();')
app=app.replace('s10: () => {}','s10: () => {drawGuMap(scoreRows());}')
# 호환 링크: 이전 공유 URL과 타입/지도 딥링크를 같은 최종본으로 연결한다.
app=app.replace('const h = (location.hash || "#s1").slice(1);','const rawHash=(location.hash||"#s1").slice(1); const h=({overview:"s1",find:"s6",detail:"s6",step5:"s7",distribution:"s8",rules:"s10"})[rawHash]||rawHash;')
(WEB/'app.js').write_text(app,encoding='utf-8')

html=(SOURCE/'template.html').read_text(encoding='utf-8')
html=html.replace('SpotFit 최종 산출물','SpotFit 팀 통합 최종 산출물')
html=html.replace('15문항 검사 → 상권 L/V · E/P 맞추기와 S/G 가중치.','15문항 운영 선호 → L/V·희망 업종 E/P·공식 S/D 조건으로 후보 비교.')
html=html.replace('상권 유형 L/V · E/P는 인구 구성과 객단가로 정한 대리 지표입니다.','상권 유형은 인구 구성·희망 업종 건당 금액·공식 영업 기간의 대리 지표입니다.')
html=html.replace('9개 데이터셋','공통 9종과 공식 상권변화지표')
html=html.replace('공통 9종과 공식 상권변화지표을 받았습니다.','공통 9종을 수집했고, 통합에서는 공식 상권변화지표(K08)를 추가로 연결했습니다.')
html=html.replace('STEP 4 · 5 변수 6개','STEP 4 · 5 변수 7개')
html=html.replace('추가한 6개','추가한 7개')
html=html.replace('금융 MBTI 기반 개인화','운영 선호 기반 후보 비교')
html=html.replace('상권 L/V × E/P 점수','직장 구성 비율 × 업종 건당 금액 백분위')
html=html.replace('<h3>계획서 목표별 결과</h3>','''<div class="callout"><b>팀 자료를 다시 비교한 11월 23일 통합본</b><p>보고서·EDA는 김지영, 공식 지표·검사지·픽셀 지도는 이승희, 재계산 검증·화면 연결·배포는 박성은의 산출물을 결합했습니다. 11월 19일 팀 합의와 통계적 근거는 구별합니다. <a href="#s10">선택 이유와 검증 결과</a></p></div><h3>계획서 목표별 결과</h3>''')
start=html.index('  <p class="lead">금융 MBTI 세 글자')
end=html.index('  <div class="seg big" id="mbtiMode"',start)
html=html[:start]+'''  <p class="lead">고객·가격 운영·영업 환경에 대한 선호를 묻는 팀 제작 초안입니다. L/V는 인구 구성, E/P는 희망 업종의 건당 금액, S/D는 공식 영업 기간 특성에 연결합니다. 각 축 5문항 중 4:1 이상만 후보 조건으로 적용합니다. 성장률·금융 성향·창업 성공률을 검증한 검사는 아닙니다.</p>\n'''+html[end:]
html=html.replace('가는 가로 · 세로선은 서울 중앙값(판정 기준)입니다','가운데 45~55 구간은 보류입니다. 가로축은 직장/(상주+직장) %, 세로축은 희망 업종 건당 금액 백분위입니다')
html=html.replace('STEP 5 설계표 (2026-11-14 승인) · 유형표 · 가중치','통합 STEP 5 규칙 · 유형표 · 공통 비중')
html=html.replace('S/G → 영역 가중치 [가정]','유형별 가중치를 자동 적용하지 않습니다')
html=html.replace('<p id="scoreStatus"','<div class="card pixel-panel"><h3>자치구별 상대 수준</h3><div id="guControls"></div><div id="guMap"></div><div id="guLegend" class="note"></div></div>\n  <p id="scoreStatus"')
html=html.replace('<div class="card" id="detail"></div>','<div class="card" id="detail"></div><div class="card"><h3>가정에 따른 순위 변화와 결과 다운로드</h3><p class="note">가중치 비교는 서울 전체 같은 업종 기준입니다. CSV는 현재 가중치·구·적용한 선호 조건을 반영합니다.</p><button id="downloadCsv">현재 조건 CSV 다운로드</button><div id="sensitivity"></div></div>')
start=html.index('  <p class="lead">팀 저장소에서 이 결과를')
end=html.index('\n</section>',start)
html=html[:start]+'''  <p class="lead">원본 팀원 폴더는 읽기만 합니다. 이 통합본은 박성은/team_unified_final에 별도로 작성했습니다.</p>
  <div class="card"><p>김지영: 공통 데이터·원패널 점수·10개 보고서 화면·EDA 7종</p><p>이승희: 공식 S/D·검사지·픽셀 지도 자산과 표시 규칙</p><p>박성은: 독립 재계산·비교 검증·공통 규칙 연결·공유 배포</p><pre>python 박성은/team_unified_final/build.py
node 박성은/team_unified_final/verify.js</pre><p>완성 HTML은 report/SpotFit_팀통합_최종대시보드.html입니다. 파일을 더블클릭해 열 수 있습니다. 외부 지도 타일·API·설치 없이 동작합니다.</p></div>'''+html[end:]
start=html.index('  <h3>팀이 정해야 할 것 [가정]</h3>')
end=html.index('\n</section>',start)
html=html[:start]+'''  <h3>객관적 재검토와 통합 선택</h3>
  <div class="card"><p>작성자 이름이나 기존 박성은 안을 우선순위로 두지 않았습니다. 목적 적합성·원입력 재현성·해석 가능성·결측 처리·성과 검증 여부를 기준으로 비교했습니다.</p>
  <ul><li>희망 업종을 비교하므로 업종 내 점수와 E/P를 채택했습니다. 업종 전체의 건당 금액을 섞으면 사용자가 고른 업종의 의미가 흐려집니다.</li>
  <li>수요는 유동·직장·상주의 세 백분위가 모두 있을 때 같은 구성으로 평균합니다. 유동 하나만으로 실제 구매 수요를 설명할 수는 없습니다.</li>
  <li>2025년 한 해의 매출 수준을 ‘성장’으로 바꾸지 않습니다. 공식 S/D는 장기 영업 기간 특성이고 분기 변동성은 별도 참고입니다.</li>
  <li>상권 전체를 중앙값으로 강제 양분하는 유형 대신 경계와 자료 부족을 보류합니다. 45/55·점포 5개·비교 30곳은 운영 가정이며 객관적 정답은 아닙니다.</li>
  <li>기본 비중 30·25·15·30은 비교용 기본 시나리오입니다. 실제 창업 성과 자료가 없어 최적이라고 입증할 수 없습니다. 사용자는 비중을 바꿔 비교할 수 있습니다.</li>
  <li>L/V는 실제 고객 구성이 아니고 E/P는 가격 민감도 검증이 아닙니다. 공식 HH·LL의 S/D 연결은 팀의 해석입니다.</li></ul>
  <p>11월 19일 슬랙에 두 팀원이 공식 지표·공통 기준 채택을 명시했습니다. 이번 보고서·화면 통합 전체에 대한 새로운 팀 승인을 의미하지는 않습니다.</p>
  <p><a href="audit.json" download>원패널 재계산·최신 팀원 비교 결과 JSON</a> · <a href="review.md" download>팀원별 채택·수정 이유 보고서</a></p>
  </div><div id="auditSummary" class="card"></div>'''+html[end:]
html=html.replace('<tr><td>서울시 상권변화지표 (OA-15576)</td><td>상권 쪽 S/G 판정. 지금은 창업자 S/G를 가중치로만 씁니다</td></tr>','<tr><td>실제 고객 구성·성과 관측</td><td>L/V 대리 구분과 추천 결과를 실증 검증합니다. 공식 영업 기간 자료는 이미 S/D에 사용했습니다.</td></tr>')
html=html.replace('/*__APP__*/','/*__APP__*/')
(WEB/'template.html').write_text(html,encoding='utf-8')
css=(SOURCE/'style.css').read_text(encoding='utf-8')+'\n'+(HERE/'team_style.css').read_text(encoding='utf-8')
(WEB/'style.css').write_text(css,encoding='utf-8')
print('팀원 원본은 수정하지 않고 통합 화면 생성 완료')
from short_quiz_upgrade import upgrade
upgrade(WEB)
