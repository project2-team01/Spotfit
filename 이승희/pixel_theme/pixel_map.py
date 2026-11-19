# -*- coding: utf-8 -*-
"""
SpotFit 도트(픽셀 아트) 지도 공용 모듈. STEP 4·STEP 5 대시보드와 디자인 시안이 함께 쓴다.
(대시보드 머리말·도트 핀은 folium 없이 쓰도록 header.py에 있다.)

- gu_map_html(): 자치구 지도(folium) HTML.
    서울 전체 화면: 25개 자치구를 도트(픽셀 아트)로 그린 지도.
    구를 클릭하면: 배경 지도(Esri 회색 지도) 위에 그 구의 실제 상권 경계를 종합 점수 색으로 칠한 상세 지도와 상위 5곳.
    (STEP 4·5의 '조건에 맞는 상권 지도'(Plotly)와 같은 색·설명 방식)

경계 도트 모양은 ../design_samples/ 의 geojson 캐시(seoul_gu_pixel·outside_pixel)를 읽는다.
다시 만드는 방법은 ../design_samples/README.md 참고.

색 기준
    서울 전체 화면: 구별 '보이는 점수 상권의 종합 점수 중앙값'을 구끼리 순위로 5단계에 나눈 색.
    구 상세 화면: 상권마다 종합 점수(0~100)를 연한 파랑 → 진한 파랑 연속 색으로. 점수 없는 상권은 옅은 색.
"""
from __future__ import annotations

import copy
import html
import json
from functools import lru_cache
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from branca.element import MacroElement
from jinja2 import Template
from shapely.geometry import shape
from shapely.ops import unary_union

from header import BLUE, YELLOW, header_html, pin_svg  # noqa: F401  header_html은 다른 곳에서 px.header_html로도 쓴다

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "design_samples"
GU_FILE = SAMPLES / "seoul_gu_pixel.geojson"         # 25개 자치구 도트 모양과 한강 칸
OUTSIDE_FILE = SAMPLES / "outside_pixel.geojson"     # 서울 주변 시·군 도트 실루엣
REAL_GU_FILE = SAMPLES / "seoul_gu_real.geojson"     # [업그레이드 시안] 실제 자치구 경계 (구 상세 화면 테두리, 없으면 도트 테두리)

CELL_LON, CELL_LAT = 0.0045, 0.0036                  # 구 도트 모양의 격자 (약 400m)
INK, CREAM, CARD, RIVER = "#2B2A26", "#FBF3DC", "#FFFBEF", "#9EC3F2"
OUTSIDE_FILL, OUTSIDE_LINE = "#E6DCC0", "#D6C9A6"
COLORS = ["#9FD3A8", "#3E9B5B", "#F4C430", "#5B8FE0", "#163F82"]   # 구 5단계: 낮음 → 높음 (밝기도 함께 달라짐)
# [업그레이드 시안] 구 색 = 서울 같은 업종 중앙값과의 차이. 가운데(비슷)는 크림, 높으면 파랑, 낮으면 노랑 쪽으로 진해진다.
# 가운데에서 멀수록 진해져 색만으로 높낮이가 한 방향으로 읽힌다. 경계 ±2점·±5점은 [가정].
DIFF_COLORS = ["#C08A00", "#F2D27A", "#F3EEDF", "#9EC3F2", "#1F5FC4"]
DIFF_LABELS = ["5점 넘게 낮음", "2~5점 낮음", "비슷 (±2점 안)", "2~5점 높음", "5점 넘게 높음"]
MIN_GU = 10        # [가정] 점수 상권이 이보다 적은 구는 중앙값이 흔들리므로 점선 테두리 + '참고용'
# [업그레이드 시안] 상권 상세 카드: 4개 영역 막대 색(STEP 4 views.LIGHT s1·s2·s3·blues[4]와 같음)과 원값 비교 항목
AREA_BARS = [("매출", "score_sales", "#1F5FC4"), ("경쟁", "score_comp", "#A67C00"), ("안정성", "score_stab", "#2E8B57"),
             ("수요", "score_dem", "#163F82")]
RAW_ITEMS = [("점포당 월매출", "sales_month", "money"), ("유동인구 1,000명당 같은 업종 점포", "comp_ratio", (3, "개")),
             ("보정 폐업률 (연간)", "close_pct_shrunk", (1, "%")), ("면적당 유동인구 (㎢당)", "floating_density", (0, "명")),
             ("평균 점포 수", "stores", (1, "개"))]
SCALE = [(0.0, "#D6E6FA"), (0.5, "#5B8FE0"), (1.0, "#163F82")]    # 상세 화면 점수 색 (STEP 4 views.LIGHT blues[0]·[2]·[4]와 같음)
NO_SCORE = "#CFC6AE"
AREA_NO_SCORE = "#A89F88"                            # 상세 화면 점수 없는 상권 (STEP 4 views.LIGHT missing과 같음)
# 구 상세 화면 배경 지도: Esri 회색 지도(API 키 필요 없음) + 지명 글자 층.
# CARTO 타일은 대시보드 iframe 안에서 'API KEY REQUIRED' 워터마크가 찍혀 쓰지 않는다(2026-11-17 확인).
TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
TILES_LABELS = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
TILES_ATTR = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
PAD_OVERVIEW = {"paddingTopLeft": [20, 110], "paddingBottomRight": [290, 20]}
TOP_PINS = 10      # 서울 전체 화면 핀 (지금 조건의 상위 10곳)
TOP_GU = 5         # 구 상세 화면 번호·상자 (그 구의 상위 5곳)
PIN = pin_svg()


# ---------------------------------------------------------------- 지도 바탕 (한 번만 읽음)


@lru_cache(maxsize=1)
def _base():
    if not GU_FILE.exists() or not OUTSIDE_FILE.exists():
        raise FileNotFoundError("픽셀 지도 경계 파일이 없습니다: 이승희/design_samples/seoul_gu_pixel.geojson, outside_pixel.geojson")
    fc = json.loads(GU_FILE.read_text(encoding="utf-8"))
    gus = [f for f in fc["features"] if f["properties"]["kind"] == "gu"]
    river = next(f for f in fc["features"] if f["properties"]["kind"] == "river")
    outside = json.loads(OUTSIDE_FILE.read_text(encoding="utf-8"))["features"]
    shapes = {f["properties"]["name"]: shape(f["geometry"]) for f in gus}
    seoul = unary_union(list(shapes.values()))
    x0, y0, x1, y1 = seoul.bounds
    label_at = {n: (s.representative_point().y, s.representative_point().x) for n, s in shapes.items()}
    bounds = {n: [[s.bounds[1], s.bounds[0]], [s.bounds[3], s.bounds[2]]] for n, s in shapes.items()}
    ring = [(y, x) for x, y in seoul.exterior.coords]
    return gus, river, outside, [[y0, x0], [y1, x1]], label_at, bounds, ring


@lru_cache(maxsize=1)
def _real_gu():
    """실제 자치구 경계(없으면 None). 디자인 시안 스크립트가 행정동 원본에서 한 번 만들어 둔다."""
    if not REAL_GU_FILE.exists():
        return None
    return json.loads(REAL_GU_FILE.read_text(encoding="utf-8"))["features"]


def _fmt(v, how) -> str:
    """원값 표기 (STEP 4 views.fmt_money·fmt_num과 같은 방식)."""
    if v is None or pd.isna(v):
        return "자료 없음"
    if how == "money":
        return f"{v / 1e4:,.0f}만 원"
    digits, unit = how
    return f"{v:,.{digits}f}{unit}"


def raw_medians(seoul: pd.DataFrame) -> dict:
    """서울 같은 업종 점수 상권의 원값 중앙값 (상세 카드의 비교 기준)."""
    t = seoul.loc[seoul["score_total"].notna()]
    return {col: (float(t[col].median()) if col in t.columns and t[col].notna().any() else None) for _, col, _ in RAW_ITEMS}


