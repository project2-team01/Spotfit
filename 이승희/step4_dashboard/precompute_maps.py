# -*- coding: utf-8 -*-
"""업종별 '상권 찾기' 기본 화면 지도를 미리 만들어 data/map_cache/ 에 저장한다.

대시보드는 저장된 지도가 있으면 바로 불러오고, 없으면 처음 볼 때 만들어 저장한다.
이 스크립트는 그 '처음' 시간을 미리 써 두는 것이다. 몇 번을 실행해도 이미 있는 저장본은 건너뛴다.

실행 (팀 저장소 루트에서):
    uv run --project "이승희/step4_dashboard" python "이승희/step4_dashboard/precompute_maps.py"
    uv run --project "이승희/step4_dashboard" python "이승희/step4_dashboard/precompute_maps.py" --dark   # 어두운 화면용도 함께
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import views as v  # noqa: E402
from build_scores import DEFAULT_WEIGHTS  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="업종별 기본 화면 지도를 미리 저장")
    ap.add_argument("--dark", action="store_true", help="어두운 화면(다크 모드)용 지도도 함께 저장")
    args = ap.parse_args()
    themes = ["light", "dark"] if args.dark else ["light"]

    bundle = v.load_bundle()
    codes = list(bundle.industries.sort_values("업종명")["업종_코드"])
    made = loaded = 0
    start = time.perf_counter()
    for i, code in enumerate(codes, 1):
        scope = v.filter_scope(bundle, code, None, None, DEFAULT_WEIGHTS, "avg")
        if scope.empty:
            continue
        selected = v.choose_code(None, scope)  # 대시보드 첫 화면과 같은 '고른 상권'
        for theme in themes:
            _, _, source = v.map_views(bundle, code, [], [], DEFAULT_WEIGHTS, "avg", selected, theme, scope=scope, seoul=scope)
            made += source == "새로 계산"
            loaded += source != "새로 계산"
        if i % 10 == 0 or i == len(codes):
            print(f"  {i}/{len(codes)} 업종 처리 ({time.perf_counter() - start:.0f}초)")
    files = list(v.MAP_CACHE.glob("*.pkl.gz"))
    size = sum(f.stat().st_size for f in files) / 1e6
    print(f"새로 저장 {made}개 · 이미 있음 {loaded}개 · 저장 폴더 {len(files)}개 파일 {size:.1f}MB ({v.MAP_CACHE.relative_to(HERE.parents[1]).as_posix()})")


if __name__ == "__main__":
    main()
