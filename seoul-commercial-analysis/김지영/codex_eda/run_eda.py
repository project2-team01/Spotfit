"""원본을 읽어 Codex EDA 보고서, 그림, 근거 표를 재생성한다."""
from pathlib import Path
import json, warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
warnings.filterwarnings('ignore', category=FutureWarning)
ROOT=Path(__file__).resolve().parents[2]; RAW=ROOT/'data/raw'; OUT=Path(__file__).resolve().parent; FIG=OUT/'figures'; TAB=OUT/'tables'
for p in [FIG,TAB]: p.mkdir(exist_ok=True,parents=True)
fonts={f.name for f in font_manager.fontManager.ttflist}
font=next((f for f in ['Apple SD Gothic Neo','AppleGothic','NanumGothic','Noto Sans CJK KR'] if f in fonts),'DejaVu Sans')
plt.rcParams.update({'font.family':font,'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.titleweight':'bold','savefig.dpi':160})
C=['#3478b8','#ed9250','#41a58a','#a780bb']
def read(p): return pd.read_csv(RAW/p,encoding='cp949',dtype=str)
rename={'기준_년분기_코드':'분기','상권_코드':'상권코드','상권_코드_명':'상권명','상권_구분_코드_명':'상권구분','서비스_업종_코드':'업종코드','서비스_업종_코드_명':'업종명','당월_매출_금액':'매출','당월_매출_건수':'건수'}
s=read('seoul/extracted/seoul_sales_trdar_2025/서울시 상권분석서비스(추정매출-상권)_2025년.csv').rename(columns=rename)
t=read('seoul/extracted/seoul_store_trdar_2025/서울시 상권분석서비스(점포-상권)_2025년.csv').rename(columns={'stdr_yyqu_cd':'분기','trdar_cd':'상권코드','trdar_cd_nm':'상권명','trdar_se_cd_nm':'상권구분','svc_induty_cd':'업종코드','svc_induty_cd_nm':'업종명','similr_induty_stor_co':'점포수','stor_co':'일반점포수','frc_stor_co':'프랜차이즈수','opbiz_stor_co':'개업수','clsbiz_stor_co':'폐업수','opbiz_rt':'원본개업률','clsbiz_rt':'원본폐업률'})
for c in s:
 if c.endswith(('금액','건수')) or c in ['매출','건수']: s[c]=pd.to_numeric(s[c],errors='raise')
for c in ['점포수','일반점포수','프랜차이즈수','개업수','폐업수','원본개업률','원본폐업률']: t[c]=pd.to_numeric(t[c],errors='raise')
a=gpd.read_file(RAW/'seoul/extracted/seoul_area_trdar/서울시 상권분석서비스(영역-상권).shp').rename(columns={'TRDAR_CD':'상권코드','TRDAR_CD_N':'상권명','TRDAR_SE_1':'상권구분'})
a['상권코드']=a['상권코드'].astype(str)
aux={k:read('seoul/'+f).rename(columns=rename) for k,f in {'유동인구':'seoul_flpop_trdar_2025_sheet.csv','직장인구':'seoul_wrcpop_trdar_all_sheet.csv','상주인구':'seoul_repop_trdar_all_sheet.csv','집객시설':'seoul_facility_trdar_all_sheet.csv'}.items()}
key=['분기','상권코드','업종코드']
assert not s.duplicated(key).any() and not t.duplicated(key).any()
assert set(s['분기'])==set(t['분기'])=={'20251','20252','20253','20254'}
quality=[]
for name,d in [('매출',s),('점포',t),*aux.items()]:
 k=key if name in ['매출','점포'] else ['분기','상권코드']
 quality.append({'데이터':name,'행수_전체파일':len(d),'열수':len(d.columns),'2025행수':int(d['분기'].str.startswith('2025').sum()),'중복키':int(d.duplicated(k).sum()),'결측셀':int(d.isna().sum().sum())})
quality=pd.DataFrame(quality); quality.to_csv(TAB/'quality.csv',index=False,encoding='utf-8-sig')
ss=s[s['상권구분']!='관광특구'].copy(); tt=t[t['상권구분']!='관광특구'].copy()
p=tt.merge(ss[key+['매출','건수']],on=key,how='left',validate='one_to_one')
p['점포당월매출']=p['매출']/p['점포수'].replace(0,np.nan)/3/10000
q4=tt[tt['분기']=='20254']; codes=set(ss['업종코드']); eligible=p[p['업종코드'].isin(codes)].copy()
cell=p.groupby(['상권코드','업종코드','업종명']).agg(매출=('매출',lambda x:x.sum(min_count=1)),매출분기수=('매출','count'),평균점포수=('점포수','mean'),폐업수=('폐업수','sum'),개업수=('개업수','sum')).reset_index()
full=cell[cell['매출분기수']==4].copy(); full['점포당월매출']=full['매출']/full['평균점포수']/12/10000
full['분기변동계수']=ss.groupby(['상권코드','업종코드'])['매출'].agg(lambda x:x.std(ddof=0)/x.mean()).reindex(pd.MultiIndex.from_frame(full[['상권코드','업종코드']])).values
industry=tt.groupby('업종명').agg(분기점포합=('점포수','sum'),개업수=('개업수','sum'),폐업수=('폐업수','sum'))
industry['평균점포수']=industry['분기점포합']/4; industry['연간폐업건수비']=industry['폐업수']/industry['평균점포수']*100; industry['연간개업건수비']=industry['개업수']/industry['평균점포수']*100
industry['연매출_조원']=ss.groupby('업종명')['매출'].sum()/1e12
industry['점포당월매출중앙값_만원']=full.groupby('업종명')['점포당월매출'].median()
industry.to_csv(TAB/'industry.csv',encoding='utf-8-sig'); full.to_csv(TAB/'complete_cells.csv',index=False,encoding='utf-8-sig')
sections=[]
def save(title,reading,result,caution='',fig=None):
 n=len(sections)+1; fn=f'{n:02d}.png'; fig=fig or plt.gcf(); fig.suptitle(f'{n:02d}. {title}',fontsize=16,fontweight='bold',y=1.02); fig.tight_layout(); fig.savefig(FIG/fn,bbox_inches='tight'); plt.close(fig)
 sections.append(f'## {n}. {title}\n\n![{title}](codex_eda/figures/{fn})\n\n**그림 읽기:** {reading}\n\n**확인한 점:** {result}\n\n'+(f'**해석할 때 주의:** {caution}\n\n' if caution else ''))
