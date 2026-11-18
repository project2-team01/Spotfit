"""통합 v1의 점수·유형·선호 필터. 모든 수치는 운영 가정이며 성과 예측이 아니다."""
from __future__ import annotations

import numpy as np
import pandas as pd

VERSION = "spotfit-unified-1.0.0-20261118"
WEIGHTS = {"sales": 30, "comp": 25, "stab": 15, "dem": 30}
AXES = {"LV": ("L", "V"), "EP": ("E", "P"), "SD": ("S", "D")}
SD_MAP = {"HH": "S", "LL": "D"}
TYPE_NAMES = {"LES": "동네 단골형", "LED": "생활 역동형", "LPS": "동네 취향형", "LPD": "취향 역동형", "VES": "실속 유동형", "VED": "유동 역동형", "VPS": "목적 방문형", "VPD": "방문 역동형"}


def score(d, weights=None, mode="avg"):
    weights = WEIGHTS if weights is None else weights
    if mode not in {"avg", "available", "floating", "worker", "resident"}:
        raise ValueError("없는 수요 모드")
    num = pd.Series(0., index=d.index)
    den = pd.Series(0., index=d.index)
    used = pd.Series(0, index=d.index)
    for k in WEIGHTS:
        w = float(weights.get(k, 0))
        if not np.isfinite(w) or w < 0:
            raise ValueError("가중치는 유한한 0 이상의 수")
        v = d[f"score_dem_{mode}" if k == "dem" else f"score_{k}"]
        ok = v.notna() & np.isfinite(v) & (w > 0)
        num += v.where(ok, 0) * w
        den += ok.astype(float) * w
        used += ok.astype(int)
    target = d.score_status.eq("점수 대상")
    return (num / den.where(den > 0)).where(target), used.where(target & den.gt(0), 0)


def lv_axis(resident, worker):
    ok = resident.notna() & worker.notna() & np.isfinite(resident) & np.isfinite(worker) & resident.ge(0) & worker.ge(0) & (resident + worker).gt(0)
    share = (resident / (resident + worker)).where(ok)
    axis = pd.Series(pd.NA, index=resident.index, dtype="string")
    axis.loc[share.gt(.55)] = "L"
    axis.loc[share.lt(.45)] = "V"
    return share, axis


def ep_axis(d):
    valid = d.score_status.eq("점수 대상") & d.sales_quarters.eq(4) & d.ticket.gt(0) & np.isfinite(d.ticket) & ~d.repeated_sales.fillna(False)
    peers = d.industry_code.map(d.loc[valid].groupby("industry_code").size()).fillna(0).astype(int)
    valid &= peers.ge(30)
    pct = pd.Series(np.nan, index=d.index)
    # 55/100*100이 55.00000000000001이 되는 부동소수점 오차로 경계가 P가 되지 않게 한다.
    pct.loc[valid] = (d.loc[valid].groupby("industry_code").ticket.rank(method="average", pct=True) * 100).round(12)
    axis = pd.Series(pd.NA, index=d.index, dtype="string")
    axis.loc[pct.lt(45)] = "E"
    axis.loc[pct.gt(55)] = "P"
    return pct, axis, peers


def matches(d, choices):
    chosen = {a: v for a, v in choices.items() if v}
    mask = pd.Series(True, index=d.index)
    if chosen:
        mask &= d.score_status.eq("점수 대상")
    for axis, value in chosen.items():
        if axis not in AXES or value not in AXES[axis]:
            raise ValueError("지원하지 않는 선호 축")
        mask &= d[axis].eq(value).fillna(False)
    return mask


def explore(d, choices, weights=None, mode="avg", linked=False, limit=None):
    selected = d.loc[matches(d, choices) & d.score_status.eq("점수 대상")].copy()
    actual_mode = ("resident" if choices.get("LV") == "L" else "floating") if linked and choices.get("LV") else mode
    selected["score_total"], selected["n_areas"] = score(selected, weights, actual_mode)
    selected["demand_mode"] = actual_mode
    selected = selected.sort_values(["score_total", "stores", "trdar_code"], ascending=[False, False, True], na_position="last")
    return selected if limit is None else selected.head(limit)


def quiz_result(questions, answers):
    result = {"axes": {}, "choices": {}, "answered": 0, "code": None}
    for axis, letters in AXES.items():
        qs = [q for q in questions if q["axis"] == axis]
        counts = dict.fromkeys(letters, 0)
        for q in qs:
            answer = answers.get(str(q["id"]), answers.get(q["id"]))
            if not answer:
                continue
            if answer not in {o["value"] for o in q["options"]}:
                raise ValueError("문항에 없는 응답")
            counts[answer] += 1
        n = sum(counts.values())
        letter = max(counts, key=counts.get) if n == 5 else None
        status = "미완료" if n < 5 else "뚜렷" if counts[letter] >= 4 else "경계"
        result["axes"][axis] = {"counts": counts, "answered": n, "letter": letter, "status": status}
        result["choices"][axis] = letter if status == "뚜렷" else ""
        result["answered"] += n
    if result["answered"] == 15:
        result["code"] = "".join(result["axes"][axis]["letter"] for axis in AXES)
    return result
