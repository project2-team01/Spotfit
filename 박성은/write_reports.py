"""build_step23.py의 실제 실행 결과로 한국어 인수인계 문서를 생성한다."""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'seoul-commercial-analysis'
if (ROOT / '.analysis_deps').exists():
    sys.path.insert(0, str(ROOT / '.analysis_deps'))
import pandas as pd

R = HERE / 'reports'
# 감사표에는 실행 PC의 절대 경로 대신 프로젝트 상대 경로만 남긴다.
audit_path = R / 'validation_checks.csv'
audit_text = audit_path.read_text(encoding='utf-8-sig')
audit_text = audit_text.replace(str(ROOT), 'seoul-commercial-analysis').replace(ROOT.as_posix(), 'seoul-commercial-analysis')
audit_path.write_text(audit_text, encoding='utf-8-sig')
S = json.loads((R / 'run_summary.json').read_text(encoding='utf-8'))
F = pd.read_csv(R / 'feature_dictionary.csv').fillna('')


def table(df):
    cols = df.columns.tolist()
    def val(x):
        return str(x).replace('|', '\\|').replace('\n', ' ')
    rows = ['| ' + ' | '.join(map(val, cols)) + ' |', '| ' + ' | '.join('---' for _ in cols) + ' |']
    rows.extend('| ' + ' | '.join(val(x) for x in row) + ' |' for row in df.itertuples(index=False, name=None))
    return '\n'.join(rows)


def write(name, text):
    if name == 'README.md' and (HERE / '분석내용_쉬운설명과_검토결과.md').exists():
        text = text.replace('## 먼저 읽을 문서\n', '## 먼저 읽을 문서\n\n처음 보는 팀원은 [분석 내용의 쉬운 설명과 재검토 결과](분석내용_쉬운설명과_검토결과.md)부터 읽으세요. 무엇을 분석했는지, 어떤 계산을 확인했는지, 결과를 어디까지 해석할 수 있는지 정리했습니다.\n', 1)
    (HERE / name).write_text(text.strip() + '\n', encoding='utf-8')


sp = S['spatial']
cov = pd.read_csv(R / 'join_coverage_by_quarter.csv')
rates = pd.read_csv(R / 'opening_closure_denominator_audit.csv')
labels = pd.read_csv(R / 'semas_codebook_label_differences.csv')
stability = pd.read_csv(R / 'population_facility_update_audit.csv')
geo = pd.read_csv(R / 'market_geometry_audit.csv')
q4 = pd.read_parquet(ROOT / 'data/processed/park_step23/market_industry_features_2025.parquet', filters=[('quarter_code', '=', '20254')])
ap = '../seoul-commercial-analysis/data/processed/park_step23/'

write('README.md', f'''
# 박성은 · 서울 상권 STEP 2/STEP 3 결과

작성일: 2026-11-02. 분석 기간: 2025년 Q1~Q4. 실제 데이터 인수인계 문서와 지정된 9종만 사용했습니다.

**v0.1 · 팀 검토용 1차 분석본**입니다. 계산 검증과 분석 가정의 확정은 구분합니다. 업종 대응·공간 중첩 배정·매출 비관측 처리의 검토사항은 [REVIEW_NOTES.md](REVIEW_NOTES.md)에 정리했습니다.

## 먼저 읽을 문서

1. [STEP 2 전처리·결합 결과](STEP2_전처리_결합_결과.md)
2. [STEP 3 파생변수 정의·결과](STEP3_파생변수_정의_결과.md)
3. [핵심 결과와 팀 검토사항](팀공유_핵심결과.md)

## 완료한 작업

- 분기×상권×서울 서비스업종 패널 {S['panel_rows']:,}행. 점포 원본의 모든 키와 매출 원본 {S['sales_rows']:,}행을 보존했습니다.
- 상권×분기 맥락 테이블 {S['context_rows']:,}행. 인구·시설은 이 테이블에서 집계하세요.
- {S['computed_feature_count']}개 파생지표 정의 및 계산. 원본과 가공본을 분리했습니다.
- 소진공 {sp['total_stores']:,}개 점포 공간 결합. 후보 중첩과 상권 밖 점포를 별도로 보존했습니다.
- 원본 18개 파일 해시 실행 전후 동일. 필수 검증 {S['validation_passed']}개 통과, 실패 {S['validation_failed']}개.

## 결과 파일

아래 전체 가공 데이터 6종은 Git에 포함하지 않았습니다. 재실행하면 `seoul-commercial-analysis/data/processed/park_step23/`에 생성됩니다. 바로 볼 수 있는 [작은 예시 CSV](samples/feature_examples_2025q4.csv)와 [요약 Excel](summary/STEP2_STEP3_결과요약.xlsx)은 이 폴더에 포함했습니다.

| 파일 | 내용 |
| --- | --- |
| `market_industry_features_2025.parquet` | 전체 분기×상권×업종 패널 및 지표 |
| `market_industry_features_2025q4.csv` | 4분기 {S['q4_rows']:,}행. Excel에서 확인하기 쉬운 UTF-8 BOM CSV |
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

대용량 원본과 가공본은 Git 제외 대상입니다. 코드·보고서·작은 정의표만 Git 공유 대상으로 두었습니다. 원본 폴더와 인수인계 메타데이터는 이번 작업에서 수정하지 않았습니다.
''')

