"""STEP 2·3 산출물과 상권 경계로 대시보드용 소형 데이터를 만든다.

원본과 step2_3/ 은 읽기만 한다. 결과는 claude_dashboard/data/ 에만 쓴다.
실행: .venv/bin/python 김지영/claude_dashboard/build_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PERSONAL = HERE.parent
PROJECT = PERSONAL.parent
STEP = PERSONAL / "step2_3"
OUT = HERE / "data"

SHP = PROJECT / "data/raw/seoul/extracted/seoul_area_trdar/서울시 상권분석서비스(영역-상권).shp"
S01 = PROJECT / "data/raw/semas/extracted/semas_store_20251231/소상공인시장진흥공단_상가(상권)정보_서울_202512.csv"

# STEP 3의 비교 규칙을 연간 단위에 그대로 쓴다. 두 값 모두 운영 가정이다.
MIN_STORES = 5
MIN_PEERS = 30

GROUPS = {"CS1": "외식", "CS2": "서비스", "CS3": "소매"}
TIMES = ["00_06", "06_11", "11_14", "14_17", "17_21", "21_24"]
AGES = ["10", "20", "30", "40", "50", "60_plus"]
TIME_COLS = [f"time_{t}_sales" for t in TIMES]
AGE_COLS = [f"age_{a}_sales" for a in AGES]
IDS = {"quarter": str, "trdar_code": str, "industry_code": str}


def read_fact() -> pd.DataFrame:
    cols = ["quarter", "trdar_code", "industry_code", "industry_name", "main_analysis_eligible", "sales_supported_industry",
            "store_count", "open_count", "close_count", "franchise_store_count", "sales_amount", "sales_count", "sales_observed",
            "weekend_sales", "male_sales", "female_sales", *TIME_COLS, *AGE_COLS]
    fact = pd.read_csv(STEP / "data/fact_trdar_industry_quarter.csv.gz", dtype=IDS, usecols=cols)
    return fact.loc[fact["main_analysis_eligible"]].copy()


def build_cells(fact: pd.DataFrame) -> pd.DataFrame:
    """상권×업종 연간 표. 매출이 없는 칸은 0이 아니라 결측으로 둔다."""
    d = fact.assign(store_on_sales=fact["store_count"].where(fact["sales_observed"]))
    money = ["sales_amount", "sales_count", "weekend_sales", "male_sales", "female_sales", *TIME_COLS, *AGE_COLS]
    g = d.groupby(["trdar_code", "industry_code", "industry_name"], as_index=False).agg(
        stores_sum=("store_count", "sum"), opens=("open_count", "sum"), closes=("close_count", "sum"),
        franchise_sum=("franchise_store_count", "sum"), sales_quarters=("sales_observed", "sum"),
        stores_on_sales=("store_on_sales", "sum"), supported=("sales_supported_industry", "first"),
        distinct_sales=("sales_amount", "nunique"), **{c: (c, lambda s: s.sum(min_count=1)) for c in money})
    g["stores"] = g["stores_sum"] / 4  # K02에 행이 없는 분기는 점포 0개다
    g = g.loc[g["stores"] > 0].copy()

    g["sales_status"] = np.select(
        [~g["supported"], g["sales_quarters"].eq(0), g["sales_quarters"].lt(4)],
        ["미제공 업종", "미공개", "일부 분기"], default="네 분기")
    g["repeated_sales"] = g["sales_quarters"].eq(4) & g["distinct_sales"].eq(1)
    g["sales_month"] = g["sales_amount"] / g["stores_on_sales"].replace(0, np.nan) / 3
    g["franchise_pct"] = g["franchise_sum"] / g["stores_sum"] * 100
    g["open_pct"] = g["opens"] / g["stores"] * 100
    g["close_pct"] = g["closes"] / g["stores"] * 100

    # 업종 내 지수: 네 분기가 모두 있고 평균 점포 5개 이상인 칸끼리 비교한다
    eligible = g["sales_status"].eq("네 분기") & g["stores"].ge(MIN_STORES)
    peers = g.loc[eligible].groupby("industry_code")["sales_month"].agg(peer_median="median", peer_count="count")
    g = g.merge(peers, left_on="industry_code", right_index=True, how="left")
    enough = eligible & g["peer_count"].ge(MIN_PEERS)
    g["sales_index"] = (g["sales_month"] / g["peer_median"]).where(enough)

    # 폐업 축소 추정 (EDA 4.2와 같은 포아송-감마 적률 추정)
    by = g.groupby("industry_code")
    industry_rate = by["closes"].transform("sum") / by["stores"].transform("sum")
    g["expected_closes"] = g["stores"] * industry_rate
    alpha = (g["expected_closes"] ** 2).sum() / ((g["closes"] - g["expected_closes"]) ** 2 - g["expected_closes"]).sum()
    g["close_pct_shrunk"] = ((g["closes"] + alpha) / (g["stores"] + alpha / industry_rate.replace(0, np.nan)) * 100)
    g.attrs["alpha"] = float(alpha)
    g.attrs["pseudo_stores"] = float((alpha / industry_rate.replace(0, np.nan)).median())

    known_age = g[AGE_COLS].sum(axis=1, min_count=1)
    for t in TIMES:
        g[f"time_{t}"] = g[f"time_{t}_sales"] / g["sales_amount"] * 100
    for a in AGES:
        g[f"age_{a}"] = g[f"age_{a}_sales"] / known_age * 100
    g["weekend_pct"] = g["weekend_sales"] / g["sales_amount"] * 100
    g["unidentified_pct"] = (1 - (g["male_sales"] + g["female_sales"]) / g["sales_amount"]) * 100
    g["ticket"] = g["sales_amount"] / g["sales_count"]
    g["group"] = g["industry_code"].str[:3].map(GROUPS)
    return g


def build_areas(fact: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    dim = pd.read_csv(STEP / "data/dim_trdar.csv.gz", dtype={"trdar_code": str})
    dim = dim.loc[dim["main_analysis_eligible"], ["trdar_code", "trdar_name", "trdar_type", "gu_name", "area_km2"]]
    context = pd.read_csv(STEP / "data/trdar_quarter_context.csv.gz", dtype=IDS)
    context = context.loc[context["main_analysis_eligible"]]
    latest = context.loc[context["quarter"].eq("20254")].set_index("trdar_code")
    flow = context.groupby("trdar_code")["floating_population"].mean()

    a = dim.set_index("trdar_code")
    total = cells.groupby("trdar_code").agg(all_stores=("stores", "sum"), area_opens=("opens", "sum"), area_closes=("closes", "sum"),
                                             expected=("expected_closes", "sum"))
    a = a.join(total)
    a["close_ratio"] = a["area_closes"] / a["expected"]
    a["close_signal"] = pd.cut(a["all_stores"], [0, 100, 300, np.inf], right=False, labels=["매우 약함", "약함", "참고 가능"]).astype("string")
    a["sales_year"] = fact.groupby("trdar_code")["sales_amount"].sum(min_count=1)
    a["floating"] = flow
    for name, col in [("worker", "worker_population"), ("resident", "resident_population"), ("facility", "facility_count")]:
        a[name] = latest[col]
    for name in ["floating", "worker", "resident", "facility"]:
        a[f"{name}_density"] = a[name] / a["area_km2"]
        a[f"{name}_pct"] = a[f"{name}_density"].rank(pct=True) * 100
    a["entropy"] = latest["normalized_industry_entropy"]
    return a.reset_index()


def build_industries(cells: pd.DataFrame) -> pd.DataFrame:
    g = cells.groupby(["industry_code", "industry_name", "group"], as_index=False).agg(
        areas=("trdar_code", "nunique"), stores=("stores", "sum"), opens=("opens", "sum"), closes=("closes", "sum"),
        franchise_sum=("franchise_sum", "sum"), stores_sum=("stores_sum", "sum"), sales_year=("sales_amount", lambda s: s.sum(min_count=1)),
        supported=("supported", "first"), peer_count=("peer_count", "first"), peer_median=("peer_median", "first"))
    g["open_pct"] = g["opens"] / g["stores"] * 100
    g["close_pct"] = g["closes"] / g["stores"] * 100
    g["net_pct"] = g["open_pct"] - g["close_pct"]
    g["franchise_pct"] = g["franchise_sum"] / g["stores_sum"] * 100
    covered = cells.loc[cells["sales_quarters"].gt(0)].groupby("industry_code")["stores_sum"].sum()
    g["sales_coverage_pct"] = g["industry_code"].map(covered).fillna(0) / g["stores_sum"] * 100
    g["median_month"] = g["industry_code"].map(cells.groupby("industry_code")["sales_month"].median())
    shares = cells.groupby("industry_code")[[*TIME_COLS, *AGE_COLS, "sales_amount"]].sum(min_count=1)
    for t in TIMES:
        g[f"time_{t}"] = g["industry_code"].map(shares[f"time_{t}_sales"] / shares["sales_amount"] * 100)
    known = shares[AGE_COLS].sum(axis=1, min_count=1)
    for a in AGES:
        g[f"age_{a}"] = g["industry_code"].map(shares[f"age_{a}_sales"] / known * 100)
    return g.drop(columns=["franchise_sum", "stores_sum"])


def half_year_reliability(fact: pd.DataFrame, areas: pd.DataFrame) -> list[dict]:
    """같은 칸의 상·하반기 값이 이어지는지 본다 (EDA 5.5와 같은 계산)."""
    d = fact.assign(half=np.where(fact["quarter"].isin(["20251", "20252"]), "H1", "H2"),
                    store_on_sales=fact["store_count"].where(fact["sales_observed"]))
    h = d.groupby(["trdar_code", "industry_code", "half"]).agg(
        closes=("close_count", "sum"), opens=("open_count", "sum"), stores=("store_count", "sum"),
        sales=("sales_amount", "sum"), stores_sales=("store_on_sales", "sum"), n=("sales_observed", "sum")).unstack("half")
    h = h[(h[("stores", "H1")] > 0) & (h[("stores", "H2")] > 0)]
    codes = h.index.get_level_values("industry_code")

    def expected(col, half):
        stock = h[("stores", half)] / 2
        rate = h[(col, half)].groupby(codes).transform("sum") / stock.groupby(codes).transform("sum")
        return stock * rate

    def z(col, half):
        e = expected(col, half)
        return (h[(col, half)] - e) / np.sqrt(e)

    def log_sales(half):
        v = np.log(h[("sales", half)] / h[("stores_sales", half)])
        return v - v.groupby(codes).transform("mean")

    f = pd.DataFrame({"c1": z("closes", "H1"), "c2": z("closes", "H2"), "o1": z("opens", "H1"), "o2": z("opens", "H2"),
                      "avg": (h[("stores", "H1")] + h[("stores", "H2")]) / 4})
    full = (h[("n", "H1")] == 2) & (h[("n", "H2")] == 2)
    f["s1"], f["s2"] = log_sales("H1").where(full), log_sales("H2").where(full)
    f["band"] = pd.cut(f["avg"], [3, 10, 20, 50, np.inf], right=False, labels=["3~9개", "10~19개", "20~49개", "50개 이상"])
    rows = []
    for band, g in f.dropna(subset=["band"]).groupby("band", observed=True):
        rows += [{"단위": "상권×업종 칸", "구간": str(band), "지표": name, "상관": float(g[a].corr(g[b]))}
                 for name, a, b in [("점포당 매출", "s1", "s2"), ("개업률", "o1", "o2"), ("폐업률", "c1", "c2")]]

    def area_z(col, half):
        t = pd.DataFrame({"o": h[(col, half)], "e": expected(col, half)}).groupby(level="trdar_code").sum()
        return (t["o"] - t["e"]) / np.sqrt(t["e"])

    t = pd.DataFrame({"c1": area_z("closes", "H1"), "c2": area_z("closes", "H2"), "o1": area_z("opens", "H1"), "o2": area_z("opens", "H2")})
    t["all_stores"] = areas.set_index("trdar_code")["all_stores"].reindex(t.index)
    t["band"] = pd.cut(t["all_stores"], [0, 100, 300, np.inf], labels=["100개 미만", "100~299개", "300개 이상"])
    for band, g in t.groupby("band", observed=True):
        rows += [{"단위": "상권 전체", "구간": str(band), "지표": name, "상관": float(g[a].corr(g[b]))}
                 for name, a, b in [("개업률", "o1", "o2"), ("폐업률", "c1", "c2")]]
    return rows


def sales_availability(fact: pd.DataFrame) -> list[dict]:
    d = fact.loc[fact["sales_supported_industry"]].copy()
    labels = ["0", "1", "2", "3", "4", "5", "6-9", "10-19", "20-49", "50-99", "100+"]
    d["band"] = pd.cut(d["store_count"], [-1, 0, 1, 2, 3, 4, 5, 9, 19, 49, 99, np.inf], labels=labels)
    g = d.groupby("band", observed=False)["sales_observed"].agg(["size", "mean"])
    return [{"구간": str(i), "칸수": int(r["size"]), "보유율": float(r["mean"] * 100)} for i, r in g.iterrows()]


def build_geometry(codes: set[str]) -> list[dict]:
    g = gpd.read_file(SHP).set_crs(5181, allow_override=True)
    g = g.loc[g["TRDAR_CD"].isin(codes), ["TRDAR_CD", "geometry"]].copy()
    g["geometry"] = g.make_valid().simplify(12, preserve_topology=True)
    g = g.to_crs(4326)
    point = g.representative_point()
    features = json.loads(g.assign(geometry=g.set_precision(1e-5)).to_json(drop_id=True))["features"]
    return [{"trdar_code": f["properties"]["TRDAR_CD"], "lon": round(point.iloc[i].x, 5), "lat": round(point.iloc[i].y, 5), "geometry": f["geometry"]}
            for i, f in enumerate(features)]


def build_backdrop() -> pd.DataFrame:
    """서울 윤곽을 보여 주는 상가 밀도 격자. 지도 배경 타일 없이 위치 감각을 준다."""
    s = pd.read_csv(S01, encoding="utf-8", usecols=["경도", "위도", "시군구명"])
    step = 0.0045
    s["lon"] = (s["경도"] / step).round() * step
    s["lat"] = (s["위도"] / step).round() * step
    grid = s.groupby(["lon", "lat"]).size().rename("n").reset_index()
    grid = grid.loc[grid["n"].ge(3)].round(4)
    labels = s.groupby("시군구명")[["경도", "위도"]].median().round(4).reset_index()
    labels.columns = ["gu_name", "lon", "lat"]
    grid["kind"], labels["kind"] = "grid", "label"
    return pd.concat([grid, labels], ignore_index=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    fact = read_fact()
    cells = build_cells(fact)
    areas = build_areas(fact, cells)
    industries = build_industries(cells)

    keep = ["trdar_code", "industry_code", "industry_name", "group", "stores", "opens", "closes", "open_pct", "close_pct", "close_pct_shrunk",
            "franchise_pct", "sales_status", "sales_quarters", "repeated_sales", "sales_amount", "sales_month", "sales_index", "peer_median",
            "weekend_pct", "unidentified_pct", "ticket", *[f"time_{t}" for t in TIMES], *[f"age_{a}" for a in AGES]]
    cells[keep].to_parquet(OUT / "cells.parquet", index=False, compression="zstd")
    areas.to_parquet(OUT / "areas.parquet", index=False, compression="zstd")
    industries.to_parquet(OUT / "industries.parquet", index=False, compression="zstd")
    fact[["quarter", "trdar_code", "industry_code", "store_count", "open_count", "close_count", "sales_amount"]].to_parquet(
        OUT / "quarters.parquet", index=False, compression="zstd")
    build_backdrop().to_parquet(OUT / "backdrop.parquet", index=False, compression="zstd")
    (OUT / "areas.geojson.json").write_text(json.dumps(build_geometry(set(areas["trdar_code"])), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    manifest = json.loads((STEP / "manifest.json").read_text(encoding="utf-8"))
    meta = {
        "rules": {"min_stores": MIN_STORES, "min_peers": MIN_PEERS},
        "alpha": cells.attrs["alpha"], "pseudo_stores": cells.attrs["pseudo_stores"],
        "totals": {"areas": int(len(areas)), "sales": float(fact["sales_amount"].sum()), "opens": int(fact["open_count"].sum()),
                   "closes": int(fact["close_count"].sum()), "stores_q4": int(fact.loc[fact["quarter"].eq("20254"), "store_count"].sum())},
        "freshness": manifest["freshness"],
        "reliability": half_year_reliability(fact, areas),
        "availability": sales_availability(fact),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:24s} {p.stat().st_size / 1e6:6.2f} MB")


if __name__ == "__main__":
    main()
