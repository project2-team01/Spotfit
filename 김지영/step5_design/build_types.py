"""STEP 5: 금융 MBTI의 상권 쪽 유형 글자(L/V · E/P)를 2025년 자료로 정한다.

읽기만 하는 입력
  <저장소>/김지영/step2_3/data/fact_trdar_industry_quarter.csv.gz   분기×상권×업종 패널 (매출 금액·건수)
  <저장소>/김지영/step2_3/data/trdar_quarter_context.csv.gz        상권×분기 유동·직장·상주인구
  <저장소>/김지영/step2_3/data/dim_trdar.csv.gz                    상권 기본 정보 (관광특구 표시)
  <저장소>/seoul-commercial-analysis/data/raw/금융_MBTI.md         팀 유형표. 있으면 아래 문항·유형이 원문과 같은지 확인한다
                                                                  (data/raw 는 Git에서 빠져 있어, 문항·유형은 이 파일에 옮겨 적었다)

S/G(상권 변화)는 상권 쪽에서 판정하지 않는다. 팀 결정: 2025년 자료만 있어 성장성은 산출하지 않고, 분기 변화로 대신하지 않는다.
창업자의 S/G 글자는 STEP 4 영역 가중치로만 쓴다 (유형별_가중치.csv).

결과는 이 작업 폴더의 data/ 에만 쓴다. 같은 입력이면 몇 번을 실행해도 바이트까지 같은 파일이 나온다.

실행 (저장소 루트에서)
  uv run --project "김지영/step4_dashboard" python "김지영/step5_design/build_types.py"
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent  # 작업 폴더
ROOT = HERE.parents[1]  # 팀 저장소 루트
SOURCE = ROOT / "김지영" / "step2_3" / "data"  # 팀 공용 STEP 2·3 산출물 (STEP 4와 같은 입력)
MBTI_DOC = ROOT / "seoul-commercial-analysis" / "data" / "raw" / "금융_MBTI.md"
OUT = HERE / "data"

INPUTS = {
    "fact": SOURCE / "fact_trdar_industry_quarter.csv.gz",
    "context": SOURCE / "trdar_quarter_context.csv.gz",
    "dim": SOURCE / "dim_trdar.csv.gz",
}
EXPECTED_ROWS = {"fact": 304_775, "context": 6_600, "dim": 1_650}
QUARTERS = ["20251", "20252", "20253", "20254"]
IDS = {"quarter": str, "trdar_code": str, "industry_code": str}
NEAR = 5  # 중앙값 ±5점 안의 상권은 '판정이 쉽게 바뀔 수 있음'으로 센다

# ---------------------------------------------------------------- 팀 유형표 (출처: seoul-commercial-analysis/data/raw/금융_MBTI.md)

AXES = [  # 1장 세 가지 기준. 글자 순서는 주요 고객 → 소비 성향 → 상권 변화
    {"기준": "주요 고객", "왼쪽": "L", "왼쪽 이름": "생활형", "오른쪽": "V", "오른쪽 이름": "방문형",
     "의미": "주민 중심인가, 직장인·관광객·외부 방문객 중심인가"},
    {"기준": "소비 성향", "왼쪽": "E", "왼쪽 이름": "실속형", "오른쪽": "P", "오른쪽 이름": "프리미엄형",
     "의미": "가격·편의 중심인가, 높은 객단가·차별화 중심인가"},
    {"기준": "상권 변화", "왼쪽": "S", "왼쪽 이름": "안정형", "오른쪽": "G", "오른쪽 이름": "성장형",
     "의미": "수요가 꾸준한가, 최근 소비와 방문이 증가하는가"},
]

QUESTIONS = [  # 4장 검사 문항 (번호, 기준, 질문, A, A 글자, B, B 글자)
    (1, "주요 고객", "가게를 연 지 1년, 가장 듣고 싶은 말은?", '"사장님, 오늘도 늘 먹던 걸로요."', "L", '"소문 듣고 처음 와 봤어요."', "V"),
    (2, "주요 고객", "손님이 우리 가게에 오는 가장 큰 이유는?", "회사·학교 근처라서, 또는 일부러 찾아와서", "V", "집에서 가깝고 생활의 일부라서", "L"),
    (3, "주요 고객", "월세가 같다면 어느 자리를 고를까요?", "역 출구 앞. 오가는 사람은 많지만 대부분 처음 보는 얼굴", "V", "아파트 단지 상가. 지나는 사람은 적지만 매일 같은 얼굴", "L"),
    (4, "주요 고객", "홍보비 50만 원이 생겼다면?", "지도 앱 리뷰 이벤트·SNS 광고로 새 손님을 부른다", "V", "적립 쿠폰·동네 커뮤니티로 온 손님을 다시 오게 한다", "L"),
    (5, "주요 고객", "손님과는 어떤 사이가 편한가요?", "이름과 취향을 기억하고 안부를 묻는 사이", "L", "빠르고 깔끔하게, 적당히 거리를 두는 사이", "V"),
    (6, "소비 성향", "하루 매출 200만 원을 만든다면?", "1만 원짜리 200건", "E", "4만 원짜리 50건", "P"),
    (7, "소비 성향", "바로 옆에 비슷한 가게가 생겼다면?", "가격은 그대로, 맛·분위기·서비스로 차이를 낸다", "P", "세트 메뉴·할인으로 가격 경쟁력을 높인다", "E"),
    (8, "소비 성향", "창업 자금이 조금 남았다면 어디에 쓸까요?", "인테리어와 브랜딩. 들어서는 순간부터 달라야 한다", "P", "설비와 좌석. 더 빨리, 더 많이 받을 수 있어야 한다", "E"),
    (9, "소비 성향", "메뉴판을 짠다면?", "누구나 아는 메뉴를 빠르게, 늘 같은 맛으로", "E", "여기서만 먹을 수 있는 시그니처 몇 가지로", "P"),
    (10, "소비 성향", "내가 손님일 때 더 자주 하는 말은?", '"가성비 좋네."', "E", '"비싸도 여기가 낫지."', "P"),
    (11, "상권 변화", "여윳돈 1,000만 원이 생겼다면?", "정기예금. 이자는 적어도 원금은 지킨다", "S", "주식·펀드. 잃을 수도 있지만 더 벌 수도 있다", "G"),
    (12, "상권 변화", "두 동네 중 어디에 열까요?", "10년째 큰 변화 없이 장사가 되는 동네", "S", "요즘 새 가게가 계속 생기고 사람이 늘어나는 동네", "G"),
    (13, "상권 변화", "한 달 순이익이 이렇다면 어느 쪽을 고를까요?", "매달 300만 원", "S", "100만~600만 원 사이로 오르내리고 평균 350만 원", "G"),
    (14, "상권 변화", "뜨는 동네라 2년 뒤 월세가 오를 수 있다면?", "그래도 들어간다. 손님이 늘면 감당할 수 있다", "G", "월세가 오래 안정적인 곳을 찾는다", "S"),
    (15, "상권 변화", "창업 자금이 계획보다 모자라다면?", "대출을 받아서라도 계획한 규모로 연다", "G", "규모를 줄여 가진 돈 안에서 연다", "S"),
]
# 유형표: "실제 검사 화면에서는 문항 순서를 섞고 글자는 숨겨요." 화면 순서를 고정해 두어 누구에게나 같은 순서로 보인다.
# (random.Random(2025).shuffle 로 한 번 만든 순서를 적어 두었다. 화면 1번 = 원래 7번 문항)
DISPLAY_ORDER = [7, 13, 12, 10, 14, 5, 4, 6, 1, 15, 3, 8, 11, 2, 9]

TYPES = [  # 2장 8가지 유형 (유형, 이모지, 이름, 상권 특징, 창업 아이템 예시)
    ("LES", "🏡", "동네 단골형", "주민의 일상 소비가 꾸준하고 가격에 민감", "반찬가게, 세탁소, 가성비 식당"),
    ("LEG", "🌱", "생활 성장형", "주거 수요와 생활 소비가 늘어나는 상권", "베이커리, 생활용품점, 테이크아웃 카페"),
    ("LPS", "☕", "동네 취향형", "주민의 구매력을 바탕으로 취향 소비가 꾸준", "스페셜티 카페, 프리미엄 식료품점"),
    ("LPG", "✨", "취향 확장형", "주민의 소비가 늘고 고급·취향 업종이 성장", "브런치 카페, 디저트 전문점, 편집숍"),
    ("VES", "🍱", "실속 유동형", "출퇴근·통학 등 반복 방문과 실속 소비 중심", "분식, 도시락, 저가 커피"),
    ("VEG", "🚶", "유동 성장형", "방문객과 소비가 증가하며 접근성이 중요", "간편식, 테이크아웃 음료, 소형 음식점"),
    ("VPS", "🛍️", "목적 방문형", "쇼핑·외식·문화 등 목적 있는 방문이 꾸준", "전문 음식점, 와인바, 전문 소매점"),
    ("VPG", "🔥", "트렌드 성장형", "외부 방문과 취향 소비가 빠르게 증가", "콘셉트 카페, 팝업스토어, 체험형 매장"),
]

# [가정, 2026-11-14 승인] 창업자 S/G 글자 → STEP 4 영역 가중치 (매출 잠재력 · 경쟁 · 안정성 · 수요)
SG_WEIGHTS = [
    {"구분": "S", "이름": "S 안정형", "매출 잠재력": 20, "경쟁": 30, "안정성": 30, "수요": 20,
     "근거": "팀 계획서 STEP 5 예시: 안정형은 상권 안정성·경쟁 위험을 중요하게 본다"},
    {"구분": "G", "이름": "G 성장형", "매출 잠재력": 35, "경쟁": 15, "안정성": 10, "수요": 40,
     "근거": "팀 계획서 STEP 5 예시: 성장형은 매출 성장성·수요 증가 가능성을 본다. 성장성 점수가 없어 매출 잠재력·수요에 무게를 둔다 (성장성 점수가 아님)"},
    {"구분": "경계", "이름": "S/G 경계 (STEP 4 기본값)", "매출 잠재력": 30, "경쟁": 25, "안정성": 15, "수요": 30,
     "근거": "S/G가 3:2로 갈리면 어느 쪽에도 치우치지 않게 STEP 4 기본값을 쓴다"},
]

OUTPUT_NAMES = {
    "types": "상권_유형_2025.parquet",
    "types_csv": "상권_유형_2025.csv",
    "questions": "검사_문항.csv",
    "type_table": "유형표.csv",
    "weights": "유형별_가중치.csv",
    "design": "STEP5_설계표.csv",
    "meta": "stage5_meta.json",
}


# ---------------------------------------------------------------- 입력


def sha256(path: Path) -> str:
    """출처: 김지영/step4_dashboard/build_scores.py sha256"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprints() -> dict[str, str]:
    paths = [*INPUTS.values(), *([MBTI_DOC] if MBTI_DOC.exists() else [])]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def read_inputs() -> dict[str, pd.DataFrame]:
    fact = pd.read_csv(INPUTS["fact"], dtype=IDS, usecols=[
        "quarter", "trdar_code", "industry_code", "industry_name", "sales_supported_industry", "store_count",
        "open_count", "close_count", "sales_amount", "sales_count", "sales_observed"])
    context = pd.read_csv(INPUTS["context"], dtype=IDS, usecols=[
        "quarter", "trdar_code", "floating_population", "worker_population", "resident_population"])
    dim = pd.read_csv(INPUTS["dim"], dtype={"trdar_code": str})
    data = {"fact": fact, "context": context, "dim": dim}
    wrong = {k: len(v) for k, v in data.items() if len(v) != EXPECTED_ROWS[k]}
    if wrong:
        raise ValueError(f"입력 행 수가 설명과 다릅니다: {wrong} (기대값 {EXPECTED_ROWS})")
    if set(fact["quarter"]) != set(QUARTERS):
        raise ValueError(f"2025년 네 분기만 있어야 합니다: {sorted(set(fact['quarter']))}")
    if not dim["is_tourist"].eq(~dim["main_analysis_eligible"]).all():
        raise ValueError("관광특구 표시(is_tourist)와 main_analysis_eligible이 서로 맞지 않습니다.")
    return data


