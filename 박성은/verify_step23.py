"""저장된 결과를 다시 읽어 원본·독립 계산과 비교하는 인수 검사."""
from pathlib import Path
import json
import sys

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'seoul-commercial-analysis'
if (ROOT / '.analysis_deps').exists():
    sys.path.insert(0, str(ROOT / '.analysis_deps'))
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import intersects

P = ROOT / 'data/processed/park_step23'
I = ROOT / 'data/interim/park_step23'
R = Path(__file__).resolve().parent / 'reports'
KEY = ['quarter_code', 'market_code', 'industry_code']
results = []


def test(name, ok, detail=''):
    results.append({'check': name, 'passed': bool(ok), 'detail': str(detail)})
    if not ok:
        raise AssertionError(name + ': ' + str(detail))


panel = pd.read_parquet(P / 'market_industry_features_2025.parquet')
context = pd.read_parquet(P / 'market_quarter_context_2025.parquet')
step2 = pd.read_parquet(I / 'integrated_panel_step2_2025.parquet')
annual = pd.read_parquet(P / 'annual_industry_variability_2025.parquet')
snapshot = pd.read_parquet(I / 'semas_store_spatial_2025q4.parquet')
edges = pd.read_parquet(I / 'semas_spatial_candidates.parquet')
native = pd.read_parquet(P / 'semas_native_industry_2025q4.parquet')
membership = pd.read_parquet(P / 'semas_all_memberships_industry_2025q4.parquet')
test('saved panel keys unique', not panel.duplicated(KEY).any())
test('step2 vs step3 identical keys', pd.MultiIndex.from_frame(panel[KEY]).sort_values().equals(pd.MultiIndex.from_frame(step2[KEY]).sort_values()))
test('saved context complete grid', len(context) == 1650*4 and not context.duplicated(KEY[:2]).any())
test('saved code types preserved', all(pd.api.types.is_string_dtype(panel[c]) for c in KEY))
q4csv = pd.read_csv(P / 'market_industry_features_2025q4.csv', dtype={c:'string' for c in KEY}, low_memory=False)
test('CSV/Parquet row and key agreement', len(q4csv) == panel.quarter_code.eq('20254').sum() and set(map(tuple,q4csv[KEY].to_numpy())) == set(map(tuple,panel.loc[panel.quarter_code.eq('20254'),KEY].to_numpy())))
rawk01 = pd.read_csv(next((ROOT/'data/raw').rglob('*추정매출-상권*csv')),encoding='cp949',dtype={'기준_년분기_코드':'string','상권_코드':'string','서비스_업종_코드':'string'})
rawk02 = pd.read_csv(next((ROOT/'data/raw').rglob('*점포-상권*csv')),encoding='cp949',dtype={'stdr_yyqu_cd':'string','trdar_cd':'string','svc_induty_cd':'string'})
sales_source = rawk01.rename(columns=dict(zip(['기준_년분기_코드','상권_코드','서비스_업종_코드','당월_매출_금액'], KEY+['original_sales'])))[KEY+['original_sales']]
reconciled = panel[KEY+['sales_amount']].merge(sales_source,on=KEY,how='inner',validate='1:1')
test('every saved sales value equals raw K01', len(reconciled)==len(rawk01) and reconciled.sales_amount.eq(reconciled.original_sales).all())
stores_source = rawk02.rename(columns=dict(zip(['stdr_yyqu_cd','trdar_cd','svc_induty_cd','similr_induty_stor_co'],KEY+['original_store_count'])))[KEY+['original_store_count']]
reconciled = panel[KEY+['total_store_count']].merge(stores_source,on=KEY,how='inner',validate='1:1')
test('every saved store value equals raw K02', len(reconciled)==len(rawk02) and reconciled.total_store_count.eq(reconciled.original_store_count).all())
test('sales missing preserved after save', panel.loc[~panel.sales_observed,'sales_amount'].isna().all())
test('S01 not propagated backward', panel.loc[panel.quarter_code.ne('20254'),[c for c in panel if c.startswith('snapshot_') and c not in ['snapshot_mapping_source_class_count','snapshot_mapping_available']]].isna().all().all())
valid=panel.sales_observed & panel.total_store_count.gt(0)
test('all sales/store formulas', np.allclose(panel.loc[valid,'sales_per_store'].astype(float),panel.loc[valid,'sales_amount'].astype(float)/panel.loc[valid,'total_store_count'].astype(float)))
denzero=panel.total_store_count.le(0) | panel.total_store_count.isna()
test('all stock denominator zero/missing yield null', panel.loc[denzero,['sales_per_store','franchise_share','closure_per_current_store','opening_per_current_store']].isna().all().all())
# 그룹 shift 대신 직전 분기 키를 +1 한 테이블로 독립적인 self-join.
previous = panel[KEY+['sales_amount']].copy()
previous.quarter_code=(previous.quarter_code.astype(int)+1).astype('string')
previous=previous.rename(columns={'sales_amount':'previous_sales'})
joined=panel.merge(previous,on=KEY,how='left',validate='1:1')
expected=(joined.sales_amount-joined.previous_sales)/joined.previous_sales.where(joined.previous_sales.gt(0))
test('qoq equals exact previous-quarter self-join', np.allclose(joined.sales_qoq_change.to_numpy(dtype=float,na_value=np.nan),expected.to_numpy(dtype=float,na_value=np.nan),equal_nan=True))
test('Q1 qoq always null', panel.loc[panel.quarter_code.eq('20251'),['sales_qoq_change','stores_qoq_change']].isna().all().all())
test('CV requires 4 quarters', annual.loc[~annual.all_four_quarters_observed,'sales_cv_four_quarters'].isna().all())
test('partial annual total not called complete', annual.loc[~annual.all_four_quarters_observed,'annual_sales_complete'].isna().all())
complete = annual[annual.all_four_quarters_observed].sample(n=20,random_state=2025)
for row in complete.itertuples():
    values=panel.loc[panel.market_code.eq(row.market_code)&panel.industry_code.eq(row.industry_code),'sales_amount'].to_numpy(dtype=float)
    test(f'CV independent sample {row.market_code}/{row.industry_code}', np.isclose(np.std(values,ddof=0)/np.mean(values),row.sales_cv_four_quarters))
