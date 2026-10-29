#!/usr/bin/env python3
"""STEP 1 Raw Data 다운로드 스크립트.

공식 출처(공공데이터포털, 서울 열린데이터광장)에서 원본 파일을 내려받아
data/raw/ 아래에 저장한다. 파일 내용은 바꾸지 않고, 저장 파일명만 규칙에 맞춘다.

- 표준 라이브러리만 사용한다 (추가 설치 불필요).
- 인증키가 필요 없는 경로만 사용한다.
- 내려받은 결과는 data/metadata/download_manifest.csv 에 누적 기록한다.
- 압축파일은 원본을 보존하고 data/raw/{provider}/extracted/ 에 별도로 해제한다.

사용 예:
    python3 scripts/download_data.py                 # 기본 수집 대상 전체
    python3 scripts/download_data.py --only K01 K02  # 일부만
    python3 scripts/download_data.py --force         # 이미 있어도 다시 받기
    python3 scripts/download_data.py --semas-extra 20250331 20250630 20251030
                                                     # 2025년 다른 분기 스냅숏 추가
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
META = ROOT / "data" / "metadata"
MANIFEST = META / "download_manifest.csv"

UA = {"User-Agent": "Mozilla/5.0 (seoul-commercial-analysis STEP1 collector)"}
KST = dt.timezone(dt.timedelta(hours=9))

# ---------------------------------------------------------------------------
# 공공데이터포털: 상가(상권)정보 릴리스 (포털 '주기성 과거 데이터' 목록에서 확인한 ID)
# ---------------------------------------------------------------------------
SEMAS_STORE_PK = "15083033"
SEMAS_STORE_RELEASES = {
    # 기준일(포털 데이터명 끝 날짜): publicDataDetailPk
    "20260630": "uddi:b3094bc9-8756-4ecc-9141-9144b98a531e",
    "20260331": "uddi:6a450671-390c-4b6d-979c-fa056a627084",
    "20251231": "uddi:3e70fffc-390a-4bc7-8b4a-ab5cf0f846bf",
    "20251030": "uddi:9a136460-5faf-4ab7-a887-8c2b425274e4",
    "20250630": "uddi:05123ff0-e436-40f2-9814-ad1ac0ae4be4",
    "20250331": "uddi:e61bf1be-7a4c-400a-99a7-f91543ca64ca",
    "20241231": "uddi:86a02b73-c0ce-447f-a492-f99490392056",
    "20240930": "uddi:9cefeea7-4b0a-4817-ae7c-9f79ca2c7cfd",
    "20240630": "uddi:b5774885-a961-41a0-9e17-ac43087a3767",
    "20240331": "uddi:4e95c557-240a-45cd-ab99-e631763a9f1c",
}


def semas_store_target(ref_date: str) -> dict:
    return {
        "id": f"S01_{ref_date}",
        "dataset_id": "S01",
        "provider": "소상공인시장진흥공단",
        "dataset_name": f"소상공인시장진흥공단_상가(상권)정보_{ref_date}",
        "source_url": "https://www.data.go.kr/data/15083033/fileData.do",
        "method": "datagokr",
        "public_data_pk": SEMAS_STORE_PK,
        "detail_pk": SEMAS_STORE_RELEASES[ref_date],
        "expect_name": f"상가(상권)정보_{ref_date}",
        "subdir": "semas",
        "local_name": f"semas_store_{ref_date}.zip",
        "reference_period": ref_date,
        # 전국 ZIP 중 서울 CSV와 안내문만 해제한다 (원본 ZIP은 그대로 보존)
        "extract_filter": ("서울", "필독"),
    }


TARGETS = [
    semas_store_target("20251231"),
    {
        "id": "S02",
        "dataset_id": "S02",
        "provider": "소상공인시장진흥공단",
        "dataset_name": "소상공인시장진흥공단_상가(상권)정보 업종코드_20230228",
        "source_url": "https://www.data.go.kr/data/15067631/fileData.do",
        "method": "datagokr",
        "public_data_pk": "15067631",
        "detail_pk": "uddi:25e5510c-001c-41e5-9f93-80ad8faba582",
        "expect_name": "업종코드",
        "subdir": "semas",
        "local_name": "semas_industry_code_20230228.csv",
        "reference_period": "20230228",
    },
    {
        "id": "K01",
        "dataset_id": "K01",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(추정매출-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15572/S/1/datasetView.do",
        "method": "seoul_file",
        "inf_id": "OA-15572",
        "file_match": "(추정매출-상권)_2025년.zip",
        "subdir": "seoul",
        "local_name": "seoul_sales_trdar_2025.zip",
        "reference_period": "2025",
    },
    {
        "id": "K02",
        "dataset_id": "K02",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(점포-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15577/S/1/datasetView.do",
        "method": "seoul_file",
        "inf_id": "OA-15577",
        "file_match": "(점포-상권)_2025년.zip",
        "subdir": "seoul",
        "local_name": "seoul_store_trdar_2025.zip",
        "reference_period": "2025",
    },
    {
        "id": "K03",
        "dataset_id": "K03",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(영역-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do",
        "method": "seoul_file",
        "inf_id": "OA-15560",
        "file_match": "(영역-상권).zip",
        "subdir": "seoul",
        "local_name": "seoul_area_trdar.zip",
        "reference_period": "현행 상권 영역(시점 구분 없음)",
    },
    {
        "id": "K04",
        "dataset_id": "K04",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(길단위인구-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do",
        "method": "seoul_sheet",
        "inf_id": "OA-15568",
        # 포털 시트 화면이 제공하는 '기준_년분기_코드' 필터 (앞부분 일치로 동작 확인)
        "sheet_filter": ("STDR_YYQU_CD", "2025"),
        "order_by": "STDR_YYQU_CD DESC",
        "subdir": "seoul",
        "local_name": "seoul_flpop_trdar_2025_sheet.csv",
        "reference_period": "2025",
    },
    {
        "id": "K05",
        "dataset_id": "K05",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(집객시설-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15580/S/1/datasetView.do",
        "method": "seoul_sheet",
        "inf_id": "OA-15580",
        "sheet_filter": None,  # 포털이 필터를 제공하지 않아 전체 기간 파일만 받을 수 있음
        "order_by": "STDR_YYQU_CD DESC",
        "subdir": "seoul",
        "local_name": "seoul_facility_trdar_all_sheet.csv",
        "reference_period": "전체 제공 기간(2025 외 연도 포함)",
    },
    {
        "id": "K06",
        "dataset_id": "K06",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(직장인구-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15569/S/1/datasetView.do",
        "method": "seoul_sheet",
        "inf_id": "OA-15569",
        "sheet_filter": None,
        "order_by": "STDR_YYQU_CD DESC",
        "subdir": "seoul",
        "local_name": "seoul_wrcpop_trdar_all_sheet.csv",
        "reference_period": "전체 제공 기간(2025 외 연도 포함)",
    },
    {
        "id": "K07",
        "dataset_id": "K07",
        "provider": "서울신용보증재단(서울특별시)",
        "dataset_name": "서울시 상권분석서비스(상주인구-상권)",
        "source_url": "https://data.seoul.go.kr/dataList/OA-15584/S/1/datasetView.do",
        "method": "seoul_sheet",
        "inf_id": "OA-15584",
        "sheet_filter": None,
        "order_by": "STDR_YYQU_CD DESC",
        "subdir": "seoul",
        "local_name": "seoul_repop_trdar_all_sheet.csv",
        "reference_period": "전체 제공 기간(2025 외 연도 포함)",
    },
]

MANIFEST_FIELDS = [
    "target_id", "dataset_id", "provider", "dataset_name", "source_url", "download_url",
    "request_params", "local_file_path", "original_filename", "bytes", "sha256",
    "reference_period", "collected_at", "status", "error",
]


class DownloadError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _request(url: str, data: dict | None = None, extra_headers: dict | None = None,
             timeout: int = 300):
    headers = dict(UA)
    if extra_headers:
        headers.update(extra_headers)
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def _text(url: str, data: dict | None = None, **kw) -> str:
    with _request(url, data, **kw) as r:
        return r.read().decode("utf-8", "replace")


def decode_content_disposition(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"filename\*=UTF-8''([^;]+)", value, re.I)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.search(r'filename="?([^";]+)"?', value)
    if not m:
        return None
    raw = m.group(1)
    for enc in ("utf-8", "cp949"):
        try:
            return raw.encode("latin-1").decode(enc)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return urllib.parse.unquote(raw)


def stream_to_file(resp, dest: Path) -> tuple[int, str]:
    """응답 본문을 .part 파일에 쓰고, 끝나면 최종 이름으로 바꾼다."""
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    total = 0
    expected = resp.headers.get("Content-Length")
    next_report = 50 * 1024 * 1024
    with open(part, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            total += len(chunk)
            if total >= next_report:
                print(f"    ... {total / 1024 / 1024:,.0f} MB", file=sys.stderr)
                next_report += 50 * 1024 * 1024
    if expected is not None and int(expected) != total:
        part.unlink(missing_ok=True)
        raise DownloadError(f"크기 불일치: Content-Length={expected}, 수신={total}")
    if total == 0:
        part.unlink(missing_ok=True)
        raise DownloadError("빈 응답")
    part.replace(dest)
    return total, h.hexdigest()


def with_retry(fn, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except DownloadError:
            raise
        except Exception as e:  # 네트워크 오류 등은 재시도
            last = e
            wait = 5 * (i + 1)
            print(f"    재시도 {i + 1}/{attempts} ({e}); {wait}s 대기", file=sys.stderr)
            time.sleep(wait)
    raise DownloadError(f"{attempts}회 시도 실패: {last}")


# ---------------------------------------------------------------------------
# 출처별 다운로드
# ---------------------------------------------------------------------------
def download_datagokr(t: dict, dest: Path) -> dict:
    meta = json.loads(_text(
        "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
        {"publicDataPk": t["public_data_pk"], "publicDataDetailPk": t["detail_pk"],
         "atchFileId": "", "fileDetailSn": "1", "publicDataTyCode": "PR0051"},
    ))
    if not meta.get("status"):
        raise DownloadError(f"포털 다운로드 정보 조회 실패: {meta.get('error')}")
    info = meta.get("dataSetFileDetailInfo") or {}
    data_nm = info.get("dataNm") or ""
    if t["expect_name"] not in data_nm:
        raise DownloadError(f"예상과 다른 데이터명: {data_nm!r}")
    atch, sn = meta["atchFileId"], meta["fileDetailSn"]

    limit = json.loads(_text("https://www.data.go.kr/cmm/cmm/check-limit.json",
                             {"atchFileId": atch, "fileDetailSn": sn}))
    if limit.get("needCaptcha"):
        raise DownloadError("공공데이터포털이 캡차 인증을 요구함 → 브라우저 수동 다운로드 필요 "
                            "(docs/DATA_COLLECTION_GUIDE.md 참고)")

    url = ("https://www.data.go.kr/cmm/cmm/fileDownload.do?"
           + urllib.parse.urlencode({"atchFileId": atch, "fileDetailSn": sn, "dataNm": data_nm}))
    with _request(url, timeout=600) as r:
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise DownloadError(f"파일 대신 HTML 응답 (Content-Type={ctype})")
        original = decode_content_disposition(r.headers.get("Content-Disposition"))
        size, sha = stream_to_file(r, dest)
    return {"download_url": url, "request_params": json.dumps({"atchFileId": atch, "fileDetailSn": sn}),
            "original_filename": original, "bytes": size, "sha256": sha}


def download_seoul_file(t: dict, dest: Path) -> dict:
    page = _text(f"https://data.seoul.go.kr/dataList/{t['inf_id']}/S/1/datasetView.do?tab=F")
    files = re.findall(r"onclick=\"javascript:downloadFile\('(\d+)'\);\">([^<]+)<", page)
    hits = [(seq, name) for seq, name in files if name.strip().endswith(t["file_match"])]
    if len(hits) != 1:
        raise DownloadError(f"파일 목록에서 '{t['file_match']}'를 하나로 특정하지 못함: {files}")
    seq, listed_name = hits[0]
    m = re.search(r'name="infSeq" value="(\d+)"/>\s*</form>', page)
    inf_seq = m.group(1) if m else "3"
    url = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
    params = {"infId": t["inf_id"], "seqNo": "", "seq": seq, "infSeq": inf_seq}
    with _request(url, params, extra_headers={"Referer": "https://data.seoul.go.kr/"}) as r:
        original = decode_content_disposition(r.headers.get("Content-Disposition"))
        if not original or not original.endswith(t["file_match"]):
            raise DownloadError(f"응답 파일명이 예상과 다름: {original!r}")
        size, sha = stream_to_file(r, dest)
    return {"download_url": url, "request_params": json.dumps(params, ensure_ascii=False),
            "original_filename": original or listed_name, "bytes": size, "sha256": sha}


def download_seoul_sheet(t: dict, dest: Path) -> dict:
    col, value = t["sheet_filter"] if t.get("sheet_filter") else ("필터선택", "")
    url = "https://datafile.seoul.go.kr/bigfile/iot/sheet/csv/download.do"
    params = {"srvType": "S", "infId": t["inf_id"], "serviceKind": "1", "pageNo": "1",
              "gridTotalCnt": "", "ssUserId": "SAMPLE_VIEW", "strWhere": "",
              "strOrderby": t.get("order_by", ""), "filterCol": col, "txtFilter": value}
    with _request(url, params, extra_headers={"Referer": "https://data.seoul.go.kr/"}, timeout=900) as r:
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise DownloadError(f"CSV 대신 HTML 응답 (Content-Type={ctype})")
        original = decode_content_disposition(r.headers.get("Content-Disposition"))
        size, sha = stream_to_file(r, dest)
    return {"download_url": url, "request_params": json.dumps(params, ensure_ascii=False),
            "original_filename": original, "bytes": size, "sha256": sha}


METHODS = {"datagokr": download_datagokr, "seoul_file": download_seoul_file,
           "seoul_sheet": download_seoul_sheet}


# ---------------------------------------------------------------------------
# 압축 해제 (원본 ZIP 보존)
# ---------------------------------------------------------------------------
def member_name(info: zipfile.ZipInfo) -> str:
    """UTF-8 플래그가 없는 ZIP 항목명은 CP949로 다시 해석한다."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def extract_zip(zpath: Path, name_filter: tuple[str, ...] | None) -> list[str]:
    out_dir = zpath.parent / "extracted" / zpath.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = member_name(info)
            if name_filter and not any(s in name for s in name_filter):
                continue
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts:
                raise DownloadError(f"안전하지 않은 ZIP 경로: {name}")
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                while True:
                    buf = src.read(1024 * 1024)
                    if not buf:
                        break
                    dst.write(buf)
            written.append(str(target.relative_to(ROOT)))
    return written


