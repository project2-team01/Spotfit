"""2025년 원본 → 검증 가능한 STEP 2·3 분석 테이블. 원본은 읽기 전용."""
from pathlib import Path
import hashlib,json,platform
import numpy as np
import pandas as pd
import geopandas as gpd
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent; RAW=ROOT/'data/raw'
DATA=OUT/'data'; QA=OUT/'qa'
for d in [DATA,QA]: d.mkdir(exist_ok=True)
inputs=[]; checks=[]; schemas=[]; features=[]
def read(rel,encoding='cp949',**kw):
 p=RAW/rel; inputs.append(p); return pd.read_csv(p,encoding=encoding,dtype=str,**kw)
def check(name,ok,detail):
 checks.append({'check':name,'passed':bool(ok),'detail':str(detail)})
 if not ok: raise ValueError(f'{name}: {detail}')
def unique(d,key,name):
 check(name+'_key_nonnull',not d[key].isna().any().any(),key)
 check(name+'_key_unique',not d.duplicated(key).any(),f'rows={len(d)}; key={key}')
def num(d,cols):
 for c in cols: d[c]=pd.to_numeric(d[c],errors='raise')
 return d
# 분모가 0이거나 결측이면 계산 불가로 남긴다.
def ratio(a,b): return a/b.where(b>0)
def write(d,name,key):
 unique(d,key,name)
 for c in d.select_dtypes(include='number'):
  check(name+'_'+c+'_finite',not np.isinf(d[c].to_numpy(dtype=float,na_value=np.nan)).any(),'infinity=0')
 path=DATA/(name+'.csv.gz'); d.to_csv(path,index=False,encoding='utf-8-sig',compression={'method':'gzip','mtime':0})
 for c in d: schemas.append({'table':name,'column':c,'dtype':str(d[c].dtype),'missing_rows':int(d[c].isna().sum()),'key':c in key})
 return path
KEY=['quarter','trdar_code','industry_code']
common={'기준_년분기_코드':'quarter','상권_코드':'trdar_code','상권_코드_명':'trdar_name_source','상권_구분_코드':'trdar_type_code_source','상권_구분_코드_명':'trdar_type_source','서비스_업종_코드':'industry_code','서비스_업종_코드_명':'industry_name'}
s=read('seoul/extracted/seoul_sales_trdar_2025/서울시 상권분석서비스(추정매출-상권)_2025년.csv').rename(columns=common)
rename={'당월_매출_금액':'sales_amount','당월_매출_건수':'sales_count','주중_매출_금액':'weekday_sales','주말_매출_금액':'weekend_sales','남성_매출_금액':'male_sales','여성_매출_금액':'female_sales'}
for k,d in enumerate('월화수목금토일'): rename[f'{d}요일_매출_금액']=f'day_{k+1}_sales'
for tag,orig,broken in zip(['00_06','06_11','11_14','14_17','17_21','21_24'],['00~06','06~11','11~14','14~17','17~21','21~24'],['06','11','14','17','21','24']):
 rename[f'시간대_{orig}_매출_금액']=f'time_{tag}_sales'; rename[f'시간대_건수~{broken}_매출_건수']=f'time_{tag}_count'
