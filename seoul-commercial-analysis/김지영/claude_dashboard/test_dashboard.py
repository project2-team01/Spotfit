"""대시보드 데이터와 조회·차트 함수를 검증한다.

실행: .venv/bin/python 김지영/claude_dashboard/test_dashboard.py
"""
from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import views as v

HERE = Path(__file__).resolve().parent
bundle = v.load_bundle(HERE)
code_of = bundle.industries.set_index("industry_name")["industry_code"]
PAL = v.palette("light")
COFFEE, LAWYER, REALTY = code_of["커피-음료"], code_of["변호사사무소"], code_of["부동산중개업"]


def test_reproduces_eda_totals():
    t = bundle.meta["totals"]
    assert t["areas"] == 1644 and len(bundle.geometry) == 1644
    assert round(t["sales"] / 1e12, 1) == 87.0
    assert (t["opens"], t["closes"], t["stores_q4"]) == (38194, 49596, 481196)
    assert round(bundle.meta["alpha"], 2) == 13.19
    assert (bundle.cells["sales_status"] == "네 분기").sum() == 19863
    c = bundle.cells
    assert round(c["closes"].sum() / c["stores"].sum() * 100, 1) == 10.1
    assert round(c["opens"].sum() / c["stores"].sum() * 100, 1) == 7.9


def test_reliability_matches_eda():
    r = {(x["구간"], x["지표"]): round(x["상관"], 2) for x in bundle.meta["reliability"]}
    assert r[("3~9개", "폐업률")] == 0.01 and r[("50개 이상", "폐업률")] == 0.26
    assert r[("3~9개", "점포당 매출")] == 0.93 and r[("50개 이상", "점포당 매출")] == 0.95
    assert r[("300개 이상", "폐업률")] == 0.42 and r[("100~299개", "폐업률")] == 0.19


def test_missing_sales_stay_missing():
    c = bundle.cells
    hidden = c["sales_status"].isin(["미공개", "미제공 업종"])
    assert c.loc[hidden, "sales_month"].isna().all() and c.loc[hidden, "sales_index"].isna().all()
    assert not (c["sales_month"] == 0).any()
    table = v.area_table(v.filter_scope(bundle, COFFEE, min_stores=1))
    assert table["점포당 월매출(만원)"].isna().any()
    assert (table.loc[table["점포당 월매출(만원)"].isna(), "근거"].str.contains("미공개|일부")).all()


def test_index_rule_is_fixed_for_all_filters():
    """지역 필터를 바꿔도 지수의 기준(서울 전체)은 그대로여야 한다."""
    whole = v.filter_scope(bundle, COFFEE).set_index("trdar_code")["sales_index"]
    gangnam = v.filter_scope(bundle, COFFEE, gus=["강남구"]).set_index("trdar_code")["sales_index"]
    assert len(gangnam) and gangnam.equals(whole.reindex(gangnam.index))
    c = bundle.cells.dropna(subset=["sales_index"])
    assert (c["stores"] >= bundle.meta["rules"]["min_stores"]).all() and (c["sales_status"] == "네 분기").all()
    assert abs(c.loc[c["industry_code"].eq(COFFEE), "sales_index"].median() - 1) < 1e-9


def test_filters():
    scope = v.filter_scope(bundle, COFFEE, gus=["마포구"], types=["발달상권"], min_stores=10)
    assert len(scope) and set(scope["gu_name"]) == {"마포구"} and set(scope["trdar_type"]) == {"발달상권"} and (scope["stores"] >= 10).all()
    assert "관광특구" not in set(bundle.areas["trdar_type"])
    ranked = v.filter_scope(bundle, COFFEE)["sales_index"].dropna()
    assert ranked.is_monotonic_decreasing


