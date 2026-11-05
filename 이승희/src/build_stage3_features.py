#!/usr/bin/env python3
"""SpotFit 3단계: 상권 특성 파생변수 산출 파이프라인 (build_stage3_features.py)

규칙:
1. 모든 숫자는 코드로 계산하여 stage3_summary_stats.json 및 결과 파일에 저장한다.
2. 후보의 통계 근거 문구 및 결측 사유 문구에서 하드코딩 숫자(73개, 92개 등)를 완전히 배제한다.
3. 윈저화 및 극단치 기준별 비교 결과를 data/processed/stage3/매출증감률_극단치_민감도.csv로 산출한다.
4. 변수사전.csv에 267개 컬럼 전원에 대해 실제 뜻, 수식, 입력 파일/컬럼, 단위, 결측 규칙, 분모0 규칙을 명시한다.
"""

import sys
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
STAGE2_DIR = DATA_DIR / "processed" / "stage2"
STAGE3_DIR = DATA_DIR / "processed" / "stage3"
STAGE3_DIR.mkdir(parents=True, exist_ok=True)

# 분기 목록
QUARTERS = [20251, 20252, 20253, 20254]
PREV_Q_MAP = {20252: 20251, 20253: 20252, 20254: 20253}


def load_stage2_data():
    """2단계 마트 및 행정동 마스터 로드"""
    print("[1/6] 2단계 마트 데이터 로드 중...")
    df_ind = pd.read_parquet(STAGE2_DIR / "상권_업종_분기_마트.parquet")
    df_q = pd.read_csv(STAGE2_DIR / "상권_분기_마트.csv", encoding="utf-8-sig")
    df_m = pd.read_csv(STAGE2_DIR / "상권_마스터.csv", encoding="utf-8-sig")
    df_dong_m = pd.read_csv(DATA_DIR / "processed" / "행정동_마스터.csv", encoding="utf-8-sig")
    return df_ind, df_q, df_m, df_dong_m


def build_industry_quarterly_features(df_ind, df_m):
    """1. 상권_업종_분기_특성표 생성 (246,197행)"""
    print("[2/6] 상권_업종_분기_특성표 생성 중...")
    df = df_ind.copy()

    # 면적 조인
    df = df.merge(df_m[["상권_코드", "영역_면적_ha"]], on="상권_코드", how="left")

    # 1. 매출 결측 구분
    cond_sales_na = df["당월_매출_금액"].isna()
    cond_store_zero = df["전체_점포_수"] == 0
    df["매출_결측_여부"] = cond_sales_na
    df["매출_결측_구분"] = np.where(
        ~cond_sales_na, "정상 실적",
        np.where(cond_store_zero, "점포 0개", "점포 있음, 추정매출 행 없음")
    )

    # 2. 분기 건당 결제금액 (객단가)
    cond_bill_valid = (df["당월_매출_건수"].notna()) & (df["당월_매출_건수"] > 0)
    df["분기_객단가"] = np.where(cond_bill_valid, df["당월_매출_금액"] / df["당월_매출_건수"], np.nan)
    df["객단가_결측_사유"] = np.where(
        df["분기_객단가"].notna(), "정상 산출",
        np.where(cond_store_zero, "점포 0개",
        np.where(cond_sales_na, "추정매출 실적 부재", "결제건수 0건"))
    )

    # 3. 분기 객단가 백분위 (업종내 / 공통그룹내) - 설계안 공식 rank(method="average", pct=True) * 100 복원
    def calc_pctile(sub_s):
        valid = sub_s.dropna()
        if len(valid) == 0:
            return pd.Series(np.nan, index=sub_s.index)
        pct = valid.rank(ascending=True, method="average", pct=True) * 100.0
        res = pd.Series(np.nan, index=sub_s.index)
        res.loc[valid.index] = pct
        return res

    df["분기_객단가_백분위_업종내"] = df.groupby(["기준_년분기_코드", "서비스_업종_코드"])["분기_객단가"].transform(calc_pctile)
    df["분기_객단가_백분위_공통그룹내"] = df.groupby(["기준_년분기_코드", "공통그룹"])["분기_객단가"].transform(calc_pctile)

    valid_trades_q = df.dropna(subset=["분기_객단가"]).groupby(["기준_년분기_코드", "서비스_업종_코드"])["상권_코드"].transform("nunique")
    df["유효_상권_수"] = df[["기준_년분기_코드", "서비스_업종_코드"]].merge(
        df.dropna(subset=["분기_객단가"]).groupby(["기준_년분기_코드", "서비스_업종_코드"])["상권_코드"].nunique().reset_index(name="유효_상권_수"),
        on=["기준_년분기_코드", "서비스_업종_코드"], how="left"
    )["유효_상권_수"].fillna(0).astype(int)

    # 4. 분기 프랜차이즈 점포 비율
    cond_store_pos = df["전체_점포_수"] > 0
    df["분기_프랜차이즈_점포_비율"] = np.where(cond_store_pos, df["프랜차이즈_점포_수"] / df["전체_점포_수"] * 100.0, np.nan)
    df["프랜차이즈_결측_사유"] = np.where(df["분기_프랜차이즈_점포_비율"].notna(), "정상 산출", "점포수 0개")

    # 5. 분기 개폐업 점포 비율
    df["분기_개업_점포_비율"] = np.where(cond_store_pos, df["개업_점포_수"] / df["전체_점포_수"] * 100.0, np.nan)
    df["분기_폐업_점포_비율"] = np.where(cond_store_pos, df["폐업_점포_수"] / df["전체_점포_수"] * 100.0, np.nan)
    df["개폐업_결측_사유"] = np.where(df["분기_개업_점포_비율"].notna(), "정상 산출", "점포수 0개")

    # 6. 분기 매출 증감률
    df["prev_q"] = df["기준_년분기_코드"].map(PREV_Q_MAP)
    prev_df = df[["상권_코드", "서비스_업종_코드", "기준_년분기_코드", "당월_매출_금액"]].copy()
    prev_df.rename(columns={"기준_년분기_코드": "prev_q", "당월_매출_금액": "당월_매출_금액_prev"}, inplace=True)
    df = df.merge(prev_df, on=["상권_코드", "서비스_업종_코드", "prev_q"], how="left")

    cond_growth_calc = (df["당월_매출_금액_prev"].notna()) & (df["당월_매출_금액_prev"] > 0) & (df["당월_매출_금액"].notna())
    df["분기_매출_증감률"] = np.where(
        cond_growth_calc,
        (df["당월_매출_금액"] - df["당월_매출_금액_prev"]) / df["당월_매출_금액_prev"] * 100.0,
        np.nan
    )
    df["매출증감_결측_사유"] = np.where(
        df["분기_매출_증감률"].notna(), "정상 산출",
        np.where(df["기준_년분기_코드"] == 20251, "전분기 자료 부재(2025Q1)",
        np.where(df["당월_매출_금액_prev"].isna() | (df["당월_매출_금액_prev"] == 0), "직전분기 매출 부재 또는 0원", "당분기 매출 부재"))
    )
    df["매출증감_극단치_플래그"] = (df["분기_매출_증감률"] < -90.0) | (df["분기_매출_증감률"] > 500.0)

    # 7. 분기 점포 밀집도
    df["분기_점포_밀집도_ha"] = df["전체_점포_수"] / df["영역_면적_ha"]

    df.drop(columns=["prev_q", "당월_매출_금액_prev"], inplace=True)
    print(f"  -> 상권_업종_분기_특성표 완료: {len(df):,}행 × {len(df.columns)}열")
    return df


def build_industry_annual_features(df_ind_feat, df_m):
    """2. 상권_업종_연간_특성표 생성 (62,641행)"""
    print("[3/6] 상권_업종_연간_특성표 생성 중...")

    # 연간 집계
    agg_df = df_ind_feat.groupby(["상권_코드", "서비스_업종_코드"]).agg(
        점포_행_보유_분기수=("전체_점포_수", "count"),
        매출_보유_분기수=("당월_매출_금액", lambda s: s.notna().sum()),
        연간_추정매출_금액_합계=("당월_매출_금액", "sum"),
        연간_추정매출_건수_합계=("당월_매출_건수", "sum"),
        점포수합=("전체_점포_수", "sum"),
        프랜차이즈합=("프랜차이즈_점포_수", "sum"),
        연간_개업_점포_수_합계=("개업_점포_수", "sum"),
        연간_폐업_점포_수_합계=("폐업_점포_수", "sum")
    ).reset_index()

    # 상권 및 업종 마스터 메타데이터 결합
    meta = df_ind_feat[["상권_코드", "서비스_업종_코드", "상권_코드_명", "상권_표시_명", "상권_구분_코드_명", "행정동_코드", "서비스_업종_코드_명", "공통그룹", "영역_면적_ha"]].drop_duplicates()
    df = meta.merge(agg_df, on=["상권_코드", "서비스_업종_코드"], how="left")

    # 매출 결측 처리
    df["연간_추정매출_금액_합계"] = np.where(df["매출_보유_분기수"] > 0, df["연간_추정매출_금액_합계"], np.nan)
    df["연간_추정매출_건수_합계"] = np.where(df["매출_보유_분기수"] > 0, df["연간_추정매출_건수_합계"], np.nan)
    df["연간_매출_결측_구분"] = np.where(
        df["매출_보유_분기수"] > 0, "정상 실적",
        "4개분기 매출 실적 부재"
    )

    # 연간 객단가
    cond_valid_bill = (df["연간_추정매출_건수_합계"].notna()) & (df["연간_추정매출_건수_합계"] > 0)
    df["연간_객단가"] = np.where(cond_valid_bill, df["연간_추정매출_금액_합계"] / df["연간_추정매출_건수_합계"], np.nan)
    df["연간_객단가_결측_사유"] = np.where(
        df["연간_객단가"].notna(), "정상 산출",
        "4개분기 매출 실적 부재"
    )

    # 연간 백분위 - 설계안 공식 rank(method="average", pct=True) * 100 복원
    def calc_ann_pctile(sub_s):
        valid = sub_s.dropna()
        if len(valid) == 0:
            return pd.Series(np.nan, index=sub_s.index)
        pct = valid.rank(ascending=True, method="average", pct=True) * 100.0
        res = pd.Series(np.nan, index=sub_s.index)
        res.loc[valid.index] = pct
        return res

    df["연간_객단가_백분위_업종내"] = df.groupby("서비스_업종_코드")["연간_객단가"].transform(calc_ann_pctile)
    df["연간_객단가_백분위_공통그룹내"] = df.groupby("공통그룹")["연간_객단가"].transform(calc_ann_pctile)

    valid_trades_ann = df.dropna(subset=["연간_객단가"]).groupby("서비스_업종_코드")["상권_코드"].nunique().reset_index(name="유효_상권_수")
    df = df.merge(valid_trades_ann, on="서비스_업종_코드", how="left")
    df["유효_상권_수"] = df["유효_상권_수"].fillna(0).astype(int)

    # 연간 평균 전체 점포 수 (합 ÷ 4.0)
    df["연간_평균_전체_점포_수"] = df["점포수합"] / 4.0
    df["연간_평균_프랜차이즈_점포_수"] = df["프랜차이즈합"] / 4.0

    df["연간_프랜차이즈_점포_비율"] = np.where(
        df["점포수합"] > 0,
        df["프랜차이즈합"] / df["점포수합"] * 100.0,
        np.nan
    )
    df["연간_프랜차이즈_결측_사유"] = np.where(df["연간_프랜차이즈_점포_비율"].notna(), "정상 산출", "연간 점포수 0개")

    # 연간 개폐업 점포 비율 (합 ÷ 연간평균점포수 * 100.0)
    cond_ann_pos = df["연간_평균_전체_점포_수"] > 0
    df["연간_개업_점포_비율"] = np.where(
        cond_ann_pos,
        df["연간_개업_점포_수_합계"] / df["연간_평균_전체_점포_수"] * 100.0,
        np.nan
    )
    df["연간_폐업_점포_비율"] = np.where(
        cond_ann_pos,
        df["연간_폐업_점포_수_합계"] / df["연간_평균_전체_점포_수"] * 100.0,
        np.nan
    )
    df["연간_개폐업_결측_사유"] = np.where(df["연간_개업_점포_비율"].notna(), "정상 산출", "연간 평균 점포수 0개")

    # 연간 점포 밀집도
    df["연간_점포_밀집도_ha"] = df["연간_평균_전체_점포_수"] / df["영역_면적_ha"]

    df.drop(columns=["점포수합", "프랜차이즈합"], inplace=True)
    print(f"  -> 상권_업종_연간_특성표 완료: {len(df):,}행 × {len(df.columns)}열")
    return df