def bar(x,xlabel,title,reading,result,caution=''):
 fig,ax=plt.subplots(figsize=(10,max(4,len(x)*.34))); x.sort_values().plot.barh(ax=ax,color=C[0]); ax.set_xlabel(xlabel); ax.set_ylabel(''); ax.grid(axis='x',alpha=.2); ax.margins(x=.16); ax.bar_label(ax.containers[0],fmt=lambda z:f'{z:,.1f}' if abs(z)<100 else f'{z:,.0f}',padding=4,fontsize=9); save(title,reading,result,caution,fig)
def heat(d,title,reading,result,caution='',cmap='Blues',fmt='.0f'):
 fig,ax=plt.subplots(figsize=(max(8,len(d.columns)*.75),max(4,len(d)*.40))); im=ax.imshow(d,cmap=cmap,aspect='auto',**({'vmin':-1,'vmax':1} if cmap=='RdBu' else {})); ax.set_xticks(range(len(d.columns)),d.columns,rotation=35,ha='right'); ax.set_yticks(range(len(d)),d.index)
 for i in range(len(d)):
  for j in range(len(d.columns)):
   v=d.iloc[i,j]
   if pd.notna(v): ax.text(j,i,format(v,fmt),ha='center',va='center',fontsize=9,color=('black' if abs(v)<.65 else 'white') if cmap=='RdBu' else ('black' if v<(np.nanmax(d.values)+np.nanmin(d.values))/2 else 'white'))
 fig.colorbar(im,ax=ax,shrink=.7); save(title,reading,result,caution,fig)
