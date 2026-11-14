# -*- coding: utf-8 -*-
"""
SpotFit STEP 5: 금융 MBTI 3개 축(L/V · E/P · S/D)으로 상권×업종마다 유형을 판정한다.

입력 (모두 읽기만 함):
    이승희/step4_dashboard/data/상권_업종_비교점수_2025.parquet   STEP 4 점수표 (관광특구 제외, 76,591칸)
    이승희/data/processed/stage2/상권_분기_마트.csv             상권변화지표 (원본 OA-15576과 6,600행 동일)
    김지영/claude_dashboard/data/cells.parquet                  결제 건당 금액(ticket), 네 분기 매출 동일 표시
    김지영/claude_dashboard/data/areas.parquet                  관광특구 제외 상권 1,644곳
출력 (이 폴더의 data/ 안에만 씀):
    data/상권업종_유형_2025.parquet, data/상권_유형축_2025.csv, data/유형_정의.csv,
    data/업종별_유형_가능여부.csv, data/유형별_분포.csv, data/stage5_meta.json

실행 (팀 저장소 루트에서):
    uv run --project "이승희/step5_recommend" python "이승희/step5_recommend/build_types.py"

축 정의:
    L 생활형 / V 방문형   [가정] 주민 ÷ (주민 + 직장인). 0.55 초과 L, 0.45 미만 V, 그 사이는 보류 (박성은 규칙과 같음)
    E 실속형 / P 프리미엄형 [가정] 결제 건당 금액의 업종 안 백분위. 45 미만 E, 55 초과 P, 그 사이는 보류 (박성은 규칙과 같음)
    S 안정형 / D 역동형   서울시 상권변화지표 2025년 4분기. 정체 → S, 다이나믹 → D, 상권확장·상권축소 → 중간(보류)
                         (2026-11-12 이승희 제안: 'G 성장형'은 2025년 1년치로 만들 수 없어 'D 역동형'으로 바꿈)
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]              # 팀 저장소 루트 (<이름>/step5_recommend/ 의 두 단계 위)
STAGE4 = REPO / "이승희" / "step4_dashboard" / "data"
MART = REPO / "이승희" / "data" / "processed" / "stage2" / "상권_분기_마트.csv"
JY_DATA = REPO / "김지영" / "claude_dashboard" / "data"
OUT = HERE / "data"

INPUTS = [STAGE4 / "상권_업종_비교점수_2025.parquet", MART, JY_DATA / "cells.parquet", JY_DATA / "areas.parquet"]

MIN_PEERS = 30                      # 7.3 결정과 같음: 비교 상권 30곳 이상
LV_L, LV_V = 0.55, 0.45             # [가정] 주민 비중 경계
EP_E, EP_P = 45.0, 55.0             # [가정] 건당 금액 백분위 경계
SD_QUARTER = 20254                  # 2025년 4분기 (가장 최근 값)
SD_MAP = {"정체": "S", "다이나믹": "D", "상권확장": None, "상권축소": None}

AXES = {
    "LV": {"L": "생활형", "V": "방문형"},
    "EP": {"E": "실속형", "P": "프리미엄형"},
    "SD": {"S": "안정형", "D": "역동형"},
}
AXIS_TITLES = {"LV": "주 고객", "EP": "가격대", "SD": "상권 변화"}
AXIS_MEANING = {
    "L": "주민이 직장인보다 많은 상권 (동네 생활권)",
    "V": "직장인이 주민보다 많은 상권 (출퇴근·방문 생활권)",
    "E": "같은 업종 안에서 결제 1건당 금액이 낮은 편",
    "P": "같은 업종 안에서 결제 1건당 금액이 높은 편",
    "S": "변화가 적은 상권: 영업 중인 가게도, 문 닫은 가게도 오래 영업함 (서울시 '정체')",
    "D": "변화가 활발한 상권: 영업 기간이 짧고 가게가 자주 바뀜 (서울시 '다이나믹')",
}
# 이름: S/D 이름은 박성은 types.json 제안을 따름 (팀 확정 전). 아이템은 설명용 예시이며 데이터로 검증하지 않음.
TYPES = [
    ("LES", "LES", "동네 단골형", "동네 단골형", "반찬가게, 세탁소, 가성비 식당"),
    ("LED", "LEG", "생활 역동형", "생활 성장형", "베이커리, 생활용품점, 테이크아웃 카페"),
    ("LPS", "LPS", "동네 취향형", "동네 취향형", "스페셜티 카페, 프리미엄 식료품점"),
    ("LPD", "LPG", "취향 역동형", "취향 확장형", "브런치 카페, 디저트 전문점, 편집숍"),
    ("VES", "VES", "실속 유동형", "실속 유동형", "분식, 도시락, 저가 커피"),
    ("VED", "VEG", "유동 역동형", "유동 성장형", "간편식, 테이크아웃 음료, 소형 음식점"),
    ("VPS", "VPS", "목적 방문형", "목적 방문형", "전문 음식점, 와인바, 전문 소매점"),
    ("VPD", "VPG", "방문 역동형", "트렌드 성장형", "콘셉트 카페, 팝업스토어, 체험형 매장"),
]
TYPE_NAMES = {t[0]: t[2] for t in TYPES}
LEGACY = {t[1]: t[0] for t in TYPES}   # 예전 G 코드 → D 코드


TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".html"}


def sha256(path):
    """파일 지문. 글자 파일은 줄바꿈(CRLF/LF)을 LF로 맞춘 뒤 계산한다.
    윈도우 Git(core.autocrlf=true)은 받을 때 CRLF로 바꾸므로, 맞추지 않으면 같은 데이터인데 지문이 달라진다."""
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def spearman(x, y):
    """Spearman 순위 상관. scipy 없이 두 값이 모두 있는 행만 순위를 매긴 뒤 피어슨 상관을 구한다."""
    ok = x.notna() & y.notna()
    return float(x[ok].rank().corr(y[ok].rank()))


def pct_rank(s):
    """업종 안 백분위(0 초과 100 이하). 동점은 평균 순위. STEP 4 pct_rank와 같은 방식."""
    return s.rank(pct=True, method="average") * 100


def load_inputs():
    missing = [p for p in INPUTS if not p.exists()]
    if missing:
        names = "\n".join(f"  - {p.relative_to(REPO).as_posix()}" for p in missing)
        sys.exit("입력 파일이 없습니다. 팀 저장소 main을 최신으로 받았는지 확인하세요:\n" + names)
    scores = pd.read_parquet(INPUTS[0])
    mart = pd.read_csv(MART, encoding="utf-8-sig", dtype={"상권_코드": str},
                       usecols=["상권_코드", "기준_년분기_코드", "상권_코드_명", "상권_구분_코드_명",
                                "상권_변화_지표", "상권_변화_지표_명", "운영_영업_개월_평균", "폐업_영업_개월_평균"])
    cells = pd.read_parquet(JY_DATA / "cells.parquet", columns=["trdar_code", "industry_code", "ticket", "repeated_sales"])
    areas = pd.read_parquet(JY_DATA / "areas.parquet")
    return scores, mart, cells, areas


def axis_lv(resident, worker):
    """L/V 판정과 보류 사유. 두 값 중 하나라도 없거나 음수이거나 합이 0이면 보류."""
    ok = resident.notna() & worker.notna() & resident.ge(0) & worker.ge(0) & (resident + worker).gt(0)
    share = (resident / (resident + worker)).where(ok)
    lv = pd.Series(np.select([share > LV_L, share < LV_V], ["L", "V"], default=""), index=share.index).replace("", None)
    reason = np.select([~ok, lv.isna()], ["주민·직장인 자료 없음 또는 합계 0", "주민·직장인 비중이 비슷함 (0.45~0.55)"], default="")
    return share, lv, pd.Series(reason, index=share.index).replace("", None)


def build_areas(areas, mart):
    """상권 단위 L/V와 S/D (관광특구 제외 1,644곳)."""
    a = areas[["trdar_code", "trdar_name", "gu_name", "trdar_type", "resident", "worker"]].copy()
    a["lv_share"], a["LV"], a["LV_reason"] = axis_lv(a["resident"], a["worker"])

    m = mart.rename(columns={"상권_코드": "trdar_code", "기준_년분기_코드": "quarter"})
    q4 = m.loc[m["quarter"].eq(SD_QUARTER), ["trdar_code", "상권_변화_지표", "상권_변화_지표_명", "운영_영업_개월_평균", "폐업_영업_개월_평균"]]
    q4 = q4.rename(columns={"상권_변화_지표": "chg_code", "상권_변화_지표_명": "chg_name",
                            "운영_영업_개월_평균": "run_months", "폐업_영업_개월_평균": "closed_months"})
    year = m.groupby("trdar_code").agg(chg_quarters=("quarter", "nunique"), chg_kinds=("상권_변화_지표_명", "nunique"))
    a = a.merge(q4, on="trdar_code", how="left", validate="one_to_one").merge(year, on="trdar_code", how="left", validate="one_to_one")
    a["chg_same_all_year"] = a["chg_quarters"].eq(4) & a["chg_kinds"].eq(1)
    a["SD"] = a["chg_name"].map(SD_MAP)
    a["SD_reason"] = np.select(
        [a["chg_name"].isna(), a["chg_name"].isin(["상권확장", "상권축소"])],
        ["상권변화지표 없음", "상권변화지표 중간 유형 (" + a["chg_name"].fillna("") + ")"], default="")
    a["SD_reason"] = a["SD_reason"].replace("", None)
    return a.drop(columns=["chg_kinds"]).sort_values("trdar_code").reset_index(drop=True)


def build_cells(scores, cells, area_axes):
    """상권×업종 단위 E/P와 최종 유형. 유형은 STEP 4 점수 대상 칸에만 붙인다."""
    d = scores.merge(cells, on=["trdar_code", "industry_code"], how="left", validate="one_to_one")
    target = d["score_status"].eq("점수 대상")

    ep_ok = target & d["sales_status"].eq("네 분기") & d["ticket"].gt(0) & ~d["repeated_sales"].fillna(False).astype(bool)
    peers = d.loc[ep_ok].groupby("industry_code").size()
    d["ep_peers"] = d["industry_code"].map(peers).fillna(0).astype(int)
    ep_ok = ep_ok & d["ep_peers"].ge(MIN_PEERS)
    d["ticket_pct"] = np.nan
    d.loc[ep_ok, "ticket_pct"] = d.loc[ep_ok].groupby("industry_code")["ticket"].transform(pct_rank)
    d["EP"] = pd.Series(np.select([d["ticket_pct"] < EP_E, d["ticket_pct"] > EP_P], ["E", "P"], default=""), index=d.index).replace("", None)
    d["EP_reason"] = np.select(
        [~target, d["sales_status"].eq("미제공 업종"), ~d["sales_status"].eq("네 분기"),
         d["repeated_sales"].fillna(False).astype(bool), ~(d["ticket"] > 0), d["ep_peers"].lt(MIN_PEERS), d["EP"].isna()],
        ["점수 대상 아님 (STEP 4)", "매출 미제공 업종", "4개 분기 매출 없음 (" + d["sales_status"] + ")",
         "네 분기 매출이 똑같음 (품질 확인 필요)", "결제 건당 금액 없음", "건당 금액 비교 상권 30곳 미만",
         "건당 금액이 업종 중간 (백분위 45~55)"], default="")
    d["EP_reason"] = d["EP_reason"].replace("", None)

    ax = area_axes[["trdar_code", "lv_share", "LV", "LV_reason", "chg_code", "chg_name", "run_months", "closed_months",
                    "chg_same_all_year", "SD", "SD_reason"]]
    d = d.merge(ax, on="trdar_code", how="left", validate="many_to_one")

    letters = d[["LV", "EP", "SD"]]
    full = target & letters.notna().all(axis=1)
    d["type_code"] = (d["LV"].fillna("?") + d["EP"].fillna("?") + d["SD"].fillna("?")).where(target)
    d["type_full"] = d["type_code"].where(full)
    d["type_name"] = d["type_full"].map(TYPE_NAMES)
    d["type_status"] = np.select([~target, full], ["점수 대상 아님", "유형 판정"], default="일부 축 보류")
    keep = ["trdar_code", "industry_code", "industry_name", "group", "trdar_name", "gu_name", "trdar_type", "stores",
            "score_status", "sales_status", "ticket", "repeated_sales", "ep_peers", "ticket_pct", "EP", "EP_reason",
            "lv_share", "LV", "LV_reason", "chg_code", "chg_name", "run_months", "closed_months", "chg_same_all_year",
            "SD", "SD_reason", "type_code", "type_full", "type_name", "type_status"]
    return d[keep].sort_values(["industry_code", "trdar_code"]).reset_index(drop=True)


def summarize(c, a, scores):
    """업종별 가능 여부, 유형별 분포, 메타 정보."""
    t = c.loc[c["score_status"].eq("점수 대상")]
    full = t.loc[t["type_full"].notna()]
    names = c.groupby("industry_code")["industry_name"].first()
    ind = pd.DataFrame({"업종명": names})
    ind["점수_대상_칸"] = t.groupby("industry_code").size()
    ind["EP_판정_칸"] = t.loc[t["EP"].notna()].groupby("industry_code").size()
    ind["유형_판정_칸"] = full.groupby("industry_code").size()
    for code, _, *_ in TYPES:
        ind[code] = full.loc[full["type_full"].eq(code)].groupby("industry_code").size()
    ind = ind.fillna(0).astype({k: int for k in ind.columns if k != "업종명"})
    ind["판정_불가_사유"] = np.select(
        [ind["점수_대상_칸"].eq(0), ind["EP_판정_칸"].eq(0)],
        ["STEP 4 점수 없음 (비교 상권 30곳 미만)", "가격대(E/P)를 판정할 매출 자료 부족"], default="")
    ind = ind.reset_index().rename(columns={"industry_code": "업종_코드"})

    dist = []
    for code, legacy, name, original, items in TYPES:
        g = full.loc[full["type_full"].eq(code)]
        dist.append({"유형_코드": code, "유형_이름": name, "칸_수": len(g), "상권_수": g["trdar_code"].nunique(),
                     "업종_수": g["industry_code"].nunique()})
    dist = pd.DataFrame(dist)

    # S/D와 STEP 4 안정성(보정 폐업률)이 얼마나 겹치는지: 같은 정보를 두 번 반영하지 않으려는 확인
    s = t.merge(scores[["trdar_code", "industry_code", "score_stab", "score_dem_resident", "score_dem_floating", "score_sales"]],
                on=["trdar_code", "industry_code"], how="left", validate="one_to_one")
    sd = s.loc[s["SD"].notna()]
    within = sd.groupby("industry_code").filter(lambda g: g["SD"].nunique() == 2 and len(g) >= MIN_PEERS)
    per_ind = within.groupby("industry_code").apply(
        lambda g: spearman(g["SD"].eq("D").astype(int), g["score_stab"]), include_groups=False)
    overlap = {
        "S_안정성_중앙값": round(float(sd.loc[sd["SD"].eq("S"), "score_stab"].median()), 2),
        "D_안정성_중앙값": round(float(sd.loc[sd["SD"].eq("D"), "score_stab"].median()), 2),
        "D여부_안정성_spearman_전체": round(spearman(sd["SD"].eq("D").astype(int), sd["score_stab"]), 3),
        "D여부_안정성_spearman_업종별_중앙값": round(float(per_ind.median()), 3),
        "업종별_계산_업종_수": int(per_ind.size),
        "운영개월_안정성_spearman_전체": round(spearman(s["run_months"], s["score_stab"]), 3),
        "주민비중_수요주민_spearman": round(spearman(s["lv_share"], s["score_dem_resident"]), 3),
        "건당금액백분위_매출_spearman": round(spearman(s["ticket_pct"], s["score_sales"]), 3),
    }
    area_counts = {
        "areas": int(len(a)),
        "LV": {k: int(v) for k, v in a["LV"].fillna("보류").value_counts().sort_index().items()},
        "SD": {k: int(v) for k, v in a["SD"].fillna("중간(보류)").value_counts().sort_index().items()},
        "chg_name": {k: int(v) for k, v in a["chg_name"].fillna("없음").value_counts().sort_index().items()},
        "chg_same_all_year": int(a["chg_same_all_year"].sum()),
    }
    counts = {
        "cells": int(len(c)), "target_cells": int(len(t)), "typed_cells": int(len(full)),
        "partial_cells": int(t["type_full"].isna().sum()), "ep_cells": int(t["EP"].notna().sum()),
        "typed_industries": int(ind["유형_판정_칸"].gt(0).sum()), "typed_areas": int(full["trdar_code"].nunique()),
        "type_status": {k: int(v) for k, v in c["type_status"].value_counts().sort_index().items()},
        "hold_reasons": {
            ax: {k: int(v) for k, v in t[f"{ax}_reason"].value_counts().sort_index().items()} for ax in ["LV", "EP", "SD"]},
    }
    meta = {
        "rules": {"min_peers": MIN_PEERS, "lv_bounds": [LV_V, LV_L], "ep_bounds": [EP_E, EP_P], "sd_quarter": SD_QUARTER,
                  "sd_map": SD_MAP, "axes": AXES, "axis_titles": AXIS_TITLES, "legacy_codes": LEGACY},
        "counts": counts, "area_counts": area_counts, "sd_stability_overlap": overlap,
        "inputs": {p.relative_to(REPO).as_posix(): sha256(p) for p in INPUTS},
    }
    return ind, dist, meta


def build(scores, mart, cells, areas):
    a = build_areas(areas, mart)
    c = build_cells(scores, cells, a)
    ind, dist, meta = summarize(c, a, scores)
    return c, a, ind, dist, meta


def write(c, a, ind, dist, meta, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    c.to_parquet(out / "상권업종_유형_2025.parquet", index=False)
    csv = dict(index=False, encoding="utf-8-sig", lineterminator="\n")
    a.to_csv(out / "상권_유형축_2025.csv", **csv)
    pd.DataFrame(TYPES, columns=["유형_코드", "예전_코드", "유형_이름", "예전_이름", "아이템_예시(설명용)"]).to_csv(out / "유형_정의.csv", **csv)
    ind.to_csv(out / "업종별_유형_가능여부.csv", **csv)
    dist.to_csv(out / "유형별_분포.csv", **csv)
    (out / "stage5_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    before = {p: sha256(p) for p in INPUTS if p.exists()}
    c, a, ind, dist, meta = build(*load_inputs())
    write(c, a, ind, dist, meta)
    assert before == {p: sha256(p) for p in INPUTS}, "입력 파일이 실행 중에 바뀌었습니다"
    k, ac = meta["counts"], meta["area_counts"]
    print(f"[완료] 점수 대상 {k['target_cells']:,}칸 중 3개 축이 모두 판정된 칸 {k['typed_cells']:,}칸 "
          f"(업종 {k['typed_industries']}개, 상권 {k['typed_areas']:,}곳)")
    print(f"       상권 {ac['areas']:,}곳 · L/V {ac['LV']} · S/D {ac['SD']}")


if __name__ == "__main__":
    main()