def parse_doc(text: str) -> tuple[list[tuple], list[tuple]]:
    """유형표 원문에서 문항 표와 유형 표를 읽는다 (옮겨 적은 내용이 원문과 같은지 확인용)."""
    questions, axis = [], None
    for line in text.splitlines():
        m = re.match(r"### (주요 고객|소비 성향|상권 변화)", line)
        if m:
            axis = m.group(1)
        m = re.match(r"\| (\d+) \| (.+?) \| (.+?) → \*\*([A-Z])\*\* \| (.+?) → \*\*([A-Z])\*\* \|$", line)
        if m:
            g = m.groups()
            questions.append((int(g[0]), axis, *g[1:]))
    types = [m.groups() for m in (re.match(r"\| \*\*([LV][EP][SG])\*\* \| (\S+) (.+?) \| (.+?) \| (.+?) \|$", x) for x in text.splitlines()) if m]
    return questions, types


def check_doc() -> dict:
    rel = MBTI_DOC.relative_to(ROOT).as_posix()
    if not MBTI_DOC.exists():
        return {"path": rel, "present": False, "note": "원문 파일이 없어 옮겨 적은 문항·유형과 비교하지 못했다"}
    questions, types = parse_doc(MBTI_DOC.read_text(encoding="utf-8"))
    if questions != QUESTIONS:
        raise ValueError(f"{rel}의 검사 문항이 build_types.py에 옮겨 적은 내용과 다릅니다. 원문이 바뀌었으면 QUESTIONS를 고치세요.")
    if types != TYPES:
        raise ValueError(f"{rel}의 유형 표가 build_types.py에 옮겨 적은 내용과 다릅니다. 원문이 바뀌었으면 TYPES를 고치세요.")
    return {"path": rel, "present": True, "sha256": sha256(MBTI_DOC), "questions_match": True, "types_match": True}