# 1 coverage
cov=pd.Series({'점포':tt['상권코드'].nunique(),'매출':ss['상권코드'].nunique(),**{k:d[(d['분기'].str.startswith('2025'))&(d['상권구분']!='관광특구')]['상권코드'].nunique() for k,d in aux.items()}})
bar(cov,'2025년 관측 상권 수','데이터마다 담고 있는 상권이 다르다','막대가 길수록 자료에 등장하는 상권이 많습니다.',f'관광특구를 제외한 점포 상권은 {cov["점포"]:,}개, 매출 상권은 {cov["매출"]:,}개입니다.','행이 없다는 사실만으로 점포·인구·매출이 0이라고 판단하지 않습니다.')
# 2 coverage threshold
eligible['점포구간']=pd.cut(eligible['점포수'],[-1,0,1,2,4,9,19,49,np.inf],labels=['0','1','2','3~4','5~9','10~19','20~49','50+'])
coverage=eligible.groupby('점포구간',observed=True)['매출'].agg(칸수='size',공개수='count'); coverage['매출행비율']=coverage['공개수']/coverage['칸수']*100
bar(coverage['매출행비율'],'매출 행 보유 비율 (%)','작은 업종 칸의 매출은 보이지 않는다','한 칸은 상권×업종×분기입니다. 점포 수별로 매출 자료가 있는 비율을 비교합니다.',f'62개 매출 업종의 칸 중 매출 행이 없는 비율은 {eligible["매출"].isna().mean()*100:.1f}%입니다. 매출이 연결된 칸의 최소 점포 수는 {p.loc[p["매출"].notna(),"점포수"].min():.0f}개입니다.','관측된 패턴입니다. 미공개 사유를 공식 정책으로 단정하지 않습니다.')
# 3 missing industry
v=eligible.assign(관측점포=lambda d:d['점포수'].where(d['매출'].notna(),0)).groupby('업종명')[['점포수','관측점포']].sum(); v['비율']=v['관측점포']/v['점포수']*100
bar(v['비율'].nsmallest(15),'매출이 있는 칸에 속한 점포 비중 (%)','업종에 따라 매출의 관측 범위가 다르다','분기별 점포 수를 더한 뒤, 매출이 보이는 칸의 점포가 차지하는 비중을 구했습니다.',f'매출 관측 범위가 50% 미만인 업종은 {int((v["비율"]<50).sum())}개입니다. 가장 낮은 업종은 {v["비율"].idxmin()}({v["비율"].min():.1f}%)입니다.','각 점포의 매출을 직접 확보했다는 뜻은 아닙니다.')
# 4 exclusion
bar(s.groupby('상권구분')['매출'].sum()/1e12,'2025년 추정매출 (조원)','관광특구 합산에 주의한다','상권 종류별 매출을 비교합니다. 이 그림만 관광특구를 포함합니다.',f'관광특구 포함 합계는 {s["매출"].sum()/1e12:.2f}조원, 제외하면 {ss["매출"].sum()/1e12:.2f}조원입니다.','관광특구는 다른 상권과 공간이 겹칠 수 있어 이후 합계에서는 제외합니다. 나머지 합계도 서울 전체 업종의 실제 매출은 아닙니다.')
# 5 type
bar(q4.groupby('상권구분')['점포수'].sum(),'2025Q4 점포 수','상권 종류별 점포 규모','막대는 4분기 한 시점의 점포 수입니다.',f'점포가 가장 많은 상권 유형은 {q4.groupby("상권구분")["점포수"].sum().idxmax()}입니다.','분기별 점포 수를 4개 분기 합산하면 점포가 중복 계산됩니다.')
bar(q4.groupby('업종명')['점포수'].sum().nlargest(20),'2025Q4 점포 수','점포가 많은 업종 20개','업종별로 현재 점포가 얼마나 많은지 비교합니다.',f'4분기 점포 수 1위는 {q4.groupby("업종명")["점포수"].sum().idxmax()}입니다.','점포가 많다는 이유만으로 과잉 경쟁이라고 판단할 수 없습니다.')
bar(industry['연매출_조원'].dropna().nlargest(20),'2025년 관측 추정매출 (조원)','매출 규모가 큰 업종 20개','막대는 해당 업종의 관측 가능한 매출 합계입니다.',f'관측 매출 합계 1위는 {industry["연매출_조원"].idxmax()}입니다.','매출 자료가 없는 업종은 순위에서 제외했습니다. 이익과 창업 비용은 알 수 없습니다.')
bar(industry['점포당월매출중앙값_만원'].dropna().nlargest(20),'점포당 월 환산 추정매출 중앙값 (만원)','점포당 매출로 업종을 다시 비교한다','4개 분기 매출이 모두 있는 상권×업종에서 연매출÷평균점포 수÷12를 계산한 뒤 업종별 중앙값을 구했습니다.',f'완전 관측 조합은 {len(full):,}개입니다. 중앙값은 값을 순서대로 세웠을 때 가운데 값입니다.','매출 추정 대상과 전체 점포 분모가 정확히 같다고 보장할 수 없어 근사 지표입니다. 개인 점포의 기대 매출이 아닙니다.')
fig,ax=plt.subplots(figsize=(10,4)); val=p['점포당월매출'].dropna(); ax.hist(np.log10(val[val>0]),bins=60,color=C[0]); ax.set_xlabel('점포당 월 환산 매출 (만원, 로그 눈금)'); ticks=[1,2,3,4,5]; ax.set_xticks(ticks,[f'{10**i:,}' for i in ticks]); ax.set_ylabel('상권×업종×분기 칸 수'); save('매출은 일부 큰 값에 치우쳐 있다','가로축은 10배씩 커집니다. 막대가 높을수록 그 매출 구간에 칸이 많습니다.',f'관측 칸의 점포당 월 환산 매출 중앙값은 {val.median():,.0f}만원, 평균은 {val.mean():,.0f}만원입니다.','큰 값을 삭제하지 않았습니다. 평균만 보면 일반적인 수준을 높게 느낄 수 있습니다.',fig)
# quarter
q=ss.groupby('분기')['매출'].sum()/1e12
fig,ax=plt.subplots(figsize=(9,4)); ax.plot(['1분기','2분기','3분기','4분기'],q.values,'o-',color=C[0]); ax.set_ylabel('관측 추정매출 (조원)'); ax.grid(alpha=.2); save('분기별 매출 흐름','선이 올라가면 관측 매출 합계가 늘어난 것입니다.',f'1분기 {q.iloc[0]:.2f}조원에서 4분기 {q.iloc[-1]:.2f}조원으로 {(q.iloc[-1]/q.iloc[0]-1)*100:+.1f}% 달라졌습니다.','전년 대비 성장률이 아닙니다. 계절과 분기별 관측 대상 변화가 섞입니다.',fig)
wide=ss.pivot(index=['상권코드','업종코드'],columns='분기',values='매출').dropna(); idx=wide.sum()/wide.sum().iloc[0]*100
fig,ax=plt.subplots(figsize=(9,4)); ax.plot(['1분기','2분기','3분기','4분기'],idx,'o-',label=f'동일한 {len(wide):,}개 조합'); ax.axhline(100,color='gray',ls='--'); ax.set_ylabel('1분기 = 100'); ax.legend(); save('같은 상권과 업종만 남겨 분기를 비교한다','100보다 높으면 같은 조합의 매출이 1분기보다 높습니다.',f'동일 조합의 4분기 지수는 {idx.iloc[-1]:.1f}입니다.','네 분기 모두 보이는 조합만 남겨 작은 상권이나 새로 나타난 업종이 덜 반영됩니다.',fig)
top=ss.groupby('업종명')['매출'].sum().nlargest(12).index
h=ss[ss['업종명'].isin(top)].pivot_table(index='업종명',columns='분기',values='매출',aggfunc='sum'); h=h.div(h.iloc[:,0],axis=0)*100; h.columns=['1분기','2분기','3분기','4분기']
heat(h,'업종별 분기 흐름은 서로 다르다','각 업종의 1분기를 100으로 맞췄습니다. 진할수록 해당 업종의 1분기보다 매출이 큽니다.',f'관측 연매출 상위 12개 업종 중 4분기 지수가 가장 높은 업종은 {h.iloc[:,-1].idxmax()}입니다.','이 그림은 업종별 관측 합계를 사용합니다. 장기 성장과 계절 효과를 분리할 수 없습니다.')
# concentration
trsales=ss.groupby(['상권코드','상권명'])['매출'].sum().sort_values(ascending=False)
bar(trsales.head(15).droplevel(0)/1e8,'관측 연매출 (억원)','연매출 상위 상권 15개','상권 전체 매출 합계를 비교합니다.',f'관측 합계 1위는 {trsales.index[0][1]}입니다.','큰 상권·고매출 업종이 유리한 순위입니다. 희망 업종에 좋은 입지 순위로 해석하지 않습니다.')
conc=ss.groupby(['상권코드','업종명'])['매출'].sum().groupby(level=0).max()/ss.groupby('상권코드')['매출'].sum()*100
bar(conc.reindex(trsales.head(15).index.get_level_values(0)).set_axis(trsales.head(15).index.get_level_values(1)),'상권 매출 1위 업종의 비중 (%)','상위 상권이 특정 업종에 의존하는 정도','100%에 가까우면 한 업종이 매출 대부분을 차지합니다.',f'연매출 상위 15개 상권 중 1위 업종 비중이 50%를 넘는 곳은 {int((conc.reindex(trsales.head(15).index.get_level_values(0))>50).sum())}곳입니다.','관측 업종 안에서 계산한 집중도입니다. 업종 다양성과 수익성을 같은 뜻으로 쓰지 않습니다.')
# consumer profiles
for title,cols,labels,note in [
 ('요일별 매출 비중',[f'{d}요일_매출_금액' for d in '월화수목금토일'],list('월화수목금토일'),'요일 수는 같지만 공휴일·분기 일수의 영향을 받습니다.'),
 ('시간대별 매출 비중',[f'시간대_{x}_매출_금액' for x in ['00~06','06~11','11~14','14~17','17~21','21~24']],['00~06','06~11','11~14','14~17','17~21','21~24'],'시간대 길이가 서로 다릅니다. 비중이 크다고 시간당 매출도 높다고 단정할 수 없습니다.'),
 ('고객 연령별 매출 구성',[f'연령대_{x}_매출_금액' for x in ['10','20','30','40','50','60_이상']],['10대','20대','30대','40대','50대','60대 이상'],'연령별 알려진 매출의 구성입니다. 방문객 수·지역 인구 구성과 다릅니다.')]:
  mat=ss[ss['업종명'].isin(top)].groupby('업종명')[cols].sum(); mat=mat.div(mat.sum(axis=1),axis=0)*100; mat.columns=labels
  heat(mat,title,'행은 업종, 열은 '+('요일' if '요일' in title else '시간대' if '시간대' in title else '연령')+'입니다. 각 행의 합이 100%이며, 숫자가 클수록 그 구간에서 매출 비중이 큽니다.',f'관측 매출 상위 {len(top)}개 업종 중 한식음식점은 {mat.loc["한식음식점"].idxmax()} 비중이 {mat.loc["한식음식점"].max():.1f}%로 가장 큽니다. 호프-간이주점은 {mat.loc["호프-간이주점"].idxmax()} 비중이 {mat.loc["호프-간이주점"].max():.1f}%로 가장 큽니다.',note,fmt='.1f')
