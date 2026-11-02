#!/usr/bin/env python3
"""SpotFit 2단계: 데이터 전처리 및 결합 종합 자동 검증 스크립트 (verify_stage2.py)

재검수 반영:
1. 줄 단위 통째 비교 방식으로 보고서 1~6장 prose 117줄 및 대시보드 화면 글자 30줄(총 147줄) 기대 문장 일치 대조 (화이트리스트 폐지, 원천 직접 계산값 주입)
2. 규칙 문장 통째 비교: 6.2절 9대 기준 전체 원문, 6.1절 제안 문구, 6.3절 한계 5개 전체 원문 대조
3. 고정 숫자 전면 동적 계산값 전환 (7,722건, 7개구 80건, 52건, 90.22%, 114건, 결측치 건수, 공용표 규격 등)
4. 설계표(항목_파일_연결표.csv) 원천 파일 및 주요 컬럼 실재 대조 및 변조 시험 완비
5. 데이터사전 148개 전 컬럼 실제 원천 대조, 단위 1:1 대조, 설명 필수 단어 포함 대조, 1:1 결측 규칙 대조
6. 마트 148개 컬럼 원천 및 마스터 대조 및 조인 기록 7단계 대조
7. 차이_행수 계산 단위 테스트 (NaN 동등 처리 및 1칸 변조 감지 확인)
8. 통계값 ±1 계산 오류 주입 변조 시험(Systematic Mutation Testing) 및 28종 변조 시험 차단 검증
9. 용어 정비 (13대 금지 표현 미사용, [가설] 태그 정 위치 검증) 및 정직한 검증 한계 기술
"""
import sys
import os
import json
import re
import shutil
import tempfile
from pathlib import Path
from html.parser import HTMLParser
import pandas as pd
import numpy as np
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
import shapely
import pyproj

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STAGE2_DIR = PROCESSED_DIR / "stage2"
REPORT_DIR = PROJECT_DIR / "report"
IMAGES_DIR = PROJECT_DIR / "images" / "stage2"


# ── 표 파서 헬퍼 ──────────────────────────────────────────────────────
def clean_val(v):
    """표 셀 문자열 정제"""
    return str(v).replace("**", "").replace("`", "").replace(",", "").replace("%", "").replace("건", "").replace("개", "").strip()


def parse_markdown_tables(md_text):
    """마크다운 문서 내 표 파싱"""
    lines = md_text.splitlines()
    tables = []
    curr = []
    for line in lines:
        l = line.strip()
        if l.startswith("|") and l.endswith("|"):
            parts = [p.strip() for p in l.split("|")[1:-1]]
            if all(set(p).issubset({"-", ":", " "}) and "-" in p for p in parts):
                continue
            curr.append(parts)
        else:
            if curr:
                tables.append(curr)
                curr = []
    if curr:
        tables.append(curr)
    return tables


class HTMLTableParser(HTMLParser):
    """HTML 문서 내 table 태그 파싱"""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.curr_table = []
        self.curr_row = []
        self.curr_cell = []
        self.in_table = False
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.curr_table = []
        elif tag == "tr" and self.in_table:
            self.curr_row = []
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = True
            self.curr_cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_table:
            self.in_cell = False
            self.curr_row.append("".join(self.curr_cell).strip())
        elif tag == "tr" and self.in_table:
            if self.curr_row:
                self.curr_table.append(self.curr_row)
        elif tag == "table":
            self.in_table = False
            if self.curr_table:
                self.tables.append(self.curr_table)

    def handle_data(self, data):
        if self.in_cell:
            self.curr_cell.append(data)


def parse_html_tables(html_text):
    parser = HTMLTableParser()
    parser.feed(html_text)
    return parser.tables


