# -*- coding: utf-8 -*-
"""
[샘플] 김지영 STEP 4 대시보드(김지영/step4_dashboard)의 표를 이승희 자치구 지도(../../pixel_theme/pixel_map.py)에 넘기는 연결 파일.

- 김지영 폴더 파일은 읽기만 한다. 불러올 때 .pyc가 김지영 폴더에 생기지 않게 한다(sys.dont_write_bytecode).
- 김지영 표의 열 이름을 지도가 쓰는 이름으로 바꿀 뿐, 점수는 다시 계산하지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                     # 팀 저장소 루트 (이승희/design_samples/integrated_dashboard 의 세 단계 위)
JY_STEP4 = REPO / "김지영" / "step4_dashboard"
PIXEL = REPO / "이승희" / "pixel_theme"

sys.dont_write_bytecode = True             # 김지영 폴더에 __pycache__를 만들지 않는다
for p in (JY_STEP4, PIXEL):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# 김지영 표 열 이름 → 자치구 지도 열 이름
# total = 김지영 대시보드에서 지금 가중치로 다시 계산한 종합 점수 (score_total은 기본 가중치 값이라 쓰지 않는다)
RENAME = {"total": "score_total", "score_competition": "score_comp", "score_stability": "score_stab",
          "score_demand": "score_dem", "competition": "comp_ratio", "status": "score_status"}
_MEM: dict[str, tuple[str, str]] = {}
MEM_LIMIT = 30


def to_pixel(rows):
    """김지영 industry_rows 표를 자치구 지도 입력 모양으로 바꾼다."""
    return rows.drop(columns=["score_total"], errors="ignore").rename(columns=RENAME)


def pixel_map(bundle, industry_code: str, industry_name: str, rows, all_rows, weights: dict, where: str = "") -> tuple[str, str]:
    """(자치구 지도 HTML, 출처 '메모리'·'새로 계산'). rows = 지금 필터 안의 상권, all_rows = 서울 전체(순위·중앙값 기준)."""
    import pixel_map as px   # folium은 지도를 처음 그릴 때만 불러온다

    key = json.dumps([industry_code, where, sorted(rows["trdar_code"].astype(str)), {k: float(v) for k, v in weights.items()}],
                     ensure_ascii=False, sort_keys=True)
    if key in _MEM:
        return _MEM[key][0], "메모리"
    title = f"{industry_name} · 자치구별 종합 점수" + (f" ({where})" if where else "")
    html_text = px.gu_map_html(to_pixel(rows), to_pixel(all_rows), bundle.geometry, title, upgrade=True)
    if len(_MEM) >= MEM_LIMIT:
        _MEM.pop(next(iter(_MEM)))
    _MEM[key] = (html_text, "새로 계산")
    return html_text, "새로 계산"