# weekend normalized daily
week=ss.groupby('업종명')[['주중_매출_금액','주말_매출_금액']].sum(); week['주말하루비']= (week.iloc[:,1]/2)/(week.iloc[:,0]/5)
bar(week['주말하루비'].reindex(top),'(주말 합계÷2) ÷ (주중 합계÷5)','주중과 주말을 하루 기준으로 비교한다','1보다 크면 주말 하루 평균 매출이 주중보다 큽니다. 요일 개수 차이를 단순 보정했습니다.',f'상위 매출 업종 중 주말 쪽이 가장 강한 업종은 {week.loc[top,"주말하루비"].idxmax()}입니다.','주중을 5일, 주말을 2일로 단순 환산했습니다. 실제 영업일수와 공휴일은 반영하지 않았습니다.')
# franchise
fr=q4.groupby('업종명')[['점포수','프랜차이즈수']].sum(); fr=fr[fr['점포수']>=100]; ratio=fr['프랜차이즈수']/fr['점포수']*100
bar(ratio.nlargest(15),'프랜차이즈 비중 (%)','프랜차이즈 비중이 높은 업종','4분기 점포 100개 이상인 업종을 비교했습니다.',f'이 기준에서 비중 1위는 {ratio.idxmax()}({ratio.max():.1f}%)입니다.','가맹점이 많다는 사실만으로 신규 창업에 유리하거나 불리하다고 판단할 수 없습니다.')
flow=tt.groupby('분기')[['개업수','폐업수']].sum(); fig,ax=plt.subplots(figsize=(9,4)); flow.set_axis(['1분기','2분기','3분기','4분기']).plot.bar(ax=ax,color=C[:2],rot=0); ax.set_ylabel('개·폐업 건수'); save('분기별 개업과 폐업 건수','파란 막대는 개업, 주황 막대는 폐업입니다.',f'연간 개업 {flow["개업수"].sum():,}건, 폐업 {flow["폐업수"].sum():,}건입니다.','개업에서 폐업을 뺀 값이 점포 재고 증감과 항상 같지는 않습니다. 자료 정비와 분류 변화가 있을 수 있습니다.',fig)
r=industry[industry['평균점포수']>=100].nlargest(15,'연간폐업건수비'); fig,ax=plt.subplots(figsize=(10,6)); r[['연간개업건수비','연간폐업건수비']].plot.barh(ax=ax,color=C[:2]); ax.set_xlabel('연간 개·폐업 건수 ÷ 연평균 점포 수 (%)'); ax.set_ylabel(''); save('개업과 폐업이 잦은 업종','점포 규모 100개 이상 업종 중 폐업건수비 상위 15개입니다.',f'해당 기준에서 가장 높은 업종은 {r.index[0]}({r.iloc[0]["연간폐업건수비"]:.1f}%)입니다.','같은 점포를 1년간 추적한 폐업 확률이 아닙니다. 분기 폐업률을 단순 평균한 값도 아닙니다.',fig)
# small samples
fig,ax=plt.subplots(figsize=(9,4)); bins=pd.cut(p['점포수'],[-1,0,2,4,9,19,49,np.inf],labels=['0','1~2','3~4','5~9','10~19','20~49','50+']); bins.value_counts(sort=False).plot.bar(ax=ax,color=C[0],rot=0); ax.set_ylabel('상권×업종×분기 칸 수'); ax.set_xlabel('칸 안의 점포 수'); save('점포가 적은 칸이 얼마나 많은가','막대가 높으면 해당 규모의 칸이 많습니다.',f'전체 점포 칸 중 점포 5개 미만인 비중은 {(p["점포수"]<5).mean()*100:.1f}%입니다.','점포 2개인 칸에서 폐업 1건이면 단순 비율은 50%입니다. 작은 분모의 비율은 쉽게 흔들립니다.',fig)
# volatility
vc=full.groupby('업종명').agg(변동=('분기변동계수','median'),칸수=('상권코드','size')); vc=vc[vc['칸수']>=30]
bar(vc['변동'].nlargest(15)*100,'분기 매출 변동계수 중앙값 (%)','분기에 따라 매출이 크게 움직인 업종','변동계수는 표준편차÷평균입니다. 네 분기 매출이 얼마나 들쑥날쑥한지 봅니다.',f'완전 관측 조합이 30개 이상인 업종 중 가장 높은 업종은 {vc["변동"].idxmax()}입니다.','4개 값으로 계산했습니다. 값이 크면 계절성이 강할 수 있으며, 곧바로 사업 실패 위험을 뜻하지 않습니다.')
# joined area demand
tr=tt.groupby('상권코드').agg(분기점포합=('점포수','sum'),폐업수=('폐업수','sum')); tr['평균점포수']=tr['분기점포합']/4; tr['연매출_조원']=ss.groupby('상권코드')['매출'].sum(min_count=1)/1e12; tr['연간폐업건수비']=tr['폐업수']/tr['평균점포수'].replace(0,np.nan)*100
tr=tr.join(a.set_index('상권코드')[['상권명','상권구분']]); refresh=[]
for name,d in aux.items():
 valuecols=[c for c in d if c not in ['분기','상권코드','상권명','상권구분','상권_구분_코드']]
 d25=d[d['분기'].str.startswith('2025')].copy(); main=next(c for c in valuecols if c.startswith('총_')) if name!='집객시설' else '집객시설_수'
 tr[name]=d25.assign(v=pd.to_numeric(d25[main],errors='coerce')).groupby('상권코드')['v'].mean()
 sig=pd.util.hash_pandas_object(d[valuecols].fillna(''),index=False); w=d.assign(sig=sig).pivot(index='상권코드',columns='분기',values='sig').sort_index(axis=1)
 changes={q:int((w[q].notna()&w[prev].notna()&(w[q]!=w[prev])).sum()) for prev,q in zip(w.columns,w.columns[1:])}
 refresh.append({'데이터':name,'2025내값변경상권분기수':sum(v for q,v in changes.items() if q in ['20252','20253','20254']),'마지막관측변경분기':max([q for q,v in changes.items() if v>0],default='변경 없음')})
