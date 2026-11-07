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


TOP_N = 10  # 지도에 번호를 붙이는 상위 상권 수


def _short(v) -> str:
    return "–" if pd.isna(v) else f"{v:.0f}"


def map_rows(bundle: Bundle, scope: pd.DataFrame, seoul: pd.DataFrame | None = None) -> list[dict]:
    """지도 두 종류가 함께 쓰는 상권별 값과 짧은 설명. 순위는 서울 전체 같은 업종 기준이다."""
    seoul = scope if seoul is None else seoul
    scored = seoul.loc[seoul["score_total"].notna()].sort_values(["score_total", "stores"], ascending=[False, False])
    rank = {c: i + 1 for i, c in enumerate(scored["trdar_code"])}
    n_scored = len(scored)
    shown = scope.loc[scope["score_total"].notna()].sort_values(["score_total", "stores"], ascending=[False, False])
    top = {c: i + 1 for i, c in enumerate(shown["trdar_code"].head(TOP_N))}
    recs = {r["trdar_code"]: r for r in scope.to_dict("records")}
    rows = []
    for f in bundle.geometry:
        r = recs.get(f["trdar_code"])
        if r is None:
            continue
        total = r["score_total"]
        has = not pd.isna(total)
        rows.append({
            "trdar_code": f["trdar_code"], "geometry": f["geometry"], "lon": f["lon"], "lat": f["lat"],
            "value": round(float(total), 1) if has else None,
            "title": f"{r['trdar_name']} · {r['gu_name']}",
            "total": f"{total:.0f}점 · 서울 {n_scored:,}곳 중 {rank[f['trdar_code']]:,}위" if has else f"점수 없음 · {r['score_status']}",
            "areas": (f"매출 {_short(r['score_sales'])} · 경쟁 {_short(r['score_comp'])} · 안정 {_short(r['score_stab'])} · 수요 {_short(r['score_dem'])}"
                      if has else f"평균 점포 {r['stores']:.1f}개"),
            "top": top.get(f["trdar_code"]),
        })
    return rows


def _bounds(rows: list[dict], pad: float = 0.012) -> tuple[float, float, float, float]:
    lons = [r["lon"] for r in rows]
    lats = [r["lat"] for r in rows]
    return min(lons) - pad, max(lons) + pad, min(lats) - pad, max(lats) + pad


def map_chart(bundle: Bundle, scope: pd.DataFrame, selected: str | None, pal: dict, height: int = 520, width: int = 540,
              seoul: pd.DataFrame | None = None):
    """Altair 지도. 상권 경계를 종합 점수로 칠하고, 클릭하면 상세 상권이 바뀐다.
    출처: 김지영/claude_dashboard/views.py map_chart를 고침.
    경계 데이터는 pandas 표로 넘긴다. alt.Data(values=...)로 넘기면 Altair가 1,500여 개 경계 좌표를 하나하나 검사하고 복사해 3초 가까이 걸리기 때문이다."""
    rows = map_rows(bundle, scope, seoul)
    if not rows:
        return None
    lon_min, lon_max, lat_min, lat_max = _bounds(rows)
    back = bundle.backdrop
    inside = back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max)
    grid = back.loc[back["kind"].eq("grid") & inside, ["lon", "lat"]]
    labels = back.loc[back["kind"].eq("label") & inside, ["lon", "lat", "gu_name"]]
    cell_px = width / max((lon_max - lon_min) / 0.0045, 1)
    layers = [alt.Chart(grid).mark_square(size=float(np.clip(cell_px ** 2, 30, 900)), color=pal["neutral"], opacity=0.35)
              .encode(longitude="lon:Q", latitude="lat:Q")]
    color = alt.Color("value:Q", scale=alt.Scale(domain=[0, 100], range=[pal["blues"][0], pal["blues"][4]], interpolate="lab"),
                      legend=alt.Legend(title="종합 점수 (진할수록 높음)", values=[0, 50, 100]))
    pick = alt.selection_point(name="pick", fields=["trdar_code"], on="click", toggle=False, empty=False)
    tip = [alt.Tooltip("title:N", title="상권"), alt.Tooltip("total:N", title="종합"), alt.Tooltip("areas:N", title="영역 점수")]
    layers.append(
        alt.Chart(pd.DataFrame(rows)).mark_geoshape(stroke=pal["surface"], strokeWidth=0.3, cursor="pointer")
        .encode(shape=alt.Shape(field="geometry", type="geojson"),
                color=alt.condition("isValid(datum.value)", color, alt.value(pal["out"])), tooltip=tip)
        .add_params(pick))
    if not labels.empty:
        layers.append(alt.Chart(labels).mark_text(fontSize=10, color=pal["muted"]).encode(longitude="lon:Q", latitude="lat:Q", text="gu_name:N"))
    chosen = [r for r in rows if r["trdar_code"] == selected]
    if chosen:  # 고른 상권 테두리는 번호보다 아래에 그려 번호를 가리지 않게 한다
        layers.append(alt.Chart(alt.Data(values=[{"geometry": chosen[0]["geometry"]}])).mark_geoshape(fill=None, stroke=pal["s2"], strokeWidth=2)
                      .encode(shape=alt.Shape(field="geometry", type="geojson")))
    tops = pd.DataFrame([{k: r[k] for k in ("lon", "lat", "top", "title", "total", "areas")} for r in rows if r["top"]])
    if not tops.empty:
        layers.append(alt.Chart(tops).mark_circle(size=190, color=pal["ink"], opacity=0.85).encode(longitude="lon:Q", latitude="lat:Q", tooltip=tip))
        layers.append(alt.Chart(tops).mark_text(fontSize=10, fontWeight=600, color=pal["surface"])
                      .encode(longitude="lon:Q", latitude="lat:Q", text="top:N", tooltip=tip))
    return styled(alt.layer(*layers).project("mercator").properties(width=width, height=height), pal)


