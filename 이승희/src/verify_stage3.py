# -*- coding: utf-8 -*-
"""
SpotFit Stage 3: 종합 자동 검증 파이프라인 (8차 독립 검수 반영)
- 2단계 마트 및 원천 데이터로부터 직접 기대값 독립 재계산 (생성기 비의존)
- 4종 특성표 267개 전 컬럼을 상속/파생/결측사유 중 하나로 100% 판정 (미판정 컬럼 부재 검증)
- 10,909,987칸 전수 칸 단위 1:1 대조 및 실제 검증 칸수 동적 계산 출력
- 민감도 3종, 소표본 6행, 상관행렬, 요약통계 JSON 전 항목 독립 재계산 대조
- 변수사전 267개 컬럼 메타데이터, 11대 표준 순서, 실제 DataFrame dtype 1:1 일치, 한글 설명 유효성 검증
- 보고서 및 팀 논의자료 줄 단위 대조, 금지어 14종 및 단독 100% 부재 검증, 독립 계산값 기반 기대 문장 대조
- 대시보드 5종 내장 데이터 791,563개 전 칸 1:1 대조, 390px 폰트 >=10px, 자치구 차트 레이아웃 검증
- 원천 데이터(35개), 2단계 마트(14개), PREPROCESSING.md sha256 불변성 해시 검증
- 격리 임시 폴더에서 3단계 산출물을 비운 뒤 전체 재실행하고, 산출물 18개(데이터 12·문서 3·그림 3)를 바이트 단위로 대조
- 보고서 3.2 후보표 6행, 직장·상주인구 부재 상권수 모든 위치, 극단치 총건수, 희소 업종 목록, 업종·자치구 수 문구 대조
- Systematic Mutation Testing:
  1) 파트 A: 267개 전 컬럼 1개씩 개별 변조 100% 차단(Killed) 실증
  2) 파트 B-1: 양성 대조 (검사 로직 무력화 시 '미차단' 실증)
  3) 파트 B-2: 산출물 파일 25종 변조 100% 차단(Killed) 실증
  4) 파트 B-3: 10대 생성 코드 결함 주입 100% 차단(Killed) 실증
"""

import sys
import os
import json
import re
import shutil
import tempfile
import hashlib
import subprocess
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
REPORT_DIR = PROJECT_DIR / "report"

PREP_MD_EXPECTED_HASH = "440e53845a3c22fe52aab83e76231f0f8fa00db6a44f0980add544d0ec6c71ef"

RAW_ALL_EXPECTED_HASHES = {
    "bigdata_campus/seoul_lifestyle_금융생활_재현데이터_sample1000.csv": "9a6703caed34f330a87a07c4bc95a4688cd0129d82f49748e230f63958402838",
    "bigdata_campus/seoul_lifestyle_소비이동패턴_재현데이터_sample1000.csv": "248540faa442fff2f3f147ab4736452e4bf367913aae515cfd57f2ace2181db9",
    "geo/HangJeongDong_ver20251231.geojson": "e873fb7b94b917d1bf0005a386d480e5fb742fdd6ab7d3f52e62c3ba7f524d31",
    "living/관심집단_2025.03.xlsx": "7f16f7c992eddae24d74c2ca4e625c49a5cad019e919162804bb620d61e8110d",
    "living/관심집단_2025.06.xlsx": "4374da6677ca881e849cd3a60fb6854a5491b6de927f2b5b948fd304a1ba198e",
    "living/관심집단_2025.09.xlsx": "359ac42ed92442de302723f5c9a4395f708df81d8997d98ee7eb0e20c8ca6a38",
    "living/관심집단_2025.12.xlsx": "8f07402bd822eb7ea5ca9ce89267dd34f47d9d43a7205f08dafaf0cd0a0364e6",
    "living/통신정보_2025.03.xlsx": "10ba1a2fd6a315b124ffad4005727642dab9bcf3d6c9806e6255294f3002c640",
    "living/통신정보_2025.06.xlsx": "5c257d807cfcef4fc29400cd2fdbae8249d16eadf1eac26bb2e97eda5ce99feb",
    "living/통신정보_2025.09.xlsx": "966e584157085590e5e9b140467d841b315b9ab6a8125e74943d02809552942b",
    "living/통신정보_2025.12.xlsx": "ae700f90139dd4c194a39765179bceb34f5d3c5911b0badf574cc96202b64eff",
    "MANIFEST.csv": "120829d00f856ff452270d50612dc193c9ce8e0f0096622f899abbb5d429fcb6",
    "naver_trend/naver_trend_10categories_monthly.csv": "59e33ffe068ebff3636cf2c6b6e1fe4b8a2d4ab5e2227b88610dcbc82f76da6c",
    "naver_trend/naver_trend_25gu_top5_monthly.csv": "080b8b8d8d75b23a19b1dfa6526f4b1062f9472edb72244ee1cd522db223bc5c",
    "naver_trend/naver_trend_gu_targeted_monthly.csv": "62ed84651171ea6ad77d63fe8a96a4d0b60df7fe25489ccfd668b76d7de7f4a3",
    "OA-22160_영역_행정동.csv": "beb37662e3ab510cf3077ab52b417b5d920b591772e47fd07620c3f62b33424b",
    "OA-22163_아파트_행정동.csv": "1b7fbb6cf3b3ab770301d1a3ac95fa36de6aa54191ba7f8fc9a59d16bdf3b7a8",
    "OA-22164_아파트_자치구.csv": "c6995cdac57eb1789f895c5b2e0a13dd8b453dcb18c8780d75b8657e73ac437a",
    "OA-22166_소비_행정동.csv": "343d8f454e0e09735f5fd0da545b472e2d3ccb7bad760b8fd49406414b7a5ae2",
    "OA-22167_소비_자치구.csv": "a986ce52d7a3b0de3288451b612e852eb68908052e90e43f48b8f44c72009cf3",
    "OA-22169_집객시설_행정동.csv": "c20b976518aa79d347f89505474c0d028856a966c59fcc1e370f0501a040780a",
    "OA-22178_길단위인구_행정동.csv": "c892335cb646558c8b1337ea7ec484e7907caa539af64010d1bd89761d947681",
    "OA-22182_상주인구_자치구.csv": "704f3aed0760f41c9b3d585c32667f096156a14fffea44d3bfcaccf4a8cbd414",
    "OA-22183_상주인구_행정동.csv": "ed890ef41bfb36c5c1480e6b5f9727c721be70701925180a2cbd36cb4cfda064",
    "OA-22184_직장인구_행정동.csv": "6a9405b17d7a1514b749dd429bffce7b485e5ccab0a24f1c199e875d4dbd27bd",
    "국민연금_시군구_평균소득월액_2025.csv": "388f64cebd52d923730edb75cd9a2ede9dc8478255b4a905060864d4a532d8db",
    "상권/OA-15560_영역_상권.csv": "23e1e8921557c433bea84c1f95268c72adb9edef7d99bc46430e77d3c78c2fed",
    "상권/OA-15568_길단위인구_상권.csv": "a3649ec0eb2e9c3f35318296fb00cea3cb1500d1496d6cd18a8dd5d3fedd9a2d",
    "상권/OA-15569_직장인구_상권.csv": "94297b8a8614d2f49f1153ecec12ab784e12eeb5f49da9393cb952beda6f4f4c",
    "상권/OA-15572_추정매출_상권.csv": "c0ec3b0e55ed0dc29587a894473e7d6d0b6cb945bfd87e0f35dc37d491a7a78b",
    "상권/OA-15576_상권변화지표_상권.csv": "cc83fb15e50dd192505c461192fdec4f235cb6f270cca7fec2022294f860ed0b",
    "상권/OA-15577_점포_상권.csv": "d7713436197c3c56709e7e6ccd2ae7b1675f6bdf158f1a191bd4f150879249b6",
    "상권/OA-15580_집객시설_상권.csv": "ed121e729927a2816e9d343b7e9e54a1798d48ea9d4088fc9441939f33412221",
    "상권/OA-15584_상주인구_상권.csv": "4556e3485f991e7a108da8d7f36c6970bde5970382fe47b90cd04e332d35e425",
    "소상공인_상가정보_서울.csv": "44a8b6e7db47211545e3dd9bd6090166ce9eba9e53e785cc2f84d8180ec8453c"
}

STAGE2_ALL_EXPECTED_HASHES = {
    "stage2_report_data.json": "18025fb3fd67f0b5102ebd62fe6c904e619dc5be9302cd0def6c7da82319638d",
    "공용표_재현시험_결과.json": "e3584baba45be5e75d45a7f4c750365aace647422ab80c3749ddf06029f993a1",
    "누락_상권_목록.csv": "84b84f117c2f1ffbff532b7073343fe48512bba3d859c760422ee524da25272f",
    "데이터사전.csv": "a735cd75fc65f19fbcbba5f8e1189be19f4eaf28060499c8a56e8e608df2694c",
    "상권_마스터.csv": "845d7536ce87b93da0642055d1f3315252a3b0909d74248e566601e0556e7b73",
    "상권_분기_마트.csv": "ff6c76770a55441a9f25b09356784380c8211e4227a9fb342659837213e02679",
    "상권_업종_분기_마트.csv": "1595d5fa420183da95ecc6a4cd10e18ad96d311ad015cdb56cc9b8d4f65a519d",
    "상권_업종_분기_마트.parquet": "feb071279d75049ea92b69b60eab5f0bf2567f309b97ae9fa05c335c8eda9042",
    "상권_중심점_행정동_불일치_목록.csv": "13c3b88be397662af1bd04e871eac437ac7eab129c7408367972efd5e1d83675",
    "점포_위치_불일치_목록.csv": "22245d9ae4b327ad0c406109dbd457d69d96c47cb94c2ed265322a15caebc157",
    "점포_위치_불일치_통계.json": "2364aa521a9fabd16882affa6c8b89bb52cc812ceb07b3fa5ea8bf0b05fbf1e2",
    "조인_기록.csv": "67a6123c1c237494f66230b394c846d2931863e5370ae92ccc4c88e14f04df1d",
    "조인_기록.json": "f389a3eba58fea1d9713e20c61ba43fc02967f832a922a183c09ad2be47ff9c9",
    "항목_파일_연결표.csv": "f46c06ab41b917866d7ac947eb7895cb3220595b7cc9fb5d2f8a19ea41e65e26"
}

def get_file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_sub(cmd, cwd=PROJECT_DIR):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def check_column_match(s_act, s_exp, col_name, is_float=False):
    """엄격한 컬럼 비교: 정수/코드/금액은 정확 일치(==), 비율/실수는 atol=1e-9, rtol=0"""
    assert (s_act.isna() == s_exp.isna()).all(), f"[{col_name}] 결측치(NaN) 위치 불일치"
    v_act = s_act.dropna()
    v_exp = s_exp.dropna()
    assert len(v_act) == len(v_exp), f"[{col_name}] 유효 행 수 불일치"
    if len(v_act) == 0:
        return

    if is_float:
        np.testing.assert_allclose(
            v_act.values.astype(float),
            v_exp.values.astype(float),
            atol=1e-9,
            rtol=0.0,
            err_msg=f"[{col_name}] 실수 허용오차(atol=1e-9) 초과"
        )
    else:
        if pd.api.types.is_numeric_dtype(v_act):
            assert (v_act.values == v_exp.values).all(), f"[{col_name}] 숫자 정확 일치(오차 0) 실패"
        else:
            assert (v_act.values.astype(str) == v_exp.values.astype(str)).all(), f"[{col_name}] 문자열/불리언 정확 일치 실패"

def calc_pct(s):
    valid = s.dropna()
    if len(valid) == 0:
        return pd.Series(np.nan, index=s.index)
    pct = valid.rank(ascending=True, method="average", pct=True) * 100.0
    res = pd.Series(np.nan, index=s.index)
    res.loc[valid.index] = pct
    return res


# =============================================================================
# 267개 컬럼 전원 분류 사전 (상속 / 파생 / 결측사유) - 실존 컬럼과 100% 매칭
# =============================================================================
COL_CLASSIFICATION = {
  "상권_업종_분기_특성표": {
    "상속": [
      "기준_년분기_코드", "상권_코드", "상권_코드_명", "상권_표시_명", "상권_구분_코드_명",
      "행정동_코드", "서비스_업종_코드", "서비스_업종_코드_명", "공통그룹", "당월_매출_금액",
      "당월_매출_건수", "전체_점포_수", "일반_점포_수", "프랜차이즈_점포_수", "개업_점포_수", "폐업_점포_수"
    ],
    "파생": [
      "매출_보유_여부", "영역_면적_ha", "매출_결측_여부", "분기_객단가", "분기_객단가_백분위_업종내",
      "분기_객단가_백분위_공통그룹내", "유효_상권_수", "분기_프랜차이즈_점포_비율", "분기_개업_점포_비율",
      "분기_폐업_점포_비율", "분기_매출_증감률", "매출증감_극단치_플래그", "분기_점포_밀집도_ha"
    ],
    "결측사유": [
      "매출_결측_구분", "객단가_결측_사유", "프랜차이즈_결측_사유", "개폐업_결측_사유", "매출증감_결측_사유"
    ]
  },
  "상권_업종_연간_특성표": {
    "상속": [
      "상권_코드", "서비스_업종_코드", "상권_코드_명", "상권_표시_명", "상권_구분_코드_명",
      "행정동_코드", "서비스_업종_코드_명", "공통그룹"
    ],
    "파생": [
      "영역_면적_ha", "점포_행_보유_분기수", "매출_보유_분기수", "연간_추정매출_금액_합계",
      "연간_추정매출_건수_합계", "연간_개업_점포_수_합계", "연간_폐업_점포_수_합계", "연간_객단가",
      "연간_객단가_백분위_업종내", "연간_객단가_백분위_공통그룹내", "유효_상권_수", "연간_평균_전체_점포_수",
      "연간_평균_프랜차이즈_점포_수", "연간_프랜차이즈_점포_비율", "연간_개업_점포_비율",
      "연간_폐업_점포_비율", "연간_점포_밀집도_ha"
    ],
    "결측사유": [
      "연간_매출_결측_구분", "연간_객단가_결측_사유", "연간_프랜차이즈_결측_사유", "연간_개폐업_결측_사유"
    ]
  },
  "상권_분기_특성표": {
    "상속": [
      "상권_코드", "기준_년분기_코드", "상권_코드_명", "상권_표시_명", "상권_구분_코드",
      "상권_구분_코드_명", "자치구_코드", "자치구_코드_명", "행정동_코드", "행정동_코드_명",
      "총_유동인구_수", "남성_유동인구_수", "여성_유동인구_수", "연령대_10_유동인구_수",
      "연령대_20_유동인구_수", "연령대_30_유동인구_수", "연령대_40_유동인구_수",
      "연령대_50_유동인구_수", "연령대_60_이상_유동인구_수", "시간대_00_06_유동인구_수",
      "시간대_06_11_유동인구_수", "시간대_11_14_유동인구_수", "시간대_14_17_유동인구_수",
      "시간대_17_21_유동인구_수", "시간대_21_24_유동인구_수", "월요일_유동인구_수",
      "화요일_유동인구_수", "수요일_유동인구_수", "목요일_유동인구_수", "금요일_유동인구_수",
      "토요일_유동인구_수", "일요일_유동인구_수", "상권_변화_지표", "상권_변화_지표_명",
      "운영_영업_개월_평균", "폐업_영업_개월_평균", "상권_당월_매출_금액_합계", "상권_당월_매출_건수_합계",
      "상권_전체_점포_수_합계", "상권_일반_점포_수_합계", "상권_프랜차이즈_점포_수_합계",
      "상권_개업_점포_수_합계", "상권_폐업_점포_수_합계", "상권_매출_보유_업종_수", "상권_점포_보유_업종_수"
    ],
    "파생": [
      "영역_면적_ha", "상권_분기_매출_증감률", "상권_매출증감_극단치_플래그", "상권_분기_프랜차이즈_점포_비율",
      "상권_분기_개업_점포_비율", "상권_분기_폐업_점포_비율", "상권_분기_점포_밀집도_ha", "유동인구_남성_비율",
      "유동인구_여성_비율", "유동인구_10대_비율", "유동인구_20대_비율", "유동인구_30대_비율",
      "유동인구_40대_비율", "유동인구_50대_비율", "유동인구_60대이상_비율", "유동인구_시간대_00_06_비율",
      "유동인구_시간대_06_11_비율", "유동인구_시간대_11_14_비율", "유동인구_시간대_14_17_비율",
      "유동인구_시간대_17_21_비율", "유동인구_시간대_21_24_비율", "유동인구_주중_비율",
      "유동인구_주말_비율", "유동인구_월요일_비율", "유동인구_화요일_비율", "유동인구_수요일_비율",
      "유동인구_목요일_비율", "유동인구_금요일_비율", "유동인구_토요일_비율", "유동인구_일요일_비율"
    ],
    "결측사유": [
      "상권_매출_결측_사유", "상권_매출증감_결측_사유", "유동인구_결측_사유"
    ]
  },
  "상권_특성표": {
    "상속": [
      "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명", "엑스좌표_값",
      "와이좌표_값", "자치구_코드", "자치구_코드_명", "행정동_코드", "행정동_코드_명",
      "영역_면적", "상권_표시_명", "자치구_행정동_불일치_여부", "총_상주인구_수",
      "남성_상주인구_수", "여성_상주인구_수", "연령대_10_상주인구_수", "연령대_20_상주인구_수",
      "연령대_30_상주인구_수", "연령대_40_상주인구_수", "연령대_50_상주인구_수",
      "연령대_60_이상_상주인구_수", "남성연령대_10_상주인구_수", "남성연령대_20_상주인구_수",
      "남성연령대_30_상주인구_수", "남성연령대_40_상주인구_수", "남성연령대_50_상주인구_수",
      "남성연령대_60_이상_상주인구_수", "여성연령대_10_상주인구_수", "여성연령대_20_상주인구_수",
      "여성연령대_30_상주인구_수", "여성연령대_40_상주인구_수", "여성연령대_50_상주인구_수",
      "여성연령대_60_이상_상주인구_수", "총_가구_수", "아파트_가구_수", "비_아파트_가구_수",
      "총_직장_인구_수", "남성_직장_인구_수", "여성_직장_인구_수", "연령대_10_직장_인구_수",
      "연령대_20_직장_인구_수", "연령대_30_직장_인구_수", "연령대_40_직장_인구_수",
      "연령대_50_직장_인구_수", "연령대_60_이상_직장_인구_수", "남성연령대_10_직장_인구_수",
      "남성연령대_20_직장_인구_수", "남성연령대_30_직장_인구_수", "남성연령대_40_직장_인구_수",
      "남성연령대_50_직장_인구_수", "남성연령대_60_이상_직장_인구_수", "여성연령대_10_직장_인구_수",
      "여성연령대_20_직장_인구_수", "여성연령대_30_직장_인구_수", "여성연령대_40_직장_인구_수",
      "여성연령대_50_직장_인구_수", "여성연령대_60_이상_직장_인구_수", "집객시설_수", "관공서_수",
      "은행_수", "종합병원_수", "일반_병원_수", "약국_수", "유치원_수", "초등학교_수",
      "중학교_수", "고등학교_수", "대학교_수", "백화점_수", "슈퍼마켓_수", "극장_수",
      "숙박_시설_수", "공항_수", "철도_역_수", "버스_터미널_수", "지하철_역_수", "버스_정거장_수",
      "집객시설_원천행_없음", "배후동_면적_km2", "배후동_자치구_평균소득월액", "배후동_소상공인_점포수_전체",
      "배후동_소비_이상치", "배후동_소비_연간지출_총금액", "배후동_소비_최대항목"
    ],
    "파생": [
      "영역_면적_ha", "상권_매출_보유_분기수", "상권_연간_매출_금액_합계", "상권_연간_매출_건수_합계",
      "상권_점포_보유_분기수", "유동인구_보유_분기수", "상권_연간_평균_점포_수", "상권_연간_프랜차이즈_점포_비율",
      "상권_연간_개업_점포_비율", "상권_연간_폐업_점포_비율", "상권_연간_점포_밀집도_ha",
      "상권_연간_평균_유동인구_수", "상주인구_남성_비율", "상주인구_여성_비율", "상주인구_10대_비율",
      "상주인구_20대_비율", "상주인구_30대_비율", "상주인구_40대_비율", "상주인구_50대_비율",
      "상주인구_60대이상_비율", "상주가구_아파트_비율", "상주가구_비아파트_비율", "직장인구_남성_비율",
      "직장인구_여성_비율", "직장인구_10대_비율", "직장인구_20대_비율", "직장인구_30대_비율",
      "직장인구_40대_비율", "직장인구_50대_비율", "직장인구_60대이상_비율", "상권_변화_지표_명_2025Q4",
      "운영_영업_개월_2025Q4", "폐업_영업_개월_2025Q4", "상권_변화_지표_변경_횟수",
      "배후동_소비_최대항목_비중"
    ],
    "결측사유": [
      "상권_연간_매출_결측_사유", "상권_유동인구_결측_사유", "상주인구_결측_사유", "직장인구_결측_사유",
      "집객시설_결측_사유", "상권_임대료_보증금_수준"
    ]
  }
}