refresh=pd.DataFrame(refresh); refresh.to_csv(TAB/'refresh.csv',index=False,encoding='utf-8-sig')
bar(refresh.set_index('데이터')['2025내값변경상권분기수'],'직전 분기와 값이 다른 상권×분기 수','인구와 시설 값이 실제로 바뀌었는지 점검한다','2025년 2·3·4분기를 각각 직전 분기와 비교했습니다. 모든 수치 컬럼 중 하나라도 달라진 상권을 셉니다.', ' / '.join(f'{r["데이터"]}: {r["2025내값변경상권분기수"]:,}건' for _,r in refresh.iterrows()),'변경이 없다고 오류로 단정하지 않습니다. 파일의 기준분기와 실제 통계 작성시점이 다를 수 있습니다.')
corr=tr[['평균점포수','연매출_조원','연간폐업건수비','유동인구','직장인구','상주인구','집객시설']].corr(method='spearman')
heat(corr,'상권 규모와 수요 지표의 관계','순위상관은 -1~1입니다. +1에 가까우면 함께 커지고, -1에 가까우면 반대 방향입니다.',f'총매출과 유동인구의 순위상관은 {corr.loc["연매출_조원","유동인구"]:.2f}, 직장인구와는 {corr.loc["연매출_조원","직장인구"]:.2f}입니다.','상권 단위 관계이며 원인을 뜻하지 않습니다. 항목별로 값이 있는 상권만 사용합니다. 업종 구성·상권 면적을 보정하지 않았습니다.',cmap='RdBu',fmt='.2f')
fig,axes=plt.subplots(1,2,figsize=(12,4.5))
for ax,name in zip(axes,['유동인구','직장인구']):
 d=tr[(tr[name]>0)&(tr['연매출_조원']>0)]; ax.scatter(d[name],d['연매출_조원']*1e4,s=12,alpha=.35,color=C[0]); ax.set_xscale('log'); ax.set_yscale('log'); ax.xaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}')); ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}')); ax.set_xlabel(name+' (로그 눈금)'); ax.set_ylabel('연매출 (억원, 로그 눈금)'); ax.set_title(f'n={len(d):,}개 상권')
