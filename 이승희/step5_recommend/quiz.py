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
# 11~15번(상권 변화)은 박성은 통합 기준 v1(2026-11-18)의 수정본: 공식 영업 기간 지표에 맞추고, D를 수익·기회로 설명하는 표현을 뺐다.
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
    (11, "SD", "상권을 둘러볼 때 더 끌리는 환경은?", ("오랫동안 운영한 가게들이 자리 잡은 거리", "S"), ("영업 이력이 짧은 가게들이 주로 있는 거리", "D")),
    (12, "SD", "주변 가게의 영업 이력이 짧은 곳을 본다면?", ("새롭게 자리 잡는 가게들과 함께 시도해 보고 싶다", "D"), ("오래 운영한 가게들 사이에서 시작하고 싶다", "S")),
    (13, "SD", "창업 후 운영 방식으로 더 편한 쪽은?", ("일정한 콘셉트로 꾸준히 단골을 쌓는다", "S"), ("반응을 보며 메뉴와 콘셉트를 계속 조정한다", "D")),
    (14, "SD", "상권의 영업 기간 설명을 읽고 더 살펴보고 싶은 곳은?", ("운영 중·폐업한 가게 모두 서울 평균보다 영업 기간이 짧은 곳", "D"), ("운영 중·폐업한 가게 모두 서울 평균보다 영업 기간이 긴 곳", "S")),
    (15, "SD", "주변 매장 분위기로 더 마음이 가는 쪽은?", ("오래된 가게들이 축적한 분위기", "S"), ("영업을 시작한 지 오래되지 않은 가게들의 분위기", "D")),
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
