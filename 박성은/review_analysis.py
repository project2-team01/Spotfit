"""분석 설명서의 근거: 원본/저장 결과를 읽어 32개 변수와 해석상 제약을 재검토.

실행: 저장소 최상위에서 python 박성은/review_analysis.py
기존 분석 파일은 수정하지 않고 reports/analysis_review_evidence.json만 생성한다.
"""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'seoul-commercial-analysis'
if (ROOT / '.analysis_deps').exists():
    sys.path.insert(0, str(ROOT / '.analysis_deps'))
import numpy as np
import pandas as pd

OUT = ROOT / 'data/processed/park_step23'
INTERIM = ROOT / 'data/interim/park_step23'
KEY = ['quarter_code', 'market_code', 'industry_code']
AK = KEY[:2]
checks = []


def check(name, condition, detail=''):
    checks.append({'check': name, 'passed': bool(condition), 'detail': str(detail)})


def num(v):
    return pd.to_numeric(v, errors='raise')


def safe_ratio(a, b):
    return a / b.where(b > 0)


def compare(name, actual, expected):
    a = np.asarray(pd.Series(actual).to_numpy(dtype=float, na_value=np.nan))
    b = np.asarray(pd.Series(expected).to_numpy(dtype=float, na_value=np.nan))
    same_null = np.array_equal(np.isnan(a), np.isnan(b))
    same = np.isclose(a, b, rtol=1e-10, atol=1e-10, equal_nan=True)
    return {'check': name, 'passed': bool(same_null and same.all()),
            'evaluated_rows': len(a), 'non_null_rows': int(np.isfinite(a).sum()),
            'mismatched_rows': int((~same).sum())}


def raw(pattern, rename, encoding='cp949'):
    p = list((ROOT / 'data/raw').rglob(pattern))
    if len(p) != 1:
        raise ValueError(f'Expected one file for {pattern}')
    d = pd.read_csv(p[0], encoding=encoding, usecols=list(rename), dtype='string').rename(columns=rename)
    for c in d:
        if c not in KEY:
            d[c] = num(d[c])
    return d[d.quarter_code.isin(['20251', '20252', '20253', '20254'])]


p = pd.read_parquet(OUT / 'market_industry_features_2025.parquet')
c = pd.read_parquet(OUT / 'market_quarter_context_2025.parquet')
annual = pd.read_parquet(OUT / 'annual_industry_variability_2025.parquet')
native = pd.read_parquet(OUT / 'semas_native_industry_2025q4.parquet')
snapshot = pd.read_parquet(INTERIM / 'semas_store_spatial_2025q4.parquet')
edges = pd.read_parquet(INTERIM / 'semas_spatial_candidates.parquet')
dictionary = pd.read_csv(HERE / 'reports/feature_dictionary.csv')

hash_ok = 0
for line in (ROOT / 'data/metadata/checksums.sha256').read_text(encoding='utf-8').splitlines():
    expected, rel = line.split(maxsplit=1)
    h = hashlib.sha256()
    with (ROOT / rel.lstrip('*')).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    hash_ok += h.hexdigest() == expected
check('original 18 file hashes still match', hash_ok == 18, hash_ok)
check('panel keys unique', not p.duplicated(KEY).any(), len(p))
check('market quarter keys unique and complete', not c.duplicated(AK).any() and len(c) == 1650*4, len(c))

km = {'기준_년분기_코드':'quarter_code', '상권_코드':'market_code', '서비스_업종_코드':'industry_code'}
salesmap = {'당월_매출_금액':'raw_sales', '당월_매출_건수':'raw_transactions',
            '주중_매출_금액':'raw_weekday', '주말_매출_금액':'raw_weekend',
            '시간대_11~14_매출_금액':'raw_lunch', '시간대_17~21_매출_금액':'raw_evening',
            '남성_매출_금액':'raw_male', '여성_매출_금액':'raw_female'}
agecols = {f'연령대_{a}_매출_금액': f'raw_age_{a}' for a in ['10','20','30','40','50','60_이상']}
sales = raw('*추정매출-상권*csv', km | salesmap | agecols)
stores = raw('*점포-상권*csv', {'stdr_yyqu_cd':'quarter_code', 'trdar_cd':'market_code', 'svc_induty_cd':'industry_code',
    'similr_induty_stor_co':'raw_stores', 'stor_co':'raw_independent', 'frc_stor_co':'raw_franchise',
    'opbiz_stor_co':'raw_openings', 'clsbiz_stor_co':'raw_closures'})