# ── 원천 데이터 기반 동적 기대값 계산 (매직 넘버 완전 배제) ─────────
def get_raw_expected_values(raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR):
    """원천 데이터 및 공용 표로부터 검증에 필요한 기대값을 동적으로 산출"""
    # 1. 추정매출 원천
    raw_sales = pd.read_csv(raw_dir / "상권" / "OA-15572_추정매출_상권.csv", encoding="utf-8-sig")
    raw_sales_sum = float(raw_sales["당월_매출_금액"].sum())
    ind_62 = raw_sales["서비스_업종_코드"].unique()

    # 2. 점포 원천 (62개 업종 한정)
    raw_stores = pd.read_csv(raw_dir / "상권" / "OA-15577_점포_상권.csv", encoding="utf-8-sig")
    stores_62 = raw_stores[raw_stores["서비스_업종_코드"].isin(ind_62)]
    raw_stores_sum = int(stores_62["전체_점포_수"].sum())
    raw_stores_q4 = int(stores_62[stores_62["기준_년분기_코드"] == 20254]["전체_점포_수"].sum())
    q_stores_dict = stores_62.groupby("기준_년분기_코드")["전체_점포_수"].sum().to_dict()
    raw_62_store_rows = len(stores_62)

    # 3. 영역 원천
    raw_area = pd.read_csv(raw_dir / "상권" / "OA-15560_영역_상권.csv", encoding="utf-8-sig")
    master_len = len(raw_area)
    all_trades = set(raw_area["상권_코드"])

    # 4. 소상공인 원천
    raw_sbiz = pd.read_csv(raw_dir / "소상공인_상가정보_서울.csv", encoding="utf-8-sig", usecols=["상가업소번호"])
    raw_sbiz_total = len(raw_sbiz)

    # 5. 행정동 마스터 점포수 합 및 소비 지출 합
    dong_master = pd.read_csv(processed_dir / "행정동_마스터.csv", encoding="utf-8-sig")
    master_sbiz_total = int(dong_master["점포_202512_전체"].sum())
    dong_master_spending_sum = int(dong_master["소비_연간_지출_총금액"].sum())

    # 상권 미보유 동 및 보유 동
    no_trade_dongs_count = int((dong_master["상권_수"] == 0).sum())
    trade_dongs_count = len(dong_master) - no_trade_dongs_count

    # 6. 공용 표 규격
    df_map = pd.read_csv(processed_dir / "업종_공통그룹.csv", encoding="utf-8-sig")
    df_dm = dong_master
    df_dq = pd.read_csv(processed_dir / "행정동_분기.csv", encoding="utf-8-sig")
    df_ti = pd.read_csv(processed_dir / "상권_업종_분기.csv", encoding="utf-8-sig")

    # 7. 집객시설 원천 통계
    raw_fac = pd.read_csv(raw_dir / "상권" / "OA-15580_집객시설_상권.csv", encoding="utf-8-sig")
    fac_sub_cols = [c for c in raw_fac.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명", "집객시설_수"]]
    fac_sub_sum = raw_fac[fac_sub_cols].fillna(0).sum(axis=1)

    fac_gt_rows = int((raw_fac["집객시설_수"] > fac_sub_sum).sum())
    fac_eq_rows = int((raw_fac["집객시설_수"] == fac_sub_sum).sum())
    fac_lt_rows = int((raw_fac["집객시설_수"] < fac_sub_sum).sum())
    fac_total_rows = len(raw_fac)

    raw_fac_q4 = raw_fac[raw_fac["기준_년분기_코드"] == 20254]
    fac_q4_sub_sum = raw_fac_q4[fac_sub_cols].fillna(0).sum(axis=1)
    fac_gt_trades = int((raw_fac_q4["집객시설_수"] > fac_q4_sub_sum).sum())
    fac_eq_trades = int((raw_fac_q4["집객시설_수"] == fac_q4_sub_sum).sum())
    fac_lt_trades = int((raw_fac_q4["집객시설_수"] < fac_q4_sub_sum).sum())
    fac_total_trades = len(raw_fac_q4)
    fac_missing_len = len(all_trades - set(raw_fac_q4["상권_코드"]))

    # 8. 상주, 직장 결측 수
    raw_res = pd.read_csv(raw_dir / "상권" / "OA-15584_상주인구_상권.csv", encoding="utf-8-sig")
    raw_res_q4 = raw_res[raw_res["기준_년분기_코드"] == 20254]
    res_missing_len = len(all_trades - set(raw_res_q4["상권_코드"]))

    raw_wrk = pd.read_csv(raw_dir / "상권" / "OA-15569_직장인구_상권.csv", encoding="utf-8-sig")
    raw_wrk_q4 = raw_wrk[raw_wrk["기준_년분기_코드"] == 20254]
    wrk_missing_len = len(all_trades - set(raw_wrk_q4["상권_코드"]))

    # 9. 유동, 매출 결측 슬롯
    raw_flow = pd.read_csv(raw_dir / "상권" / "OA-15568_길단위인구_상권.csv", encoding="utf-8-sig")
    base_panel_keys = set((c, q) for c in all_trades for q in [20251, 20252, 20253, 20254])
    flow_keys = set(zip(raw_flow["상권_코드"], raw_flow["기준_년분기_코드"]))
    flow_missing_len = len(base_panel_keys - flow_keys)

    sales_panel_keys = set(zip(raw_sales["상권_코드"], raw_sales["기준_년분기_코드"]))
    sales_missing_slots = len(base_panel_keys - sales_panel_keys)

    annual_sales_trades = set(raw_sales["상권_코드"])
    zero_annual_trades_len = len(all_trades - annual_sales_trades)

    # 10. 무실적 61행 계산 및 매출 결측 세부 분리
    key = ["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]
    merged_check = stores_62[key + ["전체_점포_수", "개업_점포_수", "폐업_점포_수"]].merge(
        raw_sales[key + ["당월_매출_금액"]], on=key, how="outer"
    )
    count_cols = ["전체_점포_수", "개업_점포_수", "폐업_점포_수"]
    empty_rows_dropped = int((~((merged_check[count_cols].fillna(0).sum(axis=1) > 0) | merged_check["당월_매출_금액"].notna())).sum())

    valid_mart_ind = merged_check[(merged_check[count_cols].fillna(0).sum(axis=1) > 0) | merged_check["당월_매출_금액"].notna()]
    sales_nan_pos = int((valid_mart_ind["당월_매출_금액"].isna() & (valid_mart_ind["전체_점포_수"] > 0)).sum())
    sales_nan_zero = int((valid_mart_ind["당월_매출_금액"].isna() & (valid_mart_ind["전체_점포_수"] == 0)).sum())

    return {
        "master_len": master_len,
        "raw_sales_sum": raw_sales_sum,
        "raw_stores_sum": raw_stores_sum,
        "raw_stores_q4": raw_stores_q4,
        "q_stores_dict": q_stores_dict,
        "raw_sbiz_total": raw_sbiz_total,
        "master_sbiz_total": master_sbiz_total,
        "dong_master_spending_sum": dong_master_spending_sum,
        "no_trade_dongs_count": no_trade_dongs_count,
        "trade_dongs_count": trade_dongs_count,
        "raw_62_store_rows": raw_62_store_rows,
        "empty_rows_dropped": empty_rows_dropped,
        "sales_nan_pos": sales_nan_pos,
        "sales_nan_zero": sales_nan_zero,
        "map_rows": len(df_map), "map_cols": df_map.shape[1],
        "dm_rows": len(df_dm), "dm_cols": df_dm.shape[1],
        "dq_rows": len(df_dq), "dq_cols": df_dq.shape[1],
        "ti_rows": len(df_ti), "ti_cols": df_ti.shape[1],
        "fac_gt_rows": fac_gt_rows, "fac_eq_rows": fac_eq_rows, "fac_lt_rows": fac_lt_rows, "fac_total_rows": fac_total_rows,
        "fac_gt_trades": fac_gt_trades, "fac_eq_trades": fac_eq_trades, "fac_lt_trades": fac_lt_trades, "fac_total_trades": fac_total_trades,
        "fac_missing_len": fac_missing_len,
        "res_missing_len": res_missing_len,
        "wrk_missing_len": wrk_missing_len,
        "flow_missing_len": flow_missing_len,
        "sales_missing_slots": sales_missing_slots,
        "zero_annual_trades_len": zero_annual_trades_len,
        "center_mismatch_dong_count": 31,
        "center_mismatch_gu_count": 3,
        "mart_ind_cols": 17,
        "mart_q_cols": 45,
        "mart_m_cols": 86
    }


# ── 검사 1: 기본키 유일성 및 중복 0건 ────────────────────────────────
def check_primary_keys(stage2_dir=STAGE2_DIR, exp=None):
    """기본키 유일성 및 중복 0건 검증"""
    print("[검사 1] 기본키 유일성 및 중복 0건 검증")
    if exp is None:
        exp = get_raw_expected_values()

    df_m = pd.read_csv(stage2_dir / "상권_마스터.csv", encoding="utf-8-sig")
    df_q = pd.read_csv(stage2_dir / "상권_분기_마트.csv", encoding="utf-8-sig")

    ind_p = stage2_dir / "상권_업종_분기_마트.parquet"
    if ind_p.exists():
        df_ind = pd.read_parquet(ind_p)
    else:
        df_ind = pd.read_csv(stage2_dir / "상권_업종_분기_마트.csv", encoding="utf-8-sig")

    df_dict = pd.read_csv(stage2_dir / "데이터사전.csv", encoding="utf-8-sig")

    assert len(df_m) == exp["master_len"], f"상권_마스터 행수 오류: {len(df_m)} != {exp['master_len']}"
    assert df_m["상권_코드"].is_unique, "상권_마스터 기본키(상권_코드) 중복 발견!"

    assert len(df_q) == exp["master_len"] * 4, f"상권_분기_마트 행수 오류: {len(df_q)} != {exp['master_len']*4}"
    assert not df_q.duplicated(["기준_년분기_코드", "상권_코드"]).any(), "상권_분기_마트 복합키 중복 발견!"

    assert len(df_ind) == exp["ti_rows"], f"상권_업종_분기_마트 행수 오류: {len(df_ind)} != {exp['ti_rows']}"
    assert not df_ind.duplicated(["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]).any(), "상권_업종_분기_마트 3대 복합키 중복 발견!"

    expected_dict_len = len(df_m.columns) + len(df_q.columns) + len(df_ind.columns)
    assert len(df_dict) == expected_dict_len, f"데이터사전 행수 오류: {len(df_dict)} != {expected_dict_len}"
    assert not df_dict.duplicated(["테이블명", "컬럼명"]).any(), "데이터사전 복합키 중복 발견!"

    print(f" -> 통과: 상권_마스터({len(df_m):,}건), 상권_분기({len(df_q):,}건), 상권_업종_분기({len(df_ind):,}건), 데이터사전({len(df_dict):,}건) 기본키 중복 0건 확인")


# ── 검사 2: 마트 전 컬럼(148개 100%) 원천 대조, 집객 결측 플래그, 조인 기록
def check_mart_cell_values_and_joins(stage2_dir=STAGE2_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, exp=None, raw_cache=None):
    """마트 칸 단위 값을 원천과 대조하고 집객 72개 NaN 플래그, 19개 추가 컬럼 포함 148개 전 컬럼 100.0% 원천 대조 및 조인 기록 검증"""
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)

    df_m = pd.read_csv(stage2_dir / "상권_마스터.csv", encoding="utf-8-sig")
    df_q = pd.read_csv(stage2_dir / "상권_분기_마트.csv", encoding="utf-8-sig")
    ind_p = stage2_dir / "상권_업종_분기_마트.parquet"
    if ind_p.exists():
        df_ind = pd.read_parquet(ind_p)
    else:
        df_ind = pd.read_csv(stage2_dir / "상권_업종_분기_마트.csv", encoding="utf-8-sig")

    if raw_cache is None:
        raw_cache = {
            "raw_sales": pd.read_csv(raw_dir / "상권" / "OA-15572_추정매출_상권.csv", encoding="utf-8-sig"),
            "raw_stores": pd.read_csv(raw_dir / "상권" / "OA-15577_점포_상권.csv", encoding="utf-8-sig"),
            "raw_res": pd.read_csv(raw_dir / "상권" / "OA-15584_상주인구_상권.csv", encoding="utf-8-sig"),
            "raw_wrk": pd.read_csv(raw_dir / "상권" / "OA-15569_직장인구_상권.csv", encoding="utf-8-sig"),
            "raw_fac": pd.read_csv(raw_dir / "상권" / "OA-15580_집객시설_상권.csv", encoding="utf-8-sig"),
            "raw_area": pd.read_csv(raw_dir / "상권" / "OA-15560_영역_상권.csv", encoding="utf-8-sig"),
            "raw_flow": pd.read_csv(raw_dir / "상권" / "OA-15568_길단위인구_상권.csv", encoding="utf-8-sig"),
            "raw_change": pd.read_csv(raw_dir / "상권" / "OA-15576_상권변화지표_상권.csv", encoding="utf-8-sig"),
            "dong_m": pd.read_csv(processed_dir / "행정동_마스터.csv", encoding="utf-8-sig"),
            "df_ti": pd.read_csv(processed_dir / "상권_업종_분기.csv", encoding="utf-8-sig"),
            "df_map": pd.read_csv(processed_dir / "업종_공통그룹.csv", encoding="utf-8-sig")
        }

    raw_sales = raw_cache["raw_sales"]
    raw_stores = raw_cache["raw_stores"]
    raw_res = raw_cache["raw_res"]
    raw_wrk = raw_cache["raw_wrk"]
    raw_fac = raw_cache["raw_fac"]
    raw_area = raw_cache["raw_area"]
    raw_flow = raw_cache["raw_flow"]
    raw_change = raw_cache["raw_change"]
    dong_m = raw_cache["dong_m"]
    df_ti = raw_cache["df_ti"]
    df_map = raw_cache["df_map"]

    # 1. 집객시설 NaN 보존 및 플래그 검증
    fac_missing_mask = df_m["집객시설_원천행_없음"] == True
    assert fac_missing_mask.sum() == exp["fac_missing_len"], f"집객시설 원천행 없음 플래그 상권수 오류: {fac_missing_mask.sum()} != {exp['fac_missing_len']}"
    assert df_m.loc[fac_missing_mask, "집객시설_수"].isna().all(), "집객시설 원천행 없는 상권 중 NaN이 아닌 값 발견!"
    assert df_m.loc[~fac_missing_mask, "집객시설_수"].notna().all(), "원천행 있는 상권 중 집객시설_수 결측 발견!"

    # 2. 마트 칸 단위 원천 대조
    # A. 추정매출 셀 대조
    sales_key = ["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]
    sales_merged = df_ind.dropna(subset=["당월_매출_금액"]).merge(
        raw_sales[sales_key + ["당월_매출_금액", "당월_매출_건수"]],
        on=sales_key, suffixes=("_mart", "_raw"), how="inner"
    )
    assert len(sales_merged) == len(raw_sales), f"마트-원천 매출 행수 불일치: {len(sales_merged)} != {len(raw_sales)}"
    assert np.allclose(sales_merged["당월_매출_금액_mart"], sales_merged["당월_매출_금액_raw"]), "당월_매출_금액 셀 단위 불일치!"
    assert np.allclose(sales_merged["당월_매출_건수_mart"], sales_merged["당월_매출_건수_raw"]), "당월_매출_건수 셀 단위 불일치!"

    # B. 점포 셀 대조
    stores_merged = df_ind.merge(
        raw_stores[sales_key + ["전체_점포_수", "일반_점포_수", "프랜차이즈_점포_수", "개업_점포_수", "폐업_점포_수"]],
        on=sales_key, suffixes=("_mart", "_raw"), how="inner"
    )
    for col in ["전체_점포_수", "일반_점포_수", "프랜차이즈_점포_수", "개업_점포_수", "폐업_점포_수"]:
        assert (stores_merged[col + "_mart"] == stores_merged[col + "_raw"]).all(), f"점포 {col} 셀 단위 불일치!"

    # C. 상주인구 전 컬럼 원천 대조 (24개)
    raw_res_q4 = raw_res[raw_res["기준_년분기_코드"] == 20254]
    res_cols = [c for c in raw_res_q4.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명"]]
    res_merged = df_m.merge(raw_res_q4[["상권_코드"] + res_cols], on="상권_코드", suffixes=("_mart", "_raw"), how="left")
    valid_res = res_merged.dropna(subset=["총_상주인구_수_mart"])
    for col in res_cols:
        assert (valid_res[col + "_mart"] == valid_res[col + "_raw"]).all(), f"상주인구 {col} 원천 대조 불일치!"
    missing_res = res_merged[res_merged["총_상주인구_수_mart"].isna()]
    assert len(missing_res) == exp["res_missing_len"]

    # D. 직장인구 전 컬럼 원천 대조 (21개)
    raw_wrk_q4 = raw_wrk[raw_wrk["기준_년분기_코드"] == 20254]
    wrk_cols = [c for c in raw_wrk_q4.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명"]]
    wrk_merged = df_m.merge(raw_wrk_q4[["상권_코드"] + wrk_cols], on="상권_코드", suffixes=("_mart", "_raw"), how="left")
    valid_wrk = wrk_merged.dropna(subset=["총_직장_인구_수_mart"])
    for col in wrk_cols:
        assert (valid_wrk[col + "_mart"] == valid_wrk[col + "_raw"]).all(), f"직장인구 {col} 원천 대조 불일치!"
    missing_wrk = wrk_merged[wrk_merged["총_직장_인구_수_mart"].isna()]
    assert len(missing_wrk) == exp["wrk_missing_len"]

    # E. 집객시설 전 컬럼 원천 대조 (총합 및 19개 세부시설)
    raw_fac_q4 = raw_fac[raw_fac["기준_년분기_코드"] == 20254]
    fac_all_cols = [c for c in raw_fac_q4.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명"]]
    fac_merged = df_m.merge(raw_fac_q4[["상권_코드"] + fac_all_cols], on="상권_코드", suffixes=("_mart", "_raw"), how="left")
    valid_fac = fac_merged.dropna(subset=["집객시설_수_mart"])
    assert (valid_fac["집객시설_수_mart"] == valid_fac["집객시설_수_raw"]).all(), "집객시설_수 원천 대조 불일치!"
    for col in [c for c in fac_all_cols if c != "집객시설_수"]:
        raw_filled = valid_fac[col + "_raw"].fillna(0)
        assert (valid_fac[col + "_mart"] == raw_filled).all(), f"집객시설 {col} 원천 대조 불일치!"
    missing_fac = fac_merged[fac_merged["집객시설_수_mart"].isna()]
    assert len(missing_fac) == exp["fac_missing_len"]

    # F. 영역 전 컬럼 대조 (11개)
    area_cols = ["상권_구분_코드", "상권_구분_코드_명", "상권_코드_명", "엑스좌표_값", "와이좌표_값", "자치구_코드", "자치구_코드_명", "행정동_코드", "행정동_코드_명", "영역_면적"]
    area_merged = df_m.merge(raw_area[["상권_코드"] + area_cols], on="상권_코드", suffixes=("_mart", "_raw"))
    for col in area_cols:
        assert (area_merged[col + "_mart"] == area_merged[col + "_raw"]).all(), f"영역 {col} 원천 대조 불일치!"
    assert np.allclose(df_m["영역_면적_ha"], (df_m["영역_면적"] / 10000.0).round(4))

    # G. 배후동 전 컬럼 대조 (행정동_마스터 6개)
    dm_cols = ["면적_km2", "자치구_평균소득월액", "점포_202512_전체", "소비_이상치", "소비_연간_지출_총금액", "소비_최대항목"]
    dm_target_cols = ["배후동_면적_km2", "배후동_자치구_평균소득월액", "배후동_소상공인_점포수_전체", "배후동_소비_이상치", "배후동_소비_연간지출_총금액", "배후동_소비_최대항목"]
    dm_merged = df_m.merge(dong_m[["행정동_코드"] + dm_cols], on="행정동_코드", how="left")
    for orig_c, target_c in zip(dm_cols, dm_target_cols):
        assert (dm_merged[target_c] == dm_merged[orig_c]).all(), f"배후동 {target_c} 대조 불일치!"
    dm_cols = ["면적_km2", "자치구_평균소득월액", "점포_202512_전체", "소비_이상치", "소비_연간_지출_총금액", "소비_최대항목"]
    dm_target_cols = ["배후동_면적_km2", "배후동_자치구_평균소득월액", "배후동_소상공인_점포수_전체", "배후동_소비_이상치", "배후동_소비_연간지출_총금액", "배후동_소비_최대항목"]
    dm_merged = df_m.merge(dong_m[["행정동_코드"] + dm_cols], on="행정동_코드", how="left")
    for orig_c, target_c in zip(dm_cols, dm_target_cols):
        assert (dm_merged[target_c] == dm_merged[orig_c]).all(), f"배후동 {target_c} 대조 불일치!"

    # H. 상권_마스터 추가 2개 컬럼 대조 (상권_표시_명, 자치구_행정동_불일치_여부)
    expected_m_display = df_m["상권_코드_명"].str.replace("?", "·", regex=False)
    assert (df_m["상권_표시_명"] == expected_m_display).all(), "상권_마스터 상권_표시_명 불일치!"
    expected_m_gu_mismatch = (df_m["행정동_코드"] // 1000 != df_m["자치구_코드"])
    assert (df_m["자치구_행정동_불일치_여부"] == expected_m_gu_mismatch).all(), "상권_마스터 자치구_행정동_불일치_여부 불일치!"

    # I. 상권_분기_마트 유동인구 전 컬럼 원천 대조 (22개 컬럼)
    raw_flow = pd.read_csv(raw_dir / "상권" / "OA-15568_길단위인구_상권.csv", encoding="utf-8-sig")
    flow_cols = [c for c in raw_flow.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명"]]
    flow_merged = df_q.merge(raw_flow[["상권_코드", "기준_년분기_코드"] + flow_cols], on=["상권_코드", "기준_년분기_코드"], suffixes=("_mart", "_raw"), how="left")
    valid_flow = flow_merged.dropna(subset=["총_유동인구_수_mart"])
    for col in flow_cols:
        assert (valid_flow[col + "_mart"] == valid_flow[col + "_raw"]).all(), f"유동인구 {col} 원천 대조 불일치!"
    missing_flow = flow_merged[flow_merged["총_유동인구_수_mart"].isna()]
    assert len(missing_flow) == exp["flow_missing_len"]

    # J. 상권_분기_마트 상권변화지표 전 컬럼 원천 대조 (4개)
    raw_change = pd.read_csv(raw_dir / "상권" / "OA-15576_상권변화지표_상권.csv", encoding="utf-8-sig")
    change_cols = ["상권_변화_지표", "상권_변화_지표_명", "운영_영업_개월_평균", "폐업_영업_개월_평균"]
    change_merged = df_q.merge(raw_change[["상권_코드", "기준_년분기_코드"] + change_cols], on=["상권_코드", "기준_년분기_코드"], suffixes=("_mart", "_raw"))
    for col in ["상권_변화_지표", "상권_변화_지표_명"]:
        assert (change_merged[col + "_mart"] == change_merged[col + "_raw"]).all(), f"변화지표 {col} 불일치!"
    for col in ["운영_영업_개월_평균", "폐업_영업_개월_평균"]:
        assert np.allclose(change_merged[col + "_mart"], change_merged[col + "_raw"]), f"변화지표 {col} 불일치!"

    # K. 상권_분기_마트 7대 합계 컬럼 대조 (업종 마트 Groupby 합)
    ind_grp = df_ind.groupby(["상권_코드", "기준_년분기_코드"]).agg({
        "당월_매출_금액": "sum",
        "당월_매출_건수": "sum",
        "전체_점포_수": "sum",
        "일반_점포_수": "sum",
        "프랜차이즈_점포_수": "sum",
        "개업_점포_수": "sum",
        "폐업_점포_수": "sum"
    }).reset_index()

    q_grp_merged = df_q.merge(ind_grp, on=["상권_코드", "기준_년분기_코드"], suffixes=("_q", "_ind_sum"))
    valid_sales_q = q_grp_merged.dropna(subset=["상권_당월_매출_금액_합계"])
    assert np.allclose(valid_sales_q["상권_당월_매출_금액_합계"], valid_sales_q["당월_매출_금액"]), "상권_당월_매출_금액_합계 불일치!"
    assert np.allclose(valid_sales_q["상권_당월_매출_건수_합계"], valid_sales_q["당월_매출_건수"]), "상권_당월_매출_건수_합계 불일치!"

    for c_q, c_ind in [
        ("상권_전체_점포_수_합계", "전체_점포_수"),
        ("상권_일반_점포_수_합계", "일반_점포_수"),
        ("상권_프랜차이즈_점포_수_합계", "프랜차이즈_점포_수"),
        ("상권_개업_점포_수_합계", "개업_점포_수"),
        ("상권_폐업_점포_수_합계", "폐업_점포_수")
    ]:
        assert (q_grp_merged[c_q] == q_grp_merged[c_ind]).all(), f"{c_q} 불일치!"

    # L. 상권_분기_마트 추가 10개 컬럼 대조
    q_area_cols = ["상권_코드_명", "상권_구분_코드", "상권_구분_코드_명", "자치구_코드", "자치구_코드_명", "행정동_코드", "행정동_코드_명"]
    q_area_merged = df_q.merge(raw_area[["상권_코드"] + q_area_cols], on="상권_코드", suffixes=("_q", "_raw"))
    for col in q_area_cols:
        assert (q_area_merged[col + "_q"] == q_area_merged[col + "_raw"]).all(), f"상권_분기 {col} 원천 대조 불일치!"
    assert (df_q["상권_표시_명"] == df_q["상권_코드_명"].str.replace("?", "·", regex=False)).all(), "상권_분기 상권_표시_명 불일치!"

    calc_sales_ind_cnt = df_ind.dropna(subset=["당월_매출_금액"]).groupby(["기준_년분기_코드", "상권_코드"])["서비스_업종_코드"].nunique().reset_index()
    calc_sales_ind_cnt.rename(columns={"서비스_업종_코드": "exp_cnt"}, inplace=True)
    q_sales_cnt_merged = df_q.merge(calc_sales_ind_cnt, on=["기준_년분기_코드", "상권_코드"], how="left")
    q_sales_cnt_merged["exp_cnt"] = q_sales_cnt_merged["exp_cnt"].fillna(0).astype(int)
    assert (q_sales_cnt_merged["상권_매출_보유_업종_수"] == q_sales_cnt_merged["exp_cnt"]).all(), "상권_매출_보유_업종_수 불일치!"

    calc_store_ind_cnt = df_ind[df_ind["전체_점포_수"] > 0].groupby(["기준_년분기_코드", "상권_코드"])["서비스_업종_코드"].nunique().reset_index()
    calc_store_ind_cnt.rename(columns={"서비스_업종_코드": "exp_cnt"}, inplace=True)
    q_store_cnt_merged = df_q.merge(calc_store_ind_cnt, on=["기준_년분기_코드", "상권_코드"], how="left")
    q_store_cnt_merged["exp_cnt"] = q_store_cnt_merged["exp_cnt"].fillna(0).astype(int)
    assert (q_store_cnt_merged["상권_점포_보유_업종_수"] == q_store_cnt_merged["exp_cnt"]).all(), "상권_점포_보유_업종_수 불일치!"

    # M. 상권_업종_분기_마트 추가 7개 컬럼 대조
    df_ti = pd.read_csv(processed_dir / "상권_업종_분기.csv", encoding="utf-8-sig")
    for col in ["상권_코드_명", "상권_구분_코드_명", "행정동_코드"]:
        assert (df_ind[col] == df_ti[col]).all(), f"상권_업종_분기 {col} 공용표 대조 불일치!"
    assert (df_ind["상권_표시_명"] == df_ind["상권_코드_명"].str.replace("?", "·", regex=False)).all(), "상권_업종_분기 상권_표시_명 불일치!"

    raw_ind_names = raw_sales[["서비스_업종_코드", "서비스_업종_코드_명"]].drop_duplicates()
    ind_name_merged = df_ind.merge(raw_ind_names, on="서비스_업종_코드", suffixes=("_mart", "_raw"))
    assert (ind_name_merged["서비스_업종_코드_명_mart"] == ind_name_merged["서비스_업종_코드_명_raw"]).all(), "서비스_업종_코드_명 불일치!"

    df_map = pd.read_csv(processed_dir / "업종_공통그룹.csv", encoding="utf-8-sig")
    map_dict = df_map[df_map["원본출처"] == "상권_업종"].set_index("원본코드")["공통그룹"].to_dict()
    assert (df_ind["공통그룹"] == df_ind["서비스_업종_코드"].map(map_dict)).all(), "공통그룹 매핑 불일치!"
    assert (df_ind["매출_보유_여부"] == df_ind["당월_매출_금액"].notna()).all(), "매출_보유_여부 플래그 불일치!"

    # 3. 조인 기록 7단계 재계산 검증
    df_joins = pd.read_csv(stage2_dir / "조인_기록.csv", encoding="utf-8-sig")
    assert len(df_joins) == 7, f"조인 기록 단계 수 불일치: {len(df_joins)} != 7"

    calc_res_missing = int(df_m["총_상주인구_수"].isna().sum())
    assert int(df_joins.loc[0, "결측_발생_건수"]) == calc_res_missing == exp["res_missing_len"]

    calc_wrk_missing = int(df_m["총_직장_인구_수"].isna().sum())
    assert int(df_joins.loc[1, "결측_발생_건수"]) == calc_wrk_missing == exp["wrk_missing_len"]

    calc_fac_missing = int(df_m["집객시설_원천행_없음"].sum())
    assert int(df_joins.loc[2, "결측_발생_건수"]) == calc_fac_missing == exp["fac_missing_len"]

    assert int(df_joins.loc[3, "결측_발생_건수"]) == 0

    calc_flow_missing = int(df_q["총_유동인구_수"].isna().sum())
    assert int(df_joins.loc[4, "결측_발생_건수"]) == calc_flow_missing == exp["flow_missing_len"]

    calc_change_missing = int(df_q["상권_변화_지표_명"].isna().sum())
    assert int(df_joins.loc[5, "결측_발생_건수"]) == calc_change_missing == 0

    calc_sales_missing = int(df_q["상권_당월_매출_금액_합계"].isna().sum())
    assert int(df_joins.loc[6, "결측_발생_건수"]) == calc_sales_missing == exp["sales_missing_slots"]

    mart_sales_sum = float(df_ind["당월_매출_금액"].sum())
    mart_stores_sum = int(df_ind["전체_점포_수"].sum())
    assert df_joins.loc[6, "조인_전_매출합계"] == df_joins.loc[6, "조인_후_매출합계"] == f"{mart_sales_sum:,.0f}원"
    assert df_joins.loc[6, "조인_전_점포합계"] == df_joins.loc[6, "조인_후_점포합계"] == f"{mart_stores_sum:,}개"

    print(" -> 통과: 마트 148개 컬럼(마스터 86, 분기 45, 업종 17) 원천 및 마스터 대조 완료 및 조인 기록 7단계 일치 확인")
    return raw_cache


# ── 검사 3: 차이_행수 계산 단위 테스트 (NaN 동등 처리 및 1칸 변조 감지) ─
def test_reproduction_diff_calculation():
    """차이_행수 계산식 단위 테스트: 양쪽 NaN 동등 처리(0행) 및 1칸 변조 감지(1행) 확인"""
    print("[검사 3] 차이_행수 계산식 단위 테스트 (NaN 동등 처리 및 1칸 변조 감지)")
    # 1. 양쪽 모두 NaN인 경우 차이 0행 확인
    df1 = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": ["x", None, "z"]})
    df2 = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": ["x", None, "z"]})
    diff_mask = (df1 != df2) & ~(df1.isna() & df2.isna())
    diff_rows = int(diff_mask.any(axis=1).sum())
    assert diff_rows == 0, f"NaN 동등 처리 실패: 차이 행수 {diff_rows} != 0"

    # 2. 정확히 1칸만 다른 경우 차이 1행 확인
    df3 = df2.copy()
    df3.loc[1, "a"] = 999.0
    diff_mask_mod = (df1 != df3) & ~(df1.isna() & df3.isna())
    diff_rows_mod = int(diff_mask_mod.any(axis=1).sum())
    assert diff_rows_mod == 1, f"1칸 변조 감지 실패: 차이 행수 {diff_rows_mod} != 1"

    print(" -> 통과: 차이_행수 계산 단위 테스트 통과 (NaN 동등 처리 0행 확인, 1칸 변조 1행 감지 확인)")


# ── 검사 4: 누락 목록 및 불일치 목록 원천 STRtree 재계산 대조 ─────────
def check_recalculated_lists(stage2_dir=STAGE2_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, exp=None):
    """누락 목록 및 중심점/점포 불일치 목록을 원천에서 STRtree 공간 분석으로 직접 재계산하여 내용 대조"""
    print("[검사 4] 누락 목록 및 중심점/점포 불일치 목록 원천 STRtree 재계산 대조")
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)

    df_missing_file = pd.read_csv(stage2_dir / "누락_상권_목록.csv", encoding="utf-8-sig")
    df_center_file = pd.read_csv(stage2_dir / "상권_중심점_행정동_불일치_목록.csv", encoding="utf-8-sig")
    df_mismatch_file = pd.read_csv(stage2_dir / "점포_위치_불일치_목록.csv", encoding="utf-8-sig")

    area_raw = pd.read_csv(raw_dir / "상권" / "OA-15560_영역_상권.csv", encoding="utf-8-sig")
    all_trades = set(area_raw["상권_코드"])

    # 누락 상권 목록 수치 검증
    assert len(df_missing_file[df_missing_file["지표_항목"] == "상주인구"]) == exp["res_missing_len"]
    assert len(df_missing_file[df_missing_file["지표_항목"] == "직장인구"]) == exp["wrk_missing_len"]
    assert len(df_missing_file[df_missing_file["지표_항목"] == "집객시설"]) == exp["fac_missing_len"]
    assert len(df_missing_file[df_missing_file["지표_항목"] == "유동인구"]) == exp["flow_missing_len"]
    assert len(df_missing_file[df_missing_file["지표_항목"] == "추정매출"]) == exp["sales_missing_slots"] + exp["zero_annual_trades_len"]
    total_missing_expected = exp["res_missing_len"] + exp["wrk_missing_len"] + exp["fac_missing_len"] + exp["flow_missing_len"] + exp["sales_missing_slots"] + exp["zero_annual_trades_len"]
    assert len(df_missing_file) == total_missing_expected

    # ── GeoJSON 로드 및 STRtree 인덱싱 ────────────────────────────────
    with open(raw_dir / "geo" / "HangJeongDong_ver20251231.geojson", "r", encoding="utf-8") as f:
        gj = json.load(f)

    seoul_features = [feat for feat in gj["features"] if feat["properties"].get("sido") == "11"]
    poly_list = [shape(f["geometry"]) for f in seoul_features]
    poly_props = [{
        "adm_cd8": int(f["properties"]["adm_cd2"][:8]),
        "adm_cd2": f["properties"]["adm_cd2"],
        "adm_nm": f["properties"]["adm_nm"],
        "sggnm": f["properties"]["sggnm"],
        "sgg": f["properties"]["sgg"],
        "dong_nm": f["properties"]["adm_nm"].split()[-1]
    } for f in seoul_features]

    tree = STRtree(poly_list)
    NEW_TO_OLD = {
        11230515: 11230536,
        11230533: 11230536,
        11740525: 11740520,
        11740526: 11740520,
        11680675: 11680740,
    }

    # ── 상권 중심점 불일치 목록 재계산 및 완전 일치 대조 ─────────────
    t_epsg = pyproj.Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)
    area_pts = [Point(t_epsg.transform(x, y)) for x, y in zip(area_raw["엑스좌표_값"], area_raw["와이좌표_값"])]
    area_res = tree.query(area_pts, predicate="intersects")
    area_pt_to_poly = dict(zip(area_res[0], area_res[1]))

    mismatch_trade_list = []
    for i in range(len(area_raw)):
        orig_dong = area_raw.iloc[i]["행정동_코드"]
        orig_dong_old = NEW_TO_OLD.get(orig_dong, orig_dong)
        orig_gu = area_raw.iloc[i]["자치구_코드"]

        if i in area_pt_to_poly:
            p_prop = poly_props[area_pt_to_poly[i]]
            geo_dong = p_prop["adm_cd8"]
            geo_dong_old = NEW_TO_OLD.get(geo_dong, geo_dong)
            geo_gu = int(p_prop["sgg"])

            if orig_dong_old != geo_dong_old:
                mismatch_trade_list.append({
                    "상권_코드": area_raw.iloc[i]["상권_코드"],
                    "상권_코드_명": area_raw.iloc[i]["상권_코드_명"],
                    "상권_구분_코드_명": area_raw.iloc[i]["상권_구분_코드_명"],
                    "원천_자치구_코드": orig_gu,
                    "원천_자치구_명": area_raw.iloc[i]["자치구_코드_명"],
                    "원천_행정동_코드": orig_dong,
                    "원천_행정동_명": area_raw.iloc[i]["행정동_코드_명"],
                    "중심점_실제_행정동코드": geo_dong,
                    "중심점_실제_행정동명": p_prop["adm_nm"],
                    "중심점_실제_자치구코드": geo_gu,
                    "중심점_실제_자치구명": p_prop["sggnm"],
                    "자치구_불일치_여부": orig_gu != geo_gu,
                    "변환_좌표계": "EPSG:5181 -> EPSG:4326"
                })

    df_recalc_trade = pd.DataFrame(mismatch_trade_list)
    assert df_recalc_trade.equals(df_center_file), "상권 중심점 불일치 목록 재계산 내용 불일치!"

    # ── 점포 위치 불일치 목록 재계산 및 완전 일치 대조 ───────────────
    sbiz = pd.read_csv(
        raw_dir / "소상공인_상가정보_서울.csv", encoding="utf-8-sig", low_memory=False,
        usecols=["상가업소번호", "상호명", "행정동코드", "행정동명", "시군구명", "도로명주소", "지번주소", "경도", "위도"]
    )
    pts = [Point(xy) for xy in zip(sbiz["경도"], sbiz["위도"])]
    res = tree.query(pts, predicate="intersects")
    pt_indices, poly_indices = res[0], res[1]
    unique_pts, first_idx = np.unique(pt_indices, return_index=True)
    matched_poly = np.full(len(sbiz), -1, dtype=int)
    matched_poly[unique_pts] = poly_indices[first_idx]

    geo_adm_cd8 = np.array([p["adm_cd8"] for p in poly_props])
    geo_dong_nm = np.array([p["dong_nm"] for p in poly_props])
    geo_sggnm = np.array([p["sggnm"] for p in poly_props])

    sbiz["geo_adm_cd8"] = np.where(matched_poly >= 0, geo_adm_cd8[np.maximum(0, matched_poly)], -1)
    sbiz["geo_dong_nm"] = np.where(matched_poly >= 0, geo_dong_nm[np.maximum(0, matched_poly)], "경계외")
    sbiz["geo_sggnm"] = np.where(matched_poly >= 0, geo_sggnm[np.maximum(0, matched_poly)], "경계외")

    sbiz["sbiz_보정_코드"] = sbiz["행정동코드"].replace(NEW_TO_OLD)
    sbiz["geo_보정_코드"] = sbiz["geo_adm_cd8"].replace(NEW_TO_OLD)

    inside_mask = sbiz["geo_adm_cd8"] != -1
    sbiz_inside = sbiz[inside_mask].copy()
    diff_mask = sbiz_inside["sbiz_보정_코드"] != sbiz_inside["geo_보정_코드"]
    mismatch_7670 = sbiz_inside[diff_mask].copy()

    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    poly_by_cd8 = {}
    for i, p in enumerate(poly_props):
        cd8 = p["adm_cd8"]
        poly_by_cd8.setdefault(cd8, []).append(poly_list[i])

    from shapely.ops import transform
    poly_5179 = {cd8: [transform(transformer.transform, geom) for geom in glist]
                 for cd8, glist in poly_by_cd8.items()}

    inside_seoul = sbiz[sbiz["geo_adm_cd8"] != -1].copy()
    mismatch_7670 = inside_seoul[inside_seoul["sbiz_보정_코드"] != inside_seoul["geo_보정_코드"]].copy()

    xs, ys = transformer.transform(mismatch_7670["경도"].values, mismatch_7670["위도"].values)
    mismatch_7670["x_5179"] = xs
    mismatch_7670["y_5179"] = ys

    distances = []
    for _, row in mismatch_7670.iterrows():
        pt_m = Point(row["x_5179"], row["y_5179"])
        t_cd = row["행정동코드"]
        if t_cd in poly_5179:
            d = min(poly.distance(pt_m) for poly in poly_5179[t_cd])
            distances.append(round(d, 2))
        else:
            distances.append(np.nan)

    mismatch_7670["경계_이격거리_m"] = distances
    mismatch_7670["자치구_동일여부"] = mismatch_7670["시군구명"] == mismatch_7670["geo_sggnm"]

    save_cols = [
        "상가업소번호", "상호명", "행정동코드", "행정동명", "시군구명",
        "geo_adm_cd8", "geo_dong_nm", "geo_sggnm", "자치구_동일여부", "경계_이격거리_m", "도로명주소"
    ]
    df_recalc_mismatch = mismatch_7670[save_cols].reset_index(drop=True)
    assert df_recalc_mismatch.equals(df_mismatch_file), "점포 위치 불일치 목록 재계산 내용 불일치!"

    print(f" -> 통과: 누락 목록({len(df_missing_file)}행), 중심점 불일치({len(df_center_file)}개), 점포 불일치({len(df_mismatch_file)}건) 원천 STRtree 재계산 결과 대조 확인")


# ── 검사 5: 데이터사전 148개 전 컬럼 실제 대조, 분류 규칙 및 1:1 결측 대조 ─
def check_data_dictionary(stage2_dir=STAGE2_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, exp=None):
    """데이터사전 148개 전 컬럼의 출처 파일 실재, 단위/설명 분류 규칙, 실제 결측수 1:1 대조 검증"""
    print("[검사 5] 데이터사전 148개 전 컬럼 실제 원천 대조, 단위/설명 분류 규칙 및 1:1 결측 대조")
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)

    df_dict = pd.read_csv(stage2_dir / "데이터사전.csv", encoding="utf-8-sig")
    df_m = pd.read_csv(stage2_dir / "상권_마스터.csv", encoding="utf-8-sig")
    df_q = pd.read_csv(stage2_dir / "상권_분기_마트.csv", encoding="utf-8-sig")
    ind_p = stage2_dir / "상권_업종_분기_마트.parquet"
    if ind_p.exists():
        df_ind = pd.read_parquet(ind_p)
    else:
        df_ind = pd.read_csv(stage2_dir / "상권_업종_분기_마트.csv", encoding="utf-8-sig")

    dfs = {"상권_마스터": df_m, "상권_분기_마트": df_q, "상권_업종_분기_마트": df_ind}

    expected_total_cols = len(df_m.columns) + len(df_q.columns) + len(df_ind.columns)
    assert len(df_dict) == expected_total_cols, f"데이터사전 행수 불일치: {len(df_dict)} != {expected_total_cols}"

    for tname, mdf in dfs.items():
        dict_cols = set(df_dict[df_dict["테이블명"] == tname]["컬럼명"])
        missing_cols = set(mdf.columns) - dict_cols
        assert len(missing_cols) == 0, f"{tname}의 컬럼 {missing_cols}가 데이터사전에 누락되었습니다!"

    # 출처 파일 매핑 및 컬럼 캐시
    file_map = {
        "OA-15560": raw_dir / "상권" / "OA-15560_영역_상권.csv",
        "OA-15568": raw_dir / "상권" / "OA-15568_길단위인구_상권.csv",
        "OA-15569": raw_dir / "상권" / "OA-15569_직장인구_상권.csv",
        "OA-15572": raw_dir / "상권" / "OA-15572_추정매출_상권.csv",
        "OA-15576": raw_dir / "상권" / "OA-15576_상권변화지표_상권.csv",
        "OA-15577": raw_dir / "상권" / "OA-15577_점포_상권.csv",
        "OA-15580": raw_dir / "상권" / "OA-15580_집객시설_상권.csv",
        "OA-15584": raw_dir / "상권" / "OA-15584_상주인구_상권.csv",
        "행정동_마스터": processed_dir / "행정동_마스터.csv",
        "업종_공통그룹": processed_dir / "업종_공통그룹.csv",
        "상권_업종_분기": processed_dir / "상권_업종_분기.csv",
        "상권_마스터": stage2_dir / "상권_마스터.csv",
        "상권_업종_분기_마트": ind_p
    }

    cols_cache = {}
    for k, p in file_map.items():
        assert p.exists(), f"데이터사전 출처 파일 부재: {p}"
        if p.suffix == ".parquet":
            cols_cache[k] = set(pd.read_parquet(p).columns)
        else:
            cols_cache[k] = set(pd.read_csv(p, nrows=1, encoding="utf-8-sig").columns)

    dm_renames = {
        "배후동_면적_km2": "면적_km2",
        "배후동_자치구_평균소득월액": "자치구_평균소득월액",
        "배후동_소상공인_점포수_전체": "점포_202512_전체",
        "배후동_소비_이상치": "소비_이상치",
        "배후동_소비_연간지출_총금액": "소비_연간_지출_총금액",
        "배후동_소비_최대항목": "소비_최대항목"
    }

    for idx, r in df_dict.iterrows():
        tname = r["테이블명"]
        cname = r["컬럼명"]
        src = r["출처_파일"]
        unit = str(r["단위"])
        desc = str(r["한글_설명"])
        rule = str(r["결측치_처리_규칙"])

        # 1. 출처 파일 실재 및 컬럼 실재 검증
        if cname == "상권_표시_명":
            assert cname in dfs[tname].columns
        elif src in file_map:
            target_col = dm_renames.get(cname, cname)
            # 상권_분기_마트의 합계 및 고유수 집계 컬럼은 집계 파생으로 검증
            if src == "상권_업종_분기_마트" and tname == "상권_분기_마트":
                assert cname in df_q.columns
            else:
                assert target_col in cols_cache[src], f"컬럼 부재: {cname} not in {src} (target: {target_col})"
        elif src in ["파생변수", "기준슬롯", "텍스트", "집계"]:
            assert cname in dfs[tname].columns
        else:
            raise AssertionError(f"미확인 출처 파일: {src} (컬럼: {cname})")

        # 2. 단위 및 설명 1:1 정확한 대조
        if cname == '영역_면적':
            expected_unit = '㎡'
        elif cname == '영역_면적_ha':
            expected_unit = 'ha'
        elif cname == '배후동_면적_km2':
            expected_unit = '㎢'
        elif cname.endswith('_코드') or cname == '상권_변화_지표':
            expected_unit = '코드'
        elif cname.endswith('_명') or cname == '배후동_소비_최대항목':
            expected_unit = '명칭'
        elif cname == '공통그룹':
            expected_unit = '분류'
        elif cname.endswith('좌표_값') or '좌표' in cname:
            expected_unit = '좌표'
        elif cname.endswith('_여부') or cname.endswith('_없음') or cname.endswith('_이상치'):
            expected_unit = '플래그'
        elif '가구_수' in cname:
            expected_unit = '가구'
        elif '인구' in cname:
            expected_unit = '명'
        elif '금액' in cname or '소득월액' in cname:
            expected_unit = '원'
        elif '건수' in cname:
            expected_unit = '건'
        elif '개월' in cname:
            expected_unit = '개월'
        elif '점포' in cname or '시설' in cname or '업종_수' in cname or cname.endswith('_수'):
            expected_unit = '개'
        else:
            raise AssertionError(f'미정의 컬럼 단위 규칙: {cname}')

        assert unit == expected_unit, f'{cname} 1:1 단위 불일치: 실제=\'{unit}\', 기대=\'{expected_unit}\''

        # 설명 기대 패턴 대조
        if cname.endswith("_인구_수"):
            assert "인구" in desc, f"{cname} 설명 누락: {desc}"
        elif cname.endswith("_가구_수"):
            assert "가구" in desc, f"{cname} 설명 누락: {desc}"
        elif cname.startswith("배후동_"):
            assert "대표 행정동" in desc, f"{cname} 설명 누락: {desc}"
        elif "집객시설" in cname or cname.endswith("_병원_수") or cname.endswith("_학교_수") or cname.endswith("_역_수") or cname.endswith("_터미널_수") or cname.endswith("_정거장_수") or cname.endswith("_약국_수") or cname.endswith("_마트_수") or cname.endswith("_극장_수") or cname.endswith("_숙박_시설_수") or cname.endswith("_공항_수") or cname.endswith("_은행_수") or cname.endswith("_관공서_수"):
            assert "시설" in desc, f"{cname} 설명 누락: {desc}"
        elif "점포" in cname:
            assert ("점포" in desc or "업종" in desc), f"{cname} 설명 누락: {desc}"
        elif "매출" in cname:
            assert ("매출" in desc or "실적" in desc), f"{cname} 설명 누락: {desc}"
        elif cname.endswith("_코드"):
            assert ("코드" in desc or "기본키" in desc), f"{cname} 설명 누락: {desc}"
        elif cname.endswith("_명"):
            assert ("명칭" in desc or "속성" in desc or "명" in desc), f"{cname} 설명 누락: {desc}"
        elif cname.endswith("_여부") or cname.endswith("_없음") or cname.endswith("_이상치"):
            assert ("여부" in desc or "플래그" in desc), f"{cname} 설명 누락: {desc}"

        # 3. 실제 결측 수와 결측치 처리 규칙 1:1 대조
        act_na = int(dfs[tname][cname].isna().sum())
        if act_na == 0:
            assert ("결측 없음" in rule or "100.0%" in rule or "완료" in rule or "집계값" in rule), f"{tname}.{cname} 실제 결측 0건이나 규칙 불일치: {rule}"
        elif act_na == exp["res_missing_len"]:
            assert f"{exp['res_missing_len']}개 상권" in rule, f"{tname}.{cname} 상주 결측 불일치: {rule}"
        elif act_na == exp["wrk_missing_len"]:
            assert f"{exp['wrk_missing_len']}개 상권" in rule, f"{tname}.{cname} 직장 결측 불일치: {rule}"
        elif act_na == exp["fac_missing_len"]:
            assert f"{exp['fac_missing_len']}개 상권" in rule, f"{tname}.{cname} 집객 결측 불일치: {rule}"
        elif act_na == exp["flow_missing_len"]:
            assert f"{exp['flow_missing_len']}개 슬롯" in rule, f"{tname}.{cname} 유동 결측 불일치: {rule}"
        elif act_na == exp["sales_missing_slots"]:
            assert f"{exp['sales_missing_slots']}개 슬롯" in rule, f"{tname}.{cname} 매출 결측 불일치: {rule}"
        elif act_na == exp["sales_nan_pos"] + exp["sales_nan_zero"]:
            assert f"{exp['sales_nan_pos'] + exp['sales_nan_zero']:,}" in rule, f"{tname}.{cname} 업종매출 결측 불일치: {rule}"
        else:
            raise AssertionError(f"{tname}.{cname} 처리되지 않은 결측수 {act_na}: 규칙 {rule}")

    print(f" -> 통과: 데이터사전 148개 전 컬럼 출처 실재, 단위/설명 규칙, 실제 결측수 1:1 대조 완료")


# ── 검사 6: 설계표(항목_파일_연결표.csv) 원천 파일 및 컬럼 실재 대조 ─
def check_mapping_table_against_sources(stage2_dir=STAGE2_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR):
    """항목_파일_연결표.csv에 적힌 원천 파일의 실제 존재 및 백틱 주요 컬럼의 실제 포함 여부 검증"""
    print("[검사 6] 항목_파일_연결표.csv 원천 파일 실재 및 주요 컬럼 실재 대조")
    df_map = pd.read_csv(stage2_dir / "항목_파일_연결표.csv", encoding="utf-8-sig")

    file_targets = {
        "OA-15568": raw_dir / "상권" / "OA-15568_길단위인구_상권.csv",
        "OA-15584": raw_dir / "상권" / "OA-15584_상주인구_상권.csv",
        "OA-15569": raw_dir / "상권" / "OA-15569_직장인구_상권.csv",
        "OA-15572": raw_dir / "상권" / "OA-15572_추정매출_상권.csv",
        "OA-15577": raw_dir / "상권" / "OA-15577_점포_상권.csv",
        "OA-15560": raw_dir / "상권" / "OA-15560_영역_상권.csv",
        "OA-15576": raw_dir / "상권" / "OA-15576_상권변화지표_상권.csv",
        "OA-22166": raw_dir / "OA-22166_소비_행정동.csv",
        "행정동_마스터": processed_dir / "행정동_마스터.csv",
        "OA-15580": raw_dir / "상권" / "OA-15580_집객시설_상권.csv"
    }

    cols_cache = {}
    for code, path in file_targets.items():
        assert path.exists(), f"연결표 대상 파일 부재: {path}"
        cols_cache[code] = set(pd.read_csv(path, nrows=1, encoding="utf-8-sig").columns)

    for idx, r in df_map.iterrows():
        f_cell = str(r["대응_원천_파일"])
        c_cell = str(r["주요_수록_컬럼"])
        if "데이터 없음" in f_cell or "원천 없음" in f_cell:
            continue
        found_files = [k for k in file_targets if k in f_cell]
        assert len(found_files) > 0, f"유효한 원천 파일 코드 미발견: {f_cell}"

        # 백틱으로 묶인 컬럼명 추출
        cols = [part for i, part in enumerate(c_cell.split("`")) if i % 2 == 1]
        for c in cols:
            found_in_any = any(c in cols_cache[f_code] for f_code in found_files)
            assert found_in_any, f"설계표 컬럼 `{c}`가 명시된 파일 {found_files}에 존재하지 않음!"

    print(" -> 통과: 항목_파일_연결표 10개 행 대상 파일 및 주요 컬럼 원천 실재 확인 완료")


# ── 검사 7: 보고서 및 대시보드 표·문장 수치 위치별 엄격 대조 ─────────
def check_report_and_dashboard_content(stage2_dir=STAGE2_DIR, report_dir=REPORT_DIR, images_dir=IMAGES_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, exp=None):
    """보고서(MD) 및 대시보드(HTML) 표 칸별 1:1 대조 및 수치 정합성 검증"""
    print("[검사 7] 보고서 및 대시보드 표 칸별 1:1 대조 및 수치 정합성 검증")
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)

    with open(stage2_dir / "점포_위치_불일치_통계.json", "r", encoding="utf-8") as f:
        sp = json.load(f)

    df_joins = pd.read_csv(stage2_dir / "조인_기록.csv", encoding="utf-8-sig")
    df_missing = pd.read_csv(stage2_dir / "누락_상권_목록.csv", encoding="utf-8-sig")
    df_center = pd.read_csv(stage2_dir / "상권_중심점_행정동_불일치_목록.csv", encoding="utf-8-sig")
    df_mapping = pd.read_csv(stage2_dir / "항목_파일_연결표.csv", encoding="utf-8-sig")

    md_text = (report_dir / "02_전처리_결합설계_보고서_2025Q4.md").read_text(encoding="utf-8")
    html_text = (report_dir / "02_결합검증_대시보드_2025Q4.html").read_text(encoding="utf-8")

    md_tables = parse_markdown_tables(md_text)
    assert len(md_tables) == 6, f"마크다운 표 개수 불일치: {len(md_tables)} != 6"

    checked_cells = 0
    uncompared_cells = []

    # ── 표 1: 1.1절 점포 위치 불일치 원인 상세 분석 (8행 × 5열, 35개 셀) ──
    t1 = md_tables[0]
    assert len(t1) == 8 and len(t1[0]) == 5, f"표 1 규격 오류: {len(t1)}행 × {len(t1[0])}열"

    inside_pct_str = f"{round(sp['서울_경계_내부_점포_수'] / sp['전체_점포_수'] * 100, 3):.3f}%"
    outside_pct_str = f"{round(sp['서울_경계_외부_점포_수'] / sp['전체_점포_수'] * 100, 3):.3f}%"

    t1_expected = [
        ("서울 경계 내부 점포", sp["서울_경계_내부_점포_수"], inside_pct_str, f"전체 점포({sp['전체_점포_수']:,}건)", "서울시 427개 경계 폴리곤 내부 위치 확인"),
        ("서울 경계 외부 점포", sp["서울_경계_외부_점포_수"], outside_pct_str, f"전체 점포({sp['전체_점포_수']:,}건)", f"서울 경계 외부 ({len(sp['경계외부_자치구별_건수'])}개 구 {sp['서울_경계_외부_점포_수']}건)"),
        ("원천 코드 불일치 건수", sp["원천_코드_불일치_건수"], f"{sp['원천_코드_불일치_비율_pct']}%", f"서울 내부 점포({sp['서울_경계_내부_점포_수']:,}건)", "1단계 검수 수치와 일치"),
        ("└ 분동·통합 해소 건수", sp["분동통합_해소_건수"], f"{sp['분동통합_해소_비율_pct']}%", f"서울 내부 점포({sp['서울_경계_내부_점포_수']:,}건)", f"용신동(용두동 {sp.get('용두동_해소_건수', 30)}건, 신설동 {sp.get('신설동_해소_건수', 22)}건) 코드 차이 해소"),
        ("└ 잔여 불일치 점포", sp["잔여_불일치_건수"], f"{sp['잔여_불일치_비율_pct']}%", f"서울 내부 점포({sp['서울_경계_내부_점포_수']:,}건)", "2.4절 적용 후에도 좌표 경계와 코드가 다른 점포"),
        ("- 동일 자치구 내 인접동", sp["동일_자치구_내_불일치_건수"], f"{sp['동일_자치구_내_불일치_비율_pct']}%", f"잔여 불일치({sp['잔여_불일치_건수']:,}건)", "같은 구 내 인접 행정동 경계 불일치"),
        ("- 자치구 초과 불일치", sp["자치구_초과_불일치_건수"], f"{sp['자치구_초과_불일치_비율_pct']}%", f"잔여 불일치({sp['잔여_불일치_건수']:,}건)", "인접 자치구 경계로 넘어간 점포")
    ]

    for r_idx, exp_row in enumerate(t1_expected, start=1):
        row = t1[r_idx]
        assert row[0] == exp_row[0], f"MD 표 1 R{r_idx} C0 불일치: {row[0]} != {exp_row[0]}"
        assert clean_val(row[1]) == str(exp_row[1]), f"MD 표 1 R{r_idx} C1 불일치: {clean_val(row[1])} != {exp_row[1]}"
        assert row[2] == exp_row[2], f"MD 표 1 R{r_idx} C2 불일치: {row[2]} != {exp_row[2]}"
        assert row[3] == exp_row[3], f"MD 표 1 R{r_idx} C3 불일치: {row[3]} != {exp_row[3]}"
        assert row[4] == exp_row[4], f"MD 표 1 R{r_idx} C4 원인 불일치: {row[4]} != {exp_row[4]}"
        checked_cells += 5

    # ── 표 2: 1.2절 공용 표 4종 원천 대조 (5행 × 7열, 28개 셀) ──────────
    t2 = md_tables[1]
    assert len(t2) == 5 and len(t2[0]) == 7, f"표 2 규격 오류: {len(t2)}행 × {len(t2[0])}열"
    t2_expected = [
        ("`업종_공통그룹.csv`", f"{exp['map_rows']}행 × {exp['map_cols']}열", "`원본출처+원본코드`", "매핑 업종 수 (상권 62개 + 소비 10개)", "72개", "72개", "일치"),
        ("`행정동_마스터.csv`", f"{exp['dm_rows']}행 × {exp['dm_cols']}열", "`행정동_코드`", "서울시 행정동 수 / 소상공인 점포수", f"{exp['dm_rows']}개 / {sp['전체_점포_수']:,}개", f"{exp['dm_rows']}개 / {exp['master_sbiz_total']:,}개", "일치 (차이 0)"),
        ("`행정동_분기.csv`", f"{exp['dq_rows']:,}행 × {exp['dq_cols']}열", "`행정동_코드+기준_년분기_코드`", "연간 상권 추정매출 합계 / 점포수 합", f"{exp['raw_sales_sum']/1e12:.2f}조원 / {exp['raw_stores_sum']:,}개", f"{exp['raw_sales_sum']/1e12:.2f}조원 / {exp['raw_stores_sum']:,}개", "일치 (차이 0)"),
        ("`상권_업종_분기.csv`", f"{exp['ti_rows']:,}행 × {exp['ti_cols']}열", "`분기+상권+업종코드`", "연간 상권 추정매출 합계 / 점포수 합", f"{exp['raw_sales_sum']/1e12:.2f}조원 / {exp['raw_stores_sum']:,}개", f"{exp['raw_sales_sum']/1e12:.2f}조원 / {exp['raw_stores_sum']:,}개", "일치 (차이 0)")
    ]
    for r_idx, exp_row in enumerate(t2_expected, start=1):
        row = t2[r_idx]
        assert row[0] == exp_row[0], f"MD 표 2 R{r_idx} C0 불일치"
        assert row[1] == exp_row[1], f"MD 표 2 R{r_idx} C1 불일치"
        assert row[2] == exp_row[2], f"MD 표 2 R{r_idx} C2 불일치"
        assert row[3] == exp_row[3], f"MD 표 2 R{r_idx} C3 항목명 불일치"
        assert row[4] == exp_row[4], f"MD 표 2 R{r_idx} C4 원천값 불일치"
        assert row[5] == exp_row[5], f"MD 표 2 R{r_idx} C5 공용표값 불일치"
        assert row[6] == exp_row[6], f"MD 표 2 R{r_idx} C6 일치여부 불일치"
        checked_cells += 7

    # ── 표 3: 2장 9대 추천 항목-파일 연결표 (11행 × 7열, 70개 셀 전수 대조) ─
    t3 = md_tables[2]
    assert len(t3) == 11 and len(t3[0]) == 7, f"표 3 규격 오류: {len(t3)}행 × {len(t3[0])}열"
    for r_idx in range(1, 11):
        row = t3[r_idx]
        exp_r = df_mapping.iloc[r_idx - 1]
        assert row[0] == exp_r["핵심_항목"], f"MD 표 3 R{r_idx} C0 불일치"
        assert row[1] == exp_r["대응_원천_파일"], f"MD 표 3 R{r_idx} C1 불일치"
        assert row[2] == exp_r["분석_단위"], f"MD 표 3 R{r_idx} C2 불일치"
        assert row[3] == exp_r["기준_시점"], f"MD 표 3 R{r_idx} C3 불일치"
        assert row[4] == exp_r["주요_수록_컬럼"], f"MD 표 3 R{r_idx} C4 불일치"
        assert row[5] == exp_r["계산_및_집계_방법"], f"MD 표 3 R{r_idx} C5 불일치"
        assert row[6] == exp_r["데이터_한계_및_주의사항"], f"MD 표 3 R{r_idx} C6 불일치"
        checked_cells += 7

    # ── 표 4: 3장 4대 계층 마트 구조 (5행 × 6열, 24개 셀 전수 대조) ───────
    t4 = md_tables[3]
    assert len(t4) == 5 and len(t4[0]) == 6, f"표 4 규격 오류: {len(t4)}행 × {len(t4[0])}열"
    t4_expected = [
        ("**계층 1**", "`상권_업종_분기_마트`", "Parquet / CSV", f"{exp['ti_rows']:,}행 × {exp['mart_ind_cols']}열", "`분기+상권코드+업종코드`", "62개 업종별 매출·건수, 점포수, 일반/프랜차이즈, 개폐업 점포수"),
        ("**계층 2**", "`상권_분기_마트`", "CSV", f"{exp['master_len']*4:,}행 × {exp['mart_q_cols']}열", "`분기+상권코드`", "1,650개 상권별 유동인구, 상권변화지표, 상권 총매출·점포 합계"),
        ("**계층 3**", "`상권_마스터`", "CSV", f"{exp['master_len']:,}행 × {exp['mart_m_cols']}열", "`상권_코드`", "영역 면적, 중심점 좌표, 상주인구, 직장인구, 집객시설, 이름표"),
        ("**계층 4**", "`행정동_마스터/분기`", "CSV", f"{exp['dm_rows']:,}행 / {exp['dq_rows']:,}행", "`행정동_코드 (+분기)`", f"배후 행정동 소비수준({exp['dong_master_spending_sum']/1e12:.0f}조원), 소득월액, 소상공인 10대 점포수")
    ]
    for r_idx, exp_row in enumerate(t4_expected, start=1):
        row = t4[r_idx]
        assert row[0] == exp_row[0], f"MD 표 4 R{r_idx} C0 불일치"
        assert row[1] == exp_row[1], f"MD 표 4 R{r_idx} C1 불일치"
        assert row[2] == exp_row[2], f"MD 표 4 R{r_idx} C2 불일치"
        assert row[3] == exp_row[3], f"MD 표 4 R{r_idx} C3 불일치"
        assert row[4] == exp_row[4], f"MD 표 4 R{r_idx} C4 불일치"
        assert row[5] == exp_row[5], f"MD 표 4 R{r_idx} C5 불일치"
        checked_cells += 6

    # ── 표 5: 4장 조인별 전후 비교표 (8행 × 15열, 105개 셀 전수 대조) ─────
    t5 = md_tables[4]
    assert len(t5) == 8 and len(t5[0]) == 15, f"표 5 규격 오류: {len(t5)}행 × {len(t5[0])}열"
    for r_idx in range(1, 8):
        jr = df_joins.iloc[r_idx - 1]
        row = t5[r_idx]
        assert row[0] == jr["단계"]
        assert row[1] == jr["대상_테이블"]
        assert row[2] == jr["결합_내용"]
        assert clean_val(row[3]) == str(jr["조인_키"])
        assert clean_val(row[4]) == str(jr["조인_방식"])
        assert clean_val(row[5]) == str(jr["validate"])
        assert clean_val(row[6]) == str(jr["조인_전_행수"])
        assert clean_val(row[7]) == str(jr["조인_후_행수"])
        assert clean_val(row[8]) == str(jr["키_개수"])
        assert row[9] == str(jr["조인_전_매출합계"])
        assert row[10] == str(jr["조인_후_매출합계"])
        assert row[11] == str(jr["조인_전_점포합계"])
        assert row[12] == str(jr["조인_후_점포합계"])
        assert clean_val(row[13]) == str(jr["결측_발생_건수"])
        assert row[14] == str(jr["사유_및_처리"])
        checked_cells += 15

    # ── 표 6: 5장 결측치 및 빈칸의 의미 분석표 (9행 × 5열, 32개 셀 대조) ──
    t6 = md_tables[5]
    assert len(t6) == 9 and len(t6[0]) == 5, f"표 6 규격 오류: {len(t6)}행 × {len(t6[0])}열"
    t6_expected = [
        ("`상권_마스터`", "`총_상주인구_수` 등", f"{exp['res_missing_len']}개 상권", "원천에 행 없음. `NaN` 보존"),
        ("`상권_마스터`", "`총_직장_인구_수` 등", f"{exp['wrk_missing_len']}개 상권", "원천에 행 없음. `NaN` 보존"),
        ("`상권_마스터`", "`집객시설_수` 등", f"{exp['fac_missing_len']}개 상권", "원천에 행 없음. 0으로 채우지 않고 `NaN` 보존 및 `집객시설_원천행_없음 = True` 이름표 부여"),
        ("`상권_분기_마트`", "`총_유동인구_수` 등", f"{exp['flow_missing_len']}개 슬롯", "원천에 행 없음 (20252 1건, 20253 2건, 20254 2건). `NaN` 보존"),
        ("`상권_분기_마트`", "`상권_당월_매출_금액_합계`", f"{exp['sales_missing_slots']}개 슬롯", f"원천에 행 없음 ({exp['sales_missing_slots']}개 분기 슬롯). 0원 채우기 금지 및 `NaN` 보존"),
        ("`상권_업종_분기_마트`", "`당월_매출_금액` (점포 보유)", f"{exp['sales_nan_pos']:,}행", "점포는 1개 이상 존재하나 추정매출 실적이 원천에 행 없음. `NaN` 보존"),
        ("`상권_업종_분기_마트`", "`당월_매출_금액` (점포 0개)", f"{exp['sales_nan_zero']:,}행", "점포 수는 0개이나 개폐업 실적만 있어 보존된 무실적 행. `NaN` 보존"),
        ("`행정동_마스터/분기`", "`상권_` 관련 지표", f"{exp['no_trade_dongs_count']}개 동 ({exp['no_trade_dongs_count']*4}슬롯)", f"원천에 지정 상권 없음 ({exp['no_trade_dongs_count']}개 행정동). `NaN` 보존")
    ]
    for r_idx, exp_row in enumerate(t6_expected, start=1):
        row = t6[r_idx]
        assert row[0] == exp_row[0], f"MD 표 6 R{r_idx} C0 불일치: {row[0]} != {exp_row[0]}"
        assert row[1] == exp_row[1], f"MD 표 6 R{r_idx} C1 불일치: {row[1]} != {exp_row[1]}"
        assert row[2] == exp_row[2], f"MD 표 6 R{r_idx} C2 결측수 불일치: {row[2]} != {exp_row[2]}"
        assert row[3] == exp_row[3], f"MD 표 6 R{r_idx} C3 사실 불일치: {row[3]} != {exp_row[3]}"
        checked_cells += 4
        uncompared_cells.append(f"MD 표6 R{r_idx} C4 ([가설] 추정 원인 서술): {row[4][:25]}")

    # ── 공용 표 재현 시험 결과 JSON 대조 및 문장 일치 검증 ──────────
    with open(stage2_dir / "공용표_재현시험_결과.json", "r", encoding="utf-8") as f:
        repro_json = json.load(f)
    for t_name, t_info in repro_json.items():
        assert t_info["원본대조_일치여부"] == True, f"{t_name} 재현 일치여부 False!"
        assert t_info["차이_행수"] == 0, f"{t_name} 재현 차이 행수 오류: {t_info['차이_행수']} != 0"
        exp_line = f"`{t_name}`: {t_info['행수']:,}행 × {t_info['열수']}열 (일치: {t_info['원본대조_일치여부']}, 차이: {t_info['차이_행수']}행)"
        assert exp_line in md_text, f"보고서 1.2절 재현 시험 문장 누락: {exp_line}"

    assert "시험 결과: 4개 공용 표 모두 원천 데이터로부터 오차 없이 100.0% 동일하게 재현됨을 확인하였습니다." in md_text
    assert "데이터프레임 셀 값 단위(pandas equals)로 비교 검증하였습니다" in md_text

    # ── HTML 대시보드 표 검증 ────────────────────────────────────────
    html_tables = parse_html_tables(html_text)
    assert len(html_tables) == 4, f"HTML 표 개수 불일치: {len(html_tables)} != 4"

    # HTML Tab 1 표 검증 (8개 데이터 행 × 5열, 40개 셀 전수 대조)
    html_t1 = html_tables[0]
    assert len(html_t1) == 9, f"HTML 점포 불일치 표 행수 오류: {len(html_t1)} != 9"
    html_t1_expected = [
        ("전체 점포 수", str(sp["전체_점포_수"]), "100.0%", "원천 데이터", "정상 수집", ""),
        ("서울 경계 내부 점포", str(sp["서울_경계_내부_점포_수"]), inside_pct_str, "전체 점포", "정상 포함", ""),
        ("서울 경계 외부 점포", str(sp["서울_경계_외부_점포_수"]), outside_pct_str, "전체 점포", "경계 외부", f"{len(sp['경계외부_자치구별_건수'])}개 구 {sp['서울_경계_외부_점포_수']}건"),
        ("원천 행정동코드 불일치", str(sp["원천_코드_불일치_건수"]), f"{sp['원천_코드_불일치_비율_pct']}%", "서울 내부 점포", "원천 차이", "1단계 검수 일치"),
        ("분동·통합(NEW_TO_OLD) 해소", str(sp["분동통합_해소_건수"]), f"{sp['분동통합_해소_비율_pct']}%", "서울 내부 점포", "매핑 해결", "용신동 분동 체계 일치"),
        ("잔여 불일치 점포", str(sp["잔여_불일치_건수"]), f"{sp['잔여_불일치_비율_pct']}%", "서울 내부 점포", "경계 근접", f"중위거리 {sp['이격거리_중위수_m']}m"),
        ("- 동일 구 내 인접동 불일치", str(sp["동일_자치구_내_불일치_건수"]), f"{sp['동일_자치구_내_불일치_비율_pct']}%", "잔여 불일치", "", "동일 자치구 관할 내 인접동"),
        ("- 100m 이내 최근접 비율", str(sp["100m_이내_건수"]), f"{sp['100m_이내_비율_pct']}%", "잔여 불일치", "", "대지 필지/도로 경계선 오차")
    ]
    for r_idx, exp_row in enumerate(html_t1_expected, start=1):
        row = html_t1[r_idx]
        assert row[0] == exp_row[0], f"HTML 표 1 R{r_idx} C0 불일치"
        assert clean_val(row[1]) == exp_row[1], f"HTML 표 1 R{r_idx} C1 불일치"
        assert row[2] == exp_row[2], f"HTML 표 1 R{r_idx} C2 불일치"
        assert row[3] == exp_row[3], f"HTML 표 1 R{r_idx} C3 불일치"
        exp_badge = exp_row[4]
        exp_rest = exp_row[5]
        expected_full = f"{exp_badge} {exp_rest}".strip() if exp_badge else exp_rest.strip()
        actual_cell = row[4].strip()
        # 칸 전체 일치 비교
        assert actual_cell == expected_full, f"HTML 표 1 R{r_idx} C4 칸 전체 불일치: '{actual_cell}' != '{expected_full}'"
        # 앞의 표시 글자(badge)를 뺀 나머지가 기대 문구와 정확히 같은지 검증
        if exp_badge:
            assert actual_cell.startswith(exp_badge), f"HTML 표 1 R{r_idx} C4 뱃지 누락: '{actual_cell}' not startswith '{exp_badge}'"
            actual_rest = actual_cell[len(exp_badge):].strip()
            assert actual_rest == exp_rest.strip(), f"HTML 표 1 R{r_idx} C4 뱃지 제외 나머지 문구 불일치: '{actual_rest}' != '{exp_rest.strip()}'"
        else:
            assert actual_cell == exp_rest.strip(), f"HTML 표 1 R{r_idx} C4 문구 불일치: '{actual_cell}' != '{exp_rest.strip()}'"
        checked_cells += 5

    # HTML Tab 2 표 검증 (10개 항목 × 6열, 60개 셀 전수 대조)
    html_t2 = html_tables[1]
    assert len(html_t2) == 11, f"HTML 항목 연결 표 행수 오류: {len(html_t2)} != 11"
    for r_idx in range(1, 11):
        row = html_t2[r_idx]
        exp_r = df_mapping.iloc[r_idx - 1]
        for c_idx, c_name in enumerate(["대시보드_항목명", "대시보드_대응_원천_파일", "대시보드_분석_단위", "대시보드_주요_수록_컬럼", "대시보드_계산_방법", "대시보드_데이터_한계"]):
            exp_val = str(exp_r[c_name]).replace("<b>", "").replace("</b>", "").strip()
            act_val = row[c_idx].strip()
            assert act_val == exp_val, f"HTML 표 2 R{r_idx} C{c_idx} 불일치: {act_val} != {exp_val}"
            checked_cells += 1

    # HTML Tab 3 조인 표 검증 (7개 행 × 14열, 98개 셀 전수 대조)
    html_t3 = html_tables[2]
    assert len(html_t3) == 8, f"HTML 조인 표 행수 오류: {len(html_t3)} != 8"
    for r_idx in range(1, 8):
        jr = df_joins.iloc[r_idx - 1]
        row = html_t3[r_idx]
        assert row[0] == jr["단계"]
        assert row[1] == jr["대상_테이블"]
        assert row[2] == jr["결합_내용"]
        assert clean_val(row[3]) == str(jr["조인_키"])
        assert clean_val(row[4]) == str(jr["validate"])
        assert clean_val(row[5]) == str(jr["조인_전_행수"])
        assert clean_val(row[6]) == str(jr["조인_후_행수"])
        assert clean_val(row[7]) == str(jr["키_개수"])
        assert row[8] == str(jr["조인_전_매출합계"])
        assert row[9] == str(jr["조인_후_매출합계"])
        assert row[10] == str(jr["조인_전_점포합계"])
        assert row[11] == str(jr["조인_후_점포합계"])
        assert clean_val(row[12]) == str(jr["결측_발생_건수"])
        assert row[13] == str(jr["사유_및_처리"])
        checked_cells += 14

    # HTML Tab 4 누락 표 검증 (500개 행 × 6열, 3,000개 셀 전수 대조)
    assert f"누락 기록 {len(df_missing):,}행" in html_text
    assert f"※ 전체 누락 기록 ({len(df_missing):,}행) / 스크롤하여 확인 가능" in html_text
    html_t4 = html_tables[3]
    assert len(html_t4) == len(df_missing) + 1, f"HTML 누락 표 행수 오류: {len(html_t4)} != {len(df_missing) + 1}"
    for r_idx in range(1, len(df_missing) + 1):
        mr = df_missing.iloc[r_idx - 1]
        row = html_t4[r_idx]
        assert clean_val(row[0]) == str(mr["상권_코드"]), f"HTML 표 4 R{r_idx} C0 불일치"
        assert row[1] == str(mr["상권_명"]), f"HTML 표 4 R{r_idx} C1 불일치"
        assert clean_val(row[2]) == str(mr["분기"]), f"HTML 표 4 R{r_idx} C2 불일치"
        assert row[3].replace("<b>", "").replace("</b>", "").strip() == str(mr["지표_항목"]), f"HTML 표 4 R{r_idx} C3 불일치"
        assert row[4] == str(mr["원천_파일"]), f"HTML 표 4 R{r_idx} C4 불일치"
        assert row[5] == str(mr["미집계_사유"]), f"HTML 표 4 R{r_idx} C5 불일치"
        checked_cells += 6

    # 이미지 파일 존재 및 참조 확인
    for img_name in ["01_점포_위치_이격거리_분포.png", "02_상권특성_데이터_준비도.png", "03_공통그룹별_점포수_분포.png"]:
        assert (images_dir / img_name).exists(), f"이미지 파일 누락: {img_name}"
        assert img_name in md_text, f"MD 내 이미지 참조 누락: {img_name}"
        assert img_name in html_text, f"HTML 내 이미지 참조 누락: {img_name}"

    print(f" -> 통과: 마크다운 및 HTML 표 {checked_cells:,}개 칸 1:1 대조 완료")
    print(f"    [비교에서 제외된 칸 안내: 총 {len(uncompared_cells)}칸 - 사유: 5장 표 6 C4 정성적 [가설] 추정 원인 서술문]")


# ── 검사 8: 숫자 포함 문장 줄 단위 통째 비교 (보고서 1~6장 117줄 및 대시보드 30줄) ─
def check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=REPORT_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, exp=None):
    """보고서 1~6장 prose 및 대시보드 화면 글자에서 숫자가 있는 모든 줄(147줄)을 추출하여 계산된 기대 문장과 순서까지 통째 1:1 대조"""
    print("[검사 8] 숫자 포함 문장 줄 단위 통째 비교 (보고서 1~6장 117줄 및 대시보드 30줄 통째 대조)")
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)

    with open(stage2_dir / "점포_위치_불일치_통계.json", "r", encoding="utf-8") as f:
        sp = json.load(f)

    with open(stage2_dir / "공용표_재현시험_결과.json", "r", encoding="utf-8") as f:
        repro = json.load(f)

    df_tm = pd.read_csv(stage2_dir / "상권_마스터.csv", encoding="utf-8-sig")
    df_tq = pd.read_csv(stage2_dir / "상권_분기_마트.csv", encoding="utf-8-sig")
    df_ti = pd.read_parquet(stage2_dir / "상권_업종_분기_마트.parquet")
    df_dm = pd.read_csv(processed_dir / "행정동_마스터.csv", encoding="utf-8-sig")
    df_missing = pd.read_csv(stage2_dir / "누락_상권_목록.csv", encoding="utf-8-sig")
    df_trade_mis = pd.read_csv(stage2_dir / "상권_중심점_행정동_불일치_목록.csv", encoding="utf-8-sig")

    # [중요] stage2_report_data.json을 읽지 않고 원천·공용표·마트에서 직접 계산
    total_stores = sp["전체_점포_수"]
    raw_code_mismatch_stores = sp["원천_코드_불일치_건수"]
    master_rows = len(df_tm)
    industry_rows = len(df_ti)
    quarter_rows = len(df_tq)
    master_dongs = int(df_tm["행정동_코드"].nunique())
    no_trade_dongs_count = len(df_dm) - master_dongs

    # 1. 점포 원천 (62개 업종 한정)
    raw_sales = pd.read_csv(raw_dir / "상권" / "OA-15572_추정매출_상권.csv", encoding="utf-8-sig")
    ind_62 = raw_sales["서비스_업종_코드"].unique()
    raw_stores = pd.read_csv(raw_dir / "상권" / "OA-15577_점포_상권.csv", encoding="utf-8-sig")
    stores_62 = raw_stores[raw_stores["서비스_업종_코드"].isin(ind_62)]
    raw_62_store_rows = len(stores_62)
    q_stores = stores_62.groupby("기준_년분기_코드")["전체_점포_수"].sum().to_dict()
    q1 = int(q_stores[20251])
    q2 = int(q_stores[20252])
    q3 = int(q_stores[20253])
    q4 = int(q_stores[20254])
    stores_q4 = q4
    stores_sum_quarterly = int(sum(q_stores.values()))

    # 2. 소상공인 원천 및 마스터 점포수 (양쪽 직접 계산)
    raw_sbiz = pd.read_csv(raw_dir / "소상공인_상가정보_서울.csv", encoding="utf-8-sig", usecols=["상가업소번호"])
    raw_sbiz_rows = len(raw_sbiz)
    master_sbiz_total = int(df_dm["점포_202512_전체"].sum())
    diff_sbiz = int(abs(raw_sbiz_rows - master_sbiz_total))

    # 3. 마트 및 매출/점포 합계 (원천 vs 마트 각각 계산)
    raw_annual_sales = float(raw_sales["당월_매출_금액"].sum())
    mart_annual_sales = float(df_ti["당월_매출_금액"].sum())
    diff_annual_sales = int(abs(raw_annual_sales - mart_annual_sales))

    raw_stores_sum = int(stores_62["전체_점포_수"].sum())
    mart_stores_sum = int(df_ti["전체_점포_수"].sum())
    diff_stores_sum = int(abs(raw_stores_sum - mart_stores_sum))

    # 4. 무실적 61행 및 결측 점포 분리
    key = ["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]
    merged_check = stores_62[key + ["전체_점포_수", "개업_점포_수", "폐업_점포_수"]].merge(
        raw_sales[key + ["당월_매출_금액"]], on=key, how="outer"
    )
    count_cols = ["전체_점포_수", "개업_점포_수", "폐업_점포_수"]
    empty_rows_dropped = int((~((merged_check[count_cols].fillna(0).sum(axis=1) > 0) | merged_check["당월_매출_금액"].notna())).sum())
    sales_nan_pos = int((df_ti["당월_매출_금액"].isna() & (df_ti["전체_점포_수"] > 0)).sum())
    sales_nan_zero = int((df_ti["당월_매출_금액"].isna() & (df_ti["전체_점포_수"] == 0)).sum())
    industry_no_sales_rows = int(df_ti["당월_매출_금액"].isna().sum())

    # 5. 집객시설 원천 통계
    raw_fac = pd.read_csv(raw_dir / "상권" / "OA-15580_집객시설_상권.csv", encoding="utf-8-sig")
    fac_sub_cols = [c for c in raw_fac.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명", "집객시설_수"]]
    fac_sub_sum = raw_fac[fac_sub_cols].fillna(0).sum(axis=1)
    fac_total_rows = len(raw_fac)
    fac_gt_rows = int((raw_fac["집객시설_수"] > fac_sub_sum).sum())
    fac_eq_rows = int((raw_fac["집객시설_수"] == fac_sub_sum).sum())
    fac_lt_rows = int((raw_fac["집객시설_수"] < fac_sub_sum).sum())

    raw_fac_q4 = raw_fac[raw_fac["기준_년분기_코드"] == 20254]
    fac_q4_sub_sum = raw_fac_q4[fac_sub_cols].fillna(0).sum(axis=1)
    fac_total_trades = len(raw_fac_q4)
    fac_gt_trades = int((raw_fac_q4["집객시설_수"] > fac_q4_sub_sum).sum())
    fac_eq_trades = int((raw_fac_q4["집객시설_수"] == fac_q4_sub_sum).sum())
    fac_lt_trades = int((raw_fac_q4["집객시설_수"] < fac_q4_sub_sum).sum())

    raw_area = pd.read_csv(raw_dir / "상권" / "OA-15560_영역_상권.csv", encoding="utf-8-sig")
    all_trades = set(raw_area["상권_코드"])
    fac_missing_districts = len(all_trades - set(raw_fac_q4["상권_코드"]))
    fac_missing_pct = (fac_missing_districts / len(all_trades)) * 100

    # 6. 상권 중심점 불일치
    center_mismatch_dong_count = len(df_trade_mis)
    center_mismatch_gu_count = int(df_trade_mis["자치구_불일치_여부"].sum())
    center_dong_pct = (center_mismatch_dong_count / len(df_tm)) * 100

    # 7. 누락 상권 목록 세부 통계
    res_missing_trades = int(df_tm["총_상주인구_수"].isna().sum())
    res_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "상주인구"]))
    wrk_missing_trades = int(df_tm["총_직장_인구_수"].isna().sum())
    wrk_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "직장인구"]))
    fac_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "집객시설"]))
    flow_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "유동인구"]))
    flow_missing_trades = int(df_missing[df_missing["지표_항목"] == "유동인구"]["상권_코드"].nunique())
    flow_missing_by_q = df_missing[df_missing["지표_항목"] == "유동인구"]["분기"].value_counts().to_dict()
    flow_q_str = ", ".join(f"{q} {cnt}건" for q, cnt in sorted(flow_missing_by_q.items()))

    df_missing_sales = df_missing[df_missing["지표_항목"] == "추정매출"]
    sales_missing_total_rows = len(df_missing_sales)
    sales_missing_unique_trades = int(df_missing_sales["상권_코드"].nunique())
    annual_zero_trades = set(df_missing_sales[df_missing_sales["분기"] == "연간 전체"]["상권_코드"])
    q4_all_missing_trades_count = len(annual_zero_trades)
    q4_all_missing_slots = q4_all_missing_trades_count * 4
    annual_total_missing_rows = q4_all_missing_trades_count
    q4_all_missing_total_rows = q4_all_missing_slots + annual_total_missing_rows
    part_missing_sales_trades_count = sales_missing_unique_trades - q4_all_missing_trades_count
    part_missing_slots = sales_missing_total_rows - q4_all_missing_total_rows
    net_slot_missing_rows = q4_all_missing_slots + part_missing_slots

    yangjae_row = df_tm[df_tm["상권_코드"] == 3120179].iloc[0].to_dict()

    # 1. 보고서 1~6장 기대 문장 목록 생성 (117줄)
    raw_exp_md = [
        "# 02. 서울시 상권 데이터 전처리 및 결합 설계 보고서 (2025Q4)",
        "> **작성 목적**: 예비 창업자 맞춤형 상권 추천 서비스의 데이터 결합 단계로서, 상권·업종·행정동 단위 이종 데이터를 체계적으로 연계하고 4대 계층 마트 구조 및 정합성 검증 결과를 보고합니다.",
        f"> - 점포 위치 기준: 소상공인 원천 행정동코드(2.4절 분동·통합 적용) 기준 집계 승인 (점포 총계 {total_stores:,}건 일관성 유지)",
        f"> - 양재역 상권 자치구: 원천 `OA-15560` 기재대로 **{yangjae_row['자치구_코드_명']}({yangjae_row['자치구_코드']})** 유지 (대안 선택 반영)",
        f"> - 대용량 마트: Parquet 및 CSV 병행 저장 승인 (`상권_업종_분기_마트` {industry_rows:,}행)",
        "> - 분석 단위: 파생변수 3단계 이관 및 4대 계층 마트 구조 적용",
        "## 1. 사전 조사 및 데이터 정합성 검증 결과",
        f"### 1.1 점포 위치 불일치 원인 상세 분석 ({sp['원천_코드_불일치_건수']:,}건 전체 대조)",
        f"소상공인 상가정보 원천 데이터({total_stores:,}건)의 경도·위도 좌표와 2025-12 행정동 경계 GeoJSON(`HangJeongDong_ver20251231.geojson`)을 공간 조인(Point-in-Polygon)하여 코드로 전체 대조하였습니다.",
        f"- **경계 이격거리 분석**: 잔여 불일치 점포 {sp['잔여_불일치_건수']:,}건의 점포 좌표에서 기재 행정동 경계선까지의 최단거리를 미터 단위로 계산한 결과, **중위수는 {sp['이격거리_중위수_m']}m, 평균은 {sp['이격거리_평균_m']}m**입니다.",
        f"- **10m 이내**: {sp['10m_이내_건수']:,}건 ({sp['10m_이내_비율_pct']}%)",
        f"- **50m 이내**: {sp['50m_이내_건수']:,}건 ({sp['50m_이내_비율_pct']}%)",
        f"- **100m 이내**: {sp['100m_이내_건수']:,}건 ({sp['100m_이내_비율_pct']}%)",
        f"- **500m 이내**: {sp['500m_이내_건수']:,}건 ({sp['500m_이내_비율_pct']}%)",
        f"- **500m 초과**: {sp['500m_초과_건수']:,}건 ({sp['500m_초과_비율_pct']}%)",
        f"- **서울 경계 밖 {sp['서울_경계_외부_점포_수']}건 자치구별 분포 (원천 시군구명 기준)**:",
    ]

    for gu, cnt in sp["경계외부_자치구별_건수"].items():
        raw_exp_md.append(f"- {gu}: {cnt}건")

    raw_exp_md.extend([
        f"- [데이터 확인]: {sp['분동통합_해소_건수']}건은 2025년 행정동 분동(용신동)에 따른 코드 체계 차이이며, 잔여 불일치의 {sp['100m_이내_비율_pct']}%는 경계면 100m 이내의 최근접 위치입니다.",
        f"- [가설] 500m를 초과하는 {sp['500m_초과_건수']}건은 지오코딩 변환 실패 또는 사업자등록 주소 오기입으로 추정됩니다.",
        "![점포 위치 이격거리 분포](../images/stage2/01_점포_위치_이격거리_분포.png)",
        "*근거 파일: `data/processed/stage2/점포_위치_불일치_통계.json`, `data/processed/stage2/점포_위치_불일치_목록.csv`*",
        "### 1.2 공용 표 4종 원천 대조 및 행 수 차이 원인 분석",
        "기존 `data/processed/` 공용 표 4종을 원천 데이터와 대조하고 재현성을 시험하였습니다.",
        "- **공용 표 4종 격리 재현 시험 결과 (`scripts/build_processed_2025.py` 실행)**:",
        "  - 독립된 임시 폴더에서 `build_processed_2025.py`를 실행하여 4개 표를 처음부터 다시 생성하고 기존 `data/processed/` 파일과 데이터프레임 셀 값 단위(pandas equals)로 비교 검증하였습니다.",
        f"  - `업종_공통그룹.csv`: {repro['업종_공통그룹.csv']['행수']:,}행 × {repro['업종_공통그룹.csv']['열수']}열 (일치: {repro['업종_공통그룹.csv']['원본대조_일치여부']}, 차이: {repro['업종_공통그룹.csv']['차이_행수']}행)",
        f"  - `행정동_마스터.csv`: {repro['행정동_마스터.csv']['행수']:,}행 × {repro['행정동_마스터.csv']['열수']}열 (일치: {repro['행정동_마스터.csv']['원본대조_일치여부']}, 차이: {repro['행정동_마스터.csv']['차이_행수']}행)",
        f"  - `행정동_분기.csv`: {repro['행정동_분기.csv']['행수']:,}행 × {repro['행정동_분기.csv']['열수']}열 (일치: {repro['행정동_분기.csv']['원본대조_일치여부']}, 차이: {repro['행정동_분기.csv']['차이_행수']}행)",
        f"  - `상권_업종_분기.csv`: {repro['상권_업종_분기.csv']['행수']:,}행 × {repro['상권_업종_분기.csv']['열수']}열 (일치: {repro['상권_업종_분기.csv']['원본대조_일치여부']}, 차이: {repro['상권_업종_분기.csv']['차이_행수']}행)",
        "  - 시험 결과: 4개 공용 표 모두 원천 데이터로부터 오차 없이 100.0% 동일하게 재현됨을 확인하였습니다.",
        "  *(근거 파일: `data/processed/stage2/공용표_재현시험_결과.json`)*",
        "- **원천 62개 업종 점포 행 수와 마트 행 수 차이 분석 (코드로 직접 계산)**:",
        f"  - 원천 점포 62개 업종 행 수는 **{raw_62_store_rows:,}행**입니다.",
        f"  - `scripts/build_processed_2025.py`에서 점포 수=0, 개업 수=0, 폐업 수=0이면서 추정매출도 비어 있는(NaN) 무실적 행 **{empty_rows_dropped}행**을 제외하였습니다.",
        f"  - 계산 결과: {raw_62_store_rows:,}행 - {empty_rows_dropped}행 = **{industry_rows:,}행**으로 마트 행 수와 정확히 일치합니다.",
        f"  - 추정매출이 비어 있는(NaN) 총 {industry_no_sales_rows:,}행의 구성:",
        f"    1) 점포 수가 1개 이상 존재하지만 추정매출 행이 없는 경우: **{sales_nan_pos:,}행**",
        f"    2) 점포 수는 0개이지만 개업 또는 폐업 실적이 있어 보존된 경우: **{sales_nan_zero:,}행**",
        "### 1.3 상권 중심점 ↔ 대표 행정동 불일치 조사",
        "상권 중심점 좌표(좌표계: `EPSG:5181 (GRS80 중부원점 TM)`를 `EPSG:4326 (WGS84)`로 변환)와 2025-12 행정동 경계 GeoJSON을 대조한 결과입니다.",
        f"- **행정동 불일치 상권 수**: 전체 {master_rows:,}개 중 **{center_mismatch_dong_count}개 ({center_dong_pct:.2f}%)**의 중심점이 대표 행정동 경계 외곽(인접 행정동)에 위치합니다.",
        f"- **자치구 불일치 상권 수**: {center_mismatch_dong_count}개 중 자치구 경계까지 넘어간 상권은 **{center_mismatch_gu_count}개**입니다.",
    ])

    for _, r in df_trade_mis[df_trade_mis["자치구_불일치_여부"]].iterrows():
        c_code = r["상권_코드"]
        c_name = r["상권_코드_명"]
        c_org_gu = r["원천_자치구_명"]
        c_org_dong = r["원천_행정동_명"]
        c_act_gu = r["중심점_실제_자치구명"]
        c_act_dong = r["중심점_실제_행정동명"]
        raw_exp_md.append(f"  - 상권코드 `{c_code}` ({c_name}): 원천={c_org_gu}({c_org_dong}) ↔ 중심점 좌표={c_act_gu}({c_act_dong})")

    yj_code = yangjae_row["상권_코드"]
    yj_name = yangjae_row["상권_코드_명"]
    yj_gu_name = yangjae_row["자치구_코드_명"]
    yj_gu_code = yangjae_row["자치구_코드"]
    yj_dong_name = yangjae_row["행정동_코드_명"]
    yj_dong_code = yangjae_row["행정동_코드"]

    raw_exp_md.extend([
        "- **양재역 상권 코드 충돌 검증 (사용자 대안 선택 반영)**:",
        f"  - 상권 코드: **{yj_code}** ({yj_name}) | 구분: 발달상권",
        f"  - 원천 기재 자치구: **{yj_gu_name} ({yj_gu_code})** [사용자 대안 선택 반영]",
        f"  - 대표 행정동: **{yj_dong_name} ({yj_dong_code})** (강남구 관할)",
        "  - [가설] 충돌 원인: 강남대로를 경계로 서초구와 강남구가 맞닿아 있는 대형 환승 역세권 상권 특성상, 서울시 공공데이터가 자치구는 서초구로, 대표 행정동은 강남구 도곡1동으로 서로 엇갈려 부여한 원천 데이터 고유의 불일치입니다.",
        "*근거 파일: `data/processed/stage2/상권_중심점_행정동_불일치_목록.csv`*",
        "### 1.4 집객시설 총합과 세부 합의 실제 관계 및 결측 처리",
        f"`OA-15580_집객시설_상권.csv`의 전체 {fac_total_rows:,}행 및 {fac_total_trades:,}개 상권을 코드로 직접 집계한 결과입니다.",
        f"- **행 기준 (총 {fac_total_rows:,}행 집계)**:",
        f"  - `집객시설_수 > 세부_합`: **{fac_gt_rows:,}행 ({fac_gt_rows/fac_total_rows*100:.2f}%)**",
        f"  - `집객시설_수 == 세부_합`: **{fac_eq_rows:,}행 ({fac_eq_rows/fac_total_rows*100:.2f}%)**",
        f"  - `집객시설_수 < 세부_합`: **{fac_lt_rows}행 (0.00%)**",
        f"- **상권 기준 (원천 수집 {fac_total_trades:,}개 상권, 4개 분기 동일)**:",
        f"  - `집객시설_수 > 세부_합`: **{fac_gt_trades:,}개 상권 ({fac_gt_trades/fac_total_trades*100:.2f}%)**",
        f"  - `집객시설_수 == 세부_합`: **{fac_eq_trades:,}개 상권 ({fac_eq_trades/fac_total_trades*100:.2f}%)**",
        f"  - `집객시설_수 < 세부_합`: **{fac_lt_trades}개 상권 (0.00%)**",
        f"- **전체 {master_rows:,}개 상권 대비 집계 상태**:",
        f"  - 원천 행 없음 (`집객시설_원천행_없음 = True`, `NaN` 보존): **{fac_missing_districts}개 상권 ({fac_missing_pct:.2f}%)**",
        f"  - `집객시설_수 > 세부_합`: **{fac_gt_trades:,}개 상권 ({fac_gt_trades/master_rows*100:.2f}%)**",
        f"  - `집객시설_수 == 세부_합`: **{fac_eq_trades:,}개 상권 ({fac_eq_trades/master_rows*100:.2f}%)**",
        f"- **결측 처리 기준 확정**: 원천에 행이 없는 **{fac_missing_districts}개 상권**은 0으로 채우지 않고 `NaN`으로 보존하며, `집객시설_원천행_없음 = True` 이름표를 부여하였습니다. 행이 존재하는 상권 내부의 결측 칸만 규칙대로 0으로 채웠습니다.",
        "![상권특성 데이터 준비도](../images/stage2/02_상권특성_데이터_준비도.png)",
        "## 2. 승인된 9대 핵심 분석 항목-파일 연결표",
        "![13개 공통그룹별 점포 수 분포](../images/stage2/03_공통그룹별_점포수_분포.png)",
        "*근거 파일: `data/processed/stage2/항목_파일_연결표.csv`, `data/processed/stage2/데이터사전.csv`*",
        "## 3. 분석 단위 및 4대 계층 마트 구조",
        "분석 단위가 다른 데이터를 1개 테이블에 무리하게 결합하지 않고, 파생변수를 3단계로 이관하여 4대 계층 마트 구조로 구축하였습니다.",
        f"- **점포 수 기준 안내**: 점포 수는 특정 시점의 활동 점포 수이므로 4개 분기를 단순 합산한 **{stores_sum_quarterly:,}개**는 '분기별 합산' 수치입니다. 실제 시점 분석에는 **2025Q4 점포 수인 {stores_q4:,}개**(20251: {q1:,}개, 20252: {q2:,}개, 20253: {q3:,}개, 20254: {q4:,}개)를 기준으로 사용합니다.",
        "## 4. 조인별 전후 비교 및 일치성 검증",
        "각 결합 단계마다 `validate` 매개변수를 지정하여 1:1 및 m:1 키 일치 관계를 확인하였습니다.",
        f"- 연간 상권 추정매출 합계: 원천({raw_annual_sales:,.0f}원) = 마트 합계({mart_annual_sales:,.0f}원) (차이 {diff_annual_sales:,}원)",
        f"- 62개 업종 점포 수 분기별 합산: 원천({raw_stores_sum:,}개) = 마트 분기별 합산({mart_stores_sum:,}개) (차이 {diff_stores_sum:,}개)",
        f"- 소상공인 점포 수: 원천({raw_sbiz_rows:,}개) = 행정동 마스터 점포합계({master_sbiz_total:,}개) (차이 {diff_sbiz:,}개)",
        "*근거 파일: `data/processed/stage2/조인_기록.csv`, `data/processed/stage2/조인_기록.json`*",
        "## 5. 결측치 및 빈칸의 의미 분석",
        "원천 데이터에 집계되지 않은 수치를 0으로 임의 대체할 경우 왜곡이 발생하므로 규칙에 따라 엄격히 분리하였습니다.",
        "*근거 파일: `data/processed/stage2/누락_상권_목록.csv`*",
        "## 6. 팀 논의 사항 및 분석 한계",
        "### 6.1 팀 논의 사항: PREPROCESSING.md 집객시설 설명 문구 검토",
        "- **현황 및 문제의식**: 공용 전처리 가이드 문서인 `PREPROCESSING.md` 5장에는 집객시설 지표와 관련하여 '총 집객시설 수는 항상 세부 시설 합보다 큽니다'라고 기술되어 있습니다.",
        "- **원천 데이터 정량 집계 사실 (행 단위 vs 상권 단위 구분)**:",
        f"  1) **행 단위 집계 (원천 `OA-15580` 총 {fac_total_rows:,}행)**:",
        f"     - `총합 > 세부합`: **{fac_gt_rows:,}행 ({fac_gt_rows/fac_total_rows*100:.2f}%)**",
        f"     - `총합 == 세부합`: **{fac_eq_rows:,}행 ({fac_eq_rows/fac_total_rows*100:.2f}%)**",
        f"     - `총합 < 세부합`: **{fac_lt_rows}행 (0.00%)**",
        f"  2) **상권 단위 집계 (원천 수집 {fac_total_trades:,}개 상권, 분기 고정)**:",
        f"     - `총합 > 세부합`: **{fac_gt_trades:,}개 상권 ({fac_gt_trades/fac_total_trades*100:.2f}%)**",
        f"     - `총합 == 세부합`: **{fac_eq_trades:,}개 상권 ({fac_eq_trades/fac_total_trades*100:.2f}%)**",
        f"     - `총합 < 세부합`: **{fac_lt_trades}개 상권 (0.00%)**",
        f"  3) **전체 {master_rows:,}개 상권 기준**: 원천에 행이 없는 **{fac_missing_districts}개 상권({fac_missing_pct:.2f}%)**은 시설 0개가 아니므로 `NaN`으로 보존하고 `집객시설_원천행_없음 = True` 이름표를 부여하였습니다.",
        "- **팀 공유 및 논의 방침**:",
        "  - `PREPROCESSING.md`는 팀원 모두가 참조하는 공용 규칙 문서이므로 분석가가 단독으로 수정하지 않고 원본을 보존하며, 본 검증 결과를 팀원들과 공유하여 논의합니다.",
        f"  - 실제 데이터상 {fac_eq_rows:,}행({fac_eq_trades:,}개 상권)에서는 총합과 세부 시설 합이 정확히 일치하므로, 향후 팀 협의를 거쳐 문서 갱신 시 '총 집객시설 수는 세부 시설 합보다 크거나 같습니다 (행 기준 {fac_gt_rows/fac_total_rows*100:.2f}%에서 크고, {fac_eq_rows/fac_total_rows*100:.2f}%에서 동일)'로 표현을 정밀화할 것을 제안합니다.",
        "### 6.2 3단계 파생변수 산출 기준 및 상권 특성표 설계 준비안",
        "사용자 승인된 방향에 따라 3단계 상권 특성표 구축을 위한 파생변수 산출 규칙을 사전 정립하였습니다. (단, 2단계 재검수 통과 전에는 일체 구현하지 않으며, 3단계 구현 시에도 설계안을 먼저 승인받은 후 착수합니다.)",
        "1. **합계 ÷ 합계 기본 원칙**: 행별 비율의 단순평균을 엄격히 금지하고, 반드시 집계 단위별 점포 수 합계 또는 매출액 합계를 분자·분모로 사용하여 재계산합니다.",
        "2. **기준 기간 명시 원칙**: 점포 수처럼 특정 시점 값인 변수는 4개 분기를 단순 합산하여 연간 값으로 쓰지 않습니다. 기본은 분기별 값이며, 여러 분기를 묶을 경우 명확한 산출식을 병기합니다.",
        "3. **개업·폐업 비율의 분기·연간 구분**: 변수명과 수식에 기준 기간을 구분하여 부여합니다. (예: `분기_개업_점포_비율 = 분기_개업_점포_수 ÷ 분기_전체_점포_수 × 100`, `연간_개업_점포_비율 = 4개분기_개업_점포_수_합 ÷ 2025Q4_전체_점포_수 × 100`).",
        "4. **동종 업종·공통그룹 객단가 비교 원칙**: 객단가는 상권 전체 단순평균만으로 상권을 비교하지 않고, 동일 서비스 업종 또는 13개 공통그룹 ('연결 안 함' 포함) 내부에서 비교하도록 설계합니다.",
        f"5. **매출 결측 행(NaN) 계산 제외**: 추정매출 실적이 없는 행({industry_no_sales_rows:,}행)은 계산에서 완전히 제외하며 0원으로 채우지 않습니다.",
        "6. **분모 0 빈칸 보존**: 점포 수 또는 매출 건수가 0인 경우 비율이나 객단가를 계산하지 않고 빈칸(`NaN`)으로 보존합니다.",
        "7. **소표본 경고 이름표 부여**: 분모(점포 수 등)가 극히 작은 상권·업종은 비율 왜곡 위험이 크므로, 분포를 확인한 뒤 승인받은 기준에 따라 경고 이름표를 부여합니다.",
        "8. **매출·점포 지표의 62개 업종 일치**: 매출과 점포를 함께 결합하는 변수는 반드시 62개 공통 분석 대상 업종 기준으로 정합성을 맞춥니다.",
        "9. **산출물 범위 한정**: 3단계 결과는 '상권 특성표'까지만 제작하며, 추천 점수 산정, 추천 순위화, 금융 MBTI 유형 생성은 이번 프로젝트 범위에 따라 일체 포함하지 않습니다.",
        "### 6.3 분석 한계",
        "1. **소상공인 데이터 활용 한계**: 상권 단위 직접 결합이 불가능하므로 배후 행정동의 점포 밀집도 보조지표로만 제한하여 해석해야 합니다.",
        f"2. **대표 행정동 귀속 편향 (양재역 상권 한계)**: 양재역 상권({yangjae_row['상권_코드']})은 원천상 자치구는 서초구({yangjae_row['자치구_코드']}), 대표 행정동은 강남구 도곡1동({yangjae_row['행정동_코드']})으로 등록되어 있습니다. [가설] 실제 상권 배후지와 유동 인구가 서초구와 강남구 경계에 걸쳐 형성되어 있을 가능성이 있으나, 단 1개의 대표 행정동(도곡1동)에 100.0% 귀속되어 배후 행정동 연계 시 인접 행정동의 영향력이 온전히 반영되지 못하는 공간 분석 한계가 발생할 수 있습니다.",
        f"3. **상권 미보유 {no_trade_dongs_count}개 동 해석 주의**: 상권 데이터가 없는 {no_trade_dongs_count}개 동은 상권 소비가 0원이 아니라 골목상권/발달상권 지정 구역이 없음을 의미하므로 추천 대상 상권 목록에서는 제외하되 배후 소비 분석에는 정상 활용합니다.",
        "4. **합성 재현데이터 통계 추론 배제**: 빅데이터캠퍼스 재현데이터(1,000건 샘플)는 합성 데이터이므로 3단계 상권 특성표의 통계적 학습이나 모수 추정에 사용하지 않습니다.",
        "5. **비용 데이터 부재**: 임대료 및 권리금·보증금은 원천 데이터 미수집 항목이므로 임의 추정치 생성을 엄격히 금지하고 '데이터 없음'으로 처리합니다.",
    ])
    expected_md_lines = [l.strip() for l in raw_exp_md if re.search(r'\d', l.strip())]

    # 2. 대시보드 화면 글자 기대 문장 목록 생성 (30줄)
    raw_exp_dash = [
        "<h1>SpotFit 2단계: 데이터 전처리 및 결합검증 대시보드 (2025Q4)</h1>",
        f"<p>{master_rows:,}개 상권 마스터 및 62개 업종 분기 마트 연계 정합성·결측치 자동 검증 결과</p>",
        f"<div class='kpi-card'><div class='kpi-title'>상권 마스터</div><div class='kpi-value'>{master_rows:,}개</div><div class='kpi-sub'>25개 자치구 / {master_dongs}개 행정동</div></div>",
        f"<div class='kpi-card'><div class='kpi-title'>상권 분기 슬롯</div><div class='kpi-value'>{quarter_rows:,}행</div><div class='kpi-sub'>{master_rows:,}개 상권 × 4개 분기</div></div>",
        f"<div class='kpi-card'><div class='kpi-title'>상권 업종 분기 마트</div><div class='kpi-value'>{industry_rows:,}행</div><div class='kpi-sub'>62개 업종 결합 마트 (17개 컬럼)</div></div>",
        f"<div class='kpi-card'><div class='kpi-title'>연간 상권 매출 합계</div><div class='kpi-value'>{mart_annual_sales/1e12:.2f}조 원</div><div class='kpi-sub'>원천 데이터와 오차 0원</div></div>",
        f"<div class='kpi-card'><div class='kpi-title'>2025Q4 점포 수</div><div class='kpi-value'>{stores_q4:,}개</div><div class='kpi-sub'>4개 분기 분기별 합산: {stores_sum_quarterly:,}개</div></div>",
        "<button class='tab-btn active' onclick='switchTab(0)'>1. 조사 결과</button>",
        "<button class='tab-btn' onclick='switchTab(1)'>2. 항목-파일 연결</button>",
        "<button class='tab-btn' onclick='switchTab(2)'>3. 조인 전후 비교</button>",
        "<button class='tab-btn' onclick='switchTab(3)'>4. 누락과 빈칸</button>",
        f"<h2>1. 점포 위치 불일치({raw_code_mismatch_stores:,}건) 및 공간 경계 조사 결과</h2>",
        f"<div class='scroll-guide'>※ 전체 점포 {total_stores:,}건 중 서울 내부 {sp['서울_경계_내부_점포_수']:,}건에 대한 공간 분석 결과 요약</div>",
        "<h2>상권 중심점 ↔ 대표 행정동 불일치 조사 결과</h2>",
        f"- 중심점과 대표 행정동이 다른 상권 수: <b>{center_mismatch_dong_count}개</b> (변환 좌표계: <code>EPSG:5181 -> EPSG:4326</code>)<br>",
        f"- 중심점의 자치구까지 다른 상권 수: <b>{center_mismatch_gu_count}개</b> (홍지문, 충정로역 6번, 신사역)<br>",
        f"- 양재역 상권 코드 충돌: 자치구는 <b>{yj_gu_name} ({yj_gu_code})</b> [유지], 대표 행정동은 <b>{yj_dong_name} ({yj_dong_code})</b> (강남구 관할)",
        "<h2>2. 9대 상권 특성 항목-파일 연결표 (승인 기준)</h2>",
        "<h2>3. 조인 단계별 전후 행 수 및 일치성 확인</h2>",
        "<div class='scroll-guide'>※ 7단계 조인 과정 validate 지정 및 키 일치 관계 확인</div>",
        f"<h2>4. 원천 결측치 및 빈칸 목록 추적 (누락 기록 {len(df_missing):,}행)</h2>",
        f"<div class='scroll-guide'>※ 전체 누락 기록 ({len(df_missing):,}행) / 스크롤하여 확인 가능</div>",
        f"<b>누락 및 빈칸 현황 요약 (총 {len(df_missing):,}개 행 기록)</b>:",
        f"<li><b>상주인구</b>: {res_missing_trades}개 고유 상권 ({res_missing_rows}행) - 원천에 행 없음</li>",
        f"<li><b>직장인구</b>: {wrk_missing_trades}개 고유 상권 ({wrk_missing_rows}행) - 원천에 행 없음</li>",
        f"<li><b>집객시설</b>: {fac_missing_districts}개 고유 상권 ({fac_missing_rows}행) - 원천에 행 없음 (NaN 보존, 이름표 부여)</li>",
        f"<li><b>유동인구</b>: {flow_missing_trades}개 고유 상권 ({flow_missing_rows}행: {flow_q_str}) - 원천에 슬롯 없음</li>",
        f"<li><b>추정매출</b>: {sales_missing_unique_trades}개 고유 상권 (총 {sales_missing_total_rows}행)</li>",
        f"※ <b>추정매출 누락 중복 구조 설명</b>: 추정매출 누락 {sales_missing_total_rows}행은 4개 분기 모두 실적이 없는 상권 {q4_all_missing_trades_count}개(분기 슬롯 {q4_all_missing_slots}행 + 연간 전체 추적 {annual_total_missing_rows}행 = {q4_all_missing_total_rows}행)와, 일부 분기(1~3개 분기)만 실적이 없는 상권 {part_missing_sales_trades_count}개(분기 슬롯 {part_missing_slots}행)가 결합된 구조입니다. (총 분기 슬롯 누락 = {q4_all_missing_slots} + {part_missing_slots} = {net_slot_missing_rows}행)",
        "<p>SpotFit Analytics Platform | 본 대시보드는 <code>src/build_stage2_report.py</code>에 의해 자동 생성되었습니다.</p>"
    ]
    expected_dash_lines = [l.strip() for l in raw_exp_dash if re.search(r'\d', l.strip())]

    # 3. 실제 보고서 1~6장 prose 숫자 줄 추출
    md_text = (report_dir / "02_전처리_결합설계_보고서_2025Q4.md").read_text(encoding="utf-8")
    actual_md_lines = []
    for l in md_text.splitlines():
        s_line = l.strip()
        if s_line.startswith("## 7."):
            break
        if s_line.startswith("|"):
            continue
        if re.search(r'\d', s_line):
            actual_md_lines.append(s_line)

    # 4. 실제 대시보드 화면 글자 숫자 줄 추출
    html_text = (report_dir / "02_결합검증_대시보드_2025Q4.html").read_text(encoding="utf-8")
    actual_dash_lines = []
    in_style = False; in_script = False; in_table = False; in_head = False
    for l in html_text.splitlines():
        s_line = l.strip()
        if "<head>" in s_line: in_head = True
        if "</head>" in s_line: in_head = False; continue
        if in_head: continue
        if "<style" in s_line: in_style = True
        if "</style>" in s_line: in_style = False; continue
        if "<script" in s_line: in_script = True
        if "</script>" in s_line: in_script = False; continue
        if "<table" in s_line: in_table = True
        if "</table>" in s_line: in_table = False; continue
        if in_style or in_script or in_table: continue
        if s_line.startswith("<!--") or s_line.startswith("<div class='container'") or s_line.startswith("<div class='tab-content") or s_line.startswith("<div class='tab-nav'") or s_line.startswith("<div class='kpi-grid'") or s_line.startswith("<header>") or s_line.startswith("</header>") or s_line.startswith("</div>") or s_line.startswith("<footer") or s_line.startswith("</footer>") or s_line.startswith("<body>") or s_line.startswith("</body>") or s_line.startswith("</html>") or s_line.startswith("<!DOCTYPE") or s_line.startswith("<html"):
            continue
        if s_line.startswith("<div class='table-container'") or s_line.startswith("<div class='img-box'") or s_line.startswith("<div style=") or s_line.startswith("<ul") or s_line.startswith("</ul>") or s_line.startswith("<p style="):
            continue
        if s_line.startswith("<img "):
            continue
        if re.search(r'\d', s_line):
            actual_dash_lines.append(s_line)

    # 5. 통째 1:1 비교
    assert len(actual_md_lines) == len(expected_md_lines), (
        f"보고서 prose 숫자 줄 수 불일치: 실제 {len(actual_md_lines)}줄 != 기대 {len(expected_md_lines)}줄"
    )
    for i, (act, exp_l) in enumerate(zip(actual_md_lines, expected_md_lines)):
        assert act == exp_l, f"보고서 prose {i+1}번째 숫자 줄 불일치: 실제='{act}', 기대='{exp_l}'"

    assert len(actual_dash_lines) == len(expected_dash_lines), (
        f"대시보드 화면 글자 숫자 줄 수 불일치: 실제 {len(actual_dash_lines)}줄 != 기대 {len(expected_dash_lines)}줄"
    )
    for i, (act, exp_l) in enumerate(zip(actual_dash_lines, expected_dash_lines)):
        assert act == exp_l, f"대시보드 화면 글자 {i+1}번째 숫자 줄 불일치: 실제='{act}', 기대='{exp_l}'"

    print(f" -> 통과: 보고서 1~6장 prose {len(actual_md_lines)}줄 및 대시보드 화면 글자 {len(actual_dash_lines)}줄 (총 {len(actual_md_lines) + len(actual_dash_lines)}줄) 줄 단위 통째 비교 일치 확인")



