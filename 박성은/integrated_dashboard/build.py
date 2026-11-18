"""팀 산출물을 읽기만 하여 통합 분석·웹 데이터를 재생성한다. 원본/다른 팀원 폴더는 수정하지 않는다."""
from __future__ import annotations

import ast
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs

from model import VERSION, WEIGHTS, TYPE_NAMES, SD_MAP, score, lv_axis, ep_axis, explore

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "data"
WEB = HERE / "dist"
REPORT = HERE / "report"
FILES = {
    "scores": REPO / "박성은/step4_dashboard/data/상권_업종_비교점수_2025.parquet",
    "jiyeong_scores": REPO / "김지영/step4_dashboard/data/상권_업종_비교점수_2025.parquet",
    "seunghee_types": REPO / "이승희/step5_recommend/data/상권업종_유형_2025.parquet",
    "previous_types": REPO / "박성은/step5_personalization/data/상권업종_유형후보_2025.parquet",
    "fact": REPO / "김지영/step2_3/data/fact_trdar_industry_quarter.csv.gz",
    "context": REPO / "김지영/step2_3/data/trdar_quarter_context.csv.gz",
    "dim": REPO / "김지영/step2_3/data/dim_trdar.csv.gz",
    "mart": REPO / "이승희/data/processed/stage2/상권_분기_마트.csv",
    "cells": REPO / "김지영/claude_dashboard/data/cells.parquet",
    "areas": REPO / "김지영/claude_dashboard/data/areas.parquet",
    "meta": REPO / "김지영/claude_dashboard/data/meta.json",
    "quarters": REPO / "박성은/step4_dashboard/data/quarter_mart.parquet",
    "geometry": REPO / "박성은/step4_dashboard/data/map_geometry.json",
    "quiz_source": REPO / "이승희/step5_recommend/quiz.py",
    "config": HERE / "config.json",
    "model_code": HERE / "model.py",
    "builder_code": HERE / "build.py",
}


def digest(p):
    data = p.read_bytes()
    if p.suffix in {".csv", ".json", ".md", ".py"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def hashes():
    return {p.relative_to(REPO).as_posix(): digest(p) for p in FILES.values()}


def records(d):
    return json.loads(d.to_json(orient="records", force_ascii=False, double_precision=12))


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def csv_write(d, path):
    d.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def rank_corr(a, b):
    valid = a.notna() & b.notna()
    return float(a.loc[valid].rank().corr(b.loc[valid].rank())) if valid.sum() > 1 else None


def questions():
    tree = ast.parse(FILES["quiz_source"].read_text(encoding="utf-8-sig"))
    original = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "QUESTIONS" for t in n.targets))
    # 영업 기간 지표로 확인할 수 없는 수익·폐업 빈도·새 손님 증가 표현을 피한다.
    revised = {
        11: ("상권을 둘러볼 때 더 끌리는 환경은?", ("오랫동안 운영한 가게들이 자리 잡은 거리", "S"), ("영업 이력이 짧은 가게들이 주로 있는 거리", "D")),
        12: ("주변 가게의 영업 이력이 짧은 곳을 본다면?", ("새롭게 자리 잡는 가게들과 함께 시도해 보고 싶다", "D"), ("오래 운영한 가게들 사이에서 시작하고 싶다", "S")),
        13: ("창업 후 운영 방식으로 더 편한 쪽은?", ("일정한 콘셉트로 꾸준히 단골을 쌓는다", "S"), ("반응을 보며 메뉴와 콘셉트를 계속 조정한다", "D")),
        14: ("상권의 영업 기간 설명을 읽고 더 살펴보고 싶은 곳은?", ("운영 중·폐업한 가게 모두 서울 평균보다 영업 기간이 짧은 곳", "D"), ("운영 중·폐업한 가게 모두 서울 평균보다 영업 기간이 긴 곳", "S")),
        15: ("주변 매장 분위기로 더 마음이 가는 쪽은?", ("오래된 가게들이 축적한 분위기", "S"), ("영업을 시작한 지 오래되지 않은 가게들의 분위기", "D")),
    }
    result = []
    for no, axis, text, a, b in original:
        if no in revised:
            text, a, b = revised[no]
        result.append({"id": no, "axis": axis, "text": text, "options": [{"label": a[0], "value": a[1]}, {"label": b[0], "value": b[1]}], "revised": no in revised})
    # 축이 연속해서 몰리지 않도록 표시 순서만 섞는다. 채점·문항 번호는 보존한다.
    order = [1, 6, 11, 2, 7, 12, 3, 8, 13, 4, 9, 14, 5, 10, 15]
    return [next(q for q in result if q["id"] == no) for no in order]