fm = {'기준_년분기_코드':'quarter_code', '상권_코드':'market_code'}
bands = ['00_06','06_11','11_14','14_17','17_21','21_24']
flow = raw('seoul_flpop_trdar_2025_sheet.csv', fm | {'총_유동인구_수':'raw_flow', '연령대_20_유동인구_수':'raw_flow20', '연령대_30_유동인구_수':'raw_flow30'} | {f'시간대_{b}_유동인구_수': f'raw_flow_{b}' for b in bands})
worker = raw('seoul_wrcpop_trdar_all_sheet.csv', fm | {'총_직장_인구_수':'raw_worker'})
resident = raw('seoul_repop_trdar_all_sheet.csv', fm | {'총_상주인구_수':'raw_resident'})
facility_path = ROOT / 'data/raw/seoul/seoul_facility_trdar_all_sheet.csv'
fc = pd.read_csv(facility_path, encoding='cp949', dtype='string')
facility_cols = [x for x in fc if x.endswith('_수') and x != '집객시설_수']
fc = fc.rename(columns=fm)
fc = fc[fc.quarter_code.isin(['20251','20252','20253','20254'])].copy()
fc['raw_facility_sum'] = fc[facility_cols].apply(num).fillna(0).sum(axis=1)

base = p[KEY].merge(sales, on=KEY, how='left', validate='1:1').merge(stores, on=KEY, how='left', validate='1:1').merge(flow[AK+['raw_flow']],on=AK,how='left',validate='m:1')
check('all 85,732 raw sales keys retained', base.raw_sales.notna().sum() == len(sales), len(sales))
check('all 304,775 raw store keys retained', base.raw_stores.notna().sum() == len(stores), len(stores))
checks.append(compare('all raw sales amounts retained', p.sales_amount, base.raw_sales))
checks.append(compare('all raw stock counts retained', p.total_store_count, base.raw_stores))
check('sales absence preserved as null', p.loc[~p.sales_observed,'sales_amount'].isna().all())
check('Q1-Q3 snapshot values not backfilled', p.loc[p.quarter_code.ne('20254'),['snapshot_store_count','snapshot_mapped_store_count']].isna().all().all())

expected = {}
r = safe_ratio
expected['sales_per_store'] = r(base.raw_sales, base.raw_stores)
expected['sales_per_transaction'] = r(base.raw_sales, base.raw_transactions)
expected['sales_per_1000_flow'] = r(base.raw_sales*1000, base.raw_flow)
expected['same_industry_store_density_km2'] = r(base.raw_stores, p.polygon_area_m2/1e6)
expected['same_industry_stores_per_1000_flow'] = r(base.raw_stores*1000, base.raw_flow)
expected['franchise_share'] = r(base.raw_franchise, base.raw_stores)
expected['opening_per_current_store'] = r(base.raw_openings, base.raw_stores)
expected['closure_per_current_store'] = r(base.raw_closures, base.raw_stores)
expected['net_openings_per_current_store'] = r(base.raw_openings-base.raw_closures, base.raw_stores)
expected['turnover_per_current_store'] = r(base.raw_openings+base.raw_closures, base.raw_stores)
expected['weekend_sales_share'] = r(base.raw_weekend,base.raw_weekday+base.raw_weekend)
expected['lunch_sales_share'] = r(base.raw_lunch,base.raw_sales)
expected['evening_sales_share'] = r(base.raw_evening,base.raw_sales)
expected['classified_gender_sales_share'] = r(base.raw_male+base.raw_female,base.raw_sales)
expected['age20_30_sales_share_classified'] = r(base.raw_age_20+base.raw_age_30,base[list(agecols.values())].sum(axis=1,min_count=6))
expected['log1p_sales_amount'] = np.log1p(base.raw_sales.where(base.raw_sales>=0))
for variable, src in [('sales_qoq_change','raw_sales'),('stores_qoq_change','raw_stores')]:
    prev = base[KEY+[src]].copy()
    prev.quarter_code = (prev.quarter_code.astype(int)+1).astype('string')
    prev = prev.rename(columns={src:'previous_value'})
    tmp = base[KEY+[src]].merge(prev,on=KEY,how='left',validate='1:1')
    expected[variable] = r(tmp[src]-tmp.previous_value,tmp.previous_value)
