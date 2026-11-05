# 전체 최종 가공본 받기

2026-11-05 공유. 2026-11-02에 계산한 2025년 STEP 2·3 v0.1 결과입니다. 이번 공유는 기존 결과를 포장한 것으로, 분석 수치나 계산 기준을 변경하지 않았습니다.

**[전체 가공본 ZIP 다운로드](https://github.com/project2-team01/Spotfit/raw/refs/heads/main/%EB%B0%95%EC%84%B1%EC%9D%80/data/park_step23_2025_v0.1.zip)**

ZIP을 내려받아 Windows의 **모두 압축 풀기**를 누르세요. `processed/`의 CSV를 Excel에서 열면 됩니다. 원본 다운로드, Python 설치, 분석 코드 실행은 필요하지 않습니다. Excel에서 코드형 열을 정확히 유지하려면 **데이터 → 텍스트/CSV에서** 가져온 뒤 `quarter_code`, `market_code`, `industry_code` 등 `*_code` 열을 텍스트로 지정하세요.

## 포함한 최종 분석표

| 파일 | 행 수 | 용도 |
| --- | ---: | --- |
| `market_industry_features_2025.csv` / `.parquet` | 304,775 | 2025년 전체 4분기 상권×업종 패널, 84개 열 |
| `market_industry_features_2025q4.csv` | 75,985 | 같은 패널의 4분기 부분집합 |
| `market_quarter_context_2025.csv` / `.parquet` | 6,600 | 상권×분기 인구·시설·지역 특성 |
| `annual_industry_variability_2025.csv` / `.parquet` | 77,694 | 상권×업종의 관측 분기 수와 연간 변동 지표 |
| `semas_native_industry_2025q4.csv` / `.parquet` | 109,786 | 소진공 원래 업종, 최소면적 대표 배정 집계 |
| `semas_all_memberships_industry_2025q4.csv` / `.parquet` | 110,570 | 상권 경계 안 모든 소속 집계, 중첩 중복 포함 |

작은 예시 `feature_examples_2025q4.csv`도 포함했습니다. CSV와 Parquet는 같은 표의 대체 형식이며 서로 더하지 않습니다. 기존 CSV의 소수값은 원래 내보내기 규칙인 유효숫자 10자리입니다. 새 전체 연도 CSV와 Parquet는 저장된 수치 정밀도를 유지합니다. CSV의 빈칸은 결측으로, 숫자 0과 구분합니다. 모든 인구·시설 값은 업종 행에 반복되므로 지역 총량을 볼 때에는 맥락 표를 사용하세요.

`metadata/`에는 변수 정의, 전체 열 사전, 입력 파일 해시, 실행 요약, 검토 기록, 잠정 업종 대응표가 들어 있습니다. 소진공→서울 업종 대응은 공식 동등 분류로 확정되지 않았습니다. 공간 대표 배정과 모든 소속 집계는 목적이 다르며, 모든 소속 결과를 상권 간 합산하면 중복될 수 있습니다.

## Python에서 읽기

압축을 푼 폴더에서 실행합니다. 분석을 다시 계산하지 않고 이미 계산된 결과를 읽습니다.

```python
import pandas as pd
panel = pd.read_parquet('processed/market_industry_features_2025.parquet')
context = pd.read_parquet('processed/market_quarter_context_2025.parquet')
```

## 파일 확인

[MANIFEST.csv](MANIFEST.csv)는 파일별 행 수·열 수·크기·SHA-256, [MANIFEST.json](MANIFEST.json)은 열 목록·키·분석 코드 기준 커밋도 기록합니다. ZIP 내부에도 동일한 목록이 있습니다. [checksums.sha256](checksums.sha256)은 ZIP 자체의 검증값입니다.

저장소 최상위에서 `python 박성은/verify_shared_results.py`를 실행하면 추가 패키지나 원본 없이 ZIP 해시, 내부 데이터 파일 해시, CSV 행·열 수와 키 중복을 확인합니다. CSV는 대응 Parquet 및 4분기 부분집합과 값을 대조한 뒤 공유했습니다. 이는 파일 공유·보존 검증이며 추천 성능 검증을 뜻하지 않습니다.

공유 범위는 위 최종 결과 전체입니다. 원본과 중간 처리 파일은 포함하지 않습니다. 원본부터 다시 계산하려면 [저장소의 재실행 안내](https://github.com/project2-team01/Spotfit/tree/main/%EB%B0%95%EC%84%B1%EC%9D%80#다시-실행하기)를 사용하세요. 재계산 후 공유 ZIP을 갱신하려면 저장소 최상위에서 `python 박성은/package_results.py --source-commit <분석코드가_있는_커밋>`을 실행하세요. 이 명령은 로컬 ZIP만 만들며 GitHub 업로드는 별도입니다.
