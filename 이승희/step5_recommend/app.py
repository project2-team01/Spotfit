import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="SpotFit 금융 MBTI 상권 추천 (2025)")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import pandas as pd

    import recommend as r

    PAGES = ["내 유형으로 상권 찾기", "유형 분포", "유형 기준과 한계"]
    return PAGES, mo, pd, r


@app.cell(hide_code=True)
def _(mo, r):
    try:
        bundle = r.load_bundle()
    except FileNotFoundError as _error:
        mo.stop(True, mo.callout(str(_error), kind="danger"))
    pal = r.v4.palette(mo.app_meta().theme)


    def panel(title, note, content):
        """제목과 읽는 법을 차트 위에 붙인다. 차트가 없으면 이유를 대신 보여 준다."""
        body = mo.callout(content, kind="neutral") if isinstance(content, str) or content is None else content
        return mo.vstack([mo.md(f"**{title}**<br><small>{note}</small>"), body], gap=0.4)


    def chart(spec):
        return mo.ui.altair_chart(spec, chart_selection=False, legend_selection=False) if spec is not None else None


    def plain(frame):
        return mo.ui.table(frame, selection=None, pagination=False, show_column_summaries=False, show_data_types=False,
                           show_download=False, show_search=False)
    return bundle, chart, pal, panel, plain


@app.cell(hide_code=True)
def _(bundle, mo):
    _c = bundle.meta["counts"]
    mo.md(f"""
    # SpotFit 금융 MBTI 상권 추천 (2025년)

    **나의 창업 성향(주 고객 · 가격대 · 상권 변화)**과 **희망 업종**을 고르면, 성향이 맞는 상권을 STEP 4 비교 점수 순서로 보여 줍니다.
    STEP 4 점수 대상 {_c['target_cells']:,}칸 중 세 축이 모두 판정된 칸 {_c['typed_cells']:,}칸 · 업종 {_c['typed_industries']}개.
    **유형과 점수는 창업 성공 가능성이나 수익을 뜻하지 않습니다.** 예산은 비용 자료(임대료·보증금 등)가 없어 판단하지 않습니다.
    """)
    return


@app.cell(hide_code=True)
def _(bundle, mo):
    mo.stop(not bundle.stale)
    mo.callout(mo.md("**유형표가 옛 입력으로 만들어졌습니다.** 만든 뒤에 바뀐 파일: " + ", ".join(f"`{p}`" for p in bundle.stale)
                     + "<br>팀 저장소 루트에서 `uv run --project \"이승희/step5_recommend\" python \"이승희/step5_recommend/build_types.py\"`를 실행한 뒤 다시 여세요."),
               kind="danger")
    return


@app.cell(hide_code=True)
def _(PAGES, mo):
    nav = mo.ui.tabs({name: "" for name in PAGES})
    nav
    return (nav,)


@app.cell(hide_code=True)
def _(bundle, mo, r):
    _ind = bundle.industries.loc[bundle.industries["점수_대상_칸"].gt(0)].sort_values("업종명")
    industry_ui = mo.ui.dropdown(dict(zip(_ind["업종명"], _ind["업종_코드"])), value="커피-음료", searchable=True, label="희망 업종")
    _opt = lambda ax: {r.ANY: "", **{f"{k} {name}": k for k, name in r.AXES[ax].items()}}
    lv_ui = mo.ui.radio(_opt("LV"), value=r.ANY, label="**주 고객** (L 생활형 / V 방문형)", inline=True)
    ep_ui = mo.ui.radio(_opt("EP"), value=r.ANY, label="**가격대** (E 실속형 / P 프리미엄형)", inline=True)
    sd_ui = mo.ui.radio(_opt("SD"), value=r.ANY, label="**상권 변화** (S 안정형 / D 역동형)", inline=True)
    gu_ui = mo.ui.multiselect(sorted(bundle.cells["gu_name"].dropna().unique()), label="자치구 (비우면 전체)")
    _w = r.bs.DEFAULT_WEIGHTS
    w_sales = mo.ui.slider(0, 50, step=5, value=_w["sales"], label="매출 잠재력", show_value=True, debounce=True)
    w_comp = mo.ui.slider(0, 50, step=5, value=_w["comp"], label="경쟁", show_value=True, debounce=True)
    w_stab = mo.ui.slider(0, 50, step=5, value=_w["stab"], label="안정성", show_value=True, debounce=True)
    w_dem = mo.ui.slider(0, 50, step=5, value=_w["dem"], label="수요", show_value=True, debounce=True)
    return ep_ui, gu_ui, industry_ui, lv_ui, sd_ui, w_comp, w_dem, w_sales, w_stab


