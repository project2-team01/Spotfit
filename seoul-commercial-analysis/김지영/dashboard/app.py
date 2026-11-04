import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Spotfit · 서울 상권 탐색")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    from pathlib import Path
    import sys
    import html
    import re

    dashboard_dir = Path(__file__).resolve().parent
    if str(dashboard_dir) not in sys.path:
        sys.path.insert(0, str(dashboard_dir))
    import dashboard_data as dd
    return dashboard_dir, dd, html, mo, np, pd, re


@app.cell(hide_code=True)
def _(mo):
    mo.Html('''<style>
    :root {--sf-ink:#243b37; --sf-muted:#6c7b76; --sf-accent:#147d72;}
    body {background:#f7f8f4 !important; color:var(--sf-ink);}
    #root {font-family:"Apple SD Gothic Neo","Noto Sans KR",sans-serif;}
    .sf-hero {padding:30px 0 24px;border-bottom:1px solid #dce5df; margin-bottom:12px;}
    .sf-brand {font-size:15px;letter-spacing:.16em;font-weight:800;color:#147d72;}
    .sf-hero h1 {font-size:clamp(28px,3vw,42px);line-height:1.2;letter-spacing:-1.3px;margin:17px 0 12px;}
    .sf-hero p {font-size:15px;color:#6c7b76;line-height:1.7;margin:0;}
    .sf-eyebrow {font-size:12px;letter-spacing:.10em;color:#6c7b76;font-weight:700;}
    .sf-kpis {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:8px 0 10px;}
    .sf-kpi {background:white;border:1px solid #dce5df;border-radius:14px;padding:22px;}
    .sf-kpi .label {font-size:13px;color:#6c7b76;}
    .sf-kpi .value {font-size:30px;font-weight:750;letter-spacing:-1px;margin:8px 0;color:#147d72;}
    .sf-kpi .sub {font-size:12px;line-height:1.5;color:#6c7b76;}
    .sf-note {padding:12px 16px;background:#edf4ef;border-left:3px solid #147d72;border-radius:6px;font-size:13px;line-height:1.7;color:#405b50;}
    .sf-foot {font-size:12px;color:#6c7b76;padding:22px 0;border-top:1px solid #dce5df;line-height:1.8;}
    .sf-panel {background:white;border:1px solid #dce5df;border-radius:14px;padding:18px;}
    @media(max-width:800px){.sf-kpis{grid-template-columns:repeat(2,minmax(0,1fr));}.sf-kpi{padding:16px;}.sf-kpi .value{font-size:25px;}}
    </style>''')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.Html('''<header class="sf-hero"><div class="sf-brand">SPOTFIT <span style="font-weight:400;color:#7c8f85">/ SEOUL 2025</span></div><h1>내 업종에 맞는 상권, 데이터로 살펴보기</h1><p>상권의 크기부터 고객이 소비하는 시간까지.<br>2025년 서울 상권 데이터를 골라 보고, 비교하고, 이해해 보세요.</p></header>''')
    return


@app.cell(hide_code=True)
def _(dashboard_dir, dd, mo):
    try:
        bundle = dd.load_bundle(dashboard_dir)
        load_error = None
    except FileNotFoundError as _error:
        bundle = None
        load_error = str(_error)
    mo.stop(bundle is None, mo.callout(load_error or "데이터를 읽을 수 없습니다.", kind="warn"))
    fact = bundle['fact']
    return bundle, fact