def build_trade_quarterly_features(df_q, df_m, df_ind_feat):
    """3. 상권_분기_특성표 생성 (6,600행)"""
    print("[4/6] 상권_분기_특성표 생성 중...")
    df = df_q.copy()
    df = df.merge(df_m[["상권_코드", "영역_면적_ha"]], on="상권_코드", how="left")

    # 1. 상권 매출 결측 사유
    df["상권_당월_매출_금액_합계"] = np.where(df["상권_매출_보유_업종_수"] > 0, df["상권_당월_매출_금액_합계"], np.nan)
    df["상권_당월_매출_건수_합계"] = np.where(df["상권_매출_보유_업종_수"] > 0, df["상권_당월_매출_건수_합계"], np.nan)
    df["상권_매출_결측_사유"] = np.where(df["상권_매출_보유_업종_수"] > 0, "정상 산출", "해당 분기 추정매출 실적 부재")

    # 2. 상권 분기 매출 증감률
    df["prev_q"] = df["기준_년분기_코드"].map(PREV_Q_MAP)
    prev_trade_sales = df[["상권_코드", "기준_년분기_코드", "상권_당월_매출_금액_합계"]].copy()
    prev_trade_sales.rename(columns={"기준_년분기_코드": "prev_q", "상권_당월_매출_금액_합계": "상권_당월_매출_금액_합계_prev"}, inplace=True)
    df = df.merge(prev_trade_sales, on=["상권_코드", "prev_q"], how="left")

    cond_tg = (df["상권_당월_매출_금액_합계_prev"].notna()) & (df["상권_당월_매출_금액_합계_prev"] > 0) & (df["상권_당월_매출_금액_합계"].notna())
    df["상권_분기_매출_증감률"] = np.where(
        cond_tg,
        (df["상권_당월_매출_금액_합계"] - df["상권_당월_매출_금액_합계_prev"]) / df["상권_당월_매출_금액_합계_prev"] * 100.0,
        np.nan
    )
    df["상권_매출증감_결측_사유"] = np.where(
        df["상권_분기_매출_증감률"].notna(), "정상 산출",
        np.where(df["기준_년분기_코드"] == 20251, "전분기 자료 부재(2025Q1)",
        np.where(df["상권_당월_매출_금액_합계_prev"].isna() | (df["상권_당월_매출_금액_합계_prev"] == 0), "직전분기 상권매출 부재 또는 0원", "당분기 상권매출 부재"))
    )
    df["상권_매출증감_극단치_플래그"] = (df["상권_분기_매출_증감률"] < -90.0) | (df["상권_분기_매출_증감률"] > 500.0)

    # 상권 점포 비율
    store_tot = df["상권_전체_점포_수_합계"]
    df["상권_분기_프랜차이즈_점포_비율"] = np.where(store_tot > 0, df["상권_프랜차이즈_점포_수_합계"] / store_tot * 100.0, np.nan)
    df["상권_분기_개업_점포_비율"] = np.where(store_tot > 0, df["상권_개업_점포_수_합계"] / store_tot * 100.0, np.nan)
    df["상권_분기_폐업_점포_비율"] = np.where(store_tot > 0, df["상권_폐업_점포_수_합계"] / store_tot * 100.0, np.nan)
    df["상권_분기_점포_밀집도_ha"] = store_tot / df["영역_면적_ha"]

    # 유동인구 구성비
    flow_base = df["총_유동인구_수"]
    df["유동인구_남성_비율"] = df["남성_유동인구_수"] / flow_base * 100.0
    df["유동인구_여성_비율"] = df["여성_유동인구_수"] / flow_base * 100.0
    for a in [10, 20, 30, 40, 50]:
        df[f"유동인구_{a}대_비율"] = df[f"연령대_{a}_유동인구_수"] / flow_base * 100.0
    df["유동인구_60대이상_비율"] = df["연령대_60_이상_유동인구_수"] / flow_base * 100.0

    for t in ["00_06", "06_11", "11_14", "14_17", "17_21", "21_24"]:
        df[f"유동인구_시간대_{t}_비율"] = df[f"시간대_{t}_유동인구_수"] / flow_base * 100.0

    df["유동인구_주중_비율"] = (df["월요일_유동인구_수"] + df["화요일_유동인구_수"] + df["수요일_유동인구_수"] + df["목요일_유동인구_수"] + df["금요일_유동인구_수"]) / flow_base * 100.0
    df["유동인구_주말_비율"] = (df["토요일_유동인구_수"] + df["일요일_유동인구_수"]) / flow_base * 100.0

    # 복원: 유동인구 요일별 비율 7개 및 유동인구 결측 사유 (총 78열 복원)
    for day in ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]:
        df[f"유동인구_{day}_비율"] = df[f"{day}_유동인구_수"] / flow_base * 100.0
    df["유동인구_결측_사유"] = np.where(df["총_유동인구_수"].notna(), "정상 산출", "원천 미집계")

    df.drop(columns=["prev_q", "상권_당월_매출_금액_합계_prev"], inplace=True)
    print(f"  -> 상권_분기_특성표 완료: {len(df):,}행 × {len(df.columns)}열")
    return df


def build_trade_annual_features(df_m, df_t_q, df_ind_ann, df_dong_m):
    """4. 상권_특성표 생성 (1,650행)"""
    print("[5/6] 상권_특성표 생성 중...")
    df = df_m.copy()

    # 상권 연간 집계
    sales_agg = df_t_q.groupby("상권_코드").agg(
        상권_매출_보유_분기수=("상권_당월_매출_금액_합계", lambda s: s.notna().sum()),
        상권_연간_매출_금액_합계=("상권_당월_매출_금액_합계", "sum"),
        상권_연간_매출_건수_합계=("상권_당월_매출_건수_합계", "sum"),
        상권_점포_보유_분기수=("상권_전체_점포_수_합계", lambda s: s.notna().sum()),
        점포합=("상권_전체_점포_수_합계", "sum"),
        프랜차이즈합=("상권_프랜차이즈_점포_수_합계", "sum"),
        개업합=("상권_개업_점포_수_합계", "sum"),
        폐업합=("상권_폐업_점포_수_합계", "sum"),
        유동인구_보유_분기수=("총_유동인구_수", lambda s: s.notna().sum()),
        유동인구합=("총_유동인구_수", "sum")
    ).reset_index()

    df = df.merge(sales_agg, on="상권_코드", how="left")

    # 상권 연간 매출 결측 규칙
    df["상권_연간_매출_금액_합계"] = np.where(df["상권_매출_보유_분기수"] > 0, df["상권_연간_매출_금액_합계"], np.nan)
    df["상권_연간_매출_건수_합계"] = np.where(df["상권_매출_보유_분기수"] > 0, df["상권_연간_매출_건수_합계"], np.nan)
    df["상권_연간_매출_결측_사유"] = np.where(
        df["상권_매출_보유_분기수"] == 4, "정상 산출",
        np.where(df["상권_매출_보유_분기수"] == 0, "4개분기 전체 매출 부재", "일부 분기 매출 부재")
    )

    # 상권 연간 점포 및 개폐업 종합 (분모: 점포합 ÷ 4.0)
    df["상권_연간_평균_점포_수"] = df["점포합"] / 4.0
    df["상권_연간_프랜차이즈_점포_비율"] = np.where(
        df["점포합"] > 0, df["프랜차이즈합"] / df["점포합"] * 100.0, np.nan
    )
    df["상권_연간_개업_점포_비율"] = np.where(
        df["상권_연간_평균_점포_수"] > 0, df["개업합"] / df["상권_연간_평균_점포_수"] * 100.0, np.nan
    )
    df["상권_연간_폐업_점포_비율"] = np.where(
        df["상권_연간_평균_점포_수"] > 0, df["폐업합"] / df["상권_연간_평균_점포_수"] * 100.0, np.nan
    )
    df["상권_연간_점포_밀집도_ha"] = df["상권_연간_평균_점포_수"] / df["영역_면적_ha"]

    # 상권 연간 유동인구 (존재 분기만 평균)
    df["상권_연간_평균_유동인구_수"] = np.where(
        df["유동인구_보유_분기수"] > 0,
        df["유동인구합"] / df["유동인구_보유_분기수"],
        np.nan
    )
    df["상권_유동인구_결측_사유"] = np.where(df["유동인구_보유_분기수"] > 0, "정상 산출", "원천 유동인구 미집계")

    # 상주인구 구성비
    res_base = df["총_상주인구_수"]
    df["상주인구_결측_사유"] = np.where(res_base.notna(), "정상 산출", "원천 상주인구 미집계")
    df["상주인구_남성_비율"] = df["남성_상주인구_수"] / res_base * 100.0
    df["상주인구_여성_비율"] = df["여성_상주인구_수"] / res_base * 100.0
    for a in [10, 20, 30, 40, 50]:
        df[f"상주인구_{a}대_비율"] = df[f"연령대_{a}_상주인구_수"] / res_base * 100.0
    df["상주인구_60대이상_비율"] = df["연령대_60_이상_상주인구_수"] / res_base * 100.0
    df["상주가구_아파트_비율"] = df["아파트_가구_수"] / df["총_가구_수"] * 100.0
    df["상주가구_비아파트_비율"] = df["비_아파트_가구_수"] / df["총_가구_수"] * 100.0

    # 직장인구 구성비
    wrk_base = df["총_직장_인구_수"]
    df["직장인구_결측_사유"] = np.where(wrk_base.notna(), "정상 산출", "원천 직장인구 미집계")
    df["직장인구_남성_비율"] = df["남성_직장_인구_수"] / wrk_base * 100.0
    df["직장인구_여성_비율"] = df["여성_직장_인구_수"] / wrk_base * 100.0
    for a in [10, 20, 30, 40, 50]:
        df[f"직장인구_{a}대_비율"] = df[f"연령대_{a}_직장_인구_수"] / wrk_base * 100.0
    df["직장인구_60대이상_비율"] = df["연령대_60_이상_직장_인구_수"] / wrk_base * 100.0

    # 상권변화지표 2025Q4 및 변경 횟수
    q4_ind_trade = df_t_q[df_t_q["기준_년분기_코드"] == 20254][["상권_코드", "상권_변화_지표_명", "운영_영업_개월_평균", "폐업_영업_개월_평균"]].copy()
    q4_ind_trade.rename(columns={
        "상권_변화_지표_명": "상권_변화_지표_명_2025Q4",
        "운영_영업_개월_평균": "운영_영업_개월_2025Q4",
        "폐업_영업_개월_평균": "폐업_영업_개월_2025Q4"
    }, inplace=True)
    df = df.merge(q4_ind_trade, on="상권_코드", how="left")

    piv_chg = df_t_q.pivot(index="상권_코드", columns="기준_년분기_코드", values="상권_변화_지표_명")
    chg_cnt = (piv_chg[20252] != piv_chg[20251]).astype(int) + (piv_chg[20253] != piv_chg[20252]).astype(int) + (piv_chg[20254] != piv_chg[20253]).astype(int)
    chg_df = chg_cnt.reset_index(name="상권_변화_지표_변경_횟수")
    df = df.merge(chg_df, on="상권_코드", how="left")

    # 집객시설 결측 사유
    df["집객시설_결측_사유"] = np.where(df["집객시설_원천행_없음"] == True, "원천 집객시설 미집계", "정상 산출")

    # 배후동 소비 결합
    df_dong_sub = df_dong_m[["행정동_코드", "소비_최대항목_비중"]].copy()
    df_dong_sub.rename(columns={"소비_최대항목_비중": "배후동_소비_최대항목_비중"}, inplace=True)
    df = df.merge(df_dong_sub, on="행정동_코드", how="left")

    # 임대료 보증금 수준
    df["상권_임대료_보증금_수준"] = "데이터 없음"

    df.drop(columns=["점포합", "프랜차이즈합", "개업합", "폐업합", "유동인구합"], inplace=True)
    print(f"  -> 상권_특성표 완료: {len(df):,}행 × {len(df.columns)}열")
    return df


