import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="SpotFit 상권 비교 점수 (2025)")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import pandas as pd

    import views as v

    PAGES = ["상권 찾기", "상권 상세", "지표 분포와 자치구 비교", "점수 기준과 한계"]
    return PAGES, mo, pd, v


@app.cell(hide_code=True)
def _(mo, v):
    try:
        bundle = v.load_bundle()
    except FileNotFoundError as _error:
        mo.stop(True, mo.callout(str(_error), kind="danger"))
    pal = v.palette(mo.app_meta().theme)


    def panel(title, note, content):
        """제목과 읽는 법을 차트 위에 붙인다. 차트가 없으면 이유를 대신 보여 준다."""
        body = mo.callout(content, kind="neutral") if isinstance(content, str) or content is None else content
        return mo.vstack([mo.md(f"**{title}**<br><small>{note}</small>"), body], gap=0.4)


    def chart(spec):
        return mo.ui.altair_chart(spec, chart_selection=False, legend_selection=False) if spec is not None else None
    return bundle, chart, pal, panel


@app.cell(hide_code=True)
def _(bundle, mo):
    _c = bundle.meta["counts"]
    mo.md(f"""
    # SpotFit 상권 비교 점수 (2025년)

    희망 업종을 고르면, **서울의 같은 업종 상권끼리** 4개 영역(매출 잠재력 · 경쟁 · 안정성 · 수요)을 비교한 점수를 보여 줍니다.
    관광특구를 뺀 상권 기준 · 점수 대상 {_c['target_cells']:,}칸 · 점수를 만들 수 있는 업종 {_c['scored_industries']}개 / {_c['industries']}개.
    **성장성은 2025년 자료만 있어 산출하지 않습니다.** 이 점수는 창업 성공 가능성이나 수익을 뜻하지 않습니다.
    """)
    return


@app.cell(hide_code=True)
def _(PAGES, mo):
    nav = mo.ui.tabs({name: "" for name in PAGES})
    nav
    return (nav,)


@app.cell(hide_code=True)
def _(bundle, mo, v):
    _ind = bundle.industries.sort_values("업종명")
    industry_ui = mo.ui.dropdown(dict(zip(_ind["업종명"], _ind["업종_코드"])), value="커피-음료", searchable=True, label="희망 업종")
    gu_ui = mo.ui.multiselect(sorted(bundle.scores["gu_name"].dropna().unique()), label="자치구 (비우면 전체)")
    type_ui = mo.ui.multiselect(v.TYPES, label="상권 유형 (비우면 전체)")
    _w = bundle.meta["rules"]["default_weights"]
    w_sales = mo.ui.slider(0, 50, step=5, value=_w["sales"], label="매출 잠재력", show_value=True, debounce=True)
    w_comp = mo.ui.slider(0, 50, step=5, value=_w["comp"], label="경쟁", show_value=True, debounce=True)
    w_stab = mo.ui.slider(0, 50, step=5, value=_w["stab"], label="안정성", show_value=True, debounce=True)
    w_dem = mo.ui.slider(0, 50, step=5, value=_w["dem"], label="수요", show_value=True, debounce=True)
    demand_ui = mo.ui.dropdown({v_: k for k, v_ in bundle.meta["rules"]["demand_modes"].items()}, value="세 값 평균", label="수요: 주 고객층")
    get_code, set_code = mo.state(None)
    return demand_ui, get_code, gu_ui, industry_ui, set_code, type_ui, w_comp, w_dem, w_sales, w_stab


@app.cell(hide_code=True)
def _(PAGES, demand_ui, gu_ui, industry_ui, mo, nav, type_ui, w_comp, w_dem, w_sales, w_stab):
    mo.stop(nav.value == PAGES[3])
    mo.vstack([
        mo.hstack([industry_ui, gu_ui, type_ui, demand_ui], justify="start", align="end", gap=1.5, wrap=True),
        mo.hstack([mo.md("**가중치**"), w_sales, w_comp, w_stab, w_dem], justify="start", align="center", gap=1.5, wrap=True),
        mo.md("<small>기본 가중치(매출 30 · 경쟁 25 · 안정성 15 · 수요 30)는 팀이 확정하지 않은 <b>가정</b>입니다. "
              "금융 MBTI 유형표가 확정되면 유형별 기본 가중치를 연결합니다.</small>"),
    ], gap=0.5)
    return