@app.cell(hide_code=True)
def _(fact, mo):
    _industries = fact[['industry_code', 'industry_name']].drop_duplicates().sort_values('industry_name')
    _options = dict(zip(_industries['industry_name'], _industries['industry_code']))
    industry_filter = mo.ui.dropdown(_options, value='커피-음료', searchable=True, label='희망 업종', full_width=True)
    quarter_filter = mo.ui.dropdown({'2025년 1분기':'20251','2025년 2분기':'20252','2025년 3분기':'20253','2025년 4분기':'20254'},value='2025년 4분기',label='기준 분기', full_width=True)
    gu_filter = mo.ui.dropdown(['서울 전체'] + sorted(fact['gu_name'].dropna().unique()), value='서울 전체', label='자치구', full_width=True)
    type_filter = mo.ui.dropdown(['전체 유형','골목상권','발달상권','전통시장'],value='전체 유형',label='상권 유형',full_width=True)
    minimum_filter = mo.ui.slider(0,50,step=1,value=5,label='같은 업종 최소 점포 수',show_value=True,full_width=True,debounce=True)
    mo.vstack([mo.hstack([industry_filter,quarter_filter,gu_filter,type_filter],widths='equal',wrap=True),minimum_filter,mo.md('관광특구는 중복 집계를 막기 위해 제외했습니다. 최소 점포 수는 선택 분기의 같은 업종 점포 수에 적용합니다.')],gap=.6)
    return gu_filter, industry_filter, minimum_filter, quarter_filter, type_filter


@app.cell(hide_code=True)
def _(dd, fact, gu_filter, industry_filter, minimum_filter, quarter_filter, type_filter):
    scope, history = dd.filter_scope(fact,industry_filter.value,quarter_filter.value,gu_filter.value,type_filter.value,minimum_filter.value)
    return history, scope


@app.cell(hide_code=True)
def _(dd, html, industry_filter, mo, pd, quarter_filter, scope):
    _m = dd.metrics(scope)
    _format = lambda v,fmt=',.0f': '자료 없음' if v is None or pd.isna(v) else format(v,fmt)
    _sales = None if pd.isna(_m['sales']) else _m['sales']/1e8
    _median = None if pd.isna(_m['median_month']) else _m['median_month']/1e4
    _cards = [
        ('조건에 맞는 상권',f'{_m["areas"]:,}곳','선택한 업종·지역·점포 수 기준'),
        ('같은 업종 점포',_format(_m['stores'])+'개' if _m['stores'] is not None else '자료 없음','선택 분기 한 시점의 점포 수'),
        ('관측 분기 매출',_format(_sales,',.1f')+'억원' if _sales is not None else '자료 없음',f'매출 행이 있는 {_m["observed"]:,}개 상권의 합계'),
        ('점포당 월 환산 중앙값',_format(_median,',.0f')+'만원' if _median is not None else '자료 없음','관측 상권별 매출÷점포 수÷3의 가운데 값')
    ]
    _markup = ''.join(f'<div class="sf-kpi"><div class="label">{html.escape(a)}</div><div class="value">{html.escape(b)}</div><div class="sub">{html.escape(c)}</div></div>' for a,b,c in _cards)
    mo.vstack([mo.Html(f'<div class="sf-eyebrow">2025 Q{quarter_filter.value[-1]} · {html.escape(industry_filter.selected_key or "")}</div><div class="sf-kpis">{_markup}</div>'),mo.Html(f'<div class="sf-note">매출이 없는 상권은 0원으로 계산하지 않았습니다. 관측 매출은 자료가 있는 상권만의 합계이며, 실제 서울 전체 업종 매출이나 가게의 이익을 뜻하지 않습니다.</div>')])
    return


@app.cell(hide_code=True)
def _(mo, scope):
    _choices = {f'{r.trdar_name} · {r.gu_name} [{r.trdar_code}]':r.trdar_code for r in scope.sort_values('trdar_name')[['trdar_code','trdar_name','gu_name']].itertuples(index=False)}
    area_select = mo.ui.dropdown(_choices or {'선택 조건에 맞는 상권 없음':None},value=next(iter(_choices),'선택 조건에 맞는 상권 없음'),searchable=True,label='자세히 볼 상권',full_width=True)
    rank_metric = mo.ui.dropdown({'점포당 월 환산 매출':'sales_per_store_month','분기 추정매출 합계':'sales_amount','같은 업종 점포 수':'store_count'},value='점포당 월 환산 매출',label='순위 기준',full_width=True)
    return area_select, rank_metric