# ---------------------------------------------------------------- 상권 유형


def pct_rank(values: pd.Series) -> pd.Series:
    """서울 안 백분위 (0~100). 동점은 평균 순위, 결측은 결측. STEP 4 점수와 같은 방식이다."""
    return values.rank(method="average", pct=True) * 100


def split(score: pd.Series, low: str, high: str) -> tuple[pd.Series, float]:
    """서울 중앙값보다 크면 high 글자, 같거나 작으면 low 글자. 점수가 없으면 결측."""
    median = float(score.median())
    letters = pd.Series(np.where(score > median, high, low), index=score.index, dtype=object)
    return letters.where(score.notna()), median


def build_lv(context: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    """L 생활형 / V 방문형: 상주인구에 비해 직장인구·유동인구가 많을수록 V 쪽.

    직장인구 ÷ 상주인구, 유동인구 ÷ 상주인구를 각각 서울 안 백분위로 바꿔 평균한 값(L/V 점수, 0~100)을 서울 중앙값으로 나눈다.
    유동인구는 있는 분기의 평균(STEP 4와 같음). 직장·상주인구는 2025년 안에서 값이 바뀌지 않는다.
    """
    areas = dim.loc[~dim["is_tourist"], ["trdar_code", "trdar_name", "gu_name", "trdar_type"]].set_index("trdar_code")
    c = context.loc[context["trdar_code"].isin(areas.index)]
    for col in ["worker_population", "resident_population"]:
        n = int((c.groupby("trdar_code")[col].nunique(dropna=True) > 1).sum())
        if n:
            raise ValueError(f"{col} 값이 2025년 안에서 바뀌는 상권이 {n}곳 있습니다.")
    g = c.groupby("trdar_code").agg(
        floating=("floating_population", "mean"), floating_quarters=("floating_population", "count"),
        worker=("worker_population", "first"), resident=("resident_population", "first"))
    a = areas.join(g)
    with np.errstate(divide="ignore", invalid="ignore"):
        # 상주인구가 0이면 비율은 무한대(가장 V 쪽). 직장·상주가 모두 0이면 0/0이라 판정하지 않는다.
        a["worker_ratio"] = a["worker"] / a["resident"]
        a["floating_ratio"] = a["floating"] / a["resident"]
    ok = a[["worker_ratio", "floating_ratio"]].notna().all(axis=1)
    a["pct_worker_ratio"] = pct_rank(a["worker_ratio"].where(ok))
    a["pct_floating_ratio"] = pct_rank(a["floating_ratio"].where(ok))
    a["lv_score"] = a[["pct_worker_ratio", "pct_floating_ratio"]].mean(axis=1, skipna=False)
    a["lv"], median = split(a["lv_score"], "L", "V")
    a["lv_note"] = np.select(
        [a["resident"].isna() & a["worker"].isna(), a["resident"].isna(), a["worker"].isna(), a["floating"].isna(), ~ok],
        ["상주·직장인구 자료 없음", "상주인구 자료 없음", "직장인구 자료 없음", "유동인구 자료 없음", "상주·직장인구가 모두 0"], default="")
    return a, median


def build_ep_cells(fact: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    """E/P 계산에 쓰는 상권×업종 칸: 관광특구 제외, 매출 제공 업종, 4개 분기 매출이 모두 있고 매출 건수가 0보다 큰 칸.

    객단가 = 연간 매출 금액 ÷ 연간 매출 건수. 같은 업종 안 백분위로 바꾼다 (객단가는 업종마다 크게 달라서).
    """
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    f = fact.loc[~fact["trdar_code"].isin(tourist) & fact["sales_supported_industry"]]
    if not f["sales_amount"].notna().eq(f["sales_observed"]).all():
        raise ValueError("sales_observed 표시와 매출 금액 결측이 서로 맞지 않습니다.")
    if not f["sales_amount"].notna().eq(f["sales_count"].notna()).all():
        raise ValueError("매출 금액과 매출 건수의 결측 위치가 다릅니다.")
    g = f.groupby(["trdar_code", "industry_code"], sort=True).agg(
        industry_name=("industry_name", "first"), amount=("sales_amount", "sum"), count=("sales_count", "sum"),
        sales_quarters=("sales_observed", "sum"), store_sum=("store_count", "sum")).reset_index()
    g["stores"] = g["store_sum"] / 4
    cells = g.loc[g["sales_quarters"].eq(4) & g["count"].gt(0)].drop(columns="store_sum").copy()
    cells["per_sale"] = cells["amount"] / cells["count"]
    cells["pct_per_sale"] = cells.groupby("industry_code")["per_sale"].rank(method="average", pct=True) * 100
    return cells.reset_index(drop=True)


def ep_scores(cells: pd.DataFrame) -> pd.DataFrame:
    """상권별 E/P 점수 = 객단가 업종 내 백분위의 매출 건수 가중 평균 (0~100, 높을수록 P 쪽)."""
    num = (cells["pct_per_sale"] * cells["count"]).groupby(cells["trdar_code"]).sum()
    den = cells["count"].groupby(cells["trdar_code"]).sum()
    return pd.DataFrame({"ep_score": num / den, "ep_cells": cells.groupby("trdar_code").size(), "ep_sales_count": den})


def build_types(data: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    a, lv_median = build_lv(data["context"], data["dim"])
    cells = build_ep_cells(data["fact"], data["dim"])
    a = a.join(ep_scores(cells))
    a["ep_cells"] = a["ep_cells"].fillna(0).astype(int)
    a["ep"], ep_median = split(a["ep_score"], "E", "P")
    a["ep_note"] = np.where(a["ep_score"].isna(), "매출 제공 업종의 4개 분기 매출이 없음", "")
    a["type2"] = (a["lv"] + a["ep"]).where(a["lv"].notna() & a["ep"].notna())
    a["sg"] = None  # 상권 S/G는 판정하지 않는다 (팀 결정)
    a.attrs = {"lv_median": lv_median, "ep_median": ep_median}
    return a, cells


def spearman(x: pd.Series, y: pd.Series) -> float:
    """출처: 김지영/step4_dashboard/build_scores.py spearman (scipy 없이 순위의 피어슨 상관)"""
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    return float(d["x"].rank().corr(d["y"].rank()))


def open_close_spearman(fact: pd.DataFrame, dim: pd.DataFrame) -> float:
    """상권 개업률(연간 개업 ÷ 평균 점포)과 폐업률의 순위상관. S/G에 개업률을 쓰지 않은 근거."""
    f = fact.loc[~fact["trdar_code"].isin(set(dim.loc[dim["is_tourist"], "trdar_code"]))]
    t = f.groupby("trdar_code").agg(o=("open_count", "sum"), c=("close_count", "sum"), s=("store_count", "sum"))
    t = t.loc[t["s"] > 0]
    return spearman(t["o"] / (t["s"] / 4), t["c"] / (t["s"] / 4))


def robustness(types: pd.DataFrame, cells: pd.DataFrame) -> dict:
    """판정을 조금 다르게 했을 때 글자가 얼마나 같게 나오는지 (팀 확인용)."""
    out = {}
    # L/V: 두 비율 중 하나만 썼을 때
    for key, col in [("worker_ratio_only", "pct_worker_ratio"), ("floating_ratio_only", "pct_floating_ratio")]:
        alt_letter, _ = split(types[col], "L", "V")
        both = types["lv"].notna()
        out[f"lv_{key}_agree"] = round(float((alt_letter[both] == types.loc[both, "lv"]).mean()), 4)
    # E/P: 평균 점포 5개 이상 칸만 썼을 때 (STEP 4 점수 대상과 같은 점포 기준)
    big = cells.loc[cells["stores"] >= 5].copy()
    big["pct_per_sale"] = big.groupby("industry_code")["per_sale"].rank(method="average", pct=True) * 100
    alt_e = ep_scores(big)["ep_score"]
    alt_letter, _ = split(alt_e, "E", "P")
    common = types["ep"].dropna().index.intersection(alt_letter.dropna().index)
    out["ep_stores_ge5_areas"] = int(alt_letter.notna().sum())
    out["ep_stores_ge5_agree"] = round(float((alt_letter[common] == types.loc[common, "ep"]).mean()), 4)
    out["ep_stores_ge5_common"] = int(len(common))
    for axis, col, median in [("lv", "lv_score", types.attrs["lv_median"]), ("ep", "ep_score", types.attrs["ep_median"])]:
        out[f"{axis}_near_median_{NEAR}"] = int(((types[col] - median).abs() <= NEAR).sum())
    return out


def counts(types: pd.DataFrame, cells: pd.DataFrame) -> dict:
    t = types
    by_kind = t.dropna(subset=["type2"]).groupby(["trdar_type", "type2"]).size().unstack(fill_value=0)
    return {
        "areas": int(len(t)),
        "tourist_excluded": None,  # main()에서 채운다
        "lv": {"L": int(t["lv"].eq("L").sum()), "V": int(t["lv"].eq("V").sum()), "판정 불가": int(t["lv"].isna().sum())},
        "lv_notes": {k: int(v) for k, v in t.loc[t["lv_note"].ne(""), "lv_note"].value_counts().sort_index().items()},
        "ep": {"E": int(t["ep"].eq("E").sum()), "P": int(t["ep"].eq("P").sum()), "판정 불가": int(t["ep"].isna().sum())},
        "type2": {k: int(t["type2"].eq(k).sum()) for k in ["LE", "LP", "VE", "VP"]} | {"판정 불가": int(t["type2"].isna().sum())},
        "type2_by_trdar_type": {k: {c: int(by_kind.at[k, c]) for c in by_kind.columns} for k in by_kind.index},
        "ep_cells": int(len(cells)),
        "ep_industries": int(cells["industry_code"].nunique()),
        "ep_industries_lt30_cells": int((cells.groupby("industry_code").size() < 30).sum()),
        "floating_quarters": {str(k): int(v) for k, v in t["floating_quarters"].value_counts().sort_index().items()},
    }


def build_design(c: dict, open_close: float) -> pd.DataFrame:
    rows = [
        ("1", "창업자 유형", "15문항 검사(기준마다 5문항, 둘 중 하나 고르기). 문항 순서는 섞고 글자는 숨긴다. 기준마다 3개 이상 고른 쪽이 그 글자. "
         "5:0·4:1은 뚜렷, 3:2는 경계", "팀 유형표 그대로", "15문항"),
        ("2", "상권 L/V (주요 고객)", "직장인구 ÷ 상주인구, 유동인구 ÷ 상주인구를 서울 안 백분위로 바꿔 평균(L/V 점수) → 서울 중앙값보다 크면 V",
         "[가정]", f"판정 {c['lv']['L'] + c['lv']['V']:,}곳 (L {c['lv']['L']:,} · V {c['lv']['V']:,}), 판정 불가 {c['lv']['판정 불가']}곳"),
        ("3", "상권 E/P (소비 성향)", "상권×업종 객단가(연간 매출 금액 ÷ 매출 건수, 4개 분기 매출이 모두 있는 칸) → 같은 업종 안 백분위 → "
         "상권별 매출 건수 가중 평균(E/P 점수) → 서울 중앙값보다 크면 P. 프랜차이즈 비율은 방향을 정할 수 없어 쓰지 않음",
         "[가정]", f"판정 {c['ep']['E'] + c['ep']['P']:,}곳 (E {c['ep']['E']:,} · P {c['ep']['P']:,}), 판정 불가 {c['ep']['판정 불가']}곳"),
        ("4", "상권 S/G (상권 변화)", "판정하지 않는다. 2025년 자료만 있어 성장성은 산출하지 않고 분기 변화로 대신하지 않는다(팀 결정). "
         f"상권변화지표는 수집하지 않았다. 상권 개업률은 폐업률과 같이 움직여(순위상관 {open_close:.2f}) 성장보다 손바뀜에 가깝다", "팀 결정과의 충돌 해결", "0곳"),
        ("5", "창업자 S/G → 가중치", "S 안정형: 매출 20 · 경쟁 30 · 안정성 30 · 수요 20 / G 성장형: 35 · 15 · 10 · 40 / 3:2 경계: STEP 4 기본값 30 · 25 · 15 · 30",
         "[가정] 값", "3가지"),
        ("6", "위험 감수 성향", "따로 묻지 않는다. 유형표 11~15번 금융 문항이 곧 S/G라, 따로 받으면 같은 성향을 두 번 반영한다", "계획서 조건", "-"),
        ("7", "결과 보여 주기", "희망 업종에서 L·E 두 글자가 같은 상권만 남기고 STEP 4 업종 내 비교 점수(5번 가중치) 순으로 보여 준다. "
         "경계 글자가 있으면 그 글자를 반대로 바꾼 상권 유형도 '경계 유형'으로 함께 보여 준다 (두 글자가 모두 경계여도 한 글자씩만 바꾼다)",
         "유형표 + 계획서", f"두 글자 모두 판정 {sum(v for k, v in c['type2'].items() if k != '판정 불가'):,}곳"),
        ("8", "소비 잠재력", "이번에는 만들지 않는다. 계산 방식을 적은 EDA_raw_2025.md 8장이 저장소에 없고, '기대보다 덜 쓰여 성장 여지'라는 해석은 검증되지 않았다",
         "자료 없음", "0곳"),
        ("9", "예산", "필터를 만들지 않는다. 보증금·월세 자료가 없어 예산 적합성은 판단하지 않는다", "자료 없음", "-"),
        ("10", "표현", "순위를 매기거나 결과를 약속하는 말 대신 '유형이 맞는 상권', '점수가 높은 상권'으로 쓴다. 유형 이름과 창업 아이템 예시는 팀 유형표의 예시라고 밝힌다",
         "STEP 4 규칙 유지", "-"),
    ]
    return pd.DataFrame(rows, columns=["번호", "항목", "설계", "구분", "대상 수"])


# ---------------------------------------------------------------- 저장


def question_frame() -> pd.DataFrame:
    q = pd.DataFrame(QUESTIONS, columns=["번호", "기준", "질문", "A", "A 글자", "B", "B 글자"])
    q["화면 순서"] = q["번호"].map({no: i + 1 for i, no in enumerate(DISPLAY_ORDER)})
    return q[["번호", "화면 순서", "기준", "질문", "A", "A 글자", "B", "B 글자"]]


def type_frame() -> pd.DataFrame:
    t = pd.DataFrame(TYPES, columns=["유형", "이모지", "이름", "상권 특징", "창업 아이템 예시"])
    names = {ax[side]: ax[f"{side} 이름"] for ax in AXES for side in ["왼쪽", "오른쪽"]}
    for i, ax in enumerate(AXES):
        t[ax["기준"]] = [f"{code[i]} {names[code[i]]}" for code in t["유형"]]
    return t[["유형", "이모지", "이름", "주요 고객", "소비 성향", "상권 변화", "상권 특징", "창업 아이템 예시"]]


TYPE_COLUMNS = ["trdar_code", "trdar_name", "gu_name", "trdar_type", "type2", "lv", "ep", "sg", "lv_score", "ep_score",
                "worker", "resident", "floating", "floating_quarters", "worker_ratio", "floating_ratio", "pct_worker_ratio", "pct_floating_ratio",
                "ep_cells", "ep_sales_count", "lv_note", "ep_note"]


def write_outputs(out: Path, types: pd.DataFrame, design: pd.DataFrame, meta: dict) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    p = {k: out / v for k, v in OUTPUT_NAMES.items()}
    t = types.reset_index()[TYPE_COLUMNS]
    t.to_parquet(p["types"], index=False, compression="zstd")
    csv = dict(index=False, encoding="utf-8-sig", lineterminator="\n")  # 엑셀에서 한글이 깨지지 않도록 BOM
    t.to_csv(p["types_csv"], float_format="%.6f", **csv)
    question_frame().to_csv(p["questions"], **csv)
    type_frame().to_csv(p["type_table"], **csv)
    pd.DataFrame(SG_WEIGHTS).to_csv(p["weights"], **csv)
    design.to_csv(p["design"], **csv)
    p["meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return list(p.values())


def main(out: Path = OUT) -> list[Path]:
    """out은 작업 폴더 안이어야 한다 (검증 때 두 번 실행 비교용 임시 폴더도 작업 폴더 안에 만든다)."""
    out = Path(out).resolve()
    if HERE not in (out, *out.parents):
        raise ValueError(f"결과는 작업 폴더({HERE}) 안에만 씁니다: {out}")
    before = fingerprints()
    doc = check_doc()
    data = read_inputs()
    types, cells = build_types(data)
    c = counts(types, cells)
    c["tourist_excluded"] = int(data["dim"]["is_tourist"].sum())
    rob = robustness(types, cells)
    open_close = open_close_spearman(data["fact"], data["dim"])
    design = build_design(c, open_close)
    if before != fingerprints():
        raise RuntimeError("실행 중에 입력 파일이 바뀌었습니다.")
    meta = {
        "title": "STEP 5 금융 MBTI 상권 유형 (2025년)",
        "axes": AXES,
        "rules": {
            "lv": "직장인구÷상주인구, 유동인구÷상주인구의 서울 안 백분위 평균 > 서울 중앙값 → V, 아니면 L",
            "ep": "상권×업종 객단가(4개 분기 매출 있는 칸)의 같은 업종 안 백분위를 매출 건수로 가중 평균 > 서울 중앙값 → P, 아니면 E",
            "sg": "상권 쪽은 판정하지 않음 (팀 결정: 2025년 자료만 있어 성장성 미산출). 창업자 S/G는 영역 가중치로만 씀",
            "survey": "기준마다 5문항 중 3개 이상 고른 쪽이 그 글자. 5:0·4:1 뚜렷, 3:2 경계",
            "boundary": "경계 글자를 반대로 바꾼 상권 유형도 '경계 유형'으로 함께 보여 줌. 두 글자가 모두 경계이면 한 글자씩만 바꾼다 [가정]",
            "consumption_potential": "만들지 않음 (계산 방식 문서 EDA_raw_2025.md 8장이 저장소에 없음)",
            "budget": "판단하지 않음 (보증금·월세 자료 없음)",
            "near_median_points": NEAR,
        },
        "medians": {"lv_score": types.attrs["lv_median"], "ep_score": types.attrs["ep_median"]},
        "counts": c,
        "diagnostics": {
            "spearman_lv_ep": round(spearman(types["lv_score"], types["ep_score"]), 4),
            "spearman_worker_floating_ratio": round(spearman(types["pct_worker_ratio"], types["pct_floating_ratio"]), 4),
            "spearman_area_open_close_rate": round(open_close, 4),
            **rob,
        },
        "sg_weights": SG_WEIGHTS,
        "display_order": DISPLAY_ORDER,
        "mbti_doc": doc,
        "input_rows": EXPECTED_ROWS,
        "input_sha256": before,
    }
    return write_outputs(out, types, design, meta)


if __name__ == "__main__":
    for path in main():
        print(path.relative_to(ROOT).as_posix())