write('STEP2_전처리_결합_결과.md', f'''
# STEP 2 · 2025년 전처리 및 결합 결과

기준: [DATA_HANDOFF.md](../seoul-commercial-analysis/docs/DATA_HANDOFF.md), [ANALYSIS_PLAN.md](../seoul-commercial-analysis/docs/ANALYSIS_PLAN.md). 실행 시각: {S['generated_at']}. 데이터 출처: 소상공인시장진흥공단, 서울특별시·서울시 상권분석서비스.

## 1. 결합 구조와 분석 단위

`K01 매출 ↔ K02 점포`를 `분기+상권코드+서비스업종코드`로 1:1 외부 결합했습니다. 양쪽 키의 합집합을 사용해 한쪽에만 있는 행을 버리지 않도록 했습니다. 실제 결과는 K02 {S['panel_rows']:,}행과 같고, 매출 {S['sales_rows']:,}행은 모두 포함됩니다.

`K03 상권영역×2025년 4개 분기`로 {S['context_rows']:,}행의 완전한 상권×분기 격자를 만들었습니다. K04~K07은 분기+상권으로 1:1 결합한 뒤, 업종 패널에는 m:1로 연결했습니다. 시설·인구·면적은 업종마다 반복되므로 업종 행을 합산하면 중복됩니다. 지역 수준 분석에는 별도 context 테이블을 사용합니다.

| 자료 | 기준 단위 | 연결 방식 |
| --- | --- | --- |
| K01 추정매출 | 분기×상권×업종 | K02와 키 합집합, 원본 매출 합·행 수 보존 |
| K02 점포 | 분기×상권×업종 | `전체점포=일반점포+프랜차이즈` 전 행 검증 |
| K03 영역 | 상권 1,650개 | 상권 차원표·5181 좌표계 면적 |
| K04~K07 | 분기×상권 | 존재 여부 플래그와 함께 m:1 연결 |
| S01 상가 | 2025-12-31 개별점포 | 좌표로 상권 공간 결합 후 2025Q4에만 연결 |
| S02 업종코드표 | 소진공 소분류 | S01 코드 247개 전부 확인 |

## 2. 전처리 규칙

1. S01 UTF-8, S02 및 서울 CSV CP949로 읽었습니다. 식별 코드는 문자열로 보존했습니다.
2. K05~K07의 2025년 외 행은 가공본에서만 제외했습니다. 분기는 `20251`~`20254`만 허용했습니다.
3. K01 시간대 건수 6개 컬럼의 깨진 이름은 순서와 종료시각을 확인해 `시간대_00~06_매출_건수` 등의 이름으로 수정했습니다. 실제 값은 변경하지 않았습니다.
4. K02 영문 헤더를 `total_store_count` 등으로 통일했습니다. `similr_induty_stor_co`가 전체점포 수입니다. `stor_co`는 일반점포 수입니다.
5. K05 하위 시설 칸의 공백 {S['facility_component_blanks_imputed']:,}개를 0으로 바꿨습니다. 근거는 인수인계 문서의 CSV/API 대조입니다. 이 가정은 **행이 존재하는 하위 시설 칸**에만 적용합니다. 원본에 행이 없는 상권·분기는 0으로 만들지 않았습니다.
6. K05 공시 `집객시설_수`와 하위 19개 시설 수 합은 2025년 {S['facility_total_mismatch_rows_2025']:,}행에서 다릅니다. `facility_count_source`와 `facility_components_sum`을 분리했습니다. 시설밀도는 정의가 명확한 하위 합을 사용하며 고유 시설수로 부르지 않습니다.
7. 원본에 없는 매출은 결측으로 유지했습니다. 비관측 {S['sales_unobserved_rows']:,}행 중 서울 매출 자료 미제공 업종에 속한 {S['sales_unsupported_industry_rows']:,}행과, 제공 업종이지만 해당 키의 매출 행이 없는 경우를 `sales_missing_reason`으로 구분합니다.
8. 이상치를 임의 삭제·상한 처리하지 않았습니다. 공식 비율 100 초과, 소수 점포 분모, 공간 중첩 등은 플래그와 감사표로 관리했습니다.

S01/S02 업종코드는 모두 일치하지만 이름 두 개에서 `;`/`,` 구두점 차이가 있었습니다. 코드로 연결하고 최신 S01 명칭을 유지했습니다.

{table(labels)}

## 3. 공간 결합과 좌표계 검증

K03 파일 CRS는 실제 EPSG:5181로 인식되었습니다. S01 점을 EPSG:4326에서 5181로 변환했습니다. 원본 도형 {S['invalid_geometries_before']}개가 유효하지 않아 가공 메모리의 도형에만 `make_valid()`를 적용했습니다. [도형 감사표](reports/market_geometry_audit.csv)에 원래 오류 설명, 보정 여부, 전후 면적 차이를 기록했습니다.

면적은 보정 후 폴리곤에서 m²로 계산했습니다. 원본 `RELM_AR / 계산면적` 비의 중앙값은 {S['area_ratio_median']:.9f}, 범위는 {S['area_ratio_min']:.6f}~{S['area_ratio_max']:.6f}입니다. 실제 기하 면적과 거의 일치하므로 원본 면적의 m² 해석을 지지합니다. 지표 분모는 계산한 `polygon_area_m2`를 사용합니다.

점·폴리곤 `intersects`를 사용해 경계 위 점도 후보에 포함했습니다. 중첩 후보는 다음처럼 보존했습니다.

| 구분 | 점포 수 | 전체 대비 |
| --- | ---: | ---: |
| 상권 1개에만 속함 | {sp['unique_spatial_stores']:,} | {sp['unique_spatial_stores']/sp['total_stores']:.2%} |
| 상권 여러 개에 속함 | {sp['multiple_spatial_stores']:,} | {sp['multiple_spatial_stores']/sp['total_stores']:.2%} |
| 상권 밖 또는 좌표 미유효 | {sp['unmatched_spatial_stores']:,} | {sp['unmatched_spatial_stores']/sp['total_stores']:.2%} |

- 대표 배정: 후보 면적이 가장 작은 상권에 배정하고 동률은 상권코드 순으로 정했습니다. 공식 배정 규칙이 아닌 재현 가능한 분석 가정입니다.
- 유일매칭 수: 후보가 하나뿐인 점포만 센 수도 함께 제공합니다. 대표 배정 결과와 비교할 수 있습니다.
- 모든 소속: 각 상권에 실제 포함되는 점포를 모두 세는 별도 표도 제공합니다. 공간 관계 {sp['all_spatial_memberships']:,}건입니다. 이 표는 지역 내부 시설 분석에 유용하지만 상권 사이를 합산하면 중복됩니다.
- 상권 밖 점포: 가장 가까운 상권에 강제로 붙이지 않았습니다. 미연계 점포 Parquet에 보존했습니다. 1,650개 상권은 서울 전역을 빠짐없이 덮는 행정구역이 아니므로 상권 밖은 곧 데이터 오류를 뜻하지 않습니다.
- 관광특구 같은 넓은 상권은 최소면적 배정 시 점포 수가 줄 수 있습니다. 지역 내부 시설을 볼 때는 `snapshot_all_membership_store_count`나 모든 소속 표를 사용하세요. 대표 배정 점포 0을 실제 상점 0으로 읽지 마세요.

행정동코드는 직접 결합하지 않았습니다. K03의 대표 행정동은 상권마다 하나 붙은 속성이며, 상권 전체가 그 행정동과 동일한 경계를 갖는다는 뜻이 아닙니다.

공간 API 근거: [GeoPandas 공간 결합](https://geopandas.org/en/stable/docs/reference/api/geopandas.sjoin.html).

## 4. 업종 체계 대응

소진공 247개와 서울 100개는 서로 다른 분류입니다. 공식 연계표는 인수인계에서 확보되지 않았으므로 [잠정 대응표](config/industry_crosswalk.csv)를 작성했습니다.

- {sp['mapped_semas_classes']}개 소분류 → 서울 {sp['mapped_seoul_classes']}개 업종으로 잠정 연결했습니다. {sp['unmapped_semas_classes']}개 소분류는 검토 대상으로 미연계 유지했습니다.
- 전체 S01 {sp['total_stores']:,}개 중 {sp['mapped_industry_stores_all']:,}개({sp['mapped_industry_stores_all']/sp['total_stores']:.2%})가 잠정 업종 대응에 해당합니다. 공간 대표배정까지 가능한 대응 점포는 {sp['mapped_industry_stores_assigned']:,}개입니다.
- 예: 여러 한식 소분류 → 한식음식점, 카페 → 커피-음료, 치킨 → 치킨전문점.
- 보류 예: 기숙사/고시원, 독서실/스터디카페, 주류 소매→주류도매, 동남아식→양식, 유흥주점→호프-간이주점. 명칭이 비슷해도 범위가 다르면 강제로 연결하지 않았습니다.
- 모든 연결은 `provisional_rule`입니다. 공식 업종 동등성이나 두 기관 점포수의 일치를 주장하지 않습니다. 검토가 끝날 때까지 K02 점포수를 S01 대응 점포수로 대체하지 않습니다.
- K02 100업종의 경쟁·점포당매출 지표와, S01 247업종의 구성·다양성 결과를 각각 유지했습니다. 대응표에 의존하지 않고 원래 분류로 재검토할 수 있습니다.

`snapshot_mapped_store_count`는 대응 가능한 소분류만 센 대표배정 점포입니다. `snapshot_membership_mapped_store_count`는 중첩을 허용한 상권 내부 점포입니다. 범위·수집 방식·연계 누락 때문에 K02 점포수와 차이가 날 수 있으며 이 차이를 곧바로 부족점포/오류로 해석하지 않습니다.

## 5. 개·폐업률이 100을 넘는 경우

공식 비율이 100을 넘는 행은 {S['source_rate_over100_rows']}개입니다. 공시 비율을 삭제하거나 100으로 잘라내지 않았습니다. 현재 전체점포수와 일반점포수를 각각 분모로 재계산한 비교 결과입니다. `pp`는 퍼센트포인트입니다.

{table(rates)}

예를 들어 2025Q2 용산세무서 상권의 한식음식점은 현재점포 1개, 폐업신고 2개, 공시폐업률 200입니다. 기간 중 개·폐업 흐름과 시점의 점포 재고는 다르므로 비율이 100을 넘을 수 있습니다. 이를 폐업 확률이나 점포 생존율로 해석하지 않습니다.

공시 비율은 원파일에서 정수 단위입니다. 전체점포수를 분모로 하면 비교 가능한 302,578개 행 모두 공시값과 0.55%포인트 이내로 일치합니다. 재계산치와의 소수점 차이는 공시 정밀도와 관련될 수 있으나 정확한 반올림 과정은 확인되지 않았습니다. 비율 공시값을 복원했다고 주장하지 않고, 재현 가능한 `개업/현재전체점포`와 `폐업/현재전체점포`를 별도 지표로 제공합니다. 분모 0은 공시값을 따라 0으로 만들지 않고 결측 처리합니다.

참고: [서울시 상권분석서비스 지표 정의](https://golmokxpert.seoul.go.kr/main.do). 이 페이지의 일반 정의와 현재 원파일의 공시 정밀도는 구분해 해석합니다.

## 6. 결합 커버리지와 시간 정렬

{table(cov)}

- S01은 2025-12-31 스냅숏이므로 Q4 행에만 연결했습니다. Q1~Q3의 소진공 점포·구성은 결측입니다. Q4와도 정확히 같은 모집단·측정기간은 아닙니다.
- 인구·시설은 원본에서 제공하는 분기 코드를 그대로 따릅니다. 실제 값의 반복 여부는 아래와 같습니다. 반복값을 독립적인 분기 수요 증가로 해석하지 않습니다.

{table(stability)}

- K01 `당월_매출_금액`은 인수인계에 따라 분기 추정매출로 사용했습니다. 월 매출이나 개별 상가의 실제 매출로 해석하지 않습니다.
- 서로 중첩하는 상권의 원자료 매출·점포 총합은 서울시 고유 전체 총량이 아닐 수 있습니다. 결합 전후 합계 검증은 같은 원본 행 집합 보존 여부를 확인하는 검사입니다.

## 7. 저장 구조와 재현

```text
data/raw/                         원본: 읽기 전용으로 사용
data/interim/park_step23/          K01~K07 정제, 공간 후보, 점포 배정, STEP2 통합 패널
data/processed/park_step23/        STEP3 지표 패널, 상권×분기, 소진공 구성, 연간 변동
박성은/config/industry_crosswalk.csv
박성은/reports/                   커버리지·정의서·감사표·실행 요약
박성은/build_step23.py
```

원본 18개 파일의 SHA-256을 실행 전후 검사했습니다. 중복키·결합 행 수·매출 및 점포 합계·결측 보존·과거분기 스냅숏 누수·비율 범위 등 필수 검증 {S['validation_passed']}개 통과, 실패 {S['validation_failed']}개입니다. [전체 검사](reports/validation_checks.csv), [실행 요약](reports/run_summary.json).
''')

