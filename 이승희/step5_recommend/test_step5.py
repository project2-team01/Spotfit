# -*- coding: utf-8 -*-
"""
STEP 5 유형표·추천 검증. 팀 저장소 루트에서 실행:
    uv run --project "이승희/step5_recommend" python "이승희/step5_recommend/test_step5.py"
"""
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_types as bt  # noqa: E402
import recommend as r  # noqa: E402

REPO = bt.REPO
DIM = REPO / "김지영" / "step2_3" / "data" / "dim_trdar.csv.gz"
OUT_FILES = ["상권업종_유형_2025.parquet", "상권_유형축_2025.csv", "유형_정의.csv", "업종별_유형_가능여부.csv", "유형별_분포.csv", "stage5_meta.json"]
# 서울시 원본(OA-15576)에 있는 분기별 서울 평균 (운영 영업 개월, 폐업 영업 개월). 2단계 마트에는 이 두 열이 없다.
SEOUL_AVG = {20251: (111, 52), 20252: (112, 53), 20253: (113, 53), 20254: (115, 53)}
RESULTS = []


def record(no, name, ok, detail):
    RESULTS.append((no, name, ok, detail))
    print(f"[검사 {no:>2}] {'통과' if ok else '실패'} | {name} | {detail}", flush=True)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def outside_changes():
    """이 폴더 밖에서 Git이 보는 변경 목록 (실행 전후 비교용)."""
    out = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "-uall"], capture_output=True, text=True, encoding="utf-8").stdout
    return sorted(line for line in out.splitlines() if "이승희/step5_recommend/" not in line and "step5_recommend" not in line)


# ---------------------------------------------------------------- 규칙 검사 (변조 시험에서 재사용)

def check_tourist(c, a, dim):
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    n = int(c["trdar_code"].isin(tourist).sum() + a["trdar_code"].isin(tourist).sum())
    return n == 0 and a["trdar_code"].is_unique, f"관광특구 {n}건, 상권 {len(a):,}곳 (중복 {int(a['trdar_code'].duplicated().sum())})"


def check_sd(a, mart):
    q4 = mart.loc[mart["기준_년분기_코드"].eq(bt.SD_QUARTER)].set_index("상권_코드")
    x = a.set_index("trdar_code")
    same_name = int((x["chg_name"] != q4.loc[x.index, "상권_변화_지표_명"]).sum())
    same_code = int((x["chg_code"] != q4.loc[x.index, "상권_변화_지표"]).sum())
    expect = x["chg_name"].map({"정체": "S", "다이나믹": "D"})
    bad_map = int((x["SD"].fillna("-") != expect.fillna("-")).sum())
    pair = x.groupby(["chg_code", "chg_name"]).size().index.tolist()
    pair_ok = set(pair) <= {("HH", "정체"), ("LL", "다이나믹"), ("LH", "상권확장"), ("HL", "상권축소")}
    no_reason = int((x["SD"].isna() & x["SD_reason"].isna()).sum())
    ok = same_name == 0 and same_code == 0 and bad_map == 0 and pair_ok and no_reason == 0
    return ok, f"4분기 지표명 불일치 {same_name}, 코드 불일치 {same_code}, S/D 연결 위반 {bad_map}, 코드-이름 짝 {pair_ok}, 보류 사유 없음 {no_reason}"


def check_lv(a):
    s = a["resident"] / (a["resident"] + a["worker"])
    valid = a["resident"].ge(0) & a["worker"].ge(0) & (a["resident"] + a["worker"]).gt(0)
    exp = pd.Series(np.where(~valid, None, np.where(s > 0.55, "L", np.where(s < 0.45, "V", None))), index=a.index)
    bad = int((a["LV"].fillna("-") != exp.fillna("-")).sum())
    no_reason = int((a["LV"].isna() & a["LV_reason"].isna()).sum())
    return bad == 0 and no_reason == 0, f"손계산과 다른 상권 {bad}, 보류인데 사유 없음 {no_reason}"


