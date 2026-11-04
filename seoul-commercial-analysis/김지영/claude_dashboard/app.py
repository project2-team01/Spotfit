import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Spotfit 상권 탐색기")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import pandas as pd

    import views as v

    PAGES = ["상권 찾기", "업종 비교", "근거와 한계"]
    return PAGES, mo, pd, v


@app.cell(hide_code=True)
def _(mo, v):
    try:
        bundle = v.load_bundle(mo.notebook_dir())
    except FileNotFoundError as _error:
        mo.stop(True, mo.callout(str(_error), kind="danger"))
    pal = v.palette(mo.app_meta().theme)


    def panel(title, note, content):
        """제목과 읽는 법을 차트 위에 붙인다. 차트가 없으면 이유를 대신 보여 준다."""
        body = mo.callout(content, kind="neutral") if isinstance(content, str) else content
        return mo.vstack([mo.md(f"**{title}**<br><small>{note}</small>"), body], gap=0.4)


    def chart(spec):
        return mo.ui.altair_chart(spec, chart_selection=False, legend_selection=False) if spec is not None else None
    return bundle, chart, pal, panel


@app.cell(hide_code=True)
def _(bundle, mo):
    _t = bundle.meta["totals"]
    mo.md(f"""
    # Spotfit 상권 탐색기

    희망 업종을 고르면 어느 상권을 살펴볼지, 그 근거를 얼마나 믿을 수 있는지 보여 줍니다.
    서울 2025년 · 관광특구를 뺀 {_t['areas']:,}개 상권 · 추정매출 {_t['sales'] / 1e12:.1f}조원
    """)
    return


@app.cell(hide_code=True)
def _(PAGES, mo):
    nav = mo.ui.tabs({name: "" for name in PAGES})
    nav
    return (nav,)


@app.cell(hide_code=True)
def _(bundle, mo, v):
    _industries = bundle.industries.sort_values("industry_name")
    industry_ui = mo.ui.dropdown(dict(zip(_industries["industry_name"], _industries["industry_code"])), value="커피-음료", searchable=True, label="희망 업종")
    gu_ui = mo.ui.multiselect(sorted(bundle.areas["gu_name"].unique()), label="자치구 (비우면 전체)")
    type_ui = mo.ui.multiselect(v.TYPES, label="상권 유형 (비우면 전체)")
    min_ui = mo.ui.slider(1, 30, value=bundle.meta["rules"]["min_stores"], step=1, label="같은 업종 최소 점포 수", show_value=True, debounce=True)
    get_code, set_code = mo.state(None)
    return get_code, gu_ui, industry_ui, min_ui, set_code, type_ui


@app.cell(hide_code=True)
def _(PAGES, gu_ui, industry_ui, min_ui, mo, nav, type_ui):
    mo.stop(nav.value != PAGES[0])
    mo.hstack([industry_ui, gu_ui, type_ui, min_ui], justify="start", align="end", gap=1.5, wrap=True)
    return


@app.cell(hide_code=True)
def _(bundle, get_code, gu_ui, industry_ui, min_ui, type_ui, v):
    scope = v.filter_scope(bundle, industry_ui.value, gu_ui.value, type_ui.value, min_ui.value)
    shown = v.visible_areas(bundle.areas, gu_ui.value, type_ui.value)
    summary = v.summarize(scope)
    industry = bundle.industries.set_index("industry_code").loc[industry_ui.value]
    selected_code = v.choose_code(get_code(), scope)
    return industry, scope, selected_code, shown, summary