def build_data():
    before = hashes()
    d = pd.read_parquet(FILES["scores"])
    keys = ["trdar_code", "industry_code"]
    assert not d.duplicated(keys).any() and len(d) == 76591
    fact = pd.read_csv(FILES["fact"], dtype={**dict.fromkeys(keys, str), "quarter": str}, usecols=[*keys, "quarter", "store_count", "close_count", "sales_amount", "sales_count", "sales_observed"])
    context = pd.read_csv(FILES["context"], dtype={"trdar_code": str, "quarter": str}, usecols=["trdar_code", "quarter", "resident_population", "worker_population", "floating_population"])
    dim = pd.read_csv(FILES["dim"], dtype={"trdar_code": str})
    assert len(fact) == 304775 and len(context) == 6600 and len(dim) == 1650
    assert not fact.duplicated([*keys, "quarter"]).any() and not context.duplicated(["trdar_code", "quarter"]).any()
    assert set(fact.quarter) == set(context.quarter) == {"20251", "20252", "20253", "20254"}
    assert not d.trdar_code.isin(dim.loc[dim.is_tourist, "trdar_code"]).any()
    independent = fact.groupby(keys).agg(store_sum=("store_count", "sum"), closes=("close_count", "sum"), sales=("sales_amount", lambda x: x.sum(min_count=1)), transactions=("sales_count", lambda x: x.sum(min_count=1)), sales_n=("sales_observed", "sum"))
    check = d[keys + ["stores", "closes"]].merge(independent, on=keys, suffixes=("", "_check"), validate="one_to_one")
    assert np.allclose(check.stores, check.store_sum / 4) and np.array_equal(check.closes, check.closes_check)
    cells = pd.read_parquet(FILES["cells"])[keys + ["ticket", "repeated_sales"]]
    d = d.merge(cells, on=keys, validate="one_to_one")
    ticket_check = d[keys + ["ticket"]].merge(independent, on=keys, validate="one_to_one")
    ok = ticket_check.ticket.notna() & ticket_check.transactions.gt(0)
    assert np.allclose(ticket_check.loc[ok, "ticket"], ticket_check.loc[ok, "sales"] / ticket_check.loc[ok, "transactions"])
    areas = pd.read_parquet(FILES["areas"])
    assert len(areas) == 1644 and areas.trdar_code.is_unique
    for col in ["worker_population", "resident_population"]:
        assert context.groupby("trdar_code")[col].nunique().le(1).all()
    mart = pd.read_csv(FILES["mart"], encoding="utf-8-sig", dtype={"상권_코드": str, "기준_년분기_코드": str}, usecols=["상권_코드", "기준_년분기_코드", "상권_변화_지표", "상권_변화_지표_명", "운영_영업_개월_평균", "폐업_영업_개월_평균"])
    assert len(mart) == 6600 and not mart.duplicated(["상권_코드", "기준_년분기_코드"]).any()
    q4 = mart.loc[mart["기준_년분기_코드"].eq("20254")].rename(columns={"상권_코드": "trdar_code", "상권_변화_지표": "chg_code", "상권_변화_지표_명": "chg_name", "운영_영업_개월_평균": "run_months", "폐업_영업_개월_평균": "closed_months", "서울_운영_영업_개월_평균": "seoul_run_months", "서울_폐업_영업_개월_평균": "seoul_closed_months"}).drop(columns="기준_년분기_코드")
    codes = {"HH": "정체", "LL": "다이나믹", "LH": "상권확장", "HL": "상권축소"}
    assert q4.chg_code.map(codes).eq(q4.chg_name).all()
    area_axes = areas[["trdar_code", "resident", "worker"]].merge(q4, on="trdar_code", validate="one_to_one")
    # 공유 마트에는 서울 평균 두 열이 없다. 임의로 채우지 않고 제공된 공식 코드를 사용한다.
    area_axes["seoul_run_months"] = np.nan
    area_axes["seoul_closed_months"] = np.nan
    area_axes["resident_share_proxy"], area_axes["LV_area"] = lv_axis(area_axes.resident, area_axes.worker)
    area_axes["SD_area"] = area_axes.chg_code.map(SD_MAP).astype("string")
    year = mart.groupby("상권_코드")["상권_변화_지표"].nunique()
    area_axes["sd_same_all_year"] = area_axes.trdar_code.map(year).eq(1)
    d = d.merge(area_axes.drop(columns=["resident", "worker"]), on="trdar_code", validate="many_to_one")
    target = d.score_status.eq("점수 대상")
    d["LV"] = d.LV_area.where(target)
    d["ticket_pct"], d["EP"], d["ep_peers"] = ep_axis(d)
    d["SD"] = d.SD_area.where(target)
    d["known_axes"] = d[["LV", "EP", "SD"]].notna().sum(axis=1)
    d["candidate_type"] = (d.LV + d.EP + d.SD).where(target & d.known_axes.eq(3))
    reference = pd.read_parquet(FILES["seunghee_types"])[keys + ["EP", "ticket_pct", "type_full"]].rename(columns={"EP":"seunghee_EP","ticket_pct":"seunghee_ticket_pct","type_full":"seunghee_type"})
    d = d.merge(reference,on=keys,validate="one_to_one")
    d["boundary_changed"] = d.EP.fillna("?").ne(d.seunghee_EP.fillna("?"))
    assert d.loc[d.boundary_changed,"ticket_pct"].isin([45.,55.]).all()
    assert d.loc[d.boundary_changed,"EP"].isna().all()
    d["type_status"] = np.select([~target, d.candidate_type.notna()], ["점수 대상 아님", "세 축 판정"], default="일부 축 보류")
    d["LV_reason"] = np.select([~target, d.resident_share_proxy.isna(), d.LV.isna()], ["점수 대상 아님", "상주·직장인구 부족 또는 합계 0", "상주·직장 구성 45~55% 경계"], default="상주·직장 구성의 대리 판정")
    d["EP_reason"] = np.select([~target, d.sales_quarters.ne(4), d.repeated_sales, ~d.ticket.gt(0), d.ep_peers.lt(30), d.EP.isna()], ["점수 대상 아님", "네 분기 매출 미관측", "네 분기 동일 매출: 품질 확인", "건당 금액 자료 부족", "유효 비교 상권 30곳 미만", "건당 금액 백분위 45~55 경계"], default="희망 업종의 건당 금액 상대 수준")
    d["SD_reason"] = np.select([~target, d.chg_code.isna(), d.SD.isna()], ["점수 대상 아님", "2025Q4 상권변화지표 없음", "공식 " + d.chg_name.fillna("자료 없음") + ": S/D에 대응하지 않음"], default="2025Q4 " + d.chg_name.fillna("") + "의 영업 기간 특성")
    d["hold_reason"] = ""
    for axis in ["LV", "EP", "SD"]:
        d["hold_reason"] += np.where(d[axis].isna(), axis + ": " + d[axis + "_reason"] + "; ", "")
    d["hold_reason"] = d.hold_reason.str.rstrip("; ")
    d["score_total_previous"] = d.score_total_default
    d["score_dem_available"] = d.score_dem_avg
    parts = ["score_dem_floating", "score_dem_worker", "score_dem_resident"]
    d["score_dem_avg"] = d[parts].mean(axis=1, skipna=False)
    d["score_total_default"], d["n_areas_default"] = score(d)
    d["default_delta"] = d.score_total_default - d.score_total_previous
    previous = pd.read_parquet(FILES["previous_types"])[keys + ["candidate_type", "SD", "sales_month_cv", "floating_cv", "dynamism_index"]].rename(columns={"candidate_type": "previous_type", "SD": "volatility_SD"})
    d = d.merge(previous, on=keys, validate="one_to_one")
    jy = pd.read_parquet(FILES["jiyeong_scores"])[keys + ["score_total", "score_demand"]]
    compare = d.merge(jy, on=keys, validate="one_to_one")
    assert np.allclose(compare.loc[target, "score_total_default"], compare.loc[target, "score_total"], atol=1e-9)
    assert before == hashes(), "입력 파일이 실행 중 바뀜"
    return d.sort_values(["industry_code", "trdar_code"]).reset_index(drop=True), area_axes, before


