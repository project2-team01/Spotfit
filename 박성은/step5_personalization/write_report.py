"""실제 STEP5 산출물로 진단 표·한국어 보고서·독립 HTML 요약을 만든다."""
from __future__ import annotations

import html
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import analyze_step5 as a


def csv(name):
    return pd.read_csv(a.OUT / name, encoding="utf-8-sig")


def table(frame):
    columns = [str(c) for c in frame.columns]
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for values in frame.itertuples(index=False, name=None):
        rows.append("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") if pd.notna(v) else "자료 없음" for v in values) + " |")
    return "\n".join(rows)


def chart_style(fig, height=380):
    fig.update_layout(template="plotly_white", height=height, font=dict(family="Malgun Gothic, Noto Sans KR, sans-serif", size=12),
                      colorway=["#2878b5", "#dd9363", "#77996b"], margin=dict(l=90, r=35, t=50, b=70),
                      paper_bgcolor="white", plot_bgcolor="white")
    return fig


def diagnostics(d):
    # 분류 단위(상권×업종)와 상권 고유 수는 구별한다.
    scope = d.loc[d.candidate_type.notna()]
    types = scope.groupby("candidate_type").agg(조합_수=("trdar_code", "size"), 상권_고유수=("trdar_code", "nunique"), 업종_수=("industry_code", "nunique")).reset_index()
    a.save_csv(types, a.OUT / "유형별_분석범위.csv")
    by_type = pd.crosstab([d.industry_code, d.industry_name], d.candidate_type).reset_index()
    a.save_csv(by_type, a.OUT / "업종별_유형구성.csv")
    target = d.loc[d.score_status.eq("점수 대상")]
    pairs = [("resident_share_proxy", "score_dem_resident"), ("ticket_pct", "score_sales"), ("dynamism_index", "score_stab")]
    correlations = []
    for x, y in pairs:
        valid = target[[x,y]].dropna()
        correlations.append({"범위": "전체 점수대상 (업종 행 반복 포함)", "업종_코드": "전체", "업종명": "전체", "지표1": x, "지표2": y,
                             "유효_행수": len(valid), "Spearman": valid.corr("spearman").iloc[0,1]})
        for code, part in target.groupby("industry_code"):
            valid = part[[x,y]].dropna()
            correlations.append({"범위": "업종별", "업종_코드": code, "업종명": part.industry_name.iloc[0], "지표1": x, "지표2": y,
                                 "유효_행수": len(valid), "Spearman": valid.corr("spearman").iloc[0,1] if len(valid)>1 else np.nan})
    corr = pd.DataFrame(correlations)
    a.save_csv(corr, a.OUT / "분류지표_STEP4_중복검토.csv")
    f = pd.read_csv(a.INPUTS["fact"], dtype=a.IDS, usecols=[*a.IDS,"store_count","sales_amount","sales_observed"])
    f["monthly"] = (f.sales_amount/f.store_count.where(f.store_count>0)/3).where(f.sales_observed)
    q = f.pivot(index=a.KEYS, columns="quarter", values="monthly")
    q["sales_h2_h1_change_pct"] = (q[["20253","20254"]].mean(axis=1,skipna=False)/q[["20251","20252"]].mean(axis=1,skipna=False).where(lambda s:s>0)-1)*100
    change = q[["sales_h2_h1_change_pct"]].reset_index()
    c = pd.read_csv(a.INPUTS["context"], dtype=a.IDS, usecols=["quarter","trdar_code","floating_population"])
    qc = c.pivot(index="trdar_code",columns="quarter",values="floating_population")
    qc["floating_h2_h1_change_pct"] = (qc[["20253","20254"]].mean(axis=1,skipna=False)/qc[["20251","20252"]].mean(axis=1,skipna=False).where(lambda s:s>0)-1)*100
    dynamic = d.loc[d.SD.eq("D").fillna(False), [*a.KEYS,"industry_name","trdar_name","candidate_type","sales_month_cv","floating_cv","dynamism_index"]].merge(change,on=a.KEYS,validate="one_to_one").merge(qc[["floating_h2_h1_change_pct"]].reset_index(),on="trdar_code",validate="many_to_one")
    a.save_csv(dynamic,a.OUT / "역동형_연내변화_진단.csv")
    # 자료 보유 범위가 다른 업종의 건당 금액 수준은 별도로 참고한다.
    tickets = d.loc[d.ep_valid_before_peers & d.ep_peers.ge(30)].groupby(["industry_code","industry_name"]).ticket.agg(유효_조합수="size",건당금액_중앙값="median",건당금액_최소="min",건당금액_최대="max").reset_index()
    a.save_csv(tickets,a.OUT / "업종별_건당금액_참고수준.csv")
    preview = pd.concat([d.loc[d.candidate_type.eq(item["code"]).fillna(False)].head(3) for item in a.load_type_config()["types"]]+[target.loc[target.candidate_type.isna()].head(8)])
    cols=[*a.KEYS,"industry_name","trdar_name","LV","EP","SD","candidate_type","type_status","resident_share_proxy","ticket","ticket_pct","dynamism_index","hold_reason"]
    a.save_csv(preview[cols],a.OUT / "유형후보_미리보기.csv")
    return types,corr,dynamic


