"""STEP 6 EDA·시각화와 최종 산출물 대시보드(HTML 파일 하나)를 만든다.

입력은 모두 읽기만 한다: 김지영/step2_3 · step4_dashboard · step5_design · claude_dashboard 산출물과
seoul-commercial-analysis/data/metadata 의 수집 메타데이터.

출력
- data/STEP6_시각화_설계표.csv   STEP 6 시각화 7종의 목적 · 데이터 · 방법 · 기대 인사이트 · 확인한 결과
- data/stage6_meta.json         개수, 확인한 결과의 숫자, 입력 sha256
- report/SpotFit_최종산출물_대시보드_2025.html   설치 없이 브라우저로 여는 최종 대시보드

몇 번 실행해도 바이트까지 같은 결과가 나온다(실행 시각을 기록하지 않는다).

실행 (팀 저장소 루트에서):
    uv run --project "김지영/step4_dashboard" python "김지영/step6_final/build_final.py"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ME = HERE.parent
ROOT = ME.parent
WEB = HERE / "web"
HTML_NAME = "SpotFit_최종산출물_대시보드_2025.html"
DESIGN_NAME = "STEP6_시각화_설계표.csv"
META_NAME = "stage6_meta.json"
VERSION = "v1.0 (2026-11-21)"
DEFAULT_INDUSTRY = "CS100010"  # 커피-음료. STEP 4 대시보드 기본값과 같다
AREA_KEYS = ["sales", "competition", "stability", "demand"]
DEFAULT_WEIGHTS = {"sales": 30, "competition": 25, "stability": 15, "demand": 30}

INPUTS = {
    "scores": ME / "step4_dashboard/data/상권_업종_비교점수_2025.parquet",
    "availability": ME / "step4_dashboard/data/업종별_점수_가능여부.csv",
    "score_design": ME / "step4_dashboard/data/점수_설계표.csv",
    "stage4_meta": ME / "step4_dashboard/data/stage4_meta.json",
    "types": ME / "step5_design/data/상권_유형_2025.parquet",
    "questions": ME / "step5_design/data/검사_문항.csv",
    "type_table": ME / "step5_design/data/유형표.csv",
    "sg_weights": ME / "step5_design/data/유형별_가중치.csv",
    "step5_design": ME / "step5_design/data/STEP5_설계표.csv",
    "stage5_meta": ME / "step5_design/data/stage5_meta.json",
    "geometry": ME / "claude_dashboard/data/areas.geojson.json",
    "backdrop": ME / "claude_dashboard/data/backdrop.parquet",
    "shared_meta": ME / "claude_dashboard/data/meta.json",
    "annual": ME / "step2_3/data/annual_features.csv.gz",
    "context": ME / "step2_3/data/trdar_quarter_context.csv.gz",
    "dim": ME / "step2_3/data/dim_trdar.csv.gz",
    "bridge": ME / "step2_3/data/semas_spatial_bridge.csv.gz",
    "semas_counts": ME / "step2_3/data/semas_q4_industry_counts.csv.gz",
    "features": ME / "step2_3/feature_dictionary.csv",
    "schema": ME / "step2_3/table_schema.csv",
    "manifest23": ME / "step2_3/manifest.json",
    "catalog": ROOT / "seoul-commercial-analysis/data/metadata/data_catalog.csv",
    "dictionary": ROOT / "seoul-commercial-analysis/data/metadata/data_dictionary.csv",
}
WEB_FILES = ["template.html", "style.css", "core.js", "app.js"]

# 원본 컬럼 → STEP 2 표준 컬럼. 출처: 김지영/STEP2(Codex).md 3장 '입력 자료와 컬럼 표준화'
STANDARD = {
    "K01": {"기준_년분기_코드": "quarter", "상권_코드": "trdar_code", "서비스_업종_코드": "industry_code",
            "당월_매출_금액": "sales_amount", "당월_매출_건수": "sales_count",
            "주중_매출_금액": "weekday_sales", "주말_매출_금액": "weekend_sales",
            "남성_매출_금액": "male_sales", "여성_매출_금액": "female_sales",
            **{f"시간대_{a}~{b}_매출_금액": f"time_{a}_{b}_sales" for a, b in [("00", "06"), ("06", "11"), ("11", "14"), ("14", "17"), ("17", "21"), ("21", "24")]},
            **{f"시간대_건수~{b}_매출_건수": f"time_{a}_{b}_count" for a, b in [("00", "06"), ("06", "11"), ("11", "14"), ("14", "17"), ("17", "21"), ("21", "24")]},
            **{f"연령대_{a}_매출_금액": f"age_{a}_sales" for a in ["10", "20", "30", "40", "50"]},
            "연령대_60_이상_매출_금액": "age_60_plus_sales"},
    "K02": {"stdr_yyqu_cd": "quarter", "trdar_cd": "trdar_code", "svc_induty_cd": "industry_code",
            "similr_induty_stor_co": "store_count", "stor_co": "independent_store_count", "frc_stor_co": "franchise_store_count",
            "opbiz_stor_co": "open_count", "clsbiz_stor_co": "close_count", "opbiz_rt": "reported_open_rate", "clsbiz_rt": "reported_close_rate"},
    "K03": {"TRDAR_CD": "trdar_code", "TRDAR_CD_N": "trdar_name", "TRDAR_SE_C": "trdar_type_code", "TRDAR_SE_1": "trdar_type",
            "SIGNGU_CD": "gu_code", "SIGNGU_CD_": "gu_name", "ADSTRD_CD": "admin_dong_code", "ADSTRD_CD_": "admin_dong_name",
            "RELM_AR": "reported_area_m2"},
    "K04": {"기준_년분기_코드": "quarter", "상권_코드": "trdar_code", "총_유동인구_수": "floating_population",
            **{f"연령대_{a}_유동인구_수": f"floating_age_{a}" for a in ["10", "20", "30", "40", "50"]},
            "연령대_60_이상_유동인구_수": "floating_age_60_plus",
            **{f"시간대_{a}_{b}_유동인구_수": "floating_peak_time_share 계산" for a, b in [("00", "06"), ("06", "11"), ("11", "14"), ("14", "17"), ("17", "21"), ("21", "24")]}},
    "K05": {"기준_년분기_코드": "quarter", "상권_코드": "trdar_code", "집객시설_수": "facility_count"},
    "K06": {"기준_년분기_코드": "quarter", "상권_코드": "trdar_code", "총_직장_인구_수": "worker_population"},
    "K07": {"기준_년분기_코드": "quarter", "상권_코드": "trdar_code", "총_상주인구_수": "resident_population"},
    "S01": {"상가업소번호": "store_id", "상권업종소분류코드": "semas_industry_code", "경도": "공간 조인 (경도)", "위도": "공간 조인 (위도)"},
    "S02": {"소분류코드": "semas_industry_code 해석", "소분류명": "소상공인 업종명 표시"},
}

# 집객시설 세부 항목 → 화면 묶음 5개. 세부 항목 합이 총수보다 작은 나머지는 '세부 미기재'로 따로 둔다.
FACILITY_GROUPS = {
    "교통": ["지하철_역", "버스_정거장", "철도_역", "버스_터미널", "공항"],
    "의료": ["종합병원", "일반_병원", "약국"],
    "생활·행정": ["관공서", "은행", "슈퍼마켓"],
    "교육": ["유치원", "초등학교", "중학교", "고등학교", "대학교"],
    "쇼핑·문화·숙박": ["백화점", "극장", "숙박_시설"],
}

# 각 수집 자료가 이번 분석에서 맡은 역할 (STEP 2~5 산출물 기준)
DATASET_ROLE = {
    "S01": "점포 좌표 → 상권 공간 조인 보조 집계 (점수에는 쓰지 않음)",
    "S02": "소상공인 업종코드 해석",
    "K01": "매출 잠재력 점수, 상권 E/P, 매출 히트맵",
    "K02": "점포 수 · 개폐업 → 경쟁 · 안정성 점수, 업종 분포 지도",
    "K03": "상권 경계 · 면적 → 지도, 면적당 밀도",
    "K04": "유동인구 → 경쟁 분모, 수요 점수, 상권 L/V",
    "K05": "집객시설 → STEP 6 시각화 5 (점수에는 쓰지 않음)",
    "K06": "직장인구 → 수요 점수, 상권 L/V",
    "K07": "상주인구 → 수요 점수, 상권 L/V",
}


# ---------------------------------------------------------------- 공통


def sha256(path: Path) -> str:
    """출처: 김지영/step4_dashboard/build_scores.py sha256"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprints() -> dict[str, str]:
    paths = list(INPUTS.values()) + [WEB / name for name in WEB_FILES]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def clean(value, nd: int | None = None):
    """JSON에 넣을 값. 결측은 None, nd가 0이면 정수, 그 밖에는 소수 nd자리."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and nd is None:
        return int(value)
    if isinstance(value, (float, np.floating, int, np.integer)):
        v = float(value)
        if math.isnan(v):
            return None
        if nd is None:
            return v
        return int(round(v)) if nd == 0 else round(v, nd)
    if pd.isna(value):
        return None
    return str(value)


def column(series: pd.Series, nd: int | None = None) -> list:
    return [clean(v, nd) for v in series.tolist()]


def spearman(x: pd.Series, y: pd.Series) -> float | None:
    """평균 순위(동점은 평균)의 피어슨 상관. 화면(core.js spearman)과 같은 규칙."""
    ok = x.notna() & y.notna()
    if ok.sum() < 3:
        return None
    rx, ry = x[ok].rank(), y[ok].rank()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def composite(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """STEP 4 규칙: 자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균. 출처: 김지영/step4_dashboard/views.py composite"""
    num = pd.Series(0.0, index=frame.index)
    den = pd.Series(0.0, index=frame.index)
    for key in AREA_KEYS:
        w = float(weights.get(key, 0))
        score = frame[f"score_{key}"]
        has = score.notna() & (w > 0)
        num = num + np.where(has, score * w, 0.0)
        den = den + np.where(has, w, 0.0)
    return (num / den).where(den > 0)


def read_inputs() -> dict:
    code = {"trdar_code": str, "industry_code": str, "gu_code": str, "admin_dong_code": str, "trdar_type_code": str}
    d = {
        "scores": pd.read_parquet(INPUTS["scores"]),
        "types": pd.read_parquet(INPUTS["types"]),
        "backdrop": pd.read_parquet(INPUTS["backdrop"]),
        "geometry": json.loads(INPUTS["geometry"].read_text(encoding="utf-8")),
        "annual": pd.read_csv(INPUTS["annual"], dtype=code),
        "context": pd.read_csv(INPUTS["context"], dtype=code),
        "dim": pd.read_csv(INPUTS["dim"], dtype=code),
        "bridge_rows": int(len(pd.read_csv(INPUTS["bridge"], usecols=[0]))),
        "semas_rows": int(len(pd.read_csv(INPUTS["semas_counts"], usecols=[0]))),
    }
    for key in ["availability", "score_design", "questions", "type_table", "sg_weights", "step5_design", "features", "schema", "catalog", "dictionary"]:
        d[key] = pd.read_csv(INPUTS[key], encoding="utf-8-sig", dtype={"업종코드": str})
    for key in ["stage4_meta", "stage5_meta", "shared_meta", "manifest23"]:
        d[key] = json.loads(INPUTS[key].read_text(encoding="utf-8"))
    return d


# ---------------------------------------------------------------- 지도 (경도·위도 → SVG 좌표, 0.1px 단위 정수)


class Projection:
    """서울 범위에서 쓰는 등장방형 투영. 가로 1000px 기준, 위도 중앙의 cos로 가로를 줄인다."""

    def __init__(self, geometry: list[dict], width: int = 1000, pad: int = 14):
        lons, lats = [], []
        for f in geometry:
            for ring in rings(f["geometry"]):
                for lon, lat in ring:
                    lons.append(lon)
                    lats.append(lat)
        self.lon_min, self.lon_max = min(lons), max(lons)
        self.lat_min, self.lat_max = min(lats), max(lats)
        self.pad = pad
        self.kx = (width - 2 * pad) / (self.lon_max - self.lon_min)
        self.ky = self.kx / math.cos(math.radians((self.lat_min + self.lat_max) / 2))
        self.width = width
        self.height = int(math.ceil((self.lat_max - self.lat_min) * self.ky + 2 * pad))

    def tenths(self, lon: float, lat: float) -> tuple[int, int]:
        x = (lon - self.lon_min) * self.kx + self.pad
        y = (self.lat_max - lat) * self.ky + self.pad
        return int(round(x * 10)), int(round(y * 10))

    def point(self, lon: float, lat: float) -> list[float]:
        x, y = self.tenths(lon, lat)
        return [x / 10, y / 10]


def rings(geom: dict) -> list:
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [ring for poly in geom["coordinates"] for ring in poly]
    raise ValueError(f"지원하지 않는 도형: {geom['type']}")


def fmt_tenths(t: int) -> str:
    """12 → '1.2', -5 → '-.5', 30 → '3' (SVG 경로를 짧게)"""
    whole, frac = divmod(abs(t), 10)
    s = (str(whole) if whole else "") + (f".{frac}" if frac else "")
    return ("-" if t < 0 else "") + (s or "0")


def svg_path(geom: dict, proj: Projection) -> str:
    parts = []
    for ring in rings(geom):
        pts = []
        for lon, lat in ring:
            p = proj.tenths(lon, lat)
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        if len(pts) < 3:
            continue
        x0, y0 = pts[0]
        steps = [f"{fmt_tenths(b[0] - a[0])},{fmt_tenths(b[1] - a[1])}" for a, b in zip(pts, pts[1:])]
        parts.append(f"M{fmt_tenths(x0)},{fmt_tenths(y0)}l" + " ".join(steps) + "z")
    return "".join(parts)


def build_map(backdrop: pd.DataFrame, proj: Projection) -> dict:
    grid = backdrop.loc[backdrop["kind"].eq("grid")].sort_values(["lat", "lon"], ascending=[False, True])
    size = int(round(0.0045 * proj.kx * 0.62 * 10))
    squares = []
    for lon, lat in zip(grid["lon"], grid["lat"]):
        x, y = proj.tenths(lon, lat)
        squares.append(f"M{fmt_tenths(x - size // 2)},{fmt_tenths(y - size // 2)}h{fmt_tenths(size)}v{fmt_tenths(size)}h{fmt_tenths(-size)}z")
    labels = backdrop.loc[backdrop["kind"].eq("label")].sort_values("gu_name")
    return {
        "w": proj.width, "h": proj.height, "grid": "".join(squares),
        "labels": [[*proj.point(lon, lat), name] for lon, lat, name in zip(labels["lon"], labels["lat"], labels["gu_name"])],
    }


# ---------------------------------------------------------------- 상권 · 업종


def area_frame(d: dict) -> pd.DataFrame:
    """상권 1,644곳(관광특구 제외). 점수표의 상권 속성 + STEP 5 유형 + 집객시설 묶음."""
    s = d["scores"]
    cols = ["trdar_code", "trdar_name", "gu_name", "trdar_type", "area_km2", "floating", "worker", "resident",
            "floating_density", "worker_density", "resident_density"]
    areas = s[cols].drop_duplicates("trdar_code").sort_values("trdar_code").reset_index(drop=True)
    if len(areas) != s["trdar_code"].nunique():
        raise ValueError("상권 속성이 업종마다 다릅니다")
    t = d["types"][["trdar_code", "type2", "lv", "ep", "lv_score", "ep_score", "lv_note", "ep_note"]]
    areas = areas.merge(t, on="trdar_code", how="left", validate="1:1")
    groups = s.pivot_table(index="trdar_code", columns="group", values="stores", aggfunc="sum").reindex(areas["trdar_code"]).fillna(0)
    for g in ["외식", "서비스", "소매"]:
        areas[f"stores_{g}"] = groups[g].to_numpy()
    fac = facility_frame(d["context"])
    return areas.merge(fac, on="trdar_code", how="left", validate="1:1")


def facility_frame(context: pd.DataFrame) -> pd.DataFrame:
    """2025Q4 집객시설. K05는 2021Q1 이후 값이 바뀌지 않아 어느 분기를 써도 같다. 세부 공백은 0으로 바꾸지 않고 '세부 미기재'로 남긴다."""
    q = context.loc[context["quarter"].eq(context["quarter"].max()) & ~context["is_tourist"].astype(bool)].copy()
    out = pd.DataFrame({"trdar_code": q["trdar_code"], "facility_total": q["facility_count"]})
    known = pd.Series(0.0, index=q.index)
    for name, items in FACILITY_GROUPS.items():
        v = sum(q[f"facility_raw_{i}_수"].fillna(0) for i in items)
        out[f"fac_{name}"] = v.where(q["facility_count"].notna())
        known = known + v
    unknown = (q["facility_count"] - known)
    if (unknown.dropna() < 0).any():
        raise ValueError("집객시설 세부 항목 합이 총수보다 큰 상권이 있습니다")
    out["fac_세부 미기재"] = unknown
    return out


def industry_list(d: dict) -> list[dict]:
    s, av = d["scores"], d["availability"].set_index("업종코드")
    present = s.loc[s["stores"].gt(0)]
    out = []
    for code, g in present.groupby("industry_code", sort=True):
        r = av.loc[code]
        status = g["status"].value_counts()
        out.append({
            "code": code, "name": r["업종명"], "group": r["업종군"],
            "scored": r["점수 생성"] == "예", "salesSupplied": r["매출 제공"] == "예", "salesScored": r["매출 잠재력 점수"] == "예",
            "areas": int(r["점포가 있는 상권 수"]), "peers": int(r["비교 상권 수(평균 점포 5개 이상)"]),
            "salesPeers": int(r["매출 비교 상권 수(4개 분기 매출)"]), "cells": int(r["점수 대상 칸"]), "reason": r["사유"],
            "stores": round(float(g["stores"].sum()), 1),
            "status": {k: int(v) for k, v in status.sort_index().items()},
        })
    if len(out) != 100:
        raise ValueError(f"업종이 100개가 아닙니다: {len(out)}")
    return sorted(out, key=lambda r: (["외식", "서비스", "소매"].index(r["group"]), r["name"]))


def store_cells(d: dict, index: dict[str, int]) -> dict:
    """업종 분포 지도용: 업종마다 점포가 있는 상권의 [상권 번호], [평균 점포 수 × 10]."""
    s = d["scores"].loc[d["scores"]["stores"].gt(0)].sort_values(["industry_code", "trdar_code"])
    out = {}
    for code, g in s.groupby("industry_code", sort=True):
        out[code] = [[index[c] for c in g["trdar_code"]], [int(round(v * 10)) for v in g["stores"]]]
    return out


SALES_NOTES = ["", "4개 분기 매출이 모두 있지는 않음", "매출 미제공 업종", "업종 안 매출 비교 상권 30곳 미만"]


def score_cells(d: dict, index: dict[str, int]) -> dict:
    """점수 대상 20,522칸. 업종마다 열 단위로 담는다.

    영역 점수는 반올림하지 않는다: 소수 4자리로 줄이면 점수가 거의 같은 상권의 순서가 Python(STEP 4)과 달라진다(검증 8번).
    폐업률도 순위상관(시각화 4)이 Python과 같도록 소수 6자리로 둔다.
    """
    s = d["scores"].loc[d["scores"]["scored"]].sort_values(["industry_code", "trdar_code"])
    unknown = set(s["sales_note"].fillna("")) - set(SALES_NOTES)
    if unknown:
        raise ValueError(f"모르는 매출 결측 사유: {unknown}")
    out = {}
    for code, g in s.groupby("industry_code", sort=True):
        out[code] = {
            "a": [index[c] for c in g["trdar_code"]],
            "sa": column(g["score_sales"]), "co": column(g["score_competition"]),
            "st": column(g["score_stability"]), "de": column(g["score_demand"]),
            "n": column(g["stores"], 2), "op": column(g["opens"], 0), "cs": column(g["closes"], 0),
            "sm": column(g["sales_month"], 0), "cp": column(g["competition"], 6), "cl": column(g["close_pct_shrunk"], 6),
            "pf": column(g["pct_floating"], 1), "pw": column(g["pct_worker"], 1), "pr": column(g["pct_resident"], 1),
            "sn": [SALES_NOTES.index(v) for v in g["sales_note"].fillna("")],
        }
    return out


# ---------------------------------------------------------------- STEP 6 시각화 집계


def sales_heat(d: dict, names: dict[str, str]) -> dict:
    """시각화 2: 매출 상위 20개 상권 · 25개 자치구 × 서울 매출 상위 10개 업종의 매출 비중(%)."""
    dim = d["dim"].loc[~d["dim"]["is_tourist"].astype(bool), ["trdar_code", "trdar_name", "gu_name"]]
    a = d["annual"].merge(dim, on="trdar_code", how="inner")
    a = a.loc[a["annual_observed_sales"].notna()]
    top_ind = a.groupby("industry_code")["annual_observed_sales"].sum().sort_values(ascending=False).head(10).index.tolist()

    def matrix(key: str, label: str, rows: list) -> dict:
        tot = a.groupby(key)["annual_observed_sales"].sum()
        cell = a.loc[a["industry_code"].isin(top_ind)].pivot_table(index=key, columns="industry_code", values="annual_observed_sales", aggfunc="sum").reindex(index=rows, columns=top_ind).fillna(0)
        lead = a.groupby([key, "industry_code"])["annual_observed_sales"].sum().reset_index().sort_values([key, "annual_observed_sales"], ascending=[True, False]).drop_duplicates(key).set_index(key)
        return {
            "label": label,
            "rows": [label_of(r) for r in rows],
            "total": [round(float(tot[r]) / 1e8, 1) for r in rows],
            "share": [[round(float(cell.at[r, c]) / float(tot[r]) * 100, 2) for c in top_ind] for r in rows],
            "lead": [names[lead.at[r, "industry_code"]] for r in rows],
            "leadShare": [round(float(lead.at[r, "annual_observed_sales"]) / float(tot[r]) * 100, 2) for r in rows],
        }

    names_by_code = dim.set_index("trdar_code")
    by_area = a.groupby("trdar_code")["annual_observed_sales"].sum().sort_values(ascending=False)
    top_areas = by_area.head(20).index.tolist()
    gus = a.groupby("gu_name")["annual_observed_sales"].sum().sort_values(ascending=False).index.tolist()

    def label_of(r):
        return f"{names_by_code.at[r, 'trdar_name']} ({names_by_code.at[r, 'gu_name']})" if r in names_by_code.index else r

    area_m = matrix("trdar_code", "상권", top_areas)
    area_m["codes"] = top_areas
    return {
        "industries": [names[c] for c in top_ind], "industryCodes": top_ind,
        "area": area_m, "gu": matrix("gu_name", "자치구", gus),
        "seoulTotal": round(float(a["annual_observed_sales"].sum()) / 1e12, 2),
    }


def store_density(d: dict, names: dict[str, str]) -> list[dict]:
    """시각화 3: 업종마다 점포가 있는 상권의 면적당 점포 수(개/㎢) 사분위."""
    s = d["scores"].loc[d["scores"]["stores"].gt(0)].copy()
    s["density"] = s["stores"] / s["area_km2"]
    out = []
    for code, g in s.groupby("industry_code", sort=True):
        q = g["density"].quantile([0.25, 0.5, 0.75])
        out.append({"code": code, "name": names[code], "group": g["group"].iloc[0], "n": int(len(g)),
                    "stores": round(float(g["stores"].sum()), 1),
                    "p25": round(float(q[0.25]), 2), "p50": round(float(q[0.5]), 2), "p75": round(float(q[0.75]), 2)})
    return out


def sales_close(d: dict) -> dict:
    """시각화 4 (대체): 같은 업종 안에서 점포당 월매출과 축소 추정 폐업률의 순위상관. 성장률은 2024년 자료가 없어 계산하지 않는다."""
    s = d["scores"].loc[d["scores"]["scored"] & d["scores"]["score_sales"].notna()]
    rho = {}
    for code, g in s.groupby("industry_code", sort=True):
        r = spearman(g["sales_month"], g["close_pct_shrunk"])
        if r is not None:
            rho[code] = round(r, 4)
    v = pd.Series(rho)
    return {"rho": rho, "industries": int(len(v)), "negative": int((v < 0).sum()), "median": round(float(v.median()), 4),
            "min": round(float(v.min()), 4), "max": round(float(v.max()), 4)}


def facility_summary(areas: pd.DataFrame) -> dict:
    """시각화 5: 상권 유형별 · 서울 전체 집객시설 구성, 집객시설이 많은 상권 15곳."""
    keys = list(FACILITY_GROUPS) + ["세부 미기재"]
    has = areas.loc[areas["facility_total"].notna()]
    rows = []
    for label, g in [("서울 전체", has)] + [(t, has.loc[has["trdar_type"].eq(t)]) for t in ["골목상권", "발달상권", "전통시장"]]:
        total = float(g["facility_total"].sum())
        rows.append({"label": label, "areas": int(len(g)), "total": int(total),
                     "values": [int(g[f"fac_{k}"].sum()) for k in keys],
                     "perArea": round(total / len(g), 1)})
    top = has.sort_values(["facility_total", "trdar_code"], ascending=[False, True]).head(15)
    seoul = rows[0]
    known = seoul["total"] - seoul["values"][-1]
    return {
        "keys": keys, "byType": rows,
        "top": [{"code": r["trdar_code"], "name": r["trdar_name"], "gu": r["gu_name"], "total": int(r["facility_total"]),
                 "values": [int(r[f"fac_{k}"]) for k in keys]} for _, r in top.iterrows()],
        "missingAreas": int(areas["facility_total"].isna().sum()),
        "unknownShare": round(seoul["values"][-1] / seoul["total"] * 100, 1),
        "transportShareKnown": round(seoul["values"][0] / known * 100, 1),
        "groups": {k: [i.replace("_", " ") for i in v] for k, v in FACILITY_GROUPS.items()},
    }


def mbti_compare(d: dict, areas: pd.DataFrame, industry: str) -> dict:
    """시각화 7 기본 업종의 확인값: 상권 유형(두 글자)마다 일치 상권 수, S 가중치와 G 가중치 상위 5곳이 몇 곳 겹치는지."""
    w = d["sg_weights"].set_index("구분")
    s = d["scores"].loc[d["scores"]["scored"] & d["scores"]["industry_code"].eq(industry)].merge(areas[["trdar_code", "type2"]], on="trdar_code")
    out = {}
    for t2 in ["LE", "LP", "VE", "VP"]:
        pool = s.loc[s["type2"].eq(t2)].copy()
        tops = {}
        for sg in ["S", "G"]:
            weights = {k: float(w.at[sg, n]) for k, n in zip(AREA_KEYS, ["매출 잠재력", "경쟁", "안정성", "수요"])}
            pool["total"] = composite(pool, weights)
            ranked = pool.loc[pool["total"].notna()].sort_values(["total", "stores", "trdar_code"], ascending=[False, False, True])
            tops[sg] = ranked["trdar_code"].head(5).tolist()
        out[t2] = {"pool": int(len(pool)), "S": tops["S"], "G": tops["G"], "overlap": len(set(tops["S"]) & set(tops["G"]))}
    return out


def map_concentration(d: dict, industry: str) -> dict:
    """시각화 1 확인값: 업종 점포가 상위 10% 상권에 몰린 비율과 상권별 최다 업종군."""
    g = d["scores"].loc[d["scores"]["industry_code"].eq(industry) & d["scores"]["stores"].gt(0)].sort_values("stores", ascending=False)
    k = max(1, int(math.ceil(len(g) * 0.1)))
    return {"areas": int(len(g)), "top10Areas": k, "top10Share": round(float(g["stores"].head(k).sum() / g["stores"].sum() * 100), 1)}


# ---------------------------------------------------------------- 문서 부분 (계획서 5장 2~5절)


def dataset_rows(d: dict) -> list[dict]:
    cat = d["catalog"]
    fresh = {f["dataset"]: f for f in d["shared_meta"]["freshness"]}
    out = []
    for ds, g in cat.groupby("dataset_id", sort=False):
        main = g.loc[g["row_count"].notna()].iloc[0]
        f = fresh.get(ds)
        if f is None:
            vintage = "2025-12-31 스냅숏" if ds == "S01" else ("2023-02-28 코드표" if ds == "S02" else ("현행 경계 (시점 구분 없음)" if ds == "K03" else "2025년 4개 분기"))
        elif f["last_observed_value_change"] is None:
            vintage = "2021Q1~2026Q2 값이 바뀌지 않음"
        else:
            q = f["last_observed_value_change"]
            vintage = f"마지막으로 값이 바뀐 분기 {q[:4]}Q{q[4]}"
        out.append({
            "id": ds, "name": main["dataset_name"], "provider": main["provider"], "url": main["source_url"],
            "format": " · ".join(sorted(set(g["file_format"]))), "rows": int(main["row_count"]), "cols": int(main["column_count"]),
            "period": main["reference_period"], "vintage": vintage, "role": DATASET_ROLE[ds],
        })
    return out


def column_rows(d: dict) -> list[list]:
    dic = d["dictionary"]
    out = []
    for r in dic.itertuples(index=False):
        std = STANDARD.get(r.dataset_id, {})
        if r.dataset_id == "K05" and str(r.column_name).endswith("_수") and r.column_name not in std and r.column_name != "집객시설_수":
            target = f"facility_raw_{r.column_name}"
        else:
            target = std.get(r.column_name, "")
        out.append([r.dataset_id, int(r.column_order), r.column_name, clean(r.meaning) or "", clean(r.unit) or "",
                    round(float(r.missing_rate) * 100, 2), int(r.distinct_count), clean(r.example_value) or "", target])
    return out


def table_rows(d: dict) -> list[dict]:
    """STEP 2·3 테이블 6개. 행 수는 실제 파일에서 다시 센 값."""
    schema = d["schema"]
    keys = schema.loc[schema["key"].astype(str).eq("True")].groupby("table")["column"].apply(lambda s: " + ".join(s))
    cols = schema.groupby("table")["column"].size()
    rows = {
        "dim_trdar": (len(d["dim"]), "상권 1,650곳의 이름 · 유형 · 자치구 · 면적 · 관광특구 여부"),
        "fact_trdar_industry_quarter": (d["stage4_meta"]["input_rows"]["fact"], "상권 × 업종 × 분기. 점포 · 개폐업 · 매출(왼쪽 결합)"),
        "trdar_quarter_context": (len(d["context"]), "상권 × 분기. 유동 · 직장 · 상주인구, 집객시설. fact와 분리 저장"),
        "annual_features": (len(d["annual"]), "상권 × 업종 × 연도. 연간 매출 · 평균 점포 · 개폐업"),
        "semas_spatial_bridge": (d["bridge_rows"], "상가업소 좌표 → 상권 경계 공간 조인 결과"),
        "semas_q4_industry_counts": (d["semas_rows"], "상권 × 소상공인 업종 점포 수 (2025Q4 보조 집계)"),
    }
    return [{"table": t, "rows": int(n), "cols": int(cols.get(t, 0)), "key": keys.get(t, ""), "desc": desc} for t, (n, desc) in rows.items()]


EXTRA_FEATURES = [
    ["competition", "상권×업종×연도", "같은 업종 평균 점포 수 ÷ (유동인구 ÷ 1,000)", "점포/유동 1,000명", "K02; K04", "STEP 4 경쟁 영역", "수요 대비 공급. 낮을수록 경쟁 점수가 높다 [가정]", "산출 (STEP 4)"],
    ["close_pct_shrunk", "상권×업종×연도", "(연간 폐업 + α) ÷ (평균 점포 + α ÷ 업종 폐업률) × 100, α = 13.19", "%", "K02", "STEP 4 안정성 영역", "작은 칸의 우연한 폐업률을 업종 평균 쪽으로 당긴 값. 1년치라 신뢰도 낮음", "산출 (STEP 4)"],
    ["score_demand", "상권×업종×연도", "면적당 유동 · 직장 · 상주인구의 같은 업종 내 백분위 3개 평균", "점(0~100)", "K03; K04; K06; K07", "STEP 4 수요 영역", "셋 중 하나라도 없으면 자료 없음 [가정]", "산출 (STEP 4)"],
    ["score_total", "상권×업종×연도", "Σ(가중치 × 영역 점수) ÷ Σ(자료가 있는 영역의 가중치)", "점(0~100)", "STEP 4 영역 점수", "업종 내 비교 종합 점수", "같은 업종의 다른 상권보다 지표가 상대적으로 낫다는 뜻. 창업 결과 예측 아님", "산출 (STEP 4)"],
    ["lv_score", "상권", "직장인구 ÷ 상주인구, 유동인구 ÷ 상주인구의 서울 안 백분위 평균", "점(0~100)", "K04; K06; K07", "STEP 5 상권 L/V", "서울 중앙값보다 크면 V(방문형) [가정]", "산출 (STEP 5)"],
    ["ep_score", "상권", "상권×업종 객단가의 같은 업종 내 백분위를 매출 건수로 가중 평균", "점(0~100)", "K01", "STEP 5 상권 E/P", "서울 중앙값보다 크면 P(프리미엄형) [가정]", "산출 (STEP 5)"],
]


def feature_rows(d: dict) -> list[list]:
    f = d["features"]
    rows = [[clean(v) or "" for v in r] for r in f[["variable", "level", "formula", "unit", "source", "purpose", "interpretation", "availability"]].itertuples(index=False)]
    return rows + EXTRA_FEATURES


# ---------------------------------------------------------------- STEP 6 설계표


def step6_design(c: dict, ind_name: str) -> pd.DataFrame:
    heat, dens, sc, fac, mb, conc = c["heat"], c["density"], c["salesClose"], c["facility"], c["mbti"], c["map"]
    top_dense = max(dens, key=lambda r: r["p50"])
    over_half = sum(1 for v in heat["area"]["leadShare"] if v > 50)
    overlap = " · ".join(f"{k} {v['overlap']}곳" for k, v in mb.items())
    rows = [
        [1, "서울시 상권별 업종 분포 지도", "업종이 서울 어디에 몰려 있는지, 상권마다 어떤 업종군이 중심인지 본다",
         "K02 점포 수(2025년 4개 분기 평균), K03 상권 경계", "상권 경계 지도. 선택 업종의 평균 점포 수 5단계, 또는 상권별 최다 업종군(외식 · 서비스 · 소매)",
         "업종마다 점포가 몰린 상권이 다르다. 점수는 업종 안에서 비교해야 한다",
         "구현", f"{ind_name}: 점포가 있는 상권 {conc['areas']:,}곳 중 상위 10%({conc['top10Areas']}곳)에 점포의 {conc['top10Share']}%"],
        [2, "상권별 추정매출 히트맵", "상권 총매출 순위가 입지가 아니라 특정 업종 쏠림을 보여 주는지 확인한다",
         "K01 추정매출(4개 분기 관측 합계, 관광특구 제외), K03 자치구", "매출 상위 20개 상권(또는 25개 자치구) × 서울 매출 상위 10개 업종의 행 내 매출 비중 히트맵",
         "총매출 상위 상권 상당수는 업종 하나가 매출 절반을 넘는다",
         "구현", f"매출 상위 20개 상권 중 {over_half}곳은 1위 업종이 매출의 50%를 넘음 (서울 합계 {heat['seoulTotal']}조원)"],
        [3, "업종별 점포 밀집도 비교", "업종마다 한 상권에 얼마나 빽빽하게 모이는지 비교한다",
         "K02 점포 수, K03 상권 면적(㎢)", "업종별 면적당 점포 수(개/㎢)의 25 · 50 · 75 백분위 막대(로그 축). 점포가 있는 상권만",
         "밀집도는 업종마다 크게 달라 같은 기준으로 감점하면 안 된다",
         "구현", f"중앙값이 가장 높은 업종은 {top_dense['name']} ({top_dense['p50']:,.1f}개/㎢)"],
        [4, "매출 성장률과 폐업률의 관계", "매출이 오르는 곳에서 폐업이 적은지 본다",
         "계획: 2024 · 2025년 K01 · K02. 실제: 2025년만 있어 성장률 계산 불가", "[대체] 같은 업종 안에서 점포당 월매출(로그) × 축소 추정 폐업률 산점도와 순위상관. 2024년 자료가 들어오면 x축을 전년 대비 성장률로 바꾼다",
         "매출 수준과 폐업률의 관계는 상권 단위에서 약하다. 성장률과의 관계는 아직 말할 수 없다",
         "대체 구현", f"매출 점수가 있는 {sc['industries']}개 업종 중 {sc['negative']}개에서 음(−)의 상관, 중앙값 ρ = {sc['median']:+.2f} (범위 {sc['min']:+.2f} ~ {sc['max']:+.2f})"],
        [5, "상권별 집객시설 구성", "상권 유형마다 사람을 끌어오는 시설 구성이 어떻게 다른지 본다",
         "K05 집객시설 총수와 세부 항목 19개(2021Q1 이후 값 변화 없음)", "100% 누적 막대(서울 전체 · 골목 · 발달 · 전통시장)와 집객시설이 많은 상권 15곳의 누적 막대. 세부 항목 합이 총수보다 작은 나머지는 '세부 미기재'로 따로 표시",
         "세부 항목만으로는 집객시설의 절반 이상을 설명하지 못한다. 점수에 쓰기 전 총수 정의 확인이 필요하다",
         "구현", f"서울 집객시설 총수의 {fac['unknownShare']}%가 세부 미기재. 세부가 있는 시설 중 교통이 {fac['transportShareKnown']}%"],
        [6, "상권 점수 레이더 차트", "고른 상권들의 4개 영역 점수를 같은 업종 중앙값과 함께 비교한다",
         "STEP 4 영역 점수(매출 · 경쟁 · 안정성 · 수요)", "상권 최대 3곳 + 업종 중앙값의 레이더. 기본은 현재 가중치 종합 점수 상위 3곳. 자료 없는 영역은 축에 표시하지 않고 따로 적음",
         "종합 점수가 비슷해도 강한 영역이 다르다", "구현", "경쟁과 수요는 둘 다 유동인구를 써서 순위상관 0.47 (STEP 4 진단)"],
        [7, "금융 MBTI별 추천 상권 비교", "창업자 유형 8개마다 같은 업종에서 어떤 상권이 먼저 보이는지 비교한다",
         "STEP 5 상권 L/V · E/P, 유형별 가중치, STEP 4 영역 점수", "유형 8개 카드: 두 글자가 같은 상권만 남기고 S/G 가중치 종합 점수 상위 5곳. 유형마다 후보 상권 수 막대",
         "앞 두 글자(L/V · E/P)가 후보를 정하고, S/G는 순서만 바꾼다",
         "구현", f"{ind_name}: S와 G 상위 5곳이 겹치는 수 {overlap}"],
    ]
    return pd.DataFrame(rows, columns=["번호", "시각화", "분석 목적", "필요한 데이터", "구현 방법", "기대 인사이트", "상태", "확인한 결과"])


# ---------------------------------------------------------------- 조립


def build_payload(d: dict) -> tuple[dict, dict, pd.DataFrame]:
    proj = Projection(d["geometry"])
    areas = area_frame(d)
    geo = {f["trdar_code"]: f for f in d["geometry"]}
    if set(geo) != set(areas["trdar_code"]):
        raise ValueError("상권 경계와 점수표의 상권이 다릅니다")
    index = {c: i for i, c in enumerate(areas["trdar_code"])}
    industries = industry_list(d)
    names = {r["code"]: r["name"] for r in industries}
    s4, s5 = d["stage4_meta"], d["stage5_meta"]

    checks = {
        "map": map_concentration(d, DEFAULT_INDUSTRY),
        "heat": sales_heat(d, names),
        "density": store_density(d, names),
        "salesClose": sales_close(d),
        "facility": facility_summary(areas),
        "mbti": mbti_compare(d, areas, DEFAULT_INDUSTRY),
    }
    design = step6_design(checks, names[DEFAULT_INDUSTRY])
    fac_keys = checks["facility"]["keys"]

    payload = {
        "version": VERSION,
        "defaultIndustry": DEFAULT_INDUSTRY,
        "defaultWeights": DEFAULT_WEIGHTS,
        "kpi": {
            "areas": s4["counts"]["areas"], "tourist": s4["tourist_areas"], "industries": s4["counts"]["industries"]["total"],
            "scoredIndustries": s4["counts"]["industries"]["scored"], "scoredCells": s4["counts"]["by_status"]["점수 대상"],
            "salesCells": s4["counts"]["area_scores"]["sales"], "salesIndustries": s4["counts"]["industries"]["sales_scored"],
            "type2Areas": int(areas["type2"].notna().sum()), "semasStores": d["manifest23"]["summary"]["semas_stores"],
            "factRows": s4["input_rows"]["fact"], "features": d["manifest23"]["summary"]["derived_variable_definitions"],
            "seoulSales": checks["heat"]["seoulTotal"], "byStatus": s4["counts"]["by_status"],
            "areasUsed": s4["counts"]["areas_used_default"], "alpha": round(s4["alpha"], 2),
            "type2Counts": s5["counts"]["type2"], "lvCounts": s5["counts"]["lv"], "epCounts": s5["counts"]["ep"],
        },
        "map": build_map(d["backdrop"], proj),
        "areas": {
            "code": areas["trdar_code"].tolist(), "name": areas["trdar_name"].tolist(), "gu": areas["gu_name"].tolist(),
            "kind": areas["trdar_type"].tolist(),
            "path": [svg_path(geo[c]["geometry"], proj) for c in areas["trdar_code"]],
            "c": [proj.point(geo[c]["lon"], geo[c]["lat"]) for c in areas["trdar_code"]],
            "km2": column(areas["area_km2"], 4),
            "fd": column(areas["floating_density"], 0), "wd": column(areas["worker_density"], 0), "rd": column(areas["resident_density"], 0),
            "type2": column(areas["type2"]), "lv": column(areas["lv"]), "ep": column(areas["ep"]),
            "lvs": column(areas["lv_score"], 2), "eps": column(areas["ep_score"], 2),
            "lvNote": column(areas["lv_note"]), "epNote": column(areas["ep_note"]),
            "grp": [[clean(r[f"stores_{g}"], 1) for g in ["외식", "서비스", "소매"]] for _, r in areas.iterrows()],
            "fac": [None if pd.isna(r["facility_total"]) else [int(r[f"fac_{k}"]) for k in fac_keys] for _, r in areas.iterrows()],
        },
        "industries": industries,
        "cells": store_cells(d, index),
        "scores": score_cells(d, index),
        "salesNotes": SALES_NOTES,
        "viz": {"heat": checks["heat"], "density": checks["density"], "salesClose": checks["salesClose"], "facility": checks["facility"]},
        "step4": {
            "design": d["score_design"].fillna("").to_dict("records"),
            "correlation": {k: {kk: round(vv, 2) for kk, vv in v.items() if kk.startswith("score_")}
                            for k, v in s4["diagnostics"]["spearman_overall"].items() if k.startswith("score_")},
        },
        "step5": {
            "axes": s5["axes"], "medians": {k: round(v, 2) for k, v in s5["medians"].items()},
            "questions": d["questions"].to_dict("records"), "types": d["type_table"].to_dict("records"),
            "weights": d["sg_weights"].to_dict("records"), "design": d["step5_design"].fillna("").to_dict("records"),
        },
        "step6": {"design": design.to_dict("records")},
        "docs": {"datasets": dataset_rows(d), "columns": column_rows(d), "tables": table_rows(d), "features": feature_rows(d),
                 "pipeline": d["manifest23"]["summary"]},
    }
    meta = {
        "title": "STEP 6 EDA·시각화와 최종 산출물 대시보드 (2025)",
        "version": VERSION, "default_industry": DEFAULT_INDUSTRY,
        "counts": {"areas": len(areas), "industries": len(industries), "score_industries": len(payload["scores"]),
                   "score_cells": sum(len(v["a"]) for v in payload["scores"].values()),
                   "store_cells": sum(len(v[0]) for v in payload["cells"].values()),
                   "type2_areas": payload["kpi"]["type2Areas"], "facility_missing_areas": checks["facility"]["missingAreas"]},
        "checks": {"map": checks["map"], "sales_close": {k: v for k, v in checks["salesClose"].items() if k != "rho"},
                   "facility_unknown_share": checks["facility"]["unknownShare"], "facility_transport_share_known": checks["facility"]["transportShareKnown"],
                   "heat_lead_over_half": sum(1 for v in checks["heat"]["area"]["leadShare"] if v > 50), "seoul_sales_trillion": checks["heat"]["seoulTotal"],
                   "mbti_default_industry": checks["mbti"]},
        "input_sha256": fingerprints(),
    }
    return payload, meta, design


def render(payload: dict) -> str:
    template = (WEB / "template.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    parts = {
        "/*__STYLE__*/": (WEB / "style.css").read_text(encoding="utf-8"),
        "/*__CORE__*/": (WEB / "core.js").read_text(encoding="utf-8"),
        "/*__APP__*/": (WEB / "app.js").read_text(encoding="utf-8"),
        "__PAYLOAD__": data,
    }
    for key, value in parts.items():
        if template.count(key) != 1:
            raise ValueError(f"템플릿 자리표시 {key}가 정확히 한 번 있어야 합니다")
        template = template.replace(key, value)
    return template


def main(out: Path = HERE) -> list[Path]:
    before = fingerprints()
    d = read_inputs()
    payload, meta, design = build_payload(d)
    if fingerprints() != before:
        raise RuntimeError("실행 중에 입력 파일이 바뀌었습니다")
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "report").mkdir(parents=True, exist_ok=True)
    paths = [out / "data" / DESIGN_NAME, out / "data" / META_NAME, out / "report" / HTML_NAME]
    design.to_csv(paths[0], index=False, encoding="utf-8-sig", lineterminator="\n")
    paths[1].write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths[2].write_text(render(payload), encoding="utf-8")
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE, help="출력 폴더 (검증용. 기본은 이 폴더)")
    args = parser.parse_args()
    for p in main(args.out):
        size = p.stat().st_size / 1024
        print(f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}  {size:,.0f} KB")