denominator = base.groupby(AK).raw_stores.transform('sum')
expected['industry_share_of_market_stores'] = r(base.raw_stores,denominator)
expected['snapshot_mapped_spatial_ambiguity_share'] = r(p.snapshot_mapped_store_count-p.snapshot_mapped_unique_spatial_count,p.snapshot_mapped_store_count)
feature_checks = [compare(k,p[k],v) for k,v in expected.items()]

context_raw = c[AK].merge(flow,on=AK,how='left',validate='1:1').merge(worker,on=AK,how='left',validate='1:1').merge(resident,on=AK,how='left',validate='1:1').merge(fc[AK+['raw_facility_sum']],on=AK,how='left',validate='1:1')
flowtime = [f'raw_flow_{b}' for b in bands]
context_expected = {
    'worker_share_of_worker_resident':r(context_raw.raw_worker,context_raw.raw_worker+context_raw.raw_resident),
    'resident_share_of_worker_resident':r(context_raw.raw_resident,context_raw.raw_worker+context_raw.raw_resident),
    'flow_20_30_share':r(context_raw.raw_flow20+context_raw.raw_flow30,context_raw.raw_flow),
    'flow_peak_band_share':r(context_raw[flowtime].max(axis=1,skipna=False),context_raw[flowtime].sum(axis=1,min_count=6)),
    'facility_density_km2':r(context_raw.raw_facility_sum,c.polygon_area_m2/1e6),
}
assigned = snapshot[snapshot.market_code.notna()]
native_expected = assigned.groupby(['market_code','semas_industry_code']).size().rename('n').reset_index()
nn = native[['market_code','semas_industry_code','snapshot_store_count']].merge(native_expected,on=['market_code','semas_industry_code'],validate='1:1')
check('native source-class counts reconcile with store assignments', len(nn)==len(native_expected) and nn.snapshot_store_count.eq(nn.n).all())
native_share = native.snapshot_store_count/native.groupby('market_code').snapshot_store_count.transform('sum')
feature_checks.append(compare('snapshot_native_industry_share',native.snapshot_native_industry_share,native_share))
native_math = native[['market_code']].copy()
native_math['hhi'] = native_share**2
native_math['entropy'] = -native_share*np.log(native_share)
agg = assigned.groupby('market_code').agg(n=('store_id','size'),distinct=('semas_industry_code','nunique'))
agg['unique_n'] = assigned[assigned.spatial_candidate_count.eq(1)].groupby('market_code').size()
agg.unique_n=agg.unique_n.fillna(0)
agg = agg.join(native_math.groupby('market_code')[['hhi','entropy']].sum())
agg['memberships'] = edges.groupby('market_code').size()
q4 = c.quarter_code.eq('20254')
def mapped_area(col, zero=False):
    result=c.market_code.map(agg[col])
    if zero:
        result=result.fillna(0)
    return result.where(q4)
context_expected |= {
    'snapshot_distinct_industries':mapped_area('distinct',zero=True),
    'snapshot_industry_hhi':mapped_area('hhi'),
    'snapshot_industry_entropy':mapped_area('entropy'),
    'snapshot_spatial_ambiguity_share':r(mapped_area('n',zero=True)-mapped_area('unique_n',zero=True),mapped_area('n',zero=True)),
    'snapshot_membership_store_density_km2':r(c.market_code.map(edges.groupby('market_code').size()).fillna(0).where(q4),c.polygon_area_m2/1e6),
}
feature_checks += [compare(k,c[k],v) for k,v in context_expected.items()]
source_annual = sales.groupby(KEY[1:]).raw_sales.agg(['count','mean'])
source_annual['sd'] = sales.groupby(KEY[1:]).raw_sales.std(ddof=0)
source_annual['cv']=r(source_annual.sd,source_annual['mean']).where(source_annual['count']==4)
cv = annual[KEY[1:]].merge(source_annual[['cv']],on=KEY[1:],how='left',validate='1:1').cv
feature_checks.append(compare('sales_cv_four_quarters',annual.sales_cv_four_quarters,cv))
check('all 32 dictionary variables covered', set(x['check'] for x in feature_checks)==set(dictionary.variable), len(feature_checks))