@app.cell(hide_code=True)
def _(bundle, demand_ui, get_code, gu_ui, industry_ui, type_ui, v, w_comp, w_dem, w_sales, w_stab):
    weights = {"sales": w_sales.value, "comp": w_comp.value, "stab": w_stab.value, "dem": w_dem.value}
    demand_mode = demand_ui.value
    scope = v.filter_scope(bundle, industry_ui.value, gu_ui.value, type_ui.value, weights, demand_mode)
    industry_all = v.filter_scope(bundle, industry_ui.value, None, None, weights, demand_mode)
    industry = v.industry_info(bundle, industry_ui.value)
    summary = v.summarize(scope)
    selected_code = v.choose_code(get_code(), scope)
    return demand_mode, industry, industry_all, scope, selected_code, summary, weights


@app.cell(hide_code=True)
def _(PAGES, demand_mode, industry, mo, nav, scope, summary, v, weights):
    mo.stop(nav.value != PAGES[0])
    _notes = []
    if sum(weights.values()) == 0:
        _notes.append(mo.callout("가중치가 모두 0입니다. 하나 이상 올려 주세요.", kind="warn"))
    if summary["areas"] == 0:
        _notes.append(mo.callout("조건에 맞는 상권이 없습니다. 자치구나 상권 유형을 넓혀 보세요.", kind="warn"))
    elif not industry["점수_생성"]:
        _notes.append(mo.callout(mo.md(
            f"**{industry['업종명']}**은 점포 5개 이상인 상권이 서울 전체에 {industry['점포5개이상_상권_수']}곳뿐이라(기준 30곳) 점수를 만들지 않았습니다. "
            "아래 표에서 원값만 참고용으로 볼 수 있습니다."), kind="info"))
    elif not industry["매출_점수_생성"]:
        _why = "서울시가 추정매출을 제공하지 않는 업종" if not industry["매출_제공_업종"] else f"4개 분기 매출이 있는 상권이 {industry['매출비교_상권_수']}곳뿐인 업종(기준 30곳)"
        _notes.append(mo.callout(mo.md(f"**{industry['업종명']}**은 {_why}이라 매출 잠재력 없이 3개 영역으로 계산합니다. 매출이 낮다는 뜻이 아닙니다."), kind="info"))
    _tiles = mo.hstack([
        mo.stat(f"{summary['areas']:,}곳", label="조건 안 상권", caption="이 업종 점포가 있는 상권", bordered=True),
        mo.stat(f"{summary['scored']:,}곳", label="점수가 있는 상권", caption=f"매출 점수까지 있는 곳 {summary['with_sales']:,}곳", bordered=True),
        mo.stat(f"{summary['small']:,}곳", label="점포 5개 미만 (참고용)", caption="점수 없이 원값만 표시", bordered=True),
        mo.stat(f"{summary['few_peers']:,}곳", label="업종 비교 상권 부족", caption="업종 전체가 30곳 미만", bordered=True),
    ], widths="equal", gap=1)
    _chg = v.top_change(scope, weights, demand_mode)
    if _chg is not None:
        _notes.append(mo.callout(mo.md(
            f"**경쟁·수요 겹침 확인**: 경쟁 영역을 빼고 계산하면 지금 상위 {_chg['k']}곳 중 **{_chg['changed']}곳**이 바뀝니다 ({_chg['kept']}곳 유지). "
            "경쟁과 수요는 둘 다 유동인구를 써서 일부 겹칩니다(상관 0.47). 바뀌는 곳이 적으면 겹침의 영향이 작다는 뜻입니다."), kind="neutral"))
    mo.vstack([*_notes, _tiles], gap=0.8)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, demand_mode, gu_ui, industry_all, industry_ui, mo, nav, panel, scope, selected_code, type_ui, v, weights):
    mo.stop(nav.value != PAGES[0] or scope.empty)
    import time as _time
    _t0 = _time.perf_counter()
    # 한 번 만든 지도는 저장해 두고 다음부터 불러온다 (views.map_views 설명 참고)
    _spec, _html, _source = v.map_views(bundle, industry_ui.value, gu_ui.value, type_ui.value, weights, demand_mode,
                                        selected_code, mo.app_meta().theme, scope=scope, seoul=industry_all)
    map_ui = mo.ui.altair_chart(_spec, chart_selection=False, legend_selection=False) if _spec is not None else None
    _fig = mo.Html(_html) if _html else None
    _sec = _time.perf_counter() - _t0
    _how = {"메모리": "이번 실행 중 저장해 둔 지도를 불러왔습니다", "저장 파일": "저장된 지도 파일을 불러왔습니다",
            "새로 계산": "처음 보는 조합이라 새로 그리고 저장했습니다. 다음부터는 바로 불러옵니다"}[_source]
    _common = (f"진한 파란색일수록 종합 점수가 높습니다. 검은 번호는 지금 보이는 범위의 상위 {v.TOP_N}곳, 주황 테두리는 지금 고른 상권입니다. "
               "옅은 회색은 점수가 없는 상권(점포 5개 미만 등)이고 0점이 아닙니다.")
    mo.vstack([
        mo.md(f"**상권 지도**<br><small>{_common}<br>지도 준비: {_how} ({_sec:.2f}초).</small>"),
        mo.hstack([
            panel("Plotly 지도: 확대·이동", "마우스 휠로 확대·축소, 끌어서 이동합니다. 오른쪽 위 도구로 처음 위치로 돌아갑니다. 배경 지도는 인터넷 연결이 필요합니다.",
                  _fig if _fig is not None else "지도에 그릴 상권이 없습니다."),
            panel("Altair 지도: 클릭해서 고르기", "상권을 클릭하면 상권 상세 탭과 아래 비교표 선택이 그 상권으로 바뀝니다. 확대·이동은 되지 않습니다.",
                  map_ui if map_ui is not None else "지도에 그릴 상권이 없습니다."),
        ], widths="equal", gap=1.5, align="start", wrap=True),
    ], gap=0.6)
    return (map_ui,)