def main():
    d=pd.read_parquet(a.OUT / "상권업종_유형후보_2025.parquet")
    meta=json.loads((a.OUT / "analysis_meta.json").read_text(encoding="utf-8"))
    validation=json.loads((a.REPORT / "validation.json").read_text(encoding="utf-8"))
    assert all(r["passed"] for r in validation)
    assert meta["input_sha256"]==a.input_hashes(),"보고서 작성 전 입력 변경"
    types,corr,dynamic=diagnostics(d)
    config=csv("8유형_정의와_결과.csv")
    sensitivity=csv("임계값_민감도.csv")
    hold=csv("축별_보류사유.csv")
    ind=csv("업종별_분류가능여부.csv")
    area=csv("상권별_LV_대리지표.csv")
    coffee=csv("커피음료_유형별_탐색예시.csv")
    c=meta["classification"]
    dynamic_count=len(dynamic)
    dynamic_decline=int(dynamic.sales_h2_h1_change_pct.lt(0).sum())
    both_decline=int((dynamic.sales_h2_h1_change_pct.lt(0)&dynamic.floating_h2_h1_change_pct.lt(0)).sum())
    summary={"date":"2026-11-12","target_cells":c["target_cells"],"full_candidates":c["full_type_candidates"],"held":c["target_held"],
             "D_axis_rows":dynamic_count,"D_sales_h2_lower_than_h1":dynamic_decline,"D_both_sales_and_floating_lower":both_decline,
             "validation_passed":sum(r["passed"] for r in validation),"validation_total":len(validation),"types":dict(zip(config.code,config["후보_조합_수"]))}
    (a.REPORT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    parts=["# STEP 5 · 8유형 적합성 분석 및 개인화 탐색 설계", "", "작성: 2026-11-12 · 박성은 작업용 분석 · 데이터: 2025년만", "",
           "## 먼저 볼 결론", "",
           f"STEP 4 점수 대상 {c['target_cells']:,}개 상권×업종 중 **{c['full_type_candidates']:,}개({c['full_type_candidates']/c['target_cells']*100:.1f}%)**에 세 축이 모두 있는 분석용 대리분류 후보가 생겼습니다. **{c['target_held']:,}개는 보류**했습니다. 분류 가능한 업종은 {c['supported_industries_with_candidates']}개입니다. 전체 입력 76,591개 조합과 모든 보류 사유도 그대로 공유합니다.", "",
           "이 결과는 실제 고객 성향·브랜드 프리미엄·사용자의 금융 성향을 측정한 확정 유형이 아닙니다. 운영 가정으로 만든 후보를 검토하는 단계입니다. 사용자 설문과 창업 성과 정답 자료가 없어 개인화 추천의 정확도·만족도·성공률은 평가하지 못했습니다.", "",
           "## STEP 5에서 구분해야 할 두 개념", "",
           "기존 ANALYSIS_PLAN의 STEP 5는 사용자의 금융 MBTI·위험 감수 성향·예산·희망 업종을 받아 개인화하는 설계였습니다. 이번에 받은 8유형은 상권 자체의 성격을 설명합니다. 상권 유형을 사용자의 금융 MBTI로 간주하지 않았습니다.", "",
           "이번 구현은 ① 상권 유형 후보 산출과 ② 사용자가 선호 유형·희망 업종을 선택한 경우의 탐색 실험입니다. 실제 사용자 응답이 없으므로 금융 성향이나 위험 감수 성향을 추론하지 않습니다. 비용 데이터가 없어 예산 적합성도 판단하지 않습니다.", "",
           "## 코드 정리와 의미 변경", "",
           "받은 첫 표는 S/D이고 8유형 표에는 G가 남아 있어 LEG→LED, LPG→LPD, VEG→VED, VPG→VPD로 통일했습니다. 원래 코드·이름·아이템 예시는 types.json과 결과 CSV에 보존했습니다. 역동형 이름은 분석용 제안이며 팀 최종 합의가 아닙니다.", "",
           "D는 '최근 소비·방문이 증가하는 성장형'이라는 원래 설명을 그대로 측정할 수 없어 **2025년 내 변동성이 상대적으로 큰 유형**으로 재정의했습니다. 이 변경에 대한 팀 합의가 필요합니다. D가 매출·유동 증가나 유망 상권을 뜻하지 않습니다.", "",
           "## 실제 지표와 판정 규칙", "",
           "| 축 | 자료에서 계산한 값 | 기본 판정 [가정] | 확정할 수 없는 의미 |", "|---|---|---|---|",
           "| L/V | 주민/(주민+직장인) | 0.55 초과 L, 0.45 미만 V, 중간 보류 | 실제 거주 고객·외부 방문객·관광객 비중 |",
           "| E/P | 연간 추정매출/추정매출 건수의 업종 내 백분위 | 45 미만 E, 55 초과 P, 중간 보류 | 가격 민감성·구매력·실속·브랜드 프리미엄 |",
           "| S/D | 분기 점포당 월매출 CV와 분기 유동인구 CV의 업종 내 백분위 평균 | 45 미만 S, 55 초과 D, 중간 보류 | 장기 안정성·성장성·폐업 확률 |", "",
           "CV는 표준편차를 평균으로 나눈 상대 변동성입니다. 네 분기 모표준편차(ddof=0)를 썼으며 평균이 0이거나 분기가 부족하면 보류합니다. 매출·유동 두 값 중 하나만 있는 경우 나머지를 0으로 채우거나 단독으로 S/D를 매기지 않습니다.", "",
           "L/V 지표의 주민과 직장인은 서로 겹칠 수 있는 인구 집계입니다. 따라서 분모를 서로 다른 실제 고객 수의 합으로 해석하면 안 됩니다. 2025년 자료의 두 값은 반복되며 공통 메타데이터의 마지막 값 변경은 직장인구 2024Q4·상주인구 2023Q4입니다. 마지막 값 변경과 실제 통계 기준 시점은 다르며 실제 기준 시점은 미확인입니다.", "",
           "세 축은 2025년·관광특구 제외·평균 점포 5개 이상·업종 비교 30곳 이상이라는 공통 기준을 유지합니다. E/P와 S/D의 유효 비교 집단도 각각 30곳 이상이어야 합니다. 네 분기 매출이 완전히 같은 146개 점수 대상 조합은 실제 반복인지 확인하지 못해 E/P·S/D를 보류했습니다. 오류라고 확정한 것은 아닙니다.", "",
           "## 분석 단위와 결과", "",
           "E/P·S/D는 같은 업종 안에서 비교하므로 결과 단위는 **상권×업종**입니다. 한 상권에 보편적인 코드 하나를 붙이지 않았습니다. 예를 들어 같은 지역도 커피와 한식에서 E/P 위치가 다를 수 있습니다. L/V만 상권 수준에서 별도로 계산했습니다.", "",
           f"관광특구 제외 상권 {len(area):,}곳의 L/V 대리지표는 L {int(area.LV.eq('L').sum()):,}곳, V {int(area.LV.eq('V').sum()):,}곳, 보류 {int(area.LV.isna().sum()):,}곳입니다. 이 V를 실제 외부 방문형 상권 수로 읽으면 안 됩니다.", "",
           table(config[["code","legacy_code","name","original_name","후보_조합_수"]]), "",
           "위 숫자는 상권 수가 아니라 상권×업종 조합 수입니다. 유형별 고유 상권 범위는 유형별_분석범위.csv에 별도로 저장했습니다. 동일 상권이 업종에 따라 다른 유형에 들어갈 수 있어 고유 상권 수를 유형끼리 더하면 중복됩니다.", "",
           "## 보류는 중요한 분석 결과", "",
           table(hold), "",
           "보류 사유는 축별 집계여서 같은 행이 여러 축에 포함됩니다. 위 표를 더해 전체 보류 조합 수로 쓰면 안 됩니다. 매출 미제공 38개 업종의 14,716개 전체 조합은 E/P·S/D·완전 유형을 부여하지 않았습니다. 점포 5개 미만 55,824개 조합도 유형을 부여하지 않았습니다.", "",
           "## 역동성과 성장은 다르다", "",
           f"S/D에서 D인 {dynamic_count:,}개 조합 중 {dynamic_decline:,}개({dynamic_decline/dynamic_count*100 if dynamic_count else 0:.1f}%)는 **2025년 하반기 점포당 월매출 평균이 상반기보다 낮았습니다**. 매출과 유동인구가 둘 다 낮은 경우도 {both_decline:,}개입니다. 역동성이 곧 증가·성장이 아님을 실제 데이터에서도 확인했습니다.", "",
           "이 반기 비교는 방향을 설명하는 참고 진단이며 분류나 점수에는 넣지 않았습니다. 전년 대비 성장이나 장기 추세로 해석하지 않습니다. 세부값은 역동형_연내변화_진단.csv에 있습니다.", "",
           "## 기준을 바꾸면 어떻게 달라지나", "",
           table(sensitivity[["설정","유형후보_수","점수대상중_보류","기본과_동시판정","동시판정중_유형변경","판정가능여부_변경"]]), "",
           "동시판정 중 유형변경은 두 설정에서 모두 완전 유형이 있는 행만 비교한 수입니다. 판정가능여부 변경은 보류↔분류의 전환을 센 수입니다. 경계를 넓히면 보류가 늘고 후보가 줄어듭니다. 어느 설정이 실제 성향을 더 정확히 나타내는지는 정답 자료가 없어 판단하지 못했습니다.", "",
           "## 유형 기반 개인화 탐색 실험", "",
           "사용자가 희망 업종과 선호 유형을 선택한 상황만 가정합니다. 기본은 정확히 세 축이 일치한 후보만 출력합니다. 결과가 없으면 없다고 보고하며, 부족한 유형을 다른 유형으로 자동 보충하지 않습니다. 미판정 축을 가진 부분 후보는 --allow-partial을 사용한 경우에만 별도 표시합니다.", "",
           "L 선호에서는 수요의 주민 중심 점수, V 선호에서는 유동 중심 점수를 쓰는 연결 가정을 실험했습니다. 매출30·경쟁25·안정성15·수요30은 공통으로 유지했습니다. 8유형에 서로 다른 숫자 가중치를 임의로 만들지 않았습니다. 유형 필터 이후 동일 지표에 추가 보너스를 주지 않았습니다.", "",
           "S/D의 연내 변동성과 STEP 4 안정성의 보정 폐업률은 서로 다른 지표입니다. 필터와 점수에 관련 정보가 함께 반영될 가능성은 남아 있습니다. 분류 지표와 STEP 4 지표의 전체·업종별 Spearman 상관을 분류지표_STEP4_중복검토.csv에 저장했습니다. 전체 상관은 업종 행 반복과 집계 효과를 포함하므로 독립성이나 인과관계를 입증하지 않습니다.", "",
           table(corr.loc[corr["업종_코드"].eq("전체"), ["지표1","지표2","유효_행수","Spearman"]].round({"Spearman":3})), "",
           "커피-음료 업종의 유형별 상위 비교 후보 예시는 CSV로 공유했습니다. 이는 창업 추천 아이템이나 성과의 검증이 아니며, 사용자가 적은 아이템 예시를 서울 업종 코드에 자동 대응하지 않았습니다.", "",
           table(csv("커피음료_수요연결_민감도.csv")), "",
           "## 검증 결과", "",
           f"**{sum(r['passed'] for r in validation)}/{len(validation)}개 검사 통과.** 입력·다른 팀원 폴더 보존, 2회 실행 SHA-256 동일, 원본부터 손계산, 결측·경계·동점, 유형·업종 필터, 빈 결과·부분 일치, 다섯 가지 변조 탐지를 확인했습니다.", "",
           table(pd.DataFrame(validation).assign(passed=lambda x:x.passed.map({True:"통과",False:"실패"})).rename(columns={"name":"검사","passed":"결과","evidence":"근거"})), "",
           "## 팀이 결정할 것과 추가로 필요한 자료", "",
           "1. 상권 유형과 사용자의 금융·위험 선호를 별도 체계로 유지할지 확정해야 합니다.",
           "2. 실제 고객의 거주·직장·방문 출처가 필요합니다. 주민/직장인 숫자만으로 L/V를 확정할 수 없습니다.",
           "3. 가격대·객수·장바구니·브랜드·구매 목적 자료 없이 E/P를 실속/프리미엄으로 확정할 수 없습니다. 현재는 결제 건당 금액의 상대 위치입니다.",
           "4. D를 이번 연내 변동성으로 사용할지 합의해야 합니다. 증가·성장 의미를 유지하려면 더 긴 기간과 계절성 검토가 필요합니다.",
           "5. 임대료·보증금·권리금·시설비가 없으므로 예산 적합성을 확정할 수 없습니다.",
           "6. 유형 경계·경계구간 폭·두 변동성의 동등 비중은 검증되지 않은 가정입니다. 사용자 조사와 실제 성과를 이용한 별도 평가가 필요합니다.", "",
           "## 재현과 출처", "",
           "데이터 출처: 서울시 상권분석서비스. 공통 전처리·파생변수: 김지영 step2_3·claude_dashboard. STEP 4 기반: 이승희 및 박성은 step4_dashboard. 이번 STEP 5 대리분류·검증·진단: 박성은 작업용 분석. 참조 저장소 스냅숏: fc093dee4c8dd041612fa93071a95dd131139a8b. 정확한 입력 파일 SHA-256은 data/analysis_meta.json에 있습니다.", "",
           "실행 방법과 파일 목록은 [README](../README.md), 상세 판정식은 [DESIGN](../DESIGN.md)을 참고하세요. 기존 STEP 4 대시보드와 공유 웹사이트는 이번 분석으로 변경하지 않았습니다."]
    (a.REPORT/"STEP5_분석보고서.md").write_text("\n".join(parts)+"\n",encoding="utf-8")
    # 팀원이 설치 없이 열어 볼 수 있는 자기완결적 HTML 요약.
    fig1=chart_style(go.Figure(go.Bar(x=config.code,y=config["후보_조합_수"],text=config["후보_조합_수"],textposition="outside",marker_color="#2878b5")))
    fig1.update_layout(title="8유형 후보 수 · 상권×업종 조합",xaxis_title="분석용 대리분류 코드",yaxis_title="조합 수")
    fig2=chart_style(go.Figure([go.Bar(y=sensitivity["설정"],x=sensitivity["유형후보_수"],name="유형 후보",orientation="h"),go.Bar(y=sensitivity["설정"],x=sensitivity["점수대상중_보류"],name="보류",orientation="h")]),height=460)
    fig2.update_layout(title="경계 설정에 따른 분류 가능 범위",barmode="stack",margin=dict(l=175,r=35,t=50,b=50),xaxis_title="STEP 4 점수 대상 조합 수",legend=dict(orientation="h",y=1.15))
    fig3=chart_style(go.Figure(go.Histogram(x=dynamic.sales_h2_h1_change_pct.clip(-100,200),nbinsx=45,marker_color="#77996b")))
    fig3.add_vline(x=0,line_dash="dash",line_color="#dd9363")
    fig3.update_layout(title="D(역동형)도 상반기보다 매출이 줄 수 있음",xaxis_title="하반기/상반기 점포당 월매출 변화(%) · 200% 초과는 끝에 모음",yaxis_title="조합 수")
    figures=[fig1,fig2,fig3]
    chart_html="\n".join(fig.to_html(full_html=False,include_plotlyjs=(i==0),config={"responsive":True,"displaylogo":False}) for i,fig in enumerate(figures))
    body=f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>STEP 5 유형 분석 · 박성은</title><style>body{{font-family:Malgun Gothic,system-ui,sans-serif;background:#f3f6f1;color:#173c36;line-height:1.9;margin:0}}main{{max-width:1160px;margin:auto;padding:36px 24px}}h1{{font-size:30px;line-height:1.5}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}}.card,section{{background:white;border:1px solid #dce4d7;padding:24px;margin-bottom:20px}}.card strong{{font-size:32px;display:block}}.note{{background:#fff2d9;padding:18px;border-left:4px solid #dd9363}}table{{border-collapse:collapse;font-size:12px;min-width:500px}}th,td{{border-bottom:1px solid #dce4d7;padding:9px;text-align:left;vertical-align:top}}.scroll{{overflow:auto}}a{{color:#2878b5}}@media(max-width:650px){{.cards{{grid-template-columns:1fr}}}}</style></head><body><main><p>SpotFit / STEP 5 / 2026-11-12</p><h1>8유형을 실제 데이터로<br>어디까지 구분할 수 있을까?</h1><p>박성은 작업용 분석 · 2025년 서울 상권 자료</p><div class="cards"><div class="card">STEP 4 점수 대상<strong>{c['target_cells']:,}</strong>상권×업종 조합</div><div class="card">세 축이 있는 후보<strong>{c['full_type_candidates']:,}</strong>확정 유형이 아닌 대리분류</div><div class="card">보류<strong>{c['target_held']:,}</strong>자료 부족·경계 구간 보존</div></div><p class="note">사용자 금융 MBTI와 상권 유형을 구분합니다. L/V는 주민·직장 구성, E/P는 결제 건당 금액, S/D는 연내 관측 변동성의 대리분류입니다. D는 성장성이 아니며 추천 성능·창업 성공 가능성을 검증한 결과가 아닙니다.</p><section><h2>정의와 분류 결과</h2><div class="scroll">{config[['code','legacy_code','name','original_name','후보_조합_수']].to_html(index=False,border=0)}</div><p>G를 D로 통일했습니다. 명칭 변경과 경계값은 분석용 제안이며 팀 합의가 필요합니다.</p></section><section>{chart_html}</section><section><h2>역동성과 성장의 차이</h2><p>D 축으로 분류된 {dynamic_count:,}개 중 {dynamic_decline:,}개는 하반기 점포당 월매출이 상반기보다 낮았습니다. 매출·유동이 모두 낮은 경우도 {both_decline:,}개입니다. 계절성·측정오차가 섞인 연내 변화이며 장기 성장으로 읽으면 안 됩니다.</p></section><section><h2>검증 결과</h2><p>{len(validation)}개 검사 모두 통과. 두 번 실행한 10개 핵심 산출물의 바이트 동일, 원본 손계산 재현, 관광특구·소표본·결측 보존, 다섯 가지 변조 탐지 확인.</p><div class="scroll">{pd.DataFrame(validation).assign(passed=lambda x:x.passed.map({True:'통과',False:'실패'})).to_html(index=False,border=0)}</div></section><section><h2>전체 자료</h2><p>전체 결과는 data/의 Parquet와 CSV.gz에 있습니다. 보류 행도 포함합니다. 정확한 판정식은 DESIGN.md, 자세한 해석은 STEP5_분석보고서.md를 확인하세요.</p><p>기존 STEP 4 대시보드와 공유 사이트는 이번 분석으로 변경하지 않았습니다.</p></section><p>출처: 서울시 상권분석서비스 · 공통 가공: 김지영 · STEP 4 기반: 이승희·박성은 · STEP 5 실험: 박성은 작업용 구현</p></main></body></html>"""
    (a.REPORT/"STEP5_결과요약.html").write_text(body,encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=="__main__":
    main()