def card_data(r: dict, n_seoul: int, meds: dict) -> dict:
    """상권을 클릭하면 왼쪽 상자에 나오는 상세 카드 내용."""
    sub = [str(r["gu_name"])]
    if isinstance(r.get("trdar_type"), str):
        sub.append(r["trdar_type"])
    has = not pd.isna(r["score"])
    rank = r.get("seoul_rank")
    out = {
        "nm": str(r["trdar_name"]), "sub": " · ".join(sub),
        "sc": round(float(r["score"]), 1) if has else None,
        "rk": f"서울 {n_seoul:,}곳 중 {int(rank):,}위" if has and rank is not None and not pd.isna(rank) else "",
        "status": str(r.get("score_status") or "점수 없음"),
        "raw": [[label, _fmt(r.get(col), how), _fmt(meds.get(col), how)] for label, col, how in RAW_ITEMS if col in r],
    }
    if has and "score_sales" in r:
        out["a"] = [[label, None if pd.isna(r.get(col)) else round(float(r[col]), 1), color] for label, col, color in AREA_BARS]
    return out


def score_color(score) -> str:
    """종합 점수(0~100) → 연한 파랑 ~ 진한 파랑. 결측은 점수 없음 색."""
    if score is None or pd.isna(score):
        return AREA_NO_SCORE
    t = float(np.clip(score, 0, 100)) / 100
    for (t0, c0), (t1, c1) in zip(SCALE, SCALE[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
            b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
            return "#" + "".join(f"{round(x + (y - x) * k):02X}" for x, y in zip(a, b))
    return SCALE[-1][1]


def _round(coords, nd=5):
    """경계 좌표를 소수 5자리(약 1m)로 줄여 HTML 크기를 줄인다."""
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(float(c), nd) for c in coords]
    return [_round(c, nd) for c in coords]


def _short(v) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.0f}"


# ---------------------------------------------------------------- 데이터 정리


def points_of(areas) -> pd.DataFrame:
    """상권 경계 목록(trdar_code, lon, lat, geometry)에서 좌표 표를 만든다."""
    return pd.DataFrame([{k: a[k] for k in ("trdar_code", "lon", "lat")} for a in areas])


def prepare(shown: pd.DataFrame, seoul: pd.DataFrame, points: pd.DataFrame) -> pd.DataFrame:
    """지도에 그릴 상권(shown)에 좌표와 서울 순위를 붙인다.

    shown·seoul: trdar_code, trdar_name, gu_name, score_total 열이 있는 표 (한 업종).
        영역 점수(score_sales·score_comp·score_stab·score_dem)와 score_status가 있으면 설명에 쓴다.
    seoul: 서울 전체 같은 업종 표. 순위는 이 표의 점수 있는 상권 안에서 매긴다.
    points: trdar_code, lon, lat.
    """
    s = seoul.loc[seoul["score_total"].notna(), ["trdar_code", "score_total"]]
    s = s.assign(seoul_rank=s["score_total"].rank(ascending=False, method="min").astype(int))
    extra = [c for c in ("score_sales", "score_comp", "score_stab", "score_dem", "score_status", "stores", "trdar_type",
                         "sales_month", "comp_ratio", "close_pct_shrunk", "floating_density") if c in shown.columns]
    d = shown[["trdar_code", "trdar_name", "gu_name", "score_total", *extra]].merge(points, on="trdar_code", how="inner")
    d = d.merge(s[["trdar_code", "seoul_rank"]], on="trdar_code", how="left").rename(columns={"score_total": "score"})
    return d


def diff_class(diff: float) -> int:
    """서울 중앙값과의 차이 → 0(5점 넘게 낮음) ~ 4(5점 넘게 높음)."""
    if diff < -5:
        return 0
    if diff < -2:
        return 1
    if diff <= 2:
        return 2
    if diff <= 5:
        return 3
    return 4


