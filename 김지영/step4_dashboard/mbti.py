"""STEP 5 금융 MBTI: 검사 채점, 상권 유형 맞추기, S/G 가중치. marimo 없이 불러서 테스트할 수 있다.

규칙 출처: seoul-commercial-analysis/data/raw/금융_MBTI.md 5장 '채점과 결과' (문항·유형은 김지영/step5_design/data/ 에 옮겨 적었다).
설계: 김지영/step5_design/STEP5_금융MBTI_설계.md
"""
from __future__ import annotations

import pandas as pd

MODE_OFF, MODE_SURVEY, MODE_DIRECT = "사용 안 함", "검사 결과", "직접 고르기"
MODES = [MODE_OFF, MODE_SURVEY, MODE_DIRECT]
MATCH, NEAR, OTHER, UNKNOWN = "일치", "경계 유형", "다른 유형", "판정 불가"
MATCH_ORDER = [MATCH, NEAR, OTHER, UNKNOWN]
WEIGHT_KEYS = {"매출 잠재력": "sales", "경쟁": "competition", "안정성": "stability", "수요": "demand"}


def ordered_questions(questions: pd.DataFrame) -> pd.DataFrame:
    """화면에 보여 줄 순서 (문항 순서를 섞고 글자는 숨긴다)."""
    return questions.sort_values("화면 순서").reset_index(drop=True)


def parse_answers(text: str | None, questions: pd.DataFrame) -> dict[int, str]:
    """시험·내보내기용: 문항 번호 순서로 쓴 15글자 (A·B, 답하지 않은 문항은 '-'). 예: 'ABBAA BAABA ABBBA' (빈칸 무시)."""
    letters = [c for c in str(text or "").upper() if c in "AB-"]
    numbers = sorted(int(n) for n in questions["번호"])
    return {no: c for no, c in zip(numbers, letters) if c in "AB"}


def score_answers(answers: dict[int, str], questions: pd.DataFrame, axes: list[dict]) -> dict:
    """기준마다 5문항 중 3개 이상 고른 쪽이 그 글자. 5:0·4:1은 뚜렷, 3:2는 경계. 한 문항이라도 비면 그 기준은 글자가 없다."""
    out, records = [], questions.to_dict("records")
    for ax in axes:
        left, right = ax["왼쪽"], ax["오른쪽"]
        rows = [r for r in records if r["기준"] == ax["기준"]]
        picked = [r[f"{answers[int(r['번호'])]} 글자"] for r in rows if answers.get(int(r["번호"])) in ("A", "B")]
        n_left, n_right = picked.count(left), picked.count(right)
        done = len(picked) == len(rows)
        letter = (left if n_left > n_right else right) if done else None
        clear = done and max(n_left, n_right) >= 4
        out.append({"기준": ax["기준"], "left": left, "right": right, "letter": letter, "counts": {left: n_left, right: n_right},
                    "answered": len(picked), "total": len(rows), "clear": clear, "boundary": done and not clear})
    complete = all(a["letter"] for a in out)
    return {"source": MODE_SURVEY, "complete": complete, "answered": sum(a["answered"] for a in out), "total": int(len(questions)),
            "type": "".join(a["letter"] for a in out) if complete else None, "axes": out}


def direct_result(code: str, axes: list[dict]) -> dict:
    """유형을 직접 고른 경우. 검사 점수가 없으므로 모든 글자를 '뚜렷'으로 본다 (경계 유형 없음)."""
    out = [{"기준": ax["기준"], "left": ax["왼쪽"], "right": ax["오른쪽"], "letter": code[i], "counts": None,
            "answered": 0, "total": 0, "clear": True, "boundary": False} for i, ax in enumerate(axes)]
    return {"source": MODE_DIRECT, "complete": True, "answered": 0, "total": 0, "type": code, "axes": out}


def axis_text(result: dict) -> str:
    """예: 'V 4:1 · P 3:2 (경계) · G 5:0'. 직접 고른 경우는 글자만."""
    if result["source"] == MODE_DIRECT:
        return " · ".join(a["letter"] for a in result["axes"]) + " (직접 고름, 검사 점수 없음)"
    parts = []
    for a in result["axes"]:
        if a["letter"] is None:
            parts.append(f"{a['기준']} {a['answered']}/{a['total']}문항")
            continue
        other = a["right"] if a["letter"] == a["left"] else a["left"]
        parts.append(f"{a['letter']} {a['counts'][a['letter']]}:{a['counts'][other]}" + (" (경계)" if a["boundary"] else ""))
    return " · ".join(parts)


def matched_types(result: dict) -> dict[str, str]:
    """상권 유형(L/V·E/P 두 글자) → 일치 / 경계 유형.

    유형표 5장: 3:2 경계이면 반대 글자의 유형 상권도 같이 보여 준다. 두 글자가 모두 경계이면 한 글자씩만 바꾼다 [가정]
    (두 글자를 한꺼번에 바꾼 유형은 넣지 않는다). S/G는 상권 쪽에서 판정하지 않으므로 맞추지 않는다.
    """
    code = result["type"]
    out = {code[:2]: MATCH}
    for i in (0, 1):
        a = result["axes"][i]
        if a["boundary"]:
            flipped = a["right"] if code[i] == a["left"] else a["left"]
            near = code[:2][:i] + flipped + code[:2][i + 1:]
            out.setdefault(near, NEAR)
    return out


def sg_weights(result: dict, weights: pd.DataFrame) -> tuple[dict[str, float], str]:
    """창업자 S/G 글자 → STEP 4 영역 가중치. 3:2 경계이면 기본값 행('경계')."""
    sg = result["axes"][2]
    key = "경계" if sg["boundary"] else sg["letter"]
    row = weights.set_index("구분").loc[key]
    return {WEIGHT_KEYS[k]: float(row[k]) for k in WEIGHT_KEYS}, str(row["이름"])


def make_profile(mode: str, survey: dict, pick: str | None, axes: list[dict], type_table: pd.DataFrame, weights: pd.DataFrame) -> dict | None:
    """대시보드에 적용할 유형. 사용 안 함이거나 검사를 끝내지 않았으면 None."""
    if mode == MODE_SURVEY and survey["complete"]:
        result = survey
    elif mode == MODE_DIRECT and pick:
        result = direct_result(pick, axes)
    else:
        return None
    info = type_table.set_index("유형").loc[result["type"]]
    w, label = sg_weights(result, weights)
    return {"type": result["type"], "emoji": info["이모지"], "name": info["이름"], "feature": info["상권 특징"], "items": info["창업 아이템 예시"],
            "result": result, "text": axis_text(result), "matched": matched_types(result), "weights": w, "weight_label": label}


def match_label(type2, matched: dict[str, str] | None) -> str:
    if type2 is None or pd.isna(type2):
        return UNKNOWN
    return (matched or {}).get(type2, OTHER)


def matched_text(matched: dict[str, str]) -> str:
    """예: 'VP(일치) · VE(경계 유형)'"""
    return " · ".join(f"{k}({v})" for k, v in matched.items())
