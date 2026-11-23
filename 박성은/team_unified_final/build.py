"""팀 최신 산출물의 독립 대조 및 통합. 다른 팀원 파일에는 쓰지 않는다."""
from pathlib import Path
import importlib.util
import sys
import json
import hashlib
import ast
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
VERSION='team-evidence-20261123'
SOURCE='aafbb4a'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
jy=module('jy_final',ROOT/'김지영/step6_final/build_final.py')
js=module('jy_scores',ROOT/'김지영/step4_dashboard/build_scores.py')
sys.path.insert(0,str(ROOT/'박성은/integrated_dashboard'))
legacy=module('canonical_adapter',ROOT/'박성은/integrated_dashboard/build.py')
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def digest(path):
    data=path.read_bytes()
    if path.suffix in {'.py','.md','.csv','.json','.js','.html','.css'}: data=data.replace(b'\r\n',b'\n')
    return hashlib.sha256(data).hexdigest()
def compare(a,b,cols):
    c=a.merge(b,on=['trdar_code','industry_code'],suffixes=('_a','_b'),validate='one_to_one')
    result={}
    for left,right in cols:
        x=c[left+'_a' if left in b.columns else left];y=c[right+'_b' if right in a.columns else right]
        same=np.isclose(x,y,atol=1e-9,rtol=1e-10,equal_nan=True)
        result[left]={'different':int((~same).sum()),'compared':len(c),'max_abs':float((x-y).abs().max())}
    return result

