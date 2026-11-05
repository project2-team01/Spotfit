# 박성은 · 서울 상권 STEP 2/STEP 3 결과

작성일: 2026-11-02. 분석 기간: 2025년 Q1~Q4. 실제 데이터 인수인계 문서와 지정된 9종만 사용했습니다.

**v0.1 · 팀 검토용 1차 분석본**입니다. 계산 검증과 분석 가정의 확정은 구분합니다. 업종 대응·공간 중첩 배정·매출 비관측 처리의 검토사항은 [REVIEW_NOTES.md](REVIEW_NOTES.md)에 정리했습니다.

## 먼저 읽을 문서

처음 보는 팀원은 [분석 내용의 쉬운 설명과 재검토 결과](분석내용_쉬운설명과_검토결과.md)부터 읽으세요. 무엇을 분석했는지, 어떤 계산을 확인했는지, 결과를 어디까지 해석할 수 있는지 정리했습니다.

1. [STEP 2 전처리·결합 결과](STEP2_전처리_결합_결과.md)
2. [STEP 3 파생변수 정의·결과](STEP3_파생변수_정의_결과.md)
3. [핵심 결과와 팀 검토사항](팀공유_핵심결과.md)

## 완료한 작업

- 분기×상권×서울 서비스업종 패널 304,775행. 점포 원본의 모든 키와 매출 원본 85,732행을 보존했습니다.
- 상권×분기 맥락 테이블 6,600행. 인구·시설은 이 테이블에서 집계하세요.
- 32개 파생지표 정의 및 계산. 원본과 가공본을 분리했습니다.
- 소진공 534,978개 점포 공간 결합. 후보 중첩과 상권 밖 점포를 별도로 보존했습니다.
- 원본 18개 파일 해시 실행 전후 동일. 필수 검증 193개 통과, 실패 0개.

## 결과 파일

**2026-11-05: [전체 최종 가공본 ZIP 다운로드](https://github.com/project2-team01/Spotfit/raw/refs/heads/main/%EB%B0%95%EC%84%B1%EC%9D%80/data/park_step23_2025_v0.1.zip)** · [파일별 행 수·검증값](data/MANIFEST.csv) · [열기 및 사용 안내](data/README.md)

전체 가공 데이터 6종을 CSV·Parquet로 공유했습니다. ZIP을 풀면 원본 다운로드나 분석 재실행 없이 전체 결과표를 열 수 있습니다. 특히 전체 2025년 패널 304,775행의 CSV도 추가했습니다. Python 재계산 결과는 기존처럼 `seoul-commercial-analysis/data/processed/park_step23/`에 생성됩니다. [작은 예시 CSV](samples/feature_examples_2025q4.csv)와 [요약 Excel](summary/STEP2_STEP3_결과요약.xlsx)도 볼 수 있습니다.

| 파일 | 내용 |
| --- | --- |
| `market_industry_features_2025.parquet` | 전체 분기×상권×업종 패널 및 지표 |
| `market_industry_features_2025q4.csv` | 4분기 75,985행. Excel에서 확인하기 쉬운 UTF-8 BOM CSV |
| `market_quarter_context_2025.csv` | 상권×분기 인구·시설·상권 특성 |
| `semas_native_industry_2025q4.csv` | 원래 소진공 247개 업종 체계, 최소면적 대표 배정 기준 |
| `semas_all_memberships_industry_2025q4.csv` | 각 상권 내부의 모든 점포. 중첩 상권 간 중복 포함 |
| `annual_industry_variability_2025.csv` | 연간 관측 분기 수·4분기 변동계수 |
| [feature_dictionary.csv](reports/feature_dictionary.csv) | 파생변수 정의·공식·원본·단위·해석 |
| [output_column_dictionary.csv](reports/output_column_dictionary.csv) | 최종 테이블 전체 컬럼·자료형·결측 수 |
| [industry_crosswalk.csv](config/industry_crosswalk.csv) | 소진공→서울 업종 잠정 대응표. 공식 연계표 아님 |
| [STEP2_STEP3_결과요약.xlsx](summary/STEP2_STEP3_결과요약.xlsx) | 요약·지표 정의·수식 계산 예시 |

## 다시 실행하기

저장소 최상위 `Spotfit` 폴더에서 실행합니다. 원본 데이터가 없다면 아래 수집 절차를 먼저 실행하세요. 이미 있으면 재사용합니다.

```powershell
python -m pip install -r 박성은/requirements.txt
# 원본이 없는 팀원만 실행합니다.
python seoul-commercial-analysis/scripts/download_data.py
python 박성은/build_step23.py
python 박성은/verify_step23.py
python 박성은/write_reports.py
```

`build_step23.py`는 원본을 수정하지 않습니다. 같은 실행 경로의 가공본·감사표만 갱신합니다. 원본 해시가 인수인계와 다르면 분석을 중단합니다. 현재 `config/industry_crosswalk.csv`를 다시 읽으므로 팀이 수정한 대응표를 반영할 수 있습니다. 새 외부 다운로드/API 호출은 하지 않습니다.

공유한 요약 Excel은 이 1차 분석 시점의 결과입니다. 위 Python 재실행은 분석 데이터·보고서·검증 기록을 재생성하며 Excel을 자동 갱신하지 않습니다.

```python
import pandas as pd
panel = pd.read_parquet('seoul-commercial-analysis/data/processed/park_step23/market_industry_features_2025.parquet')
coffee_q4 = panel[(panel['quarter_code'] == '20254') & (panel['industry_code'] == 'CS100010')]
observed = coffee_q4[coffee_q4['sales_observed'] & (coffee_q4['total_store_count'] > 0)]
```

CSV를 읽을 때 `quarter_code`, `market_code`, `industry_code`는 문자열로 지정하세요. Parquet에서는 문자열 자료형이 보존됩니다.

## 해석 범위

지표가 높다고 창업 성공이나 수익을 보장하지 않습니다. 점수화·MBTI 가중치·추천순위는 이번 STEP 2/3에 포함하지 않았습니다. 원자료에 없는 임대료·이익률·전년 성장률도 만들지 않았습니다.

원본·중간 처리 파일은 Git 제외 대상으로 유지합니다. 최종 가공본은 `박성은/data/`의 ZIP과 파일 목록으로 공유합니다. 공유 파일 보존 확인은 `python 박성은/verify_shared_results.py`로 실행할 수 있으며 추가 패키지나 원본은 필요하지 않습니다. 원본 폴더와 인수인계 메타데이터는 이번 작업에서 수정하지 않았습니다.

저장된 결과를 원본과 다시 대조한 독립 검증: 52개 통과, 0개 실패. 모든 매출·점포 값 일치, 정확한 직전분기 조인, 분모 0·결측, 500개 공간 배정 샘플, 모든 공간 후보 및 집계 수 보존을 확인했습니다. [독립 검증 기록](reports/independent_validation.json).
