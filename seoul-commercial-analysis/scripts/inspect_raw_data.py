#!/usr/bin/env python3
"""STEP 1 Raw Data 구조·품질 점검 스크립트.

data/raw/ 아래 원본 파일을 **읽기만** 하고, 결과를 data/metadata/ 에 쓴다.
원본 파일을 고치거나 지우지 않는다. 결측·중복·불일치는 기록만 한다.

출력:
    data/metadata/data_catalog.csv      파일 단위 카탈로그
    data/metadata/data_dictionary.csv   컬럼 정의서
    data/metadata/quality_report.csv    품질 점검 결과 (긴 형식: 파일 × 점검항목)
    data/metadata/join_key_check.csv    결합 키 후보의 값 겹침 검증 (병합은 하지 않음)
    data/metadata/checksums.sha256      `shasum -a 256 -c` 로 검증 가능한 해시 목록

사용 예:
    python3 scripts/inspect_raw_data.py               # 로컬 점검만
    python3 scripts/inspect_raw_data.py --verify-api  # 서울 Open API 샘플키로 행 수·값 대조 추가
"""
from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import json
import re
import struct
import sys
import urllib.request
import warnings
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
META = ROOT / "data" / "metadata"
PROBE = ROOT / "docs" / "source_probe_20261029.json"
CHUNK = 200_000

# 같은 의미의 컬럼이 파일마다 다른 이름으로 나오는 경우 (예: 점포 2025 ZIP은 영문 소문자 헤더)
ALIASES = {
    "quarter": ["기준_년분기_코드", "stdr_yyqu_cd", "STDR_YYQU_CD"],
    "trdar": ["상권_코드", "trdar_cd", "TRDAR_CD"],
    "trdar_se": ["상권_구분_코드", "trdar_se_cd", "TRDAR_SE_C", "TRDAR_SE_CD"],
    "svc": ["서비스_업종_코드", "svc_induty_cd", "SVC_INDUTY_CD"],
    "adong": ["행정동_코드", "ADSTRD_CD"],
    "signgu": ["자치구_코드", "SIGNGU_CD"],
}
SET_LOGICAL = ["quarter", "trdar", "trdar_se", "svc", "adong", "signgu"]
SET_LITERAL = {"행정동코드", "시군구코드", "시도명", "상권업종소분류코드", "소분류코드"}

KEY_COLUMNS = {  # 중복 키 점검용 (병합 아님)
    "S01": [["상가업소번호"]],
    "S02": [["소분류코드"]],
    "K01": [["quarter", "trdar", "svc"]],
    "K02": [["quarter", "trdar", "svc"]],
    "K03": [["trdar"]],
    "K04": [["quarter", "trdar"]],
    "K05": [["quarter", "trdar"]],
    "K06": [["quarter", "trdar"]],
    "K07": [["quarter", "trdar"]],
}

# 합계 관계 점검 (값이 맞지 않아도 고치지 않고 건수·최대 차이만 기록)
#   (합계 컬럼, 구성 컬럼들, 공백을 0으로 보고 비교할지, 해석 메모)
FAQ_GENDER = "포털 FAQ: 분기 매출은 개인+법인 합산이라 성별·연령별 합과 다를 수 있음 (예상된 차이)"
RELATIONS = {
    "K01": [("당월_매출_금액", ["주중_매출_금액", "주말_매출_금액"], False, ""),
            ("당월_매출_건수", ["주중_매출_건수", "주말_매출_건수"], False, ""),
            ("당월_매출_금액", ["남성_매출_금액", "여성_매출_금액"], False, FAQ_GENDER)],
    "K02": [("similr_induty_stor_co", ["stor_co", "frc_stor_co"], False,
             "포털 설명 '전체 = 일반 + 프랜차이즈'의 검증")],
    "K04": [("총_유동인구_수", ["남성_유동인구_수", "여성_유동인구_수"], False, "")],
    "K05": [("집객시설_수", ["관공서_수", "은행_수", "종합병원_수", "일반_병원_수", "약국_수", "유치원_수",
                          "초등학교_수", "중학교_수", "고등학교_수", "대학교_수", "백화점_수", "슈퍼마켓_수",
                          "극장_수", "숙박_시설_수", "공항_수", "철도_역_수", "버스_터미널_수", "지하철_역_수",
                          "버스_정거장_수"], True,
             "비교용으로만 공백을 0으로 계산. 집객시설_수의 산정 기준은 명세에 없음")],
    "K06": [("총_직장_인구_수", ["남성_직장_인구_수", "여성_직장_인구_수"], False, "")],
    "K07": [("총_상주인구_수", ["남성_상주인구_수", "여성_상주인구_수"], False, ""),
            ("총_가구_수", ["아파트_가구_수", "비_아파트_가구_수"], False, "")],
}

# Shapefile DBF 필드명은 10자로 잘리고, 잘린 이름이 겹치면 _1 이 붙는다. 값으로 대응을 확인한 것만 적는다.
DBF_FIELD_MAP = {"TRDAR_SE_C": "TRDAR_SE_CD", "TRDAR_SE_1": "TRDAR_SE_CD_NM"}

