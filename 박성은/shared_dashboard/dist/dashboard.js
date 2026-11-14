/* 검증된 STEP4 점수의 공유용 브라우저 구현. 기본 점수는 재추정하지 않는다. */
(() => {
  'use strict';
  const KEYS = ['sales','comp','stab','dem'];
  const LABELS = ['매출 잠재력','경쟁','안정성(신뢰도 낮음)','수요'];
  const DEFAULT = {sales:30, comp:25, stab:15, dem:30};
  const valid = x => typeof x === 'number' && Number.isFinite(x);
  const median = values => { const a=values.filter(valid).sort((a,b)=>a-b); return a.length ? (a[Math.floor((a.length-1)/2)]+a[Math.floor(a.length/2)])/2 : null; };
  function score(row,weights=DEFAULT,mode='avg') {
    const values=[row.score_sales,row.score_comp,row.score_stab,row['score_dem_'+mode]];
    let num=0,den=0,n=0;
    values.forEach((value,i)=>{const w=Number(weights[KEYS[i]])||0;if(valid(value)&&w>0){num+=value*w;den+=w;n++;}});
    return {...row,score_dem:values[3],score_total:row.score_status==='점수 대상'&&den>0?num/den:null,n_areas:row.score_status==='점수 대상'&&den>0?n:0};
  }
  function ranks(a) {const s=a.map((v,i)=>({v,i})).sort((a,b)=>a.v-b.v),out=[];for(let i=0;i<s.length;){let j=i+1;while(j<s.length&&s[j].v===s[i].v)j++;for(let k=i;k<j;k++)out[s[k].i]=(i+1+j)/2;i=j;}return out;}
  function spearman(rows,a,b){const p=rows.filter(r=>valid(r[a])&&valid(r[b]));if(p.length<2)return null;const x=ranks(p.map(r=>r[a])),y=ranks(p.map(r=>r[b])),mx=x.reduce((a,b)=>a+b,0)/x.length,my=y.reduce((a,b)=>a+b,0)/y.length;let cov=0,vx=0,vy=0;x.forEach((v,i)=>{cov+=(v-mx)*(y[i]-my);vx+=(v-mx)**2;vy+=(y[i]-my)**2;});return vx&&vy?cov/Math.sqrt(vx*vy):null;}
  const descending = (a,b) => (valid(b.score_total)?b.score_total:-Infinity)-(valid(a.score_total)?a.score_total:-Infinity)||b.stores-a.stores||a.trdar_code.localeCompare(b.trdar_code);
  const core={score,median,spearman,descending,valid,DEFAULT};
  if(typeof module!=='undefined'&&module.exports)module.exports=core;
  if(typeof document==='undefined')return;

  const $=id=>document.getElementById(id), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=(x,d=0)=>valid(x)?x.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'자료 없음';
  const money=x=>valid(x)?number(x/10000)+'만 원':'자료 없음';
  const signed=x=>valid(x)?(x>0?'+':'')+number(x,1)+'%':'자료 없음';
  const cell=x=>valid(x)?number(x):'<span class="missing">자료 없음</span>';
  const cache=new Map();
  const state={meta:null,geometry:[],code:'CS100010',rows:[],quarters:[],all:[],scope:[],selected:null,tab:'find',weights:{...DEFAULT},mode:'avg',page:0,sort:'score_total',direction:-1,compare:new Set(),request:0};
  const PLOT={responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d','autoScale2d']};
  const color='#2878b5',orange='#d97942',ink='#173c36',muted='#6c7b76';
  const layout=(more={})=>({font:{family:'Noto Sans KR, system-ui, sans-serif',size:11,color:ink},paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',margin:{l:62,r:20,t:20,b:45},...more});
  const draw=(id,data,opts={})=>Plotly.react($(id),data,layout(opts),PLOT);
  const empty=(id,text)=>{Plotly.purge($(id));$(id).innerHTML=`<div class="empty-chart">${esc(text)}</div>`;};
  function table(id,headers,rows){$(id).innerHTML=`<thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody>`;}
  async function read(url){const r=await fetch(url);if(!r.ok)throw new Error('자료를 불러오지 못했습니다. 새로고침해 주세요.');return r.json();}
  function setStatus(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
  async function loadIndustry(code){
    const request=++state.request;setStatus('선택한 업종의 자료를 불러오는 중입니다…');document.querySelector('.content').classList.add('loading');
    try{let payload=cache.get(code);if(!payload){payload=await read(`data/${code}.json`);cache.set(code,payload);}if(request!==state.request)return;
      const types=new Map(payload.step5_rows.map(a=>{const r=Object.fromEntries(payload.step5_columns.map((c,i)=>[c,a[i]]));return [r.trdar_code,r];}));
      state.code=code;state.rows=payload.rows.map(a=>{const r=Object.fromEntries(payload.columns.map((c,i)=>[c,a[i]]));return {...r,...types.get(r.trdar_code)};});
      state.quarters=payload.quarters.map(a=>Object.fromEntries(payload.quarter_columns.map((c,i)=>[c,a[i]])));
      state.selected=null;state.compare.clear();state.page=0;render();
    }catch(e){setStatus(e.message,true);}finally{if(request===state.request)document.querySelector('.content').classList.remove('loading');}
  }
  function selectedIndustry(){return state.meta.industries.find(r=>r['업종_코드']===state.code);}
  function switchTab(tab){state.tab=tab;history.replaceState(null,'','#'+tab);document.querySelectorAll('.tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-selected',String(b.dataset.tab===tab));});document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===tab));renderActive();}
  function render(){
    state.all=state.rows.map(r=>score(r,state.weights,state.mode)).sort(descending);
    const gu=$('district').value,type=$('type').value;
    state.scope=state.all.filter(r=>(!gu||r.gu_name===gu)&&(!type||r.trdar_type===type));
    if(!state.scope.some(r=>r.trdar_code===state.selected)){state.selected=state.scope.find(r=>valid(r.score_total))?.trdar_code??state.scope[0]?.trdar_code??null;state.compare=new Set(state.selected?[state.selected]:[]);}
    state.compare=new Set([...state.compare].filter(c=>state.scope.some(r=>r.trdar_code===c)));
    const ind=selectedIndustry(),total=KEYS.reduce((n,k)=>n+state.weights[k],0);
    $('weight-sum').textContent=total;KEYS.forEach(k=>$(k+'-value').textContent=state.weights[k]);
    const corr=spearman(state.all,'score_comp','score_dem'),notes=[];
    if(!state.scope.length)notes.push('조건에 맞는 상권이 없습니다. 자치구나 상권 유형을 넓혀 보세요.');
    if(total===0)notes.push('가중치가 모두 0입니다. 하나 이상 올려 주세요. 현재 종합 점수를 계산하지 않습니다.');
    if(!ind['점수_생성'])notes.push(`${ind['업종명']}은 평균 점포 5개 이상인 비교 상권이 ${ind['점포5개이상_상권_수']}곳으로, 기준 30곳에 미달합니다. 점수 없이 원값만 참고하세요.`);
    else if(!ind['매출_점수_생성'])notes.push(`${ind['업종명']}은 매출 영역을 계산할 자료가 부족하거나 매출 미제공 업종입니다. 매출이 낮다는 뜻이 아닙니다. 나머지 유효 영역으로 계산합니다.`);
    if(valid(corr)&&Math.abs(corr)>=.8)notes.push(`경쟁·수요 상관이 ${number(corr,3)}으로 중복 반영 경고 기준 0.8 이상입니다. 경쟁 가중치를 0으로 두거나 주 고객층을 바꿔 비교하세요.`);
    $('notice').hidden=!notes.length;$('notice').textContent=notes.join(' ');
    setStatus(`${ind['업종명']} · 2025년 · ${number(state.scope.length)}곳 표시 · 점수는 서울 전체 같은 업종 기준`);
    renderActive();
  }
  function tiles(id,items){$(id).innerHTML=items.map(([label,value,note])=>`<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`).join('');}
  function renderActive(){if(!state.meta||!state.rows.length)return;if(state.tab==='find')renderFind();if(state.tab==='detail')renderDetail();if(state.tab==='distribution')renderDistribution();if(state.tab==='rules')renderRules();if(state.tab==='step5')Step5UI.render(state,code=>{state.selected=code;state.compare=new Set([code]);switchTab('detail');});}
  function renderFind(){const s=state.scope,scored=s.filter(r=>valid(r.score_total));tiles('stats',[
    ['조건 안 상권',number(s.length)+'곳','선택 업종 점포가 있는 상권'],['점수가 있는 상권',number(scored.length)+'곳','매출 영역까지 '+number(s.filter(r=>valid(r.score_sales)).length)+'곳'],
    ['평균 점포 5개 미만',number(s.filter(r=>r.stores<5).length)+'곳','점수 없이 참고용 원값'],['비교 상권 부족',number(s.filter(r=>r.score_status==='업종 비교 상권 30곳 미만').length)+'곳','업종 전체 비교 30곳 미만']]);
    renderMap();renderScoreTable();
    const corr=spearman(state.all,'score_comp','score_dem');
    const alternate=s.filter(r=>valid(r.score_total)).map(r=>score(r,{...state.weights,comp:0},state.mode)).filter(r=>valid(r.score_total)).sort(descending);
    const k=Math.min(10,scored.length),top=new Set(scored.slice(0,k).map(r=>r.trdar_code)),kept=alternate.slice(0,k).filter(r=>top.has(r.trdar_code)).length;
    $('overlap').textContent=`경쟁·수요 상관 ${valid(corr)?number(corr,2):'자료 없음'}. `+(k&&alternate.length?`경쟁 영역을 빼면 현재 상위 ${k}곳 중 ${k-kept}곳이 바뀝니다. `:'')+'상위 목록의 변화는 점수의 타당성이나 추천 성능을 입증하지 않습니다.';
  }
  function renderMap(){
    if(!state.scope.length){empty('map','표시할 상권이 없습니다.');return;}
    if(!selectedIndustry()['점수_생성']){empty('map','비교 상권이 30곳 미만인 업종입니다. 아래 표에서 원값과 제외 사유를 확인하세요.');return;}
    const lookup=new Map(state.scope.map(r=>[r.trdar_code,r])),geo=state.geometry.filter(g=>lookup.has(g.trdar_code));
    if(!geo.length){empty('map','지도 경계가 없습니다.');return;}
    const traces=[];
    for(const has of [false,true]){const features=geo.filter(g=>valid(lookup.get(g.trdar_code).score_total)===has);if(!features.length)continue;
      traces.push({type:'choroplethmap',geojson:{type:'FeatureCollection',features:features.map(g=>({type:'Feature',id:g.trdar_code,properties:{},geometry:g.geometry}))},locations:features.map(g=>g.trdar_code),
        z:features.map(g=>has?lookup.get(g.trdar_code).score_total:0),zmin:0,zmax:100,colorscale:has?[[0,'#dbe9ed'],[.5,'#5b9dba'],[1,'#174b77']]:[[0,'#d8ddd7'],[1,'#d8ddd7']],showscale:has,
        marker:{line:{width:.4,color:'#fff'},opacity:.95},colorbar:{title:{text:'종합 점수',side:'right',font:{size:10}},thickness:10,len:.45,x:1},
        customdata:features.map(g=>{const r=lookup.get(g.trdar_code);return [r.trdar_code,r.trdar_name,r.gu_name,has?number(r.score_total,1)+'점':r.score_status];}),
        hovertemplate:'<b>%{customdata[1]}</b><br>%{customdata[2]} · %{customdata[3]}<extra></extra>',name:has?'종합 점수':'점수 없음'});
    }
    const lons=geo.map(g=>g.lon),lats=geo.map(g=>g.lat),span=Math.max(Math.max(...lons)-Math.min(...lons),(Math.max(...lats)-Math.min(...lats))*1.25,.01);
    const select=geo.find(g=>g.trdar_code===state.selected);
    if(select)traces.push({type:'scattermap',lon:[select.lon],lat:[select.lat],mode:'markers',marker:{color:orange,size:12},customdata:[[select.trdar_code]],hoverinfo:'skip',name:'선택 상권'});
    draw('map',traces,{margin:{l:0,r:30,t:0,b:0},map:{style:'white-bg',center:{lon:(Math.min(...lons)+Math.max(...lons))/2,lat:(Math.min(...lats)+Math.max(...lats))/2},zoom:Math.max(8.7,Math.min(14,Math.log2(560*360/(span*512))))},showlegend:false,uirevision:`${state.code}|${$('district').value}|${$('type').value}`}).then(()=>{
      $('map').removeAllListeners('plotly_click');$('map').on('plotly_click',event=>{const p=event.points[0],code=p.location||p.customdata?.[0];if(lookup.has(code)){state.selected=code;state.compare=new Set([code]);switchTab('detail');document.querySelector('.tabs').scrollIntoView({block:'start',behavior:'smooth'});}});
    });
  }
  const TABLE_COLS=[['trdar_name','상권'],['gu_name','자치구'],['trdar_type','유형'],['score_total','종합 점수'],['n_areas','계산 영역 수'],['score_sales','매출'],['score_comp','경쟁'],['score_stab','안정성·신뢰도 낮음'],['score_dem','수요'],['stores','평균 점포 수'],['score_status','점수 상태']];
  function renderScoreTable(){
    const term=$('search').value.trim(),rows=state.scope.filter(r=>r.trdar_name.includes(term));
    rows.sort((a,b)=>{const x=a[state.sort],y=b[state.sort];if(x===null||x===undefined)return y===null?0:1;if(y===null||y===undefined)return -1;return (typeof x==='string'?x.localeCompare(y):x-y)*state.direction||descending(a,b);});
    const pages=Math.max(1,Math.ceil(rows.length/15));state.page=Math.min(state.page,pages-1);
    $('score-table').innerHTML='<thead><tr>'+TABLE_COLS.map(([key,label])=>`<th><button data-sort="${key}">${esc(label)}${state.sort===key?(state.direction>0?' ↑':' ↓'):''}</button></th>`).join('')+'</tr></thead><tbody>'+rows.slice(state.page*15,state.page*15+15).map(r=>`<tr data-code="${r.trdar_code}" tabindex="0" aria-label="${esc(r.trdar_name)} 상세 보기">`+TABLE_COLS.map(([key])=>`<td>${['trdar_name','gu_name','trdar_type','score_status'].includes(key)?esc(r[key]):key==='stores'?number(r[key],1):cell(r[key])}</td>`).join('')+'</tr>').join('')+'</tbody>';
    $('table-count').textContent=number(rows.length)+'곳';$('page-count').textContent=`${state.page+1} / ${pages}`;$('previous').disabled=state.page===0;$('next').disabled=state.page>=pages-1;
  }
  function values(r){return [r.score_sales,r.score_comp,r.score_stab,r.score_dem];}
  function medians(){const target=state.all.filter(r=>r.score_status==='점수 대상');return ['score_sales','score_comp','score_stab','score_dem'].map(c=>median(target.map(r=>r[c])));}
  function renderDetail(){
    const r=state.scope.find(r=>r.trdar_code===state.selected);
    $('area').innerHTML=state.scope.map(r=>`<option value="${r.trdar_code}" ${r.trdar_code===state.selected?'selected':''}>${esc(r.trdar_name)} · ${esc(r.gu_name)}</option>`).join('');
    if(!r){$('detail-title').textContent='조건에 맞는 상권이 없습니다';$('detail-subtitle').textContent='필터를 넓혀 주세요.';$('detail-stats').innerHTML='';['bars','radar','sales-trend','flow','facets'].forEach(id=>empty(id,'표시할 상권이 없습니다.'));['raw-table','qoq-table'].forEach(id=>$(id).innerHTML='');$('compare-options').innerHTML='';return;}
    $('detail-title').textContent=r.trdar_name;$('detail-subtitle').textContent=`${selectedIndustry()['업종명']} · ${r.gu_name} · ${r.trdar_type}`;
    tiles('detail-stats',[['종합 점수',valid(r.score_total)?number(r.score_total)+'점':'점수 없음',valid(r.score_total)?r.n_areas+'개 영역으로 계산':r.score_status],['평균 점포 수',number(r.stores,1)+'개','프랜차이즈 '+number(r.franchise_pct)+'%'],['점포당 월매출',money(r.sales_month),r.sales_area_status],['보정 폐업률',number(r.close_pct_shrunk,1)+'%','연간 폐업 '+number(r.closes)+'건 · 신뢰도 낮음']]);
    const v=values(r),m=medians();
    draw('bars',[{type:'bar',orientation:'h',x:v.map(n=>valid(n)?n:0),y:LABELS,marker:{color},text:v.map(n=>valid(n)?number(n)+'점':'자료 없음'),textposition:'outside',cliponaxis:false,hovertemplate:'%{y}: %{text}<extra></extra>',name:'선택 상권'},
      {type:'scatter',mode:'markers',x:m,y:LABELS,marker:{symbol:'line-ns-open',size:23,color:orange,line:{width:2}},name:'업종 중앙값',hovertemplate:'업종 중앙값 %{x:.1f}점<extra></extra>'}],{margin:{l:126,r:55,t:10,b:35},xaxis:{range:[0,106],title:{text:'업종 안 점수 (0~100)',font:{size:10}},gridcolor:'#e8ede5'},yaxis:{autorange:'reversed'},showlegend:false});
    draw('radar',[{type:'scatterpolar',r:[...m,m[0]],theta:[...LABELS,LABELS[0]],mode:'lines+markers',line:{color:orange,dash:'dash'},connectgaps:false,name:'업종 중앙값'},
      {type:'scatterpolar',r:[...v,v[0]],theta:[...LABELS,LABELS[0]],mode:'lines+markers',line:{color},connectgaps:false,name:r.trdar_name}],{margin:{l:80,r:85,t:35,b:40},polar:{radialaxis:{range:[0,100],tickvals:[0,25,50,75,100],gridcolor:'#e1e8df'},angularaxis:{gridcolor:'#edf1e8',tickfont:{size:9}}},legend:{orientation:'h',y:-.2,font:{size:10}}});
    const target=state.all.filter(r=>r.score_status==='점수 대상'),rawMed=c=>median(target.filter(a=>c!=='sales_month'||valid(a.score_sales)).map(a=>a[c]));
    table('raw-table',['영역','지표','이 상권','업종 중앙값','참고'],[
      ['매출 잠재력','점포당 월매출',money(r.sales_month),money(rawMed('sales_month')),'매출 점수 유효 상권 기준 중앙값'],['경쟁','유동인구 1,000명당 같은 업종 점포',number(r.comp_ratio,3)+'개',number(rawMed('comp_ratio'),3)+'개','낮을수록 높은 점수'],
      ['안정성','축소 추정 폐업률',number(r.close_pct_shrunk,1)+'%',number(rawMed('close_pct_shrunk'),1)+'%','1년치라 신뢰도 낮음'],
      ...[['floating_density','유동인구'],['worker_density','직장인구'],['resident_density','상주인구']].map(([c,label])=>['수요','면적당 '+label+' (㎢당)',number(r[c])+'명',number(rawMed(c))+'명',c==='floating_density'?'2025년 분기 평균':'2025년 중 값 변화 없음'])]);
    const q=[1,2,3,4].map(i=>state.quarters.find(q=>q.trdar_code===r.trdar_code&&q.quarter===`2025${i}`)||{quarter:`2025${i}`});
    const quarters=['1분기','2분기','3분기','4분기'];
    if(q.some(r=>valid(r.sales_month)))draw('sales-trend',[{x:quarters,y:q.map(q=>valid(q.sales_month)?q.sales_month/10000:null),type:'scatter',mode:'lines+markers',line:{color},connectgaps:false,hovertemplate:'%{x}: %{y:,.0f}만 원<extra></extra>'}],{yaxis:{title:{text:'점포당 월매출 (만 원)',font:{size:10}},rangemode:'tozero',gridcolor:'#e8ede5'}});else empty('sales-trend','분기 매출 자료가 없습니다.');
    draw('flow',[{type:'bar',x:quarters,y:q.map(q=>q.open_count??null),name:'개업',marker:{color:'#759a70'}},{type:'bar',x:quarters,y:q.map(q=>q.close_count??null),name:'폐업',marker:{color:orange}}],{barmode:'group',yaxis:{title:'건수',rangemode:'tozero',gridcolor:'#e8ede5'},legend:{orientation:'h',y:1.15}});
    table('qoq-table',['분기','증감률 · 상하위 5% 경계 적용','원값'],q.map((r,i)=>[quarters[i],signed(r.qoq_winsor),signed(r.qoq_raw)]));
    const vintage={K06:'직장인구',K07:'상주인구',K05:'집객시설'};
    $('freshness').textContent=state.meta.freshness.filter(f=>vintage[f.dataset]).map(f=>vintage[f.dataset]+': '+(f.last_observed_value_change?f.last_observed_value_change.slice(0,4)+'Q'+f.last_observed_value_change.slice(4)+' 마지막 값 변경':'2021Q1 이후 값 변경 없음')).join(' · ')+' · 실제 통계 기준 시점은 미확인입니다.';
    renderCompareOptions();renderFacets();
  }
  function renderCompareOptions(){
    const box=$('compare-options');if(!box.querySelector('#compare-search')){box.innerHTML='<input type="search" id="compare-search" aria-label="비교할 상권 검색" placeholder="비교할 상권 검색"><div id="compare-list" class="compare-options"></div>';}
    const term=$('compare-search').value.trim(),list=state.scope.filter(r=>state.compare.has(r.trdar_code)||r.trdar_name.includes(term)).slice(0,60);
    $('compare-list').innerHTML=list.map(r=>`<label><input type="checkbox" data-compare="${r.trdar_code}" ${state.compare.has(r.trdar_code)?'checked':''} ${state.compare.size>=4&&!state.compare.has(r.trdar_code)?'disabled':''}>${esc(r.trdar_name)}</label>`).join('')+`<p class="fineprint">${state.compare.size}/4곳 선택 · 처음 60곳 표시, 검색으로 다른 상권을 찾을 수 있습니다.</p>`;
  }
  function renderFacets(){
    const rows=[...state.compare].map(c=>state.scope.find(r=>r.trdar_code===c)).filter(Boolean);if(!rows.length){empty('facets','비교할 상권을 선택하세요.');return;}
    const narrow=window.innerWidth<700,columns=narrow?1:2,nrows=Math.ceil(rows.length/columns),gap=.12,traces=[],opts={height:nrows*220,margin:{l:125,r:20,t:30,b:25},annotations:[],showlegend:false};
    $('facets').style.height=opts.height+'px';rows.forEach((r,i)=>{const axis=i===0?'':String(i+1),col=i%columns,row=Math.floor(i/columns),dx=(1-gap)/columns,dy=(1-gap)/nrows,x0=col*(1/columns),y1=1-row/nrows;
      opts['xaxis'+axis]={domain:[x0,x0+dx],range:[0,105],anchor:'y'+axis,gridcolor:'#e8ede5'};opts['yaxis'+axis]={domain:[y1-dy,y1],anchor:'x'+axis,autorange:'reversed',tickfont:{size:9}};
      traces.push({type:'bar',orientation:'h',x:values(r).map(n=>valid(n)?n:0),y:LABELS,xaxis:'x'+axis,yaxis:'y'+axis,marker:{color:[color,'#80a390','#b8b577','#d49b71']},text:values(r).map(n=>valid(n)?number(n):'자료 없음'),textposition:'outside',cliponaxis:false});
      opts.annotations.push({text:r.trdar_name,x:x0,y:y1+.07,xref:'paper',yref:'paper',showarrow:false,xanchor:'left',font:{size:11,color:ink}});
    });draw('facets',traces,opts);
  }
  function renderDistribution(){
    const key=$('metric').value,s=state.scope.filter(r=>valid(r[key])),transform=v=>key==='sales_month'?v/10000:v;
    if(!s.length)empty('histogram','표시할 값이 없습니다.');else{const a=s.map(r=>transform(r[key])).sort((a,b)=>a-b),cap=a[Math.floor((a.length-1)*.99)];
      draw('histogram',[true,false].map(yes=>({type:'histogram',x:s.filter(r=>(r.score_status==='점수 대상')===yes).map(r=>Math.min(transform(r[key]),cap)),name:yes?'점수 대상':'점수 없음',marker:{color:yes?color:'#bec7ba'},nbinsx:35,opacity:.8})),{barmode:'stack',xaxis:{title:$('metric').selectedOptions[0].text},yaxis:{title:'상권 수',gridcolor:'#e8ede5'},legend:{orientation:'h',y:1.15},shapes:key==='stores'?[{type:'line',x0:5,x1:5,y0:0,y1:1,yref:'paper',line:{color:orange,dash:'dash'}}]:[]});}
    const groups=new Map();state.scope.filter(r=>valid(r.score_total)).forEach(r=>{if(!groups.has(r.gu_name))groups.set(r.gu_name,[]);groups.get(r.gu_name).push(r.score_total);});
    const districts=[...groups].map(([name,a])=>({name,median:median(a),n:a.length})).sort((a,b)=>a.median-b.median);
    if(!districts.length)empty('district-chart','점수가 있는 상권이 없습니다.');else{const height=Math.max(290,districts.length*25+60);$('district-chart').style.height=height+'px';draw('district-chart',[{type:'bar',orientation:'h',x:districts.map(r=>r.median),y:districts.map(r=>r.name),marker:{color},text:districts.map(r=>`${number(r.median)}점 (${r.n}곳)`),textposition:'outside',cliponaxis:false}],{height,margin:{l:70,r:90,t:10,b:35},xaxis:{range:[0,110],title:'종합 점수 중앙값',gridcolor:'#e8ede5'}});}
  }
  function renderRules(){const design=state.meta.design,headers=['영역','지표','계산','방향','대상 조건','결측 처리','대상 행 수','중복 반영 주의·대안'];table('design-table',headers,design.map(r=>headers.map(h=>r[h]??'')));table('exclusion-counts',['점수 상태','조합 수'],Object.entries(state.meta.counts.status).map(([k,v])=>[k,number(v)]));}

  document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));
  $('industry').addEventListener('change',()=>loadIndustry($('industry').value));
  ['district','type','demand'].forEach(id=>$(id).addEventListener('change',()=>{state.mode=$('demand').value;state.page=0;render();}));
  let timer;KEYS.forEach(k=>$(k).addEventListener('input',()=>{state.weights[k]=Number($(k).value);$(k+'-value').textContent=state.weights[k];$('weight-sum').textContent=KEYS.reduce((n,k)=>n+state.weights[k],0);clearTimeout(timer);timer=setTimeout(render,150);}));
  $('reset').addEventListener('click',()=>{state.weights={...DEFAULT};KEYS.forEach(k=>$(k).value=DEFAULT[k]);['district','type'].forEach(id=>$(id).value='');$('demand').value='avg';state.mode='avg';$('search').value='';state.page=0;state.sort='score_total';state.direction=-1;if(state.code!=='CS100010'){$('industry').value='CS100010';loadIndustry('CS100010');}else render();});
  $('search').addEventListener('input',()=>{state.page=0;renderScoreTable();});$('previous').addEventListener('click',()=>{state.page--;renderScoreTable();});$('next').addEventListener('click',()=>{state.page++;renderScoreTable();});
  $('score-table').addEventListener('click',e=>{const button=e.target.closest('[data-sort]');if(button){const key=button.dataset.sort;state.direction=state.sort===key?-state.direction:typeof state.scope[0]?.[key]==='string'?1:-1;state.sort=key;renderScoreTable();return;}const row=e.target.closest('[data-code]');if(row){state.selected=row.dataset.code;state.compare=new Set([state.selected]);switchTab('detail');document.querySelector('.tabs').scrollIntoView({block:'start',behavior:'smooth'});}});
  $('score-table').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('[data-code]'))e.target.click();});
  $('area').addEventListener('change',()=>{state.selected=$('area').value;state.compare=new Set([state.selected]);renderDetail();});$('metric').addEventListener('change',renderDistribution);
  $('compare-options').addEventListener('change',e=>{const code=e.target.dataset.compare;if(!code)return;if(e.target.checked&&state.compare.size<4)state.compare.add(code);else state.compare.delete(code);renderCompareOptions();renderFacets();});
  $('compare-options').addEventListener('input',e=>{if(e.target.id==='compare-search')renderCompareOptions();});
  window.addEventListener('resize',()=>{if(state.tab==='detail')renderFacets();});
  Promise.all([read('data/meta.json'),read('data/geometry.json')]).then(([meta,geo])=>{state.meta=meta;state.geometry=geo;$('industry').innerHTML=meta.industries.map(r=>`<option value="${r['업종_코드']}" ${r['업종_코드']==='CS100010'?'selected':''}>${esc(r['업종명'])}</option>`).join('');$('district').innerHTML+=[...meta.districts].map(g=>`<option>${esc(g)}</option>`).join('');return loadIndustry('CS100010');}).then(()=>{const tab=location.hash.slice(1);if(['find','detail','distribution','rules','step5'].includes(tab))switchTab(tab);}).catch(e=>setStatus(e.message,true));
})();