def build_sensitivity_and_discussion_files(df_ind, df_q, df_m, df_ind_feat, df_ind_ann, df_t_q, df_t_a):
    """5. 민감도 분석, 소표본 비교표, 윈저화 결과, 요약 통계 JSON 생성"""
    print("[6/6] 민감도 분석 및 부가 산출물 파일 생성 중...")

    # A. 소표본 후보 비교표 (연간 및 분기)
    ann_total = len(df_ind_ann)
    ann_open_100 = df_ind_ann["연간_개업_점포_비율"] >= 100.0
    ann_close_100 = df_ind_ann["연간_폐업_점포_비율"] >= 100.0
    ann_either_100 = ann_open_100 | ann_close_100

    th_records = []
    for label, th, crit_desc in [
        ("후보 1", 1.0, "연간 평균 점포수 1.0개 이하 구간"),
        ("후보 2 (분석가 권고)", 2.0, "연간 평균 점포수 2.0개 이하 구간"),
        ("후보 3", 5.0, "연간 평균 점포수 5.0개 이하 구간")
    ]:
        warn = df_ind_ann["연간_평균_전체_점포_수"] <= th
        non_warn = ~warn
        nw_combos = non_warn.sum()
        th_records.append({
            "후보명": label,
            "분석단위": "상권×업종 연간",
            "임계값": f"연간 평균 점포수 <= {th}개",
            "통계근거": crit_desc,
            "경고대상_조합수": int(warn.sum()),
            "경고_비율_pct": round(warn.sum() / ann_total * 100, 2),
            "영향_상권수": int(df_ind_ann[warn]["상권_코드"].nunique()),
            "영향_업종수": int(df_ind_ann[warn]["서비스_업종_코드"].nunique()),
            "개업이상치_포착건수": int((warn & ann_open_100).sum()),
            "개업이상치_포착률_pct": round((warn & ann_open_100).sum() / ann_open_100.sum() * 100, 2),
            "폐업이상치_포착건수": int((warn & ann_close_100).sum()),
            "폐업이상치_포착률_pct": round((warn & ann_close_100).sum() / ann_close_100.sum() * 100, 2),
            "둘중하나_이상치_포착건수": int((warn & ann_either_100).sum()),
            "둘중하나_이상치_포착률_pct": round((warn & ann_either_100).sum() / ann_either_100.sum() * 100, 2),
            "비경고군_잔여_이상치건수": int((non_warn & ann_either_100).sum()),
            "비경고군_잔여율_전체이상치대비_pct": round((non_warn & ann_either_100).sum() / ann_either_100.sum() * 100, 2),
            "비경고군_잔여율_비경고조합대비_pct": round((non_warn & ann_either_100).sum() / nw_combos * 100, 2)
        })

    q_total = len(df_ind_feat)
    q_open_100 = df_ind_feat["분기_개업_점포_비율"] >= 100.0
    q_close_100 = df_ind_feat["분기_폐업_점포_비율"] >= 100.0
    q_either_100 = q_open_100 | q_close_100

    for label, th, crit_desc in [
        ("분기 후보 1", 1, "분기 점포수 1개 이하 구간"),
        ("분기 후보 2", 2, "분기 점포수 2개 이하 구간"),
        ("분기 후보 3", 5, "분기 점포수 5개 이하 구간")
    ]:
        warn = df_ind_feat["전체_점포_수"] <= th
        non_warn = ~warn
        nw_combos = non_warn.sum()
        th_records.append({
            "후보명": label,
            "분석단위": "상권×업종 분기",
            "임계값": f"분기 점포수 <= {th}개",
            "통계근거": crit_desc,
            "경고대상_조합수": int(warn.sum()),
            "경고_비율_pct": round(warn.sum() / q_total * 100, 2),
            "영향_상권수": int(df_ind_feat[warn]["상권_코드"].nunique()),
            "영향_업종수": int(df_ind_feat[warn]["서비스_업종_코드"].nunique()),
            "개업이상치_포착건수": int((warn & q_open_100).sum()),
            "개업이상치_포착률_pct": round((warn & q_open_100).sum() / q_open_100.sum() * 100, 2),
            "폐업이상치_포착건수": int((warn & q_close_100).sum()),
            "폐업이상치_포착률_pct": round((warn & q_close_100).sum() / q_close_100.sum() * 100, 2),
            "둘중하나_이상치_포착건수": int((warn & q_either_100).sum()),
            "둘중하나_이상치_포착률_pct": round((warn & q_either_100).sum() / q_either_100.sum() * 100, 2),
            "비경고군_잔여_이상치건수": int((non_warn & q_either_100).sum()),
            "비경고군_잔여율_전체이상치대비_pct": round((non_warn & q_either_100).sum() / q_either_100.sum() * 100, 2),
            "비경고군_잔여율_비경고조합대비_pct": round((non_warn & q_either_100).sum() / nw_combos * 100, 2)
        })

    df_th_comp = pd.DataFrame(th_records)
    df_th_comp.to_csv(STAGE3_DIR / "소표본_후보_비교.csv", index=False, encoding="utf-8-sig")

    # B. 민감도 분석 결과 파일 생성 (상권×업종 연간 기준)
    df_sens = df_ind_ann[["상권_코드", "서비스_업종_코드", "상권_표시_명", "서비스_업종_코드_명", "연간_평균_전체_점포_수", "연간_개업_점포_수_합계", "연간_폐업_점포_수_합계", "연간_개업_점포_비율", "연간_폐업_점포_비율"]].copy()

    # 1. 2025Q4 분모 민감도
    q4_stores = df_ind[df_ind["기준_년분기_코드"] == 20254][["상권_코드", "서비스_업종_코드", "전체_점포_수"]].copy()
    q4_stores.rename(columns={"전체_점포_수": "점포수_2025Q4"}, inplace=True)
    df_sens = df_sens.merge(q4_stores, on=["상권_코드", "서비스_업종_코드"], how="left")

    df_sens["연간_개업_점포_비율_Q4분모"] = np.where(
        (df_sens["점포수_2025Q4"].notna()) & (df_sens["점포수_2025Q4"] > 0),
        df_sens["연간_개업_점포_수_합계"] / df_sens["점포수_2025Q4"] * 100.0,
        np.nan
    )
    df_sens["연간_폐업_점포_비율_Q4분모"] = np.where(
        (df_sens["점포수_2025Q4"].notna()) & (df_sens["점포수_2025Q4"] > 0),
        df_sens["연간_폐업_점포_수_합계"] / df_sens["점포수_2025Q4"] * 100.0,
        np.nan
    )
    df_sens["Q4민감도_결측_사유"] = np.where(
        df_sens["연간_개업_점포_비율_Q4분모"].notna(), "정상 산출",
        "2025Q4 점포수 0개 또는 실적 부재"
    )

    # 2. 행 보유 분기만 평균한 점포수 민감도
    store_cnt_series = df_ind.groupby(["상권_코드", "서비스_업종_코드"]).agg(
        행수=("전체_점포_수", "count"),
        점포합=("전체_점포_수", "sum")
    ).reset_index()
    store_cnt_series["연간_평균_점포수_행보유분기만"] = store_cnt_series["점포합"] / store_cnt_series["행수"]
    df_sens = df_sens.merge(store_cnt_series[["상권_코드", "서비스_업종_코드", "연간_평균_점포수_행보유분기만"]], on=["상권_코드", "서비스_업종_코드"], how="left")
    df_sens["연간_개업_점포_비율_행보유분기만"] = np.where(
        df_sens["연간_평균_점포수_행보유분기만"] > 0,
        df_sens["연간_개업_점포_수_합계"] / df_sens["연간_평균_점포수_행보유분기만"] * 100.0,
        np.nan
    )
    df_sens["연간_폐업_점포_비율_행보유분기만"] = np.where(
        df_sens["연간_평균_점포수_행보유분기만"] > 0,
        df_sens["연간_폐업_점포_수_합계"] / df_sens["연간_평균_점포수_행보유분기만"] * 100.0,
        np.nan
    )

    # 3. 소표본 경고 플래그
    df_sens["소표본_후보1_경고_플래그"] = df_sens["연간_평균_전체_점포_수"] <= 1.0
    df_sens["소표본_후보2_경고_플래그"] = df_sens["연간_평균_전체_점포_수"] <= 2.0
    df_sens["소표본_후보3_경고_플래그"] = df_sens["연간_평균_전체_점포_수"] <= 5.0

    df_sens.to_csv(STAGE3_DIR / "민감도_분석_결과.csv", index=False, encoding="utf-8-sig")

    # C. 상권 공통업종 매출 증감률 민감도 파일
    sales_combos = df_ind.dropna(subset=["당월_매출_금액"]).groupby(["상권_코드", "서비스_업종_코드"])["기준_년분기_코드"].nunique()
    combos_4q = sales_combos[sales_combos == 4].index

    df_ind_4q = df_ind.set_index(["상권_코드", "서비스_업종_코드"]).loc[combos_4q].reset_index()
    trade_q_4q = df_ind_4q.groupby(["상권_코드", "기준_년분기_코드"])["당월_매출_금액"].sum().reset_index()
    trade_q_4q.rename(columns={"당월_매출_금액": "상권_공통업종_매출합계"}, inplace=True)

    sens_trade_growth = df_t_q[["상권_코드", "기준_년분기_코드", "상권_표시_명", "상권_당월_매출_금액_합계", "상권_분기_매출_증감률"]].merge(
        trade_q_4q, on=["상권_코드", "기준_년분기_코드"], how="left"
    )
    sens_trade_growth["prev_q"] = sens_trade_growth["기준_년분기_코드"].map(PREV_Q_MAP)
    prev_g = sens_trade_growth[["상권_코드", "기준_년분기_코드", "상권_공통업종_매출합계"]].copy()
    prev_g.rename(columns={"기준_년분기_코드": "prev_q", "상권_공통업종_매출합계": "상권_공통업종_매출합계_prev"}, inplace=True)
    sens_trade_growth = sens_trade_growth.merge(prev_g, on=["상권_코드", "prev_q"], how="left")

    cond_cg = (sens_trade_growth["상권_공통업종_매출합계_prev"].notna()) & (sens_trade_growth["상권_공통업종_매출합계_prev"] > 0) & (sens_trade_growth["상권_공통업종_매출합계"].notna())
    sens_trade_growth["상권_공통업종_매출_증감률"] = np.where(
        cond_cg,
        (sens_trade_growth["상권_공통업종_매출합계"] - sens_trade_growth["상권_공통업종_매출합계_prev"]) / sens_trade_growth["상권_공통업종_매출합계_prev"] * 100.0,
        np.nan
    )
    sens_trade_growth["공통증감_결측_사유"] = np.where(
        sens_trade_growth["상권_공통업종_매출_증감률"].notna(), "정상 산출",
        np.where(sens_trade_growth["기준_년분기_코드"] == 20251, "전분기 자료 부재(2025Q1)",
        np.where(sens_trade_growth["상권_공통업종_매출합계"].isna(), "4개분기 공통 매출 업종 부재", "비교 분기 매출 결측 또는 0원"))
    )
    sens_trade_growth.drop(columns=["prev_q", "상권_공통업종_매출합계_prev"], inplace=True)
    sens_trade_growth.to_csv(STAGE3_DIR / "상권_공통업종_매출증감률_민감도.csv", index=False, encoding="utf-8-sig")

    # D. 매출증감률 극단치 기준별 비교 및 윈저화 민감도 파일
    growth_s = df_ind_feat["분기_매출_증감률"].dropna()
    p5_val = round(float(growth_s.quantile(0.05)), 1)
    p95_val = round(float(growth_s.quantile(0.95)), 1)
    p1_val = round(float(growth_s.quantile(0.01)), 1)
    p99_val = round(float(growth_s.quantile(0.99)), 1)

    growth_sens = df_ind_feat[["상권_코드", "서비스_업종_코드", "기준_년분기_코드", "분기_매출_증감률", "매출증감_결측_사유"]].copy()
    growth_sens["매출증감_극단치_플래그_90_500"] = (growth_sens["분기_매출_증감률"] < -90.0) | (growth_sens["분기_매출_증감률"] > 500.0)
    growth_sens["매출증감_극단치_플래그_p5_p95"] = (growth_sens["분기_매출_증감률"] < p5_val) | (growth_sens["분기_매출_증감률"] > p95_val)
    growth_sens["매출증감_극단치_플래그_p1_p99"] = (growth_sens["분기_매출_증감률"] < p1_val) | (growth_sens["분기_매출_증감률"] > p99_val)
    growth_sens["분기_매출_증감률_윈저화_p5_p95"] = growth_sens["분기_매출_증감률"].clip(lower=p5_val, upper=p95_val)
    growth_sens.to_csv(STAGE3_DIR / "매출증감률_극단치_민감도.csv", index=False, encoding="utf-8-sig")

    # E. 종합 통계 JSON (전 수치 동적 계산)
    valid_ind_counts = df_ind_ann.dropna(subset=["연간_객단가"]).groupby(["서비스_업종_코드", "서비스_업종_코드_명"])["상권_코드"].nunique().reset_index(name="유효상권수")
    
    ind_under_30 = valid_ind_counts[valid_ind_counts["유효상권수"] < 30]["서비스_업종_코드_명"].tolist()
    ind_under_50 = valid_ind_counts[valid_ind_counts["유효상권수"] < 50]["서비스_업종_코드_명"].tolist()
    ind_under_100 = valid_ind_counts[valid_ind_counts["유효상권수"] < 100]["서비스_업종_코드_명"].tolist()
    ind_under_200 = valid_ind_counts[valid_ind_counts["유효상권수"] < 200]["서비스_업종_코드_명"].tolist()

    sales_q_counts = df_t_q.groupby("상권_코드")["상권_당월_매출_금액_합계"].count()
    flow_q_counts = df_t_q.dropna(subset=["총_유동인구_수"]).groupby("상권_코드")["기준_년분기_코드"].count()
    partial_flow_trades = flow_q_counts[flow_q_counts < 4].index.tolist()

    # 유동인구 일부 상권 2개 동적 상세 정보 (3110946, 3111002)
    flow_part_df = df_t_q[df_t_q["상권_코드"].isin(partial_flow_trades)].groupby("상권_코드").agg(
        cnt=("총_유동인구_수", lambda s: s.notna().sum()),
        mean_flow=("총_유동인구_수", "mean")
    ).reset_index().merge(df_m[["상권_코드", "상권_코드_명", "자치구_코드_명", "행정동_코드_명"]], on="상권_코드")
    flow_part_details = []
    for _, r in flow_part_df.iterrows():
        flow_part_details.append({
            "code": int(r["상권_코드"]),
            "name": str(r["상권_코드_명"]),
            "gu": str(r["자치구_코드_명"]),
            "dong": str(r["행정동_코드_명"]),
            "quarters": int(r["cnt"]),
            "mean_flow": round(float(r["mean_flow"]), 1)
        })

    # 방안 B 대상 건수 계산 (연간평균점포수 <= 2.0인 조합에 속한 분기 행 수)
    cand2_keys = set(df_ind_ann[df_ind_ann["연간_평균_전체_점포_수"] <= 2.0][["상권_코드", "서비스_업종_코드"]].itertuples(index=False, name=None))
    q_keys = list(df_ind_feat[["상권_코드", "서비스_업종_코드"]].itertuples(index=False, name=None))
    plan_b_rows_cnt = sum(1 for k in q_keys if k in cand2_keys)

    # 비중 컬럼 개수 집계
    flow_ratio_cols_cnt = len([c for c in df_t_q.columns if "유동인구_" in c and "_비율" in c])
    res_ratio_cols_cnt = len([c for c in df_t_a.columns if "상주" in c and "비율" in c])
    work_ratio_cols_cnt = len([c for c in df_t_a.columns if "직장" in c and "비율" in c])

    # 집객시설 원천 행/상권 큼/같음 비율 동적 계산
    raw_fac_file = DATA_DIR / "raw" / "상권" / "OA-15580_집객시설_상권.csv"
    try:
        raw_fac_df = pd.read_csv(raw_fac_file, encoding="utf-8-sig")
    except Exception:
        raw_fac_df = pd.read_csv(raw_fac_file, encoding="cp949")
    exclude_fac_cols = ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명", "집객시설_수"]
    sub_fac_cols = [c for c in raw_fac_df.columns if c not in exclude_fac_cols]
    raw_fac_df["sub_sum"] = raw_fac_df[sub_fac_cols].fillna(0).sum(axis=1)
    fac_row_gt = int((raw_fac_df["집객시설_수"] > raw_fac_df["sub_sum"]).sum())
    fac_row_eq = int((raw_fac_df["집객시설_수"] == raw_fac_df["sub_sum"]).sum())
    fac_row_tot = int(len(raw_fac_df))
    fac_trade_agg = raw_fac_df.groupby("상권_코드").agg(tot=("집객시설_수", "first"), sub=("sub_sum", "first"))
    fac_trade_gt = int((fac_trade_agg["tot"] > fac_trade_agg["sub"]).sum())
    fac_trade_eq = int((fac_trade_agg["tot"] == fac_trade_agg["sub"]).sum())
    fac_trade_tot = int(len(fac_trade_agg))

    # 증감률 기준 2, 3 건수 (반올림 전 vs 반올림 1자리)
    p5_raw = float(growth_s.quantile(0.05))
    p95_raw = float(growth_s.quantile(0.95))
    p1_raw = float(growth_s.quantile(0.01))
    p99_raw = float(growth_s.quantile(0.99))
    c2_low_raw = int((growth_s < p5_raw).sum())
    c2_high_raw = int((growth_s > p95_raw).sum())
    c3_low_raw = int((growth_s < p1_raw).sum())
    c3_high_raw = int((growth_s > p99_raw).sum())

    c2_low_round = int((growth_s < p5_val).sum())
    c2_high_round = int((growth_s > p95_val).sum())
    c3_low_round = int((growth_s < p1_val).sum())
    c3_high_round = int((growth_s > p99_val).sum())

    diff_growth = (sens_trade_growth["상권_분기_매출_증감률"] - sens_trade_growth["상권_공통업종_매출_증감률"]).dropna()

    summary_stats = {
        "ind_quarterly_rows": int(len(df_ind_feat)),
        "ind_annual_rows": int(len(df_ind_ann)),
        "trade_quarterly_rows": int(len(df_t_q)),
        "trade_annual_rows": int(len(df_m)),
        "unique_trade_ind_combos": int(len(df_ind_ann)),
        "annual_sales_missing_combos": int(df_ind_ann["연간_추정매출_금액_합계"].isna().sum()),
        "valid_ind_count_under_30": int(len(ind_under_30)),
        "valid_ind_count_under_50": int(len(ind_under_50)),
        "valid_ind_count_under_100": int(len(ind_under_100)),
        "valid_ind_count_under_200": int(len(ind_under_200)),
        "valid_ind_examples_under_30": ind_under_30,
        "valid_ind_examples_under_50": ind_under_50,
        "valid_ind_examples_under_100": ind_under_100,
        "valid_ind_examples_under_200": ind_under_200,
        "outlier_dong_trades_count": int(df_m[df_m["배후동_소비_이상치"] == True]["상권_코드"].nunique()),
        "outlier_trades_by_dong": df_m[df_m["배후동_소비_이상치"] == True].groupby("행정동_코드_명")["상권_코드"].nunique().to_dict(),
        "all_missing_sales_trades": int((sales_q_counts == 0).sum()),
        "partial_missing_sales_trades": int(((sales_q_counts > 0) & (sales_q_counts < 4)).sum()),
        "all_4q_sales_trades": int((sales_q_counts == 4).sum()),
        "flow_4q_trades": int((flow_q_counts == 4).sum()),
        "flow_partial_trades": int((flow_q_counts < 4).sum()),
        "flow_partial_trade_codes": partial_flow_trades,
        "flow_partial_details": flow_part_details,
        "ratio_counts": {
            "flow": flow_ratio_cols_cnt,
            "resident": res_ratio_cols_cnt,
            "work": work_ratio_cols_cnt
        },
        "plan_b_rows": plan_b_rows_cnt,
        "plan_b_pct": round(float(plan_b_rows_cnt / len(df_ind_feat) * 100), 2),
        "facilities_stats": {
            "row_gt_cnt": fac_row_gt,
            "row_gt_pct": round(float(fac_row_gt / fac_row_tot * 100), 2),
            "row_eq_cnt": fac_row_eq,
            "row_eq_pct": round(float(fac_row_eq / fac_row_tot * 100), 2),
            "row_tot": fac_row_tot,
            "trade_gt_cnt": fac_trade_gt,
            "trade_gt_pct": round(float(fac_trade_gt / fac_trade_tot * 100), 2),
            "trade_eq_cnt": fac_trade_eq,
            "trade_eq_pct": round(float(fac_trade_eq / fac_trade_tot * 100), 2),
            "trade_tot": fac_trade_tot
        },
        "missing_trades": {
            "work": int(df_m["총_직장_인구_수"].isna().sum()),
            "resident": int(df_m["총_상주인구_수"].isna().sum()),
            "facilities": int(df_m["집객시설_원천행_없음"].sum())
        },
        "growth_criteria_counts": {
            "crit2_low": c2_low_round,
            "crit2_high": c2_high_round,
            "crit3_low": c3_low_round,
            "crit3_high": c3_high_round
        },
        "growth_boundary_counts": {
            "crit2_raw_low": c2_low_raw,
            "crit2_raw_high": c2_high_raw,
            "crit3_raw_low": c3_low_raw,
            "crit3_raw_high": c3_high_raw,
            "crit2_low": c2_low_round,
            "crit2_high": c2_high_round,
            "crit3_low": c3_low_round,
            "crit3_high": c3_high_round
        },
        "no_common_ind_trades": int(len(set(df_m["상권_코드"]) - set(combos_4q.get_level_values(0)))),
        "growth_diff_mean_pctp": round(float(diff_growth.abs().mean()), 2),
        "growth_diff_median_pctp": round(float(diff_growth.abs().median()), 2),
        "q_stores_th1_rows": int((df_ind_feat["전체_점포_수"] <= 1).sum()),
        "q_stores_th1_pct": round(float((df_ind_feat["전체_점포_수"] <= 1).mean() * 100), 2),
        "q_stores_th2_rows": int((df_ind_feat["전체_점포_수"] <= 2).sum()),
        "q_stores_th2_pct": round(float((df_ind_feat["전체_점포_수"] <= 2).mean() * 100), 2),
        "q_stores_th3_rows": int((df_ind_feat["전체_점포_수"] <= 5).sum()),
        "q_stores_th3_pct": round(float((df_ind_feat["전체_점포_수"] <= 5).mean() * 100), 2),
        "ann_stores_th1_combos": int((df_ind_ann["연간_평균_전체_점포_수"] <= 1.0).sum()),
        "ann_stores_th1_pct": round(float((df_ind_ann["연간_평균_전체_점포_수"] <= 1.0).mean() * 100), 2),
        "ann_stores_th2_combos": int((df_ind_ann["연간_평균_전체_점포_수"] <= 2.0).sum()),
        "ann_stores_th2_pct": round(float((df_ind_ann["연간_평균_전체_점포_수"] <= 2.0).mean() * 100), 2),
        "ann_stores_th3_combos": int((df_ind_ann["연간_평균_전체_점포_수"] <= 5.0).sum()),
        "ann_stores_th3_pct": round(float((df_ind_ann["연간_평균_전체_점포_수"] <= 5.0).mean() * 100), 2),
        "ann_either_100_total": int(ann_either_100.sum()),
        "ann_open_100_total": int(ann_open_100.sum()),
        "ann_close_100_total": int(ann_close_100.sum()),
        "th2_capture_count": int(((df_ind_ann["연간_평균_전체_점포_수"] <= 2.0) & ann_either_100).sum()),
        "th2_capture_pct": round(float(((df_ind_ann["연간_평균_전체_점포_수"] <= 2.0) & ann_either_100).sum() / ann_either_100.sum() * 100), 2),
        "th2_nonwarn_remain_count": int(((df_ind_ann["연간_평균_전체_점포_수"] > 2.0) & ann_either_100).sum()),
        "th2_nonwarn_remain_pct_of_either": round(float(((df_ind_ann["연간_평균_전체_점포_수"] > 2.0) & ann_either_100).sum() / ann_either_100.sum() * 100), 2),
        "th2_nonwarn_remain_pct_of_nonwarn": round(float(((df_ind_ann["연간_평균_전체_점포_수"] > 2.0) & ann_either_100).sum() / (df_ind_ann["연간_평균_전체_점포_수"] > 2.0).sum() * 100), 2),
        "growth_median": round(float(growth_s.median()), 2),
        "growth_p5": p5_val,
        "growth_p25": round(float(growth_s.quantile(0.25)), 2),
        "growth_p75": round(float(growth_s.quantile(0.75)), 2),
        "growth_p95": p95_val,
        "growth_p1": p1_val,
        "growth_p99": p99_val,
        "growth_extreme_low_rows": int((growth_s < -90.0).sum()),
        "growth_extreme_high_rows": int((growth_s > 500.0).sum()),
        "growth_winsor_p5_p95_mean": round(float(growth_sens["분기_매출_증감률_윈저화_p5_p95"].mean()), 2),
        "growth_raw_mean": round(float(growth_s.mean()), 2),
        "growth_raw_std": round(float(growth_s.std()), 2),
        "growth_winsor_std": round(float(growth_sens["분기_매출_증감률_윈저화_p5_p95"].std()), 2),
        "change_indicator_q4": df_t_q[df_t_q["기준_년분기_코드"] == 20254]["상권_변화_지표_명"].value_counts().to_dict(),
        "change_counts": df_t_a["상권_변화_지표_변경_횟수"].value_counts().rename(lambda x: f"{x}회").to_dict(),
        "operating_months_q4_median": round(float(df_t_q[df_t_q["기준_년분기_코드"] == 20254]["운영_영업_개월_평균"].median()), 1),
        "closed_months_q4_median": round(float(df_t_q[df_t_q["기준_년분기_코드"] == 20254]["폐업_영업_개월_평균"].median()), 1)
    }

    with open(STAGE3_DIR / "stage3_summary_stats.json", "w", encoding="utf-8") as f:
        json.dump(summary_stats, f, ensure_ascii=False, indent=2)

    print("  -> 민감도 및 요약 통계 저장 완료")