@app.cell(hide_code=True)
def _(PAGES, bundle, industry, mo, nav, summary, v):
    mo.stop(nav.value != PAGES[0])
    _rules = bundle.meta["rules"]
    _notice = None
    if summary["areas"] == 0:
        _notice = mo.callout("조건에 맞는 상권이 없습니다. 자치구나 상권 유형을 넓히거나 최소 점포 수를 낮춰 보세요.", kind="warn")
    elif not industry["supported"]:
        _notice = mo.callout(f"**{industry['industry_name']}**은 서울시가 추정매출을 제공하지 않는 업종입니다. 매출이 낮다는 뜻이 아닙니다. 지도는 점포 수로 칠합니다.", kind="info")
    elif not summary["indexed"]:
        _notice = mo.callout(
            f"**{industry['industry_name']}**은 지수를 계산할 비교 상권이 부족합니다. 네 분기 매출이 있고 점포가 {_rules['min_stores']}개 이상인 상권이 서울 전체 또는 현재 조건에서 "
            f"{_rules['min_peers']}곳 기준에 못 미칩니다. 지도는 점포 수로 칠합니다.", kind="info")

    _value = lambda x, fmt, unit: "자료 없음" if x is None else f"{x:{fmt}}{unit}"
    _tiles = mo.hstack([
        mo.stat(f"{summary['areas']:,}곳", label="비교 상권", caption=f"지수를 낼 수 있는 곳 {summary['indexed']:,}곳", bordered=True),
        mo.stat(_value(summary["median_month"] and summary["median_month"] / 1e4, ",.0f", "만원"), label="점포당 월매출 중앙값", caption=f"매출이 있는 {summary['observed_areas']:,}곳 기준", bordered=True),
        mo.stat(_value(summary["coverage_pct"], ".0f", "%"), label="매출 근거가 있는 점포", caption="조건 안 점포 중 매출 칸의 비중", bordered=True),
        mo.stat(_value(summary["close_pct"], ".1f", "%"), label="연간 폐업률", caption=f"개업률 {_value(summary['open_pct'], '.1f', '%')}", bordered=True),
    ], widths="equal", gap=1)
    mo.vstack([_notice, _tiles] if _notice is not None else [_tiles], gap=0.8)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, mo, nav, pal, panel, scope, selected_code, shown, v):
    mo.stop(nav.value != PAGES[0] or scope.empty)
    map_ui = mo.ui.altair_chart(v.map_chart(bundle, scope, shown, selected_code, pal), chart_selection=False, legend_selection=False)
    _is_index = v.map_mode(scope) == "index"
    _map_note = ("파란색은 서울 같은 업종의 중앙값보다 점포당 매출이 높은 상권, 빨간색은 낮은 상권입니다. 회색은 매출이 없는 상권이고 0원이 아닙니다." if _is_index
                 else "진할수록 같은 업종 점포가 많습니다.") + " 상권을 클릭하면 아래 상세가 바뀝니다."
    _scatter = chart(v.competition_chart(scope, selected_code, pal))
    mo.hstack([
        panel("상권 지도", _map_note, map_ui),
        panel("경쟁과 매출", "오른쪽일수록 같은 업종 점포가 많고 위쪽일수록 점포당 매출이 높습니다. 점포가 많은 곳의 매출이 높아도 원인과 결과는 알 수 없습니다.",
              _scatter if _scatter is not None else "매출이 있는 상권이 없어 그릴 수 없습니다."),
    ], gap=1.5, align="start", wrap=True)
    return (map_ui,)


@app.cell(hide_code=True)
def _(map_ui, set_code, v):
    _picked = v.picked_code(map_ui.selections)
    if _picked is not None:
        set_code(_picked)
    return


@app.cell(hide_code=True)
def _(PAGES, mo, nav, panel, scope, v):
    mo.stop(nav.value != PAGES[0] or scope.empty)
    area_ui = mo.ui.table(
        v.area_table(scope), selection="single", page_size=8, hidden_columns=["trdar_code"], show_column_summaries=False, show_data_types=False,
        freeze_columns_left=["상권"], wrapped_columns=["근거"],
        header_tooltip={
            "업종 내 지수": "서울 같은 업종 중앙값 대비 배수. 네 분기 매출이 있고 점포 5개 이상인 상권만 계산합니다.",
            "보정 폐업률(%)": "점포가 적을수록 업종 평균 쪽으로 당긴 값입니다.",
            "상권 폐업비": "상권 전체에서 업종 구성으로 기대한 폐업 수 대비 실제 폐업 수입니다. 1보다 크면 기대보다 많습니다.",
            "폐업 신호": "상권 규모로 나눈 신뢰도입니다. 상·하반기 상관이 300개 이상 상권에서만 0.4 수준입니다.",
        })
    panel("상권 비교표", "업종 내 지수가 높은 순서입니다. 행을 고르면 아래 상세가 바뀝니다. 빈칸은 자료가 없다는 뜻입니다.", area_ui)
    return (area_ui,)


@app.cell(hide_code=True)
def _(area_ui, set_code):
    if len(area_ui.value):
        set_code(area_ui.value["trdar_code"].iloc[0])
    return