def gu_summary(d: pd.DataFrame, seoul_median: float | None = None) -> pd.DataFrame:
    """구별 점수 상권 수·중앙값·최고 상권과 5단계 순위 색 번호(cls). 점수 상권이 없는 구는 빠진다.
    seoul_median을 주면 업그레이드 시안용 열도 붙인다: rank(중앙값 높은 순, 1위부터), diff(서울 중앙값과 차이),
    cls2(차이 5단계), small(점수 상권 MIN_GU곳 미만)."""
    s = d.dropna(subset=["score"])
    if s.empty:
        return pd.DataFrame(columns=["n", "median", "best", "cls", "rank", "diff", "cls2", "small"])
    g = s.groupby("gu_name").agg(n=("trdar_code", "size"), median=("score", "median"))
    best = s.loc[s.groupby("gu_name")["score"].idxmax(), ["gu_name", "trdar_name", "score"]].set_index("gu_name")
    g["best"] = best["trdar_name"] + " " + best["score"].round(0).astype(int).astype(str) + "점"
    # 구끼리 중앙값 순위를 5단계로 (구가 25개면 5개씩).
    # 구가 5개보다 적으면 양 끝과 사이 단계에 고르게 나누고, 구가 하나뿐이면 비교할 구가 없으니 가운데 단계로 칠한다.
    n = len(g)
    order = g["median"].rank(method="first").astype(int) - 1
    if n >= 5:
        g["cls"] = (order * 5 // n).astype(int)
    elif n == 1:
        g["cls"] = 2
    else:
        g["cls"] = (order * 4 / (n - 1)).round().astype(int)
    g["rank"] = g["median"].rank(ascending=False, method="min").astype(int)
    g["small"] = g["n"] < MIN_GU
    if seoul_median is not None:
        g["diff"] = g["median"] - seoul_median
        g["cls2"] = g["diff"].map(diff_class).astype(int)
    return g


# [업그레이드 시안] 서울 전체 화면 '구 색 기준' 버튼: (열쇠, 버튼 이름, 지도 표 열, 서울 표 열, 범례 설명)
METRICS = [
    ("total", "종합", "score", "score_total", "종합 점수"),
    ("sales", "매출", "score_sales", "score_sales", "매출 잠재력 점수 · 점포당 월매출 기준, 매출 자료가 있는 상권만"),
    ("comp", "경쟁", "score_comp", "score_comp", "경쟁 점수 · 높을수록 같은 업종 점포가 덜 붐빔"),
    ("stab", "안정성", "score_stab", "score_stab", "안정성 점수 · 높을수록 보정 폐업률이 낮음 (1년치라 신뢰도 낮음)"),
    ("dem", "수요", "score_dem", "score_dem", "수요 점수 · 면적당 유동·직장·상주인구"),
]
TOP_SHARE = 0.10   # '상위 10% 상권 수': 서울 같은 업종 종합 점수 상위 10% 안에 드는 상권
TOP_COLORS = ["#F3EEDF", "#D6E6FA", "#9EC3F2", "#5B8FE0", "#1F5FC4"]
TOP_BINS = [(0, 0, "0곳"), (1, 1, "1곳"), (2, 3, "2~3곳"), (4, 6, "4~6곳"), (7, 10 ** 9, "7곳 이상")]


def metric_views(d: pd.DataFrame, seoul: pd.DataFrame, names: list[str]) -> tuple[dict, dict, list]:
    """구 색 기준마다 구별 색·이름표·설명과 범례를 만든다.
    돌려주는 값: ({구 이름: {열쇠: {c 색, l 이름표, neg 음수, sm 참고용, t 설명}}}, {열쇠: 범례 HTML}, [(열쇠, 버튼 이름)])."""
    per = {n: {} for n in names}
    legends, keys = {}, []
    base = seoul.loc[seoul["score_total"].notna()]
    for key, label, col, scol, desc in METRICS:
        if col not in d.columns or scol not in base.columns or base[scol].notna().sum() == 0 or d[col].notna().sum() == 0:
            continue   # 이 업종에 없는 기준(예: 매출 자료가 없는 업종의 매출)은 버튼을 만들지 않는다
        sm = float(base[scol].median())
        s = d.dropna(subset=[col])
        g = s.groupby("gu_name").agg(n=("trdar_code", "size"), median=(col, "median"))
        g["diff"] = g["median"] - sm
        g["cls"] = g["diff"].map(diff_class).astype(int)
        g["rank"] = g["median"].rank(ascending=False, method="min").astype(int)
        g["small"] = g["n"] < MIN_GU
        if key == "total":
            best = s.loc[s.groupby("gu_name")[col].idxmax(), ["gu_name", "trdar_name", col]].set_index("gu_name")
        for name in names:
            if name not in g.index:
                per[name][key] = {"c": NO_SCORE, "l": "-", "neg": False, "sm": False,
                                  "t": f"<b>{html.escape(name)}</b><br>조건에 맞는 점수 상권 없음"}
                continue
            r = g.loc[name]
            tip = (f"<b>{html.escape(name)}</b> · {label}<br>구 중앙값 <b>{r['median']:.1f}점</b><br>"
                   f"서울 중앙값 {sm:.1f}점 대비 <b>{r['diff']:+.1f}점</b> ({DIFF_LABELS[int(r['cls'])]})<br>"
                   f"{len(g)}개 구 중 {int(r['rank'])}위 · 점수 상권 {int(r['n'])}곳" + (f" (참고용: {MIN_GU}곳 미만)" if r["small"] else ""))
            if key == "total":
                tip += f"<br>최고 상권: {html.escape(str(best.loc[name, 'trdar_name']))} {best.loc[name, col]:.0f}점"
            per[name][key] = {"c": DIFF_COLORS[int(r["cls"])], "l": f"{r['diff']:+.1f}" + ("*" if r["small"] else ""),
                              "neg": bool(r["diff"] < 0), "sm": bool(r["small"]), "t": tip}
        counts = g["cls"].value_counts()
        legends[key] = (
            f'<b>{label}: 구별 중앙값</b><div class="lg-desc">{html.escape(desc)}<br>서울 같은 업종 중앙값 '
            f'<b>{sm:.1f}점</b>과의 차이</div>'
            + "".join(f'<div class="lg-row"><span style="background:{DIFF_COLORS[c]}"></span>{DIFF_LABELS[c]}'
                      f'<em class="lg-n">{int(counts.get(c, 0))}개 구</em></div>' for c in range(4, -1, -1))
            + f'<div class="lg-desc">가장 높은 구와 낮은 구의 차이 {g["median"].max() - g["median"].min():.1f}점 · 이름표 숫자 = 차이</div>'
            + (f'<div class="lg-row"><span style="background:{DIFF_COLORS[3]};opacity:0.5;border-style:dashed"></span>'
               f'흐린 색·점선 = 점수 상권 {MIN_GU}곳 미만 (참고용, 숫자 옆 *)</div>' if g["small"].any() else "")
            + (f'<div class="px-warn" style="margin:2px 0 0">구 {int(g["small"].sum())}개가 참고용이라 이 기준으로는 구끼리 비교하기 어렵습니다</div>'
               if g["small"].mean() >= 0.5 else ""))
        keys.append((key, label))

    # 상위 10% 상권 수: 창업 후보가 몇 곳 있는 구인지
    if base["score_total"].notna().any() and d["score"].notna().any():
        thr = float(base["score_total"].quantile(1 - TOP_SHARE))
        n_top = int((base["score_total"] >= thr).sum())
        cnt = d.loc[d["score"] >= thr].groupby("gu_name").size()
        cnt = pd.Series({n: int(cnt.get(n, 0)) for n in names})
        rank = cnt.rank(ascending=False, method="min").astype(int)
        cls = cnt.map(lambda v: next(i for i, (lo, hi, _) in enumerate(TOP_BINS) if lo <= v <= hi))
        for name in names:
            c = int(cnt[name])
            per[name]["top10"] = {
                "c": TOP_COLORS[int(cls[name])], "l": f"{c}곳", "neg": False, "sm": False,
                "t": (f"<b>{html.escape(name)}</b> · 상위 10% 상권<br><b>{c}곳</b> (서울 전체 {n_top}곳 중 {c / n_top:.0%})<br>"
                      f"{len(names)}개 구 중 {int(rank[name])}위 · 기준: 종합 {thr:.1f}점 이상")}
        counts = cls.value_counts()
        legends["top10"] = (
            f'<b>상위 10% 상권 수</b><div class="lg-desc">서울 같은 업종 종합 점수 상위 10%(<b>{thr:.1f}점 이상</b>, '
            f'서울 {n_top}곳) 중 그 구에 있는 상권 수</div>'
            + "".join(f'<div class="lg-row"><span style="background:{TOP_COLORS[i]}"></span>{TOP_BINS[i][2]}'
                      f'<em class="lg-n">{int(counts.get(i, 0))}개 구</em></div>' for i in range(4, -1, -1))
            + '<div class="lg-desc">이름표 숫자 = 상위 10% 상권 수 · 구 면적이 클수록 많아지기 쉽습니다</div>')
        keys.append(("top10", "상위 10% 상권 수"))
    return per, legends, keys


def area_tip(r, n_seoul: int) -> str:
    """상세 지도에서 상권에 마우스를 올리면 나오는 설명 (STEP 4 map_rows와 같은 내용)."""
    title = f"<b>{html.escape(str(r['trdar_name']))}</b> · {html.escape(str(r['gu_name']))}"
    if pd.isna(r["score"]):
        status = r.get("score_status")
        return f"{title}<br>점수 없음{' · ' + html.escape(str(status)) if isinstance(status, str) else ''}"
    rank = "" if pd.isna(r.get("seoul_rank")) else f" · 서울 {n_seoul:,}곳 중 {int(r['seoul_rank']):,}위"
    lines = [title, f"종합 {r['score']:.0f}점{rank}"]
    if "score_sales" in r:
        lines.append(f"매출 {_short(r.get('score_sales'))} · 경쟁 {_short(r.get('score_comp'))} · "
                     f"안정 {_short(r.get('score_stab'))} · 수요 {_short(r.get('score_dem'))}")
    return "<br>".join(lines)


def detail_data(d: pd.DataFrame, g: pd.DataFrame, n_seoul: int, geometry: dict, seoul_median: float | None = None,
                meds: dict | None = None) -> dict:
    """구마다 상세 화면에 쓸 상권 경계·색·설명, 상위 5곳, 확대 범위.
    seoul_median을 주면(업그레이드 시안) 서울 중앙값 대비 차이·구 순위·참고용 여부(cmp)도 넣는다.
    meds를 주면(업그레이드 시안) 상권마다 클릭하면 나오는 상세 카드(k)도 넣는다."""
    gus, _, _, _, _, bounds, _ = _base()
    out = {}
    for f in gus:
        name = f["properties"]["name"]
        part = d.loc[d["gu_name"].eq(name)]
        top = part.dropna(subset=["score"]).sort_values("score", ascending=False, kind="mergesort").head(TOP_GU)
        no = {c: i for i, c in enumerate(top["trdar_code"], start=1)}
        areas = []
        # 점수 없는 상권을 먼저(아래에), 점수 있는 상권을 나중에(위에) 그린다
        for r in sorted(part.to_dict("records"), key=lambda r: (not pd.isna(r["score"]), r["score"] if not pd.isna(r["score"]) else 0)):
            geom = geometry.get(r["trdar_code"])
            if geom is None:
                continue
            props = {"c": score_color(r["score"]), "s": not pd.isna(r["score"]), "t": area_tip(r, n_seoul)}
            if meds is not None:
                props.update({"id": str(r["trdar_code"]), "k": card_data(r, n_seoul, meds)})
            areas.append({"type": "Feature", "geometry": {"type": geom["type"], "coordinates": _round(geom["coordinates"])},
                          "properties": props})
        has = name in g.index
        out[name] = {
            "bounds": bounds[name], "areas": areas,
            "nums": [{"n": no[r["trdar_code"]], "ll": [round(r["lat"], 6), round(r["lon"], 6)]} for _, r in top.iterrows()],
            "n": int(g.loc[name, "n"]) if has else 0,
            "median": round(float(g.loc[name, "median"]), 1) if has else None,
            "top": [{"name": r.trdar_name, "score": round(float(r.score), 1), "code": str(r.trdar_code),
                     "rank": None if pd.isna(r.seoul_rank) else int(r.seoul_rank)} for r in top.itertuples()],
            "seoul_n": n_seoul,
        }
        if seoul_median is not None and has:
            out[name]["cmp"] = {"diff": round(float(g.loc[name, "diff"]), 1), "rank": int(g.loc[name, "rank"]), "n_gu": int(len(g)),
                                "small": bool(g.loc[name, "small"]), "seoul_median": round(float(seoul_median), 1), "min_gu": MIN_GU}
    return out


# ---------------------------------------------------------------- 클릭 동작


class ClickDetail(MacroElement):
    """구를 클릭하면 배경 지도 위에 그 구의 상권 지도를 그리고, '서울 전체' 버튼으로 도트 지도로 되돌린다."""
    _template = Template("""{% macro script(this, kwargs) %}{% raw %}
(function () {
  var map = __MAP__, gj = __GJ__, DETAIL = __DATA__, SEOUL = __SEOUL__, PAD = __PAD__;
  var pixelBits = [__OUTSIDE__, __RIVER__, __SHADOW__];          // 상세 화면에서 숨기는 도트 장식
  var markerBits = [__LABELS__, __PINS__];                        // 상세 화면에서 숨기는 구 이름표·상위 10곳 핀
  var realGu = __REALGU__;                                         // [업그레이드] 실제 구 경계 (상세 화면 테두리, 없으면 null)
  if (realGu && __RING__) { pixelBits.push(__RING__); }             // 실제 경계가 있으면 서울 도트 테두리도 상세 화면에서 숨긴다
  var byCode = {}, picked = null;                                  // [업그레이드] 상권 클릭 → 상세 카드
  var UPGRADE = __UPGRADE__, LEGENDS = __LEGENDS__, curMetric = 'total';   // [업그레이드] 구 색 기준 버튼
  var riverRef = __RIVER__, ringRef = __RING__, byGu = {};
  gj.eachLayer(function (l) { byGu[l.feature.properties.name] = l; });
  var tiles = L.layerGroup([L.tileLayer(__TILES__, {attribution: __ATTR__, maxZoom: 17, maxNativeZoom: 16}),
                             L.tileLayer(__LABELS_TILES__, {maxZoom: 17, maxNativeZoom: 16, pane: 'shadowPane'})]);
  var layer = L.layerGroup().addTo(map);
  var panel = document.getElementById('gu-panel');
  var lgOverview = document.getElementById('legend-overview'), lgDetail = document.getElementById('legend-detail');
  var current = null;   // 지금 확대한 구 (null = 서울 전체)
  var DETAIL_PAD = {paddingTopLeft: [320, 30], paddingBottomRight: [30, 30]};
  var saved = pixelBits.map(function (b) { return b ? Object.assign({}, b.options) : null; });
  function refit() {    // 틀 크기가 바뀌면(대시보드 안에서 처음 열릴 때 등) 지도 크기와 범위를 다시 맞춘다
    map.invalidateSize();
    if (current && DETAIL[current]) { map.fitBounds(DETAIL[current].bounds, DETAIL_PAD); } else { map.fitBounds(SEOUL, PAD); }
  }
  window.addEventListener('resize', refit);
  window.addEventListener('load', refit);
  setTimeout(refit, 300);
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function pixelMode(on) {
    pixelBits.forEach(function (b, i) {
      if (!b) { return; }
      b.setStyle(on ? {opacity: saved[i].opacity === undefined ? 1 : saved[i].opacity, fillOpacity: saved[i].fillOpacity === undefined ? 1 : saved[i].fillOpacity}
                    : {opacity: 0, fillOpacity: 0});
    });
    markerBits.forEach(function (m) { if (!m) { return; } if (on) { map.addLayer(m); } else { map.removeLayer(m); } });
    if (on) { map.removeLayer(tiles); } else { tiles.addTo(map); }
    if (realGu && on) { realGu.setStyle({opacity: 0, fillOpacity: 0}); }
  }
  function bar(a) {   // 4개 영역 막대 한 줄: [이름, 점수 또는 null, 색]
    var v = a[1];
    return '<div class="px-bar"><span>' + esc(a[0]) + '</span><div><i style="width:' + (v === null ? 0 : v) + '%;background:' + a[2] +
           '"></i><u></u></div><em>' + (v === null ? '자료 없음' : Math.round(v)) + '</em></div>';
  }
  function cardHtml(k) {
    var h = '<div class="px-card-h"><b>' + esc(k.nm) + '</b><button type="button" class="px-x" aria-label="상권 카드 닫기" onclick="spotfitUnpick()">×</button></div>' +
            '<div class="px-sub">' + esc(k.sub) + '</div>';
    h += k.sc === null ? '<div class="px-big">점수 없음 · ' + esc(k.status) + '</div>'
                       : '<div class="px-big">종합 <b>' + k.sc.toFixed(1) + '</b>점 · ' + esc(k.rk) + '</div>';
    if (k.a) { h += k.a.map(bar).join('') + '<div class="px-note">점선 = 50점 (서울 같은 업종의 가운데)</div>'; }
    if (k.raw && k.raw.length) {
      h += '<table class="px-raw"><tr><th>원값</th><th>이 상권</th><th>서울 중앙값</th></tr>' +
           k.raw.map(function (r) { return '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td><td>' + esc(r[2]) + '</td></tr>'; }).join('') +
           '</table><div class="px-note">점포 밀도(경쟁)와 폐업률은 낮을수록 점수가 높습니다. 중앙값은 서울 같은 업종 점수 상권 기준입니다.</div>';
    }
    return h;
  }
  function unpick() {
    if (picked) { picked.setStyle({weight: 0.6, color: '#FFFFFF'}); }
    picked = null;
    var c = document.getElementById('area-card'); if (c) { c.style.display = 'none'; c.innerHTML = ''; }
    var hint = document.getElementById('area-hint'); if (hint) { hint.style.display = 'block'; }
  }
  function pick(l) {
    if (picked) { picked.setStyle({weight: 0.6, color: '#FFFFFF'}); }
    picked = l;
    l.setStyle({weight: 3.5, color: '#2B2A26'}); l.bringToFront();
    var c = document.getElementById('area-card');
    c.innerHTML = cardHtml(l.feature.properties.k); c.style.display = 'block';
    var hint = document.getElementById('area-hint'); if (hint) { hint.style.display = 'none'; }
    panel.scrollTop = 0;
  }
  window.spotfitUnpick = unpick;
  window.spotfitPick = function (code) {
    var l = byCode[code]; if (!l) { return; }
    pick(l);
    map.panInside(l.getBounds().getCenter(), {paddingTopLeft: [330, 40], paddingBottomRight: [40, 40]});
  };
  // ---- [업그레이드] 구 색 기준 바꾸기
  function guStyle(l) {
    var m = l.feature.properties.m[curMetric];
    return {fillColor: m.c, fillOpacity: m.sm ? 0.4 : 1, color: m.sm ? '#2B2A26' : '#FFFFFF', weight: m.sm ? 2 : 2.5,
            opacity: 1, dashArray: m.sm ? '6 4' : null};
  }
  function applyMetric(key) {
    curMetric = key;
    gj.eachLayer(function (l) { l.setStyle(guStyle(l)); });
    document.querySelectorAll('.gu-label[data-gu]').forEach(function (el) {
      var l = byGu[el.getAttribute('data-gu')], sp = el.querySelector('span');
      if (!l || !sp) { return; }
      var m = l.feature.properties.m[key];
      sp.textContent = m.l; sp.className = m.neg ? 'neg' : '';
    });
    var lg = document.getElementById('legend-metric'); if (lg && LEGENDS[key]) { lg.innerHTML = LEGENDS[key]; }
    document.querySelectorAll('.px-mbtn').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-key') === key ? 'true' : 'false');
    });
  }
  function moveTo(bounds, pad) {   // 업그레이드 시안은 부드럽게 날아가며 확대·축소한다
    if (UPGRADE) { map.flyToBounds(bounds, Object.assign({duration: 0.7}, pad)); } else { map.fitBounds(bounds, pad); }
  }
  function setOverviewUi(on, name) {
    var bar = document.getElementById('metric-bar'); if (bar) { bar.style.display = on ? 'block' : 'none'; }
    var crumb = document.getElementById('crumb');
    if (crumb) {
      crumb.innerHTML = on ? '<b>서울 전체</b>'
                           : '<button type="button" class="px-crumb-btn">서울 전체</button> › <b>' + esc(name) + '</b>';
      var b = crumb.querySelector('button'); if (b) { b.addEventListener('click', reset); }
    }
  }
  if (UPGRADE && __PINS__) {   // 이름표가 핀보다 위에 있으므로, 핀에 마우스를 올리면 그 핀을 맨 앞으로
    __PINS__.eachLayer(function (pin) {
      pin.on('mouseover', function () { pin.setZIndexOffset(3000); });
      pin.on('mouseout', function () { pin.setZIndexOffset(0); });
    });
  }
  if (UPGRADE) {
    document.querySelectorAll('.px-mbtn').forEach(function (b) {
      b.addEventListener('click', function () { applyMetric(b.getAttribute('data-key')); });
    });
    gj.eachLayer(function (l) {
      var name = l.feature.properties.name;
      l.bindTooltip(function () {
        return current ? '<b>' + esc(name) + '</b> · 눌러서 이 구 보기' : l.feature.properties.m[curMetric].t;
      }, {className: 'px-tip', sticky: true});
      l.on('mouseover', function () {   // 서울 전체 화면에서 구가 살짝 떠오른다
        if (current || !l._path) { return; }
        l._path.classList.add('gu-hover'); l.bringToFront();
      });
      l.on('mouseout', function () {
        if (!l._path) { return; }
        l._path.classList.remove('gu-hover');
        if (riverRef) { riverRef.bringToFront(); }   // 한강·서울 테두리를 다시 맨 위로
        if (ringRef) { ringRef.bringToFront(); }
      });
    });
  }
  function reset() {
    current = null;
    picked = null; byCode = {};
    layer.clearLayers();
    pixelMode(true);
    if (UPGRADE) { applyMetric(curMetric); } else { gj.eachLayer(function (l) { gj.resetStyle(l); }); }   // 처음 모양으로
    setOverviewUi(true);
    panel.style.display = 'none'; lgOverview.style.display = 'flex'; lgDetail.style.display = 'none';
    moveTo(SEOUL, PAD);
  }
  function show(name) {
    var d = DETAIL[name]; if (!d) { return; }
    current = name;
    picked = null; byCode = {};
    layer.clearLayers();
    pixelMode(false);
    gj.eachLayer(function (l) { if (l._path) { l._path.classList.remove('gu-hover'); } l.closeTooltip(); });   // 서울 화면의 구 설명은 닫는다
    if (realGu) {   // 실제 구 경계로 테두리를 그린다. 도트 구는 안 보이게 두되 눌러서 다른 구로 옮겨 갈 수 있게 남긴다
      gj.eachLayer(function (l) { l.setStyle({fillOpacity: 0.01, opacity: 0}); });
      realGu.setStyle(function (f) {
        return f.properties.name === name ? {opacity: 1, weight: 3.5, color: '#2B2A26', fillOpacity: 0}
                                          : {opacity: 0.45, weight: 1.5, color: '#2B2A26', fillOpacity: 0};
      });
    } else {
      gj.eachLayer(function (l) {   // 구는 투명하게 두고 테두리만. 다른 구를 눌러 바로 옮겨 갈 수 있다
        var on = l.feature.properties.name === name;
        l.setStyle(on ? {fillOpacity: 0, weight: 4, color: '#2B2A26', opacity: 1} : {fillOpacity: 0.05, weight: 1.5, color: '#2B2A26', opacity: 0.35});
      });
    }
    L.geoJSON({type: 'FeatureCollection', features: d.areas}, {
      style: function (f) { return {fillColor: f.properties.c, fillOpacity: f.properties.s ? 0.82 : 0.35, color: '#FFFFFF', weight: 0.6}; },
      onEachFeature: function (f, l) {
        l.bindTooltip(f.properties.t, {className: 'px-tip', sticky: true});
        if (f.properties.id) { byCode[f.properties.id] = l; }
        l.on('mouseover', function () { if (l !== picked) { l.setStyle({weight: 2.5, color: '#2B2A26'}); } });
        l.on('mouseout', function () { if (l !== picked) { l.setStyle({weight: 0.6, color: '#FFFFFF'}); } });
        if (f.properties.k) { l.on('click', function (e) { L.DomEvent.stopPropagation(e); pick(l); }); }
      }
    }).addTo(layer);
    if (realGu) { realGu.bringToFront(); }
    d.nums.forEach(function (p) {
      L.marker(p.ll, {interactive: false, icon: L.divIcon({className: 'px-num-wrap', html: '<span class="px-num">' + p.n + '</span>', iconSize: [22, 22], iconAnchor: [11, 11]})}).addTo(layer);
    });
    var cards = d.areas.length > 0 && !!d.areas[0].properties.k;   // [업그레이드] 상세 카드가 있으면 목록도 눌러서 열 수 있다
    var rows = d.top.map(function (t, i) {
      var rank = t.rank === null ? '' : '<small>서울 ' + t.rank + '위</small>';
      var inner = '<b>' + (i + 1) + '</b><span>' + esc(t.name) + '</span><em>' + t.score.toFixed(1) + '</em>' + rank;
      return cards ? '<li><button type="button" class="px-li" data-code="' + esc(t.code) + '">' + inner + '</button></li>'
                   : '<li>' + inner + '</li>';
    }).join('');
    var cmp = '';
    if (d.cmp) {   // 업그레이드 시안: 서울 중앙값과 비교, 구 순위, 표본 적음 경고
      var c = d.cmp, sign = c.diff > 0 ? '+' : '';
      cmp = '<div class="px-cmp"><b>' + sign + c.diff.toFixed(1) + '점</b> 서울 중앙값(' + c.seoul_median.toFixed(1) + '점) 대비 · ' +
            c.n_gu + '개 구 중 <b>' + c.rank + '위</b></div>' +
            (c.small ? '<div class="px-warn">점수 상권이 ' + c.min_gu + '곳 미만이라 중앙값이 흔들릴 수 있습니다 (참고용)</div>' : '');
    }
    var body = d.n === 0
      ? '<div class="px-sub">이 구에는 조건에 맞는 점수 상권이 없습니다.</div>'
      : '<div class="px-sub">이 구의 점수 상위 5곳 (지도의 검은 번호 · 서울 같은 업종 ' + d.seoul_n + '곳 중 순위)</div><ol class="px-top">' + rows + '</ol>';
    panel.innerHTML =
      '<button type="button" class="px-back" onclick="spotfitReset()">← 서울 전체</button>' +
      '<h2>' + esc(name) + '</h2>' +
      '<div class="px-stats"><div><small>점수 상권</small><b>' + d.n + '곳</b></div><div><small>점수 중앙값</small><b>' +
      (d.median === null ? '-' : d.median.toFixed(1)) + '</b></div></div>' + cmp +
      (cards ? '<div id="area-hint" class="px-hint">상권을 클릭하거나 아래 목록을 누르면 여기에 4개 영역 점수와 원값이 나옵니다.</div>' +
               '<div id="area-card" class="px-card" style="display:none"></div>' : '') + body +
      '<div class="px-note">상권에 마우스를 올리면 점수·서울 순위·4개 영역 점수가 나옵니다. 휠로 확대·축소, 끌어서 이동합니다.</div>';
    panel.querySelectorAll('.px-li').forEach(function (btn) {   // 상위 5곳 목록을 누르면 그 상권 카드
      btn.addEventListener('click', function () { window.spotfitPick(btn.getAttribute('data-code')); });
    });
    panel.style.display = 'block'; lgOverview.style.display = 'none'; lgDetail.style.display = 'flex';
    setOverviewUi(false, name);
    moveTo(d.bounds, DETAIL_PAD);
  }
  gj.eachLayer(function (l) {
    l.on('click', function (e) { L.DomEvent.stopPropagation(e); show(l.feature.properties.name); });
  });
  window.spotfitReset = reset;
})();
{% endraw %}{% endmacro %}""")

    def __init__(self, map_obj, gj, data, seoul, parts: dict, extra: dict | None = None):
        super().__init__()
        self._js = {**(extra or {"__UPGRADE__": "false", "__LEGENDS__": "{}"}),
                    "__MAP__": map_obj.get_name(), "__GJ__": gj.get_name(), "__DATA__": json.dumps(data, ensure_ascii=False),
                    "__SEOUL__": json.dumps(seoul), "__PAD__": json.dumps(PAD_OVERVIEW),
                    "__LABELS_TILES__": json.dumps(TILES_LABELS), "__TILES__": json.dumps(TILES), "__ATTR__": json.dumps(TILES_ATTR),
                    **{f"__{k.upper()}__": (v.get_name() if v is not None else "null") for k, v in parts.items()}}

    def render(self, **kwargs):
        text = str(self._template.module.__dict__["script"](self, kwargs))   # 템플릿의 script 매크로 내용
        for k, v in self._js.items():
            text = text.replace(k, v)
        self.get_root().script.add_child(folium.Element(text), name=self.get_name())


# ---------------------------------------------------------------- 지도 그리기


def gu_map(shown: pd.DataFrame, seoul: pd.DataFrame, areas, title: str, note: str = "", brand: bool = False,
           upgrade: bool = False) -> folium.Map:
    """자치구 픽셀 지도(folium.Map).

    shown = 지도에 칠할 상권(조건 적용), seoul = 서울 전체 같은 업종(순위 기준),
    areas = 상권 경계 목록 [{trdar_code, lon, lat, geometry}, ...] (김지영/claude_dashboard/data/areas.geojson.json).
    upgrade = True면 업그레이드 시안: 구 색을 서울 중앙값과의 차이로, 이름표에 차이, 설명에 구 순위, 표본 적은 구는 점선.
    """
    gus, river, outside, seoul_bounds, label_at, _, ring = _base()
    areas = list(areas)
    d = prepare(shown, seoul, points_of(areas))
    seoul_median = float(seoul["score_total"].median()) if upgrade and seoul["score_total"].notna().any() else None
    g = gu_summary(d, seoul_median)
    n_seoul = int(seoul["score_total"].notna().sum())
    gus = copy.deepcopy(gus)
    for f in gus:
        name = f["properties"]["name"]
        if name in g.index:
            r = g.loc[name]
            f["properties"].update({"median": f"{r['median']:.1f}점", "n": f"{int(r['n'])}곳", "best": r["best"], "color": COLORS[int(r["cls"])],
                                    "label": f"{r['median']:.0f}", "small": False})
            if seoul_median is not None:
                f["properties"].update({
                    "color": DIFF_COLORS[int(r["cls2"])], "label": f"{r['diff']:+.1f}" + ("*" if r["small"] else ""), "small": bool(r["small"]),
                    "diff": f"{r['diff']:+.1f}점 ({DIFF_LABELS[int(r['cls2'])]})", "rank": f"{len(g)}개 구 중 {int(r['rank'])}위",
                    "n": f"{int(r['n'])}곳" + (f" (참고용: {MIN_GU}곳 미만)" if r["small"] else "")})
        else:
            f["properties"].update({"median": "-", "n": "0곳", "best": "조건에 맞는 점수 상권 없음", "color": NO_SCORE, "label": "-",
                                    "small": False, "diff": "-", "rank": "-"})
    legends, keys = {}, []
    if upgrade:   # [업그레이드] 구 색 기준 버튼: 기준마다 색·이름표·설명을 구에 넣어 두고 화면에서 바꾼다
        per, legends, keys = metric_views(d, seoul, [f["properties"]["name"] for f in gus])
        for f in gus:
            f["properties"]["m"] = per[f["properties"]["name"]]
    if seoul_median is not None:
        tip_fields = ["name", "median", "diff", "rank", "n", "best"]
        tip_alias = ["", "점수 중앙값", f"서울 중앙값 {seoul_median:.1f}점 대비", "구 순위", "점수 상권 수", "최고 상권"]
    else:
        tip_fields, tip_alias = ["name", "median", "n", "best"], ["", "점수 중앙값", "점수 상권 수", "최고 상권"]

    def gu_style(f):
        style = {"fillColor": f["properties"]["color"], "fillOpacity": 1, "color": "#FFFFFF", "weight": 2.5}
        if f["properties"].get("small"):   # 표본 적은 구: 색을 흐리게 + 검은 점선 테두리
            style.update({"fillOpacity": 0.4, "color": INK, "weight": 2, "dashArray": "6 4"})
        return style

    m = folium.Map(location=[37.565, 126.985], zoom_start=11, min_zoom=10, max_zoom=17, tiles=None, zoom_snap=0.25)
    m.fit_bounds(seoul_bounds, padding_top_left=PAD_OVERVIEW["paddingTopLeft"], padding_bottom_right=PAD_OVERVIEW["paddingBottomRight"])
    out_layer = folium.GeoJson({"type": "FeatureCollection", "features": outside}, name="서울 밖", interactive=False,
                               style_function=lambda f: {"fillColor": OUTSIDE_FILL, "fillOpacity": 1, "color": OUTSIDE_LINE, "weight": 1.5,
                                                         "opacity": 1}).add_to(m)
    shadow = folium.PolyLine([(y - 0.0012, x + 0.0015) for y, x in ring], color=YELLOW, weight=7, opacity=1, interactive=False).add_to(m)
    gj = folium.GeoJson(
        {"type": "FeatureCollection", "features": gus}, name="자치구",
        style_function=gu_style,
        # 업그레이드 시안은 기준 버튼에 따라 설명이 바뀌므로 화면 스크립트(ClickDetail)가 설명을 붙인다
        tooltip=None if upgrade else folium.GeoJsonTooltip(fields=tip_fields, aliases=tip_alias, class_name="px-tip"),
    ).add_to(m)
    river_layer = folium.GeoJson(river, interactive=False,
                                 style_function=lambda f: {"fillColor": RIVER, "fillOpacity": 1, "color": RIVER, "weight": 0.5,
                                                           "opacity": 1}).add_to(m)
    ring_line = folium.PolyLine(ring, color=INK, weight=4, opacity=1, interactive=False).add_to(m)

    labels = folium.FeatureGroup(name="구 이름", control=False).add_to(m)
    for f in gus:
        y, x = label_at[f["properties"]["name"]]
        neg = ' class="neg"' if str(f["properties"]["label"]).startswith("-") and f["properties"]["label"] != "-" else ""
        label = (f'<div class="gu-label" data-gu="{f["properties"]["name"]}">{f["properties"]["name"]}'
                 f'<span{neg}>{f["properties"]["label"]}</span></div>')
        folium.Marker([y, x], icon=folium.DivIcon(html=label, icon_size=(90, 22), icon_anchor=(45, 11), class_name="gu-label-wrap"),
                      interactive=False, z_index_offset=1000 if upgrade else 0).add_to(labels)   # 업그레이드: 이름표를 핀보다 위에

    pins = folium.FeatureGroup(name="상위 10곳", control=False).add_to(m)
    top = d.dropna(subset=["score"]).sort_values("score", ascending=False, kind="mergesort").head(TOP_PINS)
    for i, r in enumerate(top.itertuples(), start=1):
        rank = "" if pd.isna(r.seoul_rank) else f" · 서울 {int(r.seoul_rank)}위"
        folium.Marker([r.lat, r.lon], icon=folium.DivIcon(html=f'<div style="position:relative">{PIN}<span class="px-rank">{i}</span></div>',
                                                         icon_size=(30, 39), icon_anchor=(15, 39), class_name="px-pin"),
                      tooltip=folium.Tooltip(f"<b>{i}위 {html.escape(str(r.trdar_name))}</b> · {r.gu_name}<br>종합 {r.score:.1f}점{rank}",
                                             class_name="px-tip")).add_to(pins)

    real_layer = None
    if upgrade and _real_gu() is not None:   # 실제 구 경계: 처음엔 안 보이고, 구 상세 화면에서만 테두리로 보인다
        real_layer = folium.GeoJson({"type": "FeatureCollection", "features": _real_gu()}, name="실제 구 경계", interactive=False,
                                    style_function=lambda f: {"opacity": 0, "fillOpacity": 0, "color": INK, "weight": 1.5}).add_to(m)
    meds = raw_medians(seoul) if upgrade else None
    geometry = {a["trdar_code"]: a["geometry"] for a in areas}
    ClickDetail(m, gj, detail_data(d, g, n_seoul, geometry, seoul_median, meds), seoul_bounds,
                {"outside": out_layer, "river": river_layer, "shadow": shadow, "labels": labels, "pins": pins,
                 "realgu": real_layer, "ring": ring_line},
                {"__UPGRADE__": "true" if upgrade else "false", "__LEGENDS__": json.dumps(legends, ensure_ascii=False)}).add_to(m)
    _decorate(m, g, title, note, brand, seoul_median, keys, legends)
    return m


def gu_map_html(shown: pd.DataFrame, seoul: pd.DataFrame, areas, title: str, note: str = "", brand: bool = False,
                upgrade: bool = False) -> str:
    """gu_map을 한 장짜리 HTML 문자열로 (marimo에서는 mo.iframe으로 띄운다)."""
    return gu_map(shown, seoul, areas, title, note, brand, upgrade).get_root().render()


def _decorate(m: folium.Map, g: pd.DataFrame, title: str, note: str, brand: bool, seoul_median: float | None = None,
              keys: list | None = None, legends: dict | None = None) -> None:
    keys, legends = keys or [], legends or {}
    if g.empty:
        legend_overview = '<div style="font-size:12px">조건에 맞는 점수 상권이 없습니다.</div>'
    elif "total" in legends:   # [업그레이드] 기준 버튼에 따라 바뀌는 범례
        legend_overview = f'<div id="legend-metric" style="display:flex;flex-direction:column;gap:6px">{legends["total"]}</div>'
    elif seoul_median is not None:
        counts = g["cls2"].value_counts()
        spread = g["median"].max() - g["median"].min()
        legend_overview = (
            f'<div style="font-size:12px;color:#5A5446">서울 같은 업종 중앙값 <b style="color:{INK}">{seoul_median:.1f}점</b>과의 차이</div>'
            + "".join(f'<div class="lg-row"><span style="background:{DIFF_COLORS[c]}"></span>{DIFF_LABELS[c]}'
                      f'<em class="lg-n">{int(counts.get(c, 0))}개 구</em></div>' for c in range(4, -1, -1))
            + f'<div style="font-size:11px;color:#5A5446">가장 높은 구와 낮은 구의 차이 {spread:.1f}점 · 이름표 숫자 = 차이</div>'
            + (f'<div class="lg-row"><span style="background:{DIFF_COLORS[3]};opacity:0.5;border-style:dashed"></span>'
               f'흐린 색·점선 = 점수 상권 {MIN_GU}곳 미만 (참고용, 숫자 옆 *)</div>' if g["small"].any() else "")
            + (f'<div class="px-warn" style="margin:2px 0 0">구 {int(g["small"].sum())}개가 참고용이라 이 업종은 구끼리 비교하기 어렵습니다</div>'
               if g["small"].mean() >= 0.5 else ""))
    else:
        ranges = g.groupby("cls")["median"].agg(["min", "max"])
        legend_overview = "".join(
            f'<div class="lg-row"><span style="background:{COLORS[c]}"></span>{ranges.loc[c, "min"]:.1f} ~ {ranges.loc[c, "max"]:.1f}점</div>'
            for c in sorted(ranges.index, reverse=True))
    gradient = ", ".join(f"{c} {int(t * 100)}%" for t, c in SCALE)
    pin_row = (f'<div class="lg-row" style="margin-top:4px"><i>{pin_svg(12)}</i>'
               f'{"종합 점수 " if legends else ""}상위 {TOP_PINS}곳 상권</div>')
    toolbar = ""
    if keys:   # [업그레이드] 구 색 기준 버튼 (서울 전체 화면에서만 보임)
        toolbar = ('<div id="metric-bar" class="px-box" role="group" aria-label="구 색 기준">'
                   '<div class="mb-title">구 색 기준</div><div class="mb-btns">'
                   + "".join(f'<button type="button" class="px-mbtn" data-key="{k}" aria-pressed="{"true" if k == "total" else "false"}">'
                             f'{html.escape(lbl)}</button>' for k, lbl in keys)
                   + '</div></div>')
    crumb = '<div id="crumb" class="px-crumb"><b>서울 전체</b></div>' if keys else ""
    no_row = f'<div class="lg-row"><span style="background:{NO_SCORE}"></span>점수 없음</div>'
    brand_html = (f'<div style="font-family:\'Press Start 2P\',monospace;font-size:18px;color:{BLUE};text-shadow:3px 3px 0 {YELLOW};'
                  'margin-bottom:6px">SPOTFIT</div>') if brand else ""
    m.get_root().header.add_child(folium.Element(f"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  html, body {{ background: {CREAM}; }}
  .leaflet-container {{ background: {CREAM} !important; font-family: 'Malgun Gothic', '맑은 고딕', 'Noto Sans KR', sans-serif; }}
  .leaflet-overlay-pane svg path {{ shape-rendering: crispEdges; }}
  .leaflet-interactive {{ cursor: pointer; }}
  .leaflet-interactive:focus {{ outline: none; }}   /* 클릭한 구 둘레에 브라우저가 그리는 사각형 테두리 끄기 */
  .gu-label {{ display: inline-flex; gap: 5px; align-items: center; padding: 1px 6px; background: {CARD}; color: {INK};
    border: 2px solid {INK}; box-shadow: 2px 2px 0 {INK}; font-weight: 700; font-size: 12px; white-space: nowrap; pointer-events: none; }}
  .gu-label span {{ font-family: 'Press Start 2P', monospace; font-size: 9px; color: {BLUE}; }}
  .gu-label span.neg {{ color: #8A6400; }}   /* 서울 중앙값보다 낮은 구 (업그레이드 시안) */
  .gu-label-wrap {{ display: flex; justify-content: center; align-items: center; pointer-events: none; }}
  .px-rank {{ position: absolute; left: 22px; top: -6px; min-width: 20px; padding: 3px 4px; background: {INK}; color: #fff;
    font-family: 'Press Start 2P', monospace; font-size: 9px; text-align: center; }}
  .px-num-wrap {{ pointer-events: none; }}
  .px-num {{ display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%;
    background: {INK}; color: #fff; font-size: 12px; font-weight: 700; opacity: 0.88; }}
  .leaflet-tooltip.px-tip {{ background: {CARD}; color: {INK}; border: 3px solid {INK}; border-radius: 0; box-shadow: 3px 3px 0 {INK};
    font-size: 13px; padding: 6px 10px; }}
  .leaflet-tooltip.px-tip::before {{ display: none; }}
  .leaflet-bar {{ border: 3px solid {INK} !important; border-radius: 0 !important; box-shadow: 3px 3px 0 {INK}; }}
  .leaflet-bar a {{ border-radius: 0 !important; color: {INK}; background: {CARD}; font-family: 'Press Start 2P', monospace; font-size: 14px; }}
  .px-box {{ position: fixed; z-index: 1000; background: {CARD}; color: {INK}; border: 4px solid {INK}; box-shadow: 6px 6px 0 {INK};
    font-family: 'Malgun Gothic', '맑은 고딕', 'Noto Sans KR', sans-serif; }}
  .lg-row {{ display: flex; align-items: center; gap: 8px; }}
  .lg-row span {{ width: 16px; height: 16px; border: 2px solid {INK}; display: inline-block; box-sizing: border-box; }}
  .lg-row i {{ display: inline-block; width: 16px; text-align: center; font-style: normal; }}
  .lg-bar {{ height: 12px; border: 2px solid {INK}; background: linear-gradient(90deg, {gradient}); }}
  .lg-ticks {{ display: flex; justify-content: space-between; font-size: 11px; color: #5A5446; }}
  #gu-panel {{ display: none; top: 104px; left: 14px; width: 300px; padding: 12px 14px; font-size: 14px; max-height: calc(100vh - 130px);
    overflow-y: auto; box-sizing: border-box; }}
  #gu-panel h2 {{ margin: 8px 0 8px; font-size: 20px; color: {BLUE}; }}
  .px-back {{ min-height: 40px; padding: 0 12px; font: inherit; font-weight: 700; color: {INK}; background: {YELLOW};
    border: 3px solid {INK}; box-shadow: 3px 3px 0 {INK}; cursor: pointer; }}
  .px-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }}
  .px-stats div {{ background: #FFF3C4; border: 2px solid {INK}; padding: 4px 8px; }}
  .px-stats small {{ display: block; font-size: 12px; color: #5A5446; }}
  .px-stats b {{ font-size: 18px; }}
  .px-sub {{ font-size: 12px; color: #5A5446; margin-bottom: 4px; }}
  .px-top {{ list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 6px; }}
  .px-top li {{ display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; grid-template-rows: auto auto; column-gap: 8px;
    padding: 6px 8px; background: #FFFFFF; border: 2px solid {INK}; }}
  .px-top li b {{ grid-row: span 2; font-family: 'Press Start 2P', monospace; font-size: 11px; align-self: center; }}
  .px-top li span {{ font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .px-top li em {{ font-style: normal; font-weight: 700; color: {BLUE}; }}
  .px-top li small {{ grid-column: 2 / 4; font-size: 12px; color: #5A5446; }}
  .px-note {{ font-size: 12px; color: #5A5446; }}
  .px-cmp {{ font-size: 13px; margin: -2px 0 8px; }}
  .px-cmp b {{ color: {BLUE}; }}
  .px-warn {{ font-size: 12px; margin: -4px 0 8px; padding: 4px 8px; border: 2px dashed {INK}; background: #FFFFFF; }}
  .lg-n {{ margin-left: auto; padding-left: 10px; font-style: normal; font-size: 12px; color: #5A5446; }}
  /* [업그레이드] 상권 상세 카드 */
  .px-hint {{ font-size: 12px; margin: 0 0 10px; padding: 6px 8px; border: 2px dashed #B9AE8F; color: #5A5446; }}
  .px-card {{ margin: 0 0 12px; padding: 8px 10px; background: #FFFFFF; border: 3px solid {INK}; box-shadow: 3px 3px 0 {INK}; }}
  .px-card-h {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }}
  .px-card-h b {{ font-size: 16px; }}
  .px-x {{ min-width: 32px; min-height: 32px; font: inherit; font-size: 18px; line-height: 1; background: {CARD}; color: {INK};
    border: 2px solid {INK}; cursor: pointer; }}
  .px-big {{ margin: 6px 0 8px; font-size: 13px; }}
  .px-big b {{ font-size: 20px; color: {BLUE}; }}
  .px-bar {{ display: grid; grid-template-columns: 44px minmax(0, 1fr) 58px; align-items: center; gap: 6px; margin: 4px 0; font-size: 12px; }}
  .px-bar div {{ position: relative; height: 12px; background: #EFE6CC; border: 2px solid {INK}; }}
  .px-bar i {{ display: block; height: 100%; }}
  .px-bar u {{ position: absolute; left: 50%; top: -4px; bottom: -4px; border-left: 2px dashed {INK}; }}
  .px-bar em {{ font-style: normal; font-weight: 700; text-align: right; white-space: nowrap; }}
  .px-raw {{ width: 100%; margin-top: 8px; border-collapse: collapse; font-size: 12px; }}
  .px-raw th {{ text-align: left; font-weight: 700; padding: 3px 4px; background: #FFF3C4; border-bottom: 2px solid {INK}; }}
  .px-raw td {{ padding: 3px 4px; border-bottom: 1px solid #E8DDBF; vertical-align: top; }}
  .px-raw td:not(:first-child), .px-raw th:not(:first-child) {{ text-align: right; white-space: nowrap; }}
  .px-li {{ all: unset; box-sizing: border-box; width: 100%; cursor: pointer; display: grid; grid-template-columns: 20px minmax(0, 1fr) auto;
    grid-template-rows: auto auto; column-gap: 8px; }}
  .px-li:hover span, .px-li:focus-visible span {{ text-decoration: underline; }}
  .px-li:focus-visible {{ outline: 3px solid {BLUE}; outline-offset: 4px; }}
  .px-top li:has(.px-li) {{ display: block; }}
  .px-li b {{ grid-row: span 2; font-family: 'Press Start 2P', monospace; font-size: 11px; align-self: center; }}
  .px-li span {{ font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .px-li em {{ font-style: normal; font-weight: 700; color: {BLUE}; }}
  .px-li small {{ grid-column: 2 / 4; font-size: 12px; color: #5A5446; }}
  /* [업그레이드] 구 색 기준 버튼 · 위치 표시 · 마우스 올리면 떠오르는 구 */
  #metric-bar {{ top: 14px; right: 14px; padding: 8px 10px; max-width: 470px; }}
  .mb-title {{ font-size: 12px; font-weight: 700; margin-bottom: 6px; }}
  .mb-btns {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .px-mbtn {{ min-height: 36px; padding: 0 12px; font: inherit; font-size: 13px; color: {INK}; background: {CARD};
    border: 3px solid {INK}; cursor: pointer; }}
  .px-mbtn[aria-pressed="true"] {{ background: {BLUE}; color: #FFFFFF; font-weight: 700; box-shadow: 3px 3px 0 {INK}; }}
  .px-mbtn:focus-visible {{ outline: 3px solid {YELLOW}; outline-offset: 2px; }}
  .lg-desc {{ font-size: 11px; color: #5A5446; line-height: 1.45; }}
  .lg-desc b {{ color: {INK}; }}
  .px-crumb {{ margin: 4px 0 2px; font-size: 13px; }}
  .px-crumb-btn {{ font: inherit; font-weight: 700; color: {BLUE}; background: none; border: 0; padding: 0; cursor: pointer; text-decoration: underline; }}
  .gu-hover {{ filter: drop-shadow(4px 4px 0 rgba(43, 42, 38, 0.85)); transform: translate(-3px, -3px); }}
</style>"""))
    note_html = f'<div style="font-size:12px;color:#5A5446">{html.escape(note)}</div>' if note else ""
    m.get_root().html.add_child(folium.Element(f"""
<div class="px-box" style="top:14px;left:60px;padding:10px 14px;max-width:calc(100% - 110px)">
  {brand_html}
  <div style="font-size:14px;font-weight:700">{html.escape(title)}</div>
  {crumb}
  <div style="font-size:12px;color:#5A5446">구를 클릭하면 그 구의 상권을 자세히 봅니다</div>
  {note_html}
</div>
{toolbar}
<div id="gu-panel" class="px-box" aria-live="polite"></div>
<div class="px-box" style="bottom:20px;right:14px;padding:10px 12px;font-size:13px;max-width:330px">
  <div id="legend-overview" style="display:flex;flex-direction:column;gap:6px">
    {"" if legends else ("<b>구별 점수 중앙값</b>" if seoul_median is not None else "<b>구별 점수 중앙값 (구끼리 순위 5단계)</b>")}
    {legend_overview}
    {no_row}
    {pin_row}
  </div>
  <div id="legend-detail" style="display:none;flex-direction:column;gap:6px;min-width:190px">
    <b>상권 종합 점수 (진할수록 높음)</b>
    <div class="lg-bar"></div>
    <div class="lg-ticks"><span>0</span><span>50</span><span>100</span></div>
    <div class="lg-row"><span style="background:{AREA_NO_SCORE};opacity:0.6"></span>점수 없음 (점포 5개 미만 등)</div>
    <div class="lg-row"><span class="px-num" style="display:flex;width:16px;height:16px;font-size:10px;border:0;border-radius:50%">1</span>이 구의 상위 {TOP_GU}곳</div>
    <div style="font-size:11px;color:#5A5446">배경 지도는 인터넷이 필요합니다</div>
  </div>
</div>"""))
