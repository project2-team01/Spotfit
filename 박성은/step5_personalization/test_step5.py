"""STEP5 데이터 규칙·원값 재현·보류·변조·탐색·재실행을 검증한다."""
import hashlib
import json
import math
import subprocess
import sys

import numpy as np
import pandas as pd

import analyze_step5 as a

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS = []


def record(name, ok, evidence):
    RESULTS.append({"name": name, "passed": bool(ok), "evidence": evidence})
    print(f"[{'통과' if ok else '실패'}] {name}: {evidence}", flush=True)


def validate(d, tourist):
    allowed = {r["code"] for r in a.load_type_config()["types"]}
    full = d.candidate_type.notna()
    errors = []
    if d.trdar_code.isin(tourist).any(): errors.append("관광특구")
    if d.loc[full, "stores"].lt(5).any(): errors.append("소표본")
    if d.loc[full, "score_status"].ne("점수 대상").any(): errors.append("점수 제외 대상")
    if not set(d.loc[full, "candidate_type"]).issubset(allowed): errors.append("코드")
    if d.loc[full, ["LV", "EP", "SD"]].isna().any().any(): errors.append("불완전 유형")
    if not d.loc[full, "candidate_type"].eq(d.loc[full, "LV"] + d.loc[full, "EP"] + d.loc[full, "SD"]).all(): errors.append("축·코드 불일치")
    if d.loc[d.EP.notna(), "ticket"].le(0).any() or d.loc[d.EP.notna(), "ticket"].isna().any(): errors.append("매출 결측 채움")
    if d.loc[d.EP.notna(), "sales_quarters"].ne(4).any(): errors.append("매출 분기 부족")
    if d.loc[d.EP.notna(), "ep_peers"].lt(30).any(): errors.append("E/P 비교 부족")
    if d.loc[d.SD.notna(), "sd_peers"].lt(30).any(): errors.append("S/D 비교 부족")
    if d.loc[d.SD.notna(), ["sales_month_cv", "floating_cv"]].isna().any().any(): errors.append("변동성 자료 부족")
    if d.loc[d.repeated_sales, ["EP", "SD"]].notna().any().any(): errors.append("반복 매출 분류")
    ep_bad = (d.EP.eq("E") & ~d.ticket_pct.lt(45)) | (d.EP.eq("P") & ~d.ticket_pct.gt(55))
    sd_bad = (d.SD.eq("S") & ~d.dynamism_index.lt(45)) | (d.SD.eq("D") & ~d.dynamism_index.gt(55))
    lv_bad = (d.LV.eq("L") & ~d.resident_share_proxy.gt(.55)) | (d.LV.eq("V") & ~d.resident_share_proxy.lt(.45))
    if ep_bad.fillna(False).any() or sd_bad.fillna(False).any() or lv_bad.fillna(False).any(): errors.append("분류 방향")
    return errors


def manual_cv(values):
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) / mean


def manual_rank(series, value):
    values = series.dropna().tolist()
    less = sum(x < value for x in values)
    ties = sum(x == value for x in values)
    return (less + (ties + 1) / 2) / len(values) * 100


