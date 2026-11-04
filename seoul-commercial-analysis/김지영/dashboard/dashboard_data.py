"""대시보드 데이터 처리. 미관측 매출과 실제 0을 구분한다."""
from pathlib import Path
from functools import lru_cache
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

TEAL='#147D72'; ORANGE='#DB8652'; INK='#243B37'; MUTED='#6C7B76'
TIMES=['00_06','06_11','11_14','14_17','17_21','21_24']
AGES=['10','20','30','40','50','60_plus']
BASE_COLS=['quarter','trdar_code','trdar_name','industry_code','industry_name','gu_name','trdar_type','main_analysis_eligible','store_count','open_count','close_count','franchise_store_count','sales_amount','sales_observed','sales_status','sales_per_store_month','sales_vs_industry_median','industry_peer_count','weekend_sales','weekday_sales','gender_sales_coverage','age_sales_coverage']
BASE_COLS += [f'time_{x}_sales' for x in TIMES]+[f'age_{x}_sales' for x in AGES]+[f'day_{i}_sales' for i in range(1,8)]

@lru_cache(maxsize=1)
def load_bundle(directory):
    directory=Path(directory); source=directory.parent/'step2_3'
    required=[source/'data/fact_trdar_industry_quarter.csv.gz',source/'data/trdar_quarter_context.csv.gz',source/'data/annual_features.csv.gz',source/'feature_dictionary.csv',source/'manifest.json']
    missing=[str(p) for p in required if not p.exists()]
    if missing: raise FileNotFoundError('STEP 2·3 데이터를 먼저 생성하세요: '+', '.join(missing))
    ids={'quarter':str,'trdar_code':str,'industry_code':str}
    fact=pd.read_csv(required[0],dtype=ids,usecols=BASE_COLS)
    fact=fact.loc[fact['main_analysis_eligible']].copy()
    context=pd.read_csv(required[1],dtype=ids)
    annual=pd.read_csv(required[2],dtype=ids)
    points_path=directory/'assets/trdar_points.csv'
    points=pd.read_csv(points_path,dtype={'trdar_code':str}) if points_path.exists() else pd.DataFrame(columns=['trdar_code','lat','lon'])
    outlines_path=directory/'assets/trdar_outlines.json'
    points.attrs['outlines']=json.loads(outlines_path.read_text()) if outlines_path.exists() else None
    return {'fact':fact,'context':context,'annual':annual,'dictionary':pd.read_csv(required[3]),'manifest':json.loads(required[4].read_text()),'points':points,'directory':directory}

def filter_scope(fact,industry,quarter,gu='서울 전체',trdar_type='전체 유형',minimum=5):
    history=fact.loc[fact['industry_code'].eq(industry)].copy()
    if gu!='서울 전체': history=history.loc[history['gu_name'].eq(gu)]
    if trdar_type!='전체 유형': history=history.loc[history['trdar_type'].eq(trdar_type)]
    scope=history.loc[history['quarter'].eq(quarter)&history['store_count'].ge(minimum)].copy()
    return scope,history

def metrics(scope):
    return {'areas':scope['trdar_code'].nunique(),'stores':scope['store_count'].sum() if len(scope) else None,'sales':scope['sales_amount'].sum(min_count=1),'observed':int(scope['sales_observed'].sum()),'median_month':scope['sales_per_store_month'].median(),'coverage':scope['sales_observed'].mean() if len(scope) else None}

def table_data(scope):
    d=scope[['trdar_name','gu_name','trdar_type','store_count','sales_amount','sales_per_store_month','open_count','close_count','sales_status','sales_vs_industry_median']].copy()
    d['sales_amount']=d['sales_amount']/1e8; d['sales_per_store_month']=d['sales_per_store_month']/1e4
    d['sales_status']=d['sales_status'].map({'observed':'매출 관측','unsupported_industry':'매출 미제공 업종','missing_cell':'해당 칸 매출 없음'})
    return d.rename(columns={'trdar_name':'상권','gu_name':'자치구','trdar_type':'유형','store_count':'점포 수','sales_amount':'분기 매출(억원)','sales_per_store_month':'점포당 월 환산(만원)','open_count':'개업 건수','close_count':'폐업 건수','sales_status':'매출 자료 상태','sales_vs_industry_median':'서울 동일 업종 중앙값 대비(배)'}).round(2)

