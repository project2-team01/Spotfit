# 서울시 창업 상권 분석 · STEP 1 Raw Data 패키지

금융 성향(금융 MBTI), 창업 예산, 위험 감수 성향을 상권 분석과 결합해 창업 상권을 추천하는 팀 프로젝트의 **데이터 수집 단계** 결과물입니다.

이 저장소에는 분석 결과가 없습니다. 팀원이 바로 STEP 2(전처리·결합·EDA)를 시작할 수 있도록 **공식 원본 데이터와 그 설명서**만 담았습니다.

## 수집 범위

- 지역: 서울특별시
- 기간: **2025년** (팀 결정, 2026-10-29)
- 출처: 공공데이터포털(소상공인시장진흥공단), 서울 열린데이터광장(서울시 상권분석서비스)

| ID | 데이터 | 저장 파일 |
|---|---|---|
| S01 | 소상공인 상가(상권)정보, 2025-12-31 기준 | `data/raw/semas/semas_store_20251231.zip` (서울 CSV는 `extracted/`) |
| S02 | 소상공인 상가(상권)정보 업종코드표 | `data/raw/semas/semas_industry_code_20230228.csv` |
| K01 | 서울 상권분석서비스 추정매출-상권 2025 | `data/raw/seoul/seoul_sales_trdar_2025.zip` |
| K02 | 서울 상권분석서비스 점포-상권 2025 | `data/raw/seoul/seoul_store_trdar_2025.zip` |
| K03 | 서울 상권분석서비스 영역-상권 (SHP) | `data/raw/seoul/seoul_area_trdar.zip` |
| K04 | 서울 상권분석서비스 길단위인구-상권 2025 | `data/raw/seoul/seoul_flpop_trdar_2025_sheet.csv` |
| K05 | 서울 상권분석서비스 집객시설-상권 | `data/raw/seoul/seoul_facility_trdar_all_sheet.csv` |
| K06 | 서울 상권분석서비스 직장인구-상권 | `data/raw/seoul/seoul_wrcpop_trdar_all_sheet.csv` |
| K07 | 서울 상권분석서비스 상주인구-상권 | `data/raw/seoul/seoul_repop_trdar_all_sheet.csv` |

K05~K07은 포털이 기간 필터를 제공하지 않아 전체 제공 기간 파일을 원본 그대로 보존했습니다. 2025년 행만 쓰려면 STEP 2에서 `기준_년분기_코드`가 `2025`로 시작하는 행을 고르면 됩니다.

## 폴더 구조

```
seoul-commercial-analysis/
├── data/
│   ├── raw/                    # 원본. 절대 수정 금지. Git 제외
│   │   ├── semas/              #   소상공인시장진흥공단
│   │   │   └── extracted/      #   ZIP 압축 해제본 (서울 CSV + 안내문)
│   │   └── seoul/              #   서울 열린데이터광장
│   │       └── extracted/
│   └── metadata/
│       ├── data_catalog.csv        # 파일 목록·출처·해시·행/열 수
│       ├── data_dictionary.csv     # 컬럼 정의서
│       ├── quality_report.csv      # 품질 점검 결과
│       ├── join_key_check.csv      # 결합 키 후보 검증 결과
│       ├── download_manifest.csv   # 다운로드 기록 (URL, 요청값, 수집 시각)
│       └── checksums.sha256        # 무결성 확인용 해시
├── scripts/
│   ├── download_data.py        # 공식 출처에서 원본 다운로드
│   └── inspect_raw_data.py     # 원본을 읽기만 하며 구조·품질 점검
├── docs/
│   ├── ANALYSIS_PLAN.md        # 전체 분석 계획서 (초안, 수정 가능)
│   ├── DATA_SOURCES.md         # 출처 조사 결과
│   ├── DATA_COLLECTION_GUIDE.md# 재수집·수동 다운로드 절차
│   ├── DATA_HANDOFF.md         # 팀원 인수인계 문서 (먼저 읽기)
│   └── source_probe_20261029.json
├── requirements.txt
└── README.md
```

## 빠른 시작

```bash
pip install -r requirements.txt

# 1) 원본 받기 (공유 드라이브에서 data/raw/ 를 받았다면 생략)
python3 scripts/download_data.py

# 2) 무결성 확인 (공유 드라이브본과 같은 파일인지)
shasum -a 256 -c data/metadata/checksums.sha256

# 3) 구조·품질 점검 다시 실행 (메타데이터 CSV 재생성)
python3 scripts/inspect_raw_data.py --verify-api
```

인증키는 필요 없습니다. 자세한 절차와 실패 시 대처는 [docs/DATA_COLLECTION_GUIDE.md](docs/DATA_COLLECTION_GUIDE.md)에 있습니다.

## 데이터 관리 원칙

1. `data/raw/`의 파일은 수정·삭제하지 않습니다. 가공 결과는 `data/interim/`, `data/processed/`에 따로 둡니다.
2. 원본 CSV 인코딩을 바꿔 저장하지 않습니다. 읽을 때 인코딩을 지정합니다.
3. 모든 파일은 `data_catalog.csv`에서 출처 URL, 수집 시각, SHA-256으로 추적할 수 있습니다.
4. API 키·비밀정보는 `.env`에 두고 커밋하지 않습니다. 현재 수집 경로는 키가 필요 없습니다.
5. 대용량 원본은 Git이 아닌 팀 공유 드라이브로 공유합니다.

팀원은 [docs/DATA_HANDOFF.md](docs/DATA_HANDOFF.md)부터 읽어 주세요. 전체 분석 단계와 결정이 필요한 사항은 [docs/ANALYSIS_PLAN.md](docs/ANALYSIS_PLAN.md)에 있습니다.