def main():
    before = a.input_hashes()
    hashes = []
    for run in range(2):
        completed = subprocess.run([sys.executable, str(a.HERE / "analyze_step5.py")], capture_output=True, text=True, encoding="utf-8")
        assert completed.returncode == 0, completed.stdout + completed.stderr
        hashes.append({p.name: a.sha(p) for p in sorted(a.OUT.iterdir()) if p.is_file()})
        print(f"재현 실행 {run + 1}/2 완료", flush=True)
    d = pd.read_parquet(a.OUT / "상권업종_유형후보_2025.parquet")
    dim = pd.read_csv(a.INPUTS["dim"], dtype={"trdar_code": str})
    tourist = set(dim.loc[dim.is_tourist, "trdar_code"])
    errors = validate(d, tourist)
    record("분류 불변 규칙", not errors, "위반 " + str(errors) + f", 전체 {len(d):,}행")
    record("입력·작업 범위 보존", before == a.input_hashes(), f"입력 SHA-256 {len(before)}개 실행 전후 동일")
    relative = a.HERE.relative_to(a.REPO).as_posix()
    git = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all", "--", ".", f":(exclude){relative}"], cwd=a.REPO, capture_output=True, text=True, encoding="utf-8")
    record("작업 폴더 밖 변경 없음", git.returncode == 0 and not git.stdout.strip(), git.stdout.strip() or "작업 폴더 밖 변경 0건")
    record("두 번 실행 바이트 동일", hashes[0] == hashes[1], f"출력 {len(hashes[0])}개 SHA-256 비교")
    industries = pd.read_csv(a.INPUTS["industries"], dtype={"업종_코드": str})
    unsupported = set(industries.loc[~industries["매출_제공_업종"], "업종_코드"])
    u = d.loc[d.industry_code.isin(unsupported)]
    record("매출 미제공 업종 보류", len(unsupported) == 38 and u[["ticket", "EP", "SD", "candidate_type"]].isna().all().all(),
           f"38개 업종 {len(u):,}행: 결측 유지, E/P·S/D·완전 유형 없음")
    small = d.loc[d.stores.lt(5)]
    record("소표본 분류 보류", small[["LV", "EP", "SD", "candidate_type"]].isna().all().all(), f"평균 점포 5개 미만 {len(small):,}행 유형 미부여")
    missing = d.loc[d.candidate_type.isna() & d.score_status.eq("점수 대상")]
    record("축별 보류 사유 제공", missing.hold_reason.notna().all() and missing.hold_reason.str.len().gt(0).all(), f"점수 대상 중 유형 보류 {len(missing):,}행 사유 있음")
    bounds = pd.Series([.44, .45, .50, .55, .56, np.nan])
    lv = a.split_axis(bounds, .45, .55, "V", "L").fillna("?").tolist()
    ranks = pd.Series([44.,45.,50.,55.,56.,np.nan])
    ep = a.split_axis(ranks,45,55,"E","P").fillna("?").tolist()
    record("경계·결측 규칙", lv == ["V","?","?","?","L","?"] and ep == ["E","?","?","?","P","?"], f"LV {lv}; EP {ep}")
    ties = pd.DataFrame({"industry_code": ["x"]*30, "raw": [10.]*30})
    pct, _ = a.rank_signal(ties, "raw", pd.Series(True,index=ties.index))
    record("동점 처리", pct.nunique() == 1 and a.split_axis(pct,45,55,"E","P").isna().all(), f"동일 원값 30개 → 동일 백분위 {pct.iloc[0]:.6f}, 모두 경계 보류")
    sample_cv = a.cv(pd.Series([10.,20.,30.,40.]))
    record("변동계수 정의", abs(sample_cv-manual_cv([10.,20.,30.,40.]))<1e-12 and pd.isna(a.cv(pd.Series([0.,0.,0.,0.]))) and pd.isna(a.cv(pd.Series([1.,2.,3.,np.nan]))), "모표준편차/평균 손계산 일치, 평균 0·결측 보류")
    # 실제 커피 상권 두 곳: 입력 패널과 맥락 표부터 수동 재현.
    fact = pd.read_csv(a.INPUTS["fact"], dtype=a.IDS, usecols=[*a.IDS,"store_count","sales_amount","sales_count","sales_observed"])
    context = pd.read_csv(a.INPUTS["context"], dtype=a.IDS, usecols=["quarter","trdar_code","floating_population"])
    coffee = d.loc[d.industry_code.eq("CS100010") & d.candidate_type.notna()]
    chosen = coffee.sort_values("score_total_default").iloc[[len(coffee)//4,3*len(coffee)//4]]
    hand_ok, evidence = True, []
    peers = d.loc[d.industry_code.eq("CS100010") & d.sd_valid_before_peers & d.sd_peers.ge(30)]
    for _, r in chosen.iterrows():
        f = fact.loc[fact.industry_code.eq("CS100010") & fact.trdar_code.eq(r.trdar_code)]
        flow = context.loc[context.trdar_code.eq(r.trdar_code), "floating_population"].tolist()
        monthly = (f.sales_amount / f.store_count / 3).tolist()
        hs = manual_cv(monthly); hf = manual_cv(flow); ticket = f.sales_amount.sum()/f.sales_count.sum()
        ep_peers = d.loc[d.industry_code.eq("CS100010") & d.ep_valid_before_peers & d.ep_peers.ge(30)]
        ht = manual_rank(ep_peers.ticket, r.ticket)
        hd = (manual_rank(peers.sales_month_cv,r.sales_month_cv)+manual_rank(peers.floating_cv,r.floating_cv))/2
        hand_ok &= abs(hs-r.sales_month_cv)<1e-9 and abs(hf-r.floating_cv)<1e-9 and abs(ticket-r.ticket)<1e-5 and abs(ht-r.ticket_pct)<1e-9 and abs(hd-r.dynamism_index)<1e-9
        evidence.append(f"{r.trdar_name}: ticket {ticket:.3f}, 매출CV {hs:.6f}, 유동CV {hf:.6f}, EP백분위 {ht:.3f}, SD지수 {hd:.3f} → {r.candidate_type}")
    record("실제 원값·백분위 손계산", hand_ok, " / ".join(evidence))
    # 다른 목적의 가중치를 임의 생성하지 않았는지, 원래 STEP4 점수도 재현되는지.
    delta = (a.profile_score(d,"avg") - d.score_total_default).abs().max()
    record("STEP4 점수 재현", delta < 1e-9, f"최대 절대 오차 {delta:.3g}")
    selections = []
    for code in [r["code"] for r in a.load_type_config()["types"]]:
        result = a.explore(d,"CS100010",code)
        selections.append(result.empty or (result.industry_code.eq("CS100010").all() and result.candidate_type.eq(code).all() and result.known_axes.eq(3).all()))
        if len(result):
            frame = d.set_index(a.KEYS).loc[list(zip(result.trdar_code,result.industry_code))].copy()
            columns = ["score_sales","score_comp","score_stab", "score_dem_resident" if code.startswith("L") else "score_dem_floating"]
            hand = frame[columns].mul([30,25,15,30]).sum(axis=1) / frame[columns].notna().mul([30,25,15,30]).sum(axis=1)
            selections.append(np.allclose(hand.to_numpy(),result.exploration_score.to_numpy(),atol=1e-9))
    record("유형·업종 필터와 점수 연결", all(selections), "8개 유형의 커피 탐색: 정확 일치만, 부분 일치로 자동 대체하지 않음, 점수 손계산 일치")
    no_industry = industries.loc[~industries["점수_생성"],"업종_코드"].iloc[0]
    empty = a.explore(d,no_industry,"LES")
    unsup_code = industries.loc[~industries["매출_제공_업종"] & industries["점수_생성"],"업종_코드"].iloc[0]
    exact = a.explore(d,unsup_code,"LES")
    partial = a.explore(d,unsup_code,"LES",allow_partial=True)
    record("빈 결과·부분 일치 구분", empty.empty and exact.empty and (partial.empty or partial.match_status.eq("부분 일치: 미판정 축 있음").all()), f"비교 부족 업종 정확 {len(empty)}건, 매출 미제공 정확 {len(exact)}건, 명시적 부분 허용 {len(partial)}건")
    record("G→D와 잘못된 코드 처리", a.normalize_type("LEG")=="LED" and a.normalize_type("VPG")=="VPD", "기존 G 코드 변환, 출력은 S/D 코드만")
    rejected = []
    for kind in ["코드", "업종"]:
        try:
            a.explore(d,"BAD" if kind=="업종" else "CS100010","BAD" if kind=="코드" else "LES")
            rejected.append(False)
        except ValueError:
            rejected.append(True)
    record("유효하지 않은 입력 거부", all(rejected), "없는 업종과 유형 모두 ValueError")
    # 변조가 실제로 발견되는지 검사.
    mutations = []
    first = d.index[d.candidate_type.notna()][0]
    for name in ["관광특구","소표본","코드","매출0","방향"]:
        m=d.copy()
        if name=="관광특구": m.loc[first,"trdar_code"]=sorted(tourist)[0]
        if name=="소표본": m.loc[first,"stores"]=3
        if name=="코드": m.loc[first,"candidate_type"]="LEG"
        if name=="매출0": m.loc[first,"ticket"]=0
        if name=="방향": m.loc[first,"EP"]="P" if m.loc[first,"EP"]=="E" else "E"
        mutations.append((name,bool(validate(m,tourist))))
    record("변조 탐지", all(ok for _,ok in mutations), ", ".join(name+(' 발견' if ok else ' 놓침') for name,ok in mutations))
    a.REPORT.mkdir(exist_ok=True)
    (a.REPORT / "validation.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print(f"결과: {sum(r['passed'] for r in RESULTS)}/{len(RESULTS)} 통과",flush=True)
    sys.exit(0 if all(r["passed"] for r in RESULTS) else 1)


if __name__ == "__main__":
    main()
