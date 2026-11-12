"""STEP5: 8유형의 데이터 적합성을 분석하고 보류를 보존한 대리분류 후보를 만든다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "data"
REPORT = HERE / "report"
JY = REPO / "김지영/claude_dashboard/data"
STEP = REPO / "김지영/step2_3/data"
STEP4 = HERE.parent / "step4_dashboard/data"
KEYS = ["trdar_code", "industry_code"]
IDS = {"quarter": str, "trdar_code": str, "industry_code": str}
DEFAULT = {"lv_center": .5, "lv_band": .05, "ep_center": 50., "sd_center": 50., "rank_band": 5.}
WEIGHTS = {"sales": 30, "comp": 25, "stab": 15, "dem": 30}
INPUTS = {
    "scores": STEP4 / "상권_업종_비교점수_2025.parquet",
    "industries": STEP4 / "업종별_점수_가능여부.csv",
    "cells": JY / "cells.parquet", "areas": JY / "areas.parquet", "meta": JY / "meta.json",
    "fact": STEP / "fact_trdar_industry_quarter.csv.gz", "context": STEP / "trdar_quarter_context.csv.gz",
    "dim": STEP / "dim_trdar.csv.gz", "dictionary": REPO / "김지영/step2_3/feature_dictionary.csv",
    "plan": REPO / "seoul-commercial-analysis/docs/ANALYSIS_PLAN.md", "types": HERE / "types.json",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_hashes():
    return {p.relative_to(REPO).as_posix(): sha(p) for p in INPUTS.values()}


def finite(s):
    return s.notna() & np.isfinite(s)


def cv(series):
    """네 분기의 모표준편차/평균. 결측·분모 0이면 계산하지 않는다."""
    if len(series) != 4 or not finite(series).all() or series.mean() <= 0:
        return np.nan
    return float(series.std(ddof=0) / series.mean())


def rank_signal(d, column, eligible):
    peers = d.loc[eligible].groupby("industry_code").size()
    n = d.industry_code.map(peers).fillna(0).astype(int)
    use = eligible & n.ge(30)
    pct = pd.Series(np.nan, index=d.index)
    pct.loc[use] = d.loc[use].groupby("industry_code")[column].rank(method="average", pct=True) * 100
    return pct, n


def make_features():
    d = pd.read_parquet(INPUTS["scores"])
    cells = pd.read_parquet(INPUTS["cells"])
    areas = pd.read_parquet(INPUTS["areas"])
    dim = pd.read_csv(INPUTS["dim"], dtype={"trdar_code": str})
    fact = pd.read_csv(INPUTS["fact"], dtype=IDS, usecols=[*IDS, "store_count", "sales_amount", "sales_count", "sales_observed", "main_analysis_eligible"])
    context = pd.read_csv(INPUTS["context"], dtype=IDS,
                          usecols=["quarter", "trdar_code", "floating_population", "worker_population", "resident_population"])
    assert len(fact) == 304775 and len(context) == 6600 and len(dim) == 1650
    assert set(fact.quarter) == set(context.quarter) == {"20251", "20252", "20253", "20254"}
    assert not fact.duplicated([*IDS]).any()
    assert not context.duplicated(["trdar_code", "quarter"]).any()
    tourist = set(dim.loc[dim.is_tourist, "trdar_code"])
    assert not d.trdar_code.isin(tourist).any()
    d = d.merge(cells[[*KEYS, "ticket", "repeated_sales"]], on=KEYS, validate="one_to_one")
    f = fact.loc[fact.main_analysis_eligible].copy()
    f["monthly"] = (f.sales_amount / f.store_count.where(f.store_count > 0) / 3).where(f.sales_observed)
    annual = f.groupby(KEYS).agg(
        monthly_n=("monthly", "count"), sales_month_cv=("monthly", cv),
        observed_quarters=("sales_observed", "sum"),
        annual_sales=("sales_amount", lambda s: s.sum(min_count=1)),
        annual_transactions=("sales_count", lambda s: s.sum(min_count=1)),
    ).reset_index()
    annual["ticket_recomputed"] = annual.annual_sales / annual.annual_transactions.where(annual.annual_transactions > 0)
    d = d.merge(annual, on=KEYS, validate="one_to_one", how="left")
    both = finite(d.ticket) & finite(d.ticket_recomputed)
    assert np.allclose(d.loc[both, "ticket"], d.loc[both, "ticket_recomputed"], rtol=1e-10, atol=1e-5)
    float_cv = context.groupby("trdar_code").floating_population.agg(floating_n="count", floating_cv=cv).reset_index()
    d = d.merge(float_cv, on="trdar_code", validate="many_to_one", how="left")
    d["resident_share_proxy"] = d.resident / (d.resident + d.worker).where(d.resident + d.worker > 0)
    d["lv_data_valid"] = finite(d.resident) & finite(d.worker) & d.resident.ge(0) & d.worker.ge(0) & (d.resident + d.worker).gt(0)
    target = d.score_status.eq("점수 대상")
    ep_valid = target & d.sales_quarters.eq(4) & d.observed_quarters.eq(4) & finite(d.ticket) & d.ticket.gt(0) & ~d.repeated_sales
    sd_valid = target & d.monthly_n.eq(4) & d.floating_n.eq(4) & finite(d.sales_month_cv) & finite(d.floating_cv) & ~d.repeated_sales
    d["ep_valid_before_peers"] = ep_valid
    d["sd_valid_before_peers"] = sd_valid
    d["ticket_pct"], d["ep_peers"] = rank_signal(d, "ticket", ep_valid)
    d["sales_cv_pct"], d["sd_peers"] = rank_signal(d, "sales_month_cv", sd_valid)
    d["floating_cv_pct"], _ = rank_signal(d, "floating_cv", sd_valid)
    d["dynamism_index"] = (d.sales_cv_pct + d.floating_cv_pct) / 2
    d = d.sort_values(KEYS).reset_index(drop=True)
    area_lv = areas[["trdar_code", "trdar_name", "gu_name", "resident", "worker", "floating"]].copy()
    area_lv["resident_share_proxy"] = area_lv.resident / (area_lv.resident + area_lv.worker).where(area_lv.resident + area_lv.worker > 0)
    area_lv["valid"] = finite(area_lv.resident) & finite(area_lv.worker) & area_lv.resident.ge(0) & area_lv.worker.ge(0) & (area_lv.resident + area_lv.worker).gt(0)
    audit = {
        "fact_rows": len(fact), "context_rows": len(context), "dim_rows": len(dim), "areas": len(areas),
        "cells": len(d), "quarters": sorted(fact.quarter.unique()),
        "ticket_recomputed_cells": int(both.sum()),
        "ticket_max_absolute_difference": float((d.ticket - d.ticket_recomputed).abs().max()),
        "tourist_cells": int(d.trdar_code.isin(tourist).sum()),
    }
    return d, area_lv, audit


def split_axis(values, low, high, left, right):
    result = pd.Series(pd.NA, index=values.index, dtype="string")
    result.loc[values.lt(low).fillna(False)] = left
    result.loc[values.gt(high).fillna(False)] = right
    return result


def classify(features, params=None, reasons=True):
    p = dict(DEFAULT, **(params or {}))
    d = features.copy()
    target = d.score_status.eq("점수 대상")
    d["LV"] = split_axis(d.resident_share_proxy.where(target & d.lv_data_valid), p["lv_center"]-p["lv_band"], p["lv_center"]+p["lv_band"], "V", "L")
    d["EP"] = split_axis(d.ticket_pct, p["ep_center"]-p["rank_band"], p["ep_center"]+p["rank_band"], "E", "P")
    d["SD"] = split_axis(d.dynamism_index, p["sd_center"]-p["rank_band"], p["sd_center"]+p["rank_band"], "S", "D")
    full = target & d[["LV", "EP", "SD"]].notna().all(axis=1)
    d["candidate_type"] = (d.LV + d.EP + d.SD).where(full)
    d["known_axes"] = d[["LV", "EP", "SD"]].notna().sum(axis=1)
    d["type_status"] = np.select([~target, full], ["STEP4 점수 대상 아님", "분석용 대리분류 후보"], default="유형 보류")
    if reasons:
        d["LV_reason"] = np.select([~target, ~d.lv_data_valid, d.LV.isna()],
                                    ["STEP4 점수 대상 아님", "주민·직장 자료 부족 또는 합계 0", "주민·직장 비중 경계 구간"], default="주민·직장 구성의 대리 판정")
        d["EP_reason"] = np.select([~target, d.sales_quarters.ne(4) | d.observed_quarters.ne(4), d.repeated_sales,
                                    ~d.ep_valid_before_peers, d.ep_peers.lt(30), d.EP.isna()],
                                   ["STEP4 점수 대상 아님", "매출 네 분기 미관측", "네 분기 매출 동일: 품질 확인 필요",
                                    "결제 건당 금액 자료 부족", "유효 비교 상권 30곳 미만", "결제 건당 금액 백분위 경계 구간"], default="업종 내 결제 건당 금액의 대리 판정")
        d["SD_reason"] = np.select([~target, d.repeated_sales, ~d.sd_valid_before_peers, d.sd_peers.lt(30), d.SD.isna()],
                                   ["STEP4 점수 대상 아님", "네 분기 매출 동일: 품질 확인 필요", "매출·유동 변동성 네 분기 자료 부족",
                                    "유효 비교 상권 30곳 미만", "관측 변동성 지수 경계 구간"], default="연내 변동성의 대리 판정")
        d["hold_reason"] = ""
        for axis in ["LV", "EP", "SD"]:
            d["hold_reason"] += np.where(d[axis].isna(), axis + ": " + d[axis + "_reason"] + "; ", "")
        d["hold_reason"] = d.hold_reason.str.rstrip("; ")
    return d


def profile_score(frame, demand_mode="avg"):
    columns = ["score_sales", "score_comp", "score_stab", f"score_dem_{demand_mode}"]
    weights = np.array([30., 25., 15., 30.])
    values = frame[columns].to_numpy(dtype=float)
    available = np.isfinite(values)
    den = (available * weights).sum(axis=1)
    num = np.where(available, values, 0).dot(weights)
    result = np.divide(num, den, out=np.full(len(frame), np.nan), where=den > 0)
    return pd.Series(result, index=frame.index).where(frame.score_status.eq("점수 대상"))


def load_type_config():
    return json.loads((HERE / "types.json").read_text(encoding="utf-8"))


def normalize_type(code):
    types = load_type_config()["types"]
    mapping = {r["legacy_code"]: r["code"] for r in types} | {r["code"]: r["code"] for r in types}
    if code not in mapping:
        raise ValueError("지원하지 않는 유형입니다: " + code)
    return mapping[code]


def explore(frame, industry_code, type_code, limit=10, allow_partial=False, demand_link=True):
    code = normalize_type(type_code)
    d = frame.loc[frame.industry_code.eq(industry_code) & frame.score_status.eq("점수 대상")].copy()
    if industry_code not in set(frame.industry_code):
        raise ValueError("없는 업종 코드입니다: " + industry_code)
    compatible = pd.Series(True, index=d.index)
    for axis, letter in zip(["LV", "EP", "SD"], code):
        compatible &= d[axis].eq(letter).fillna(allow_partial)
    compatible &= d.known_axes.gt(0) if allow_partial else d.candidate_type.eq(code).fillna(False)
    d = d.loc[compatible].copy()
    mode = ("resident" if code[0] == "L" else "floating") if demand_link else "avg"
    d["requested_type"] = code
    d["match_status"] = np.where(d.candidate_type.eq(code).fillna(False), "세 축 일치 후보", "부분 일치: 미판정 축 있음")
    d["demand_mode_assumption"] = mode
    d["exploration_score"] = profile_score(d, mode)
    d["budget_fit"] = "비용 자료 없어 판단 불가"
    d["user_financial_profile"] = "사용자 응답 없음: 추론하지 않음"
    d = d.sort_values(["known_axes", "exploration_score", "stores", "trdar_code"], ascending=[False, False, False, True]).head(limit)
    cols = ["industry_code", "industry_name", "trdar_code", "trdar_name", "gu_name", "requested_type", "candidate_type", "LV", "EP", "SD",
            "known_axes", "match_status", "exploration_score", "score_total_default", "demand_mode_assumption", "stores", "ticket",
            "resident_share_proxy", "sales_month_cv", "floating_cv", "dynamism_index", "budget_fit", "user_financial_profile"]
    return d[cols].reset_index(drop=True)


def sensitivity(features, baseline):
    variants = {
        "기본": {}, "백분위 경계구간 없음": {"rank_band": 0}, "백분위 경계구간 ±10": {"rank_band": 10},
        "L/V 중심 0.35": {"lv_center": .35}, "L/V 중심 0.65": {"lv_center": .65},
        "E/P 중심 35": {"ep_center": 35}, "E/P 중심 65": {"ep_center": 65},
        "S/D 중심 35": {"sd_center": 35}, "S/D 중심 65": {"sd_center": 65},
    }
    rows = []
    for name, params in variants.items():
        result = classify(features, params, reasons=False)
        a, b = baseline.candidate_type, result.candidate_type
        both = a.notna() & b.notna()
        row = {"설정": name, "유형후보_수": int(b.notna().sum()), "점수대상중_보류": int((result.score_status.eq("점수 대상") & b.isna()).sum()),
               "기본과_동시판정": int(both.sum()), "동시판정중_유형변경": int(a.loc[both].ne(b.loc[both]).sum()),
               "판정가능여부_변경": int(a.notna().ne(b.notna()).sum())}
        for code in [r["code"] for r in load_type_config()["types"]]:
            row[code] = int(b.eq(code).fillna(False).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def save_csv(frame, path):
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def main():
    before = input_hashes()
    features, area_lv, audit = make_features()
    d = classify(features)
    OUT.mkdir(exist_ok=True)
    REPORT.mkdir(exist_ok=True)
    d.to_parquet(OUT / "상권업종_유형후보_2025.parquet", index=False)
    # gzip 메타데이터 시간을 고정해 재실행 시 바이트 재현성을 보장한다.
    d.to_csv(OUT / "상권업종_유형후보_2025.csv.gz", index=False, encoding="utf-8-sig", lineterminator="\n", compression={"method": "gzip", "mtime": 0})
    area_lv["LV"] = split_axis(area_lv.resident_share_proxy.where(area_lv.valid), .45, .55, "V", "L")
    save_csv(area_lv.sort_values("trdar_code"), OUT / "상권별_LV_대리지표.csv")
    config = load_type_config()
    types = pd.DataFrame(config["types"])
    types["가중치_상태"] = "유형별 차등 근거 없음: 공통 기본 가중치 유지"
    types["수요연결_가정"] = types.code.str[0].map({"L": "resident", "V": "floating"})
    for key, value in WEIGHTS.items():
        types[f"weight_{key}"] = value
    types["후보_조합_수"] = types.code.map(d.candidate_type.value_counts()).fillna(0).astype(int)
    save_csv(types, OUT / "8유형_정의와_결과.csv")
    by_industry = d.groupby(["industry_code", "industry_name"]).agg(
        전체_조합=("trdar_code", "size"), STEP4_점수대상=("score_status", lambda s: int(s.eq("점수 대상").sum())),
        LV_판정=("LV", "count"), EP_판정=("EP", "count"), SD_판정=("SD", "count"), 유형후보=("candidate_type", "count"),
        EP_유효비교=("ep_peers", "first"), SD_유효비교=("sd_peers", "first"),
    ).reset_index()
    save_csv(by_industry, OUT / "업종별_분류가능여부.csv")
    save_csv(sensitivity(features, d), OUT / "임계값_민감도.csv")
    hold = []
    for axis in ["LV", "EP", "SD"]:
        selected = d.score_status.eq("점수 대상") & d[axis].isna()
        for reason, n in d.loc[selected, axis + "_reason"].value_counts().items():
            hold.append({"축": axis, "보류_사유": reason, "조합_수": int(n)})
    save_csv(pd.DataFrame(hold), OUT / "축별_보류사유.csv")
    examples, ordering = [], []
    for code in types.code:
        base = explore(d, "CS100010", code, demand_link=False)
        linked = explore(d, "CS100010", code)
        if len(linked):
            examples.append(linked)
        ordering.append({"업종": "커피-음료", "유형": code, "선택_후보수": len(linked),
                         "공통수요와_연결수요_상위후보_교체": len(set(base.trdar_code) - set(linked.trdar_code))})
    example = pd.concat(examples, ignore_index=True) if examples else explore(d, "CS100010", "LES")
    save_csv(example, OUT / "커피음료_유형별_탐색예시.csv")
    save_csv(pd.DataFrame(ordering), OUT / "커피음료_수요연결_민감도.csv")
    audit["classification"] = {
        "target_cells": int(d.score_status.eq("점수 대상").sum()), "full_type_candidates": int(d.candidate_type.notna().sum()),
        "target_held": int((d.score_status.eq("점수 대상") & d.candidate_type.isna()).sum()),
        "LV_known": int(d.LV.notna().sum()), "EP_known": int(d.EP.notna().sum()), "SD_known": int(d.SD.notna().sum()),
        "supported_industries_with_candidates": int(d.loc[d.candidate_type.notna(), "industry_code"].nunique()),
    }
    audit["params"] = DEFAULT
    audit["input_sha256"] = before
    audit["scope"] = "상권×업종의 분석용 대리분류. 실제 고객 성향·금융 성향·성장성·창업 성과를 입증하지 않음."
    (OUT / "analysis_meta.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert before == input_hashes(), "입력 파일이 변경되었습니다."
    print(json.dumps(audit["classification"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
