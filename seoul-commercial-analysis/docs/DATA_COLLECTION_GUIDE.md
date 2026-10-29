# 데이터 수집 가이드

원본 데이터를 다시 받거나, 자동 다운로드가 실패했을 때 수동으로 받는 절차입니다.

- 기준일: 2026-10-29
- 수집 범위: 2025년 (팀 결정)
- 인증키: 필요 없음

---

## 1. 자동 수집

```bash
cd seoul-commercial-analysis
pip install -r requirements.txt

python3 scripts/download_data.py                  # 기본 대상 9건 전체
python3 scripts/inspect_raw_data.py --verify-api  # 메타데이터 CSV 재생성
shasum -a 256 -c data/metadata/checksums.sha256   # 무결성 확인
```

자주 쓰는 옵션:

| 옵션 | 용도 |
|---|---|
| `--only K01 K02` | 일부 대상만 받기. 대상 ID는 아래 표 참고 |
| `--semas-extra 20250331 20250630 20251030` | 2025년 다른 분기 상가정보 스냅숏 추가 |
| `--reextract` | 이미 받은 ZIP을 다운로드 없이 다시 압축 해제 |
| `--register-existing` | 브라우저로 직접 받은 파일을 다운로드 기록에 등록 |
| `--force` | 이미 있는 파일을 다시 받아 덮어쓰기. 공유본에는 쓰지 마세요 |

- 이미 있는 파일은 건너뜁니다. 원본을 실수로 덮어쓰지 않기 위해서입니다.
- 결과는 `data/metadata/download_manifest.csv`에 한 줄씩 쌓입니다. URL, 요청값, 수집 시각, 바이트 수, SHA-256이 들어갑니다.
- `inspect_raw_data.py`는 이 기록을 기준으로 파일을 찾습니다. 기록에 없는 파일은 점검하지 않습니다.

## 2. 대상과 수집 경로

| 대상 ID | 저장 파일 | 수집 경로 |
|---|---|---|
| S01_20251231 | `data/raw/semas/semas_store_20251231.zip` | 공공데이터포털 파일 다운로드 |
| S02 | `data/raw/semas/semas_industry_code_20230228.csv` | 공공데이터포털 파일 다운로드 |
| K01 | `data/raw/seoul/seoul_sales_trdar_2025.zip` | 서울 열린데이터광장 파일 탭 |
| K02 | `data/raw/seoul/seoul_store_trdar_2025.zip` | 서울 열린데이터광장 파일 탭 |
| K03 | `data/raw/seoul/seoul_area_trdar.zip` | 서울 열린데이터광장 파일 탭 |
| K04 | `data/raw/seoul/seoul_flpop_trdar_2025_sheet.csv` | 서울 시트 CSV, `기준_년분기_코드` 필터 `2025` |
| K05 | `data/raw/seoul/seoul_facility_trdar_all_sheet.csv` | 서울 시트 CSV, 필터 없음 |
| K06 | `data/raw/seoul/seoul_wrcpop_trdar_all_sheet.csv` | 서울 시트 CSV, 필터 없음 |
| K07 | `data/raw/seoul/seoul_repop_trdar_all_sheet.csv` | 서울 시트 CSV, 필터 없음 |

- 서울 파일 탭은 화면의 파일 목록에서 파일명으로 항목을 찾습니다. 포털이 목록 순서를 바꿔도 같은 파일을 받습니다.
- K04 필터는 앞부분 일치로 동작합니다. `2025`를 넣으면 20251~20254가 나오는 것을 확인했습니다.
- K05~K07 시트 화면에는 필터가 없습니다. 그래서 전체 제공 기간이 한 파일로 받아집니다.
- 압축 해제 규칙
  - S01: 전국 ZIP에서 서울 CSV와 `[필독]파일열람방법.txt`만 `extracted/semas_store_20251231/`에 풉니다.
  - K01~K03: 전체를 `extracted/{파일명}/`에 풉니다.

## 3. 수동 다운로드 절차

자동 다운로드가 실패하면 아래 순서로 받습니다. 저장한 뒤 `--register-existing`으로 기록을 남깁니다.

### S01 상가(상권)정보 2025-12-31

