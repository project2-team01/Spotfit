"""STEP 6 · 최종 산출물 대시보드 검증 14개.

실행 (팀 저장소 루트에서):
    uv run --project "김지영/step4_dashboard" python "김지영/step6_final/test_final.py"              # 약 1분
    uv run --project "김지영/step4_dashboard" python "김지영/step6_final/test_final.py" --skip-browser

- 화면 계산(web/core.js)은 node로 돌려 STEP 4 · 5 Python 함수(views.composite · order_rows, mbti.py)와 대조한다.
- 브라우저 확인은 Chrome headless로 HTML을 열어 콘솔 오류와 그려진 요소를 센다.
- node가 없으면 6~9번, Chrome이 없으면 13 · 14번을 '건너뜀'으로 표시한다(통과로 세지 않는다).
- 임시 파일은 김지영/step6_final/.check/test_run/ 에 만들고 끝나면 지운다(--keep 이면 남긴다).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ME = HERE.parent
ROOT = ME.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ME / "step4_dashboard"))
import build_final as B  # noqa: E402
import mbti  # noqa: E402
import views  # noqa: E402

WORK = HERE / ".check" / "test_run"
HTML = HERE / "report" / B.HTML_NAME
CORE = HERE / "web" / "core.js"
RESULTS: list[tuple[str, str, str]] = []
SKIP = "건너뜀"


def check(name):
    def deco(fn):
        def run(*args):
            try:
                msg = fn(*args) or ""
                status = SKIP if msg.startswith(SKIP) else "통과"
            except AssertionError as e:
                status, msg = "실패", str(e)
            except Exception as e:  # 검증 코드 자체의 오류도 실패로 센다
                status, msg = "실패", f"{type(e).__name__}: {e}"
            RESULTS.append((name, status, msg))
            print(f"[{status}] {name}" + (f" - {msg}" if msg else ""), flush=True)
        return run
    return deco


def payload_of(path: Path = HTML) -> dict:
    m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', path.read_text(encoding="utf-8"), re.S)
    assert m, "HTML에 payload가 없습니다"
    return json.loads(m.group(1).replace("<\\/", "</"))


def node() -> str | None:
    return shutil.which("node")


def chrome() -> str | None:
    cands = [os.environ.get("CHROME", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             shutil.which("google-chrome") or "", shutil.which("chromium") or "", shutil.which("chrome") or ""]
    return next((c for c in cands if c and Path(c).exists()), None)


def run_node(code: str, *args: str) -> object:
    out = subprocess.run([node(), "-e", code, "--", *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def file_url(path: Path, query: str = "", hash_: str = "") -> str:
    return path.resolve().as_uri() + query + hash_


def dump_dom(url: str) -> tuple[str, list[str]]:
    """Chrome headless로 열어 JS가 그린 뒤의 DOM과 콘솔 오류 줄을 돌려준다."""
    cmd = [chrome(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={WORK / 'profile'}",
           "--window-size=1440,1600", "--virtual-time-budget=8000", "--enable-logging=stderr", "--v=0", "--dump-dom", url]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    errors = [ln for ln in out.stderr.splitlines() if "CONSOLE" in ln and re.search(r"Uncaught|Error|error", ln)]
    return out.stdout, errors


WEIGHT_SETS = [dict(B.DEFAULT_WEIGHTS), {"sales": 20, "competition": 30, "stability": 30, "demand": 20},
               {"sales": 35, "competition": 15, "stability": 10, "demand": 40}, {"sales": 0, "competition": 0, "stability": 0, "demand": 0},
               {"sales": 0, "competition": 50, "stability": 0, "demand": 0}]


def payload_frame(P: dict, code: str) -> pd.DataFrame:
    s = P["scores"][code]
    return pd.DataFrame({
        "trdar_code": [P["areas"]["code"][i] for i in s["a"]], "scored": True, "stores": s["n"],
        "score_sales": pd.array(s["sa"], dtype="Float64").astype(float), "score_competition": pd.array(s["co"], dtype="Float64").astype(float),
        "score_stability": pd.array(s["st"], dtype="Float64").astype(float), "score_demand": pd.array(s["de"], dtype="Float64").astype(float),
    })


def python_order(frame: pd.DataFrame, weights: dict) -> pd.DataFrame:
    f = frame.copy()
    f["total"], f["used"] = views.composite(f, weights)
    return views.order_rows(f)


# ---------------------------------------------------------------- 1~4. 산출물


@check("1. 입력 지문: 산출물이 지금 입력 · 화면 원본으로 만든 것")
def t_fingerprint():
    meta = json.loads((HERE / "data" / B.META_NAME).read_text(encoding="utf-8"))
    now = B.fingerprints()
    diff = [k for k in now if meta["input_sha256"].get(k) != now[k]]
    assert not diff, f"다시 빌드가 필요합니다 (바뀐 입력: {diff[:3]})"
    return f"입력 {len(now)}개 sha256 일치"


@check("2. 재실행 동일: 두 번 만들어도, 저장된 산출물과도 바이트까지 같음")
def t_deterministic():
    a = B.main(WORK / "run1")
    b = B.main(WORK / "run2")
    for x, y in zip(a, b):
        assert x.read_bytes() == y.read_bytes(), f"두 번 실행 결과가 다름: {x.name}"
        saved = HERE / x.parent.name / x.name
        assert saved.read_bytes() == x.read_bytes(), f"저장된 산출물과 다름: {saved.name} (build_final.py를 다시 실행하세요)"
    return f"{len(a)}개 파일"


@check("3. 단일 파일: 외부 스크립트 · 스타일 · 요청 없이 열림")
def t_self_contained():
    html = HTML.read_text(encoding="utf-8")
    for pat in [r"<script[^>]+src=", r"<link[^>]+href=", r"@import", r"url\(\s*['\"]?https?:", r"XMLHttpRequest", r"\bimport\("]:
        assert not re.search(pat, html), f"외부 자원 참조: {pat}"
    # fetch는 payload가 비어 있을 때(claude.ai 게시본) 옆의 payload.json을 읽는 대체 경로에만 있다
    calls = re.findall(r"\bfetch\(([^)]*)\)", html)
    assert calls == ['"payload.json"'], f"payload.json 외의 fetch: {calls}"
    assert len(re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S).group(1)) > 1_000_000, "HTML 안에 데이터가 비어 있음"
    srcs = re.findall(r"\bsrc\s*=\s*[\"']https?:", html)
    assert not srcs, "src로 외부 주소를 부릅니다"
    mb = HTML.stat().st_size / 1e6
    assert mb < 10, f"파일이 큽니다: {mb:.1f}MB"
    return f"{mb:.2f}MB, 데이터 내장, 외부 링크는 데이터셋 출처 <a href>뿐"


@check("4. 개수: 상권 · 업종 · 점수 대상 · 점포 칸 · 유형 판정")
def t_counts():
    P = payload_of()
    s = pd.read_parquet(B.INPUTS["scores"])
    t = pd.read_parquet(B.INPUTS["types"])
    got = {"상권": len(P["areas"]["code"]), "업종": len(P["industries"]), "점수 업종": len(P["scores"]),
           "점수 칸": sum(len(v["a"]) for v in P["scores"].values()), "점포 칸": sum(len(v[0]) for v in P["cells"].values()),
           "유형 판정": sum(1 for v in P["areas"]["type2"] if v)}
    want = {"상권": s["trdar_code"].nunique(), "업종": s["industry_code"].nunique(), "점수 업종": s.loc[s["scored"], "industry_code"].nunique(),
            "점수 칸": int(s["scored"].sum()), "점포 칸": int(s["stores"].gt(0).sum()), "유형 판정": int(t["type2"].notna().sum())}
    assert got == want, f"{got} != {want}"
    assert want["점수 칸"] == 20522 and want["상권"] == 1644 and want["유형 판정"] == 1534, f"STEP 4 · 5 기준 개수와 다름: {want}"
    return " · ".join(f"{k} {v:,}" for k, v in got.items())


# ---------------------------------------------------------------- 5~9. 계산


@check("5. 값 보존: payload 점수 · 원값이 STEP 4 점수표와 같음(반올림 범위 안)")
def t_values():
    P = payload_of()
    s = pd.read_parquet(B.INPUTS["scores"])
    s = s.loc[s["scored"]].sort_values(["industry_code", "trdar_code"])
    # 영역 점수는 반올림 없이 그대로, 나머지는 build_final.score_cells의 자릿수 + 부동소수 오차
    tol = {"sa": ("score_sales", 0), "co": ("score_competition", 0), "st": ("score_stability", 0), "de": ("score_demand", 0),
           "n": ("stores", 5e-3 + 1e-9), "sm": ("sales_month", 0.5 + 1e-6), "cp": ("competition", 5e-7 + 1e-12), "cl": ("close_pct_shrunk", 5e-7 + 1e-12),
           "pf": ("pct_floating", 0.05 + 1e-9), "pw": ("pct_worker", 0.05 + 1e-9), "pr": ("pct_resident", 0.05 + 1e-9)}
    worst = {}
    order_diff = 0
    for code, g in s.groupby("industry_code"):
        p = P["scores"][code]
        assert [P["areas"]["code"][i] for i in p["a"]] == g["trdar_code"].tolist(), f"{code} 상권 순서가 다름"
        for key, (col, t) in tol.items():
            a = np.array([np.nan if v is None else v for v in p[key]], dtype=float)
            b = g[col].to_numpy(dtype=float)
            assert np.array_equal(np.isnan(a), np.isnan(b)), f"{code} {col} 결측 위치가 다름"
            d = float(np.nanmax(np.abs(a - b))) if (~np.isnan(a)).any() else 0.0
            worst[col] = max(worst.get(col, 0), d)
            assert d <= t, f"{code} {col} 차이 {d}"
        full = python_order(g.assign(scored=True).reset_index(drop=True), B.DEFAULT_WEIGHTS)["trdar_code"].head(20).tolist()
        rounded = python_order(payload_frame(P, code), B.DEFAULT_WEIGHTS)["trdar_code"].head(20).tolist()
        order_diff += full != rounded
    assert order_diff == 0, f"payload 값으로 정한 상위 20곳 순서가 원래 점수표와 다른 업종 {order_diff}개"
    return "77개 업종, 영역 점수는 원래 값 그대로, 상위 20곳 순서도 점수표와 같음"


JS_RANK = r"""
const fs = require("fs"); const a = process.argv.slice(-3);
const C = require(a[0]); const P = JSON.parse(fs.readFileSync(a[1], "utf8")); const W = JSON.parse(fs.readFileSync(a[2], "utf8"));
const out = {};
for (const code of Object.keys(P.scores)) out[code] = W.map(w => C.rankRows(C.industryRows(P, code, w)).map(r => [r.code, r.total, r.used]));
process.stdout.write(JSON.stringify(out));
"""


@check("6. 종합 점수 · 순위: 화면 계산 = STEP 4 views.composite · order_rows (가중치 5가지)")
def t_rank():
    if not node():
        return f"{SKIP}: node 없음"
    P = payload_of()
    (WORK / "payload.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    (WORK / "weights.json").write_text(json.dumps(WEIGHT_SETS), encoding="utf-8")
    js = run_node(JS_RANK, str(CORE), str(WORK / "payload.json"), str(WORK / "weights.json"))
    rows = 0
    for code in P["scores"]:
        frame = payload_frame(P, code)
        for k, w in enumerate(WEIGHT_SETS):
            py = python_order(frame, w)
            got = js[code][k]
            assert [g[0] for g in got] == py["trdar_code"].tolist(), f"{code} 가중치 {w} 순서가 다름"
            for g, t, u in zip(got, py["total"], py["used"]):
                assert (g[1] is None) == pd.isna(t), f"{code} {g[0]} 종합 점수 결측이 다름"
                assert g[1] is None or abs(g[1] - t) < 1e-9, f"{code} {g[0]} 종합 점수 {g[1]} != {t}"
                assert g[2] == int(u), f"{code} {g[0]} 영역 수가 다름"
            rows += len(got)
    return f"{rows:,}행 순서 · 점수 · 영역 수 일치 (가중치 0 · 0 · 0 · 0이면 종합 점수 없음 포함)"


JS_QUIZ = r"""
const fs = require("fs"); const a = process.argv.slice(-3);
const C = require(a[0]); const P = JSON.parse(fs.readFileSync(a[1], "utf8")); const L = JSON.parse(fs.readFileSync(a[2], "utf8"));
const nos = P.step5.questions.map(q => q["번호"]).sort((x, y) => x - y);
const out = L.map(text => {
  const ans = {}; nos.forEach((no, i) => { if (text[i] === "A" || text[i] === "B") ans[no] = text[i]; });
  const r = C.scoreAnswers(ans, P.step5.questions, P.step5.axes);
  const o = { type: r.type, complete: r.complete, answered: r.answered, axes: r.axes.map(x => [x.letter, x.counts, x.answered, x.clear, x.boundary]) };
  if (r.complete) { o.matched = Object.entries(C.matchedTypes(r)); const w = C.sgWeights(r, P.step5.weights); o.weights = w.weights; o.label = w.label; o.text = C.axisText(r); }
  return o;
});
process.stdout.write(JSON.stringify(out));
"""


@check("7. 금융 MBTI 채점: 화면 계산 = mbti.py (완성 응답 32,768가지 + 미완성 3,000가지)")
def t_quiz():
    if not node():
        return f"{SKIP}: node 없음"
    P = payload_of()
    questions = pd.read_csv(B.INPUTS["questions"], encoding="utf-8-sig")
    axes = json.loads(B.INPUTS["stage5_meta"].read_text(encoding="utf-8"))["axes"]
    weights = pd.read_csv(B.INPUTS["sg_weights"], encoding="utf-8-sig")
    rng = random.Random(6)
    texts = ["".join(p) for p in itertools.product("AB", repeat=15)]
    texts += ["".join(rng.choice("AB-") for _ in range(15)) for _ in range(3000)]
    (WORK / "payload.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    (WORK / "answers.json").write_text(json.dumps(texts), encoding="utf-8")
    js = run_node(JS_QUIZ, str(CORE), str(WORK / "payload.json"), str(WORK / "answers.json"))
    boundary = 0
    for text, j in zip(texts, js):
        r = mbti.score_answers(mbti.parse_answers(text, questions), questions, axes)
        assert j["type"] == r["type"] and j["complete"] == r["complete"] and j["answered"] == r["answered"], f"{text}: 유형 {j['type']} != {r['type']}"
        for ja, pa in zip(j["axes"], r["axes"]):
            assert ja == [pa["letter"], pa["counts"], pa["answered"], pa["clear"], pa["boundary"]], f"{text}: 기준 {pa['기준']} 판정이 다름"
        if r["complete"]:
            assert [tuple(x) for x in j["matched"]] == list(mbti.matched_types(r).items()), f"{text}: 맞춰 볼 상권 유형이 다름"
            w, label = mbti.sg_weights(r, weights)
            assert j["weights"] == w and j["label"] == label, f"{text}: 가중치가 다름"
            assert j["text"] == mbti.axis_text(r), f"{text}: 판정 문구가 다름"
            boundary += any(a["boundary"] for a in r["axes"])
    return f"{len(texts):,}가지 일치 (경계 글자가 있는 완성 응답 {boundary:,}가지 포함)"


JS_TYPES = r"""
const fs = require("fs"); const a = process.argv.slice(-2);
const C = require(a[0]); const P = JSON.parse(fs.readFileSync(a[1], "utf8"));
const out = {};
for (const code of Object.keys(P.scores)) {
  const T = C.typeCompare(P, code, P.step5.weights, 5); out[code] = {};
  for (const k of Object.keys(T)) out[code][k] = { pool: T[k].pool, top: T[k].top.map(r => r.code) };
}
process.stdout.write(JSON.stringify(out));
"""


@check("8. 시각화 7: 유형별 상위 5곳 = build_final.mbti_compare (77개 업종)")
def t_types():
    if not node():
        return f"{SKIP}: node 없음"
    P = payload_of()
    (WORK / "payload.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    js = run_node(JS_TYPES, str(CORE), str(WORK / "payload.json"))
    d = B.read_inputs()
    areas = B.area_frame(d)
    for code in P["scores"]:
        py = B.mbti_compare(d, areas, code)
        for two, v in py.items():
            for sg in ["S", "G"]:
                j = js[code][two + sg]
                assert j["pool"] == v["pool"] and j["top"] == v[sg], f"{code} {two}{sg}: {j['top']} != {v[sg]}"
    meta = json.loads((HERE / "data" / B.META_NAME).read_text(encoding="utf-8"))["checks"]["mbti_default_industry"]
    assert all(js[B.DEFAULT_INDUSTRY][t + sg]["top"] == meta[t][sg] for t in meta for sg in ["S", "G"]), "설계표의 확인값과 다름"
    return "77개 업종 × 8개 유형 일치, 설계표 확인값(커피-음료)과도 같음"


JS_RHO = r"""
const fs = require("fs"); const a = process.argv.slice(-2);
const C = require(a[0]); const P = JSON.parse(fs.readFileSync(a[1], "utf8"));
const out = {};
for (const code of Object.keys(P.scores)) {
  const rows = C.industryRows(P, code, P.defaultWeights).filter(r => r.sales !== null);
  out[code] = { rho: C.spearman(rows.map(r => r.salesMonth), rows.map(r => r.close)), nonpos: rows.filter(r => !(r.salesMonth > 0)).length };
}
process.stdout.write(JSON.stringify(out));
"""


@check("9. 시각화 4: 화면의 순위상관 = 점수표 원래 정밀도의 Python spearman, 로그 축에서 빠지는 점 없음")
def t_rho():
    if not node():
        return f"{SKIP}: node 없음"
    P = payload_of()
    (WORK / "payload.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    js = run_node(JS_RHO, str(CORE), str(WORK / "payload.json"))
    rho = P["viz"]["salesClose"]["rho"]
    s = pd.read_parquet(B.INPUTS["scores"])
    s = s.loc[s["scored"] & s["score_sales"].notna()]
    for code, v in rho.items():
        g = s.loc[s["industry_code"].eq(code)]
        full = B.spearman(g["sales_month"], g["close_pct_shrunk"])
        assert js[code]["rho"] is not None and abs(js[code]["rho"] - full) <= 1e-9, f"{code}: 화면 {js[code]['rho']} != Python {full}"
        assert abs(round(full, 4) - v) < 1e-12, f"{code}: 설계표 값 {v}가 다시 계산한 값과 다름"
        assert js[code]["nonpos"] == 0, f"{code}: 점포당 월매출 0 이하 {js[code]['nonpos']}곳"
    extra = [c for c, v in js.items() if v["rho"] is not None and c not in rho]
    assert not extra, f"매출 점수가 없는데 상관을 계산한 업종: {extra}"
    return f"{len(rho)}개 업종 일치"


# ---------------------------------------------------------------- 10~12. 집계 · 문서


@check("10. 시각화 2: 서울 매출 합계 · 행 비중이 원자료와 맞음")
def t_heat():
    P = payload_of()
    H = P["viz"]["heat"]
    shared = json.loads(B.INPUTS["shared_meta"].read_text(encoding="utf-8"))
    assert abs(H["seoulTotal"] - round(shared["totals"]["sales"] / 1e12, 2)) < 1e-9, f"서울 합계 {H['seoulTotal']} != EDA {shared['totals']['sales'] / 1e12:.2f}"
    for M in [H["area"], H["gu"]]:
        for k, row in enumerate(M["share"]):
            assert sum(row) <= 100 + 1e-6 and M["leadShare"][k] + 1e-6 >= max(row), f"{M['rows'][k]} 비중이 맞지 않음"
    assert len(H["gu"]["rows"]) == 25 and len(H["area"]["rows"]) == 20
    return f"서울 {H['seoulTotal']}조원 = EDA 합계, 상위 20곳 중 1위 업종 50% 초과 {sum(v > 50 for v in H['area']['leadShare'])}곳"


@check("11. 시각화 5: 상권마다 묶음 합 + 세부 미기재 = 집객시설 총수")
def t_facility():
    P = payload_of()
    c = pd.read_csv(B.INPUTS["context"], dtype={"trdar_code": str})
    q = c.loc[c["quarter"].eq(20254)].set_index("trdar_code")["facility_count"]
    n = 0
    for code, fac in zip(P["areas"]["code"], P["areas"]["fac"]):
        if fac is None:
            assert pd.isna(q.get(code)), f"{code} 자료가 있는데 빠짐"
            continue
        assert min(fac) >= 0 and sum(fac) == q[code], f"{code}: {sum(fac)} != {q[code]}"
        n += 1
    F = P["viz"]["facility"]
    assert n + F["missingAreas"] == len(P["areas"]["code"])
    return f"{n:,}곳 일치, 세부 미기재 {F['unknownShare']}%"


@check("12. 문서: 표준 컬럼 대응 · 데이터셋 · 표 · 파생변수가 원본 문서와 맞음")
def t_docs():
    P = payload_of()
    dic = pd.read_csv(B.INPUTS["dictionary"], encoding="utf-8-sig")
    have = set(zip(dic["dataset_id"], dic["column_name"]))
    missing = [(ds, col) for ds, m in B.STANDARD.items() for col in m if (ds, col) not in have]
    assert not missing, f"데이터 사전에 없는 원본 컬럼: {missing}"
    cat = pd.read_csv(B.INPUTS["catalog"], encoding="utf-8-sig")
    assert [d["id"] for d in P["docs"]["datasets"]] == list(dict.fromkeys(cat["dataset_id"])), "데이터셋 목록이 다름"
    feats = pd.read_csv(B.INPUTS["features"], encoding="utf-8-sig")
    assert len(P["docs"]["features"]) == len(feats) + len(B.EXTRA_FEATURES) == 63
    assert {t["table"]: t["rows"] for t in P["docs"]["tables"]}["fact_trdar_industry_quarter"] == 304775
    tree = (HERE / "web" / "template.html").read_text(encoding="utf-8")
    for path in ["step2_3", "claude_dashboard", "step4_dashboard", "step5_design", "step6_final/build_final.py", "step6_final/test_final.py"]:
        assert (ME / path).exists(), f"폴더 구조에 적은 경로가 없음: {path}"
    assert "SpotFit_최종산출물_대시보드_2025.html" in tree
    return f"표준 컬럼 {sum(len(m) for m in B.STANDARD.values())}개, 데이터셋 9개, 파생변수 63개"


# ---------------------------------------------------------------- 13~14. 브라우저

PAGE_MARKS = {
    "s1": [(r'class="tile"', 6)], "s2": [(r"열기 ↗", 9)], "s3": [(r'data-ds="K0', 7)], "s4": [(r"<rect ", 18)],
    "s5": [(r'class="status (?:done|none)">(?:● 산출|○ 보류)', 63)], "s6": [(r'class="a" data-ti=', 1644), (r'<tr class="click', 15)],
    "s7": [(r"data-q=", 30)], "s8": [(r"<b>확인한 결과</b>", 7), (r'class="a" data-ti=', 1644)], "s9": [(r'class="tree"', 1)], "s10": [(r"박성은 님 통합본", 1)],
}

INJECT = r"""<script>
(function () {
  var q = new URLSearchParams(location.search), P = JSON.parse(document.getElementById("payload").textContent);
  if (q.get("quiz")) {
    var want = { "주요 고객": "VVVVL", "소비 성향": "PPPEE", "상권 변화": "GGGGG" }, by = {};
    location.hash = "#s7"; window.dispatchEvent(new HashChangeEvent("hashchange"));
    P.step5.questions.slice().sort(function (a, b) { return a["번호"] - b["번호"]; }).forEach(function (x) { (by[x["기준"]] = by[x["기준"]] || []).push(x); });
    Object.keys(want).forEach(function (ax) { by[ax].forEach(function (x, k) {
      var pick = x["A 글자"] === want[ax][k] ? "A" : "B";
      document.querySelector('[data-q="' + x["번호"] + '"][data-a="' + pick + '"]').click(); }); });
    document.querySelector('[data-act="on"]').click();
  }
  if (q.get("ind")) { var s = document.getElementById("industry"); s.value = q.get("ind"); s.dispatchEvent(new Event("change")); }
  var go = q.get("go");
  if (go) { location.hash = "#" + go; window.dispatchEvent(new HashChangeEvent("hashchange")); }
})();
</script>"""


@check("13. 브라우저: 10개 화면이 오류 없이 그려짐 (Chrome headless)")
def t_browser():
    if not chrome():
        return f"{SKIP}: Chrome 없음 (CHROME 환경변수로 경로 지정 가능)"
    notes = []
    for page, marks in PAGE_MARKS.items():
        dom, errors = dump_dom(file_url(HTML, hash_="#" + page))
        assert 'data-ready="1"' in dom, f"{page}: 초기화가 끝나지 않음"
        assert not errors, f"{page}: 콘솔 오류 {errors[:2]}"
        assert re.search(rf'<section id="p-{page}" class="page"(?![^>]*hidden)', dom), f"{page}: 화면이 보이지 않음"
        for pat, n in marks:
            got = len(re.findall(pat, dom))
            assert got >= n, f"{page}: '{pat}' {got}개 < {n}개"
        notes.append(page)
    return f"{len(notes)}개 화면, 콘솔 오류 0"


@check("14. 상호작용: 검사 → 적용 → 6장 반영, 점수 없는 업종 화면")
def t_interact():
    if not chrome():
        return f"{SKIP}: Chrome 없음"
    copy = WORK / "interact.html"
    copy.write_text(HTML.read_text(encoding="utf-8").replace("</body>", INJECT + "</body>"), encoding="utf-8")
    dom, errors = dump_dom(file_url(copy, "?quiz=1&go=s7"))
    assert not errors, f"콘솔 오류 {errors[:2]}"
    assert "V 4:1 · P 3:2 (경계) · G 5:0" in dom and "VP(일치) · VE(경계 유형)" in dom, "검사 결과가 화면에 없음"
    assert len(re.findall(r'<span class="badge (?:match|near)"', dom)) >= 20, "추천 표가 비어 있음"
    dom, errors = dump_dom(file_url(copy, "?quiz=1&go=s6"))
    assert not errors, f"콘솔 오류 {errors[:2]}"
    assert "<b>VPG</b>" in dom and 'id="w_sales" min="0" max="50" step="5" value="35"' in dom, "적용한 유형 · G 가중치가 6장에 없음"
    assert len(re.findall(r'<span class="badge match"', dom)) >= 5, "6장 표에 유형 일치 열이 없음"
    P = payload_of()
    none = next(r for r in P["industries"] if not r["scored"])
    for go, text in [("s6", "점수를 만들지 않았습니다"), ("s8", "레이더를 그리지 않습니다")]:
        dom, errors = dump_dom(file_url(copy, f"?ind={none['code']}&go={go}"))
        assert not errors, f"{none['name']} {go}: 콘솔 오류 {errors[:2]}"
        assert text in dom, f"{none['name']} {go}: 안내 문구가 없음"
    return f"VPG 적용 · 경계 유형 표시 · 점수 없는 업종({none['name']}) 안내 확인"


def main() -> int:
    parser = argparse.ArgumentParser(description="STEP 6 · 최종 대시보드 검증")
    parser.add_argument("--skip-browser", action="store_true", help="13 · 14번(Chrome)을 건너뜀")
    parser.add_argument("--keep", action="store_true", help="임시 파일(.check/test_run)을 남김")
    args = parser.parse_args()
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    try:
        for t in [t_fingerprint, t_deterministic, t_self_contained, t_counts, t_values, t_rank, t_quiz, t_types, t_rho, t_heat, t_facility, t_docs]:
            t()
        if args.skip_browser:
            RESULTS.append(("13 · 14. 브라우저", SKIP, "--skip-browser"))
            print(f"[{SKIP}] 13 · 14. 브라우저 - --skip-browser")
        else:
            t_browser()
            t_interact()
    finally:
        if not args.keep:
            shutil.rmtree(WORK, ignore_errors=True)
            if WORK.parent.exists() and not any(WORK.parent.iterdir()):
                WORK.parent.rmdir()
    counts = {s: sum(1 for r in RESULTS if r[1] == s) for s in ["통과", "실패", SKIP]}
    print(f"\n통과 {counts['통과']} · 실패 {counts['실패']} · 건너뜀 {counts[SKIP]}")
    return 1 if counts["실패"] else 0


if __name__ == "__main__":
    sys.exit(main())