def summarize(d, areas, config):
    t = d.loc[d.score_status.eq("점수 대상")]
    types = [{"code": c, "name": n, "count": int(d.candidate_type.eq(c).fillna(False).sum())} for c, n in TYPE_NAMES.items()]
    coverage = []
    for code, g in d.groupby("industry_code"):
        coverage.append({"code": code, "name": g.industry_name.iloc[0], "rows": len(g), "target": int(g.score_status.eq("점수 대상").sum()), "full": int(g.candidate_type.notna().sum()), "sales": int(g.score_sales.notna().sum()), "EP": int(g.EP.notna().sum())})
    scenarios = [
        ("통합 기본", WEIGHTS, "avg"), ("일부 인구 평균", WEIGHTS, "available"),
        ("안정성 제외", dict(WEIGHTS, stab=0), "avg"), ("경쟁 제외", dict(WEIGHTS, comp=0), "avg"),
        ("모든 영역 동일", dict.fromkeys(WEIGHTS, 25), "avg"),
        ("S/G 안정 가중치 대안", {"sales": 20, "comp": 30, "stab": 30, "dem": 20}, "avg"),
        ("S/G 성장 가중치 대안", {"sales": 35, "comp": 15, "stab": 10, "dem": 40}, "avg"),
    ]
    sensitivity = []
    for name, weights, mode in scenarios:
        corr, kept = [], []
        alt, _ = score(t, weights, mode)
        for _, g in t.groupby("industry_code"):
            base = g.sort_values(["score_total_default", "stores", "trdar_code"], ascending=[False, False, True]).head(10)
            b = g.assign(alternative=alt.loc[g.index]).sort_values(["alternative", "stores", "trdar_code"], ascending=[False, False, True]).head(10)
            corr.append(rank_corr(g.score_total_default, alt.loc[g.index]))
            kept.append(len(set(base.trdar_code) & set(b.trdar_code)))
        sensitivity.append({"name": name, "weights": weights, "mode": mode, "rank_correlation_median": float(np.median(corr)), "rank_correlation_min": float(np.min(corr)), "top10_retained_median": float(np.median(kept)), "top10_retained_min": int(np.min(kept))})
    holds = []
    for axis in ["LV", "EP", "SD"]:
        holds += [{"axis": axis, "reason": reason, "count": int(n)} for reason, n in t.loc[t[axis].isna(), axis + "_reason"].value_counts().items()]
    both = t.SD.notna() & t.volatility_SD.notna()
    counts = {"rows": len(d), "areas": int(d.trdar_code.nunique()), "industries": 100, "target": len(t), "scored_industries": int(t.industry_code.nunique()), "sales_scored": int(t.score_sales.notna().sum()), "full": int(t.candidate_type.notna().sum()), "held": int(t.candidate_type.isna().sum()), "typed_industries": int(t.loc[t.candidate_type.notna(), "industry_code"].nunique()), "demand_missing": int(t.score_dem_avg.isna().sum()), "default_changed": int(t.default_delta.abs().gt(1e-8).sum()), "boundary_reclassified":int(t.boundary_changed.sum()), "max_score_change": float(t.default_delta.abs().max()), "sd_both_known": int(both.sum()), "sd_agreement": float(t.loc[both, "SD"].eq(t.loc[both, "volatility_SD"]).mean())}
    meta = {"config": config, "counts": counts, "types": types, "industries": sorted(coverage, key=lambda r:r["name"]), "districts": sorted(d.gu_name.unique()), "holds": holds, "sensitivity": sensitivity, "area_sd": {str(k): int(v) for k, v in areas.chg_name.value_counts().items()}, "sd_same_all_year": int(areas.sd_same_all_year.sum()), "competition_demand_correlation": rank_corr(t.score_comp, t.score_dem_avg), "questions": questions(), "freshness": json.loads(FILES["meta"].read_text(encoding="utf-8"))["freshness"]}
    return meta


