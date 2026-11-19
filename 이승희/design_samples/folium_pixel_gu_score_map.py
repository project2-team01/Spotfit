# -*- coding: utf-8 -*-
"""
folium 픽셀 아트 자치구 점수 지도 샘플 (디자인 시안, 대시보드에 들어간 채택안).
25개 자치구를 커피-음료 종합 점수(기본 가중치) 중앙값으로 칠하고, 구를 클릭하면 그 구로 확대해 약 400m 점수 칸과 상위 상권을 보여 준다.
지도를 그리는 코드는 STEP 4·5 대시보드와 같은 ../pixel_theme/pixel_map.py 를 쓴다.

실행 (팀 저장소 루트에서):
    uv run --project "이승희/step4_dashboard" python "이승희/design_samples/folium_pixel_gu_score_map.py"
    서울 밖 실루엣을 다시 만들기: outside_pixel.geojson을 지우고 실행 (행정동 경계 원본 필요, 아래 RAW_GEO)
결과:
    이승희/design_samples/folium_pixel_gu_score_map_sample.html  (배경 지도 타일 없음. 글꼴만 인터넷)
필요한 파일: 같은 폴더의 seoul_gu_pixel.geojson (folium_pixel_gu_map.py가 만든 도트 구 모양과 한강), outside_pixel.geojson
"""
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "pixel_theme"))
import pixel_map as px  # noqa: E402

SCORES = REPO / "이승희" / "step4_dashboard" / "data" / "상권_업종_비교점수_2025.parquet"
GEO = REPO / "김지영" / "claude_dashboard" / "data" / "areas.geojson.json"
RAW_GEO = [Path(p) for p in [os.environ.get("SPOTFIT_RAW_GEO", "")] if p] + [
    REPO / "이승희" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson",
    REPO.parent / "PJT2-SpotFit" / "data" / "raw" / "geo" / "HangJeongDong_ver20251231.geojson",   # 팀 저장소 옆 개인 저장소
]
# 실루엣을 그릴 범위 (경도·위도). 대시보드 지도 틀이 가로로 길어(약 2:1) 동서로 넉넉히 잡는다.
AROUND = (126.15, 37.20, 127.85, 37.95)
OUT = HERE / "folium_pixel_gu_score_map_sample.html"
INDUSTRY, INDUSTRY_NAME = "CS100010", "커피-음료"


def outside_silhouettes():
    """서울 주변(경기·인천) 시·군을 같은 400m 격자의 도트 실루엣으로 만들어 px.OUTSIDE_FILE에 저장한다. 이름·점수 없이 모양만 쓴다."""
    if px.OUTSIDE_FILE.exists():
        return
    raw = next((p for p in RAW_GEO if p.exists()), None)
    if raw is None:
        sys.exit("행정동 경계 원본(HangJeongDong_ver20251231.geojson)이 없습니다. 이승희/data/raw/geo/ 에 넣거나 SPOTFIT_RAW_GEO로 위치를 알려 주세요.")
    area = box(*AROUND)
    groups = {}
    for f in json.loads(raw.read_text(encoding="utf-8"))["features"]:
        pr = f["properties"]
        if pr["sido"] == "11":
            continue
        geom = shape(f["geometry"])
        if not geom.intersects(area):
            continue
        # 인천은 하나로, 경기는 시·군 단위로 (고양시덕양구 → 고양시)
        key = "인천" if pr["sidonm"].startswith("인천") else re.match(r"^(.+?[시군])", pr["sggnm"]).group(1)
        groups.setdefault(key, []).append(geom)
    shapes = {k: prep(unary_union(v)) for k, v in groups.items()}
    cells = {k: [] for k in groups}
    x0, y0, x1, y1 = AROUND
    for cx in range(int(np.floor(x0 / px.CELL_LON)), int(np.floor(x1 / px.CELL_LON)) + 1):
        for cy in range(int(np.floor(y0 / px.CELL_LAT)), int(np.floor(y1 / px.CELL_LAT)) + 1):
            c = Point((cx + 0.5) * px.CELL_LON, (cy + 0.5) * px.CELL_LAT)
            k = next((k for k, s in shapes.items() if s.contains(c)), None)
            if k:
                cells[k].append(box(cx * px.CELL_LON, cy * px.CELL_LAT, (cx + 1) * px.CELL_LON, (cy + 1) * px.CELL_LAT))
    feats = [{"type": "Feature", "properties": {"name": k, "cells": len(v)}, "geometry": mapping(unary_union(v).buffer(0))}
             for k, v in sorted(cells.items()) if v]
    px.OUTSIDE_FILE.write_text(json.dumps({"type": "FeatureCollection", "source": raw.name, "around": AROUND, "features": feats},
                                          ensure_ascii=False), encoding="utf-8")
    print(f"[실루엣] {px.OUTSIDE_FILE.name} · 시·군 {len(feats)}개 · 범위 {AROUND}")


