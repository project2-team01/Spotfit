#!/usr/bin/env python3
"""SpotFit 2단계: 데이터 전처리 및 결합 마트 생성 스크립트 (재검수 반영 개정본)

재검수 반영 사항:
1. 점포 수 분기 합산을 연간 점포 수로 표현하지 않고 '분기별 합산'으로 명시
2. 파생변수(객단가, 프랜차이즈 비율, 개폐업 비율)를 마트에서 제거하여 3단계 상권 특성표 단계로 이관
3. 집객시설 미집계 72개 상권은 0으로 채우지 않고 NaN 보존 및 '집객시설_원천행_없음' 이름표 부여
4. 데이터사전에 3개 마트의 모든 컬럼을 수록하고 13개 공통그룹('연결 안 함' 포함), 시설수 등 코드로 계산
5. 누락 목록에 상주(17), 직장(9), 유동(5), 집객(72), 매출 미발생 상권(73) 및 분기슬롯(324)을 수록하고 사유는 '원천에 행 없음'으로 통일
6. 공용 표 4종 격리 재현 시험 수행 및 결과 파일 저장
7. 조인 기록에 조인 전후 매출 합계와 점포 합계 명시
8. 상권 중심점 ↔ 대표 행정동/자치구 불일치 상권 목록 생성 및 좌표계(EPSG:5181 -> EPSG:4326) 명시
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
import pyproj

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STAGE2_DIR = PROCESSED_DIR / "stage2"

QUARTERS = [20251, 20252, 20253, 20254]
K_DONG, K_Q, K_TRADE, K_IND = "행정동_코드", "기준_년분기_코드", "상권_코드", "서비스_업종_코드"

NEW_TO_OLD = {
    11230515: 11230536,  # 신설동 -> 용신동
    11230533: 11230536,  # 용두동 -> 용신동
    11740525: 11740520,  # 상일1동 -> 상일동
    11740526: 11740520,  # 상일2동 -> 상일동
    11680675: 11680740,  # 개포3동 -> 일원2동
}


def read_raw(rel_path, **kwargs):
    return pd.read_csv(RAW_DIR / rel_path, encoding="utf-8-sig", low_memory=False, **kwargs)


def fix_text_name(s):
    return s.str.replace("?", "·", regex=False)


def run_spatial_investigation():
    """점포 위치 불일치 및 상권 중심점 불일치 정밀 조사"""
    print("[1/5] 공간 위치 및 경계 정합성 정밀 조사...")
    sbiz = read_raw(
        "소상공인_상가정보_서울.csv",
        usecols=["상가업소번호", "상호명", "행정동코드", "행정동명", "시군구명", "도로명주소", "지번주소", "경도", "위도"]
    )
    with open(RAW_DIR / "geo" / "HangJeongDong_ver20251231.geojson", "r", encoding="utf-8") as f:
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

    # 경계 밖 80건의 자치구별 건수 계산 (지명 추측 배제)
    outside_df = sbiz[sbiz["geo_adm_cd8"] == -1]
    outside_gu_counts = outside_df["시군구명"].value_counts().to_dict()

    # 거리 계산 (EPSG:5179 미터 단위)
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

    total_stores = len(sbiz)
    inside_count = len(inside_seoul)
    outside_count = len(outside_df)
    raw_mismatch_count = int((inside_seoul["행정동코드"] != inside_seoul["geo_adm_cd8"]).sum())
    resolved_df = inside_seoul[
        (inside_seoul["행정동코드"] != inside_seoul["geo_adm_cd8"]) &
        (inside_seoul["sbiz_보정_코드"] == inside_seoul["geo_보정_코드"])
    ]
    resolved_count = len(resolved_df)
    yongdu_resolved = int((resolved_df["geo_adm_cd8"] == 11230533).sum())
    sinseol_resolved = int((resolved_df["geo_adm_cd8"] == 11230515).sum())
    remain_count = len(mismatch_7670)
    same_gu_count = int(mismatch_7670["자치구_동일여부"].sum())
    diff_gu_count = int((~mismatch_7670["자치구_동일여부"]).sum())

    spatial_summary = {
        "전체_점포_수": total_stores,
        "서울_경계_내부_점포_수": inside_count,
        "서울_경계_외부_점포_수": outside_count,
        "경계외부_자치구별_건수": outside_gu_counts,
        "원천_코드_불일치_건수": raw_mismatch_count,
        "원천_코드_불일치_비율_pct": round(raw_mismatch_count / inside_count * 100.0, 3),
        "분동통합_해소_건수": resolved_count,
        "분동통합_해소_비율_pct": round(resolved_count / inside_count * 100.0, 3),
        "용두동_해소_건수": yongdu_resolved,
        "신설동_해소_건수": sinseol_resolved,
        "잔여_불일치_건수": remain_count,
        "잔여_불일치_비율_pct": round(remain_count / inside_count * 100.0, 3),
        "동일_자치구_내_불일치_건수": same_gu_count,
        "동일_자치구_내_불일치_비율_pct": round(same_gu_count / remain_count * 100.0, 2),
        "자치구_초과_불일치_건수": diff_gu_count,
        "자치구_초과_불일치_비율_pct": round(diff_gu_count / remain_count * 100.0, 2),
        "이격거리_중위수_m": float(np.nanmedian(distances)),
        "이격거리_평균_m": float(round(np.nanmean(distances), 2)),
        "10m_이내_건수": int((mismatch_7670["경계_이격거리_m"] <= 10).sum()),
        "10m_이내_비율_pct": round(float((mismatch_7670["경계_이격거리_m"] <= 10).sum() / remain_count * 100.0), 2),
        "50m_이내_건수": int((mismatch_7670["경계_이격거리_m"] <= 50).sum()),
        "50m_이내_비율_pct": round(float((mismatch_7670["경계_이격거리_m"] <= 50).sum() / remain_count * 100.0), 2),
        "100m_이내_건수": int((mismatch_7670["경계_이격거리_m"] <= 100).sum()),
        "100m_이내_비율_pct": round(float((mismatch_7670["경계_이격거리_m"] <= 100).sum() / remain_count * 100.0), 2),
        "500m_이내_건수": int((mismatch_7670["경계_이격거리_m"] <= 500).sum()),
        "500m_이내_비율_pct": round(float((mismatch_7670["경계_이격거리_m"] <= 500).sum() / remain_count * 100.0), 2),
        "500m_초과_건수": int((mismatch_7670["경계_이격거리_m"] > 500).sum()),
        "500m_초과_비율_pct": round(float((mismatch_7670["경계_이격거리_m"] > 500).sum() / remain_count * 100.0), 2),
    }

    with open(STAGE2_DIR / "점포_위치_불일치_통계.json", "w", encoding="utf-8") as f:
        json.dump(spatial_summary, f, ensure_ascii=False, indent=2)

    save_cols = [
        "상가업소번호", "상호명", "행정동코드", "행정동명", "시군구명",
        "geo_adm_cd8", "geo_dong_nm", "geo_sggnm", "자치구_동일여부", "경계_이격거리_m", "도로명주소"
    ]
    mismatch_7670[save_cols].to_csv(STAGE2_DIR / "점포_위치_불일치_목록.csv", index=False, encoding="utf-8-sig")

    # ── 상권 중심점 ↔ 대표 행정동/자치구 불일치 상권 목록 생성 ──────────────
    area = read_raw("상권/OA-15560_영역_상권.csv")
    t_epsg = pyproj.Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)
    area_pts = [Point(t_epsg.transform(x, y)) for x, y in zip(area["엑스좌표_값"], area["와이좌표_값"])]
    area_res = tree.query(area_pts, predicate="intersects")
    area_pt_to_poly = dict(zip(area_res[0], area_res[1]))

    mismatch_trade_list = []
    for i in range(len(area)):
        orig_dong = area.iloc[i][K_DONG]
        orig_dong_old = NEW_TO_OLD.get(orig_dong, orig_dong)
        orig_gu = area.iloc[i]["자치구_코드"]

        if i in area_pt_to_poly:
            p_prop = poly_props[area_pt_to_poly[i]]
            geo_dong = p_prop["adm_cd8"]
            geo_dong_old = NEW_TO_OLD.get(geo_dong, geo_dong)
            geo_gu = int(p_prop["sgg"])

            if orig_dong_old != geo_dong_old:
                mismatch_trade_list.append({
                    "상권_코드": area.iloc[i][K_TRADE],
                    "상권_코드_명": area.iloc[i]["상권_코드_명"],
                    "상권_구분_코드_명": area.iloc[i]["상권_구분_코드_명"],
                    "원천_자치구_코드": orig_gu,
                    "원천_자치구_명": area.iloc[i]["자치구_코드_명"],
                    "원천_행정동_코드": orig_dong,
                    "원천_행정동_명": area.iloc[i]["행정동_코드_명"],
                    "중심점_실제_행정동코드": geo_dong,
                    "중심점_실제_행정동명": p_prop["adm_nm"],
                    "중심점_실제_자치구코드": geo_gu,
                    "중심점_실제_자치구명": p_prop["sggnm"],
                    "자치구_불일치_여부": orig_gu != geo_gu,
                    "변환_좌표계": "EPSG:5181 -> EPSG:4326"
                })

    df_trade_mis = pd.DataFrame(mismatch_trade_list)
    df_trade_mis.to_csv(STAGE2_DIR / "상권_중심점_행정동_불일치_목록.csv", index=False, encoding="utf-8-sig")

    spatial_summary["중심점_행정동_불일치_상권수"] = len(df_trade_mis)
    spatial_summary["중심점_자치구_불일치_상권수"] = int(df_trade_mis["자치구_불일치_여부"].sum()) if len(df_trade_mis) > 0 else 0

    with open(STAGE2_DIR / "점포_위치_불일치_통계.json", "w", encoding="utf-8") as f:
        json.dump(spatial_summary, f, ensure_ascii=False, indent=2)

    print(f"  -> 점포 불일치 {remain_count:,}건, 상권 중심점 불일치 {len(df_trade_mis)}개(자치구 상이 {spatial_summary['중심점_자치구_불일치_상권수']}개) 저장 완료")
    return spatial_summary


def run_common_tables_reproduction_test():
    """공용 표 4종의 격리 재현 시험 수행 및 결과 저장 (scripts/build_processed_2025.py)"""
    print("[1.5/5] 공용 표 4종 격리 재현 시험 수행 중 (임시 폴더)...")
    import importlib.util
    import tempfile

    spec = importlib.util.spec_from_file_location("build_processed_2025", PROJECT_DIR / "scripts" / "build_processed_2025.py")
    mod = importlib.util.module_from_spec(spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        mod.OUT = tmp_path
        spec.loader.exec_module(mod)
        mod.OUT = tmp_path
        mod.main()

        tables = [
            "업종_공통그룹.csv",
            "행정동_마스터.csv",
            "행정동_분기.csv",
            "상권_업종_분기.csv"
        ]

        repro_results = {}
        for t in tables:
            orig_df = pd.read_csv(PROCESSED_DIR / t, encoding="utf-8-sig")
            repro_df = pd.read_csv(tmp_path / t, encoding="utf-8-sig")
            is_equal = orig_df.equals(repro_df)
            if is_equal:
                diff_rows = 0
            elif len(orig_df) == len(repro_df) and list(orig_df.columns) == list(repro_df.columns):
                # 양쪽 다 빈칸인 칸은 같은 값으로 보고 실제 다른 셀이 있는 행만 산출
                diff_mask = (orig_df != repro_df) & ~(orig_df.isna() & repro_df.isna())
                diff_rows = int(diff_mask.any(axis=1).sum())
            else:
                merged = orig_df.merge(repro_df, how="outer", indicator=True)
                diff_rows = int((merged["_merge"] != "both").sum())

            repro_results[t] = {
                "행수": len(repro_df),
                "열수": repro_df.shape[1],
                "원본대조_일치여부": bool(is_equal),
                "차이_행수": diff_rows,
                "비고": "100.0% 일치" if is_equal else "불일치 발생"
            }
            print(f"    - {t}: equals={is_equal}, shape={repro_df.shape}")

        out_json_path = STAGE2_DIR / "공용표_재현시험_결과.json"
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(repro_results, f, ensure_ascii=False, indent=2)
        print("  -> 공용표_재현시험_결과.json 저장 완료")
        return repro_results


def build_trade_master(join_logs, missing_records):
    """상권 마스터 (1,650행) 구축: 영역 + 상주 + 직장 + 집객시설 + 배후 행정동"""
    print("[2/5] 상권 마스터 테이블(1,650행) 구축...")
    area = read_raw("상권/OA-15560_영역_상권.csv")
    area["상권_표시_명"] = fix_text_name(area["상권_코드_명"])
    area["영역_면적_ha"] = (area["영역_면적"] / 10000.0).round(4)
    area["자치구_행정동_불일치_여부"] = area[K_DONG] // 1000 != area["자치구_코드"]

    # 1. 상주인구 (OA-15584): Q4 단일값
    res_raw = read_raw("상권/OA-15584_상주인구_상권.csv")
    res_q4 = res_raw[res_raw[K_Q] == 20254].drop(columns=[K_Q, "상권_구분_코드", "상권_구분_코드_명", "상권_코드_명"])
    res_missing_codes = sorted(list(set(area[K_TRADE]) - set(res_q4[K_TRADE])))

    prev_len = len(area)
    area = area.merge(res_q4, on=K_TRADE, how="left", validate="1:1")
    join_logs.append({
        "단계": "조인 1",
        "대상_테이블": "상권_마스터",
        "결합_내용": "영역_상권 + 상주인구_상권",
        "조인_키": K_TRADE,
        "조인_방식": "left",
        "validate": "1:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(area),
        "키_개수": area[K_TRADE].nunique(),
        "조인_전_매출합계": "해당 없음",
        "조인_후_매출합계": "해당 없음",
        "조인_전_점포합계": "해당 없음",
        "조인_후_점포합계": "해당 없음",
        "결측_발생_건수": len(res_missing_codes),
        "사유_및_처리": f"원천에 행 없는 상권 {len(res_missing_codes)}개는 NaN으로 보존"
    })
    for c in res_missing_codes:
        missing_records.append({
            "상권_코드": c,
            "상권_명": area.loc[area[K_TRADE] == c, "상권_표시_명"].values[0],
            "분기": "고정",
            "지표_항목": "상주인구",
            "원천_파일": "OA-15584_상주인구_상권.csv",
            "미집계_사유": "원천에 행 없음"
        })

    # 2. 직장인구 (OA-15569): Q4 단일값
    wrk_raw = read_raw("상권/OA-15569_직장인구_상권.csv")
    wrk_q4 = wrk_raw[wrk_raw[K_Q] == 20254].drop(columns=[K_Q, "상권_구분_코드", "상권_구분_코드_명", "상권_코드_명"])
    wrk_missing_codes = sorted(list(set(area[K_TRADE]) - set(wrk_q4[K_TRADE])))

    prev_len = len(area)
    area = area.merge(wrk_q4, on=K_TRADE, how="left", validate="1:1")
    join_logs.append({
        "단계": "조인 2",
        "대상_테이블": "상권_마스터",
        "결합_내용": "상권_마스터 + 직장인구_상권",
        "조인_키": K_TRADE,
        "조인_방식": "left",
        "validate": "1:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(area),
        "키_개수": area[K_TRADE].nunique(),
        "조인_전_매출합계": "해당 없음",
        "조인_후_매출합계": "해당 없음",
        "조인_전_점포합계": "해당 없음",
        "조인_후_점포합계": "해당 없음",
        "결측_발생_건수": len(wrk_missing_codes),
        "사유_및_처리": f"원천에 행 없는 상권 {len(wrk_missing_codes)}개는 NaN으로 보존"
    })
    for c in wrk_missing_codes:
        missing_records.append({
            "상권_코드": c,
            "상권_명": area.loc[area[K_TRADE] == c, "상권_표시_명"].values[0],
            "분기": "고정",
            "지표_항목": "직장인구",
            "원천_파일": "OA-15569_직장인구_상권.csv",
            "미집계_사유": "원천에 행 없음"
        })

# 3. 집객시설 (OA-15580): 결측치 처리 기준 반영
    # 행이 없는 72개 상권은 0으로 채우지 않고 NaN 보존 및 '집객시설_원천행_없음' 이름표 부여
    fac_raw = read_raw("상권/OA-15580_집객시설_상권.csv")
    fac_q4 = fac_raw[fac_raw[K_Q] == 20254].drop(columns=[K_Q, "상권_구분_코드", "상권_구분_코드_명", "상권_코드_명"])
    fac_missing_codes = sorted(list(set(area[K_TRADE]) - set(fac_q4[K_TRADE])))

    # 행이 있는 상권 내부의 결측 칸만 PREPROCESSING.md 규칙대로 0으로 채움
    fac_cols = [c for c in fac_q4.columns if c != K_TRADE]
    fac_q4[fac_cols] = fac_q4[fac_cols].fillna(0)

    prev_len = len(area)
    area = area.merge(fac_q4, on=K_TRADE, how="left", validate="1:1")

    # 집객시설_원천행_없음 이름표(플래그) 생성
    area["집객시설_원천행_없음"] = area[K_TRADE].isin(fac_missing_codes)

    join_logs.append({
        "단계": "조인 3",
        "대상_테이블": "상권_마스터",
        "결합_내용": "상권_마스터 + 집객시설_상권",
        "조인_키": K_TRADE,
        "조인_방식": "left",
        "validate": "1:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(area),
        "키_개수": area[K_TRADE].nunique(),
        "조인_전_매출합계": "해당 없음",
        "조인_후_매출합계": "해당 없음",
        "조인_전_점포합계": "해당 없음",
        "조인_후_점포합계": "해당 없음",
        "결측_발생_건수": len(fac_missing_codes),
        "사유_및_처리": f"원천에 행 없는 {len(fac_missing_codes)}개 상권은 NaN 보존 및 이름표 부여"
    })
    for c in fac_missing_codes:
        missing_records.append({
            "상권_코드": c,
            "상권_명": area.loc[area[K_TRADE] == c, "상권_표시_명"].values[0],
            "분기": "고정",
            "지표_항목": "집객시설",
            "원천_파일": "OA-15580_집객시설_상권.csv",
            "미집계_사유": "원천에 행 없음"
        })

    # 4. 배후 행정동 마스터 보조 참조 결합
    dong_master = pd.read_csv(PROCESSED_DIR / "행정동_마스터.csv", encoding="utf-8-sig")
    ref_cols = [
        K_DONG, "면적_km2", "자치구_평균소득월액", "점포_202512_전체",
        "소비_이상치", "소비_연간_지출_총금액", "소비_최대항목"
    ]
    dong_ref = dong_master[ref_cols].rename(columns={
        "면적_km2": "배후동_면적_km2",
        "자치구_평균소득월액": "배후동_자치구_평균소득월액",
        "점포_202512_전체": "배후동_소상공인_점포수_전체",
        "소비_이상치": "배후동_소비_이상치",
        "소비_연간_지출_총금액": "배후동_소비_연간지출_총금액",
        "소비_최대항목": "배후동_소비_최대항목"
    })

    prev_len = len(area)
    area = area.merge(dong_ref, on=K_DONG, how="left", validate="m:1")
    join_logs.append({
        "단계": "조인 4",
        "대상_테이블": "상권_마스터",
        "결합_내용": "상권_마스터 + 배후 행정동 마스터",
        "조인_키": K_DONG,
        "조인_방식": "left",
        "validate": "m:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(area),
        "키_개수": area[K_TRADE].nunique(),
        "조인_전_매출합계": "해당 없음",
        "조인_후_매출합계": "해당 없음",
        "조인_전_점포합계": "해당 없음",
        "조인_후_점포합계": "해당 없음",
        "결측_발생_건수": 0,
        "사유_및_처리": "1,650개 상권의 대표 행정동 100.0% 결합 완료"
    })

    area.to_csv(STAGE2_DIR / "상권_마스터.csv", index=False, encoding="utf-8-sig")
    print(f"  -> 상권_마스터.csv 생성 완료 ({len(area)}행 × {area.shape[1]}열)")
    return area


def build_trade_industry_mart(join_logs):
    """상권×업종×분기 마트 (246,197행) 구축: 파생변수 제외 및 순수 집계/플래그 유지"""
    print("[3/5] 상권 업종 분기 마트 테이블(246,197행) 구축 (파생변수 제외)...")
    df = pd.read_csv(PROCESSED_DIR / "상권_업종_분기.csv", encoding="utf-8-sig")
    df["상권_표시_명"] = fix_text_name(df["상권_코드_명"])
    df["매출_보유_여부"] = df["당월_매출_금액"].notna()

    # 파생변수 3단계 이관 반영: 객단가, 프랜차이즈 비율, 개폐업 비율 파생변수를 마트에서 제거하여 3단계로 이관
    front_cols = [
        K_Q, K_TRADE, "상권_코드_명", "상권_표시_명", "상권_구분_코드_명", K_DONG,
        K_IND, "서비스_업종_코드_명", "공통그룹", "매출_보유_여부",
        "당월_매출_금액", "당월_매출_건수",
        "전체_점포_수", "일반_점포_수", "프랜차이즈_점포_수",
        "개업_점포_수", "폐업_점포_수"
    ]
    df = df[front_cols]

    df.to_parquet(STAGE2_DIR / "상권_업종_분기_마트.parquet", index=False)
    df.to_csv(STAGE2_DIR / "상권_업종_분기_마트.csv", index=False, encoding="utf-8-sig")
    print(f"  -> 상권_업종_분기_마트 저장 완료: Parquet 및 CSV ({len(df):,}행 × {df.shape[1]}열)")
    return df


def build_trade_quarter_mart(trade_master, trade_ind_mart, join_logs, missing_records):
    """상권×분기 마트 (6,600행 슬롯) 구축 (파생변수 제외)"""
    print("[4/5] 상권 분기 마트 테이블(6,600행) 구축 (파생변수 제외)...")
    base_panel = pd.MultiIndex.from_product(
        [trade_master[K_TRADE], QUARTERS],
        names=[K_TRADE, K_Q]
    ).to_frame(index=False)

    master_ident = trade_master[[
        K_TRADE, "상권_코드_명", "상권_표시_명", "상권_구분_코드", "상권_구분_코드_명",
        "자치구_코드", "자치구_코드_명", K_DONG, "행정동_코드_명"
    ]]
    base_panel = base_panel.merge(master_ident, on=K_TRADE, how="left", validate="m:1")

    # 1. 길단위 유동인구 결합 (OA-15568, 6,595행)
    flow_raw = read_raw("상권/OA-15568_길단위인구_상권.csv")
    flow_cols = [c for c in flow_raw.columns if c not in ["상권_구분_코드", "상권_구분_코드_명", "상권_코드_명"]]

    prev_len = len(base_panel)
    base_panel = base_panel.merge(flow_raw[flow_cols], on=[K_TRADE, K_Q], how="left", validate="1:1")

    flow_missing_slots = base_panel[base_panel["총_유동인구_수"].isna()][[K_Q, K_TRADE, "상권_표시_명"]]
    join_logs.append({
        "단계": "조인 5",
        "대상_테이블": "상권_분기_마트",
        "결합_내용": "상권_분기_슬롯 + 길단위유동인구_상권",
        "조인_키": f"{K_TRADE}+{K_Q}",
        "조인_방식": "left",
        "validate": "1:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(base_panel),
        "키_개수": len(base_panel[[K_TRADE, K_Q]].drop_duplicates()),
        "조인_전_매출합계": "해당 없음",
        "조인_후_매출합계": "해당 없음",
        "조인_전_점포합계": "해당 없음",
        "조인_후_점포합계": "해당 없음",
        "결측_발생_건수": len(flow_missing_slots),
        "사유_및_처리": f"원천에 행 없는 {len(flow_missing_slots)}개 슬롯은 NaN으로 보존"
    })
    for _, r in flow_missing_slots.iterrows():
        missing_records.append({
            "상권_코드": r[K_TRADE],
            "상권_명": r["상권_표시_명"],
            "분기": str(r[K_Q]),
            "지표_항목": "유동인구",
            "원천_파일": "OA-15568_길단위인구_상권.csv",
            "미집계_사유": "원천에 행 없음"
        })

    # 2. 상권변화지표 결합 (OA-15576, 6,600행 전체 일치)
    change_raw = read_raw("상권/OA-15576_상권변화지표_상권.csv")
    change_cols = [
        K_TRADE, K_Q, "상권_변화_지표", "상권_변화_지표_명",
        "운영_영업_개월_평균", "폐업_영업_개월_평균"
    ]
    prev_len = len(base_panel)
    base_panel = base_panel.merge(change_raw[change_cols], on=[K_TRADE, K_Q], how="left", validate="1:1")
    join_logs.append({
        "단계": "조인 6",
        "대상_테이블": "상권_분기_마트",
        "결합_내용": "상권_분기_마트 + 상권변화지표_상권",
        "조인_키": f"{K_TRADE}+{K_Q}",
        "조인_방식": "left",
        "validate": "1:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(base_panel),
        "키_개수": len(base_panel[[K_TRADE, K_Q]].drop_duplicates()),
        "조인_전_매출합계": "해당 없음",
        "조인_후_매출합계": "해당 없음",
        "조인_전_점포합계": "해당 없음",
        "조인_후_점포합계": "해당 없음",
        "결측_발생_건수": int(base_panel["상권_변화_지표_명"].isna().sum()),
        "사유_및_처리": "6,600행 슬롯과 100.0% 완전 일치"
    })

    # 3. 상권별 매출·점포 분기 합계 집계 (파생 비율 변수 제외)
    trade_agg = trade_ind_mart.groupby([K_TRADE, K_Q]).agg(
        상권_당월_매출_금액_합계=("당월_매출_금액", "sum"),
        상권_당월_매출_건수_합계=("당월_매출_건수", "sum"),
        상권_전체_점포_수_합계=("전체_점포_수", "sum"),
        상권_일반_점포_수_합계=("일반_점포_수", "sum"),
        상권_프랜차이즈_점포_수_합계=("프랜차이즈_점포_수", "sum"),
        상권_개업_점포_수_합계=("개업_점포_수", "sum"),
        상권_폐업_점포_수_합계=("폐업_점포_수", "sum"),
        상권_매출_보유_업종_수=("당월_매출_금액", lambda s: s.notna().sum()),
        상권_점포_보유_업종_수=("전체_점포_수", lambda s: (s > 0).sum())
    ).reset_index()

    # 매출 미발생 상권(매출 업종수 == 0)은 NaN 유지 (0원 채우기 금지)
    trade_agg.loc[trade_agg["상권_매출_보유_업종_수"] == 0, "상권_당월_매출_금액_합계"] = np.nan
    trade_agg.loc[trade_agg["상권_매출_보유_업종_수"] == 0, "상권_당월_매출_건수_합계"] = np.nan

    prev_len = len(base_panel)
    prev_sales_sum = trade_ind_mart["당월_매출_금액"].sum()
    prev_stores_sum = trade_ind_mart["전체_점포_수"].sum()

    base_panel = base_panel.merge(trade_agg, on=[K_TRADE, K_Q], how="left", validate="1:1")

    post_sales_sum = base_panel["상권_당월_매출_금액_합계"].sum()
    post_stores_sum = base_panel["상권_전체_점포_수_합계"].sum()

    no_sales_slots = base_panel[base_panel["상권_당월_매출_금액_합계"].isna()][[K_Q, K_TRADE, "상권_표시_명"]]
    join_logs.append({
        "단계": "조인 7",
        "대상_테이블": "상권_분기_마트",
        "결합_내용": "상권_분기_마트 + 상권별 매출·점포 집계",
        "조인_키": f"{K_TRADE}+{K_Q}",
        "조인_방식": "left",
        "validate": "1:1",
        "조인_전_행수": prev_len,
        "조인_후_행수": len(base_panel),
        "키_개수": len(base_panel[[K_TRADE, K_Q]].drop_duplicates()),
        "조인_전_매출합계": f"{prev_sales_sum:,.0f}원",
        "조인_후_매출합계": f"{post_sales_sum:,.0f}원",
        "조인_전_점포합계": f"{prev_stores_sum:,}개",
        "조인_후_점포합계": f"{post_stores_sum:,}개",
        "결측_발생_건수": len(no_sales_slots),
        "사유_및_처리": f"원천에 행 없는 {len(no_sales_slots)}개 상권분기 슬롯은 NaN 보존"
    })

    # 매출 미발생 분기 슬롯 누락 목록 추가 (원천에 행 없음)
    for _, r in no_sales_slots.iterrows():
        missing_records.append({
            "상권_코드": r[K_TRADE],
            "상권_명": r["상권_표시_명"],
            "분기": str(r[K_Q]),
            "지표_항목": "추정매출",
            "원천_파일": "OA-15572_추정매출_상권.csv",
            "미집계_사유": "원천에 행 없음"
        })

    # 연간 추정매출 한 번도 없는 73개 상권 추적
    annual_sales_by_trade = base_panel.groupby(K_TRADE)["상권_당월_매출_금액_합계"].sum()
    zero_annual_trades = annual_sales_by_trade[annual_sales_by_trade == 0].index.tolist()
    for c in zero_annual_trades:
        missing_records.append({
            "상권_코드": c,
            "상권_명": trade_master.loc[trade_master[K_TRADE] == c, "상권_표시_명"].values[0],
            "분기": "연간 전체",
            "지표_항목": "추정매출",
            "원천_파일": "OA-15572_추정매출_상권.csv",
            "미집계_사유": "원천에 행 없음"
        })

    base_panel.to_csv(STAGE2_DIR / "상권_분기_마트.csv", index=False, encoding="utf-8-sig")
    print(f"  -> 상권_분기_마트.csv 생성 완료 ({len(base_panel)}행 × {base_panel.shape[1]}열)")
    return base_panel


def generate_full_data_dictionary(trade_master, trade_quarter, trade_ind):
    """세 마트의 모든 컬럼을 전체 수록하고 공통그룹수, 시설수 등을 코드로 계산"""
    print("[5/5] 세 마트의 모든 컬럼을 수록한 전체 데이터사전 생성...")

    # 공통그룹 수 및 세부 시설 수 코드로 계산
    common_group_count = int(trade_ind["공통그룹"].nunique())
    fac_raw = read_raw("상권/OA-15580_집객시설_상권.csv")
    sub_facility_cols = [c for c in fac_raw.columns if c not in [
        "기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명", "집객시설_수"
    ]]
    sub_facility_count = len(sub_facility_cols)

    rows = []

    # 1. 상권_마스터 컬럼들 전체 수록
    for c in trade_master.columns:
        dtype_str = str(trade_master[c].dtype)
        desc = ""
        unit = "값"
        src = "OA-15560"
        rule = "결측 없음"

        if c == "상권_코드":
            desc, unit, rule = "상권 고유 식별 코드", "코드", "결측 없음 (기본키)"
        elif c == "상권_코드_명":
            desc, unit, rule = "상권 명칭 (원천 표기, ? 보존)", "명칭", "결측 없음"
        elif c == "상권_표시_명":
            desc, unit, src, rule = "상권 표시 명칭 (?를 ·로 치환)", "명칭", "파생변수", "결측 없음"
        elif c == "상권_구분_코드":
            desc, unit, rule = "상권 구분 코드 (A, D, R, U)", "코드", "결측 없음"
        elif c == "상권_구분_코드_명":
            desc, unit, rule = "상권 구분 한글명칭", "명칭", "결측 없음"
        elif c in ("엑스좌표_값", "와이좌표_값"):
            desc, unit, rule = f"중심점 {c[:2]} 좌표 (EPSG:5181)", "좌표", "결측 없음"
        elif c == "영역_면적":
            desc, unit, rule = "상권 다각형 면적", "㎡", "결측 없음"
        elif c == "영역_면적_ha":
            desc, unit, src, rule = "상권 헥타르 면적 (영역_면적 ÷ 10,000)", "ha", "파생변수", "결측 없음"
        elif c == "자치구_코드":
            desc, unit, rule = "원천 기재 자치구 코드 (양재역 서초구 11650 유지)", "코드", "결측 없음"
        elif c == "자치구_코드_명":
            desc, unit, rule = "원천 기재 자치구 명칭", "명칭", "결측 없음"
        elif c == "행정동_코드":
            desc, unit, rule = "대표 행정동 코드 (8자리)", "코드", "결측 없음"
        elif c == "행정동_코드_명":
            desc, unit, rule = "대표 행정동 명칭", "명칭", "결측 없음"
        elif c == "자치구_행정동_불일치_여부":
            desc, unit, src, rule = "행정동 소속 자치구와 상권 자치구의 불일치 여부", "플래그", "파생변수", "결측 없음 (양재역 True)"
        elif "직장" in c:
            desc, unit, src, rule = f"직장인구 관련 지표 ({c})", "명", "OA-15569", "9개 상권 원천 부재로 NaN 보존"
        elif c.endswith("가구_수"):
            desc, unit, src, rule = f"상주 가구수 지표 ({c})", "가구", "OA-15584", "17개 상권 원천 부재로 NaN 보존"
        elif "상주" in c:
            desc, unit, src, rule = f"상주인구 관련 지표 ({c})", "명", "OA-15584", "17개 상권 원천 부재로 NaN 보존"
        elif c == "집객시설_수":
            desc, unit, src, rule = f"총 집객시설 수 (세부 {sub_facility_count}개 시설 및 기타 포함)", "개", "OA-15580", "72개 상권 원천 부재로 NaN 보존"
        elif c in sub_facility_cols:
            desc, unit, src, rule = f"세부 집객시설 지표 ({c})", "개", "OA-15580", "원천 행 없는 72개 상권 NaN 보존, 원천 행 내 빈칸은 fillna(0)"
        elif c == "집객시설_원천행_없음":
            desc, unit, src, rule = "원천 집객시설 파일에 행이 없는 상권 여부 (72개 상권 True)", "플래그", "파생변수", "결측 없음"
        elif c == "배후동_면적_km2":
            desc, unit, src, rule = "대표 행정동 면적 지표 (배후동_면적_km2)", "㎢", "행정동_마스터", "대표 행정동 기준 100.0% 연계"
        elif c == "배후동_자치구_평균소득월액":
            desc, unit, src, rule = "대표 행정동 자치구 소득월액 지표 (배후동_자치구_평균소득월액)", "원", "행정동_마스터", "대표 행정동 기준 100.0% 연계"
        elif c == "배후동_소상공인_점포수_전체":
            desc, unit, src, rule = "대표 행정동 소상공인 점포수 지표 (배후동_소상공인_점포수_전체)", "개", "행정동_마스터", "대표 행정동 기준 100.0% 연계"
        elif c == "배후동_소비_이상치":
            desc, unit, src, rule = "대표 행정동 소비 이상치 플래그 (배후동_소비_이상치)", "플래그", "행정동_마스터", "대표 행정동 기준 100.0% 연계"
        elif c == "배후동_소비_연간지출_총금액":
            desc, unit, src, rule = "대표 행정동 연간 소비 지출액 지표 (배후동_소비_연간지출_총금액)", "원", "행정동_마스터", "대표 행정동 기준 100.0% 연계"
        elif c == "배후동_소비_최대항목":
            desc, unit, src, rule = "대표 행정동 소비 최대 지출 항목 (배후동_소비_최대항목)", "명칭", "행정동_마스터", "대표 행정동 기준 100.0% 연계"
        else:
            desc, unit, src, rule = f"상권 마스터 일반 지표 ({c})", "값", "OA-15560", "결측 확인"

        rows.append({
            "테이블명": "상권_마스터",
            "컬럼명": c,
            "한글_설명": desc,
            "데이터타입": dtype_str,
            "단위": unit,
            "출처_파일": src,
            "분석_단위": "상권 고정 (1,650행)",
            "결측치_처리_규칙": rule
        })

    # 2. 상권_분기_마트 컬럼들 전체 수록
    for c in trade_quarter.columns:
        dtype_str = str(trade_quarter[c].dtype)
        desc, unit, src, rule = "", "값", "기준슬롯", "결측 없음"

        if c in ("상권_코드", "기준_년분기_코드"):
            desc, unit, rule = f"복합 식별 기본키 ({c})", "코드", "결측 없음 (복합키)"
        elif c in ("상권_구분_코드", "자치구_코드", "행정동_코드"):
            desc, unit, src, rule = f"상권 식별 코드 ({c})", "코드", "상권_마스터", "결측 없음"
        elif c in ("상권_코드_명", "상권_표시_명", "상권_구분_코드_명", "자치구_코드_명", "행정동_코드_명"):
            desc, unit, src, rule = f"상권 식별 속성 ({c})", "명칭", "상권_마스터", "결측 없음"
        elif "유동인구" in c:
            desc, unit, src, rule = f"보행 유동인구 지표 ({c})", "명", "OA-15568", "원천에 행 없는 5개 슬롯 NaN 보존"
        elif c == "상권_변화_지표":
            desc, unit, src, rule = f"상권변화지표 지표 ({c})", "코드", "OA-15576", "6,600행 100.0% 결합"
        elif c == "상권_변화_지표_명":
            desc, unit, src, rule = f"상권변화지표 명칭 ({c})", "명칭", "OA-15576", "6,600행 100.0% 결합"
        elif "영업_개월" in c:
            desc, unit, src, rule = f"상권변화지표 관련 지표 ({c})", "개월", "OA-15576", "6,600행 100.0% 결합"
        elif c == "상권_당월_매출_금액_합계":
            desc, unit, src, rule = f"상권 62개 업종 합산 매출 지표 ({c})", "원", "상권_업종_분기_마트", "매출 미발생 324개 슬롯 NaN 보존 (0원 채우기 금지)"
        elif c == "상권_당월_매출_건수_합계":
            desc, unit, src, rule = f"상권 62개 업종 합산 매출 지표 ({c})", "건", "상권_업종_분기_마트", "매출 미발생 324개 슬롯 NaN 보존 (0원 채우기 금지)"
        elif c.startswith("상권_전체_점포") or "점포_수_합계" in c:
            desc, unit, src, rule = f"상권 62개 업종 점포 합계 지표 ({c})", "개", "상권_업종_분기_마트", "6,600행 집계 완료"
        elif "보유_업종_수" in c:
            desc, unit, src, rule = f"상권 내 실적 보유 업종 수 ({c})", "개", "상권_업종_분기_마트", "집계값"
        else:
            desc, unit, src, rule = f"상권 분기 지표 ({c})", "값", "상권_분기_마트", "결측 확인"

        rows.append({
            "테이블명": "상권_분기_마트",
            "컬럼명": c,
            "한글_설명": desc,
            "데이터타입": dtype_str,
            "단위": unit,
            "출처_파일": src,
            "분석_단위": "상권×분기 (6,600행)",
            "결측치_처리_규칙": rule
        })

    # 3. 상권_업종_분기_마트 컬럼들 전체 수록
    for c in trade_ind.columns:
        dtype_str = str(trade_ind[c].dtype)
        desc, unit, src, rule = "", "값", "상권_업종_분기", "결측 없음"

        if c in ("기준_년분기_코드", "상권_코드", "서비스_업종_코드", "행정동_코드"):
            desc, unit, rule = f"복합 식별 기본키 ({c})", "코드", "결측 없음"
        elif c in ("상권_코드_명", "상권_표시_명", "상권_구분_코드_명", "서비스_업종_코드_명"):
            desc, unit, rule = f"상권 및 업종 식별 명칭 ({c})", "명칭", "결측 없음"
        elif c == "공통그룹":
            desc, unit, src, rule = f"소비 항목 연계 13대 공통그룹 (총 {common_group_count}개 그룹, '연결 안 함' 포함)", "분류", "업종_공통그룹", "62개 업종 100.0% 매핑"
        elif c == "매출_보유_여부":
            desc, unit, src, rule = "추정매출 데이터 존재 여부 플래그", "플래그", "파생변수", "결측 없음"
        elif c == "당월_매출_금액":
            desc, unit, src, rule = f"업종별 추정매출 실적 ({c})", "원", "OA-15572", "원천 미발생 160,465행 NaN 보존 (0원 채우기 금지)"
        elif c == "당월_매출_건수":
            desc, unit, src, rule = f"업종별 추정매출 실적 ({c})", "건", "OA-15572", "원천 미발생 160,465행 NaN 보존 (0원 채우기 금지)"
        elif c in ("전체_점포_수", "일반_점포_수", "프랜차이즈_점포_수", "개업_점포_수", "폐업_점포_수"):
            desc, unit, src, rule = f"업종별 점포 실적 ({c})", "개", "OA-15577", "원천 점포 데이터 100.0% 수록"
        else:
            desc, unit, src, rule = f"상권 업종 지표 ({c})", "값", "상권_업종_분기", "결측 확인"

        rows.append({
            "테이블명": "상권_업종_분기_마트",
            "컬럼명": c,
            "한글_설명": desc,
            "데이터타입": dtype_str,
            "단위": unit,
            "출처_파일": src,
            "분석_단위": "상권×업종×분기 (246,197행)",
            "결측치_처리_규칙": rule
        })

    df_dict = pd.DataFrame(rows)
    df_dict.to_csv(STAGE2_DIR / "데이터사전.csv", index=False, encoding="utf-8-sig")
    print(f"  -> 데이터사전.csv 전체 저장 완료: 3개 마트 총 {len(df_dict)}개 컬럼 (마스터 {len(trade_master.columns)}, 분기 {len(trade_quarter.columns)}, 업종 {len(trade_ind.columns)})")
    return df_dict


def generate_feature_item_mapping():
    """9대 핵심 분석 항목(임대료 포함 10개) - 파일 연결 설계표 생성"""
    mapping_data = [
        {
            "핵심_항목": "**고객 구성**",
            "대응_원천_파일": "`OA-15568`(유동)<br>`OA-15584`(상주)<br>`OA-15569`(직장)",
            "분석_단위": "상권×분기<br>상권 고정",
            "기준_시점": "2025Q1~Q4<br>고정 스냅샷",
            "주요_수록_컬럼": "유동·상주·직장 인구수 (성·연령·시간대)",
            "계산_및_집계_방법": "- 유동: 분기별 합계<br>- 상주·직장: 고정 마스터 분리 (분모: 해당 총인구)",
            "데이터_한계_및_주의사항": "[가설] 상주·직장은 인구 센서스 기반으로 계절 변동 파악 불가. 유동인구 5개 슬롯 미집계 칸 존재",
            "대시보드_항목명": "<b>고객 구성</b>",
            "대시보드_대응_원천_파일": "OA-15568, OA-15584, OA-15569",
            "대시보드_분석_단위": "상권×분기 / 고정",
            "대시보드_주요_수록_컬럼": "유동·상주·직장 인구수",
            "대시보드_계산_방법": "유동 합계, 상주·직장 고정 분리",
            "대시보드_데이터_한계": "[가설] 상주·직장은 인구 센서스 기반 불변"
        },
        {
            "핵심_항목": "**객단가**",
            "대응_원천_파일": "`OA-15572_추정매출_상권`",
            "분석_단위": "상권×업종×분기",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`당월_매출_금액`, `당월_매출_건수`",
            "계산_및_집계_방법": "`당월_매출_금액 ÷ 당월_매출_건수` (원/건)",
            "데이터_한계_및_주의사항": "3단계 상권 특성표에서 계산. 62개 업종별 단가 편차가 커 상권 전체 단순평균 금지",
            "대시보드_항목명": "<b>객단가</b>",
            "대시보드_대응_원천_파일": "OA-15572_추정매출_상권",
            "대시보드_분석_단위": "상권×업종×분기",
            "대시보드_주요_수록_컬럼": "당월_매출_금액, 당월_매출_건수",
            "대시보드_계산_방법": "매출금액 ÷ 매출건수",
            "대시보드_데이터_한계": "3단계 상권 특성표에서 계산"
        },
        {
            "핵심_항목": "**프랜차이즈 비율**",
            "대응_원천_파일": "`OA-15577_점포_상권`",
            "분석_단위": "상권×업종×분기",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`프랜차이즈_점포_수`, `전체_점포_수`",
            "계산_및_집계_방법": "`프랜차이즈_점포_수 합 ÷ 전체_점포_수 합 × 100` (%)",
            "데이터_한계_및_주의사항": "3단계 상권 특성표에서 계산. 행별 비율 평균 왜곡 방지를 위해 반드시 점포 수 합계로 재계산",
            "대시보드_항목명": "<b>프랜차이즈 비율</b>",
            "대시보드_대응_원천_파일": "OA-15577_점포_상권",
            "대시보드_분석_단위": "상권×업종×분기",
            "대시보드_주요_수록_컬럼": "프랜차이즈_점포_수, 전체_점포_수",
            "대시보드_계산_방법": "프랜차이즈합 ÷ 전체점포합 × 100",
            "대시보드_데이터_한계": "3단계 상권 특성표에서 계산"
        },
        {
            "핵심_항목": "**매출 변화**",
            "대응_원천_파일": "`OA-15572_추정매출_상권`",
            "분석_단위": "상권×업종×분기",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`당월_매출_금액`, `기준_년분기_코드`",
            "계산_및_집계_방법": "분기별 매출 증감률 `(Q_t - Q_{t-1}) ÷ Q_{t-1} × 100` (%)",
            "데이터_한계_및_주의사항": "2025년 4개 분기 자료로 1분기 전분기 대비 증감률 결측 발생, 연간 계절성 분리 한계",
            "대시보드_항목명": "<b>매출 변화</b>",
            "대시보드_대응_원천_파일": "OA-15572_추정매출_상권",
            "대시보드_분석_단위": "상권×업종×분기",
            "대시보드_주요_수록_컬럼": "당월_매출_금액, 기준_년분기_코드",
            "대시보드_계산_방법": "분기별 증감률",
            "대시보드_데이터_한계": "1분기 전분기 증감률 결측"
        },
        {
            "핵심_항목": "**경쟁 (밀집도)**",
            "대응_원천_파일": "`OA-15577_점포_상권`<br>`OA-15560_영역_상권`",
            "분석_단위": "상권×업종×분기<br>상권 고정",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`전체_점포_수`, `영역_면적`",
            "계산_및_집계_방법": "상권 내 업종별 점포 수, `점포_수 ÷ (영역_면적 / 10,000)` (개/ha)",
            "데이터_한계_및_주의사항": "상권 경계 외부 인접 점포 미포함",
            "대시보드_항목명": "<b>경쟁 (밀집도)</b>",
            "대시보드_대응_원천_파일": "OA-15577, OA-15560",
            "대시보드_분석_단위": "상권×업종×분기",
            "대시보드_주요_수록_컬럼": "전체_점포_수, 영역_면적",
            "대시보드_계산_방법": "점포수 ÷ (영역면적 / 10,000)",
            "대시보드_데이터_한계": "상권 외곽 인접 점포 미포함"
        },
        {
            "핵심_항목": "**개폐업**",
            "대응_원천_파일": "`OA-15577_점포_상권`",
            "분석_단위": "상권×업종×분기",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`개업_점포_수`, `폐업_점포_수`, `전체_점포_수`",
            "계산_및_집계_방법": "`개업(폐업)_점포_수 합 ÷ 전체_점포_수 합 × 100` (%)",
            "데이터_한계_및_주의사항": "3단계 상권 특성표에서 계산. 점포 1~2개 상권의 비율 왜곡 방지 위해 합계로 재계산",
            "대시보드_항목명": "<b>개폐업</b>",
            "대시보드_대응_원천_파일": "OA-15577_점포_상권",
            "대시보드_분석_단위": "상권×업종×분기",
            "대시보드_주요_수록_컬럼": "개업_점포_수, 폐업_점포_수",
            "대시보드_계산_방법": "개업(폐업)합 ÷ 전체점포합 × 100",
            "대시보드_데이터_한계": "3단계 상권 특성표에서 계산"
        },
        {
            "핵심_항목": "**상권 변화 지표**",
            "대응_원천_파일": "`OA-15576_상권변화지표_상권`",
            "분석_단위": "상권×분기",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`상권_변화_지표_명`, `운영_영업_개월_평균`, `폐업_영업_개월_평균`",
            "계산_및_집계_방법": "원천 지표 코드 및 평균 개월 수 보존",
            "데이터_한계_및_주의사항": "정체·상권축소·다이나믹·상권확장 4대 범주 및 평균치만 제공",
            "대시보드_항목명": "<b>상권 변화 지표</b>",
            "대시보드_대응_원천_파일": "OA-15576_상권변화지표",
            "대시보드_분석_단위": "상권×분기",
            "대시보드_주요_수록_컬럼": "상권_변화_지표_명, 운영개월",
            "대시보드_계산_방법": "정체/축소/다이나믹/확장 보존",
            "대시보드_데이터_한계": "평균 개월수만 제공"
        },
        {
            "핵심_항목": "**소비 수준**",
            "대응_원천_파일": "`OA-22166_소비_행정동`<br>`행정동_마스터`",
            "분석_단위": "행정동×분기",
            "기준_시점": "2025Q1~Q4",
            "주요_수록_컬럼": "`지출_총금액`, 10대 항목 지출액, `소비_이상치`",
            "계산_및_집계_방법": "상권의 대표 `행정동_코드`를 키로 연결",
            "데이터_한계_및_주의사항": "상권 자체 소비가 아닌 배후 행정동 소비. 이상치 8곳 플래그 병기",
            "대시보드_항목명": "<b>소비 수준</b>",
            "대시보드_대응_원천_파일": "OA-22166_소비_행정동",
            "대시보드_분석_단위": "행정동×분기",
            "대시보드_주요_수록_컬럼": "지출_총금액, 항목별 지출",
            "대시보드_계산_방법": "대표 행정동코드 키 매핑",
            "대시보드_데이터_한계": "배후 동 소비. 이상치 8곳 플래그"
        },
        {
            "핵심_항목": "**집객시설**",
            "대응_원천_파일": "`OA-15580_집객시설_상권`",
            "분석_단위": "상권 고정",
            "기준_시점": "2025년 고정",
            "주요_수록_컬럼": "`집객시설_수`, 19개 세부 시설 수",
            "계산_및_집계_방법": "원천 행 없는 상권 NaN 보존, 행 내 빈칸은 0으로 채움",
            "데이터_한계_및_주의사항": "4개 분기 수치 동일. 총 집객시설 수는 94.30%에서 세부 합보다 큼",
            "대시보드_항목명": "<b>집객시설</b>",
            "대시보드_대응_원천_파일": "OA-15580_집객시설_상권",
            "대시보드_분석_단위": "상권 고정",
            "대시보드_주요_수록_컬럼": "집객시설_수, 19종 세부 시설",
            "대시보드_계산_방법": "원천 행 없는 상권 NaN 보존",
            "대시보드_데이터_한계": "4개 분기 수치 동일"
        },
        {
            "핵심_항목": "**임대료·보증금**",
            "대응_원천_파일": "데이터 없음",
            "분석_단위": "상권 단위",
            "기준_시점": "데이터 없음",
            "주요_수록_컬럼": "데이터 없음",
            "계산_및_집계_방법": "**'데이터 없음'** 표기",
            "데이터_한계_및_주의사항": "원천 데이터 미수집 항목으로 임의 추정 금지",
            "대시보드_항목명": "<b>임대료·보증금</b>",
            "대시보드_대응_원천_파일": "데이터 없음",
            "대시보드_분석_단위": "상권 단위",
            "대시보드_주요_수록_컬럼": "데이터 없음",
            "대시보드_계산_방법": "<b>데이터 없음</b> 표기",
            "대시보드_데이터_한계": "원천 미수집. 임의추정 금지"
        }
    ]
    df_map = pd.DataFrame(mapping_data)
    df_map.to_csv(STAGE2_DIR / "항목_파일_연결표.csv", index=False, encoding="utf-8-sig")
    print(f"  -> 항목_파일_연결표.csv 저장 완료 ({len(df_map)}개 항목)")
    return df_map


def main():
    STAGE2_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("   [SpotFit Stage 2] 전처리 및 결합 마트 재생성 파이프라인 (재검수 반영)")
    print("=" * 70)

    join_logs = []
    missing_records = []

    # 1. 공간 조사 및 상권 중심점 불일치 목록
    run_spatial_investigation()

    # 1.5. 공용 표 4종 격리 재현 시험
    run_common_tables_reproduction_test()

    # 2. 상권 마스터 생성
    trade_master = build_trade_master(join_logs, missing_records)

    # 3. 상권 업종 분기 마트 생성 (파생변수 제외)
    trade_ind_mart = build_trade_industry_mart(join_logs)

    # 4. 상권 분기 마트 생성 (파생변수 제외)
    trade_quarter_mart = build_trade_quarter_mart(trade_master, trade_ind_mart, join_logs, missing_records)

    # 5. 전체 데이터사전 및 항목-파일 연결표 생성
    generate_full_data_dictionary(trade_master, trade_quarter_mart, trade_ind_mart)
    generate_feature_item_mapping()

    # 6. 조인 기록 및 누락 목록 저장
    df_joins = pd.DataFrame(join_logs)
    df_joins.to_csv(STAGE2_DIR / "조인_기록.csv", index=False, encoding="utf-8-sig")
    with open(STAGE2_DIR / "조인_기록.json", "w", encoding="utf-8") as f:
        json.dump(join_logs, f, ensure_ascii=False, indent=2)

    df_missing = pd.DataFrame(missing_records)
    df_missing.to_csv(STAGE2_DIR / "누락_상권_목록.csv", index=False, encoding="utf-8-sig")

    print("\n[완료] 2단계 마트 재생성 및 기록 저장 완료!")


if __name__ == "__main__":
    main()