def report(d, meta):
    c = meta["counts"]
    coffee = d.loc[d.industry_code.eq("CS100010") & d.score_status.eq("점수 대상")].sort_values(["score_total_default", "stores", "trdar_code"], ascending=[False, False, True]).head(5)
    text = f"""# SpotFit 통합 분석 보고서

분석 기준 {VERSION} · 2026-11-18 · 입력 기준 커밋 {meta['config']['source_commit']}

사용자의 통합 작업 요청에 따라 박성은 폴더에서 작성한 하나의 구현 기준입니다. 팀 전체가 승인한 기준이나 검증된 창업 성공 모델로 주장하지 않습니다.

## 통합한 내용

김지영의 공통 패널·원값과 세 인구 완비 조건, 이승희의 점수·공식 S/D·검사지 구조, 박성은의 결측 검증·분기 변동성·공유 화면을 결합했습니다. 상권×업종 단위 E/P를 사용하고 L/V와 공식 S/D는 상권 속성을 연결합니다. S/D는 2025Q4 HH→S, LL→D로 대응하며 LH/HL은 공식 명칭을 보존하고 대응을 보류합니다. 이 대응 자체는 분석 가정입니다.

## 계산한 결과

- 관광특구를 제외한 {c['areas']:,}개 상권, 100개 업종의 {c['rows']:,}개 상권×업종 조합입니다.
- 평균 점포 5개·업종 비교 30곳 기준의 점수 대상 {c['target']:,}개, {c['scored_industries']}개 업종입니다. 매출 영역 점수가 있는 조합은 {c['sales_scored']:,}개입니다.
- 세 축 완전 판정 {c['full']:,}개, 대상 중 보류 {c['held']:,}개, 완전 판정 가능한 업종 {c['typed_industries']}개입니다. 보류를 0 또는 임의 유형으로 채우지 않았습니다.
- 승희의 완전 판정 7,680개와 비교하면 {c['boundary_reclassified']}개가 경계 보류로 바뀌었습니다. 대청초등학교·제과점과 천호역·PC방은 백분위가 수학적으로 55인데, 부동소수점에서 55.000000000000007로 표현돼 P였던 조합입니다. 백분위를 소수 12자리로 정리한 뒤 45~55를 포함해 보류하도록 수정했습니다. 그 밖의 축 판정은 승희 산출물과 같습니다.
- 기본 수요 평균의 세 지표 완비 조건 때문에 기존 성은·승희 기본 점수 중 {c['default_changed']}개가 변했습니다. 최대 절대 변화는 {c['max_score_change']:.2f}점입니다. 통합 기본 점수는 김지영 기본 점수와 전체 대상에서 일치합니다.
- 공식 S/D와 과거 변동성 S/D가 모두 판정한 {c['sd_both_known']:,}개에서 일치율 {c['sd_agreement']*100:.1f}%입니다. 다른 현상을 측정하므로 분기 변동성을 별도 참고값으로 남겼습니다.

## 8유형 결과

| 코드 | 분석용 이름 | 상권×업종 조합 수 |
|---|---|---:|
"""
    text += "\n".join(f"| {r['code']} | {r['name']} | {r['count']:,} |" for r in meta["types"])
    text += "\n\n같은 상권이 여러 업종으로 반복됩니다. 조합 수와 고유 상권 수를 혼동하지 않습니다. 이름은 분석용 설명이며 실제 고객·가격 민감도·브랜드 성향을 검증한 결과가 아닙니다.\n\n## 기본 조건 커피 음료 상위 예시\n\n| 상권 | 자치구 | 기본 점수 | 평균 점포 | 유형 |\n|---|---|---:|---:|---|\n"
    text += "\n".join(f"| {r.trdar_name} | {r.gu_name} | {r.score_total_default:.1f} | {r.stores:.1f} | {r.candidate_type if pd.notna(r.candidate_type) else '보류'} |" for r in coffee.itertuples())
    text += "\n\n이 순서는 성공 확률·수익 순위가 아닙니다. 같은 업종 안의 4개 비교 점수에 대한 가중 평균입니다.\n\n## 가중치와 수요의 민감도\n\n| 시나리오 | 업종별 순위 상관 중앙값 | 상위 10곳 유지 중앙값 |\n|---|---:|---:|\n"
    text += "\n".join(f"| {r['name']} | {r['rank_correlation_median']:.3f} | {r['top10_retained_median']:.0f} |" for r in meta["sensitivity"])
    text += """

기본 비중 30·25·15·30, 점포 5개, 비교 30곳, L/V·E/P 경계는 운영 가정입니다. 시나리오 비교는 규칙에 대한 민감도를 보여 주며 성능 검증이 아닙니다. 일부 인구 평균과 S/G 차등 비중은 대안 비교로만 보존하고 기본값으로 쓰지 않습니다.

## 사용자 선호와 검사지

15문항은 창업 운영 선호를 묻는 팀 제작 초안입니다. 원래 이승희 문항의 1~10번을 보존하고, 11~15번은 공식 영업 기간 지표와 연결되도록 수정했습니다. 높은 수익·폐업 빈도·새 손님 증가를 D의 검증된 속성으로 설명하지 않습니다. 각 축은 5문항이며 4:1 이상만 필터로 제안하고 3:2 및 미완료 축은 제한하지 않습니다. 사용자가 직접 선택하면 해당 선택을 우선합니다. 설문 응답은 서버로 전송하거나 저장하지 않습니다.

지도·목록·상세·유형 탐색은 같은 가중치와 수요 모드를 사용합니다. L→주민, V→유동 연결은 기본 끄기이며 명시적으로 켜야 적용됩니다. 가중치 변경은 실험으로 표시합니다. 선택 축의 판정 보류는 일치 결과에서 제외하지만 보류 조회에서 그대로 볼 수 있습니다. 결과가 없으면 다른 유형으로 대체하지 않습니다.

## 한계와 해석

- S는 저위험, D는 성장·높은 수익이라는 뜻이 아닙니다. 공식 원 지표는 운영·폐업 사업체의 평균 영업 기간 비교입니다. LH/HL은 중간 점수나 결측이 아닙니다.
- L/V는 상주·직장 구성 대리값입니다. 실제 고객·관광객 비중이 아닙니다. E/P는 같은 업종의 건당 추정매출 상대 수준입니다.
- 상주·직장인구는 2025년 안에서 변하지 않습니다. 실제 통계 기준 시점은 미확인입니다.
- 안정성은 1년치 축소 추정 폐업률로 신뢰도가 낮습니다. 경쟁과 수요는 유동인구를 공유합니다. 중복 반영 및 가중치 변화의 영향을 확인해야 합니다.
- 비용·보증금·월세·권리금·순이익 자료가 없어 예산 적합성을 판단하지 않습니다. 정답 창업 성과나 실제 사용자 결과가 없어 추천 정확도와 성공 확률을 주장하지 않습니다.

## 기여와 출처

"""
    text += "\n".join(f"- [{r['name']}]({r['url']})" for r in meta["config"]["sources"])
    (REPORT / "통합분석보고서.md").write_text(text + "\n", encoding="utf-8")