1. https://www.data.go.kr/data/15083033/fileData.do 에 접속합니다.
2. 페이지 안 "주기성 과거 데이터" 목록에서 `소상공인시장진흥공단_상가(상권)정보_20251231`을 누릅니다.
3. 열린 창에서 다운로드를 누릅니다. 로그인은 필요 없습니다.
4. 받은 파일을 `data/raw/semas/semas_store_20251231.zip`으로 저장합니다. 파일 안은 열거나 고치지 않습니다.
5. 기록 등록과 압축 해제를 합니다.

```bash
python3 scripts/download_data.py --only S01_20251231 \
  --register-existing "소상공인시장진흥공단_상가(상권)정보_20251231.zip"
```

### S02 업종코드

1. https://www.data.go.kr/data/15067631/fileData.do 에서 다운로드를 누릅니다.
2. `data/raw/semas/semas_industry_code_20230228.csv`로 저장합니다.
3. `python3 scripts/download_data.py --only S02 --register-existing "<브라우저가 저장한 원본 파일명>"`

### K01·K02·K03 서울 파일

1. 아래 페이지의 "파일내려받기" 목록에서 파일명을 눌러 받습니다.
   - K01: https://data.seoul.go.kr/dataList/OA-15572/S/1/datasetView.do → `서울시 상권분석서비스(추정매출-상권)_2025년.zip`
   - K02: https://data.seoul.go.kr/dataList/OA-15577/S/1/datasetView.do → `서울시 상권분석서비스(점포-상권)_2025년.zip`
   - K03: https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do → `서울시 상권분석서비스(영역-상권).zip`
2. 2장 표의 저장 파일명으로 저장합니다.
3. `python3 scripts/download_data.py --only K01 --register-existing "<원본 파일명>"` 처럼 등록합니다.

### K04~K07 서울 시트 CSV

1. 데이터셋 페이지의 미리보기에서 "Sheet" 탭을 엽니다.
   - K04: https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do
   - K05: https://data.seoul.go.kr/dataList/OA-15580/S/1/datasetView.do
   - K06: https://data.seoul.go.kr/dataList/OA-15569/S/1/datasetView.do
   - K07: https://data.seoul.go.kr/dataList/OA-15584/S/1/datasetView.do
2. K04만 필드명 `기준_년분기_코드`, 검색명 `2025`를 넣습니다. K05~K07은 조건 없이 둡니다.
3. "내려받기(CSV)"를 누릅니다. 파일은 CP949 인코딩입니다. 엑셀로 열었다가 저장하지 마세요.
4. 2장 표의 저장 파일명으로 저장하고 `--register-existing`으로 등록합니다.

## 4. 실패 원인별 대처

| 증상 | 원인 | 대처 |
|---|---|---|
| "캡차 인증을 요구함" | 공공데이터포털 다운로드 횟수 제한 | 브라우저에서 캡차를 풀고 수동 다운로드 |
| "예상과 다른 데이터명" | 포털이 릴리스 ID를 바꿈 | `download_data.py`의 `SEMAS_STORE_RELEASES`를 포털 목록과 대조해 갱신 |
| "파일 목록에서 … 특정하지 못함" | 서울 포털이 파일명을 바꿈 | 페이지에서 새 파일명을 확인하고 `file_match`를 갱신 |
| "크기 불일치" | 전송 중단 | 다시 실행. `.part` 파일은 자동 삭제됨 |
| HTML 응답 | 포털 점검·주소 변경 | 수동 다운로드 |

## 5. 다시 받을 때 주의

- 공식 서버 파일은 예고 없이 갱신될 수 있습니다. 다시 받은 파일의 해시가 `checksums.sha256`과 다르면 내용이 바뀐 것입니다.
- 팀 분석 기준본은 공유 드라이브에 올린 파일입니다. 새 버전을 받을 때는 기존 파일을 덮어쓰지 말고 다른 폴더에 받아 비교하세요.
- 공공데이터포털 상가(상권)정보의 다음 릴리스는 2026-10-31 등록 예정입니다. 이번 수집 범위인 2025년 자료에는 영향이 없습니다.
- 서울 Open API(`openapi.seoul.go.kr`)는 인증키가 필요하고 1회 1,000행 제한이 있습니다. 이번 수집에는 쓰지 않았습니다. 키를 쓰게 되면 `.env`에 넣고 Git에 올리지 마세요.