# ---------------------------------------------------------------------------
# 컬럼 의미·단위 사전
#   meaning_basis: '공식 명세' = 포털 설명·Open API 명세에 있는 내용
#                  '명칭 기반 추정' = 컬럼명에서 추정 (STEP 2에서 확인 필요)
# ---------------------------------------------------------------------------
SEMAS_MEANING = {  # 공공데이터포털 상가(상권)정보 Open API(15012005) Swagger 필드 설명 기준
    "상가업소번호": ("해당 상가업소에 부여된 일련번호", ""),
    "상호명": ("해당 상가업소의 상호명", ""),
    "지점명": ("해당 상가업소가 지점인 경우 지점명", ""),
    "상권업종대분류코드": ("상권업종대분류코드(2자리)", ""),
    "상권업종대분류명": ("상권업종대분류명", ""),
    "상권업종중분류코드": ("상권업종중분류코드(4자리)", ""),
    "상권업종중분류명": ("상권업종중분류명", ""),
    "상권업종소분류코드": ("상권업종소분류코드(6자리)", ""),
    "상권업종소분류명": ("상권업종소분류명", ""),
    "표준산업분류코드": ("표준산업분류코드(6자리). 포털 안내 기준 10차", ""),
    "표준산업분류명": ("표준산업분류코드에 대한 명칭", ""),
    "시도코드": ("시도 코드", ""),
    "시도명": ("시도 명칭", ""),
    "시군구코드": ("시군구 코드", ""),
    "시군구명": ("시군구 명칭", ""),
    "행정동코드": ("행정동 코드", ""),
    "행정동명": ("행정동 명칭", ""),
    "법정동코드": ("법정동 코드", ""),
    "법정동명": ("법정동 명칭", ""),
    "지번코드": ("지번주소에 해당하는 PNU코드", ""),
    "대지구분코드": ("지번주소의 대지구분 코드(1:대지, 2:산)", ""),
    "대지구분명": ("지번주소의 대지구분 코드명(대지, 산)", ""),
    "지번본번지": ("지번주소의 본번지", ""),
    "지번부번지": ("지번주소의 부번지", ""),
    "지번주소": ("지번기준 전체주소", ""),
    "도로명코드": ("도로명주소 도로명코드", ""),
    "도로명": ("도로명코드에 대한 명칭", ""),
    "건물본번지": ("도로명주소 기준 건물 본번지", ""),
    "건물부번지": ("도로명주소 기준 건물 부번지", ""),
    "건물관리번호": ("도로명주소 기준 건물관리번호", ""),
    "건물명": ("도로명주소 기준 건물명", ""),
    "도로명주소": ("도로명 주소기준 전체주소", ""),
    "구우편번호": ("구우편번호(개편전 우편번호)", ""),
    "신우편번호": ("신우편번호(개편후 우편번호)", ""),
    "동정보": ("상가업소가 소재한 동정보", ""),
    "층정보": ("상가업소가 소재한 층정보", ""),
    "호정보": ("상가업소가 소재한 호정보", ""),
    "경도": ("WGS84기준 경도 좌표값", "도(degree), WGS84"),
    "위도": ("WGS84기준 위도 좌표값", "도(degree), WGS84"),
}
S02_MEANING = {  # 업종코드표: 컬럼명이 S01 업종 컬럼과 대응
    "대분류코드": "상권업종대분류코드(2자리)",
    "대분류명": "상권업종대분류명",
    "중분류코드": "상권업종중분류코드(4자리)",
    "중분류명": "상권업종중분류명",
    "소분류코드": "상권업종소분류코드(6자리)",
    "소분류명": "상권업종소분류명",
}

SEOUL_FIXED = {
    "기준_년분기_코드": ("기준 연도·분기 코드. YYYYQ 형식(예: 20251 = 2025년 1분기)", "", "명칭·값 기반 추정"),
    "상권_구분_코드": ("상권 유형 코드", "", "공식 명세"),
    "상권_구분_코드_명": ("상권 유형 이름", "", "공식 명세"),
    "상권_코드": ("서울시 상권분석서비스 상권 식별 코드", "", "공식 명세"),
    "상권_코드_명": ("상권 이름", "", "공식 명세"),
    "서비스_업종_코드": ("서울시 상권분석서비스 서비스업종(생활밀접업종) 코드", "", "공식 명세"),
    "서비스_업종_코드_명": ("서비스업종 이름", "", "공식 명세"),
    "당월_매출_금액": ("추정 매출 금액. 컬럼명은 '당월'이지만 포털 FAQ는 분기당 매출 금액(개인+법인 합산)으로 설명", "원", "공식 명세"),
    "당월_매출_건수": ("추정 매출 건수. 컬럼명은 '당월'이지만 행 단위는 분기", "건", "명칭 기반 추정"),
    "전체_점포_수": ("전체 점포 수. 포털 설명: 전체_점포_수 = 일반_점포_수 + 프랜차이즈_점포_수", "개", "공식 명세(관계식)"),
    "엑스좌표_값": ("상권 대표점 X 좌표", "m, EPSG:5181", "공식 명세(좌표계)"),
    "와이좌표_값": ("상권 대표점 Y 좌표", "m, EPSG:5181", "공식 명세(좌표계)"),
    "자치구_코드": ("자치구 코드", "", "공식 명세"),
    "자치구_코드_명": ("자치구 이름", "", "공식 명세"),
    "행정동_코드": ("행정동 코드. 행정안전부 '주민등록 행정기관코드'", "", "공식 명세"),
    "행정동_코드_명": ("행정동 이름", "", "공식 명세"),
    "영역_면적": ("상권 영역 면적", "㎡로 추정(확인 필요)", "명칭 기반 추정"),
}
BROKEN_TMZON = {"06": "00", "11": "06", "14": "11", "17": "14", "21": "17", "24": "21"}


def seoul_meaning(col: str) -> tuple[str, str, str]:
    if col in SEOUL_FIXED:
        return SEOUL_FIXED[col]
    m = re.fullmatch(r"시간대_건수~(\d\d)_매출_건수", col)
    if m:
        e = m.group(1)
        s = BROKEN_TMZON.get(e, "??")
        return (f"시간대 {s}~{e} 매출 건수. 원본 컬럼명 표기 오류(시작 시각 자리에 '건수'). "
                f"Open API 필드 TMZON_{s}_{e}_SELNG_CO와 순서 대조", "건", "Open API 필드명 대조")
    label = col.replace("_", " ")
    if col.endswith("_매출_금액"):
        return (f"{label} (추정매출)", "원", "공식 명세(단위: 원)")
    if col.endswith("_매출_건수"):
        return (f"{label} (추정매출)", "건", "명칭 기반 추정")
    if col.endswith(("_율", "_률")):
        return (label, "%로 추정(확인 필요)", "명칭 기반 추정")
    if col.endswith("_가구_수"):
        return (label, "가구", "명칭 기반 추정")
    if col.endswith(("인구_수", "인구수")):
        return (label, "명", "명칭 기반 추정")
    if col.endswith("_수"):
        return (label, "개", "명칭 기반 추정")
    return (label, "", "명칭 기반 추정")


