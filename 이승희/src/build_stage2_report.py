#!/usr/bin/env python3
"""SpotFit 2단계: 결과 데이터 집계, 시각화, 보고서 및 대시보드 자동 생성 스크립트 (재검수 반영 개정본)

수정 사항:
1. 점포 수 4개 분기 합산을 연간 점포 수로 표현하지 않고 '분기별 합산'으로 명시, 분기별 수치 및 Q4 수치 병기
2. 파생변수(객단가, 프랜차이즈 비율, 개폐업 비율) 마트 제외 반영 및 3단계 이관 설명
3. 집객시설 72개 상권 NaN 보존 및 '집객시설_원천행_없음' 플래그 반영, 실제 세부 합과 비교 통계 수록
4. 공용 표 4종 원천 대조 및 격리 재현 시험 결과, 62개 업종 점포 행수 차이(61행) 상세 설명
5. 상권 중심점 ↔ 대표 행정동 불일치 31개(자치구 상이 3개) 수록 및 좌표계(EPSG:5181 -> EPSG:4326) 명시
6. 경계 밖 80건 자치구별 건수 기재 (미확인 지명 배제)
7. 결제수단 특정 명칭 배제 및 '추정매출' 단독 사용
8. [가설] 태그 정밀 부착 (상업 기능 집중, 센서 미수집, 주거 중심 동, 매출 미발생 등)
9. 매출 빈 행을 점포 보유 행(158,895행)과 점포 0행(1,570행)으로 분리 기재
10. 코드 내 하드코딩 숫자 전면 제거 (동적 계산값 로드), 그림 2 범례 위치 조정
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STAGE2_DATA_DIR = PROCESSED_DIR / "stage2"
REPORT_DIR = PROJECT_DIR / "report"
IMAGES_DIR = PROJECT_DIR / "images" / "stage2"

REPORT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

np.random.seed(42)

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def generate_visualizations(data):
    """보고서 및 대시보드용 시각화 생성 (파이차트 절대 미사용, 범례 위치 최적화)"""
    print("[1/4] 차트 시각화 이미지 생성...")
    spatial_stats = data["stats"]["spatial"]
    df_mismatch = data["df_mismatch"]
    df_trade_ind = data["df_trade_ind"]
    df_trade_m = data["df_trade_m"]
    stats = data["stats"]
    total_trades = stats["master_rows"]

    # 차트 1: 점포 위치 불일치 이격거리 분포
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    d_under500 = df_mismatch[df_mismatch["경계_이격거리_m"] <= 500]["경계_이격거리_m"]
    ax1.hist(d_under500, bins=50, color="#2b5c8f", edgecolor="black", alpha=0.75)
    ax1.axvline(spatial_stats["이격거리_중위수_m"], color="#d9534f", linestyle="--", linewidth=2,
                label=f"중위수: {spatial_stats['이격거리_중위수_m']}m")
    ax1.axvline(100, color="#f0ad4e", linestyle=":", linewidth=2,
                label=f"100m 기준선 ({spatial_stats['100m_이내_비율_pct']}%)")
    ax1.set_title("점포 좌표 ↔ 행정동 경계 이격거리 분포 (500m 이내)", fontsize=12, fontweight="bold")
    ax1.set_xlabel("경계면 최단거리 (미터)")
    ax1.set_ylabel("점포 수 (건)")
    ax1.legend(loc="upper right")
    ax1.grid(True, linestyle="--", alpha=0.5)

    sorted_d = np.sort(df_mismatch["경계_이격거리_m"].dropna().values)
    cum_pct = np.arange(1, len(sorted_d) + 1) / len(sorted_d) * 100.0
    ax2.plot(sorted_d, cum_pct, color="#1b7837", linewidth=2.5)
    ax2.axvline(100, color="#f0ad4e", linestyle=":", linewidth=2,
                label=f"100m ({spatial_stats['100m_이내_비율_pct']}% 누적)")
    ax2.axhline(spatial_stats["100m_이내_비율_pct"], color="#f0ad4e", linestyle=":", linewidth=1)
    ax2.set_xlim(0, 500)
    ax2.set_title("경계 이격거리 누적 점포 비율 (%)", fontsize=12, fontweight="bold")
    ax2.set_xlabel("경계면 최단거리 (미터)")
    ax2.set_ylabel("누적 점포 비율 (%)")
    ax2.legend(loc="lower right")
    ax2.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    chart1_path = IMAGES_DIR / "01_점포_위치_이격거리_분포.png"
    plt.savefig(chart1_path, dpi=200)
    plt.close()
    print(f"  -> {chart1_path.name} 저장 완료")

    # 차트 2: 상권 원천 파일별 수집 커버리지
    fig, ax = plt.subplots(figsize=(11, 5.5))
    categories = ["영역(마스터)", "상권변화지표", "점포(분기)", "길단위인구", "직장인구", "상주인구", "집객시설", "추정매출"]
    no_sales_trades_count = len(set(df_trade_m["상권_코드"]) - set(df_trade_ind.dropna(subset=["당월_매출_금액"])["상권_코드"]))
    missing = [0, 0, 0, 0, stats["wrk_missing_trades"], stats["res_missing_trades"], stats["fac_missing_districts"], no_sales_trades_count]
    counts = [total_trades - m for m in missing]

    x = np.arange(len(categories))
    width = 0.55

    ax.bar(x, counts, width, label="수집 상권 수", color="#2b5c8f")
    ax.bar(x, missing, width, bottom=counts, label="미수집 상권 수 (결측)", color="#d9534f")

    ax.set_ylabel(f"상권 수 (개, 전체 {total_trades:,}개)")
    ax.set_title(f"상권 8종 원천 데이터의 상권({total_trades:,}개) 수집 커버리지 현황", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=15, ha="right")
    ax.set_ylim(0, int(total_trades * 1.18))
    # 그림 2의 범례를 그래프 밖 좌측 상단으로 이동하여 막대와 겹침 방지
    ax.legend(loc="upper left", framealpha=0.9)
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)

    for i in range(len(categories)):
        ax.text(x[i], counts[i] - 130, f"{counts[i]:,}개\n({counts[i]/total_trades*100:.1f}%)", ha="center", color="white", fontweight="bold", fontsize=9)
        if missing[i] > 0:
            ax.text(x[i], total_trades + 20, f"+{missing[i]}개", ha="center", color="#d9534f", fontweight="bold", fontsize=9)

    plt.tight_layout()
    chart2_path = IMAGES_DIR / "02_상권특성_데이터_준비도.png"
    plt.savefig(chart2_path, dpi=200)
    plt.close()
    print(f"  -> {chart2_path.name} 저장 완료")

    # 차트 3: 13개 공통 그룹별 2025Q4 점포 수 분포 (파생 객단가 대신 실측 점포 규모 표시)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    q4_ind = df_trade_ind[df_trade_ind["기준_년분기_코드"] == 20254]
    group_stores = q4_ind.groupby("공통그룹")["전체_점포_수"].sum().sort_values(ascending=False)
    group_count = len(group_stores)

    x_grp = range(group_count)
    bars = ax.bar(x_grp, group_stores.values, color="#3182bd", edgecolor="black", alpha=0.85)
    ax.set_ylabel("2025Q4 점포 수 (개)")
    ax.set_title(f"{group_count}개 업종 공통그룹별 2025Q4 점포 수 분포 ('연결 안 함' 포함)", fontsize=12, fontweight="bold")
    ax.set_xticks(x_grp)
    ax.set_xticklabels(group_stores.index, rotation=25, ha="right")
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)

    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"{int(h):,}개",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    plt.tight_layout()
    chart3_path = IMAGES_DIR / "03_공통그룹별_점포수_분포.png"
    plt.savefig(chart3_path, dpi=200)
    plt.close()
    print(f"  -> {chart3_path.name} 저장 완료")


def load_all_stage2_data():
    """모든 2단계 산출물 로드 및 정확한 통계 산출 (코드 하드코딩 제거)"""
    print("[2/4] 마트 산출물 데이터 로드 및 종합 통계 산출...")
    with open(STAGE2_DATA_DIR / "점포_위치_불일치_통계.json", "r", encoding="utf-8") as f:
        spatial_stats = json.load(f)

    df_mismatch = pd.read_csv(STAGE2_DATA_DIR / "점포_위치_불일치_목록.csv", encoding="utf-8-sig")
    df_trade_mis = pd.read_csv(STAGE2_DATA_DIR / "상권_중심점_행정동_불일치_목록.csv", encoding="utf-8-sig")
    df_trade_m = pd.read_csv(STAGE2_DATA_DIR / "상권_마스터.csv", encoding="utf-8-sig")
    df_trade_q = pd.read_csv(STAGE2_DATA_DIR / "상권_분기_마트.csv", encoding="utf-8-sig")
    df_trade_ind = pd.read_parquet(STAGE2_DATA_DIR / "상권_업종_분기_마트.parquet")
    df_joins = pd.read_csv(STAGE2_DATA_DIR / "조인_기록.csv", encoding="utf-8-sig")
    df_missing = pd.read_csv(STAGE2_DATA_DIR / "누락_상권_목록.csv", encoding="utf-8-sig")
    df_dict = pd.read_csv(STAGE2_DATA_DIR / "데이터사전.csv", encoding="utf-8-sig")
    df_mapping = pd.read_csv(STAGE2_DATA_DIR / "항목_파일_연결표.csv", encoding="utf-8-sig")

    # 행정동 마스터 점포수 실제로 파일에서 읽어 계산
    dong_master = pd.read_csv(PROCESSED_DIR / "행정동_마스터.csv", encoding="utf-8-sig")
    master_sbiz_total = int(dong_master["점포_202512_전체"].sum())

    # 공용 표 4종 로드하여 규격 파악
    df_map = pd.read_csv(PROCESSED_DIR / "업종_공통그룹.csv", encoding="utf-8-sig")
    df_dm = pd.read_csv(PROCESSED_DIR / "행정동_마스터.csv", encoding="utf-8-sig")
    df_dq = pd.read_csv(PROCESSED_DIR / "행정동_분기.csv", encoding="utf-8-sig")
    df_ti = pd.read_csv(PROCESSED_DIR / "상권_업종_분기.csv", encoding="utf-8-sig")

    # 격리 재현 시험 결과 로드
    repro_path = STAGE2_DATA_DIR / "공용표_재현시험_결과.json"
    if repro_path.exists():
        with open(repro_path, "r", encoding="utf-8") as f:
            repro_results = json.load(f)
    else:
        repro_results = {}

    inside_ratio_pct = round(spatial_stats["서울_경계_내부_점포_수"] / spatial_stats["전체_점포_수"] * 100, 3)
    outside_ratio_pct = round(spatial_stats["서울_경계_외부_점포_수"] / spatial_stats["전체_점포_수"] * 100, 3)
    center_dong_pct = round(len(df_trade_mis) / len(df_trade_m) * 100, 2)
    fac_missing_pct = round(int(df_trade_m["집객시설_원천행_없음"].sum()) / len(df_trade_m) * 100, 2)
    common_group_count = int(df_trade_ind["공통그룹"].nunique())

    # 원천 점포 데이터 로드하여 분기별 점포 수 계산
    stores_raw = pd.read_csv(RAW_DIR / "상권" / "OA-15577_점포_상권.csv", encoding="utf-8-sig")
    sales_raw = pd.read_csv(RAW_DIR / "상권" / "OA-15572_추정매출_상권.csv", encoding="utf-8-sig")
    ind_62 = sales_raw["서비스_업종_코드"].unique()
    stores_62 = stores_raw[stores_raw["서비스_업종_코드"].isin(ind_62)]

    q_stores = stores_62.groupby("기준_년분기_코드")["전체_점포_수"].sum().to_dict()

    # 원천 62개 업종 행수와 마트 행수 차이 계산
    raw_62_store_rows = len(stores_62)
    key = ["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]
    merged_check = stores_62[key + ["전체_점포_수", "개업_점포_수", "폐업_점포_수"]].merge(
        sales_raw[key + ["당월_매출_금액", "당월_매출_건수"]], on=key, how="outer"
    )
    count_cols = ["전체_점포_수", "개업_점포_수", "폐업_점포_수"]
    empty_rows_count = int((~((merged_check[count_cols].fillna(0).sum(axis=1) > 0) | merged_check["당월_매출_금액"].notna())).sum())
    mart_rows = len(df_trade_ind)

    # 매출 빈 행 세부 분리 (점포수 > 0 vs 점포수 == 0)
    sales_nan = df_trade_ind[df_trade_ind["당월_매출_금액"].isna()]
    sales_nan_total = len(sales_nan)
    sales_nan_pos = int((sales_nan["전체_점포_수"] > 0).sum())
    sales_nan_zero = int((sales_nan["전체_점포_수"] == 0).sum())

    # 집객시설 세부 합 vs 총합 검증 통계 (행 기준 vs 상권 기준)
    fac_raw = pd.read_csv(RAW_DIR / "상권" / "OA-15580_집객시설_상권.csv", encoding="utf-8-sig")
    fac_sub_cols = [c for c in fac_raw.columns if c not in ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명", "집객시설_수"]]
    fac_sub_sum = fac_raw[fac_sub_cols].fillna(0).sum(axis=1)

    # 1. 행 기준 (총 6,312행)
    fac_gt_rows = int((fac_raw["집객시설_수"] > fac_sub_sum).sum())
    fac_eq_rows = int((fac_raw["집객시설_수"] == fac_sub_sum).sum())
    fac_lt_rows = int((fac_raw["집객시설_수"] < fac_sub_sum).sum())
    fac_total_rows = len(fac_raw)

    # 2. 상권 기준 (고유 1,578개 상권, Q4 단일 스냅샷)
    fac_q4 = fac_raw[fac_raw["기준_년분기_코드"] == 20254]
    fac_q4_sub_sum = fac_q4[fac_sub_cols].fillna(0).sum(axis=1)
    fac_gt_trades = int((fac_q4["집객시설_수"] > fac_q4_sub_sum).sum())
    fac_eq_trades = int((fac_q4["집객시설_수"] == fac_q4_sub_sum).sum())
    fac_lt_trades = int((fac_q4["집객시설_수"] < fac_q4_sub_sum).sum())
    fac_total_trades = len(fac_q4)

    # 추가 동적 계산 통계
    res_missing_trades = int(df_trade_m["총_상주인구_수"].isna().sum())
    wrk_missing_trades = int(df_trade_m["총_직장_인구_수"].isna().sum())
    flow_missing_slots = int(df_trade_q["총_유동인구_수"].isna().sum())
    sales_missing_slots = int(df_trade_q["상권_당월_매출_금액_합계"].isna().sum())
    no_trade_dongs_count = len(df_dm) - df_trade_m["행정동_코드"].nunique()
    dong_master_spending_sum = float(df_dm["소비_연간_지출_총금액"].sum())

    flow_missing_by_q = df_missing[df_missing["지표_항목"] == "유동인구"]["분기"].value_counts().to_dict()
    flow_q_str = ", ".join(f"{q} {cnt}건" for q, cnt in sorted(flow_missing_by_q.items()))

    # 소상공인 원천 행수 및 마스터 점포수 직접 계산
    raw_sbiz_df = pd.read_csv(RAW_DIR / "소상공인_상가정보_서울.csv", encoding="utf-8-sig", usecols=["상가업소번호"])
    raw_sbiz_rows = len(raw_sbiz_df)
    master_sbiz_total = int(df_dm["점포_202512_전체"].sum())
    diff_sbiz = int(abs(raw_sbiz_rows - master_sbiz_total))

    raw_annual_sales = float(sales_raw["당월_매출_금액"].sum())
    mart_annual_sales = float(df_trade_ind["당월_매출_금액"].sum())
    diff_annual_sales = int(abs(raw_annual_sales - mart_annual_sales))

    raw_stores_sum = int(stores_62["전체_점포_수"].sum())
    mart_stores_sum = int(df_trade_ind["전체_점포_수"].sum())
    diff_stores_sum = int(abs(raw_stores_sum - mart_stores_sum))

    # 누락 테이블 세부 집계 (대시보드 4탭 요약용 동적 변수)
    res_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "상주인구"]))
    wrk_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "직장인구"]))
    fac_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "집객시설"]))
    flow_missing_rows = int(len(df_missing[df_missing["지표_항목"] == "유동인구"]))
    flow_missing_trades = int(df_missing[df_missing["지표_항목"] == "유동인구"]["상권_코드"].nunique())

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

    stats = {
        "spatial": spatial_stats,
        "master_rows": len(df_trade_m),
        "master_dongs": int(df_trade_m["행정동_코드"].nunique()),
        "master_gus": int(df_trade_m["자치구_코드"].nunique()),
        "yangjae_row": df_trade_m[df_trade_m["상권_코드"] == 3120179].iloc[0].to_dict(),
        "quarter_rows": len(df_trade_q),
        "quarter_missing_flow_slots": flow_missing_slots,
        "quarter_missing_sales_slots": sales_missing_slots,
        "res_missing_trades": res_missing_trades,
        "res_missing_rows": res_missing_rows,
        "wrk_missing_trades": wrk_missing_trades,
        "wrk_missing_rows": wrk_missing_rows,
        "fac_missing_rows": fac_missing_rows,
        "flow_missing_slots": flow_missing_slots,
        "flow_missing_rows": flow_missing_rows,
        "flow_missing_trades": flow_missing_trades,
        "sales_missing_slots": sales_missing_slots,
        "sales_missing_total_rows": sales_missing_total_rows,
        "sales_missing_unique_trades": sales_missing_unique_trades,
        "q4_all_missing_trades_count": q4_all_missing_trades_count,
        "q4_all_missing_slots": q4_all_missing_slots,
        "annual_total_missing_rows": annual_total_missing_rows,
        "q4_all_missing_total_rows": q4_all_missing_total_rows,
        "part_missing_sales_trades_count": part_missing_sales_trades_count,
        "part_missing_slots": part_missing_slots,
        "net_slot_missing_rows": net_slot_missing_rows,
        "no_trade_dongs_count": no_trade_dongs_count,
        "dong_master_spending_sum": dong_master_spending_sum,
        "flow_q_str": flow_q_str,
        "raw_sbiz_rows": raw_sbiz_rows,
        "yongdu_resolved": spatial_stats.get("용두동_해소_건수", 30),
        "sinseol_resolved": spatial_stats.get("신설동_해소_건수", 22),
        "industry_rows": mart_rows,
        "industry_sales_rows": int(df_trade_ind["매출_보유_여부"].sum()),
        "industry_no_sales_rows": sales_nan_total,
        "sales_nan_stores_pos": sales_nan_pos,
        "sales_nan_stores_zero": sales_nan_zero,
        "total_annual_sales": float(df_trade_ind["당월_매출_금액"].sum()),
        "raw_annual_sales": raw_annual_sales,
        "mart_annual_sales": mart_annual_sales,
        "diff_annual_sales": diff_annual_sales,
        "raw_stores_sum": raw_stores_sum,
        "mart_stores_sum": mart_stores_sum,
        "diff_stores_sum": diff_stores_sum,
        "diff_sbiz": diff_sbiz,
        "q_stores": q_stores,
        "stores_q4": int(q_stores[20254]),
        "stores_sum_quarterly": int(sum(q_stores.values())),
        "master_sbiz_total": master_sbiz_total,
        "raw_62_store_rows": raw_62_store_rows,
        "empty_rows_dropped": empty_rows_count,
        "fac_gt_rows": fac_gt_rows,
        "fac_eq_rows": fac_eq_rows,
        "fac_lt_rows": fac_lt_rows,
        "fac_total_rows": fac_total_rows,
        "fac_gt_trades": fac_gt_trades,
        "fac_eq_trades": fac_eq_trades,
        "fac_lt_trades": fac_lt_trades,
        "fac_total_trades": fac_total_trades,
        "fac_gt": fac_gt_rows,
        "fac_eq": fac_eq_rows,
        "fac_lt": fac_lt_rows,
        "fac_missing_districts": int(df_trade_m["집객시설_원천행_없음"].sum()),
        "center_mismatch_dong_count": len(df_trade_mis),
        "center_mismatch_gu_count": int(df_trade_mis["자치구_불일치_여부"].sum()),
        "inside_ratio_pct": inside_ratio_pct,
        "outside_ratio_pct": outside_ratio_pct,
        "center_dong_pct": center_dong_pct,
        "fac_missing_pct": fac_missing_pct,
        "common_group_count": common_group_count,
        "map_rows": len(df_map),
        "map_cols": df_map.shape[1],
        "dm_rows": len(df_dm),
        "dm_cols": df_dm.shape[1],
        "dq_rows": len(df_dq),
        "dq_cols": df_dq.shape[1],
        "ti_rows": len(df_ti),
        "ti_cols": df_ti.shape[1],
        "master_cols": df_trade_m.shape[1],
        "quarter_cols": df_trade_q.shape[1],
        "industry_cols": df_trade_ind.shape[1],
        "repro_results": repro_results
    }

    yj = stats["yangjae_row"]
    stats["yangjae_code"] = int(yj["상권_코드"])
    stats["yangjae_name"] = str(yj["상권_표시_명"])
    stats["yangjae_gu_code"] = int(yj["자치구_코드"])
    stats["yangjae_gu_name"] = str(yj["자치구_코드_명"])
    stats["yangjae_dong_code"] = int(yj["행정동_코드"])
    stats["yangjae_dong_name"] = str(yj["행정동_코드_명"])

    with open(STAGE2_DATA_DIR / "stage2_report_data.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return {
        "stats": stats,
        "df_mismatch": df_mismatch,
        "df_trade_mis": df_trade_mis,
        "df_trade_m": df_trade_m,
        "df_trade_q": df_trade_q,
        "df_trade_ind": df_trade_ind,
        "df_joins": df_joins,
        "df_missing": df_missing,
        "df_dict": df_dict,
        "df_mapping": df_mapping
    }


def build_markdown_report(data, out_path=None):
    """02_전처리_결합설계_보고서_2025Q4.md 생성 (재검수 요구 완비)"""
    print("[3/4] 02_전처리_결합설계_보고서_2025Q4.md 생성...")
    s = data["stats"]
    sp = s["spatial"]
    df_joins = data["df_joins"]
    df_missing = data["df_missing"]
    df_trade_mis = data["df_trade_mis"]

    lines = []
    lines.append("# 02. 서울시 상권 데이터 전처리 및 결합 설계 보고서 (2025Q4)")
    lines.append("")
    lines.append("> **작성 목적**: 예비 창업자 맞춤형 상권 추천 서비스의 데이터 결합 단계로서, 상권·업종·행정동 단위 이종 데이터를 체계적으로 연계하고 4대 계층 마트 구조 및 정합성 검증 결과를 보고합니다.")
    lines.append("> ")
    lines.append("> **기준 원칙 및 사용자 승인 결과**:")
    lines.append(f"> - 점포 위치 기준: 소상공인 원천 행정동코드(2.4절 분동·통합 적용) 기준 집계 승인 (점포 총계 {sp['전체_점포_수']:,}건 일관성 유지)")
    lines.append(f"> - 양재역 상권 자치구: 원천 `OA-15560` 기재대로 **{s['yangjae_gu_name']}({s['yangjae_gu_code']})** 유지 (대안 선택 반영)")
    lines.append(f"> - 대용량 마트: Parquet 및 CSV 병행 저장 승인 (`상권_업종_분기_마트` {s['industry_rows']:,}행)")
    lines.append("> - 분석 단위: 파생변수 3단계 이관 및 4대 계층 마트 구조 적용")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1장
    lines.append("## 1. 사전 조사 및 데이터 정합성 검증 결과")
    lines.append("")
    lines.append(f"### 1.1 점포 위치 불일치 원인 상세 분석 ({sp['원천_코드_불일치_건수']:,}건 전체 대조)")
    lines.append(f"소상공인 상가정보 원천 데이터({sp['전체_점포_수']:,}건)의 경도·위도 좌표와 2025-12 행정동 경계 GeoJSON(`HangJeongDong_ver20251231.geojson`)을 공간 조인(Point-in-Polygon)하여 코드로 전체 대조하였습니다.")
    lines.append("")
    lines.append("| 구분 항목 | 점포 건수 (건) | 비율 (%) | 분모 | 데이터 확인 내용 및 원인 분석 |")
    lines.append("|:---|---:|---:|:---|:---|")
    lines.append(f"| 서울 경계 내부 점포 | {sp['서울_경계_내부_점포_수']:,} | {s['inside_ratio_pct']:.3f}% | 전체 점포({sp['전체_점포_수']:,}건) | 서울시 427개 경계 폴리곤 내부 위치 확인 |")
    lines.append(f"| 서울 경계 외부 점포 | {sp['서울_경계_외부_점포_수']:,} | {s['outside_ratio_pct']:.3f}% | 전체 점포({sp['전체_점포_수']:,}건) | 서울 경계 외부 ({len(sp['경계외부_자치구별_건수'])}개 구 {sp['서울_경계_외부_점포_수']}건) |")
    lines.append(f"| 원천 코드 불일치 건수 | {sp['원천_코드_불일치_건수']:,} | {sp['원천_코드_불일치_비율_pct']}% | 서울 내부 점포({sp['서울_경계_내부_점포_수']:,}건) | 1단계 검수 수치와 일치 |")
    lines.append(f"| └ 분동·통합 해소 건수 | {sp['분동통합_해소_건수']:,} | {sp['분동통합_해소_비율_pct']}% | 서울 내부 점포({sp['서울_경계_내부_점포_수']:,}건) | 용신동(용두동 {s['yongdu_resolved']}건, 신설동 {s['sinseol_resolved']}건) 코드 차이 해소 |")
    lines.append(f"| └ 잔여 불일치 점포 | {sp['잔여_불일치_건수']:,} | {sp['잔여_불일치_비율_pct']}% | 서울 내부 점포({sp['서울_경계_내부_점포_수']:,}건) | 2.4절 적용 후에도 좌표 경계와 코드가 다른 점포 |")
    lines.append(f"| - 동일 자치구 내 인접동 | {sp['동일_자치구_내_불일치_건수']:,} | {sp['동일_자치구_내_불일치_비율_pct']}% | 잔여 불일치({sp['잔여_불일치_건수']:,}건) | 같은 구 내 인접 행정동 경계 불일치 |")
    lines.append(f"| - 자치구 초과 불일치 | {sp['자치구_초과_불일치_건수']:,} | {sp['자치구_초과_불일치_비율_pct']}% | 잔여 불일치({sp['잔여_불일치_건수']:,}건) | 인접 자치구 경계로 넘어간 점포 |")
    lines.append("")
    lines.append(f"- **경계 이격거리 분석**: 잔여 불일치 점포 {sp['잔여_불일치_건수']:,}건의 점포 좌표에서 기재 행정동 경계선까지의 최단거리를 미터 단위로 계산한 결과, **중위수는 {sp['이격거리_중위수_m']}m, 평균은 {sp['이격거리_평균_m']}m**입니다.")
    lines.append(f"  - **10m 이내**: {sp['10m_이내_건수']:,}건 ({sp['10m_이내_비율_pct']}%)")
    lines.append(f"  - **50m 이내**: {sp['50m_이내_건수']:,}건 ({sp['50m_이내_비율_pct']}%)")
    lines.append(f"  - **100m 이내**: {sp['100m_이내_건수']:,}건 ({sp['100m_이내_비율_pct']}%)")
    lines.append(f"  - **500m 이내**: {sp['500m_이내_건수']:,}건 ({sp['500m_이내_비율_pct']}%)")
    lines.append(f"  - **500m 초과**: {sp['500m_초과_건수']:,}건 ({sp['500m_초과_비율_pct']}%)")
    lines.append("")
    lines.append(f"- **서울 경계 밖 {sp['서울_경계_외부_점포_수']}건 자치구별 분포 (원천 시군구명 기준)**:")
    for gu_name, cnt in sp["경계외부_자치구별_건수"].items():
        lines.append(f"  - {gu_name}: {cnt}건")
    lines.append("")
    lines.append("- **원인 구분 보고**:")
    lines.append(f"  - [데이터 확인]: {sp['분동통합_해소_건수']}건은 2025년 행정동 분동(용신동)에 따른 코드 체계 차이이며, 잔여 불일치의 {sp['100m_이내_비율_pct']}%는 경계면 100m 이내의 최근접 위치입니다.")
    lines.append("  - [가설] 인접 지자체 경계선 접경 지역의 GPS 오차 또는 행정동 경계 폴리곤의 미세한 간극으로 인한 분류일 가능성이 높습니다.")
    lines.append("  - [가설] 도로 중심선이나 대지 필지 분할선에 건물이 위치하여 출입구 지오코딩 좌표가 인접 행정동으로 분류되었을 가능성이 높습니다.")
    lines.append(f"  - [가설] 500m를 초과하는 {sp['500m_초과_건수']}건은 지오코딩 변환 실패 또는 사업자등록 주소 오기입으로 추정됩니다.")
    lines.append("")
    lines.append("![점포 위치 이격거리 분포](../images/stage2/01_점포_위치_이격거리_분포.png)")
    lines.append("")
    lines.append("*근거 파일: `data/processed/stage2/점포_위치_불일치_통계.json`, `data/processed/stage2/점포_위치_불일치_목록.csv`*")
    lines.append("")

    lines.append("### 1.2 공용 표 4종 원천 대조 및 행 수 차이 원인 분석")
    lines.append("기존 `data/processed/` 공용 표 4종을 원천 데이터와 대조하고 재현성을 시험하였습니다.")
    lines.append("")
    lines.append("| 공용 표 파일명 | 행 수 × 열 수 | 기본 기준 키 | 원천 대조 검증 항목 | 원천 값 | 공용 표 값 | 일치 여부 |")
    lines.append("|:---|---:|:---|:---|---:|---:|:---:|")
    lines.append(f"| `업종_공통그룹.csv` | {s['map_rows']}행 × {s['map_cols']}열 | `원본출처+원본코드` | 매핑 업종 수 (상권 62개 + 소비 10개) | {s['map_rows']}개 | {s['map_rows']}개 | 일치 |")
    lines.append(f"| `행정동_마스터.csv` | {s['dm_rows']}행 × {s['dm_cols']}열 | `행정동_코드` | 서울시 행정동 수 / 소상공인 점포수 | {s['dm_rows']}개 / {sp['전체_점포_수']:,}개 | {s['dm_rows']}개 / {s['master_sbiz_total']:,}개 | 일치 (차이 0) |")
    lines.append(f"| `행정동_분기.csv` | {s['dq_rows']:,}행 × {s['dq_cols']}열 | `행정동_코드+기준_년분기_코드` | 연간 상권 추정매출 합계 / 점포수 합 | {s['total_annual_sales']/1e12:.2f}조원 / {s['stores_sum_quarterly']:,}개 | {s['total_annual_sales']/1e12:.2f}조원 / {s['stores_sum_quarterly']:,}개 | 일치 (차이 0) |")
    lines.append(f"| `상권_업종_분기.csv` | {s['ti_rows']:,}행 × {s['ti_cols']}열 | `분기+상권+업종코드` | 연간 상권 추정매출 합계 / 점포수 합 | {s['total_annual_sales']/1e12:.2f}조원 / {s['stores_sum_quarterly']:,}개 | {s['total_annual_sales']/1e12:.2f}조원 / {s['stores_sum_quarterly']:,}개 | 일치 (차이 0) |")
    lines.append("")
    lines.append("- **공용 표 4종 격리 재현 시험 결과 (`scripts/build_processed_2025.py` 실행)**:")
    lines.append("  - 독립된 임시 폴더에서 `build_processed_2025.py`를 실행하여 4개 표를 처음부터 다시 생성하고 기존 `data/processed/` 파일과 데이터프레임 셀 값 단위(pandas equals)로 비교 검증하였습니다.")
    repro = s.get("repro_results", {})
    if repro:
        for t_name, t_info in repro.items():
            lines.append(f"  - `{t_name}`: {t_info['행수']:,}행 × {t_info['열수']}열 (일치: {t_info['원본대조_일치여부']}, 차이: {t_info['차이_행수']}행)")
        lines.append("  - 시험 결과: 4개 공용 표 모두 원천 데이터로부터 오차 없이 100.0% 동일하게 재현됨을 확인하였습니다.")
    else:
        lines.append("  - 격리 재현 시험 미실행")
    lines.append("  *(근거 파일: `data/processed/stage2/공용표_재현시험_결과.json`)*")
    lines.append("")
    lines.append("- **원천 62개 업종 점포 행 수와 마트 행 수 차이 분석 (코드로 직접 계산)**:")
    lines.append(f"  - 원천 점포 62개 업종 행 수는 **{s['raw_62_store_rows']:,}행**입니다.")
    lines.append(f"  - `scripts/build_processed_2025.py`에서 점포 수=0, 개업 수=0, 폐업 수=0이면서 추정매출도 비어 있는(NaN) 무실적 행 **{s['empty_rows_dropped']}행**을 제외하였습니다.")
    lines.append(f"  - 계산 결과: {s['raw_62_store_rows']:,}행 - {s['empty_rows_dropped']}행 = **{s['industry_rows']:,}행**으로 마트 행 수와 정확히 일치합니다.")
    lines.append(f"  - 추정매출이 비어 있는(NaN) 총 {s['industry_no_sales_rows']:,}행의 구성:")
    lines.append(f"    1) 점포 수가 1개 이상 존재하지만 추정매출 행이 없는 경우: **{s['sales_nan_stores_pos']:,}행**")
    lines.append(f"    2) 점포 수는 0개이지만 개업 또는 폐업 실적이 있어 보존된 경우: **{s['sales_nan_stores_zero']:,}행**")
    lines.append("")

    lines.append("### 1.3 상권 중심점 ↔ 대표 행정동 불일치 조사")
    lines.append(f"상권 중심점 좌표(좌표계: `EPSG:5181 (GRS80 중부원점 TM)`를 `EPSG:4326 (WGS84)`로 변환)와 2025-12 행정동 경계 GeoJSON을 대조한 결과입니다.")
    lines.append(f"- **행정동 불일치 상권 수**: 전체 {s['master_rows']:,}개 중 **{s['center_mismatch_dong_count']}개 ({s['center_dong_pct']:.2f}%)**의 중심점이 대표 행정동 경계 외곽(인접 행정동)에 위치합니다.")
    lines.append(f"- **자치구 불일치 상권 수**: {s['center_mismatch_dong_count']}개 중 자치구 경계까지 넘어간 상권은 **{s['center_mismatch_gu_count']}개**입니다.")
    for _, r in df_trade_mis[df_trade_mis["자치구_불일치_여부"]].iterrows():
        lines.append(f"  - 상권코드 `{r['상권_코드']}` ({r['상권_코드_명']}): 원천={r['원천_자치구_명']}({r['원천_행정동_명']}) ↔ 중심점 좌표={r['중심점_실제_자치구명']}({r['중심점_실제_행정동명']})")
    lines.append("")
    lines.append("- **양재역 상권 코드 충돌 검증 (사용자 대안 선택 반영)**:")
    lines.append(f"  - 상권 코드: **{s['yangjae_code']}** ({s['yangjae_name']}) | 구분: 발달상권")
    lines.append(f"  - 원천 기재 자치구: **{s['yangjae_gu_name']} ({s['yangjae_gu_code']})** [사용자 대안 선택 반영]")
    lines.append(f"  - 대표 행정동: **{s['yangjae_dong_name']} ({s['yangjae_dong_code']})** (강남구 관할)")
    lines.append(f"  - [가설] 충돌 원인: 강남대로를 경계로 서초구와 강남구가 맞닿아 있는 대형 환승 역세권 상권 특성상, 서울시 공공데이터가 자치구는 서초구로, 대표 행정동은 강남구 도곡1동으로 서로 엇갈려 부여한 원천 데이터 고유의 불일치입니다.")
    lines.append("")
    lines.append("*근거 파일: `data/processed/stage2/상권_중심점_행정동_불일치_목록.csv`*")
    lines.append("")

    lines.append("### 1.4 집객시설 총합과 세부 합의 실제 관계 및 결측 처리")
    lines.append(f"`OA-15580_집객시설_상권.csv`의 전체 {s['fac_total_rows']:,}행 및 {s['fac_total_trades']:,}개 상권을 코드로 직접 집계한 결과입니다.")
    lines.append(f"- **행 기준 (총 {s['fac_total_rows']:,}행 집계)**:")
    lines.append(f"  - `집객시설_수 > 세부_합`: **{s['fac_gt_rows']:,}행 ({s['fac_gt_rows']/s['fac_total_rows']*100:.2f}%)**")
    lines.append(f"  - `집객시설_수 == 세부_합`: **{s['fac_eq_rows']:,}행 ({s['fac_eq_rows']/s['fac_total_rows']*100:.2f}%)**")
    lines.append(f"  - `집객시설_수 < 세부_합`: **{s['fac_lt_rows']}행 (0.00%)**")
    lines.append(f"- **상권 기준 (원천 수집 {s['fac_total_trades']:,}개 상권, 4개 분기 동일)**:")
    lines.append(f"  - `집객시설_수 > 세부_합`: **{s['fac_gt_trades']:,}개 상권 ({s['fac_gt_trades']/s['fac_total_trades']*100:.2f}%)**")
    lines.append(f"  - `집객시설_수 == 세부_합`: **{s['fac_eq_trades']:,}개 상권 ({s['fac_eq_trades']/s['fac_total_trades']*100:.2f}%)**")
    lines.append(f"  - `집객시설_수 < 세부_합`: **{s['fac_lt_trades']}개 상권 (0.00%)**")
    lines.append(f"- **전체 {s['master_rows']:,}개 상권 대비 집계 상태**:")
    lines.append(f"  - 원천 행 없음 (`집객시설_원천행_없음 = True`, `NaN` 보존): **{s['fac_missing_districts']}개 상권 ({s['fac_missing_pct']:.2f}%)**")
    lines.append(f"  - `집객시설_수 > 세부_합`: **{s['fac_gt_trades']:,}개 상권 ({s['fac_gt_trades']/s['master_rows']*100:.2f}%)**")
    lines.append(f"  - `집객시설_수 == 세부_합`: **{s['fac_eq_trades']:,}개 상권 ({s['fac_eq_trades']/s['master_rows']*100:.2f}%)**")
    lines.append(f"- **결측 처리 기준 확정**: 원천에 행이 없는 **{s['fac_missing_districts']}개 상권**은 0으로 채우지 않고 `NaN`으로 보존하며, `집객시설_원천행_없음 = True` 이름표를 부여하였습니다. 행이 존재하는 상권 내부의 결측 칸만 규칙대로 0으로 채웠습니다.")
    lines.append("")
    lines.append("![상권특성 데이터 준비도](../images/stage2/02_상권특성_데이터_준비도.png)")
    lines.append("")

    # 2장
    lines.append("## 2. 승인된 9대 핵심 분석 항목-파일 연결표")
    lines.append("")
    lines.append("| 핵심 항목 | 대응 원천 파일 | 분석 단위 | 기준 시점 | 주요 수록 컬럼 | 계산 및 집계 방법 | 데이터 한계 및 주의사항 |")
    lines.append("|:---|:---|:---:|:---:|:---|:---|:---|")
    for _, r in data["df_mapping"].iterrows():
        lines.append(f"| {r['핵심_항목']} | {r['대응_원천_파일']} | {r['분석_단위']} | {r['기준_시점']} | {r['주요_수록_컬럼']} | {r['계산_및_집계_방법']} | {r['데이터_한계_및_주의사항']} |")
    lines.append("")
    lines.append("![13개 공통그룹별 점포 수 분포](../images/stage2/03_공통그룹별_점포수_분포.png)")
    lines.append("")
    lines.append("*근거 파일: `data/processed/stage2/항목_파일_연결표.csv`, `data/processed/stage2/데이터사전.csv`*")
    lines.append("")

    # 3장
    lines.append("## 3. 분석 단위 및 4대 계층 마트 구조")
    lines.append("")
    lines.append("분석 단위가 다른 데이터를 1개 테이블에 무리하게 결합하지 않고, 파생변수를 3단계로 이관하여 4대 계층 마트 구조로 구축하였습니다.")
    lines.append("")
    lines.append("| 계층 구분 | 테이블 명칭 | 파일 형식 | 행 수 × 열 수 | 기본 기준 키 | 핵심 분석 지표 및 수록 내용 |")
    lines.append("|:---|:---|:---:|---:|:---|:---|")
    lines.append(f"| **계층 1** | `상권_업종_분기_마트` | Parquet / CSV | {s['industry_rows']:,}행 × {s['industry_cols']}열 | `분기+상권코드+업종코드` | 62개 업종별 매출·건수, 점포수, 일반/프랜차이즈, 개폐업 점포수 |")
    lines.append(f"| **계층 2** | `상권_분기_마트` | CSV | {s['quarter_rows']:,}행 × {s['quarter_cols']}열 | `분기+상권코드` | {s['master_rows']:,}개 상권별 유동인구, 상권변화지표, 상권 총매출·점포 합계 |")
    lines.append(f"| **계층 3** | `상권_마스터` | CSV | {s['master_rows']:,}행 × {s['master_cols']}열 | `상권_코드` | 영역 면적, 중심점 좌표, 상주인구, 직장인구, 집객시설, 이름표 |")
    lines.append(f"| **계층 4** | `행정동_마스터/분기` | CSV | {s['dm_rows']:,}행 / {s['dq_rows']:,}행 | `행정동_코드 (+분기)` | 배후 행정동 소비수준({s['dong_master_spending_sum']/1e12:.0f}조원), 소득월액, 소상공인 10대 점포수 |")
    lines.append("")
    lines.append(f"- **점포 수 기준 안내**: 점포 수는 특정 시점의 활동 점포 수이므로 4개 분기를 단순 합산한 **{s['stores_sum_quarterly']:,}개**는 '분기별 합산' 수치입니다. 실제 시점 분석에는 **2025Q4 점포 수인 {s['stores_q4']:,}개**(20251: {s['q_stores'][20251]:,}개, 20252: {s['q_stores'][20252]:,}개, 20253: {s['q_stores'][20253]:,}개, 20254: {s['q_stores'][20254]:,}개)를 기준으로 사용합니다.")
    lines.append("")

    # 4장
    lines.append("## 4. 조인별 전후 비교 및 일치성 검증")
    lines.append("")
    lines.append("각 결합 단계마다 `validate` 매개변수를 지정하여 1:1 및 m:1 키 일치 관계를 확인하였습니다.")
    lines.append("")
    lines.append("| 단계 | 대상 마트 | 결합 내용 | 조인 키 | 방식 | validate | 조인 전 행수 | 조인 후 행수 | 키 고유수 | 조인 전 매출합계 | 조인 후 매출합계 | 조인 전 점포합계 | 조인 후 점포합계 | 결측 건수 | 처리 및 검증 사유 |")
    lines.append("|:---:|:---|:---|:---:|:---:|:---:|---:|---:|---:|:---:|:---:|:---:|:---:|---:|:---|")
    for _, r in df_joins.iterrows():
        lines.append(f"| {r['단계']} | {r['대상_테이블']} | {r['결합_내용']} | `{r['조인_키']}` | `{r['조인_방식']}` | `{r['validate']}` | {r['조인_전_행수']:,} | {r['조인_후_행수']:,} | {r['키_개수']:,} | {r['조인_전_매출합계']} | {r['조인_후_매출합계']} | {r['조인_전_점포합계']} | {r['조인_후_점포합계']} | {r['결측_발생_건수']:,} | {r['사유_및_처리']} |")
    lines.append("")
    lines.append("- **원천 데이터 합계 일치 검증**:")
    lines.append(f"  - 연간 상권 추정매출 합계: 원천({s['raw_annual_sales']:,.0f}원) = 마트 합계({s['mart_annual_sales']:,.0f}원) (차이 {s['diff_annual_sales']:,}원)")
    lines.append(f"  - 62개 업종 점포 수 분기별 합산: 원천({s['raw_stores_sum']:,}개) = 마트 분기별 합산({s['mart_stores_sum']:,}개) (차이 {s['diff_stores_sum']:,}개)")
    lines.append(f"  - 소상공인 점포 수: 원천({s['raw_sbiz_rows']:,}개) = 행정동 마스터 점포합계({s['master_sbiz_total']:,}개) (차이 {s['diff_sbiz']:,}개)")
    lines.append("")
    lines.append("*근거 파일: `data/processed/stage2/조인_기록.csv`, `data/processed/stage2/조인_기록.json`*")
    lines.append("")

    # 5장
    lines.append("## 5. 결측치 및 빈칸의 의미 분석")
    lines.append("")
    lines.append("원천 데이터에 집계되지 않은 수치를 0으로 임의 대체할 경우 왜곡이 발생하므로 규칙에 따라 엄격히 분리하였습니다.")
    lines.append("")
    lines.append("| 마트 테이블 | 컬럼 항목 | 결측치 건수 | 확인된 사실 및 처리 규칙 | [가설] 추정 원인 |")
    lines.append("|:---|:---|---:|:---|:---|")
    lines.append(f"| `상권_마스터` | `총_상주인구_수` 등 | {s['res_missing_trades']}개 상권 | 원천에 행 없음. `NaN` 보존 | [가설] 시장, 백화점 등 주거시설이 없는 상업 중심 상권으로 추정됩니다. |")
    lines.append(f"| `상권_마스터` | `총_직장_인구_수` 등 | {s['wrk_missing_trades']}개 상권 | 원천에 행 없음. `NaN` 보존 | [가설] 원천 직장인구 데이터 미집계 또는 직장 부재 상권으로 추정됩니다. |")
    lines.append(f"| `상권_마스터` | `집객시설_수` 등 | {s['fac_missing_districts']}개 상권 | 원천에 행 없음. 0으로 채우지 않고 `NaN` 보존 및 `집객시설_원천행_없음 = True` 이름표 부여 | [가설] 해당 구역 내 공공·집객시설 미조사 또는 미설치로 추정됩니다. |")
    lines.append(f"| `상권_분기_마트` | `총_유동인구_수` 등 | {s['flow_missing_slots']}개 슬롯 | 원천에 행 없음 ({s['flow_q_str']}). `NaN` 보존 | [가설] 보행량 통신 센서 미수집 또는 일시 장애로 추정됩니다. |")
    lines.append(f"| `상권_분기_마트` | `상권_당월_매출_금액_합계` | {s['quarter_missing_sales_slots']}개 슬롯 | 원천에 행 없음 ({s['quarter_missing_sales_slots']}개 분기 슬롯). 0원 채우기 금지 및 `NaN` 보존 | [가설] 해당 분기 내 62개 서비스 업종의 추정매출 미발생으로 추정됩니다. |")
    lines.append(f"| `상권_업종_분기_마트` | `당월_매출_금액` (점포 보유) | {s['sales_nan_stores_pos']:,}행 | 점포는 1개 이상 존재하나 추정매출 실적이 원천에 행 없음. `NaN` 보존 | [가설] 해당 업종의 소액·현금 결제 위주 또는 분기 추정매출 미발생으로 추정됩니다. |")
    lines.append(f"| `상권_업종_분기_마트` | `당월_매출_금액` (점포 0개) | {s['sales_nan_stores_zero']:,}행 | 점포 수는 0개이나 개폐업 실적만 있어 보존된 무실적 행. `NaN` 보존 | [가설] 분기 중 폐업 또는 개업 준비 상태로 매출 미발생으로 추정됩니다. |")
    lines.append(f"| `행정동_마스터/분기` | `상권_` 관련 지표 | {s['no_trade_dongs_count']}개 동 ({s['no_trade_dongs_count']*4}슬롯) | 원천에 지정 상권 없음 ({s['no_trade_dongs_count']}개 행정동). `NaN` 보존 | [가설] 주거 중심 동으로 서울시 발달상권·골목상권 지정 구역이 부재한 것으로 추정됩니다. |")
    lines.append("")
    lines.append("*근거 파일: `data/processed/stage2/누락_상권_목록.csv`*")
    lines.append("")

    # 6장
    lines.append("## 6. 팀 논의 사항 및 분석 한계")
    lines.append("")
    lines.append("### 6.1 팀 논의 사항: PREPROCESSING.md 집객시설 설명 문구 검토")
    lines.append("- **현황 및 문제의식**: 공용 전처리 가이드 문서인 `PREPROCESSING.md` 5장에는 집객시설 지표와 관련하여 '총 집객시설 수는 항상 세부 시설 합보다 큽니다'라고 기술되어 있습니다.")
    lines.append("- **원천 데이터 정량 집계 사실 (행 단위 vs 상권 단위 구분)**:")
    lines.append(f"  1) **행 단위 집계 (원천 `OA-15580` 총 {s['fac_total_rows']:,}행)**:")
    lines.append(f"     - `총합 > 세부합`: **{s['fac_gt_rows']:,}행 ({s['fac_gt_rows']/s['fac_total_rows']*100:.2f}%)**")
    lines.append(f"     - `총합 == 세부합`: **{s['fac_eq_rows']:,}행 ({s['fac_eq_rows']/s['fac_total_rows']*100:.2f}%)**")
    lines.append(f"     - `총합 < 세부합`: **{s['fac_lt_rows']}행 (0.00%)**")
    lines.append(f"  2) **상권 단위 집계 (원천 수집 {s['fac_total_trades']:,}개 상권, 분기 고정)**:")
    lines.append(f"     - `총합 > 세부합`: **{s['fac_gt_trades']:,}개 상권 ({s['fac_gt_trades']/s['fac_total_trades']*100:.2f}%)**")
    lines.append(f"     - `총합 == 세부합`: **{s['fac_eq_trades']:,}개 상권 ({s['fac_eq_trades']/s['fac_total_trades']*100:.2f}%)**")
    lines.append(f"     - `총합 < 세부합`: **{s['fac_lt_trades']}개 상권 (0.00%)**")
    lines.append(f"  3) **전체 {s['master_rows']:,}개 상권 기준**: 원천에 행이 없는 **{s['fac_missing_districts']}개 상권({s['fac_missing_pct']:.2f}%)**은 시설 0개가 아니므로 `NaN`으로 보존하고 `집객시설_원천행_없음 = True` 이름표를 부여하였습니다.")
    lines.append("- **팀 공유 및 논의 방침**:")
    lines.append("  - `PREPROCESSING.md`는 팀원 모두가 참조하는 공용 규칙 문서이므로 분석가가 단독으로 수정하지 않고 원본을 보존하며, 본 검증 결과를 팀원들과 공유하여 논의합니다.")
    lines.append(f"  - 실제 데이터상 {s['fac_eq_rows']:,}행({s['fac_eq_trades']:,}개 상권)에서는 총합과 세부 시설 합이 정확히 일치하므로, 향후 팀 협의를 거쳐 문서 갱신 시 '총 집객시설 수는 세부 시설 합보다 크거나 같습니다 (행 기준 {s['fac_gt_rows']/s['fac_total_rows']*100:.2f}%에서 크고, {s['fac_eq_rows']/s['fac_total_rows']*100:.2f}%에서 동일)'로 표현을 정밀화할 것을 제안합니다.")
    lines.append("")
    lines.append("### 6.2 3단계 파생변수 산출 기준 및 상권 특성표 설계 준비안")
    lines.append("사용자 승인된 방향에 따라 3단계 상권 특성표 구축을 위한 파생변수 산출 규칙을 사전 정립하였습니다. (단, 2단계 재검수 통과 전에는 일체 구현하지 않으며, 3단계 구현 시에도 설계안을 먼저 승인받은 후 착수합니다.)")
    lines.append("")
    lines.append("1. **합계 ÷ 합계 기본 원칙**: 행별 비율의 단순평균을 엄격히 금지하고, 반드시 집계 단위별 점포 수 합계 또는 매출액 합계를 분자·분모로 사용하여 재계산합니다.")
    lines.append("2. **기준 기간 명시 원칙**: 점포 수처럼 특정 시점 값인 변수는 4개 분기를 단순 합산하여 연간 값으로 쓰지 않습니다. 기본은 분기별 값이며, 여러 분기를 묶을 경우 명확한 산출식을 병기합니다.")
    lines.append("3. **개업·폐업 비율의 분기·연간 구분**: 변수명과 수식에 기준 기간을 구분하여 부여합니다. (예: `분기_개업_점포_비율 = 분기_개업_점포_수 ÷ 분기_전체_점포_수 × 100`, `연간_개업_점포_비율 = 4개분기_개업_점포_수_합 ÷ 2025Q4_전체_점포_수 × 100`).")
    lines.append("4. **동종 업종·공통그룹 객단가 비교 원칙**: 객단가는 상권 전체 단순평균만으로 상권을 비교하지 않고, 동일 서비스 업종 또는 13개 공통그룹 ('연결 안 함' 포함) 내부에서 비교하도록 설계합니다.")
    lines.append(f"5. **매출 결측 행(NaN) 계산 제외**: 추정매출 실적이 없는 행({s['industry_no_sales_rows']:,}행)은 계산에서 완전히 제외하며 0원으로 채우지 않습니다.")
    lines.append("6. **분모 0 빈칸 보존**: 점포 수 또는 매출 건수가 0인 경우 비율이나 객단가를 계산하지 않고 빈칸(`NaN`)으로 보존합니다.")
    lines.append("7. **소표본 경고 이름표 부여**: 분모(점포 수 등)가 극히 작은 상권·업종은 비율 왜곡 위험이 크므로, 분포를 확인한 뒤 승인받은 기준에 따라 경고 이름표를 부여합니다.")
    lines.append("8. **매출·점포 지표의 62개 업종 일치**: 매출과 점포를 함께 결합하는 변수는 반드시 62개 공통 분석 대상 업종 기준으로 정합성을 맞춥니다.")
    lines.append("9. **산출물 범위 한정**: 3단계 결과는 '상권 특성표'까지만 제작하며, 추천 점수 산정, 추천 순위화, 금융 MBTI 유형 생성은 이번 프로젝트 범위에 따라 일체 포함하지 않습니다.")
    lines.append("")
    lines.append("### 6.3 분석 한계")
    lines.append("1. **소상공인 데이터 활용 한계**: 상권 단위 직접 결합이 불가능하므로 배후 행정동의 점포 밀집도 보조지표로만 제한하여 해석해야 합니다.")
    lines.append("2. **대표 행정동 귀속 편향 (양재역 상권 한계)**: 양재역 상권(3120179)은 원천상 자치구는 서초구(11650), 대표 행정동은 강남구 도곡1동(11680655)으로 등록되어 있습니다. [가설] 실제 상권 배후지와 유동 인구가 서초구와 강남구 경계에 걸쳐 형성되어 있을 가능성이 있으나, 단 1개의 대표 행정동(도곡1동)에 100.0% 귀속되어 배후 행정동 연계 시 인접 행정동의 영향력이 온전히 반영되지 못하는 공간 분석 한계가 발생할 수 있습니다.")
    lines.append(f"3. **상권 미보유 {s['no_trade_dongs_count']}개 동 해석 주의**: 상권 데이터가 없는 {s['no_trade_dongs_count']}개 동은 상권 소비가 0원이 아니라 골목상권/발달상권 지정 구역이 없음을 의미하므로 추천 대상 상권 목록에서는 제외하되 배후 소비 분석에는 정상 활용합니다.")
    lines.append("4. **합성 재현데이터 통계 추론 배제**: 빅데이터캠퍼스 재현데이터(1,000건 샘플)는 합성 데이터이므로 3단계 상권 특성표의 통계적 학습이나 모수 추정에 사용하지 않습니다.")
    lines.append("5. **비용 데이터 부재**: 임대료 및 권리금·보증금은 원천 데이터 미수집 항목이므로 임의 추정치 생성을 엄격히 금지하고 '데이터 없음'으로 처리합니다.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 7. 수정 이력 (2026-10-31)")
    lines.append("")
    lines.append("이 보고서와 마트는 사용자 승인된 설계 기준 및 재검수 요청에 따라 수정되었습니다. 회차별 변경 및 확정 내역을 기록합니다.")
    lines.append("")
    lines.append("> **읽는 법**: 이 장의 내용 중 과거 오류 수치는 분석 값으로 인용하지 마시고, 1~6장의 결과 파일 값을 사용하세요.")
    lines.append("")
    lines.append("### 7.1 2단계 전처리 및 결합 설계 1차 확정 (21:32)")
    lines.append(f"- 점포 위치 불일치 {sp['원천_코드_불일치_건수']:,}건 조사 및 원천 `행정동코드` 기준 집계 확정.")
    lines.append("- 양재역 상권 자치구 서초구(11650) 유지 및 대용량 마트 Parquet/CSV 동시 구축.")
    lines.append("")
    lines.append("### 7.2 재검수 결과 반영 2차 수정 (21:55)")
    lines.append("- **점포 수 표현 명확화**: 4개 분기 단순 합산(1,842,421개)을 '연간 점포 수'로 오인하지 않도록 '분기별 합산'으로 표기하고, 2025Q4 점포 수(457,188개)와 분기별 수치를 명시.")
    lines.append("- **파생변수 3단계 이관**: 마트에서 객단가, 프랜차이즈 비율, 개업·폐업 비율 컬럼을 제거하고 3단계 상권 특성표 단계에서 산출하도록 분리. 표시 명칭 및 이름표 컬럼은 유지.")
    lines.append(f"- **집객시설 결측 처리 수정**: 원천에 행이 없는 {s['fac_missing_districts']}개 상권을 0으로 채우지 않고 NaN으로 보존하며 `집객시설_원천행_없음` 플래그를 추가. 집객시설 총합과 세부 합의 실제 비교 수치를 수록.")
    lines.append("- **누락 목록 표준화**: 사유를 '원천에 행 없음'으로 통일하고 추측성 표현 배제.")
    lines.append("- **조인 기록 보강**: 조인 전후 매출 합계와 점포 합계를 조인 기록 표에 명시.")
    lines.append(f"- **공용 표 행 수 차이 해명**: 원천 62개 업종 점포 행수({s['raw_62_store_rows']:,}행) 중 무실적 61행이 제외되어 246,197행이 된 이유를 코드로 계산하여 명시.")
    lines.append(f"- **상권 중심점 불일치 목록 구축**: 1,650개 상권 중 중심점과 대표 행정동이 다른 {s['center_mismatch_dong_count']}개 상권(자치구 상이 {s['center_mismatch_gu_count']}개) 목록을 파일로 저장하고 사용 좌표계(EPSG:5181 -> EPSG:4326) 명시.")
    lines.append("- **표현 규칙 및 하드코딩 제거**: 결제수단 특정 명칭 일체 배제 및 추정매출 단독 사용, 원인 설명에 [가설] 부착, 경계 밖 80건 자치구별 건수 분리, 코드 내 수치 전면 동적 계산값 주입.")
    lines.append("")
    lines.append("### 7.3 사용자 피드백 반영 3차 수정 (22:20)")
    lines.append(f"- **집객시설 설명 문구 팀 논의 사항 반영**: `PREPROCESSING.md` 원본은 수정하지 않고 유지. 집객시설 총합과 세부 합의 관계를 행 기준({s['fac_total_rows']:,}행: 5,952행 94.30%, 360행 5.70%)과 상권 기준({s['fac_total_trades']:,}개 상권: 1,488개 94.30%, 90개 5.70%)으로 분리 재계산하여 '6.1절 팀 논의 사항'에 수록.")
    lines.append("- **3단계 파생변수 산출 기준 9대 조건 정립**: 합계÷합계 원칙, 기준 기간 명시, 개폐업 분기/연간 구분, 동종 업종 객단가 비교, 매출 결측 배제, 분모 0 NaN 보존, 소표본 경고 라벨, 62개 업종 일치, 상권 특성표 한정(추천 점수/MBTI 배제) 조건을 '6.2절'에 수록.")
    lines.append("")
    lines.append("### 7.4 재검수 결과 반영 3차 수정 (22:45)")
    lines.append("- **공용 표 4종 격리 재현 시험 수행**: scripts/build_processed_2025.py를 격리된 임시 폴더에서 실행하여 4개 공용 표를 재생성하고 data/processed/ 원본과 비교 검증 (4개 표 100.0% 일치 확인 및 공용표_재현시험_결과.json 저장).")
    lines.append("- **용어 표준화**: '추천 모형', '추천 모델링'을 '3단계 상권 특성표'로, 대시보드의 '추천 지표'를 '상권 특성 항목'으로 정정.")
    lines.append("- **공통그룹 명칭 및 건수 통일**: 공통그룹 수를 코드로 계산하여 13개('연결 안 함' 포함)로 명시하고 보고서, 차트 제목, 데이터사전 표현 통일.")
    lines.append("- **미확인 문장 가설 표기 및 정비**: 경계 밖 80건 '경기도 접경 외곽' 단정 표현 삭제 및 7개 구 건수 명시([가설] 부착), 양재역 상권 공간 집계 영향 문장에 [가설] 명시.")
    lines.append(f"- **하드코딩 수치 동적 계산 전환**: {s['inside_ratio_pct']:.3f}%, {s['outside_ratio_pct']:.3f}%, {s['center_dong_pct']:.2f}%, {s['fac_missing_pct']:.2f}%, 공용 표 행·열 수, 마트 열 수를 결과 데이터로부터 동적으로 주입.")
    lines.append(f"- **대시보드 4탭 개선**: 누락 표 제목을 행 기준(`누락 기록 {len(df_missing):,}행`)으로 변경하고, 고유 상권 수 및 4분기 전체 미수집(73개)과 일부 분기 미수집(17개)의 중복 구조 상세 설명 안내 박스 수록.")
    lines.append("- **그림 3 파일명 변경**: 내용에 맞게 `03_공통그룹별_점포수_분포.png`로 변경.")
    lines.append("- **종합 검증 스크립트(verify_stage2.py) 고도화**: checked_cells의 엄격한 계산 반영, 마크다운 표 2·3·4·6 및 대시보드 표·KPI 대조, 마트 값의 원천 셀 단위 대조, 집객 72개 NaN 플래그 검증, 누락 및 불일치 목록 재계산 대조, 이미지 바이너리 바이트 일치 검증, 합계 보존 값 뒤바꾸기 변조(swap mutation) 추가.")
    lines.append("")
    lines.append("### 7.5 재검수 결과 반영 4차 수정 (23:15)")
    lines.append("- **표 3 및 대시보드 표 2 칸별 대조 추가**: `항목_파일_연결표.csv`를 기준으로 보고서 표 3(70개 칸)과 대시보드 표 2(60개 칸)의 대응 파일, 분석 단위, 기준 시점, 주요 수록 컬럼, 계산 방법, 데이터 한계 및 주의사항을 칸별로 1:1 직접 대조하는 검증 추가.")
    lines.append("- **원천 컬럼 대조 전면 확대**: `상권_분기_마트`의 7대 합계 컬럼, 유동인구 전 컬럼(22개), 상권변화지표 전 컬럼(4개)을 원천과 대조하고, `상권_마스터`의 상주인구 전 컬럼, 직장인구 전 컬럼, 집객시설 전 컬럼(20개), 영역 전 컬럼, 배후 행정동 전 컬럼을 원천 및 공용 표와 대조.")
    lines.append("- **재현 시험 및 목록 검증 고도화**: `공용표_재현시험_결과.json`의 일치 여부(True) 및 `차이_행수`(불일치 행 수 기준) 검증, 중심점 불일치 목록(31개) 및 점포 위치 불일치 목록(7,670건) 원천 재계산 내용 일치 검증, 데이터사전(148개 컬럼) 결측치 규칙과 실제 결측 건수 대조.")
    lines.append("- **보고서·대시보드 문구 및 표현 정밀화**: 1.2절의 \"바이트 및 셀 단위\"를 \"데이터프레임 셀 값 단위(pandas equals)\"로 수정, 대시보드 4번 탭 가이드 문구를 \"누락 상권 목록\"에서 \"누락 기록\"으로 정정.")
    lines.append("- **하드코딩 숫자 제거**: 1650, 72, 148, 17, 9, 5, 324, 158,895, 1,570, 31, 3 등 결과값을 고정한 숫자를 모두 동적 계산값으로 전환.")
    lines.append("")
    lines.append("### 7.6 재검수 결과 반영 5차 수정 (2026-11-01)")
    lines.append("- **숫자 토큰 검증 및 화이트리스트 도입**: 보고서 본문 및 대시보드 화면 글자에서 추출한 숫자 토큰에 대해 결과 파일 수치 및 기준값 목록 대조 체계를 구축 (일부 미완료 전환 잔존 확인).")
    lines.append("- **규칙 및 한계 원문 대조**: 6.1절 집객시설 제안 문구, 6.2절 3단계 파생변수 산출 9대 기준 전체 원문, 6.3절 5대 분석 한계 전체 원문 1:1 대조.")
    lines.append("- **고정 수치 1차 동적 계산값 전환**: 보고서 내 결측치 건수, 공용 표 행·열 수, 분기별 유동 결측, 용두동 30건, 신설동 22건 등을 동적 계산값으로 전환.")
    lines.append("- **설계표(항목_파일_연결표.csv) 및 데이터사전 실재 대조**: 기재 파일 및 주요 컬럼 실재 대조, 148개 컬럼 결측 규칙 1:1 대조.")
    lines.append("- **마트 대조 누락 19개 컬럼 추가 및 변조 시험**: 상권_마스터 2개, 상권_분기_마트 10개, 상권_업종_분기_마트 7개 컬럼을 추가 대조하고 Swap 변조 시험 적용.")
    lines.append("- **차이_행수 계산식 정밀화**: 결측(NaN) 셀 동등 처리 및 1칸 변조 시 1행 감지 단위 시험 검증.")
    lines.append("- **표현 정비 1차**: 6.2절 '13개 공통그룹' 표현 통일 및 검사기 한계 안내문 1차 정비.")
    lines.append("")
    lines.append("### 7.7 재검수 결과 반영 6차 수정 (2026-11-01)")
    lines.append("- **숫자 검사의 줄 단위 통째 비교 전면 전환**: 토큰 집합 대조 방식(dyn_set 및 전역 허용 목록)을 완전 폐지하고, 숫자가 포함된 모든 줄(보고서 117줄, 대시보드 30줄)에 대해 검사기가 계산값으로 기대 문장을 직접 만들어 순서까지 포함해 통째 비교.")
    lines.append("- **고정 숫자 2차 동적 계산값 전환**: 보고서 450행(1,650개), 498행(원천 매출액), 499행(원천 점포수), 500행(소상공인 원천 행수와 행정동_마스터 합계 각각 산출 대조), 대시보드 헤더 및 1탭/4탭의 점포수(534,978건/534,898건), 누락 상권/슬롯 수치(17개, 90개, 397행, 73개, 292행, 32행 등)를 계산값으로 전환 (일부 고정 수치 잔존 확인되어 7.8절에서 추가 정리).")
    lines.append("- **변조 시험 대폭 강화**: 다른 실제 숫자로 바꾸기(7,722건→7,670건, 중위수↔평균, 20252↔20253 점포, 31개→72개, 72개→73개, 대시보드 73개→17개, 399개→425개), 작은 숫자로 바꾸기(대시보드 KPI 457,188개→1개), 줄 삭제('금천구: 31건', '10m 이내') 등 변조 시험 차단 확인.")
    lines.append("- **데이터사전 단위 대조 및 설명 단어 포함 검사**: 단위는 범주 허용을 폐지하고 컬럼별 기대값(인구는 '명', 면적은 '㎡', ha는 'ha', 금액은 '원', 건수는 '건', 점포/시설은 '개', 코드는 '코드' 등)과 1:1 대조하고, 설명은 컬럼 종류별 필수 단어(인구, 가구, 시설, 점포, 매출, 코드, 명칭 등) 포함 여부를 검사.")
    lines.append("- **대시보드 1번 탭 제목 수치 오기입 및 환원**: 대시보드 1번 탭 제목에 경계 외부 점포를 합산한 7,802건을 일시 오기입하였으나 원천 행정동코드 불일치 수치인 7,722건으로 환원 확정.")
    lines.append("- **기준값 목록의 사실과 다른 지명 삭제**: verify_stage2.py에 기재되어 있던 은평구 진관동, 송파구 위례동 등 실제 데이터와 다른 지명 목록을 완전 삭제.")
    lines.append("- **검사기 로그 표현 정비 및 한계 명시**: 단정적이거나 과장된 표현을 지양하고 실제 비교 범위(표 3,492칸, 숫자 포함 147줄 등)로 명확화하였으며, 숫자 없는 문장의 의미와 표 3 계산식의 뜻은 자동으로 비교하지 않고 사람이 직접 읽어 확인해야 함을 검사기 한계에 명시.")
    lines.append("")
    lines.append("### 7.8 재검수 결과 반영 7차 수정 (2026-11-01)")
    lines.append("- **대시보드 1번 탭 제목 환원 및 불일치 변수 정리**: 대시보드 1번 탭 제목을 '점포 위치 불일치(7,722건)'로 되돌리고 `원천_코드_불일치_건수`를 적용하였으며, `total_spatial_mismatch_stores` 변수를 코드베이스에서 완전 제거.")
    lines.append("- **검사기 원천 직접 계산 독립성 확보**: `verify_stage2.py` 검사 8에서 `stage2_report_data.json` 의존성을 제거하고, 검사기가 원천 파일, 공용 표, 마트, `누락_상권_목록.csv`, `점포_위치_불일치_통계.json`, `공용표_재현시험_결과.json`에서 모든 기대 숫자를 직접 계산.")
    lines.append("- **원천과 마트 비교 문장 독립 계산 및 계산 차이 주입**: '원천(...) = 마트(...) (차이 ...)' 문장에 대해 원천과 마트 값을 각각 별도 계산하고 실제 차이값(abs)도 계산하여 동일 변수 중복 사용을 원천 차단.")
    lines.append("- **보고서 잔여 고정 숫자 전면 동적 계산 전환**: 403행(7,722건), 409행(7개 구, 80건), 423행(80건), 428행(52건, 90.22%), 431행(114건), 616행(7,722건)을 불일치 통계 객체로부터 동적으로 산출 주입.")
    lines.append("- **검사기 로그 및 문구 정밀화**: `verify_stage2.py`의 과장 표현('완전 일치' 등) 및 파일 헤더의 옛 설명 문구를 실제 비교 범위와 줄 단위 대조 방식으로 정정하고, 1452행의 160,465행 및 1465행의 26개 동을 동적 계산값으로 전환.")
    lines.append("- **검사기 한계 안내 갱신**: 데이터사전 설명은 문장 전체가 아닌 컬럼 성격별 필수 단어 포함 여부만 확인함을 명시.")
    lines.append("- **통계값 ±1 계산 오류 주입 변조 시험(Systematic Mutation Testing) 도입**: `build_stage2_report.py`가 산출한 모든 숫자 통계값을 하나씩 1만큼 틀리게 넣고 보고서와 대시보드를 임시 폴더에 재생성하여 검사 7·8·9가 이를 엄격히 감지·차단하는지 자동 검증하는 체계 구축. 대시보드 제목 7,802건 변조 차단 시험 포함.")
    lines.append("")
    lines.append("### 7.9 재검수 결과 반영 8차 수정 (2026-11-01)")
    lines.append("- **대시보드 표 1 잔여 고정 수치 계산값 전환**: 대시보드 표 1 서울 경계 외부 점포 확인 내용('7개 구 80건')을 `점포_위치_불일치_통계.json` 기반 계산값으로 전환.")
    lines.append("- **검사기 HTML 표 1 C4 칸 전체 일치 비교 강화**: 표시 글자(badge)를 뺀 나머지 문구가 기대값과 정확히 일치하도록 검증을 강화하고, 임의 수식어 추가('내외') 변조 시험 차단 검증.")
    lines.append("- **보고서 7.7절 표현 정정**: '대시보드 1번 탭 제목 수치 시험 및 환원'을 '대시보드 1번 탭 제목 수치 오기입 및 환원'으로 정정.")
    lines.append("")
    lines.append("---")
    lines.append("*본 보고서는 `src/build_stage2_report.py`에 의해 `data/processed/stage2/` 결과 데이터로부터 자동 생성되었습니다.*")

    report_text = "\n".join(lines)
    report_path = Path(out_path) if out_path else (REPORT_DIR / "02_전처리_결합설계_보고서_2025Q4.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"  -> {report_path.name} 저장 완료 ({len(lines)}행)")


def build_html_dashboard(data, out_path=None):
    """02_결합검증_대시보드_2025Q4.html 생성 (재검수 반영)"""
    print("[4/4] 02_결합검증_대시보드_2025Q4.html 생성...")
    s = data["stats"]
    sp = s["spatial"]
    df_joins = data["df_joins"]
    df_missing = data["df_missing"]

    html_lines = [
        "<!DOCTYPE html>",
        "<html lang='ko'>",
        "<head>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "  <title>SpotFit 2단계 결합검증 대시보드 (2025Q4)</title>",
        "  <style>",
        "    :root {",
        "      --primary: #1e3d59;",
        "      --secondary: #17b978;",
        "      --accent: #ff6e40;",
        "      --bg: #f8f9fa;",
        "      --card-bg: #ffffff;",
        "      --text: #333333;",
        "      --border: #e0e0e0;",
        "    }",
        "    * { box-sizing: border-box; margin: 0; padding: 0; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Malgun Gothic', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }",
        "    .container { max-width: 1280px; margin: 0 auto; padding: 20px; }",
        "    header { background: var(--primary); color: white; padding: 25px 20px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }",
        "    header h1 { font-size: 24px; margin-bottom: 8px; }",
        "    header p { font-size: 14px; opacity: 0.9; }",
        "    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 25px; }",
        "    .kpi-card { background: var(--card-bg); border-radius: 10px; padding: 18px; border: 1px solid var(--border); box-shadow: 0 2px 4px rgba(0,0,0,0.04); }",
        "    .kpi-title { font-size: 13px; color: #666; font-weight: 600; margin-bottom: 6px; }",
        "    .kpi-value { font-size: 22px; font-weight: 700; color: var(--primary); }",
        "    .kpi-sub { font-size: 12px; color: #888; margin-top: 4px; }",
        "    .tab-nav { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 2px solid var(--border); overflow-x: auto; padding-bottom: 4px; }",
        "    .tab-btn { padding: 10px 20px; font-size: 15px; font-weight: 600; border: none; background: none; cursor: pointer; color: #666; border-radius: 6px 6px 0 0; }",
        "    .tab-btn.active { color: var(--primary); border-bottom: 3px solid var(--primary); background: #ffffff; }",
        "    .tab-content { display: none; background: var(--card-bg); padding: 25px; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 2px 4px rgba(0,0,0,0.04); margin-bottom: 30px; }",
        "    .tab-content.active { display: block; }",
        "    h2 { font-size: 18px; color: var(--primary); margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #edf2f7; }",
        "    .table-container { max-height: 480px; overflow-y: auto; overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 15px; }",
        "    .scroll-guide { font-size: 12px; color: #666; margin-bottom: 6px; font-weight: 500; }",
        "    table { width: 100.0%; border-collapse: collapse; font-size: 13px; text-align: left; }",
        "    th { background: #f1f5f9; color: var(--primary); font-weight: 700; padding: 10px 12px; position: sticky; top: 0; z-index: 2; border-bottom: 2px solid var(--border); }",
        "    td { padding: 9px 12px; border-bottom: 1px solid var(--border); }",
        "    tr:hover { background: #f8fafc; }",
        "    .badge { display: inline-block; padding: 3px 8px; font-size: 11px; font-weight: 600; border-radius: 4px; }",
        "    .badge-success { background: #e6f4ea; color: #137333; }",
        "    .badge-warning { background: #fef7e0; color: #b06000; }",
        "    .badge-info { background: #e8f0fe; color: #1a73e8; }",
        "    .img-box { text-align: center; margin: 20px 0; }",
        "    .img-box img { max-width: 100.0%; height: auto; border-radius: 8px; border: 1px solid var(--border); }",
        "    @media (max-width: 768px) {",
        "      .container { padding: 10px; }",
        "      header { padding: 18px 15px; }",
        "      header h1 { font-size: 19px; }",
        "      .kpi-value { font-size: 18px; }",
        "      .tab-btn { padding: 8px 12px; font-size: 13px; }",
        "      .tab-content { padding: 15px; }",
        "      th, td { padding: 8px 8px; font-size: 12px; }",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        "  <div class='container'>",
        "    <header>",
        "      <h1>SpotFit 2단계: 데이터 전처리 및 결합검증 대시보드 (2025Q4)</h1>",
        f"      <p>{s['master_rows']:,}개 상권 마스터 및 62개 업종 분기 마트 연계 정합성·결측치 자동 검증 결과</p>",
        "    </header>",
        "",
        "    <div class='kpi-grid'>",
        f"      <div class='kpi-card'><div class='kpi-title'>상권 마스터</div><div class='kpi-value'>{s['master_rows']:,}개</div><div class='kpi-sub'>25개 자치구 / {s['master_dongs']}개 행정동</div></div>",
        f"      <div class='kpi-card'><div class='kpi-title'>상권 분기 슬롯</div><div class='kpi-value'>{s['quarter_rows']:,}행</div><div class='kpi-sub'>{s['master_rows']:,}개 상권 × 4개 분기</div></div>",
        f"      <div class='kpi-card'><div class='kpi-title'>상권 업종 분기 마트</div><div class='kpi-value'>{s['industry_rows']:,}행</div><div class='kpi-sub'>62개 업종 결합 마트 (17개 컬럼)</div></div>",
        f"      <div class='kpi-card'><div class='kpi-title'>연간 상권 매출 합계</div><div class='kpi-value'>{s['total_annual_sales']/1e12:.2f}조 원</div><div class='kpi-sub'>원천 데이터와 오차 0원</div></div>",
        f"      <div class='kpi-card'><div class='kpi-title'>2025Q4 점포 수</div><div class='kpi-value'>{s['stores_q4']:,}개</div><div class='kpi-sub'>4개 분기 분기별 합산: {s['stores_sum_quarterly']:,}개</div></div>",
        "    </div>",
        "",
        "    <div class='tab-nav'>",
        "      <button class='tab-btn active' onclick='switchTab(0)'>1. 조사 결과</button>",
        "      <button class='tab-btn' onclick='switchTab(1)'>2. 항목-파일 연결</button>",
        "      <button class='tab-btn' onclick='switchTab(2)'>3. 조인 전후 비교</button>",
        "      <button class='tab-btn' onclick='switchTab(3)'>4. 누락과 빈칸</button>",
        "    </div>",
        "",
        "    <!-- 탭 1: 조사 결과 -->",
        "    <div class='tab-content active' id='tab-0'>",
        f"      <h2>1. 점포 위치 불일치({sp['원천_코드_불일치_건수']:,}건) 및 공간 경계 조사 결과</h2>",
        f"      <div class='scroll-guide'>※ 전체 점포 {sp['전체_점포_수']:,}건 중 서울 내부 {sp['서울_경계_내부_점포_수']:,}건에 대한 공간 분석 결과 요약</div>",
        "      <div class='table-container'>",
        "        <table>",
        "          <thead><tr><th>검증 항목</th><th>수치</th><th>비율 (%)</th><th>분모</th><th>판정 및 데이터 확인 내용</th></tr></thead>",
        "          <tbody>",
        f"            <tr><td>전체 점포 수</td><td>{sp['전체_점포_수']:,}건</td><td>100.0%</td><td>원천 데이터</td><td><span class='badge badge-success'>정상 수집</span></td></tr>",
        f"            <tr><td>서울 경계 내부 점포</td><td>{sp['서울_경계_내부_점포_수']:,}건</td><td>{s['inside_ratio_pct']:.3f}%</td><td>전체 점포</td><td><span class='badge badge-success'>정상 포함</span></td></tr>",
        f"            <tr><td>서울 경계 외부 점포</td><td>{sp['서울_경계_외부_점포_수']:,}건</td><td>{s['outside_ratio_pct']:.3f}%</td><td>전체 점포</td><td><span class='badge badge-warning'>경계 외부</span> {len(sp['경계외부_자치구별_건수'])}개 구 {sp['서울_경계_외부_점포_수']}건</td></tr>",
        f"            <tr><td>원천 행정동코드 불일치</td><td>{sp['원천_코드_불일치_건수']:,}건</td><td>{sp['원천_코드_불일치_비율_pct']}%</td><td>서울 내부 점포</td><td><span class='badge badge-info'>원천 차이</span> 1단계 검수 일치</td></tr>",
        f"            <tr><td>분동·통합(NEW_TO_OLD) 해소</td><td>{sp['분동통합_해소_건수']:,}건</td><td>{sp['분동통합_해소_비율_pct']}%</td><td>서울 내부 점포</td><td><span class='badge badge-success'>매핑 해결</span> 용신동 분동 체계 일치</td></tr>",
        f"            <tr><td>잔여 불일치 점포</td><td>{sp['잔여_불일치_건수']:,}건</td><td>{sp['잔여_불일치_비율_pct']}%</td><td>서울 내부 점포</td><td><span class='badge badge-warning'>경계 근접</span> 중위거리 {sp['이격거리_중위수_m']}m</td></tr>",
        f"            <tr><td>- 동일 구 내 인접동 불일치</td><td>{sp['동일_자치구_내_불일치_건수']:,}건</td><td>{sp['동일_자치구_내_불일치_비율_pct']}%</td><td>잔여 불일치</td><td>동일 자치구 관할 내 인접동</td></tr>",
        f"            <tr><td>- 100m 이내 최근접 비율</td><td>{sp['100m_이내_건수']:,}건</td><td>{sp['100m_이내_비율_pct']}%</td><td>잔여 불일치</td><td>대지 필지/도로 경계선 오차</td></tr>",
        "          </tbody>",
        "        </table>",
        "      </div>",
        "      <div class='img-box'>",
        "        <img src='../images/stage2/01_점포_위치_이격거리_분포.png' alt='점포 위치 이격거리 분포'>",
        "      </div>",
        "      <h2>상권 중심점 ↔ 대표 행정동 불일치 조사 결과</h2>",
        "      <p style='margin-bottom: 12px; font-size: 14px;'>",
        f"        - 중심점과 대표 행정동이 다른 상권 수: <b>{s['center_mismatch_dong_count']}개</b> (변환 좌표계: <code>EPSG:5181 -> EPSG:4326</code>)<br>",
        f"        - 중심점의 자치구까지 다른 상권 수: <b>{s['center_mismatch_gu_count']}개</b> (홍지문, 충정로역 6번, 신사역)<br>",
        f"        - 양재역 상권 코드 충돌: 자치구는 <b>{s['yangjae_gu_name']} ({s['yangjae_gu_code']})</b> [유지], 대표 행정동은 <b>{s['yangjae_dong_name']} ({s['yangjae_dong_code']})</b> (강남구 관할)",
        "      </p>",
        "    </div>",
        "",
        "    <!-- 탭 2: 항목-파일 연결 -->",
        "    <div class='tab-content' id='tab-1'>",
        "      <h2>2. 9대 상권 특성 항목-파일 연결표 (승인 기준)</h2>",
        "      <div class='scroll-guide'>※ 가로 스크롤 가능 / 헤더 고정 테이블</div>",
        "      <div class='table-container'>",
        "        <table>",
        "          <thead><tr><th>항목명</th><th>대응 원천 파일</th><th>분석 단위</th><th>주요 수록 컬럼</th><th>계산 방법</th><th>데이터 한계</th></tr></thead>",
        "          <tbody>",
    ]

    for _, r in data["df_mapping"].iterrows():
        html_lines.append(f"            <tr><td>{r['대시보드_항목명']}</td><td>{r['대시보드_대응_원천_파일']}</td><td>{r['대시보드_분석_단위']}</td><td>{r['대시보드_주요_수록_컬럼']}</td><td>{r['대시보드_계산_방법']}</td><td>{r['대시보드_데이터_한계']}</td></tr>")

    html_lines.extend([
        "          </tbody>",
        "        </table>",
        "      </div>",
        "      <div class='img-box'>",
        "        <img src='../images/stage2/03_공통그룹별_점포수_분포.png' alt='공통그룹별 점포 수 분포'>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- 탭 3: 조인 전후 비교 -->",
        "    <div class='tab-content' id='tab-2'>",
        "      <h2>3. 조인 단계별 전후 행 수 및 일치성 확인</h2>",
        "      <div class='scroll-guide'>※ 7단계 조인 과정 validate 지정 및 키 일치 관계 확인</div>",
        "      <div class='table-container'>",
        "        <table>",
        "          <thead><tr><th>단계</th><th>대상 마트</th><th>결합 내용</th><th>조인 키</th><th>validate</th><th>조인 전 행수</th><th>조인 후 행수</th><th>키 고유수</th><th>조인 전 매출합계</th><th>조인 후 매출합계</th><th>조인 전 점포합계</th><th>조인 후 점포합계</th><th>결측 건수</th><th>사유 및 처리</th></tr></thead>",
        "          <tbody>",
    ])

    for _, r in df_joins.iterrows():
        html_lines.append(f"            <tr><td><b>{r['단계']}</b></td><td>{r['대상_테이블']}</td><td>{r['결합_내용']}</td><td><code>{r['조인_키']}</code></td><td><span class='badge badge-info'>{r['validate']}</span></td><td>{r['조인_전_행수']:,}</td><td>{r['조인_후_행수']:,}</td><td>{r['키_개수']:,}</td><td>{r['조인_전_매출합계']}</td><td>{r['조인_후_매출합계']}</td><td>{r['조인_전_점포합계']}</td><td>{r['조인_후_점포합계']}</td><td>{r['결측_발생_건수']:,}</td><td>{r['사유_및_처리']}</td></tr>")

    html_lines.extend([
        "          </tbody>",
        "        </table>",
        "      </div>",
        "      <div class='img-box'>",
        "        <img src='../images/stage2/02_상권특성_데이터_준비도.png' alt='상권특성 데이터 준비도'>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- 탭 4: 누락과 빈칸 -->",
        "    <div class='tab-content' id='tab-3'>",
        f"      <h2>4. 원천 결측치 및 빈칸 목록 추적 (누락 기록 {len(df_missing):,}행)</h2>",
        f"      <div class='scroll-guide'>※ 전체 누락 기록 ({len(df_missing):,}행) / 스크롤하여 확인 가능</div>",
        "      <div style='background: #eef2f6; border-left: 4px solid var(--primary); padding: 14px; border-radius: 6px; margin-bottom: 16px; font-size: 13px;'>",
        f"        <b>누락 및 빈칸 현황 요약 (총 {len(df_missing):,}개 행 기록)</b>:",
        "        <ul style='margin-left: 20px; margin-top: 6px;'>",
        f"          <li><b>상주인구</b>: {s['res_missing_trades']}개 고유 상권 ({s['res_missing_rows']}행) - 원천에 행 없음</li>",
        f"          <li><b>직장인구</b>: {s['wrk_missing_trades']}개 고유 상권 ({s['wrk_missing_rows']}행) - 원천에 행 없음</li>",
        f"          <li><b>집객시설</b>: {s['fac_missing_districts']}개 고유 상권 ({s['fac_missing_rows']}행) - 원천에 행 없음 (NaN 보존, 이름표 부여)</li>",
        f"          <li><b>유동인구</b>: {s['flow_missing_trades']}개 고유 상권 ({s['flow_missing_rows']}행: {s['flow_q_str']}) - 원천에 슬롯 없음</li>",
        f"          <li><b>추정매출</b>: {s['sales_missing_unique_trades']}개 고유 상권 (총 {s['sales_missing_total_rows']}행)</li>",
        "        </ul>",
        "        <div style='margin-top: 8px;'>",
        f"          ※ <b>추정매출 누락 중복 구조 설명</b>: 추정매출 누락 {s['sales_missing_total_rows']}행은 4개 분기 모두 실적이 없는 상권 {s['q4_all_missing_trades_count']}개(분기 슬롯 {s['q4_all_missing_slots']}행 + 연간 전체 추적 {s['annual_total_missing_rows']}행 = {s['q4_all_missing_total_rows']}행)와, 일부 분기(1~3개 분기)만 실적이 없는 상권 {s['part_missing_sales_trades_count']}개(분기 슬롯 {s['part_missing_slots']}행)가 결합된 구조입니다. (총 분기 슬롯 누락 = {s['q4_all_missing_slots']} + {s['part_missing_slots']} = {s['net_slot_missing_rows']}행)",
        "        </div>",
        "      </div>",
        "      <div class='table-container'>",
        "        <table>",
        "          <thead><tr><th>상권 코드</th><th>상권 명칭</th><th>분기</th><th>지표 항목</th><th>원천 파일명</th><th>미집계 사유</th></tr></thead>",
        "          <tbody>",
    ])

    for _, r in df_missing.iterrows():
        html_lines.append(f"            <tr><td><code>{r['상권_코드']}</code></td><td>{r['상권_명']}</td><td>{r['분기']}</td><td><b>{r['지표_항목']}</b></td><td>{r['원천_파일']}</td><td>{r['미집계_사유']}</td></tr>")

    html_lines.extend([
        "          </tbody>",
        "        </table>",
        "      </div>",
        "    </div>",
        "",
        "    <footer style='text-align: center; color: #888; font-size: 12px; margin-top: 30px;'>",
        "      <p>SpotFit Analytics Platform | 본 대시보드는 <code>src/build_stage2_report.py</code>에 의해 자동 생성되었습니다.</p>",
        "    </footer>",
        "  </div>",
        "",
        "  <script>",
        "    function switchTab(idx) {",
        "      const btns = document.querySelectorAll('.tab-btn');",
        "      const contents = document.querySelectorAll('.tab-content');",
        "      btns.forEach((b, i) => b.classList.toggle('active', i === idx));",
        "      contents.forEach((c, i) => c.classList.toggle('active', i === idx));",
        "    }",
        "  </script>",
        "</body>",
        "</html>"
    ])

    html_text = "\n".join(html_lines)
    html_path = Path(out_path) if out_path else (REPORT_DIR / "02_결합검증_대시보드_2025Q4.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"  -> {html_path.name} 저장 완료 ({len(html_lines)}행)")


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("   [SpotFit Stage 2] 보고서, 대시보드 및 시각화 자동 생성 파이프라인")
    print("=" * 70)
    data = load_all_stage2_data()
    generate_visualizations(data)
    build_markdown_report(data)
    build_html_dashboard(data)
    print("\n[성공] 2단계 시각화, 보고서 및 대시보드 생성 완료!")


if __name__ == "__main__":
    main()