def style(fig,height=370):
    fig.update_layout(template='plotly_white',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font={'family':'Apple SD Gothic Neo, AppleGothic, sans-serif','color':INK,'size':12},margin={'l':15,'r':20,'t':45,'b':30},height=height,hoverlabel={'bgcolor':'white'},colorway=[TEAL,ORANGE,'#8AAE9F','#A7A2BF'],legend={'orientation':'h','y':1.15,'x':0},title={'font':{'size':16}},modebar={'bgcolor':'rgba(0,0,0,0)'})
    fig.update_xaxes(gridcolor='#E9EEEB',zeroline=False);fig.update_yaxes(gridcolor='#E9EEEB',zeroline=False)
    return fig

def empty_chart(message='이 조건에 표시할 자료가 없습니다.'):
    f=go.Figure();f.add_annotation(text=message,x=.5,y=.5,xref='paper',yref='paper',showarrow=False,font={'size':15,'color':MUTED});f.update_xaxes(visible=False);f.update_yaxes(visible=False);return style(f)

def ranking_chart(scope,metric='sales_per_store_month'):
    d=scope.dropna(subset=[metric]).nlargest(12,metric).sort_values(metric)
    if d.empty:return empty_chart('관측된 매출 자료가 없습니다. 점포·개폐업 자료는 아래에서 확인하세요.')
    scale=1e4 if metric=='sales_per_store_month' else 1e8 if metric=='sales_amount' else 1
    label='점포당 월 환산 매출 (만원)' if metric=='sales_per_store_month' else '분기 추정매출 (억원)' if metric=='sales_amount' else '점포 수'
    f=go.Figure(go.Bar(x=d[metric]/scale,y=d['trdar_name'],orientation='h',marker_color=TEAL,customdata=d[['store_count']],hovertemplate='%{y}<br>'+label+': %{x:,.1f}<br>점포 %{customdata[0]:,}개<extra></extra>'))
    f.update_xaxes(title=label);f.update_yaxes(title=None,automargin=True);return style(f,450)

def trend_chart(history,minimum,metric='sales'):
    d=history.loc[history['store_count'].ge(minimum)]
    if d.empty:return empty_chart()
    g=d.groupby('quarter').agg(sales=('sales_amount',lambda x:x.sum(min_count=1)),stores=('store_count','sum'),observed=('sales_observed','sum'),areas=('trdar_code','nunique')).reset_index()
    g['분기']=g['quarter'].map(lambda q:f'{q[:4]} Q{q[-1]}');g['매출(억원)']=g['sales']/1e8
    if metric=='sales' and g['sales'].isna().all():return empty_chart('이 업종은 분기 매출 자료가 없습니다.')
    f=px.line(g,x='분기',y='매출(억원)' if metric=='sales' else 'stores',markers=True,custom_data=['areas','observed'])
    f.update_traces(line_color=TEAL,line_width=3,marker_size=8,connectgaps=False,hovertemplate='%{x}<br>%{y:,.1f}<br>조건 충족 상권 %{customdata[0]}개<br>매출 관측 %{customdata[1]}개<extra></extra>'); f.update_yaxes(title='관측 매출 (억원)' if metric=='sales' else '점포 수');return style(f)