@app.cell(hide_code=True)
def _(dashboard_dir, mo, re):
    _report = dashboard_dir.parent/'eda(Codex).md'
    gallery_titles = dict((f'{int(n):02d}. {title}',f'{int(n):02d}.png') for n,title in re.findall(r'^## (\d+)\. (.+)$',_report.read_text()) if int(n)<=31) if _report.exists() else {}
    gallery_select = mo.ui.dropdown(gallery_titles or {'EDA 그림 없음':None},value=next(iter(gallery_titles),'EDA 그림 없음'),label='EDA 그림 선택',searchable=True,full_width=True)
    gallery_report = _report.read_text() if _report.exists() else ''
    return gallery_report, gallery_select


@app.cell(hide_code=True)
def _(area_select, bundle, dashboard_dir, dd, gallery_report, gallery_select, history, html, minimum_filter, mo, np, pd, quarter_filter, rank_metric, re, scope):
    def panel(title,content,explanation):
        return mo.vstack([mo.md(f'### {title}'),content,mo.md(explanation)],gap=.5).style({'background':'white','border':'1px solid #dce5df','border-radius':'14px','padding':'18px'})

    def chart(figure):
        return mo.ui.plotly(figure,config={'displaylogo':False,'responsive':True,'modeBarButtonsToRemove':['lasso2d','select2d']})

    _table = dd.table_data(scope)
    _download = mo.download(_table.to_csv(index=False).encode('utf-8-sig'),filename=f'spotfit_{quarter_filter.value}.csv',label='현재 조건의 표 CSV 저장',mimetype='text/csv')
    _overview = mo.vstack([
        rank_metric,
        mo.hstack([
            panel('관측 상권의 위치',chart(dd.map_chart(scope,bundle['points'])),'점 하나는 상권의 대표 위치입니다. 초록색은 매출 자료가 있는 곳, 회색은 없는 곳입니다. 옅은 선은 상권 경계입니다. 상권의 면적이나 매출 순위를 뜻하지 않습니다.'),
            panel('선택 기준 상위 12개',chart(dd.ranking_chart(scope,rank_metric.value)),'막대가 길수록 선택한 값이 큽니다. 매출 기준에서는 자료가 없는 칸을 제외합니다. **높은 매출은 높은 이익이나 창업 성공을 보장하지 않습니다.**')
        ],widths=[1,1],wrap=True,align='start'),
        mo.hstack([
            panel('네 분기의 매출 흐름',chart(dd.trend_chart(history,minimum_filter.value)),'분기마다 같은 업종·지역·점포 기준을 다시 적용한 관측 합계입니다. 분기별 포함 상권이 달라질 수 있고 계절성도 섞입니다. **전년 대비 성장률이 아닙니다.**'),
            panel('점포 수와 점포당 매출',chart(dd.scatter_chart(scope)),'점 하나는 상권입니다. 오른쪽은 같은 업종 점포가 많고 위쪽은 점포당 매출이 큽니다. 눈금은 배수입니다. 점포가 많아 매출이 오른 것인지, 수요가 있어 점포가 모인 것인지는 알 수 없습니다.')
        ],widths=[1,1],wrap=True,align='start'),
        panel('상권 비교표',mo.ui.table(_table,selection=None,page_size=12,show_data_types=False,show_column_summaries=False),'열 제목을 눌러 정렬하고 검색할 수 있습니다. 빈 매출 칸은 0원이 아닙니다. 업종 중앙값 배율은 서울 전체의 같은 업종·분기에서 계산한 기존 지표로, 현재 지역 필터에 따라 다시 계산한 값은 아닙니다.'),
        _download
    ])
    _code = area_select.value
    _selected = scope.loc[scope['trdar_code'].eq(_code)]
    _context = dd.selected_context(bundle,quarter_filter.value,_code)
    if _selected.empty:
        _detail = mo.callout('조건에 맞는 상권이 없습니다. 최소 점포 수를 낮추거나 지역·유형을 넓혀 보세요.',kind='info')
        _profiles = mo.callout('선택할 상권이 없습니다. 필터를 조정해 주세요.',kind='info')
    else:
        _row = _selected.iloc[0]
        _status = {'observed':'매출 관측','unsupported_industry':'매출 미제공 업종','missing_cell':'이 칸의 매출 자료 없음'}[_row['sales_status']]
        _peer = '비교 자료 부족' if pd.isna(_row['sales_vs_industry_median']) else f'서울 동일 업종 중앙값의 {_row["sales_vs_industry_median"]:.2f}배'
        _intro = mo.md(f'## {html.escape(_row["trdar_name"])}\n{_row["gu_name"]} · {_row["trdar_type"]} · {_row["store_count"]:,}개 점포 · **{_status}**\n\n{_peer}. 점포 5개 이상·관광특구 제외·동일 분기 업종 비교집단 30개 이상일 때만 매출 배율을 제공합니다.')
        _demand = []
        if not _context.empty:
            _ctx = _context.iloc[0]
            for _col,_label in [('floating_population','유동인구(원자료 수)'),('worker_population','직장인구(명)'),('resident_population','상주인구(명)'),('facility_count','집객시설(원자료 수)')]:
                _v = _ctx[_col]
                _demand.append({'지표':_label,'값':'자료 없음' if pd.isna(_v) else f'{_v:,.0f}','작성 시점 확인':{'changes_within_2025':'2025년 내 값 변화 있음','unchanged_within_2025_actual_vintage_unknown':'2025년 내 값 동일 · 실제 통계 시점 미확인'}.get(_ctx.get(_col+'_reference_time_status'),'확인 필요')})
        _annual = bundle['annual'].loc[bundle['annual']['trdar_code'].eq(_code)&bundle['annual']['industry_code'].eq(_row['industry_code'])]
        _annual_text = '연간 자료가 없습니다.'
        if not _annual.empty:
            _ar = _annual.iloc[0]
            _cv = '자료 없음' if pd.isna(_ar['annual_sales_cv']) else f'{_ar["annual_sales_cv"]*100:.1f}%'
            _as = '자료 없음' if pd.isna(_ar['annual_sales_complete']) else f'{_ar["annual_sales_complete"]/1e8:,.1f}억원'
            _annual_text = f'**2025년 완전 연매출:** {_as} · **매출 관측:** {int(_ar["observed_sales_quarters"])}개 분기 · **분기 매출 변동계수:** {_cv}. 네 분기 모두 관측된 경우에만 연매출·변동계수를 계산합니다. 변동계수는 매출의 출렁임이며, 장기 안정성 점수가 아닙니다.'
        _detail = mo.vstack([_intro,mo.hstack([panel('선택 상권의 분기 매출',chart(dd.selected_trend(history,_code)),'위의 분기 필터와 관계없이 선택 상권의 2025년 네 분기를 보여 줍니다. 매출 자료가 없는 분기는 막대를 만들지 않습니다.'),panel('선택 상권의 개업·폐업',chart(dd.selected_flow(history,_code)),'파란색 계열은 개업, 주황색은 폐업 건수입니다. 개업−폐업이 점포 수 증감과 항상 같지는 않습니다.')],widths=[1,1],wrap=True),mo.callout(mo.md(_annual_text),kind='info'),panel('상권의 수요와 시설',mo.ui.table(pd.DataFrame(_demand),selection=None,show_data_types=False,show_column_summaries=False),'유동·직장·상주인구는 서로 다른 개념이라 합산하지 않습니다. 직장·상주인구와 시설은 2025년 내 값이 반복되며 실제 통계 작성 시점은 확인되지 않았습니다.')])
        _profiles = mo.vstack([
            mo.md(f'## {html.escape(_row["trdar_name"])}의 고객과 소비 시간\n선택 분기·선택 업종의 관측 매출로 계산했습니다.'),
            mo.hstack([panel('어느 시간에 소비할까?',chart(dd.profile_chart(_selected,'time')),'진한 막대는 비중이 가장 높은 시간대입니다. 6시간 구간과 3시간 구간이 섞여 있으므로 시간당 매출 효율과 다릅니다.'),panel('어느 연령대가 소비할까?',chart(dd.profile_chart(_selected,'age')),'알려진 연령 매출의 합을 100%로 둔 구성입니다. 지역 거주민이나 방문자의 연령 비중이 아닙니다.')],widths=[1,1],wrap=True),
            panel('어느 요일에 소비할까?',chart(dd.profile_chart(_selected,'day')),'선택 상권·업종의 요일별 매출 비중입니다. 공휴일과 실제 영업일수는 보정하지 않았습니다.')
        ])
    _image_path = dashboard_dir.parent/'codex_eda/figures'/str(gallery_select.value)
    _gallery_items = [gallery_select,mo.callout('이 탭은 기존 EDA 그림 31개를 보여 줍니다. 위의 업종·지역·분기 필터가 적용되는 그림이 아닙니다.',kind='info')]
    if gallery_select.value and _image_path.exists():
        _gallery_items.append(mo.image(str(_image_path),width='100%'))
        _number = int(str(gallery_select.value).split('.')[0])
        _match = re.search(rf'^## {_number}\. .*?\n(.*?)(?=^## |\Z)',gallery_report,re.M|re.S)
        if _match:
            _text = re.sub(r'!\[[^\]]*\]\([^\n]+\)','',_match.group(1)).strip()
            _gallery_items.append(mo.md(_text))
    _dictionary = bundle['dictionary'].rename(columns={'variable':'변수명','level':'분석 단위','formula':'계산식','unit':'단위','source':'출처','purpose':'목적','interpretation':'해석','availability':'산출 상태'})
    _quality = mo.vstack([
        mo.md('## 숫자를 믿기 전에 확인할 것\n매출과 점포의 자료 범위가 다릅니다. 이 화면은 자료가 없는 값을 임의로 채우지 않습니다.'),
        panel('현재 필터의 매출 자료 상태',mo.ui.table(scope['sales_status'].map({'observed':'매출 관측','missing_cell':'해당 칸 매출 없음','unsupported_industry':'매출 미제공 업종'}).value_counts().rename_axis('자료 상태').reset_index(name='상권 수'),selection=None,show_data_types=False,show_column_summaries=False),'선택 업종에 매출을 제공하지 않아도 점포·개폐업 자료는 볼 수 있습니다. 매출이 안 보인다고 장사가 안 된다는 뜻은 아닙니다.'),
        mo.accordion({'분석 범위와 시점':mo.md('2025년 서울 서비스업종 100개 중 추정매출은 62개 업종에 있습니다. 관광특구는 제외합니다. 인구·시설은 제공 분기에 맞춰 연결했으며 실제 작성시점을 확인한 것은 아닙니다. 임대료·비용·순이익과 금융 MBTI 추천 점수는 이 대시보드에 없습니다.'),'점포당 매출과 개폐업 비율':mo.md('점포당 월 환산=분기 매출÷전체 점포 수÷3입니다. 개별 가게의 실적이 아닙니다. 연간 폐업 건수÷평균 점포 수는 폐업 확률이 아니고, 매출 없음과 분모 0은 결측으로 보존합니다.'),'업종 중앙값 배율의 기준':mo.md('같은 업종·분기에서 관광특구를 빼고 점포 5개 이상·매출이 있는 상권들로 중앙값을 계산했습니다. 비교집단이 30개 미만이면 배율을 만들지 않습니다. 자치구 필터를 바꿔도 서울 기준은 유지합니다.')}),
        panel('파생변수 사전',mo.ui.table(_dictionary,selection=None,page_size=10,show_data_types=False,show_column_summaries=False),'산출 변수와 자료 부족으로 보류한 변수를 함께 확인할 수 있습니다.')
    ])
    mo.vstack([
        mo.hstack([area_select],justify='start'),
        mo.ui.tabs({'상권 비교':_overview,'선택 상권 상세':_detail,'고객·소비 시간':_profiles,'EDA 그림 모음':mo.vstack(_gallery_items),'데이터 확인':_quality}),
        mo.Html('<footer class="sf-foot">출처: 서울특별시 상권분석서비스 · 소상공인시장진흥공단 상가(상권)정보<br>분석: Spotfit / 2025년 저장 원본 기반 · EDA 및 STEP 2·3 · 매출은 추정치이며 인과관계나 창업 성공을 뜻하지 않습니다.</footer>')
    ],gap=1.5)
    return


if __name__ == "__main__":
    app.run()