def main():
    # 저장 결과를 믿기 전에 공통 원패널에서 김지영 점수를 다시 계산한다.
    raw=js.read_inputs();area,_=js.build_areas(raw['context'],raw['dim']);fresh,_=js.build_cells(raw,area)
    saved=pd.read_parquet(jy.INPUTS['scores'])
    score_cols=['score_sales','score_competition','score_stability','score_demand','score_total']
    oracle=compare(fresh,saved,[(x,x) for x in score_cols])
    assert all(v['different']==0 for v in oracle.values())
    # 이 어댑터는 원패널의 연간 점포·매출·거래건수·점수·유형을 별도 재계산한다.
    canonical,axes,hashes=legacy.build_data()
    keys=['trdar_code','industry_code']
    sh=pd.read_parquet(ROOT/'이승희/step4_dashboard/data/상권_업종_비교점수_2025.parquet')
    ps=pd.read_parquet(ROOT/'박성은/step4_dashboard/data/상권_업종_비교점수_2025.parquet')
    target=canonical.score_status.eq('점수 대상');ct=canonical.loc[target]
    mapped=[('score_sales','score_sales'),('score_comp','score_competition'),('score_stab','score_stability'),('score_dem_avg','score_demand'),('score_total_default','score_total')]
    checks={'jy_recomputed_vs_saved':oracle,'canonical_vs_jy':compare(ct,saved,mapped),
      'canonical_vs_latest_seunghee':compare(ct,sh,[('score_total_default','score_total_default')]),
      'canonical_vs_old_park':compare(ct,ps,[('score_total_default','score_total_default')])}
    sht=pd.read_parquet(ROOT/'이승희/step5_recommend/data/상권업종_유형_2025.parquet')
    joined=ct.merge(sht[keys+['type_full']],on=keys,validate='one_to_one')
    checks['latest_seunghee_type_differences']=int(joined.candidate_type.fillna('?').ne(joined.type_full.fillna('?')).sum())
    assert checks['latest_seunghee_type_differences']==0
    assert checks['canonical_vs_jy']['score_total_default']['different']==0
    assert checks['canonical_vs_latest_seunghee']['score_total_default']['different']==0
    jytypes=pd.read_parquet(jy.INPUTS['types'])
    contrast=ct.merge(jytypes[['trdar_code','lv','ep']],on='trdar_code',validate='many_to_one')
    checks['jy_area_vs_industry_axes']={}
    for axis,old in [('LV','lv'),('EP','ep')]:
        both=contrast[axis].notna()&contrast[old].notna()
        checks['jy_area_vs_industry_axes'][axis]={'both_known':int(both.sum()),'different':int(contrast.loc[both,axis].ne(contrast.loc[both,old]).sum()),'unit':'상권×업종'}
    counts={'areas':1644,'all_cells':len(saved),'positive_cells':len(canonical),'scored_cells':len(ct),'industries':100,
      'scored_industries':ct.industry_code.nunique(),'full_types':int(ct.candidate_type.notna().sum()),'held_types':int(ct.candidate_type.isna().sum()),
      'sd_unmapped_areas':int(axes.SD_area.isna().sum()),'sd_area_denominator':len(axes)}
    audit={'version':VERSION,'source_commit':SOURCE,'counts':{k:int(v) for k,v in counts.items()},'checks':checks,
      'official_definition':'https://data.seoul.go.kr/dataList/OA-15576/S/1/datasetView.do',
      'team_decision':'https://innercircledata13.slack.com/archives/C0C00701HEE/p1795094826703179',
      'objective_limit':'정답 창업 성과·실제 고객 구성·심리검사 타당도 자료가 없어 최적 모델은 판별 불가. 목적 적합성·해석 가능성·재현성 기준으로 선택.',
      'input_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in set(jy.INPUTS.values())|set(legacy.FILES.values())}}
    # 보고서 틀·STEP 6 시각화는 김지영 최종 산출물에서 읽어 온다.
    inputs=jy.read_inputs();P,_,design=jy.build_payload(inputs)
    P['version']=VERSION;P['audit']=audit
    # 업종 내 점수 배열은 원 정밀도 유지. 다른 유형·평균 처리 규칙을 끼워 넣지 않는다.
    index={v:i for i,v in enumerate(P['areas']['code'])}
    P['unified']={}
    for code,part in ct.groupby('industry_code'):
        arr=[None]*1644
        for row in part.itertuples():
            arr[index[row.trdar_code]]={'type':''.join('?' if pd.isna(v) else v for v in [row.LV,row.EP,row.SD]),
              'lv':None if pd.isna(row.resident_share_proxy) else 100*(1-row.resident_share_proxy),
              'ep':None if pd.isna(row.ticket_pct) else row.ticket_pct,
              'note':row.hold_reason,'official':row.chg_name,'ticket':None if pd.isna(row.ticket) else row.ticket}
        P['unified'][code]=arr
    # 검사지 원문은 최신 승희 파일에서 가져와 이전 임의 수정본을 다시 쓰지 않는다.
    tree=ast.parse((ROOT/'이승희/step5_recommend/quiz.py').read_text(encoding='utf-8-sig'))
    qs=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='QUESTIONS' for t in n.targets))
    order=[1,6,11,2,7,12,3,8,13,4,9,14,5,10,15]
    P['step5']['axes']=[{'기준':a,'왼쪽':l,'오른쪽':r} for a,l,r in [('LV','L','V'),('EP','E','P'),('SD','S','D')]]
    P['step5']['questions']=[{'번호':n,'기준':a,'질문':q,'A':aa[0],'A 글자':aa[1],'B':bb[0],'B 글자':bb[1],'화면 순서':order.index(n)} for n,a,q,aa,bb in qs]
    P['step5']['types']=[{'유형':code,'이모지':'','이름':name,'상권 특징':'인구 구성·업종 내 건당 금액·공식 영업 기간을 연결한 대리 분류','창업 아이템 예시':'희망 업종을 직접 선택해 비교하세요.'} for code,name in legacy.TYPE_NAMES.items()]
    P['step5']['weights']=[{'기본 비중':'매출 30 · 경쟁 25 · 안정성 15 · 수요 30','원칙':'검사 결과는 후보 조건만 변경. 가중치 자동 변경 없음.'}]
    P['step5']['design']=[{'축':'L/V','통합 규칙':'상주/(상주+직장) >55% L, <45% V, 경계 보류','한계':'실제 고객 구성 아님'},
      {'축':'E/P','통합 규칙':'같은 업종 건당 금액 백분위 <45 E, >55 P, 경계 보류','한계':'상권 전체 가격·실제 메뉴 가격 아님'},
      {'축':'S/D','통합 규칙':'공식 2025Q4 HH→S, LL→D, LH/HL 대응 보류','한계':'성장·저위험 의미 아님'},
      {'축':'검사','통합 규칙':'4:1 이상만 필터, 3:2·미완료 축 미적용','한계':'금융·심리 성향 검증 안 됨'}]
    P['kpi']['type2Areas']=counts['full_types']
    # 이전 상권 단위 유형·S/G 가정이 사전계산 표나 문서 데이터로 노출되지 않게 정비한다.
    P['areas']['type2']=[None]*1644;P['areas']['lv']=[None]*1644;P['areas']['ep']=[None]*1644
    P['areas']['lvs']=[None]*1644;P['areas']['eps']=[None]*1644
    P['areas']['lvNote']=['통합 L/V 대리 지표']*1644;P['areas']['epNote']=['희망 업종 내 건당 금액']*1644
    P['kpi']['type2Counts']={};P['kpi']['lvCounts']={};P['kpi']['epCounts']={}
    P['docs']['features']=[row for row in P['docs']['features'] if row[0] not in {'lv_score','ep_score','type2'}]
    P['docs']['features'] += [
      ['lv_share','상권','상주/(상주+직장); >0.55 L, <0.45 V','비율(0~1)','K06; K07','L/V 대리 구분','실제 고객 구성이 아니며 가운데·자료 부족은 보류','산출 (STEP 5)'],
      ['ticket_pct','상권×희망업종×연도','연간 매출/거래건수의 업종 내 백분위; <45 E, >55 P','백분위(0~100)','K01','희망 업종 가격 상대 수준','4분기 관측·반복 매출 제외·유효 비교 30곳; 가운데 보류','산출 (STEP 5)'],
      ['official_SD','상권×2025Q4','공식 HH→S, LL→D; LH/HL 명칭 보존·대응 보류','분류','K08','영업 기간 환경 선호','팀 해석이며 성장률·성공·저위험 의미 아님','산출 (STEP 5)']]
    P['step6']['design'][-1].update({'시각화':'운영 선호 8유형별 후보와 상위 상권 비교','구현 방법':'동일 기본 비중으로 L/V·업종 E/P·공식 S/D가 일치하는 후보만 비교','기대 인사이트':'유형별 후보 수와 점수 구성의 차이','확인한 결과':f"세 축 완전 판정 {counts['full_types']:,}개 조합. S/G 가중치 비교를 재사용하지 않고 재계산."})
    for ds in P['docs']['datasets']:
        if ds['id']=='K04': ds['role']='유동인구 → 경쟁 분모·수요 점수 (통합 L/V에는 직접 쓰지 않음)'
    P['docs']['datasets'].append({'id':'K08','name':'상권변화지표-상권 (팀 마트에서 필수 6열 추출)','provider':'서울시 → 이승희 팀 마트','format':'CSV','rows':6600,'cols':6,'period':'2025Q1~Q4','vintage':'판정은 2025Q4','role':'공식 영업 기간 특성 → S/D 연결. 원본 다운로드 파일의 열 수가 아닌 사용한 추출표 기준','url':audit['official_definition']})
    official=pd.read_csv(legacy.FILES['mart'],usecols=['상권_코드','기준_년분기_코드','상권_변화_지표','상권_변화_지표_명','운영_영업_개월_평균','폐업_영업_개월_평균'])
    standard={'기준_년분기_코드':('연분기','2025Q1~Q4','quarter'),'상권_코드':('상권 식별자','코드','trdar_code'),'상권_변화_지표':('공식 영업 기간 H/L 코드','분류','chg_code'),'상권_변화_지표_명':('정체·다이나믹·상권확장·상권축소','분류','chg_name'),'운영_영업_개월_평균':('운영 사업체 평균 영업 기간','개월','run_months'),'폐업_영업_개월_평균':('폐업 사업체 평균 영업 기간','개월','closed_months')}
    for j,col in enumerate(official.columns,1):
        meaning,unit,std=standard.get(col,('공식 마트의 보조 열','원자료 참조',''))
        v=official[col]
        P['docs']['columns'].append(['K08',j,col,meaning,unit,float(v.isna().mean()*100),int(v.nunique()),str(v.dropna().iloc[0]) if v.notna().any() else '',std])
    # 픽셀 지오메트리는 승희 자산, 투영·차트는 지영 SVG 도구를 함께 사용한다.
    proj=jy.Projection(inputs['geometry'])
    geo=json.loads((ROOT/'이승희/design_samples/seoul_gu_pixel.geojson').read_text(encoding='utf-8'))
    labels={r[2]:r[:2] for r in P['map']['labels']}
    P['guPixel']=[{'name':f['properties'].get('name','한강'),'kind':f['properties']['kind'],'path':jy.svg_path(f['geometry'],proj),'label':labels.get(f['properties'].get('name'))} for f in geo['features']]
    P['sourceCredits']=['김지영: 공통 데이터·전처리·변수사전·10개 보고서 화면·STEP 6 시각화','이승희: 공식 지표·최신 검사지·픽셀 지도 자산·지도 표시 규칙','박성은: 입력 재계산·차이 검증·공통 계산 연결·배포']
    for dir in ['data','report','dist']: (HERE/dir).mkdir(exist_ok=True)
    canonical.to_parquet(HERE/'data/통합_분석.parquet',index=False)
    ct.groupby('candidate_type',dropna=False).size().rename('조합 수').to_csv(HERE/'data/유형분포.csv',encoding='utf-8-sig')
    dump(HERE/'data/audit.json',audit)
    dump(HERE/'data/payload.json',P)
    for ax,old in [('LV','lv'),('EP','ep')]:
        both=contrast[ax].notna()&contrast[old].notna()
        contrast.loc[both&contrast[ax].ne(contrast[old]),['trdar_code','trdar_name','industry_code','industry_name',ax,old]].to_csv(HERE/f'data/{ax}_정의차이.csv',index=False,encoding='utf-8-sig')
    template=(HERE/'web/template.html').read_text(encoding='utf-8')
    for marker,file in [('/*__STYLE__*/','style.css'),('/*__CORE__*/','core.js'),('/*__APP__*/','app.js')]:
        assert template.count(marker)==1;template=template.replace(marker,(HERE/'web'/file).read_text(encoding='utf-8'))
    assert template.count('__PAYLOAD__')==1
    html=template.replace('__PAYLOAD__',json.dumps(P,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/'))
    (HERE/'dist/index.html').write_text(html,encoding='utf-8')
    (HERE/'report/SpotFit_팀통합_최종대시보드.html').write_text(html,encoding='utf-8')
    fixtures={}
    for code,g in ct.groupby('industry_code'):
        fixtures[code]={'all':dict(zip(g.trdar_code,g.score_total_default)), 'types':{t:g.loc[g.candidate_type.eq(t).fillna(False)].sort_values(['score_total_default','stores','trdar_code'],ascending=[False,False,True]).trdar_code.head(5).tolist() for t in legacy.TYPE_NAMES}}
    dump(HERE/'data/oracle.json',fixtures)
    for directory in ['dist','report']:
        (HERE/directory/'review.md').write_text((HERE/'REVIEW.md').read_text(encoding='utf-8'),encoding='utf-8')
        dump(HERE/directory/'audit.json',audit)
    print(json.dumps({'counts':counts,'checks':checks,'html_bytes':len(html.encode())},ensure_ascii=False))

if __name__=='__main__':
    if '--assemble-only' in sys.argv:
        P=json.loads((HERE/'data/payload.json').read_text(encoding='utf-8'))
        html=(HERE/'web/template.html').read_text(encoding='utf-8')
        for marker,file in [('/*__STYLE__*/','style.css'),('/*__CORE__*/','core.js'),('/*__APP__*/','app.js')]: html=html.replace(marker,(HERE/'web'/file).read_text(encoding='utf-8'))
        html=html.replace('__PAYLOAD__',json.dumps(P,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/'))
        for p in [HERE/'dist/index.html',HERE/'report/SpotFit_팀통합_최종대시보드.html']:p.write_text(html,encoding='utf-8')
        print('기존 검증 데이터로 화면 재조립 완료')
    else:main()