for tag in ['10','20','30','40','50','60_이상']: rename[f'연령대_{tag}_매출_금액']='age_'+tag.replace('이상','plus')+'_sales'
s=s.rename(columns=rename); source_cols=list(rename.values()); num(s,source_cols); unique(s,KEY,'sales')
s=s[s['quarter'].str.startswith('2025')].copy()
t=read('seoul/extracted/seoul_store_trdar_2025/서울시 상권분석서비스(점포-상권)_2025년.csv').rename(columns={'stdr_yyqu_cd':'quarter','trdar_cd':'trdar_code','trdar_cd_nm':'trdar_name_source','trdar_se_cd':'trdar_type_code_source','trdar_se_cd_nm':'trdar_type_source','svc_induty_cd':'industry_code','svc_induty_cd_nm':'industry_name','stor_co':'independent_store_count','similr_induty_stor_co':'store_count','frc_stor_co':'franchise_store_count','opbiz_stor_co':'open_count','clsbiz_stor_co':'close_count','opbiz_rt':'reported_open_rate','clsbiz_rt':'reported_close_rate'})
t=t[t['quarter'].str.startswith('2025')].copy(); unique(t,KEY,'stores'); num(t,['independent_store_count','store_count','franchise_store_count','open_count','close_count','reported_open_rate','reported_close_rate'])
check('store_identity',t['store_count'].eq(t['independent_store_count']+t['franchise_store_count']).all(),'whole=independent+franchise')
for c in ['store_count','open_count','close_count']: check('nonnegative_'+c,t[c].ge(0).all(),c)
for c in source_cols: check('nonnegative_'+c,s[c].ge(0).all(),c)
area_path=RAW/'seoul/extracted/seoul_area_trdar/서울시 상권분석서비스(영역-상권).shp'
inputs.extend(sorted(area_path.parent.glob('*')))
a=gpd.read_file(area_path); check('crs',a.crs.to_epsg()==5181,str(a.crs))
a=a.rename(columns={'TRDAR_CD':'trdar_code','TRDAR_CD_N':'trdar_name','TRDAR_SE_C':'trdar_type_code','TRDAR_SE_1':'trdar_type','SIGNGU_CD':'gu_code','SIGNGU_CD_':'gu_name','ADSTRD_CD':'admin_dong_code','ADSTRD_CD_':'admin_dong_name','RELM_AR':'reported_area_m2'})
a['trdar_code']=a['trdar_code'].astype(str); unique(a,['trdar_code'],'area'); invalid=int((~a.is_valid).sum()); a['geometry']=a.geometry.make_valid(); a['area_m2']=a.area; a['area_km2']=a['area_m2']/1e6
check('valid_geometry_after_repair',a.is_valid.all() and (~a.is_empty).all(),'invalid before='+str(invalid)); check('positive_area',a['area_m2'].gt(0).all(),'EPSG:5181 geometry area')
area_ratio=a['reported_area_m2']/a['area_m2']; a['is_tourist']=a['trdar_type_code'].eq('U'); a['main_analysis_eligible']=~a['is_tourist']
area_cols=['trdar_code','trdar_name','trdar_type_code','trdar_type','gu_code','gu_name','admin_dong_code','admin_dong_name','reported_area_m2','area_m2','area_km2','is_tourist','main_analysis_eligible']
area=a[area_cols].copy(); write(area,'dim_trdar',['trdar_code'])
check('sales_store_keys',len(s.merge(t[KEY],on=KEY,how='left',indicator=True).query('_merge=="left_only"'))==0,'sales keys subset of store keys')
check('all_store_areas',set(t['trdar_code'])<=set(a['trdar_code']),'all stores match area')
p=t.drop(columns=['trdar_name_source','trdar_type_code_source','trdar_type_source']).merge(s[KEY+source_cols],on=KEY,how='left',validate='one_to_one',indicator='_sales_merge')
p['sales_observed']=p.pop('_sales_merge').eq('both'); p['sales_supported_industry']=p['industry_code'].isin(s['industry_code']); p['sales_status']=np.select([p['sales_observed'],~p['sales_supported_industry']],['observed','unsupported_industry'],default='missing_cell')
p['year']=p['quarter'].str[:4].astype(int); p['quarter_number']=p['quarter'].str[-1].astype(int); p=p.merge(area,on='trdar_code',how='left',validate='many_to_one')
check('left_join_no_expansion',len(p)==len(t),f'{len(t)} → {len(p)}')
# 수요 테이블은 업종으로 펼치지 않고 상권×분기에 유지한다.
base=pd.MultiIndex.from_product([['20251','20252','20253','20254'],area['trdar_code']],names=['quarter','trdar_code']).to_frame(index=False)
context=base.copy(); freshness=[]
auxspec=[('K04','seoul_flpop_trdar_2025_sheet.csv','총_유동인구_수','floating_population'),('K05','seoul_facility_trdar_all_sheet.csv','집객시설_수','facility_count'),('K06','seoul_wrcpop_trdar_all_sheet.csv','총_직장_인구_수','worker_population'),('K07','seoul_repop_trdar_all_sheet.csv','총_상주인구_수','resident_population')]
for id,fn,src,dst in auxspec:
 d=read('seoul/'+fn).rename(columns=common); unique(d,['quarter','trdar_code'],id)
 ids=['quarter','trdar_code','trdar_name_source','trdar_type_code_source','trdar_type_source']; vals=[c for c in d if c not in ids]
 sig=pd.util.hash_pandas_object(d[vals].fillna(''),index=False); w=d.assign(sig=sig).pivot(index='trdar_code',columns='quarter',values='sig').sort_index(axis=1)
 changed=[q for prev,q in zip(w.columns,w.columns[1:]) if (w[prev].notna()&w[q].notna()&w[prev].ne(w[q])).any()]
 last=max(changed,default=None); d=d[d['quarter'].str.startswith('2025')].copy(); num(d,vals)
 keep=['quarter','trdar_code',src]; sub=d[keep].rename(columns={src:dst}); sub[id+'_row_present']=True
 if id=='K04':
  for tag in ['10','20','30','40','50','60_이상']:
   col=f'연령대_{tag}_유동인구_수'; out='floating_age_'+tag.replace('이상','plus'); sub[out]=d[col]; sub[out+'_share']=ratio(d[col],d[src])
  times=[f'시간대_{tag}_유동인구_수' for tag in ['00_06','06_11','11_14','14_17','17_21','21_24']]
  sub['floating_peak_time_share']=ratio(d[times].max(axis=1),d[src])
 if id=='K05':
  # 빈 시설 값은 확인 없이 0으로 바꾸지 않는다.
  for col in vals:
   if col!=src: sub['facility_raw_'+col]=d[col]
  sub['facility_subtype_missing_count']=d[[c for c in vals if c!=src]].isna().sum(axis=1)
 context=context.merge(sub,on=['quarter','trdar_code'],how='left',validate='one_to_one'); context[id+'_row_present']=context[id+'_row_present'].fillna(False)
 context[dst+'_last_observed_change']=last if last else 'not_observed_in_file'
 context[dst+'_reference_time_status']='changes_within_2025' if any(q.startswith('2025') for q in changed) else 'unchanged_within_2025_actual_vintage_unknown'
 freshness.append({'dataset':id,'last_observed_value_change':last,'changed_quarters':changed,'actual_statistical_vintage_verified':False})
