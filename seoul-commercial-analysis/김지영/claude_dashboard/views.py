"""대시보드의 데이터 조회와 차트. marimo에 의존하지 않아 따로 테스트할 수 있다."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd

TIMES = ["00_06", "06_11", "11_14", "14_17", "17_21", "21_24"]
TIME_LABELS = ["00~06시", "06~11시", "11~14시", "14~17시", "17~21시", "21~24시"]
AGES = ["10", "20", "30", "40", "50", "60_plus"]
AGE_LABELS = ["10대", "20대", "30대", "40대", "50대", "60대+"]
TYPES = ["골목상권", "발달상권", "전통시장"]
GROUPS = ["외식", "서비스", "소매"]
QUARTER_LABELS = {"20251": "1분기", "20252": "2분기", "20253": "3분기", "20254": "4분기"}
DATASET_LABELS = {"K04": "유동인구", "K05": "집객시설", "K06": "직장인구", "K07": "상주인구"}

FONT = 'system-ui, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif'

# 색은 dataviz 기준 팔레트를 쓴다. 산점도처럼 모든 쌍이 비교되는 차트는 3색까지만 쓴다.
LIGHT = {
    "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb",
    "neutral": "#f0efec", "out": "#e8e7e1", "missing": "#a8a69f", "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
    "blues": ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
    "diverge": ["#c23636", "#ee9190", "#f0efec", "#5598e7", "#184f95"],
}
DARK = {
    "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835", "surface": "#1a1a19",
    "neutral": "#383835", "out": "#2c2c2a", "missing": "#6b6a64", "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70",
    "blues": ["#184f95", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"],
    "diverge": ["#e66767", "#a84444", "#383835", "#2a78d6", "#86b6ef"],
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
    """결측을 JSON의 null로 바꾼다. NaN은 Vega에서 0처럼 보일 수 있다."""
    return json.loads(frame.to_json(orient="records", force_ascii=False))


@dataclass(frozen=True)
class Bundle:
    cells: pd.DataFrame
    areas: pd.DataFrame
    industries: pd.DataFrame
    quarters: pd.DataFrame
    backdrop: pd.DataFrame
    geometry: tuple
    meta: dict


def load_bundle(directory: Path | str) -> Bundle:
    data = Path(directory) / "data"
    required = ["cells.parquet", "areas.parquet", "industries.parquet", "quarters.parquet", "backdrop.parquet", "areas.geojson.json", "meta.json"]
    missing = [name for name in required if not (data / name).exists()]
    if missing:
        raise FileNotFoundError(f"대시보드 데이터가 없습니다: {', '.join(missing)}. build_data.py를 먼저 실행하세요.")
    geometry = tuple(json.loads((data / "areas.geojson.json").read_text(encoding="utf-8")))
    points = pd.DataFrame([{k: f[k] for k in ("trdar_code", "lon", "lat")} for f in geometry])
    return Bundle(
        cells=pd.read_parquet(data / "cells.parquet"),
        areas=pd.read_parquet(data / "areas.parquet").merge(points, on="trdar_code", how="left"),
        industries=pd.read_parquet(data / "industries.parquet"),
        quarters=pd.read_parquet(data / "quarters.parquet"),
        backdrop=pd.read_parquet(data / "backdrop.parquet"),
        geometry=geometry,
        meta=json.loads((data / "meta.json").read_text(encoding="utf-8")),
    )


# ---------------------------------------------------------------- 조회


def visible_areas(areas: pd.DataFrame, gus=None, types=None) -> pd.DataFrame:
    """지역 필터. 아무것도 고르지 않으면 전체다."""
    d = areas
    if gus:
        d = d.loc[d["gu_name"].isin(list(gus))]
    if types:
        d = d.loc[d["trdar_type"].isin(list(types))]
    return d


def filter_scope(bundle: Bundle, industry_code: str, gus=None, types=None, min_stores: float = 5) -> pd.DataFrame:
    """고른 업종의 상권 표. 업종 내 지수는 서울 전체 기준이라 필터로 다시 계산하지 않는다."""
    area = visible_areas(bundle.areas, gus, types)[["trdar_code", "trdar_name", "trdar_type", "gu_name", "area_km2", "all_stores", "close_ratio", "close_signal"]]
    d = bundle.cells.loc[bundle.cells["industry_code"].eq(industry_code)].merge(area, on="trdar_code", how="inner")
    return d.loc[d["stores"].ge(min_stores)].sort_values(["sales_index", "sales_month", "stores"], ascending=False, na_position="last").reset_index(drop=True)


def summarize(scope: pd.DataFrame) -> dict:
    stores = scope["stores"].sum()
    observed = scope["sales_month"].notna()
    return {
        "areas": len(scope),
        "stores": float(stores),
        "indexed": int(scope["sales_index"].notna().sum()),
        "observed_areas": int(observed.sum()),
        "median_month": float(scope["sales_month"].median()) if observed.any() else None,
        "close_pct": float(scope["closes"].sum() / stores * 100) if stores else None,
        "open_pct": float(scope["opens"].sum() / stores * 100) if stores else None,
        "coverage_pct": float(scope.loc[observed, "stores"].sum() / stores * 100) if stores else None,
    }


def evidence_label(row) -> str:
    text = {"네 분기": "네 분기 관측", "일부 분기": "일부 분기만", "미공개": "매출 미공개", "미제공 업종": "매출 미제공 업종"}[row["sales_status"]]
    if row["repeated_sales"]:
        text += " · 네 분기 값 동일"
    if row["sales_status"] == "네 분기" and pd.isna(row["sales_index"]):
        text += " · 지수 비교 제외"
    return text


def area_table(scope: pd.DataFrame) -> pd.DataFrame:
    """표에 쓰는 값. 매출이 없는 칸은 빈칸으로 남긴다."""
    d = scope
    return pd.DataFrame({
        "trdar_code": d["trdar_code"],
        "상권": d["trdar_name"],
        "자치구": d["gu_name"],
        "유형": d["trdar_type"],
        "점포 수": d["stores"].round(1),
        "점포당 월매출(만원)": (d["sales_month"] / 1e4).round(0),
        "업종 내 지수": d["sales_index"].round(2),
        "보정 폐업률(%)": d["close_pct_shrunk"].round(1),
        "상권 폐업비": d["close_ratio"].round(2),
        "폐업 신호": d["close_signal"],
        "프랜차이즈(%)": d["franchise_pct"].round(0),
        "근거": [evidence_label(r) for r in d.to_dict("records")],
    })


def choose_code(current: str | None, scope: pd.DataFrame) -> str | None:
    """선택한 상권이 현재 조건에 없으면 첫 행으로 돌아간다."""
    if scope.empty:
        return None
    if current is not None and current in set(scope["trdar_code"]):
        return current
    return scope["trdar_code"].iloc[0]


def picked_code(selections: dict) -> str | None:
    """지도 클릭 선택에서 상권 코드를 꺼낸다."""
    codes = (selections or {}).get("pick", {}).get("trdar_code") or []
    return str(codes[0]) if codes else None


def quarter_rows(bundle: Bundle, code: str, industry_code: str) -> pd.DataFrame:
    q = bundle.quarters
    d = q.loc[q["trdar_code"].eq(code) & q["industry_code"].eq(industry_code)]
    d = pd.DataFrame({"quarter": list(QUARTER_LABELS)}).merge(d, on="quarter", how="left")
    d["분기"] = d["quarter"].map(QUARTER_LABELS)
    d["sales_month"] = d["sales_amount"] / d["store_count"].where(d["store_count"].gt(0)) / 3
    d[["open_count", "close_count"]] = d[["open_count", "close_count"]].fillna(0)
    return d


def vintage_text(meta: dict, dataset: str) -> str:
    last = next(i for i in meta["freshness"] if i["dataset"] == dataset)["last_observed_value_change"]
    return "2021Q1 이후 값 변경 없음" if last is None else f"값이 마지막으로 바뀐 분기 {last[:4]}Q{last[4]}"


def demand_table(area: pd.Series, meta: dict) -> pd.DataFrame:
    """인구는 기준 시점이 달라 합치지 않고 나란히 보여 준다."""
    rows = [
        ("유동인구", "floating", "2025년 분기 평균, 집계 단위 미확인"),
        ("직장인구", "worker", vintage_text(meta, "K06")),
        ("상주인구", "resident", vintage_text(meta, "K07")),
        ("집객시설", "facility", vintage_text(meta, "K05")),
    ]
    out = []
    for label, key, vintage in rows:
        value, pct = area[key], area[f"{key}_pct"]
        out.append({"지표": label, "값": "자료 없음" if pd.isna(value) else f"{value:,.0f}",
                    "면적당 밀도 서울 순위": "자료 없음" if pd.isna(pct) else f"상위 {max(100 - pct, 1):.0f}%", "기준": vintage})
    return pd.DataFrame(out)


# ---------------------------------------------------------------- 상권 찾기 차트


def map_mode(scope: pd.DataFrame) -> str:
    return "index" if scope["sales_index"].notna().any() else "stores"


def map_chart(bundle: Bundle, scope: pd.DataFrame, shown: pd.DataFrame, selected: str | None, pal: dict, height: int = 500, width: int = 640):
    """상권 지도. 조건 안의 상권만 칠하고 매출이 없는 곳은 회색으로 구분한다."""
    mode = map_mode(scope)
    in_scope = scope.set_index("trdar_code")
    shown_codes = set(shown["trdar_code"])
    names = shown.set_index("trdar_code")["trdar_name"]
    rows, faint = [], []
    for f in bundle.geometry:
        code = f["trdar_code"]
        if code not in shown_codes:
            continue
        if code not in in_scope.index:
            faint.append({"geometry": f["geometry"], "name": names[code]})
            continue
        r = in_scope.loc[code]
        value = r["stores"] if mode == "stores" else (np.log2(r["sales_index"]) if pd.notna(r["sales_index"]) and r["sales_index"] > 0 else None)
        rows.append({
            "trdar_code": code, "geometry": f["geometry"], "name": r["trdar_name"], "gu": r["gu_name"], "kind": r["trdar_type"],
            "value": None if value is None else round(float(value), 3),
            "index": "비교 불가" if pd.isna(r["sales_index"]) else f"{r['sales_index']:.2f}배",
            "month": "미공개" if pd.isna(r["sales_month"]) else f"{r['sales_month'] / 1e4:,.0f}만원",
            "stores": f"{r['stores']:.1f}개",
        })

    lon_min, lon_max = float(shown["lon"].min()) - 0.012, float(shown["lon"].max()) + 0.012
    lat_min, lat_max = float(shown["lat"].min()) - 0.012, float(shown["lat"].max()) + 0.012
    back = bundle.backdrop
    grid = back.loc[back["kind"].eq("grid") & back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max), ["lon", "lat"]]
    labels = back.loc[back["kind"].eq("label") & back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max), ["lon", "lat", "gu_name"]]

    # 격자 한 칸이 화면에서 몇 px인지 계산해 자치구로 좁혀도 윤곽이 끊기지 않게 한다
    cell_px = width / max((lon_max - lon_min) / 0.0045, 1)
    layers = [alt.Chart(grid).mark_square(size=float(np.clip(cell_px ** 2, 30, 900)), color=pal["neutral"], opacity=0.75).encode(longitude="lon:Q", latitude="lat:Q")]
    if faint:
        layers.append(alt.Chart(alt.Data(values=faint)).mark_geoshape(fill=pal["out"], stroke=pal["axis"], strokeWidth=0.3)
                      .encode(shape=alt.Shape(field="geometry", type="geojson"), tooltip=[alt.Tooltip("name:N", title="조건 밖 상권")]))
    if rows:
        if mode == "index":
            color = alt.Color("value:Q", scale=alt.Scale(domain=[-1.5, -0.75, 0, 0.75, 1.5], range=pal["diverge"], interpolate="lab", clamp=True),
                              legend=alt.Legend(title="업종 내 지수", values=[-1, 0, 1], labelExpr="datum.value < 0 ? '절반' : datum.value > 0 ? '2배' : '중앙값'"))
        else:
            color = alt.Color("value:Q", scale=alt.Scale(type="log", range=[pal["blues"][0], pal["blues"][4]], interpolate="lab"), legend=alt.Legend(title="같은 업종 점포 수"))
        pick = alt.selection_point(name="pick", fields=["trdar_code"], on="click", toggle=False, empty=False)
        layers.append(
            alt.Chart(alt.Data(values=rows)).mark_geoshape(stroke=pal["axis"], strokeWidth=0.4, cursor="pointer")
            .encode(shape=alt.Shape(field="geometry", type="geojson"),
                    color=alt.condition("isValid(datum.value)", color, alt.value(pal["missing"])),
                    tooltip=[alt.Tooltip("name:N", title="상권"), alt.Tooltip("gu:N", title="자치구"), alt.Tooltip("kind:N", title="유형"),
                             alt.Tooltip("index:N", title="업종 내 지수"), alt.Tooltip("month:N", title="점포당 월매출"), alt.Tooltip("stores:N", title="점포 수")])
            .add_params(pick))
        chosen = [r for r in rows if r["trdar_code"] == selected]
        if chosen:
            layers.append(alt.Chart(alt.Data(values=[{"geometry": chosen[0]["geometry"]}])).mark_geoshape(fill=None, stroke=pal["ink"], strokeWidth=1.8)
                          .encode(shape=alt.Shape(field="geometry", type="geojson")))
    if not labels.empty:
        layers.append(alt.Chart(labels).mark_text(fontSize=10, color=pal["ink2"]).encode(longitude="lon:Q", latitude="lat:Q", text="gu_name:N"))
    return styled(alt.layer(*layers).project("mercator").properties(width=width, height=height), pal)


def competition_chart(scope: pd.DataFrame, selected: str | None, pal: dict, height: int = 500, width: int = 420):
    """점포 수와 점포당 매출. 경쟁이 많아도 매출이 낮다고 단정할 수 없음을 보여 준다."""
    d = scope.dropna(subset=["sales_month"]).loc[lambda x: x["sales_month"].gt(0)]
    if d.empty:
        return None
    d = pd.DataFrame({
        "trdar_code": d["trdar_code"], "상권": d["trdar_name"], "유형": d["trdar_type"], "stores": d["stores"], "month": d["sales_month"] / 1e4,
        "지수": d["sales_index"].map(lambda v: "비교 불가" if pd.isna(v) else f"{v:.2f}배"),
    })
    x_ticks = [v for v in [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000] if d["stores"].min() / 1.2 <= v <= d["stores"].max() * 1.2]
    y_ticks = [v for v in [1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000] if d["month"].min() / 1.5 <= v <= d["month"].max() * 1.5]
    x = alt.X("stores:Q", scale=alt.Scale(type="log", nice=False), title="같은 업종 점포 수 (로그 눈금)", axis=alt.Axis(grid=True, values=x_ticks, format=",.0f"))
    y = alt.Y("month:Q", scale=alt.Scale(type="log", nice=False), title="점포당 월매출, 만원 (로그 눈금)", axis=alt.Axis(grid=True, values=y_ticks, format=",.0f"))
    tooltip = [alt.Tooltip("상권:N"), alt.Tooltip("유형:N"), alt.Tooltip("month:Q", title="점포당 월매출(만원)", format=",.0f"),
               alt.Tooltip("stores:Q", title="점포 수", format=".1f"), alt.Tooltip("지수:N", title="업종 내 지수")]
    base = alt.Chart(d)
    dots = base.mark_circle(size=64, opacity=0.8, stroke=pal["surface"], strokeWidth=1).encode(
        x=x, y=y, color=alt.Color("유형:N", scale=alt.Scale(domain=TYPES, range=[pal["s1"], pal["s2"], pal["s3"]]), legend=alt.Legend(title=None)))
    hit = base.mark_circle(size=500, opacity=0).encode(x=x, y=y, tooltip=tooltip)
    layers = [dots, hit]
    if selected in set(d["trdar_code"]):
        layers.append(base.transform_filter(alt.datum.trdar_code == selected).mark_circle(size=170, fillOpacity=0, stroke=pal["ink"], strokeWidth=2).encode(x=x, y=y))
    return styled(alt.layer(*layers).properties(width=width, height=height), pal)


def month_trend_chart(quarters: pd.DataFrame, pal: dict, width: int = 520):
    d = quarters.loc[quarters["sales_month"].notna(), ["분기", "sales_month"]].assign(월매출=lambda x: x["sales_month"] / 1e4)
    if d.empty:
        return None
    x = alt.X("분기:N", sort=list(QUARTER_LABELS.values()), scale=alt.Scale(domain=list(QUARTER_LABELS.values())), title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y("월매출:Q", title="점포당 월매출 (만원)", scale=alt.Scale(zero=True), axis=alt.Axis(format=",.0f", grid=True, domain=False))
    base = alt.Chart(d)
    line = base.mark_line(strokeWidth=2, color=pal["s1"]).encode(x=x, y=y)
    dots = base.mark_circle(size=70, color=pal["s1"], opacity=1, stroke=pal["surface"], strokeWidth=2).encode(x=x, y=y, tooltip=[alt.Tooltip("분기:N"), alt.Tooltip("월매출:Q", format=",.0f", title="점포당 월매출(만원)")])
    return styled(alt.layer(line, dots).properties(width=width, height=210), pal)


def flow_chart(quarters: pd.DataFrame, pal: dict, width: int = 520):
    d = quarters.melt(id_vars="분기", value_vars=["open_count", "close_count"], var_name="kind", value_name="건수")
    d["구분"] = d["kind"].map({"open_count": "개업", "close_count": "폐업"})
    chart = alt.Chart(d).mark_bar(size=20, cornerRadiusEnd=4).encode(
        x=alt.X("분기:N", sort=list(QUARTER_LABELS.values()), title=None, axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("구분:N", sort=["개업", "폐업"]),
        y=alt.Y("건수:Q", title="건수", axis=alt.Axis(tickMinStep=1, format="d", grid=True, domain=False)),
        color=alt.Color("구분:N", sort=["개업", "폐업"], scale=alt.Scale(domain=["개업", "폐업"], range=[pal["s1"], pal["s2"]]), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("분기:N"), alt.Tooltip("구분:N"), alt.Tooltip("건수:Q")])
    return styled(chart.properties(width=width, height=210), pal)


def profile_chart(cell: pd.Series, industry: pd.Series, kind: str, pal: dict, width: int = 520):
    """선택한 상권과 서울 같은 업종의 구성을 나란히 놓는다."""
    keys, labels = (TIMES, TIME_LABELS) if kind == "time" else (AGES, AGE_LABELS)
    prefix = "time" if kind == "time" else "age"
    if pd.isna(cell.get(f"{prefix}_{keys[0]}")):
        return None
    rows = []
    for key, label in zip(keys, labels):
        rows.append({"구간": label, "대상": "이 상권", "비중": cell[f"{prefix}_{key}"]})
        rows.append({"구간": label, "대상": "서울 같은 업종", "비중": industry[f"{prefix}_{key}"]})
    d = pd.DataFrame(rows).round(1)
    chart = alt.Chart(d).mark_bar(size=14, cornerRadiusEnd=4).encode(
        x=alt.X("구간:N", sort=labels, title=None, axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("대상:N", sort=["이 상권", "서울 같은 업종"]),
        y=alt.Y("비중:Q", title="매출 비중 (%)", axis=alt.Axis(grid=True, domain=False)),
        color=alt.Color("대상:N", sort=["이 상권", "서울 같은 업종"], scale=alt.Scale(domain=["이 상권", "서울 같은 업종"], range=[pal["s1"], pal["axis"]]), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("대상:N"), alt.Tooltip("비중:Q", format=".1f", title="비중(%)")])
    return styled(chart.properties(width=width, height=210), pal)


# ---------------------------------------------------------------- 업종 비교 차트

INDUSTRY_METRICS = {
    "연간 폐업률 (%)": "close_pct", "연간 개업률 (%)": "open_pct", "순증률 (%포인트)": "net_pct", "점포당 월매출 중앙값 (만원)": "median_month_man",
    "프랜차이즈 비중 (%)": "franchise_pct", "매출 칸 점포 비중 (%)": "sales_coverage_pct",
}


def filter_industries(industries: pd.DataFrame, groups=None) -> pd.DataFrame:
    d = industries.assign(median_month_man=industries["median_month"] / 1e4)
    return d.loc[d["group"].isin(list(groups))] if groups else d


def scatter_limit(d: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """축 범위와 범위 밖 업종. 상위 1% 바깥 업종은 가장자리에 붙여 그린다."""
    top = float(max(d["close_pct"].quantile(0.99), d["open_pct"].quantile(0.99), 1)) * 1.1
    return top, d.loc[(d["open_pct"] > top) | (d["close_pct"] > top)]


def industry_scatter(d: pd.DataFrame, pal: dict, height: int = 420, width: int = 520):
    top, _ = scatter_limit(d)
    x = alt.X("open_pct:Q", title="연간 개업률 (%)", scale=alt.Scale(domain=[0, top], nice=False, clamp=True), axis=alt.Axis(grid=True))
    y = alt.Y("close_pct:Q", title="연간 폐업률 (%)", scale=alt.Scale(domain=[0, top], nice=False, clamp=True), axis=alt.Axis(grid=True))
    base = alt.Chart(d)
    diagonal = alt.Chart(pd.DataFrame({"a": [0, top]})).mark_line(color=pal["muted"], strokeWidth=1).encode(x=alt.X("a:Q", scale=alt.Scale(domain=[0, top], nice=False)), y=alt.Y("a:Q", scale=alt.Scale(domain=[0, top], nice=False)))
    note = alt.Chart(pd.DataFrame({"a": [top * 0.97], "b": [top * 0.91], "t": ["선 위쪽: 폐업이 더 많음"]})).mark_text(align="right", color=pal["ink2"], fontSize=11).encode(x=alt.X("a:Q", scale=alt.Scale(domain=[0, top], nice=False)), y=alt.Y("b:Q", scale=alt.Scale(domain=[0, top], nice=False)), text="t:N")
    dots = base.mark_circle(size=80, opacity=0.85, stroke=pal["surface"], strokeWidth=1.5).encode(
        x=x, y=y, color=alt.Color("group:N", scale=alt.Scale(domain=GROUPS, range=[pal["s1"], pal["s2"], pal["s3"]]), legend=alt.Legend(title=None)))
    hit = base.mark_circle(size=500, opacity=0).encode(x=x, y=y, tooltip=[
        alt.Tooltip("industry_name:N", title="업종"), alt.Tooltip("group:N", title="업종군"), alt.Tooltip("close_pct:Q", title="폐업률(%)", format=".1f"),
        alt.Tooltip("open_pct:Q", title="개업률(%)", format=".1f"), alt.Tooltip("stores:Q", title="평균 점포 수", format=",.0f")])
    return styled(alt.layer(diagonal, note, dots, hit).properties(width=width, height=height), pal)


def industry_rank_chart(d: pd.DataFrame, metric: str, label: str, pal: dict, top: int = 15, width: int = 460):
    v = d.dropna(subset=[metric]).nlargest(top, metric)
    if v.empty:
        return None
    chart = alt.Chart(v).mark_bar(size=14, cornerRadiusEnd=4, color=pal["s1"]).encode(
        y=alt.Y("industry_name:N", sort="-x", title=None, axis=alt.Axis(grid=False)),
        x=alt.X(f"{metric}:Q", title=label, axis=alt.Axis(grid=True, domain=False, format=",.1~f")),
        tooltip=[alt.Tooltip("industry_name:N", title="업종"), alt.Tooltip(f"{metric}:Q", title=label, format=",.1f")])
    return styled(chart.properties(width=width, height=420), pal)


def industry_table(d: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "업종": d["industry_name"], "업종군": d["group"], "평균 점포 수": d["stores"].round(0), "상권 수": d["areas"],
        "점포당 월매출 중앙값(만원)": d["median_month_man"].round(0), "연간 개업률(%)": d["open_pct"].round(1), "연간 폐업률(%)": d["close_pct"].round(1),
        "순증률(%p)": d["net_pct"].round(1), "프랜차이즈(%)": d["franchise_pct"].round(1), "매출 칸 점포 비중(%)": d["sales_coverage_pct"].round(1),
    }).sort_values("평균 점포 수", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------- 근거 차트


def refresh_chart(meta: dict, pal: dict, width: int = 1080):
    quarters = [f"{y}{q}" for y in range(2021, 2027) for q in range(1, 5)]
    quarters = [q for q in quarters if "20212" <= q <= "20262"]
    rows = []
    for item in meta["freshness"]:
        name = DATASET_LABELS[item["dataset"]]
        for q in quarters:
            state = "값 변경" if q in item["changed_quarters"] else "직전 분기와 같음"
            if item["dataset"] == "K04" and q < "20252":
                state = "자료 없음"
            rows.append({"데이터": name, "분기": f"{q[2:4]}Q{q[4]}", "상태": state})
    d = pd.DataFrame(rows)
    order = [f"{q[2:4]}Q{q[4]}" for q in quarters]
    chart = alt.Chart(d).mark_rect(stroke=pal["surface"], strokeWidth=2, cornerRadius=2).encode(
        x=alt.X("분기:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, domain=False, labelOverlap=True, labelFontSize=10)),
        y=alt.Y("데이터:N", sort=list(DATASET_LABELS.values()), title=None, axis=alt.Axis(domain=False)),
        color=alt.Color("상태:N", scale=alt.Scale(domain=["값 변경", "직전 분기와 같음", "자료 없음"], range=[pal["s1"], pal["neutral"], pal["surface"]]), legend=alt.Legend(title=None, symbolType="square")),
        tooltip=[alt.Tooltip("데이터:N"), alt.Tooltip("분기:N"), alt.Tooltip("상태:N")])
    return styled(chart.properties(width=width, height=170), pal)


def reliability_chart(meta: dict, unit: str, pal: dict, width: int = 470):
    d = pd.DataFrame(meta["reliability"]).loc[lambda x: x["단위"].eq(unit)].dropna(subset=["상관"])
    bands = list(dict.fromkeys(d["구간"]))
    series = [s for s in ["점포당 매출", "개업률", "폐업률"] if s in set(d["지표"])]
    colors = {"점포당 매출": pal["s1"], "개업률": pal["s3"], "폐업률": pal["s2"]}
    x = alt.X("구간:N", sort=bands, title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y("상관:Q", title="상·하반기 값의 상관", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(grid=True, domain=False))
    color = alt.Color("지표:N", sort=series, scale=alt.Scale(domain=series, range=[colors[s] for s in series]), legend=alt.Legend(title=None))
    base = alt.Chart(d)
    line = base.mark_line(strokeWidth=2).encode(x=x, y=y, color=color)
    dots = base.mark_circle(size=70, opacity=1, stroke=pal["surface"], strokeWidth=2).encode(x=x, y=y, color=color, tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("지표:N"), alt.Tooltip("상관:Q", format=".2f")])
    return styled(alt.layer(line, dots).properties(width=width, height=240), pal)


def availability_chart(meta: dict, pal: dict, width: int = 470):
    d = pd.DataFrame(meta["availability"])
    chart = alt.Chart(d).mark_bar(size=22, cornerRadiusEnd=4, color=pal["s1"]).encode(
        x=alt.X("구간:N", sort=list(d["구간"]), title="칸의 점포 수", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("보유율:Q", title="매출 행이 있는 칸 (%)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(grid=True, domain=False)),
        tooltip=[alt.Tooltip("구간:N", title="점포 수"), alt.Tooltip("보유율:Q", format=".1f", title="보유율(%)"), alt.Tooltip("칸수:Q", format=",", title="칸 수")])
    return styled(chart.properties(width=width, height=240), pal)