def export(d, meta):
    web_data, assets = WEB / "data", WEB / "assets"
    web_data.mkdir(exist_ok=True, parents=True)
    assets.mkdir(exist_ok=True, parents=True)
    q = pd.read_parquet(FILES["quarters"])
    qcols = ["trdar_code", "quarter", "sales_month", "open_count", "close_count", "qoq_raw", "qoq_winsor"]
    cols = ["trdar_code", "trdar_name", "gu_name", "trdar_type", "stores", "score_status", "score_sales", "score_comp", "score_stab", "score_dem_avg", "score_dem_available", "score_dem_floating", "score_dem_worker", "score_dem_resident", "score_total_default", "n_areas_default", "score_total_previous", "default_delta", "sales_month", "sales_area_status", "closes", "close_pct_shrunk", "comp_ratio", "floating_density", "worker_density", "resident_density", "franchise_pct", "resident_share_proxy", "ticket", "ticket_pct", "ep_peers", "LV", "EP", "SD", "candidate_type", "known_axes", "type_status", "LV_reason", "EP_reason", "SD_reason", "hold_reason", "chg_code", "chg_name", "run_months", "closed_months", "seoul_run_months", "seoul_closed_months", "sales_month_cv", "floating_cv", "previous_type", "volatility_SD", "boundary_changed"]
    for code, g in d.groupby("industry_code"):
        payload = {"columns": cols, "rows": json.loads(g[cols].to_json(orient="values", force_ascii=False, double_precision=12)), "quarter_columns": qcols, "quarters": json.loads(q.loc[q.industry_code.eq(code), qcols].to_json(orient="values", force_ascii=False, double_precision=12))}
        json_write(web_data / f"{code}.json", payload)
    json_write(web_data / "meta.json", meta)
    (web_data / "geometry.json").write_bytes(FILES["geometry"].read_bytes())
    (assets / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    (assets / "analysis.md").write_bytes((REPORT / "통합분석보고서.md").read_bytes())
    for name in ["8유형_분포.csv", "업종별_분석범위.csv", "보류사유.csv", "민감도.csv", "기본점수_변경내역.csv", "경계정밀도_변경내역.csv"]:
        (assets / name).write_bytes((OUT / name).read_bytes())
    fixture=[]
    for industry in ["CS100010", "CS100001", "CS300003", "CS200028"]:
        g=d.loc[d.industry_code.eq(industry)]
        for lv,ep,sd in itertools.product(["", "L", "V"],["", "E", "P"],["", "S", "D"]):
            choices={"LV":lv,"EP":ep,"SD":sd}
            for linked in [False,True]:
                r=explore(g,choices,linked=linked,limit=10)
                fixture.append({"industry":industry,"choices":choices,"linked":linked,"expected":records(r[["trdar_code","score_total","n_areas","demand_mode"]])})
    json_write(HERE / "test_fixtures.json", fixture)


def main():
    for path in [OUT, REPORT]:path.mkdir(exist_ok=True)
    config=json.loads(FILES["config"].read_text(encoding="utf-8"))
    d,areas,input_hashes=build_data()
    meta=summarize(d,areas,config)
    meta["input_sha256"]=input_hashes
    d.to_parquet(OUT / "통합_상권업종_2025.parquet", index=False)
    json_write(OUT / "integration_meta.json", meta)
    csv_write(pd.DataFrame(meta["types"]),OUT / "8유형_분포.csv")
    csv_write(pd.DataFrame(meta["industries"]),OUT / "업종별_분석범위.csv")
    csv_write(pd.DataFrame(meta["holds"]),OUT / "보류사유.csv")
    csv_write(pd.DataFrame([{k:v for k,v in s.items() if k!="weights"} for s in meta["sensitivity"]]),OUT / "민감도.csv")
    csv_write(d.loc[d.default_delta.abs().gt(1e-8),["trdar_code","industry_code","trdar_name","industry_name","score_total_previous","score_total_default","default_delta","score_dem_available","score_dem_avg"]],OUT / "기본점수_변경내역.csv")
    csv_write(d.loc[d.boundary_changed,["trdar_code","industry_code","trdar_name","industry_name","seunghee_ticket_pct","ticket_pct","seunghee_EP","EP","seunghee_type","candidate_type"]],OUT / "경계정밀도_변경내역.csv")
    json_write(OUT / "검사지.json",meta["questions"])
    report(d,meta)
    export(d,meta)
    assert input_hashes==hashes()
    print(json.dumps({"version":VERSION,"counts":meta["counts"],"dist_mib":round(sum(p.stat().st_size for p in WEB.rglob('*') if p.is_file())/1024**2,1)},ensure_ascii=False),flush=True)


if __name__=="__main__":main()