def check_ep(c, scores_ind):
    t = c["score_status"].eq("점수 대상")
    valid = t & c["sales_status"].eq("네 분기") & c["ticket"].gt(0) & ~c["repeated_sales"].fillna(False).astype(bool)
    off = int(c.loc[~valid, ["ticket_pct", "EP"]].notna().any(axis=1).sum())
    unsup = set(scores_ind.loc[~scores_ind["매출_제공_업종"], "업종_코드"])
    unsup_ep = int(c.loc[c["industry_code"].isin(unsup), "EP"].notna().sum())
    exp = np.where(c["ticket_pct"] < 45, "E", np.where(c["ticket_pct"] > 55, "P", None))
    bad_letter = int((c["EP"].fillna("-") != pd.Series(exp, index=c.index).fillna("-")).sum())
    no_reason = int((t & c["EP"].isna() & c["EP_reason"].isna()).sum())
    rng = int(((c["ticket_pct"] <= 0) | (c["ticket_pct"] > 100)).sum())
    ok = off == 0 and unsup_ep == 0 and bad_letter == 0 and no_reason == 0 and rng == 0 and len(unsup) == 38
    return ok, (f"판정 대상 밖의 E/P {off}, 매출 미제공 {len(unsup)}개 업종의 E/P {unsup_ep}, 경계 규칙 위반 {bad_letter}, "
                f"사유 없음 {no_reason}, 백분위 범위 밖 {rng}")


def check_types(c):
    t = c["score_status"].eq("점수 대상")
    full = t & c[["LV", "EP", "SD"]].notna().all(axis=1)
    valid = set(bt.TYPE_NAMES)
    bad_code = int((c["type_full"].notna() & ~c["type_full"].isin(valid)).sum())
    bad_full = int((c["type_full"].notna() != full).sum())
    bad_concat = int((c.loc[full, "type_full"] != c.loc[full, "LV"] + c.loc[full, "EP"] + c.loc[full, "SD"]).sum())
    non_target = int(c.loc[~t, ["type_code", "type_full"]].notna().any(axis=1).sum())
    has_g = int(c["type_code"].fillna("").str.contains("G").sum())
    ok = bad_code == 0 and bad_full == 0 and bad_concat == 0 and non_target == 0 and has_g == 0
    return ok, f"없는 코드 {bad_code}, 판정 여부 불일치 {bad_full}, 글자 조합 불일치 {bad_concat}, 점수 대상 밖 유형 {non_target}, G 코드 {has_g}"


def check_scores(picks, choice, weights):
    """종합 점수를 가중 평균 공식으로 손계산한다. 자료가 없는 영역은 빼고 가중치를 다시 나눈다."""
    mode = r.DEMAND_LINK[choice.get("LV")]
    cols = {"sales": "score_sales", "comp": "score_comp", "stab": "score_stab", "dem": f"score_dem_{mode}"}
    worst = 0.0
    for _, row in picks.iterrows():
        num = sum(weights[k] * row[col] for k, col in cols.items() if not pd.isna(row[col]))
        den = sum(weights[k] for k, col in cols.items() if not pd.isna(row[col]))
        worst = max(worst, abs(num / den - row["score_total"]))
    dem_ok = bool((picks["score_dem"].fillna(-1) == picks[f"score_dem_{mode}"].fillna(-1)).all())
    return worst < 1e-9 and dem_ok, f"최대 오차 {worst:.2e}, 수요 연결 {mode} 일치 {dem_ok}"


# ---------------------------------------------------------------- 실행

