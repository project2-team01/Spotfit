# STEP 5 금융 MBTI 기반 개인화 설계 (2025년)

예비 창업자의 금융 MBTI 세 글자 중 앞의 두 글자(L/V · E/P)는 **같은 글자의 상권과 맞추고**, 마지막 글자(S/G)는 **STEP 4 업종 내 비교 점수의 가중치**로 씁니다.
설계 내용과 근거, 한계, 팀이 정할 것은 [STEP5_금융MBTI_설계.md](STEP5_금융MBTI_설계.md)에 있습니다.

- 상권의 S/G는 판정하지 않습니다. **2025년 자료만 있어 성장성은 산출하지 않습니다.**
- 소비 잠재력은 계산 방식이 확정되지 않아 만들지 않았습니다.
- **예산 적합성은 판단하지 않습니다** (보증금 · 월세 자료가 없습니다).
- 유형이 맞는 상권은 "상권을 고르는 조건"일 뿐이며, 창업 결과를 예측하지 않습니다.

## 실행 (팀 저장소 루트에서, uv만 있으면 됩니다)

STEP 4 대시보드와 같은 uv 환경을 씁니다.

```bash
uv run --project "김지영/step4_dashboard" python "김지영/step5_design/build_types.py"     # 1) 상권 유형 만들기 (몇 초)
uv run --project "김지영/step4_dashboard" marimo run "김지영/step4_dashboard/app.py"      # 2) 대시보드 (탭 1이 금융 MBTI 검사)
uv run --project "김지영/step4_dashboard" python "김지영/step5_design/test_step5.py"      # 3) 검증 13개 (약 4~5분, --skip-app 이면 30초)
```

## 입력 (읽기만 함)

- `김지영/step2_3/data/`의 STEP 2·3 산출물 3개 (분기 패널, 상권×분기 인구, 상권 기본 정보)
- `seoul-commercial-analysis/data/raw/금융_MBTI.md` (팀 유형표). 이 폴더는 Git에서 빠져 있어 문항 · 유형을 `build_types.py`와 `data/검사_문항.csv` · `data/유형표.csv`에 옮겨 적었습니다.
  원문이 있으면 실행할 때 글자까지 같은지 확인하고, 다르면 멈춥니다.

## 파일

| 파일 | 하는 일 |
|:---|:---|
| `STEP5_금융MBTI_설계.md` | 설계안 (팀 공유용) |
| `build_types.py` | 상권 L/V · E/P 유형을 정한다. 몇 번 실행해도 바이트까지 같은 결과 |
| `test_step5.py` | 검증 13개 |
| `data/상권_유형_2025.parquet` · `.csv` | 상권 1,644곳의 L/V · E/P 점수와 글자, 판정 불가 이유 |
| `data/검사_문항.csv` · `data/유형표.csv` | 문항 15개(화면 순서 포함) · 유형 8개 |
| `data/유형별_가중치.csv` | S/G → 영역 가중치 [가정] |
| `data/STEP5_설계표.csv` | 2026-11-14 승인한 설계표 |
| `data/stage5_meta.json` | 규칙, 개수, 중앙값, 단단함 확인, 입력 sha256 |

대시보드 쪽 코드(검사 채점 · 유형 맞추기 `mbti.py`, 화면 `app.py` · `views.py`)는 `김지영/step4_dashboard/`에 있습니다.