@app.cell(hide_code=True)
def _(map_ui, set_code, v):
    if map_ui is not None:
        _picked = v.picked_code(map_ui.selections)
        if _picked is not None:
            set_code(_picked)
    return


@app.cell(hide_code=True)
def _(PAGES, mo, nav, panel, scope, v):
    mo.stop(nav.value != PAGES[0] or scope.empty)
    table_ui = mo.ui.table(
        v.score_table(scope), selection="single", page_size=10, hidden_columns=["trdar_code"], show_column_summaries=False,
        show_data_types=False, freeze_columns_left=["상권"],
        header_tooltip={
            "종합 점수": "자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균입니다. 0~100.",
            "매출 잠재력": "점포당 월매출의 업종 안 백분위. 4개 분기 매출이 모두 있는 상권만.",
            "경쟁": "유동인구 1,000명당 같은 업종 점포 수가 적을수록 높습니다.",
            "안정성(신뢰도 낮음)": "보정 폐업률이 낮을수록 높습니다. 1년치라 신뢰도가 낮습니다.",
            "수요": "선택한 주 고객층의 면적당 인구 백분위입니다.",
        })
    panel("상권 비교표", "종합 점수가 높은 순서입니다. 빈칸은 자료가 없다는 뜻이고 0점이 아닙니다. 행을 고르면 상세가 바뀝니다. 점수는 서울 전체 같은 업종 기준이라 필터를 바꿔도 다시 계산하지 않습니다.", table_ui)
    return (table_ui,)


@app.cell(hide_code=True)
def _(set_code, table_ui):
    if len(table_ui.value):
        set_code(table_ui.value["trdar_code"].iloc[0])
    return