featuretable = F[['variable', 'label', 'grain', 'formula', 'inputs', 'unit', 'interpretation', 'non_null_rows']].rename(columns={'variable':'변수명','label':'의미','grain':'단위','formula':'계산식','inputs':'원본','unit':'값의 단위','interpretation':'해석·한계','non_null_rows':'계산된 행 수'})
available = q4[q4.sales_observed & q4.total_store_count.ge(5)]
describe = available[['sales_per_store', 'franchise_share', 'same_industry_store_density_km2', 'weekend_sales_share']].quantile([.25,.5,.75]).T.reset_index()
describe.columns = ['variable', 'p25', 'median', 'p75']
deferred = pd.read_csv(R / 'deferred_features.csv')

write('STEP3_파생변수_정의_결과.md', f'''
# STEP 3 · 파생변수 정의 및 생성 결과

작성일: 2026-11-02. STEP 2 결합 결과를 바탕으로 {S['computed_feature_count']}개 지표를 실제 계산했습니다. 숫자는 예측·추천점수가 아니라 기술통계와 분석용 변수입니다.

## 1. 산출 단위와 공통 계산 규칙

- 주 테이블: 분기×상권×서울 서비스업종 {S['panel_rows']:,}행. Q4 {S['q4_rows']:,}행.
- 별도 테이블: 상권×분기 {S['context_rows']:,}행, 상권×소진공소분류 스냅숏, 연도×상권×업종 변동표.
- 비율은 기본적으로 0~1 척도입니다. 공시 개·폐업률은 `_pct`로 구분해 0~100 이상 척도를 보존합니다. 예: `franchise_share=0.2`는 20%입니다.
- 분모가 0·음수·결측이면 계산 결과도 결측입니다. 분자가 결측이면 0으로 바꾸지 않습니다.
- 원 지표를 삭제하지 않고 로그 변환을 추가했습니다. 극단값을 임의로 자르지 않았습니다.
- 전분기 변화는 직전 분기가 실제로 존재하고 이전 값이 양수인 경우에만 계산합니다. Q1, 누락분기 건너뛰기, 이전 값 0은 결측입니다.
- 4분기 변동계수는 매출이 모두 관측된 경우에만 계산하며 표준편차 `ddof=0`을 사용합니다. 4개 값에 대한 기술통계로서 장기 안정성의 추정치가 아닙니다.
- S01 관련 지표는 2025년 말 시점만 나타냅니다. 분기 패널에서는 Q4에만 붙였습니다.

## 2. 파생변수 정의서

`계산된 행 수`는 각 지표가 정의된 테이블에서의 유효값 수입니다. 주 패널과 상권표의 행 수를 합산하거나 같은 분모로 비교하면 안 됩니다.

{table(featuretable)}

기계 판독용 정의서: [feature_dictionary.csv](reports/feature_dictionary.csv). 최종 테이블의 원본·플래그 컬럼까지 포함한 사전: [output_column_dictionary.csv](reports/output_column_dictionary.csv).

## 3. 해석 예시와 실제 분포

2025Q4 중 매출이 관측되고 전체점포가 5개 이상인 행만 아래 기술통계에 사용했습니다. 업종을 모두 섞은 분포이므로 추천기준으로 사용할 수 없고, 값의 규모를 확인하기 위한 참고입니다. 업종별 사업구조·단가·매출 분포가 달라 실제 상권 비교는 동일 업종·동일 분기로 제한해야 합니다.

{table(describe.round(6))}

예시를 확인하는 순서:

1. 희망 업종 1개와 2025Q4를 고릅니다.
2. `sales_observed=True`인 행에서 점포당 추정매출·점포 밀도·프랜차이즈 비중을 나란히 확인합니다.
3. 점포가 1~4개인 행은 `small_store_base_lt5=True`로 표시했습니다. 제거하지 않았으며 작은 분모로 값이 커질 수 있음을 확인합니다. 기준 5는 통계적으로 검증된 임계값이 아니라 검토용 표시 기준입니다.
4. `flow_observed`, `facility_observed`, `worker_observed`, `resident_observed`로 수요·시설 자료의 존재 여부를 확인합니다.
5. 소진공 대응 점포수는 `snapshot_mapping_available`을 확인한 후 읽습니다. 대응값 0은 대응 가능한 부분집합의 집계 0일 뿐 실제 업종 전체 점포가 0이라는 뜻은 아닙니다.
6. `snapshot_spatial_ambiguity_share`가 큰 지역은 최소면적 배정과 모든 소속 집계를 비교합니다.

실제 업종별 첫 유효 예시를 [feature_examples_2025q4.csv](samples/feature_examples_2025q4.csv)에 저장했습니다. 상권코드 순으로 뽑았으며 추천 순위가 아닙니다. 요약 Excel의 예시에는 원 매출·점포수와 계산 수식을 함께 넣었습니다.

## 4. 고객 특성 비중의 분모

20·30대 매출 비중은 6개 연령대의 분류된 매출 합을 분모로 사용했습니다. 총매출과 분류 매출은 범위가 다를 수 있으므로 임의로 총매출에 맞춰 늘리지 않았습니다. `classified_gender_sales_share`로 성별 분류 매출 커버리지를 별도로 보여줍니다. 인수인계의 과거 EDA 가정과 현재 파일을 혼동하지 않도록 연령합과 성별합의 차이도 검사 기록에 남겼습니다.

유동인구 대비 매출은 두 집계량의 비율입니다. 고유 방문자/구매자를 연결한 값이 아니므로 구매전환율, 방문자 1인당 소비액, 잠재고객 수로 표현하지 않습니다. 시간대 비중은 시간 구간의 길이가 서로 달라 시간당 효율과 구분합니다.

## 5. 이번 자료로 계산하지 않은 변수

{table(deferred)}

임대료·보증금·권리금·시설비가 없으므로 사용자 예산으로 입점 가능 여부를 확정할 수 없습니다. 2024 매출이 없으므로 전년 동기 성장률도 산출하지 않았습니다. 개별점포 이익·생존확률은 이번 자료에서 알 수 없습니다.

## 6. 다음 단계로 넘길 사항

STEP 4에서 점수화할 때는 업종 안에서의 비교, 변수 중복 반영, 소수 점포 분모, 비관측 매출, 공간 배정 가정, 업종 대응표 민감도를 먼저 정해야 합니다. 금융 MBTI별 가중치는 팀 유형표와 추천목표가 확정된 뒤 별도로 설계합니다.

본 STEP 3의 완료 범위는 **변수 정의·공식·출처·결측 규칙·실제 계산 결과·검증**입니다. 특정 가중치나 성공 가능성을 임의로 추가하지 않았습니다.
''')

