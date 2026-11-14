# -*- coding: utf-8 -*-
"""STEP 5 금융 MBTI 상권 추천의 조회와 차트. marimo 없이 테스트할 수 있다.

추천 규칙:
    1. 희망 업종의 STEP 4 점수 대상 상권 중, 고른 축(L/V · E/P · S/D)이 일치하는 곳만 남긴다.
       '상관없음'으로 둔 축은 거르지 않는다. 판정이 보류된 칸은 그 축을 고르면 빠진다(다른 유형으로 채우지 않음).
    2. 남은 상권을 STEP 4 종합 점수로 줄 세운다. 가중치는 STEP 4 기본값(매출 30 · 경쟁 25 · 안정성 15 · 수요 30) [가정].
    3. 유형에 따라 자동으로 바뀌는 것은 '수요의 주 고객층' 하나다. L → 주민 중심, V → 유동인구 중심, 상관없음 → 세 값 평균.
       E/P와 S/D는 거르는 데만 쓰고 점수에 다시 더하지 않는다. 같은 정보를 두 번 반영하지 않기 위해서다.
       (S/D와 안정성 점수의 겹침은 build_types.py에서 직접 확인했고 약하다: Spearman −0.09)
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import altair as alt
import pandas as pd

HERE = Path(__file__).resolve().parent
STEP4 = HERE.parent / "step4_dashboard"
sys.path.insert(0, str(STEP4))
sys.path.insert(0, str(HERE))  # 다른 폴더에서 불러도 build_types를 찾게 한다
import build_scores as bs  # noqa: E402  STEP 4의 composite(종합 점수)를 그대로 쓴다
import views as v4  # noqa: E402  STEP 4의 데이터 묶음·지도·색을 그대로 쓴다

from build_types import AXES, AXIS_MEANING, AXIS_TITLES, LEGACY, REPO, TYPE_NAMES  # noqa: E402

DATA = HERE / "data"
DEMAND_LINK = {"L": "resident", "V": "floating", None: "avg"}
ANY = "상관없음"


@dataclass(frozen=True)
class Bundle:
    step4: v4.Bundle
    cells: pd.DataFrame
    areas: pd.DataFrame
    industries: pd.DataFrame
    types: pd.DataFrame
    meta: dict
    stale: tuple  # 유형표를 만든 뒤 바뀐 입력 파일. 비어 있지 않으면 build_types.py를 다시 실행해야 한다


def stale_inputs(meta: dict) -> tuple:
    """유형표를 만들 때 기록한 입력 지문(SHA-256)과 지금 파일을 비교한다. STEP 4 점수를 다시 만들었는데 유형표가 옛것이면 알린다."""
    out = []
    for rel, digest in meta.get("inputs", {}).items():
        p = REPO / rel
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            out.append(rel)
    return tuple(out)


def load_bundle() -> Bundle:
    need = [DATA / "상권업종_유형_2025.parquet", DATA / "상권_유형축_2025.csv", DATA / "업종별_유형_가능여부.csv",
            DATA / "유형_정의.csv", DATA / "stage5_meta.json"]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        raise FileNotFoundError("STEP 5 데이터가 없습니다: " + ", ".join(missing) + ". build_types.py를 먼저 실행하세요.")
    step4 = v4.load_bundle()
    cells = pd.read_parquet(need[0])
    extra = ["trdar_code", "industry_code", "ticket_pct", "EP", "EP_reason", "lv_share", "LV", "LV_reason", "chg_name",
             "run_months", "closed_months", "chg_same_all_year", "SD", "SD_reason", "type_code", "type_full", "type_name", "type_status"]
    joined = step4.scores.merge(cells[extra], on=["trdar_code", "industry_code"], how="left", validate="one_to_one")
    meta = json.loads(need[4].read_text(encoding="utf-8"))
    return Bundle(
        step4=step4, cells=joined,
        areas=pd.read_csv(need[1], dtype={"trdar_code": str}, encoding="utf-8-sig"),
        industries=pd.read_csv(need[2], dtype={"업종_코드": str}, encoding="utf-8-sig"),
        types=pd.read_csv(need[3], encoding="utf-8-sig"),
        meta=meta, stale=stale_inputs(meta),
    )


# ---------------------------------------------------------------- 유형 입력


def parse_type(code: str | None) -> dict:
    """'LES'처럼 세 글자 유형을 축별 선택으로 바꾼다. 예전 G 코드(LEG 등)는 D 코드로 바꾼다. 잘못된 코드는 ValueError."""
    if not code:
        return {"LV": None, "EP": None, "SD": None}
    code = LEGACY.get(code.upper(), code.upper())
    if code not in TYPE_NAMES:
        raise ValueError(f"알 수 없는 유형 코드입니다: {code}. 가능한 코드: {', '.join(TYPE_NAMES)}")
    return {"LV": code[0], "EP": code[1], "SD": code[2]}


def check_choice(choice: dict) -> dict:
    out = {}
    for ax, letters in AXES.items():
        val = choice.get(ax)
        val = None if val in (None, "", ANY) else val
        if val is not None and val not in letters:
            raise ValueError(f"{AXIS_TITLES[ax]} 축에 없는 값입니다: {val}. 가능한 값: {', '.join(letters)} 또는 {ANY}")
        out[ax] = val
    return out


def choice_code(choice: dict) -> str:
    """축별 선택을 'L?S'처럼 보여 준다. ?는 상관없음."""
    return "".join(choice.get(ax) or "?" for ax in AXES)


def choice_name(choice: dict) -> str:
    code = choice_code(choice)
    if code in TYPE_NAMES:
        return f"{code} · {TYPE_NAMES[code]}"
    parts = [f"{AXES[ax][choice[ax]]}" for ax in AXES if choice.get(ax)]
    return f"{code} · " + " + ".join(parts) if parts else "모든 유형 (세 축 모두 상관없음)"


def demand_mode(choice: dict) -> str:
    return DEMAND_LINK[choice.get("LV")]


# ---------------------------------------------------------------- 추천


def industry_row(b: Bundle, industry_code: str) -> pd.Series:
    ind = b.industries.set_index("업종_코드")
    if industry_code not in ind.index:
        raise ValueError(f"알 수 없는 업종 코드입니다: {industry_code}")
    return ind.loc[industry_code]


def seoul_scope(b: Bundle, industry_code: str, choice: dict, weights=None) -> pd.DataFrame:
    """같은 업종 점수 대상 전체(유형 무관)에 고른 유형의 수요 연결로 종합 점수를 매긴다. 순위의 기준."""
    industry_row(b, industry_code)
    mode = demand_mode(check_choice(choice))
    d = b.cells.loc[b.cells["industry_code"].eq(industry_code) & b.cells["score_status"].eq("점수 대상")].copy()
    d["score_dem"] = d[f"score_dem_{mode}"]
    d["score_total"], d["n_areas"] = bs.composite(d, v4.normalize_weights(weights or bs.DEFAULT_WEIGHTS), mode)
    d["seoul_rank"] = d["score_total"].rank(ascending=False, method="min")
    d["seoul_n"] = int(d["score_total"].notna().sum())
    return d.sort_values(["score_total", "stores"], ascending=[False, False], na_position="last").reset_index(drop=True)


def recommend(b: Bundle, industry_code: str, choice: dict, gus=None, weights=None) -> pd.DataFrame:
    """희망 업종 + 고른 축에 맞는 상권. STEP 4 종합 점수 순서. 점수는 서울 같은 업종 기준이라 자치구로 다시 계산하지 않는다."""
    choice = check_choice(choice)
    d = seoul_scope(b, industry_code, choice, weights)
    match = pd.Series(True, index=d.index)
    for ax, val in choice.items():
        if val is not None:
            match &= d[ax].eq(val)
    d = d.loc[match]
    if gus:
        d = d.loc[d["gu_name"].isin(list(gus))]
    return d.sort_values(["score_total", "stores"], ascending=[False, False], na_position="last").reset_index(drop=True)


def funnel(b: Bundle, industry_code: str, choice: dict, gus=None) -> list[tuple[str, int]]:
    """조건을 하나씩 더할 때 남는 상권 수. 결과가 없을 때 어느 조건에서 줄었는지 보여 준다."""
    choice = check_choice(choice)
    d = b.cells.loc[b.cells["industry_code"].eq(industry_code) & b.cells["score_status"].eq("점수 대상")]
    steps = [("STEP 4 점수 대상", len(d))]
    for ax, val in choice.items():
        if val is not None:
            d = d.loc[d[ax].eq(val)]
            steps.append((f"+ {AXIS_TITLES[ax]} {val} {AXES[ax][val]}", len(d)))
    if gus:
        d = d.loc[d["gu_name"].isin(list(gus))]
        steps.append((f"+ 자치구 {len(gus)}곳", len(d)))
    return steps


def hold_counts(b: Bundle, industry_code: str) -> pd.DataFrame:
    """이 업종 점수 대상 칸에서 축별 판정 결과 (L·V·보류 등)."""
    d = b.cells.loc[b.cells["industry_code"].eq(industry_code) & b.cells["score_status"].eq("점수 대상")]
    rows = []
    for ax, letters in AXES.items():
        for letter, name in letters.items():
            rows.append({"축": AXIS_TITLES[ax], "판정": f"{letter} {name}", "상권 수": int(d[ax].eq(letter).sum())})
        rows.append({"축": AXIS_TITLES[ax], "판정": "보류", "상권 수": int(d[ax].isna().sum())})
    return pd.DataFrame(rows)


def type_counts(b: Bundle, industry_code: str) -> pd.DataFrame:
    d = b.cells.loc[b.cells["industry_code"].eq(industry_code) & b.cells["score_status"].eq("점수 대상")]
    t = b.types[["유형_코드", "유형_이름"]].copy()
    t["상권 수"] = t["유형_코드"].map(d["type_full"].value_counts()).fillna(0).astype(int)
    t["보기"] = t["유형_코드"] + " " + t["유형_이름"]
    return t


# ---------------------------------------------------------------- 표와 설명


def fmt(v, digits=0, unit=""):
    return "" if pd.isna(v) else f"{v:,.{digits}f}{unit}"


def rank_text(rank, n) -> str:
    return "점수 없음" if pd.isna(rank) else f"{rank:,.0f} / {n:,}"


def result_table(d: pd.DataFrame) -> pd.DataFrame:
    """추천 상권 표. 축마다 판정 근거 값을 함께 둔다. 결과가 없어도 같은 열의 빈 표를 돌려준다."""
    r = lambda s: s.round(0)
    return pd.DataFrame({
        "trdar_code": d["trdar_code"],
        "상권": d["trdar_name"], "자치구": d["gu_name"],
        "유형": d["type_code"], "유형 이름": d["type_name"].fillna("일부 축 보류"),
        "종합 점수": r(d["score_total"]),
        "서울 순위": pd.Series([rank_text(a, n) for a, n in zip(d["seoul_rank"], d["seoul_n"])], index=d.index, dtype=object),
        "매출": r(d["score_sales"]), "경쟁": r(d["score_comp"]), "안정성": r(d["score_stab"]), "수요": r(d["score_dem"]),
        "주민 비중": d["lv_share"].round(2), "건당 금액 백분위": r(d["ticket_pct"]),
        "상권변화지표": d["chg_name"], "영업 중 가게 평균 개월": d["run_months"], "문 닫은 가게 평균 개월": d["closed_months"],
        "평균 점포 수": d["stores"].round(1),
    })


def type_card(choice: dict) -> str:
    """고른 유형을 쉬운 말로 설명하는 마크다운."""
    lines = [f"### {choice_name(choice)}"]
    for ax in AXES:
        val = choice.get(ax)
        lines.append(f"- **{AXIS_TITLES[ax]}**: " + (f"{val} {AXES[ax][val]} — {AXIS_MEANING[val]}" if val else f"{ANY} (거르지 않음)"))
    mode = bs.DEMAND_MODES[demand_mode(choice)]
    lines.append(f"- **자동 설정**: 수요 점수의 주 고객층 = **{mode}**"
                 + (" (L 생활형이라 주민을 봄)" if choice.get("LV") == "L" else " (V 방문형이라 유동인구를 봄)" if choice.get("LV") == "V" else ""))
    if choice.get("SD") == "D":
        lines.append("- ⚠️ **역동형은 '좋은 상권'이라는 뜻이 아닙니다.** 새 가게가 많이 들어오지만 일찍 닫는 가게도 많습니다. "
                     "변화와 위험을 감수하고 기회를 노리는 선택입니다.")
    return "\n".join(lines)


# ---------------------------------------------------------------- 차트


def type_bar(t: pd.DataFrame, chosen: str, pal: dict, width: int = 460):
    """이 업종 점수 대상 상권의 8유형 분포. 고른 유형만 진하게."""
    d = t.assign(pick=t["유형_코드"].eq(chosen))
    base = alt.Chart(d).encode(
        y=alt.Y("보기:N", sort=list(d["보기"]), title=None),
        x=alt.X("상권 수:Q", title="상권 수"),
        tooltip=["유형_코드", "유형_이름", "상권 수"])
    bars = base.mark_bar(cornerRadiusEnd=3, height=16).encode(
        color=alt.condition("datum.pick", alt.value(pal["s1"]), alt.value(pal["blues"][0])))
    text = base.mark_text(align="left", dx=4, fontSize=11, color=pal["ink2"]).encode(text="상권 수:Q")
    return v4.styled((bars + text).properties(width=width, height=24 * len(d)), pal)


def hold_bar(h: pd.DataFrame, pal: dict, width: int = 460):
    """축별 판정·보류 수. 보류가 많으면 그 축을 '상관없음'으로 두는 편이 결과가 많다."""
    d = h.assign(hold=h["판정"].eq("보류"))
    chart = alt.Chart(d).mark_bar(height=14).encode(
        y=alt.Y("판정:N", sort=None, title=None), x=alt.X("상권 수:Q"),
        row=alt.Row("축:N", sort=list(AXIS_TITLES.values()), title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
        color=alt.condition("datum.hold", alt.value(pal["missing"]), alt.value(pal["s3"])),
        tooltip=["축", "판정", "상권 수"])
    return v4.styled(chart.properties(width=width, height=60), pal).resolve_scale(y="independent")


def area_sd_chart(areas: pd.DataFrame, pal: dict, width: int = 460):
    """서울 상권 1,644곳의 상권변화지표 4유형과 S/D 연결."""
    order = ["정체", "상권축소", "상권확장", "다이나믹"]
    label = {"정체": "정체 → S 안정형", "다이나믹": "다이나믹 → D 역동형", "상권확장": "상권확장 → 중간", "상권축소": "상권축소 → 중간"}
    d = areas["chg_name"].value_counts().reindex(order).fillna(0).astype(int).rename_axis("chg").reset_index(name="n")
    d["보기"] = d["chg"].map(label)
    d["색"] = d["chg"].map({"정체": pal["s1"], "다이나믹": pal["s2"]}).fillna(pal["missing"])
    base = alt.Chart(d).encode(y=alt.Y("보기:N", sort=[label[o] for o in order], title=None), x=alt.X("n:Q", title="상권 수"))
    return v4.styled((base.mark_bar(height=18).encode(color=alt.Color("색:N", scale=None))
                      + base.mark_text(align="left", dx=4, color=pal["ink2"]).encode(text="n:Q")).properties(width=width, height=130), pal)


def map_figure(b: Bundle, picks: pd.DataFrame, seoul: pd.DataFrame, selected: str | None, pal: dict, view_key: str = ""):
    """조건에 맞는 상권만 칠한 Plotly 지도. 순위는 서울 같은 업종(유형 무관) 기준. STEP 4 map_plotly를 그대로 쓴다."""
    if picks.empty:
        return None
    return v4.map_plotly(b.step4, picks, selected, pal, height=480, seoul=seoul, view_key=view_key)
