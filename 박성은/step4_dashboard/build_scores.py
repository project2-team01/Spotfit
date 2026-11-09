# -*- coding: utf-8 -*-
"""
SpotFit STEP 4: 희망 업종 안에서 상권을 비교하는 4개 영역 점수표를 만든다.

입력 (모두 읽기만 함):
    김지영/claude_dashboard/data/cells.parquet, areas.parquet, industries.parquet, quarters.parquet, meta.json
    김지영/step2_3/data/dim_trdar.csv.gz (관광특구 확인용)
출력 (이 폴더의 data/ 안에만 씀):
    data/상권_업종_비교점수_2025.parquet
    data/업종별_점수_가능여부.csv
    data/점수_설계표.csv
    data/stage4_meta.json

실행 (팀 저장소 루트에서):
    uv run --project "박성은/step4_dashboard" python "박성은/step4_dashboard/build_scores.py"

팀 결정 (2026-11-05):
    - 2025년 자료만 쓴다. 성장성은 만들지 않고 4개 영역(매출 잠재력·경쟁·안정성·수요)으로 점수를 만든다.
    - 관광특구 제외. 연간 평균 점포 5개 이상인 칸만 점수. 비교 상권 30곳 미만 업종은 점수 없음.
    - 매출 결측은 0으로 채우지 않는다. 폐업률은 4분기 평균 점포 분모 + 축소 추정.
    - 분기 매출 증감률은 점수에 넣지 않는다(상세 화면 참고용, 상하위 5% 윈저화).
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from audit_inputs import audit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]              # 팀 저장소 루트 (<이름>/step4_dashboard/ 의 두 단계 위)
JY_DATA = REPO / "김지영" / "claude_dashboard" / "data"
JY_STEP = REPO / "김지영" / "step2_3" / "data"
OUT = HERE / "data"

MIN_STORES = 5      # 7.3 결정: 연간 평균 점포 5개 이상
MIN_PEERS = 30      # 7.3 결정: 업종 비교 상권 30곳 이상
DEFAULT_WEIGHTS = {"sales": 30, "comp": 25, "stab": 15, "dem": 30}   # [가정] 팀 미확정
AREA_LABELS = {"sales": "매출 잠재력", "comp": "경쟁", "stab": "안정성", "dem": "수요"}
DEMAND_MODES = {"avg": "세 값 평균", "floating": "유동인구 중심", "worker": "직장인 중심", "resident": "주민 중심"}

INPUTS = [
    JY_DATA / "cells.parquet", JY_DATA / "areas.parquet", JY_DATA / "industries.parquet",
    JY_DATA / "quarters.parquet", JY_DATA / "meta.json", JY_STEP / "dim_trdar.csv.gz",
]
INPUTS += [JY_STEP / f for f in ("fact_trdar_industry_quarter.csv.gz", "annual_features.csv.gz", "trdar_quarter_context.csv.gz")]
INPUTS += [JY_DATA / f for f in ("areas.geojson.json", "backdrop.parquet")]
INPUTS += [REPO / "김지영/step2_3/feature_dictionary.csv"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pct_rank(s, higher_is_better=True):
    """업종 안 백분위 점수(0 초과 100 이하). 동점은 평균 순위. 결측은 결측으로 둔다."""
    return s.rank(pct=True, method="average", ascending=higher_is_better) * 100


def composite(df, weights=None, demand_mode="avg"):
    """자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균. (종합 점수, 계산에 쓴 영역 수)를 돌려준다."""
    weights = weights or DEFAULT_WEIGHTS
    cols = {"sales": "score_sales", "comp": "score_comp", "stab": "score_stab", "dem": f"score_dem_{demand_mode}"}
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    n = pd.Series(0, index=df.index)
    for key, col in cols.items():
        w = float(weights.get(key, 0))
        has = df[col].notna()
        num = num + df[col].fillna(0) * w * has
        den = den + w * has
        n = n + (has & (w > 0)).astype(int)
    total = (num / den.where(den > 0)).where(df["score_status"].eq("점수 대상"))
    return total, n.where(total.notna())


def load_inputs():
    missing = [p for p in INPUTS if not p.exists()]
    if missing:
        names = "\n".join(f"  - {p.relative_to(REPO).as_posix()}" for p in missing)
        sys.exit("입력 파일이 없습니다. 팀 저장소 main을 최신으로 받았는지 확인하세요:\n" + names)
    cells = pd.read_parquet(JY_DATA / "cells.parquet")
    areas = pd.read_parquet(JY_DATA / "areas.parquet")
    industries = pd.read_parquet(JY_DATA / "industries.parquet")
    quarters = pd.read_parquet(JY_DATA / "quarters.parquet")
    dim = pd.read_csv(JY_STEP / "dim_trdar.csv.gz", dtype={"trdar_code": str})
    return cells, areas, industries, quarters, dim


def build(cells, areas, industries, quarters, dim):
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    a = areas[["trdar_code", "trdar_name", "gu_name", "trdar_type", "area_km2", "floating", "worker", "resident",
               "floating_density", "worker_density", "resident_density"]]
    d = cells[["trdar_code", "industry_code", "industry_name", "group", "stores", "opens", "closes", "sales_status",
               "sales_quarters", "sales_month", "sales_index", "peer_median", "franchise_pct", "close_pct", "close_pct_shrunk"]]
    d = d.merge(a, on="trdar_code", how="left", validate="many_to_one")
    d = d.loc[~d["trdar_code"].isin(tourist)].copy()     # 7.4 관광특구 제외 (cells에 이미 없지만 한 번 더 거른다)

    # 경쟁 [가정]: 유동인구 1,000명당 같은 업종 점포 수. 수요에 비해 점포가 적을수록 좋다.
    d["comp_ratio"] = d["stores"] / (d["floating"] / 1000).where(d["floating"] > 0)

    # 대상 판정
    big = d["stores"].ge(MIN_STORES)
    peers = d.loc[big].groupby("industry_code").size()
    d["industry_peers"] = d["industry_code"].map(peers).fillna(0).astype(int)
    d["score_status"] = np.select(
        [~big, d["industry_peers"].lt(MIN_PEERS)],
        ["평균 점포 5개 미만 (참고용)", "업종 비교 상권 30곳 미만"], default="점수 대상")
    target = d["score_status"].eq("점수 대상")

    # ① 매출 잠재력: 4개 분기 매출이 모두 있는 칸끼리, 업종 안 백분위
    has_sales = target & d["sales_status"].eq("네 분기") & d["sales_month"].notna()
    sales_peers = d.loc[has_sales].groupby("industry_code").size()
    d["sales_peers"] = d["industry_code"].map(sales_peers).fillna(0).astype(int)
    sales_ok = has_sales & d["sales_peers"].ge(MIN_PEERS)
    d["score_sales"] = np.nan
    d.loc[sales_ok, "score_sales"] = d.loc[sales_ok].groupby("industry_code")["sales_month"].transform(pct_rank)
    d["sales_area_status"] = np.select(
        [~target, sales_ok, d["sales_status"].eq("미제공 업종"), ~d["sales_status"].eq("네 분기"), d["sales_peers"].lt(MIN_PEERS)],
        ["점수 대상 아님", "점수 있음", "매출 미제공 업종", f"4개 분기 매출 없음 ({'·'.join(['미공개', '일부 분기'])})", "업종 매출 비교 상권 30곳 미만"],
        default="기타")
    # 미공개·일부 분기 표기를 실제 값으로 구체화
    part = target & ~sales_ok & d["sales_status"].isin(["미공개", "일부 분기"])
    d.loc[part, "sales_area_status"] = "4개 분기 매출 없음 (" + d.loc[part, "sales_status"] + ")"

    # ② 경쟁, ③ 안정성, ④ 수요: 점수 대상 칸끼리, 업종 안 백분위
    t = d.loc[target]
    g = t.groupby("industry_code")
    d["score_comp"] = np.nan
    d["score_stab"] = np.nan
    d.loc[target, "score_comp"] = g["comp_ratio"].transform(lambda s: pct_rank(s, higher_is_better=False))
    d.loc[target, "score_stab"] = g["close_pct_shrunk"].transform(lambda s: pct_rank(s, higher_is_better=False))
    for key in ["floating", "worker", "resident"]:
        d[f"score_dem_{key}"] = np.nan
        d.loc[target, f"score_dem_{key}"] = g[f"{key}_density"].transform(pct_rank)
    dem_cols = ["score_dem_floating", "score_dem_worker", "score_dem_resident"]
    d["score_dem_avg"] = d[dem_cols].mean(axis=1, skipna=True)
    d["dem_avg_n"] = d[dem_cols].notna().sum(axis=1).where(target)

    d["score_total_default"], d["n_areas_default"] = composite(d)
    d = d.sort_values(["industry_code", "trdar_code"]).reset_index(drop=True)
    target = d["score_status"].eq("점수 대상")   # 정렬 후 인덱스가 바뀌었으므로 다시 계산

    # 업종별 점수 가능 여부 (100개 업종)
    ind = industries[["industry_code", "industry_name", "group", "supported"]].copy()
    stat = d.groupby("industry_code").agg(
        cells=("trdar_code", "size"), peers=("industry_peers", "first"), sales_peers=("sales_peers", "max"),
        scored=("score_status", lambda s: int(s.eq("점수 대상").sum())),
        sales_scored=("score_sales", lambda s: int(s.notna().sum())))
    ind = ind.merge(stat, on="industry_code", how="left").fillna({"cells": 0, "peers": 0, "sales_peers": 0, "scored": 0, "sales_scored": 0})
    ind["점수_생성"] = ind["peers"].ge(MIN_PEERS)
    ind["매출_점수_생성"] = ind["sales_scored"].gt(0)
    ind["사유"] = np.select(
        [~ind["점수_생성"], ~ind["supported"], ~ind["매출_점수_생성"]],
        [f"점포 5개 이상 상권이 {MIN_PEERS}곳 미만", "점수 있음 (매출 미제공 업종이라 매출 영역 제외)", f"점수 있음 (4개 분기 매출 상권이 {MIN_PEERS}곳 미만이라 매출 영역 제외)"],
        default="점수 있음 (4개 영역)")
    ind = ind.rename(columns={
        "industry_code": "업종_코드", "industry_name": "업종명", "group": "업종군", "supported": "매출_제공_업종",
        "cells": "상권_수", "peers": "점포5개이상_상권_수", "sales_peers": "매출비교_상권_수", "scored": "점수_상권_수", "sales_scored": "매출점수_상권_수"})
    for c in ["상권_수", "점포5개이상_상권_수", "매출비교_상권_수", "점수_상권_수", "매출점수_상권_수"]:
        ind[c] = ind[c].astype(int)
    ind = ind.sort_values("업종_코드").reset_index(drop=True)

    # 분기 매출 증감률 윈저화 경계 (참고용, 점수에 쓰지 않음)
    q = quarters.loc[~quarters["trdar_code"].isin(tourist)].sort_values(["trdar_code", "industry_code", "quarter"])
    prev = q.groupby(["trdar_code", "industry_code"])["sales_amount"].shift(1)
    prev_q = q.groupby(["trdar_code", "industry_code"])["quarter"].shift(1)
    consecutive = pd.to_numeric(q.quarter) - pd.to_numeric(prev_q) == 1
    qoq = ((q["sales_amount"] / prev.where(prev > 0) - 1) * 100).where(consecutive)
    qoq = qoq[np.isfinite(qoq)]
    bounds = {"p5": round(float(qoq.quantile(0.05)), 4), "p95": round(float(qoq.quantile(0.95)), 4), "n": int(qoq.size)}

    tt = d.loc[target]
    corr = {
        "경쟁_수요(세 값 평균)": round(float(tt[["score_comp", "score_dem_avg"]].corr("spearman").iloc[0, 1]), 3),
        "직장인구_상주인구_밀도": round(float(tt[["score_dem_worker", "score_dem_resident"]].corr("spearman").iloc[0, 1]), 3),
        "매출_경쟁": round(float(tt[["score_sales", "score_comp"]].corr("spearman").iloc[0, 1]), 3),
        "매출_안정성": round(float(tt[["score_sales", "score_stab"]].corr("spearman").iloc[0, 1]), 3),
        "매출_수요(세 값 평균)": round(float(tt[["score_sales", "score_dem_avg"]].corr("spearman").iloc[0, 1]), 3),
    }
    meta = {
        "rules": {"min_stores": MIN_STORES, "min_peers": MIN_PEERS, "default_weights": DEFAULT_WEIGHTS,
                  "area_labels": AREA_LABELS, "demand_modes": DEMAND_MODES},
        "counts": {
            "cells": int(len(d)), "target_cells": int(target.sum()), "sales_scored_cells": int(d["score_sales"].notna().sum()),
            "industries": int(len(ind)), "scored_industries": int(ind["점수_생성"].sum()),
            "sales_scored_industries": int(ind["매출_점수_생성"].sum()),
            "status": {k: int(v) for k, v in d["score_status"].value_counts().sort_index().items()},
            "sales_area_status": {k: int(v) for k, v in d.loc[target, "sales_area_status"].value_counts().sort_index().items()},
        },
        "qoq_winsor": bounds,
        "spearman": corr,
        "inputs": {p.relative_to(REPO).as_posix(): sha256(p) for p in INPUTS},
    }
    return d, ind, meta


DESIGN = [
    ("매출 잠재력", "점포당 월매출 (sales_month = 분기 추정매출 ÷ 매출 분기 점포 수 ÷ 3의 연간 값)", "업종 안 백분위 × 100",
     "높을수록 좋음", "점수 대상 칸 중 4개 분기 매출이 모두 있는 칸. 업종 안에서 그런 상권이 30곳 미만이면 영역 제외", "자료 없음(NaN). 0점 아님"),
    ("경쟁 [가정]", "유동인구 1,000명당 같은 업종 점포 수 (stores ÷ (floating ÷ 1,000))", "업종 안 백분위를 뒤집음",
     "낮을수록 좋음", "점수 대상 칸", "유동인구가 없으면 자료 없음"),
    ("안정성", "축소 추정 폐업률 (close_pct_shrunk, 분모 = 4개 분기 평균 점포)", "업종 안 백분위를 뒤집음",
     "낮을수록 좋음", "점수 대상 칸. 1년치라 신뢰도 낮음 표시", "자료 없음(NaN)"),
    ("수요 [가정]", "면적당 유동인구·직장인구·상주인구 (주 고객층 선택: 세 값 평균 / 유동 / 직장 / 주민)", "각 밀도의 업종 안 백분위. 세 값 평균은 있는 값끼리 평균",
     "높을수록 좋음", "점수 대상 칸", "직장·상주인구가 없으면 있는 값으로만 계산하고 개수 표시"),
    ("종합", "4개 영역 가중 평균 (기본 매출 30 · 경쟁 25 · 안정성 15 · 수요 30) [가정]", "자료가 있는 영역끼리 가중치를 다시 나눔",
     "높을수록 좋음", "점수 대상 칸", "계산에 쓴 영역 수 표시"),
    ("성장성", "만들지 않음", "-", "-", "2025년 자료만 있어 전년 대비 성장률을 계산할 수 없음 (팀 결정)", "-"),
]


def main():
    before = {p: sha256(p) for p in INPUTS if p.exists()}
    audit_result = audit()
    d, ind, meta = build(*load_inputs())
    meta["input_audit"] = audit_result
    meta["implementation"] = "김지영 공통 데이터·이승희 STEP4 기반, 박성은 검증 및 강사 피드백 반영 (2026-11-09)"
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "상권_업종_비교점수_2025.parquet", index=False)
    ind.to_csv(OUT / "업종별_점수_가능여부.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    design = pd.DataFrame(DESIGN, columns=["영역", "지표", "계산", "방향", "대상 조건", "결측 처리"])
    design["대상 행 수"] = [int(d.score_sales.notna().sum()), int(d.score_comp.notna().sum()),
                              int(d.score_stab.notna().sum()), int(d.score_dem_avg.notna().sum()),
                              int(d.score_total_default.notna().sum()), 0]
    design["경쟁·수요 상관(전체 점수 대상)"] = meta["spearman"]["경쟁_수요(세 값 평균)"]
    design.to_csv(
        OUT / "점수_설계표.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    # 강사 피드백: 분기 계산과 지도용 정적 데이터는 실행 전에 만들어 저장한다.
    q = pd.read_parquet(JY_DATA / "quarters.parquet").sort_values(["trdar_code", "industry_code", "quarter"])
    q["sales_month"] = q.sales_amount / q.store_count.where(q.store_count > 0) / 3
    prev = q.groupby(["trdar_code", "industry_code"]).sales_amount.shift(1)
    prev_q = q.groupby(["trdar_code", "industry_code"]).quarter.shift(1)
    consecutive = pd.to_numeric(q.quarter) - pd.to_numeric(prev_q) == 1
    q["qoq_raw"] = ((q.sales_amount / prev.where(prev > 0) - 1) * 100).where(consecutive)
    q["qoq_winsor"] = q.qoq_raw.clip(meta["qoq_winsor"]["p5"], meta["qoq_winsor"]["p95"])
    q.to_parquet(OUT / "quarter_mart.parquet", index=False)
    geometry = json.loads((JY_DATA / "areas.geojson.json").read_text(encoding="utf-8"))
    (OUT / "map_geometry.json").write_text(json.dumps(geometry, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    correlations = []
    for code, part in d.loc[d.score_status.eq("점수 대상")].groupby("industry_code"):
        correlations.append({"업종_코드": code, "업종명": part.industry_name.iloc[0], "대상_행_수": len(part),
                             "경쟁_수요_Spearman": part[["score_comp", "score_dem_avg"]].corr("spearman").iloc[0, 1]})
    pd.DataFrame(correlations).to_csv(OUT / "업종별_경쟁수요_상관.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    high_overlap = [r for r in correlations if abs(r["경쟁_수요_Spearman"]) >= 0.8]
    meta["high_overlap_industries"] = high_overlap
    overlap_note = "; ".join(f"{r['업종명']} {r['대상_행_수']}곳 상관 {r['경쟁_수요_Spearman']:.3f}" for r in high_overlap)
    alternative = (overlap_note + ". 대안: 경쟁 가중치를 0으로 두어 민감도를 비교하거나 직장/주민 중심 수요를 별도로 비교. 기본 규칙은 팀 합의 전 유지.") if high_overlap else "업종별 절대 상관 0.8 이상 없음"
    design["중복 반영 주의·대안"] = ["", alternative, "", alternative, "가중치와 고객층 변경에 따른 민감도 확인", ""]
    design.to_csv(OUT / "점수_설계표.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    (OUT / "stage4_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    after = {p: sha256(p) for p in INPUTS}
    assert before == after, "입력 파일이 실행 중에 바뀌었습니다"
    c = meta["counts"]
    print(f"[완료] 상권×업종 {c['cells']:,}칸 중 점수 대상 {c['target_cells']:,}칸, 매출 점수 {c['sales_scored_cells']:,}칸")
    print(f"       점수 생성 업종 {c['scored_industries']}개 / {c['industries']}개, 매출 점수 업종 {c['sales_scored_industries']}개")
    print(f"       분기 매출 증감률 윈저화 경계 p5 {meta['qoq_winsor']['p5']:.1f}% ~ p95 {meta['qoq_winsor']['p95']:.1f}%")


if __name__ == "__main__":
    main()
