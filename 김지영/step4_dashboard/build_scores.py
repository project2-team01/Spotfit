"""STEP 4: 2025년 상권×업종 '업종 내 비교 점수' 표를 만든다.

읽기만 하는 입력 (팀 공용 STEP 2·3 산출물)
  <저장소>/김지영/step2_3/data/fact_trdar_industry_quarter.csv.gz   분기×상권×업종 패널 (304,775행)
  <저장소>/김지영/step2_3/data/annual_features.csv.gz              연간 상권×업종 (77,694행)
  <저장소>/김지영/step2_3/data/trdar_quarter_context.csv.gz        상권×분기 인구·시설·면적 (6,600행)
  <저장소>/김지영/step2_3/data/dim_trdar.csv.gz                    상권 기본 정보 (1,650행)

결과는 이 작업 폴더의 data/ 에만 쓴다. 같은 입력이면 몇 번을 실행해도 바이트까지 같은 파일이 나온다.

실행 (저장소 루트에서)
  uv run --project "김지영/step4_dashboard" python "김지영/step4_dashboard/build_scores.py"
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent  # 작업 폴더
ROOT = HERE.parents[1]  # 팀 저장소 루트
# 팀 공용 입력 위치. 작업 폴더를 다른 팀원 폴더로 복사해도 입력 위치는 그대로다.
SOURCE = ROOT / "김지영" / "step2_3"
OUT = HERE / "data"

INPUTS = {
    "fact": SOURCE / "data" / "fact_trdar_industry_quarter.csv.gz",
    "annual": SOURCE / "data" / "annual_features.csv.gz",
    "context": SOURCE / "data" / "trdar_quarter_context.csv.gz",
    "dim": SOURCE / "data" / "dim_trdar.csv.gz",
}
EXPECTED_ROWS = {"fact": 304_775, "annual": 77_694, "context": 6_600, "dim": 1_650}

# 팀 결정 사항 (2026-11-05)
MIN_STORES = 5  # 연간 평균 점포 5개 이상인 칸만 점수
MIN_PEERS = 30  # 같은 업종 비교 상권이 30곳 미만이면 점수를 만들지 않음 (매출 영역에도 같은 기준, 2026-11-07 승인)
WINSOR = (0.05, 0.95)  # 분기 매출 증감률 참고 표시용 (점수에는 넣지 않음)
# [가정, 팀 미확정] 기본 가중치. 대시보드 슬라이더로 바꿀 수 있다.
DEFAULT_WEIGHTS = {"sales": 30, "competition": 25, "stability": 15, "demand": 30}

AREA_KEYS = ["sales", "competition", "stability", "demand"]
GROUPS = {"CS1": "외식", "CS2": "서비스", "CS3": "소매"}
QUARTERS = ["20251", "20252", "20253", "20254"]
IDS = {"quarter": str, "trdar_code": str, "industry_code": str}

STATUS_SCORED = "점수 대상"
STATUS_REFERENCE = "점포 5개 미만 (참고용)"
STATUS_THIN = "업종 비교 상권 30곳 미만"
STATUS_EMPTY = "평균 점포 0개"


# ---------------------------------------------------------------- 입력


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprints() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in INPUTS.values()}


def read_inputs() -> dict[str, pd.DataFrame]:
    fact = pd.read_csv(INPUTS["fact"], dtype=IDS, usecols=[
        "quarter", "trdar_code", "industry_code", "industry_name", "main_analysis_eligible", "sales_supported_industry",
        "store_count", "open_count", "close_count", "sales_amount", "sales_observed", "sales_qoq_change"])
    annual = pd.read_csv(INPUTS["annual"], dtype=IDS)
    context = pd.read_csv(INPUTS["context"], dtype=IDS)
    dim = pd.read_csv(INPUTS["dim"], dtype={"trdar_code": str})
    data = {"fact": fact, "annual": annual, "context": context, "dim": dim}
    wrong = {k: len(v) for k, v in data.items() if len(v) != EXPECTED_ROWS[k]}
    if wrong:
        raise ValueError(f"입력 행 수가 설명과 다릅니다: {wrong} (기대값 {EXPECTED_ROWS})")
    if set(fact["quarter"]) != set(QUARTERS):
        raise ValueError(f"2025년 네 분기만 있어야 합니다: {sorted(set(fact['quarter']))}")
    if not dim["is_tourist"].eq(~dim["main_analysis_eligible"]).all():
        raise ValueError("관광특구 표시(is_tourist)와 main_analysis_eligible이 서로 맞지 않습니다.")
    return data


# ---------------------------------------------------------------- 상권 정보


def build_areas(context: pd.DataFrame, dim: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """상권 하나에 값 하나. 직장·상주인구와 집객시설은 2025년 안에서 바뀌지 않으므로 분기 값으로 다루지 않는다."""
    c = context.loc[context["trdar_code"].isin(dim.loc[~dim["is_tourist"], "trdar_code"])]
    changing = {}
    for col in ["worker_population", "resident_population", "facility_count", "area_km2"]:
        changing[col] = int((c.groupby("trdar_code")[col].nunique(dropna=True) > 1).sum())
        if changing[col]:
            raise ValueError(f"{col} 값이 2025년 안에서 바뀌는 상권이 {changing[col]}곳 있습니다. 분기 값으로 다뤄야 하는지 확인하세요.")
    g = c.groupby("trdar_code").agg(
        area_km2=("area_km2", "first"),
        floating=("floating_population", "mean"),  # 유동인구만 분기마다 바뀌므로 있는 분기의 평균
        floating_quarters=("floating_population", "count"),
        worker=("worker_population", "first"),
        resident=("resident_population", "first"),
        facility=("facility_count", "first"),
    )
    a = dim.loc[~dim["is_tourist"], ["trdar_code", "trdar_name", "trdar_type", "gu_name"]].set_index("trdar_code").join(g)
    for key in ["floating", "worker", "resident"]:
        a[f"{key}_density"] = a[key] / a["area_km2"]
    checks = {"changing_areas_within_2025": changing,
              "floating_quarters": {str(k): int(v) for k, v in a["floating_quarters"].value_counts().sort_index().items()},
              "missing_areas": {k: int(a[k].isna().sum()) for k in ["floating", "worker", "resident", "facility"]}}
    return a.reset_index(), checks


# ---------------------------------------------------------------- 점수 계산 규칙


def shrink_close_rate(d: pd.DataFrame) -> tuple[pd.Series, float]:
    """축소 추정 폐업률(%).

    출처: 김지영/claude_dashboard/build_data.py build_cells 의 포아송-감마 적률 추정.
    점포가 적은 칸은 폐업 한두 건에도 폐업률이 크게 흔들리므로 업종 평균 쪽으로 당긴다.
      업종 폐업률 r = 업종 전체 폐업 / 업종 전체 평균 점포
      기대 폐업 mu = 평균 점포 × r
      alpha = Σ mu² / Σ((폐업 − mu)² − mu)
      축소 폐업률 = (폐업 + alpha) / (평균 점포 + alpha / r) × 100
    """
    by = d.groupby("industry_code")
    rate = by["closes"].transform("sum") / by["stores"].transform("sum")
    expected = d["stores"] * rate
    alpha = float((expected ** 2).sum() / ((d["closes"] - expected) ** 2 - expected).sum())
    shrunk = (d["closes"] + alpha) / (d["stores"] + alpha / rate.where(rate > 0)) * 100
    return shrunk, alpha


def percentile(values: pd.Series, groups: pd.Series, higher_is_better: bool) -> pd.Series:
    """같은 업종 안 백분위 점수(0~100). 동점은 평균 순위, 결측은 결측 그대로 둔다."""
    v = values if higher_is_better else -values
    return v.groupby(groups).rank(method="average", pct=True) * 100


def composite(frame: pd.DataFrame, weights: dict[str, float]) -> tuple[pd.Series, pd.Series]:
    """자료가 있는 영역끼리 가중치를 다시 나눈 가중 평균과 계산에 쓴 영역 수.

    결측 영역은 0점으로 넣지 않고 분자·분모에서 함께 뺀다. 가중치가 모두 0이면 결측이다.
    """
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


# ---------------------------------------------------------------- 상권×업종 연간 표


def build_cells(data: dict[str, pd.DataFrame], areas: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    fact, annual, dim = data["fact"], data["annual"], data["dim"]
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])

    g = fact.groupby(["trdar_code", "industry_code"], as_index=False).agg(
        industry_name=("industry_name", "first"), sales_supported=("sales_supported_industry", "first"),
        stores_sum=("store_count", "sum"), opens=("open_count", "sum"), closes=("close_count", "sum"))
    g["stores"] = g["stores_sum"] / 4  # 점포 행이 없는 분기는 점포 0개로 본 4개 분기 평균
    keep = ["trdar_code", "industry_code", "observed_store_quarters", "observed_sales_quarters", "mean_store_count_observed",
            "annual_close_count", "annual_sales_complete", "annual_monthly_sales_per_store"]
    d = annual[keep].merge(g, on=["trdar_code", "industry_code"], how="outer", validate="one_to_one", indicator=True)
    if not d["_merge"].eq("both").all():
        raise ValueError("연간 표와 분기 패널의 상권×업종 키가 다릅니다.")
    if not np.allclose(d["annual_close_count"], d["closes"]):
        raise ValueError("연간 폐업 건수가 분기 합과 다릅니다.")

    differs = ~np.isclose(d["stores"], d["mean_store_count_observed"])
    checks = {
        "annual_rows": int(len(d)),
        "tourist_rows": int(d["trdar_code"].isin(tourist).sum()),
        # 4개 분기 평균(합 ÷ 4)과 관측 분기만의 평균이 다른 칸. 관측 분기가 4개 미만인 칸에서만 생긴다.
        "stores_vs_observed_mean_diff_cells": int(differs.sum()),
        "stores_vs_observed_mean_diff_cells_ge5": int((differs & d["stores"].ge(MIN_STORES)).sum()),
    }
    d = d.loc[~d["trdar_code"].isin(tourist)].drop(columns=["_merge", "annual_close_count", "mean_store_count_observed"])
    d = d.merge(areas, on="trdar_code", how="left", validate="many_to_one")
    d["group"] = d["industry_code"].str[:3].map(GROUPS)

    # 원값 ---------------------------------------------------------------
    # 매출: 매출 제공 업종에서 4개 분기 매출이 모두 있는 칸만. 없으면 결측이며 0으로 채우지 않는다.
    d["sales_month"] = d["annual_monthly_sales_per_store"].where(d["sales_supported"] & d["annual_sales_complete"].notna())
    d["close_pct"] = (d["closes"] / d["stores"] * 100).where(d["stores"] > 0)
    positive = d["stores"] > 0
    shrunk, alpha = shrink_close_rate(d.loc[positive])
    d["close_pct_shrunk"] = shrunk.reindex(d.index)
    # 경쟁 [가정]: 유동인구 1,000명당 같은 업종 점포 수
    d["competition"] = d["stores"] / (d["floating"].where(d["floating"] > 0) / 1000)

    # 대상 여부와 제외 사유 -----------------------------------------------
    peer = d.loc[d["stores"].ge(MIN_STORES)].groupby("industry_code").size()
    d["peer_count"] = d["industry_code"].map(peer).fillna(0).astype(int)
    d["status"] = np.select(
        [d["stores"].le(0), d["stores"].lt(MIN_STORES), d["peer_count"].lt(MIN_PEERS)],
        [STATUS_EMPTY, STATUS_REFERENCE, STATUS_THIN], default=STATUS_SCORED)
    d["scored"] = d["status"].eq(STATUS_SCORED)

    s = d["scored"]
    sales_peer = d.loc[s & d["sales_month"].notna()].groupby("industry_code").size()
    d["sales_peer_count"] = d["industry_code"].map(sales_peer).fillna(0).astype(int)
    sales_ok = s & d["sales_month"].notna() & d["sales_peer_count"].ge(MIN_PEERS)
    d["sales_note"] = np.select(
        [~s, ~d["sales_supported"], d["sales_month"].isna(), d["sales_peer_count"].lt(MIN_PEERS)],
        ["", "매출 미제공 업종", "4개 분기 매출이 모두 있지는 않음", "업종 안 매출 비교 상권 30곳 미만"], default="")
    demand_parts = ["floating_density", "worker_density", "resident_density"]
    d["demand_note"] = np.where(s & d[demand_parts].isna().any(axis=1), "인구 자료 일부 없음", "")

    # 영역 점수: 점수 대상 칸끼리, 같은 업종 안 백분위 ------------------------
    x = d.loc[s]
    ind = x["industry_code"]
    scores = pd.DataFrame(index=x.index)
    scores["score_sales"] = percentile(x["sales_month"].where(sales_ok[s]), ind, True)
    scores["score_competition"] = percentile(x["competition"], ind, False)
    scores["score_stability"] = percentile(x["close_pct_shrunk"], ind, False)
    for part in demand_parts:
        scores[f"pct_{part.removesuffix('_density')}"] = percentile(x[part], ind, True)
    scores["score_demand"] = scores[["pct_floating", "pct_worker", "pct_resident"]].mean(axis=1, skipna=False)
    d = d.join(scores)
    d["score_total"], d["areas_used"] = composite(d, DEFAULT_WEIGHTS)

    columns = [
        "trdar_code", "trdar_name", "gu_name", "trdar_type", "industry_code", "industry_name", "group",
        "status", "scored", "peer_count", "sales_peer_count",
        "stores", "opens", "closes", "observed_store_quarters", "observed_sales_quarters", "sales_supported",
        "sales_month", "competition", "close_pct", "close_pct_shrunk",
        "area_km2", "floating", "floating_quarters", "worker", "resident", "facility",
        "floating_density", "worker_density", "resident_density",
        "score_sales", "score_competition", "score_stability", "score_demand", "pct_floating", "pct_worker", "pct_resident",
        "score_total", "areas_used", "sales_note", "demand_note",
    ]
    d = d[columns].sort_values(["industry_code", "trdar_code"]).reset_index(drop=True)
    d["observed_sales_quarters"] = d["observed_sales_quarters"].fillna(0).astype(int)
    d["areas_used"] = d["areas_used"].astype(int)
    checks["alpha"] = alpha
    return d, checks


# ---------------------------------------------------------------- 분기 추이 (상세 화면 참고용)


def build_quarters(fact: pd.DataFrame, cells: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """분기별 점포·개폐업·매출. 분기 매출 증감률은 점수에 넣지 않고 상하위 5%를 잘라 참고로만 보여 준다."""
    keys = cells.loc[cells["stores"] > 0, ["trdar_code", "industry_code"]]
    q = fact.merge(keys, on=["trdar_code", "industry_code"], how="inner")
    q = q[["quarter", "trdar_code", "industry_code", "store_count", "open_count", "close_count", "sales_amount", "sales_observed", "sales_qoq_change"]].copy()
    q["sales_month_q"] = (q["sales_amount"] / q["store_count"].where(q["store_count"] > 0) / 3).where(q["sales_observed"])
    observed = q["sales_qoq_change"].dropna()
    low, high = (float(observed.quantile(p)) for p in WINSOR)
    q["qoq_winsor"] = q["sales_qoq_change"].clip(low, high)
    info = {"low_pct": WINSOR[0] * 100, "high_pct": WINSOR[1] * 100, "low": low, "high": high, "observed": int(len(observed))}
    return q.sort_values(["industry_code", "trdar_code", "quarter"]).reset_index(drop=True), info


# ---------------------------------------------------------------- 업종별 가능 여부·설계표


def build_availability(cells: pd.DataFrame, fact: pd.DataFrame) -> pd.DataFrame:
    names = fact.groupby("industry_code").agg(name=("industry_name", "first"), supported=("sales_supported_industry", "first"))
    rows = []
    for code, r in names.sort_index().iterrows():
        c = cells.loc[cells["industry_code"].eq(code)]
        peers = int(c["stores"].ge(MIN_STORES).sum())
        scored = peers >= MIN_PEERS
        sales_scored = int(c["score_sales"].notna().sum())
        raw_sales_peers = int((c["scored"] & c["sales_month"].notna()).sum())
        if not scored:
            reason = f"비교 상권 {peers}곳: 평균 점포 {MIN_STORES}개 이상인 상권이 {MIN_PEERS}곳 미만이라 점수를 만들지 않음"
        elif not r["supported"]:
            reason = "점수 생성. 매출 미제공 업종이라 매출 잠재력은 자료 없음, 나머지 3개 영역으로 계산"
        elif sales_scored == 0:
            reason = f"점수 생성. 4개 분기 매출이 있는 비교 상권이 {raw_sales_peers}곳({MIN_PEERS}곳 미만)이라 매출 잠재력은 자료 없음"
        else:
            reason = "점수 생성 (4개 영역)"
        rows.append({
            "업종코드": code, "업종명": r["name"], "업종군": GROUPS[code[:3]], "매출 제공": "예" if r["supported"] else "아니오",
            "점포가 있는 상권 수": int(c["stores"].gt(0).sum()), "비교 상권 수(평균 점포 5개 이상)": peers,
            "점수 생성": "예" if scored else "아니오", "매출 비교 상권 수(4개 분기 매출)": raw_sales_peers,
            "매출 잠재력 점수": "예" if sales_scored else "아니오", "점수 대상 칸": int(c["scored"].sum()), "사유": reason,
        })
    return pd.DataFrame(rows)


def build_design(cells: pd.DataFrame) -> pd.DataFrame:
    """승인받은 점수 설계표 (2026-11-07). 대상 행 수는 실행할 때 다시 센다."""
    s = cells.loc[cells["scored"]]
    n = lambda col: f"{int(s[col].notna().sum()):,}칸"
    used = s["areas_used"].value_counts().sort_index(ascending=False)
    used_text = " / ".join(f"{k}개 영역 {v:,}칸" for k, v in used.items() if k > 0)
    return pd.DataFrame([
        {"영역": "공통: 점수 대상", "사용할 지표(컬럼)": "stores (store_count 4개 분기 합 ÷ 4), is_tourist · main_analysis_eligible",
         "계산식": "점수를 매길 상권×업종 칸을 고른다", "방향": "-",
         "대상 조건": f"관광특구 아님 + 연간 평균 점포 {MIN_STORES}개 이상 + 같은 업종 비교 상권 {MIN_PEERS}곳 이상",
         "결측 처리": "조건 밖 칸은 점수 없이 원값만 '참고용'으로 보여 줌", "대상 행 수": f"{len(s):,}칸 / {s['industry_code'].nunique()}개 업종", "구분": "팀 결정"},
        {"영역": "① 매출 잠재력", "사용할 지표(컬럼)": "annual_monthly_sales_per_store (점포당 월매출, 원)",
         "계산식": "같은 업종 안 백분위 = rank(pct=True) × 100, 동점은 평균 순위", "방향": "높을수록 좋음",
         "대상 조건": f"공통 + 매출 제공 업종 + 4개 분기 매출이 모두 있음 + 같은 업종 매출 비교 상권 {MIN_PEERS}곳 이상",
         "결측 처리": "매출 미제공 업종 · 4개 분기 미만 · 매출 비교 상권 부족은 '자료 없음' (0으로 채우지 않음)", "대상 행 수": n("score_sales"),
         "구분": "팀 결정. 30곳 규칙을 매출 영역에도 적용 (2026-11-07 승인)"},
        {"영역": "② 경쟁", "사용할 지표(컬럼)": "stores, floating_population (2025년 분기 평균)",
         "계산식": "같은 업종 점포 수 ÷ (유동인구 ÷ 1,000) → 같은 업종 안 백분위", "방향": "낮을수록 좋음 → 뒤집음",
         "대상 조건": "공통", "결측 처리": "유동인구가 없으면 '자료 없음'", "대상 행 수": n("score_competition"), "구분": "[가정]"},
        {"영역": "③ 안정성 (1년치·신뢰도 낮음)", "사용할 지표(컬럼)": "close_count, store_count → 축소 추정 폐업률",
         "계산식": "(연간 폐업 + α) ÷ (평균 점포 + α ÷ 업종 폐업률) × 100 → 같은 업종 안 백분위", "방향": "낮을수록 좋음 → 뒤집음",
         "대상 조건": "공통", "결측 처리": "결측 없음", "대상 행 수": n("score_stability"), "구분": "팀 결정"},
        {"영역": "④ 수요", "사용할 지표(컬럼)": "floating_population, worker_population, resident_population, area_km2",
         "계산식": "세 값을 면적(㎢)으로 나눔 → 각각 같은 업종 안 백분위 → 세 백분위의 평균", "방향": "높을수록 좋음",
         "대상 조건": "공통", "결측 처리": "셋 중 하나라도 없으면 '자료 없음' (2026-11-07 승인)", "대상 행 수": n("score_demand"), "구분": "[가정]"},
        {"영역": "종합", "사용할 지표(컬럼)": "①~④ 영역 점수",
         "계산식": "Σ(가중치 × 점수) ÷ Σ(자료가 있는 영역의 가중치). 기본 가중치 매출 30 · 경쟁 25 · 안정성 15 · 수요 30",
         "방향": "높을수록 같은 업종 안에서 상대적으로 유리", "대상 조건": "공통",
         "결측 처리": "계산에 쓴 영역 수를 함께 표시. 가중치가 모두 0이면 계산하지 않음", "대상 행 수": f"{n('score_total')} ({used_text})",
         "구분": "가중치 [가정, 팀 미확정]"},
    ])


# ---------------------------------------------------------------- 진단값


def spearman(a: pd.Series, b: pd.Series) -> float:
    """순위상관. 두 값이 모두 있는 칸만 순위를 매긴 뒤 상관을 구한다 (scipy 없이 계산)."""
    both = a.notna() & b.notna()
    return float(a[both].rank().corr(b[both].rank()))


def diagnostics(cells: pd.DataFrame) -> dict:
    s = cells.loc[cells["scored"]]
    cols = ["score_sales", "score_competition", "score_stability", "score_demand", "pct_floating", "pct_worker", "pct_resident"]
    corr = s[cols].corr(method="spearman")
    per = pd.Series({code: spearman(g["score_competition"], g["score_demand"]) for code, g in s.groupby("industry_code")})
    names = s.drop_duplicates("industry_code").set_index("industry_code")["industry_name"]
    top = per.sort_values(ascending=False).head(3)
    return {
        "spearman_overall": {a: {b: round(float(corr.loc[a, b]), 4) for b in cols} for a in cols},
        "competition_demand": {
            "overall": round(float(corr.loc["score_competition", "score_demand"]), 4),
            "industry_median": round(float(per.median()), 4),
            "industry_max": round(float(per.max()), 4),
            "industries_ge_0_8": int((per >= 0.8).sum()),
            "top3": [{"업종": names[c], "상관": round(float(v), 4)} for c, v in top.items()],
        },
    }


def counts(cells: pd.DataFrame, checks: dict, availability: pd.DataFrame) -> dict:
    s = cells.loc[cells["scored"]]
    supported = availability["매출 제공"].eq("예")
    scored_ind = availability["점수 생성"].eq("예")
    sales_ind = availability["매출 잠재력 점수"].eq("예")
    return {
        "annual_rows": checks["annual_rows"],
        "by_status": {
            "관광특구 (점수표에서 뺌)": checks["tourist_rows"],
            STATUS_EMPTY: int(cells["status"].eq(STATUS_EMPTY).sum()),
            STATUS_REFERENCE: int(cells["status"].eq(STATUS_REFERENCE).sum()),
            STATUS_THIN: int(cells["status"].eq(STATUS_THIN).sum()),
            STATUS_SCORED: int(len(s)),
        },
        "areas": int(cells["trdar_code"].nunique()),
        "industries": {
            "total": int(len(availability)), "scored": int(scored_ind.sum()), "not_scored": int((~scored_ind).sum()),
            "sales_supported": int(supported.sum()), "sales_scored": int(sales_ind.sum()),
            "scored_without_sales_supply": int((scored_ind & ~supported).sum()),
            "scored_sales_peer_short": int((scored_ind & supported & ~sales_ind).sum()),
        },
        "area_scores": {k: int(s[f"score_{k}"].notna().sum()) for k in AREA_KEYS},
        "areas_used_default": {str(k): int(v) for k, v in s["areas_used"].value_counts().sort_index().items()},
        "sales_missing_reason": {k: int(v) for k, v in s.loc[s["sales_note"].ne(""), "sales_note"].value_counts().sort_index().items()},
        "demand_missing": int(s["score_demand"].isna().sum()),
    }


# ---------------------------------------------------------------- 저장


OUTPUT_NAMES = {
    "scores": "상권_업종_비교점수_2025.parquet",
    "design": "점수_설계표.csv",
    "availability": "업종별_점수_가능여부.csv",
    "quarters": "분기_추이_2025.parquet",
    "meta": "stage4_meta.json",
}


def write_outputs(out: Path, cells, quarters, availability, design, meta) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    p = {k: out / v for k, v in OUTPUT_NAMES.items()}
    cells.to_parquet(p["scores"], index=False, compression="zstd")
    quarters.to_parquet(p["quarters"], index=False, compression="zstd")
    # 엑셀에서 한글이 깨지지 않도록 BOM을 붙인다
    design.to_csv(p["design"], index=False, encoding="utf-8-sig", lineterminator="\n")
    availability.to_csv(p["availability"], index=False, encoding="utf-8-sig", lineterminator="\n")
    p["meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return list(p.values())


def main(out: Path = OUT) -> list[Path]:
    """out은 작업 폴더 안이어야 한다 (검증 때 두 번 실행 비교용 임시 폴더도 작업 폴더 안에 만든다)."""
    out = Path(out).resolve()
    if HERE not in (out, *out.parents):
        raise ValueError(f"결과는 작업 폴더({HERE}) 안에만 씁니다: {out}")
    before = fingerprints()
    data = read_inputs()
    areas, area_checks = build_areas(data["context"], data["dim"])
    cells, checks = build_cells(data, areas)
    quarters, winsor = build_quarters(data["fact"], cells)
    availability = build_availability(cells, data["fact"])
    design = build_design(cells)
    if before != fingerprints():
        raise RuntimeError("실행 중에 입력 파일이 바뀌었습니다.")
    meta = {
        "title": "STEP 4 상권×업종 업종 내 비교 점수 (2025년)",
        "rules": {"min_stores": MIN_STORES, "min_peers": MIN_PEERS, "sales_min_peers": MIN_PEERS,
                  "percentile": "같은 업종의 점수 대상 칸 안에서 rank(method='average', pct=True) × 100"},
        "default_weights": DEFAULT_WEIGHTS,
        "alpha": checks["alpha"],
        "winsor": winsor,
        "input_rows": EXPECTED_ROWS,
        "input_sha256": before,
        "checks_before_use": {
            "stores_definition": "store_count 4개 분기 합 ÷ 4 (점포 행이 없는 분기는 0개)",
            "stores_vs_observed_mean_diff_cells": checks["stores_vs_observed_mean_diff_cells"],
            "stores_vs_observed_mean_diff_cells_ge5": checks["stores_vs_observed_mean_diff_cells_ge5"],
            **area_checks,
        },
        "counts": counts(cells, checks, availability),
        "diagnostics": diagnostics(cells),
        "tourist_areas": int(data["dim"]["is_tourist"].sum()),
        "comparison_areas": int((~data["dim"]["is_tourist"]).sum()),
    }
    return write_outputs(out, cells, quarters, availability, design, meta)


if __name__ == "__main__":
    for path in main():
        print(f"{path.name:32s} {path.stat().st_size / 1e6:6.2f} MB")
