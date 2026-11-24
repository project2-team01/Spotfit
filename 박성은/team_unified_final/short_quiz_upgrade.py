"""15문항을 보존하고 7문항 단축 검사와 버전별 상태를 추가한다. adapt_sources 후에도 적용."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def upgrade(web=HERE/'web'):
    app=(web/'app.js').read_text(encoding='utf-8')
    if 'SHORT_QUIZ_VERSION' in app:return
    core=(web/'core.js').read_text(encoding='utf-8')
    core=core.replace('function scoreAnswers(answers, questions, axes) {','function scoreAnswers(answers, questions, axes, version) {\n    version=version||"standard15";')
    core=core.replace('var done = picked.length === rows.length;','var done = rows.length > 0 && picked.length === rows.length;')
    core=core.replace('var clear = done && Math.max(nl, nr) >= 4;','var clear = done && Math.max(nl, nr) / rows.length >= 0.8;')
    core=core.replace('letter: done ? (nl > nr ? left : right) : null','letter: done && nl !== nr ? (nl > nr ? left : right) : null')
    core=core.replace('var complete = out.every(function (a) { return a.letter; });','var complete = out.every(function (a) { return a.total > 0 && a.answered === a.total; });\n    var typed = out.every(function(a){return a.letter;});')
    core=core.replace('return { source: "검사 결과", complete: complete,','return { source: version==="short7"?"7문항 간편 검사":"15문항 기본 검사", quizVersion: version, complete: complete,')
    core=core.replace('type: complete ? out.map(function (a) { return a.letter; }).join("") : null','type: typed ? out.map(function (a) { return a.letter; }).join("") : null')
    core=core.replace('if (!a.letter) return a.axis + " " + a.answered + "/" + a.total + "문항";','if (!a.letter) return a.answered===a.total ? a.axis+" "+a.counts[a.left]+":"+a.counts[a.right]+" (동률 · 제한 없음)" : a.axis + " " + a.answered + "/" + a.total + "문항";')
    core=core.replace('  var api = {','''  var QUIZ_VERSIONS = {
    standard15:{label:'15문항 기본 검사',counts:{LV:5,EP:5,SD:5}},
    short7:{label:'7문항 간편 검사',ids:[2,6,11,3,8,14,10],counts:{LV:2,EP:3,SD:2}}
  };
  function quizQuestions(questions,version){
    if(version==='short7')return QUIZ_VERSIONS.short7.ids.map(id=>questions.find(q=>q['번호']===id));
    return questions.slice().sort((a,b)=>a['화면 순서']-b['화면 순서']);
  }
  var api = {QUIZ_VERSIONS:QUIZ_VERSIONS,quizQuestions:quizQuestions,''')
    (web/'core.js').write_text(core,encoding='utf-8')
    app=app.replace('const QUESTIONS =','const SHORT_QUIZ_VERSION="short7";\n    const QUESTIONS =',1)
    app=app.replace('answers: {}, mode: "survey"','answers: {}, shortAnswers: {}, mode: "survey"')
    app=app.replace('function surveyResult() { return C.scoreAnswers(state.answers, P.step5.questions, P.step5.axes); }','''function quizVersion(){return state.mode==='short'?SHORT_QUIZ_VERSION:'standard15';}
    function currentQuestions(){return C.quizQuestions(P.step5.questions,quizVersion());}
    function currentAnswers(){return state.mode==='short'?state.shortAnswers:state.answers;}
    function surveyResult() { return C.scoreAnswers(currentAnswers(),currentQuestions(),P.step5.axes,quizVersion()); }''')
    app=app.replace('if (state.mode === "survey")','if (state.mode !== "direct")')
    app=app.replace("'이름':'일부 축 선호'","'이름':'일부 축 선호'")
    # 결과를 적용해야 공통 조건을 바꾼다. 탭 전환은 각 버전의 응답·적용 중 결과를 보존한다.
    app=app.replace('<b>${p.type}</b> ${esc(p.info["이름"])}','<b>${p.type}</b> ${esc(p.info["이름"])} · ${esc(p.result.source)}')
    start=app.index('    function drawMbtiInput()')
    end=app.index('\n    function activeProfile()',start)
    app=app[:start]+'''    function drawMbtiInput() {
      const host=$('mbtiInput');
      if(state.mode==='direct'){
        host.innerHTML='<h3>유형 직접 고르기</h3><p class="note">검사 대신 세 축을 직접 고릅니다.</p><div class="types">'+TYPE_ORDER.map(t=>`<button data-t="${t}" aria-pressed="${state.pick===t}"><b>${t}</b> ${esc(TYPES[t]['이름'])}</button>`).join('')+'</div>';
        host.onclick=e=>{const b=e.target.closest('[data-t]');if(b){state.pick=b.dataset.t;renderS7();}};return;
      }
      const qs=currentQuestions(),answers=currentAnswers(),r=surveyResult(),short=state.mode==='short';
      host.innerHTML=`<div class="table-head"><h3>${esc(r.source)}</h3><button class="ghost" id="clearAnswers">이 버전 응답 지우기</button></div>
      <p class="note" id="quizNote">${short?'고객층 2 · 가격 운영 3 · 영업 환경 2문항. 축의 답이 모두 같을 때만 조건으로 적용합니다.':'각 축 5문항 중 4:1·5:0만 조건으로 적용합니다.'} <span id="quizProgress">${r.answered}/${qs.length} 답함</span></p>
      ${short?'<p class="note">15문항에서 고른 간편 초안입니다. 같은 정확도나 검사 타당도를 검증하지 않았습니다. 애매하면 15문항으로 더 살펴보세요.</p>':''}
      <p class="note">버전별 응답은 따로 유지됩니다. ‘선호 조건 적용’을 눌러야 공통 추천 조건이 바뀝니다.</p>
      <div class="progress" aria-hidden="true"><i style="width:${r.answered/qs.length*100}%"></i></div>`+
      qs.map((q,k)=>`<div class="q" role="group" aria-label="문항 ${k+1}"><p>${k+1}. ${esc(q['질문'])}</p><div class="opts">${['A','B'].map(x=>`<button data-q="${q['번호']}" data-a="${x}" aria-pressed="${answers[q['번호']]===x}">${esc(q[x])}</button>`).join('')}</div></div>`).join('');
      host.onclick=e=>{
        if(e.target.closest('#clearAnswers')){
          const key=quizVersion();if(state.mode==='short')state.shortAnswers={};else state.answers={};
          if(state.profile&&state.profile.result.quizVersion===key)applyProfile(null);
          renderS7();return;
        }
        const b=e.target.closest('[data-q]');if(!b)return;
        currentAnswers()[b.dataset.q]=b.dataset.a;
        b.parentNode.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
        const rr=surveyResult();host.querySelector('.progress i').style.width=rr.answered/qs.length*100+'%';
        $('quizProgress').textContent=rr.answered+'/'+qs.length+' 답함';drawMbtiResult();drawReco();
      };
    }
    function drawMbtiResult(){
      const host=$('mbtiResult'),p=pendingProfile(),applied=state.profile;
      const active=applied?`<p class="note">현재 적용 중: ${esc(applied.result.source)} · ${esc(applied.type)}</p><button class="ghost" data-act="off">적용된 선호 해제</button>`:'';
      if(!p){host.innerHTML='<h3>운영 선호</h3><p>문항에 답하거나 유형을 직접 고르세요.</p>'+active;}
      else{
        const short=p.result.quizVersion==='short7',choices=p.matched.pattern.filter(Boolean).length;
        host.innerHTML=`<h3>${esc(p.type)} · ${esc(p.info['이름'])}</h3><p><b>${esc(p.result.source)}</b> · ${p.result.source==='직접 고르기'?'검사 응답 없음':p.result.answered+'/'+p.result.total+' 답함'}</p><p>${esc(p.text)}</p>
        <p>필터로 적용할 선호: <b>${p.matched.pattern.map((v,j)=>v||['L/V 제한 없음','E/P 제한 없음','S/D 제한 없음'][j]).join(' · ')}</b></p>
        <p class="note">${short?'고객층·영업 환경은 2:0, 가격 운영은 3:0일 때만 적용합니다. 1:1·2:1·미완료 축은 제한하지 않습니다.':'기본형은 각 축 4:1·5:0만 적용합니다. 3:2·미완료 축은 제한하지 않습니다.'} 현재 비중 ${weightText(state.weights)}를 그대로 씁니다.</p>
        <div class="actions"><button class="primary" data-act="on" ${choices?'':'disabled'}>선호 조건 적용</button></div>`+active;
      }
      host.onclick=e=>{const b=e.target.closest('[data-act]');if(b)applyProfile(b.dataset.act==='on'?pendingProfile():null);};
    }
''' + app[end:]
    app=app.replace('${ap.p.type} 기준 · 가중치','${ap.p.type} · ${ap.p.result.source} 기준 · 가중치')
    app=app.replace("'선호패턴','버전'","'선호패턴','검사버전','버전'")
    app=app.replace('pattern.join(\'/\'):"제한 없음",P.version','pattern.join(\'/\'):"제한 없음",state.profile&&state.onlyMatch?state.profile.result.source:"적용 없음",P.version')
    (web/'app.js').write_text(app,encoding='utf-8')
    html=(web/'template.html').read_text(encoding='utf-8')
    html=html.replace('<button type="button" role="tab" data-mode="direct">','<button type="button" role="tab" data-mode="short">7문항 간편 검사</button>\n    <button type="button" role="tab" data-mode="direct">',1)
    html=html.replace('>15문항 검사</button>','>15문항 기본 검사</button>')
    html=html.replace('각 축 5문항 중 4:1 이상만 후보 조건으로 적용합니다.','15문항 기본형과 7문항 간편형을 선택할 수 있습니다. 기본형은 각 축 4:1 이상, 간편형은 각 축 전원 일치 때만 후보 조건으로 적용합니다.')
    (web/'template.html').write_text(html,encoding='utf-8')

if __name__=='__main__':upgrade()