# ---------------------------------------------------------------------------
def append_manifest(row: dict) -> None:
    META.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_target(t: dict, force: bool, extract: bool, reextract: bool = False,
               register: str | None = None) -> dict:
    dest = RAW / t["subdir"] / t["local_name"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    row = {"target_id": t["id"], "dataset_id": t["dataset_id"], "provider": t["provider"],
           "dataset_name": t["dataset_name"], "source_url": t["source_url"],
           "local_file_path": str(dest.relative_to(ROOT)), "reference_period": t["reference_period"]}
    if dest.exists() and not force:
        print(f"[skip] {t['id']} 이미 있음: {dest.relative_to(ROOT)}")
        if register is not None:  # 수동으로 받아 둔 파일을 다운로드 기록에 등록
            mtime = dt.datetime.fromtimestamp(dest.stat().st_mtime, KST).isoformat(timespec="seconds")
            row.update(download_url="manual", request_params="", original_filename=register or "수동 다운로드",
                       bytes=dest.stat().st_size, sha256=file_sha256(dest), collected_at=mtime,
                       status="collected", error="수동 다운로드 후 --register-existing 으로 등록")
            append_manifest(row)
            print(f"       다운로드 기록에 등록 (sha256={row['sha256'][:12]}...)")
        if (reextract or register is not None) and extract and dest.suffix.lower() == ".zip":
            files = extract_zip(dest, t.get("extract_filter"))
            print(f"       압축 해제 {len(files)}개 → {dest.parent.relative_to(ROOT)}/extracted/{dest.stem}/")
        return {**row, "status": row.get("status", "skipped_exists")}
    print(f"[get ] {t['id']} {t['dataset_name']}")
    collected_at = dt.datetime.now(KST).isoformat(timespec="seconds")
    try:
        result = with_retry(lambda: METHODS[t["method"]](t, dest))
        row.update(result, collected_at=collected_at, status="collected")
        print(f"       → {dest.relative_to(ROOT)} ({result['bytes']:,} B)")
        if extract and dest.suffix.lower() == ".zip":
            files = extract_zip(dest, t.get("extract_filter"))
            print(f"       압축 해제 {len(files)}개 → {dest.parent.relative_to(ROOT)}/extracted/{dest.stem}/")
            if not files:
                row["error"] = f"해제 대상 없음 (filter={t.get('extract_filter')!r})"
    except Exception as e:  # 실패는 기록하고 다음 대상으로 진행
        row.update(collected_at=collected_at, status="failed", error=str(e))
        print(f"[fail] {t['id']}: {e}", file=sys.stderr)
    append_manifest(row)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="받을 대상 ID (예: S01_20251231 S02 K01)")
    ap.add_argument("--force", action="store_true", help="이미 있는 파일도 다시 받기")
    ap.add_argument("--no-extract", action="store_true", help="ZIP 압축 해제 생략")
    ap.add_argument("--reextract", action="store_true", help="이미 받은 ZIP을 다운로드 없이 다시 압축 해제")
    ap.add_argument("--register-existing", nargs="?", const="", default=None, metavar="원본파일명",
                    help="브라우저로 수동 저장한 파일을 다운로드 기록에 등록 (--only 와 함께 사용)")
    ap.add_argument("--semas-extra", nargs="*", default=[],
                    help=f"추가로 받을 상가(상권)정보 기준일. 가능 값: {', '.join(SEMAS_STORE_RELEASES)}")
    args = ap.parse_args()

    targets = list(TARGETS)
    for d in args.semas_extra:
        if d not in SEMAS_STORE_RELEASES:
            ap.error(f"알 수 없는 기준일: {d}")
        targets.append(semas_store_target(d))
    if args.only:
        wanted = set(args.only)
        targets = [t for t in targets if t["id"] in wanted or t["dataset_id"] in wanted]

    if args.register_existing is not None and not args.only:
        ap.error("--register-existing 은 --only 로 대상을 지정해야 합니다")
    results = [run_target(t, args.force, not args.no_extract, args.reextract, args.register_existing)
               for t in targets]
    failed = [r for r in results if r["status"] == "failed"]
    print(f"\n완료: {sum(r['status'] == 'collected' for r in results)}건 수집·등록, "
          f"{sum(r['status'] == 'skipped_exists' for r in results)}건 건너뜀, {len(failed)}건 실패")
    for r in failed:
        print(f"  실패 {r['target_id']}: {r['error']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