@app.cell(hide_code=True)
def _(PAGES, ep_ui, gu_ui, industry_ui, lv_ui, mo, nav, sd_ui, w_comp, w_dem, w_sales, w_stab):
    mo.stop(nav.value == PAGES[2])
    if nav.value == PAGES[1]:  # 유형 분포 탭은 업종과 유형만 쓴다. 자치구·가중치는 첫 탭에만 적용된다
        _out = mo.vstack([industry_ui, lv_ui, ep_ui, sd_ui], gap=0.6)
    else:
        _out = mo.vstack([
            mo.hstack([industry_ui, gu_ui], justify="start", align="end", gap=1.5, wrap=True),
            lv_ui, ep_ui, sd_ui,
            mo.accordion({"점수 가중치 바꾸기 (선택)": mo.vstack([
                mo.hstack([w_sales, w_comp, w_stab, w_dem], justify="start", gap=1.5, wrap=True),
                mo.md("<small>기본값(매출 30 · 경쟁 25 · 안정성 15 · 수요 30)은 STEP 4와 같은 <b>가정</b>입니다. "
                      "유형별로 다른 가중치는 근거가 없어 만들지 않았습니다(팀 결정 필요).</small>")])}),
        ], gap=0.6)
    _out
    return


@app.cell(hide_code=True)
def _(bundle, ep_ui, gu_ui, industry_ui, lv_ui, r, sd_ui, w_comp, w_dem, w_sales, w_stab):
    choice = r.check_choice({"LV": lv_ui.value, "EP": ep_ui.value, "SD": sd_ui.value})
    weights = {"sales": w_sales.value, "comp": w_comp.value, "stab": w_stab.value, "dem": w_dem.value}
    industry = r.industry_row(bundle, industry_ui.value)
    seoul = r.seoul_scope(bundle, industry_ui.value, choice, weights)
    picks = r.recommend(bundle, industry_ui.value, choice, gu_ui.value, weights)
    steps = r.funnel(bundle, industry_ui.value, choice, gu_ui.value)
    return choice, industry, picks, seoul, steps, weights


@app.cell(hide_code=True)
def _(PAGES, choice, industry, mo, nav, picks, r, seoul, steps, weights):
    mo.stop(nav.value != PAGES[0])
    _notes = []
    if sum(weights.values()) == 0:
        _notes.append(mo.callout("가중치가 모두 0입니다. 하나 이상 올려 주세요.", kind="warn"))
    if industry["EP_판정_칸"] == 0 and choice["EP"]:
        _notes.append(mo.callout(mo.md(f"**{industry['업종명']}**은 {industry['판정_불가_사유']}이라 가격대(E/P)를 고르면 결과가 없습니다. "
                                       f"가격대를 **{r.ANY}**으로 두세요."), kind="info"))
    if picks.empty:
        _notes.append(mo.callout(mo.md("**조건에 맞는 상권이 없습니다.** 아래 '조건별로 남은 상권'에서 어느 조건에서 0이 됐는지 확인하고, "
                                       f"그 축을 **{r.ANY}**으로 바꾸거나 자치구를 넓혀 보세요. 다른 유형으로 자동으로 채우지 않습니다."), kind="warn"))
    _tiles = mo.hstack([
        mo.stat(f"{len(seoul):,}곳", label="STEP 4 점수 대상", caption=f"{industry['업종명']} · 서울 전체", bordered=True),
        mo.stat(f"{int(industry['유형_판정_칸']):,}곳", label="세 축 모두 판정", caption="나머지는 일부 축 보류", bordered=True),
        mo.stat(f"{len(picks):,}곳", label="내 조건과 일치", caption=r.choice_name(choice), bordered=True),
    ], widths="equal", gap=1)
    _funnel = " → ".join(f"{name} **{n:,}**" for name, n in steps)
    mo.hstack([
        mo.md(r.type_card(choice)),
        mo.vstack([*_notes, _tiles, mo.md(f"<small>조건별로 남은 상권: {_funnel}</small>")], gap=0.6),
    ], widths=[1, 1.4], gap=2, align="start", wrap=True)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, mo, nav, pal, panel, picks, r, seoul):
    mo.stop(nav.value != PAGES[0] or picks.empty)
    _fig = r.map_figure(bundle, picks, seoul, None, pal, view_key=str(picks["industry_code"].iloc[0]))
    panel("조건에 맞는 상권 지도",
          f"내 조건과 일치하는 상권만 칠했습니다. 진할수록 종합 점수가 높고, 검은 번호는 상위 {r.v4.TOP_N}곳입니다. "
          "마우스를 올리면 서울 같은 업종(유형 무관) 안의 순위가 나옵니다. 배경 지도는 인터넷 연결이 필요합니다.",
          mo.Html(mo.as_html(_fig).text) if _fig is not None else "지도에 그릴 상권이 없습니다.")
    return


