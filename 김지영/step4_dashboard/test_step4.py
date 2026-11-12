"""STEP 4 검증 13개 (지시서 6장). 각 검사의 숫자 근거를 출력하고, 하나라도 실패하면 종료 코드 1.

실행 (저장소 루트에서, 약 3~4분)
  uv run --project "김지영/step4_dashboard" python "김지영/step4_dashboard/test_step4.py"
  ... test_step4.py --skip-app    # 11~13 (marimo 확인·내보내기) 건너뛰기

임시 결과(두 번 실행 비교, 화면 내보내기)는 작업 폴더 안 .check/ 에 만들고 끝나면 지운다.
검사 12의 정적 HTML만 report/04_상권비교점수_대시보드_2025.html 로 남긴다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import build_scores as b
import views as v

HERE, ROOT = b.HERE, b.ROOT
CHECK = HERE / ".check"
REPORT = HERE / "report" / "04_상권비교점수_대시보드_2025.html"
SHARED_FILES = sorted(p for p in v.SHARED.iterdir() if p.is_file())
SCORE_COLS = ["score_sales", "score_competition", "score_stability", "score_demand", "pct_floating", "pct_worker", "pct_resident", "score_total"]
AREA_COLS = ["score_sales", "score_competition", "score_stability", "score_demand"]
EPS = 1e-9
RESULTS: list[tuple[int, str, bool, str]] = []


def record(no: int, name: str, problems: list[str], evidence: str) -> None:
    ok = not problems
    RESULTS.append((no, name, ok, evidence if ok else f"{evidence} | 문제: {'; '.join(problems[:5])}"))
    print(f"[{'통과' if ok else '실패'}] {no:>2}. {name}: {RESULTS[-1][3]}", flush=True)


# ---------------------------------------------------------------- 데이터 검사 (변조 시험에서 다시 쓴다). 문제 목록을 돌려준다.


def problems_tourist(scores: pd.DataFrame, dim: pd.DataFrame) -> list[str]:
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    n = int(scores["trdar_code"].isin(tourist).sum())
    return [f"관광특구 행 {n}건"] if n else []


def problems_min_stores(scores: pd.DataFrame) -> list[str]:
    has_score = scores[SCORE_COLS].notna().any(axis=1)
    out = []
    small = has_score & scores["stores"].lt(b.MIN_STORES)
    if small.any():
        out.append(f"평균 점포 5개 미만인데 점수가 있는 행 {int(small.sum())}건 (예: 점포 {scores.loc[small, 'stores'].iloc[0]:.2f}개)")
    if (has_score & ~scores["scored"]).any():
        out.append(f"점수 대상이 아닌데 점수가 있는 행 {int((has_score & ~scores['scored']).sum())}건")
    return out


def problems_thin(scores: pd.DataFrame, availability: pd.DataFrame) -> list[str]:
    peers = scores.loc[scores["stores"].ge(b.MIN_STORES)].groupby("industry_code").size()
    thin = set(availability["업종코드"]) - set(peers[peers >= b.MIN_PEERS].index)
    rows = scores["industry_code"].isin(thin) & scores[SCORE_COLS].notna().any(axis=1)
    out = [f"비교 상권 30곳 미만 업종에 점수가 있는 행 {int(rows.sum())}건"] if rows.any() else []
    listed = set(availability.loc[availability["점수 생성"].eq("아니오"), "업종코드"])
    if listed != thin:
        out.append(f"가능여부 CSV의 점수 불가 업종({len(listed)})이 다시 센 값({len(thin)})과 다름")
    return out


def problems_sales(scores: pd.DataFrame, unsupported: set[str], source_sales: pd.Series) -> list[str]:
    out = []
    bad = scores["industry_code"].isin(unsupported) & (scores["score_sales"].notna() | scores["sales_month"].notna())
    if bad.any():
        out.append(f"매출 미제공 업종에 매출 값·점수가 있는 행 {int(bad.sum())}건")
    src = scores.set_index(["trdar_code", "industry_code"]).index.map(source_sales)
    filled = pd.Series(src, index=scores.index).isna() & scores["sales_month"].notna()
    if filled.any():
        out.append(f"원자료에 매출이 없는데 값이 들어간 행 {int(filled.sum())}건 (예: {scores.loc[filled, 'sales_month'].iloc[0]})")
    zero_score = scores["sales_month"].isna() & scores["score_sales"].notna()
    if zero_score.any():
        out.append(f"매출 원값이 없는데 매출 점수가 있는 행 {int(zero_score.sum())}건")
    return out


def problems_range(scores: pd.DataFrame) -> list[str]:
    out = []
    for c in SCORE_COLS:
        x = scores[c].dropna()
        if len(x) and (x.min() < 0 or x.max() > 100):
            out.append(f"{c} 범위 {x.min():.3f}~{x.max():.3f}")
    return out


def monotone(raw: pd.Series, score: pd.Series, groups: pd.Series, higher_is_better: bool) -> int:
    """같은 업종에서 원값이 더 좋은데 점수가 더 낮은 경우(동점 원값의 점수가 다른 경우 포함)의 수."""
    d = pd.DataFrame({"raw": raw, "score": score, "g": groups}).dropna()
    if not higher_is_better:
        d["raw"] = -d["raw"]
    d = d.sort_values(["g", "raw", "score"])
    bad = 0
    for _, x in d.groupby("g"):
        r, s = x["raw"].to_numpy(), x["score"].to_numpy()
        bad += int(np.sum(np.diff(s) < -EPS))
        same = np.diff(r) == 0
        bad += int(np.sum(same & (np.abs(np.diff(s)) > EPS)))
    return bad


def dominance_violations(scores: pd.DataFrame) -> int:
    """수요: 세 구성값이 모두 같거나 더 큰 상권의 수요 점수가 더 낮은 쌍의 수."""
    d = scores.loc[scores["scored"]].dropna(subset=["score_demand"])
    bad = 0
    for _, x in d.groupby("industry_code"):
        a = x[["floating_density", "worker_density", "resident_density"]].to_numpy()
        s = x["score_demand"].to_numpy()
        ge = (a[:, None, :] >= a[None, :, :]).all(axis=2)
        bad += int(np.sum(ge & (s[:, None] < s[None, :] - EPS)))
    return bad


def problems_direction(scores: pd.DataFrame) -> tuple[list[str], dict]:
    s = scores.loc[scores["scored"]]
    g = s["industry_code"]
    counts = {
        "매출(월매출↑ 점수↑)": monotone(s["sales_month"].where(s["score_sales"].notna()), s["score_sales"], g, True),
        "경쟁(유동 대비 점포↑ 점수↓)": monotone(s["competition"], s["score_competition"], g, False),
        "안정성(축소 폐업률↑ 점수↓)": monotone(s["close_pct_shrunk"], s["score_stability"], g, False),
        "수요-유동": monotone(s["floating_density"], s["pct_floating"], g, True),
        "수요-직장": monotone(s["worker_density"], s["pct_worker"], g, True),
        "수요-상주": monotone(s["resident_density"], s["pct_resident"], g, True),
        "수요(세 구성 모두 같거나 큼 → 점수 같거나 큼)": dominance_violations(scores),
    }
    mean_gap = (s[["pct_floating", "pct_worker", "pct_resident"]].mean(axis=1, skipna=False) - s["score_demand"]).abs().max()
    counts["수요 = 세 백분위 평균 (최대 차이)"] = float(0 if pd.isna(mean_gap) else mean_gap)
    out = [f"{k} 위반 {n}건" for k, n in counts.items() if not k.startswith("수요 =") and n]
    if counts["수요 = 세 백분위 평균 (최대 차이)"] > 1e-9:
        out.append("수요 점수가 세 백분위 평균과 다름")
    return out, counts


def independent_total(row: pd.Series, weights: dict) -> float:
    """종합 점수 손계산: 자료가 있는 영역의 (가중치 × 점수) 합 ÷ 그 영역들의 가중치 합."""
    parts = [(weights[k], row[f"score_{k}"]) for k in b.AREA_KEYS if pd.notna(row[f"score_{k}"]) and weights[k] > 0]
    total_w = sum(w for w, _ in parts)
    return sum(w * x for w, x in parts) / total_w if total_w > 0 else np.nan


def problems_weights(scores: pd.DataFrame, weights: dict = b.DEFAULT_WEIGHTS) -> tuple[list[str], dict]:
    s = scores.loc[scores["scored"]]
    expect = s.apply(independent_total, axis=1, weights=weights)
    gap = (expect - s["score_total"]).abs()
    both_nan = expect.isna() & s["score_total"].isna()
    bad = ~(both_nan | (gap < 1e-9))
    one_missing = s[AREA_COLS].isna().sum(axis=1).eq(1)
    used = s[AREA_COLS].notna().sum(axis=1)
    out = [f"종합 점수가 가중 평균과 다른 행 {int(bad.sum())}건"] if bad.any() else []
    if not s["areas_used"].eq(used).all():
        out.append(f"계산 영역 수가 다른 행 {int((~s['areas_used'].eq(used)).sum())}건")
    return out, {"checked": int(len(s)), "one_missing": int(one_missing.sum()), "one_missing_ok": int((one_missing & ~bad).sum()),
                 "max_gap": float(gap.max())}


# ---------------------------------------------------------------- 손계산 (원자료에서 따로 다시 계산)


def hand_percentile(values: pd.Series, me: float, higher_is_better: bool) -> float:
    """평균 순위 백분위를 직접 센다: (나보다 나쁜 곳 수 + (나와 같은 곳 수 + 1) / 2) ÷ 비교 상권 수 × 100."""
    x = values.dropna().to_numpy()
    worse = np.sum(x < me) if higher_is_better else np.sum(x > me)
    same = np.sum(x == me)
    return (worse + (same - 1) / 2 + 1) / len(x) * 100


def hand_recompute(data: dict, scores: pd.DataFrame) -> tuple[list[str], list[dict]]:
    fact, annual, ctx, dim = data["fact"], data["annual"], data["context"], data["dim"]
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    f = fact.loc[~fact["trdar_code"].isin(tourist)]
    # 축소 추정 α: 관광특구를 뺀 점포가 있는 모든 칸에서 다시 계산
    cell = f.groupby(["trdar_code", "industry_code"]).agg(st=("store_count", "sum"), cl=("close_count", "sum")).reset_index()
    cell["st"] = cell["st"] / 4
    cell = cell.loc[cell["st"] > 0]
    ind = cell.groupby("industry_code")[["cl", "st"]].sum()
    cell["r"] = cell["industry_code"].map(ind["cl"] / ind["st"])
    mu = cell["st"] * cell["r"]
    alpha = (mu ** 2).sum() / (((cell["cl"] - mu) ** 2) - mu).sum()
    cell["shrunk"] = (cell["cl"] + alpha) / (cell["st"] + alpha / cell["r"]) * 100

    code = fact.loc[fact["industry_name"].eq("커피-음료"), "industry_code"].iloc[0]
    c = cell.loc[cell["industry_code"].eq(code)].set_index("trdar_code")
    peers = c.loc[c["st"] >= b.MIN_STORES].copy()
    x = ctx.loc[~ctx["trdar_code"].isin(tourist)].groupby("trdar_code").agg(
        flow=("floating_population", "mean"), area=("area_km2", "first"), worker=("worker_population", "first"), resident=("resident_population", "first"))
    peers = peers.join(x)
    a = annual.loc[annual["industry_code"].eq(code)].set_index("trdar_code")
    peers["sales"] = a["annual_monthly_sales_per_store"].where(a["annual_sales_complete"].notna())
    peers["comp"] = peers["st"] / (peers["flow"] / 1000)
    for k in ["flow", "worker", "resident"]:
        peers[f"{k}_d"] = peers[k] / peers["area"]

    mine = scores.loc[scores["industry_code"].eq(code) & scores["scored"]].set_index("trdar_code")
    full = mine.loc[mine[AREA_COLS].notna().all(axis=1)].sort_values("score_total", ascending=False)
    partial = mine.loc[mine["score_sales"].isna() & mine[["score_competition", "score_stability", "score_demand"]].notna().all(axis=1)]
    picks = [full.index[len(full) // 2]] + ([partial.sort_values("stores", ascending=False).index[0]] if len(partial) else [full.index[0]])
    out, shown = [], []
    w = b.DEFAULT_WEIGHTS
    for t in picks:
        p = peers.loc[t]
        hand = {
            "score_sales": hand_percentile(peers["sales"], p["sales"], True) if pd.notna(p["sales"]) else np.nan,
            "score_competition": hand_percentile(peers["comp"], p["comp"], False),
            "score_stability": hand_percentile(peers["shrunk"], p["shrunk"], False),
            "score_demand": np.mean([hand_percentile(peers[f"{k}_d"], p[f"{k}_d"], True) for k in ["flow", "worker", "resident"]]),
        }
        parts = [(w[k.removeprefix("score_")], hand[k]) for k in AREA_COLS if pd.notna(hand[k])]
        hand["score_total"] = sum(a * s for a, s in parts) / sum(a for a, _ in parts)
        row = {"상권": mine.at[t, "trdar_name"], "trdar_code": t, "평균 점포": round(float(p["st"]), 2),
               "점포당 월매출(원)": None if pd.isna(p["sales"]) else round(float(p["sales"])), "유동 1천명당 점포": round(float(p["comp"]), 5),
               "축소 폐업률(%)": round(float(p["shrunk"]), 3)}
        for k, value in hand.items():
            table_value = mine.at[t, k]
            row[f"{k} 손계산"] = None if pd.isna(value) else round(float(value), 4)
            row[f"{k} 점수표"] = None if pd.isna(table_value) else round(float(table_value), 4)
            if not ((pd.isna(value) and pd.isna(table_value)) or abs(value - table_value) < 1e-9):
                out.append(f"{t} {k}: 손계산 {value} vs 점수표 {table_value}")
        shown.append(row)
    if abs(alpha - scores.attrs.get("alpha", alpha)) > 1e-12:
        out.append("α 불일치")
    return out, shown


# ---------------------------------------------------------------- 화면 내보내기 검사


def export_html(out: Path, args: list[str]) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "marimo", "export", "html", str(HERE / "app.py"), "-o", str(out), "-f"]
    if args:
        cmd += ["--", *args]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def read_session(path: Path) -> tuple[list[dict], dict]:
    t = path.read_text(encoding="utf-8")
    m = re.search(r'__MARIMO_MOUNT_CONFIG__", \{\s*value: Object\.freeze\((\{.*?\})\),\s*writable', t, re.S)
    cfg = json.loads(m.group(1))
    code = {c["id"]: c["code"] for c in cfg["notebook"]["cells"]}
    return cfg["session"]["cells"], code


def inspect_export(path: Path, tab: int) -> dict:
    cells, code = read_session(path)
    errors, stopped, rendered, gated = [], 0, 0, 0
    for c in cells:
        for o in c["outputs"]:
            if o["type"] == "error":
                if o.get("ename") == "ancestor-stopped":
                    stopped += 1
                else:
                    errors.append(f"{o.get('ename')}: {o.get('evalue')}")
        if any(x.get("name") == "stderr" for x in c["console"]):
            errors.append("stderr 출력: " + " ".join(str(x.get("text", x.get("data", "")))[:200] for x in c["console"] if x.get("name") == "stderr"))
        if f"nav.value != PAGES[{tab - 1}]" in code.get(c["id"], ""):
            gated += 1
            rendered += int(any(o["type"] == "data" and any(str(val).strip() for val in o["data"].values()) for o in c["outputs"]))
    return {"cells": len(cells), "errors": errors, "ancestor_stopped": stopped, "tab_cells": gated, "tab_rendered": rendered}


def empty_filter(bundle: v.Bundle) -> tuple[str, str, str]:
    """고른 업종의 점포가 있는 상권이 0곳이 되는 자치구 × 유형 조합을 찾는다 (커피-음료부터).

    25개 자치구 모두 세 유형의 상권이 있어 '상권 자체가 0곳'인 조합은 없다. 그래서 '이 업종 점포가 있는 상권 0곳'을 시험한다.
    """
    areas = bundle.areas
    scored = bundle.availability.loc[bundle.availability["점수 생성"].eq("예"), "업종명"]
    names = ["커피-음료", *sorted(set(scored) - {"커피-음료"})]  # 점수가 있는 업종에서 찾는다
    code_of = bundle.availability.set_index("업종명")["업종코드"]
    for name in names:
        rows = bundle.scores.loc[bundle.scores["industry_code"].eq(code_of[name]) & bundle.scores["stores"].gt(0)]
        have = set(zip(rows["gu_name"], rows["trdar_type"]))
        for gu in sorted(areas["gu_name"].unique()):
            for kind in v.TYPES:
                if (gu, kind) not in have and ((areas["gu_name"] == gu) & (areas["trdar_type"] == kind)).any():
                    return name, gu, kind
    raise RuntimeError("점포가 0곳인 조합을 찾지 못했습니다")


# ---------------------------------------------------------------- 실행


def git_outside_changes() -> list[str]:
    p = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True, text=True, check=True)
    mine = HERE.relative_to(ROOT).as_posix() + "/"
    return [line for line in p.stdout.splitlines() if line and not line[3:].strip('"').startswith(mine)]


def shared_fingerprints() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): b.sha256(p) for p in SHARED_FILES} | b.fingerprints() | {
        (b.SOURCE / "feature_dictionary.csv").relative_to(ROOT).as_posix(): b.sha256(b.SOURCE / "feature_dictionary.csv")}


def main(skip_app: bool) -> int:
    before = shared_fingerprints()
    if CHECK.exists():
        shutil.rmtree(CHECK)
    CHECK.mkdir()
    try:
        data = b.read_inputs()
        bundle = v.load_bundle()
        scores, availability = bundle.scores, bundle.availability
        dim = data["dim"]
        scores.attrs["alpha"] = bundle.meta["alpha"]

        # 2
        p = problems_tourist(scores, dim) + problems_min_stores(scores)
        s = scores.loc[scores["scored"]]
        record(2, "관광특구 0건 · 점수 행 평균 점포 5개 이상", p,
               f"점수표 {len(scores):,}행 중 관광특구 {int(scores['trdar_code'].isin(set(dim.loc[dim['is_tourist'], 'trdar_code'])).sum())}건, "
               f"점수 있는 행 {len(s):,}건의 최소 평균 점포 {s['stores'].min():.2f}개")

        # 3
        p = problems_thin(scores, availability)
        if len(availability) != 100 or availability["업종코드"].nunique() != 100:
            p.append(f"가능여부 CSV 업종 수 {len(availability)}")
        if set(availability["업종코드"]) != set(data["fact"]["industry_code"]):
            p.append("가능여부 CSV 업종이 패널 업종과 다름")
        thin = availability.loc[availability["점수 생성"].eq("아니오")]
        record(3, "비교 상권 30곳 미만 업종 점수 없음 · 업종 100개", p,
               f"CSV {len(availability)}개 업종 = 점수 생성 {int((availability['점수 생성'] == '예').sum())} + 불가 {len(thin)}; "
               f"불가 업종 행 {int(scores['industry_code'].isin(thin['업종코드']).sum()):,}건의 점수 결측 {int(scores.loc[scores['industry_code'].isin(thin['업종코드']), SCORE_COLS].isna().all(axis=1).sum()):,}건")

        # 4
        unsupported = set(data["fact"].loc[~data["fact"]["sales_supported_industry"], "industry_code"])
        a = data["annual"].set_index(["trdar_code", "industry_code"])
        source_sales = a["annual_monthly_sales_per_store"].where(a["annual_sales_complete"].notna())
        p = problems_sales(scores, unsupported, source_sales)
        q = bundle.quarters
        if (q["sales_month_q"].notna() & ~q["sales_observed"]).any():
            p.append("분기 표에서 매출 미관측 분기에 값이 있음")
        u = scores["industry_code"].isin(unsupported)
        record(4, "매출 미제공 38개 업종 매출 점수 결측 · 0 채움 없음", p,
               f"미제공 업종 {len(unsupported)}개, 그 행 {int(u.sum()):,}건 중 매출 점수 결측 {int(scores.loc[u, 'score_sales'].isna().sum()):,}건; "
               f"원자료에 매출이 없는 행 {int(pd.Series(scores.set_index(['trdar_code', 'industry_code']).index.map(source_sales)).isna().sum()):,}건 모두 결측 유지; "
               f"월매출 0원 행 {int(scores['sales_month'].eq(0).sum())}건 (원자료 0원 {int(source_sales.eq(0).sum())}건)")

        # 5
        p = problems_range(scores)
        record(5, "모든 점수 0~100", p, " · ".join(f"{c.removeprefix('score_')} {scores[c].min():.2f}~{scores[c].max():.2f}" for c in AREA_COLS + ["score_total"]))

        # 6
        p, counts = problems_direction(scores)
        record(6, "방향 검사 (같은 업종 안)", p, ", ".join(f"{k} {n}" if isinstance(n, int) else f"{k} {n:.1e}" for k, n in counts.items()))

        # 7
        p, info = problems_weights(scores)
        ex = s.loc[s["score_sales"].isna() & s[["score_competition", "score_stability", "score_demand"]].notna().all(axis=1)].iloc[0]
        w = b.DEFAULT_WEIGHTS
        hand = (w["competition"] * ex["score_competition"] + w["stability"] * ex["score_stability"] + w["demand"] * ex["score_demand"]) / (w["competition"] + w["stability"] + w["demand"])
        if abs(hand - ex["score_total"]) > 1e-9:
            p.append("손계산 예시 불일치")
        zero_total, _ = v.composite(s, {k: 0 for k in b.AREA_KEYS})
        if zero_total.notna().any():
            p.append("가중치가 모두 0인데 종합 점수가 있음")
        record(7, "가중치 재분배", p,
               f"점수 행 {info['checked']:,}건 독립 재계산 최대 차이 {info['max_gap']:.1e}; 영역 1개 결측 {info['one_missing']:,}건 모두 일치. "
               f"손계산 예시 [{ex['trdar_name']} · {ex['industry_name']}] 매출 자료 없음 → (25×{ex['score_competition']:.2f} + 15×{ex['score_stability']:.2f} + 30×{ex['score_demand']:.2f}) ÷ 70 "
               f"= {hand:.4f} (점수표 {ex['score_total']:.4f}); 가중치 모두 0 → 종합 점수 0건")

        # 8
        p, shown = hand_recompute(data, scores)
        text = "; ".join(f"[{r['상권']}] 매출 {r['score_sales 손계산']} 경쟁 {r['score_competition 손계산']} 안정성 {r['score_stability 손계산']} "
                         f"수요 {r['score_demand 손계산']} 종합 {r['score_total 손계산']} (점수표 종합 {r['score_total 점수표']})" for r in shown)
        record(8, "커피-음료 2곳 손계산 재현", p, text)
        (CHECK / "hand.json").write_text(json.dumps(shown, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(shown, ensure_ascii=False, indent=1))

        # 9
        p = []
        runs = [b.main(CHECK / "run1"), b.main(CHECK / "run2")]
        for x, y in zip(*runs):
            if x.read_bytes() != y.read_bytes():
                p.append(f"{x.name} 두 실행 결과가 다름")
            if x.read_bytes() != (b.OUT / x.name).read_bytes():
                p.append(f"{x.name} 저장된 결과와 다름")
        record(9, "두 번 실행 바이트 동일", p, f"{len(runs[0])}개 파일 × 2회 실행, 저장된 data/ 파일과도 비교: " +
               ", ".join(f"{x.name} {b.sha256(x)[:12]}" for x in runs[0]))

        # 10 변조 시험: 일부러 틀린 데이터를 넣었을 때 위 검사가 실패해야 한다
        caught = {}
        t = scores.copy()
        t.loc[len(t)] = t.loc[t["scored"]].iloc[0]
        t.loc[len(t) - 1, "trdar_code"] = sorted(dim.loc[dim["is_tourist"], "trdar_code"])[0]
        caught["관광특구 1건 섞기"] = bool(problems_tourist(t, dim))
        t = scores.copy()
        i = t.index[t["industry_code"].isin(unsupported) & t["scored"]][0]
        t.loc[i, "sales_month"] = 0.0
        caught["매출 결측을 0으로 바꾸기 (미제공 업종)"] = bool(problems_sales(t, unsupported, source_sales))
        t = scores.copy()
        i = t.index[t["industry_code"].isin(set(unsupported) ^ set(t["industry_code"])) & t["sales_month"].isna() & t["scored"]][0]
        t.loc[i, "sales_month"] = 0.0
        caught["매출 결측을 0으로 바꾸기 (제공 업종, 일부 분기)"] = bool(problems_sales(t, unsupported, source_sales))
        t = scores.copy()
        i = (t["stores"] - 3).abs().idxmin()
        t.loc[i, ["score_competition", "score_total"]] = 50.0
        caught[f"점포 {scores.at[i, 'stores']:.2f}개 칸에 점수 넣기"] = bool(problems_min_stores(t))
        t = scores.copy()
        sc = t["scored"]
        t.loc[sc, "score_stability"] = b.percentile(t.loc[sc, "close_pct_shrunk"], t.loc[sc, "industry_code"], True)
        caught["안정성 방향 뒤집기"] = bool(problems_direction(t)[0])
        t = scores.copy()
        t.loc[sc, "score_competition"] = b.percentile(t.loc[sc, "competition"], t.loc[sc, "industry_code"], True)
        caught["경쟁 방향 뒤집기"] = bool(problems_direction(t)[0])
        t = scores.copy()
        t.loc[sc, "pct_worker"] = b.percentile(t.loc[sc, "worker_density"], t.loc[sc, "industry_code"], False)
        t.loc[sc, "score_demand"] = t.loc[sc, ["pct_floating", "pct_worker", "pct_resident"]].mean(axis=1, skipna=False)
        caught["수요 구성(직장) 방향 뒤집기"] = bool(problems_direction(t)[0])
        t = scores.copy()
        miss = t["scored"] & t["score_sales"].isna()
        t.loc[miss, "score_total"] = (t.loc[miss, AREA_COLS].fillna(0) * pd.Series({f"score_{k}": w[k] for k in b.AREA_KEYS})).sum(axis=1) / 100
        caught["결측 영역을 0점으로 넣어 종합 계산"] = bool(problems_weights(t)[0])
        t = scores.copy()
        i = t.index[t["status"].eq(b.STATUS_THIN)][0]
        t.loc[i, "score_stability"] = 40.0
        caught["비교 상권 부족 업종에 점수 넣기"] = bool(problems_thin(t, availability))
        t = scores.copy()
        t.loc[t.index[sc][0], "score_demand"] = 100.5
        caught["점수 100 초과"] = bool(problems_range(t))
        record(10, "변조 시험", [k for k, ok in caught.items() if not ok], f"{sum(caught.values())}/{len(caught)}개 변조 모두 검출: " + ", ".join(f"{k} {'검출' if ok else '놓침'}" for k, ok in caught.items()))

        if not skip_app:
            # 11
            pr = subprocess.run([sys.executable, "-m", "marimo", "check", str(HERE / "app.py")], cwd=ROOT, capture_output=True, text=True)
            msg = (pr.stdout + pr.stderr).strip()
            record(11, "marimo check", [msg or f"종료 코드 {pr.returncode}"] if pr.returncode or msg else [], f"종료 코드 {pr.returncode}, 경고·오류 출력 {len(msg.splitlines()) if msg else 0}줄")

            # 12
            REPORT.parent.mkdir(exist_ok=True)
            code, msg = export_html(REPORT, [])
            info = inspect_export(REPORT, 1)
            p = ([f"종료 코드 {code}: {msg[-300:]}"] if code else []) + info["errors"]
            if info["tab_rendered"] < info["tab_cells"]:
                p.append(f"첫 탭 셀 {info['tab_cells']}개 중 {info['tab_rendered']}개만 내용이 있음")
            record(12, "정적 HTML 내보내기", p, f"{REPORT.name} {REPORT.stat().st_size / 1e6:.1f} MB, 셀 {info['cells']}개, 오류 {len(info['errors'])}건, "
                   f"첫 탭 셀 {info['tab_rendered']}/{info['tab_cells']}개 출력, ancestor-stopped {info['ancestor_stopped']}건")

            # 13
            no_sales = availability.loc[availability["점수 생성"].eq("예") & availability["매출 제공"].eq("아니오"), "업종명"].sort_values().iloc[0]
            not_scored = availability.loc[availability["점수 생성"].eq("아니오"), "업종명"].sort_values().iloc[0]
            short = availability.loc[availability["점수 생성"].eq("예") & availability["매출 제공"].eq("예") & availability["매출 잠재력 점수"].eq("아니오"), "업종명"].sort_values().iloc[0]
            empty_name, gu, kind = empty_filter(bundle)
            scenarios = {
                "기본 (커피-음료)": [],
                f"매출 미제공 업종 ({no_sales})": ["--industry", no_sales],
                f"점수 생성 불가 업종 ({not_scored})": ["--industry", not_scored],
                f"매출 비교 상권 부족 업종 ({short})": ["--industry", short],
                f"필터 결과 0건 ({empty_name} · {gu} × {kind})": ["--industry", empty_name, "--gu", gu, "--type", kind],
                "가중치 모두 0": ["--weights", "0,0,0,0"],
            }
            p, lines = [], []
            for si, (label, args) in enumerate(scenarios.items()):
                res = []
                for tab in range(1, 5):
                    out = CHECK / f"s{si}_tab{tab}.html"
                    code, msg = export_html(out, [*args, "--tab", str(tab)])
                    info = inspect_export(out, tab)
                    if code:
                        p.append(f"{label} 탭{tab} 종료 코드 {code}")
                    p += [f"{label} 탭{tab} {e}" for e in info["errors"]]
                    if info["tab_rendered"] == 0:
                        p.append(f"{label} 탭{tab} 내용이 그려진 셀 없음")
                    res.append(f"탭{tab} {info['tab_rendered']}/{info['tab_cells']}")
                lines.append(f"{label}: " + " ".join(res))
                print("    ", lines[-1], flush=True)
            record(13, "화면 경계 상황 6가지 × 4개 탭 내보내기", p, f"{len(scenarios) * 4}회 내보내기, 셀 오류 {len(p)}건 (ancestor-stopped 제외). 탭별 '출력 있는 셀/탭 셀': " + " | ".join(lines))

        # 1 (마지막에: 위 실행 전후 지문 비교)
        after = shared_fingerprints()
        p = [f"{k} 지문이 바뀜" for k in before if before[k] != after[k]]
        p += [f"build 기록과 다름: {k}" for k, h in bundle.meta["input_sha256"].items() if after.get(k) != h]
        outside = git_outside_changes()
        p += [f"작업 폴더 밖 변경: {x}" for x in outside]
        record(1, "입력 지문 · 작업 폴더 밖 변경 없음", p, f"입력 {len(before)}개 파일 sha256 실행 전후 동일 (build 기록 {len(bundle.meta['input_sha256'])}개와도 동일), "
               f"git status 작업 폴더 밖 변경 {len(outside)}건")
    finally:
        shutil.rmtree(CHECK, ignore_errors=True)

    print("\n요약")
    for no, name, ok, _ in sorted(RESULTS):
        print(f"  {no:>2}. {'통과' if ok else '실패'}  {name}")
    return 0 if all(ok for *_, ok, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main(skip_app="--skip-app" in sys.argv))