save('사람이 많은 상권의 매출을 점으로 확인한다','점 하나가 상권 하나입니다. 오른쪽은 인구가 많고 위쪽은 매출이 큽니다. 눈금 간격은 배수입니다.','같은 인구 수준에서도 매출이 넓게 퍼져 있습니다. 수요 지표 하나만으로 매출을 설명하기 어렵습니다.','유동인구는 고유 방문자 수나 실제 구매자 수가 아닙니다. 0 또는 결측인 값은 로그 그림에서 제외했습니다.',fig)
# cafe same industry
cafe=p[p['업종명']=='커피-음료'].copy(); cafe=cafe[cafe['매출'].notna()&(cafe['점포수']>0)]
fig,ax=plt.subplots(figsize=(9,5)); ax.hexbin(cafe['점포수'],cafe['점포당월매출'],xscale='log',yscale='log',gridsize=35,mincnt=1,cmap='Blues'); ax.xaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}')); ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}')); ax.set_xlabel('같은 상권의 커피-음료 점포 수 (로그)'); ax.set_ylabel('점포당 월 환산 매출 (만원, 로그)'); rho=cafe[['점포수','점포당월매출']].corr(method='spearman').iloc[0,1]; save('커피 업종에서 경쟁 점포와 매출을 함께 본다','육각형 색이 진하면 비슷한 값의 칸이 많습니다. 오른쪽으로 갈수록 같은 업종 점포가 많습니다.',f'커피-음료 관측 칸 {len(cafe):,}개에서 점포 수와 점포당 월 환산 매출의 순위상관은 {rho:.2f}입니다.','분기가 반복된 탐색 그림입니다. 점포가 많아서 매출이 올랐는지, 매출이 높은 곳에 점포가 모였는지 알 수 없습니다.',fig)
# map
m=a[a['상권구분']!='관광특구'].merge(tr[['연매출_조원','평균점포수']],left_on='상권코드',right_index=True,how='left'); fig,axes=plt.subplots(1,2,figsize=(13,7))
for ax,col,title in zip(axes,['연매출_조원','평균점포수'],['상권 연매출 (조원)','상권 연평균 점포 수']):
 m.plot(ax=ax,column=col,cmap='Blues',scheme=None,legend=True,vmax=m[col].quantile(.95),missing_kwds={'color':'#cccccc'}); ax.set_axis_off(); ax.set_title(title+'\n색 상한: 95백분위')
save('매출과 점포의 공간 분포','색이 진할수록 값이 큽니다. 회색은 연결된 값이 없고, 흰 배경은 상권 영역 밖입니다.','상권 경계에 관측 값을 직접 붙여 점포와 매출이 모여 있는 위치를 비교했습니다.','큰 값 몇 개 때문에 다른 상권이 흐려지지 않도록 색의 상한을 95백분위로 맞췄습니다. 상한 이상은 같은 색입니다. 면적당 밀도 지도가 아닙니다.',fig)
# S01
stores=pd.read_csv(RAW/'semas/extracted/semas_store_20251231/소상공인시장진흥공단_상가(상권)정보_서울_202512.csv',encoding='utf-8',dtype=str,usecols=['상가업소번호','시군구명','상권업종대분류명','경도','위도'])
bar(stores['시군구명'].value_counts(),'2025-12-31 상가업소 수','상가정보로 본 25개 자치구의 점포 분포','별도 출처인 소상공인 상가정보를 자치구별로 셌습니다.',f'원본은 {len(stores):,}행이고 상가업소번호 중복은 {stores["상가업소번호"].duplicated().sum():,}건입니다. 점포가 가장 많은 곳은 {stores["시군구명"].value_counts().index[0]}입니다.','서울 상권분석 데이터와 업종 범위·수집 기준이 다릅니다. 두 자료의 점포 수를 단순 합산하지 않습니다.')
bar(stores['상권업종대분류명'].value_counts(),'2025-12-31 상가업소 수','상가정보의 대분류별 구성','점포 수를 넓은 업종 묶음으로 나눴습니다.',f'가장 큰 대분류는 {stores["상권업종대분류명"].value_counts().index[0]}입니다.','소상공인 업종코드와 서울 서비스업종코드는 서로 다릅니다. 이름이 비슷하다고 자동으로 결합하지 않습니다.')
# extra time length correction
cols=[f'시간대_{x}_매출_금액' for x in ['00~06','06~11','11~14','14~17','17~21','21~24']]; vtime=ss[cols].sum()/np.array([6,5,3,3,4,3])/1e8; vtime.index=['00~06','06~11','11~14','14~17','17~21','21~24']
bar(vtime,'2025년 누적 매출 ÷ 시간대 길이 (억원/시간)','시간대 길이를 보정하면 어떻게 보일까','각 시간대 총매출을 그 시간대의 시간 수로 나눴습니다. 6시간 구간과 3시간 구간을 같은 길이로 비교하는 방법입니다.',f'시간 길이를 보정한 값이 가장 큰 구간은 {vtime.idxmax()}입니다.','연간 누적액을 시간대 길이로만 나눈 값입니다. 실제 하루·영업일당 시간 매출은 아닙니다.')
tr.to_csv(TAB/'districts.csv',encoding='utf-8-sig'); coverage.to_csv(TAB/'coverage.csv',encoding='utf-8-sig'); v.to_csv(TAB/'industry_coverage.csv',encoding='utf-8-sig')
# checks
assert len(p)==len(tt)
assert np.isclose(ss['매출'].sum(),ss.groupby('분기')['매출'].sum().sum())
assert ((t['일반점포수']+t['프랜차이즈수'])==t['점포수']).all()
orphans=ss.merge(tt[key],on=key,how='left',indicator=True)['_merge'].eq('left_only').sum()
zero=tt[tt['점포수']==0]; negative={c:int((s[c]<0).sum()) for c in ['매출','건수']}
def md(df):
 d=df.copy(); return '| '+' | '.join(map(str,d.columns))+' |\n| '+' | '.join(['---']*len(d.columns))+' |\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in d.itertuples(index=False,name=None))