@app.cell(hide_code=True)
def _(PAGES, mo, nav, scope, selected_code, set_code):
    mo.stop(nav.value != PAGES[0] or scope.empty)
    _labels = {f"{r.trdar_name} · {r.gu_name}": r.trdar_code for r in scope.itertuples()}
    _current = next(k for k, c in _labels.items() if c == selected_code)
    area_pick = mo.ui.dropdown(_labels, value=_current, searchable=True, label="자세히 볼 상권", on_change=set_code)
    area_pick
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, industry, mo, nav, panel, pal, pd, scope, selected_code, v):
    mo.stop(nav.value != PAGES[0] or selected_code is None)
    _cell = scope.loc[scope["trdar_code"].eq(selected_code)].iloc[0]
    _area = bundle.areas.set_index("trdar_code").loc[selected_code]
    _quarters = v.quarter_rows(bundle, selected_code, industry.name)
    _money = "미공개" if pd.isna(_cell["sales_month"]) else f"{_cell['sales_month'] / 1e4:,.0f}만원"
    _index = "비교 불가" if pd.isna(_cell["sales_index"]) else f"{_cell['sales_index']:.2f}배"
    _median = "서울 중앙값 없음" if pd.isna(_cell["peer_median"]) else f"서울 중앙값 {_cell['peer_median'] / 1e4:,.0f}만원"
    _tiles = mo.hstack([
        mo.stat(f"{_cell['stores']:.1f}개", label="같은 업종 점포", caption=f"프랜차이즈 {_cell['franchise_pct']:.0f}%", bordered=True),
        mo.stat(_money, label="점포당 월매출", caption=_median, bordered=True),
        mo.stat(_index, label="업종 내 지수", caption=v.evidence_label(_cell), bordered=True),
        mo.stat(f"{_cell['close_pct_shrunk']:.1f}%", label="보정 폐업률", caption=f"폐업 {_cell['closes']:.0f}건, 업종 평균 {industry['close_pct']:.1f}%", bordered=True),
        mo.stat(f"{_area['close_ratio']:.2f}", label="상권 폐업비", caption=f"신호 {_area['close_signal']} · 상권 점포 {_area['all_stores']:,.0f}개", bordered=True),
    ], widths="equal", gap=1)
    _trend, _flow = chart(v.month_trend_chart(_quarters, pal)), chart(v.flow_chart(_quarters, pal))
    _time, _age = chart(v.profile_chart(_cell, industry, "time", pal)), chart(v.profile_chart(_cell, industry, "age", pal))
    _no_sales = "이 칸은 매출 자료가 없습니다."
    mo.vstack([
        mo.md(f"### {_cell['trdar_name']} · {_cell['industry_name']}\n{_cell['gu_name']} · {_cell['trdar_type']}"),
        _tiles,
        mo.hstack([
            panel("분기별 점포당 월매출", "1년치 네 점이라 계절성과 추세를 구분할 수 없습니다.", _trend if _trend is not None else _no_sales),
            panel("분기별 개업·폐업", "점포가 적은 칸은 한두 건에도 크게 흔들립니다.", _flow),
        ], gap=1.5, align="start", wrap=True),
        mo.hstack([
            panel("언제 쓰나", "시간대 구간 길이가 달라 시간당 효율로 읽으면 안 됩니다.", _time if _time is not None else _no_sales),
            panel("누가 쓰나", "성별·연령이 식별된 결제 기준입니다. 방문자 구성이 아닙니다.", _age if _age is not None else _no_sales),
        ], gap=1.5, align="start", wrap=True),
        panel("상권 수요", "인구는 종류마다 기준 시점이 달라 더하지 않습니다.", mo.ui.table(v.demand_table(_area, bundle.meta), selection=None, pagination=False, show_column_summaries=False, show_data_types=False, show_download=False, show_search=False)),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(mo, v):
    group_ui = mo.ui.multiselect(v.GROUPS, label="업종군 (비우면 전체)")
    metric_ui = mo.ui.dropdown(v.INDUSTRY_METRICS, value="연간 폐업률 (%)", label="순위 기준")
    return group_ui, metric_ui


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, group_ui, metric_ui, mo, nav, pal, panel, v):
    mo.stop(nav.value != PAGES[1])
    _d = v.filter_industries(bundle.industries, group_ui.value)
    _rank = chart(v.industry_rank_chart(_d, metric_ui.value, metric_ui.selected_key, pal))
    _, _outside = v.scatter_limit(_d)
    _outside_note = "".join(f" {r.industry_name}(개업률 {r.open_pct:.0f}%, 폐업률 {r.close_pct:.0f}%)은 축 끝에 붙여 그렸습니다." for r in _outside.itertuples())
    mo.vstack([
        mo.hstack([group_ui, metric_ui], justify="start", align="end", gap=1.5, wrap=True),
        mo.hstack([
            panel("개업률과 폐업률", "점 하나가 업종입니다. 대각선보다 위에 있으면 2025년에 폐업이 개업보다 많았습니다." + _outside_note, chart(v.industry_scatter(_d, pal))),
            panel(f"{metric_ui.selected_key} 상위 15개", "빈 값이 있는 업종은 빠집니다. 추정매출은 100개 중 62개 업종에만 있습니다.", _rank if _rank is not None else "표시할 값이 없습니다."),
        ], gap=1.5, align="start", wrap=True),
        panel("업종 표", "연간 비율은 네 분기 건수 합을 평균 점포 수로 나눈 값이며 폐업 확률이 아닙니다.",
              mo.ui.table(v.industry_table(_d), selection=None, page_size=10, show_column_summaries=False, show_data_types=False, freeze_columns_left=["업종"])),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, mo, nav, pal, panel, v):
    mo.stop(nav.value != PAGES[2])
    _m = bundle.meta
    _r = _m["rules"]
    _rows = {(x["단위"], x["구간"], x["지표"]): x["상관"] for x in _m["reliability"]}
    _guide = mo.md(f"""
    ### 숫자를 읽는 기준

    | 값 | 뜻 | 주의 |
    |:---|:---|:---|
    | 점포당 월매출 | 분기 추정매출 ÷ 점포 수 ÷ 3 | 카드사 자료 기반 추정치입니다. 개별 가게의 매출이나 이익이 아닙니다 |
    | 업종 내 지수 | 서울 같은 업종 중앙값 대비 배수 | 네 분기 매출이 있고 평균 점포 {_r['min_stores']}개 이상인 상권만 계산하고, 그런 상권이 {_r['min_peers']}곳 미만인 업종은 만들지 않습니다. 지역 필터로 기준이 바뀌지 않습니다 |
    | 보정 폐업률 | 작은 칸을 업종 평균 쪽으로 당긴 폐업률 | 점포가 약 {_m['pseudo_stores']:.0f}개쯤 되어야 칸 자체 값과 업종 평균을 반반 반영합니다 |
    | 상권 폐업비 | 업종 구성으로 기대한 폐업 수 대비 실제 폐업 수 | 1보다 크면 기대보다 많습니다. 폐업 신호 라벨로 신뢰도를 함께 봅니다 |

    **종합 점수는 일부러 만들지 않았습니다.** 가중치는 STEP 4에서 정할 일이고, 임대료·권리금·이익 자료가 없어 매출만으로 창업 적합성을 말할 수 없습니다.
    관광특구는 다른 상권과 겹쳐 이중 집계가 되므로 뺐습니다. 모든 관계는 상관이며 인과가 아닙니다.
    """)
    mo.vstack([
        _guide,
        mo.hstack([
            panel("매출 행은 점포 3개 이상인 칸에만 있습니다", "62개 업종 기준입니다. 경쟁 점포가 거의 없는 입지는 매출 근거가 없습니다.", chart(v.availability_chart(_m, pal))),
            panel("칸 단위 폐업률은 우연과 구별하기 어렵습니다", f"점포당 매출의 상·하반기 상관은 0.9를 넘지만 폐업률은 50개 이상 칸에서도 {_rows[('상권×업종 칸', '50개 이상', '폐업률')]:.2f}입니다.", chart(v.reliability_chart(_m, "상권×업종 칸", pal))),
            panel("상권 단위로 묶으면 나아집니다", f"점포 300개 이상 상권의 폐업률 상관은 {_rows[('상권 전체', '300개 이상', '폐업률')]:.2f}입니다. 그래서 작은 상권에는 신호가 약하다고 표시합니다.", chart(v.reliability_chart(_m, "상권 전체", pal))),
        ], gap=1.5, align="start", wrap=True),
        panel("'2025년' 값이 2025년에 바뀌지 않은 데이터가 있습니다", "상주·직장인구와 집객시설은 2025년 안에서 값이 그대로입니다. 분기 변수로 쓰지 말고 기준 시점을 함께 봐야 합니다.", chart(v.refresh_chart(_m, pal))),
    ], gap=1.4)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    <small>출처: 서울특별시, 서울시 상권분석서비스 / 소상공인시장진흥공단, 상가(상권)정보. 데이터 처리: 김지영 EDA, STEP 2·3 산출물.</small>
    """)
    return


if __name__ == "__main__":
    app.run()
