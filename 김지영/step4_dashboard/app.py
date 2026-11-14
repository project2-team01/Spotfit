import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="SpotFit 상권 비교 점수")


@app.cell(hide_code=True)
def _():
    # 화면 구성은 김지영/claude_dashboard/app.py 의 '희망 업종 → 상권 찾기 → 근거와 한계' 흐름을 따른다.
    import marimo as mo

    import mbti
    import views as v

    PAGES = ["금융 MBTI 검사", "상권 찾기", "상권 상세", "지표 분포와 자치구 비교", "점수 기준과 한계"]
    return PAGES, mbti, mo, v


@app.cell(hide_code=True)
def _(PAGES, mo):
    # 시험·내보내기용 시작 조건. 예: marimo export html app.py -o out.html -- --tab 3 --industry 고시원 --weights 0,0,0,0
    #   --mbti VPG (유형 직접 고르기) · --answers ABBAA... (문항 번호 순서 15글자, 답하지 않은 문항은 -) · --match 0 (유형이 맞는 상권만 보기 끄기)
    _args = mo.cli_args()

    def _arg(name):
        value = _args.get(name)
        return None if value is None or str(value) == "" else str(value)

    _tab = _arg("tab") or "2"  # 처음 열리는 탭은 '상권 찾기'
    start_page = PAGES[int(_tab) - 1] if _tab.isdigit() and 1 <= int(_tab) <= len(PAGES) else (_tab if _tab in PAGES else PAGES[1])
    start = {"industry": _arg("industry") or "커피-음료", "gu": _arg("gu"), "type": _arg("type"), "weights": _arg("weights"), "code": _arg("code"),
             "mbti": _arg("mbti"), "answers": _arg("answers"), "match": _arg("match")}
    return start, start_page


@app.cell(hide_code=True)
def _(mo, v):
    try:
        bundle = v.load_bundle()
    except FileNotFoundError as _error:
        mo.stop(True, mo.callout(str(_error), kind="danger"))
    pal = v.palette(mo.app_meta().theme)


    def panel(title, note, content):
        """제목과 읽는 법을 내용 위에 붙인다. 내용이 글자면 회색 상자로 보여 준다."""
        body = mo.callout(content, kind="neutral") if isinstance(content, str) else content
        return mo.vstack([mo.md(f"**{title}**<br><small>{note}</small>"), body], gap=0.4)


    def chart(spec):
        return mo.ui.altair_chart(spec, chart_selection=False, legend_selection=False) if spec is not None else None


    def table(frame, **options):
        base = dict(selection=None, pagination=False, show_column_summaries=False, show_data_types=False, show_download=False, show_search=False)
        return mo.ui.table(frame, **(base | options))
    return bundle, chart, pal, panel, table


@app.cell(hide_code=True)
def _(bundle, mo):
    _c = bundle.meta["counts"]
    mo.vstack([
        mo.md(f"""
    # SpotFit 상권 비교 점수 (2025년)

    희망 업종 하나를 고르면 **서울의 같은 업종 상권끼리** 비교한 **업종 내 비교 점수**(0~100)를 보여 줍니다.
    점수가 높은 상권은 같은 업종의 다른 상권보다 4개 영역(매출 잠재력 · 경쟁 · 안정성 · 수요) 지표가 상대적으로 나은 곳이라는 뜻입니다.
    관광특구 {bundle.meta['tourist_areas']}곳을 뺀 {bundle.meta['comparison_areas']:,}개 상권, 100개 업종 중 {_c['industries']['scored']}개 업종에서 점수를 만들었습니다.
    왼쪽에서 **금융 MBTI**를 적용하면 유형이 맞는 상권만 보고, 가중치 기본값이 S/G 글자에 따라 바뀝니다 [가정].
    """),
        mo.callout(mo.md(
            "**2025년 자료만 있어 성장성은 산출하지 않습니다.** &nbsp;·&nbsp; "
            "**예산 적합성은 판단하지 않습니다** (임대료·보증금·권리금 자료가 없습니다). &nbsp;·&nbsp; "
            "이 점수는 창업 결과를 예측하지 않습니다."), kind="warn"),
    ], gap=0.6)
    return


@app.cell(hide_code=True)
def _(PAGES, mo, start_page):
    nav = mo.ui.tabs({name: "" for name in PAGES}, value=start_page)
    nav
    return (nav,)