def load_api_columns() -> dict[str, dict[str, str]]:
    """데이터셋별 {Open API 필드명(대문자): 한글 라벨}."""
    ids = {"OA-15572": "K01", "OA-15577": "K02", "OA-15560": "K03", "OA-15568": "K04",
           "OA-15580": "K05", "OA-15569": "K06", "OA-15584": "K07"}
    out: dict[str, dict[str, str]] = {}
    if PROBE.exists():
        j = json.loads(PROBE.read_text(encoding="utf-8"))
        for oa, d in j.get("seoul", {}).items():
            out[ids[oa]] = {c["field"]: c["label_ko"] for c in d.get("openapi_columns", [])}
    return out


API_FIELDS = load_api_columns()


def describe_column(ds: str, col: str) -> tuple[str, str, str]:
    """(의미, 단위, 근거)."""
    if ds == "S01":
        if col in SEMAS_MEANING:
            m, u = SEMAS_MEANING[col]
            return m, u, "공식 명세(Open API 15012005 필드 설명)"
        return "", "", "명세 미확인"
    if ds == "S02":
        return S02_MEANING.get(col, ""), "", "명칭 기반(S01 업종 컬럼과 대응)"
    fields = API_FIELDS.get(ds, {})
    if col in fields.values() or col.startswith("시간대_건수~"):
        return seoul_meaning(col)
    up = DBF_FIELD_MAP.get(col, col.upper())
    label = fields.get(up)
    if label is None:  # DBF는 필드명이 10자로 잘림
        hits = [f for f in fields if f[:10] == up[:10] and (f.startswith(up) or up.startswith(f[:10]))]
        if len(hits) == 1:
            label = fields[hits[0]]
            up = hits[0]
    if label is None:
        return seoul_meaning(col)
    m, u, b = seoul_meaning(label)
    note = f" [원본 헤더 '{col}' = Open API 필드 {up} = 한글 라벨 '{label}']"
    if up == "SIMILR_INDUTY_STOR_CO":
        note += " 필드명 자체는 '유사업종 점포 수'를 뜻함"
    if col in DBF_FIELD_MAP:
        note += " (DBF 필드명 잘림. 값으로 대응 확인)"
    return m + note, u, b + " + 필드명 대조"


# ---------------------------------------------------------------------------
# 기본 유틸
# ---------------------------------------------------------------------------
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_encoding(path: Path) -> tuple[str, bool]:
    """(인코딩, BOM 여부). 파일 전체를 엄격 디코딩해 판정하며 파일은 바꾸지 않는다."""
    with open(path, "rb") as f:
        bom = f.read(3) == codecs.BOM_UTF8
    for enc in ("utf-8", "cp949"):
        dec = codecs.getincrementaldecoder(enc)(errors="strict")
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    dec.decode(chunk)
                dec.decode(b"", final=True)
            return enc, bom
        except UnicodeDecodeError:
            continue
    return "unknown", bom


def read_encoding(enc: str, bom: bool) -> str:
    return "utf-8-sig" if (enc == "utf-8" and bom) else enc


def sniff_delimiter(path: Path, enc: str) -> str:
    with open(path, encoding=enc, errors="replace") as f:
        head = f.readline()
    counts = {d: head.count(d) for d in [",", "|", "\t", ";"]}
    return max(counts, key=counts.get)


def zip_member_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def col_of(columns, logical: str) -> str | None:
    for c in ALIASES.get(logical, [logical]):
        if c in columns:
            return c
    return None


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


INT_RE = r"-?\d+"
FLOAT_RE = r"-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?"


# ---------------------------------------------------------------------------
# CSV 프로파일링 (청크 단위, dtype=str 로 원문 그대로 읽음)
# ---------------------------------------------------------------------------
def iter_csv(path: Path, prof: dict, usecols=None):
    return pd.read_csv(path, sep=prof["sep"], encoding=read_encoding(prof["encoding"], prof["bom"]),
                       dtype=str, keep_default_na=False, usecols=usecols, chunksize=CHUNK)


