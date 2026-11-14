"""STEP 5 금융 MBTI 검증 13개. 각 검사의 숫자 근거를 출력하고, 하나라도 실패하면 종료 코드 1.

실행 (저장소 루트에서, 약 4~5분)
  uv run --project "김지영/step4_dashboard" python "김지영/step5_design/test_step5.py"
  ... test_step5.py --skip-app    # 13 (대시보드 내보내기) 건너뛰기

임시 결과(두 번 실행 비교, 화면 내보내기)는 이 폴더 안 .check/ 에 만들고 끝나면 지운다.
채점·유형 맞추기 함수(mbti.py)와 화면 내보내기 도구(test_step4.py)는 김지영/step4_dashboard 에서 불러 쓴다.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # 작업 폴더에 __pycache__ 를 남기지 않는다

import itertools
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import build_types as b

DASH = b.HERE.parent / "step4_dashboard"
sys.path.insert(0, str(DASH))  # 대시보드 폴더의 mbti.py · views.py · test_step4.py
import mbti  # noqa: E402
import test_step4 as t4  # noqa: E402
import views as v  # noqa: E402

HERE, ROOT = b.HERE, b.ROOT
CHECK = HERE / ".check"
WORK_DIRS = [HERE, DASH]
FORBIDDEN = ["추천 1위", "유망 상권", "창업 성공 가능성"]
EPS = 1e-9
RESULTS: list[tuple[int, str, bool, str]] = []


def record(no: int, name: str, problems: list[str], evidence: str) -> None:
    ok = not problems
    RESULTS.append((no, name, ok, evidence if ok else f"{evidence} | 문제: {'; '.join(problems[:5])}"))
    print(f"[{'통과' if ok else '실패'}] {no:>2}. {name}: {RESULTS[-1][3]}", flush=True)


# ---------------------------------------------------------------- 따로 다시 계산 (build_types.py 를 쓰지 않는다)


def hand_pct(values: pd.Series) -> pd.Series:
    """평균 순위 백분위를 직접 센다: (나보다 작은 수 + (나와 같은 수 + 1) / 2) ÷ 개수 × 100. 결측은 결측."""
    x = values.dropna()
    s = np.sort(x.to_numpy())
    less = np.searchsorted(s, x.to_numpy(), side="left")
    same = np.searchsorted(s, x.to_numpy(), side="right") - less
    return pd.Series((less + (same + 1) / 2) / len(s) * 100, index=x.index).reindex(values.index)


def reference_types() -> pd.DataFrame:
    """원자료에서 L/V · E/P 점수와 글자를 처음부터 다시 계산한다."""
    dim = pd.read_csv(b.INPUTS["dim"], dtype={"trdar_code": str})
    keep = dim.loc[~dim["is_tourist"], "trdar_code"]
    ctx = pd.read_csv(b.INPUTS["context"], dtype={"trdar_code": str, "quarter": str})
    ctx = ctx.loc[ctx["trdar_code"].isin(keep)]
    a = pd.DataFrame(index=pd.Index(sorted(keep), name="trdar_code"))
    a["floating"] = ctx.groupby("trdar_code")["floating_population"].mean()
    a["worker"] = ctx.groupby("trdar_code")["worker_population"].max()
    a["resident"] = ctx.groupby("trdar_code")["resident_population"].max()
    with np.errstate(divide="ignore", invalid="ignore"):
        r1, r2 = a["worker"] / a["resident"], a["floating"] / a["resident"]
    ok = r1.notna() & r2.notna()
    a["lv_score"] = (hand_pct(r1.where(ok)) + hand_pct(r2.where(ok))) / 2
    med = np.median(a["lv_score"].dropna())
    a["lv"] = np.where(a["lv_score"].isna(), None, np.where(a["lv_score"] > med, "V", "L"))

    fact = pd.read_csv(b.INPUTS["fact"], dtype={"trdar_code": str, "industry_code": str, "quarter": str},
                       usecols=["trdar_code", "industry_code", "sales_supported_industry", "sales_amount", "sales_count"])
    f = fact.loc[fact["trdar_code"].isin(keep) & fact["sales_supported_industry"]]
    g = f.groupby(["trdar_code", "industry_code"]).agg(amt=("sales_amount", "sum"), cnt=("sales_count", "sum"), nq=("sales_amount", "count"))
    g = g.loc[(g["nq"] == 4) & (g["cnt"] > 0)].reset_index()
    g["apt"] = g["amt"] / g["cnt"]
    g["pct"] = pd.concat([hand_pct(x["apt"]) for _, x in g.groupby("industry_code")])
    w = g.assign(wp=g["pct"] * g["cnt"]).groupby("trdar_code")[["wp", "cnt"]].sum()
    a["ep_score"] = w["wp"] / w["cnt"]
    med = np.median(a["ep_score"].dropna())
    a["ep"] = np.where(a["ep_score"].isna(), None, np.where(a["ep_score"] > med, "P", "E"))
    a.attrs["cells"] = g
    return a


def question_groups(q: pd.DataFrame) -> list[list[dict]]:
    """기준(주요 고객 → 소비 성향 → 상권 변화)별 문항. 손계산에서 쓴다."""
    return [q.loc[q["기준"].eq(axis)].to_dict("records") for axis in ["주요 고객", "소비 성향", "상권 변화"]]


def hand_score(answers: dict[int, str], groups: list[list[dict]]) -> tuple[str | None, list[bool]]:
    """채점 손계산: 기준마다 고른 글자를 세어 많은 쪽, 4개 이상이면 뚜렷."""
    letters, clear = "", []
    for rows in groups:
        if not all(int(r["번호"]) in answers for r in rows):
            return None, []
        got = [r[f"{answers[int(r['번호'])]} 글자"] for r in rows]
        top = max(set(got), key=got.count)
        letters += top
        clear.append(got.count(top) >= 4)
    return letters, clear


# ---------------------------------------------------------------- 검사 (변조 시험에서 다시 쓴다). 문제 목록을 돌려준다.


def problems_counts(types: pd.DataFrame, dim: pd.DataFrame, area_codes: set[str]) -> list[str]:
    out = []
    tourist = set(dim.loc[dim["is_tourist"], "trdar_code"])
    if types["trdar_code"].isin(tourist).any():
        out.append(f"관광특구 행 {int(types['trdar_code'].isin(tourist).sum())}건")
    if types["trdar_code"].duplicated().any():
        out.append("상권 코드 중복")
    if set(types["trdar_code"]) != area_codes:
        out.append(f"상권 목록이 지도 상권({len(area_codes)}곳)과 다름")
    for col, letters in [("lv", "LV"), ("ep", "EP")]:
        bad = types[col].notna() & ~types[col].isin(list(letters))
        if bad.any():
            out.append(f"{col}에 다른 글자 {int(bad.sum())}건")
    both = types["lv"].notna() & types["ep"].notna()
    if not (types.loc[both, "type2"] == types.loc[both, "lv"] + types.loc[both, "ep"]).all() or types.loc[~both, "type2"].notna().any():
        out.append("type2가 두 글자를 이은 값과 다름")
    return out


def problems_letters(types: pd.DataFrame, ref: pd.DataFrame) -> tuple[list[str], dict]:
    t = types.set_index("trdar_code").reindex(ref.index)
    out, info = [], {}
    for col, score in [("lv", "lv_score"), ("ep", "ep_score")]:
        gap = (t[score] - ref[score]).abs()
        miss = t[score].isna() != ref[score].isna()
        diff = (t[col].fillna("-") != pd.Series(ref[col], index=ref.index).fillna("-"))
        info[col] = {"max_gap": float(gap.max()), "letter_diff": int(diff.sum()), "missing_diff": int(miss.sum())}
        if gap.max() > 1e-9 or miss.any():
            out.append(f"{score} 손계산과 다름 (최대 {gap.max():.3g}, 결측 위치 {int(miss.sum())}건)")
        if diff.any():
            out.append(f"{col} 글자가 손계산과 다른 상권 {int(diff.sum())}곳")
    return out, info


def problems_split(types: pd.DataFrame) -> list[str]:
    """글자는 점수의 서울 중앙값으로만 나뉜다: 중앙값보다 크면 V·P, 같거나 작으면 L·E."""
    out = []
    for col, score, hi in [("lv", "lv_score", "V"), ("ep", "ep_score", "P")]:
        s = types[score]
        med = float(np.median(s.dropna()))
        low = {"lv": "L", "ep": "E"}[col]
        expect = pd.Series(np.where(s > med, hi, low), index=types.index).where(s.notna())
        bad = expect.fillna("-") != types[col].fillna("-")
        if bad.any():
            out.append(f"{col} 글자가 중앙값({med:.3f}) 기준과 다른 상권 {int(bad.sum())}곳")
    return out


def dominance(types: pd.DataFrame) -> int:
    """L/V: 두 비율이 모두 같거나 큰 상권의 L/V 점수가 더 낮은 쌍의 수."""
    d = types.dropna(subset=["lv_score"])
    a = d[["worker_ratio", "floating_ratio"]].to_numpy()
    s = d["lv_score"].to_numpy()
    ge = (a[:, None, :] >= a[None, :, :]).all(axis=2)
    return int(np.sum(ge & (s[:, None] < s[None, :] - EPS)))


def problems_not_made(types: pd.DataFrame, texts: dict[str, str]) -> tuple[list[str], dict]:
    out = []
    if types["sg"].notna().any():
        out.append(f"상권 S/G가 들어간 행 {int(types['sg'].notna().sum())}건")
    extra = [c for c in types.columns if re.search(r"budget|rent|consum|potential|growth|예산|임대|잠재|성장", c, re.I)]
    if extra:
        out.append(f"만들지 않기로 한 값의 열: {extra}")
    hits = {f"{name}: {w}": text.count(w) for name, text in texts.items() for w in FORBIDDEN if w in text}
    out += [f"금지 표현 {k} {n}회" for k, n in hits.items()]
    app = texts["app.py"]
    for must in ["예산 적합성은 판단하지 않습니다", "성장성은 산출하지 않습니다", "소비 잠재력", "상권의 S/G는 판정하지 않아"]:
        if must not in app:
            out.append(f"화면에 '{must}' 안내가 없음")
    return out, {"forbidden_hits": len(hits)}


def all_answers(q: pd.DataFrame):
    numbers = sorted(int(n) for n in q["번호"])
    for combo in itertools.product("AB", repeat=len(numbers)):
        yield dict(zip(numbers, combo))


def problems_survey(score_fn, q: pd.DataFrame, axes: list[dict]) -> tuple[list[str], dict]:
    """2^15 = 32,768가지 답을 모두 넣어 채점을 손계산과 비교하고, 빈 답이 있으면 유형이 없어야 한다."""
    out, n, clear_count = [], 0, {True: 0, False: 0}
    groups = question_groups(q)
    for ans in all_answers(q):
        r = score_fn(ans, q, axes)
        hand, clear = hand_score(ans, groups)
        n += 1
        if r["type"] != hand or [a["clear"] for a in r["axes"]] != clear or [a["boundary"] for a in r["axes"]] != [not c for c in clear]:
            out.append(f"{''.join(ans.values())}: {r['type']} vs 손계산 {hand}")
            if len(out) > 5:
                break
        clear_count[all(clear)] += 1
    rng = np.random.default_rng(15)
    partial = 0
    numbers = sorted(int(x) for x in q["번호"])
    for _ in range(500):
        ans = {no: str(rng.choice(["A", "B"])) for no in numbers}
        for k in rng.choice(numbers, size=int(rng.integers(1, 16)), replace=False):
            ans.pop(int(k))
        r = score_fn(ans, q, axes)
        partial += 1
        if r["complete"] or r["type"] is not None or r["answered"] != len(ans):
            out.append(f"답 {len(ans)}개인데 유형 {r['type']}")
            break
    return out, {"combos": n, "all_clear": clear_count[True], "some_boundary": clear_count[False], "partial": partial}


def expected_matched(code: str, boundary: list[bool]) -> dict[str, str]:
    pairs = [("L", "V"), ("E", "P")]
    out = {code[:2]: mbti.MATCH}
    for i in (0, 1):
        if boundary[i]:
            flip = pairs[i][1] if code[i] == pairs[i][0] else pairs[i][0]
            out[code[:i] + flip + code[i + 1:2]] = mbti.NEAR
    return out


def problems_matching(matched_fn, weights_fn, sg: pd.DataFrame, axes: list[dict]) -> tuple[list[str], dict]:
    """8유형 × 경계 조합 8가지: 경계 글자는 한 글자씩만 바꾸고, S/G 경계는 상권을 늘리지 않으며, 가중치는 S/G 글자로만 정해진다."""
    out, n = [], 0
    rows = sg.set_index("구분")
    for code, (b1, b2, b3) in itertools.product([t[0] for t in b.TYPES], itertools.product([False, True], repeat=3)):
        res = mbti.direct_result(code, axes)
        for a, flag in zip(res["axes"], (b1, b2, b3)):
            a["boundary"], a["clear"] = flag, not flag
        n += 1
        got = matched_fn(res)
        want = expected_matched(code, [b1, b2])
        if got != want:
            out.append(f"{code} 경계 {b1, b2, b3}: {got} vs {want}")
        w, _ = weights_fn(res, sg)
        key = "경계" if b3 else code[2]
        want_w = {mbti.WEIGHT_KEYS[k]: float(rows.at[key, k]) for k in mbti.WEIGHT_KEYS}
        if w != want_w:
            out.append(f"{code} 경계 {b1, b2, b3}: 가중치 {w} vs {want_w}")
    if rows.loc["경계", list(mbti.WEIGHT_KEYS)].tolist() != [v.DEFAULT_WEIGHTS[k] for k in v.AREA_KEYS]:
        out.append("S/G 경계 가중치가 STEP 4 기본값과 다름")
    for key in ["S", "G", "경계"]:
        if rows.loc[key, list(mbti.WEIGHT_KEYS)].sum() != 100:
            out.append(f"{key} 가중치 합이 100이 아님")
    return out, {"cases": n}


def problems_double_count(weights_fn, q: pd.DataFrame, axes: list[dict], sg: pd.DataFrame) -> tuple[list[str], int]:
    """위험 감수 성향(S/G)을 두 번 반영하지 않는다: 가중치는 S/G 다섯 문항의 답으로만 정해져야 한다."""
    out, groups = [], {}
    sg_numbers = [int(n) for n in q.loc[q["기준"].eq("상권 변화"), "번호"]]
    for ans in all_answers(q):
        r = mbti.score_answers(ans, q, axes)
        w, _ = weights_fn(r, sg)
        key = tuple(ans[n] for n in sg_numbers)
        if groups.setdefault(key, w) != w:
            out.append(f"S/G 답이 같은데 가중치가 다름: {key}")
            break
    return out, len(groups)


def survey_string(letters: dict[str, tuple[str, int]], q: pd.DataFrame) -> str:
    """기준별 (글자, 그 글자를 고른 수)로 --answers 문자열을 만든다. 예: {'주요 고객': ('V', 4), ...}"""
    out = {}
    for axis, (letter, n) in letters.items():
        rows = q.loc[q["기준"].eq(axis)].sort_values("번호").to_dict("records")
        for i, r in enumerate(rows):
            want = letter if i < n else (r["A 글자"] if r["B 글자"] == letter else r["B 글자"])
            out[int(r["번호"])] = "A" if r["A 글자"] == want else "B"
    return "".join(out[k] for k in sorted(out))


# ---------------------------------------------------------------- 실행


def texts() -> dict[str, str]:
    names = {"app.py": DASH / "app.py", "views.py": DASH / "views.py", "mbti.py": DASH / "mbti.py",
             "설계 문서": HERE / "STEP5_금융MBTI_설계.md", "README": HERE / "README.md"}
    out = {k: p.read_text(encoding="utf-8") for k, p in names.items() if p.exists()}
    for p in sorted((HERE / "data").glob("*.csv")):
        out[p.name] = p.read_text(encoding="utf-8-sig")
    return out


def main(skip_app: bool) -> int:
    before = b.fingerprints()
    if CHECK.exists():
        shutil.rmtree(CHECK)
    CHECK.mkdir()
    try:
        bundle = v.load_bundle()
        types, q, axes, sg = bundle.area_types, bundle.questions, bundle.meta5["axes"], bundle.sg_weights
        dim = pd.read_csv(b.INPUTS["dim"], dtype={"trdar_code": str})
        area_codes = set(bundle.areas["trdar_code"])

        # 2 원문 일치
        p = []
        doc = b.MBTI_DOC
        if doc.exists():
            dq, dt = b.parse_doc(doc.read_text(encoding="utf-8"))
            if dq != b.QUESTIONS:
                p.append("원문 문항과 옮겨 적은 문항이 다름")
            if dt != b.TYPES:
                p.append("원문 유형과 옮겨 적은 유형이 다름")
        else:
            p.append(f"원문 {doc.relative_to(ROOT)} 없음")
        csv_q = [tuple(r) for r in q[["번호", "기준", "질문", "A", "A 글자", "B", "B 글자"]].itertuples(index=False)]
        if csv_q != [tuple(x) for x in b.QUESTIONS]:
            p.append("검사_문항.csv가 원문과 다름")
        if sorted(q["화면 순서"]) != list(range(1, 16)) or (q.sort_values("화면 순서")["번호"].tolist() == sorted(q["번호"])):
            p.append("화면 순서가 1~15를 한 번씩 쓰지 않거나 섞이지 않음")
        for ax in axes:
            rows = q.loc[q["기준"].eq(ax["기준"])]
            if len(rows) != 5 or not all({a, c} == {ax["왼쪽"], ax["오른쪽"]} for a, c in zip(rows["A 글자"], rows["B 글자"])):
                p.append(f"{ax['기준']} 문항이 5개가 아니거나 두 글자가 아님")
        codes = {a + e + s for a in "LV" for e in "EP" for s in "SG"}
        if set(bundle.type_table["유형"]) != codes or len(bundle.type_table) != 8:
            p.append("유형표가 8가지 조합이 아님")
        record(2, "유형표 원문과 옮겨 적은 문항 · 유형 일치", p,
               f"원문 sha256 {b.sha256(doc)[:12] if doc.exists() else '-'}; 문항 {len(q)}개(기준마다 5개, A·B는 그 기준의 두 글자) · 유형 {len(bundle.type_table)}개가 원문과 글자까지 같음; "
               f"화면 순서 {q.sort_values('화면 순서')['번호'].tolist()}")

        # 3 채점 전수 검사
        p, info = problems_survey(mbti.score_answers, q, axes)
        example = survey_string({"주요 고객": ("V", 4), "소비 성향": ("P", 3), "상권 변화": ("G", 5)}, q)
        r = mbti.score_answers(mbti.parse_answers(example, q), q, axes)
        if (r["type"], mbti.axis_text(r), mbti.matched_types(r)) != ("VPG", "V 4:1 · P 3:2 (경계) · G 5:0", {"VP": mbti.MATCH, "VE": mbti.NEAR}):
            p.append(f"유형표 결과 예시와 다름: {r['type']} {mbti.axis_text(r)} {mbti.matched_types(r)}")
        record(3, "검사 채점 (모든 답 조합)", p,
               f"{info['combos']:,}가지 답 모두 손계산과 같음 (세 글자 모두 뚜렷 {info['all_clear']:,} · 경계 글자 있음 {info['some_boundary']:,}); "
               f"빈 답 {info['partial']}가지는 모두 유형 없음; 유형표 예시 {example} → {r['type']} {mbti.axis_text(r)} → {mbti.matched_text(mbti.matched_types(r))}")

        # 4 경계 유형 · 가중치
        p, info = problems_matching(mbti.matched_types, mbti.sg_weights, sg, axes)
        record(4, "경계 유형 규칙 · S/G 가중치", p,
               f"8유형 × 경계 조합 8가지 = {info['cases']}가지 모두 기대값과 같음 (경계 글자는 한 글자씩만 바꿈, S/G 경계는 상권을 늘리지 않음); "
               f"S {sg.set_index('구분').loc['S', list(mbti.WEIGHT_KEYS)].tolist()} · G {sg.set_index('구분').loc['G', list(mbti.WEIGHT_KEYS)].tolist()} · "
               f"경계 {sg.set_index('구분').loc['경계', list(mbti.WEIGHT_KEYS)].tolist()} (= STEP 4 기본값), 합 100")

        # 5 이중 반영 없음
        p, n_groups = problems_double_count(mbti.sg_weights, q, axes, sg)
        if re.search(r"label=[\"'][^\"']*위험", (DASH / "app.py").read_text(encoding="utf-8")):
            p.append("화면에 위험 감수 성향 입력이 따로 있음")
        record(5, "위험 감수 성향 이중 반영 없음", p,
               f"32,768가지 답에서 가중치는 S/G 다섯 문항의 답({n_groups}가지)으로만 정해짐 (L/V · E/P 답을 바꿔도 가중치 같음); 위험 감수 성향 입력칸 없음")

        # 6 상권 수
        p = problems_counts(types, dim, area_codes)
        c = bundle.meta5["counts"]
        for key, letters in [("lv", "LV"), ("ep", "EP")]:
            if sum(c[key].values()) != len(types):
                p.append(f"{key} 개수 합이 {len(types)}과 다름")
        if sum(c["type2"].values()) != len(types):
            p.append("두 글자 유형 개수 합이 다름")
        record(6, "상권 수 · 관광특구 제외", p,
               f"관광특구 {int(dim['is_tourist'].sum())}곳 제외 {len(types):,}곳 = 지도 상권 {len(area_codes):,}곳; "
               f"L {c['lv']['L']} + V {c['lv']['V']} + 판정 불가 {c['lv']['판정 불가']} = {sum(c['lv'].values())}; "
               f"E {c['ep']['E']} + P {c['ep']['P']} + 판정 불가 {c['ep']['판정 불가']} = {sum(c['ep'].values())}; "
               f"LE {c['type2']['LE']} · LP {c['type2']['LP']} · VE {c['type2']['VE']} · VP {c['type2']['VP']} · 판정 불가 {c['type2']['판정 불가']}")

        # 7·8 손계산
        ref = reference_types()
        p, info = problems_letters(types, ref)
        lv_p = [x for x in p if x.startswith(("lv", "lv_score"))]
        ep_p = [x for x in p if x.startswith(("ep", "ep_score"))]
        tt = types.set_index("trdar_code")
        ex_v = tt.loc[tt["lv"].eq("V")].sort_values("lv_score").iloc[-1]
        ex_l = tt.loc[tt["lv"].eq("L")].sort_values("lv_score").iloc[0]
        record(7, "L/V 손계산 (원자료부터 다시)", lv_p,
               f"{int(types['lv_score'].notna().sum()):,}곳 L/V 점수 최대 차이 {info['lv']['max_gap']:.1e}, 글자 다른 상권 {info['lv']['letter_diff']}곳; "
               f"예: [{ex_v['trdar_name']}] 직장/상주 {ex_v['worker_ratio']:.2f} · 유동/상주 {ex_v['floating_ratio']:.1f} → {ex_v['lv_score']:.2f}점 V, "
               f"[{ex_l['trdar_name']}] 직장/상주 {ex_l['worker_ratio']:.3f} · 유동/상주 {ex_l['floating_ratio']:.2f} → {ex_l['lv_score']:.2f}점 L "
               f"(중앙값 {bundle.meta5['medians']['lv_score']:.2f})")
        cells = ref.attrs["cells"]
        ex = tt.loc[tt["ep"].notna()].sort_values("ep_cells").iloc[len(tt.loc[tt["ep"].notna()]) // 2]
        mine = cells.loc[cells["trdar_code"].eq(ex.name)]
        hand = float((mine["pct"] * mine["cnt"]).sum() / mine["cnt"].sum())
        if abs(hand - ex["ep_score"]) > 1e-9:
            ep_p.append("손계산 예시 불일치")
        record(8, "E/P 손계산 (원자료부터 다시)", ep_p,
               f"{int(types['ep_score'].notna().sum()):,}곳 E/P 점수 최대 차이 {info['ep']['max_gap']:.1e}, 글자 다른 상권 {info['ep']['letter_diff']}곳 (객단가 칸 {len(cells):,}개); "
               f"예: [{ex['trdar_name']}] 업종 {len(mine)}개의 객단가 업종 내 백분위를 매출 건수로 가중 평균 = {hand:.4f} (표 {ex['ep_score']:.4f}) → {ex['ep']}")

        # 9 방향
        p = problems_split(types)
        dom = dominance(types)
        if dom:
            p.append(f"L/V 지배 관계 위반 {dom}쌍")
        tt2 = types.dropna(subset=["type2"])
        record(9, "방향 · 중앙값 나누기", p,
               f"글자는 점수의 서울 중앙값으로만 나뉨 (L/V {bundle.meta5['medians']['lv_score']:.2f} · E/P {bundle.meta5['medians']['ep_score']:.2f}, 어긋난 상권 0곳); "
               f"두 비율이 모두 크거나 같은데 L/V 점수가 낮은 쌍 {dom}쌍; 발달상권 중 V {int(tt2.loc[tt2['trdar_type'].eq('발달상권'), 'lv'].eq('V').sum())}/"
               f"{int(tt2['trdar_type'].eq('발달상권').sum())}곳")

        # 10 만들지 않은 것 · 표현
        txt = texts()
        p, info = problems_not_made(types, txt)
        record(10, "S/G · 소비 잠재력 · 예산을 만들지 않음, 금지 표현 없음", p,
               f"상권 S/G 값 {int(types['sg'].notna().sum())}건, 예산·임대료·잠재력·성장 열 0개; 금지 표현({', '.join(FORBIDDEN)}) {len(txt)}개 파일에서 0회; "
               "화면 안내 4가지(예산·성장성·소비 잠재력·상권 S/G) 있음")

        # 11 두 번 실행
        p = []
        runs = [b.main(CHECK / "run1"), b.main(CHECK / "run2")]
        for x, y in zip(*runs):
            if x.read_bytes() != y.read_bytes():
                p.append(f"{x.name} 두 실행 결과가 다름")
            if x.read_bytes() != (b.OUT / x.name).read_bytes():
                p.append(f"{x.name} 저장된 결과와 다름")
        record(11, "두 번 실행 바이트 동일", p, f"{len(runs[0])}개 파일 × 2회 실행, 저장된 data/ 파일과도 비교: " +
               ", ".join(f"{x.name} {b.sha256(x)[:10]}" for x in runs[0]))

        # 12 변조 시험
        caught = {}
        m = types.copy()
        m.loc[len(m)] = m.iloc[0]
        m.loc[len(m) - 1, "trdar_code"] = sorted(dim.loc[dim["is_tourist"], "trdar_code"])[0]
        caught["관광특구 1곳 섞기"] = bool(problems_counts(m, dim, area_codes))
        m = types.copy()
        m["lv_score"] = 100 - m["lv_score"] + 100 / m["lv_score"].notna().sum()
        m["lv"] = np.where(m["lv_score"].isna(), None, np.where(m["lv_score"] > m["lv_score"].median(), "V", "L"))
        caught["L/V 방향 뒤집기 (상주 많을수록 V)"] = bool(problems_letters(m, ref)[0])
        m = types.copy()
        m["ep"] = np.where(m["ep_score"].isna(), None, np.where(m["ep_score"] > m["ep_score"].mean(), "P", "E"))
        caught["중앙값 대신 평균으로 나누기"] = bool(problems_split(m)) or bool(problems_letters(m, ref)[0])
        m = types.copy()
        raw = cells.assign(pct=hand_pct(cells["apt"]))  # 업종을 무시하고 서울 전체 객단가로 순위
        w = raw.assign(wp=raw["pct"] * raw["cnt"]).groupby("trdar_code")[["wp", "cnt"]].sum()
        m["ep_score"] = m["trdar_code"].map(w["wp"] / w["cnt"])
        caught["E/P를 업종 구분 없이 계산"] = bool(problems_letters(m, ref)[0])
        m = types.copy()
        m.loc[m.index[0], "sg"] = "G"
        caught["상권에 S/G 글자 넣기"] = bool(problems_not_made(m, txt)[0])
        m_txt = dict(txt) | {"app.py": txt["app.py"] + "\n추천 1위 상권"}
        caught["화면에 '추천 1위' 쓰기"] = bool(problems_not_made(types, m_txt)[0])

        def wrong_score(ans, qq, aa):  # 4개 이상이어야 글자를 주는 잘못된 채점
            r = mbti.score_answers(ans, qq, aa)
            for a in r["axes"]:
                if a["letter"] and a["boundary"]:
                    a["letter"] = a["right"] if a["letter"] == a["left"] else a["left"]
            r["type"] = "".join(a["letter"] for a in r["axes"]) if r["complete"] else None
            return r
        caught["3:2 경계에서 반대 글자 주기"] = bool(problems_survey(wrong_score, q, axes)[0])

        def double_flip(res):  # 두 글자가 모두 경계면 대각선 유형까지 넣는 잘못된 규칙
            out = mbti.matched_types(res)
            if res["axes"][0]["boundary"] and res["axes"][1]["boundary"]:
                code = res["type"]
                out[("V" if code[0] == "L" else "L") + ("P" if code[1] == "E" else "E")] = mbti.NEAR
            return out
        caught["경계 두 글자를 한꺼번에 바꾸기"] = bool(problems_matching(double_flip, mbti.sg_weights, sg, axes)[0])

        def lv_weights(res, table):  # L/V 글자까지 가중치에 쓰는 잘못된 규칙 (성향 이중 반영)
            w, label = mbti.sg_weights(res, table)
            if res["axes"][0]["letter"] == "V":
                w = dict(w) | {"demand": w["demand"] + 5}
            return w, label
        caught["S/G 말고 다른 글자도 가중치에 쓰기"] = bool(problems_double_count(lv_weights, q, axes, sg)[0])
        record(12, "변조 시험", [k for k, ok in caught.items() if not ok],
               f"{sum(caught.values())}/{len(caught)}개 변조 모두 검출: " + ", ".join(f"{k} {'검출' if ok else '놓침'}" for k, ok in caught.items()))

        if not skip_app:
            # 13 대시보드 연결
            p, lines = [], []
            coffee = bundle.availability.set_index("업종명").at["커피-음료", "업종코드"]
            for code in ["VPG", "LES"]:
                prof = mbti.make_profile(mbti.MODE_DIRECT, None, code, axes, bundle.type_table, sg)
                rows = v.with_match(v.industry_rows(bundle, coffee, prof["weights"]), prof["matched"])
                kept = v.filter_rows(rows, None, None, list(prof["matched"]))
                s = rows.loc[rows["scored"]]
                expect = s.apply(t4.independent_total, axis=1, weights=prof["weights"])
                gap = float((expect - s["total"]).abs().max())
                if gap > 1e-9:
                    p.append(f"{code} 종합 점수 재계산 차이 {gap}")
                if set(kept["type2"]) - set(prof["matched"]) or len(kept) != int(rows["type2"].isin(list(prof["matched"])).sum()):
                    p.append(f"{code} 유형 필터가 맞지 않음")
                lines.append(f"{code}: 커피-음료 점수 행 {len(s):,}건 S/G 가중치 재계산 최대 차이 {gap:.1e}, 유형이 맞는 상권 {len(kept):,}곳만 남음")
            q_ = bundle.questions
            boundary2 = survey_string({"주요 고객": ("L", 3), "소비 성향": ("E", 3), "상권 변화": ("S", 3)}, q_)
            # 자치구 × 상권 유형 안에 상권은 있지만 LP 상권은 없는 조합 (모든 자치구에 LP 상권이 있어 자치구 하나로는 0곳이 안 된다)
            ar = bundle.areas
            empty_gu, empty_kind = next((g, k) for g in sorted(ar["gu_name"].unique()) for k in v.TYPES
                                        if (ar["gu_name"].eq(g) & ar["trdar_type"].eq(k)).any()
                                        and not (ar["gu_name"].eq(g) & ar["trdar_type"].eq(k) & ar["type2"].eq("LP")).any())
            scenarios = {
                "검사 완료 (유형표 예시 VPG, P 경계)": ["--answers", example],
                "검사 덜 함 (10문항)": ["--answers", example[:10]],
                "두 글자 경계 (L·E·S 모두 3:2)": ["--answers", boundary2],
                "직접 고르기 LES": ["--mbti", "LES"],
                "직접 고르기 VPG · 맞는 상권만 보기 끔": ["--mbti", "VPG", "--match", "0"],
                f"유형이 맞는 상권 0곳 (LPS · {empty_gu} × {empty_kind})": ["--mbti", "LPS", "--gu", empty_gu, "--type", empty_kind],
                "점수 불가 업종 + 유형 (DVD방 · VES)": ["--mbti", "VES", "--industry", "DVD방"],
            }
            for si, (label, args) in enumerate(scenarios.items()):
                res = []
                for tab in range(1, t4.TABS + 1):
                    out = CHECK / f"s{si}_tab{tab}.html"
                    code, msg = t4.export_html(out, [*args, "--tab", str(tab)])
                    info = t4.inspect_export(out, tab)
                    if code:
                        p.append(f"{label} 탭{tab} 종료 코드 {code}: {msg[-200:]}")
                    p += [f"{label} 탭{tab} {e}" for e in info["errors"]]
                    if info["tab_rendered"] == 0:
                        p.append(f"{label} 탭{tab} 내용이 그려진 셀 없음")
                    res.append(f"탭{tab} {info['tab_rendered']}/{info['tab_cells']}")
                lines.append(f"{label}: " + " ".join(res))
                print("    ", lines[-1], flush=True)
            record(13, f"대시보드 연결 · 경계 상황 {len(scenarios)}가지 × {t4.TABS}개 탭 내보내기", p,
                   f"{len(scenarios) * t4.TABS}회 내보내기 셀 오류 0건. " + " | ".join(lines))

        # 1 (마지막에: 실행 전후 지문 비교)
        after = b.fingerprints()
        p = [f"{k} 지문이 바뀜" for k in before if before[k] != after[k]]
        p += [f"build 기록과 다름: {k}" for k, h in bundle.meta5["input_sha256"].items() if after.get(k) != h]
        outside = t4.git_outside_changes(WORK_DIRS)
        p += [f"작업 폴더 밖 변경: {x}" for x in outside]
        record(1, "입력 지문 · 작업 폴더 밖 변경 없음", p,
               f"입력 {len(before)}개 파일(STEP 2·3 자료 3개 + 유형표 원문) sha256 실행 전후 동일, build 기록과도 동일; "
               f"git status 작업 폴더({', '.join(d.name for d in WORK_DIRS)}) 밖 변경 {len(outside)}건")
    finally:
        shutil.rmtree(CHECK, ignore_errors=True)

    print("\n요약")
    for no, name, ok, _ in sorted(RESULTS):
        print(f"  {no:>2}. {'통과' if ok else '실패'}  {name}")
    return 0 if all(ok for *_, ok, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main(skip_app="--skip-app" in sys.argv))