@app.cell(hide_code=True)
def _(PAGES, mo, nav, panel, picks, r):
    mo.stop(nav.value != PAGES[0] or picks.empty)
    _table = mo.ui.table(
        r.result_table(picks), selection=None, page_size=10, hidden_columns=["trdar_code"], show_column_summaries=False,
        show_data_types=False, freeze_columns_left=["상권"],
        header_tooltip={
            "종합 점수": "STEP 4 종합 점수(0~100). 수요는 고른 주 고객(L 주민 / V 유동인구)으로 자동 연결됩니다.",
            "서울 순위": "서울 같은 업종 점수 대상 상권(유형 무관) 안의 순위입니다.",
            "주민 비중": "주민 ÷ (주민 + 직장인). 0.55 초과 L, 0.45 미만 V.",
            "건당 금액 백분위": "같은 업종 안 결제 1건당 금액의 위치. 45 미만 E, 55 초과 P.",
            "상권변화지표": "서울시 2025년 4분기. 정체 → S, 다이나믹 → D, 상권확장·상권축소 → 중간.",
            "영업 중 가게 평균 개월": "지금 영업 중인 가게들의 평균 영업 기간. 서울 평균 115개월.",
            "문 닫은 가게 평균 개월": "문을 닫은 가게들이 닫기까지 영업한 평균 기간. 서울 평균 53개월.",
        })
    panel("추천 상권 표", "종합 점수가 높은 순서입니다. 빈칸은 자료가 없다는 뜻이고 0점이 아닙니다. "
          "오른쪽 칸들은 유형을 판정한 근거 값입니다.", _table)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, chart, choice, industry, industry_ui, mo, nav, pal, panel, plain, r):
    mo.stop(nav.value != PAGES[1])
    _t = r.type_counts(bundle, industry_ui.value)
    _code = r.choice_code(choice)
    mo.vstack([
        mo.hstack([
            panel(f"{industry['업종명']}: 8유형별 상권 수", f"STEP 4 점수 대상 상권 중 세 축이 모두 판정된 곳입니다. 지금 고른 유형({_code})이 완성된 유형이면 진하게 표시합니다.",
                  chart(r.type_bar(_t, _code, pal))),
            panel(f"{industry['업종명']}: 축별 판정과 보류", "회색 '보류'는 판정 경계에 있거나 자료가 부족한 상권입니다. 보류가 많은 축은 '상관없음'으로 두면 결과가 늘어납니다.",
                  chart(r.hold_bar(r.hold_counts(bundle, industry_ui.value), pal))),
        ], widths="equal", gap=2, align="start", wrap=True),
        mo.hstack([
            panel("서울 상권 1,644곳의 상권변화지표 (2025년 4분기)", "관광특구 제외. 정체는 S 안정형, 다이나믹은 D 역동형이고 상권확장·상권축소는 '중간'으로 보류합니다.",
                  chart(r.area_sd_chart(bundle.areas, pal))),
            panel("8유형 정의", "S/D 이름은 박성은 제안(팀 확정 전)입니다. 아이템은 설명용 예시이고 데이터로 검증하지 않았습니다.",
                  plain(bundle.types)),
        ], widths="equal", gap=2, align="start", wrap=True),
        panel("업종별 유형 판정 가능 여부 (100개 업종)", "점수 대상이 없거나 매출 자료가 부족한 업종은 유형을 만들 수 없습니다.",
              mo.ui.table(bundle.industries, selection=None, page_size=10, show_column_summaries=False, show_data_types=False, freeze_columns_left=["업종명"])),
    ], gap=1.2)
    return