def profile_csv(path: Path, ds: str) -> dict:
    enc, bom = detect_encoding(path)
    if enc == "unknown":
        return {"error": "인코딩 판정 실패(UTF-8, CP949 모두 아님)", "encoding": "unknown", "bom": bom}
    sep = sniff_delimiter(path, read_encoding(enc, bom))
    prof = {"encoding": enc, "bom": bom, "sep": sep}
    cols: list[str] | None = None
    stats: dict[str, dict] = {}
    row_hashes, key_hashes = [], defaultdict(list)
    sets: dict[str, set] = defaultdict(set)
    quarters: Counter = Counter()
    rows = 0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            reader = pd.read_csv(path, sep=sep, encoding=read_encoding(enc, bom), dtype=str,
                                 keep_default_na=False, chunksize=CHUNK, on_bad_lines="warn")
            for chunk in reader:
                if cols is None:
                    cols = list(chunk.columns)
                    for c in cols:
                        stats[c] = {"missing": 0, "nonempty": 0, "int_ok": True, "float_ok": True,
                                    "leading_zero": False, "maxlen": 0, "example": "", "distinct": set(),
                                    "zero": 0}
                    keysets = []
                    for ks in KEY_COLUMNS.get(ds, []):
                        real = [col_of(cols, k) for k in ks]
                        if all(real):
                            keysets.append(real)
                    qcol = col_of(cols, "quarter")
                    set_cols = {col_of(cols, lg) for lg in SET_LOGICAL} | (SET_LITERAL & set(cols))
                    set_cols.discard(None)
                rows += len(chunk)
                row_hashes.append(pd.util.hash_pandas_object(chunk, index=False).to_numpy())
                for real in keysets:
                    key_hashes["+".join(real)].append(pd.util.hash_pandas_object(chunk[real], index=False).to_numpy())
                for c in cols:
                    s = chunk[c]
                    empty = s.isna() | (s.fillna("").str.strip() == "")
                    st = stats[c]
                    st["missing"] += int(empty.sum())
                    v = s[~empty]
                    if v.empty:
                        continue
                    st["nonempty"] += len(v)
                    st["zero"] += int(v.str.fullmatch(r"0+(\.0+)?").sum())
                    if not st["example"]:
                        st["example"] = str(v.iloc[0])[:60]
                    if st["int_ok"] and not v.str.fullmatch(INT_RE).all():
                        st["int_ok"] = False
                    if st["float_ok"] and not v.str.fullmatch(FLOAT_RE).all():
                        st["float_ok"] = False
                    if not st["leading_zero"] and v.str.fullmatch(r"0\d+").any():
                        st["leading_zero"] = True
                    st["maxlen"] = max(st["maxlen"], int(v.str.len().max()))
                    st["distinct"].update(v.unique().tolist())
                    if c in set_cols:
                        sets[c].update(v.unique().tolist())
                if qcol:
                    quarters.update(chunk[qcol].tolist())
        except Exception as e:
            return {**prof, "error": f"{type(e).__name__}: {e}"}
    bad = [str(w.message)[:300] for w in caught if "Skipping line" in str(w.message)]
    all_hash = np.concatenate(row_hashes) if row_hashes else np.array([], dtype=np.uint64)
    dup_keys = {k: int(sum(len(p) for p in parts) - len(np.unique(np.concatenate(parts))))
                for k, parts in key_hashes.items()}
    prof.update(rows=rows, columns=cols or [], stats=stats, sets=sets, quarters=dict(sorted(quarters.items())),
                dup_rows=int(len(all_hash) - len(np.unique(all_hash))), dup_keys=dup_keys, bad_lines=bad)
    return prof


CODE_NAME = re.compile(r"(코드|번호|_cd$|^.*_CD$|우편번호)", re.I)


def infer_type(st: dict, col: str = "") -> str:
    if st["nonempty"] == 0:
        return "empty"
    if st["int_ok"]:
        if st["leading_zero"]:
            return "code (숫자 문자열, 선행 0 있음 → 문자열 유지 필수)"
        if CODE_NAME.search(col):
            return "code (숫자 문자열 → 문자열 유지 권장)"
        return "integer"
    if st["float_ok"]:
        return "float"
    return "string"


def relation_mismatches(path: Path, prof: dict, total: str, parts: list[str],
                        blank_as_zero: bool = False) -> tuple[int, int, int, float]:
    """(비교 행 수, 불일치 행 수, 결측으로 비교 제외된 행 수, 최대 절대 차이)."""
    n = bad = skipped = 0
    maxdiff = 0.0
    for ch in iter_csv(path, prof, usecols=[total, *parts]):
        t = pd.to_numeric(ch[total], errors="coerce")
        ps = [pd.to_numeric(ch[p], errors="coerce") for p in parts]
        if blank_as_zero:
            ps = [p.fillna(0) for p in ps]
        ok = t.notna()
        for p in ps:
            ok &= p.notna()
        skipped += int((~ok).sum())
        diff = (t - sum(ps)).abs()[ok]
        n += int(ok.sum())
        bad += int((diff > 0.5).sum())
        if len(diff):
            maxdiff = max(maxdiff, float(diff.max()))
    return n, bad, skipped, maxdiff


# ---------------------------------------------------------------------------
# Shapefile (외부 라이브러리 없이 헤더·DBF만 읽음)
# ---------------------------------------------------------------------------
SHAPE_TYPES = {0: "Null", 1: "Point", 3: "PolyLine", 5: "Polygon", 8: "MultiPoint",
               11: "PointZ", 13: "PolyLineZ", 15: "PolygonZ", 21: "PointM", 23: "PolyLineM", 25: "PolygonM"}


def profile_shp(shp: Path) -> dict:
    with open(shp, "rb") as f:
        h = f.read(100)
    out = {"file_code": struct.unpack(">i", h[0:4])[0],
           "shape_type": SHAPE_TYPES.get(struct.unpack("<i", h[32:36])[0], "unknown"),
           "bbox": "{:.1f},{:.1f},{:.1f},{:.1f}".format(*struct.unpack("<4d", h[36:68]))}
    prj, cpg = shp.with_suffix(".prj"), shp.with_suffix(".cpg")
    out["prj"] = prj.read_text(errors="replace").strip() if prj.exists() else ""
    out["cpg"] = cpg.read_text(errors="replace").strip() if cpg.exists() else ""
    dbf = shp.with_suffix(".dbf")
    if dbf.exists():
        out.update(read_dbf(dbf, out["cpg"]))
    shx = shp.with_suffix(".shx")
    if shx.exists():  # shx 레코드 수 = (파일 길이 - 100) / 8
        out["shx_records"] = (shx.stat().st_size - 100) // 8
    return out


def read_dbf(dbf: Path, cpg: str) -> dict:
    data = dbf.read_bytes()
    nrec = struct.unpack("<I", data[4:8])[0]
    hlen, rlen = struct.unpack("<H", data[8:10])[0], struct.unpack("<H", data[10:12])[0]
    fields, pos = [], 32
    while data[pos] != 0x0D:
        d = data[pos:pos + 32]
        fields.append((d[:11].split(b"\x00")[0].decode("ascii", "replace"), chr(d[11]), d[16], d[17]))
        pos += 32
    for enc in ([cpg.lower()] if cpg else []) + ["utf-8", "cp949"]:
        try:
            recs = []
            for i in range(nrec):
                rec = data[hlen + i * rlen: hlen + (i + 1) * rlen]
                if not rec or rec[0:1] == b"*":
                    continue
                vals, p = {}, 1
                for name, _t, ln, _dc in fields:
                    vals[name] = rec[p:p + ln].decode(enc).strip()
                    p += ln
                recs.append(vals)
            return {"dbf_records": nrec, "dbf_fields": fields, "dbf_encoding": enc, "dbf_rows": recs}
        except (UnicodeDecodeError, LookupError):
            continue
    return {"dbf_records": nrec, "dbf_fields": fields, "dbf_encoding": None, "dbf_rows": []}