write('팀공유_핵심결과.md', f'''
# 팀 공유용 · STEP 2/3 핵심 결과

2025년 지정 원본 9종으로 전처리·결합과 파생변수 생성을 완료했습니다.

- 분기×상권×업종 패널: **{S['panel_rows']:,}행**. 매출 원본 {S['sales_rows']:,}행을 모두 보존했습니다.
- 상권×분기 수요·시설 맥락: **{S['context_rows']:,}행**.
- 지표 정의·계산: **{S['computed_feature_count']}개**. 점포당매출, 경쟁밀도, 프랜차이즈 비중, 수요비중, 전분기 변화 등입니다.
- 원본 해시 18개 모두 실행 전후 동일. 필수 검증 {S['validation_passed']}개 통과, 실패 {S['validation_failed']}개.

## 데이터에서 확인한 사항

1. 매출 미관측 **{S['sales_unobserved_rows']:,}행**은 0으로 채우지 않았습니다. 미제공 업종과 해당 키 미관측을 구분했습니다.
2. S01 점포 {sp['total_stores']:,}개 중 상권 단일 매칭 {sp['unique_spatial_stores']:,}, 중첩 후보 {sp['multiple_spatial_stores']:,}, 상권 밖 {sp['unmatched_spatial_stores']:,}개입니다. 중첩은 대표배정·유일매칭·모든 소속 집계로 비교할 수 있습니다.
3. 소진공 247개 업종 중 {sp['mapped_semas_classes']}개를 서울 {sp['mapped_seoul_classes']}개 업종에 잠정 대응했습니다. {sp['unmapped_semas_classes']}개는 근거 부족으로 보류했습니다. 공식 연계표가 아닙니다.
4. 상권 도형 {S['invalid_geometries_before']}개를 가공본에서 보정했습니다. 원본은 그대로입니다.
5. 공시 개·폐업률 100 초과 {S['source_rate_over100_rows']}행을 보존했습니다. 생존확률로 읽지 않으며 자체 계산 비율과 구분합니다.
6. 집객시설 공시 합계와 하위 시설 합이 {S['facility_total_mismatch_rows_2025']:,}행에서 달라 별도 컬럼으로 관리했습니다.

## 팀에서 검토할 선택

- 업종 잠정 대응표의 범위를 확정할지, 원 분류끼리 별도 분석할지.
- 중첩 지역에서 대표 배정과 모든 소속 집계 중 어떤 질문에 어떤 값을 사용할지.
- 매출 미관측 업종은 매출 추천에서 제외할지, 시설·수요 정보만 보여줄지.
- 다음 점수화에서 어떤 지표를 어떤 근거로 쓸지. 이번 단계에는 가중치·추천순위를 넣지 않았습니다.

파일 안내: [README](README.md) → [STEP2](STEP2_전처리_결합_결과.md) → [STEP3](STEP3_파생변수_정의_결과.md).
''')
print('Korean reports written:', len(F), 'computed features')
independent = R / 'independent_validation.json'
if independent.exists():
    v = json.loads(independent.read_text(encoding='utf-8'))
    extra = f'\n저장된 결과를 원본과 다시 대조한 독립 검증: {v["passed"]}개 통과, {v["failed"]}개 실패. 모든 매출·점포 값 일치, 정확한 직전분기 조인, 분모 0·결측, 500개 공간 배정 샘플, 모든 공간 후보 및 집계 수 보존을 확인했습니다. [독립 검증 기록](reports/independent_validation.json).\n'
    for name in ['README.md', 'STEP2_전처리_결합_결과.md', '팀공유_핵심결과.md']:
        path = HERE / name
        path.write_text(path.read_text(encoding='utf-8') + extra, encoding='utf-8')