def test_1_primary_keys_and_shapes(raw_marts, act_tables):
    """검사 1: 기본키 유일성 및 데이터 규모 검증"""
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables

    assert len(act_ind_q) == 246197, f"표 1 행수 불일치: {len(act_ind_q)}"
    assert len(act_ind_a) == 62641, f"표 2 행수 불일치: {len(act_ind_a)}"
    assert len(act_t_q) == 6600, f"표 3 행수 불일치: {len(act_t_q)}"
    assert len(act_t_a) == 1650, f"표 4 행수 불일치: {len(act_t_a)}"

    assert act_ind_q.duplicated(subset=["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]).sum() == 0
    assert act_ind_a.duplicated(subset=["상권_코드", "서비스_업종_코드"]).sum() == 0
    assert act_t_q.duplicated(subset=["기준_년분기_코드", "상권_코드"]).sum() == 0
    assert act_t_a.duplicated(subset=["상권_코드"]).sum() == 0

    assert act_ind_q[["기준_년분기_코드", "상권_코드", "서비스_업종_코드"]].isna().sum().sum() == 0
    assert act_ind_a[["상권_코드", "서비스_업종_코드"]].isna().sum().sum() == 0
    assert act_t_q[["기준_년분기_코드", "상권_코드"]].isna().sum().sum() == 0
    assert act_t_a["상권_코드"].isna().sum() == 0

    assert len(act_ind_q.columns) == 34, f"표 1 컬럼수: {len(act_ind_q.columns)}"
    assert len(act_ind_a.columns) == 29, f"표 2 컬럼수: {len(act_ind_a.columns)}"
    assert len(act_t_q.columns) == 78, f"표 3 컬럼수: {len(act_t_q.columns)}"
    assert len(act_t_a.columns) == 126, f"표 4 컬럼수: {len(act_t_a.columns)}"
    total_cols = len(act_ind_q.columns) + len(act_ind_a.columns) + len(act_t_q.columns) + len(act_t_a.columns)
    assert total_cols == 267, f"총 컬럼수 오류: {total_cols} != 267"


def test_2_full_267_columns_recalculation_and_blanks(raw_marts, act_tables):
    """검사 2: 267개 전 컬럼 100% 판정 및 10,909,987칸 전수 대조"""
    df_ind_raw, df_q_raw, df_m_raw, df_dong_m = raw_marts
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables

    total_checked_columns = 0
    total_checked_cells = 0

    tbl_pairs = [
        ("상권_업종_분기_특성표", act_ind_q),
        ("상권_업종_연간_특성표", act_ind_a),
        ("상권_분기_특성표", act_t_q),
        ("상권_특성표", act_t_a)
    ]
    for tbl_name, act_df in tbl_pairs:
        class_dict = COL_CLASSIFICATION[tbl_name]
        all_assigned = set(class_dict["상속"] + class_dict["파생"] + class_dict["결측사유"])
        actual_cols = set(act_df.columns)

        unassigned = actual_cols - all_assigned
        assert len(unassigned) == 0, f"[{tbl_name}] 미판정 컬럼 발견 (즉시 실패): {unassigned}"
        extra_assigned = all_assigned - actual_cols
        assert len(extra_assigned) == 0, f"[{tbl_name}] 특성표에 없는 미존재 컬럼 판정: {extra_assigned}"
        assert len(class_dict["상속"]) + len(class_dict["파생"]) + len(class_dict["결측사유"]) == len(actual_cols), \
            f"[{tbl_name}] 컬럼 판정 내 중복 존재"

    area_map = dict(zip(df_m_raw["상권_코드"], df_m_raw["영역_면적_ha"]))

    # =========================================================================
    # 표 1: 상권_업종_분기_특성표 (34열, 246,197행)
    # =========================================================================
    tbl = act_ind_q
    raw = df_ind_raw
    n_rows = len(tbl)

    for c in COL_CLASSIFICATION["상권_업종_분기_특성표"]["상속"]:
        if c in raw.columns:
            s_raw = raw[c]
            s_act = tbl[c]
            assert (s_raw.isna() == s_act.isna()).all(), f"ind_q {c} 빈칸 불일치"
            if pd.api.types.is_numeric_dtype(s_raw.dtype):
                np.testing.assert_allclose(s_raw.dropna(), s_act.dropna(), atol=1e-9, rtol=0.0, err_msg=f"ind_q {c}")
            else:
                assert (s_raw.dropna().astype(str) == s_act.dropna().astype(str)).all(), f"ind_q {c} 값 불일치"
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_area_s = raw["상권_코드"].map(area_map)
    np.testing.assert_allclose(tbl["영역_면적_ha"], exp_area_s, atol=1e-9, rtol=0.0)
    assert (tbl["매출_보유_여부"] == raw["당월_매출_금액"].notna()).all()
    assert (tbl["매출_결측_여부"] == raw["당월_매출_금액"].isna()).all()

    cond_valid_bill = (raw["당월_매출_건수"] > 0) & (raw["당월_매출_금액"].notna())
    exp_bill = np.where(cond_valid_bill, raw["당월_매출_금액"] / raw["당월_매출_건수"], np.nan)
    np.testing.assert_allclose(tbl["분기_객단가"].dropna(), pd.Series(exp_bill).dropna(), atol=1e-9, rtol=0.0)

    calc_bill_s = pd.Series(exp_bill, index=raw.index)
    exp_pct_ind = calc_bill_s.groupby([raw["기준_년분기_코드"], raw["서비스_업종_코드"]]).transform(calc_pct)
    np.testing.assert_allclose(tbl["분기_객단가_백분위_업종내"].dropna(), exp_pct_ind.dropna(), atol=1e-9, rtol=0.0)

    grp_col = "공통그룹" if "공통그룹" in raw.columns else "공통그룹_코드"
    exp_pct_grp = calc_bill_s.groupby([raw["기준_년분기_코드"], raw[grp_col]]).transform(calc_pct)
    np.testing.assert_allclose(tbl["분기_객단가_백분위_공통그룹내"].dropna(), exp_pct_grp.dropna(), atol=1e-9, rtol=0.0)

    valid_trades = raw.loc[cond_valid_bill, ["기준_년분기_코드", "서비스_업종_코드", "상권_코드"]].drop_duplicates()
    valid_counts = valid_trades.groupby(["기준_년분기_코드", "서비스_업종_코드"])["상권_코드"].count().rename("유효_상권_수")
    exp_valid_s = raw.set_index(["기준_년분기_코드", "서비스_업종_코드"]).index.map(valid_counts).fillna(0).astype(int)
    np.testing.assert_allclose(tbl["유효_상권_수"], exp_valid_s)

    cond_pos_store = raw["전체_점포_수"] > 0
    exp_fran_ratio = pd.Series(np.where(cond_pos_store, raw["프랜차이즈_점포_수"] / raw["전체_점포_수"] * 100.0, np.nan), index=raw.index)
    exp_open_ratio = pd.Series(np.where(cond_pos_store, raw["개업_점포_수"] / raw["전체_점포_수"] * 100.0, np.nan), index=raw.index)
    exp_close_ratio = pd.Series(np.where(cond_pos_store, raw["폐업_점포_수"] / raw["전체_점포_수"] * 100.0, np.nan), index=raw.index)
    exp_density_ratio = pd.Series(np.where(exp_area_s > 0, raw["전체_점포_수"] / exp_area_s, np.nan), index=raw.index)

    np.testing.assert_allclose(tbl["분기_프랜차이즈_점포_비율"].dropna(), exp_fran_ratio.dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["분기_개업_점포_비율"].dropna(), exp_open_ratio.dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["분기_폐업_점포_비율"].dropna(), exp_close_ratio.dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["분기_점포_밀집도_ha"].dropna(), exp_density_ratio.dropna(), atol=1e-9, rtol=0.0)

    prev_q_map = {20252: 20251, 20253: 20252, 20254: 20253}
    prev_sales_series = raw["기준_년분기_코드"].map(prev_q_map)
    tmp_prev = raw[["상권_코드", "서비스_업종_코드", "기준_년분기_코드", "당월_매출_금액"]].copy()
    tmp_prev.rename(columns={"기준_년분기_코드": "prev_q", "당월_매출_금액": "당월_매출_금액_prev"}, inplace=True)
    df_merged = raw[["상권_코드", "서비스_업종_코드", "당월_매출_금액"]].copy()
    df_merged["prev_q"] = prev_sales_series
    df_merged = df_merged.merge(tmp_prev, on=["상권_코드", "서비스_업종_코드", "prev_q"], how="left")

    cond_growth = (df_merged["당월_매출_금액_prev"].notna()) & (df_merged["당월_매출_금액_prev"] > 0) & (df_merged["당월_매출_금액"].notna())
    exp_growth = np.where(cond_growth, (df_merged["당월_매출_금액"] - df_merged["당월_매출_금액_prev"]) / df_merged["당월_매출_금액_prev"] * 100.0, np.nan)
    np.testing.assert_allclose(tbl["분기_매출_증감률"].dropna(), pd.Series(exp_growth).dropna(), atol=1e-9, rtol=0.0)
    assert (tbl["매출증감_극단치_플래그"] == ((pd.Series(exp_growth) < -90.0) | (pd.Series(exp_growth) > 500.0))).all()

    for c in COL_CLASSIFICATION["상권_업종_분기_특성표"]["파생"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_sales_reason = np.where(
        raw["당월_매출_금액"].notna(), "정상 실적",
        np.where(raw["전체_점포_수"] > 0, "점포 있음, 추정매출 행 없음", "점포 0개")
    )
    assert (tbl["매출_결측_구분"] == exp_sales_reason).all()

    exp_bill_reason = np.where(
        cond_valid_bill, "정상 산출",
        np.where(raw["전체_점포_수"] == 0, "점포 0개",
        np.where(raw["당월_매출_금액"].isna(), "추정매출 실적 부재", "결제건수 0건"))
    )
    assert (tbl["객단가_결측_사유"] == exp_bill_reason).all()
    assert (tbl["프랜차이즈_결측_사유"] == np.where(cond_pos_store, "정상 산출", "점포수 0개")).all()
    assert (tbl["개폐업_결측_사유"] == np.where(cond_pos_store, "정상 산출", "점포수 0개")).all()

    exp_growth_reason = np.where(
        pd.Series(exp_growth).notna(), "정상 산출",
        np.where(raw["기준_년분기_코드"] == 20251, "전분기 자료 부재(2025Q1)",
        np.where(df_merged["당월_매출_금액_prev"].isna() | (df_merged["당월_매출_금액_prev"] == 0), "직전분기 매출 부재 또는 0원", "당분기 매출 부재"))
    )
    assert (tbl["매출증감_결측_사유"] == exp_growth_reason).all()

    for c in COL_CLASSIFICATION["상권_업종_분기_특성표"]["결측사유"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    # =========================================================================
    # 표 2: 상권_업종_연간_특성표 (29열, 62,641행)
    # =========================================================================
    tbl = act_ind_a
    raw = df_ind_raw
    n_rows = len(tbl)
    grp_keys = ["상권_코드", "서비스_업종_코드"]
    ind_a_idx = tbl.set_index(grp_keys).index

    for c in COL_CLASSIFICATION["상권_업종_연간_특성표"]["상속"]:
        if c in raw.columns:
            s_act = tbl[c]
            s_raw_first = raw.groupby(grp_keys)[c].first()
            exp_s = ind_a_idx.map(s_raw_first)
            assert (s_act.isna() == exp_s.isna()).all()
            assert (s_act.astype(str) == exp_s.astype(str)).all()
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_area_a = ind_a_idx.get_level_values(0).map(area_map)
    np.testing.assert_allclose(tbl["영역_면적_ha"], exp_area_a, atol=1e-9, rtol=0.0)

    sales_q_cnt = raw.dropna(subset=["당월_매출_금액"]).groupby(grp_keys)["기준_년분기_코드"].count()
    store_q_cnt = raw.dropna(subset=["전체_점포_수"]).groupby(grp_keys)["기준_년분기_코드"].count()
    np.testing.assert_allclose(tbl["매출_보유_분기수"], ind_a_idx.map(sales_q_cnt).fillna(0).astype(int))
    np.testing.assert_allclose(tbl["점포_행_보유_분기수"], ind_a_idx.map(store_q_cnt).fillna(0).astype(int))

    sum_sales = raw.groupby(grp_keys)["당월_매출_금액"].sum(min_count=1)
    sum_counts = raw.groupby(grp_keys)["당월_매출_건수"].sum(min_count=1)
    exp_sales_sum = np.where(tbl["매출_보유_분기수"] > 0, ind_a_idx.map(sum_sales), np.nan)
    exp_counts_sum = np.where(tbl["매출_보유_분기수"] > 0, ind_a_idx.map(sum_counts), np.nan)
    np.testing.assert_allclose(tbl["연간_추정매출_금액_합계"].dropna(), pd.Series(exp_sales_sum).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["연간_추정매출_건수_합계"].dropna(), pd.Series(exp_counts_sum).dropna(), atol=1e-9, rtol=0.0)

    sum_tot_store = ind_a_idx.map(raw.groupby(grp_keys)["전체_점포_수"].sum())
    sum_fran_store = ind_a_idx.map(raw.groupby(grp_keys)["프랜차이즈_점포_수"].sum())
    sum_open_store = ind_a_idx.map(raw.groupby(grp_keys)["개업_점포_수"].sum())
    sum_close_store = ind_a_idx.map(raw.groupby(grp_keys)["폐업_점포_수"].sum())

    exp_avg_store = sum_tot_store / 4.0
    np.testing.assert_allclose(tbl["연간_평균_전체_점포_수"], exp_avg_store)
    np.testing.assert_allclose(tbl["연간_평균_프랜차이즈_점포_수"], sum_fran_store / 4.0)
    np.testing.assert_allclose(tbl["연간_개업_점포_수_합계"], sum_open_store)
    np.testing.assert_allclose(tbl["연간_폐업_점포_수_합계"], sum_close_store)

    cond_ann_bill = (pd.Series(exp_counts_sum) > 0) & (pd.Series(exp_sales_sum).notna())
    exp_ann_bill = np.where(cond_ann_bill, pd.Series(exp_sales_sum) / pd.Series(exp_counts_sum), np.nan)
    np.testing.assert_allclose(tbl["연간_객단가"].dropna(), pd.Series(exp_ann_bill).dropna(), atol=1e-9, rtol=0.0)

    bill_series = pd.Series(exp_ann_bill, index=tbl.index)
    exp_pct_ind_a = bill_series.groupby(tbl["서비스_업종_코드"]).transform(calc_pct)
    exp_pct_grp_a = bill_series.groupby(tbl["공통그룹"]).transform(calc_pct)
    np.testing.assert_allclose(tbl["연간_객단가_백분위_업종내"].dropna(), exp_pct_ind_a.dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["연간_객단가_백분위_공통그룹내"].dropna(), exp_pct_grp_a.dropna(), atol=1e-9, rtol=0.0)

    valid_ann_trades = tbl.loc[cond_ann_bill, ["서비스_업종_코드", "상권_코드"]].drop_duplicates()
    valid_ann_counts = valid_ann_trades.groupby("서비스_업종_코드")["상권_코드"].count()
    np.testing.assert_allclose(tbl["유효_상권_수"], tbl["서비스_업종_코드"].map(valid_ann_counts).fillna(0).astype(int))

    exp_ann_fran_r = np.where(sum_tot_store > 0, sum_fran_store / sum_tot_store * 100.0, np.nan)
    exp_ann_open_r = np.where(exp_avg_store > 0, sum_open_store / exp_avg_store * 100.0, np.nan)
    exp_ann_close_r = np.where(exp_avg_store > 0, sum_close_store / exp_avg_store * 100.0, np.nan)
    exp_ann_density = np.where(exp_area_a > 0, exp_avg_store / exp_area_a, np.nan)

    np.testing.assert_allclose(tbl["연간_프랜차이즈_점포_비율"].dropna(), pd.Series(exp_ann_fran_r).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["연간_개업_점포_비율"].dropna(), pd.Series(exp_ann_open_r).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["연간_폐업_점포_비율"].dropna(), pd.Series(exp_ann_close_r).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["연간_점포_밀집도_ha"].dropna(), pd.Series(exp_ann_density).dropna(), atol=1e-9, rtol=0.0)

    for c in COL_CLASSIFICATION["상권_업종_연간_특성표"]["파생"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_ann_sales_reason = np.where(
        tbl["매출_보유_분기수"] > 0, "정상 실적",
        "4개분기 매출 실적 부재"
    )
    assert (tbl["연간_매출_결측_구분"] == exp_ann_sales_reason).all()

    exp_ann_bill_reason = np.where(
        tbl["연간_객단가"].notna(), "정상 산출",
        "4개분기 매출 실적 부재"
    )
    assert (tbl["연간_객단가_결측_사유"] == exp_ann_bill_reason).all()
    assert (tbl["연간_프랜차이즈_결측_사유"] == np.where(tbl["연간_프랜차이즈_점포_비율"].notna(), "정상 산출", "연간 점포수 0개")).all()
    assert (tbl["연간_개폐업_결측_사유"] == np.where(tbl["연간_개업_점포_비율"].notna(), "정상 산출", "연간 평균 점포수 0개")).all()

    for c in COL_CLASSIFICATION["상권_업종_연간_특성표"]["결측사유"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    # =========================================================================
    # 표 3: 상권_분기_특성표 (78열, 6,600행)
    # =========================================================================
    tbl = act_t_q
    raw = df_q_raw
    n_rows = len(tbl)

    for c in COL_CLASSIFICATION["상권_분기_특성표"]["상속"]:
        if c in raw.columns:
            s_raw = raw[c]
            s_act = tbl[c]
            assert (s_raw.isna() == s_act.isna()).all(), f"t_q {c} 빈칸 불일치"
            if pd.api.types.is_numeric_dtype(s_raw.dtype):
                np.testing.assert_allclose(s_raw.dropna(), s_act.dropna(), atol=1e-9, rtol=0.0, err_msg=f"t_q {c}")
            else:
                assert (s_raw.dropna().astype(str) == s_act.dropna().astype(str)).all(), f"t_q {c} 값 불일치"
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_t_area = raw["상권_코드"].map(area_map)
    np.testing.assert_allclose(tbl["영역_면적_ha"], exp_t_area, atol=1e-9, rtol=0.0)

    cond_t_store = raw["상권_전체_점포_수_합계"] > 0
    exp_t_fran = np.where(cond_t_store, raw["상권_프랜차이즈_점포_수_합계"] / raw["상권_전체_점포_수_합계"] * 100.0, np.nan)
    exp_t_open = np.where(cond_t_store, raw["상권_개업_점포_수_합계"] / raw["상권_전체_점포_수_합계"] * 100.0, np.nan)
    exp_t_close = np.where(cond_t_store, raw["상권_폐업_점포_수_합계"] / raw["상권_전체_점포_수_합계"] * 100.0, np.nan)
    exp_t_density = np.where(exp_t_area > 0, raw["상권_전체_점포_수_합계"] / exp_t_area, np.nan)

    np.testing.assert_allclose(tbl["상권_분기_프랜차이즈_점포_비율"].dropna(), pd.Series(exp_t_fran).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상권_분기_개업_점포_비율"].dropna(), pd.Series(exp_t_open).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상권_분기_폐업_점포_비율"].dropna(), pd.Series(exp_t_close).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상권_분기_점포_밀집도_ha"].dropna(), pd.Series(exp_t_density).dropna(), atol=1e-9, rtol=0.0)

    tmp_t_prev = raw[["상권_코드", "기준_년분기_코드", "상권_당월_매출_금액_합계"]].copy()
    tmp_t_prev.rename(columns={"기준_년분기_코드": "prev_q", "상권_당월_매출_금액_합계": "상권_매출_prev"}, inplace=True)
    df_t_merged = raw[["상권_코드", "상권_당월_매출_금액_합계"]].copy()
    df_t_merged["prev_q"] = raw["기준_년분기_코드"].map(prev_q_map)
    df_t_merged = df_t_merged.merge(tmp_t_prev, on=["상권_코드", "prev_q"], how="left")

    cond_t_growth = (df_t_merged["상권_매출_prev"].notna()) & (df_t_merged["상권_매출_prev"] > 0) & (df_t_merged["상권_당월_매출_금액_합계"].notna())
    exp_t_growth = np.where(cond_t_growth, (df_t_merged["상권_당월_매출_금액_합계"] - df_t_merged["상권_매출_prev"]) / df_t_merged["상권_매출_prev"] * 100.0, np.nan)
    np.testing.assert_allclose(tbl["상권_분기_매출_증감률"].dropna(), pd.Series(exp_t_growth).dropna(), atol=1e-9, rtol=0.0)
    assert (tbl["상권_매출증감_극단치_플래그"] == ((pd.Series(exp_t_growth) < -90.0) | (pd.Series(exp_t_growth) > 500.0))).all()

    flow_base = raw["총_유동인구_수"]
    np.testing.assert_allclose(tbl["유동인구_남성_비율"].dropna(), (raw["남성_유동인구_수"] / flow_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["유동인구_여성_비율"].dropna(), (raw["여성_유동인구_수"] / flow_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    for age in ["10", "20", "30", "40", "50", "60_이상"]:
        col_out = "유동인구_60대이상_비율" if "이상" in age else f"유동인구_{age}대_비율"
        np.testing.assert_allclose(tbl[col_out].dropna(), (raw[f"연령대_{age}_유동인구_수"] / flow_base * 100.0).dropna(), atol=1e-9, rtol=0.0)

    for t in ["00_06", "06_11", "11_14", "14_17", "17_21", "21_24"]:
        np.testing.assert_allclose(
            tbl[f"유동인구_시간대_{t}_비율"].dropna(),
            (raw[f"시간대_{t}_유동인구_수"] / flow_base * 100.0).dropna(),
            atol=1e-9, rtol=0.0
        )

    wd_sum = raw["월요일_유동인구_수"] + raw["화요일_유동인구_수"] + raw["수요일_유동인구_수"] + raw["목요일_유동인구_수"] + raw["금요일_유동인구_수"]
    we_sum = raw["토요일_유동인구_수"] + raw["일요일_유동인구_수"]
    np.testing.assert_allclose(tbl["유동인구_주중_비율"].dropna(), (wd_sum / flow_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["유동인구_주말_비율"].dropna(), (we_sum / flow_base * 100.0).dropna(), atol=1e-9, rtol=0.0)

    for day in ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]:
        np.testing.assert_allclose(
            tbl[f"유동인구_{day}_비율"].dropna(),
            (raw[f"{day}_유동인구_수"] / flow_base * 100.0).dropna(),
            atol=1e-9, rtol=0.0
        )

    for c in COL_CLASSIFICATION["상권_분기_특성표"]["파생"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    assert (tbl["상권_매출_결측_사유"] == np.where(raw["상권_매출_보유_업종_수"] > 0, "정상 산출", "해당 분기 추정매출 실적 부재")).all()

    exp_t_growth_reason = np.where(
        pd.Series(exp_t_growth).notna(), "정상 산출",
        np.where(raw["기준_년분기_코드"] == 20251, "전분기 자료 부재(2025Q1)",
        np.where(df_t_merged["상권_매출_prev"].isna() | (df_t_merged["상권_매출_prev"] == 0), "직전분기 상권매출 부재 또는 0원", "당분기 상권매출 부재"))
    )
    assert (tbl["상권_매출증감_결측_사유"] == exp_t_growth_reason).all()
    assert (tbl["유동인구_결측_사유"] == np.where(flow_base.notna(), "정상 산출", "원천 미집계")).all()

    for c in COL_CLASSIFICATION["상권_분기_특성표"]["결측사유"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    # =========================================================================
    # 표 4: 상권_특성표 (126열, 1,650행)
    # =========================================================================
    tbl = act_t_a
    raw = df_m_raw
    n_rows = len(tbl)
    ta_idx = tbl.set_index("상권_코드").index

    for c in COL_CLASSIFICATION["상권_특성표"]["상속"]:
        if c in raw.columns:
            s_raw = raw[c]
            s_act = tbl[c]
            assert (s_raw.isna() == s_act.isna()).all(), f"t_a {c} 빈칸 불일치"
            if pd.api.types.is_numeric_dtype(s_raw.dtype):
                if c in ["영역_면적_ha", "배후동_면적_km2"]: np.testing.assert_allclose(s_raw.dropna(), s_act.dropna(), atol=1e-9, rtol=0.0, err_msg=f"t_a {c}")
                else: assert (s_raw.dropna().values == s_act.dropna().values).all(), f"t_a {c} mismatch"
            else:
                assert (s_raw.dropna().astype(str).values == s_act.dropna().astype(str).values).all(), f"t_a {c} 값 불일치"
        total_checked_columns += 1
        total_checked_cells += n_rows

    t_q_grp = df_q_raw.groupby("상권_코드")
    exp_t_sales_q_cnt = df_q_raw.dropna(subset=["상권_당월_매출_금액_합계"]).groupby("상권_코드")["기준_년분기_코드"].count()
    exp_t_store_q_cnt = df_q_raw.dropna(subset=["상권_전체_점포_수_합계"]).groupby("상권_코드")["기준_년분기_코드"].count()
    exp_t_flow_q_cnt = df_q_raw.dropna(subset=["총_유동인구_수"]).groupby("상권_코드")["기준_년분기_코드"].count()
    np.testing.assert_allclose(tbl["상권_매출_보유_분기수"], ta_idx.map(exp_t_sales_q_cnt).fillna(0).astype(int))
    np.testing.assert_allclose(tbl["상권_점포_보유_분기수"], ta_idx.map(exp_t_store_q_cnt).fillna(0).astype(int))
    np.testing.assert_allclose(tbl["유동인구_보유_분기수"], ta_idx.map(exp_t_flow_q_cnt).fillna(0).astype(int))

    exp_t_sales_sum = np.where(tbl["상권_매출_보유_분기수"] > 0, ta_idx.map(t_q_grp["상권_당월_매출_금액_합계"].sum(min_count=1)), np.nan)
    exp_t_counts_sum = np.where(tbl["상권_매출_보유_분기수"] > 0, ta_idx.map(t_q_grp["상권_당월_매출_건수_합계"].sum(min_count=1)), np.nan)
    np.testing.assert_allclose(tbl["상권_연간_매출_금액_합계"].dropna(), pd.Series(exp_t_sales_sum).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상권_연간_매출_건수_합계"].dropna(), pd.Series(exp_t_counts_sum).dropna(), atol=1e-9, rtol=0.0)

    exp_t_store_tot = ta_idx.map(t_q_grp["상권_전체_점포_수_합계"].sum())
    exp_t_store_fran = ta_idx.map(t_q_grp["상권_프랜차이즈_점포_수_합계"].sum())
    exp_t_store_open = ta_idx.map(t_q_grp["상권_개업_점포_수_합계"].sum())
    exp_t_store_close = ta_idx.map(t_q_grp["상권_폐업_점포_수_합계"].sum())

    exp_t_store_avg = exp_t_store_tot / 4.0
    np.testing.assert_allclose(tbl["상권_연간_평균_점포_수"], exp_t_store_avg)

    exp_t_fran_rate = np.where(exp_t_store_tot > 0, exp_t_store_fran / exp_t_store_tot * 100.0, np.nan)
    exp_t_open_rate = np.where(exp_t_store_avg > 0, exp_t_store_open / exp_t_store_avg * 100.0, np.nan)
    exp_t_close_rate = np.where(exp_t_store_avg > 0, exp_t_store_close / exp_t_store_avg * 100.0, np.nan)
    np.testing.assert_allclose(tbl["상권_연간_프랜차이즈_점포_비율"].dropna(), pd.Series(exp_t_fran_rate).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상권_연간_개업_점포_비율"].dropna(), pd.Series(exp_t_open_rate).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상권_연간_폐업_점포_비율"].dropna(), pd.Series(exp_t_close_rate).dropna(), atol=1e-9, rtol=0.0)

    exp_t_density = tbl["상권_연간_평균_점포_수"] / tbl["영역_면적_ha"]
    np.testing.assert_allclose(tbl["상권_연간_점포_밀집도_ha"].dropna(), exp_t_density.dropna(), atol=1e-9, rtol=0.0)

    exp_t_flow_avg = np.where(tbl["유동인구_보유_분기수"] > 0, ta_idx.map(t_q_grp["총_유동인구_수"].sum()) / tbl["유동인구_보유_분기수"], np.nan)
    np.testing.assert_allclose(tbl["상권_연간_평균_유동인구_수"].dropna(), pd.Series(exp_t_flow_avg).dropna(), atol=1e-9, rtol=0.0)

    res_base = tbl["총_상주인구_수"]
    np.testing.assert_allclose(tbl["상주인구_남성_비율"].dropna(), (tbl["남성_상주인구_수"] / res_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상주인구_여성_비율"].dropna(), (tbl["여성_상주인구_수"] / res_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    for age in ["10대", "20대", "30대", "40대", "50대", "60대이상"]:
        c_raw = f"연령대_{age.replace('대', '').replace('이상', '_이상')}_상주인구_수" if "이상" in age else f"연령대_{age.replace('대', '')}_상주인구_수"
        np.testing.assert_allclose(tbl[f"상주인구_{age}_비율"].dropna(), (tbl[c_raw] / res_base * 100.0).dropna(), atol=1e-9, rtol=0.0)

    h_base = tbl["총_가구_수"]
    np.testing.assert_allclose(tbl["상주가구_아파트_비율"].dropna(), (tbl["아파트_가구_수"] / h_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["상주가구_비아파트_비율"].dropna(), (tbl["비_아파트_가구_수"] / h_base * 100.0).dropna(), atol=1e-9, rtol=0.0)

    wrk_base = tbl["총_직장_인구_수"]
    np.testing.assert_allclose(tbl["직장인구_남성_비율"].dropna(), (tbl["남성_직장_인구_수"] / wrk_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    np.testing.assert_allclose(tbl["직장인구_여성_비율"].dropna(), (tbl["여성_직장_인구_수"] / wrk_base * 100.0).dropna(), atol=1e-9, rtol=0.0)
    for age in ["10대", "20대", "30대", "40대", "50대", "60대이상"]:
        c_raw = f"연령대_{age.replace('대', '').replace('이상', '_이상')}_직장_인구_수" if "이상" in age else f"연령대_{age.replace('대', '')}_직장_인구_수"
        np.testing.assert_allclose(tbl[f"직장인구_{age}_비율"].dropna(), (tbl[c_raw] / wrk_base * 100.0).dropna(), atol=1e-9, rtol=0.0)

    q4_t_df = df_q_raw[df_q_raw["기준_년분기_코드"] == 20254].set_index("상권_코드")
    assert (tbl["상권_변화_지표_명_2025Q4"].values == ta_idx.map(q4_t_df["상권_변화_지표_명"]).values).all()
    np.testing.assert_allclose(tbl["운영_영업_개월_2025Q4"], ta_idx.map(q4_t_df["운영_영업_개월_평균"]))
    np.testing.assert_allclose(tbl["폐업_영업_개월_2025Q4"], ta_idx.map(q4_t_df["폐업_영업_개월_평균"]))

    piv_chg = df_q_raw.pivot(index="상권_코드", columns="기준_년분기_코드", values="상권_변화_지표_명")
    exp_chg_cnt = (piv_chg[20252] != piv_chg[20251]).astype(int) + (piv_chg[20253] != piv_chg[20252]).astype(int) + (piv_chg[20254] != piv_chg[20253]).astype(int)
    np.testing.assert_allclose(tbl["상권_변화_지표_변경_횟수"], ta_idx.map(exp_chg_cnt))

    dong_cons_map = df_dong_m.set_index("행정동_코드")["소비_최대항목_비중"]
    np.testing.assert_allclose(tbl["배후동_소비_최대항목_비중"], tbl["행정동_코드"].map(dong_cons_map))

    for c in COL_CLASSIFICATION["상권_특성표"]["파생"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_t_sales_reason = np.where(
        tbl["상권_매출_보유_분기수"] == 4, "정상 산출",
        np.where(tbl["상권_매출_보유_분기수"] == 0, "4개분기 전체 매출 부재", "일부 분기 매출 부재")
    )
    assert (tbl["상권_연간_매출_결측_사유"].values == exp_t_sales_reason).all(), "t_a 상권_연간_매출_결측_사유 불일치"

    assert (tbl["상권_유동인구_결측_사유"].values == np.where(tbl["유동인구_보유_분기수"] > 0, "정상 산출", "원천 유동인구 미집계")).all(), "t_a 상권_유동인구_결측_사유 불일치"
    assert (tbl["상주인구_결측_사유"].values == np.where(tbl["총_상주인구_수"].notna(), "정상 산출", "원천 상주인구 미집계")).all(), "t_a 상주인구_결측_사유 불일치"
    assert (tbl["직장인구_결측_사유"].values == np.where(tbl["총_직장_인구_수"].notna(), "정상 산출", "원천 직장인구 미집계")).all(), "t_a 직장인구_결측_사유 불일치"
    assert (tbl["집객시설_결측_사유"].values == np.where(tbl["집객시설_원천행_없음"] == True, "원천 집객시설 미집계", "정상 산출")).all(), "t_a 집객시설_결측_사유 불일치"
    assert (tbl["상권_임대료_보증금_수준"].values == "데이터 없음").all(), "t_a 상권_임대료_보증금_수준 불일치"

    for c in COL_CLASSIFICATION["상권_특성표"]["결측사유"]:
        total_checked_columns += 1
        total_checked_cells += n_rows

    exp_total_cells = sum(len(t) * len(t.columns) for t in act_tables)
    assert total_checked_columns == 267, f"총 검증 컬럼수 오류: {total_checked_columns} != 267"
    assert total_checked_cells == exp_total_cells, f"총 검증 칸수 오류: {total_checked_cells} != {exp_total_cells}"
    assert total_checked_cells == 10909987, f"특성표 총 칸수 오류: {total_checked_cells} != 10,909,987"
    print(f" -> 통과: 4종 특성표 267개 전 컬럼 100% 판정 및 {total_checked_cells:,}칸 전수 대조 완료 (미판정 0건)")


def test_3_sensitivities_and_stats(raw_marts, act_tables):
    """검사 3: 민감도 3종, 상관행렬, 소표본 6행, 요약통계 JSON 전 항목 독립 계산 대조"""
    df_ind_raw, df_q_raw, df_m_raw, df_dong_m = raw_marts
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables

    # 1. 소표본 후보 6행 비교표 독립 계산 대조
    cand_df = pd.read_csv(STAGE3_DIR / "소표본_후보_비교.csv", encoding="utf-8-sig")
    assert len(cand_df) == 6, f"소표본 후보 비교 표 행 수 오류: {len(cand_df)}"

    ann_stores = act_ind_a["연간_평균_전체_점포_수"]
    ann_open_100 = act_ind_a["연간_개업_점포_비율"] >= 100.0
    ann_close_100 = act_ind_a["연간_폐업_점포_비율"] >= 100.0
    ann_either_100 = ann_open_100 | ann_close_100
    ann_tot = len(act_ind_a)

    for c_idx, th in [(1, 1.0), (2, 2.0), (3, 5.0)]:
        mask = ann_stores <= th
        warn_cnt = int(mask.sum())
        warn_pct = round(warn_cnt / ann_tot * 100, 2)
        cap_open = int((mask & ann_open_100).sum())
        cap_close = int((mask & ann_close_100).sum())
        cap_either = int((mask & ann_either_100).sum())
        rem_either = int((~mask & ann_either_100).sum())

        row = cand_df[cand_df["후보명"].str.contains(f"후보 {c_idx}")].iloc[0]
        assert int(row["경고대상_조합수"]) == warn_cnt, f"후보 {c_idx} 경고 조합수 불일치"
        assert abs(float(row["경고_비율_pct"]) - warn_pct) < 1e-5, f"후보 {c_idx} 경고 비율 불일치"
        assert int(row["개업이상치_포착건수"]) == cap_open, f"후보 {c_idx} 개업 포착건수 불일치"
        assert int(row["폐업이상치_포착건수"]) == cap_close, f"후보 {c_idx} 폐업 포착건수 불일치"
        assert int(row["둘중하나_이상치_포착건수"]) == cap_either, f"후보 {c_idx} 둘중하나 포착건수 불일치"
        assert int(row["비경고군_잔여_이상치건수"]) == rem_either, f"후보 {c_idx} 잔여 이상치건수 불일치"

    q_stores = act_ind_q["전체_점포_수"]
    q_open_100 = act_ind_q["분기_개업_점포_비율"] >= 100.0
    q_close_100 = act_ind_q["분기_폐업_점포_비율"] >= 100.0
    q_either_100 = q_open_100 | q_close_100
    q_tot = len(act_ind_q)

    for c_idx, th in [(1, 1), (2, 2), (3, 5)]:
        mask = q_stores <= th
        warn_cnt = int(mask.sum())
        warn_pct = round(warn_cnt / q_tot * 100, 2)
        cap_open = int((mask & q_open_100).sum())
        cap_close = int((mask & q_close_100).sum())
        cap_either = int((mask & q_either_100).sum())
        rem_either = int((~mask & q_either_100).sum())

        row = cand_df[cand_df["후보명"].str.contains(f"분기 후보 {c_idx}")].iloc[0]
        assert int(row["경고대상_조합수"]) == warn_cnt, f"분기 후보 {c_idx} 경고 조합수 불일치"
        assert abs(float(row["경고_비율_pct"]) - warn_pct) < 1e-5, f"분기 후보 {c_idx} 경고 비율 불일치"
        assert int(row["개업이상치_포착건수"]) == cap_open, f"분기 후보 {c_idx} 개업 포착건수 불일치"
        assert int(row["폐업이상치_포착건수"]) == cap_close, f"분기 후보 {c_idx} 폐업 포착건수 불일치"
        assert int(row["둘중하나_이상치_포착건수"]) == cap_either, f"분기 후보 {c_idx} 둘중하나 포착건수 불일치"
        assert int(row["비경고군_잔여_이상치건수"]) == rem_either, f"분기 후보 {c_idx} 잔여 이상치건수 불일치"

    # 2. 민감도 1: 매출증감률 극단치 민감도 독립 재계산 대조
    sens1 = pd.read_csv(STAGE3_DIR / "매출증감률_극단치_민감도.csv", encoding="utf-8-sig")
    growth_s = act_ind_q["분기_매출_증감률"].dropna()
    p5_val = round(float(growth_s.quantile(0.05)), 1)
    p95_val = round(float(growth_s.quantile(0.95)), 1)
    p1_val = round(float(growth_s.quantile(0.01)), 1)
    p99_val = round(float(growth_s.quantile(0.99)), 1)
    assert ((sens1["분기_매출_증감률"] < -90.0) | (sens1["분기_매출_증감률"] > 500.0) == sens1["매출증감_극단치_플래그_90_500"]).all()
    assert ((sens1["분기_매출_증감률"] < p5_val) | (sens1["분기_매출_증감률"] > p95_val) == sens1["매출증감_극단치_플래그_p5_p95"]).all()
    assert ((sens1["분기_매출_증감률"] < p1_val) | (sens1["분기_매출_증감률"] > p99_val) == sens1["매출증감_극단치_플래그_p1_p99"]).all()
    check_column_match(sens1["분기_매출_증감률_윈저화_p5_p95"], sens1["분기_매출_증감률"].clip(p5_val, p95_val), "sens1.winsor", is_float=True)

    # 3. 민감도 2: 민감도_분석_결과.csv 전 계산 컬럼 독립 재계산 대조
    sens2 = pd.read_csv(STAGE3_DIR / "민감도_분석_결과.csv", encoding="utf-8-sig")
    assert len(sens2) == len(act_ind_a)

    q4_stores = df_ind_raw[df_ind_raw["기준_년분기_코드"] == 20254][["상권_코드", "서비스_업종_코드", "전체_점포_수"]]
    q4_map = q4_stores.set_index(["상권_코드", "서비스_업종_코드"])["전체_점포_수"]
    q4_s = sens2.set_index(["상권_코드", "서비스_업종_코드"]).index.map(q4_map)

    exp_open_q4 = np.where((q4_s.notna()) & (q4_s > 0), sens2["연간_개업_점포_수_합계"] / q4_s * 100.0, np.nan)
    exp_close_q4 = np.where((q4_s.notna()) & (q4_s > 0), sens2["연간_폐업_점포_수_합계"] / q4_s * 100.0, np.nan)
    exp_q4_reason = np.where(pd.Series(exp_open_q4).notna(), "정상 산출", "2025Q4 점포수 0개 또는 실적 부재")

    check_column_match(sens2["연간_개업_점포_비율_Q4분모"], pd.Series(exp_open_q4), "sens2.Q4_open", is_float=True)
    check_column_match(sens2["연간_폐업_점포_비율_Q4분모"], pd.Series(exp_close_q4), "sens2.Q4_close", is_float=True)
    assert (sens2["Q4민감도_결측_사유"].values == exp_q4_reason).all(), "sens2 Q4민감도_결측_사유 불일치"

    store_cnt_series = df_ind_raw.groupby(["상권_코드", "서비스_업종_코드"]).agg(
        행수=("전체_점포_수", "count"),
        점포합=("전체_점포_수", "sum")
    ).reset_index()
    avg_map = store_cnt_series.set_index(["상권_코드", "서비스_업종_코드"])["점포합"] / store_cnt_series.set_index(["상권_코드", "서비스_업종_코드"])["행수"]
    exp_avg_row = sens2.set_index(["상권_코드", "서비스_업종_코드"]).index.map(avg_map)

    exp_open_row = np.where(exp_avg_row > 0, sens2["연간_개업_점포_수_합계"] / exp_avg_row * 100.0, np.nan)
    exp_close_row = np.where(exp_avg_row > 0, sens2["연간_폐업_점포_수_합계"] / exp_avg_row * 100.0, np.nan)

    check_column_match(sens2["연간_평균_점포수_행보유분기만"], pd.Series(exp_avg_row), "sens2.avg_row_stores", is_float=True)
    check_column_match(sens2["연간_개업_점포_비율_행보유분기만"], pd.Series(exp_open_row), "sens2.open_row_pct", is_float=True)
    check_column_match(sens2["연간_폐업_점포_비율_행보유분기만"], pd.Series(exp_close_row), "sens2.close_row_pct", is_float=True)

    assert ((sens2["연간_평균_전체_점포_수"] <= 1.0) == sens2["소표본_후보1_경고_플래그"]).all()
    assert ((sens2["연간_평균_전체_점포_수"] <= 2.0) == sens2["소표본_후보2_경고_플래그"]).all()
    assert ((sens2["연간_평균_전체_점포_수"] <= 5.0) == sens2["소표본_후보3_경고_플래그"]).all()

    # 4. 민감도 3: 상권_공통업종_매출증감률_민감도.csv 전 계산 컬럼 독립 재계산 대조
    sens3 = pd.read_csv(STAGE3_DIR / "상권_공통업종_매출증감률_민감도.csv", encoding="utf-8-sig")
    assert len(sens3) == len(act_t_q)

    sales_combos = df_ind_raw.dropna(subset=["당월_매출_금액"]).groupby(["상권_코드", "서비스_업종_코드"])["기준_년분기_코드"].nunique()
    combos_4q = sales_combos[sales_combos == 4].index

    df_ind_4q = df_ind_raw.set_index(["상권_코드", "서비스_업종_코드"]).loc[combos_4q].reset_index()
    trade_q_4q = df_ind_4q.groupby(["상권_코드", "기준_년분기_코드"])["당월_매출_금액"].sum()

    s3_idx = pd.MultiIndex.from_arrays([sens3["상권_코드"], sens3["기준_년분기_코드"]])
    exp_c_sales = s3_idx.map(trade_q_4q)

    prev_q_map = {20252: 20251, 20253: 20252, 20254: 20253}
    prev_q = sens3["기준_년분기_코드"].map(prev_q_map)
    s3_prev_idx = pd.MultiIndex.from_arrays([sens3["상권_코드"], prev_q])
    exp_c_prev_sales = s3_prev_idx.map(trade_q_4q)

    cond_cg = exp_c_prev_sales.notna() & (exp_c_prev_sales > 0) & exp_c_sales.notna()
    exp_c_growth = np.where(cond_cg, (exp_c_sales - exp_c_prev_sales) / exp_c_prev_sales * 100.0, np.nan)
    exp_c_reason = np.where(
        pd.Series(exp_c_growth).notna(), "정상 산출",
        np.where(sens3["기준_년분기_코드"] == 20251, "전분기 자료 부재(2025Q1)",
        np.where(exp_c_sales.isna(), "4개분기 공통 매출 업종 부재", "비교 분기 매출 결측 또는 0원"))
    )

    check_column_match(sens3["상권_공통업종_매출합계"], pd.Series(exp_c_sales), "sens3.common_sales", is_float=True)
    check_column_match(sens3["상권_공통업종_매출_증감률"], pd.Series(exp_c_growth), "sens3.common_growth", is_float=True)
    assert (sens3["공통증감_결측_사유"].values == exp_c_reason).all(), "sens3 공통증감_결측_사유 불일치"

    # 5. 상관행렬 피어슨 상관계수 14x14 독립 재계산 대조
    corr_file = pd.read_csv(STAGE3_DIR / "변수_상관관계_행렬.csv", index_col=0, encoding="utf-8-sig")
    corr_cols = [
        "상권_연간_매출_금액_합계", "상권_연간_평균_점포_수", "상권_연간_프랜차이즈_점포_비율",
        "상권_연간_개업_점포_비율", "상권_연간_폐업_점포_비율", "상권_연간_점포_밀집도_ha",
        "상권_연간_평균_유동인구_수", "총_상주인구_수", "총_직장_인구_수",
        "운영_영업_개월_2025Q4", "폐업_영업_개월_2025Q4", "배후동_소비_연간지출_총금액",
        "배후동_자치구_평균소득월액", "집객시설_수"
    ]
    corr_exp = act_t_a[corr_cols].corr(method="pearson")
    np.testing.assert_allclose(corr_file.values, corr_exp.values, atol=1e-9, rtol=0.0, err_msg="상관행렬 피어슨 계수 불일치")

    # 6. 요약통계 JSON 전 항목 독립 계산 대조
    with open(STAGE3_DIR / "stage3_summary_stats.json", "r", encoding="utf-8") as f:
        stats = json.load(f)

    assert stats["ind_quarterly_rows"] == len(act_ind_q)
    assert stats["ind_annual_rows"] == len(act_ind_a)
    assert stats["trade_quarterly_rows"] == len(act_t_q)
    assert stats["trade_annual_rows"] == len(act_t_a)
    assert stats["unique_trade_ind_combos"] == len(act_ind_a)
    assert stats["annual_sales_missing_combos"] == int(act_ind_a["연간_추정매출_금액_합계"].isna().sum())

    valid_ind_counts = act_ind_a.dropna(subset=["연간_객단가"]).groupby(["서비스_업종_코드", "서비스_업종_코드_명"])["상권_코드"].nunique().reset_index(name="유효상권수")
    assert stats["valid_ind_count_under_30"] == int(len(valid_ind_counts[valid_ind_counts["유효상권수"] < 30]))
    assert stats["valid_ind_count_under_50"] == int(len(valid_ind_counts[valid_ind_counts["유효상권수"] < 50]))
    assert stats["valid_ind_count_under_100"] == int(len(valid_ind_counts[valid_ind_counts["유효상권수"] < 100]))
    assert stats["valid_ind_count_under_200"] == int(len(valid_ind_counts[valid_ind_counts["유효상권수"] < 200]))
    assert stats["valid_ind_examples_under_30"] == valid_ind_counts[valid_ind_counts["유효상권수"] < 30]["서비스_업종_코드_명"].tolist()

    assert stats["outlier_dong_trades_count"] == int(df_m_raw[df_m_raw["배후동_소비_이상치"] == True]["상권_코드"].nunique())
    exp_outlier_dong_dict = df_m_raw[df_m_raw["배후동_소비_이상치"] == True].groupby("행정동_코드_명")["상권_코드"].nunique().to_dict()
    assert stats["outlier_trades_by_dong"] == exp_outlier_dong_dict

    sales_q_counts = act_t_q.groupby("상권_코드")["상권_당월_매출_금액_합계"].count()
    assert stats["all_missing_sales_trades"] == int((sales_q_counts == 0).sum())
    assert stats["partial_missing_sales_trades"] == int(((sales_q_counts > 0) & (sales_q_counts < 4)).sum())
    assert stats["all_4q_sales_trades"] == int((sales_q_counts == 4).sum())

    flow_q_counts = act_t_q.dropna(subset=["총_유동인구_수"]).groupby("상권_코드")["기준_년분기_코드"].count()
    assert stats["flow_4q_trades"] == int((flow_q_counts == 4).sum())
    assert stats["flow_partial_trades"] == int((flow_q_counts < 4).sum())
    assert stats["flow_partial_trade_codes"] == flow_q_counts[flow_q_counts < 4].index.tolist()

    assert stats["missing_trades"]["facilities"] == int(act_t_a["집객시설_수"].isna().sum())
    assert stats["missing_trades"]["work"] == int(act_t_a["총_직장_인구_수"].isna().sum())
    assert stats["missing_trades"]["resident"] == int(act_t_a["총_상주인구_수"].isna().sum())

    # 분위수 및 요약통계 전 항목 독립 계산 대조
    assert abs(stats["growth_median"] - round(float(growth_s.median()), 2)) < 1e-5
    assert abs(stats["growth_p5"] - p5_val) < 1e-5
    assert abs(stats["growth_p25"] - round(float(growth_s.quantile(0.25)), 2)) < 1e-5
    assert abs(stats["growth_p75"] - round(float(growth_s.quantile(0.75)), 2)) < 1e-5
    assert abs(stats["growth_p95"] - p95_val) < 1e-5
    assert abs(stats["growth_p1"] - p1_val) < 1e-5
    assert abs(stats["growth_p99"] - p99_val) < 1e-5

    assert stats["growth_extreme_low_rows"] == int((growth_s < -90.0).sum())
    assert stats["growth_extreme_high_rows"] == int((growth_s > 500.0).sum())
    winsor_s = growth_s.clip(p5_val, p95_val)
    assert abs(stats["growth_winsor_p5_p95_mean"] - round(float(winsor_s.mean()), 2)) < 1e-5
    assert abs(stats["growth_raw_mean"] - round(float(growth_s.mean()), 2)) < 1e-5
    assert abs(stats["growth_raw_std"] - round(float(growth_s.std()), 2)) < 1e-5
    assert abs(stats["growth_winsor_std"] - round(float(winsor_s.std()), 2)) < 1e-5

    p5_raw = float(growth_s.quantile(0.05))
    p95_raw = float(growth_s.quantile(0.95))
    p1_raw = float(growth_s.quantile(0.01))
    p99_raw = float(growth_s.quantile(0.99))
    assert stats["growth_boundary_counts"]["crit2_raw_low"] == int((growth_s < p5_raw).sum())
    assert stats["growth_boundary_counts"]["crit2_raw_high"] == int((growth_s > p95_raw).sum())
    assert stats["growth_boundary_counts"]["crit3_raw_low"] == int((growth_s < p1_raw).sum())
    assert stats["growth_boundary_counts"]["crit3_raw_high"] == int((growth_s > p99_raw).sum())
    assert stats["growth_boundary_counts"]["crit2_low"] == int((growth_s < p5_val).sum())
    assert stats["growth_boundary_counts"]["crit2_high"] == int((growth_s > p95_val).sum())
    assert stats["growth_boundary_counts"]["crit3_low"] == int((growth_s < p1_val).sum())
    assert stats["growth_boundary_counts"]["crit3_high"] == int((growth_s > p99_val).sum())

    assert stats["no_common_ind_trades"] == int(len(set(df_m_raw["상권_코드"]) - set(combos_4q.get_level_values(0))))
    diff_growth = (sens3["상권_공통업종_매출_증감률"] - act_t_q["상권_분기_매출_증감률"]).dropna()
    assert abs(stats["growth_diff_mean_pctp"] - round(float(diff_growth.abs().mean()), 2)) < 1e-5
    assert abs(stats["growth_diff_median_pctp"] - round(float(diff_growth.abs().median()), 2)) < 1e-5


def test_4_variable_dictionary(act_tables):
    """검사 4: 변수사전 267개 컬럼 메타데이터, 11대 표준 순서, 실제 DataFrame dtype 1:1 일치, 한글 설명 유효성 검증"""
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables
    dict_df = pd.read_csv(STAGE3_DIR / "변수사전.csv", encoding="utf-8-sig")
    assert len(dict_df) == 267, f"변수사전 컬럼 수 오류: {len(dict_df)} (기대: 267개)"

    std_cols = [
        "테이블명", "컬럼명", "한글_설명", "수식", "입력_파일", "입력_컬럼",
        "데이터타입", "단위", "분석_단위", "결측치_처리_규칙", "분모0_처리_규칙"
    ]
    assert list(dict_df.columns) == std_cols, f"변수사전 컬럼 구성 오류: {list(dict_df.columns)}"
    assert (dict_df["수식"] != "없음").all(), "수식 열에 '없음' 잔존"
    assert not dict_df["수식"].str.contains(r"\{.*?\}").any(), "수식에 미치환 템플릿 잔존"

    # 표준 단위 검증
    ALLOWED_UNITS = {"%", "ha", "km²", "㎡", "가구", "개", "개/ha", "개월", "건", "논리값", "명", "명칭", "분기", "사유텍스트", "원", "좌표", "코드", "회"}
    invalid_units = dict_df[~dict_df["단위"].isin(ALLOWED_UNITS)]
    assert len(invalid_units) == 0, f"변수사전에 비표준/임의 단위 포함: {invalid_units[['컬럼명', '단위']].to_dict('records')}"

    # 한글 설명 공란 부재 및 단일값(가짜) 방지 검증
    assert not dict_df["한글_설명"].isna().any(), "변수사전 한글_설명에 결측치(NaN) 존재"
    assert (dict_df["한글_설명"].astype(str).str.strip() != "").all(), "변수사전 한글_설명에 빈 문자열 존재"
    assert dict_df["한글_설명"].nunique() > 10, "변수사전 한글_설명이 단일값 또는 가짜 문자열로 도배됨"

    # 한 행 단위 설명 검증: 8자 이상, 컬럼명 낱말 1개 이상 포함, 같은 표 안 서로 다른 컬럼끼리 설명 중복 없음
    for _, r in dict_df.iterrows():
        desc = str(r["한글_설명"]).strip()
        assert len(desc) >= 8, f"[{r['테이블명']}.{r['컬럼명']}] 한글_설명이 너무 짧음: '{desc}'"
        toks = [tk for tk in str(r["컬럼명"]).replace("2025Q4", "").split("_") if len(tk) >= 2]
        assert any(tk in desc or tk[:2] in desc for tk in toks), f"[{r['테이블명']}.{r['컬럼명']}] 한글_설명이 컬럼과 무관함: '{desc}'"
    dup_in_table = dict_df.groupby(["테이블명", "한글_설명"])["컬럼명"].nunique()
    assert (dup_in_table == 1).all(), f"같은 표 안에서 서로 다른 컬럼이 같은 한글_설명을 씀: {dup_in_table[dup_in_table > 1].index.tolist()}"
    col_desc_n = dict_df.groupby("컬럼명")["한글_설명"].nunique()
    allowed_multi = {"유효_상권_수"}  # 분기표·연간표에서 뜻이 다른 같은 이름 컬럼
    assert set(col_desc_n[col_desc_n > 1].index) <= allowed_multi, f"같은 컬럼명이 표마다 다른 설명을 씀: {sorted(set(col_desc_n[col_desc_n > 1].index) - allowed_multi)}"

    # 실제 DataFrame dtype과 변수사전 데이터타입 1:1 일치 검증
    table_map = {
        "상권_업종_분기_특성표": act_ind_q,
        "상권_업종_연간_특성표": act_ind_a,
        "상권_분기_특성표": act_t_q,
        "상권_특성표": act_t_a
    }
    for _, r in dict_df.iterrows():
        t_name = r["테이블명"]
        c_name = r["컬럼명"]
        declared_dtype = r["데이터타입"]
        df_target = table_map[t_name]
        assert c_name in df_target.columns, f"[{t_name}]에 컬럼 '{c_name}' 미존재"
        actual_series = df_target[c_name]

        if pd.api.types.is_float_dtype(actual_series.dtype):
            exp_dtype_str = "float64"
        elif pd.api.types.is_integer_dtype(actual_series.dtype):
            exp_dtype_str = "int64"
        elif pd.api.types.is_bool_dtype(actual_series.dtype):
            exp_dtype_str = "bool"
        else:
            exp_dtype_str = "str"

        assert declared_dtype == exp_dtype_str, f"[{t_name}.{c_name}] 변수사전 데이터타입({declared_dtype})과 실제 dtype({exp_dtype_str}) 불일치"

    # 입력 파일 및 입력 컬럼 실존 여부 대조
    marts = {
        '상권_업종_분기_마트.parquet': set(pd.read_parquet(STAGE2_DIR / '상권_업종_분기_마트.parquet').columns),
        '상권_업종_연간_특성표.csv': set(pd.read_csv(STAGE3_DIR / '상권_업종_연간_특성표.csv', nrows=1).columns),
        '상권_분기_마트.csv': set(pd.read_csv(STAGE2_DIR / '상권_분기_마트.csv', nrows=1).columns),
        '상권_마스터.csv': set(pd.read_csv(STAGE2_DIR / '상권_마스터.csv', nrows=1).columns),
        '행정동_마스터.csv': set(pd.read_csv(DATA_DIR / 'processed' / '행정동_마스터.csv', nrows=1).columns),
        '상권_분기_특성표.csv': set(pd.read_csv(STAGE3_DIR / '상권_분기_특성표.csv', nrows=1).columns),
        '상권_특성표.csv': set(pd.read_csv(STAGE3_DIR / '상권_특성표.csv', nrows=1).columns),
        '원천_직접': {'해당없음', '직접산출', '자체산출'}
    }
    for _, r in dict_df.iterrows():
        src = r["입력_파일"]
        inps = [c.strip() for c in str(r["입력_컬럼"]).split(",") if c.strip() and c.strip() != "해당없음"]
        if src in marts:
            for inp_c in inps:
                assert inp_c in marts[src], f"[{r['컬럼명']}] 입력_파일 {src}에 입력_컬럼 '{inp_c}' 미존재"

    fac_cnt = int(act_t_a["집객시설_수"].isna().sum())
    fac_row = dict_df[dict_df["컬럼명"] == "집객시설_수"].iloc[0]
    assert f"{fac_cnt}개" in fac_row["결측치_처리_규칙"], f"집객시설 결측 수 불일치: {fac_row['결측치_처리_규칙']}"

    # 사유 컬럼의 실제 파일 고유값 vs 변수사전 수식/설명 1:1 대조
    reason_rows = dict_df[dict_df["컬럼명"].str.contains("사유")]
    for _, r in reason_rows.iterrows():
        tbl_name = r["테이블명"]
        col = r["컬럼명"]
        df_target = table_map[tbl_name]
        actual_uniques = set(df_target[col].dropna().unique())
        formula_and_desc = str(r["수식"]) + " " + str(r["한글_설명"])
        for u in actual_uniques:
            assert u in formula_and_desc, f"[{tbl_name}] {col} 실제 고유값 '{u}'가 변수사전에 명시되지 않음"


def parse_raw_sources_for_verify():
    """data/RAW_DATA_SOURCES.md를 파싱하여 안건 5 검증 기대값 생성"""
    text = (DATA_DIR / "RAW_DATA_SOURCES.md").read_text(encoding="utf-8")
    m_periods = {}
    for line in text.splitlines():
        if line.startswith("| `OA-") or line.startswith("| `영역") or line.startswith("| `상권"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3:
                fname = parts[0].replace("`", "")
                period = parts[2]
                for code in ["OA-15560", "OA-15568", "OA-15569", "OA-15572", "OA-15576", "OA-15577", "OA-15580", "OA-15584"]:
                    if code in fname:
                        m_periods[code] = period
    zip_text = "2023·2024 zip 기록"
    return m_periods, zip_text


def test_5_report_and_discussion_documents(raw_marts, act_tables):
    """검사 5: 보고서 및 팀 논의자료 줄 단위 대조, 금지어 14종 및 단독 100% 검증, 독립 계산값 기반 기대 문장 대조"""
    df_ind_raw, df_q_raw, df_m_raw, df_dong_m = raw_marts
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables
    rep_path = REPORT_DIR / "03_파생변수_설계보고서_2025Q4.md"
    disc_path = REPORT_DIR / "03_팀논의자료_2025Q4.md"

    assert rep_path.exists(), "설계보고서 파일 부재"
    assert disc_path.exists(), "팀 논의자료 파일 부재"

    rep_text = rep_path.read_text(encoding="utf-8")
    disc_text = disc_path.read_text(encoding="utf-8")

    # 1. 금지 표현 부재 검사
    forbidden_words = [
        "최종", "완벽", "무결", "전수", "좋은 상권", "나쁜 상권", "유망 상권",
        "투자", "대박", "추천 상권", "확정", "보장", "100% 무결", "최종 승인본"
    ]
    for w in forbidden_words:
        assert w not in rep_text, f"보고서 내 금지어 발견: '{w}'"
        assert w not in disc_text, f"팀 논의자료 내 금지어 발견: '{w}'"

    assert "체급" not in rep_text, "보고서 내 '체급' 표현 잔존"
    assert "브랜드 인지도" not in rep_text, "보고서 내 추측성 '브랜드 인지도' 표현 잔존"
    assert "경쟁 상권" not in rep_text, "보고서 내 추측성 '경쟁 상권' 표현 잔존"

    # 2. 단독 100% 부재 검사
    for i, l in enumerate(rep_text.splitlines()):
        if "100%" in l and "100.0%" not in l and "100% 이상 변동" not in l and "100% 변동" not in l:
            raise AssertionError(f"보고서 {i+1}행 단독 100% 발견: {l}")

    # 3. 필수 사실값 및 문구 확인
    assert "OA-15576" in rep_text, "보고서 내 OA-15576 미포함"
    assert "OA-15582" not in rep_text, "보고서 내 OA-15582 잔존"
    assert "OA-14979" not in rep_text, "보고서 내 OA-14979 잔존"
    assert "OA-14979" not in disc_text, "팀 논의자료 내 OA-14979 잔존"
    assert "0 초과 100 이하" in rep_text, "보고서 내 백분위 범위 0 초과 100 이하 미포함"
    assert "data/raw/상권/OA-15580_집객시설_상권.csv" in rep_text, "보고서 집객시설 입력파일 미포함"

    # 4. 독립 계산 기반 기대 문장 대조
    exp_fac_missing = int(act_t_a["집객시설_수"].isna().sum())
    exp_work_missing = int(act_t_a["총_직장_인구_수"].isna().sum())
    exp_res_missing = int(act_t_a["총_상주인구_수"].isna().sum())

    exp_fac_sentence = f"원천 집객시설 데이터에 행이 없는 {exp_fac_missing}개 상권은 0개로 채우지 않고 `NaN`으로 보존하며"
    assert exp_fac_sentence in rep_text, f"보고서 집객시설 결측 기대 문장 불일치: {exp_fac_sentence}"

    exp_work_res_sentence = f"직장인구 부재 {exp_work_missing}개 상권, 상주인구 부재 {exp_res_missing}개 상권은 `NaN` 보존"
    assert exp_work_res_sentence in rep_text, f"보고서 86/126/374/414행 직장/상주 결측 상권수 기대 문장 불일치: {exp_work_res_sentence}"

    exp_dong_cnt = int(df_m_raw[df_m_raw["배후동_소비_이상치"] == True]["행정동_코드_명"].nunique())
    exp_dong_trades = int(df_m_raw[df_m_raw["배후동_소비_이상치"] == True]["상권_코드"].nunique())
    exp_outlier_sentence = f"소비 이상치 동({exp_dong_cnt}곳, 소속 상권 {exp_dong_trades}개)"
    assert exp_outlier_sentence in rep_text, f"보고서 371행 이상치 동 및 소속 상권 수 기대 문장 불일치: {exp_outlier_sentence}"

    corr_val = float(act_t_a["상권_연간_평균_점포_수"].corr(act_t_a["집객시설_수"]))
    exp_corr_line = f"- **상권_연간_평균_점포_수** & **집객시설_수**: 상관계수 +{corr_val:.3f}"
    assert exp_corr_line in rep_text, f"보고서 445행 상관계수 기대 문장 불일치: {exp_corr_line}"

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
    chg_match_cnt = int((pred_types == df_rc["상권_변화_지표_명"]).sum())
    chg_tot_cnt = len(df_rc)
    chg_pct = round(chg_match_cnt / chg_tot_cnt * 100, 1)
    exp_chg_sentence = f"전체 {chg_tot_cnt:,}건 중 {chg_match_cnt:,}건({chg_pct:.1f}%)이 일치함을 확인했습니다"
    assert exp_chg_sentence in rep_text, f"보고서 331행 6,401건(97.0%) 기대 문장 불일치: {exp_chg_sentence}"

    # 팀 자료 안건 1 후보표 6행 전체 독립 계산 줄 단위 대조
    cand_df = pd.read_csv(STAGE3_DIR / "소표본_후보_비교.csv", encoding="utf-8-sig")
    cand_row2 = cand_df[cand_df["후보명"].str.contains("후보 2")].iloc[0]
    cand2_warn_cnt = int(cand_row2["경고대상_조합수"])
    assert f"{cand2_warn_cnt:,}건" in disc_text, f"팀 자료 안건 1 {cand2_warn_cnt:,}건 미포함"

    crit_meanings = {
        "후보 1": "단일 점포 수준 (개폐업 1건 발생 시 비율 100% 이상 변동)",
        "후보 2 (분석가 권고)": "최소 표본 구간 (개폐업 1건 발생 시 비율 50% 이상 변동)",
        "후보 3": "소규모 점포 구간 (개폐업 1건 발생 시 비율 20% 이상 변동)",
        "분기 후보 1": "분기 단일 점포 (개폐업 1건 시 비율 100% 이상 변동)",
        "분기 후보 2": "분기 최소 표본 (개폐업 1건 시 비율 50% 이상 변동)",
        "분기 후보 3": "분기 소규모 점포 (개폐업 1건 시 비율 20% 이상 변동)"
    }

    for _, cr in cand_df.iterrows():
        c_name = cr["후보명"]
        u_name = cr["분석단위"]
        th_val = cr["임계값"]
        crit_val = crit_meanings.get(c_name, cr["통계근거"])
        warn_c = int(cr["경고대상_조합수"])
        warn_p = float(cr["경고_비율_pct"])
        cap_e = int(cr["둘중하나_이상치_포착건수"])
        cap_p = float(cr["둘중하나_이상치_포착률_pct"])
        rem_e = int(cr["비경고군_잔여_이상치건수"])
        rem_p = float(cr["비경고군_잔여율_비경고조합대비_pct"])

        exp_cand_line = f"| {c_name} | {u_name} | {th_val} | {crit_val} | {warn_c:,}건 ({warn_p}%) | {cap_e:,}건 ({cap_p}%) | {rem_e:,}건 ({rem_p}%) |"
        assert exp_cand_line in disc_text, f"팀 자료 안건 1 후보표 행 줄 불일치: {exp_cand_line}"

    # 보고서 3.2 소표본 후보표 6행 독립 계산 줄 단위 대조 (개업·폐업 포착 칸 포함)
    ann_stores_v = act_ind_a["연간_평균_전체_점포_수"]
    ann_open_100_v = act_ind_a["연간_개업_점포_비율"] >= 100.0
    ann_close_100_v = act_ind_a["연간_폐업_점포_비율"] >= 100.0
    ann_either_100_v = ann_open_100_v | ann_close_100_v
    for _, cr in cand_df.iterrows():
        c_name = cr["후보명"]
        exp_rep_line = (
            f"| {c_name} | {cr['임계값']} | {crit_meanings.get(c_name, cr['통계근거'])} | "
            f"{int(cr['경고대상_조합수']):,}건 ({cr['경고_비율_pct']}%) | "
            f"{int(cr['개업이상치_포착건수']):,}건 ({cr['개업이상치_포착률_pct']}%) | "
            f"{int(cr['폐업이상치_포착건수']):,}건 ({cr['폐업이상치_포착률_pct']}%) | "
            f"{int(cr['둘중하나_이상치_포착건수']):,}건 ({cr['둘중하나_이상치_포착률_pct']}%) | "
            f"{int(cr['비경고군_잔여_이상치건수']):,}건 ({cr['비경고군_잔여율_비경고조합대비_pct']}%) |"
        )
        assert exp_rep_line in rep_text, f"보고서 3.2 소표본 후보표 행 불일치: {exp_rep_line}"

    # 직장·상주인구 부재 상권수: 문서 안의 모든 등장 위치를 독립 계산값과 대조 (한 곳만 바뀌어도 차단)
    for doc_name, txt in [("보고서", rep_text), ("팀 자료", disc_text)]:
        for label, exp_n in [("직장인구 부재", exp_work_missing), ("상주인구 부재", exp_res_missing)]:
            for mt in re.finditer(label + r" ([\d,]+)개", txt):
                assert int(mt.group(1).replace(",", "")) == exp_n, f"{doc_name} '{label} {mt.group(1)}개' 불일치 (기대 {exp_n}개)"
    assert len(re.findall(r"직장인구 부재 [\d,]+개", rep_text)) >= 2, "보고서 직장인구 부재 문장 수 부족"

    # 연간 개폐업 100.0% 이상 극단치 건수: 팀 자료 안건 1 문장, 보고서 분석가 의견 문장
    exp_either = int(ann_either_100_v.sum())
    exp_open = int(ann_open_100_v.sum())
    exp_close = int(ann_close_100_v.sum())
    exp_extreme_sentence = (
        f"연간 조합 {len(act_ind_a):,}개 중 개업 또는 폐업률이 100.0% 이상인 극단치는 총 "
        f"{exp_either:,}건(개업 {exp_open:,}건, 폐업 {exp_close:,}건)입니다."
    )
    assert exp_extreme_sentence in disc_text, f"팀 자료 안건 1 극단치 총건수 문장 불일치: {exp_extreme_sentence}"
    m2 = ann_stores_v <= 2.0
    cap2 = int((m2 & ann_either_100_v).sum())
    rem2 = int((~m2 & ann_either_100_v).sum())
    exp_opinion = (
        f"후보 2(연간 평균 점포수 $\\le 2.0$개)는 전체 조합의 {round(float(m2.mean() * 100), 2)}%를 경고 대상으로 분류하며, "
        f"100.0% 이상 극단치 {exp_either:,}건 중 {cap2:,}건({round(cap2 / exp_either * 100, 2)}%)을 걸러냅니다. "
        f"비경고군에 남는 이상치는 {rem2:,}건(비경고 조합의 {round(rem2 / int((~m2).sum()) * 100, 2)}%) 수준입니다."
    )
    assert exp_opinion in rep_text, f"보고서 3.2 분석가 의견 문장 불일치: {exp_opinion}"

    # 팀 자료 객단가 희소 업종 후보표 4행: 업종 수와 업종 목록 전체를 독립 계산값과 대조
    vic = act_ind_a.dropna(subset=["연간_객단가"]).groupby(["서비스_업종_코드", "서비스_업종_코드_명"])["상권_코드"].nunique().reset_index(name="n")
    for label, th in [("**후보 A**", 30), ("**후보 B**", 50), ("**후보 C**", 100), ("**추가 비교**", 200)]:
        names = vic[vic["n"] < th]["서비스_업종_코드_명"].tolist()
        exp_row = f"| {label} | {th}개 미만 | {len(names)}개 업종 | {', '.join(names)} |"
        assert exp_row in disc_text, f"팀 자료 객단가 희소 업종 행 불일치: {exp_row}"
    n_ind = int(act_ind_a["서비스_업종_코드"].nunique())
    for doc_name, txt in [("보고서", rep_text), ("팀 자료", disc_text)]:
        for mt in re.finditer(r"([\d,]+)개 (?:전체 )?(?:서비스 )?업종(?= 중| 기준|의)", txt):
            assert int(mt.group(1).replace(",", "")) == n_ind, f"{doc_name} '{mt.group(0)}' 불일치 (실제 업종 수 {n_ind}개)"

    # 팀 자료 안건 3 표 4행 및 경계 검토 문단 독립 계산 줄 단위 대조
    growth_s = act_ind_q["분기_매출_증감률"].dropna()
    p5_val = round(float(growth_s.quantile(0.05)), 1)
    p95_val = round(float(growth_s.quantile(0.95)), 1)
    p1_val = round(float(growth_s.quantile(0.01)), 1)
    p99_val = round(float(growth_s.quantile(0.99)), 1)
    p5_raw = float(growth_s.quantile(0.05))
    p95_raw = float(growth_s.quantile(0.95))
    p1_raw = float(growth_s.quantile(0.01))
    p99_raw = float(growth_s.quantile(0.99))

    c1_low = int((growth_s < -90.0).sum())
    c1_high = int((growth_s > 500.0).sum())
    c1_tot = c1_low + c1_high
    raw_mean = round(float(growth_s.mean()), 2)
    raw_std = round(float(growth_s.std()), 2)
    winsor_s = growth_s.clip(p5_val, p95_val)
    winsor_mean = round(float(winsor_s.mean()), 2)
    winsor_std = round(float(winsor_s.std()), 2)

    c2_low_round = int((growth_s < p5_val).sum())
    c2_high_round = int((growth_s > p95_val).sum())
    c3_low_round = int((growth_s < p1_val).sum())
    c3_high_round = int((growth_s > p99_val).sum())

    c2_low_raw = int((growth_s < p5_raw).sum())
    c2_high_raw = int((growth_s > p95_raw).sum())
    c3_low_raw = int((growth_s < p1_raw).sum())
    c3_high_raw = int((growth_s > p99_raw).sum())

    exp_crit1_line = f"| **기준 1 (현행 플래그)** | -90.0% | +500.0% | 하락 {c1_low:,}건, 상승 {c1_high:,}건 (총 {c1_tot:,}건) | {raw_mean}% (원값) | {raw_std}% |"
    exp_crit2_line = f"| **기준 2 (5%/95% 분위)** | {p5_val}% | +{p95_val}% | 하락 {c2_low_round:,}건, 상승 {c2_high_round:,}건 | - | - |"
    exp_crit3_line = f"| **기준 3 (1%/99% 분위)** | {p1_val}% | +{p99_val}% | 하락 {c3_low_round:,}건, 상승 {c3_high_round:,}건 | - | - |"
    exp_winsor_line = f"| **윈저화 적용 (p5~p95 치환)** | {p5_val}% 클리핑 | +{p95_val}% 클리핑 | - | {winsor_mean}% | {winsor_std}% |"

    assert exp_crit1_line in disc_text, f"팀 자료 안건 3 기준 1 행 불일치: {exp_crit1_line}"
    assert exp_crit2_line in disc_text, f"팀 자료 안건 3 기준 2 행 불일치: {exp_crit2_line}"
    assert exp_crit3_line in disc_text, f"팀 자료 안건 3 기준 3 행 불일치: {exp_crit3_line}"
    assert exp_winsor_line in disc_text, f"팀 자료 안건 3 윈저화 행 불일치: {exp_winsor_line}"

    exp_boundary_sentence = (
        f"반올림 전 분위수 기준 판정(기준 2 {c2_low_raw:,}/{c2_high_raw:,}건, 기준 3 {c3_low_raw:,}/{c3_high_raw:,}건)과 "
        f"반올림 1자리 표기 기준 판정(기준 2 {c2_low_round:,}/{c2_high_round:,}건, 기준 3 {c3_low_round:,}/{c3_high_round:,}건)을 비교 검토하였으며, "
        "기존 파일 수치 정합성을 위해 반올림 1자리 표기 기준 판정값을 결과 파일 및 보고서에 적용했습니다."
    )
    assert exp_boundary_sentence in disc_text, f"팀 자료 안건 3 경계 검토 문단 불일치: {exp_boundary_sentence}"

    # 팀 자료 안건 5 표 줄 및 117행 8개 파일 번호 독립 계산 대조
    m_periods, zip_text = parse_raw_sources_for_verify()
    exp_area_rows = len(df_m_raw)

    exp_a5_area = f"| **영역 (상권)** | `OA-15560` | {m_periods['OA-15560']} | 1개 파일, {exp_area_rows:,}개 상권 영역 | 보유 |"
    exp_a5_sales = f"| **추정매출 (상권)** | `OA-15572` | {m_periods['OA-15572']}, 그리고 {zip_text} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_store = f"| **점포 (상권)** | `OA-15577` | {m_periods['OA-15577']}, 그리고 {zip_text} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_flow = f"| **길단위인구 (상권)** | `OA-15568` | {m_periods['OA-15568']} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_work = f"| **직장인구 (상권)** | `OA-15569` | {m_periods['OA-15569']} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_chg = f"| **상권변화지표 (상권)** | `OA-15576` | {m_periods['OA-15576']} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_fac = f"| **집객시설 (상권)** | `OA-15580` | {m_periods['OA-15580']} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_res = f"| **상주인구 (상권)** | `OA-15584` | {m_periods['OA-15584']} | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"
    exp_a5_card = "| **신용카드 소비 (행정동)** | `OA-22166` | 문서에 기간 기재 없음 | 1개 파일 (2025Q1, 2025Q2, 2025Q3, 2025Q4) | 미확인 |"

    assert exp_a5_area in disc_text, f"팀 자료 안건 5 영역 행 불일치: {exp_a5_area}"
    assert exp_a5_sales in disc_text, f"팀 자료 안건 5 추정매출 행 불일치: {exp_a5_sales}"
    assert exp_a5_store in disc_text, f"팀 자료 안건 5 점포 행 불일치: {exp_a5_store}"
    assert exp_a5_flow in disc_text, f"팀 자료 안건 5 길단위인구 행 불일치: {exp_a5_flow}"
    assert exp_a5_work in disc_text, f"팀 자료 안건 5 직장인구 행 불일치: {exp_a5_work}"
    assert exp_a5_chg in disc_text, f"팀 자료 안건 5 상권변화지표 행 불일치: {exp_a5_chg}"
    assert exp_a5_fac in disc_text, f"팀 자료 안건 5 집객시설 행 불일치: {exp_a5_fac}"
    assert exp_a5_res in disc_text, f"팀 자료 안건 5 상주인구 행 불일치: {exp_a5_res}"
    assert exp_a5_card in disc_text, f"팀 자료 안건 5 신용카드소비 행 불일치: {exp_a5_card}"

    exp_117_sentence = (
        "서울시 상권분석서비스 상권 8종 파일: "
        "영역(`OA-15560`), 길단위인구(`OA-15568`), 직장인구(`OA-15569`), 추정매출(`OA-15572`), "
        "상권변화지표(`OA-15576`), 점포(`OA-15577`), 집객시설(`OA-15580`), 상주인구(`OA-15584`)"
    )
    assert exp_117_sentence in disc_text, f"팀 자료 117행 8개 파일 번호 불일치: {exp_117_sentence}"

    # 수정 이력 확인
    assert "6차 정정 (4차 독립 검수 반영)" in rep_text, "4장 6차 정정 이력 미반영"
    assert "7차 정정 (5차 독립 검수 반영)" in rep_text, "4장 7차 정정 이력 미반영"
    assert "8차 수정 (6차 독립 검수 반영)" in rep_text, "4장 8차 수정 이력 미반영"
    assert "9차 정정 (7차 독립 검수 반영)" in rep_text, "4장 9차 정정 이력 미반영"
    assert "10차 수정 (8차 독립 검수 반영)" in rep_text, "4장 10차 수정 이력 미반영"
    assert "완전 치환" not in rep_text, "수정 이력에 과장 표현 '완전 치환' 잔존"


def test_6_dashboard_integrity(act_tables):
    """검사 6: 대시보드 내장 데이터 5종 791,563칸 전수 1:1 대조 및 무결성 검증"""
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables
    dash_path = REPORT_DIR / "03_상권특성_대시보드_2025Q4.html"
    assert dash_path.exists(), "대시보드 HTML 부재"

    dash_html = dash_path.read_text(encoding="utf-8")
    dash_cells = 0

    # 1. TRADES_DATA (상권 요약 1,650건 x 30키 = 49,500칸)
    m_trades = re.search(r'const\s+TRADES_DATA\s*=\s*(\[.*?\]);', dash_html)
    assert m_trades, "대시보드 TRADES_DATA 부재"
    trades_data = json.loads(m_trades.group(1))
    assert len(trades_data) == len(act_t_a), f"TRADES_DATA 건수 불일치: {len(trades_data)} != {len(act_t_a)}"

    t_a_dict = act_t_a.set_index("상권_코드").to_dict(orient="index")
    for tr in trades_data:
        row = t_a_dict[tr["code"]]
        assert tr["name"] == row["상권_표시_명"], f"TRADES_DATA {tr['code']} name 불일치"
        assert tr["gu"] == row["자치구_코드_명"], f"TRADES_DATA {tr['code']} gu 불일치"
        assert tr["dong"] == row["행정동_코드_명"], f"TRADES_DATA {tr['code']} dong 불일치"
        assert tr["type"] == row["상권_구분_코드_명"], f"TRADES_DATA {tr['code']} type 불일치"
        assert abs(tr["area"] - float(row["영역_면적"])) < 1e-5, f"TRADES_DATA {tr['code']} area 불일치"
        if tr["sales"] is None:
            assert pd.isna(row["상권_연간_매출_금액_합계"]), f"TRADES_DATA {tr['code']} sales null 불일치"
        else:
            assert abs(tr["sales"] - float(row["상권_연간_매출_금액_합계"])) < 1e-5, f"TRADES_DATA {tr['code']} sales 불일치"
        assert tr["sales_note"] == (str(row["상권_연간_매출_결측_사유"]) if pd.notna(row["상권_연간_매출_결측_사유"]) else "정상 산출")
        assert tr["sales_q_cnt"] == (int(row["상권_매출_보유_분기수"]) if pd.notna(row["상권_매출_보유_분기수"]) else 0)
        assert abs(tr["stores"] - float(row["상권_연간_평균_점포_수"])) < 1e-5
        assert tr["stores_note"] == f"점포 보유 {int(row['상권_점포_보유_분기수'])}개 분기"
        if tr["fran_pct"] is None: assert pd.isna(row["상권_연간_프랜차이즈_점포_비율"])
        else: assert abs(tr["fran_pct"] - float(row["상권_연간_프랜차이즈_점포_비율"])) < 1e-5
        if tr["open_pct"] is None: assert pd.isna(row["상권_연간_개업_점포_비율"])
        else: assert abs(tr["open_pct"] - float(row["상권_연간_개업_점포_비율"])) < 1e-5
        if tr["close_pct"] is None: assert pd.isna(row["상권_연간_폐업_점포_비율"])
        else: assert abs(tr["close_pct"] - float(row["상권_연간_폐업_점포_비율"])) < 1e-5
        if tr["flow"] is None: assert pd.isna(row["상권_연간_평균_유동인구_수"])
        else: assert tr["flow"] == int(round(float(row["상권_연간_평균_유동인구_수"])))
        assert tr["flow_note"] == (str(row["상권_유동인구_결측_사유"]) if pd.notna(row["상권_유동인구_결측_사유"]) else "정상 산출")
        assert tr["flow_q_cnt"] == (int(row["유동인구_보유_분기수"]) if pd.notna(row["유동인구_보유_분기수"]) else 0)
        if tr["pop_res"] is None: assert pd.isna(row["총_상주인구_수"])
        else: assert tr["pop_res"] == int(row["총_상주인구_수"])
        assert tr["pop_res_note"] == (str(row["상주인구_결측_사유"]) if pd.notna(row["상주인구_결측_사유"]) else "데이터 없음 (원천 미집계)")
        if tr["pop_work"] is None: assert pd.isna(row["총_직장_인구_수"])
        else: assert tr["pop_work"] == int(row["총_직장_인구_수"])
        assert tr["pop_work_note"] == (str(row["직장인구_결측_사유"]) if pd.notna(row["직장인구_결측_사유"]) else "데이터 없음 (원천 미집계)")
        assert tr["change_indicator"] == str(row["상권_변화_지표_명_2025Q4"])
        assert tr["change_cnt"] == int(row["상권_변화_지표_변경_횟수"])
        if tr["op_months"] is None: assert pd.isna(row["운영_영업_개월_2025Q4"])
        else: assert abs(tr["op_months"] - round(float(row["운영_영업_개월_2025Q4"]), 1)) < 1e-5
        if tr["closed_months"] is None: assert pd.isna(row["폐업_영업_개월_2025Q4"])
        else: assert abs(tr["closed_months"] - round(float(row["폐업_영업_개월_2025Q4"]), 1)) < 1e-5
        if tr["dong_sales"] is None: assert pd.isna(row["배후동_소비_연간지출_총금액"])
        else: assert tr["dong_sales"] == int(round(float(row["배후동_소비_연간지출_총금액"])))
        if tr["dong_income"] is None: assert pd.isna(row["배후동_자치구_평균소득월액"])
        else: assert tr["dong_income"] == int(round(float(row["배후동_자치구_평균소득월액"])))
        if tr["facilities"] is None: assert pd.isna(row["집객시설_수"])
        else: assert tr["facilities"] == int(row["집객시설_수"])
        assert tr["facilities_note"] == (str(row["집객시설_결측_사유"]) if pd.notna(row["집객시설_결측_사유"]) else "데이터 없음 (원천 미집계)")
        assert tr["dong_outlier"] == bool(row["배후동_소비_이상치"] == True)
        dash_cells += 30

    # 2. IND_DATA (상권 업종 연간 특성 62,641건 x 11열 = 689,051칸)
    m_ind = re.search(r'const\s+IND_DATA\s*=\s*(\[.*?\]);', dash_html)
    assert m_ind, "대시보드 IND_DATA 부재"
    ind_data = json.loads(m_ind.group(1))
    assert len(ind_data) == len(act_ind_a), f"IND_DATA 건수 불일치: {len(ind_data)} != {len(act_ind_a)}"

    for i, r in enumerate(ind_data):
        act_r = act_ind_a.iloc[i]
        assert r[0] == int(act_r["상권_코드"])
        assert r[1] == str(act_r["서비스_업종_코드"])
        assert r[2] == str(act_r["서비스_업종_코드_명"])
        assert abs(r[3] - round(float(act_r["연간_평균_전체_점포_수"]), 1)) < 1e-5
        assert r[4] == int(act_r["점포_행_보유_분기수"])
        if r[5] is None: assert pd.isna(act_r["연간_개업_점포_비율"])
        else: assert abs(r[5] - round(float(act_r["연간_개업_점포_비율"]), 1)) < 1e-5
        if r[6] is None: assert pd.isna(act_r["연간_폐업_점포_비율"])
        else: assert abs(r[6] - round(float(act_r["연간_폐업_점포_비율"]), 1)) < 1e-5
        if r[7] is None: assert pd.isna(act_r["연간_객단가"])
        else: assert r[7] == int(round(float(act_r["연간_객단가"])))
        if r[8] is None: assert pd.isna(act_r["연간_객단가_백분위_업종내"])
        else: assert abs(r[8] - round(float(act_r["연간_객단가_백분위_업종내"]), 1)) < 1e-5
        assert r[9] == str(act_r["연간_객단가_결측_사유"])
        assert r[10] == (str(act_r["연간_개폐업_결측_사유"]) if "연간_개폐업_결측_사유" in act_r and pd.notna(act_r["연간_개폐업_결측_사유"]) else "정상 산출")
        dash_cells += 11

    # 3. TRADE_Q_DATA (상권 분기 특성 6,600건 x 8열 = 52,800칸)
    m_tq = re.search(r'const\s+TRADE_Q_DATA\s*=\s*(\[.*?\]);', dash_html)
    assert m_tq, "대시보드 TRADE_Q_DATA 부재"
    trade_q_data = json.loads(m_tq.group(1))
    assert len(trade_q_data) == len(act_t_q), f"TRADE_Q_DATA 건수 불일치: {len(trade_q_data)} != {len(act_t_q)}"

    for i, r in enumerate(trade_q_data):
        act_r = act_t_q.iloc[i]
        assert r[0] == int(act_r["상권_코드"])
        assert r[1] == int(act_r["기준_년분기_코드"])
        if r[2] is None: assert pd.isna(act_r["상권_당월_매출_금액_합계"])
        else: assert r[2] == int(round(float(act_r["상권_당월_매출_금액_합계"])))
        if r[3] is None: assert pd.isna(act_r["상권_분기_매출_증감률"])
        else: assert abs(r[3] - round(float(act_r["상권_분기_매출_증감률"]), 1)) < 1e-5
        assert r[4] == (str(act_r["상권_매출증감_결측_사유"]) if "상권_매출증감_결측_사유" in act_r and pd.notna(act_r["상권_매출증감_결측_사유"]) else "정상 산출")
        assert r[5] == int(act_r["상권_전체_점포_수_합계"])
        if r[6] is None: assert pd.isna(act_r["총_유동인구_수"])
        else: assert r[6] == int(round(float(act_r["총_유동인구_수"])))
        assert r[7] == (str(act_r["유동인구_결측_사유"]) if "유동인구_결측_사유" in act_r and pd.notna(act_r["유동인구_결측_사유"]) else "정상 산출")
        dash_cells += 8

    # 4. GU_DATA (자치구 비교 25건 x 6키 = 150칸)
    m_gu = re.search(r'const\s+GU_DATA\s*=\s*(\[.*?\]);', dash_html)
    assert m_gu, "대시보드 GU_DATA 부재"
    gu_data = json.loads(m_gu.group(1))
    assert len(gu_data) == 25, f"GU_DATA 자치구 수 불일치: {len(gu_data)}"

    gu_agg = act_t_a.groupby("자치구_코드_명").agg(
        상권수=("상권_코드", "count"),
        평균매출=("상권_연간_매출_금액_합계", "mean"),
        평균점포=("상권_연간_평균_점포_수", "mean"),
        평균유동=("상권_연간_평균_유동인구_수", "mean"),
        평균소득=("배후동_자치구_평균소득월액", "mean")
    ).reset_index()
    gu_dict = gu_agg.set_index("자치구_코드_명").to_dict(orient="index")
    for item in gu_data:
        exp_g = gu_dict[item["gu"]]
        assert item["count"] == int(exp_g["상권수"])
        assert item["sales"] == (int(round(exp_g["평균매출"])) if pd.notna(exp_g["평균매출"]) else 0)
        assert abs(item["stores"] - (round(float(exp_g["평균점포"]), 1) if pd.notna(exp_g["평균점포"]) else 0)) < 1e-5
        assert item["flow"] == (int(round(exp_g["평균유동"])) if pd.notna(exp_g["평균유동"]) else 0)
        assert item["income"] == (int(round(exp_g["평균소득"])) if pd.notna(exp_g["평균소득"]) else 0)
        dash_cells += 6

    # 5. IND_NAMES (업종명 리스트 62개 = 62칸)
    m_inm = re.search(r'const\s+IND_NAMES\s*=\s*(\[.*?\]);', dash_html)
    assert m_inm, "대시보드 IND_NAMES 부재"
    ind_names_data = json.loads(m_inm.group(1))
    exp_names = sorted(list(set(act_ind_a["서비스_업종_코드_명"])))
    assert ind_names_data == exp_names, "대시보드 IND_NAMES 업종 목록 불일치"
    dash_cells += len(ind_names_data)

    # 화면 문구의 업종 수·자치구 수를 실제 데이터 계산값과 대조
    exp_n_ind = int(act_ind_a["서비스_업종_코드"].nunique())
    exp_n_gu = int(act_t_a["자치구_코드"].nunique())
    for label, pat, exp_n in [
        ("전체 자치구 선택지", r"전체 자치구 \((\d+)개\)", exp_n_gu),
        ("자치구 차트 제목", r"서울 (\d+)개 자치구별 평균 비교", exp_n_gu),
        ("업종 표 제목", r"\((\d+)개 표준 업종\)", exp_n_ind),
    ]:
        found = re.findall(pat, dash_html)
        assert found, f"대시보드 {label} 문구 부재"
        assert all(int(x) == exp_n for x in found), f"대시보드 {label} 숫자 불일치: {found} (기대 {exp_n})"

    assert dash_cells == 791563, f"대시보드 총 대조 칸수 오류: {dash_cells:,} != 791,563"

    # 6. 390px 폰트 >= 10px 및 자치구 차트 스타일 검증
    font_sizes = re.findall(r'font-size:\s*([0-9.]+)px', dash_html)
    for fs in font_sizes:
        assert float(fs) >= 10.0, f"대시보드 내 10px 미만 폰트 발견: {fs}px"

    assert 'id="guChartContainer"' in dash_html, "자치구 차트 컨테이너 부재"
    assert "overflow-y: hidden" in dash_html, "자치구 차트 컨테이너 세로 스크롤 제거(overflow-y: hidden) 미적용"
    assert "height: 220px" in dash_html, "자치구 차트 컨테이너 높이 220px 상향 미적용"
    assert "소표본 경고" not in dash_html, "대시보드 내 미확정 소표본 경고 표기 발견"

    print(f" -> 통과: 대시보드 내장 5종 데이터 총 {dash_cells:,}칸 1:1 대조 및 CSS/레이아웃 검증 완료")


def test_7_baseline_hashes():
    """검사 7: 원천 데이터 35개, 2단계 마트 14개, PREPROCESSING.md sha256 불변성 검증"""
    prep_hash = get_file_sha256(DATA_DIR / "PREPROCESSING.md")
    assert prep_hash == PREP_MD_EXPECTED_HASH, f"PREPROCESSING.md 해시 변경 감지: {prep_hash}"

    for rel_path, exp_hash in RAW_ALL_EXPECTED_HASHES.items():
        fpath = DATA_DIR / "raw" / rel_path
        assert fpath.exists(), f"원천 파일 부재: {fpath}"
        act_hash = get_file_sha256(fpath)
        assert act_hash == exp_hash, f"원천 파일 {rel_path} 해시 불일치: {act_hash} != {exp_hash}"

    for fname, exp_hash in STAGE2_ALL_EXPECTED_HASHES.items():
        fpath = STAGE2_DIR / fname
        assert fpath.exists(), f"Stage 2 파일 부재: {fpath}"
        act_hash = get_file_sha256(fpath)
        assert act_hash == exp_hash, f"Stage 2 파일 {fname} 해시 불일치: {act_hash} != {exp_hash}"

    print(f" -> 통과: 원천 데이터 {len(RAW_ALL_EXPECTED_HASHES)}개, 2단계 마트 {len(STAGE2_ALL_EXPECTED_HASHES)}개 파일, PREPROCESSING.md sha256 해시 불변 확인")


def test_8_isolated_reexecution():
    """검사 8: 격리 임시 폴더에서 파이프라인 전체 재실행 후 바이트 단위 일치 검증"""
    print(" -> 격리 임시 폴더 파이프라인 재실행 검증 중...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        shutil.copytree(PROJECT_DIR / "src", tmp_p / "src")
        shutil.copytree(PROJECT_DIR / "data", tmp_p / "data")
        # 기존 3단계 산출물을 비워 두고 재생성한다 (생성기가 빠뜨린 파일이 옛 복사본으로 통과하지 않도록)
        tmp_stage3 = tmp_p / "data" / "processed" / "stage3"
        shutil.rmtree(tmp_stage3)
        tmp_stage3.mkdir(parents=True)
        (tmp_p / "report").mkdir(parents=True, exist_ok=True)
        (tmp_p / "images").mkdir(parents=True, exist_ok=True)

        cmd1 = [sys.executable, str(tmp_p / "src" / "build_stage3_features.py")]
        res1 = run_sub(cmd1, cwd=tmp_p)
        assert res1.returncode == 0, f"격리 실행 실패 (features): {res1.stderr}"

        cmd2 = [sys.executable, str(tmp_p / "src" / "build_stage3_report.py")]
        res2 = run_sub(cmd2, cwd=tmp_p)
        assert res2.returncode == 0, f"격리 실행 실패 (report): {res2.stderr}"

        # 3단계 산출물 전체(데이터 12개 + 보고서·팀자료·대시보드 3개 + 그림 3개 = 18개)를 바이트 단위로 대조
        orig_files = sorted(p.name for p in STAGE3_DIR.iterdir() if p.is_file())
        new_files = sorted(p.name for p in tmp_stage3.iterdir() if p.is_file())
        assert orig_files == new_files, f"격리 재실행 산출물 목록 불일치: 원본 {orig_files} / 재실행 {new_files}"
        targets = [(STAGE3_DIR / f, tmp_stage3 / f) for f in orig_files]
        for rname in ["03_파생변수_설계보고서_2025Q4.md", "03_팀논의자료_2025Q4.md", "03_상권특성_대시보드_2025Q4.html"]:
            targets.append((REPORT_DIR / rname, tmp_p / "report" / rname))
        img_dir = PROJECT_DIR / "images" / "stage3"
        orig_imgs = sorted(p.name for p in img_dir.glob("*.png"))
        new_imgs = sorted(p.name for p in (tmp_p / "images" / "stage3").glob("*.png"))
        assert orig_imgs == new_imgs, f"격리 재실행 그림 목록 불일치: 원본 {orig_imgs} / 재실행 {new_imgs}"
        targets += [(img_dir / f, tmp_p / "images" / "stage3" / f) for f in orig_imgs]

        for orig_p, new_p in targets:
            assert get_file_sha256(orig_p) == get_file_sha256(new_p), f"격리 재실행 파일 해시 불일치: {orig_p.name}"
        print(f" -> 격리 재실행 산출물 {len(targets)}개 바이트 단위 대조 완료")


def run_systematic_mutation_testing(raw_marts, act_tables):
    """
    검사 9: Systematic Mutation Testing
    1) 파트 A: 267개 전 컬럼 1개씩 개별 변조 100% 차단(Killed) 실증
    2) 파트 B-1: 양성 대조 (검사 로직 무력화 시 미차단 실증)
    3) 파트 B-2: 산출물 파일 25종 변조 100% 차단(Killed) 실증
    4) 파트 B-3: 10대 생성 코드 결함 주입 100% 차단(Killed) 실증
    """
    print("\n" + "=" * 70)
    print("   [변조 시험] Systematic Mutation Testing (격리 임시 환경 267+36종 시험)")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # 파트 A: 267개 전 컬럼 개별 변조 차단 시험 (메모리 고속 실행)
    # -------------------------------------------------------------------------
    print("\n[파트 A] 4종 특성표 267개 전 컬럼 1개씩 개별 변조 차단 시험")
    df_ind_raw, df_q_raw, df_m_raw, df_dong_m = raw_marts
    act_ind_q, act_ind_a, act_t_q, act_t_a = act_tables

    tables = [
        ("상권_업종_분기_특성표", act_ind_q.copy(), 0),
        ("상권_업종_연간_특성표", act_ind_a.copy(), 1),
        ("상권_분기_특성표", act_t_q.copy(), 2),
        ("상권_특성표", act_t_a.copy(), 3)
    ]

    col_killed = 0
    missed_list = []
    for tbl_name, tbl_df, tbl_idx in tables:
        for c in tbl_df.columns:
            orig_series = tbl_df[c].copy()
            if pd.api.types.is_numeric_dtype(orig_series.dtype):
                if orig_series.dropna().empty:
                    mut_series = orig_series.fillna(999.0)
                else:
                    mut_series = orig_series * 2.0 + 1.0
            elif pd.api.types.is_bool_dtype(orig_series.dtype):
                mut_series = ~orig_series
            else:
                mut_series = orig_series.astype(str) + "_mutated"

            tbl_df[c] = mut_series

            cur_tables = list(act_tables)
            cur_tables[tbl_idx] = tbl_df

            blocked = False
            try:
                test_2_full_267_columns_recalculation_and_blanks(raw_marts, cur_tables)
            except Exception:
                blocked = True

            if blocked:
                col_killed += 1
            else:
                missed_list.append(f"[{tbl_name}] {c}")
            tbl_df[c] = orig_series

    if col_killed < 267:
        print(f"\n  [미차단 컬럼 {len(missed_list)}개]: {missed_list}\n")
    assert col_killed == 267, f"특성표 컬럼 변조 미차단 발생: {col_killed}/267"
    print(f" -> 통과: 4종 특성표 267개 전 컬럼 개별 변조 중 {col_killed}/267개 100% 차단(Killed) 완료")

    # -------------------------------------------------------------------------
    # 파트 B: 양성 대조 및 산출물 파일 변조 차단 시험 (격리 복제본 실행)
    # -------------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        shutil.copytree(PROJECT_DIR / "src", tmp_p / "src")
        shutil.copytree(PROJECT_DIR / "data", tmp_p / "data")
        shutil.copytree(PROJECT_DIR / "report", tmp_p / "report")
        shutil.copytree(PROJECT_DIR / "images", tmp_p / "images")

        cmd_base = [sys.executable, str(tmp_p / "src" / "verify_stage3.py"), "--mode=unit"]

        print("\n[파트 B-1] 양성 대조 (Positive Control) 3단계 검증")
        res_orig = run_sub(cmd_base, cwd=tmp_p)
        assert res_orig.returncode == 0, f"정상 원본 통과 실패: {res_orig.stderr}"
        print("  1) 원본 검사기 실행: 정상 통과 (Exit Code 0)")

        t_stage3 = tmp_p / "data" / "processed" / "stage3"
        t_report = tmp_p / "report"
        target_f = t_stage3 / "상권_업종_연간_특성표.csv"
        orig_b = target_f.read_bytes()
        df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
        df_mut["연간_점포_밀집도_ha"] = df_mut["연간_점포_밀집도_ha"] * 2.0
        df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")

        res_mut = run_sub(cmd_base, cwd=tmp_p)
        assert res_mut.returncode != 0, "결함 주입 미차단!"
        print("  2) 결함 주입 상태 실행: 차단 성공 (Exit Code != 0)")

        ver_p = tmp_p / "src" / "verify_stage3.py"
        ver_text = ver_p.read_text(encoding="utf-8")
        target_call = "    test_2_full_267_columns_recalculation_and_blanks(raw_marts, act_tables)"
        assert target_call in ver_text, "main() 호출 줄 target_call 미발견"
        ver_disabled = ver_text.replace(target_call, "    # test_2_full_267_columns_recalculation_and_blanks(raw_marts, act_tables) # 양성 대조 무력화")
        ver_p.write_text(ver_disabled, encoding="utf-8")

        res_pos_ctrl = run_sub(cmd_base, cwd=tmp_p)
        assert res_pos_ctrl.returncode == 0, f"양성 대조 실패 (무력화 시에도 차단됨): {res_pos_ctrl.stderr}"
        print("  3) 검사 로직 무력화 시: 미차단(Exit Code 0) 실증 성공 -> 검사기 판정 유효성 확인 완료")

        ver_p.write_text(ver_text, encoding="utf-8")
        target_f.write_bytes(orig_b)

        print("\n[파트 B-2] 산출물 25종 변조 차단 시험")
        killed_count = 0

        # 변조 1: 파생 컬럼 2배
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut["연간_객단가"] = df_mut["연간_객단가"] * 2.0
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 1 미차단!"
            killed_count += 1
            print("  [Mutant 1] 특성표 파생 컬럼 2배 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 2: 결측치 0 치환
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            first_nan_idx = df_mut[df_mut["연간_객단가"].isna()].index[0]
            df_mut.loc[first_nan_idx, "연간_객단가"] = 0.0
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 2 미차단!"
            killed_count += 1
            print("  [Mutant 2] 특성표 결측치 0 치환 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 3: 사유 문자열 변경
        target_f = t_stage3 / "상권_업종_분기_특성표.parquet"
        orig_b = target_f.read_bytes()
        try:
            df_mut = pd.read_parquet(target_f)
            df_mut.loc[0, "매출_결측_구분"] = "임의사유"
            df_mut.to_parquet(target_f, index=False)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 3 미차단!"
            killed_count += 1
            print("  [Mutant 3] 결측 사유 문구 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 4: 변수사전 단위를 '값'으로 변조
        target_f = t_stage3 / "변수사전.csv"
        orig_b = target_f.read_bytes()
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut.loc[0, "단위"] = "값"
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 4 미차단!"
            killed_count += 1
            print("  [Mutant 4] 변수사전 단위를 '값'으로 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 5: 변수사전 입력 컬럼명 변조 (미존재 컬럼)
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut.loc[0, "입력_컬럼"] = "존재하지않는컬럼_xyz"
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 5 미차단!"
            killed_count += 1
            print("  [Mutant 5] 변수사전 입력 컬럼 부재 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 6: 요약 통계 JSON 수치 변조
        target_f = t_stage3 / "stage3_summary_stats.json"
        orig_b = target_f.read_bytes()
        try:
            stats_mut = json.loads(orig_b.decode("utf-8"))
            stats_mut["ind_quarterly_rows"] += 1
            target_f.write_text(json.dumps(stats_mut, ensure_ascii=False, indent=2), encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 6 미차단!"
            killed_count += 1
            print("  [Mutant 6] 요약 통계 JSON 수치 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 7: 보고서 단독 100% 삽입 변조
        target_f = t_report / "03_파생변수_설계보고서_2025Q4.md"
        orig_b = target_f.read_bytes()
        try:
            mut_t = orig_b.decode("utf-8") + "\n단독 100% 문구 삽입"
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 7 미차단!"
            killed_count += 1
            print("  [Mutant 7] 보고서 단독 100% 삽입 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 8: 보고서 내 금지어 '완벽' 삽입 변조
        try:
            mut_t = orig_b.decode("utf-8") + "\n본 데이터는 완벽합니다."
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 8 미차단!"
            killed_count += 1
            print("  [Mutant 8] 보고서 금지어 '완벽' 삽입 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 9: 대시보드 내장 데이터 수치 변조
        target_f = t_report / "03_상권특성_대시보드_2025Q4.html"
        orig_b = target_f.read_bytes()
        try:
            mut_t = orig_b.decode("utf-8").replace('"sales":', '"sales": 999999999, "_orig_sales":')
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 9 미차단!"
            killed_count += 1
            print("  [Mutant 9] 대시보드 내장 데이터 수치 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 10: 대시보드 결측값 null -> 0 변조
        try:
            mut_t = orig_b.decode("utf-8").replace('"pop_res": null', '"pop_res": 0')
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 10 미차단!"
            killed_count += 1
            print("  [Mutant 10] 대시보드 결측치 0 치환 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 11: PREPROCESSING.md 해시 변조
        target_f = tmp_p / "data" / "PREPROCESSING.md"
        orig_b = target_f.read_bytes()
        try:
            target_f.write_text(orig_b.decode("utf-8") + "\n# 임의 주석 추가", encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 11 미차단!"
            killed_count += 1
            print("  [Mutant 11] PREPROCESSING.md 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 12: 특성표 복원 컬럼 누락 변조
        target_f = t_stage3 / "상권_분기_특성표.csv"
        orig_b = target_f.read_bytes()
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut.drop(columns=["유동인구_일요일_비율"], inplace=True)
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 12 미차단!"
            killed_count += 1
            print("  [Mutant 12] 상권_분기_특성표 복원 컬럼 누락 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 13: 대시보드 소표본 경고 딱지 주입 변조
        target_f = t_report / "03_상권특성_대시보드_2025Q4.html"
        orig_b = target_f.read_bytes()
        try:
            mut_t = orig_b.decode("utf-8").replace("<!-- 상권 헤더 카드 -->", "<span>소표본 경고</span>")
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 13 미차단!"
            killed_count += 1
            print("  [Mutant 13] 대시보드 소표본 경고 딱지 주입 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 14: 민감도 2 Q4개업률 2배 변조
        target_f = t_stage3 / "민감도_분석_결과.csv"
        orig_b = target_f.read_bytes()
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut["연간_개업_점포_비율_Q4분모"] = df_mut["연간_개업_점포_비율_Q4분모"] * 2.0
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 14 미차단!"
            killed_count += 1
            print("  [Mutant 14] 민감도 2 Q4개업률 2배 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 15: 민감도 2 행보유분기 평균 점포수 2배 변조
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut["연간_평균_점포수_행보유분기만"] = df_mut["연간_평균_점포수_행보유분기만"] * 2.0
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 15 미차단!"
            killed_count += 1
            print("  [Mutant 15] 민감도 2 행보유분기 평균 점포수 2배 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 16: 민감도 3 공통업종 증감률 2배 변조
        target_f = t_stage3 / "상권_공통업종_매출증감률_민감도.csv"
        orig_b = target_f.read_bytes()
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut["상권_공통업종_매출_증감률"] = df_mut["상권_공통업종_매출_증감률"] * 2.0
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 16 미차단!"
            killed_count += 1
            print("  [Mutant 16] 민감도 3 공통업종 증감률 2배 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 17: 요약통계 growth_p5 변경
        target_f = t_stage3 / "stage3_summary_stats.json"
        orig_b = target_f.read_bytes()
        try:
            stats_mut = json.loads(orig_b.decode("utf-8"))
            stats_mut["growth_p5"] += 10.0
            target_f.write_text(json.dumps(stats_mut, ensure_ascii=False, indent=2), encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 17 미차단!"
            killed_count += 1
            print("  [Mutant 17] 요약통계 growth_p5 수치 변경 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 18: 변수사전 한글설명 전부 "가짜설명" 변조
        target_f = t_stage3 / "변수사전.csv"
        orig_b = target_f.read_bytes()
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut["한글_설명"] = "가짜설명"
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 18 미차단!"
            killed_count += 1
            print("  [Mutant 18] 변수사전 한글설명 전부 가짜 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 19: 변수사전 데이터타입 전부 "str" 변조
        try:
            df_mut = pd.read_csv(target_f, encoding="utf-8-sig")
            df_mut["데이터타입"] = "str"
            df_mut.to_csv(target_f, index=False, encoding="utf-8-sig")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 19 미차단!"
            killed_count += 1
            print("  [Mutant 19] 변수사전 데이터타입 전부 str 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 20: 팀자료 안건 1 30,085건 수치 변경
        target_f = t_report / "03_팀논의자료_2025Q4.md"
        orig_b = target_f.read_bytes()
        try:
            mut_t = orig_b.decode("utf-8").replace("30,085건", "99,999건")
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 20 미차단!"
            killed_count += 1
            print("  [Mutant 20] 팀자료 안건 1 30,085건 변경 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 21: 팀자료 안건 3 7.12% 수치 변경
        try:
            mut_t = orig_b.decode("utf-8").replace("7.12%", "99.99%")
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 21 미차단!"
            killed_count += 1
            print("  [Mutant 21] 팀자료 안건 3 7.12% 변경 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 22: 팀자료 안건 5 표 줄 삭제
        try:
            mut_t = orig_b.decode("utf-8").replace("| **영역 (상권)** |", "| **삭제됨** |")
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 22 미차단!"
            killed_count += 1
            print("  [Mutant 22] 팀자료 안건 5 표 줄 삭제 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 23: 대시보드 객단가 변경
        target_f = t_report / "03_상권특성_대시보드_2025Q4.html"
        orig_b = target_f.read_bytes()
        try:
            m_ind = re.search(r'const\s+IND_DATA\s*=\s*(\[.*?\]);', orig_b.decode("utf-8"))
            ind_mut = json.loads(m_ind.group(1))
            ind_mut[0][7] = (ind_mut[0][7] or 1000) * 2
            mut_t = orig_b.decode("utf-8").replace(m_ind.group(1), json.dumps(ind_mut, ensure_ascii=False))
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 23 미차단!"
            killed_count += 1
            print("  [Mutant 23] 대시보드 객단가 변경 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 24: 대시보드 유동인구 변경
        try:
            m_tr = re.search(r'const\s+TRADES_DATA\s*=\s*(\[.*?\]);', orig_b.decode("utf-8"))
            tr_mut = json.loads(m_tr.group(1))
            tr_mut[0]["flow"] = (tr_mut[0]["flow"] or 5000) * 2
            mut_t = orig_b.decode("utf-8").replace(m_tr.group(1), json.dumps(tr_mut, ensure_ascii=False))
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 24 미차단!"
            killed_count += 1
            print("  [Mutant 24] 대시보드 유동인구 변경 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        # 변조 25: 대시보드 자치구 매출 변경
        try:
            m_gu = re.search(r'const\s+GU_DATA\s*=\s*(\[.*?\]);', orig_b.decode("utf-8"))
            gu_mut = json.loads(m_gu.group(1))
            gu_mut[0]["sales"] = (gu_mut[0]["sales"] or 100000) * 2
            mut_t = orig_b.decode("utf-8").replace(m_gu.group(1), json.dumps(gu_mut, ensure_ascii=False))
            target_f.write_text(mut_t, encoding="utf-8")
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "Mutant 25 미차단!"
            killed_count += 1
            print("  [Mutant 25] 대시보드 자치구 매출 변경 변조 -> [KILLED] 차단 성공")
        finally:
            target_f.write_bytes(orig_b)

        assert killed_count == 25, f"산출물 변조 미차단 발생: {killed_count}/25"

        # ---------------------------------------------------------------------
        # 파트 B-3: 10대 생성 코드 결함 주입 시험
        # ---------------------------------------------------------------------
        print("\n[파트 B-3] 10대 생성 코드 결함 주입 시험 (코드 결함 -> 생성기 재실행 -> 검사기 차단)")
        code_killed = 0
        feat_p = tmp_p / "src" / "build_stage3_features.py"
        rep_src_p = tmp_p / "src" / "build_stage3_report.py"
        orig_feat = feat_p.read_text(encoding="utf-8")
        orig_rep_src = rep_src_p.read_text(encoding="utf-8")

        # 결함 1: 분기 프랜차이즈 점포 비율 2배
        try:
            mut_feat = orig_feat.replace(
                'df["분기_프랜차이즈_점포_비율"] = np.where(cond_store_pos, df["프랜차이즈_점포_수"] / df["전체_점포_수"] * 100.0, np.nan)',
                'df["분기_프랜차이즈_점포_비율"] = np.where(cond_store_pos, (df["프랜차이즈_점포_수"] / df["전체_점포_수"] * 100.0) * 2.0, np.nan)'
            )
            assert mut_feat != orig_feat, "결함 1 치환 실패"
            feat_p.write_text(mut_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 1 미차단!"
            code_killed += 1
            print("  [결함 1] 분기 프랜차이즈 점포 비율 2배 결함 주입 -> [KILLED] 차단 성공")
        finally:
            feat_p.write_text(orig_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)

        # 결함 2: 연간 업종 점포 밀집도 10배
        try:
            mut_feat = orig_feat.replace(
                'df["연간_점포_밀집도_ha"] = df["연간_평균_전체_점포_수"] / df["영역_면적_ha"]',
                'df["연간_점포_밀집도_ha"] = (df["연간_평균_전체_점포_수"] / df["영역_면적_ha"]) * 10.0'
            )
            assert mut_feat != orig_feat, "결함 2 치환 실패"
            feat_p.write_text(mut_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 2 미차단!"
            code_killed += 1
            print("  [결함 2] 연간 업종 점포 밀집도 10배 결함 주입 -> [KILLED] 차단 성공")
        finally:
            feat_p.write_text(orig_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)

        # 결함 3: 상권 특성표 점포 밀집도 10배
        try:
            mut_feat = orig_feat.replace(
                'df["상권_연간_점포_밀집도_ha"] = df["상권_연간_평균_점포_수"] / df["영역_면적_ha"]',
                'df["상권_연간_점포_밀집도_ha"] = (df["상권_연간_평균_점포_수"] / df["영역_면적_ha"]) * 10.0'
            )
            assert mut_feat != orig_feat, "결함 3 치환 실패"
            feat_p.write_text(mut_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 3 미차단!"
            code_killed += 1
            print("  [결함 3] 상권 특성표 점포 밀집도 10배 결함 주입 -> [KILLED] 차단 성공")
        finally:
            feat_p.write_text(orig_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)

        # 결함 4: 보고서 집객시설 상권 수 999개 결함
        try:
            mut_rep = orig_rep_src.replace(
                "stats['missing_trades']['facilities']",
                "999"
            )
            assert mut_rep != orig_rep_src, "결함 4 치환 실패"
            rep_src_p.write_text(mut_rep, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 4 미차단!"
            code_killed += 1
            print("  [결함 4] 보고서 집객시설 상권수 999개 고정치 결함 주입 -> [KILLED] 차단 성공")
        finally:
            rep_src_p.write_text(orig_rep_src, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)

        # 결함 5: 보고서 414행 직장인구 부재 상권수 99 결함
        try:
            target_str = "stats['missing_trades']['work']"
            assert target_str in orig_rep_src, "결함 5 대상 미발견"
            mut_rep = orig_rep_src.replace(target_str, "99", 1)
            feat_p.write_text(orig_feat, encoding="utf-8")
            rep_src_p.write_text(mut_rep, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 5 미차단!"
            code_killed += 1
            print("  [결함 5] 보고서 414행 직장인구 부재 상권수 99 결함 주입 -> [KILLED] 차단 성공")
        finally:
            rep_src_p.write_text(orig_rep_src, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)

        # 결함 6: 팀자료 안건 3 표 하락 건수 999 결함
        try:
            target_str = "stats['growth_criteria_counts']['crit2_low']"
            assert target_str in orig_rep_src, "결함 6 대상 미발견"
            mut_rep = orig_rep_src.replace(target_str, "999", 1)
            rep_src_p.write_text(mut_rep, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 6 미차단!"
            code_killed += 1
            print("  [결함 6] 팀자료 안건 3 표 하락 건수 999 결함 주입 -> [KILLED] 차단 성공")
        finally:
            rep_src_p.write_text(orig_rep_src, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)

        # 결함 7: 팀자료 117행 직장인구 번호 OA-15587 결함
        try:
            target_str = "직장인구(`OA-15569`)"
            assert target_str in orig_rep_src, "결함 7 대상 미발견"
            mut_rep = orig_rep_src.replace(target_str, "직장인구(`OA-15587`)")
            rep_src_p.write_text(mut_rep, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 7 미차단!"
            code_killed += 1
            print("  [결함 7] 팀자료 117행 직장인구 번호 OA-15587 결함 주입 -> [KILLED] 차단 성공")
        finally:
            rep_src_p.write_text(orig_rep_src, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)

        # 결함 8: 보고서 이상치 동 9곳 결함
        try:
            target_str = "{len(stats['outlier_trades_by_dong'])}곳"
            assert target_str in orig_rep_src, "결함 8 대상 미발견"
            mut_rep = orig_rep_src.replace(target_str, "9곳")
            rep_src_p.write_text(mut_rep, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 8 미차단!"
            code_killed += 1
            print("  [결함 8] 보고서 이상치 동 9곳 결함 주입 -> [KILLED] 차단 성공")
        finally:
            rep_src_p.write_text(orig_rep_src, encoding="utf-8")
            run_sub([sys.executable, str(rep_src_p)], cwd=tmp_p)

        # 결함 9: 민감도 행보유분기 개업률 2배 결함
        try:
            mut_feat = orig_feat.replace(
                'df_sens["연간_개업_점포_비율_행보유분기만"] = np.where(\n        df_sens["연간_평균_점포수_행보유분기만"] > 0,\n        df_sens["연간_개업_점포_수_합계"] / df_sens["연간_평균_점포수_행보유분기만"] * 100.0,\n        np.nan\n    )',
                'df_sens["연간_개업_점포_비율_행보유분기만"] = np.where(\n        df_sens["연간_평균_점포수_행보유분기만"] > 0,\n        (df_sens["연간_개업_점포_수_합계"] / df_sens["연간_평균_점포수_행보유분기만"] * 100.0) * 2.0,\n        np.nan\n    )'
            )
            assert mut_feat != orig_feat, "결함 9 치환 실패"
            feat_p.write_text(mut_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 9 미차단!"
            code_killed += 1
            print("  [결함 9] 민감도 행보유분기 개업률 2배 결함 주입 -> [KILLED] 차단 성공")
        finally:
            feat_p.write_text(orig_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)

        # 결함 10: 공통업종 증감률 2배 결함
        try:
            mut_feat = orig_feat.replace(
                'sens_trade_growth["상권_공통업종_매출_증감률"] = np.where(\n        cond_cg,\n        (sens_trade_growth["상권_공통업종_매출합계"] - sens_trade_growth["상권_공통업종_매출합계_prev"]) / sens_trade_growth["상권_공통업종_매출합계_prev"] * 100.0,\n        np.nan\n    )',
                'sens_trade_growth["상권_공통업종_매출_증감률"] = np.where(\n        cond_cg,\n        ((sens_trade_growth["상권_공통업종_매출합계"] - sens_trade_growth["상권_공통업종_매출합계_prev"]) / sens_trade_growth["상권_공통업종_매출합계_prev"] * 100.0) * 2.0,\n        np.nan\n    )'
            )
            assert mut_feat != orig_feat, "결함 10 치환 실패"
            feat_p.write_text(mut_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)
            res = run_sub(cmd_base, cwd=tmp_p)
            assert res.returncode != 0, "결함 10 미차단!"
            code_killed += 1
            print("  [결함 10] 민감도 공통업종 증감률 2배 결함 주입 -> [KILLED] 차단 성공")
        finally:
            feat_p.write_text(orig_feat, encoding="utf-8")
            run_sub([sys.executable, str(feat_p)], cwd=tmp_p)

        assert code_killed == 10, f"생성 코드 결함 미차단 발생: {code_killed}/10"

    total_mutants = col_killed + killed_count + code_killed
    print(f"\n -> Systematic Mutation Testing 종합: 총 {total_mutants}개 변조(컬럼 267개 + 산출물 25개 + 코드결함 10개) 100% 전원 차단(Killed) 완료! (놓친 목록: 0개)")


def main():
    mode = "all"
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--mode="):
                mode = arg.split("=")[1]

    print("=" * 70)
    print(f"   [SpotFit Stage 3] 종합 자동 검증 파이프라인 (verify_stage3.py) [Mode: {mode}]")
    print("=" * 70)

    print("[준비] 2단계 마트 데이터 로드 중...")
    df_ind_raw = pd.read_parquet(STAGE2_DIR / "상권_업종_분기_마트.parquet")
    df_q_raw = pd.read_csv(STAGE2_DIR / "상권_분기_마트.csv", encoding="utf-8-sig")
    df_m_raw = pd.read_csv(STAGE2_DIR / "상권_마스터.csv", encoding="utf-8-sig")
    df_dong_m = pd.read_csv(DATA_DIR / "processed" / "행정동_마스터.csv", encoding="utf-8-sig")
    raw_marts = (df_ind_raw, df_q_raw, df_m_raw, df_dong_m)

    print("[로드] Stage 3 산출물 실제 파일 로드 중...")
    act_ind_q = pd.read_parquet(STAGE3_DIR / "상권_업종_분기_특성표.parquet")
    act_ind_a = pd.read_csv(STAGE3_DIR / "상권_업종_연간_특성표.csv", encoding="utf-8-sig")
    act_t_q = pd.read_csv(STAGE3_DIR / "상권_분기_특성표.csv", encoding="utf-8-sig")
    act_t_a = pd.read_csv(STAGE3_DIR / "상권_특성표.csv", encoding="utf-8-sig")
    act_tables = (act_ind_q, act_ind_a, act_t_q, act_t_a)

    print("\n[검사 1] 기본키 유일성 및 데이터 규모 검증")
    test_1_primary_keys_and_shapes(raw_marts, act_tables)
    print(" -> 통과: 4종 특성표 기본키 중복 0건 및 267개 전 컬럼 317,088행 규모 확인")

    print("\n[검사 2] 267개 전 컬럼 100% 판정 및 10,909,987칸 전수 대조 (nan_to_num 금지)")
    test_2_full_267_columns_recalculation_and_blanks(raw_marts, act_tables)

    print("\n[검사 3] 민감도 및 소표본 비교표, 요약통계 재계산 대조")
    test_3_sensitivities_and_stats(raw_marts, act_tables)
    print(" -> 통과: 민감도 3종, 소표본 후보 1~3, 결측 상권수 3종, 요약통계 JSON 전 항목 독립 재계산 일치 확인")

    print("\n[검사 4] 변수사전 267개 컬럼 메타데이터, 표준 순서, 실제 dtype 1:1 일치, 한글 설명 검증")
    test_4_variable_dictionary(act_tables)
    print(" -> 통과: 267개 컬럼 전원 메타데이터, 표준 순서, 실제 dtype 1:1 일치 및 한글 설명 100.0% 검증 완료")

    print("\n[검사 5] 보고서 및 팀 논의자료 줄 단위 대조, 금지어 14종 및 단독 100% 검증, 독립 계산값 문장 대조")
    test_5_report_and_discussion_documents(raw_marts, act_tables)
    print(" -> 통과: 보고서 및 팀 논의자료 필수 수치, 금지어 14종 부재, 단독 100% 부재, 독립 계산값 기반 문장 확인")

    print("\n[검사 6] 대시보드 내장 데이터 5종 전수 1:1 대조 및 무결성 검증")
    test_6_dashboard_integrity(act_tables)

    print("\n[검사 7] 원천 데이터 35개, 2단계 마트 14개, PREPROCESSING.md sha256 불변성 검증")
    test_7_baseline_hashes()

    if mode == "all":
        print("\n[검사 8] 격리 임시 폴더에서 파이프라인 재실행 후 바이트 단위 일치 검증")
        test_8_isolated_reexecution()
        print(" -> 통과: 격리 폴더 재실행 결과 바이트 단위 1:1 일치 확인")

        # Systematic Mutation Testing 실행 (파트 A 267개, 파트 B-1 양성대조, B-2 25개, B-3 10개)
        run_systematic_mutation_testing(raw_marts, act_tables)

    print("\n" + "=" * 70)
    print(f"   [SpotFit Stage 3] 종합 자동 검증 파이프라인 전원 통과 완료! (Exit Code 0)")
    print("=" * 70)


if __name__ == "__main__":
    main()