context=context.merge(area,on='trdar_code',validate='many_to_one')
for col in ['floating_population','worker_population','resident_population','facility_count']: context[col+'_per_km2']=ratio(context[col],context['area_km2'])
# 서로 단위/기준시점이 다른 세 인구의 합계·구성비는 만들지 않는다.
total=t.groupby(['quarter','trdar_code'])['store_count'].sum().rename('all_industry_store_count').reset_index(); context=context.merge(total,on=['quarter','trdar_code'],how='left',validate='one_to_one'); context['stores_per_1000_floating_population']=ratio(context['all_industry_store_count']*1000,context['floating_population'])
write(context,'trdar_quarter_context',['quarter','trdar_code'])
# 파생변수 정의서는 계산 코드와 같은 위치에서 관리한다.
def feature(name,formula,unit,source,purpose,interpretation,availability='산출',level='상권×업종×분기'):
 features.append(dict(variable=name,level=level,formula=formula,unit=unit,source=source,purpose=purpose,interpretation=interpretation,availability=availability))
def calc(name,value,formula,unit,source,purpose,interpretation): p[name]=value; feature(name,formula,unit,source,purpose,interpretation)
calc('sales_per_store_quarter',ratio(p['sales_amount'],p['store_count']),'sales_amount / store_count','원/점포/분기','K01 당월_매출_금액; K02 similr_induty_stor_co','매출 규모 비교','전체 점포 분모를 쓴 근사값. 개별 점포의 실적 아님')
calc('sales_per_store_month',p['sales_per_store_quarter']/3,'sales_per_store_quarter / 3','원/점포/월 환산','K01;K02','월 단위 설명','평균적인 월로 환산. 월별 관측 자료가 아님')
calc('sales_per_transaction',ratio(p['sales_amount'],p['sales_count']),'sales_amount / sales_count','원/추정 매출 1건','K01 당월_매출_금액·건수','결제 단가 비교','객단가 근사값. 고유 고객 수를 뜻하지 않음')
calc('franchise_share',ratio(p['franchise_store_count'],p['store_count']),'franchise_store_count / store_count','0~1','K02 frc_stor_co;similr_induty_stor_co','경쟁 구조','비중이 높다고 자동 감점하지 않음')
calc('store_density_km2',ratio(p['store_count'],p['area_km2']),'store_count / area_km2','점포/km²','K02;K03 repaired geometry','점포 밀집도','상권 면적당 해당 업종 점포 수')
calc('open_count_ratio',ratio(p['open_count'],p['store_count']),'open_count / store_count','비율(100 초과 가능)','K02 opbiz_stor_co;similr_induty_stor_co','개업 움직임','동일 시점 재고 대비 건수. 개업 확률 아님')
calc('close_count_ratio',ratio(p['close_count'],p['store_count']),'close_count / store_count','비율(100 초과 가능)','K02 clsbiz_stor_co;similr_induty_stor_co','폐업 움직임','점포 0이면 결측. 0인 칸의 폐업 건수는 별도로 보존')
calc('net_open_count',p['open_count']-p['close_count'],'open_count - close_count','건','K02','개폐업 균형','실제 점포 수 증감과 다를 수 있음')
calc('weekend_sales_share',ratio(p['weekend_sales'],p['sales_amount']),'weekend_sales / sales_amount','0~1','K01 주말_매출_금액;당월_매출_금액','주말형 수요','비중. 요일 수 차이를 보정하지 않음')
calc('weekend_daily_ratio',ratio(p['weekend_sales']/2,p['weekday_sales']/5),'(weekend_sales / 2) / (weekday_sales / 5)','배','K01 주중·주말_매출_금액','주말 하루 비교','주중 5일·주말 2일의 단순 환산. 공휴일 미보정')
known=p['male_sales']+p['female_sales']
calc('female_sales_share_known',ratio(p['female_sales'],known),'female_sales / (male_sales + female_sales)','0~1','K01 여성·남성_매출_금액','관측 고객 구성','성별이 알려진 매출 중 비중')
calc('gender_sales_coverage',ratio(known,p['sales_amount']),'(male_sales + female_sales) / sales_amount','비율','K01','성별 정보 범위','알려진 성별 매출의 총매출 대비 비중')
ages=['age_'+x+'_sales' for x in ['10','20','30','40','50','60_plus']]; age_total=p[ages].sum(axis=1,min_count=len(ages))
for age,col in zip(['10','20','30','40','50','60_plus'],ages): calc('sales_age_'+age+'_share',ratio(p[col],age_total),f'{col} / known_age_sales_total','0~1','K01 연령대별 매출 금액','고객 연령 구성','연령이 알려진 매출 안의 비중. 방문 인구 비중 아님')
calc('age_sales_coverage',ratio(age_total,p['sales_amount']),'known_age_sales_total / sales_amount','비율','K01','연령 정보 범위','총매출과 연령별 매출 합은 다를 수 있음')
times=['00_06','06_11','11_14','14_17','17_21','21_24']
for time in times: calc('time_'+time+'_sales_share',ratio(p['time_'+time+'_sales'],p['sales_amount']),f'time_{time}_sales / sales_amount','0~1','K01 시간대별 매출 금액','운영 시간 적합성','구간 길이가 다름. 시간당 효율로 단정하지 않음')
calc('night_sales_share',ratio(p['time_21_24_sales']+p['time_00_06_sales'],p['sales_amount']),'(time_21_24_sales + time_00_06_sales) / sales_amount','0~1','K01','야간 수요','21~06시 구간의 관측 매출 비중')
p=p.sort_values(['trdar_code','industry_code','quarter']).reset_index(drop=True); g=p.groupby(['trdar_code','industry_code'],sort=False); prevq=g['quarter_number'].shift(); consecutive=p['quarter_number'].eq(prevq+1); prevstore=g['store_count'].shift(); prevsales=g['sales_amount'].shift()
calc('store_qoq_change',((ratio(p['store_count'],prevstore)-1).where(consecutive)),'store_count / previous_quarter_store_count - 1, 연속분기만','증감률','K02','점포 변화','전분기 점포 0 또는 부재면 결측. 1분기 결측')
calc('sales_qoq_change',((ratio(p['sales_amount'],prevsales)-1).where(consecutive)),'sales_amount / previous_quarter_sales_amount - 1, 연속분기만','증감률','K01','단기 매출 변화','전년 동기 성장률 아님. 계절성 포함')
p['small_store_flag']=p['store_count']<5; p['zero_stock_with_closure']=p['store_count'].eq(0)&p['close_count'].gt(0)
p['sales_rank_eligible']=p['sales_observed']&p['store_count'].ge(5)&p['main_analysis_eligible']
# 업종 내 상대 비교: 분기와 업종이 같고 관광특구 제외·점포 5개 이상인 관측 칸만.
valid=p['sales_rank_eligible']; ranks=p.loc[valid].groupby(['quarter','industry_code'])['sales_per_store_month']; counts=ranks.transform('count'); p['industry_peer_count']=pd.Series(pd.NA,index=p.index,dtype='Int64'); p.loc[valid,'industry_peer_count']=counts.astype('Int64'); peer_median=ranks.transform('median'); p['sales_vs_industry_median']=np.nan; p.loc[valid,'sales_vs_industry_median']=ratio(p.loc[valid,'sales_per_store_month'],peer_median).where(counts>=30)
feature('sales_vs_industry_median','sales_per_store_month / 동일 분기·동일 업종 적격칸 중앙값, 적격칸≥30','배','K01;K02','업종 보정 비교','점포≥5·비관광특구. 30·5는 운영 가정이며 검증된 임계값 아님')
# 업종별·분기별 HHI: 해당 업종 점포가 상권들에 얼마나 집중되어 있는가.
shares=p.loc[p['main_analysis_eligible']].copy(); denom=shares.groupby(['quarter','industry_code'])['store_count'].transform('sum'); shares['sq']=ratio(shares['store_count'],denom)**2; hhi=shares.groupby(['quarter','industry_code'])['sq'].sum(min_count=1).rename('industry_spatial_hhi').reset_index()
p=p.merge(hhi,on=['quarter','industry_code'],how='left',validate='many_to_one'); feature('industry_spatial_hhi','Σ상권 (해당업종 점포수 / 서울 해당업종 점포수)², 관광특구 제외','0~1','K02','공간 집중도','업종이 특정 상권에 모이는 정도. 상권 내 경쟁 강도와 다름',level='업종×분기')
# 다양성은 모든 100개 업종 점포로 계산. 한 업종당 인구를 다시 합산하지 않는다.
b=p[p['main_analysis_eligible']].copy(); b['share']=ratio(b['store_count'],b.groupby(['quarter','trdar_code'])['store_count'].transform('sum')); b['entropy_part']=-(b['share']*np.log(b['share'].where(b['share']>0))).fillna(0); b['share_sq']=b['share']**2
mix=b.groupby(['quarter','trdar_code']).agg(industry_entropy=('entropy_part','sum'),store_mix_hhi=('share_sq','sum'),positive_industry_count=('store_count',lambda x:int(x.gt(0).sum())))
mix['normalized_industry_entropy']=mix['industry_entropy']/np.log(100); mix.loc[mix['positive_industry_count'].eq(0),['industry_entropy','store_mix_hhi','normalized_industry_entropy']]=np.nan; context=context.merge(mix.reset_index(),on=['quarter','trdar_code'],how='left',validate='one_to_one')
feature('normalized_industry_entropy','-Σ업종 p×ln(p) / ln(100), p=업종점포/상권전체점포','0~1','K02 전체 100개 업종','업종 다양성','점포 없는 업종은 0 기여. 관광특구는 결측',level='상권×분기')
# 최신 context를 같은 파일에 저장하되 fact에는 중복 업종별 인구를 넣지 않는다.
write(context,'trdar_quarter_context',['quarter','trdar_code'])
write(p,'fact_trdar_industry_quarter',KEY)
# 연간 파생치: K02 행이 실제 네 분기 있고 매출도 네 분기 관측된 경우만 매출지표 산출.
annual=p.groupby(['trdar_code','industry_code']).agg(observed_store_quarters=('quarter','nunique'),observed_sales_quarters=('sales_amount','count'),annual_observed_sales=('sales_amount',lambda x:x.sum(min_count=1)),mean_store_count_observed=('store_count','mean'),annual_open_count=('open_count','sum'),annual_close_count=('close_count','sum'),sales_sd=('sales_amount',lambda x:x.std(ddof=0)),sales_mean=('sales_amount','mean')).reset_index(); annual['year']=2025
complete=annual['observed_store_quarters'].eq(4); complete_sales=complete&annual['observed_sales_quarters'].eq(4)
annual['annual_sales_complete']=annual['annual_observed_sales'].where(complete_sales); annual['annual_sales_cv']=ratio(annual['sales_sd'],annual['sales_mean']).where(complete_sales); annual['annual_monthly_sales_per_store']=ratio(annual['annual_sales_complete'],annual['mean_store_count_observed'])/12
annual['annual_close_count_ratio']=ratio(annual['annual_close_count'],annual['mean_store_count_observed']).where(complete); annual['annual_open_count_ratio']=ratio(annual['annual_open_count'],annual['mean_store_count_observed']).where(complete)
annual=annual.merge(area[['trdar_code','main_analysis_eligible']],on='trdar_code',validate='many_to_one'); write(annual,'annual_features',['year','trdar_code','industry_code'])
for name,formula,unit,interpret in [('annual_sales_complete','네 분기 매출 합, 점포·매출 모두 4분기 관측','원/년','분기 결측이면 연간 매출로 표시하지 않음'),('annual_sales_cv','4분기 매출 표준편차(ddof=0) / 평균','비율','계절성과 측정오차 포함. 안정성 확정 불가'),('annual_monthly_sales_per_store','annual_sales_complete / mean_store_count_observed / 12','원/점포/월 환산','전체 점포 분모를 쓴 근사값'),('annual_close_count_ratio','연간 폐업 건수 / 4분기 평균점포수','비율','점포 생존 확률이 아님'),('annual_open_count_ratio','연간 개업 건수 / 4분기 평균점포수','비율','점포 4분기 완전 관측 필요')]: feature(name,formula,unit,'K01;K02','연간 비교',interpret,level='상권×업종×연도')
for name,formula,unit,source,interp in [('floating_population_per_km2','floating_population / area_km2','원자료 인구 수/km²','K04;K03','유일한 사람 수로 해석하지 않음'),('worker_population_per_km2','worker_population / area_km2','명/km²','K06;K03','실제 통계 시점 미확인'),('resident_population_per_km2','resident_population / area_km2','명/km²','K07;K03','실제 통계 시점 미확인'),('facility_count_per_km2','facility_count / area_km2','시설/km²','K05;K03','시설 총수 원본 정의 주의'),('stores_per_1000_floating_population','상권 전체 점포수 / floating_population ×1000','점포/원자료 인구 1000단위','K02;K04','수요 대비 공급의 보조치. 구매전환율 아님'),('floating_peak_time_share','max(시간대별 유동인구) / 총유동인구','비율','K04','시간대 길이 다름. 구성 집중도만 표시')]: feature(name,formula,unit,source,'입지 수요',interp,level='상권×분기')
for age in ['10','20','30','40','50','60_plus']: feature('floating_age_'+age+'_share',f'floating_age_{age} / floating_population','비율','K04 연령대별 유동인구·총_유동인구_수','고객층과 입지 비교','총인구와 세부 합 사이 반올림 차이 가능',level='상권×분기')
for name,formula,unit,meaning in [('industry_entropy','-Σ업종 p×ln(p)','0~ln(100)','업종 다양성 원지표'),('store_mix_hhi','Σ업종 p²','0~1','상권 내 업종 편중. 단일 업종이면 1'),('positive_industry_count','점포 수가 양수인 업종 수','개','상권 안에서 영업하는 업종의 종류')]: feature(name,formula,unit,'K02','상업시설 구성',meaning,level='상권×분기')
# S01/S02 코드 검증 및 공간 조인. 업종 체계는 자동으로 섞지 않는다.
s01=read('semas/extracted/semas_store_20251231/소상공인시장진흥공단_상가(상권)정보_서울_202512.csv',encoding='utf-8',usecols=['상가업소번호','상권업종소분류코드','상권업종소분류명','시군구코드','경도','위도']).rename(columns={'상가업소번호':'store_id','상권업종소분류코드':'semas_industry_code','상권업종소분류명':'semas_industry_name'})
s02=read('semas/semas_industry_code_20230228.csv'); unique(s01,['store_id'],'semas'); check('semas_industry_code_dictionary',set(s01['semas_industry_code'])<=set(s02['소분류코드']),'247 codes validated against S02')
lon=pd.to_numeric(s01['경도'],errors='coerce'); lat=pd.to_numeric(s01['위도'],errors='coerce'); validcoord=lon.between(-180,180)&lat.between(-90,90)
points=gpd.GeoDataFrame(s01.loc[validcoord,['store_id','semas_industry_code']],geometry=gpd.points_from_xy(lon[validcoord],lat[validcoord]),crs=4326).to_crs(5181)
bridge=gpd.sjoin(points,a[['trdar_code','is_tourist','geometry']],how='left',predicate='within').drop(columns=['geometry','index_right'])
bridge=bridge.merge(s01[['store_id']],on='store_id',how='outer'); bridge['spatial_status']=np.where(bridge['trdar_code'].notna(),'within','outside_or_boundary'); bridge.loc[bridge['store_id'].isin(s01.loc[~validcoord,'store_id']),'spatial_status']='invalid_coordinate'; bridge['snapshot_date']='2025-12-31'
bridge['match_number']=bridge.groupby('store_id').cumcount()+1; write(bridge,'semas_spatial_bridge',['store_id','match_number'])
core=bridge[bridge['trdar_code'].notna()&bridge['is_tourist'].eq(False)]; core_n=core.groupby('store_id')['trdar_code'].nunique(); ambiguous=set(core_n[core_n>1].index); accepted=core[~core['store_id'].isin(ambiguous)]
counts=accepted.groupby(['trdar_code','semas_industry_code'])['store_id'].nunique().rename('semas_store_count_q4').reset_index(); counts['quarter']='20254'; write(counts,'semas_q4_industry_counts',['quarter','trdar_code','semas_industry_code'])
feature('semas_store_count_q4','관광특구 제외, 비관광 상권이 하나로 정해진 S01 점포 ID 고유 개수','점포','S01;S02;K03','공간 분포 보조','서울 서비스업종 수와 직접 합산 금지',level='상권×소상공인업종×2025Q4')
# 보조 집계는 매핑 승인 전까지 서울 업종에 붙이지 않는다.
mapping=s02.rename(columns={'소분류코드':'semas_industry_code','소분류명':'semas_industry_name'})[['semas_industry_code','semas_industry_name']].copy(); mapping['seoul_industry_code']=''; mapping['mapping_status']='pending_review'; mapping['mapping_relation']=''; mapping['rationale']=''; mapping['reviewer']=''; mapping['review_date']=''
# 검토한 매핑 파일을 재실행으로 덮어쓰지 않는다.
map_path=OUT/'industry_mapping_review.csv'
if not map_path.exists(): mapping.to_csv(map_path,index=False,encoding='utf-8-sig')
t[['industry_code','industry_name']].drop_duplicates().sort_values('industry_code').to_csv(OUT/'seoul_industry_reference.csv',index=False,encoding='utf-8-sig')
for name,src,reason in [('sales_yoy_change','K01 2024 동분기','2024 매출 없음'),('population_growth','K04 과거연도 및 K06/K07 실제작성시점','현재 파일만으로 일관된 성장률 확정 불가'),('business_survival_probability','점포별 시계열 개폐업 이력','분기 집계와 단일 스냅숏만 있음'),('budget_fit','임대료·보증금·권리금·시설비','비용 자료 없음'),('mapped_semas_competitor_count','S01;S02;승인된 기관 간 업종 매핑','공식 연계표 및 승인 매핑 없음')]: feature(name,'계산하지 않음','해당 없음',src,'향후 확장',reason,availability='보류')
pd.DataFrame(features).to_csv(OUT/'feature_dictionary.csv',index=False,encoding='utf-8-sig')
# QA 표는 출력에 의존하지 않는 독립 점검을 기록한다.
check('total_sales_reconciled',np.isclose(p['sales_amount'].sum(),s['sales_amount'].sum()),'전체 관광특구 포함 합계 보존')
check('tourist_count',int(a['is_tourist'].sum())==6,str(int(a['is_tourist'].sum())))
check('first_quarter_qoq_missing',p.loc[p['quarter']=='20251',['sales_qoq_change','store_qoq_change']].isna().all().all(),'2024 lag not fabricated')
check('missing_sales_preserved',p.loc[~p['sales_observed'],'sales_per_store_month'].isna().all(),'미관측 매출→0 금지')
check('zero_denominator_missing',p.loc[p['store_count'].eq(0),['close_count_ratio','sales_per_store_month']].isna().all().all(),'0 denominator→missing')
check('full_year_coverage',annual.loc[annual['observed_sales_quarters']<4,'annual_sales_complete'].isna().all(),'partial-year sums not annualized')
check('all_spatial_stores_preserved',bridge['store_id'].nunique()==len(s01),'outside/ambiguous/invalid retained in bridge')
# 개폐업과 점포수 사이 잔차를 숨기지 않는다.
resid=p[['quarter','trdar_code','industry_code','store_count','open_count','close_count']].copy(); grp=resid.groupby(['trdar_code','industry_code']); prev=grp['store_count'].shift(); prevquarter=grp['quarter'].shift(); eligible=(resid['quarter'].astype(int)-prevquarter.astype('Float64')).eq(1).fillna(False); resid['stock_flow_residual']=(resid['store_count']-prev-resid['open_count']+resid['close_count']).where(eligible); resid.dropna(subset=['stock_flow_residual']).query('stock_flow_residual != 0').to_csv(QA/'stock_flow_mismatches.csv',index=False,encoding='utf-8-sig')
p['sales_status'].value_counts().rename_axis('sales_status').reset_index(name='rows').to_csv(QA/'sales_status_counts.csv',index=False,encoding='utf-8-sig')
# 같은 테이블을 갱신 저장한 경우 최종 스키마만 남긴다.
pd.DataFrame(schemas).drop_duplicates(['table','column'],keep='last').to_csv(OUT/'table_schema.csv',index=False,encoding='utf-8-sig'); pd.DataFrame(checks).to_csv(QA/'validation_checks.csv',index=False,encoding='utf-8-sig')
manifest={'analysis_year':2025,'crs':'EPSG:5181','source':'서울특별시 상권분석서비스 / 소상공인시장진흥공단 상가(상권)정보','versions':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'geopandas':gpd.__version__},'assumptions':{'small_store_threshold':5,'minimum_industry_peers':30,'semas_snapshot':'2025-12-31','facility_blank_imputation':False,'semas_to_seoul_mapping_applied':False},'summary':{'fact_rows':len(p),'context_rows':len(context),'annual_rows':len(annual),'derived_variable_definitions':len(features),'main_fact_rows':int(p['main_analysis_eligible'].sum()),'complete_sales_year_cells':int(complete_sales.sum()),'invalid_polygons_repaired':invalid,'reported_to_geometry_area_ratio_min':float(area_ratio.min()),'reported_to_geometry_area_ratio_max':float(area_ratio.max()),'semas_stores':len(s01),'semas_unassigned':int(bridge.loc[bridge['trdar_code'].isna(),'store_id'].nunique()),'semas_multi_core_stores':len(ambiguous),'semas_accepted_main_stores':int(accepted['store_id'].nunique()),'nonzero_stock_flow_residual_rows':int(resid['stock_flow_residual'].dropna().ne(0).sum())},'freshness':freshness,'input_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in dict.fromkeys(inputs)},'output_sha256':{str(f.relative_to(OUT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(DATA.glob('*.gz'))}}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(manifest['summary'],ensure_ascii=False,indent=2))
