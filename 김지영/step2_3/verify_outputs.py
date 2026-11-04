from pathlib import Path
import pandas as pd,numpy as np,json,re
from urllib.parse import unquote
out=Path(__file__).resolve().parent; root=out.parents[1]; ids={'quarter':str,'trdar_code':str,'industry_code':str}
p=pd.read_csv(out/'data/fact_trdar_industry_quarter.csv.gz',dtype=ids)
c=pd.read_csv(out/'data/trdar_quarter_context.csv.gz',dtype=ids)
a=pd.read_csv(out/'data/annual_features.csv.gz',dtype=ids)
b=pd.read_csv(out/'data/semas_spatial_bridge.csv.gz',dtype={'store_id':str,'trdar_code':str})
d=pd.read_csv(out/'feature_dictionary.csv'); manifest=json.loads((out/'manifest.json').read_text()); qa=pd.read_csv(out/'qa/validation_checks.csv')
assert qa['passed'].all()
assert len(p)==manifest['summary']['fact_rows']==304775
assert len(c)==6600 and len(a)==77694
assert p.merge(c[['quarter','trdar_code','floating_population']],on=['quarter','trdar_code'],validate='many_to_one').shape[0]==len(p)
# 파일을 다시 읽은 뒤 원본 분기 매출을 독립적으로 집계해 대조한다.
raw=pd.read_csv(next((root/'data/raw/seoul/extracted/seoul_sales_trdar_2025').glob('*.csv')),encoding='cp949',dtype={'기준_년분기_코드':str})
expected=raw.groupby('기준_년분기_코드')['당월_매출_금액'].sum(); actual=p.groupby('quarter')['sales_amount'].sum()
np.testing.assert_allclose(expected.to_numpy(),actual.to_numpy(),rtol=1e-14)
# 저장 후 숫자 형식·결측 마커·분기 순서 조건을 확인한다.
assert p.loc[~p['sales_observed'],'sales_amount'].isna().all()
assert p.loc[p['store_count']==0,'close_count_ratio'].isna().all()
assert p.loc[p['quarter']=='20251','sales_qoq_change'].isna().all()
assert a.loc[a['annual_sales_complete'].notna(),'observed_sales_quarters'].eq(4).all()
assert b['store_id'].nunique()==534978
assert not d['variable'].duplicated().any() and len(d)==57
assert d['availability'].eq('산출').sum()==52
# 저장 후에도 상대지수의 표본 조건이 유지되는지 확인한다.
z=p[p['sales_vs_industry_median'].notna()]
assert z['industry_peer_count'].ge(30).all() and z['store_count'].ge(5).all() and z['main_analysis_eligible'].all()
result={'saved_file_checks_passed':True,'runtime_check_rows':len(qa),'fact_rows':len(p),'context_rows':len(c),'annual_rows':len(a),'spatial_bridge_rows':len(b),'semas_aggregates_rows':len(pd.read_csv(out/'data/semas_q4_industry_counts.csv.gz')),'dictionary_calculated':52,'dictionary_deferred':5,'tourist_excluded_complete_annual_cells':int((a['annual_sales_complete'].notna()&a['main_analysis_eligible']).sum())}
(out/'qa/post_save_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