def real_gu_boundaries():
    """구 상세 화면 테두리용 실제 자치구 경계를 px.REAL_GU_FILE에 저장한다 (행정동 경계를 구별로 합쳐 조금 단순화)."""
    if px.REAL_GU_FILE.exists():
        return
    raw = next((p for p in RAW_GEO if p.exists()), None)
    if raw is None:
        print("[알림] 행정동 경계 원본이 없어 실제 구 경계를 만들지 않았습니다. 구 상세 화면은 도트 테두리로 그립니다.")
        return
    groups = {}
    for f in json.loads(raw.read_text(encoding="utf-8"))["features"]:
        pr = f["properties"]
        if pr["sido"] == "11":
            groups.setdefault(pr["sggnm"], []).append(shape(f["geometry"]))
    # 0.0002도 ≈ 20m로 단순화: 상권 경계와 겹쳐 볼 때 차이가 눈에 띄지 않을 만큼만 줄인다
    feats = [{"type": "Feature", "properties": {"name": k},
              "geometry": mapping(unary_union(v).simplify(0.0002, preserve_topology=True))} for k, v in sorted(groups.items())]
    text = json.dumps({"type": "FeatureCollection", "source": raw.name, "simplify_deg": 0.0002, "features": feats}, ensure_ascii=False)
    text = re.sub(r"(\d+\.\d{5})\d+", r"\1", text)   # 좌표는 소수 5자리(약 1m)까지
    px.REAL_GU_FILE.write_text(text, encoding="utf-8")
    print(f"[실제 구 경계] {px.REAL_GU_FILE.name} · 구 {len(feats)}개 · {len(text) / 1e3:.0f}KB")


def main():
    outside_silhouettes()
    real_gu_boundaries()
    d = pd.read_parquet(SCORES)   # 상세 카드에 영역 점수·원값을 쓰므로 모든 열을 읽는다
    d = d.loc[d["industry_code"].eq(INDUSTRY)].copy()
    d["score_total"] = d["score_total_default"].where(d["score_status"].eq("점수 대상"))
    d["score_dem"] = d["score_dem_avg"]   # 기본값: 수요 = 세 값 평균 (STEP 4 대시보드 첫 화면과 같음)
    areas = json.loads(GEO.read_text(encoding="utf-8"))
    points = px.points_of(areas)
    # 업그레이드 시안 1단계: 구 색 = 서울 중앙값과의 차이, 이름표·설명에 숫자, 표본 적은 구 점선 (대시보드는 아직 예전 방식)
    px.gu_map(d, d, areas, f"{INDUSTRY_NAME} · 자치구별 종합 점수", brand=True, upgrade=True).save(OUT)
    med = float(d["score_total"].median())
    g = px.gu_summary(px.prepare(d, d, points), med)
    counts = ", ".join(f"{px.DIFF_LABELS[c]} {int((g['cls2'] == c).sum())}" for c in range(4, -1, -1))
    print(f"[완료] {OUT.relative_to(REPO).as_posix()} · 구 {len(g)}개, 중앙값 {g['median'].min():.1f}~{g['median'].max():.1f}, "
          f"서울 중앙값 {med:.1f} · {counts} · 참고용 구 {int(g['small'].sum())}개")


if __name__ == "__main__":
    main()
