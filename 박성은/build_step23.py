"""2025년 STEP 2/3. 원본은 읽기만 하며, 결과는 data/{interim,processed}/park_step23에 저장.

실행: python 박성은/build_step23.py
의존성: pip install -r 박성은/requirements.txt
공식 연계표가 없는 업종 대응은 분석용 가정이며 crosswalk.csv에서 수정 가능.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'seoul-commercial-analysis'
if (ROOT / '.analysis_deps').exists():
    sys.path.insert(0, str(ROOT / '.analysis_deps'))
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import is_valid_reason

RAW = ROOT / 'data/raw'
WORK = Path(__file__).resolve().parent
INTERIM = ROOT / 'data/interim/park_step23'
OUT = ROOT / 'data/processed/park_step23'
REPORT = WORK / 'reports'
KEY = ['quarter_code', 'market_code', 'industry_code']
AREAKEY = KEY[:2]
AUDIT: list[dict] = []
FEATURES: list[dict] = []
ARTIFACTS: list[dict] = []
SOURCE_ROWS: list[dict] = []
COLMAP: list[dict] = []


def log(s):
    print(s, flush=True)


def check(name, condition, detail):
    AUDIT.append({'check': name, 'passed': bool(condition), 'detail': str(detail)})
    if not condition:
        raise AssertionError(f'{name}: {detail}')


def note(name, value):
    AUDIT.append({'check': name, 'passed': None, 'detail': str(value)})


def csv(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding='utf-8-sig', float_format='%.10g')


def parquet(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression='zstd')
    ARTIFACTS.append({'file': str(path.relative_to(ROOT)), 'rows': len(df), 'columns': len(df.columns)})


def ratio(a, b):
    """분모가 0·결측·음수이면 결측. 분자 결측도 그대로 유지한다."""
    return a.div(b.where(b.gt(0))).replace([np.inf, -np.inf], np.nan)


def load(name, pattern, encoding, rename, key):
    paths = list(RAW.rglob(pattern))
    check(f'{name}: input file unique', len(paths) == 1, [str(p.relative_to(ROOT)) for p in paths])
    df = pd.read_csv(paths[0], encoding=encoding, dtype='string')
    n = len(df)
    df = df.rename(columns=rename)
    if 'quarter_code' in df:
        df = df[df.quarter_code.isin(['20251', '20252', '20253', '20254'])].copy()
    idcols = set(rename.values())
    for col in df:
        if col not in idcols:
            before = df[col].notna().sum()
            df[col] = pd.to_numeric(df[col], errors='coerce')
            check(f'{name}: numeric {col}', df[col].notna().sum() == before, f'nonempty={before}')
    check(f'{name}: key unique', not df.duplicated(key).any(), f'{len(df)} rows')
    check(f'{name}: key nonnull', not df[key].isna().any().any(), key)
    for old, new in rename.items():
        COLMAP.append({'source': name, 'original': old, 'normalized': new})
    SOURCE_ROWS.append({'source': name, 'input_rows': n, 'rows_2025': len(df), 'file': str(paths[0].relative_to(ROOT))})
    return df


COMMON = {'기준_년분기_코드': 'quarter_code', '상권_코드': 'market_code',
          '상권_코드_명': 'market_name', '상권_구분_코드': 'market_type', '상권_구분_코드_명': 'market_type_name'}


def feature(df, name, label, values, formula, inputs, unit, purpose, caution, grain='분기×상권×업종'):
    df[name] = values
    FEATURES.append({'variable': name, 'label': label, 'grain': grain, 'formula': formula,
                     'inputs': inputs, 'unit': unit, 'purpose': purpose, 'interpretation': caution,
                     'missing_rule': '입력 결측 또는 분모<=0이면 결측. 개별 예외는 해석란 참고.',
                     'status': '계산 완료', 'non_null_rows': int(df[name].notna().sum())})


def source_hashes():
    rows = []
    for line in (ROOT / 'data/metadata/checksums.sha256').read_text(encoding='utf-8').splitlines():
        expected, rel = line.split(maxsplit=1)
        rel = rel.lstrip('*')
        p = ROOT / rel
        h = hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda: f.read(1024 * 1024), b''):
                h.update(b)
        actual = h.hexdigest()
        rows.append({'file': rel, 'expected_sha256': expected, 'actual_sha256': actual, 'matches': actual == expected})
    df = pd.DataFrame(rows)
    check('input checksums match handoff', df.matches.all(), f'{len(df)} files')
    return df


def crosswalk(s, stores):
    """정확한 이름 일치와 명시적인 의미 대응만 채택. 미확인 항목은 미연계."""
    path = WORK / 'config/industry_crosswalk.csv'
    if path.exists():
        cw = pd.read_csv(path, dtype='string').fillna('')
    else:
        cw = s[['semas_industry_code', 'semas_industry_name']].drop_duplicates().sort_values('semas_industry_code')
        cw['industry_code'] = ''
        cw['mapping_status'] = 'unmapped_review'
        cw['reason'] = '서울 100개 분류와 범위가 다르거나 대응 근거 부족. 미연계 유지'
        rules = {
            'CS100001': [f'I201{i:02d}' for i in range(1, 14)] + ['I20199'],
            'CS100002': ['I20201', 'I20202'], 'CS100003': ['I20301', 'I20302', 'I20303', 'I20399'],
            'CS100004': ['I20401', 'I20402', 'I20403', 'I20499'], 'CS100005': ['I21001'],
            'CS100006': ['I21003', 'I21004'], 'CS100007': ['I21006'], 'CS100008': ['I21007'],
            'CS100009': ['I21103', 'I21104'], 'CS100010': ['I21201'],
            'CS200001': ['P10501'], 'CS200002': ['P10615'], 'CS200003': ['P10609', 'P10611'],
            'CS200004': ['P10627'], 'CS200005': ['P10601', 'P10603'],
            'CS200006': [f'Q102{i:02d}' for i in range(1, 10)] + ['Q10212'],
            'CS200007': ['Q10210'], 'CS200008': ['Q10211'], 'CS200009': ['M11101'],
            'CS200010': ['M10301'], 'CS200011': ['M10302'], 'CS200012': ['M10303'],
            'CS200013': ['M10306', 'M10307', 'M10399'], 'CS200014': ['M10401'], 'CS200015': ['M10402'],
            'CS200016': ['R10310'], 'CS200017': ['R10311'], 'CS200018': ['R10309'],
            'CS200019': ['R10406'], 'CS200020': ['R10404'], 'CS200021': ['R10405'],
            'CS200022': ['R10410'], 'CS200023': ['S20201'], 'CS200024': ['R10306', 'R10307'],
            'CS200025': ['S20301'], 'CS200026': ['S20302'], 'CS200027': ['S20401'],
            'CS200028': ['S20701'], 'CS200029': ['S20703'], 'CS200030': ['S20702'],
            'CS200031': ['S20901', 'S20902'], 'CS200032': ['S20501'], 'CS200033': ['L10203'],
            'CS200034': ['I10102'], 'CS200037': ['R10407'], 'CS200039': ['R10402'],
            'CS200041': ['M11301'], 'CS200042': ['M11502'], 'CS200043': ['N10201'],
            'CS200044': ['N10501'], 'CS200045': ['N11002', 'N11003'], 'CS200046': ['N11004'],
            'CS300001': ['G20404'], 'CS300002': ['G20405'], 'CS300003': ['G20801'],
            'CS300004': ['G20802'], 'CS300006': ['G20501'], 'CS300007': ['G20503'],
            'CS300008': ['G20504', 'G20505'], 'CS300009': ['G20506'], 'CS300010': ['G20509'],
            'CS300011': ['G20901', 'G20902', 'G20905'], 'CS300012': ['G20904'],
            'CS300013': ['G20903'], 'CS300014': ['G20910'], 'CS300015': ['G20911'],
            'CS300016': ['G21602'], 'CS300017': ['G21701'], 'CS300018': ['G21501'],
            'CS300019': ['G21502'], 'CS300020': ['G21301'], 'CS300021': ['G21302'],
            'CS300022': ['G21503'], 'CS300024': ['G21304'], 'CS300025': ['G21305'],
            'CS300026': ['G21306'], 'CS300027': ['G20909'], 'CS300028': ['G21901'],
            'CS300029': ['G22001'], 'CS300031': ['G21101'], 'CS300032': ['G20803'],
            'CS300033': ['G21001'], 'CS300034': ['G21203'], 'CS300035': ['G21002'],
            'CS300036': ['G21201'], 'CS300038': ['G20201', 'G20202'],
            'CS300039': ['G20301'], 'CS300041': ['G21801'], 'CS300042': ['G21401'],
        }
        for target, codes in rules.items():
            mask = cw.semas_industry_code.isin(codes)
            cw.loc[mask, 'industry_code'] = target
            cw.loc[mask, 'mapping_status'] = 'provisional_rule'
            cw.loc[mask, 'reason'] = '분류명 의미에 따른 분석용 수동 규칙. 공식 연계표 아님; 팀 검토 필요; 동일 모집단 보장 안 됨'
        # 복합 업종을 억지로 쪼개지 않는다.
        reasons = {'I10201': '기숙사/고시원 혼합으로 고시원만 분리 불가',
                   'R10202': '독서실/스터디카페 혼합으로 독서실과 정확한 범위 일치 불명',
                   'G20602': '주류 소매와 서울 주류도매는 유통단계가 달라 미연계',
                   'I21005': '토스트/샌드위치/샐러드의 패스트푸드 범위 검토 필요',
                   'I20501': '베트남식은 서울 양식과 범위 일치 근거 부족',
                   'I20599': '동남아식은 서울 양식과 범위 일치 근거 부족',
                   'I21101': '유흥주점은 호프-간이주점과 범위 구분 필요',
                   'I21102': '무도유흥주점은 호프-간이주점과 범위 구분 필요'}
        for code, reason in reasons.items():
            cw.loc[cw.semas_industry_code.eq(code), 'reason'] = reason
        names = stores[['industry_code', 'industry_name']].drop_duplicates().set_index('industry_code').industry_name
        cw['industry_name'] = cw.industry_code.map(names).fillna('')
        csv(cw, path)
    check('crosswalk: unique source codes', not cw.semas_industry_code.duplicated().any(), len(cw))
    check('crosswalk: exhaustive source codes', set(cw.semas_industry_code) == set(s.semas_industry_code), 'all 247 source classes')
    valid = cw.industry_code.ne('')
    check('crosswalk: valid target codes', set(cw.loc[valid, 'industry_code']) <= set(stores.industry_code), 'K02 100 classes')
    return cw


def spatial_snapshot(areas, stores):
    log('S01/S02: reading store snapshot and joining points to polygons')
    rename = {'상가업소번호': 'store_id', '상권업종대분류코드': 'semas_major_code',
              '상권업종대분류명': 'semas_major_name', '상권업종소분류코드': 'semas_industry_code',
              '상권업종소분류명': 'semas_industry_name', '행정동코드': 'store_admindong_code',
              '시군구코드': 'store_district_code', '경도': 'longitude', '위도': 'latitude'}
    path = next(RAW.rglob('*서울_202512.csv'))
    s = pd.read_csv(path, encoding='utf-8', dtype='string', usecols=list(rename)).rename(columns=rename)
    check('S01: unique store ids', s.store_id.is_unique, len(s))
    codes = pd.read_csv(RAW / 'semas/semas_industry_code_20230228.csv', encoding='cp949', dtype='string')
    SOURCE_ROWS.extend([{'source': 'S01', 'input_rows': len(s), 'rows_2025': len(s), 'file': str(path.relative_to(ROOT))},
                        {'source': 'S02', 'input_rows': len(codes), 'rows_2025': len(codes), 'file': 'data/raw/semas/semas_industry_code_20230228.csv'}])
    check('S02: unique small codes', codes['소분류코드'].is_unique, len(codes))
    check('S01/S02: same industry domain', set(s.semas_industry_code) == set(codes['소분류코드']), '247 classes')
    label_comparison = s[['semas_industry_code', 'semas_industry_name']].drop_duplicates().copy()
    label_comparison['codebook_label'] = label_comparison.semas_industry_code.map(codes.set_index('소분류코드')['소분류명'])
    label_differences = label_comparison[label_comparison.semas_industry_name.ne(label_comparison.codebook_label)]
    csv(label_differences, REPORT / 'semas_codebook_label_differences.csv')
    note('S01/S02: same code but different label', len(label_differences))
    # 구 코드표와 구두점이 다른 두 항목은 S01의 명칭을 유지한다.
    for c in ['longitude', 'latitude']:
        s[c] = pd.to_numeric(s[c], errors='coerce')
    valid = s.longitude.between(124, 132) & s.latitude.between(33, 39)
    note('S01: invalid coordinates excluded from spatial match', int((~valid).sum()))
    points = gpd.GeoDataFrame(s.loc[valid, ['store_id']], geometry=gpd.points_from_xy(s.loc[valid].longitude, s.loc[valid].latitude), crs=4326).to_crs(5181)
    candidates = gpd.sjoin(points, areas[['market_code', 'geometry']], predicate='intersects', how='inner')
    edges = candidates[['store_id', 'market_code']].drop_duplicates()
    counts = edges.groupby('store_id').size()
    s['spatial_candidate_count'] = s.store_id.map(counts).fillna(0).astype('int16')
    # 최소 면적 우선의 대표 배정은 분석 선택이다. 후보 관계도 저장하고 유일매칭 집계를 병기한다.
    edges['candidate_area_m2'] = edges.market_code.map(areas.set_index('market_code').polygon_area_m2)
    chosen = edges.sort_values(['store_id', 'candidate_area_m2', 'market_code']).drop_duplicates('store_id')
    s = s.merge(chosen[['store_id', 'market_code']], on='store_id', how='left', validate='1:1')
    s['spatial_status'] = np.select([s.spatial_candidate_count.eq(0), s.spatial_candidate_count.eq(1)], ['outside_or_invalid', 'unique_match'], default='multiple_matches_smallest_area')
    cw = crosswalk(s, stores)
    s = s.merge(cw[['semas_industry_code', 'industry_code', 'mapping_status']], on='semas_industry_code', how='left', validate='m:1')
    s['industry_code'] = s.industry_code.replace('', pd.NA)
    s['snapshot_date'] = '2025-12-31'
    check('S01: spatial join preserves row count', len(s) == 534978, len(s))
    check('S01: assigned count reconciles', s.market_code.notna().sum() == len(chosen), len(chosen))
    parquet(s, INTERIM / 'semas_store_spatial_2025q4.parquet')
    parquet(edges, INTERIM / 'semas_spatial_candidates.parquet')
    parquet(s[s.market_code.isna()], INTERIM / 'semas_unmatched_stores.parquet')
    csv(s.groupby(['semas_industry_code', 'semas_industry_name', 'mapping_status'], dropna=False).size().reset_index(name='store_count'), REPORT / 'industry_mapping_coverage.csv')
    assigned = s[s.market_code.notna()].copy()
    assigned['unique_spatial'] = assigned.spatial_candidate_count.eq(1).astype('int64')
    membership = edges[['store_id', 'market_code']].merge(s.drop(columns='market_code'), on='store_id', how='left', validate='m:1')
    membership_native = membership.groupby(['market_code', 'semas_industry_code', 'semas_industry_name']).size().reset_index(name='snapshot_membership_store_count')
    membership_native['snapshot_date'] = '2025-12-31'
    check('S01: all memberships reconcile with spatial edges', membership_native.snapshot_membership_store_count.sum() == len(edges), len(edges))
    parquet(membership_native, OUT / 'semas_all_memberships_industry_2025q4.parquet')
    csv(membership_native, OUT / 'semas_all_memberships_industry_2025q4.csv')
    native = assigned.groupby(['market_code', 'semas_industry_code', 'semas_industry_name']).agg(snapshot_store_count=('store_id', 'size'), snapshot_unique_spatial_count=('unique_spatial', 'sum')).reset_index()
    native['snapshot_date'] = '2025-12-31'
    check('S01: native aggregation reconciles', native.snapshot_store_count.sum() == len(assigned), len(assigned))
    native_share = ratio(native.snapshot_store_count, native.groupby('market_code').snapshot_store_count.transform('sum'))
    feature(native, 'snapshot_native_industry_share', '소진공 소분류 점포 구성비', native_share, '상권·소분류 점포수/상권의 소진공 전체점포수', 'S01 상권업종소분류코드; K03 geometry', '비율(0~1)', '시설·업종 구성 분석', '최소면적 대표 배정 기준. 원 분류 247개를 보존. 2025-12-31 시점.', '시점×상권×소진공소분류')
    parquet(native, OUT / 'semas_native_industry_2025q4.parquet')
    csv(native, OUT / 'semas_native_industry_2025q4.csv')
    agg = assigned.groupby('market_code').agg(snapshot_store_count=('store_id', 'size'), snapshot_unique_spatial_count=('unique_spatial', 'sum'), snapshot_distinct_industries=('semas_industry_code', 'nunique')).reindex(areas.market_code).fillna(0)
    share = native_share
    native['hhi_component'] = share ** 2
    native['entropy_component'] = -share * np.log(share)
    agg['snapshot_industry_hhi'] = native.groupby('market_code').hhi_component.sum().reindex(agg.index)
    agg['snapshot_industry_entropy'] = native.groupby('market_code').entropy_component.sum().reindex(agg.index)
    agg['snapshot_multiple_spatial_count'] = agg.snapshot_store_count - agg.snapshot_unique_spatial_count
    agg['snapshot_spatial_ambiguity_share'] = ratio(agg.snapshot_multiple_spatial_count, agg.snapshot_store_count)
    agg['snapshot_all_membership_store_count'] = membership.groupby('market_code').size().reindex(agg.index).fillna(0)
    agg = agg.reset_index()
    mapped = assigned[assigned.industry_code.notna()]
    service = mapped.groupby(['market_code', 'industry_code']).agg(snapshot_mapped_store_count=('store_id', 'size'), snapshot_mapped_unique_spatial_count=('unique_spatial', 'sum')).reset_index()
    membership_service = membership[membership.industry_code.notna()].groupby(['market_code', 'industry_code']).size().reset_index(name='snapshot_membership_mapped_store_count')
    service = service.merge(membership_service, on=['market_code', 'industry_code'], how='outer', validate='1:1')
    service[['snapshot_mapped_store_count', 'snapshot_mapped_unique_spatial_count']] = service[['snapshot_mapped_store_count', 'snapshot_mapped_unique_spatial_count']].fillna(0)
    mapping_n = cw[cw.industry_code.ne('')].groupby('industry_code').size()
    coverage = {'total_stores': len(s), 'unique_spatial_stores': int(s.spatial_candidate_count.eq(1).sum()),
                'multiple_spatial_stores': int(s.spatial_candidate_count.gt(1).sum()),
                'unmatched_spatial_stores': int(s.spatial_candidate_count.eq(0).sum()),
                'mapped_industry_stores_all': int(s.industry_code.notna().sum()),
                'mapped_industry_stores_assigned': len(mapped),
                'mapped_semas_classes': int(cw.industry_code.ne('').sum()),
                'unmapped_semas_classes': int(cw.industry_code.eq('').sum()),
                'mapped_seoul_classes': int(cw.loc[cw.industry_code.ne(''), 'industry_code'].nunique()),
                'all_spatial_memberships': len(edges)}
    return s, agg, service, mapping_n, coverage


def build():
    for path in [INTERIM, OUT, REPORT, WORK / 'outputs']:
        path.mkdir(parents=True, exist_ok=True)
    log('Checking original hashes')
    hashes_before = source_hashes()
    csv(hashes_before, REPORT / 'input_checksums.csv')
    sales = load('K01', '*추정매출-상권*csv', 'cp949', dict(COMMON, **{'서비스_업종_코드': 'industry_code', '서비스_업종_코드_명': 'industry_name'}), KEY)
    # 파일에 기록된 시간대 건수 순서를 검증하고 명칭만 수정한다.
    broken = [c for c in sales if c.startswith('시간대_건수')]
    bands = ['00~06', '06~11', '11~14', '14~17', '17~21', '21~24']
    check('K01: six malformed time count columns', len(broken) == 6 and [c.split('~')[1].split('_')[0] for c in broken] == ['06', '11', '14', '17', '21', '24'], broken)
    fixes = dict(zip(broken, [f'시간대_{b}_매출_건수' for b in bands]))
    sales = sales.rename(columns=fixes)
    COLMAP.extend({'source': 'K01', 'original': a, 'normalized': b} for a, b in fixes.items())
    storemap = dict(zip(['stdr_yyqu_cd', 'trdar_se_cd', 'trdar_se_cd_nm', 'trdar_cd', 'trdar_cd_nm', 'svc_induty_cd', 'svc_induty_cd_nm', 'stor_co', 'similr_induty_stor_co', 'opbiz_rt', 'opbiz_stor_co', 'clsbiz_rt', 'clsbiz_stor_co', 'frc_stor_co'], ['quarter_code', 'market_type', 'market_type_name', 'market_code', 'market_name', 'industry_code', 'industry_name', 'independent_store_count', 'total_store_count', 'opening_rate_source_pct', 'opening_store_count', 'closure_rate_source_pct', 'closure_store_count', 'franchise_store_count']))
    stores = load('K02', '*점포-상권*csv', 'cp949', storemap, KEY)
    # 이름을 바꾼 수치 컬럼도 명시적으로 숫자로 변환한다.
    numeric_store = list(storemap.values())[7:]
    for c in numeric_store:
        stores[c] = pd.to_numeric(stores[c], errors='raise')
    check('K02: ordinary + franchise = total', stores.independent_store_count.add(stores.franchise_store_count).eq(stores.total_store_count).all(), len(stores))
    flow = load('K04', 'seoul_flpop_trdar_2025_sheet.csv', 'cp949', COMMON, AREAKEY)
    facility = load('K05', 'seoul_facility_trdar_all_sheet.csv', 'cp949', COMMON, AREAKEY)
    worker = load('K06', 'seoul_wrcpop_trdar_all_sheet.csv', 'cp949', COMMON, AREAKEY)
    resident = load('K07', 'seoul_repop_trdar_all_sheet.csv', 'cp949', COMMON, AREAKEY)
    facility_items = [c for c in facility if c.endswith('_수') and c != '집객시설_수']
    blank_count = int(facility[facility_items].isna().sum().sum())
    # 인수인계의 API 대조 근거에 따라 존재하는 행의 하위 시설 칸만 0으로 채움.
    facility[facility_items] = facility[facility_items].fillna(0)
    facility['facility_components_sum'] = facility[facility_items].sum(axis=1)
    facility['facility_total_mismatch'] = facility.facility_components_sum.ne(facility['집객시설_수'])
    note('K05: component blanks filled with 0 within existing rows', blank_count)
    note('K05: published total differs from component sum', int(facility.facility_total_mismatch.sum()))
    area = gpd.read_file(next(RAW.rglob('*.shp'))).rename(columns={'TRDAR_CD': 'market_code', 'TRDAR_CD_N': 'market_name', 'TRDAR_SE_C': 'market_type', 'TRDAR_SE_1': 'market_type_name', 'SIGNGU_CD': 'district_code', 'SIGNGU_CD_': 'district_name', 'ADSTRD_CD': 'representative_admindong_code', 'ADSTRD_CD_': 'representative_admindong_name', 'RELM_AR': 'published_area_m2'})
    check('K03: source CRS is EPSG:5181', area.crs.to_epsg() == 5181, area.crs)
    check('K03: unique market code', area.market_code.is_unique, len(area))
    invalid_before = int((~area.geometry.is_valid).sum())
    area['geometry_repaired'] = ~area.geometry.is_valid
    area['geometry_validity_original'] = is_valid_reason(area.geometry)
    area['polygon_area_before_repair_m2'] = area.geometry.area
    if invalid_before:
        area.geometry = area.geometry.make_valid()
    check('K03: valid nonempty geometries', area.geometry.is_valid.all() and not area.geometry.is_empty.any(), invalid_before)
    area['polygon_area_m2'] = area.geometry.area
    area['geometry_repair_area_delta_m2'] = area.polygon_area_m2 - area.polygon_area_before_repair_m2
    SOURCE_ROWS.append({'source': 'K03', 'input_rows': len(area), 'rows_2025': len(area), 'file': str(next(RAW.rglob('*.shp')).relative_to(ROOT))})
    check('K03: positive areas', area.polygon_area_m2.gt(0).all(), area.polygon_area_m2.min())
    area['published_to_polygon_area_ratio'] = ratio(area.published_area_m2, area.polygon_area_m2)
    csv(pd.DataFrame(area.drop(columns='geometry')), REPORT / 'market_geometry_audit.csv')
    area[['market_code', 'market_name', 'geometry']].to_parquet(INTERIM / 'market_polygons_5181.parquet', index=False)
    for name, df in [('K01', sales), ('K02', stores), ('K04', flow), ('K05', facility), ('K06', worker), ('K07', resident)]:
        check(f'{name}: market domain in K03', set(df.market_code) <= set(area.market_code), df.market_code.nunique())
        parquet(df, INTERIM / f'{name.lower()}_clean_2025.parquet')
    # 공식 공시 비율과 관측된 분모별 재계산을 대조한다. 100% 초과를 잘라내지 않음.
    rate_audit = stores[KEY + numeric_store].copy()
    rate_summary = []
    for kind, ncol, rcol in [('opening', 'opening_store_count', 'opening_rate_source_pct'), ('closure', 'closure_store_count', 'closure_rate_source_pct')]:
        for denominator in ['total_store_count', 'independent_store_count']:
            calc = ratio(stores[ncol], stores[denominator]) * 100
            valid = calc.notna() & stores[rcol].notna()
            rate_summary.append({'rate': kind, 'denominator': denominator, 'comparable_rows': int(valid.sum()), 'matched_within_0_011pp': int(((calc - stores[rcol]).abs().le(.011) & valid).sum()), 'matched_within_0_55pp': int(((calc - stores[rcol]).abs().le(.550001) & valid).sum()), 'max_abs_error_pp': float((calc - stores[rcol]).abs().max()), 'source_fractional_rows': int(stores[rcol].mod(1).ne(0).sum()), 'source_over100_rows': int(stores[rcol].gt(100).sum())})
        rate_audit[f'{kind}_per_current_total_pct'] = ratio(stores[ncol], stores.total_store_count) * 100
    csv(pd.DataFrame(rate_summary), REPORT / 'opening_closure_denominator_audit.csv')
    csv(rate_audit[rate_audit.opening_rate_source_pct.gt(100) | rate_audit.closure_rate_source_pct.gt(100)], REPORT / 'opening_closure_over100_rows.csv')
    log('Building 6,600-row market-quarter context')
    dimcols = ['market_code', 'market_name', 'market_type', 'market_type_name', 'district_code', 'district_name', 'representative_admindong_code', 'representative_admindong_name', 'polygon_area_m2']
    context = pd.DataFrame({'quarter_code': ['20251', '20252', '20253', '20254']}).merge(pd.DataFrame(area[dimcols]), how='cross')
    specs = [('flow', flow, {'총_유동인구_수': 'floating_population'}),
             ('facility', facility, {'집객시설_수': 'facility_count_source', 'facility_components_sum': 'facility_components_sum', 'facility_total_mismatch': 'facility_total_mismatch'}),
             ('worker', worker, {'총_직장_인구_수': 'worker_population'}),
             ('resident', resident, {'총_상주인구_수': 'resident_population', '총_가구_수': 'household_count'})]
    # 시간대/연령별 원자료는 clean parquet에 보존하고 필요한 컬럼만 context에 연결.
    flowcols = [f'시간대_{a}_{b}_유동인구_수' for a, b in [('00','06'),('06','11'),('11','14'),('14','17'),('17','21'),('21','24')]]
    flowextra = flow[AREAKEY + flowcols + ['연령대_20_유동인구_수', '연령대_30_유동인구_수']]
    for name, df, ren in specs:
        part = df[AREAKEY + list(ren)].rename(columns=ren).copy()
        part[f'{name}_observed'] = True
        context = context.merge(part, on=AREAKEY, how='left', validate='1:1')
        context[f'{name}_observed'] = context[f'{name}_observed'].fillna(False).astype(bool)
    context = context.merge(flowextra, on=AREAKEY, how='left', validate='1:1')
    feature(context, 'worker_share_of_worker_resident', '직장·상주인구 합 대비 직장인구 비중', ratio(context.worker_population, context.worker_population + context.resident_population), '직장인구/(직장인구+상주인구)', 'K06 총_직장_인구_수; K07 총_상주인구_수', '비율(0~1)', '업무형 배후수요 비교', '두 모집단은 중복 가능. 실제 고유 인구 구성비 아님.', '분기×상권')
    feature(context, 'resident_share_of_worker_resident', '직장·상주인구 합 대비 상주인구 비중', ratio(context.resident_population, context.worker_population + context.resident_population), '상주인구/(직장인구+상주인구)', 'K06; K07', '비율(0~1)', '주거형 배후수요 비교', '직장인구와 상주인구의 중복 가능.', '분기×상권')
    feature(context, 'flow_20_30_share', '20·30대 유동인구 비중', ratio(context['연령대_20_유동인구_수'] + context['연령대_30_유동인구_수'], context.floating_population), '(20대+30대 유동인구)/총유동인구', 'K04 연령대_20/30_유동인구_수; 총_유동인구_수', '비율(0~1)', '고객 연령대 수요', '유동인구는 고유 방문자수가 아님. 반올림 차이 가능.', '분기×상권')
    feature(context, 'flow_peak_band_share', '최대 시간대 유동인구 집중도', ratio(context[flowcols].max(axis=1, skipna=False), context[flowcols].sum(axis=1, min_count=6)), 'max(6개 시간대 인구)/sum(6개 시간대 인구)', 'K04 시간대별 유동인구 6열', '비율(0~1)', '시간대 집중도', '시간대 길이가 3~6시간으로 다름. 시간당 밀도와 다름.', '분기×상권')
    feature(context, 'facility_density_km2', '시설 종류별 개수 합의 면적당 밀도', ratio(context.facility_components_sum, context.polygon_area_m2 / 1e6), '하위 시설 19개 합/(폴리곤면적/1e6)', 'K05 하위시설 19열; K03 geometry', '시설개수합/km²', '입지 인프라 비교', '중복 시설 유형 가능. 고유 시설 수 아님. 공시 집객시설_수와 별도 지표.', '분기×상권')
    s, snap, mapped, mapping_n, spatial = spatial_snapshot(area, stores)
    # 전분기에 12월 점포 구성을 소급 적용하지 않는다.
    snap['quarter_code'] = '20254'
    context = context.merge(snap, on=AREAKEY, how='left', validate='1:1')
    for name, label, formula, purpose, caution in [
        ('snapshot_distinct_industries', '소진공 소분류 업종 수', '대표 배정 점포의 소분류 고유값 수', '업종 다양성', '점포가 0이면 0. 최솟값 면적 배정에 민감.'),
        ('snapshot_industry_hhi', '소진공 업종 집중도 HHI', 'sum((소분류점포수/전체점포수)^2)', '경쟁·시설 구성', '0~1; 클수록 집중. 분류수와 점포수에 영향. 점포 0이면 결측.'),
        ('snapshot_industry_entropy', '소진공 업종 다양성 엔트로피', '-sum(p_i*ln(p_i))', '시설 구성 다양성', '클수록 다양. 원시 엔트로피이며 업종수 보정 안 함. 점포0 결측.'),
        ('snapshot_spatial_ambiguity_share', '대표 배정 점포 중 다중 공간후보 비중', '(대표배정수-유일매칭수)/대표배정수', '공간 결합 품질', '클수록 최소면적 배정 선택의 영향이 큼. 0분모 결측.'),
    ]:
        feature(context, name, label, context[name], formula, 'S01 소분류·좌표; K03 geometry', '개' if name.endswith('industries') else '지수/비율', purpose, caution + ' 2025Q4만 연결.', '시점×상권')
    feature(context, 'snapshot_membership_store_density_km2', '상권 내부 소진공 점포 밀도', ratio(context.snapshot_all_membership_store_count, context.polygon_area_m2 / 1e6), '상권과 교차하는 모든 점포수/(폴리곤면적/1e6)', 'S01 좌표; K03 geometry', '점포/km²', '실제 지역의 상업시설 밀집도', '중첩 상권에서는 동일 점포가 각 상권에 포함. 여러 상권을 합산하면 중복. 2025Q4만 연결.', '시점×상권')
    parquet(context, OUT / 'market_quarter_context_2025.parquet')
    csv(context, OUT / 'market_quarter_context_2025.csv')
    log('Joining K01/K02 on quarter + market + service industry')
    aliases = {'당월_매출_금액': 'sales_amount', '당월_매출_건수': 'sales_transactions',
               '주중_매출_금액': 'weekday_sales_amount', '주말_매출_금액': 'weekend_sales_amount',
               '남성_매출_금액': 'male_sales_amount', '여성_매출_금액': 'female_sales_amount',
               '시간대_11~14_매출_금액': 'lunch_sales_amount', '시간대_17~21_매출_금액': 'evening_sales_amount'}
    ages = [c for c in sales if c.startswith('연령대_') and c.endswith('_매출_금액')]
    salespart = sales[KEY + list(aliases) + ages].rename(columns=aliases)
    panel = stores.merge(salespart, on=KEY, how='outer', validate='1:1', indicator='sales_store_join')
    panel['stores_observed'] = panel.sales_store_join.ne('right_only')
    panel['sales_observed'] = panel.sales_store_join.ne('left_only')
    # 만약 매출만 있는 키가 생겨도 명칭을 복구하고 수치는 결측으로 둔다.
    industry_dim = stores[['industry_code', 'industry_name']].drop_duplicates()
    check('K02: industry label mapping unique', industry_dim.industry_code.is_unique, len(industry_dim))
    panel['industry_name'] = panel.industry_code.map(industry_dim.set_index('industry_code').industry_name)
    panel = panel.drop(columns=['market_name', 'market_type', 'market_type_name']).merge(context, on=AREAKEY, how='left', validate='m:1')
    check('panel: union keys preserved', len(panel) == len(pd.concat([stores[KEY], sales[KEY]]).drop_duplicates()), len(panel))
    check('panel: sales total preserved', panel.sales_amount.sum() == sales['당월_매출_금액'].sum(), int(panel.sales_amount.sum()))
    check('panel: store total preserved', panel.total_store_count.sum() == stores.total_store_count.sum(), int(panel.total_store_count.sum()))
    check('panel: sales rows preserved', panel.sales_observed.sum() == len(sales), len(sales))
    panel['sales_missing_reason'] = np.select([panel.sales_observed, ~panel.industry_code.isin(sales.industry_code.unique())], ['observed', 'industry_not_in_sales_source'], default='no_sales_row_for_market_quarter_industry')
    panel['source_rate_over100'] = panel.opening_rate_source_pct.gt(100) | panel.closure_rate_source_pct.gt(100)
    panel['small_store_base_lt5'] = panel.total_store_count.lt(5) & panel.stores_observed
    panel['snapshot_mapping_source_class_count'] = panel.industry_code.map(mapping_n).fillna(0).astype('int16')
    panel['snapshot_mapping_available'] = panel.quarter_code.eq('20254') & panel.snapshot_mapping_source_class_count.gt(0)
    mapped['quarter_code'] = '20254'
    panel = panel.merge(mapped, on=KEY, how='left', validate='1:1')
    for c in ['snapshot_mapped_store_count', 'snapshot_mapped_unique_spatial_count', 'snapshot_membership_mapped_store_count']:
        panel.loc[panel.snapshot_mapping_available & panel[c].isna(), c] = 0
    # 공간·업종 대응 집계가 있지만 K02에는 없는 키도 별표에 보존한다.
    coverage_keys = mapped.merge(panel[KEY], on=KEY, how='left', indicator=True, validate='1:1')
    csv(coverage_keys[coverage_keys['_merge'].eq('left_only')].drop(columns='_merge'), REPORT / 'mapped_snapshot_keys_absent_from_panel.csv')
    panel = panel.sort_values(['market_code', 'industry_code', 'quarter_code']).reset_index(drop=True)
    # STEP 3の前の結合済みテーブル。
    parquet(panel, INTERIM / 'integrated_panel_step2_2025.parquet')
    feature(panel, 'sales_per_store', '점포당 분기 추정매출', ratio(panel.sales_amount, panel.total_store_count), '분기추정매출/전체점포수', 'K01 당월_매출_금액; K02 similr_induty_stor_co', '원/점포/분기', '상권·동일업종 매출 규모 비교', '상권×업종 평균 대리지표. 개별 점포 매출/이익 아님.')
    feature(panel, 'sales_per_transaction', '추정 매출 건당 금액', ratio(panel.sales_amount, panel.sales_transactions), '매출액/매출건수', 'K01 당월_매출_금액; 당월_매출_건수', '원/건', '객단가 대리변수', '건수는 고객 수가 아님. 구매자별 객단가 아님.')
    feature(panel, 'sales_per_1000_flow', '유동인구 1천 단위당 추정매출', ratio(panel.sales_amount * 1000, panel.floating_population), '매출액*1000/총유동인구', 'K01; K04 총_유동인구_수', '원/유동인구 1000단위', '유동 대비 매출 규모', '분모는 고유 방문자수가 아니므로 구매전환율/개인 지출로 해석 금지.')
    feature(panel, 'same_industry_store_density_km2', '동일업종 점포 밀도', ratio(panel.total_store_count, panel.polygon_area_m2 / 1e6), '전체점포수/(폴리곤면적/1e6)', 'K02 similr_induty_stor_co; K03 geometry', '점포/km²', '경쟁 강도', '면적이 작은 상권에서 값이 큼. 업종 내 비교.')
    feature(panel, 'same_industry_stores_per_1000_flow', '유동인구 1천 단위당 동일업종 점포', ratio(panel.total_store_count * 1000, panel.floating_population), '전체점포수*1000/총유동인구', 'K02; K04', '점포/유동인구 1000단위', '수요 대비 공급', '유동인구와 점포는 측정 방식이 다름. 부족업종의 확정 근거 아님.')
    feature(panel, 'franchise_share', '프랜차이즈 비중', ratio(panel.franchise_store_count, panel.total_store_count), '프랜차이즈점포/전체점포', 'K02 frc_stor_co; similr_induty_stor_co', '비율(0~1)', '경쟁 구조', '일반점포 stor_co를 분모로 사용하지 않음.')
    feature(panel, 'opening_per_current_store', '현 점포수 대비 개업 신고수', ratio(panel.opening_store_count, panel.total_store_count), '개업점포수/현재 전체점포수', 'K02 opbiz_stor_co; similr_induty_stor_co', '비율', '진입 활동', '기간 내 개업 흐름/관측 점포 재고 비. 1 초과 가능. 공식 개업률과 별도.')
    feature(panel, 'closure_per_current_store', '현 점포수 대비 폐업 신고수', ratio(panel.closure_store_count, panel.total_store_count), '폐업점포수/현재 전체점포수', 'K02 clsbiz_stor_co; similr_induty_stor_co', '비율', '이탈 활동', '1 초과 가능. 폐업 확률/생존율 아님. 공식 폐업률과 별도.')
    feature(panel, 'net_openings_per_current_store', '현 점포수 대비 순개업 신고수', ratio(panel.opening_store_count - panel.closure_store_count, panel.total_store_count), '(개업수-폐업수)/현재 전체점포수', 'K02', '비율', '진입·이탈 균형', '분기말 점포수 증감률과 동일하지 않음.')
    feature(panel, 'turnover_per_current_store', '현 점포수 대비 개·폐업 신고수', ratio(panel.opening_store_count + panel.closure_store_count, panel.total_store_count), '(개업수+폐업수)/현재 전체점포수', 'K02', '비율', '점포 교체 활동', '활동 흐름 지표. 고유 점포 교체확률 아님.')
    feature(panel, 'weekend_sales_share', '주말 매출 비중', ratio(panel.weekend_sales_amount, panel.weekday_sales_amount + panel.weekend_sales_amount), '주말매출/(주중매출+주말매출)', 'K01 주중/주말_매출_금액', '비율(0~1)', '요일별 수요 성격', '주중 5일·주말 2일의 기간 길이가 다름. 하루 평균 아님.')
    feature(panel, 'lunch_sales_share', '11~14시 매출 비중', ratio(panel.lunch_sales_amount, panel.sales_amount), '11~14시매출/총매출', 'K01 시간대_11~14_매출_금액; 당월_매출_금액', '비율(0~1)', '점심 수요', '시간당 매출 비교 아님.')
    feature(panel, 'evening_sales_share', '17~21시 매출 비중', ratio(panel.evening_sales_amount, panel.sales_amount), '17~21시매출/총매출', 'K01 시간대_17~21_매출_금액; 당월_매출_금액', '비율(0~1)', '저녁 수요', '점심 구간보다 시간이 길어 직접 효율 비교 금지.')
    feature(panel, 'classified_gender_sales_share', '성별 분류 매출의 총매출 대비 비중', ratio(panel.male_sales_amount + panel.female_sales_amount, panel.sales_amount), '(남성매출+여성매출)/총매출', 'K01 남성/여성/당월_매출_금액', '비율', '고객 분류 커버리지', '미분류/법인 매출 등 때문에 1보다 작을 수 있음. 임의 보정 안 함.')
    # 연령 비중은 연령 분류 금액 합을 분모로 하고 성별 합과 차이도 별도 검증한다.
    age_sum = panel[ages].sum(axis=1, min_count=len(ages))
    feature(panel, 'age20_30_sales_share_classified', '연령 분류 매출 중 20·30대 비중', ratio(panel['연령대_20_매출_금액'] + panel['연령대_30_매출_금액'], age_sum), '(20대+30대 매출)/6개 연령대 매출 합', 'K01 연령대별 매출금액 6열', '비율(0~1)', '목표 고객 구성', '성별합/총매출과 구분. 연령분류 매출 범위에서만 해석.')
    feature(panel, 'log1p_sales_amount', '추정매출 로그 변환', np.log1p(panel.sales_amount.where(panel.sales_amount.ge(0))), 'ln(1+매출액)', 'K01 당월_매출_금액', '로그(원)', '분포 왜도 완화', '매출 결측은 결측 유지. 원 금액과 혼용 금지.')
    # 지연값은 직전 분기가 실제로 존재할 때만 허용.
    group = panel.groupby(['market_code', 'industry_code'], sort=False)
    prev_q = group.quarter_code.shift().astype('Int64')
    adjacent = panel.quarter_code.astype('Int64').sub(prev_q).eq(1).fillna(False)
    for col, name, label in [('sales_amount', 'sales_qoq_change', '전분기 대비 추정매출 변화율'), ('total_store_count', 'stores_qoq_change', '전분기 대비 점포수 변화율')]:
        previous = group[col].shift().where(adjacent)
        feature(panel, name, label, ratio(panel[col] - previous, previous), '(당분기-직전분기)/직전분기; 분기 연속 조건', 'K01' if col == 'sales_amount' else 'K02', '비율', '분기간 변화 탐색', '2025Q1·누락 분기·직전값0은 결측. 계절성/일시변화이며 장기 성장 추세 아님.')
    supply = stores.groupby(AREAKEY, as_index=False).total_store_count.sum().rename(columns={'total_store_count': 'market_store_count_100industries'})
    panel = panel.merge(supply, on=AREAKEY, how='left', validate='m:1')
    feature(panel, 'industry_share_of_market_stores', '상권 내 100개 업종 점포 중 해당업종 비중', ratio(panel.total_store_count, panel.market_store_count_100industries), '업종점포수/상권 내 K02 100개 업종 점포수 합', 'K02 similr_induty_stor_co', '비율(0~1)', '업종 구성', 'K02가 제공하는 100개 업종 범위. 서울 모든 사업체의 구성비 아님.')
    feature(panel, 'snapshot_mapped_spatial_ambiguity_share', '업종 대응 점포의 공간 중복후보 비중', ratio(panel.snapshot_mapped_store_count - panel.snapshot_mapped_unique_spatial_count, panel.snapshot_mapped_store_count), '(대표배정수-유일매칭수)/대표배정수', 'S01 좌표; K03 영역; 잠정 업종 대응표', '비율(0~1)', '결합 민감도', '2025Q4만 계산. 0분모 결측. 큰 경우 유일매칭수도 함께 비교.')
    annual = panel.groupby(['market_code', 'industry_code'], as_index=False).agg(sales_quarters_observed=('sales_amount', 'count'), annual_sales_observed_sum=('sales_amount', lambda x: x.sum(min_count=1)), sales_quarter_mean=('sales_amount', 'mean'), sales_quarter_std=('sales_amount', lambda x: x.std(ddof=0)))
    annual['all_four_quarters_observed'] = annual.sales_quarters_observed.eq(4)
    feature(annual, 'sales_cv_four_quarters', '4개 분기 추정매출 변동계수', ratio(annual.sales_quarter_std, annual.sales_quarter_mean).where(annual.all_four_quarters_observed), 'std(2025 4분기 매출,ddof=0)/mean; 4개 관측 필요', 'K01 20251~20254 당월_매출_금액', '비율', '2025년 내 분기 변동', '4개 관측의 기술통계. 장기 안정성/위험예측 아님. 연간합은 관측분기 합으로 별도 표기.', '연도×상권×업종')
    annual['annual_sales_complete'] = annual.annual_sales_observed_sum.where(annual.all_four_quarters_observed)
    parquet(annual, OUT / 'annual_industry_variability_2025.parquet')
    csv(annual, OUT / 'annual_industry_variability_2025.csv')
    panel = panel.drop(columns=ages + flowcols + ['연령대_20_유동인구_수', '연령대_30_유동인구_수'])
    check('final panel: unique keys', not panel.duplicated(KEY).any(), len(panel))
    check('snapshot: no backward leakage', panel.loc[panel.quarter_code.ne('20254'), ['snapshot_store_count', 'snapshot_mapped_store_count']].isna().all().all(), 'Q1-Q3 snapshot columns null')
    check('missing sales: never filled zero', panel.loc[~panel.sales_observed, 'sales_amount'].isna().all(), int((~panel.sales_observed).sum()))
    check('features: no infinities', not np.isinf(panel.select_dtypes(include='number').to_numpy(dtype=float, na_value=np.nan)).any(), 'all numeric panel fields')
    for col in ['franchise_share', 'weekend_sales_share', 'industry_share_of_market_stores', 'age20_30_sales_share_classified', 'snapshot_mapped_spatial_ambiguity_share']:
        valid = panel[col].dropna()
        check(f'feature bounds: {col}', valid.between(0, 1.000001).all(), f'{valid.min()}..{valid.max()}')
    # 원본에서 읽은 값으로 개별 계산을 다시 확인한다.
    example = panel[panel.sales_observed & panel.total_store_count.gt(0)].iloc[len(sales) // 3]
    original_sales = sales.set_index(KEY).loc[tuple(example[k] for k in KEY), '당월_매출_금액']
    original_stores = stores.set_index(KEY).loc[tuple(example[k] for k in KEY), 'total_store_count']
    check('spot-check: sales/store from original cleaned rows', math.isclose(example.sales_per_store, original_sales / original_stores), '/'.join(str(example[k]) for k in KEY))
    parquet(panel, OUT / 'market_industry_features_2025.parquet')
    q4 = panel[panel.quarter_code.eq('20254')].copy()
    csv(q4, OUT / 'market_industry_features_2025q4.csv')
    # 고액/0점포/공간중복 등의 실제 값은 삭제하지 않고 감사표에 보존.
    anomaly = panel[panel.source_rate_over100 | (panel.sales_observed & panel.total_store_count.le(0))]
    csv(anomaly[KEY + ['market_name', 'industry_name', 'sales_amount', 'total_store_count', 'opening_rate_source_pct', 'closure_rate_source_pct', 'source_rate_over100']], REPORT / 'panel_attention_rows.csv')
    # 4분기 표본은 추천순위가 아니라 업종별 재현 확인 예시.
    examples = q4[q4.sales_observed & q4.total_store_count.ge(5)].sort_values(['industry_code', 'market_code']).groupby('industry_code').head(1)
    csv(examples, OUT / 'feature_examples_2025q4.csv')
    coverage_rows = []
    for quarter, d in context.groupby('quarter_code'):
        rec = {'quarter_code': quarter, 'markets': len(d)}
        rec.update({c: int(d[c].sum()) for c in ['flow_observed', 'facility_observed', 'worker_observed', 'resident_observed']})
        p = panel[panel.quarter_code.eq(quarter)]
        rec.update(panel_rows=len(p), sales_rows=int(p.sales_observed.sum()), no_sales_rows=int((~p.sales_observed).sum()))
        coverage_rows.append(rec)
    coverage = pd.DataFrame(coverage_rows)
    csv(coverage, REPORT / 'join_coverage_by_quarter.csv')
    # 연 1회 갱신 관련 실제 분기별 값의 반복 여부를 점검한다.
    stability = []
    for name, df, col in [('K05', facility, '집객시설_수'), ('K06', worker, '총_직장_인구_수'), ('K07', resident, '총_상주인구_수')]:
        g = df.groupby('market_code')[col].agg(['count', 'nunique'])
        stability.append({'dataset': name, 'markets_with_four_rows': int(g['count'].eq(4).sum()), 'four_rows_same_value': int((g['count'].eq(4) & g['nunique'].eq(1)).sum())})
    csv(pd.DataFrame(stability), REPORT / 'population_facility_update_audit.csv')
    age_gender_diff = age_sum - (panel.male_sales_amount + panel.female_sales_amount)  # index before last merge remains same order
    note('K01: age sum vs gender sum mismatch rows', int(age_gender_diff.dropna().ne(0).sum()))
    hashes_after = source_hashes()
    check('original raw files unchanged by pipeline', hashes_before.actual_sha256.tolist() == hashes_after.actual_sha256.tolist(), '18 files before/after')
    csv(pd.DataFrame(FEATURES), REPORT / 'feature_dictionary.csv')
    csv(pd.DataFrame(COLMAP), REPORT / 'column_renaming.csv')
    csv(pd.DataFrame(SOURCE_ROWS), REPORT / 'source_row_counts.csv')
    csv(pd.DataFrame(AUDIT), REPORT / 'validation_checks.csv')
    csv(pd.DataFrame(ARTIFACTS), REPORT / 'output_catalog.csv')
    column_rows = []
    feature_lookup = {f['variable']: f for f in FEATURES}
    for table, df in [('market_industry_features_2025', panel), ('market_quarter_context_2025', context), ('annual_industry_variability_2025', annual)]:
        for col in df:
            f = feature_lookup.get(col, {})
            column_rows.append({'table': table, 'column': col, 'dtype': str(df[col].dtype),
                                'null_count': int(df[col].isna().sum()), 'label': f.get('label', col),
                                'formula': f.get('formula', '원본/정제/상위 집계. STEP2 문서 및 column_renaming.csv 참조'),
                                'unit': f.get('unit', ''),
                                'aggregation_warning': '인구/시설/면적/소진공 상권수치는 업종행에 반복됨. 업종간 합산 금지.' if col in context.columns and col not in AREAKEY else ''})
    csv(pd.DataFrame(column_rows), REPORT / 'output_column_dictionary.csv')
    deferred = pd.DataFrame([
        ['sales_yoy_growth', '전년 동기 대비 매출 성장률', '2024 매출 미수집'],
        ['survival_probability', '개별 점포 생존확률', '개별 개·폐업 이력/정의 부족'],
        ['budget_feasibility', '예산 적합성', '임대료·보증금·권리금·시설비 없음'],
        ['profit_margin', '영업이익률', '매입/인건비/임대료 등 비용 없음'],
        ['consumer_conversion_rate', '방문자 구매전환율', '고유 방문자/구매자 매칭 없음'],
        ['long_term_growth_score', '장기 성장·안정성 점수', '1년 관측만 존재; STEP 4 별도 설계'],
    ], columns=['variable', 'label', 'reason_unavailable'])
    csv(deferred, REPORT / 'deferred_features.csv')
    summary = {'generated_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
               'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__, 'geopandas': gpd.__version__,
               'panel_rows': len(panel), 'q4_rows': len(q4), 'context_rows': len(context),
               'sales_rows': int(panel.sales_observed.sum()), 'sales_unobserved_rows': int((~panel.sales_observed).sum()),
               'sales_unsupported_industry_rows': int(panel.sales_missing_reason.eq('industry_not_in_sales_source').sum()),
               'zero_stores_with_sales_rows': int((panel.sales_observed & panel.total_store_count.le(0)).sum()),
               'source_rate_over100_rows': int(panel.source_rate_over100.sum()),
               'computed_feature_count': len(FEATURES), 'validation_passed': sum(x['passed'] is True for x in AUDIT),
               'validation_failed': sum(x['passed'] is False for x in AUDIT), 'spatial': spatial,
               'area_ratio_median': float(area.published_to_polygon_area_ratio.median()),
               'area_ratio_min': float(area.published_to_polygon_area_ratio.min()), 'area_ratio_max': float(area.published_to_polygon_area_ratio.max()),
               'invalid_geometries_before': invalid_before, 'facility_component_blanks_imputed': blank_count,
               'facility_total_mismatch_rows_2025': int(facility.facility_total_mismatch.sum()),
               'opening_closure_denominator_audit': rate_summary, 'join_coverage': coverage.to_dict('records')}
    (REPORT / 'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    # 작은 결과표: 보고서/워크북 작성용이며 대규모 패널을 재적재하지 않아도 됨.
    samplecols = ['market_code', 'market_name', 'industry_code', 'industry_name', 'sales_amount', 'total_store_count', 'sales_per_store', 'franchise_store_count', 'franchise_share']
    payload = {'summary': summary, 'features': FEATURES, 'coverage': coverage.to_dict('records'),
               'samples': json.loads(examples[samplecols].head(20).to_json(orient='records', force_ascii=False)),
               'checks': AUDIT}
    (WORK / 'outputs/workbook_payload.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    build()