def map_chart(scope,points):
    if points.empty:return empty_chart('지도 좌표 파일이 없습니다. 순위와 표는 정상적으로 이용할 수 있습니다.')
    d=scope.merge(points,on='trdar_code',how='inner',validate='one_to_one')
    if d.empty:return empty_chart()
    f=go.Figure()
    outlines=points.attrs.get('outlines')
    if outlines: f.add_trace(go.Scattermap(lat=outlines['lat'],lon=outlines['lon'],mode='lines',line={'width':1,'color':'#D8E2DA'},hoverinfo='skip',showlegend=False))
    for observed,color in [(False,'#BAC4BF'),(True,TEAL)]:
        z=d.loc[d['sales_observed'].eq(observed)].copy()
        if z.empty:continue
        custom=np.column_stack([z['trdar_name'],z['store_count'],z['sales_per_store_month'].div(1e4).map(lambda x:'자료 없음' if pd.isna(x) else f'{x:,.0f}만원')])
        f.add_trace(go.Scattermap(lat=z['lat'],lon=z['lon'],mode='markers',name='매출 관측' if observed else '매출 없음',marker={'size':9,'color':color,'opacity':.75},customdata=custom,hovertemplate='%{customdata[0]}<br>점포 %{customdata[1]}개<br>점포당 월 환산: %{customdata[2]}<extra></extra>'))
    f.update_layout(map={'style':'white-bg','center':{'lat':37.555,'lon':126.995},'zoom':10.1},legend={'orientation':'h','y':1.08},margin={'l':0,'r':0,'t':35,'b':0});return style(f,450)

def selected_trend(history,code):
    d=history.loc[history['trdar_code'].eq(code)].sort_values('quarter')
    if d.empty:return empty_chart('상권을 선택하세요.')
    f=go.Figure(); f.add_trace(go.Bar(x=d['quarter'].str[-1]+'분기',y=d['sales_amount']/1e8,name='분기 매출',marker_color=TEAL)); f.update_yaxes(title='분기 추정매출 (억원)'); return style(f)

def selected_flow(history,code):
    d=history.loc[history['trdar_code'].eq(code)].sort_values('quarter')
    if d.empty:return empty_chart()
    f=go.Figure()
    for col,label,color in [('open_count','개업',TEAL),('close_count','폐업',ORANGE)]: f.add_trace(go.Bar(x=d['quarter'].str[-1]+'분기',y=d[col],name=label,marker_color=color))
    f.update_layout(barmode='group');f.update_yaxes(title='건수');return style(f)

def profile_chart(rows,kind='time'):
    if rows.empty or not rows['sales_observed'].any():return empty_chart('매출 자료가 없어 고객 구성을 계산할 수 없습니다.')
    if kind=='time': cols=[f'time_{x}_sales' for x in TIMES]; labels=['00–06','06–11','11–14','14–17','17–21','21–24'];denom=rows['sales_amount'].sum(min_count=1)
    elif kind=='age':cols=[f'age_{x}_sales' for x in AGES];labels=['10대','20대','30대','40대','50대','60대+'];denom=rows[cols].sum(min_count=1).sum(min_count=1)
    else: cols=[f'day_{i}_sales' for i in range(1,8)];labels=list('월화수목금토일');denom=rows['sales_amount'].sum(min_count=1)
    if pd.isna(denom) or denom<=0:return empty_chart('비중을 계산할 양수 매출이 없습니다.')
    values=rows[cols].sum(min_count=1)/denom*100
    f=go.Figure(go.Bar(x=labels,y=values,marker_color=[TEAL if pd.notna(v) and v==values.max() else '#A9CBBF' for v in values],text=values.map(lambda x:'' if pd.isna(x) else f'{x:.1f}%'),textposition='outside',hovertemplate='%{x}: %{y:.1f}%<extra></extra>'));f.update_yaxes(title='매출 비중 (%)',rangemode='tozero');return style(f)

def scatter_chart(scope):
    d=scope.loc[scope['store_count'].gt(0)&scope['sales_per_store_month'].gt(0)].copy()
    if d.empty:return empty_chart('비교할 양수 매출 자료가 없습니다.')
    d['월 환산 매출(만원)']=d['sales_per_store_month']/1e4
    f=px.scatter(d,x='store_count',y='월 환산 매출(만원)',hover_name='trdar_name',color='trdar_type',log_x=True,log_y=True,labels={'store_count':'같은 업종 점포 수','trdar_type':'상권 유형'},opacity=.65);return style(f)

def selected_context(bundle,quarter,code):
    z=bundle['context'];return z.loc[z['quarter'].eq(quarter)&z['trdar_code'].eq(code)]