summary=f'''# 서울 상권 EDA 재분석 (Codex)

작성일: 2026-10-31 · 분석 대상: 저장된 2025년 원본 · 분석 단위: 상권×업종×분기

기존 [클로드 EDA](README.md)를 참고해 확인할 질문을 정한 뒤, 원본 CSV와 상권 경계를 별도 코드로 다시 읽고 계산했다. 기존 요약 CSV와 그림을 재사용하지 않았다. 이 보고서는 **{len(sections)}개 시각화**와 그림별 읽는 방법·결과·주의점을 담았다. 원본과 기존 분석 파일은 수정하지 않았다.

## 먼저 알아둘 결과

- 관광특구를 뺀 2025년 관측 추정매출 합계는 **{ss['매출'].sum()/1e12:.2f}조원**이다. 서울 전체 업종의 실제 매출 합계가 아니다.
- 점포 자료는 **{tt['업종코드'].nunique()}개 업종**, 매출 자료는 **{ss['업종코드'].nunique()}개 업종**을 담고 있다. 매출이 보이지 않는 칸을 0원으로 채우면 안 된다.
- 매출 대상 62개 업종 칸 중 **{eligible['매출'].isna().mean()*100:.1f}%**는 매출 행이 없다. 관측 범위가 업종마다 다르므로 단순 매출 순위만으로 추천하기 어렵다.
- 점포당 월 환산 매출은 전체 관측 칸의 중앙값이 **{val.median():,.0f}만원**, 평균이 **{val.mean():,.0f}만원**이다. 큰 값의 영향을 줄여 보려면 중앙값도 함께 봐야 한다.
- 4개 분기에 모두 매출이 있는 동일 조합 {len(wide):,}개의 4분기 매출 지수는 **{idx.iloc[-1]:.1f}**다(1분기=100). 1년 자료만으로 장기 성장이라고 부르기 어렵다.

## 자료와 전처리

자료 설명은 [데이터 인수인계 문서](../docs/DATA_HANDOFF.md), 파일별 출처·수집 기록은 [데이터 카탈로그](../data/metadata/data_catalog.csv)에 있다. 이번 분석은 저장된 파일의 내용에 대한 재분석이며, 포털의 현재 자료나 공식 공개 정책을 새로 확인한 것은 아니다.

{md(quality)}

행·열 수는 읽어온 원본 기준이며 결측셀은 전체 제공 기간 기준이다. 집객시설·직장·상주인구 파일은 여러 연도를 포함하므로 실제 수요 결합에는 2025년만 골랐다. 결측이 있는 시설의 세부 항목을 임의로 0으로 채우지 않았다.

| 처리 | 적용한 기준 |
| --- | --- |
| 기간 | 2025Q1~Q4, 상가정보는 2025-12-31 스냅숏 |
| 서울 자료 결합 | 분기+상권코드+업종코드, 일대일 결합 검증 |
| 전체 점포 수 | `similr_induty_stor_co` 사용. 일반점포+프랜차이즈 합과 일치 검증 |
| 관광특구 | 공간 중복 가능성이 있어 주요 합계·관계 분석에서 제외 |
| 매출 없음 | 결측으로 유지. 0원으로 변환하지 않음 |
| 점포 수 | 분기 합계를 점포 총수라고 부르지 않음. 4분기 또는 연평균 사용 |
| 월 매출 환산 | 원본 `당월_매출_금액`을 분기 매출로 취급. 분기액÷3÷해당 분기 전체 점포 수 |
| 연간 점포당 월 환산 | 네 분기 매출이 모두 있는 조합에서 연매출÷연평균 점포 수÷12 |
| 개·폐업 건수비 | 연간 건수÷연평균 점포 수×100. 개별 점포의 폐업 확률이 아님 |
| 이상치 | 원본 값은 삭제하지 않음. 로그 눈금·중앙값·지도 색 상한으로 시각화 |
| 인구·시설 | 상권+분기로 별도 확인, 상권 요약에는 2025년 평균을 한 번 결합 |

## 품질 점검과 해석 범위

매출·점포의 분석 키 중복은 각각 {s.duplicated(key).sum():,}건, {t.duplicated(key).sum():,}건이다. 관광특구 제외 매출 중 점포에 연결되지 않는 행은 {orphans:,}건이다. 매출 및 매출 건수의 음수 행은 {negative['매출']:,}건, {negative['건수']:,}건이다. 왼쪽 결합 후 점포 행 수가 늘지 않았으며, 분기 매출 합이 연간 합계와 일치함을 검증했다.

점포 수가 0인 행에서도 폐업은 {zero['폐업수'].sum():,}건 기록되어 있다. 이 행들의 원본 폐업률 최댓값은 {zero['원본폐업률'].max():.0f}%다. 따라서 원본 폐업률의 단순 평균으로 안전한 상권을 고르면 안 된다. 건수와 분모를 함께 확인해야 한다.

{md(refresh)}

위 표의 마지막 변경은 파일에 있는 연속 분기 중 모든 값 컬럼을 비교한 결과다. 이는 실제 통계 조사일을 입증하지 않는다. 인구·시설이 같은 값으로 반복되면 네 분기를 서로 독립적인 네 관측치처럼 해석하지 않는다.

## 그림을 읽기 위한 짧은 안내

막대는 크기 비교, 선은 시간 흐름, 히트맵은 색과 숫자로 구성 비교, 점 그림은 두 값의 관계, 지도는 위치 비교에 쓴다. 비중은 전체에서 차지하는 몫이다. 로그 눈금은 큰 수와 작은 수를 한 그림에 보기 위해 10배·100배 단위로 간격을 잡는 방식이다. 관계가 보여도 원인과 결과가 밝혀진 것은 아니다.

'''
end='''## 기존 EDA와 비교한 판단

매출 대상 업종에서 점포 0~2개인 칸의 비중과 매출 행이 없는 칸의 비중은 서로 다른 지표다. 이번의 65.4%는 후자이며, 관광특구를 제외한 기준이다. 점포가 3개 이상이어도 매출 행이 없는 칸이 있어 기존 문서의 48.8%(점포 0~2개 칸 비중)와 같은 수치로 비교하면 안 된다. 업종별 관측 범위도 관광특구 제외 여부에 따라 달라진다.

이번에 직접 다시 확인한 내용은 매출 관측 범위의 차이, 관광특구 제외 전후 합계 차이, 업종 하나에 치우친 상권 매출, 인구·시설의 반복 값, 작은 칸의 비율 불안정성이다. 기존 EDA의 방향과 대체로 일치한다.

기존 EDA의 공간 중복 97.1%, 회귀 탄력성, 신뢰구간, 축소 추정, 상·하반기 신뢰도는 이번 코드에서 재계산하지 않았다. 따라서 그 수치까지 독립 검증했다고 주장하지 않는다. 전자상거래업의 높은 폐업건수비만으로 데이터 오류를 단정하거나 추천 대상에서 즉시 제외하기보다는, 정의와 자료 변동을 먼저 확인하는 편이 좋다.

이번에는 요일·시간대·연령 구성, 주말 하루 환산 비교, 시간대 길이 보정, 프랜차이즈 비중, 업종별 분기 변동, 동일 조합 분기 비교를 추가했다. 상권별 매출 규모와 실제 창업 적합성을 구분해 읽도록 설명을 붙였다.

## Spotfit 추천 설계에 적용하기

| 분석에서 확인한 문제 | 다음 처리 제안 |
| --- | --- |
| 업종별 매출 수준이 크게 다름 | 희망 업종 안에서 상권을 비교한다 |
| 매출 행이 없는 작은 칸이 많음 | 미공개·미관측 상태를 표시하고 매출 점수를 억지로 만들지 않는다 |
| 점포 수는 수요와 함께 움직일 수 있음 | 점포 수만으로 경쟁 감점을 주지 않는다. 동일 업종 안에서 수요·점포당 매출을 함께 본다 |
| 개폐업 비율의 분모가 작음 | 건수와 점포 수를 함께 제시하고 더 넓은 지역·기간으로 묶어 확인한다 |
| 고객 소비 시간과 연령이 업종마다 다름 | 희망 업종의 영업 시간·고객층과 맞는 상권을 비교한다 |
| 1년으로 계절성과 성장을 분리하기 어려움 | 2024년 이전 자료를 추가해 같은 분기끼리 비교한다 |
| 시설·인구가 반복됨 | 실제 통계 시점을 확인하고 고정 속성으로 쓸지 결정한다 |
| 임대료·인건비·보증금·권리금이 없음 | 매출을 이익으로 해석하지 않고, 예산 적합성 확정에는 별도 비용 자료를 확보한다 |

금융 MBTI별 가중치나 상권 추천 점수는 이 EDA에서 만들지 않았다. 사용자 유형의 정의와 검증 자료가 있어야 실제 추천 규칙을 평가할 수 있다.

## 재현 방법과 근거 파일

프로젝트의 기존 가상환경에서 다음 명령으로 보고서·그림·근거 표를 다시 생성할 수 있다.

```bash
cd seoul-commercial-analysis
.venv/bin/python 김지영/codex_eda/run_eda.py
```

필요 패키지: pandas, numpy, matplotlib, geopandas 및 geopandas의 공간 파일 읽기 의존성. 현재 프로젝트 가상환경으로 실행했다. 한글 폰트는 시스템에 설치된 Apple SD Gothic Neo 등을 자동 선택한다.

- [재현 코드](codex_eda/run_eda.py)
- [원본 품질 점검](codex_eda/tables/quality.csv)
- [점포 규모별 매출 관측 범위](codex_eda/tables/coverage.csv)
- [업종별 관측 범위](codex_eda/tables/industry_coverage.csv)
- [업종별 요약](codex_eda/tables/industry.csv)
- [네 분기 완전 관측 조합](codex_eda/tables/complete_cells.csv)
- [상권별 요약](codex_eda/tables/districts.csv)
- [데이터 값 변경 점검](codex_eda/tables/refresh.csv)

그림을 다른 폴더로 옮길 때는 이 문서와 `codex_eda/figures/`의 상대 경로를 함께 유지해야 한다.
'''
(OUT.parent/'eda(Codex).md').write_text(summary+'\n'.join(sections)+end,encoding='utf-8')
print(json.dumps({'figures':len(sections),'report':str(OUT.parent/'eda(Codex).md'),'font':font,'sales_trillion':ss['매출'].sum()/1e12,'missing_pct':eligible['매출'].isna().mean()*100,'refresh':refresh.to_dict('records')},ensure_ascii=False,indent=2))