@app.cell(hide_code=True)
def _(PAGES, mo, nav, scope, selected_code, set_code):
    mo.stop(nav.value != PAGES[1] or scope.empty or selected_code is None)
    _labels = {f"{r.trdar_name} · {r.gu_name}": r.trdar_code for r in scope.itertuples()}
    _current = next(k for k, c in _labels.items() if c == selected_code)
    mo.ui.dropdown(_labels, value=_current, searchable=True, label="자세히 볼 상권", on_change=set_code)
    return


@app.cell(hide_code=True)
def _(mo, scope, selected_code, v):
    # 비교할 상권 고르기: 점수가 있는 상권만. 기본값은 지금 고른 상권 + 종합 점수 상위 상권으로 3곳
    _scored = scope.loc[scope["score_total"].notna()]
    _opts = {f"{r.trdar_name} · {r.gu_name} ({r.score_total:.0f}점)": r.trdar_code for r in _scored.itertuples()}
    _by_code = {c: k for k, c in _opts.items()}
    _default = [c for c in [selected_code, *_scored["trdar_code"]] if c in _by_code]
    _default = list(dict.fromkeys(_default))[:3]
    compare_ui = mo.ui.multiselect(_opts, value=[_by_code[c] for c in _default], max_selections=v.COMPARE_MAX,
                                   label=f"비교할 상권 (최대 {v.COMPARE_MAX}곳, 점수가 있는 상권만)")
    return (compare_ui,)


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, compare_ui, industry_all, mo, nav, pal, panel, pd, scope, selected_code, v):
    mo.stop(nav.value != PAGES[1])
    mo.stop(scope.empty or selected_code is None, mo.callout("조건에 맞는 상권이 없습니다.", kind="warn"))
    _row = scope.loc[scope["trdar_code"].eq(selected_code)].iloc[0]
    _q = v.quarter_rows(bundle, selected_code, _row["industry_code"])
    _total = "점수 없음" if pd.isna(_row["score_total"]) else f"{_row['score_total']:.0f}점"
    _cap = _row["score_status"] if pd.isna(_row["score_total"]) else f"{int(_row['n_areas'])}개 영역으로 계산"
    _tiles = mo.hstack([
        mo.stat(_total, label="종합 점수", caption=_cap, bordered=True),
        mo.stat(f"{_row['stores']:.1f}개", label="같은 업종 평균 점포", caption=f"프랜차이즈 {_row['franchise_pct']:.0f}%", bordered=True),
        mo.stat(v.fmt_money(_row["sales_month"]), label="점포당 월매출", caption=_row["sales_area_status"], bordered=True),
        mo.stat(v.fmt_num(_row["close_pct_shrunk"], 1, "%"), label="보정 폐업률", caption=f"폐업 {_row['closes']:.0f}건 · 신뢰도 낮음", bordered=True),
    ], widths="equal", gap=1)
    _qoq = pd.DataFrame({
        "분기": _q["분기"],
        "직전 분기 대비 매출 증감률 (참고용)": _q["qoq_winsor"].map(lambda x: "자료 없음" if pd.isna(x) else f"{x:+.1f}%"),
        "원값": _q["qoq_raw"].map(lambda x: "자료 없음" if pd.isna(x) else f"{x:+.1f}%"),
    })
    _w = bundle.meta["qoq_winsor"]
    _no = "이 칸은 분기 매출 자료가 없습니다."
    _vint = f"직장인구: {v.vintage_text(bundle.jy_meta, 'K06')} · 상주인구: {v.vintage_text(bundle.jy_meta, 'K07')} · 집객시설: {v.vintage_text(bundle.jy_meta, 'K05')}"
    _trend = chart(v.month_trend_chart(_q, pal))
    _cmp_rows = scope.set_index("trdar_code").loc[list(compare_ui.value)].reset_index() if compare_ui.value else scope.iloc[0:0]
    _radar = v.radar_chart(_cmp_rows, pal)
    _cbars = chart(v.compare_bars(_cmp_rows, pal))
    _cmp_none = "비교할 상권을 위에서 하나 이상 골라 주세요."
    _compare = mo.vstack([
        mo.md("#### 후보 상권 비교\n<small>같은 4개 영역 점수를 두 가지 그래프로 봅니다. "
              "<b>레이더 차트</b>는 상권별 모양(강점과 약점의 균형)을, <b>상권별 막대</b>는 정확한 점수를 비교하기 좋습니다. "
              "점선은 50점(서울 같은 업종의 가운데)입니다. 자료가 없는 영역은 레이더에서 선이 끊기고, 막대에서는 회색 '자료 없음'으로 보입니다.</small>"),
        compare_ui,
        mo.hstack([
            panel("레이더 차트: 강점·약점 모양", "바깥쪽으로 넓게 퍼질수록 점수가 높습니다. 범례를 누르면 그 상권을 숨기거나 다시 보입니다.",
                  _radar if _radar is not None else _cmp_none),
            panel("상권별 막대 (서브플롯)", "칸 하나가 상권 하나입니다. 가로축은 영역, 세로축은 점수, 색은 영역입니다.",
                  _cbars if _cbars is not None else _cmp_none),
        ], gap=1.5, align="start", wrap=True),
    ], gap=0.6)
    mo.vstack([
        mo.md(f"### {_row['trdar_name']} · {_row['industry_name']}\n{_row['gu_name']} · {_row['trdar_type']}"),
        _tiles,
        mo.hstack([
            panel("4개 영역 점수", "서울 같은 업종 상권 안에서의 위치입니다. 점선(50점)이 가운데입니다. 회색 '자료 없음'은 0점이 아닙니다.", chart(v.area_bars(_row, pal))),
            panel("원값과 서울 같은 업종 중앙값", "점수 대상 상권들의 중앙값과 비교합니다.",
                  mo.ui.table(v.raw_compare(_row, industry_all), selection=None, pagination=False, show_column_summaries=False, show_data_types=False, show_download=False, show_search=False)),
        ], gap=1.5, align="start", wrap=True),
        _compare,
        mo.hstack([
            panel("분기별 점포당 월매출", "1년치 네 점이라 계절 변화와 추세를 구분할 수 없습니다.", _trend if _trend is not None else _no),
            panel("분기별 개업·폐업", "점포가 적은 칸은 한두 건에도 크게 흔들립니다.", chart(v.flow_chart(_q, pal))),
        ], gap=1.5, align="start", wrap=True),
        panel("직전 분기 대비 매출 증감률 (점수에 쓰지 않음)", f"계절 변화가 섞여 성장성으로 읽으면 안 됩니다. 서울 전체 상하위 5%({_w['p5']:.1f}% ~ {_w['p95']:+.1f}%) 밖의 값은 경계값으로 잘라 표시합니다.",
              mo.ui.table(_qoq, selection=None, pagination=False, show_column_summaries=False, show_data_types=False, show_download=False, show_search=False)),
        mo.md(f"<small>데이터 시점: {_vint}. 2025년 안에서 값이 바뀌지 않은 자료는 분기마다 같은 값입니다.</small>"),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(mo, v):
    hist_ui = mo.ui.dropdown(list(v.HIST_METRICS), value="평균 점포 수", label="분포를 볼 지표")
    return (hist_ui,)


@app.cell(hide_code=True)
def _(PAGES, chart, hist_ui, mo, nav, pal, panel, scope, v):
    mo.stop(nav.value != PAGES[2])
    mo.stop(scope.empty, mo.callout("조건에 맞는 상권이 없습니다.", kind="warn"))
    _h = chart(v.histogram(scope, hist_ui.value, pal))
    _g = chart(v.gu_chart(scope, pal))
    mo.vstack([
        hist_ui,
        mo.hstack([
            panel(f"{hist_ui.value} 분포", "선택 업종의 조건 안 상권입니다. 파란색은 점수 대상, 회색은 점수가 없는 상권입니다. 평균 점포 수의 점선은 점수 기준(5개)입니다.",
                  _h if _h is not None else "표시할 값이 없습니다."),
            panel("자치구별 종합 점수 중앙값", "관광특구를 뺀 기준입니다. 상권 수가 적은 자치구는 중앙값이 쉽게 흔들립니다.",
                  _g if _g is not None else "점수가 있는 상권이 없습니다."),
        ], gap=1.5, align="start", wrap=True),
    ], gap=1)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, mo, nav, panel):
    import textwrap
    mo.stop(nav.value != PAGES[3])
    _m = bundle.meta
    _c = _m["counts"]
    _s = _m["spearman"]
    _status = "\n".join(f"| {k} | {v_:,} |" for k, v_ in _c["status"].items())
    _sales = "\n".join(f"| {k} | {v_:,} |" for k, v_ in _c["sales_area_status"].items())
    mo.vstack([
        panel("점수 설계표", "팀 결정(2026-11-05)과 승인받은 설계입니다. [가정]은 팀이 아직 확정하지 않은 항목입니다.",
              mo.ui.table(bundle.design, selection=None, pagination=False, show_column_summaries=False, show_data_types=False, show_search=False)),
        mo.md(textwrap.dedent(f"""
    ### 대상 조건과 제외 수

    | 점수 상태 (관광특구 제외 상권×업종 {_c['cells']:,}칸) | 칸 수 |
    |:---|---:|
    {{STATUS}}

    | 매출 영역 상태 (점수 대상 {_c['target_cells']:,}칸) | 칸 수 |
    |:---|---:|
    {{SALES}}

    - 관광특구 6곳은 다른 상권과 겹쳐 매출이 중복되므로 처음부터 뺐습니다.
    - 평균 점포 수 = 4개 분기 점포 수 합 ÷ 4 (분기 자료가 없으면 그 분기는 0개).
    - 점수는 서울 전체 같은 업종 안의 백분위입니다. 자치구·유형 필터는 보이는 범위만 좁히고 점수를 다시 계산하지 않습니다.

    ### 영역끼리 얼마나 겹치나 (Spearman 상관, 점수 대상 칸)

    | 짝 | 상관 | 읽는 법 |
    |:---|---:|:---|
    | 경쟁 · 수요(세 값 평균) | {_s['경쟁_수요(세 값 평균)']:+.2f} | 둘 다 유동인구를 써서 일부 겹침. 상권 찾기 탭의 '겹침 확인'으로 영향 확인 |
    | 직장인구 · 상주인구 밀도 | {_s['직장인구_상주인구_밀도']:+.2f} | 서로 반대로 움직임. 세 값 평균은 가운데로 몰리기 쉬워 주 고객층 선택을 둠 |
    | 매출 · 경쟁 | {_s['매출_경쟁']:+.2f} | |
    | 매출 · 안정성 | {_s['매출_안정성']:+.2f} | |
    | 매출 · 수요(세 값 평균) | {_s['매출_수요(세 값 평균)']:+.2f} | |

    ### 이 점수로 말할 수 없는 것

    | 말하면 안 되는 것 | 이유 |
    |:---|:---|
    | 창업 성공 확률, 생존확률 | 점포별 개·폐업 이력이 없습니다. 폐업률은 확률이 아닙니다 |
    | 순이익, 수익성 | 임대료·인건비·원가 자료가 없습니다. 매출은 카드사 자료 기반 **추정치**입니다 |
    | 예산 적합성 | 임대료·보증금·권리금·시설비 자료가 없어 **예산 적합성은 판단하지 않습니다** |
    | 전년 대비 성장 | 2025년 자료만 있어 **성장성은 산출하지 않습니다** |
    | 개별 가게의 매출 | 매출은 상권×업종 단위 추정 합계입니다. 점포당 월매출은 비교용 대리지표입니다 |
    | 원인과 결과 | 점수와 지표의 관계는 상관이며 인과가 아닙니다 |

    - 안정성은 1년치 폐업률이라 상반기와 하반기 값이 거의 따로 놉니다. 그래서 기본 가중치를 낮게(15) 두었습니다.
    - 직장인구·상주인구·집객시설은 2025년 안에서 값이 바뀌지 않습니다.
    - 출처: 서울특별시 상권분석서비스 / 소상공인시장진흥공단 상가(상권)정보. 데이터 가공: 김지영 step2_3·claude_dashboard (읽기만 함).
    """).replace("{STATUS}", _status).replace("{SALES}", _sales)),
    ], gap=1)
    return


if __name__ == "__main__":
    app.run()