def main():
    before_in = {p: sha(p) for p in bt.INPUTS}
    before_out = outside_changes()
    scores, mart, cells, areas = bt.load_inputs()
    dim = pd.read_csv(DIM, dtype={"trdar_code": str})
    scores_ind = pd.read_csv(REPO / "이승희" / "step4_dashboard" / "data" / "업종별_점수_가능여부.csv", dtype={"업종_코드": str}, encoding="utf-8-sig")

    # 1. 두 번 만들어 바이트가 같은지, 저장된 결과와 같은지
    hashes = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(2):
            out = Path(tmp) / f"run{i}"
            bt.write(*bt.build(scores, mart, cells, areas), out=out)
            hashes.append({f: sha(out / f) for f in OUT_FILES})
    saved = {f: sha(bt.OUT / f) for f in OUT_FILES}
    record(1, "두 번 실행 바이트 동일 · 저장본과 같음", hashes[0] == hashes[1] == saved,
           f"출력 {len(OUT_FILES)}개, 1·2회 동일 {hashes[0] == hashes[1]}, 저장본 동일 {hashes[0] == saved}")

    c = pd.read_parquet(bt.OUT / "상권업종_유형_2025.parquet")
    a = pd.read_csv(bt.OUT / "상권_유형축_2025.csv", dtype={"trdar_code": str}, encoding="utf-8-sig")

    record(2, "관광특구 제외 · 상권 수", *(lambda ok, d: (ok and len(a) == 1644 and len(c) == 76591, d + f", 상권×업종 {len(c):,}칸"))(*check_tourist(c, a, dim)))
    record(3, "S/D = 상권변화지표 2025년 4분기", *check_sd(a, mart))

    # 4. 서울시 H/L 글자 규칙 재현. 개월 수가 정수로 반올림돼 있어 서울 평균과 같은 값(동점)은 판정할 수 없다.
    m = mart.copy()
    m["avg_run"] = m["기준_년분기_코드"].map({k: v[0] for k, v in SEOUL_AVG.items()})
    m["avg_closed"] = m["기준_년분기_코드"].map({k: v[1] for k, v in SEOUL_AVG.items()})
    tie = m["운영_영업_개월_평균"].eq(m["avg_run"]) | m["폐업_영업_개월_평균"].eq(m["avg_closed"])
    letter = (np.where(m["운영_영업_개월_평균"] > m["avg_run"], "H", "L").astype(object)
              + np.where(m["폐업_영업_개월_평균"] > m["avg_closed"], "H", "L").astype(object))
    bad = int((letter[~tie] != m.loc[~tie, "상권_변화_지표"]).sum())
    record(4, "상권변화지표 글자 규칙 (첫 글자 = 영업 중 가게, 둘째 = 문 닫은 가게)", bad == 0,
           f"동점이 아닌 {int((~tie).sum()):,}행 중 불일치 {bad}행 · 서울 평균과 같은 값(동점) {int(tie.sum())}행은 판정 제외")

    same = a["chg_same_all_year"].sum()
    record(5, "상권변화지표 연중 일관성", a["chg_quarters"].eq(4).all() and same == 1443,
           f"1,644곳 모두 4개 분기 자료 {bool(a['chg_quarters'].eq(4).all())}, 4개 분기 같은 지표 {same:,}곳 ({same / len(a):.1%})")

    record(6, "L/V 손계산과 보류", *check_lv(a))
    edge = bt.axis_lv(pd.Series([55, 55.01, 45, 44.99, 0, np.nan, -1, 10]), pd.Series([45, 44.99, 55, 55.01, 0, 5, 5, 0]))[1]
    want = [None, "L", None, "V", None, None, None, "L"]
    record(7, "L/V 경계값 (0.55·0.45는 보류, 0·결측·음수는 보류)", [None if pd.isna(x) else x for x in edge] == want,
           f"결과 {[None if pd.isna(x) else x for x in edge]}")

    record(8, "E/P 대상·경계·결측", *check_ep(c, scores_ind))
    g = c.loc[c["industry_code"].eq("CS100010") & c["ticket_pct"].notna()].copy()
    x = g["ticket"].to_numpy()
    less = (x[None, :] < x[:, None]).sum(axis=1)   # 나보다 작은 값 개수
    equal = (x[None, :] == x[:, None]).sum(axis=1)  # 나와 같은 값 개수 (나 포함)
    hand = (less + (equal + 1) / 2) / len(x) * 100  # 동점은 평균 순위
    record(9, "E/P 백분위 손계산 (커피-음료, 직접 세기)", bool(np.allclose(hand, g["ticket_pct"])) and len(g) >= 30,
           f"{len(g)}곳, 최대 오차 {float(np.abs(hand - g['ticket_pct'].to_numpy()).max()):.2e}")

    record(10, "유형 코드", *check_types(c))

    # 11~14. 추천
    b = r.load_bundle()
    w = r.bs.DEFAULT_WEIGHTS
    rows = []
    for code in bt.TYPE_NAMES:
        ch = r.parse_type(code)
        p = r.recommend(b, "CS100010", ch)
        ok, _ = check_scores(p, ch, w)
        match = bool((p["type_full"] == code).all())
        rows.append((code, len(p), ok and match, len(p) == r.funnel(b, "CS100010", ch)[-1][1]))
    record(11, "8유형 추천: 일치·점수 손계산·조건별 수", all(x[2] and x[3] for x in rows),
           " / ".join(f"{x[0]} {x[1]}곳" for x in rows))

    allp = r.recommend(b, "CS100010", {})
    ok_s, det_s = check_scores(allp, {}, w)
    part = r.recommend(b, "CS100010", {"LV": "V", "SD": "S"}, ["강남구", "서초구"], {"sales": 50, "comp": 0, "stab": 10, "dem": 40})
    ok_p, det_p = check_scores(part, {"LV": "V"}, {"sales": 50, "comp": 0, "stab": 10, "dem": 40})
    part_ok = bool(part["LV"].eq("V").all() and part["SD"].eq("S").all() and part["gu_name"].isin(["강남구", "서초구"]).all())
    record(12, "상관없음·일부 축·자치구·가중치 변경", len(allp) == 960 and ok_s and ok_p and part_ok and len(part) > 0,
           f"모두 상관없음 {len(allp)}곳({det_s}) / V+S+강남·서초 {len(part)}곳 필터 {part_ok} ({det_p})")

    sd_hold = r.recommend(b, "CS100010", {"SD": "D"})
    no_mid = not sd_hold["chg_name"].isin(["상권확장", "상권축소"]).any()
    noep = b.industries.loc[b.industries["점수_대상_칸"].gt(0) & b.industries["EP_판정_칸"].eq(0), "업종_코드"]
    empty = r.recommend(b, noep.iloc[0], {"EP": "E"}) if len(noep) else pd.DataFrame()
    record(13, "보류 칸 제외 · 빈 결과", no_mid and len(noep) > 0 and empty.empty,
           f"D를 고르면 상권확장·축소 0건 {no_mid} / 가격대 판정이 없는 업종 {len(noep)}개 중 {noep.iloc[0] if len(noep) else '-'}에서 E 선택 → {len(empty)}곳 (다른 유형으로 채우지 않음)")

    errors = 0
    for call in [lambda: r.recommend(b, "CS999999", {}), lambda: r.recommend(b, "CS100010", {"LV": "X"}),
                 lambda: r.parse_type("ABC"), lambda: r.parse_type("LXS")]:
        try:
            call()
        except ValueError:
            errors += 1
    legacy = r.parse_type("VPG") == {"LV": "V", "EP": "P", "SD": "D"}
    record(14, "잘못된 입력 거부 · 예전 G 코드 변환", errors == 4 and legacy, f"ValueError {errors}/4, VPG → VPD {legacy}")

    # 15. 차트 함수가 빈 값·보통 값에서 깨지지 않는지
    pal = r.v4.palette(None)
    try:
        alt_specs = [r.type_bar(r.type_counts(b, "CS100010"), "LES", pal), r.hold_bar(r.hold_counts(b, "CS100010"), pal),
                     r.area_sd_chart(b.areas, pal)]
        for s in alt_specs:
            s.to_dict(validate=True)  # Vega-Lite 명세 규칙 위반이면 여기서 오류
        fig = r.map_figure(b, part, r.seoul_scope(b, "CS100010", {"LV": "V"}), None, pal)
        none_map = r.map_figure(b, part.iloc[0:0], allp, None, pal) is None
        record(15, "차트 만들기·명세 검사 (빈 결과 포함)", fig is not None and none_map,
               f"Altair 차트 {len(alt_specs)}개 명세 통과, Plotly 지도 {fig is not None}, 빈 결과 지도 없음 {none_map}")
    except Exception as e:  # noqa: BLE001
        record(15, "차트 만들기 (빈 결과 포함)", False, repr(e))

    # 16. 변조 시험: 일부러 틀린 데이터를 넣으면 위 검사가 잡아내야 한다
    caught = {}
    t_a = pd.concat([a, a.iloc[[0]].assign(trdar_code=dim.loc[dim["is_tourist"], "trdar_code"].iloc[0])])
    caught["관광특구"] = not check_tourist(c, t_a, dim)[0]
    t_a = a.copy(); t_a.loc[t_a["chg_name"].eq("상권확장"), "SD"] = "S"
    caught["확장→S"] = not check_sd(t_a, mart)[0]
    t_a = a.copy(); t_a.loc[t_a.index[0], "LV"] = "V" if t_a.loc[t_a.index[0], "LV"] == "L" else "L"
    caught["L/V 뒤집기"] = not check_lv(t_a)[0]
    t_c = c.copy(); idx = t_c.index[~t_c["score_status"].eq("점수 대상")][0]; t_c.loc[idx, ["ticket_pct", "EP"]] = [10.0, "E"]
    caught["점수 대상 밖 E/P"] = not check_ep(t_c, scores_ind)[0]
    t_c = c.copy(); idx = t_c.index[t_c["type_full"].notna()][0]; t_c.loc[idx, "type_full"] = "LEG"
    caught["G 코드"] = not check_types(t_c)[0]
    t_p = part.copy(); t_p.loc[t_p.index[0], "score_total"] += 1
    caught["점수 1점 조작"] = not check_scores(t_p, {"LV": "V"}, {"sales": 50, "comp": 0, "stab": 10, "dem": 40})[0]
    caught["옛 입력"] = len(r.stale_inputs(dict(b.meta, inputs=dict(b.meta["inputs"], **{next(iter(b.meta["inputs"])): "0" * 64})))) == 1
    record(16, "변조 시험", all(caught.values()), ", ".join(f"{k} {'발견' if v else '놓침'}" for k, v in caught.items()))

    # 17. 화면 극단 상황: 결과 0곳 표, 가중치가 모두 0, 지금 입력이 최신인지
    errs = 0
    for code in b.industries.loc[b.industries["점수_대상_칸"].gt(0), "업종_코드"]:
        for t_ in [*bt.TYPE_NAMES, None]:
            try:
                r.result_table(r.recommend(b, code, r.parse_type(t_)))
            except Exception:  # noqa: BLE001
                errs += 1
    empty_tbl = r.result_table(r.recommend(b, noep.iloc[0], {"EP": "E"}))
    zero = r.result_table(r.recommend(b, "CS100010", {"LV": "L"}, None, {"sales": 0, "comp": 0, "stab": 0, "dem": 0}))
    zero_ok = bool(zero["서울 순위"].eq("점수 없음").all()) and zero["종합 점수"].isna().all()
    record(17, "화면 극단 상황 (빈 결과·가중치 0·옛 입력)", errs == 0 and empty_tbl.empty and list(empty_tbl.columns) == list(zero.columns) and zero_ok and b.stale == (),
           f"77개 업종 × 9가지 선택 표 오류 {errs}건, 빈 표 열 유지 {list(empty_tbl.columns) == list(zero.columns)}, "
           f"가중치 0 → '점수 없음' {zero_ok}, 옛 입력 {list(b.stale)}")

    # 18. 화면 파일 검사, 19. 입력과 다른 폴더 보존
    chk = subprocess.run([sys.executable, "-m", "marimo", "check", str(HERE / "app.py")], capture_output=True, text=True, encoding="utf-8")
    record(18, "marimo check app.py", chk.returncode == 0 and not chk.stdout.strip(), f"종료 코드 {chk.returncode} {chk.stdout.strip()[:200]}")
    after_in = {p: sha(p) for p in bt.INPUTS}
    record(19, "입력 파일과 이 폴더 밖 보존", before_in == after_in and before_out == outside_changes(),
           f"입력 {len(after_in)}개 SHA-256 동일 {before_in == after_in}, 폴더 밖 변경 목록 동일 {before_out == outside_changes()}")

    failed = [x for x in RESULTS if not x[2]]
    print(f"\n결과: {len(RESULTS) - len(failed)}/{len(RESULTS)} 통과")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