@app.cell(hide_code=True)
def _(PAGES, bundle, mo, nav):
    mo.stop(nav.value != PAGES[2])
    _o = bundle.meta["sd_stability_overlap"]
    _a = bundle.meta["area_counts"]
    mo.md(f"""
    ## 세 축을 만든 방법

    | 축 | 쓰는 값 | 판정 | 단위 |
    | :--- | :--- | :--- | :--- |
    | **주 고객** L 생활형 / V 방문형 [가정] | 주민 ÷ (주민 + 직장인) | 0.55 초과 L, 0.45 미만 V, 그 사이 보류 | 상권 |
    | **가격대** E 실속형 / P 프리미엄형 [가정] | 결제 1건당 금액(연간 추정매출 ÷ 건수)의 같은 업종 안 백분위 | 45 미만 E, 55 초과 P, 그 사이 보류 | 상권×업종 |
    | **상권 변화** S 안정형 / D 역동형 | 서울시 상권변화지표 2025년 4분기 | 정체 → S, 다이나믹 → D, 상권확장·상권축소 → 중간(보류) | 상권 |

    - **S/D는 'G 성장형' 대신 새로 정한 축입니다.** 성장을 보려면 작년 자료와 비교해야 하지만, 변화가 많은지 적은지는 2025년 자료로도 판단할 수 있습니다.
      상권변화지표는 2025년에 잰 값이지만 가게들이 여러 해 동안 영업한 기간(영업 중 가게 평균, 문 닫은 가게 평균)을 서울 평균과 비교한 결과입니다.
    - **정체**는 두 값이 모두 서울 평균보다 길고(오래 버팀), **다이나믹**은 둘 다 평균보다 짧습니다(자주 바뀜). 상권확장·상권축소는 둘 중 하나만 길어 '중간'으로 둡니다.
      이름과 달리 시간에 따라 커지거나 줄어든다는 뜻이 아닙니다.
    - 서울 상권 {_a['areas']:,}곳 중 S {_a['SD'].get('S', 0)}곳, D {_a['SD'].get('D', 0)}곳, 중간 {_a['SD'].get('중간(보류)', 0)}곳입니다.
      4개 분기 내내 같은 지표를 유지한 상권은 {_a['chg_same_all_year']:,}곳({_a['chg_same_all_year'] / _a['areas']:.1%})입니다.
    - L/V·E/P 경계값(0.45/0.55, 45/55)은 박성은 STEP 5와 같은 운영 가정이고 검증된 값이 아닙니다.

    ## 추천 순서를 정하는 방법

    1. 희망 업종의 STEP 4 점수 대상 상권에서 고른 축이 일치하는 곳만 남깁니다. 보류된 칸은 그 축을 고르면 빠지고, 다른 유형으로 채우지 않습니다.
    2. STEP 4 종합 점수로 줄을 세웁니다. 유형에 따라 바뀌는 것은 **수요의 주 고객층** 하나입니다(L → 주민 중심, V → 유동인구 중심, 상관없음 → 세 값 평균).
    3. **E/P와 S/D는 거르는 데만 쓰고 점수에 다시 더하지 않습니다.** 같은 정보를 두 번 반영하지 않기 위해서입니다.

    ## S/D와 안정성 점수는 얼마나 겹치나

    안정성 점수(보정 폐업률)와 S/D가 같은 내용을 재면, S/D로 거른 뒤 안정성으로 또 점수를 매기는 셈입니다. 그래서 직접 확인했습니다.

    | 확인 | 값 |
    | :--- | ---: |
    | S 안정형 상권의 안정성 점수 중앙값 | {_o['S_안정성_중앙값']:.1f} |
    | D 역동형 상권의 안정성 점수 중앙값 | {_o['D_안정성_중앙값']:.1f} |
    | D 여부와 안정성 점수의 Spearman 상관 (전체) | {_o['D여부_안정성_spearman_전체']:+.3f} |
    | 같은 상관의 업종별 중앙값 ({_o['업종별_계산_업종_수']}개 업종) | {_o['D여부_안정성_spearman_업종별_중앙값']:+.3f} |

    D 상권의 안정성 점수가 조금 낮지만 상관은 **약합니다**(0에 가까움). 두 값은 서로 다른 것을 잽니다. 상권변화지표는 여러 해의 영업 기간이고, 안정성은 2025년 한 해의 폐업률입니다.
    그래서 S/D 필터와 안정성 점수를 함께 써도 큰 이중 반영은 아니라고 보았습니다(팀 확인 필요). 상관은 관계일 뿐 인과가 아닙니다.

    ## 이 추천으로 말할 수 없는 것

    - **사용자의 금융 성향을 측정하지 않습니다.** 사용자가 세 축을 직접 고르는 방식입니다. 설문 문항은 팀이 따로 만들 예정입니다.
    - **역동형이 유망하거나 성장한다는 뜻이 아닙니다.** 가게가 자주 바뀌는 상권입니다.
    - **L/V는 실제 손님의 출처가 아닙니다.** 주민·직장인 수의 비율이고, 두 인구는 겹칠 수 있습니다. 관광객·외부 방문객은 반영하지 못합니다.
    - **E/P는 실제 가격대나 브랜드가 아닙니다.** 결제 1건당 금액의 상대 위치입니다.
    - **예산 적합성은 판단하지 않습니다.** 임대료·보증금·권리금·시설비 자료가 없습니다(팀 결정 7.10).
    - 추천이 맞았는지 확인할 정답 자료(실제 창업 성과·만족도)는 없습니다.
    """)
    return


if __name__ == "__main__":
    app.run()
