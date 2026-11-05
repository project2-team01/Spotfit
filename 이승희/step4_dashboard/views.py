# -*- coding: utf-8 -*-
"""STEP 4 대시보드의 데이터 조회와 차트. marimo 없이 테스트할 수 있다.

색·스타일·지도 그리는 방식은 김지영/claude_dashboard/views.py 에서 복사해 고쳤다.
(출처: 김지영/claude_dashboard/views.py 의 LIGHT·DARK·styled·records·map_chart)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd

from build_scores import AREA_LABELS, DEFAULT_WEIGHTS, DEMAND_MODES, composite

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STAGE4 = HERE / "data"
JY_DATA = REPO / "김지영" / "claude_dashboard" / "data"

TYPES = ["골목상권", "발달상권", "전통시장"]
QUARTER_LABELS = {"20251": "1분기", "20252": "2분기", "20253": "3분기", "20254": "4분기"}
AREA_KEYS = ["sales", "comp", "stab", "dem"]
FONT = 'system-ui, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif'

# 출처: 김지영/claude_dashboard/views.py (dataviz 기준 팔레트)
LIGHT = {
    "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb",
    "neutral": "#f0efec", "out": "#e8e7e1", "missing": "#a8a69f", "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
    "blues": ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
}
DARK = {
    "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835", "surface": "#1a1a19",
    "neutral": "#383835", "out": "#2c2c2a", "missing": "#6b6a64", "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70",
    "blues": ["#184f95", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"],
}


def palette(theme: str | None) -> dict:
    return DARK if theme == "dark" else LIGHT


def styled(chart, pal: dict):
    return (
        chart.configure(background="transparent", font=FONT)
        .configure_view(stroke=None)
        .configure_axis(domainColor=pal["axis"], gridColor=pal["grid"], tickColor=pal["axis"], labelColor=pal["ink2"], titleColor=pal["ink2"],
                        labelFontSize=11, titleFontSize=11, titleFontWeight="normal", gridWidth=1, domainWidth=1, tickSize=0, labelPadding=6)
        .configure_legend(labelColor=pal["ink2"], titleColor=pal["ink2"], labelFontSize=11, titleFontSize=11, titleFontWeight="normal",
                          orient="top", symbolType="circle", gradientLength=180, gradientThickness=8)
        .configure_title(color=pal["ink"], subtitleColor=pal["ink2"], fontSize=13, subtitleFontSize=11, fontWeight=600, anchor="start", offset=10)
    )


def records(frame: pd.DataFrame) -> list[dict]:
    """결측을 JSON null로 바꾼다. NaN은 Vega에서 0처럼 보일 수 있다."""
    return json.loads(frame.to_json(orient="records", force_ascii=False))


@dataclass(frozen=True)
class Bundle:
    scores: pd.DataFrame
    industries: pd.DataFrame
    design: pd.DataFrame
    meta: dict
    jy_meta: dict
    quarters: pd.DataFrame
    backdrop: pd.DataFrame
    geometry: tuple
    points: pd.DataFrame


def load_bundle() -> Bundle:
    need = [STAGE4 / "상권_업종_비교점수_2025.parquet", STAGE4 / "업종별_점수_가능여부.csv", STAGE4 / "점수_설계표.csv",
            STAGE4 / "stage4_meta.json", JY_DATA / "meta.json", JY_DATA / "quarters.parquet", JY_DATA / "backdrop.parquet",
            JY_DATA / "areas.geojson.json"]
    missing = [p.relative_to(REPO).as_posix() for p in need if not p.exists()]
    if missing:
        raise FileNotFoundError("대시보드 데이터가 없습니다: " + ", ".join(missing)
                                + ". 팀 저장소 main을 최신으로 받고 build_scores.py를 먼저 실행하세요.")
    geometry = tuple(json.loads((JY_DATA / "areas.geojson.json").read_text(encoding="utf-8")))
    return Bundle(
        scores=pd.read_parquet(need[0]),
        industries=pd.read_csv(need[1], dtype={"업종_코드": str}, encoding="utf-8-sig"),
        design=pd.read_csv(need[2], encoding="utf-8-sig"),
        meta=json.loads(need[3].read_text(encoding="utf-8")),
        jy_meta=json.loads(need[4].read_text(encoding="utf-8")),
        quarters=pd.read_parquet(need[5]),
        backdrop=pd.read_parquet(need[6]),
        geometry=geometry,
        points=pd.DataFrame([{k: f[k] for k in ("trdar_code", "lon", "lat")} for f in geometry]),
    )


# ---------------------------------------------------------------- 조회


def normalize_weights(weights: dict) -> dict:
    return {k: float(weights.get(k, 0) or 0) for k in AREA_KEYS}


def industry_info(bundle: Bundle, industry_code: str) -> pd.Series:
    return bundle.industries.set_index("업종_코드").loc[industry_code]


def filter_scope(bundle: Bundle, industry_code: str, gus=None, types=None, weights=None, demand_mode="avg") -> pd.DataFrame:
    """고른 업종의 모든 상권 칸. 점수는 서울 전체 같은 업종 기준이라 지역 필터로 다시 계산하지 않는다."""
    d = bundle.scores.loc[bundle.scores["industry_code"].eq(industry_code)].copy()
    if gus:
        d = d.loc[d["gu_name"].isin(list(gus))]
    if types:
        d = d.loc[d["trdar_type"].isin(list(types))]
    d["score_dem"] = d[f"score_dem_{demand_mode}"]
    d["score_total"], d["n_areas"] = composite(d, normalize_weights(weights or DEFAULT_WEIGHTS), demand_mode)
    return d.sort_values(["score_total", "stores"], ascending=[False, False], na_position="last").reset_index(drop=True)


def summarize(scope: pd.DataFrame) -> dict:
    status = scope["score_status"].value_counts()
    return {
        "areas": int(len(scope)),
        "scored": int(scope["score_total"].notna().sum()),
        "small": int(status.get("평균 점포 5개 미만 (참고용)", 0)),
        "few_peers": int(status.get("업종 비교 상권 30곳 미만", 0)),
        "with_sales": int(scope["score_sales"].notna().sum()),
    }


def top_change(scope: pd.DataFrame, weights: dict, demand_mode: str = "avg", k: int = 10) -> dict | None:
    """경쟁 영역을 뺐을 때 상위 k개 상권이 몇 곳 바뀌는지. 경쟁·수요 겹침의 영향을 보는 칸."""
    d = scope.loc[scope["score_total"].notna()]
    if len(d) < k:
        return None
    w = normalize_weights(weights)
    no_comp = dict(w, comp=0.0)
    if sum(no_comp.values()) == 0:
        return None
    alt_total, _ = composite(d, no_comp, demand_mode)
    now = set(d.nlargest(k, "score_total")["trdar_code"])
    other = set(d.assign(t=alt_total).nlargest(k, "t")["trdar_code"])
    return {"k": k, "changed": len(now - other), "kept": len(now & other)}


def score_table(scope: pd.DataFrame) -> pd.DataFrame:
    """상권 비교표. 자료가 없는 칸은 빈칸으로 둔다."""
    d = scope
    r = lambda s: s.round(0)
    return pd.DataFrame({
        "trdar_code": d["trdar_code"],
        "상권": d["trdar_name"], "자치구": d["gu_name"], "유형": d["trdar_type"],
        "종합 점수": r(d["score_total"]), "계산 영역 수": d["n_areas"],
        "매출 잠재력": r(d["score_sales"]), "경쟁": r(d["score_comp"]), "안정성(신뢰도 낮음)": r(d["score_stab"]), "수요": r(d["score_dem"]),
        "평균 점포 수": d["stores"].round(1), "점수 상태": d["score_status"], "매출 영역": d["sales_area_status"],
    })


def choose_code(current: str | None, scope: pd.DataFrame) -> str | None:
    codes = list(scope["trdar_code"])
    if current in codes:
        return current
    scored = scope.loc[scope["score_total"].notna(), "trdar_code"]
    return scored.iloc[0] if len(scored) else (codes[0] if codes else None)


def picked_code(selections: dict) -> str | None:
    codes = (selections or {}).get("pick", {}).get("trdar_code") or []
    return str(codes[0]) if codes else None


def fmt_money(v) -> str:
    return "자료 없음" if pd.isna(v) else f"{v / 1e4:,.0f}만 원"


def fmt_num(v, digits=1, unit="") -> str:
    return "자료 없음" if pd.isna(v) else f"{v:,.{digits}f}{unit}"


def raw_compare(row: pd.Series, industry_scope: pd.DataFrame) -> pd.DataFrame:
    """영역별 원값과 서울 같은 업종(점수 대상 칸) 중앙값."""
    t = industry_scope.loc[industry_scope["score_status"].eq("점수 대상")]
    med = lambda c: t[c].median() if len(t) else np.nan
    rows = [
        ("매출 잠재력", "점포당 월매출", fmt_money(row["sales_month"]), fmt_money(med("sales_month")), row["sales_area_status"]),
        ("경쟁", "유동인구 1,000명당 같은 업종 점포", fmt_num(row["comp_ratio"], 3, "개"), fmt_num(med("comp_ratio"), 3, "개"), "낮을수록 높은 점수"),
        ("안정성", "보정 폐업률 (연간)", fmt_num(row["close_pct_shrunk"], 1, "%"), fmt_num(med("close_pct_shrunk"), 1, "%"),
         f"실제 폐업 {row['closes']:.0f}건 · 1년치라 신뢰도 낮음"),
        ("수요", "면적당 유동인구 (㎢당)", fmt_num(row["floating_density"], 0, "명"), fmt_num(med("floating_density"), 0, "명"), "2025년 분기 평균"),
        ("수요", "면적당 직장인구 (㎢당)", fmt_num(row["worker_density"], 0, "명"), fmt_num(med("worker_density"), 0, "명"), "2025년 안에서 값 변화 없음"),
        ("수요", "면적당 상주인구 (㎢당)", fmt_num(row["resident_density"], 0, "명"), fmt_num(med("resident_density"), 0, "명"), "2025년 안에서 값 변화 없음"),
    ]
    return pd.DataFrame(rows, columns=["영역", "지표", "이 상권", "서울 같은 업종 중앙값", "참고"])


def quarter_rows(bundle: Bundle, code: str, industry_code: str) -> pd.DataFrame:
    """분기별 점포당 월매출·개폐업과 직전 분기 대비 매출 증감률(윈저화, 참고용)."""
    q = bundle.quarters
    d = q.loc[q["trdar_code"].eq(code) & q["industry_code"].eq(industry_code)]
    d = pd.DataFrame({"quarter": list(QUARTER_LABELS)}).merge(d, on="quarter", how="left")
    d["분기"] = d["quarter"].map(QUARTER_LABELS)
    d["sales_month"] = d["sales_amount"] / d["store_count"].where(d["store_count"].gt(0)) / 3
    prev = d["sales_amount"].shift(1)
    raw = (d["sales_amount"] / prev.where(prev > 0) - 1) * 100
    w = bundle.meta["qoq_winsor"]
    d["qoq_raw"] = raw
    d["qoq_winsor"] = raw.clip(w["p5"], w["p95"])
    d[["open_count", "close_count"]] = d[["open_count", "close_count"]].fillna(0)
    return d


def vintage_text(jy_meta: dict, dataset: str) -> str:
    last = next(i for i in jy_meta["freshness"] if i["dataset"] == dataset)["last_observed_value_change"]
    return "2021Q1 이후 값 변경 없음" if last is None else f"값이 마지막으로 바뀐 분기 {last[:4]}Q{last[4]}"


# ---------------------------------------------------------------- 차트


def map_chart(bundle: Bundle, scope: pd.DataFrame, selected: str | None, pal: dict, height: int = 520, width: int = 640):
    """상권 경계를 종합 점수로 칠한다. 점수가 없는 상권은 회색. 출처: 김지영/claude_dashboard/views.py map_chart를 고침."""
    pts = bundle.points.set_index("trdar_code")
    in_scope = scope.set_index("trdar_code")
    rows = []
    for f in bundle.geometry:
        code = f["trdar_code"]
        if code not in in_scope.index:
            continue
        r = in_scope.loc[code]
        total = r["score_total"]
        rows.append({
            "trdar_code": code, "geometry": f["geometry"], "name": r["trdar_name"], "gu": r["gu_name"], "kind": r["trdar_type"],
            "value": None if pd.isna(total) else round(float(total), 1),
            "label": "점수 없음 · " + r["score_status"] if pd.isna(total) else f"{total:.0f}점 ({int(r['n_areas'])}개 영역)",
            "stores": f"{r['stores']:.1f}개",
        })
    if not rows:
        return None
    shown = pts.loc[pts.index.intersection(in_scope.index)]
    lon_min, lon_max = float(shown["lon"].min()) - 0.012, float(shown["lon"].max()) + 0.012
    lat_min, lat_max = float(shown["lat"].min()) - 0.012, float(shown["lat"].max()) + 0.012
    back = bundle.backdrop
    grid = back.loc[back["kind"].eq("grid") & back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max), ["lon", "lat"]]
    labels = back.loc[back["kind"].eq("label") & back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max), ["lon", "lat", "gu_name"]]
    cell_px = width / max((lon_max - lon_min) / 0.0045, 1)
    layers = [alt.Chart(grid).mark_square(size=float(np.clip(cell_px ** 2, 30, 900)), color=pal["neutral"], opacity=0.75)
              .encode(longitude="lon:Q", latitude="lat:Q")]
    color = alt.Color("value:Q", scale=alt.Scale(domain=[0, 100], range=[pal["blues"][0], pal["blues"][4]], interpolate="lab"),
                      legend=alt.Legend(title="종합 점수 (진할수록 높음)", values=[0, 50, 100]))
    pick = alt.selection_point(name="pick", fields=["trdar_code"], on="click", toggle=False, empty=False)
    layers.append(
        alt.Chart(alt.Data(values=rows)).mark_geoshape(stroke=pal["axis"], strokeWidth=0.4, cursor="pointer")
        .encode(shape=alt.Shape(field="geometry", type="geojson"),
                color=alt.condition("isValid(datum.value)", color, alt.value(pal["missing"])),
                tooltip=[alt.Tooltip("name:N", title="상권"), alt.Tooltip("gu:N", title="자치구"), alt.Tooltip("kind:N", title="유형"),
                         alt.Tooltip("label:N", title="종합 점수"), alt.Tooltip("stores:N", title="평균 점포 수")])
        .add_params(pick))
    chosen = [r for r in rows if r["trdar_code"] == selected]
    if chosen:
        layers.append(alt.Chart(alt.Data(values=[{"geometry": chosen[0]["geometry"]}])).mark_geoshape(fill=None, stroke=pal["ink"], strokeWidth=1.8)
                      .encode(shape=alt.Shape(field="geometry", type="geojson")))
    if not labels.empty:
        layers.append(alt.Chart(labels).mark_text(fontSize=10, color=pal["ink2"]).encode(longitude="lon:Q", latitude="lat:Q", text="gu_name:N"))
    return styled(alt.layer(*layers).project("mercator").properties(width=width, height=height), pal)


def area_bars(row: pd.Series, pal: dict, width: int = 460):
    """4개 영역 점수 막대. 50점 선은 서울 같은 업종의 가운데 위치."""
    d = pd.DataFrame({
        "영역": ["매출 잠재력", "경쟁", "안정성 (신뢰도 낮음)", "수요"],
        "점수": [row["score_sales"], row["score_comp"], row["score_stab"], row["score_dem"]],
    })
    d["표시"] = d["점수"].map(lambda v: "자료 없음" if pd.isna(v) else f"{v:.0f}점")
    d["막대"] = d["점수"].fillna(0)
    d["상태"] = np.where(d["점수"].isna(), "자료 없음", "점수")
    y = alt.Y("영역:N", sort=None, title=None)
    bars = alt.Chart(d).mark_bar(height=18).encode(
        y=y, x=alt.X("막대:Q", scale=alt.Scale(domain=[0, 100]), title="업종 안 점수 (0~100)"),
        color=alt.Color("상태:N", scale=alt.Scale(domain=["점수", "자료 없음"], range=[pal["s1"], pal["missing"]]), legend=None),
        tooltip=[alt.Tooltip("영역:N"), alt.Tooltip("표시:N", title="점수")])
    text = alt.Chart(d).mark_text(align="left", dx=4, color=pal["ink2"], fontSize=11).encode(y=y, x="막대:Q", text="표시:N")
    mid = alt.Chart(pd.DataFrame({"x": [50]})).mark_rule(color=pal["ink2"], strokeDash=[4, 3]).encode(x="x:Q")
    return styled(alt.layer(bars, text, mid).properties(width=width, height=170), pal)


def month_trend_chart(quarters: pd.DataFrame, pal: dict, width: int = 460):
    d = quarters.loc[quarters["sales_month"].notna(), ["분기", "sales_month"]].assign(월매출=lambda x: x["sales_month"] / 1e4)
    if d.empty:
        return None
    x = alt.X("분기:N", sort=list(QUARTER_LABELS.values()), scale=alt.Scale(domain=list(QUARTER_LABELS.values())), title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y("월매출:Q", title="점포당 월매출 (만 원)", scale=alt.Scale(zero=True), axis=alt.Axis(format=",.0f"))
    base = alt.Chart(d)
    return styled(alt.layer(base.mark_line(strokeWidth=2, color=pal["s1"]).encode(x=x, y=y),
                            base.mark_circle(size=70, color=pal["s1"], opacity=1).encode(
                                x=x, y=y, tooltip=[alt.Tooltip("분기:N"), alt.Tooltip("월매출:Q", format=",.0f", title="점포당 월매출(만 원)")]))
                  .properties(width=width, height=200), pal)


def flow_chart(quarters: pd.DataFrame, pal: dict, width: int = 460):
    d = quarters.melt(id_vars=["분기"], value_vars=["open_count", "close_count"], var_name="kind", value_name="건수")
    d["구분"] = d["kind"].map({"open_count": "개업", "close_count": "폐업"})
    return styled(alt.Chart(d).mark_bar().encode(
        x=alt.X("분기:N", sort=list(QUARTER_LABELS.values()), title=None, axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("구분:N", sort=["개업", "폐업"]),
        y=alt.Y("건수:Q", title="건수", axis=alt.Axis(format=",.0f", tickMinStep=1)),
        color=alt.Color("구분:N", scale=alt.Scale(domain=["개업", "폐업"], range=[pal["s3"], pal["s2"]]), legend=alt.Legend(title=None)),
        tooltip=["분기:N", "구분:N", alt.Tooltip("건수:Q", format=",.0f")]).properties(width=width, height=200), pal)


HIST_METRICS = {
    "평균 점포 수": ("stores", "개"),
    "점포당 월매출 (만 원)": ("sales_month", "만 원"),
    "유동인구 1,000명당 같은 업종 점포": ("comp_ratio", "개"),
    "보정 폐업률 (%)": ("close_pct_shrunk", "%"),
    "면적당 유동인구 (㎢당)": ("floating_density", "명"),
    "면적당 직장인구 (㎢당)": ("worker_density", "명"),
    "면적당 상주인구 (㎢당)": ("resident_density", "명"),
}


def histogram(scope: pd.DataFrame, label: str, pal: dict, width: int = 520):
    """선택 업종의 원값 분포. 점수 대상과 참고용을 나눠 쌓고, 평균 점포 수에는 5개 경계선을 그린다."""
    col, _ = HIST_METRICS[label]
    d = scope[[col, "score_status"]].dropna(subset=[col]).copy()
    if d.empty:
        return None
    d["v"] = d[col] / 1e4 if col == "sales_month" else d[col]
    hi = d["v"].quantile(0.99)
    d["v"] = d["v"].clip(upper=hi)       # 아주 큰 1% 값은 오른쪽 끝 칸에 모음
    d["구분"] = np.where(d["score_status"].eq("점수 대상"), "점수 대상", "점수 없음 (참고용 등)")
    chart = alt.Chart(d).mark_bar().encode(
        x=alt.X("v:Q", bin=alt.Bin(maxbins=40), title=f"{label} (상위 1%는 오른쪽 끝 칸에 모음)"),
        y=alt.Y("count():Q", title="상권 수", stack=True),
        color=alt.Color("구분:N", scale=alt.Scale(domain=["점수 대상", "점수 없음 (참고용 등)"], range=[pal["s1"], pal["missing"]]), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("count():Q", title="상권 수"), "구분:N"])
    layers = [chart]
    if col == "stores":
        layers.append(alt.Chart(pd.DataFrame({"x": [5]})).mark_rule(color=pal["ink"], strokeDash=[4, 3]).encode(x="x:Q"))
    return styled(alt.layer(*layers).properties(width=width, height=260), pal)


def gu_chart(scope: pd.DataFrame, pal: dict, width: int = 520):
    d = scope.loc[scope["score_total"].notna()].groupby("gu_name").agg(중앙값=("score_total", "median"), 상권수=("trdar_code", "size")).reset_index()
    if d.empty:
        return None
    d["표시"] = d["중앙값"].round(0).astype(int).astype(str) + "점 (" + d["상권수"].astype(str) + "곳)"
    y = alt.Y("gu_name:N", sort="-x", title=None)
    bars = alt.Chart(d).mark_bar(color=pal["s1"]).encode(
        y=y, x=alt.X("중앙값:Q", scale=alt.Scale(domain=[0, 100]), title="종합 점수 중앙값"),
        tooltip=[alt.Tooltip("gu_name:N", title="자치구"), alt.Tooltip("표시:N", title="중앙값 (상권 수)")])
    text = alt.Chart(d).mark_text(align="left", dx=4, color=pal["ink2"], fontSize=10).encode(y=y, x="중앙값:Q", text="표시:N")
    return styled(alt.layer(bars, text).properties(width=width, height=max(180, 18 * len(d))), pal)
