(() => {
  'use strict';
  const C=window.SpotFit,$=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(x,d=0)=>C.valid(x)?x.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'자료 없음';
  const money=x=>C.valid(x)?num(x/10000)+'만 원':'자료 없음';
  const pct=x=>C.valid(x)?(x>0?'+':'')+num(x,1)+'%':'자료 없음';
  const modeNames={avg:'세 인구 완비 평균',available:'있는 인구 평균 · 대안',floating:'유동인구',worker:'직장인구',resident:'상주인구'};
  const axisNames={LV:'고객층 대리 구분',EP:'업종 내 건당 금액',SD:'영업 기간 특성'};
  const scoreNames=['매출 잠재력','경쟁','안정성·신뢰도 낮음','수요'];
  const state={meta:null,geo:[],code:'CS100010',rows:[],quarters:[],all:[],baseScope:[],scope:[],selected:null,compare:new Set(),weights:{...C.DEFAULT},mode:'avg',effectiveMode:'avg',prefs:{LV:'',EP:'',SD:''},apply:false,linked:false,answers:{},tab:'overview',page:0,sort:'score_total',direction:-1,request:0};
  const cache=new Map(),PLOT={responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d']},blue='#2878b5',orange='#d97942';
  const layout=extra=>({paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{family:'Noto Sans KR,system-ui,sans-serif',size:11,color:'#173c36'},margin:{l:70,r:24,t:20,b:45},...extra});
  const draw=(id,data,extra={})=>Plotly.react($(id),data,layout(extra),PLOT).then(()=>Plotly.Plots.resize($(id)));
  const empty=(id,message)=>{Plotly.purge($(id));$(id).innerHTML=`<div class="empty-chart">${esc(message)}</div>`;};
  const table=(id,heads,rows)=>$(id).innerHTML='<thead><tr>'+heads.map(h=>`<th>${esc(h)}</th>`).join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>`<td>${esc(v)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  const tiles=(id,items)=>$(id).innerHTML=items.map(([a,b,c])=>`<div class="stat"><span>${esc(a)}</span><strong>${esc(b)}</strong><small>${esc(c)}</small></div>`).join('');
  const industry=()=>state.meta.industries.find(i=>i.code===state.code);
  const target=r=>r.score_status==='점수 대상';
  const values=r=>[r.score_sales,r.score_comp,r.score_stab,r.score_dem];
  const selected=()=>state.scope.find(r=>r.trdar_code===state.selected);
  const activeChoices=()=>state.apply?state.prefs:{};
  const unpack=(columns,rows)=>rows.map(a=>Object.fromEntries(columns.map((c,i)=>[c,a[i]])));
  async function read(url){const r=await fetch(url);if(!r.ok)throw new Error('자료를 불러오지 못했습니다. 새로고침해 주세요.');return r.json();}
  function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
  async function loadIndustry(code){
    const request=++state.request;status('선택 업종의 통합 자료를 불러오는 중입니다…');document.querySelector('.content').classList.add('loading');
    try{let data=cache.get(code);if(!data){data=await read('data/'+code+'.json');cache.set(code,data);}if(request!==state.request)return;state.code=code;state.rows=unpack(data.columns,data.rows);state.quarters=unpack(data.quarter_columns,data.quarters);state.selected=null;state.compare.clear();state.page=0;render();}
    catch(error){if(request===state.request){status(error.message,true);$('industry').value=state.code;}}
    finally{if(request===state.request)document.querySelector('.content').classList.remove('loading');}
  }
  function go(tab){if(!['overview','find','detail','step5','distribution','rules'].includes(tab))tab='overview';state.tab=tab;history.replaceState(null,'','#'+tab);document.querySelectorAll('.tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-selected',String(b.dataset.tab===tab));});document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===tab));renderActive();}
  function render(){
    if(!state.meta||!state.rows.length)return;
    const hasLink=state.linked&&state.apply&&state.prefs.LV;
    state.effectiveMode=hasLink?(state.prefs.LV==='L'?'resident':'floating'):state.mode;
    $('demand').disabled=!!hasLink;
    $('linked-note').textContent=hasLink?'선택한 '+state.prefs.LV+'의 수요를 모든 화면에 적용합니다.':state.linked?'L 또는 V 선호 필터가 적용될 때 연결됩니다.':'기본은 끄기입니다. 선택하면 적용하는 분석 가정입니다.';
    state.all=state.rows.map(r=>C.score(r,state.weights,state.effectiveMode)).sort(C.descending);
    const gu=$('district').value,type=$('area-type').value;
    state.baseScope=state.all.filter(r=>(!gu||r.gu_name===gu)&&(!type||r.trdar_type===type));
    state.scope=state.baseScope.filter(r=>C.matches(r,activeChoices()));
    if(!state.scope.some(r=>r.trdar_code===state.selected)){state.selected=state.scope.find(r=>C.valid(r.score_total))?.trdar_code??state.scope[0]?.trdar_code??null;state.compare=new Set(state.selected?[state.selected]:[]);}
    state.compare=new Set([...state.compare].filter(c=>state.scope.some(r=>r.trdar_code===c)));
    const total=C.KEYS.reduce((n,k)=>n+state.weights[k],0),changed=C.KEYS.some(k=>state.weights[k]!==C.DEFAULT[k]),preference=Object.values(activeChoices()).filter(Boolean).join(' / ')||'제한 없음';
    C.KEYS.forEach(k=>$(k+'-value').textContent=state.weights[k]);$('weight-sum').textContent=total;
    $('active-basis').textContent=`공통 적용 · ${modeNames[state.effectiveMode]} · 매출 ${state.weights.sales} / 경쟁 ${state.weights.comp} / 안정성 ${state.weights.stab} / 수요 ${state.weights.dem} · 선호 ${preference}`+(changed||state.effectiveMode!=='avg'?' · 기본 조건을 바꾼 실험':' · 통합 기본 조건');
    const notes=[];if(!state.scope.length)notes.push('조건에 맞는 상권이 없습니다. 선호 조건이나 지역을 넓혀 보세요.');if(!total)notes.push('가중치가 모두 0이므로 점수를 계산하지 않습니다.');if(!industry().target)notes.push('평균 점포 5개 이상인 비교 상권이 30곳 미만인 업종입니다. 점수 없이 원값만 참고하세요.');if(industry().target&&!industry().sales)notes.push('이 업종은 매출 자료 또는 유효 비교 상권이 부족합니다. 매출이 낮다는 뜻이 아니며 유효 영역만 계산합니다.');
    const corr=C.spearman(state.all,'score_comp','score_dem');if(C.valid(corr)&&Math.abs(corr)>=.8)notes.push('경쟁과 수요의 상관이 '+num(corr,3)+'으로 높습니다. 같은 정보가 겹칠 수 있어 비중을 바꿔 비교하세요.');
    $('notice').hidden=!notes.length;$('notice').textContent=notes.join(' ');
    status(`${industry().name} · 2025년 · ${num(state.scope.length)}곳 표시 · ${num(state.baseScope.length)}곳 중 선호 조건 반영 · 점수는 서울 전체 같은 업종 기준`);
    renderActive();
  }
  function renderActive(){if(!state.meta||!state.rows.length)return;({overview:renderOverview,find:renderFind,detail:renderDetail,step5:renderTypes,distribution:renderDistribution,rules:renderRules})[state.tab]();}
  function renderOverview(){
    const c=state.meta.counts;
    tiles('overview-stats',[['전체 점수 대상',num(c.target)+'개','77개 업종의 상권×업종 조합'],['세 축 완전 판정',num(c.full)+'개',num(c.typed_industries)+'개 업종 · 전체 조합 단위'],['판정 보류',num(c.held)+'개','대상 중 일부 축 보류'],['기본 점수 변경',num(c.default_changed)+'개','세 인구 완비 조건으로 통일']]);
    $('decisions').innerHTML=[['희망 업종별 비교','L/V·S/D는 상권 속성, E/P는 같은 업종의 건당 금액 상대 수준입니다.'],['공식 지표로 S/D 연결','2025Q4 영업 기간 특성 HH→S, LL→D. LH·HL은 원래 명칭을 보존하고 대응을 보류합니다.'],['결측 처리 통일','기본 수요 평균은 세 인구 지표가 모두 있을 때만 계산합니다. 영역 결측은 종합 점수에서 비중을 다시 나눕니다.'],['검사와 화면을 연결','뚜렷한 선호 축만 필터로 제안합니다. 직접 선택·가중치·수요 모드는 모든 화면에서 함께 적용됩니다.']].map(([a,b])=>`<div class="decision"><strong>${esc(a)}</strong><p>${esc(b)}</p></div>`).join('');
    draw('type-chart',[{type:'bar',x:state.meta.types.map(t=>t.code),y:state.meta.types.map(t=>t.count),marker:{color:state.meta.types.map(t=>t.code[0]==='L'?'#789e80':blue)},text:state.meta.types.map(t=>num(t.count)),textposition:'outside',cliponaxis:false,hovertemplate:'%{x}: %{y:,}개 조합<extra></extra>'}],{margin:{l:48,r:15,t:24,b:35},yaxis:{title:'상권×업종 수',gridcolor:'#e8ede5'},showlegend:false});
    const g=state.baseScope,nt=g.filter(target),full=nt.filter(r=>r.candidate_type);
    $('coverage-note').textContent=`${industry().name} · 지역·상권 구분 조건 안 ${num(g.length)}곳. 선호 필터를 적용하기 전의 범위입니다.`;
    draw('coverage-chart',[{type:'bar',orientation:'h',y:['세 축 판정','일부 축 보류','점수 대상 아님'],x:[full.length,nt.length-full.length,g.length-nt.length],marker:{color:['#789e80','#d49b71','#c9d1c3']},text:[full.length,nt.length-full.length,g.length-nt.length].map(n=>num(n)+'곳'),textposition:'outside',cliponaxis:false}],{margin:{l:98,r:55,t:15,b:30},xaxis:{rangemode:'tozero',gridcolor:'#e8ede5'},yaxis:{autorange:'reversed'}});
    $('integration-findings').innerHTML=`<p>이전 기본 점수와 비교해 <b>${num(c.default_changed)}개 조합</b>이 변했고, 최대 절대 변화는 ${num(c.max_score_change,2)}점입니다. 원자료 차이가 아니라 인구 지표 결측 처리의 차이를 맞춘 결과입니다.</p><p>백분위 55가 계산상 아주 조금 더 크게 표현되던 ${num(c.boundary_reclassified)}개 조합은 정확한 경계 보류로 바로잡았습니다. 그 결과 세 축 판정은 기존 공식 S/D 구현의 7,680개에서 ${num(c.full)}개가 됐습니다. <a href="assets/경계정밀도_변경내역.csv" download>경계 변경 내역 ↓</a></p><p>공식 S/D와 분기 변동성 S/D는 두 결과가 모두 판정한 ${num(c.sd_both_known)}개에서 ${num(c.sd_agreement*100,1)}% 일치했습니다. 영업 기간과 분기별 흔들림을 분리해 상세에서 함께 보여 줍니다.</p><p>2025Q4 공식 지표는 ${Object.entries(state.meta.area_sd).map(([a,b])=>esc(a)+' '+num(b)+'곳').join(' · ')}입니다. 이는 고유 상권 수이며 업종 조합 수와 다릅니다.</p>`;
  }
  function renderFind(){
    const g=state.scope,t=g.filter(target),full=t.filter(r=>r.candidate_type);
    tiles('find-stats',[['현재 표시 상권',num(g.length)+'곳','현재 업종·지역·선호 조건'],['점수가 있는 상권',num(g.filter(r=>C.valid(r.score_total)).length)+'곳','0~100 업종 내 비교'],['세 축 완전 판정',num(full.length)+'곳','유형 일치가 성공을 보장하지 않음'],['판정 보류',num(t.length-full.length)+'곳','점수 대상 중 일부 축 보류']]);renderMap();renderTable();
    const corr=C.spearman(state.all,'score_comp','score_dem'),base=state.scope.filter(r=>C.valid(r.score_total)),alt=base.map(r=>C.score(r,{...state.weights,comp:0},state.effectiveMode)).filter(r=>C.valid(r.score_total)).sort(C.descending),k=Math.min(10,base.length),top=new Set(base.slice(0,k).map(r=>r.trdar_code)),retained=alt.slice(0,k).filter(r=>top.has(r.trdar_code)).length;
    $('overlap').textContent=`업종 전체 경쟁·수요 상관 ${num(corr,3)}. `+(k?`경쟁 영역을 빼면 현재 상위 ${k}곳 중 ${k-retained}곳이 바뀝니다. `:'')+'변화는 가정에 대한 민감도이며 추천 성능을 검증하지 않습니다.';
  }
  function renderMap(){
    if(!state.scope.length){empty('map','조건에 맞는 상권이 없습니다.');return;}
    const lookup=new Map(state.scope.map(r=>[r.trdar_code,r])),geo=state.geo.filter(g=>lookup.has(g.trdar_code));if(!geo.length){empty('map','표시할 경계가 없습니다.');return;}
    const traces=[];for(const has of [false,true]){const features=geo.filter(g=>C.valid(lookup.get(g.trdar_code).score_total)===has);if(!features.length)continue;traces.push({type:'choroplethmap',geojson:{type:'FeatureCollection',features:features.map(g=>({type:'Feature',id:g.trdar_code,properties:{},geometry:g.geometry}))},locations:features.map(g=>g.trdar_code),z:features.map(g=>has?lookup.get(g.trdar_code).score_total:0),zmin:0,zmax:100,colorscale:has?[[0,'#dbe9ed'],[.5,'#5b9dba'],[1,'#174b77']]:[[0,'#d8ddd7'],[1,'#d8ddd7']],showscale:has,marker:{line:{width:.4,color:'#fff'},opacity:.95},colorbar:{title:{text:'종합 점수',side:'right',font:{size:10}},thickness:10,len:.5},customdata:features.map(g=>{const r=lookup.get(g.trdar_code);return [r.trdar_code,r.trdar_name,r.gu_name,has?num(r.score_total,1)+'점':r.score_status,r.candidate_type??'유형 보류'];}),hovertemplate:'<b>%{customdata[1]}</b><br>%{customdata[2]} · %{customdata[3]}<br>%{customdata[4]}<extra></extra>'});}
    const lons=geo.map(g=>g.lon),lats=geo.map(g=>g.lat),span=Math.max(Math.max(...lons)-Math.min(...lons),(Math.max(...lats)-Math.min(...lats))*1.25,.01),chosen=geo.find(g=>g.trdar_code===state.selected);if(chosen)traces.push({type:'scattermap',lon:[chosen.lon],lat:[chosen.lat],mode:'markers',marker:{color:orange,size:12},customdata:[[chosen.trdar_code]],hoverinfo:'skip'});
    draw('map',traces,{margin:{l:0,r:35,t:0,b:0},map:{style:'white-bg',center:{lon:(Math.min(...lons)+Math.max(...lons))/2,lat:(Math.min(...lats)+Math.max(...lats))/2},zoom:Math.max(8.7,Math.min(14,Math.log2(560*360/(span*512))))},showlegend:false,uirevision:state.code+'|'+$('district').value+'|'+JSON.stringify(activeChoices())}).then(()=>{$('map').removeAllListeners('plotly_click');$('map').on('plotly_click',e=>{const p=e.points[0],code=p.location||p.customdata?.[0];if(lookup.has(code))openArea(code);});});
  }
  const cols=[['trdar_name','상권'],['gu_name','자치구'],['candidate_type','유형'],['score_total','현재 점수'],['score_total_default','통합 기본 점수'],['n_areas','계산 영역'],['score_sales','매출'],['score_comp','경쟁'],['score_stab','안정성'],['score_dem','수요'],['stores','평균 점포'],['score_status','점수 상태']];
  function searchRows(){return state.scope.filter(r=>r.trdar_name.includes($('search').value.trim()));}
  function renderTable(){
    const rows=searchRows().sort((a,b)=>{const x=a[state.sort],y=b[state.sort];if(x==null)return y==null?0:1;if(y==null)return -1;return (typeof x==='string'?x.localeCompare(y):x-y)*state.direction||C.descending(a,b);}),pages=Math.max(1,Math.ceil(rows.length/15));state.page=Math.min(state.page,pages-1);
    $('score-table').innerHTML='<thead><tr>'+cols.map(([k,n])=>`<th><button data-sort="${k}">${esc(n)}${state.sort===k?(state.direction>0?' ↑':' ↓'):''}</button></th>`).join('')+'</tr></thead><tbody>'+rows.slice(state.page*15,state.page*15+15).map(r=>`<tr data-code="${r.trdar_code}" tabindex="0" aria-label="${esc(r.trdar_name)} 상세 보기">`+cols.map(([k])=>`<td>${k==='candidate_type'?esc(r[k]??'보류'):['trdar_name','gu_name','score_status'].includes(k)?esc(r[k]):num(r[k],k==='n_areas'?0:1)}</td>`).join('')+'</tr>').join('')+'</tbody>';
    $('table-count').textContent=num(rows.length)+'곳 · 행 클릭 → 상세';$('page-count').textContent=`${state.page+1} / ${pages}`;$('previous').disabled=state.page===0;$('next').disabled=state.page>=pages-1;$('download-results').disabled=!rows.length;
  }
  function openArea(code){state.selected=code;state.compare=new Set([code]);go('detail');document.querySelector('.tabs').scrollIntoView({block:'start',behavior:'smooth'});}
  function renderDetail(){
    const r=selected();$('area').innerHTML=state.scope.map(r=>`<option value="${r.trdar_code}" ${r.trdar_code===state.selected?'selected':''}>${esc(r.trdar_name)} · ${esc(r.gu_name)}</option>`).join('');
    if(!r){$('detail-title').textContent='조건에 맞는 상권이 없습니다';$('detail-subtitle').textContent='선호나 지역 조건을 넓혀 주세요.';$('detail-stats').innerHTML='';['bars','radar','sales-trend','flow','facets'].forEach(id=>empty(id,'표시할 상권이 없습니다.'));['axis-table','raw-table','qoq-table'].forEach(id=>$(id).innerHTML='');['detail-type-note','volatility-note','freshness'].forEach(id=>$(id).textContent='');$('compare-options').innerHTML='';return;}
    $('detail-title').textContent=r.trdar_name;$('detail-subtitle').textContent=`${industry().name} · ${r.gu_name} · ${r.trdar_type}`;
    tiles('detail-stats',[['현재 조건 점수',C.valid(r.score_total)?num(r.score_total,1)+'점':'점수 없음',r.n_areas+'개 유효 영역'],['통합 기본 점수',C.valid(r.score_total_default)?num(r.score_total_default,1)+'점':'점수 없음','세 지표 완비·30/25/15/30'],['점포당 월매출',money(r.sales_month),r.sales_area_status],['평균 점포 수',num(r.stores,1)+'개','보정 폐업률 '+num(r.close_pct_shrunk,1)+'%']]);
    const v=values(r),t=state.all.filter(target),med=['score_sales','score_comp','score_stab','score_dem'].map(k=>C.median(t.map(r=>r[k])));
    const annotations=v.flatMap((x,i)=>C.valid(x)?[]:[{x:1,y:scoreNames[i],xref:'x',yref:'y',text:'자료 없음',showarrow:false,xanchor:'left',font:{size:10,color:'#849080'}}]);
    draw('bars',[{type:'bar',orientation:'h',x:v,y:scoreNames,marker:{color:blue},text:v.map(x=>C.valid(x)?num(x,1)+'점':''),textposition:'outside',cliponaxis:false,name:'선택 상권'},{type:'scatter',mode:'markers',x:med,y:scoreNames,marker:{symbol:'line-ns-open',size:23,color:orange,line:{width:2}},name:'업종 중앙값'}],{annotations,margin:{l:130,r:48,t:12,b:35},xaxis:{range:[0,107],title:'업종 안 점수',gridcolor:'#e8ede5'},yaxis:{autorange:'reversed'},showlegend:false});
    draw('radar',[{type:'scatterpolar',r:[...med,med[0]],theta:[...scoreNames,scoreNames[0]],mode:'lines+markers',line:{color:orange,dash:'dash'},connectgaps:false,name:'업종 중앙값'},{type:'scatterpolar',r:[...v,v[0]],theta:[...scoreNames,scoreNames[0]],mode:'lines+markers',line:{color:blue},connectgaps:false,name:r.trdar_name}],{margin:{l:75,r:75,t:35,b:45},polar:{radialaxis:{range:[0,100],tickvals:[0,25,50,75,100],gridcolor:'#e1e8df'},angularaxis:{tickfont:{size:9}}},legend:{orientation:'h',y:-.2,font:{size:10}}});
    $('detail-type-note').textContent=`${r.candidate_type??r.type_status} · ${r.known_axes}/3축 판정`+(r.hold_reason?' · '+r.hold_reason:' · 세 축 모두 판정된 분석용 대리 유형');
    table('axis-table',['축','판정','자료와 상대 수준','판정·보류 이유'],[['L/V',r.LV??'보류',C.valid(r.resident_share_proxy)?'상주/(상주+직장) '+num(r.resident_share_proxy*100,1)+'%':'상주·직장인구 자료 부족',r.LV_reason],['E/P',r.EP??'보류','건당 '+(C.valid(r.ticket)?num(r.ticket)+'원':'자료 없음')+' · 업종 내 백분위 '+num(r.ticket_pct,1)+' · 유효 비교 '+num(r.ep_peers)+'곳',r.EP_reason],['S/D',r.SD??'대응 보류',`2025Q4 ${r.chg_code??'자료 없음'} ${r.chg_name??''} · 운영 ${num(r.run_months)}개월 / 폐업 ${num(r.closed_months)}개월`,r.SD_reason]]);
    const rawMed=k=>C.median(t.filter(x=>k!=='sales_month'||C.valid(x.score_sales)).map(x=>x[k]));
    table('raw-table',['지표','선택 상권','업종 중앙값','해석'],[['점포당 월매출',money(r.sales_month),money(rawMed('sales_month')),'네 분기 관측·비교 수 조건은 점수에 별도 적용'],['유동 1,000명당 같은 업종 점포',num(r.comp_ratio,3)+'개',num(rawMed('comp_ratio'),3)+'개','낮을수록 경쟁 점수가 높음'],['축소 추정 폐업률',num(r.close_pct_shrunk,1)+'%',num(rawMed('close_pct_shrunk'),1)+'%','1년치라 신뢰도 낮음'],...['floating_density','worker_density','resident_density'].map((k,i)=>[['면적당 유동인구','면적당 직장인구','면적당 상주인구'][i],num(r[k])+'명/㎢',num(rawMed(k))+'명/㎢','실제 고객 수가 아닌 인구 대리 지표'])]);
    $('freshness').textContent='상주·직장인구는 2025년 안에서 값이 변하지 않습니다. 실제 통계 기준 시점은 미확인입니다. 서울 평균 영업 기간의 두 원값은 공유 마트에 없어 채우지 않았고 제공된 공식 H/L 코드를 사용했습니다.';
    const q=[1,2,3,4].map(i=>state.quarters.find(q=>q.trdar_code===r.trdar_code&&q.quarter===`2025${i}`)||{quarter:`2025${i}`}),labels=['1분기','2분기','3분기','4분기'];
    if(q.some(x=>C.valid(x.sales_month)))draw('sales-trend',[{type:'scatter',mode:'lines+markers',x:labels,y:q.map(x=>C.valid(x.sales_month)?x.sales_month/10000:null),connectgaps:false,line:{color:blue},hovertemplate:'%{x}: %{y:,.0f}만 원<extra></extra>'}],{yaxis:{title:'점포당 월매출 (만 원)',rangemode:'tozero',gridcolor:'#e8ede5'}});else empty('sales-trend','매출 자료가 없습니다.');
    draw('flow',[{type:'bar',x:labels,y:q.map(x=>x.open_count??null),name:'개업',marker:{color:'#789e80'}},{type:'bar',x:labels,y:q.map(x=>x.close_count??null),name:'폐업',marker:{color:orange}}],{barmode:'group',legend:{orientation:'h',y:1.16},yaxis:{title:'건수',rangemode:'tozero',gridcolor:'#e8ede5'}});
    table('qoq-table',['분기','매출 증감률 원값','상하위 5% 경계 적용'],q.map((x,i)=>[labels[i],pct(x.qoq_raw),pct(x.qoq_winsor)]));
    $('volatility-note').textContent=`네 분기의 점포당 월매출 변동계수(CV) ${num(r.sales_month_cv,3)}, 유동인구 CV ${num(r.floating_cv,3)}. CV는 모표준편차/평균으로 계절 변화가 섞일 수 있습니다. 과거 변동성 기준 유형은 ${r.previous_type??'보류'}이며, 현재 공식 S/D 기반 유형 ${r.candidate_type??'보류'}와 구분합니다. 위 증감률과 CV는 점수·현재 S/D에 더하지 않습니다.`;
    renderCompareOptions();renderFacets();
  }
  function renderCompareOptions(){
    const box=$('compare-options');if(!box.querySelector('#compare-search'))box.innerHTML='<input id="compare-search" type="search" aria-label="비교할 상권 검색" placeholder="비교할 상권 검색"><div id="compare-list"></div>';
    const term=$('compare-search').value.trim(),list=[...state.scope.filter(r=>state.compare.has(r.trdar_code)),...state.scope.filter(r=>!state.compare.has(r.trdar_code)&&r.trdar_name.includes(term))].slice(0,60);
    $('compare-list').innerHTML=list.map(r=>`<label><input type="checkbox" data-compare="${r.trdar_code}" ${state.compare.has(r.trdar_code)?'checked':''} ${state.compare.size>=4&&!state.compare.has(r.trdar_code)?'disabled':''}>${esc(r.trdar_name)}</label>`).join('')+`<p class="fineprint">${state.compare.size}/4곳 선택 · 60곳까지 표시, 검색으로 다른 상권을 찾을 수 있습니다.</p>`;
  }
  function renderFacets(){
    const rows=[...state.compare].map(c=>state.scope.find(r=>r.trdar_code===c)).filter(Boolean);if(!rows.length){empty('facets','비교할 상권을 선택하세요.');return;}
    const columns=innerWidth<700?1:2,nrows=Math.ceil(rows.length/columns),traces=[],opts={height:nrows*235,margin:{l:125,r:30,t:35,b:35},annotations:[],showlegend:false};$('facets').style.height=opts.height+'px';
    rows.forEach((r,i)=>{const a=i===0?'':String(i+1),col=i%columns,row=Math.floor(i/columns),x0=col/columns,y1=1-row/nrows;opts['xaxis'+a]={domain:[x0,x0+.84/columns],range:[0,108],anchor:'y'+a,gridcolor:'#e8ede5'};opts['yaxis'+a]={domain:[y1-.8/nrows,y1],anchor:'x'+a,autorange:'reversed',tickfont:{size:9}};traces.push({type:'bar',orientation:'h',x:values(r),y:scoreNames,xaxis:'x'+a,yaxis:'y'+a,marker:{color:[blue,'#80a390','#b8b577','#d49b71']},text:values(r).map(x=>C.valid(x)?num(x,1):''),textposition:'outside',cliponaxis:false});opts.annotations.push({text:r.trdar_name,x:x0,y:y1+.055,xref:'paper',yref:'paper',showarrow:false,xanchor:'left',font:{size:11}});});draw('facets',traces,opts);
  }
  function renderTypes(){
    const t=state.baseScope.filter(target),full=t.filter(r=>r.candidate_type),chosen=Object.values(activeChoices()).filter(Boolean).join('');
    $('type-cards').innerHTML=state.meta.types.map(type=>`<button class="type-card ${chosen===type.code?'selected':''}" data-type="${type.code}" aria-pressed="${chosen===type.code}"><span class="type-code">${type.code}</span><span>${esc(type.name)}</span><strong>${num(full.filter(r=>r.candidate_type===type.code).length)}<small>곳</small></strong><small>전체 ${num(type.count)}개 조합</small></button>`).join('');
    $('preference-summary').textContent='현재 적용 선호: '+(Object.entries(activeChoices()).filter(([,v])=>v).map(([a,v])=>a+' '+v).join(' · ')||'제한 없음')+' · 유형은 선택 조건이며 점수에 보너스를 더하지 않습니다. 현재 점수와 수요 모드는 다른 화면과 같습니다.';
    const current=state.scope.filter(target);tiles('type-stats',[['조건 안 점수 대상',num(current.length)+'곳','희망 업종·지역·선호 반영'],['완전 판정',num(current.filter(r=>r.candidate_type).length)+'곳','세 축이 모두 판정된 후보'],['일부 축 보류',num(current.filter(r=>!r.candidate_type).length)+'곳','보류 유형을 임의로 채우지 않음'],['현재 점수 중앙값',num(C.median(current.map(r=>r.score_total)),1)+'점','같은 업종 안의 상대 비교']]);
    const rows=current.slice(0,15);$('type-results').innerHTML='<thead><tr>'+['상권','유형','L/V','E/P','S/D','현재 점수','보류 사유'].map(x=>`<th>${x}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>`<tr data-code="${r.trdar_code}" tabindex="0" aria-label="${esc(r.trdar_name)} 상세 보기"><td>${esc(r.trdar_name)}</td><td>${esc(r.candidate_type??'보류')}</td><td>${esc(r.LV??'보류')}</td><td>${esc(r.EP??'보류')}</td><td>${esc(r.SD??'대응 보류')}</td><td>${num(r.score_total,1)}</td><td>${esc(r.hold_reason||'—')}</td></tr>`).join('')+'</tbody>';
    renderQuizResult();
  }
  function initQuiz(){
    $('quiz').innerHTML=state.meta.questions.map((q,i)=>`<div class="quiz-question"><fieldset><legend>${i+1}. ${esc(q.text)}</legend>${q.options.map((o,j)=>`<label><input type="radio" name="question-${q.id}" data-question="${q.id}" value="${o.value}"><span>${String.fromCharCode(65+j)}. ${esc(o.label)}</span></label>`).join('')}</fieldset></div>`).join('');
  }
  function renderQuizResult(){
    const r=C.quizResult(state.meta.questions,state.answers),type=r.code?state.meta.types.find(t=>t.code===r.code):null;
    $('quiz-result').innerHTML=`<strong>${r.code?esc(r.code+' '+type.name):'응답 '+r.answered+'/15'}</strong><div class="quiz-axis">`+Object.entries(r.axes).map(([a,x])=>`${esc(axisNames[a])}: ${Object.entries(x.counts).map(([v,n])=>v+' '+n).join(' : ')} · ${x.status}`).join('<br>')+'</div><p class="fineprint">'+(r.answered===15?'다수 응답의 세 글자와 실제 적용할 필터는 다를 수 있습니다. 경계 축은 제한하지 않습니다.':'다 답한 기준 중 뚜렷한 축만 필터로 제안합니다. 미완료 축의 성향을 추론하지 않습니다.')+'</p>';
    $('apply-quiz').disabled=!Object.values(r.choices).some(Boolean)&&r.answered!==15;
  }
  function renderDistribution(){
    const key=$('metric').value,transform=x=>key==='sales_month'?x/10000:x,rows=state.scope.filter(r=>C.valid(r[key]));
    if(!rows.length)empty('histogram','표시할 값이 없습니다.');else{const a=rows.map(r=>transform(r[key])).sort((a,b)=>a-b),cap=a[Math.floor((a.length-1)*.99)];draw('histogram',[true,false].map(t=>({type:'histogram',x:rows.filter(r=>target(r)===t).map(r=>Math.min(transform(r[key]),cap)),nbinsx:35,name:t?'점수 대상':'참고용',marker:{color:t?blue:'#c6cfbe'},opacity:.8})),{barmode:'stack',xaxis:{title:key==='sales_month'?'점포당 월매출 (만 원)':$('metric').selectedOptions[0].text},yaxis:{title:'상권 수',gridcolor:'#e8ede5'},legend:{orientation:'h',y:1.13},shapes:key==='stores'?[{type:'line',x0:5,x1:5,y0:0,y1:1,yref:'paper',line:{color:orange,dash:'dash'}}]:[]});}
    const groups=new Map();state.scope.filter(r=>C.valid(r.score_total)).forEach(r=>{if(!groups.has(r.gu_name))groups.set(r.gu_name,[]);groups.get(r.gu_name).push(r.score_total);});const districts=[...groups].map(([name,a])=>({name,median:C.median(a),n:a.length})).sort((a,b)=>a.median-b.median);
    if(!districts.length)empty('district-chart','점수가 있는 상권이 없습니다.');else{const height=Math.max(290,districts.length*25+60);$('district-chart').style.height=height+'px';draw('district-chart',[{type:'bar',orientation:'h',y:districts.map(r=>r.name),x:districts.map(r=>r.median),marker:{color:blue},text:districts.map(r=>num(r.median,1)+'점 ('+r.n+'곳)'),textposition:'outside',cliponaxis:false}],{height,margin:{l:72,r:92,t:10,b:35},xaxis:{range:[0,110],title:'종합 점수 중앙값',gridcolor:'#e8ede5'}});}
    const t=state.rows.filter(target),base=t.map(r=>C.score(r)),top=new Set([...base].sort(C.descending).slice(0,10).map(r=>r.trdar_code));
    table('local-sensitivity',['시나리오','순위 상관','상위 10곳 유지','점수 있는 상권'],state.meta.sensitivity.map(s=>{const alt=t.map(r=>C.score(r,s.weights,s.mode)),joined=alt.map((r,i)=>({base:base[i].score_total,alt:r.score_total})),kept=[...alt].sort(C.descending).slice(0,10).filter(r=>top.has(r.trdar_code)).length;return [s.name,num(C.spearman(joined,'base','alt'),3),top.size?kept+' / '+Math.min(10,t.length):'해당 없음',num(alt.filter(r=>C.valid(r.score_total)).length)+'곳'];}));
    table('global-sensitivity',['시나리오','순위 상관 중앙값','상위 10곳 유지 중앙값','최소 유지'],state.meta.sensitivity.map(s=>[s.name,num(s.rank_correlation_median,3),num(s.top10_retained_median,0)+'곳',s.top10_retained_min+'곳']));
  }
  function renderRules(){
    table('method-table',['기준','통합 규칙','판정·해석 한계'],[['분석 대상','2025년 · 관광특구 제외 · 평균 점포 5개 이상 · 업종 비교 30곳 이상','같은 업종 서울 전체 안에서 점수 계산'],['매출 잠재력','점포당 월매출의 같은 업종 백분위 · 네 분기 자료 및 유효 비교 30곳','매출이 없다고 0으로 채우지 않음'],['경쟁','유동인구 1,000명당 같은 업종 점포 · 낮을수록 높은 점수','수요와 유동인구 정보가 겹칠 수 있음'],['안정성','업종 평균 쪽으로 축소 추정한 연간 폐업률 · 낮을수록 높은 점수','1년치라 신뢰도 낮음 · 생존 확률 아님'],['기본 수요','유동·직장·상주 밀도의 업종 내 백분위가 모두 있을 때 평균','일부 평균은 별도 대안 모드'],['L/V','상주/(상주+직장) >55% L, <45% V, 가운데 보류','실제 고객·관광객 구성 아님'],['E/P','희망 업종 건당 추정매출 백분위 <45 E, >55 P, 가운데 보류','네 분기 반복 매출·비교 부족은 보류'],['S/D','2025Q4 HH→S, LL→D · LH/HL은 공식 명칭 보존 후 대응 보류','영업 기간의 상대 비교 · 성장률 아님'],['가중치','기본 30·25·15·30, 유효 영역만 재배분','운영 가정 · 유형별 차등 비중은 기본 적용 안 함'],['검사지','각 축 5문항 · 4:1 이상만 필터 제안 · 3:2/미완료 축 미적용','팀 제작 초안 · 금융 성향·성과 검증 아님']]);$('method-table').classList.add('rule-table');
    table('hold-table',['축','사유','조합 수'],state.meta.holds.map(r=>[r.axis,r.reason,num(r.count)]));
    $('sources').innerHTML=state.meta.config.sources.map(r=>`<a class="source-link" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)} ↗</a>`).join('')+'<p class="rule-quote">통합한 선택은 박성은의 구현 기준입니다. 기존 팀원 결과와 차이를 보고서에 남기고, 각자의 기여를 보존했습니다.</p>';
    $('version-note').textContent=state.meta.config.version+' · 입력 기준 커밋 '+state.meta.config.source_commit+' · 분석일 '+state.meta.config.date+' · 파일별 지문과 계산 범위는 GitHub 메타데이터에 기록했습니다.';
  }
  function exportRows(){
    const rows=searchRows(),keys=['trdar_code','trdar_name','gu_name','trdar_type','candidate_type','LV','EP','SD','known_axes','hold_reason','score_total','score_total_default','n_areas','score_sales','score_comp','score_stab','score_dem','demand_mode','stores','sales_month','chg_code','chg_name','run_months','closed_months','sales_month_cv','floating_cv'];
    const safe=x=>{if(typeof x==='number')return Number.isFinite(x)?String(x):'';let s=String(x??'');if(/^[=+@\-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
    const headings=['analysis_version','industry_code','preference_LV','preference_EP','preference_SD','weight_sales','weight_comp','weight_stab','weight_dem',...keys];
    const lines=rows.map(r=>[state.meta.config.version,state.code,...['LV','EP','SD'].map(a=>activeChoices()[a]||''),...C.KEYS.map(k=>state.weights[k]),...keys.map(k=>r[k])]);
    const blob=new Blob(['\ufeff'+[headings,...lines].map(row=>row.map(safe).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8;'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='SpotFit_통합_'+state.code+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  document.querySelectorAll('[data-tab],[data-go]').forEach(b=>b.addEventListener('click',()=>{go(b.dataset.tab||b.dataset.go);document.querySelector('.tabs').scrollIntoView({block:'start',behavior:'smooth'});}));
  window.addEventListener('hashchange',()=>go(location.hash.slice(1)));
  $('industry').addEventListener('change',()=>loadIndustry($('industry').value));
  ['district','area-type','demand'].forEach(id=>$(id).addEventListener('change',()=>{state.mode=$('demand').value;state.page=0;render();}));
  for(const a of Object.keys(C.AXES))$('pref-'+a).addEventListener('change',()=>{state.prefs[a]=$('pref-'+a).value;state.prefFromQuiz=false;state.page=0;render();});
  $('apply-preferences').addEventListener('change',()=>{state.apply=$('apply-preferences').checked;state.page=0;render();});
  $('linked-demand').addEventListener('change',()=>{state.linked=$('linked-demand').checked;render();});
  function clearPreferences(){state.prefs={LV:'',EP:'',SD:''};state.prefFromQuiz=false;state.apply=false;$('apply-preferences').checked=false;for(const a in C.AXES)$('pref-'+a).value='';state.page=0;render();}
  $('clear-preferences').addEventListener('click',clearPreferences);$('inspect-held').addEventListener('click',()=>{clearPreferences();go('find');});
  let debounce;C.KEYS.forEach(k=>$(k).addEventListener('input',()=>{state.weights[k]=Number($(k).value);$(k+'-value').textContent=state.weights[k];$('weight-sum').textContent=C.KEYS.reduce((n,k)=>n+state.weights[k],0);clearTimeout(debounce);debounce=setTimeout(render,120);}));
  $('reset').addEventListener('click',()=>{state.weights={...C.DEFAULT};C.KEYS.forEach(k=>$(k).value=C.DEFAULT[k]);state.mode='avg';$('demand').value='avg';state.linked=false;$('linked-demand').checked=false;state.answers={};document.querySelectorAll('#quiz input').forEach(i=>i.checked=false);renderQuizResult();['district','area-type','search'].forEach(id=>$(id).value='');state.sort='score_total';state.direction=-1;clearPreferences();if(state.code!=='CS100010'){$('industry').value='CS100010';loadIndustry('CS100010');}});
  $('search').addEventListener('input',()=>{state.page=0;renderTable();});$('previous').addEventListener('click',()=>{state.page--;renderTable();});$('next').addEventListener('click',()=>{state.page++;renderTable();});$('download-results').addEventListener('click',exportRows);
  $('score-table').addEventListener('click',e=>{const sort=e.target.closest('[data-sort]');if(sort){state.direction=state.sort===sort.dataset.sort?-state.direction:['trdar_name','gu_name','candidate_type','score_status'].includes(sort.dataset.sort)?1:-1;state.sort=sort.dataset.sort;renderTable();return;}const row=e.target.closest('[data-code]');if(row)openArea(row.dataset.code);});
  $('type-results').addEventListener('click',e=>{const row=e.target.closest('[data-code]');if(row)openArea(row.dataset.code);});
  ['score-table','type-results'].forEach(id=>$(id).addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('[data-code]'))e.target.click();}));
  $('area').addEventListener('change',()=>{state.selected=$('area').value;state.compare=new Set([state.selected]);renderDetail();});$('metric').addEventListener('change',renderDistribution);
  $('compare-options').addEventListener('change',e=>{const code=e.target.dataset.compare;if(!code)return;if(e.target.checked&&state.compare.size<4)state.compare.add(code);else state.compare.delete(code);renderCompareOptions();renderFacets();});$('compare-options').addEventListener('input',e=>{if(e.target.id==='compare-search')renderCompareOptions();});
  $('type-cards').addEventListener('click',e=>{const b=e.target.closest('[data-type]');if(!b)return;state.prefFromQuiz=false;['LV','EP','SD'].forEach((a,i)=>{state.prefs[a]=b.dataset.type[i];$('pref-'+a).value=state.prefs[a];});state.apply=true;$('apply-preferences').checked=true;state.page=0;render();});
  $('quiz').addEventListener('change',e=>{if(e.target.dataset.question){state.answers[e.target.dataset.question]=e.target.value;renderQuizResult();}});
  $('apply-quiz').addEventListener('click',()=>{const r=C.quizResult(state.meta.questions,state.answers);state.prefs={...r.choices};state.prefFromQuiz=true;for(const a in C.AXES)$('pref-'+a).value=state.prefs[a];state.apply=Object.values(state.prefs).some(Boolean);$('apply-preferences').checked=state.apply;state.page=0;render();$('preference-summary').scrollIntoView({block:'center',behavior:'smooth'});});
  $('clear-quiz').addEventListener('click',()=>{state.answers={};document.querySelectorAll('#quiz input').forEach(i=>i.checked=false);if(state.prefFromQuiz)clearPreferences();renderQuizResult();});
  window.addEventListener('resize',()=>{document.querySelectorAll('.page.active .js-plotly-plot').forEach(el=>Plotly.Plots.resize(el));if(state.tab==='detail')renderFacets();});
  Promise.all([read('data/meta.json'),read('data/geometry.json')]).then(([meta,geo])=>{state.meta=meta;state.geo=geo;$('industry').innerHTML=meta.industries.map(i=>`<option value="${i.code}" ${i.code===state.code?'selected':''}>${esc(i.name)}</option>`).join('');$('district').innerHTML+=meta.districts.map(d=>`<option>${esc(d)}</option>`).join('');initQuiz();return loadIndustry(state.code);}).then(()=>go(location.hash.slice(1)||'overview')).catch(e=>status(e.message,true));
})();
