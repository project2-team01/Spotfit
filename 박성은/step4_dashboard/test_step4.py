# -*- coding: utf-8 -*-
"""
STEP 4 점수표·대시보드 검증. 팀 저장소 루트에서 실행:
    uv run --project "박성은/step4_dashboard" python "박성은/step4_dashboard/test_step4.py"

검사 1~10, 13을 이 파일에서 한다. 11(marimo check)과 12(HTML 내보내기)는 명령으로 따로 실행한다.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_scores as bs  # noqa: E402
import views as v  # noqa: E402

REPO = bs.REPO
OUT = bs.OUT
OUT_FILES = ["상권_업종_비교점수_2025.parquet", "업종별_점수_가능여부.csv", "점수_설계표.csv", "stage4_meta.json",
             "quarter_mart.parquet", "map_geometry.json", "업종별_경쟁수요_상관.csv"]
RESULTS = []


def record(no, name, ok, detail):
    RESULTS.append((no, name, ok, detail))
    print(f"[검사 {no:>2}] {'통과' if ok else '실패'} | {name} | {detail}", flush=True)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------- 점수표 규칙 검사 (변조 시험에서 재사용)

def check_tourist(d, dim):
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    n = int(d["trdar_code"].isin(tourist).sum())
    return n == 0, f"관광특구 {n}건"


def check_small(d):
    scored = d.filter(regex=r"^score_(sales|comp|stab|dem_|total)").notna().any(axis=1)
    bad = int((scored & d["stores"].lt(bs.MIN_STORES)).sum())
    return bad == 0, f"점수가 있는 칸 {int(scored.sum()):,}개 중 평균 점포 5개 미만 {bad}건"


def check_peers(d, ind):
    no_ind = set(ind.loc[~ind["점수_생성"], "업종_코드"])
    bad = int(d.loc[d["industry_code"].isin(no_ind)].filter(regex=r"^score_(sales|comp|stab|dem_|total)").notna().any(axis=1).sum())
    peers_ok = bool((ind.loc[ind["점수_생성"], "점포5개이상_상권_수"] >= bs.MIN_PEERS).all()
                    and (ind.loc[~ind["점수_생성"], "점포5개이상_상권_수"] < bs.MIN_PEERS).all())
    return bad == 0 and len(ind) == 100 and peers_ok, f"업종 {len(ind)}개, 점수 없는 업종 {len(no_ind)}개에 점수 {bad}건, 기준 일치 {peers_ok}"


def check_missing(d, ind):
    unsup = set(ind.loc[~ind["매출_제공_업종"], "업종_코드"])
    u = d["industry_code"].isin(unsup)
    bad_score = int(d.loc[u, "score_sales"].notna().sum())
    bad_zero = int(d.loc[u, "sales_month"].notna().sum())
    not4 = int(d.loc[~d["sales_status"].eq("네 분기"), "score_sales"].notna().sum())
    zero_sales = int(d["sales_month"].eq(0).sum())
    ok = len(unsup) == 38 and bad_score == 0 and bad_zero == 0 and not4 == 0 and zero_sales == 0
    return ok, (f"미제공 업종 {len(unsup)}개: 매출 점수 {bad_score}건, 매출값 {bad_zero}건 / "
                f"4개 분기 매출 없는 칸의 매출 점수 {not4}건 / 매출 0원으로 채운 칸 {zero_sales}건")


def check_range(d):
    cols = ["score_sales", "score_comp", "score_stab", "score_dem_floating", "score_dem_worker", "score_dem_resident", "score_dem_avg", "score_total_default"]
    bad = {c: int(((d[c] <= 0) | (d[c] > 100)).sum()) for c in cols}
    return sum(bad.values()) == 0, "범위 밖 " + ", ".join(f"{k.replace('score_', '')} {n}" for k, n in bad.items())


def check_direction(d):
    t = d.loc[d["score_status"].eq("점수 대상")]
    pairs = [("sales_month", "score_sales", True), ("comp_ratio", "score_comp", False), ("close_pct_shrunk", "score_stab", False),
             ("floating_density", "score_dem_floating", True), ("worker_density", "score_dem_worker", True), ("resident_density", "score_dem_resident", True)]
    bad = {}
    for raw, score, up in pairs:
        n = 0
        for _, g in t[["industry_code", raw, score]].dropna().groupby("industry_code"):
            g = g.sort_values(raw)
            s = g[score].to_numpy()
            r = g[raw].to_numpy()
            # 원값이 엄격히 더 좋은데 점수가 더 낮은 경우 (동점 원값은 같은 점수여야 함)
            diff_r, diff_s = np.diff(r), np.diff(s)
            n += int(((diff_r > 0) & ((diff_s < 0) if up else (diff_s > 0))).sum())
            n += int(((diff_r == 0) & (diff_s != 0)).sum())
        bad[score] = n
    return sum(bad.values()) == 0, "방향 위반 " + ", ".join(f"{k.replace('score_', '')} {n}" for k, n in bad.items())


# ---------------------------------------------------------------- 검사


def main():
    dim = pd.read_csv(bs.JY_STEP / "dim_trdar.csv.gz", dtype={"trdar_code": str})

    # 9. 두 번 실행해 결과 비교 + 1. 입력 지문
    in_before = {p: sha(p) for p in bs.INPUTS}
    hashes = []
    for _ in range(2):
        r = subprocess.run([sys.executable, str(HERE / "build_scores.py")], capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print(r.stdout, r.stderr)
            sys.exit("build_scores.py 실행 실패")
        hashes.append({f: sha(OUT / f) for f in OUT_FILES})
    in_after = {p: sha(p) for p in bs.INPUTS}
    relative = HERE.relative_to(REPO).as_posix()
    git_result = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all",
                                 "--", ".", f":(exclude){relative}"], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    git = git_result.stdout.strip()
    assert git_result.returncode == 0, git_result.stderr
    record(1, "입력 파일과 작업 폴더 밖 보존", in_before == in_after and git == "",
           f"입력 지문 {len(bs.INPUTS)}개 동일 {in_before == in_after}, 작업 폴더 밖 변경 {'없음' if git == '' else git}")

    d = pd.read_parquet(OUT / OUT_FILES[0])
    ind = pd.read_csv(OUT / OUT_FILES[1], dtype={"업종_코드": str}, encoding="utf-8-sig")

    ok1, m1 = check_tourist(d, dim)
    ok2, m2 = check_small(d)
    record(2, "관광특구 0건 · 점수 칸은 평균 점포 5개 이상", ok1 and ok2, f"{m1}, {m2}")
    ok, m = check_peers(d, ind)
    record(3, "비교 상권 30곳 미만 업종은 점수 없음 · 100개 업종", ok, m)
    ok, m = check_missing(d, ind)
    record(4, "매출 미제공 38개 업종의 매출 점수 결측 · 0원 채우기 없음", ok, m)
    ok, m = check_range(d)
    record(5, "모든 영역·종합 점수 0 초과 100 이하", ok, m)
    ok, m = check_direction(d)
    record(6, "방향 검사 (원값이 더 좋으면 점수가 더 낮지 않음)", ok, m)

    # 7. 가중치 재분배 손계산
    t = d.loc[d["score_status"].eq("점수 대상") & d["score_sales"].isna()].iloc[0]
    w = bs.DEFAULT_WEIGHTS
    hand = (t["score_comp"] * w["comp"] + t["score_stab"] * w["stab"] + t["score_dem_avg"] * w["dem"]) / (w["comp"] + w["stab"] + w["dem"])
    t2 = d.loc[d["score_status"].eq("점수 대상") & d["score_sales"].notna()].iloc[0]
    hand2 = sum(t2[c] * w[k] for k, c in [("sales", "score_sales"), ("comp", "score_comp"), ("stab", "score_stab"), ("dem", "score_dem_avg")]) / sum(w.values())
    ok7 = abs(hand - t["score_total_default"]) < 1e-9 and t["n_areas_default"] == 3 and abs(hand2 - t2["score_total_default"]) < 1e-9
    record(7, "가중치 재분배 (매출 결측 칸은 나머지 3개 영역으로)", ok7,
           f"{t['trdar_name']}·{t['industry_name']}: 손계산 {hand:.4f} = 표 {t['score_total_default']:.4f} ({int(t['n_areas_default'])}개 영역); "
           f"4개 영역 칸 손계산 {hand2:.4f} = 표 {t2['score_total_default']:.4f}")

    # 8. 손계산 재현: 커피-음료 상권 2곳을 원본 패널에서 다시 계산
    fact = pd.read_csv(bs.JY_STEP / "fact_trdar_industry_quarter.csv.gz", dtype={"quarter": str, "trdar_code": str, "industry_code": str},
                       usecols=["quarter", "trdar_code", "industry_code", "store_count", "close_count", "sales_amount", "sales_observed", "main_analysis_eligible"])
    coffee = d.loc[d["industry_code"].eq("CS100010") & d["score_status"].eq("점수 대상") & d["score_sales"].notna()]
    picks = [coffee.sort_values("score_total_default").iloc[len(coffee) // 4], coffee.sort_values("score_total_default").iloc[3 * len(coffee) // 4]]
    peers = d.loc[d["industry_code"].eq("CS100010") & d["score_status"].eq("점수 대상")]
    msgs, ok8 = [], True
    for p in picks:
        f = fact.loc[fact["trdar_code"].eq(p["trdar_code"]) & fact["industry_code"].eq("CS100010")]
        stores = f["store_count"].sum() / 4
        sales_month = f["sales_amount"].sum() / f.loc[f["sales_observed"], "store_count"].sum() / 3
        closes = f["close_count"].sum()

        def avg_rank_pct(series, x, up=True):
            s = series.dropna().tolist()
            less = sum(1 for y in s if (y < x if up else y > x))
            ties = sum(1 for y in s if y == x)
            return (less + (ties + 1) / 2) / len(s) * 100

        hs = avg_rank_pct(peers.loc[peers["score_sales"].notna(), "sales_month"], p["sales_month"])
        hc = avg_rank_pct(peers["comp_ratio"], p["stores"] / (p["floating"] / 1000), up=False)
        hst = avg_rank_pct(peers["close_pct_shrunk"], p["close_pct_shrunk"], up=False)
        hd = np.nanmean([avg_rank_pct(peers[c], p[c]) if pd.notna(p[c]) else np.nan for c in ["floating_density", "worker_density", "resident_density"]])
        ht = (hs * 30 + hc * 25 + hst * 15 + hd * 30) / 100
        good = (abs(stores - p["stores"]) < 1e-9 and abs(sales_month - p["sales_month"]) < 1e-3 and closes == p["closes"]
                and all(abs(a - b) < 1e-9 for a, b in [(hs, p["score_sales"]), (hc, p["score_comp"]), (hst, p["score_stab"]), (hd, p["score_dem_avg"]), (ht, p["score_total_default"])]))
        ok8 &= good
        msgs.append(f"{p['trdar_name']}: 점포 {stores:.2f}·월매출 {sales_month / 1e4:,.0f}만·폐업 {closes:.0f}건 원본 일치, "
                    f"영역 {hs:.1f}/{hc:.1f}/{hst:.1f}/{hd:.1f} → 종합 {ht:.2f} (표 {p['score_total_default']:.2f})")
    record(8, "손계산 재현 (커피-음료 2곳, 원본 패널부터)", ok8, " | ".join(msgs))

    record(9, "두 번 실행 결과 바이트 동일", hashes[0] == hashes[1], f"출력 {len(OUT_FILES)}개 sha256 {'동일' if hashes[0] == hashes[1] else '다름'}")

    # 10. 변조 시험: 일부러 틀린 점수표를 넣었을 때 검사가 실패해야 한다
    muts = []
    m = d.copy()
    m = pd.concat([m, m.iloc[[0]].assign(trdar_code=sorted(dim.loc[dim["is_tourist"], "trdar_code"])[0])], ignore_index=True)
    muts.append(("관광특구 1건 섞기", not check_tourist(m, dim)[0]))
    m = d.copy()
    i = m.index[m["sales_status"].eq("미제공 업종")][0]
    m.loc[i, ["sales_month", "score_sales"]] = [0.0, 50.0]
    muts.append(("매출 결측을 0원으로 바꾸기", not check_missing(m, ind)[0]))
    m = d.copy()
    i = m.index[m["stores"].lt(5) & m["stores"].ge(3)][0]
    m.loc[i, "score_total_default"] = 60.0
    muts.append(("점포 3~4개 칸에 점수 넣기", not check_small(m)[0]))
    m = d.copy()
    m["score_stab"] = 100 - m["score_stab"] + 1e-6
    muts.append(("안정성 방향 뒤집기", not check_direction(m)[0]))
    m = d.copy()
    m.loc[m.index[m["score_comp"].notna()][0], "score_comp"] = 120.0
    muts.append(("점수 120점 넣기", not check_range(m)[0]))
    m = d.copy()
    no_ind = ind.loc[~ind["점수_생성"], "업종_코드"].iloc[0]
    m.loc[m.index[m["industry_code"].eq(no_ind)][0], "score_comp"] = 40.0
    muts.append(("점수 없는 업종에 점수 넣기", not check_peers(m, ind)[0]))
    record(10, "변조 시험 (틀린 데이터를 검사가 잡는지)", all(ok for _, ok in muts),
           ", ".join(f"{n} {'잡음' if ok else '놓침'}" for n, ok in muts))

    # 13. 화면 함수: 기본·매출 미제공 업종·점수 없는 업종·빈 결과·가중치 0
    bundle = v.load_bundle()
    pal = v.palette(None)
    unsup = ind.loc[~ind["매출_제공_업종"] & ind["점수_생성"], ["업종_코드", "업종명"]].iloc[0]
    noscore = ind.loc[~ind["점수_생성"], ["업종_코드", "업종명"]].iloc[0]
    cases = [
        ("기본 (커피-음료)", "CS100010", None, None, bs.DEFAULT_WEIGHTS, "avg"),
        (f"매출 미제공 ({unsup['업종명']})", unsup["업종_코드"], None, None, bs.DEFAULT_WEIGHTS, "worker"),
        (f"점수 없는 업종 ({noscore['업종명']})", noscore["업종_코드"], None, None, bs.DEFAULT_WEIGHTS, "avg"),
        ("빈 결과 (없는 자치구)", "CS100010", ["없는구"], None, bs.DEFAULT_WEIGHTS, "avg"),
        ("가중치 모두 0", "CS100010", None, None, {"sales": 0, "comp": 0, "stab": 0, "dem": 0}, "avg"),
        ("자치구·유형 필터 (강남구 골목상권)", "CS100001", ["강남구"], ["골목상권"], bs.DEFAULT_WEIGHTS, "resident"),
    ]
    out = []
    ok13 = True
    for name, code, gus, types, w, mode in cases:
        try:
            s = v.filter_scope(bundle, code, gus, types, w, mode)
            v.summarize(s)
            v.top_change(s, w, mode)
            v.score_table(s)
            sel = v.choose_code(None, s)
            spec = v.map_chart(bundle, s, sel, pal, seoul=v.filter_scope(bundle, code, None, None, w, mode))
            fig = v.map_plotly(bundle, s, sel, pal, seoul=v.filter_scope(bundle, code, None, None, w, mode))
            if fig is not None:
                fig.to_json()
                n_geo = sum(len(t.locations) for t in fig.data if t.type == "choroplethmap" and t.name != "고른 상권")
                ok13 &= n_geo == len(s)  # 조건 안 상권이 지도에 빠짐없이 그려지는지
            if spec is not None:
                spec.to_dict()
            if sel is not None:
                row = s.loc[s["trdar_code"].eq(sel)].iloc[0]
                v.raw_compare(row, v.filter_scope(bundle, code))
                q = v.quarter_rows(bundle, sel, code)
                v.area_bars(row, pal).to_dict()
                v.area_bars(row, pal, industry_scope=v.filter_scope(bundle, code)).to_dict()
                radar = v.radar_chart(row, v.filter_scope(bundle, code), pal)
                radar.to_json()
                if pd.isna(row.score_sales):
                    ok13 &= radar.data[1].r[0] is None and radar.data[1].connectgaps is False
                facet = v.comparison_facets(s, s.trdar_code.head(4).tolist(), pal)
                facet.to_dict()
                ch = v.month_trend_chart(q, pal)
                if ch is not None:
                    ch.to_dict()
                v.flow_chart(q, pal).to_dict()
            for label in v.HIST_METRICS:
                h = v.histogram(s, label, pal)
                if h is not None:
                    h.to_dict()
            g = v.gu_chart(s, pal)
            if g is not None:
                g.to_dict()
            scored = int(s["score_total"].notna().sum())
            if name.startswith("점수 없는") or name.startswith("가중치"):
                ok13 &= scored == 0
            if name.startswith("빈 결과"):
                ok13 &= len(s) == 0
            if name.startswith("매출 미제공"):
                ok13 &= scored > 0 and int(s["score_sales"].notna().sum()) == 0 and int(s.loc[s["score_total"].notna(), "n_areas"].max()) == 3
            out.append(f"{name}: 상권 {len(s):,}곳·점수 {scored:,}곳")
        except Exception as e:  # noqa: BLE001
            ok13 = False
            out.append(f"{name}: 오류 {type(e).__name__}: {e}")
    record(13, "화면 함수 경계 상황 (오류 없음·기대 결과)", ok13, " | ".join(out))

    cached = v.filter_scope(bundle, "CS100010")
    expected = v._filter_scope_uncached(bundle, "CS100010")
    pd.testing.assert_frame_equal(cached, expected)
    cached.loc[:, "score_total"] = -999
    pd.testing.assert_frame_equal(v.filter_scope(bundle, "CS100010"), expected)
    assert v.load_bundle() is bundle
    print("[추가 검사] 캐시와 직접 계산 동일, 반환값 변경이 캐시에 영향 없음, 데이터 한 번만 로드", flush=True)

    q = bundle.quarters
    prev_q = q.groupby(["trdar_code", "industry_code"]).quarter.shift(1)
    gaps = pd.to_numeric(q.quarter) - pd.to_numeric(prev_q) != 1
    assert q.loc[gaps, "qoq_raw"].isna().all()
    print("[추가 검사] 1분기·비연속 분기의 전분기 증감률 결측 유지", flush=True)

    (HERE / "report").mkdir(exist_ok=True)
    (HERE / "report/core_validation.json").write_text(json.dumps([
        {"number": no, "name": name, "passed": bool(ok), "evidence": detail}
        for no, name, ok, detail in RESULTS], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fails = [r for r in RESULTS if not r[2]]
    print(f"\n결과: {len(RESULTS) - len(fails)}/{len(RESULTS)} 통과")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