test('snapshot ids remain unique', snapshot.store_id.is_unique and len(snapshot)==534978)
test('spatial categories partition original rows', snapshot.spatial_candidate_count.eq(0).sum()+snapshot.spatial_candidate_count.eq(1).sum()+snapshot.spatial_candidate_count.gt(1).sum()==len(snapshot))
test('native counts equal primary assigned stores', native.snapshot_store_count.sum()==snapshot.market_code.notna().sum())
test('all membership counts equal candidate edges', membership.snapshot_membership_store_count.sum()==len(edges))
test('candidate counts equal saved snapshot counts', snapshot.set_index('store_id').spatial_candidate_count.eq(edges.groupby('store_id').size().reindex(snapshot.store_id).fillna(0).to_numpy()).all())
area=gpd.read_parquet(I/'market_polygons_5181.parquet')
test('saved polygons valid EPSG:5181', area.crs.to_epsg()==5181 and area.is_valid.all())
sample=snapshot[snapshot.market_code.notna()].sample(n=500,random_state=2025)
points=gpd.GeoSeries(gpd.points_from_xy(sample.longitude,sample.latitude),crs=4326).to_crs(5181)
polys=area.set_index('market_code').geometry.reindex(sample.market_code)
test('500 assigned stores intersect assigned polygons', intersects(points.to_numpy(),polys.to_numpy()).all())
primary=edges.sort_values(['store_id','candidate_area_m2','market_code']).drop_duplicates('store_id')
test('primary assignment follows declared smallest-area rule', primary.set_index('store_id').market_code.eq(snapshot.set_index('store_id').market_code.reindex(primary.store_id).to_numpy()).all())
test('all-membership area count >= primary count', (context.loc[context.quarter_code.eq('20254'),'snapshot_all_membership_store_count']>=context.loc[context.quarter_code.eq('20254'),'snapshot_store_count']).all())
mappedq4=panel[panel.snapshot_mapping_available]
test('mapped membership counts >= primary >= unique', ((mappedq4.snapshot_membership_mapped_store_count>=mappedq4.snapshot_mapped_store_count)&(mappedq4.snapshot_mapped_store_count>=mappedq4.snapshot_mapped_unique_spatial_count)).all())
fac=context[context.facility_observed]
test('unobserved facility rows not imputed zero', context.loc[~context.facility_observed,['facility_count_source','facility_components_sum']].isna().all().all())
test('independent context vs panel join values', panel.floating_population.equals(panel[KEY[:2]].merge(context[KEY[:2]+['floating_population']],on=KEY[:2],how='left',validate='m:1').floating_population))
for c in ['worker_share_of_worker_resident','resident_share_of_worker_resident','flow_20_30_share','flow_peak_band_share']:
    test('context ratio in [0,1]: '+c,context[c].dropna().between(0,1.00001).all())
dictionary=pd.read_csv(R/'feature_dictionary.csv')
test('all defined features exist in saved outputs', set(dictionary.variable)<=set(panel.columns)|set(context.columns)|set(annual.columns)|set(native.columns))
out={'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'checks':results}
(R/'independent_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='checks'},ensure_ascii=False))