def test_empty_result_is_safe():
    scope = v.filter_scope(bundle, COFFEE, gus=["도봉구"], types=["전통시장"], min_stores=30)
    assert scope.empty
    s = v.summarize(scope)
    assert s["areas"] == 0 and s["median_month"] is None and s["close_pct"] is None
    assert v.choose_code("3120207", scope) is None
    assert v.competition_chart(scope, None, PAL) is None


def test_unsupported_and_thin_industries():
    for code in (LAWYER, REALTY):
        scope = v.filter_scope(bundle, code)
        assert len(scope) and v.map_mode(scope) == "stores" and scope["sales_index"].isna().all()
        v.map_chart(bundle, scope, bundle.areas, scope["trdar_code"].iloc[0], PAL).to_dict()
    lawyer = v.filter_scope(bundle, LAWYER)
    assert v.competition_chart(lawyer, None, PAL) is None
    assert lawyer["sales_status"].eq("미제공 업종").all()
    row = lawyer.iloc[0]
    industry = bundle.industries.set_index("industry_code").loc[LAWYER]
    assert v.profile_chart(row, industry, "time", PAL) is None
    assert v.month_trend_chart(v.quarter_rows(bundle, row["trdar_code"], LAWYER), PAL) is None


def test_selection_helpers():
    assert v.picked_code({}) is None
    assert v.picked_code({"pick": {}}) is None
    assert v.picked_code({"pick": {"trdar_code": ["3120207"], "vlPoint": {}}}) == "3120207"
    scope = v.filter_scope(bundle, COFFEE)
    assert v.choose_code(None, scope) == scope["trdar_code"].iloc[0]
    assert v.choose_code("없는코드", scope) == scope["trdar_code"].iloc[0]
    assert v.choose_code(scope["trdar_code"].iloc[3], scope) == scope["trdar_code"].iloc[3]


def test_map_has_no_nan_and_marks_missing_as_null():
    scope = v.filter_scope(bundle, COFFEE, min_stores=1)
    spec = v.map_chart(bundle, scope, bundle.areas, scope["trdar_code"].iloc[0], PAL).to_dict()
    text = json.dumps(spec, ensure_ascii=False, allow_nan=False)
    assert "미공개" in text
    rows = next(layer["data"]["values"] for layer in spec["layer"] if "trdar_code" in (layer.get("data", {}).get("values") or [{}])[0])
    assert len(rows) == len(scope)
    assert any(r["value"] is None for r in rows) and all(r["value"] is None or math.isfinite(r["value"]) for r in rows)


def test_every_chart_builds_in_both_themes():
    scope = v.filter_scope(bundle, COFFEE)
    code = scope["trdar_code"].iloc[0]
    row = scope.iloc[0]
    industry = bundle.industries.set_index("industry_code").loc[COFFEE]
    quarters = v.quarter_rows(bundle, code, COFFEE)
    assert len(quarters) == 4
    d = v.filter_industries(bundle.industries)
    for theme in ("light", "dark"):
        pal = v.palette(theme)
        for chart in [
            v.competition_chart(scope, code, pal), v.month_trend_chart(quarters, pal), v.flow_chart(quarters, pal),
            v.profile_chart(row, industry, "time", pal), v.profile_chart(row, industry, "age", pal), v.industry_scatter(d, pal),
            v.industry_rank_chart(d, "close_pct", "폐업률", pal), v.refresh_chart(bundle.meta, pal), v.availability_chart(bundle.meta, pal),
            v.reliability_chart(bundle.meta, "상권×업종 칸", pal), v.reliability_chart(bundle.meta, "상권 전체", pal),
        ]:
            assert chart.to_dict()


def test_demand_table_shows_real_vintage():
    area = bundle.areas.iloc[0]
    t = v.demand_table(area, bundle.meta).set_index("지표")["기준"]
    assert "2024Q4" in t["직장인구"] and "2023Q4" in t["상주인구"] and "변경 없음" in t["집객시설"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and inspect.isfunction(f)]
    for name, func in tests:
        func()
        print(f"통과  {name}")
    print(f"\n{len(tests)}개 테스트 통과")
