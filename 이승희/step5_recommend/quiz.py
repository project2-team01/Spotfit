# -*- coding: utf-8 -*-
"""금융 MBTI 검사지 15문항과 채점. 문항 원문은 금융MBTI_검사지_초안.md와 같아야 한다(test_step5.py가 비교한다).

채점:
    기준마다 5문항 중 3개 이상 고른 쪽이 그 글자다. 5:0·4:1은 '뚜렷함', 3:2는 '경계'.
    대시보드에서는 경계인 축과 아직 다 답하지 않은 축을 '상관없음'으로 두고 두 글자 상권을 모두 보여 준다.
"""
from __future__ import annotations

import random

from build_types import AXES, TYPE_NAMES

# (번호, 축, 질문, (A 보기, A 글자), (B 보기, B 글자))
QUESTIONS = [
    (1, "LV", "우리 가게가 가장 바빴으면 하는 때는?", ("평일 점심시간과 퇴근길", "V"), ("평일 저녁과 주말", "L")),
    (2, "LV", "손님 대부분이 이런 사람이면 좋겠다.", ("걸어서 5분 거리에 사는 주민", "L"), ("근처 사무실에 다니는 직장인", "V")),
    (3, "LV", "가게 문 앞 풍경으로 더 마음에 드는 쪽은?", ("사원증을 목에 건 사람들이 바쁘게 지나간다", "V"), ("장바구니와 유모차가 천천히 지나간다", "L")),
    (4, "LV", "손님에게 가장 신경 쓸 부분은?", ("아이 이름, 반려견 이름까지 기억하는 친근함", "L"), ("점심시간 안에 주문부터 결제까지 끝나는 빠르기", "V")),
    (5, "LV", "요일별 매출이 이렇다면 더 편한 쪽은?", ("평일에 몰리고 주말에는 한산하다", "V"), ("요일과 상관없이 비슷하게 꾸준하다", "L")),
    (6, "EP", "대표 메뉴 가격을 정한다면?", ("주변 가게보다 조금 싸게 해서 자주 오게 한다", "E"), ("주변 가게보다 비싸도 그만한 값어치를 보여 준다", "P")),
    (7, "EP", "손님 한 명이 한 번 올 때 쓰고 가는 돈은 어느 쪽이 좋을까요?", ("2~3만 원. 오래 머물며 여러 가지를 주문한다", "P"), ("5천~1만 원. 짧게 들러 한두 가지만 산다", "E")),
    (8, "EP", "재료비가 크게 올랐다면?", ("구성을 조정해 가격은 그대로 지킨다", "E"), ("더 좋은 재료로 바꾸고 가격을 올린다", "P")),
    (9, "EP", "리뷰에서 가장 듣고 싶은 말은?", ('"특별한 날 다시 오고 싶은 곳"', "P"), ('"이 가격에 이 정도면 최고"', "E")),
    (10, "EP", "매장 운영 방식으로 더 끌리는 쪽은?", ("키오스크·셀프 주문으로 비용을 줄이고 가격을 낮춘다", "E"), ("직원이 직접 응대하고 메뉴를 설명해 준다", "P")),
    (11, "SD", "상권을 둘러보다 더 끌리는 거리는?", ("20년 된 간판의 가게들이 그대로 있는 거리", "S"), ("갈 때마다 새 간판이 하나씩 보이는 거리", "D")),
    (12, "SD", "이웃 가게들이 1~2년마다 바뀐다면?", ("새 손님이 계속 드나든다는 뜻이니 기회다", "D"), ("오래 버틴 가게들 사이에 있는 편이 마음 편하다", "S")),
    (13, "SD", "창업하고 3년 동안의 계획은?", ("한 자리에서 같은 메뉴로 꾸준히 단골을 쌓는다", "S"), ("손님 반응을 보며 메뉴와 콘셉트를 계속 바꾼다", "D")),
    (14, "SD", "두 상권 중 하나를 고른다면?", ("문 닫는 가게가 많지만, 잘되는 가게는 크게 잘된다", "D"), ("크게 대박 나는 가게는 없지만, 문 닫는 가게도 드물다", "S")),
    (15, "SD", "메뉴를 정할 때 더 중요한 것은?", ("유행을 타지 않아 10년 뒤에도 팔릴 메뉴", "S"), ("지금 사람들이 찾는 새로운 메뉴를 빠르게", "D")),
]
PER_AXIS = 5
SHUFFLE_SEED = 20261114  # 화면의 문항 순서. 고정해 두어 누가 열어도 같은 순서로 보인다


def display_order() -> list[int]:
    """화면에 보여 줄 문항 번호 순서. 같은 기준 문항이 몰리지 않게 섞는다."""
    order = [q[0] for q in QUESTIONS]
    random.Random(SHUFFLE_SEED).shuffle(order)
    return order


def question(no: int) -> tuple:
    for q in QUESTIONS:
        if q[0] == no:
            return q
    raise ValueError(f"없는 문항 번호입니다: {no}")


def score(answers: dict) -> dict:
    """answers: {문항 번호: 고른 글자 또는 None}. 축마다 개수·글자·상태와 대시보드용 선택을 돌려준다."""
    result = {"axes": {}, "choice": {}, "answered": 0}
    for ax, letters in AXES.items():
        qs = [q for q in QUESTIONS if q[1] == ax]
        counts = {k: 0 for k in letters}
        for q in qs:
            val = answers.get(q[0])
            if val is None or val == "":
                continue
            if val not in (q[3][1], q[4][1]):
                raise ValueError(f"{q[0]}번 문항에 없는 답입니다: {val}")
            counts[val] += 1
        n = sum(counts.values())
        result["answered"] += n
        top, other = sorted(counts, key=lambda k: -counts[k])
        if n < PER_AXIS:
            status, letter = f"답 {n}/{PER_AXIS}", None
        elif counts[top] >= 4:
            status, letter = "뚜렷함", top
        else:
            status, letter = "경계", top
        result["axes"][ax] = {"counts": counts, "letter": letter, "status": status}
        result["choice"][ax] = letter if status == "뚜렷함" else None  # 경계·미완료는 상관없음
    letters = [result["axes"][ax]["letter"] for ax in AXES]
    result["code"] = "".join(letters) if all(letters) else None
    result["name"] = TYPE_NAMES.get(result["code"]) if result["code"] else None
    result["complete"] = result["answered"] == len(QUESTIONS)
    return result


def summary_text(res: dict) -> str:
    """'L 4:1 · P 3:2 (경계) · D 5:0' 같은 한 줄 요약."""
    parts = []
    for ax, a in res["axes"].items():
        if a["letter"] is None:
            parts.append(f"{'/'.join(AXES[ax])} {a['status']}")
            continue
        other = next(k for k in AXES[ax] if k != a["letter"])
        tag = " (경계)" if a["status"] == "경계" else ""
        parts.append(f"{a['letter']} {a['counts'][a['letter']]}:{a['counts'][other]}{tag}")
    return " · ".join(parts)