def map_plotly(bundle: Bundle, scope: pd.DataFrame, selected: str | None, pal: dict, height: int = 520,
               seoul: pd.DataFrame | None = None, view_key: str = ""):
    """Plotly 지도. 실제 지도 위에 상권을 그리고, 마우스 휠로 확대·축소, 끌어서 이동할 수 있다.
    배경 지도(CARTO)는 인터넷이 연결되어 있어야 보인다. view_key가 같으면 가중치를 바꿔도 보던 위치를 유지한다."""
    import plotly.graph_objects as go

    rows = map_rows(bundle, scope, seoul)
    if not rows:
        return None
    dark = pal is DARK

    def geo(part):  # 층마다 그 층의 경계만 넣는다. 전체를 넣으면 같은 좌표가 층 수만큼 중복돼 화면 한도(8MB)를 넘는다.
        return {"type": "FeatureCollection",
                "features": [{"type": "Feature", "id": r["trdar_code"], "properties": {}, "geometry": r["geometry"]} for r in part]}

    tip = "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>"
    fig = go.Figure()
    for has, part in ((False, [r for r in rows if r["value"] is None]), (True, [r for r in rows if r["value"] is not None])):
        if not part:
            continue
        common = dict(geojson=geo(part), locations=[r["trdar_code"] for r in part], customdata=[[r["title"], r["total"], r["areas"]] for r in part],
                      hovertemplate=tip, marker_line_width=0.3, marker_line_color=pal["surface"])
        if has:
            fig.add_trace(go.Choroplethmap(
                **common, z=[r["value"] for r in part], zmin=0, zmax=100, marker_opacity=0.82, name="종합 점수",
                colorscale=[[0, pal["blues"][0]], [0.5, pal["blues"][2]], [1, pal["blues"][4]]],
                colorbar=dict(title=dict(text="종합 점수", font=dict(size=11)), tickvals=[0, 50, 100], thickness=10, len=0.45,
                              x=0.99, xanchor="right", y=0.04, yanchor="bottom", tickfont=dict(size=10),
                              bgcolor="rgba(255,255,255,0.75)" if not dark else "rgba(0,0,0,0.5)")))
        else:
            fig.add_trace(go.Choroplethmap(**common, z=[0] * len(part), colorscale=[[0, pal["missing"]], [1, pal["missing"]]],
                                           showscale=False, marker_opacity=0.25, name="점수 없음"))
    chosen = [r for r in rows if r["trdar_code"] == selected]
    if chosen:
        fig.add_trace(go.Choroplethmap(geojson=geo(chosen), locations=[chosen[0]["trdar_code"]], z=[0], colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                                       showscale=False, marker_line_width=2.5, marker_line_color=pal["s2"], hoverinfo="skip", name="고른 상권"))
    tops = [r for r in rows if r["top"]]
    if tops:
        fig.add_trace(go.Scattermap(
            lon=[r["lon"] for r in tops], lat=[r["lat"] for r in tops], mode="markers+text", text=[str(r["top"]) for r in tops],
            marker=dict(size=17, color=pal["ink"], opacity=0.85), textfont=dict(size=10, color=pal["surface"]),
            customdata=[[r["title"], r["total"], r["areas"]] for r in tops], hovertemplate=tip, name=f"상위 {TOP_N}곳"))
    lon_min, lon_max, lat_min, lat_max = _bounds(rows, pad=0.005)
    span = max(lon_max - lon_min, (lat_max - lat_min) * 1.25, 0.01)
    zoom = float(np.clip(np.log2(560 * 360 / (span * 512)), 9, 15))
    fig.update_layout(
        map=dict(style="carto-darkmatter" if dark else "carto-positron", zoom=zoom,
                 center=dict(lon=(lon_min + lon_max) / 2, lat=(lat_min + lat_max) / 2)),
        height=height, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, uirevision=view_key,
        paper_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, color=pal["ink2"], size=11),
        hoverlabel=dict(bgcolor=pal["surface"], bordercolor=pal["axis"], font=dict(family=FONT, color=pal["ink"], size=12)),
    )
    return fig


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