# ---------------------------------------------------------------------------
# 서울 Open API 샘플키 대조 (선택)
# ---------------------------------------------------------------------------
API_SERVICE = {"K01": "VwsmTrdarSelngQq", "K02": "VwsmTrdarStorQq", "K03": "TbgisTrdarRelm",
               "K04": "VwsmTrdarFlpopQq", "K05": "VwsmTrdarFcltyQq", "K06": "VwsmTrdarWrcPopltnQq",
               "K07": "VwsmTrdarRepopQq"}
API_QUARTER_PARAM = {"K01", "K02", "K04"}


def api_json(service: str, start: int, end: int, quarter: str | None = None) -> dict:
    url = f"http://openapi.seoul.go.kr:8088/sample/json/{service}/{start}/{end}/" + (quarter or "")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
        j = json.loads(r.read().decode("utf-8"))
    return j.get(service, j)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify-api", action="store_true", help="서울 Open API 샘플키로 행 수·샘플값 대조")
    args = ap.parse_args()

    manifest_path = META / "download_manifest.csv"
    if not manifest_path.exists():
        print("download_manifest.csv 가 없습니다. 먼저 scripts/download_data.py 를 실행하세요.", file=sys.stderr)
        return 1
    manifest: dict[str, dict] = {}
    with open(manifest_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):  # 같은 파일은 마지막 기록을 사용
            manifest[r["local_file_path"]] = r

    catalog, dictionary, quality, keychecks, checksums = [], [], [], [], []
    csv_prof: dict[str, tuple[str, dict]] = {}   # path -> (dataset_id, profile)
    shp_prof: dict[str, tuple[str, dict]] = {}

    def q(ds, path, check, result, value="", detail=""):
        quality.append({"dataset_id": ds, "local_file_path": path, "check": check, "result": result,
                        "value": value, "detail": detail})

    for path_str, m in manifest.items():
        ds = m["dataset_id"]
        base = {k: m.get(k, "") for k in ["provider", "dataset_name", "source_url", "reference_period", "collected_at"]}
        p = ROOT / path_str
        if m["status"] != "collected" or not p.exists():
            catalog.append({"dataset_id": ds, **base, "local_file_path": path_str,
                            "original_filename": m.get("original_filename", ""),
                            "file_format": Path(path_str).suffix.lstrip(".").upper(),
                            "collection_status": "failed" if m["status"] == "failed" else "missing",
                            "notes": m.get("error", "")})
            q(ds, path_str, "download", "fail", "", m.get("error", "") or "파일 없음")
            continue

        digest = sha256(p)
        checksums.append((digest, path_str))
        same = digest == m.get("sha256")
        q(ds, path_str, "sha256_vs_download_manifest", "pass" if same else "fail", digest,
          "다운로드 시점 해시와 일치" if same else f"manifest={m.get('sha256')}")
        entry = {"dataset_id": ds, **base, "local_file_path": path_str,
                 "original_filename": m.get("original_filename", ""), "parent_file": "",
                 "file_format": p.suffix.lstrip(".").upper(),
                 "file_size_mb": f"{p.stat().st_size / 1024 / 1024:.3f}", "sha256": digest,
                 "collection_status": "collected"}
        targets: list[tuple[Path, str]] = []
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                members = [(zip_member_name(i), i.file_size) for i in z.infolist() if not i.is_dir()]
                bad = z.testzip()
            q(ds, path_str, "zip_integrity", "pass" if bad is None else "fail", "", bad or "CRC 검사 이상 없음")
            q(ds, path_str, "zip_members", "info", str(len(members)), "; ".join(f"{n} ({s:,} B)" for n, s in members))
            ex_dir = p.parent / "extracted" / p.stem
            extracted = sorted(f for f in ex_dir.rglob("*") if f.is_file()) if ex_dir.exists() else []
            entry["notes"] = (f"원본 ZIP. 구성 파일 {len(members)}개. 압축 해제본 {len(extracted)}개는 "
                              f"{rel(ex_dir) if ex_dir.exists() else '없음'}")
            catalog.append(entry)
            targets = [(f, path_str) for f in extracted]
        else:
            targets = [(p, "")]

        for f, parent in targets:
            fpath = rel(f)
            fe = {**entry, "local_file_path": fpath, "parent_file": parent,
                  "original_filename": f.name if parent else entry["original_filename"],
                  "file_format": f.suffix.lstrip(".").upper(),
                  "file_size_mb": f"{f.stat().st_size / 1024 / 1024:.3f}", "notes": ""}
            if parent:
                fe["sha256"] = sha256(f)
                checksums.append((fe["sha256"], fpath))
                fe["collection_status"] = "collected (압축 해제본)"
            sfx = f.suffix.lower()
            if sfx == ".csv":
                prof = profile_csv(f, ds)
                if "error" in prof:
                    fe.update(encoding=prof.get("encoding", ""), notes=f"읽기 오류: {prof['error']}")
                    q(ds, fpath, "read", "fail", "", prof["error"])
                    catalog.append(fe)
                    continue
                csv_prof[fpath] = (ds, prof)
                enc_label = prof["encoding"] + (" (BOM)" if prof["bom"] else "")
                notes = [f"구분자 {prof['sep']!r}"]
                period = fe["reference_period"]
                if prof["quarters"]:
                    qs = prof["quarters"]
                    period = f"{min(qs)}~{max(qs)} ({len(qs)}개 분기)"
                    n2025 = sum(v for k, v in qs.items() if k.startswith("2025"))
                    if n2025 != prof["rows"]:
                        notes.append(f"2025년 행 {n2025:,}개 / 전체 {prof['rows']:,}개 (2025 외 연도 포함)")
                fe.update(encoding=enc_label, row_count=prof["rows"], column_count=len(prof["columns"]),
                          reference_period=period, notes="; ".join(notes))
                catalog.append(fe)
                q(ds, fpath, "read", "pass", "", f"encoding={enc_label}, sep={prof['sep']!r}")
                q(ds, fpath, "row_count", "info", str(prof["rows"]))
                q(ds, fpath, "column_count", "info", str(len(prof["columns"])))
                q(ds, fpath, "malformed_lines", "pass" if not prof["bad_lines"] else "warn", str(len(prof["bad_lines"])),
                  " | ".join(prof["bad_lines"][:3]))
                miss = {c: s["missing"] for c, s in prof["stats"].items() if s["missing"]}
                q(ds, fpath, "missing_cells_total", "pass" if not miss else "warn", str(sum(miss.values())),
                  "; ".join(f"{c}={n:,}" for c, n in miss.items()))
                q(ds, fpath, "duplicate_rows", "pass" if prof["dup_rows"] == 0 else "warn", str(prof["dup_rows"]),
                  "모든 컬럼 값이 같은 행 수(첫 등장 제외)")
                for k, n in prof["dup_keys"].items():
                    q(ds, fpath, f"duplicate_key[{k}]", "pass" if n == 0 else "warn", str(n))
                if prof["quarters"]:
                    q(ds, fpath, "quarter_coverage", "info", str(len(prof["quarters"])),
                      json.dumps(prof["quarters"], ensure_ascii=False))
                for total, parts, b0, memo in RELATIONS.get(ds, []):
                    if all(c in prof["columns"] for c in [total, *parts]):
                        n, bad, skipped, mx = relation_mismatches(f, prof, total, parts, b0)
                        name = " + ".join(parts) if len(parts) <= 3 else f"하위 {len(parts)}개 컬럼 합"
                        res = "pass" if bad == 0 else ("info" if memo == FAQ_GENDER else "warn")
                        detail = f"최대 차이 {mx:,.0f}; 결측으로 비교 제외 {skipped:,}행"
                        if bad and mx <= 10 and memo != FAQ_GENDER:
                            detail += "; 차이가 작아 반올림 오차로 추정"
                        q(ds, fpath, f"relation[{total} = {name}]", res, f"불일치 {bad:,} / 비교 {n:,}",
                          detail + (f"; {memo}" if memo else ""))
                # 서울 통계(건수·인구·시설 수) 컬럼만 대상. 주소 번지처럼 0이 원래 없는 컬럼은 제외
                blank_zero = [c for c, s in prof["stats"].items()
                              if ds.startswith("K") and s["missing"] and s["zero"] == 0
                              and (s["int_ok"] or s["float_ok"]) and s["nonempty"]]
                if blank_zero:
                    q(ds, fpath, "blank_without_zero", "warn", str(len(blank_zero)),
                      "숫자 컬럼인데 0은 한 번도 없고 공백만 있음 → 공백이 0을 뜻할 가능성. 원본은 그대로 둠: "
                      + ", ".join(blank_zero))
                for i, c in enumerate(prof["columns"], 1):
                    st = prof["stats"][c]
                    meaning, unit, basis = describe_column(ds, c)
                    if c in blank_zero:
                        meaning += " (주의: 0 대신 공백으로 표기된 것으로 보임)"
                    dictionary.append({
                        "dataset_id": ds, "local_file_path": fpath, "column_order": i, "column_name": c,
                        "source_type": "text (CSV에는 선언된 타입 없음)", "inferred_type": infer_type(st, c),
                        "max_length": st["maxlen"], "meaning": meaning, "unit": unit, "meaning_basis": basis,
                        "missing_count": st["missing"],
                        "missing_rate": f"{st['missing'] / prof['rows']:.4f}" if prof["rows"] else "",
                        "has_missing": "Y" if st["missing"] else "N", "distinct_count": len(st["distinct"]),
                        "example_value": st["example"]})
            elif sfx == ".shp":
                sp = profile_shp(f)
                shp_prof[fpath] = (ds, sp)
                fe.update(encoding=f"DBF {sp.get('dbf_encoding')} (.cpg={sp['cpg'] or '없음'})",
                          row_count=sp.get("dbf_records", ""), column_count=len(sp.get("dbf_fields", [])),
                          reference_period=fe["reference_period"],
                          notes=f"{sp['shape_type']}; bbox={sp['bbox']}; PRJ={sp['prj'][:60]}...")
                catalog.append(fe)
                q(ds, fpath, "shp_header", "pass" if sp["file_code"] == 9994 else "fail", sp["shape_type"], f"bbox={sp['bbox']}")
                q(ds, fpath, "crs_prj", "info" if sp["prj"] else "warn", "EPSG:5181 해당" if "Central_Belt" in sp["prj"]
                  and "500000" in sp["prj"] else "", sp["prj"] or ".prj 없음")
                q(ds, fpath, "shp_dbf_record_match", "pass" if sp.get("shx_records") == sp.get("dbf_records") else "warn",
                  f"shx={sp.get('shx_records')}, dbf={sp.get('dbf_records')}")
                rows = sp.get("dbf_rows", [])
                tr = col_of([x[0] for x in sp.get("dbf_fields", [])], "trdar")
                if tr:
                    codes = [r[tr] for r in rows]
                    q(ds, fpath, f"duplicate_key[{tr}]", "pass" if len(codes) == len(set(codes)) else "warn",
                      str(len(codes) - len(set(codes))))
                for i, (name, t, ln, dc) in enumerate(sp.get("dbf_fields", []), 1):
                    vals = [r.get(name, "") for r in rows]
                    miss = sum(1 for v in vals if v == "")
                    meaning, unit, basis = describe_column(ds, name)
                    dictionary.append({
                        "dataset_id": ds, "local_file_path": fpath, "column_order": i, "column_name": name,
                        "source_type": f"DBF {t}({ln},{dc})",
                        "inferred_type": {"C": "string", "N": "numeric", "F": "float", "D": "date", "L": "logical"}.get(t, t),
                        "max_length": max((len(v) for v in vals), default=0), "meaning": meaning, "unit": unit,
                        "meaning_basis": basis, "missing_count": miss,
                        "missing_rate": f"{miss / len(vals):.4f}" if vals else "",
                        "has_missing": "Y" if miss else "N", "distinct_count": len(set(vals)),
                        "example_value": vals[0][:60] if vals else ""})
            else:
                fe.update(notes="보조 파일(구조 점검 대상 아님)" if sfx not in (".txt",) else "안내문 텍스트")
                catalog.append(fe)

    # -----------------------------------------------------------------------
    # 결합 키 후보 검증 (값 집합 비교만. 병합하지 않음)
    # -----------------------------------------------------------------------
    def find(ds_id):
        return next(((fp, p) for fp, (d, p) in csv_prof.items() if d == ds_id), (None, None))

    def values_2025(fp, prof, logical):
        col = col_of(prof["columns"], logical) or logical
        qcol = col_of(prof["columns"], "quarter")
        use = [c for c in {col, qcol} if c]
        s = set()
        for ch in iter_csv(ROOT / fp, prof, usecols=use):
            if qcol and col != qcol:
                ch = ch[ch[qcol].str.startswith("2025")]
            elif qcol:
                ch = ch[ch[qcol].str.startswith("2025")]
            s.update(ch[col].tolist())
        return s

    def compare(name, a_label, a, b_label, b, note=""):
        keychecks.append({"check": name, "left": a_label, "right": b_label, "left_n": len(a), "right_n": len(b),
                          "intersection_n": len(a & b), "left_only_n": len(a - b), "right_only_n": len(b - a),
                          "left_only_examples": ", ".join(sorted(a - b)[:10]),
                          "right_only_examples": ", ".join(sorted(b - a)[:10]),
                          "verdict": "일치" if a == b else ("부분 일치" if a & b else "불일치"), "note": note})

    area = {}
    for fp, (d, sp) in shp_prof.items():
        if d == "K03":
            names = [x[0] for x in sp["dbf_fields"]]
            for lg in ["trdar", "adong", "signgu", "trdar_se"]:
                c = col_of(names, lg)
                if c:
                    area[lg] = {r[c] for r in sp["dbf_rows"]}
            area["label"] = f"K03 영역 SHP ({fp})"
    if area.get("trdar"):
        for d in ["K01", "K02", "K04", "K05", "K06", "K07"]:
            fp, prof = find(d)
            if fp:
                compare("상권코드(2025년 행) vs 상권 영역", f"{d} {col_of(prof['columns'], 'trdar')} ({fp})",
                        values_2025(fp, prof, "trdar"), f"{area['label']} TRDAR_CD", area["trdar"])
        fp1, p1 = find("K01")
        fp4, p4 = find("K04")
        for d in ["K02", "K05", "K06", "K07"]:
            fp, prof = find(d)
            if fp and fp4:
                compare("기준_년분기_코드(2025년 행) vs 길단위인구", f"{d}", values_2025(fp, prof, "quarter"),
                        "K04", values_2025(fp4, p4, "quarter"))
        fp2, p2 = find("K02")
        if fp1 and fp2:
            compare("서비스업종코드(2025년 행): 추정매출 vs 점포", "K01 서비스_업종_코드", values_2025(fp1, p1, "svc"),
                    "K02 svc_induty_cd", values_2025(fp2, p2, "svc"))
            compare("상권코드(2025년 행): 추정매출 vs 점포", "K01 상권_코드", values_2025(fp1, p1, "trdar"),
                    "K02 trdar_cd", values_2025(fp2, p2, "trdar"), "추정매출은 매출이 잡힌 상권×업종만 행이 있음")
        if fp1:
            compare("상권구분코드: 추정매출 vs 상권 영역", "K01 상권_구분_코드", values_2025(fp1, p1, "trdar_se"),
                    "K03 TRDAR_SE_C", area.get("trdar_se", set()))
    fs1, ps1 = find("S01")
    if fs1 and area.get("adong"):
        sem_adong = ps1["sets"].get("행정동코드", set())
        compare("행정동코드: 소상공인 상가정보 vs 서울 상권 영역", "S01 행정동코드", sem_adong, "K03 ADSTRD_CD",
                area["adong"], f"자릿수 S01={dict(Counter(len(x) for x in sem_adong))}, "
                               f"K03={dict(Counter(len(x) for x in area['adong']))}. K03은 상권이 걸친 행정동만 포함")
        compare("시군구코드: 소상공인 상가정보 vs 서울 상권 영역 자치구", "S01 시군구코드",
                ps1["sets"].get("시군구코드", set()), "K03 SIGNGU_CD", area.get("signgu", set()))
    fs2, ps2 = find("S02")
    if fs1 and fs2:
        compare("상권업종소분류코드: 상가정보(2025-12-31) vs 업종코드표(2023-02-28)", "S01 상권업종소분류코드",
                ps1["sets"].get("상권업종소분류코드", set()), "S02 소분류코드", ps2["sets"].get("소분류코드", set()))
    if fs1:
        q("S01", fs1, "시도명_values", "pass" if ps1["sets"].get("시도명") == {"서울특별시"} else "warn",
          ", ".join(sorted(ps1["sets"].get("시도명", set()))), "서울 파일에 서울 외 시도가 섞였는지 확인")
        lon_min = lat_min = 1e9
        lon_max = lat_max = -1e9
        bad = 0
        for ch in iter_csv(ROOT / fs1, ps1, usecols=["경도", "위도"]):
            lon, lat = pd.to_numeric(ch["경도"], errors="coerce"), pd.to_numeric(ch["위도"], errors="coerce")
            bad += int((lon.isna() | lat.isna()).sum())
            lon_min, lon_max = min(lon_min, lon.min()), max(lon_max, lon.max())
            lat_min, lat_max = min(lat_min, lat.min()), max(lat_max, lat.max())
        inside = 126.7 <= lon_min and lon_max <= 127.3 and 37.4 <= lat_min and lat_max <= 37.75
        q("S01", fs1, "coordinate_range_wgs84", "pass" if inside else "warn",
          f"경도 {lon_min:.5f}~{lon_max:.5f}, 위도 {lat_min:.5f}~{lat_max:.5f}",
          f"숫자 변환 불가 {bad}건. 기준: 서울 대략 범위 경도 126.7~127.3, 위도 37.4~37.75")

    # -----------------------------------------------------------------------
    # 서울 Open API 샘플키 대조 (현재 서비스 값과 원본 파일 값 비교)
    # -----------------------------------------------------------------------
    if args.verify_api:
        for d, svc in API_SERVICE.items():
            fp, prof = find(d)
            if not fp and d == "K03":
                sp_item = next(((k, v) for k, (dd, v) in shp_prof.items() if dd == "K03"), None)
                if sp_item:
                    try:
                        api_n = api_json(svc, 1, 5).get("list_total_count")
                        q(d, sp_item[0], "api_total_rows", "pass" if api_n == sp_item[1]["dbf_records"] else "warn",
                          f"file={sp_item[1]['dbf_records']}, api={api_n}")
                    except Exception as e:
                        q(d, sp_item[0], "api_check", "warn", "", f"API 대조 실패: {e}")
                continue
            if not fp:
                continue
            try:
                fields = API_FIELDS.get(d, {})
                if d in API_QUARTER_PARAM:
                    for qt, n in prof["quarters"].items():
                        b = api_json(svc, 1, 5, qt)
                        api_n = b.get("list_total_count")
                        q(d, fp, f"api_row_count[{qt}]", "pass" if api_n == n else "warn", f"file={n:,}, api={api_n}")
                    qt = min(prof["quarters"])
                    rows_api = api_json(svc, 1, 5, qt).get("row", [])
                    qcol = col_of(prof["columns"], "quarter")
                    df = pd.concat(ch[ch[qcol] == qt] for ch in iter_csv(ROOT / fp, prof))
                    keyreal = [col_of(prof["columns"], k) for k in KEY_COLUMNS[d][0]]
                    ok = mismatch = notfound = 0
                    details = []
                    for r in rows_api:
                        def file_col(api_field):
                            for c in (fields.get(api_field), api_field.lower(), api_field):
                                if c and c in df.columns:
                                    return c
                            return None
                        sel = df
                        for kc in keyreal:
                            api_f = next((af for af in r if file_col(af) == kc), None)
                            sel = sel[sel[kc] == str(r.get(api_f))]
                        if sel.empty:
                            notfound += 1
                            continue
                        row = sel.iloc[0]
                        diff = []
                        for af, v in r.items():
                            c = file_col(af)
                            if c and isinstance(v, (int, float)):
                                fv = pd.to_numeric(row[c], errors="coerce")
                                if pd.isna(fv) and float(v) == 0:
                                    continue
                                if pd.isna(fv) or not np.isclose(fv, float(v)):
                                    diff.append(f"{c}: file={row[c]} api={v}")
                        if diff:
                            mismatch += 1
                            details.append("; ".join(diff[:3]))
                        else:
                            ok += 1
                    q(d, fp, f"api_sample_values[{qt}]", "pass" if mismatch == 0 and notfound == 0 else "warn",
                      f"일치 {ok}, 불일치 {mismatch}, 파일에 없음 {notfound} (API 샘플 {len(rows_api)}행)",
                      " | ".join(details[:3]))
                else:
                    api_n = api_json(svc, 1, 5).get("list_total_count")
                    q(d, fp, "api_total_rows", "pass" if api_n == prof["rows"] else "warn",
                      f"file={prof['rows']:,}, api={api_n}", "필터 없는 전체 기간 비교")
            except Exception as e:
                q(d, fp, "api_check", "warn", "", f"API 대조 실패: {type(e).__name__}: {e}")

    # -----------------------------------------------------------------------
    META.mkdir(parents=True, exist_ok=True)
    write_csv(META / "data_catalog.csv",
              ["dataset_id", "provider", "dataset_name", "source_url", "local_file_path", "original_filename",
               "parent_file", "file_format", "encoding", "row_count", "column_count", "file_size_mb", "sha256",
               "reference_period", "collected_at", "collection_status", "notes"], catalog)
    write_csv(META / "data_dictionary.csv",
              ["dataset_id", "local_file_path", "column_order", "column_name", "source_type", "inferred_type",
               "max_length", "meaning", "unit", "meaning_basis", "missing_count", "missing_rate", "has_missing",
               "distinct_count", "example_value"], dictionary)
    write_csv(META / "quality_report.csv", ["dataset_id", "local_file_path", "check", "result", "value", "detail"], quality)
    write_csv(META / "join_key_check.csv",
              ["check", "left", "right", "left_n", "right_n", "intersection_n", "left_only_n", "right_only_n",
               "left_only_examples", "right_only_examples", "verdict", "note"], keychecks)
    with open(META / "checksums.sha256", "w", encoding="utf-8") as f:
        for digest, pth in checksums:
            f.write(f"{digest}  {pth}\n")
    print(f"catalog {len(catalog)}행, dictionary {len(dictionary)}행, quality {len(quality)}행, "
          f"join_key_check {len(keychecks)}행 → {rel(META)}/")
    for x in quality:
        if x["result"] in ("warn", "fail"):
            print(f"  [{x['result']}] {x['dataset_id']} {x['check']}: {x['value']} | {x['detail'][:150]}")
    return 0


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    # 메타데이터 CSV는 엑셀에서도 한글이 깨지지 않도록 UTF-8 BOM으로 저장 (원본 데이터와 무관)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


if __name__ == "__main__":
    sys.exit(main())