q4p = p[p.quarter_code.eq('20254')]
coffee = q4p[q4p.industry_code.eq('CS100010') & q4p.market_type.eq('A') & q4p.total_store_count.ge(5) & q4p.sales_observed]
local_case = coffee[coffee.market_name.str.contains('성수',na=False)]
example = (local_case if len(local_case) else coffee).sort_values('market_code').iloc[0]
example_cols = ['quarter_code','market_code','market_name','industry_code','industry_name','sales_amount',
    'total_store_count','franchise_store_count','sales_per_store','franchise_share','same_industry_store_density_km2',
    'floating_population','weekend_sales_share','sales_qoq_change']
source_gender_diff = sales[list(agecols.values())].sum(axis=1,min_count=6)-(sales.raw_male+sales.raw_female)
current_files={}
for fname in ['build_step23.py','verify_step23.py','config/industry_crosswalk.csv']:
    data=(HERE/fname).read_bytes().replace(b'\r\n',b'\n')
    current_files[fname]=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

q4context=c[c.quarter_code.eq('20254')]
overlap = q4context[q4context.snapshot_all_membership_store_count.gt(0)].copy()
overlap['assignment_reduction'] = 1-overlap.snapshot_store_count/overlap.snapshot_all_membership_store_count
largest_reduction=overlap.sort_values('assignment_reduction',ascending=False).iloc[0]
support = p.industry_code.isin(sales.industry_code.unique())
evidence = {
    'reviewed_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
    'review_baseline_commit':'39e204fc0e41c100912d2e3685ea4acb486575ec',
    'scope':'Same-author review of frozen raw files, stored output, 32 formulas and interpretation; not external expert certification',
    'analysis_code_git_blobs':current_files,
    'structural_checks':checks,'feature_formula_checks':feature_checks,
    'formula_checks_passed':sum(x['passed'] for x in feature_checks),
    'formula_checks_failed':sum(not x['passed'] for x in feature_checks),
    'structure_checks_passed':sum(x['passed'] for x in checks),
    'structure_checks_failed':sum(not x['passed'] for x in checks),
    'panel_rows':len(p),'possible_quarter_market_industry_grid_rows':4*1650*100,
    'unrepresented_grid_keys':4*1650*100-len(p),'sales_rows':int(p.sales_observed.sum()),
    'unobserved_sales_rows':int((~p.sales_observed).sum()),'observed_sales_share_of_panel':float(p.sales_observed.mean()),
    'unsupported_sales_industry_rows':int((~support).sum()),
    'supported_industry_no_sales_rows':int((support&~p.sales_observed).sum()),
    'supported_industry_panel_rows':int(support.sum()),
    'q4_panel_rows':len(q4p),'q4_sales_rows':int(q4p.sales_observed.sum()),
    'sales_rows_with_store_count_under5':int((p.sales_observed&p.total_store_count.lt(5)).sum()),
    'all_rows_with_zero_store_count':int(p.total_store_count.eq(0).sum()),
    'four_quarter_complete_sales_groups':int(annual.all_four_quarters_observed.sum()),
    'annual_market_industry_groups':len(annual),
    'feature_grain_counts':{str(k):int(v) for k,v in dictionary.groupby('grain').size().items()},
    'source_age_gender_sum_difference':{'nonzero_rows':int(source_gender_diff.ne(0).sum()),'max_abs_won':float(source_gender_diff.abs().max()),'median_abs_won':float(source_gender_diff.abs().median())},
    'example':json.loads(example[example_cols].to_json(force_ascii=False)),
    'largest_assignment_reduction_example':json.loads(largest_reduction[['market_code','market_name','snapshot_store_count','snapshot_all_membership_store_count','assignment_reduction']].to_json(force_ascii=False)),
}
result=HERE/'reports/analysis_review_evidence.json'
result.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in evidence.items() if k not in ['structural_checks','feature_formula_checks']},ensure_ascii=False,indent=2))
if any(not r['passed'] for r in checks+feature_checks):
    raise SystemExit(1)
