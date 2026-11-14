"""STEP 4 대시보드의 데이터 조회와 차트. marimo 없이 불러서 테스트할 수 있다.

색·스타일·지도·분기 차트는 김지영/claude_dashboard/views.py 에서 복사해 고쳤다 (함수마다 출처를 적었다).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd

import mbti

HERE = Path(__file__).resolve().parent  # 작업 폴더
ROOT = HERE.parents[1]  # 팀 저장소 루트
DATA = HERE / "data"
# 상권 경계·지도 배경·데이터 시점은 팀 공용 대시보드 데이터를 읽기만 한다.
SHARED = ROOT / "김지영" / "claude_dashboard" / "data"
# STEP 5 금융 MBTI 상권 유형·검사 문항·유형표·S/G 가중치 (김지영/step5_design/build_types.py 결과)
STEP5 = ROOT / "김지영" / "step5_design" / "data"

AREA_KEYS = ["sales", "competition", "stability", "demand"]
AREA_NAMES = {"sales": "매출 잠재력", "competition": "경쟁", "stability": "안정성 (1년치·신뢰도 낮음)", "demand": "수요"}
DEFAULT_WEIGHTS = {"sales": 30, "competition": 25, "stability": 15, "demand": 30}
TYPES = ["골목상권", "발달상권", "전통시장"]
QUARTER_LABELS = {"20251": "1분기", "20252": "2분기", "20253": "3분기", "20254": "4분기"}
MISSING = "자료 없음"
STATUS_SCORED = "점수 대상"

FONT = 'system-ui, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif'

# 출처: 김지영/claude_dashboard/views.py LIGHT·DARK (dataviz 기준 팔레트)
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
    """출처: 김지영/claude_dashboard/views.py styled"""
    return (
        chart.configure(background="transparent", font=FONT)
        .configure_view(stroke=None)
        .configure_axis(domainColor=pal["axis"], gridColor=pal["grid"], tickColor=pal["axis"], labelColor=pal["ink2"], titleColor=pal["ink2"],
                        labelFontSize=11, titleFontSize=11, titleFontWeight="normal", gridWidth=1, domainWidth=1, tickSize=0, labelPadding=6)
        .configure_legend(labelColor=pal["ink2"], titleColor=pal["ink2"], labelFontSize=11, titleFontSize=11, titleFontWeight="normal",
                          orient="top", symbolType="circle", gradientLength=180, gradientThickness=8)
        .configure_title(color=pal["ink"], subtitleColor=pal["ink2"], fontSize=13, subtitleFontSize=11, fontWeight=600, anchor="start", offset=10)
    )


# ---------------------------------------------------------------- 숫자 표기 (자료 없음과 0을 구분)


def fmt(value, spec: str = ",.0f", unit: str = "", missing: str = MISSING) -> str:
    if value is None or pd.isna(value):
        return missing
    return f"{value:{spec}}{unit}"


def fmt_score(value) -> str:
    return fmt(value, ".1f", "점")


def fmt_man(value) -> str:
    """원 → 만 원"""
    return MISSING if value is None or pd.isna(value) else f"{value / 1e4:,.0f}만 원"


def fmt_comp(value) -> str:
    """경쟁 원값(유동인구 1,000명당)을 읽기 쉬운 10만 명당으로 바꿔 쓴다. 점수는 같다."""
    return MISSING if value is None or pd.isna(value) else f"{value * 100:,.2f}개"


# ---------------------------------------------------------------- 데이터 묶음


@dataclass(frozen=True)
class Bundle:
    scores: pd.DataFrame
    availability: pd.DataFrame
    design: pd.DataFrame
    quarters: pd.DataFrame
    meta: dict
    areas: pd.DataFrame
    geometry: tuple
    backdrop: pd.DataFrame
    shared_meta: dict
    area_types: pd.DataFrame  # STEP 5 상권 MBTI 유형 (L/V · E/P)
    questions: pd.DataFrame
    type_table: pd.DataFrame
    sg_weights: pd.DataFrame
    design5: pd.DataFrame
    meta5: dict


TYPE_INFO = ["trdar_code", "type2", "lv", "ep", "lv_score", "ep_score"]


def load_bundle(data: Path = DATA, shared: Path = SHARED, step5: Path = STEP5) -> Bundle:
    required = [data / "상권_업종_비교점수_2025.parquet", data / "업종별_점수_가능여부.csv", data / "점수_설계표.csv",
                data / "분기_추이_2025.parquet", data / "stage4_meta.json",
                shared / "areas.parquet", shared / "areas.geojson.json", shared / "backdrop.parquet", shared / "meta.json"]
    missing = [p.name for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(f"대시보드 데이터가 없습니다: {', '.join(missing)}. build_scores.py를 먼저 실행하세요.")
    step5_files = [step5 / n for n in ["상권_유형_2025.parquet", "검사_문항.csv", "유형표.csv", "유형별_가중치.csv", "STEP5_설계표.csv", "stage5_meta.json"]]
    missing = [p.name for p in step5_files if not p.exists()]
    if missing:
        raise FileNotFoundError(f"금융 MBTI 데이터가 없습니다: {', '.join(missing)}. 김지영/step5_design/build_types.py를 먼저 실행하세요.")
    geometry = tuple(json.loads((shared / "areas.geojson.json").read_text(encoding="utf-8")))
    points = pd.DataFrame([{k: f[k] for k in ("trdar_code", "lon", "lat")} for f in geometry])
    area_types = pd.read_parquet(step5 / "상권_유형_2025.parquet")
    areas = (pd.read_parquet(shared / "areas.parquet", columns=["trdar_code", "trdar_name", "trdar_type", "gu_name"])
             .merge(points, on="trdar_code", how="left").merge(area_types[["trdar_code", "type2"]], on="trdar_code", how="left"))
    csv = dict(encoding="utf-8-sig")
    return Bundle(
        scores=pd.read_parquet(data / "상권_업종_비교점수_2025.parquet"),
        availability=pd.read_csv(data / "업종별_점수_가능여부.csv", dtype={"업종코드": str}, encoding="utf-8-sig"),
        design=pd.read_csv(data / "점수_설계표.csv", encoding="utf-8-sig"),
        quarters=pd.read_parquet(data / "분기_추이_2025.parquet"),
        meta=json.loads((data / "stage4_meta.json").read_text(encoding="utf-8")),
        areas=areas,
        geometry=geometry,
        backdrop=pd.read_parquet(shared / "backdrop.parquet"),
        shared_meta=json.loads((shared / "meta.json").read_text(encoding="utf-8")),
        area_types=area_types,
        questions=pd.read_csv(step5 / "검사_문항.csv", **csv),
        type_table=pd.read_csv(step5 / "유형표.csv", **csv),
        sg_weights=pd.read_csv(step5 / "유형별_가중치.csv", **csv),
        design5=pd.read_csv(step5 / "STEP5_설계표.csv", dtype=str, **csv),
        meta5=json.loads((step5 / "stage5_meta.json").read_text(encoding="utf-8")),
    )


# ---------------------------------------------------------------- 업종 선택과 가중치


def industry_options(availability: pd.DataFrame) -> dict[str, str]:
    """드롭다운 이름 → 업종코드. 점수를 못 만드는 업종과 매출이 없는 업종은 이름 옆에 표시한다."""
    out = {}
    for r in availability.sort_values("업종명").to_dict("records"):
        if r["점수 생성"] == "아니오":
            tag = " · 점수 없음"
        elif r["매출 제공"] == "아니오":
            tag = " · 매출 자료 없음"
        elif r["매출 잠재력 점수"] == "아니오":
            tag = " · 매출 비교 상권 부족"
        else:
            tag = ""
        out[f"{r['업종명']}{tag}"] = r["업종코드"]
    return out


def industry_label(availability: pd.DataFrame, name: str) -> str | None:
    """업종 이름(예: 커피-음료)에 맞는 드롭다운 이름. 없으면 None."""
    for label, code in industry_options(availability).items():
        if label.split(" · ")[0] == name:
            return label
    return None


def parse_weights(text: str | None) -> dict[str, float]:
    """'30,25,15,30' → 가중치 사전. 읽을 수 없으면 기본값."""
    try:
        values = [float(x) for x in str(text).split(",")]
        if len(values) == 4 and all(v >= 0 for v in values):
            return dict(zip(AREA_KEYS, values))
    except (TypeError, ValueError):
        pass
    return dict(DEFAULT_WEIGHTS)


def composite(frame: pd.DataFrame, weights: dict[str, float]) -> tuple[pd.Series, pd.Series]:
    """자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균과 계산에 쓴 영역 수. build_scores.composite와 같은 규칙."""
    num = pd.Series(0.0, index=frame.index)
    den = pd.Series(0.0, index=frame.index)
    used = pd.Series(0, index=frame.index)
    for key in AREA_KEYS:
        w = float(weights.get(key, 0))
        score = frame[f"score_{key}"]
        has = score.notna() & (w > 0)
        num = num + np.where(has, score * w, 0.0)
        den = den + np.where(has, w, 0.0)
        used = used + has.astype(int)
    return (num / den).where(den > 0), used


def weight_text(weights: dict[str, float]) -> str:
    total = sum(weights.values())
    if total <= 0:
        return "가중치가 모두 0입니다."
    return " · ".join(f"{AREA_NAMES[k].split(' ')[0]} {weights[k] / total * 100:.0f}%" for k in AREA_KEYS)


# ---------------------------------------------------------------- 조회


def visible_areas(areas: pd.DataFrame, gus=None, types=None, mbti=None) -> pd.DataFrame:
    """출처: 김지영/claude_dashboard/views.py visible_areas. 아무것도 고르지 않으면 전체다.

    mbti: 보여 줄 상권 MBTI 유형(두 글자) 목록. 주면 그 유형의 상권만 남긴다 (금융 MBTI '유형이 맞는 상권만 보기').
    """
    d = areas
    if gus:
        d = d.loc[d["gu_name"].isin(list(gus))]
    if types:
        d = d.loc[d["trdar_type"].isin(list(types))]
    if mbti is not None:
        d = d.loc[d["type2"].isin(list(mbti))]
    return d


def industry_rows(bundle: Bundle, industry_code: str, weights: dict[str, float]) -> pd.DataFrame:
    """고른 업종의 서울 전체 상권 행(점포가 있는 칸)과 현재 가중치의 종합 점수. 점수는 서울 전체 기준이다."""
    d = bundle.scores.loc[bundle.scores["industry_code"].eq(industry_code) & bundle.scores["stores"].gt(0)].copy()
    d["total"], d["used"] = composite(d, weights)
    d["total"] = d["total"].where(d["scored"])
    d["used"] = d["used"].where(d["scored"], 0).astype(int)
    return d.merge(bundle.areas[["trdar_code", "lon", "lat"]], on="trdar_code", how="left").merge(bundle.area_types[TYPE_INFO], on="trdar_code", how="left")


def filter_rows(rows: pd.DataFrame, gus=None, types=None, mbti=None) -> pd.DataFrame:
    d = rows
    if gus:
        d = d.loc[d["gu_name"].isin(list(gus))]
    if types:
        d = d.loc[d["trdar_type"].isin(list(types))]
    if mbti is not None:
        d = d.loc[d["type2"].isin(list(mbti))]
    return d


def with_match(rows: pd.DataFrame, matched: dict[str, str] | None) -> pd.DataFrame:
    """'유형 일치' 열 (일치 / 경계 유형 / 다른 유형 / 판정 불가). 금융 MBTI를 적용하지 않았으면 그대로."""
    if matched is None:
        return rows
    return rows.assign(mbti_match=[mbti.match_label(t, matched) for t in rows["type2"]])


def order_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """종합 점수가 높은 순, 점수가 없는 칸은 점포가 많은 순으로 뒤에."""
    return rows.sort_values(["scored", "total", "stores", "trdar_code"], ascending=[False, False, False, True], na_position="last").reset_index(drop=True)


def summary(rows: pd.DataFrame, shown_areas: pd.DataFrame) -> dict:
    """비교 대상 상권 수와 점수 제외 사유별 개수 (현재 필터 안)."""
    status = rows["status"].value_counts()
    scored = rows.loc[rows["scored"]]
    return {
        "areas": int(len(shown_areas)),
        "scored": int(len(scored)),
        "with_total": int(scored["total"].notna().sum()),
        "no_total": int(scored["total"].isna().sum()),
        "reference": int(status.get("점포 5개 미만 (참고용)", 0)),
        "thin": int(status.get("업종 비교 상권 30곳 미만", 0)),
        "no_store": int(len(shown_areas) - len(rows)),
        "median_total": None if scored["total"].isna().all() else float(scored["total"].median()),
    }


def choose_code(current: str | None, rows: pd.DataFrame) -> str | None:
    """출처: 김지영/claude_dashboard/views.py choose_code. 선택한 상권이 현재 조건에 없으면 첫 행으로 돌아간다."""
    if rows.empty:
        return None
    if current is not None and current in set(rows["trdar_code"]):
        return current
    return order_rows(rows)["trdar_code"].iloc[0]


def picked_code(selections: dict) -> str | None:
    """출처: 김지영/claude_dashboard/views.py picked_code. 지도 클릭 선택에서 상권 코드를 꺼낸다."""
    codes = (selections or {}).get("pick", {}).get("trdar_code") or []
    return str(codes[0]) if codes else None


# ---------------------------------------------------------------- 탭 1. 상권 찾기


def map_chart(bundle: Bundle, rows: pd.DataFrame, shown: pd.DataFrame, selected: str | None, pal: dict, height: int = 520, width: int = 660):
    """상권 경계를 종합 점수로 칠한다. 점수가 없는 상권은 회색, 이 업종 점포가 없는 상권은 옅은 회색.

    출처: 김지영/claude_dashboard/views.py map_chart (배경 격자, 클릭 선택, 선택 외곽선)를 종합 점수용으로 고쳤다.
    """
    by = rows.set_index("trdar_code")
    names = shown.set_index("trdar_code")
    shown_codes = set(shown["trdar_code"])
    painted, faint = [], []
    for f in bundle.geometry:
        code = f["trdar_code"]
        if code not in shown_codes:
            continue
        if code not in by.index:
            faint.append({"geometry": f["geometry"], "name": names.at[code, "trdar_name"], "why": "이 업종 점포 없음"})
            continue
        r = by.loc[code]
        if r["scored"]:
            label = fmt_score(r["total"]) + (f" ({r['used']}개 영역)" if pd.notna(r["total"]) else " (가중치가 0인 영역만 자료가 있음)")
        else:
            label = f"점수 없음: {r['status']}"
        painted.append({
            "trdar_code": code, "geometry": f["geometry"], "name": r["trdar_name"], "gu": r["gu_name"], "kind": r["trdar_type"],
            "value": None if pd.isna(r["total"]) else round(float(r["total"]), 2), "label": label, "stores": f"{r['stores']:.1f}개",
            "mbti": type2_text(r.get("type2")),
        })

    lon_min, lon_max = float(shown["lon"].min()) - 0.012, float(shown["lon"].max()) + 0.012
    lat_min, lat_max = float(shown["lat"].min()) - 0.012, float(shown["lat"].max()) + 0.012
    back = bundle.backdrop
    inside = back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max)
    grid = back.loc[back["kind"].eq("grid") & inside, ["lon", "lat"]]
    labels = back.loc[back["kind"].eq("label") & inside, ["lon", "lat", "gu_name"]]
    cell_px = width / max((lon_max - lon_min) / 0.0045, 1)
    layers = [alt.Chart(grid).mark_square(size=float(np.clip(cell_px ** 2, 30, 900)), color=pal["neutral"], opacity=0.75).encode(longitude="lon:Q", latitude="lat:Q")]
    if faint:
        layers.append(alt.Chart(alt.Data(values=faint)).mark_geoshape(fill=pal["out"], stroke=pal["axis"], strokeWidth=0.3)
                      .encode(shape=alt.Shape(field="geometry", type="geojson"),
                              tooltip=[alt.Tooltip("name:N", title="상권"), alt.Tooltip("why:N", title="상태")]))
    if painted:
        color = alt.Color("value:Q", scale=alt.Scale(domain=[0, 25, 50, 75, 100], range=pal["blues"], interpolate="lab", clamp=True),
                          legend=alt.Legend(title="종합 점수 (업종 내 비교)", values=[0, 50, 100],
                                            labelExpr="datum.value == 0 ? '0 낮음' : datum.value == 100 ? '100 높음' : '50'"))
        pick = alt.selection_point(name="pick", fields=["trdar_code"], on="click", toggle=False, empty=False)
        layers.append(
            alt.Chart(alt.Data(values=painted)).mark_geoshape(stroke=pal["axis"], strokeWidth=0.4, cursor="pointer")
            .encode(shape=alt.Shape(field="geometry", type="geojson"),
                    color=alt.condition("isValid(datum.value)", color, alt.value(pal["missing"])),
                    tooltip=[alt.Tooltip("name:N", title="상권"), alt.Tooltip("gu:N", title="자치구"), alt.Tooltip("kind:N", title="유형"),
                             alt.Tooltip("label:N", title="종합 점수"), alt.Tooltip("stores:N", title="평균 점포 수"), alt.Tooltip("mbti:N", title="MBTI 유형")])
            .add_params(pick))
        chosen = [r for r in painted if r["trdar_code"] == selected]
        if chosen:
            layers.append(alt.Chart(alt.Data(values=[{"geometry": chosen[0]["geometry"]}])).mark_geoshape(fill=None, stroke=pal["ink"], strokeWidth=1.8)
                          .encode(shape=alt.Shape(field="geometry", type="geojson")))
    if not labels.empty:
        layers.append(alt.Chart(labels).mark_text(fontSize=10, color=pal["ink2"]).encode(longitude="lon:Q", latitude="lat:Q", text="gu_name:N"))
    return styled(alt.layer(*layers).project("mercator").properties(width=width, height=height), pal)


def type2_text(type2) -> str:
    return mbti.UNKNOWN if type2 is None or pd.isna(type2) else str(type2)


def score_table(rows: pd.DataFrame) -> pd.DataFrame:
    """점수 대상 상권 표. 점수 열은 숫자로 두어 정렬되게 하고, 화면에서는 '자료 없음'으로 보이게 한다 (score_formats).

    금융 MBTI를 적용했으면(rows에 mbti_match 열) 'MBTI 유형'과 '유형 일치' 열을 붙인다.
    """
    d = order_rows(rows.loc[rows["scored"]])
    missing = []
    for r in d.itertuples():
        parts = []
        if pd.isna(r.score_sales):
            parts.append(f"매출({r.sales_note})")
        if pd.isna(r.score_demand):
            parts.append("수요(인구 자료 일부 없음)")
        missing.append(", ".join(parts))
    out = pd.DataFrame({
        "trdar_code": d["trdar_code"], "상권": d["trdar_name"], "자치구": d["gu_name"], "유형": d["trdar_type"],
        "종합 점수": d["total"], "계산 영역 수": d["used"],
        "매출 잠재력": d["score_sales"], "경쟁": d["score_competition"], "안정성 (신뢰도 낮음)": d["score_stability"], "수요": d["score_demand"],
        "평균 점포 수": d["stores"], "자료 없는 영역": missing,
    })
    if "mbti_match" in d:
        out.insert(4, "MBTI 유형", [type2_text(t) for t in d["type2"]])
        out.insert(5, "유형 일치", d["mbti_match"].to_numpy())
    return out


SCORE_COLUMNS = ["종합 점수", "매출 잠재력", "경쟁", "안정성 (신뢰도 낮음)", "수요"]


def score_formats() -> dict:
    out = {c: fmt_score for c in SCORE_COLUMNS}
    out["계산 영역 수"] = lambda v: "0개 영역" if pd.isna(v) else f"{int(v)}개 영역"
    out["평균 점포 수"] = lambda v: fmt(v, ",.1f", "개")
    return out


def reference_table(rows: pd.DataFrame) -> pd.DataFrame:
    """점수 없이 보여 주는 원값 (참고용). 매출이 없는 칸은 '자료 없음'."""
    d = rows.loc[~rows["scored"]].sort_values(["stores", "trdar_code"], ascending=[False, True])
    return pd.DataFrame({
        "trdar_code": d["trdar_code"], "상권": d["trdar_name"], "자치구": d["gu_name"], "유형": d["trdar_type"],
        "평균 점포 수": d["stores"], "점포당 월매출": [fmt_man(v) for v in d["sales_month"]],
        "유동인구 10만 명당 같은 업종 점포": [fmt_comp(v) for v in d["competition"]],
        "축소 폐업률": [fmt(v, ".1f", "%") for v in d["close_pct_shrunk"]], "연간 폐업": [f"{v:,.0f}건" for v in d["closes"]],
        "점수 없는 이유": d["status"],
    })


# ---------------------------------------------------------------- 탭 2. 상권 상세


def industry_medians(rows: pd.DataFrame) -> dict:
    """서울 같은 업종 점수 대상 상권의 중앙값 (필터와 무관)."""
    s = rows.loc[rows["scored"]]
    cols = ["sales_month", "competition", "close_pct_shrunk", "close_pct", "floating_density", "worker_density", "resident_density",
            "score_sales", "score_competition", "score_stability", "score_demand", "total"]
    return {c: (None if s[c].isna().all() else float(s[c].median())) for c in cols} | {"count": int(len(s))}


def score_bar_chart(cell: pd.Series, medians: dict, pal: dict, width: int = 560):
    """영역 점수 막대와 서울 같은 업종 중앙값 선. 자료가 없는 영역은 막대 없이 '자료 없음'이라고 쓴다."""
    rows = []
    for key in AREA_KEYS:
        v = cell[f"score_{key}"]
        rows.append({"영역": AREA_NAMES[key], "점수": None if pd.isna(v) else float(v), "글자": fmt_score(v),
                     "중앙값": medians.get(f"score_{key}"), "자리": 0 if pd.isna(v) else float(v)})
    d = pd.DataFrame(rows)
    order = [AREA_NAMES[k] for k in AREA_KEYS]
    y = alt.Y("영역:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
    x = alt.X("점수:Q", scale=alt.Scale(domain=[0, 100]), title="업종 내 비교 점수 (0~100)", axis=alt.Axis(grid=True, values=[0, 25, 50, 75, 100]))
    base = alt.Chart(d)
    bars = base.mark_bar(size=18, cornerRadiusEnd=4, color=pal["s1"]).encode(
        y=y, x=x, tooltip=[alt.Tooltip("영역:N"), alt.Tooltip("글자:N", title="점수"), alt.Tooltip("중앙값:Q", title="서울 같은 업종 중앙값", format=".1f")])
    text = base.mark_text(align="left", dx=6, color=pal["ink"], fontSize=12).encode(y=y, x=alt.X("자리:Q", scale=alt.Scale(domain=[0, 100])), text="글자:N")
    median = base.transform_filter("isValid(datum.중앙값)").mark_tick(color=pal["ink"], thickness=2, size=26).encode(
        y=y, x=alt.X("중앙값:Q", scale=alt.Scale(domain=[0, 100])), tooltip=[alt.Tooltip("중앙값:Q", title="서울 같은 업종 중앙값", format=".1f")])
    return styled(alt.layer(bars, median, text).properties(width=width, height=4 * 44), pal)


def compare_table(cell: pd.Series, medians: dict) -> pd.DataFrame:
    """영역별 원값과 서울 같은 업종 중앙값."""
    density = lambda v: fmt(v, ",.0f", "명/㎢")
    rows = [
        ("매출 잠재력", "점포당 월매출", fmt_man(cell["sales_month"]), fmt_man(medians["sales_month"]), fmt_score(cell["score_sales"]),
         cell["sales_note"] or "4개 분기 매출 기준. 카드 자료 기반 추정치"),
        ("경쟁", "유동인구 10만 명당 같은 업종 점포", fmt_comp(cell["competition"]), fmt_comp(medians["competition"]), fmt_score(cell["score_competition"]),
         "적을수록 높은 점수 [가정]"),
        ("안정성 (1년치·신뢰도 낮음)", "축소 추정 폐업률", fmt(cell["close_pct_shrunk"], ".1f", "%"), fmt(medians["close_pct_shrunk"], ".1f", "%"),
         fmt_score(cell["score_stability"]), f"실제 폐업 {cell['closes']:,.0f}건 · 단순 폐업률 {fmt(cell['close_pct'], '.1f', '%')}"),
        ("수요 ① 유동인구", "면적당 유동인구", density(cell["floating_density"]), density(medians["floating_density"]), fmt_score(cell["pct_floating"]),
         "구성 백분위. 원자료 인구 수 단위"),
        ("수요 ② 직장인구", "면적당 직장인구", density(cell["worker_density"]), density(medians["worker_density"]), fmt_score(cell["pct_worker"]), "구성 백분위"),
        ("수요 ③ 상주인구", "면적당 상주인구", density(cell["resident_density"]), density(medians["resident_density"]), fmt_score(cell["pct_resident"]), "구성 백분위"),
        ("수요 (세 구성의 평균)", "", "", "", fmt_score(cell["score_demand"]), cell["demand_note"] or "[가정]"),
    ]
    return pd.DataFrame(rows, columns=["영역", "지표", "이 상권", "서울 같은 업종 중앙값", "점수", "비고"])


def quarter_rows(bundle: Bundle, code: str, industry_code: str) -> pd.DataFrame:
    """출처: 김지영/claude_dashboard/views.py quarter_rows. 점포 행이 없는 분기는 0건으로 둔다."""
    q = bundle.quarters
    d = q.loc[q["trdar_code"].eq(code) & q["industry_code"].eq(industry_code)]
    d = pd.DataFrame({"quarter": list(QUARTER_LABELS)}).merge(d, on="quarter", how="left")
    d["분기"] = d["quarter"].map(QUARTER_LABELS)
    d[["open_count", "close_count"]] = d[["open_count", "close_count"]].fillna(0)
    return d


def month_trend_chart(quarters: pd.DataFrame, pal: dict, width: int = 480):
    """출처: 김지영/claude_dashboard/views.py month_trend_chart"""
    d = quarters.loc[quarters["sales_month_q"].notna(), ["분기", "sales_month_q"]].assign(월매출=lambda x: x["sales_month_q"] / 1e4)
    if d.empty:
        return None
    x = alt.X("분기:N", sort=list(QUARTER_LABELS.values()), scale=alt.Scale(domain=list(QUARTER_LABELS.values())), title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y("월매출:Q", title="점포당 월매출 (만 원)", scale=alt.Scale(zero=True), axis=alt.Axis(format=",.0f", grid=True, domain=False))
    base = alt.Chart(d)
    line = base.mark_line(strokeWidth=2, color=pal["s1"]).encode(x=x, y=y)
    dots = base.mark_circle(size=70, color=pal["s1"], opacity=1, stroke=pal["surface"], strokeWidth=2).encode(
        x=x, y=y, tooltip=[alt.Tooltip("분기:N"), alt.Tooltip("월매출:Q", format=",.0f", title="점포당 월매출(만 원)")])
    labels = base.mark_text(dy=-12, color=pal["ink2"], fontSize=11).encode(x=x, y=y, text=alt.Text("월매출:Q", format=",.0f"))
    return styled(alt.layer(line, dots, labels).properties(width=width, height=210), pal)


def flow_chart(quarters: pd.DataFrame, pal: dict, width: int = 480):
    """출처: 김지영/claude_dashboard/views.py flow_chart"""
    d = quarters.melt(id_vars="분기", value_vars=["open_count", "close_count"], var_name="kind", value_name="건수")
    d["구분"] = d["kind"].map({"open_count": "개업", "close_count": "폐업"})
    chart = alt.Chart(d).mark_bar(size=20, cornerRadiusEnd=4).encode(
        x=alt.X("분기:N", sort=list(QUARTER_LABELS.values()), title=None, axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("구분:N", sort=["개업", "폐업"]),
        y=alt.Y("건수:Q", title="건수", axis=alt.Axis(tickMinStep=1, format="d", grid=True, domain=False)),
        color=alt.Color("구분:N", sort=["개업", "폐업"], scale=alt.Scale(domain=["개업", "폐업"], range=[pal["s1"], pal["s2"]]), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("분기:N"), alt.Tooltip("구분:N"), alt.Tooltip("건수:Q", format=",.0f")])
    return styled(chart.properties(width=width, height=210), pal)


def qoq_table(quarters: pd.DataFrame, winsor: dict) -> pd.DataFrame:
    """분기 매출 증감률 (참고용). 상하위 5%를 잘라낸 값을 보여 주고, 잘린 경우 원래 값을 함께 적는다."""
    rows = []
    for r in quarters.itertuples():
        raw, cut = r.sales_qoq_change, r.qoq_winsor
        if r.quarter == "20251":
            note = "2025년 첫 분기라 직전 분기와 비교하지 않음"
        elif pd.isna(raw):
            note = "이번 분기나 직전 분기 매출이 없어 계산하지 않음"
        elif raw != cut:
            note = f"원래 값 {raw * 100:+,.1f}% → 상하위 5% 경계({winsor['low'] * 100:+.1f}% ~ {winsor['high'] * 100:+.1f}%)로 자름"
        else:
            note = ""
        rows.append({"분기": r.분기, "직전 분기 대비 매출 증감률 (윈저화)": fmt(None if pd.isna(cut) else cut * 100, "+,.1f", "%"), "비고": note})
    return pd.DataFrame(rows)


DATASET_LABELS = {"K04": "유동인구", "K05": "집객시설", "K06": "직장인구", "K07": "상주인구"}


def vintage_text(meta: dict, dataset: str) -> str:
    """출처: 김지영/claude_dashboard/views.py vintage_text"""
    last = next(i for i in meta["freshness"] if i["dataset"] == dataset)["last_observed_value_change"]
    return "2021Q1 이후 값 변경 없음" if last is None else f"값이 마지막으로 바뀐 분기 {last[:4]}Q{last[4]}"


def vintage_table(cell: pd.Series, shared_meta: dict) -> pd.DataFrame:
    rows = [
        ("유동인구", fmt(cell["floating"], ",.0f", ""), "2025년 분기 평균" + ("" if cell["floating_quarters"] == 4 else f" ({int(cell['floating_quarters'])}개 분기만 있음)"),
         vintage_text(shared_meta, "K04")),
        ("직장인구", fmt(cell["worker"], ",.0f", "명"), "2025년 안에서 값이 같음", vintage_text(shared_meta, "K06")),
        ("상주인구", fmt(cell["resident"], ",.0f", "명"), "2025년 안에서 값이 같음", vintage_text(shared_meta, "K07")),
        ("집객시설 (점수에 안 씀)", fmt(cell["facility"], ",.0f", "곳"), "2025년 안에서 값이 같음", vintage_text(shared_meta, "K05")),
    ]
    return pd.DataFrame(rows, columns=["자료", "이 상권 값", "2025년 안에서", "실제 값 변경 시점"])


# ---------------------------------------------------------------- 탭 3. 지표 분포와 자치구 비교


METRICS = {
    "평균 점포 수 (개)": ("stores", 1.0),
    "점포당 월매출 (만 원)": ("sales_month", 1e-4),
    "유동인구 10만 명당 같은 업종 점포 (개)": ("competition", 100.0),
    "축소 추정 폐업률 (%)": ("close_pct_shrunk", 1.0),
    "면적당 유동인구 (명/㎢)": ("floating_density", 1.0),
    "면적당 직장인구 (명/㎢)": ("worker_density", 1.0),
    "면적당 상주인구 (명/㎢)": ("resident_density", 1.0),
}
GROUP_SCORED, GROUP_OUT = "점수 대상", "점수 제외 (참고용)"


def histogram_frame(rows: pd.DataFrame, label: str, bins: int = 30) -> tuple[pd.DataFrame, dict]:
    """히스토그램 칸. 상위 1% 바깥 값은 마지막 칸에 모은다."""
    col, scale = METRICS[label]
    d = rows.assign(v=rows[col] * scale).dropna(subset=["v"])
    if d.empty:
        return pd.DataFrame(), {}
    top = float(d["v"].quantile(0.99))
    top = top if top > d["v"].min() else float(d["v"].max()) + 1
    edges = np.linspace(float(min(d["v"].min(), 0 if col == "stores" else d["v"].min())), top, bins + 1)
    clipped = d["v"].clip(upper=edges[-1])
    idx = np.clip(np.searchsorted(edges, clipped, side="right") - 1, 0, bins - 1)
    d = d.assign(bin=idx, 구분=np.where(d["scored"], GROUP_SCORED, GROUP_OUT))
    g = d.groupby(["bin", "구분"]).size().rename("상권 수").reset_index()
    g["시작"], g["끝"] = edges[g["bin"]], edges[g["bin"] + 1]
    # 쌓는 위치를 직접 계산한다 (점수 대상이 아래, 점수 제외가 위)
    g["순서"] = g["구분"].map({GROUP_SCORED: 0, GROUP_OUT: 1})
    g = g.sort_values(["bin", "순서"]).reset_index(drop=True)
    g["위"] = g.groupby("bin")["상권 수"].cumsum()
    g["아래"] = g["위"] - g["상권 수"]
    info = {"outside": int((d["v"] > top).sum()), "top": top, "median": float(d.loc[d["scored"], "v"].median()) if d["scored"].any() else None}
    return g, info


def histogram_chart(rows: pd.DataFrame, label: str, min_stores: float, pal: dict, width: int = 620):
    """선택 업종의 원값 분포. 점수 대상과 점수 제외(참고용)를 쌓아 그리고, 점포 수에는 점수 기준선을 긋는다."""
    g, info = histogram_frame(rows, label)
    if g.empty:
        return None, {}
    col = METRICS[label][0]
    x = alt.X("시작:Q", title=label, axis=alt.Axis(format=",.4~f" if col == "competition" else ",.0f", grid=False))
    bars = alt.Chart(g).mark_rect(stroke=pal["surface"], strokeWidth=0.5).encode(
        x=x, x2="끝:Q", y=alt.Y("아래:Q", title="상권 수", scale=alt.Scale(zero=True), axis=alt.Axis(grid=True, domain=False, format=",.0f")), y2="위:Q",
        color=alt.Color("구분:N", sort=[GROUP_SCORED, GROUP_OUT], scale=alt.Scale(domain=[GROUP_SCORED, GROUP_OUT], range=[pal["s1"], pal["missing"]]), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("시작:Q", title="구간 시작", format=",.2f"), alt.Tooltip("끝:Q", title="구간 끝", format=",.2f"), alt.Tooltip("상권 수:Q", format=",")])
    if col == "stores":
        line_value, line_text = float(min_stores), f"점수 기준 {min_stores:g}개 (왼쪽은 점수 제외)"
    else:
        line_value, line_text = info["median"], "점수 대상 중앙값"
    layers = [bars]
    if line_value is not None:
        rule = pd.DataFrame({"x": [line_value], "t": [line_text]})
        layers += [alt.Chart(rule).mark_rule(color=pal["ink"], strokeDash=[4, 3], strokeWidth=1.5).encode(x="x:Q"),
                   alt.Chart(rule).mark_text(align="left", dx=5, dy=-6, baseline="top", color=pal["ink"], fontSize=11).encode(x="x:Q", y=alt.value(0), text="t:N")]
    return styled(alt.layer(*layers).properties(width=width, height=260), pal), info


def gu_frame(rows: pd.DataFrame) -> pd.DataFrame:
    s = rows.loc[rows["scored"] & rows["total"].notna()]
    g = s.groupby("gu_name").agg(중앙값=("total", "median"), 상권=("total", "size")).reset_index()
    g["글자"] = [f"{m:.1f}점 · {n:,}곳" for m, n in zip(g["중앙값"], g["상권"])]
    return g.sort_values(["중앙값", "gu_name"], ascending=[False, True]).reset_index(drop=True)


def gu_chart(rows: pd.DataFrame, pal: dict, highlight=None, width: int = 520):
    g = gu_frame(rows)
    if g.empty:
        return None
    g["선택"] = np.where(g["gu_name"].isin(list(highlight or [])), "고른 자치구", "다른 자치구")
    order = list(g["gu_name"])
    y = alt.Y("gu_name:N", sort=order, title=None, axis=alt.Axis(grid=False))
    base = alt.Chart(g)
    bars = base.mark_bar(size=14, cornerRadiusEnd=4).encode(
        y=y, x=alt.X("중앙값:Q", title="종합 점수 중앙값 (0~100)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(grid=True, domain=False)),
        color=alt.Color("선택:N", scale=alt.Scale(domain=["고른 자치구", "다른 자치구"], range=[pal["s2"], pal["s1"]]),
                        legend=alt.Legend(title=None) if highlight else None),
        tooltip=[alt.Tooltip("gu_name:N", title="자치구"), alt.Tooltip("중앙값:Q", format=".1f", title="종합 점수 중앙값"), alt.Tooltip("상권:Q", title="점수 있는 상권 수")])
    text = base.mark_text(align="left", dx=5, color=pal["ink2"], fontSize=11).encode(y=y, x="중앙값:Q", text="글자:N")
    mid = alt.Chart(pd.DataFrame({"x": [50]})).mark_rule(color=pal["muted"], strokeDash=[3, 3]).encode(x="x:Q")
    return styled(alt.layer(mid, bars, text).properties(width=width, height=max(22 * len(g), 80)), pal)


# ---------------------------------------------------------------- 탭 4. 점수 기준과 한계


def exclusion_table(meta: dict) -> pd.DataFrame:
    c = meta["counts"]["by_status"]
    notes = {
        "관광특구 (점수표에서 뺌)": "다른 상권과 겹쳐 이중 집계가 되므로 비교에서 뺌 (6개 상권)",
        "평균 점포 0개": "2025년 네 분기 점포 합이 0인 칸",
        "점포 5개 미만 (참고용)": "점수 없이 원값만 참고용으로 보여 줌",
        "업종 비교 상권 30곳 미만": "같은 업종 비교 상권이 부족한 23개 업종의 칸",
        STATUS_SCORED: "영역 점수와 종합 점수를 계산한 칸",
    }
    rows = [{"구분": k, "상권×업종 칸": v, "설명": notes.get(k, "")} for k, v in c.items()]
    rows.append({"구분": "합계 (연간 표 전체)", "상권×업종 칸": sum(c.values()), "설명": "annual_features 77,694행과 같아야 함"})
    return pd.DataFrame(rows)


def industry_status_counts(rows: pd.DataFrame) -> pd.DataFrame:
    s = rows["status"].value_counts()
    return pd.DataFrame([{"구분": k, "상권 수": int(s.get(k, 0))} for k in [STATUS_SCORED, "점포 5개 미만 (참고용)", "업종 비교 상권 30곳 미만"] if s.get(k, 0)])


def design_markdown(design: pd.DataFrame) -> str:
    """설계표를 줄바꿈되는 마크다운 표로 쓴다 (넓은 표가 가로로 잘리지 않게)."""
    cols = list(design.columns)
    esc = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(":---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(esc(r[c]) for c in cols) + " |" for r in design.to_dict("records")]
    return "\n".join(lines)


def correlation_table(meta: dict) -> pd.DataFrame:
    sp = meta["diagnostics"]["spearman_overall"]
    pairs = [("score_competition", "score_demand", "경쟁 ↔ 수요"), ("score_competition", "pct_floating", "경쟁 ↔ 수요의 유동인구 구성"),
             ("pct_worker", "pct_resident", "직장인구 ↔ 상주인구 (수요 안)"), ("score_sales", "score_competition", "매출 ↔ 경쟁"),
             ("score_sales", "score_demand", "매출 ↔ 수요"), ("score_stability", "score_sales", "안정성 ↔ 매출")]
    return pd.DataFrame([{"두 점수": label, "순위상관": round(sp[a][b], 2)} for a, b, label in pairs])


# ---------------------------------------------------------------- 탭 0. 금융 MBTI (STEP 5)


def match_colors(pal: dict) -> dict:
    """유형마다 다른 색을 쓰지 않는다: 4색 범주 팔레트는 모든 쌍 비교(지도는 어떤 두 상권이든 맞닿을 수 있음)에서
    색 구분 기준을 넘지 못했다. 그래서 '내 유형과 맞는가'만 파랑(일치) · 주황(경계 유형)으로 칠하고, 유형 이름은 툴팁과 사분면 글자로 보인다."""
    return {mbti.MATCH: pal["s1"], mbti.NEAR: pal["s2"], mbti.OTHER: pal["out"], mbti.UNKNOWN: pal["missing"]}


def match_scale(pal: dict, matched: dict[str, str]):
    colors = match_colors(pal)
    domain = [s for s in mbti.MATCH_ORDER if s != mbti.NEAR or mbti.NEAR in matched.values()]
    return alt.Scale(domain=domain, range=[colors[s] for s in domain])


def type_frame(bundle: Bundle, matched: dict[str, str]) -> pd.DataFrame:
    d = bundle.area_types.copy()
    d["상태"] = [mbti.match_label(t, matched) for t in d["type2"]]
    d["MBTI 유형"] = [type2_text(t) for t in d["type2"]]
    d["판정 불가 이유"] = [" · ".join(x for x in (a, b) if x) for a, b in zip(d["lv_note"], d["ep_note"])]
    return d


def mbti_map_chart(bundle: Bundle, matched: dict[str, str], pal: dict, height: int = 470, width: int = 600):
    """서울 상권을 '내 유형과 맞는가'로 칠한다. 출처: 이 파일의 map_chart (배경 격자·자치구 이름)."""
    d = type_frame(bundle, matched).set_index("trdar_code")
    values = []
    for f in bundle.geometry:
        code = f["trdar_code"]
        if code not in d.index:
            continue
        r = d.loc[code]
        values.append({"geometry": f["geometry"], "name": r["trdar_name"], "gu": r["gu_name"], "kind": r["trdar_type"], "mbti": r["MBTI 유형"],
                       "status": r["상태"], "lv": fmt(r["lv_score"], ".1f", "점"), "ep": fmt(r["ep_score"], ".1f", "점"),
                       "why": r["판정 불가 이유"] or "-", "order": mbti.MATCH_ORDER[::-1].index(r["상태"])})
    values.sort(key=lambda x: x["order"])  # 일치 상권을 위에 그린다
    a = bundle.areas
    lon_min, lon_max = float(a["lon"].min()) - 0.012, float(a["lon"].max()) + 0.012
    lat_min, lat_max = float(a["lat"].min()) - 0.012, float(a["lat"].max()) + 0.012
    back = bundle.backdrop
    inside = back["lon"].between(lon_min, lon_max) & back["lat"].between(lat_min, lat_max)
    grid = back.loc[back["kind"].eq("grid") & inside, ["lon", "lat"]]
    labels = back.loc[back["kind"].eq("label") & inside, ["lon", "lat", "gu_name"]]
    cell_px = width / max((lon_max - lon_min) / 0.0045, 1)
    shapes = alt.Chart(alt.Data(values=values)).mark_geoshape(stroke=pal["axis"], strokeWidth=0.3).encode(
        shape=alt.Shape(field="geometry", type="geojson"),
        color=alt.Color("status:N", scale=match_scale(pal, matched), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("name:N", title="상권"), alt.Tooltip("gu:N", title="자치구"), alt.Tooltip("kind:N", title="유형"),
                 alt.Tooltip("mbti:N", title="MBTI 유형"), alt.Tooltip("status:N", title="내 유형과"), alt.Tooltip("lv:N", title="L/V 점수 (높을수록 V)"),
                 alt.Tooltip("ep:N", title="E/P 점수 (높을수록 P)"), alt.Tooltip("why:N", title="판정 불가 이유")])
    layers = [alt.Chart(grid).mark_square(size=float(np.clip(cell_px ** 2, 30, 900)), color=pal["neutral"], opacity=0.75).encode(longitude="lon:Q", latitude="lat:Q"),
              shapes]
    if not labels.empty:
        layers.append(alt.Chart(labels).mark_text(fontSize=10, color=pal["ink2"]).encode(longitude="lon:Q", latitude="lat:Q", text="gu_name:N"))
    return styled(alt.layer(*layers).project("mercator").properties(width=width, height=height), pal)


def quadrant_chart(bundle: Bundle, matched: dict[str, str], pal: dict, width: int = 470, height: int = 420):
    """L/V 점수 × E/P 점수. 점선(서울 중앙값)으로 나뉜 네 칸이 LE · LP · VE · VP다."""
    med = bundle.meta5["medians"]
    d = type_frame(bundle, matched).dropna(subset=["lv_score", "ep_score"])
    d["order"] = [mbti.MATCH_ORDER[::-1].index(s) for s in d["상태"]]
    d = d.sort_values(["order", "trdar_code"])[["trdar_name", "gu_name", "MBTI 유형", "상태", "lv_score", "ep_score"]]
    x = alt.X("lv_score:Q", title="L/V 점수 (높을수록 V 방문형)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 25, 50, 75, 100], grid=False))
    y = alt.Y("ep_score:Q", title="E/P 점수 (높을수록 P 프리미엄형)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 25, 50, 75, 100], grid=False))
    dots = alt.Chart(d).mark_circle(size=24, opacity=0.85, stroke=pal["surface"], strokeWidth=0.6).encode(
        x=x, y=y, color=alt.Color("상태:N", scale=match_scale(pal, matched), legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("trdar_name:N", title="상권"), alt.Tooltip("gu_name:N", title="자치구"), alt.Tooltip("MBTI 유형:N"),
                 alt.Tooltip("상태:N", title="내 유형과"), alt.Tooltip("lv_score:Q", title="L/V 점수", format=".1f"), alt.Tooltip("ep_score:Q", title="E/P 점수", format=".1f")])
    counts = bundle.meta5["counts"]["type2"]
    corners = pd.DataFrame([
        {"x": 2, "y": 2, "t": f"LE {counts['LE']:,}곳", "align": "left", "base": "bottom"},
        {"x": 2, "y": 98, "t": f"LP {counts['LP']:,}곳", "align": "left", "base": "top"},
        {"x": 98, "y": 2, "t": f"VE {counts['VE']:,}곳", "align": "right", "base": "bottom"},
        {"x": 98, "y": 98, "t": f"VP {counts['VP']:,}곳", "align": "right", "base": "top"},
    ])
    text = [alt.Chart(corners.loc[(corners["align"] == al) & (corners["base"] == ba)]).mark_text(align=al, baseline=ba, fontSize=12, fontWeight=600, color=pal["ink"])
            .encode(x=alt.X("x:Q", scale=alt.Scale(domain=[0, 100])), y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 100])), text="t:N")
            for al in ["left", "right"] for ba in ["top", "bottom"]]
    vline = alt.Chart(pd.DataFrame({"x": [med["lv_score"]]})).mark_rule(color=pal["ink2"], strokeDash=[4, 3]).encode(x="x:Q")
    hline = alt.Chart(pd.DataFrame({"y": [med["ep_score"]]})).mark_rule(color=pal["ink2"], strokeDash=[4, 3]).encode(y="y:Q")
    return styled(alt.layer(dots, vline, hline, *text).properties(width=width, height=height), pal)


def type_count_table(bundle: Bundle) -> pd.DataFrame:
    """상권 MBTI 유형(두 글자)별 상권 수와 상권 유형(골목·발달·전통시장)별 나뉨. S/G를 붙이면 되는 8유형 이름도 함께."""
    c = bundle.meta5["counts"]
    names = bundle.type_table.set_index("유형")
    rows = []
    for code in ["LE", "LP", "VE", "VP"]:
        lv, ep = names.loc[f"{code}S", "주요 고객"], names.loc[f"{code}S", "소비 성향"]
        eight = " / ".join(f"{t} {names.loc[t, '이모지']} {names.loc[t, '이름']}" for t in (f"{code}S", f"{code}G"))
        by = {k: c["type2_by_trdar_type"].get(k, {}).get(code, 0) for k in TYPES}
        rows.append({"MBTI 유형": code, "뜻": f"{lv} · {ep}", "상권 수": f"{c['type2'][code]:,}", **{k: f"{n:,}" for k, n in by.items()},
                     "S/G를 붙인 팀 유형표 이름": eight})
    rows.append({"MBTI 유형": mbti.UNKNOWN, "뜻": f"L/V {c['lv']['판정 불가']}곳 · E/P {c['ep']['판정 불가']}곳 판정 불가 (겹침 포함)",
                 "상권 수": f"{c['type2']['판정 불가']:,}", **{k: "-" for k in TYPES}, "S/G를 붙인 팀 유형표 이름": "-"})
    return pd.DataFrame(rows)


def unknown_text(bundle: Bundle) -> str:
    c = bundle.meta5["counts"]
    why = " · ".join(f"{k} {n}곳" for k, n in c["lv_notes"].items())
    return f"판정 불가: L/V {c['lv']['판정 불가']}곳({why}), E/P {c['ep']['판정 불가']}곳(매출 제공 업종의 4개 분기 매출 없음)."