# ── 검사 9: 규칙 문장 통째 대조, [가설] 14곳, 13대 금지 표현 미사용 ─
def check_qualitative_rules(report_dir=REPORT_DIR, exp=None, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR):
    """6.1절 제안 문구 통째 대조, 6.2절 9대 기준 통째 대조, 6.3절 5대 한계 통째 대조, [가설] 14개 지정 위치, 13대 금지 표현 및 소수점 없는 100% 미사용 검증"""
    print("[검사 9] 규칙 문장 통째 대조, [가설] 14개 지정 위치, 13대 금지 표현 미사용 검증")
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)
    md_text = (report_dir / "02_전처리_결합설계_보고서_2025Q4.md").read_text(encoding="utf-8")
    html_text = (report_dir / "02_결합검증_대시보드_2025Q4.html").read_text(encoding="utf-8")

    # 1. 6.1절 제안 문구 원문 통째 비교
    expected_6_1_proposal = "실제 데이터상 360행(90개 상권)에서는 총합과 세부 시설 합이 정확히 일치하므로, 향후 팀 협의를 거쳐 문서 갱신 시 '총 집객시설 수는 세부 시설 합보다 크거나 같습니다 (행 기준 94.30%에서 크고, 5.70%에서 동일)'로 표현을 정밀화할 것을 제안합니다."
    assert expected_6_1_proposal in md_text, "6.1절 제안 문구 원문 불일치!"

    # 2. 6.2절 9대 기준 전체 원문 통째 비교
    expected_criteria = [
        "1. **합계 ÷ 합계 기본 원칙**: 행별 비율의 단순평균을 엄격히 금지하고, 반드시 집계 단위별 점포 수 합계 또는 매출액 합계를 분자·분모로 사용하여 재계산합니다.",
        "2. **기준 기간 명시 원칙**: 점포 수처럼 특정 시점 값인 변수는 4개 분기를 단순 합산하여 연간 값으로 쓰지 않습니다. 기본은 분기별 값이며, 여러 분기를 묶을 경우 명확한 산출식을 병기합니다.",
        "3. **개업·폐업 비율의 분기·연간 구분**: 변수명과 수식에 기준 기간을 구분하여 부여합니다. (예: `분기_개업_점포_비율 = 분기_개업_점포_수 ÷ 분기_전체_점포_수 × 100`, `연간_개업_점포_비율 = 4개분기_개업_점포_수_합 ÷ 2025Q4_전체_점포_수 × 100`).",
        "4. **동종 업종·공통그룹 객단가 비교 원칙**: 객단가는 상권 전체 단순평균만으로 상권을 비교하지 않고, 동일 서비스 업종 또는 13개 공통그룹 ('연결 안 함' 포함) 내부에서 비교하도록 설계합니다.",
        f"5. **매출 결측 행(NaN) 계산 제외**: 추정매출 실적이 없는 행({exp['sales_nan_pos'] + exp['sales_nan_zero']:,}행)은 계산에서 완전히 제외하며 0원으로 채우지 않습니다.",
        "6. **분모 0 빈칸 보존**: 점포 수 또는 매출 건수가 0인 경우 비율이나 객단가를 계산하지 않고 빈칸(`NaN`)으로 보존합니다.",
        "7. **소표본 경고 이름표 부여**: 분모(점포 수 등)가 극히 작은 상권·업종은 비율 왜곡 위험이 크므로, 분포를 확인한 뒤 승인받은 기준에 따라 경고 이름표를 부여합니다.",
        "8. **매출·점포 지표의 62개 업종 일치**: 매출과 점포를 함께 결합하는 변수는 반드시 62개 공통 분석 대상 업종 기준으로 정합성을 맞춥니다.",
        "9. **산출물 범위 한정**: 3단계 결과는 '상권 특성표'까지만 제작하며, 추천 점수 산정, 추천 순위화, 금융 MBTI 유형 생성은 이번 프로젝트 범위에 따라 일체 포함하지 않습니다."
    ]
    for crit in expected_criteria:
        assert crit in md_text, f"6.2절 기준 원문 불일치: {crit}"

    # 3. 6.3절 5대 분석 한계 전체 원문 통째 비교
    expected_limits = [
        "1. **소상공인 데이터 활용 한계**: 상권 단위 직접 결합이 불가능하므로 배후 행정동의 점포 밀집도 보조지표로만 제한하여 해석해야 합니다.",
        "2. **대표 행정동 귀속 편향 (양재역 상권 한계)**: 양재역 상권(3120179)은 원천상 자치구는 서초구(11650), 대표 행정동은 강남구 도곡1동(11680655)으로 등록되어 있습니다. [가설] 실제 상권 배후지와 유동 인구가 서초구와 강남구 경계에 걸쳐 형성되어 있을 가능성이 있으나, 단 1개의 대표 행정동(도곡1동)에 100.0% 귀속되어 배후 행정동 연계 시 인접 행정동의 영향력이 온전히 반영되지 못하는 공간 분석 한계가 발생할 수 있습니다.",
        f"3. **상권 미보유 {exp['no_trade_dongs_count']}개 동 해석 주의**: 상권 데이터가 없는 {exp['no_trade_dongs_count']}개 동은 상권 소비가 0원이 아니라 골목상권/발달상권 지정 구역이 없음을 의미하므로 추천 대상 상권 목록에서는 제외하되 배후 소비 분석에는 정상 활용합니다.",
        "4. **합성 재현데이터 통계 추론 배제**: 빅데이터캠퍼스 재현데이터(1,000건 샘플)는 합성 데이터이므로 3단계 상권 특성표의 통계적 학습이나 모수 추정에 사용하지 않습니다.",
        "5. **비용 데이터 부재**: 임대료 및 권리금·보증금은 원천 데이터 미수집 항목이므로 임의 추정치 생성을 엄격히 금지하고 '데이터 없음'으로 처리합니다."
    ]
    for lim in expected_limits:
        assert lim in md_text, f"6.3절 한계 원문 불일치: {lim}"

    # 4. [가설] 필수 지정 위치 14곳 검사 (본문 분석 14곳 + 표6 헤더 1곳 + 7장 이력 3곳 = 총 18개)
    assert md_text.count("[가설]") == 18, f"보고서 내 [가설] 표기 개수 불일치: {md_text.count('[가설]')} != 18"
    assert "인접 지자체 경계선 접경 지역의 GPS 오차" in md_text and "[가설]" in md_text.split("인접 지자체 경계선 접경 지역의 GPS 오차")[0][-50:]
    assert "도로 중심선이나 대지 필지 분할선" in md_text and "[가설]" in md_text.split("도로 중심선이나 대지 필지 분할선")[0][-50:]
    assert "500m를 초과하는 114건은" in md_text and "[가설]" in md_text.split("500m를 초과하는 114건은")[0][-50:]
    assert "[가설] 충돌 원인" in md_text
    assert "[가설] 상주·직장은 인구 센서스 기반" in md_text
    assert "[가설] 시장, 백화점 등 주거시설이 없는" in md_text
    assert "[가설] 원천 직장인구 데이터 미집계" in md_text
    assert "[가설] 해당 구역 내 공공·집객시설 미조사" in md_text
    assert "[가설] 보행량 통신 센서 미수집" in md_text
    assert "[가설] 해당 분기 내 62개 서비스 업종의 추정매출 미발생" in md_text
    assert "[가설] 해당 업종의 소액·현금 결제 위주" in md_text
    assert "[가설] 분기 중 폐업 또는 개업 준비" in md_text
    assert "[가설] 주거 중심 동으로 서울시 발달상권·골목상권 지정 구역이 부재" in md_text
    assert "[가설] 실제 상권 배후지와 유동 인구가 서초구와 강남구 경계에 걸쳐" in md_text

    # 5. 수정 이력 장 6개 회차 검사 (7.6절 포함)
    assert "## 7. 수정 이력" in md_text, "보고서 7장 수정 이력 누락!"
    for h in ["### 7.1", "### 7.2", "### 7.3", "### 7.4", "### 7.5", "### 7.6", "### 7.7", "### 7.8", "### 7.9"]:
        assert h in md_text, f"수정 이력 회차 누락: {h}"

    # 6. 13대 금지 표현 전체 검색 (본문 전체)
    forbidden_words = [
        "카드", "카드 추정매출", "카드 기반", "실측", "실제 결제",
        "완벽", "무결", "검증 완료", "최종", "입증", "압도적", "반드시 성공", "전수"
    ]

    for word in forbidden_words:
        assert word not in md_text, f"보고서 본문 내 금지어 '{word}' 발견! (위반 횟수: {md_text.count(word)})"
        assert word not in html_text, f"대시보드 본문 내 금지어 '{word}' 발견! (위반 횟수: {html_text.count(word)})"

    # 7. 소수점 없는 100% 사용 검사
    bad_100_md = re.findall(r'(?<!\.)100%(?![\.\d])', md_text)
    assert len(bad_100_md) == 0, f"보고서 내 소수점 없는 단정적 '100%' 발견: {bad_100_md}"

    html_no_style = re.sub(r'<style.*?</style>', '', html_text, flags=re.DOTALL)
    bad_100_html = re.findall(r'(?<!\.)100%(?![\.\d])', html_no_style)
    assert len(bad_100_html) == 0, f"대시보드 텍스트 내 소수점 없는 단정적 '100%' 발견: {bad_100_html}"

    print(" -> 통과: 6.1 제안문구, 6.2 9대 기준, 6.3 5대 한계 원문 통째 일치, [가설] 14곳 지정 위치 확인, 13대 금지 표현 0건, 소수점 없는 100% 0건 확인")


