# 이승희 · 서울 상권 STEP 1~4 결과물

2025년 서울 상권 자료로 만든 STEP 1(기본 EDA), 2(전처리·결합), 3(파생변수 특성표), 4(상권 비교 점수 대시보드) 결과물입니다.

## 바로 보기 (설치 필요 없음)

| 단계 | 보고서 | 대시보드 (브라우저로 열기) |
| :--- | :--- | :--- |
| STEP 1 기본 EDA | [01_기본EDA_보고서](report/01_기본EDA_보고서_2025Q4.md) | [01_기본EDA_대시보드](report/01_기본EDA_대시보드_2025Q4.html) |
| STEP 2 전처리·결합 | [02_전처리_결합설계_보고서](report/02_전처리_결합설계_보고서_2025Q4.md) | [02_결합검증_대시보드](report/02_결합검증_대시보드_2025Q4.html) |
| STEP 3 파생변수 | [03_파생변수_설계보고서](report/03_파생변수_설계보고서_2025Q4.md), [03_팀논의자료](report/03_팀논의자료_2025Q4.md) | [03_상권특성_대시보드](report/03_상권특성_대시보드_2025Q4.html) |
| STEP 4 비교 점수 | [step4_dashboard/README](step4_dashboard/README.md) | [04_상권비교점수_대시보드](step4_dashboard/report/04_상권비교점수_대시보드_2025.html) (정적 스냅숏) |

가공 결과 표는 `data/processed/`에 있습니다. 바로 열어서 분석에 쓸 수 있습니다.

- `stage2/`: 2단계 마트
- `stage3/`: 3단계 특성표 4종과 변수사전

## STEP 4 대시보드 실행 (원본 데이터 필요 없음)

STEP 4는 팀 저장소에 올라 있는 김지영 `step2_3`·`claude_dashboard` 데이터만 읽습니다. [uv](https://docs.astral.sh/uv/)만 있으면 팀 저장소 루트에서 바로 실행됩니다.

```bash
uv run --project "이승희/step4_dashboard" marimo run "이승희/step4_dashboard/app.py"
```

자세한 내용은 [step4_dashboard/README.md](step4_dashboard/README.md)에 있습니다.

## STEP 1~3을 처음부터 다시 만들기 (원본 데이터 필요)

STEP 1~3 코드는 `이승희/data/raw/`의 원본 파일을 읽습니다. 원본은 크기가 크고(약 450MB, 소상공인 상가정보 한 파일만 291MB) 팀 규칙상 Git에 올리지 않습니다. 그래서 **원본을 따로 받아 넣어야 실행됩니다.**

### 1) 원본 받기 (둘 중 하나)

- **방법 A, 같은 파일 받기 (추천):**
  1. 원본 압축 파일 `SpotFit_raw_2025.zip`을 팀 공유 드라이브에서 받거나 이승희에게 요청합니다.
  2. `이승희/` 폴더 안에서 압축을 풉니다. 그러면 `이승희/data/raw/`가 생깁니다.
  3. 같은 파일이라 결과도 똑같이 나옵니다.
- **방법 B, 공식 출처에서 직접 받기:** 표준 라이브러리만 써서 윈도우·맥에서 모두 됩니다.

  ```bash
  uv run --project 이승희 python 이승희/src/fetch_raw_2025.py
  ```

  - 서울시 빅데이터캠퍼스 재현데이터는 수동으로 받아야 합니다.
  - 네이버 트렌드는 API 키(`config/naver_api_key.json`, 커밋 금지)가 있을 때만 받습니다.
  - 공식 출처가 그사이 갱신됐으면 숫자가 조금 달라질 수 있습니다.
  - 출처와 파일 목록은 [data/RAW_DATA_SOURCES.md](data/RAW_DATA_SOURCES.md)에 있습니다.

`data/raw/`는 [.gitignore](.gitignore)에 등록되어 있어 실수로 커밋되지 않습니다.

### 2) 다시 만들기 (팀 저장소 루트에서)

```bash
uv run --project 이승희 python 이승희/scripts/build_processed_2025.py         # 공용 중간 표 4개 (data/processed/*.csv)
uv run --project 이승희 python 이승희/src/build_stage2_mart.py                # 2단계 마트
uv run --project 이승희 python 이승희/src/run_stage3_pipeline.py --quick      # 3단계 생성 → 보고서·대시보드 → 검증 (약 1분)
uv run --project 이승희 python 이승희/src/run_stage3_pipeline.py              # 3단계 전체 검증 (약 15분)
```

- **중간 표 4개는 이미 올라 있습니다.** `상권_업종_분기.csv`, `행정동_마스터.csv`, `행정동_분기.csv`, `업종_공통그룹.csv`입니다. 그래서 2단계부터 다시 돌려도 됩니다. 각 표의 규칙은 [data/PREPROCESSING.md](data/PREPROCESSING.md)에 있습니다.
- **3단계 자동 실행기의 동작:**
  - 임시 폴더에서 생성과 검증을 모두 마친 뒤, 통과했을 때만 바뀐 결과물을 반영합니다.
  - 원본(`data/raw`), 2단계 마트, `PREPROCESSING.md`가 실행 중에 바뀌지 않았는지도 확인합니다.
- **확인 결과 (2026-11-05):** 원본을 받은 상태에서 위 명령을 실행해 봤습니다. 중간 표 4개, 2단계 마트 14개, 3단계 결과물 18개가 올라가 있는 파일과 바이트 단위로 같았습니다.

## 폴더 구조

```text
이승희/
├── README.md, .gitignore, pyproject.toml, uv.lock   # STEP 1~3 실행 환경 (uv)
├── data/
│   ├── PREPROCESSING.md, RAW_DATA_SOURCES.md        # 전처리 규칙, 원본 출처
│   ├── raw/                                         # 원본 (Git 제외, 따로 받기)
│   └── processed/                                   # 중간 표 4개, eda_stage1/, stage2/, stage3/
├── scripts/build_processed_2025.py                  # 중간 표 4개 생성 (PREPROCESSING.md의 링크 위치 그대로)
├── src/                                             # STEP 1~3 생성·검증 코드, 원본 수집 코드
├── report/                                          # STEP 1~3 보고서·대시보드
├── images/                                          # STEP 1~3 그림
└── step4_dashboard/                                 # STEP 4 점수표·marimo 대시보드 (따로 실행 환경)
```

출처: 서울특별시 상권분석서비스·서울 열린데이터광장, 소상공인시장진흥공단 상가(상권)정보, 국민연금공단 등. 자세한 출처는 [data/RAW_DATA_SOURCES.md](data/RAW_DATA_SOURCES.md)에 있습니다.