def build_variable_dictionary(df_ind_f, df_ind_a, df_t_q, df_t_a):
    """6. 4개 특성표 전 267개 컬럼에 대한 실제 뜻, 수식, 입력파일/컬럼, 단위, 결측규칙, 분모0규칙 명시"""
    print("변수사전.csv 생성 중...")
    fac_missing_cnt = int(df_t_a["집객시설_원천행_없음"].sum())
    outlier_dong_cnt = int((df_t_a["배후동_소비_이상치"] == True).sum())

    # 서울시 공공 모델 4대 상권변화지표 원천 평균 컬럼 기준 일치율 계산
    raw_change_p = DATA_DIR / "raw" / "상권" / "OA-15576_상권변화지표_상권.csv"
    try:
        df_rc = pd.read_csv(raw_change_p, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df_rc = pd.read_csv(raw_change_p, encoding="cp949")
    op_h = df_rc["운영_영업_개월_평균"] > df_rc["서울_운영_영업_개월_평균"]
    cl_h = df_rc["폐업_영업_개월_평균"] > df_rc["서울_폐업_영업_개월_평균"]
    pred_types = pd.Series(index=df_rc.index, dtype=str)
    pred_types[op_h & cl_h] = "정체"
    pred_types[(~op_h) & cl_h] = "상권확장"
    pred_types[(~op_h) & (~cl_h)] = "다이나믹"
    pred_types[op_h & (~cl_h)] = "상권축소"
    match_change_cnt = int((pred_types == df_rc["상권_변화_지표_명"]).sum())
    total_change_cnt = len(df_rc)
    change_match_pct = round(match_change_cnt / total_change_cnt * 100.0, 1)
    change_desc_stat = f", 원천 평균 컬럼 기준 일치 {match_change_cnt:,}/{total_change_cnt:,}행({change_match_pct:.1f}%))"

    tables = [
        ("상권_업종_분기_특성표", df_ind_f),
        ("상권_업종_연간_특성표", df_ind_a),
        ("상권_분기_특성표", df_t_q),
        ("상권_특성표", df_t_a)
    ]

    def get_column_metadata(table_name, col, dtype):
        """267개 컬럼에 대한 실제 메타데이터 매핑 (규칙 전원 준수)"""
        # 1. 상권_업종_분기_특성표
        if table_name == "상권_업종_분기_특성표":
            if col == "기준_년분기_코드":
                return {"한글_설명": "분석 기준 연도와 분기 (YYYYQ)", "수식": "원천 기준_년분기_코드 적재", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "기준_년분기_코드", "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_코드", "행정동_코드", "서비스_업종_코드"]:
                return {"한글_설명": f"{col.replace('_코드', '')} 표준 행정/식별 코드", "수식": f"원천 {col} 적재", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": col, "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_코드_명", "상권_표시_명", "상권_구분_코드_명", "서비스_업종_코드_명", "공통그룹"]:
                return {"한글_설명": f"{col.replace('_명', '').replace('_코드', '')} 한글 명칭", "수식": f"원천 {col} 적재", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": col, "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "매출_보유_여부":
                return {"한글_설명": "해당 분기 추정매출 실적 존재 여부", "수식": "당월_매출_금액.notna() 판정", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif col == "당월_매출_금액":
                return {"한글_설명": "해당 분기에 발생한 추정매출 총액", "수식": "원천 당월_매출_금액 적재", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액", "단위": "원", "결측치_처리_규칙": "추정매출 미집계 상권 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "당월_매출_건수":
                return {"한글_설명": "해당 분기에 발생한 추정 결제 총건수", "수식": "원천 당월_매출_건수 적재", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_건수", "단위": "건", "결측치_처리_규칙": "추정매출 미집계 상권 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col in ["전체_점포_수", "일반_점포_수", "프랜차이즈_점포_수", "개업_점포_수", "폐업_점포_수"]:
                return {"한글_설명": f"해당 분기 {col.replace('_수', '')} 개수", "수식": f"원천 {col} 적재", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": col, "단위": "개", "결측치_처리_규칙": "결측시 0개 간주", "분모0_처리_규칙": "해당 없음"}
            elif col == "영역_면적_ha":
                return {"한글_설명": "상권 구역 전체 면적 (헥타르)", "수식": "상권_마스터.csv 영역_면적_ha 1:1 결합", "입력_파일": "상권_마스터.csv", "입력_컬럼": "영역_면적_ha", "단위": "ha", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "매출_결측_여부":
                return {"한글_설명": "해당 분기 추정매출 실적 결측 여부", "수식": "당월_매출_금액.isna() 판정", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif col == "매출_결측_구분":
                return {"한글_설명": "매출 실적 유무 및 결측 상태 세부 사유", "수식": "당월_매출_금액 및 전체_점포_수 상태 조건 판정 (정상 실적 / 점포 있음, 추정매출 행 없음 / 점포 0개)", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액, 전체_점포_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "분기_객단가":
                return {"한글_설명": "해당 분기 1회 결제당 평균 결제금액", "수식": "당월_매출_금액 ÷ 당월_매출_건수", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "원", "결측치_처리_규칙": "매출 또는 건수 부재시 NaN 보존", "분모0_처리_규칙": "결제건수 0건인 경우 NaN 보존"}
            elif col == "객단가_결측_사유":
                return {"한글_설명": "분기 객단가 산출 또는 결측 상태 사유 (정상 산출 / 점포 0개 / 추정매출 실적 부재)", "수식": "당월_매출_금액, 당월_매출_건수, 전체_점포_수 상태 조건 판정 (정상 산출 / 점포 0개 / 추정매출 실적 부재)", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액, 당월_매출_건수, 전체_점포_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "분기_객단가_백분위_업종내":
                return {"한글_설명": "동일 서비스 업종 내 분기 객단가 백분위 (0 초과 100 이하)", "수식": "동일 년분기 및 서비스업종 내 분기_객단가 rank(method='average', pct=True) * 100.0", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "%", "결측치_처리_규칙": "분기 객단가 결측시 NaN 보존", "분모0_처리_규칙": "유효 상권수 0개시 NaN 보존"}
            elif col == "분기_객단가_백분위_공통그룹내":
                return {"한글_설명": "동일 공통그룹 내 분기 객단가 백분위 (0 초과 100 이하)", "수식": "동일 년분기 및 공통그룹 내 분기_객단가 rank(method='average', pct=True) * 100.0", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "%", "결측치_처리_규칙": "분기 객단가 결측시 NaN 보존", "분모0_처리_규칙": "유효 상권수 0개시 NaN 보존"}
            elif col == "유효_상권_수":
                return {"한글_설명": "동일 업종 내 분기 객단가 실적이 존재하는 서울시 상권 수", "수식": "동일 년분기 및 서비스업종 내 객단가 유효 행 수 집계 (count)", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "개", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "분기_프랜차이즈_점포_비율":
                return {"한글_설명": "전체 점포 수 중 프랜차이즈 가맹 점포 비율", "수식": "프랜차이즈_점포_수 ÷ 전체_점포_수 × 100.0", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "프랜차이즈_점포_수, 전체_점포_수", "단위": "%", "결측치_처리_규칙": "점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(전체 점포수) 0인 경우 NaN 보존"}
            elif col == "프랜차이즈_결측_사유":
                return {"한글_설명": "프랜차이즈 점포 비율 산출 또는 결측 사유", "수식": "전체_점포_수 상태 조건 판정 (정상 산출 / 점포수 0개)", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "전체_점포_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "분기_개업_점포_비율":
                return {"한글_설명": "전체 점포 수 대비 분기 신규 개업 점포 비율 (개업률)", "수식": "개업_점포_수 ÷ 전체_점포_수 × 100.0", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "개업_점포_수, 전체_점포_수", "단위": "%", "결측치_처리_규칙": "점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(전체 점포수) 0인 경우 NaN 보존"}
            elif col == "분기_폐업_점포_비율":
                return {"한글_설명": "전체 점포 수 대비 분기 폐업 점포 비율 (폐업률)", "수식": "폐업_점포_수 ÷ 전체_점포_수 × 100.0", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "폐업_점포_수, 전체_점포_수", "단위": "%", "결측치_처리_규칙": "점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(전체 점포수) 0인 경우 NaN 보존"}
            elif col == "개폐업_결측_사유":
                return {"한글_설명": "분기 개폐업 점포 비율 산출 또는 결측 사유", "수식": "전체_점포_수 상태 조건 판정 (정상 산출 / 점포수 0개)", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "전체_점포_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "분기_매출_증감률":
                return {"한글_설명": "직전 분기 대비 당분기 매출 변동 비율", "수식": "(당분기 매출 - 직전분기 매출) ÷ 직전분기 매출 × 100.0", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액", "단위": "%", "결측치_처리_규칙": "직전분기 매출 부재 또는 당분기 매출 부재시 NaN 보존", "분모0_처리_규칙": "직전분기 매출 0원 또는 부재시 NaN 보존"}
            elif col == "매출증감_결측_사유":
                return {"한글_설명": "분기 매출 증감률 산출 또는 결측 사유", "수식": "직전분기 및 당분기 매출 상태 조건 판정 (정상 산출 / 전분기 자료 부재(2025Q1) / 직전분기 매출 부재 또는 0원 / 당분기 매출 부재)", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "매출증감_극단치_플래그":
                return {"한글_설명": "분기 매출 증감률 극단치 (증감률 < -90.0% 또는 > +500.0%) 여부", "수식": "분기_매출_증감률 < -90.0% 또는 분기_매출_증감률 > 500.0% 판정", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "당월_매출_금액", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif col == "분기_점포_밀집도_ha":
                return {"한글_설명": "상권 구역 면적(ha)당 해당 업종 점포 수", "수식": "전체_점포_수 ÷ 영역_면적_ha", "입력_파일": "상권_업종_분기_마트.parquet", "입력_컬럼": "전체_점포_수", "단위": "개/ha", "결측치_처리_규칙": "면적 부재시 NaN 보존", "분모0_처리_규칙": "분모(영역 면적) 0인 경우 NaN 보존"}

        # 2. 상권_업종_연간_특성표
        elif table_name == "상권_업종_연간_특성표":
            if col in ["상권_코드", "서비스_업종_코드", "행정동_코드"]:
                return {"한글_설명": f"{col.replace('_코드', '')} 표준 행정/식별 코드", "수식": f"원천 {col} 적재", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": col, "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_코드_명", "상권_표시_명", "상권_구분_코드_명", "서비스_업종_코드_명", "공통그룹"]:
                return {"한글_설명": f"{col.replace('_명', '').replace('_코드', '')} 한글 명칭", "수식": f"원천 {col} 적재", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": col, "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "영역_면적_ha":
                return {"한글_설명": "상권 구역 전체 면적 (헥타르)", "수식": "상권_업종_분기_특성표.csv 영역_면적_ha 적재", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "영역_면적_ha", "단위": "ha", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "점포_행_보유_분기수":
                return {"한글_설명": "2025년 4개 분기 중 점포 데이터 행 보유 분기 수", "수식": "4개 분기 중 점포 데이터 행 보유 분기수 집계", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "전체_점포_수", "단위": "분기", "결측치_처리_규칙": "결측 없음 (0~4)", "분모0_처리_규칙": "해당 없음"}
            elif col == "매출_보유_분기수":
                return {"한글_설명": "2025년 4개 분기 중 추정매출 실적 존재 분기 수", "수식": "4개 분기 중 매출 실적 존재 분기수 집계", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액", "단위": "분기", "결측치_처리_규칙": "결측 없음 (0~4)", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_추정매출_금액_합계":
                return {"한글_설명": "2025년 4개 분기 추정매출 금액 누적 합계", "수식": "존재하는 분기 당월_매출_금액 합산 (4개분기 모두 부재시 NaN)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액", "단위": "원", "결측치_처리_규칙": "4개분기 전체 결측시 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_추정매출_건수_합계":
                return {"한글_설명": "2025년 4개 분기 추정 결제건수 누적 합계", "수식": "존재하는 분기 당월_매출_건수 합산 (4개분기 모두 부재시 NaN)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_건수", "단위": "건", "결측치_처리_규칙": "4개분기 전체 결측시 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_개업_점포_수_합계":
                return {"한글_설명": "2025년 4개 분기 신규 개업 점포 수 누적 합계", "수식": "4개 분기 개업_점포_수 합산", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "개업_점포_수", "단위": "개", "결측치_처리_규칙": "결측 없음 (0개 이상)", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_폐업_점포_수_합계":
                return {"한글_설명": "2025년 4개 분기 폐업 점포 수 누적 합계", "수식": "4개 분기 폐업_점포_수 합산", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "폐업_점포_수", "단위": "개", "결측치_처리_규칙": "결측 없음 (0개 이상)", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_매출_결측_구분":
                return {"한글_설명": "연간 매출 실적 상태 구분 (정상 실적 / 4개분기 매출 실적 부재)", "수식": "연간 매출 실적 상태 조건 판정 (정상 실적 / 4개분기 매출 실적 부재)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_객단가":
                return {"한글_설명": "연간 1회 결제당 평균 결제금액", "수식": "연간_추정매출_금액_합계 ÷ 연간_추정매출_건수_합계", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "원", "결측치_처리_규칙": "연간 매출 실적 부재시 NaN 보존", "분모0_처리_규칙": "결제건수 0건인 경우 NaN 보존"}
            elif col == "연간_객단가_결측_사유":
                return {"한글_설명": "연간 객단가 산출 또는 결측 상태 사유 (정상 산출 / 4개분기 매출 실적 부재)", "수식": "연간 매출 및 결제건수 상태 조건 판정 (정상 산출 / 4개분기 매출 실적 부재)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_객단가_백분위_업종내":
                return {"한글_설명": "동일 서비스 업종 내 연간 객단가 백분위 (0 초과 100 이하)", "수식": "동일 서비스업종 내 연간_객단가 rank(method='average', pct=True) * 100.0", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "%", "결측치_처리_규칙": "연간 객단가 결측시 NaN 보존", "분모0_처리_규칙": "유효 상권수 0개시 NaN 보존"}
            elif col == "연간_객단가_백분위_공통그룹내":
                return {"한글_설명": "동일 공통그룹 내 연간 객단가 백분위 (0 초과 100 이하)", "수식": "동일 공통그룹 내 연간_객단가 rank(method='average', pct=True) * 100.0", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "%", "결측치_처리_규칙": "연간 객단가 결측시 NaN 보존", "분모0_처리_규칙": "유효 상권수 0개시 NaN 보존"}
            elif col == "유효_상권_수":
                return {"한글_설명": "동일 업종 내 연간 객단가 실적이 존재하는 서울시 상권 수", "수식": "동일 서비스업종 내 연간_객단가 유효 행 수 집계 (count)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "당월_매출_금액, 당월_매출_건수", "단위": "개", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_평균_전체_점포_수":
                return {"한글_설명": "4개 분기 점포 수 합계를 상수 4.0으로 나눈 연간 대표 점포 규모", "수식": "4개 분기 전체_점포_수 합 ÷ 4.0 (마트 행 없는 분기는 0개 점포로 가정)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "전체_점포_수", "단위": "개", "결측치_처리_규칙": "결측 없음 (0개 이상)", "분모0_처리_규칙": "분모는 상수 4.0으로 분모 0 발생 없음"}
            elif col == "연간_평균_프랜차이즈_점포_수":
                return {"한글_설명": "4개 분기 프랜차이즈 점포 수 합계를 상수 4.0으로 나눈 연간 대표 규모", "수식": "4개 분기 프랜차이즈_점포_수 합 ÷ 4.0 (마트 행 없는 분기는 0개 점포로 가정)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "프랜차이즈_점포_수", "단위": "개", "결측치_처리_규칙": "결측 없음 (0개 이상)", "분모0_처리_규칙": "분모는 상수 4.0으로 분모 0 발생 없음"}
            elif col == "연간_프랜차이즈_점포_비율":
                return {"한글_설명": "연간 평균 점포 수 중 프랜차이즈 가맹 점포 비율", "수식": "연간_평균_프랜차이즈_점포_수 ÷ 연간_평균_전체_점포_수 × 100.0", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "프랜차이즈_점포_수, 전체_점포_수", "단위": "%", "결측치_처리_규칙": "연간 점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(연간 전체 점포수) 0인 경우 NaN 보존"}
            elif col == "연간_프랜차이즈_결측_사유":
                return {"한글_설명": "연간 프랜차이즈 점포 비율 산출 또는 결측 사유 (정상 산출 / 연간 점포수 0개)", "수식": "연간 평균 전체 점포 수 상태 조건 판정 (정상 산출 / 연간 점포수 0개)", "입력_파일": "상권_업종_분기_특성표.csv", "입력_컬럼": "전체_점포_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_개업_점포_비율":
                return {"한글_설명": "연간 평균 점포 수 대비 연간 누적 신규 개업 비율 (승인 공식)", "수식": "연간_개업_점포_수_합계 ÷ 연간_평균_전체_점포_수 × 100.0 (승인 공식: 연간 개업 합계 ÷ 연간 평균 점포 수)", "입력_파일": "상권_업종_연간_특성표.csv", "입력_컬럼": "연간_개업_점포_수_합계, 연간_평균_전체_점포_수", "단위": "%", "결측치_처리_규칙": "연간 평균 점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(연간 평균 점포수) 0인 경우 NaN 보존"}
            elif col == "연간_폐업_점포_비율":
                return {"한글_설명": "연간 평균 점포 수 대비 연간 누적 폐업 비율 (승인 공식)", "수식": "연간_폐업_점포_수_합계 ÷ 연간_평균_전체_점포_수 × 100.0 (승인 공식: 연간 폐업 합계 ÷ 연간 평균 점포 수)", "입력_파일": "상권_업종_연간_특성표.csv", "입력_컬럼": "연간_폐업_점포_수_합계, 연간_평균_전체_점포_수", "단위": "%", "결측치_처리_규칙": "연간 평균 점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(연간 평균 점포수) 0인 경우 NaN 보존"}
            elif col == "연간_개폐업_결측_사유":
                return {"한글_설명": "연간 개폐업 비율 산출 또는 결측 사유 (정상 산출 / 연간 평균 점포수 0개)", "수식": "연간 평균 전체 점포 수 상태 조건 판정 (정상 산출 / 연간 평균 점포수 0개)", "입력_파일": "상권_업종_연간_특성표.csv", "입력_컬럼": "연간_평균_전체_점포_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "연간_점포_밀집도_ha":
                return {"한글_설명": "상권 구역 면적(ha)당 해당 업종 연간 평균 점포 수", "수식": "연간_평균_전체_점포_수 ÷ 영역_면적_ha", "입력_파일": "상권_업종_연간_특성표.csv", "입력_컬럼": "연간_평균_전체_점포_수, 영역_면적_ha", "단위": "개/ha", "결측치_처리_규칙": "면적 부재시 NaN 보존", "분모0_처리_규칙": "분모(영역 면적) 0인 경우 NaN 보존"}

        # 3. 상권_분기_특성표
        elif table_name == "상권_분기_특성표":
            if col == "기준_년분기_코드":
                return {"한글_설명": "분석 기준 연도와 분기 (YYYYQ)", "수식": "원천 기준_년분기_코드 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "기준_년분기_코드", "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_코드", "상권_구분_코드", "자치구_코드", "행정동_코드"]:
                return {"한글_설명": f"{col.replace('_코드', '')} 표준 행정/식별 코드", "수식": f"원천 {col} 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": col, "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_코드_명", "상권_표시_명", "상권_구분_코드_명", "자치구_코드_명", "행정동_코드_명"]:
                return {"한글_설명": f"{col.replace('_명', '').replace('_코드', '')} 한글 명칭", "수식": f"원천 {col} 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": col, "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col.endswith("_유동인구_수") or col in ["총_유동인구_수", "남성_유동인구_수", "여성_유동인구_수"]:
                return {"한글_설명": f"상권 구역을 통행한 {col.replace('_수', '')} 보행자 수", "수식": f"원천 {col} 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": col, "단위": "명", "결측치_처리_규칙": "원천 미집계시 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_변화_지표":
                return {"한글_설명": "서울시 상권분석 4대 유형 코드", "수식": "원천 상권_변화_지표 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_변화_지표", "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_변화_지표_명":
                return {"한글_설명": f"[가설] 서울시 공공 모델 4대 상권 유형 (정체/상권축소/다이나믹/상권확장: 운영영업개월과 폐업영업개월의 서울시 전체 평균 대비 고/저 조합 판정{change_desc_stat}", "수식": "원천 상권_변화_지표_명 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_변화_지표_명", "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["운영_영업_개월_평균", "폐업_영업_개월_평균"]:
                return {"한글_설명": f"상권 내 점포들의 평균 {col.replace('_평균', '')} 기간", "수식": f"원천 {col} 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": col, "단위": "개월", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_당월_매출_금액_합계", "상권_당월_매출_건수_합계"]:
                u = "원" if "금액" in col else "건"
                type_name = "금액" if "금액" in col else "건수"
                return {"한글_설명": f"해당 분기 상권 내 전체 업종의 추정매출 {type_name}", "수식": f"원천 {col} 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": col, "단위": u, "결측치_처리_규칙": "추정매출 미집계 상권 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_전체_점포_수_합계", "상권_일반_점포_수_합계", "상권_프랜차이즈_점포_수_합계", "상권_개업_점포_수_합계", "상권_폐업_점포_수_합계", "상권_매출_보유_업종_수", "상권_점포_보유_업종_수"]:
                return {"한글_설명": f"해당 분기 상권 내 전체 업종의 {col.replace('상권_', '').replace('_합계', '').replace('_수', '')} 개수", "수식": f"원천 {col} 적재", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": col, "단위": "개", "결측치_처리_규칙": "결측시 0개 간주", "분모0_처리_규칙": "해당 없음"}
            elif col == "영역_면적_ha":
                return {"한글_설명": "상권 구역 전체 면적 (헥타르)", "수식": "상권_마스터.csv 영역_면적_ha 1:1 결합", "입력_파일": "상권_마스터.csv", "입력_컬럼": "영역_면적_ha", "단위": "ha", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_매출_결측_사유":
                return {"한글_설명": "상권 분기 총매출 결측 여부 사유", "수식": "상권_당월_매출_금액_합계 결측 여부 판정 (정상 산출 / 해당 분기 추정매출 실적 부재)", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_분기_매출_증감률":
                return {"한글_설명": "직전 분기 대비 당분기 상권 전체 매출 변동 비율", "수식": "(당분기 상권매출합 - 직전분기 상권매출합) ÷ 직전분기 상권매출합 × 100.0", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "%", "결측치_처리_규칙": "직전분기 또는 당분기 매출 부재시 NaN 보존", "분모0_처리_규칙": "직전분기 매출 0원 또는 부재시 NaN 보존"}
            elif col == "상권_매출증감_결측_사유":
                return {"한글_설명": "상권 분기 매출 증감률 산출 또는 결측 사유", "수식": "직전분기 및 당분기 상권 매출 상태 조건 판정 (정상 산출 / 전분기 자료 부재(2025Q1) / 직전분기 상권매출 부재 또는 0원 / 당분기 상권매출 부재)", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_매출증감_극단치_플래그":
                return {"한글_설명": "상권 분기 매출 증감률 극단치 여부 판정 플래그", "수식": "상권_분기_매출_증감률 < -90.0% 또는 > 500.0% 판정", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_분기_프랜차이즈_점포_비율":
                return {"한글_설명": "상권 내 전체 점포 수 중 프랜차이즈 가맹 점포 비율", "수식": "상권_프랜차이즈_점포_수_합계 ÷ 상권_전체_점포_수_합계 × 100.0", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_프랜차이즈_점포_수_합계, 상권_전체_점포_수_합계", "단위": "%", "결측치_처리_규칙": "점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(전체 점포수) 0인 경우 NaN 보존"}
            elif col == "상권_분기_개업_점포_비율":
                return {"한글_설명": "상권 내 전체 점포 수 대비 분기 신규 개업 비율 (개업률)", "수식": "상권_개업_점포_수_합계 ÷ 상권_전체_점포_수_합계 × 100.0", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_개업_점포_수_합계, 상권_전체_점포_수_합계", "단위": "%", "결측치_처리_규칙": "점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(전체 점포수) 0인 경우 NaN 보존"}
            elif col == "상권_분기_폐업_점포_비율":
                return {"한글_설명": "상권 내 전체 점포 수 대비 분기 폐업 비율 (폐업률)", "수식": "상권_폐업_점포_수_합계 ÷ 상권_전체_점포_수_합계 × 100.0", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_폐업_점포_수_합계, 상권_전체_점포_수_합계", "단위": "%", "결측치_처리_규칙": "점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(전체 점포수) 0인 경우 NaN 보존"}
            elif col == "상권_분기_점포_밀집도_ha":
                return {"한글_설명": "상권 구역 면적(ha)당 점포 수", "수식": "상권_전체_점포_수_합계 ÷ 영역_면적_ha", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "상권_전체_점포_수_합계", "단위": "개/ha", "결측치_처리_규칙": "면적 부재시 NaN 보존", "분모0_처리_규칙": "분모(영역 면적) 0인 경우 NaN 보존"}
            elif "유동인구_" in col and "_비율" in col:
                sub = col.replace("유동인구_", "").replace("_비율", "")
                if sub in ["남성", "여성"]:
                    inp_sub = f"{sub}_유동인구_수"
                    sub_formula = f"{inp_sub} ÷ 총_유동인구_수 × 100.0"
                    inps = f"{inp_sub}, 총_유동인구_수"
                elif "시간대_" in sub:
                    inp_sub = f"{sub}_유동인구_수"
                    sub_formula = f"{inp_sub} ÷ 총_유동인구_수 × 100.0"
                    inps = f"{inp_sub}, 총_유동인구_수"
                elif sub == "60대이상":
                    inp_sub = "연령대_60_이상_유동인구_수"
                    sub_formula = f"{inp_sub} ÷ 총_유동인구_수 × 100.0"
                    inps = f"{inp_sub}, 총_유동인구_수"
                elif "대" in sub:
                    age_clean = sub.replace("대", "")
                    inp_sub = f"연령대_{age_clean}_유동인구_수"
                    sub_formula = f"{inp_sub} ÷ 총_유동인구_수 × 100.0"
                    inps = f"{inp_sub}, 총_유동인구_수"
                elif sub == "주중":
                    sub_formula = "(월+화+수+목+금 유동인구 합) ÷ 총_유동인구_수 × 100.0"
                    inps = "월요일_유동인구_수, 화요일_유동인구_수, 수요일_유동인구_수, 목요일_유동인구_수, 금요일_유동인구_수, 총_유동인구_수"
                elif sub == "주말":
                    sub_formula = "(토+일 유동인구 합) ÷ 총_유동인구_수 × 100.0"
                    inps = "토요일_유동인구_수, 일요일_유동인구_수, 총_유동인구_수"
                else: # 요일별
                    inp_sub = f"{sub}_유동인구_수"
                    sub_formula = f"{inp_sub} ÷ 총_유동인구_수 × 100.0"
                    inps = f"{inp_sub}, 총_유동인구_수"
                return {"한글_설명": f"전체 보행 유동인구 중 {sub} 유동인구가 차지하는 상대적 비중", "수식": sub_formula, "입력_파일": "상권_분기_마트.csv", "입력_컬럼": inps, "단위": "%", "결측치_처리_규칙": "총_유동인구_수 결측시 NaN 보존", "분모0_처리_규칙": "분모(총 유동인구) 0인 경우 NaN 보존"}
            elif col == "유동인구_결측_사유":
                return {"한글_설명": "유동인구 산출 또는 결측 상태 사유", "수식": "총_유동인구_수 결측 여부 판정 (정상 산출 / 원천 미집계)", "입력_파일": "상권_분기_마트.csv", "입력_컬럼": "총_유동인구_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}

        # 4. 상권_특성표
        else:
            if col in ["상권_구분_코드", "상권_코드", "자치구_코드", "행정동_코드"]:
                return {"한글_설명": f"{col.replace('_코드', '')} 표준 행정/식별 코드", "수식": f"원천 {col} 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": col, "단위": "코드", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["상권_구분_코드_명", "상권_코드_명", "상권_표시_명", "자치구_코드_명", "행정동_코드_명"]:
                return {"한글_설명": f"{col.replace('_명', '').replace('_코드', '')} 한글 명칭", "수식": f"원천 {col} 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": col, "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["엑스좌표_값", "와이좌표_값"]:
                return {"한글_설명": f"상권 구역 중심점의 좌표 ({col})", "수식": f"원천 {col} 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": col, "단위": "좌표", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "영역_면적":
                return {"한글_설명": "상권 구역 전체 면적 (제곱미터)", "수식": "원천 영역_면적 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "영역_면적", "단위": "㎡", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "영역_면적_ha":
                return {"한글_설명": "상권 구역 전체 면적 (헥타르)", "수식": "원천 영역_면적_ha 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "영역_면적_ha", "단위": "ha", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "자치구_행정동_불일치_여부":
                return {"한글_설명": "상권 소속 자치구와 배후 행정동 소속 자치구의 불일치 여부", "수식": "상권 자치구코드와 배후동 자치구코드 불일치 판정", "입력_파일": "상권_마스터.csv", "입력_컬럼": "자치구_코드, 행정동_코드", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif "상주인구_수" in col or "직장_인구_수" in col:
                u = "명"
                return {"한글_설명": f"상권 구역 내부의 {col.replace('_수', '')} 규모", "수식": f"원천 {col} 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": col, "단위": u, "결측치_처리_규칙": "원천 미집계 상권 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col in ["총_가구_수", "아파트_가구_수", "비_아파트_가구_수"]:
                return {"한글_설명": f"상권 구역 내부의 {col.replace('_수', '')} 규모", "수식": f"원천 {col} 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": col, "단위": "가구", "결측치_처리_규칙": "원천 미집계 상권 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "집객시설_수" or (col.endswith("_수") and any(fac in col for fac in ["관공서", "은행", "병원", "약국", "유치원", "학교", "백화점", "슈퍼마켓", "극장", "숙박", "공항", "철도", "터미널", "역", "정거장"])):
                return {"한글_설명": f"상권 내 위치한 {col.replace('_수', '')} 개수", "수식": f"원천 {col} 적재 (미집계 상권은 NaN 보존)", "입력_파일": "상권_마스터.csv", "입력_컬럼": col, "단위": "개", "결측치_처리_규칙": f"원천 미집계 {fac_missing_cnt}개 상권 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "집객시설_원천행_없음":
                return {"한글_설명": "원천 집객시설 데이터에 행 자체가 존재하지 않는 미집계 상권 여부", "수식": f"집객시설_수 결측 여부 판정 ({fac_missing_cnt}개 상권 True)", "입력_파일": "상권_마스터.csv", "입력_컬럼": "집객시설_수", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_면적_km2":
                return {"한글_설명": "상권의 대표 배후 행정동 전체 면적 (제곱킬로미터)", "수식": "원천 배후동_면적_km2 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "배후동_면적_km2", "단위": "km²", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_자치구_평균소득월액":
                return {"한글_설명": "상권이 속한 배후 자치구 거주민의 가구당 월평균 소득", "수식": "원천 배후동_자치구_평균소득월액 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "배후동_자치구_평균소득월액", "단위": "원", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_소상공인_점포수_전체":
                return {"한글_설명": "배후 행정동 내 소상공인진흥공단 등록 전체 점포 수", "수식": "원천 배후동_소상공인_점포수_전체 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "배후동_소상공인_점포수_전체", "단위": "개", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_소비_이상치":
                return {"한글_설명": "배후 행정동에서 단일 지출 항목 비중이 90% 이상인 소비 이상치 상권 여부", "수식": f"원천 배후동_소비_이상치 적재 ({outlier_dong_cnt}개 상권 True)", "입력_파일": "상권_마스터.csv", "입력_컬럼": "배후동_소비_이상치", "단위": "논리값", "결측치_처리_규칙": "결측 없음 (True/False)", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_소비_연간지출_총금액":
                return {"한글_설명": "상권의 대표 배후 행정동 거주자의 연간 신용카드 추정 지출 총액", "수식": "원천 배후동_소비_연간지출_총금액 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "배후동_소비_연간지출_총금액", "단위": "원", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_소비_최대항목":
                return {"한글_설명": "배후 행정동 거주민의 카드 지출 금액이 가장 큰 소비 항목 명칭", "수식": "원천 배후동_소비_최대항목 적재", "입력_파일": "상권_마스터.csv", "입력_컬럼": "배후동_소비_최대항목", "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "배후동_소비_최대항목_비중":
                return {"한글_설명": "배후 행정동 전체 지출 중 최대 지출 항목이 차지하는 비율", "수식": "행정동_마스터.csv 소비_최대항목_비중 1:1 결합", "입력_파일": "행정동_마스터.csv", "입력_컬럼": "소비_최대항목_비중", "단위": "%", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_매출_보유_분기수":
                return {"한글_설명": "2025년 4개 분기 중 상권 전체 매출 실적 보유 분기 수", "수식": "4개 분기 중 상권 매출 실적 보유 분기수 집계", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "분기", "결측치_처리_규칙": "결측 없음 (0~4)", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_연간_매출_금액_합계":
                return {"한글_설명": "2025년 4개 분기 상권 전체 추정매출 금액 누적 합계", "수식": "4개 분기 상권_당월_매출_금액_합계 합산 (4분기 모두 부재시 NaN)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "원", "결측치_처리_규칙": "4개분기 전체 결측시 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_연간_매출_건수_합계":
                return {"한글_설명": "2025년 4개 분기 상권 전체 추정 결제건수 누적 합계", "수식": "4개 분기 상권_당월_매출_건수_합계 합산 (4분기 모두 부재시 NaN)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_당월_매출_건수_합계", "단위": "건", "결측치_처리_규칙": "4개분기 전체 결측시 NaN 보존", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_점포_보유_분기수":
                return {"한글_설명": "2025년 4개 분기 중 상권 점포 데이터 보유 분기 수", "수식": "4개 분기 중 상권 점포 데이터 보유 분기수 집계", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_전체_점포_수_합계", "단위": "분기", "결측치_처리_규칙": "결측 없음 (0~4)", "분모0_처리_규칙": "해당 없음"}
            elif col == "유동인구_보유_분기수":
                return {"한글_설명": "2025년 4개 분기 중 보행 유동인구 관측 분기 수", "수식": "4개 분기 중 보행 유동인구 관측 분기수 집계", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "총_유동인구_수", "단위": "분기", "결측치_처리_규칙": "결측 없음 (0~4)", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_연간_매출_결측_사유":
                return {"한글_설명": "상권 연간 매출 상태 구분 (정상 산출 / 4개분기 전체 매출 부재 / 일부 분기 매출 부재)", "수식": "상권 연간 매출 상태 조건 판정 (정상 산출 / 4개분기 전체 매출 부재 / 일부 분기 매출 부재)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_당월_매출_금액_합계", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_연간_평균_점포_수":
                return {"한글_설명": "4개 분기 상권 전체 점포수 합계를 상수 4.0으로 나눈 연간 대표 점포 규모", "수식": "4개 분기 상권_전체_점포_수_합계 합 ÷ 4.0", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_전체_점포_수_합계", "단위": "개", "결측치_처리_규칙": "결측 없음 (0개 이상)", "분모0_처리_규칙": "분모는 상수 4.0으로 분모 0 발생 없음"}
            elif col == "상권_연간_프랜차이즈_점포_비율":
                return {"한글_설명": "상권 연간 전체 점포 중 프랜차이즈 가맹 점포 비율", "수식": "4개 분기 프랜차이즈 점포합 ÷ 4개 분기 전체 점포합 × 100.0", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_프랜차이즈_점포_수_합계, 상권_전체_점포_수_합계", "단위": "%", "결측치_처리_규칙": "연간 점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(연간 전체 점포수) 0인 경우 NaN 보존"}
            elif col == "상권_연간_개업_점포_비율":
                return {"한글_설명": "상권 연간 평균 점포 수 대비 연간 누적 개업 비율 (승인 공식)", "수식": "4개 분기 상권_개업_점포_수_합계 합 ÷ 상권_연간_평균_점포_수 × 100.0 (승인 공식: 연간 개업 합계 ÷ 연간 평균 점포 수)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_개업_점포_수_합계, 상권_전체_점포_수_합계", "단위": "%", "결측치_처리_규칙": "연간 평균 점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(연간 평균 점포수) 0인 경우 NaN 보존"}
            elif col == "상권_연간_폐업_점포_비율":
                return {"한글_설명": "상권 연간 평균 점포 수 대비 연간 누적 폐업 비율 (승인 공식)", "수식": "4개 분기 상권_폐업_점포_수_합계 합 ÷ 상권_연간_평균_점포_수 × 100.0 (승인 공식: 연간 폐업 합계 ÷ 연간 평균 점포 수)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_폐업_점포_수_합계, 상권_전체_점포_수_합계", "단위": "%", "결측치_처리_규칙": "연간 평균 점포수 0개시 NaN 보존", "분모0_처리_규칙": "분모(연간 평균 점포수) 0인 경우 NaN 보존"}
            elif col == "상권_연간_점포_밀집도_ha":
                return {"한글_설명": "상권 구역 면적(ha)당 연간 평균 점포 수", "수식": "상권_연간_평균_점포_수 ÷ 영역_면적_ha", "입력_파일": "상권_특성표.csv", "입력_컬럼": "상권_연간_평균_점포_수, 영역_면적_ha", "단위": "개/ha", "결측치_처리_규칙": "면적 부재시 NaN 보존", "분모0_처리_규칙": "분모(영역 면적) 0인 경우 NaN 보존"}
            elif col == "상권_연간_평균_유동인구_수":
                return {"한글_설명": "유동인구 실적이 존재하는 관측 분기만의 평균 보행 유동인구 수", "수식": "총_유동인구_수 분기합 ÷ 유동인구 관측 분기수 (미집계 결측을 0으로 보지 않음)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "총_유동인구_수", "단위": "명", "결측치_처리_규칙": "유동인구 관측 분기 0개시 NaN 보존", "분모0_처리_규칙": "관측 분기수 0인 경우 NaN 보존"}
            elif col == "상권_유동인구_결측_사유":
                return {"한글_설명": "상권 유동인구 관측 상태 사유", "수식": "유동인구 관측 분기수 상태 판정 (정상 산출 / 원천 미집계(발생 없음))", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "총_유동인구_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상주인구_결측_사유":
                return {"한글_설명": "상주인구 수집 상태 사유", "수식": "총_상주인구_수 결측 여부 판정 (정상 산출 / 원천 상주인구 미집계)", "입력_파일": "상권_마스터.csv", "입력_컬럼": "총_상주인구_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif "상주인구_" in col and "_비율" in col:
                sub = col.replace("상주인구_", "").replace("_비율", "")
                if sub in ["남성", "여성"]:
                    inp_sub = f"{sub}_상주인구_수"
                elif sub == "60대이상":
                    inp_sub = "연령대_60_이상_상주인구_수"
                else:
                    age_clean = sub.replace("대", "")
                    inp_sub = f"연령대_{age_clean}_상주인구_수"
                return {"한글_설명": f"전체 상주인구 중 {sub} 상주인구가 차지하는 상대적 비중", "수식": f"{inp_sub} ÷ 총_상주인구_수 × 100.0", "입력_파일": "상권_마스터.csv", "입력_컬럼": f"{inp_sub}, 총_상주인구_수", "단위": "%", "결측치_처리_규칙": "총_상주인구_수 결측시 NaN 보존", "분모0_처리_규칙": "분모(총 상주인구) 0인 경우 NaN 보존"}
            elif col == "상주가구_아파트_비율":
                return {"한글_설명": "상권 내부 총 가구 수 중 아파트 거주 가구 비율", "수식": "아파트_가구_수 ÷ 총_가구_수 × 100.0", "입력_파일": "상권_마스터.csv", "입력_컬럼": "아파트_가구_수, 총_가구_수", "단위": "%", "결측치_처리_규칙": "총 가구수 부재시 NaN 보존", "분모0_처리_규칙": "분모(총 가구수) 0인 경우 NaN 보존"}
            elif col == "상주가구_비아파트_비율":
                return {"한글_설명": "상권 내부 총 가구 수 중 비아파트 거주 가구 비율", "수식": "비_아파트_가구_수 ÷ 총_가구_수 × 100.0", "입력_파일": "상권_마스터.csv", "입력_컬럼": "비_아파트_가구_수, 총_가구_수", "단위": "%", "결측치_처리_규칙": "총 가구수 부재시 NaN 보존", "분모0_처리_규칙": "분모(총 가구수) 0인 경우 NaN 보존"}
            elif col == "직장인구_결측_사유":
                return {"한글_설명": "직장인구 수집 상태 사유", "수식": "총_직장_인구_수 결측 여부 판정 (정상 산출 / 원천 직장인구 미집계)", "입력_파일": "상권_마스터.csv", "입력_컬럼": "총_직장_인구_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif "직장인구_" in col and "_비율" in col:
                sub = col.replace("직장인구_", "").replace("_비율", "")
                if sub in ["남성", "여성"]:
                    inp_sub = f"{sub}_직장_인구_수"
                elif sub == "60대이상":
                    inp_sub = "연령대_60_이상_직장_인구_수"
                else:
                    age_clean = sub.replace("대", "")
                    inp_sub = f"연령대_{age_clean}_직장_인구_수"
                return {"한글_설명": f"전체 직장인구 중 {sub} 직장인구가 차지하는 상대적 비중", "수식": f"{inp_sub} ÷ 총_직장_인구_수 × 100.0", "입력_파일": "상권_마스터.csv", "입력_컬럼": f"{inp_sub}, 총_직장_인구_수", "단위": "%", "결측치_처리_규칙": "총_직장_인구_수 결측시 NaN 보존", "분모0_처리_규칙": "분모(총 직장인구) 0인 경우 NaN 보존"}
            elif col == "상권_변화_지표_명_2025Q4":
                return {"한글_설명": f"[가설] 2025년 4분기 기준 서울시 공공 모델 4대 상권 유형 (정체/상권축소/다이나믹/상권확장: 운영영업개월과 폐업영업개월의 서울시 전체 평균 대비 고/저 조합 판정{change_desc_stat}", "수식": "2025Q4 기준 상권_변화_지표_명 추출", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_변화_지표_명", "단위": "명칭", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col in ["운영_영업_개월_2025Q4", "폐업_영업_개월_2025Q4"]:
                inp = col.replace("_2025Q4", "_평균")
                return {"한글_설명": f"2025년 4분기 기준 상권 내 점포들의 평균 {col.replace('_2025Q4', '')} 기간", "수식": f"2025Q4 기준 {inp} 추출", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": inp, "단위": "개월", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_변화_지표_변경_횟수":
                return {"한글_설명": "2025년 4개 분기 동안 상권 변화 지표가 바뀐 총 횟수 (0~3회)", "수식": "인접 분기 간 상권_변화_지표_명 불일치 횟수 합산 (0~3회)", "입력_파일": "상권_분기_특성표.csv", "입력_컬럼": "상권_변화_지표_명", "단위": "회", "결측치_처리_규칙": "결측 없음 (0~3회)", "분모0_처리_규칙": "해당 없음"}
            elif col == "집객시설_결측_사유":
                return {"한글_설명": "집객시설 산출 또는 결측 상태 사유", "수식": "집객시설_수 결측 여부 판정 (정상 산출 / 원천 집객시설 미집계)", "입력_파일": "상권_마스터.csv", "입력_컬럼": "집객시설_수", "단위": "사유텍스트", "결측치_처리_규칙": "결측 없음", "분모0_처리_규칙": "해당 없음"}
            elif col == "상권_임대료_보증금_수준":
                return {"한글_설명": "상권 내 평균 임대료 및 환산보증금 수준 지표 (원천 공공데이터 미제공)", "수식": "원천 데이터 미제공으로 '데이터 없음' 표기", "입력_파일": "원천_미제공", "입력_컬럼": "없음", "단위": "사유텍스트", "결측치_처리_규칙": "원천 부재로 전원 '데이터 없음' 보존", "분모0_처리_규칙": "해당 없음"}

        raise ValueError(f"Unknown column: {table_name} -> {col}")

    records = []
    for t_name, df_target in tables:
        ana_unit = "상권×업종×분기" if t_name == "상권_업종_분기_특성표" else ("상권×업종 연간" if t_name == "상권_업종_연간_특성표" else ("상권×분기" if t_name == "상권_분기_특성표" else "상권 연간"))
        for col in df_target.columns:
            dtype = str(df_target[col].dtype)
            meta = get_column_metadata(t_name, col, dtype)
            meta["테이블명"] = t_name
            meta["컬럼명"] = col
            meta["데이터타입"] = dtype
            meta["분석_단위"] = ana_unit
            records.append(meta)

    std_cols = [
        "테이블명", "컬럼명", "한글_설명", "수식", "입력_파일", "입력_컬럼",
        "데이터타입", "단위", "분석_단위", "결측치_처리_규칙", "분모0_처리_규칙"
    ]
    df_dict = pd.DataFrame(records)[std_cols]
    df_dict.to_csv(STAGE3_DIR / "변수사전.csv", index=False, encoding="utf-8-sig")
    print(f"  -> 변수사전 저장 완료: 총 {len(df_dict)}개 컬럼 수록")


def main():
    print("=" * 70)
    print("   [SpotFit Stage 3] 파생변수 및 4종 특성표 생성 파이프라인")
    print("=" * 70)

    df_ind, df_q, df_m, df_dong_m = load_stage2_data()

    # 1. 상권_업종_분기_특성표
    df_ind_feat = build_industry_quarterly_features(df_ind, df_m)
    df_ind_feat.to_parquet(STAGE3_DIR / "상권_업종_분기_특성표.parquet", index=False)
    df_ind_feat.to_csv(STAGE3_DIR / "상권_업종_분기_특성표.csv", index=False, encoding="utf-8-sig")

    # 2. 상권_업종_연간_특성표
    df_ind_ann = build_industry_annual_features(df_ind_feat, df_m)
    df_ind_ann.to_csv(STAGE3_DIR / "상권_업종_연간_특성표.csv", index=False, encoding="utf-8-sig")

    # 3. 상권_분기_특성표
    df_t_q = build_trade_quarterly_features(df_q, df_m, df_ind_feat)
    df_t_q.to_csv(STAGE3_DIR / "상권_분기_특성표.csv", index=False, encoding="utf-8-sig")

    # 4. 상권_특성표
    df_t_a = build_trade_annual_features(df_m, df_t_q, df_ind_ann, df_dong_m)
    df_t_a.to_csv(STAGE3_DIR / "상권_특성표.csv", index=False, encoding="utf-8-sig")

    # 5. 민감도, 소표본 비교, 윈저화, 요약 통계
    build_sensitivity_and_discussion_files(df_ind, df_q, df_m, df_ind_feat, df_ind_ann, df_t_q, df_t_a)

    # 6. 상관관계 행렬 저장
    corr_cols = [
        "상권_연간_매출_금액_합계", "상권_연간_평균_점포_수", "상권_연간_프랜차이즈_점포_비율",
        "상권_연간_개업_점포_비율", "상권_연간_폐업_점포_비율", "상권_연간_점포_밀집도_ha",
        "상권_연간_평균_유동인구_수", "총_상주인구_수", "총_직장_인구_수",
        "운영_영업_개월_2025Q4", "폐업_영업_개월_2025Q4", "배후동_소비_연간지출_총금액",
        "배후동_자치구_평균소득월액", "집객시설_수"
    ]
    corr_matrix = df_t_a[corr_cols].corr()
    corr_matrix.to_csv(STAGE3_DIR / "변수_상관관계_행렬.csv", encoding="utf-8-sig")

    # 7. 변수사전 저장
    build_variable_dictionary(df_ind_feat, df_ind_ann, df_t_q, df_t_a)

    print("=" * 70)
    print("   [SpotFit Stage 3] 파생변수 산출 파이프라인 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