@app.cell(hide_code=True)
def _(bundle, mbti, mo, start, v):
    _options = v.industry_options(bundle.availability)
    _label = v.industry_label(bundle.availability, start["industry"]) or v.industry_label(bundle.availability, "커피-음료")
    industry_ui = mo.ui.dropdown(_options, value=_label, searchable=True, label="희망 업종")
    _gus = sorted(bundle.areas["gu_name"].unique())
    gu_ui = mo.ui.multiselect(_gus, value=[g for g in (start["gu"] or "").split(",") if g in _gus], label="자치구 (비우면 전체)")
    type_ui = mo.ui.multiselect(v.TYPES, value=[t for t in (start["type"] or "").split(",") if t in v.TYPES], label="상권 유형 (비우면 전체)")
    # 금융 MBTI (STEP 5): 적용 방식, 직접 고르기, 유형이 맞는 상권만 보기, 검사 15문항
    _picks = {f"{r['유형']} {r['이모지']} {r['이름']}": r["유형"] for r in bundle.type_table.to_dict("records")}
    _start_pick = next((k for k, c in _picks.items() if c == (start["mbti"] or "").upper()), None)
    _mode = mbti.MODE_SURVEY if start["answers"] else (mbti.MODE_DIRECT if _start_pick else mbti.MODE_OFF)
    mbti_mode_ui = mo.ui.radio(mbti.MODES, value=_mode, label="금융 MBTI 적용")
    mbti_pick_ui = mo.ui.dropdown(_picks, value=_start_pick or next(iter(_picks)), label="유형 직접 고르기")
    match_only_ui = mo.ui.checkbox(value=start["match"] != "0", label="유형이 맞는 상권만 보기")
    _answers = mbti.parse_answers(start["answers"], bundle.questions)
    answer_ui = mo.ui.dictionary({
        str(r["번호"]): mo.ui.radio({r["A"]: "A", r["B"]: "B"}, value=r[_answers[int(r["번호"])]] if int(r["번호"]) in _answers else None)
        for r in mbti.ordered_questions(bundle.questions).to_dict("records")})
    view_type_ui = mo.ui.dropdown(["LE", "LP", "VE", "VP"], value="LE", label="지도에서 볼 상권 MBTI 유형")
    get_code, set_code = mo.state(start["code"])
    return answer_ui, get_code, gu_ui, industry_ui, match_only_ui, mbti_mode_ui, mbti_pick_ui, set_code, type_ui, view_type_ui


@app.cell(hide_code=True)
def _(answer_ui, bundle, mbti, mbti_mode_ui, mbti_pick_ui):
    _answers = {int(k): x for k, x in answer_ui.value.items() if x in ("A", "B")}
    survey = mbti.score_answers(_answers, bundle.questions, bundle.meta5["axes"])
    profile = mbti.make_profile(mbti_mode_ui.value, survey, mbti_pick_ui.value, bundle.meta5["axes"], bundle.type_table, bundle.sg_weights)
    return profile, survey


@app.cell(hide_code=True)
def _(mo, profile, start, v):
    # 금융 MBTI를 적용하면 S/G 글자의 기본 가중치로 슬라이더를 다시 만든다 (유형이나 검사 답을 바꾸면 유형 기본값으로 돌아간다)
    _w = v.parse_weights(start["weights"]) if start["weights"] else (profile["weights"] if profile else dict(v.DEFAULT_WEIGHTS))
    weight_ui = mo.ui.dictionary({k: mo.ui.slider(0, 100, step=5, value=int(_w[k]), show_value=True, debounce=True, full_width=True) for k in v.AREA_KEYS})
    return (weight_ui,)


@app.cell(hide_code=True)
def _(gu_ui, industry_ui, match_only_ui, mbti, mbti_mode_ui, mbti_pick_ui, mo, profile, survey, type_ui, v, weight_ui):
    _sliders = []
    for _key in v.AREA_KEYS:
        _sliders += [mo.md(f"<small>{v.AREA_NAMES[_key]}</small>"), weight_ui[_key]]
    _mbti = [mo.md("### 금융 MBTI"), mbti_mode_ui]
    if mbti_mode_ui.value == mbti.MODE_DIRECT:
        _mbti.append(mbti_pick_ui)
    if profile:
        _mbti += [mo.md(f"<small>**{profile['emoji']} {profile['type']} {profile['name']}** · {profile['text']}<br>"
                        f"맞춰 볼 상권 MBTI 유형: {mbti.matched_text(profile['matched'])}</small>"), match_only_ui]
        _w = " · ".join(f"{v.AREA_NAMES[k].split(' ')[0]} {profile['weights'][k]:.0f}" for k in v.AREA_KEYS)
        _note = f"[가정, 팀 확인 필요] 금융 MBTI **{profile['weight_label']}** 기본값을 넣었습니다: {_w}. 유형이나 검사 답을 바꾸면 이 기본값으로 돌아갑니다."
    else:
        if mbti_mode_ui.value == mbti.MODE_SURVEY:
            _mbti.append(mo.md(f"<small>'금융 MBTI 검사' 탭에서 15문항 중 {survey['answered']}개 답했습니다. 끝까지 답하면 적용됩니다.</small>"))
        _note = "[가정, 팀 미확정] 기본값: 매출 잠재력 30 · 경쟁 25 · 안정성 15 · 수요 30. 금융 MBTI를 적용하면 S/G 글자에 따라 기본값이 바뀝니다."
    mo.sidebar(mo.vstack([
        *_mbti,
        mo.md("### 조건"),
        industry_ui,
        gu_ui,
        type_ui,
        # 사이드바는 마지막 요소를 바닥 쪽으로 밀어서, 제목·안내·슬라이더를 한 묶음으로 둔다
        mo.vstack([mo.md(f"### 영역별 가중치\n<small>{_note} 자료가 없는 영역은 빼고 나머지 영역끼리 비율을 다시 나눕니다.</small>"),
                   mo.vstack(_sliders, gap=0.1)], gap=0.5),
    ], gap=0.7), width="330px")
    return