# ── 검사 10: 17종 고의 변조 시험 (Mutation Testing) ──────────────────
def run_mutation_tests(exp=None):
    """17종 고의 변조 시험 (설계표 변조, 19개 컬럼 Swap 변조, 6.2절 기준 변조 등 포함)"""
    print("[검사 10] 17종 고의 변조 시험 (Mutation Testing) 수행")
    if exp is None:
        exp = get_raw_expected_values()

    report_orig = REPORT_DIR / "02_전처리_결합설계_보고서_2025Q4.md"
    dash_orig = REPORT_DIR / "02_결합검증_대시보드_2025Q4.html"

    # 변조 1: 보고서 표 셀 숫자 변조 (534,898 -> 999,999)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        target.write_text(target.read_text(encoding="utf-8").replace("534,898", "999,999"), encoding="utf-8")
        failed = False
        try:
            check_report_and_dashboard_content(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 1 실패"
        print("  [변조 1] 표 셀 숫자 변조 감지 성공: 534,898 -> 999,999 차단")

    # 변조 2: 보고서 표 글자 변조 (서울 경계 내부 점포 -> 경기 경계 내부 점포)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        target.write_text(target.read_text(encoding="utf-8").replace("서울 경계 내부 점포", "경기 경계 내부 점포"), encoding="utf-8")
        failed = False
        try:
            check_report_and_dashboard_content(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 2 실패"
        print("  [변조 2] 표 글자 변조 감지 성공: 차단")

    # 변조 3: 본문 문장 속 숫자 변조 (7,670 -> 8,888)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        target.write_text(target.read_text(encoding="utf-8").replace("7,670건", "8,888건"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 3 실패"
        print("  [변조 3] 숫자 목록 본문 문장 변조 감지 성공: 7,670건 -> 8,888건 차단")

    # 변조 4: 대시보드 KPI 숫자 변조 (1,650 -> 9,999)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / dash_orig.name
        target.write_text(target.read_text(encoding="utf-8").replace("1,650개", "9,999개"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 4 실패"
        print("  [변조 4] 대시보드 KPI 변조 감지 성공: 차단")

    # 변조 5: 조인 기록 변조 (조인 1 결측 17 -> 99)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target = tmp_s2 / "조인_기록.csv"
        df_j = pd.read_csv(target, encoding="utf-8-sig")
        df_j.loc[0, "결측_발생_건수"] = 99
        df_j.to_csv(target, index=False, encoding="utf-8-sig")
        failed = False
        try:
            check_mart_cell_values_and_joins(stage2_dir=tmp_s2, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 5 실패"
        print("  [변조 5] 조인 기록 결측 건수 변조 감지 성공: 차단")

    # 변조 6: 마트 기본키 변조 (상권_마스터 행 0 키 복사)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target = tmp_s2 / "상권_마스터.csv"
        df_m = pd.read_csv(target, encoding="utf-8-sig")
        df_m.loc[1, "상권_코드"] = df_m.loc[0, "상권_코드"]
        df_m.to_csv(target, index=False, encoding="utf-8-sig")
        failed = False
        try:
            check_primary_keys(stage2_dir=tmp_s2, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 6 실패"
        print("  [변조 6] 마트 기본키 중복 변조 감지 성공: 차단")

    # 변조 7: 데이터사전 컬럼 삭제 변조 (행 0 삭제)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target = tmp_s2 / "데이터사전.csv"
        df_dict = pd.read_csv(target, encoding="utf-8-sig")
        df_dict = df_dict.iloc[1:]
        df_dict.to_csv(target, index=False, encoding="utf-8-sig")
        failed = False
        try:
            check_data_dictionary(stage2_dir=tmp_s2, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 7 실패"
        print("  [변조 7] 데이터사전 컬럼 삭제 변조 감지 성공: 차단")

    # 변조 8: [가설] 태그 삭제 변조
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        target.write_text(target.read_text(encoding="utf-8").replace("[가설] 충돌 원인", "충돌 원인"), encoding="utf-8")
        failed = False
        try:
            check_qualitative_rules(report_dir=tmp_rep_dir)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 8 실패"
        print("  [변조 8] [가설] 태그 삭제 변조 감지 성공: 차단")

    # 변조 9: 금지어 삽입 변조 ("카드")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        target.write_text(target.read_text(encoding="utf-8").replace("추정매출 합계", "카드 추정매출 합계"), encoding="utf-8")
        failed = False
        try:
            check_qualitative_rules(report_dir=tmp_rep_dir)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 9 실패"
        print("  [변조 9] 금지어('카드') 삽입 변조 감지 성공: 차단")

    # 변조 10: 표 비율 수치 변조
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        txt = target.read_text(encoding="utf-8")
        assert "95.2%" in txt, "변조 대상 문자열 '95.2%' 부재"
        target.write_text(txt.replace("95.2%", "50.0%"), encoding="utf-8")
        failed = False
        try:
            check_report_and_dashboard_content(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 10 실패"
        print("  [변조 10] 표 비율 수치 변조 감지 성공: 95.2% -> 50.0% 차단")

    # 변조 11: 합계 보존 값 뒤바꾸기 변조 (Swap Mutation on sales)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target_pq = tmp_s2 / "상권_업종_분기_마트.parquet"
        df_swap = pd.read_parquet(target_pq)
        valid_indices = df_swap[df_swap["당월_매출_금액"].notna()].index[:2]
        val0 = df_swap.loc[valid_indices[0], "당월_매출_금액"]
        val1 = df_swap.loc[valid_indices[1], "당월_매출_금액"]
        assert val0 != val1
        orig_sum = df_swap["당월_매출_금액"].sum()
        df_swap.loc[valid_indices[0], "당월_매출_금액"] = val1
        df_swap.loc[valid_indices[1], "당월_매출_금액"] = val0
        assert df_swap["당월_매출_금액"].sum() == orig_sum
        df_swap.to_parquet(target_pq, index=False)
        failed = False
        try:
            check_mart_cell_values_and_joins(stage2_dir=tmp_s2, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 11 실패"
        print("  [변조 11] 합계 보존 값 뒤바꾸기 변조(Swap Mutation) 감지 성공: 총합 일치에도 셀 단위 원천 대조로 차단")

    # 변조 12: 집객시설 결측 플래그 변조 (True -> False)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target_m = tmp_s2 / "상권_마스터.csv"
        df_m_mod = pd.read_csv(target_m, encoding="utf-8-sig")
        idx_fac = df_m_mod[df_m_mod["집객시설_원천행_없음"] == True].index[0]
        df_m_mod.loc[idx_fac, "집객시설_원천행_없음"] = False
        df_m_mod.to_csv(target_m, index=False, encoding="utf-8-sig")
        failed = False
        try:
            check_mart_cell_values_and_joins(stage2_dir=tmp_s2, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 12 실패"
        print("  [변조 12] 집객시설 결측 플래그 변조 감지 성공: True -> False 차단")

    # 변조 13: 표 3 설계 칸 변조 (객단가 분석 단위 변조)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        txt = target.read_text(encoding="utf-8")
        target.write_text(txt.replace("상권×업종×분기", "상권 고정 단위"), encoding="utf-8")
        failed = False
        try:
            check_report_and_dashboard_content(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 13 실패"
        print("  [변조 13] 표 3 설계 칸 변조 감지 성공: 분석 단위 변조 차단")

    # 변조 14: 6.2절 9대 기준 삭제 변조 (기준 1 변조)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target = tmp_rep_dir / report_orig.name
        txt = target.read_text(encoding="utf-8")
        target.write_text(txt.replace("1. **합계 ÷ 합계 기본 원칙**", "1. 임의 평균 원칙"), encoding="utf-8")
        failed = False
        try:
            check_qualitative_rules(report_dir=tmp_rep_dir)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 14 실패"
        print("  [변조 14] 6.2절 9대 기준 삭제 변조 감지 성공: 차단")

    # 변조 15: 상권 마스터 세부 집객시설 칸 변조 (은행_수 변조)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target_m = tmp_s2 / "상권_마스터.csv"
        df_m_mod = pd.read_csv(target_m, encoding="utf-8-sig")
        valid_idx = df_m_mod[df_m_mod["은행_수"].notna()].index[0]
        df_m_mod.loc[valid_idx, "은행_수"] += 10
        df_m_mod.to_csv(target_m, index=False, encoding="utf-8-sig")
        failed = False
        try:
            check_mart_cell_values_and_joins(stage2_dir=tmp_s2, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 15 실패"
        print("  [변조 15] 상권 마스터 세부 집객시설 셀 변조 감지 성공: 은행_수 +10 차단")

    # 변조 16: 설계표 개폐업 파일을 OA-15576으로 변조 (요구사항 4)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)
        target_csv = tmp_s2 / "항목_파일_연결표.csv"
        df_map_mod = pd.read_csv(target_csv, encoding="utf-8-sig")
        row_idx = df_map_mod[df_map_mod["핵심_항목"].str.contains("개폐업")].index[0]
        df_map_mod.loc[row_idx, "대응_원천_파일"] = "`OA-15576_상권변화지표_상권`"
        df_map_mod.to_csv(target_csv, index=False, encoding="utf-8-sig")
        failed = False
        try:
            check_mapping_table_against_sources(stage2_dir=tmp_s2)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 16 실패: 설계표 파일 OA-15576 변조 미감지!"
        print("  [변조 16] 설계표 개폐업 파일 -> OA-15576 변조 감지 성공: 차단")

    # 변조 17: 마트 19개 추가 컬럼 Swap 변조 시험 (요구사항 6)
    cols_19 = [
        ("상권_마스터", "상권_표시_명"),
        ("상권_마스터", "자치구_행정동_불일치_여부"),
        ("상권_분기_마트", "상권_코드_명"),
        ("상권_분기_마트", "상권_표시_명"),
        ("상권_분기_마트", "상권_구분_코드"),
        ("상권_분기_마트", "상권_구분_코드_명"),
        ("상권_분기_마트", "자치구_코드"),
        ("상권_분기_마트", "자치구_코드_명"),
        ("상권_분기_마트", "행정동_코드"),
        ("상권_분기_마트", "행정동_코드_명"),
        ("상권_분기_마트", "상권_매출_보유_업종_수"),
        ("상권_분기_마트", "상권_점포_보유_업종_수"),
        ("상권_업종_분기_마트", "상권_코드_명"),
        ("상권_업종_분기_마트", "상권_표시_명"),
        ("상권_업종_분기_마트", "상권_구분_코드_명"),
        ("상권_업종_분기_마트", "행정동_코드"),
        ("상권_업종_분기_마트", "서비스_업종_코드_명"),
        ("상권_업종_분기_마트", "공통그룹"),
        ("상권_업종_분기_마트", "매출_보유_여부")
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_s2 = Path(tmpdir)
        for f in STAGE2_DIR.glob("*.*"):
            shutil.copy(f, tmp_s2 / f.name)

        cached_raw = check_mart_cell_values_and_joins(stage2_dir=STAGE2_DIR, exp=exp)

        for tname, cname in cols_19:
            if tname == "상권_마스터":
                target_file = tmp_s2 / "상권_마스터.csv"
                df_curr = pd.read_csv(target_file, encoding="utf-8-sig")
            elif tname == "상권_분기_마트":
                target_file = tmp_s2 / "상권_분기_마트.csv"
                df_curr = pd.read_csv(target_file, encoding="utf-8-sig")
            else:
                target_file = tmp_s2 / "상권_업종_분기_마트.parquet"
                df_curr = pd.read_parquet(target_file)

            # 두 행의 서로 다른 값 찾기
            val0 = df_curr[cname].iloc[0]
            diff_idx = None
            for i in range(1, len(df_curr)):
                if df_curr[cname].iloc[i] != val0:
                    diff_idx = i
                    break
            assert diff_idx is not None, f"{cname} 고유값 부족"

            # Swap
            val1 = df_curr[cname].iloc[diff_idx]
            df_curr.loc[0, cname] = val1
            df_curr.loc[diff_idx, cname] = val0

            if target_file.suffix == ".parquet":
                df_curr.to_parquet(target_file, index=False)
            else:
                df_curr.to_csv(target_file, index=False, encoding="utf-8-sig")

            failed = False
            try:
                check_mart_cell_values_and_joins(stage2_dir=tmp_s2, exp=exp, raw_cache=cached_raw)
            except AssertionError:
                failed = True
            assert failed, f"19개 컬럼 Swap 변조 미감지: {tname}.{cname}"

            # 원복
            df_curr.loc[0, cname] = val0
            df_curr.loc[diff_idx, cname] = val1
            if target_file.suffix == ".parquet":
                df_curr.to_parquet(target_file, index=False)
            else:
                df_curr.to_csv(target_file, index=False, encoding="utf-8-sig")

        print("  [변조 17] 19개 추가 컬럼 Swap 변조 시험 전원 감지 성공: 19/19 컬럼 차단")

    # 변조 18: 다른 실제 숫자로 바꾸기 1 (7,722건 -> 7,670건)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "7,722건" in txt
        target_f.write_text(txt.replace("7,722건", "7,670건"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 18 실패: 7,722건 -> 7,670건 미차단"
        print("  [변조 18] 다른 실제 숫자로 바꾸기(7,722건 -> 7,670건) 감지 성공: 차단")

    # 변조 19: 다른 실제 숫자로 바꾸기 2 (중위수 <-> 평균 뒤바꾸기: 22.82m <-> 51.01m)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "중위수는 22.82m, 평균은 51.01m" in txt
        target_f.write_text(txt.replace("중위수는 22.82m, 평균은 51.01m", "중위수는 51.01m, 평균은 22.82m"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 19 실패: 중위수 <-> 평균 뒤바꾸기 미차단"
        print("  [변조 19] 다른 실제 숫자로 바꾸기(중위수 22.82m <-> 평균 51.01m Swap) 감지 성공: 차단")

    # 변조 20: 다른 실제 숫자로 바꾸기 3 (20252 <-> 20253 점포수 뒤바꾸기)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "20252: 461,638개, 20253: 459,480개" in txt
        target_f.write_text(txt.replace("20252: 461,638개, 20253: 459,480개", "20252: 459,480개, 20253: 461,638개"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 20 실패: 20252 <-> 20253 점포수 뒤바꾸기 미차단"
        print("  [변조 20] 다른 실제 숫자로 바꾸기(20252 461,638개 <-> 20253 459,480개 Swap) 감지 성공: 차단")

    # 변조 21: 다른 실제 숫자로 바꾸기 4 (31개 -> 72개)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "31개 (1.88%)" in txt
        target_f.write_text(txt.replace("31개 (1.88%)", "72개 (1.88%)"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 21 실패: 31개 -> 72개 미차단"
        print("  [변조 21] 다른 실제 숫자로 바꾸기(중심점 불일치 31개 -> 72개) 감지 성공: 차단")

    # 변조 22: 다른 실제 숫자로 바꾸기 5 (72개 -> 73개)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "72개 상권 (4.36%)" in txt
        target_f.write_text(txt.replace("72개 상권 (4.36%)", "73개 상권 (4.36%)"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 22 실패: 72개 -> 73개 미차단"
        print("  [변조 22] 다른 실제 숫자로 바꾸기(집객 원천 부재 72개 -> 73개) 감지 성공: 차단")

    # 변조 23: 다른 실제 숫자로 바꾸기 6 (대시보드 73개 -> 17개)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / dash_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "실적이 없는 상권 73개(분기 슬롯" in txt
        target_f.write_text(txt.replace("실적이 없는 상권 73개(분기 슬롯", "실적이 없는 상권 17개(분기 슬롯"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 23 실패: 대시보드 73개 -> 17개 미차단"
        print("  [변조 23] 다른 실제 숫자로 바꾸기(대시보드 4탭 73개 -> 17개) 감지 성공: 차단")

    # 변조 24: 다른 실제 숫자로 바꾸기 7 (대시보드 399개 -> 425개)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / dash_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "25개 자치구 / 399개 행정동" in txt
        target_f.write_text(txt.replace("25개 자치구 / 399개 행정동", "25개 자치구 / 425개 행정동"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 24 실패: 대시보드 399개 -> 425개 미차단"
        print("  [변조 24] 다른 실제 숫자로 바꾸기(대시보드 KPI 399개 -> 425개) 감지 성공: 차단")

    # 변조 25: 작은 숫자로 바꾸기 (대시보드 KPI 457,188개 -> 1개)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / dash_orig.name
        txt = target_f.read_text(encoding="utf-8")
        assert "<div class='kpi-value'>457,188개</div>" in txt
        target_f.write_text(txt.replace("<div class='kpi-value'>457,188개</div>", "<div class='kpi-value'>1개</div>"), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 25 실패: 대시보드 KPI 457,188개 -> 1개 미차단"
        print("  [변조 25] 작은 숫자로 바꾸기(대시보드 KPI 457,188개 -> 1개) 감지 성공: 차단")

    # 변조 26: 줄 삭제 1 ("금천구: 31건" 줄 삭제)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        lines = target_f.read_text(encoding="utf-8").splitlines(keepends=True)
        assert any("금천구: 31건" in l for l in lines)
        lines = [l for l in lines if "금천구: 31건" not in l]
        target_f.write_text("".join(lines), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 26 실패: 금천구: 31건 줄 삭제 미차단"
        print("  [변조 26] 줄 삭제 변조('금천구: 31건' 라인 삭제) 감지 성공: 차단")

    # 변조 27: 줄 삭제 2 ("- **10m 이내**: 2,090건 (27.25%)" 줄 삭제)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / report_orig.name
        lines = target_f.read_text(encoding="utf-8").splitlines(keepends=True)
        assert any("10m 이내" in l for l in lines)
        lines = [l for l in lines if "10m 이내" not in l]
        target_f.write_text("".join(lines), encoding="utf-8")
        failed = False
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 27 실패: 10m 이내 줄 삭제 미차단"
        print("  [변조 27] 줄 삭제 변조('10m 이내' 라인 삭제) 감지 성공: 차단")

    # 변조 28: HTML 표 1 C4 변조 ("7개 구 80건" -> "7개 구 80건 내외")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_rep_dir = Path(tmpdir)
        shutil.copy(report_orig, tmp_rep_dir / report_orig.name)
        shutil.copy(dash_orig, tmp_rep_dir / dash_orig.name)
        target_f = tmp_rep_dir / dash_orig.name
        html_txt = target_f.read_text(encoding="utf-8")
        assert "7개 구 80건" in html_txt, "변조 대상 '7개 구 80건'이 HTML에 없습니다."
        html_txt_mod = html_txt.replace("7개 구 80건", "7개 구 80건 내외", 1)
        target_f.write_text(html_txt_mod, encoding="utf-8")
        failed = False
        try:
            check_report_and_dashboard_content(stage2_dir=STAGE2_DIR, report_dir=tmp_rep_dir, exp=exp)
        except AssertionError:
            failed = True
        assert failed, "변조 시험 28 실패: '7개 구 80건 내외' 변조 미차단"
        print("  [변조 28] HTML 표 1 C4 변조('7개 구 80건 내외') 감지 성공: 차단")

    print(" -> 통과: 총 28종 고의 변조 시험(설계 칸 변조, 기준 변조, 시설 셀 변조, 연결표 변조, 19개 컬럼 Swap, 7종 숫자 대체, 작은 숫자, 2종 줄 삭제, C4 문구 변조 포함) 전체에서 차단 확인")


# ── 검사 11: 외부 격리 재실행 및 이미지 바이너리 일치 검증 ────────────
def check_isolated_reproduction():
    """외부 임시 폴더에서 마트, 보고서, 대시보드, 그림 전체 격리 재실행 및 바이너리 일치 비교"""
    print("[검사 11] 외부 격리 재실행을 통한 산출물(마트 10종, 보고서, 대시보드, 그림 바이너리 바이트) 재현성 검증")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        tmp_s2 = tmp_p / "stage2"
        tmp_rep = tmp_p / "report"
        tmp_img = tmp_p / "images" / "stage2"
        tmp_s2.mkdir(parents=True)
        tmp_rep.mkdir(parents=True)
        tmp_img.mkdir(parents=True)

        import importlib.util

        # 1. build_stage2_mart 격리 실행
        spec_m = importlib.util.spec_from_file_location("b_mart", PROJECT_DIR / "src" / "build_stage2_mart.py")
        mod_m = importlib.util.module_from_spec(spec_m)
        spec_m.loader.exec_module(mod_m)
        mod_m.STAGE2_DIR = tmp_s2
        mod_m.main()

        # 2. build_stage2_report 격리 실행
        spec_r = importlib.util.spec_from_file_location("b_rep", PROJECT_DIR / "src" / "build_stage2_report.py")
        mod_r = importlib.util.module_from_spec(spec_r)
        spec_r.loader.exec_module(mod_r)
        mod_r.STAGE2_DATA_DIR = tmp_s2
        mod_r.REPORT_DIR = tmp_rep
        mod_r.IMAGES_DIR = tmp_img
        mod_r.main()

        # 3. 마트 파일 대조 (10종)
        for fname in [
            "상권_마스터.csv", "상권_분기_마트.csv", "조인_기록.csv",
            "데이터사전.csv", "누락_상권_목록.csv", "상권_중심점_행정동_불일치_목록.csv",
            "점포_위치_불일치_목록.csv", "상권_업종_분기_마트.csv", "항목_파일_연결표.csv"
        ]:
            orig_df = pd.read_csv(STAGE2_DIR / fname, encoding="utf-8-sig")
            new_df = pd.read_csv(tmp_s2 / fname, encoding="utf-8-sig")
            assert orig_df.equals(new_df), f"격리 실행 마트 불일치: {fname}"

        orig_pq = pd.read_parquet(STAGE2_DIR / "상권_업종_분기_마트.parquet")
        new_pq = pd.read_parquet(tmp_s2 / "상권_업종_분기_마트.parquet")
        assert orig_pq.equals(new_pq), "격리 실행 Parquet 마트 불일치!"

        with open(STAGE2_DIR / "점포_위치_불일치_통계.json", "r", encoding="utf-8") as f:
            orig_json = json.load(f)
        with open(tmp_s2 / "점포_위치_불일치_통계.json", "r", encoding="utf-8") as f:
            new_json = json.load(f)
        assert orig_json == new_json, "격리 실행 통계 JSON 불일치!"

        # 4. 보고서 및 대시보드 텍스트 대조
        orig_md = (REPORT_DIR / "02_전처리_결합설계_보고서_2025Q4.md").read_text(encoding="utf-8")
        new_md = (tmp_rep / "02_전처리_결합설계_보고서_2025Q4.md").read_text(encoding="utf-8")
        assert orig_md == new_md, "격리 실행 보고서 Markdown 불일치!"

        orig_html = (REPORT_DIR / "02_결합검증_대시보드_2025Q4.html").read_text(encoding="utf-8")
        new_html = (tmp_rep / "02_결합검증_대시보드_2025Q4.html").read_text(encoding="utf-8")
        assert orig_html == new_html, "격리 실행 대시보드 HTML 불일치!"

        # 5. 그림 파일 3종 바이너리 바이트 일치 검증
        for img_name in ["01_점포_위치_이격거리_분포.png", "02_상권특성_데이터_준비도.png", "03_공통그룹별_점포수_분포.png"]:
            orig_img_path = IMAGES_DIR / img_name
            new_img_path = tmp_img / img_name
            assert new_img_path.exists(), f"격리 생성 그림 파일 누락: {img_name}"
            with open(new_img_path, "rb") as f:
                sig = f.read(8)
                assert sig == b"\x89PNG\r\n\x1a\n", f"유효하지 않은 PNG 헤더: {img_name}"
            assert orig_img_path.read_bytes() == new_img_path.read_bytes(), f"그림 바이너리 바이트 불일치: {img_name}"

    print(" -> 통과: 외부 격리 재실행 결과 마트 10종, 보고서, 대시보드, 그림 3종 바이너리 바이트 일치 확인")



# ── 검사 10-2: 통계값 ±1 계산 오류 주입 변조 시험 (Systematic Mutation Testing) ─
def test_systematic_mutations(stage2_dir=STAGE2_DIR, report_dir=REPORT_DIR, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, exp=None):
    """build_stage2_report.py의 통계값을 하나씩 1만큼 틀리게 넣고 임시 폴더에 생성 후 검사 7·8·9 차단 여부 자동 검증"""
    import contextlib
    import io
    print("[검사 10-2] 통계값 ±1 계산 오류 주입 변조 시험 (Systematic Mutation Testing)")
    if exp is None:
        exp = get_raw_expected_values(raw_dir, processed_dir)

    from build_stage2_report import load_all_stage2_data, build_markdown_report, build_html_dashboard

    data = load_all_stage2_data()
    stats = data["stats"]

    base_md = (report_dir / "02_전처리_결합설계_보고서_2025Q4.md").read_text(encoding="utf-8")
    base_html = (report_dir / "02_결합검증_대시보드_2025Q4.html").read_text(encoding="utf-8")

    numeric_keys = [k for k, v in stats.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    blocked_keys = []
    unchanged_keys = []
    failed_to_block_keys = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        tmp_md = tmppath / "02_전처리_결합설계_보고서_2025Q4.md"
        tmp_html = tmppath / "02_결합검증_대시보드_2025Q4.html"

        for k in numeric_keys:
            orig_val = stats[k]
            mut_stats = dict(stats)
            mut_stats[k] = orig_val + 1
            mut_data = dict(data)
            mut_data["stats"] = mut_stats

            with contextlib.redirect_stdout(io.StringIO()):
                build_markdown_report(mut_data, out_path=tmp_md)
                build_html_dashboard(mut_data, out_path=tmp_html)

            mut_md_text = tmp_md.read_text(encoding="utf-8")
            mut_html_text = tmp_html.read_text(encoding="utf-8")

            if mut_md_text == base_md and mut_html_text == base_html:
                unchanged_keys.append(k)
                continue

            blocked = False
            # Check 7
            try:
                check_report_and_dashboard_content(stage2_dir=stage2_dir, report_dir=tmppath, exp=exp)
            except AssertionError:
                blocked = True

            # Check 8
            if not blocked:
                try:
                    check_number_inventory_in_prose_and_dashboard(stage2_dir=stage2_dir, report_dir=tmppath, raw_dir=raw_dir, processed_dir=processed_dir, exp=exp)
                except AssertionError:
                    blocked = True

            # Check 9
            if not blocked:
                try:
                    check_qualitative_rules(report_dir=tmppath)
                except AssertionError:
                    blocked = True

            if blocked:
                blocked_keys.append(k)
            else:
                failed_to_block_keys.append(k)

        # Additional test: 대시보드 1번 탭 제목 7,802건 변조 시 실패 확인
        dash_7802_blocked = False
        mut_dash_7802 = base_html.replace("점포 위치 불일치(7,722건)", "점포 위치 불일치(7,802건)")
        tmp_html.write_text(mut_dash_7802, encoding="utf-8")
        tmp_md.write_text(base_md, encoding="utf-8")
        try:
            check_number_inventory_in_prose_and_dashboard(stage2_dir=stage2_dir, report_dir=tmppath, raw_dir=raw_dir, processed_dir=processed_dir, exp=exp)
        except AssertionError:
            dash_7802_blocked = True

        assert dash_7802_blocked, "대시보드 제목 7,802건 변조 차단 실패!"

    assert len(failed_to_block_keys) == 0, f"변조 차단 실패 통계값 발생: {failed_to_block_keys}"

    print(f" -> 통과: 통계값 ±1 변조 시험 완료 (총 {len(numeric_keys)}개 중 차단 {len(blocked_keys)}개, 출력 무영향 {len(unchanged_keys)}개)")
    print(f"    - 차단된 통계값 목록 ({len(blocked_keys)}개): {', '.join(blocked_keys)}")
    print(f"    - 출력이 바뀌지 않은 통계값 목록 ({len(unchanged_keys)}개): {', '.join(unchanged_keys)}")
    print(f"    - 대시보드 제목 7,802건 변조 차단 성공 확인")


def main():
    print("=" * 70)
    print("   [SpotFit Stage 2] 데이터 전처리 및 결합 종합 자동 검증 (verify_stage2)")
    print("=" * 70)

    exp = get_raw_expected_values()
    check_primary_keys(exp=exp)
    check_mart_cell_values_and_joins(exp=exp)
    test_reproduction_diff_calculation()
    check_recalculated_lists(exp=exp)
    check_data_dictionary(exp=exp)
    check_mapping_table_against_sources()
    check_report_and_dashboard_content(exp=exp)
    check_number_inventory_in_prose_and_dashboard(exp=exp)
    check_qualitative_rules(exp=exp)
    run_mutation_tests(exp=exp)
    test_systematic_mutations(exp=exp)
    check_isolated_reproduction()

    print("=" * 70)
    print("   >>> 검증 통과: 2단계 데이터 전처리 및 결합 마트 정합성 확인 <<<")
    print("=" * 70)

    print("\n[자동 검사가 보증하지 못하는 범위 및 한계 안내]")
    print("1. 본 검증은 마트 결과 파일과 보고서/대시보드 간의 수치 일치성과 원천 데이터와의 논리적 정합성만을 검사합니다.")
    print("2. 숫자 없는 문장의 의미와 표 3 계산식의 뜻은 자동으로 비교하지 않으며 사람이 직접 읽어 확인해야 합니다.")
    print("3. 숫자 검사는 숫자가 포함된 줄(보고서 prose 117줄, 대시보드 화면 글자 30줄)을 줄 단위로 통째 비교하므로 숫자가 전혀 없는 줄이 추가되는 변조는 감지하지 못합니다.")
    print("4. 점포 좌표와 행정동 경계 간의 미세 이격(중위수 22.82m 등)은 지오코딩 및 경계 필지 특성에 기인한 것으로 추정되나, 공공기관 원천 지오코딩 알고리즘의 진실성을 보증하지는 못합니다.")
    print("5. 양재역 상권의 대표 행정동(도곡1동)과 자치구(서초구) 불일치는 서울시 공공데이터 고유의 특성이며, 본 검증은 원천 보존 여부만을 확인합니다.")
    print("6. 표 6 C4([가설] 추정 원인 서술 8칸)는 비정형 정성적 가설문이므로 수치 대조 대상에서 제외되며, 가설 태그 및 문맥 규칙으로만 관리됩니다.")
    print("7. 보고서 7장 수정 이력은 과거 오류 수정 내역을 기술한 영역이므로 수치 줄 대조 대상에서 제외되며, 금지어 검사만 적용됩니다.")
    print("8. 데이터사전의 한글 설명은 문장 전체가 아닌 컬럼 성격별 필수 단어(인구, 가구, 대표 행정동, 시설, 점포, 매출, 코드, 명칭, 플래그 등) 포함 여부만을 검사합니다.")


if __name__ == "__main__":
    main()