@app.cell(hide_code=True)
def _(bundle, get_code, gu_ui, industry_ui, match_only_ui, profile, type_ui, v, weight_ui):
    weights = {k: float(x) for k, x in weight_ui.value.items()}
    weights_zero = sum(weights.values()) <= 0
    industry = bundle.availability.set_index("업종코드").loc[industry_ui.value]
    industry_scored = industry["점수 생성"] == "예"
    matched = profile["matched"] if profile else None
    mbti_filter = list(matched) if profile and match_only_ui.value else None  # 유형이 맞는 상권만 보기
    all_rows = v.with_match(v.industry_rows(bundle, industry_ui.value, weights), matched)  # 서울 전체 (점수 기준)
    shown = v.visible_areas(bundle.areas, gu_ui.value, type_ui.value, mbti_filter)
    rows = v.filter_rows(all_rows, gu_ui.value, type_ui.value, mbti_filter)  # 현재 필터 안
    summary = v.summary(rows, shown)
    medians = v.industry_medians(all_rows)
    selected_code = v.choose_code(get_code(), rows)
    return all_rows, industry, industry_scored, mbti_filter, medians, rows, selected_code, shown, summary, weights, weights_zero


@app.cell(hide_code=True)
def _(PAGES, answer_ui, bundle, mbti, mbti_mode_ui, mo, nav, panel, survey):
    mo.stop(nav.value != PAGES[0])
    _items = [mo.vstack([mo.md(f"**{_i}. {_r['질문']}**"), answer_ui[str(_r["번호"])]], gap=0.25)
              for _i, _r in enumerate(mbti.ordered_questions(bundle.questions).to_dict("records"), start=1)]
    _questions = panel("검사 15문항", "둘 중 더 가까운 쪽을 고릅니다. 세 가지 기준마다 5문항이고, 문항 순서는 섞여 있습니다.", mo.vstack(_items, gap=1.0))
    if survey["complete"]:
        _t = bundle.type_table.set_index("유형").loc[survey["type"]]
        _matched = mbti.matched_types(survey)
        _w, _label = mbti.sg_weights(survey, bundle.sg_weights)
        _wtext = " · ".join(f"{k} {_w[key]:.0f}" for k, key in mbti.WEIGHT_KEYS.items())
        if mbti_mode_ui.value == mbti.MODE_SURVEY:
            _apply = mo.md("<small>'상권 찾기' · '상권 상세' 탭에 이 유형을 적용하고 있습니다.</small>")
        else:
            _apply = mo.callout("왼쪽 '금융 MBTI 적용'에서 '검사 결과'를 고르면 '상권 찾기' · '상권 상세' 탭에 이 유형이 적용됩니다.", kind="neutral")
        _result = mo.vstack([
            mo.md(f"## {_t['이모지']} {survey['type']} {_t['이름']}\n**{mbti.axis_text(survey)}**"),
            mo.md(f"- **상권 특징 (팀 유형표):** {_t['상권 특징']}\n"
                  f"- **창업 아이템 예시 (팀 유형표의 예시, 데이터로 검증하지 않음):** {_t['창업 아이템 예시']}\n"
                  f"- **맞춰 볼 상권 MBTI 유형:** {mbti.matched_text(_matched)}"
                  + ("" if len(_matched) == 1 else " (3:2 경계인 글자는 반대 글자의 상권도 함께 봅니다)") + "\n"
                  f"- **가중치 기본값:** {_label}: {_wtext} [가정]"),
            _apply,
        ], gap=0.6)
    else:
        _result = mo.callout(f"15문항 중 {survey['answered']}개 답했습니다. 모두 답하면 유형이 나옵니다. 지금까지: {mbti.axis_text(survey)}", kind="neutral")
    _how = mo.md("""
    **채점 (팀 유형표 5장)**

    - 기준마다 5문항 중 **3개 이상 고른 쪽**이 그 글자입니다. 5:0 · 4:1은 뚜렷, 3:2는 경계입니다.
    - 글자 순서는 주요 고객(L 생활형 / V 방문형) → 소비 성향(E 실속형 / P 프리미엄형) → 상권 변화(S 안정형 / G 성장형)입니다.
    - **상권과는 앞의 두 글자만 맞춥니다.** 상권의 S/G는 2025년 자료만 있어 판정하지 않습니다.
    - **S/G 글자는 영역 가중치로 씁니다.** 11~15번 금융 문항이 위험 감수 성향이라, 위험 성향을 따로 묻지 않습니다(두 번 반영하지 않기 위해).
    """)
    mo.vstack([
        mo.callout(mo.md("검사 결과는 **상권을 고르는 조건**으로만 씁니다. 창업 결과를 예측하지 않고, 예산 적합성도 판단하지 않습니다."), kind="info"),
        mo.hstack([_questions, mo.vstack([panel("검사 결과", "15문항에 모두 답하면 나옵니다.", _result), _how], gap=1.2)],
                  widths=[1, 1], gap=2, align="start", wrap=True),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, mbti, mo, nav, pal, panel, profile, survey, table, v, view_type_ui):
    mo.stop(nav.value != PAGES[0])
    if profile:
        _matched, _whose = profile["matched"], f"적용 중인 {profile['type']}"
    elif survey["complete"]:
        _matched, _whose = mbti.matched_types(survey), f"검사 결과 {survey['type']}"
    else:
        _matched, _whose = {view_type_ui.value: mbti.MATCH}, None
    _c, _m, _d = bundle.meta5["counts"], bundle.meta5["medians"], bundle.meta5["diagnostics"]
    _title = f"{_whose} 기준: 상권 MBTI 유형 {mbti.matched_text(_matched)}" if _whose else f"상권 MBTI 유형 {view_type_ui.value}"
    _maps = mo.hstack([
        panel(f"서울 상권 지도 · {_title}",
              "파란색은 같은 유형(일치), 주황색은 경계 글자를 바꾼 유형(경계 유형), 옅은 회색은 다른 유형, 진한 회색은 판정 불가입니다. 상권을 가리키면 유형과 점수가 보입니다.",
              chart(v.mbti_map_chart(bundle, _matched, pal))),
        panel("상권 유형을 나눈 방법",
              f"점 하나가 상권 하나입니다. 세로 점선은 L/V 점수, 가로 점선은 E/P 점수의 서울 중앙값({_m['lv_score']:.1f}점 · {_m['ep_score']:.1f}점)이고, 네 칸이 LE · LP · VE · VP입니다.",
              chart(v.quadrant_chart(bundle, _matched, pal))),
    ], gap=1.5, align="start", wrap=True)
    _rules = mo.md(f"""
    #### 상권 유형을 정한 방법 (2025년 자료, 관광특구 {_c['tourist_excluded']}곳을 뺀 {_c['areas']:,}곳)

    - **L 생활형 / V 방문형 [가정]:** 직장인구 ÷ 상주인구, 유동인구 ÷ 상주인구를 서울 안 순위(백분위)로 바꿔 평균한 **L/V 점수**가 서울 중앙값보다 크면 V입니다.
      두 비율 중 하나만 써도 {_d['lv_worker_ratio_only_agree'] * 100:.0f}% · {_d['lv_floating_ratio_only_agree'] * 100:.0f}% 상권이 같은 글자가 나옵니다.
    - **E 실속형 / P 프리미엄형 [가정]:** 같은 업종 안에서 객단가(매출 금액 ÷ 매출 건수) 순위를 매긴 뒤, 상권별로 매출 건수로 가중 평균한 **E/P 점수**가 서울 중앙값보다 크면 P입니다.
      매출 제공 업종 {_c['ep_industries']}개, 4개 분기 매출이 모두 있는 {_c['ep_cells']:,}칸을 썼습니다. 점포 5개 이상 칸만 써도 {_d['ep_stores_ge5_agree'] * 100:.0f}% 상권이 같은 글자입니다.
    - **S 안정형 / G 성장형:** 상권 쪽에서는 판정하지 않습니다 (2025년 자료만 있어 성장성은 산출하지 않습니다).
    - **경계에 가까운 상권:** 중앙값 ±{bundle.meta5['rules']['near_median_points']}점 안에 L/V {_d['lv_near_median_5']}곳, E/P {_d['ep_near_median_5']}곳이 있습니다. 기준을 조금만 바꿔도 글자가 바뀔 수 있습니다.
    - L/V와 E/P는 거의 따로 움직입니다 (순위상관 {_d['spearman_lv_ep']:.2f}).

    #### 이 결과로 말할 수 없는 것

    - 유형이 맞는 상권에서 창업하면 결과가 좋다는 것. 유형은 상권을 고르는 조건일 뿐입니다.
    - **소비 잠재력**(기대 소비액과 실제 소비액의 차이). 계산 방식이 확정되지 않아 만들지 않았습니다.
    - 예산 적합성 (보증금 · 월세 자료가 없습니다).
    """)
    mo.vstack([
        *([] if _whose else [view_type_ui]),
        _maps,
        panel("상권 MBTI 유형별 상권 수", "상권 유형(골목상권 · 발달상권 · 전통시장)별로 나눠 셌습니다. 발달상권은 대부분 V(방문형)로 나옵니다. " + v.unknown_text(bundle),
              table(v.type_count_table(bundle), wrapped_columns=["S/G를 붙인 팀 유형표 이름"])),
        _rules,
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(PAGES, industry, industry_scored, mbti, mbti_filter, mbti_mode_ui, mo, nav, profile, summary, survey, v, weights, weights_zero):
    mo.stop(nav.value != PAGES[1])
    _name = industry["업종명"]
    _notes = []
    _wider = "왼쪽에서 자치구나 상권 유형을 넓혀 보세요" + (" ('유형이 맞는 상권만 보기'를 끄면 모든 MBTI 유형의 상권을 봅니다)." if mbti_filter is not None else ".")
    if profile:
        _scope = (f"상권 MBTI 유형이 {mbti.matched_text(profile['matched'])}인 상권만 보여 줍니다." if mbti_filter is not None
                  else "모든 상권을 보여 주고, 비교표의 '유형 일치' 열에 표시합니다.")
        _notes.append(mo.callout(mo.md(
            f"**금융 MBTI {profile['emoji']} {profile['type']} {profile['name']}** 적용 중 ({profile['text']}). {_scope} "
            f"가중치는 **{profile['weight_label']}** 기본값입니다 [가정]. 상권의 S/G는 판정하지 않아 앞의 두 글자(L/V · E/P)만 맞춥니다."), kind="info"))
    elif mbti_mode_ui.value == mbti.MODE_SURVEY:
        _notes.append(mo.callout(f"금융 MBTI 검사를 15문항 중 {survey['answered']}개 답했습니다. '금융 MBTI 검사' 탭에서 끝까지 답하면 적용됩니다.", kind="neutral"))
    if summary["areas"] == 0:
        _notes.append(mo.callout(f"조건에 맞는 상권이 없습니다. {_wider}", kind="warn"))
    elif summary["areas"] == summary["no_store"]:
        _notes.append(mo.callout(f"현재 조건의 상권 {summary['areas']:,}곳에는 **{_name}** 점포가 없습니다. {_wider}", kind="warn"))
    if not industry_scored:
        _notes.append(mo.callout(mo.md(
            f"**{_name}**은 평균 점포 5개 이상인 상권이 서울 전체에서 {industry['비교 상권 수(평균 점포 5개 이상)']}곳뿐입니다(30곳 미만). "
            "비교할 상권이 너무 적어 **업종 내 비교 점수를 만들지 않았습니다.** 아래 표는 점수 없이 보는 참고용 원값입니다."), kind="info"))
    elif industry["매출 제공"] == "아니오":
        _notes.append(mo.callout(mo.md(
            f"**{_name}**은 서울시가 추정매출을 제공하지 않는 업종입니다. 매출 잠재력은 **자료 없음**이며 0점이 아닙니다. "
            "나머지 3개 영역(경쟁 · 안정성 · 수요)으로만 종합 점수를 계산합니다."), kind="info"))
    elif industry["매출 잠재력 점수"] == "아니오":
        _notes.append(mo.callout(mo.md(
            f"**{_name}**은 4개 분기 매출이 모두 있는 비교 상권이 {industry['매출 비교 상권 수(4개 분기 매출)']}곳(30곳 미만)이라 "
            "매출 잠재력은 **자료 없음**입니다. 나머지 3개 영역으로 계산합니다."), kind="info"))
    if weights_zero and industry_scored:
        _notes.append(mo.callout("가중치가 모두 0이라 종합 점수를 계산할 수 없습니다. 왼쪽 가중치를 하나 이상 0보다 크게 올려 주세요. 영역 점수는 표에서 그대로 볼 수 있습니다.", kind="warn"))
    _tiles = mo.hstack([
        mo.stat(f"{summary['scored']:,}곳", label="비교 대상 상권 (점수 있음)", caption=f"현재 조건의 상권 {summary['areas']:,}곳 중", bordered=True),
        mo.stat(f"{summary['reference'] + summary['thin']:,}곳", label="점수 제외 상권",
                caption=f"점포 5개 미만(참고용) {summary['reference']:,}곳 · 업종 비교 상권 부족 {summary['thin']:,}곳", bordered=True),
        mo.stat(f"{summary['no_store']:,}곳", label="이 업종 점포가 없는 상권", caption="2025년 평균 점포 0개 포함", bordered=True),
        mo.stat(v.fmt(summary["median_total"], ".1f", "점"), label="종합 점수 중앙값 (현재 조건)", caption=v.weight_text(weights), bordered=True),
    ], widths="equal", gap=1)
    mo.vstack([*_notes, _tiles], gap=0.8)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, industry_scored, mo, nav, pal, panel, rows, selected_code, shown, summary, table, v):
    mo.stop(nav.value != PAGES[1] or rows.empty)
    if industry_scored:
        map_ui = mo.ui.altair_chart(v.map_chart(bundle, rows, shown, selected_code, pal), chart_selection=False, legend_selection=False)
        _legend = mo.md(
            f"<small><span style='color:{pal['blues'][3]}'>■</span> 진할수록 종합 점수가 높음 &nbsp; "
            f"<span style='color:{pal['missing']}'>■</span> 회색: 점수 없음 (점포 5개 미만 · 참고용) &nbsp; "
            f"<span style='color:{pal['axis']}'>■</span> 옅은 회색: 이 업종 점포 없음</small>")
        _content = panel("상권 지도",
                         "상권을 클릭하면 '상권 상세' 탭의 상권이 바뀝니다. 점수는 서울 같은 업종 기준이라 자치구·유형 필터를 바꿔도 다시 계산하지 않습니다.",
                         mo.vstack([map_ui, _legend], gap=0.3))
    else:
        map_ui = None
        _ref = v.reference_table(rows)
        _content = panel(f"참고용 원값: 이 업종 점포가 있는 상권 {len(_ref):,}곳",
                         "점수를 만들 수 없는 업종이라 지도 대신 원값 표를 보여 줍니다. '자료 없음'은 0이 아닙니다.",
                         table(_ref, hidden_columns=["trdar_code"], pagination=True, page_size=10, show_search=True,
                               format_mapping={"평균 점포 수": lambda x: v.fmt(x, ",.2f", "개")}))
    _content
    return (map_ui,)


@app.cell(hide_code=True)
def _(map_ui, set_code, v):
    if map_ui is not None:
        _picked = v.picked_code(map_ui.selections)
        if _picked is not None:
            set_code(_picked)
    return


@app.cell(hide_code=True)
def _(PAGES, industry_scored, mo, nav, panel, rows, table, v):
    mo.stop(nav.value != PAGES[1] or rows.empty or not industry_scored)
    _table = v.score_table(rows)
    _tips = {
        "종합 점수": "자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균입니다.",
        "계산 영역 수": "종합 점수를 계산할 때 쓴 영역의 수입니다 (가중치가 0인 영역은 세지 않음).",
        "경쟁": "유동인구 1,000명당 같은 업종 점포 수가 적을수록 높은 점수 [가정]",
        "안정성 (신뢰도 낮음)": "축소 추정 폐업률이 낮을수록 높은 점수. 1년치 자료라 신뢰도가 낮습니다.",
        "수요": "면적당 유동·직장·상주인구 백분위의 평균 [가정]",
        "MBTI 유형": "상권의 금융 MBTI 앞 두 글자 (L 생활형/V 방문형 · E 실속형/P 프리미엄형). S/G는 판정하지 않음",
        "유형 일치": "내 금융 MBTI와 같은 유형이면 일치, 경계 글자를 바꾼 유형이면 경계 유형",
    }
    area_ui = mo.ui.table(
        _table, selection="single", page_size=10, hidden_columns=["trdar_code"], format_mapping=v.score_formats(),
        freeze_columns_left=["상권"], wrapped_columns=["자료 없는 영역"], show_column_summaries=False, show_data_types=False,
        header_tooltip={k: x for k, x in _tips.items() if k in _table.columns})  # MBTI 열은 유형을 적용했을 때만 있다
    _ref = v.reference_table(rows)
    _items = [panel("상권 비교표",
                    "종합 점수가 높은 순서입니다. 열 이름을 눌러 정렬하고, 검색창(Search)으로 상권을 찾을 수 있습니다. "
                    "행 앞의 네모 칸을 누르면 '상권 상세' 탭의 상권이 바뀝니다. '자료 없음'은 0점이 아닙니다.", area_ui)]
    if len(_ref):
        _items.append(mo.accordion({f"참고용: 점수가 없는 상권 {len(_ref):,}곳 (점포 5개 미만, 원값만)": table(
            _ref, hidden_columns=["trdar_code"], pagination=True, page_size=10, show_search=True,
            format_mapping={"평균 점포 수": lambda x: v.fmt(x, ",.2f", "개")})}))
    mo.vstack(_items, gap=1)
    return (area_ui,)


@app.cell(hide_code=True)
def _(area_ui, set_code):
    if len(area_ui.value):
        set_code(area_ui.value["trdar_code"].iloc[0])
    return


@app.cell(hide_code=True)
def _(PAGES, industry_ui, mo, nav, rows, selected_code, set_code, v):
    mo.stop(nav.value != PAGES[2])
    mo.stop(rows.empty, mo.vstack([industry_ui, mo.callout("현재 조건에 이 업종 점포가 있는 상권이 없습니다. 왼쪽에서 자치구·유형 필터나 '유형이 맞는 상권만 보기'를 넓혀 보세요.", kind="warn")]))
    _labels = {}
    for _r in v.order_rows(rows).itertuples():
        _key = f"{_r.trdar_name} · {_r.gu_name}" + ("" if _r.scored else " (참고용)")
        _labels[_key if _key not in _labels else f"{_key} [{_r.trdar_code}]"] = _r.trdar_code
    _current = next(k for k, c in _labels.items() if c == selected_code)
    area_pick = mo.ui.dropdown(_labels, value=_current, searchable=True, label="자세히 볼 상권 (점수 높은 순)", on_change=set_code)
    mo.hstack([industry_ui, area_pick], justify="start", align="end", gap=1.5, wrap=True)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, industry, medians, mo, nav, pal, panel, rows, selected_code, table, v):
    mo.stop(nav.value != PAGES[2] or selected_code is None)
    _cell = rows.loc[rows["trdar_code"].eq(selected_code)].iloc[0]
    _q = v.quarter_rows(bundle, selected_code, _cell["industry_code"])
    _mbti = f"MBTI 유형 {v.type2_text(_cell['type2'])} (L/V {v.fmt(_cell['lv_score'], '.1f', '점')} · E/P {v.fmt(_cell['ep_score'], '.1f', '점')})"
    if "mbti_match" in _cell:
        _mbti += f" · 내 유형과 {_cell['mbti_match']}"
    _head = mo.md(f"### {_cell['trdar_name']} · {_cell['industry_name']}\n{_cell['gu_name']} · {_cell['trdar_type']} · 평균 점포 {_cell['stores']:,.2f}개 · {_cell['status']}<br><small>{_mbti}</small>")
    if _cell["scored"]:
        _total = "자료 없음 (가중치가 0인 영역만 자료가 있음)" if v.fmt(_cell["total"]) == v.MISSING else f"{_cell['total']:.1f}점"
        _scores = mo.vstack([
            mo.hstack([
                mo.stat(_total, label="종합 점수", caption=f"{_cell['used']}개 영역으로 계산 · 서울 같은 업종 {medians['count']:,}곳 중 비교", bordered=True),
                mo.stat(v.fmt(medians["total"], ".1f", "점"), label="서울 같은 업종 종합 점수 중앙값", caption="현재 가중치 기준", bordered=True),
            ], widths="equal", gap=1),
            panel("영역별 점수", "막대는 이 상권의 점수, 검은 세로선은 서울 같은 업종의 중앙값입니다. 자료가 없는 영역은 막대 없이 '자료 없음'으로 씁니다.",
                  chart(v.score_bar_chart(_cell, medians, pal))),
        ], gap=0.8)
    elif not industry["점수 생성"] == "예":
        _scores = mo.callout("이 업종은 비교 상권이 30곳 미만이라 점수를 만들지 않았습니다. 아래 원값은 참고용입니다.", kind="info")
    else:
        _scores = mo.callout(f"이 상권은 이 업종 점포가 평균 {_cell['stores']:.2f}개라(5개 미만) 점수를 매기지 않았습니다. 아래 원값은 참고용입니다.", kind="info")
    _trend, _flow = chart(v.month_trend_chart(_q, pal)), chart(v.flow_chart(_q, pal))
    mo.vstack([
        _head,
        _scores,
        panel("원값과 서울 같은 업종 중앙값", "중앙값은 서울 같은 업종의 점수 대상 상권 기준입니다(필터와 무관). '자료 없음'은 0이 아닙니다.",
              table(v.compare_table(_cell, medians), wrapped_columns=["비고"])),
        mo.hstack([
            panel("분기별 점포당 월매출", "1년치 네 점이라 계절성과 추세를 구분할 수 없습니다. 매출이 없는 분기는 점을 찍지 않습니다.",
                  _trend if _trend is not None else "이 칸은 분기 매출 자료가 없습니다 (0원이 아닙니다)."),
            panel("분기별 개업·폐업 건수", "점포가 적은 칸은 한두 건에도 크게 흔들립니다.", _flow),
        ], gap=1.5, align="start", wrap=True),
        panel("분기 매출 증감률 (참고용, 점수에 넣지 않음)",
              f"직전 분기 대비 변화입니다. 계절성이 섞여 있고 전년 대비 성장이 아닙니다. 극단값을 줄이려고 서울 전체 {bundle.meta['winsor']['observed']:,}개 관측의 상하위 5%에서 잘랐습니다.",
              table(v.qoq_table(_q, bundle.meta["winsor"]), wrapped_columns=["비고"])),
        panel("데이터 시점", "직장인구 · 상주인구 · 집객시설은 2025년 안에서 값이 바뀌지 않습니다. 실제 값이 마지막으로 바뀐 분기를 함께 봅니다.",
              table(v.vintage_table(_cell, bundle.shared_meta))),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(mo, v):
    metric_ui = mo.ui.dropdown(list(v.METRICS), value="점포당 월매출 (만 원)", label="히스토그램 지표")
    return (metric_ui,)


@app.cell(hide_code=True)
def _(PAGES, all_rows, bundle, chart, gu_ui, industry, industry_scored, industry_ui, metric_ui, mo, nav, pal, panel, rows, v, weights_zero):
    mo.stop(nav.value != PAGES[3])
    _hist, _info = v.histogram_chart(rows, metric_ui.value, bundle.meta["rules"]["min_stores"], pal)
    if _hist is None:
        _left = "현재 조건에 이 지표 값이 있는 상권이 없습니다. 매출 미제공 업종이면 점포당 월매출은 자료 없음입니다."
    else:
        _left = chart(_hist)
    _outside = f" 상위 1%보다 큰 {_info['outside']:,}곳은 오른쪽 끝 칸에 모았습니다." if _info.get("outside") else ""
    if not industry_scored:
        _right = "이 업종은 비교 상권이 30곳 미만이라 종합 점수가 없습니다."
    elif weights_zero:
        _right = "가중치가 모두 0이라 종합 점수가 없습니다. 왼쪽 가중치를 올려 주세요."
    else:
        _spec = v.gu_chart(all_rows, pal, gu_ui.value)
        _right = chart(_spec) if _spec is not None else "종합 점수가 있는 상권이 없습니다."
    _empty_gus = sorted(set(bundle.areas["gu_name"]) - set(v.gu_frame(all_rows)["gu_name"])) if industry_scored and not weights_zero else []
    _gu_note = "관광특구를 뺀 상권 기준입니다. 점선은 50점입니다. 자치구 필터와 상관없이 서울 전체를 보여 주고, 고른 자치구는 주황색입니다."
    if _empty_gus:
        _gu_note += f" 점수 있는 상권이 없는 자치구: {', '.join(_empty_gus)}."
    mo.vstack([
        mo.hstack([industry_ui, metric_ui], justify="start", align="end", gap=1.5, wrap=True),
        mo.hstack([
            panel(f"{industry['업종명']} · {metric_ui.value} 분포",
                  "현재 자치구·유형 필터 안의 상권입니다. 파란색은 점수 대상, 회색은 점포 5개 미만이라 점수에서 뺀 상권입니다. "
                  "점포 수 지표에서는 점선이 점수 기준(5개)이고, 다른 지표에서는 점수 대상 중앙값입니다." + _outside, _left),
            panel("자치구별 종합 점수 중앙값", _gu_note, _right),
        ], gap=1.5, align="start", wrap=True),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, mo, nav, panel, rows, table, v):
    mo.stop(nav.value != PAGES[4])
    _m = bundle.meta
    _cd = _m["diagnostics"]["competition_demand"]
    _rel = {(x["구간"], x["지표"]): x["상관"] for x in bundle.shared_meta["reliability"] if x["단위"] == "상권×업종 칸"}
    _industry_counts = v.industry_status_counts(rows)
    mo.vstack([
        panel("점수 설계표 (2026-11-07 승인)", "[가정]은 데이터로 정할 수 없어 팀이 확인해야 하는 항목입니다. data/점수_설계표.csv와 같습니다.",
              mo.md(v.design_markdown(bundle.design))),
        panel("STEP 5 금융 MBTI 설계표 (2026-11-14 승인)", "김지영/step5_design/data/STEP5_설계표.csv와 같습니다. 자세한 설명은 STEP5_금융MBTI_설계.md에 있습니다.",
              mo.md(v.design_markdown(bundle.design5))),
        mo.hstack([
            panel("대상 조건과 제외 사유 (서울 전체)", "2025년 연간 상권×업종 77,694칸을 사유별로 나눴습니다.", table(v.exclusion_table(_m), wrapped_columns=["설명"])),
            panel("고른 업종 · 현재 조건", "점포가 있는 상권만 셉니다.", table(_industry_counts) if len(_industry_counts) else "현재 조건에 이 업종 점포가 있는 상권이 없습니다."),
        ], gap=1.5, align="start", wrap=True),
        panel("업종 100개의 점수 가능 여부", "업종별_점수_가능여부.csv와 같습니다. 검색창으로 업종을 찾을 수 있습니다.",
              table(bundle.availability, pagination=True, page_size=10, show_search=True, wrapped_columns=["사유"])),
        panel("영역끼리 겹치는 정보 (순위상관)",
              f"1에 가까울수록 두 점수의 순서가 같습니다. 경쟁과 수요는 둘 다 유동인구를 써서 일부 겹칩니다(전체 {_cd['overall']:.2f}, 업종별 중앙값 {_cd['industry_median']:.2f}). "
              f"0.8 이상인 업종은 {_cd['industries_ge_0_8']}개({_cd['top3'][0]['업종']} {_cd['top3'][0]['상관']:.2f})뿐이라 둘 다 둡니다.",
              table(v.correlation_table(_m))),
        mo.md(f"""
    **이 점수로 말할 수 없는 것**

    - 창업 성공 확률이나 가게가 살아남을 확률
    - 순이익 (임대료 · 인건비 · 원가 자료가 없습니다)
    - 예산 적합성 (임대료 · 보증금 · 권리금 자료가 없습니다)
    - 전년 대비 성장 (2025년 자료만 있어 성장성은 산출하지 않습니다)
    - 개별 가게의 매출 (상권 안 같은 업종 평균입니다)
    - 금융 MBTI 유형이 맞는 상권에서 창업하면 결과가 좋다는 것 (유형은 상권을 고르는 조건일 뿐입니다)
    - 소비 잠재력 (계산 방식이 확정되지 않아 만들지 않았습니다)

    **읽을 때 주의할 점**

    - **업종 내 비교 점수**입니다. 서울의 같은 업종 점수 대상 상권 안에서 매긴 백분위라 다른 업종의 점수와 비교하지 않습니다.
      가장 낮은 점수도 0이 아니라 100 ÷ 비교 상권 수입니다.
    - **안정성 (1년치·신뢰도 낮음)**: 폐업률은 1년치라 우연의 영향이 큽니다. 같은 칸의 상·하반기 폐업률 상관이 점포 3~9개 칸 {_rel[('3~9개', '폐업률')]:.2f},
      50개 이상 칸에서도 {_rel[('50개 이상', '폐업률')]:.2f}입니다. 그래서 업종 평균 쪽으로 당기는 축소 추정(α = {_m['alpha']:.2f})을 쓰며, 이 때문에 점수 차이가 작게 나타납니다.
    - **추정매출**은 카드 결제 자료를 바탕으로 한 추정치입니다. 실제 매출이나 이익이 아닙니다.
    - **경쟁 · 수요 [가정]**: 유동인구는 원자료 인구 수 단위이며 서로 다른 사람의 수가 아닙니다. 직장인구 · 상주인구는 실제 통계 시점이 2025년이 아닐 수 있습니다.
    - **상관관계는 인과관계가 아닙니다.** 점수가 높은 상권에서 창업하면 결과가 좋아진다는 뜻이 아닙니다.
    """),
    ], gap=1.4)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    <small>출처: 서울특별시 서울시 상권분석서비스 (추정매출 · 점포 · 유동인구 · 직장인구 · 상주인구 · 집객시설 · 상권 영역).
    데이터 가공: 팀 공용 STEP 2·3 산출물(김지영/step2_3), 상권 경계(김지영/claude_dashboard/data). 점수 계산: build_scores.py.
    금융 MBTI: 팀 유형표(seoul-commercial-analysis/data/raw/금융_MBTI.md), 상권 MBTI 유형 계산: 김지영/step5_design/build_types.py.</small>
    """)
    return


if __name__ == "__main__":
    app.run()
