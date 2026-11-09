"""Python 처리·직렬화 시간을 측정한다. 브라우저 렌더링 시간과 구분한다."""
import json
import statistics
import time
from pathlib import Path

import views as v


def timed(fn, n=5):
    durations = []
    for _ in range(n):
        start = time.perf_counter()
        fn()
        durations.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(durations), 3), "samples_ms": [round(x, 3) for x in durations]}


def main():
    v.load_bundle.cache_clear()
    v._scope_cache.cache_clear()
    start = time.perf_counter()
    b = v.load_bundle()
    cold_load = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    s = v.filter_scope(b, "CS100010")
    cold_query = (time.perf_counter() - start) * 1000
    pal = v.palette(None)
    selected = v.choose_code(None, s)
    results = {"measurement": "Python 처리와 직렬화 시간",
               "cold_load_ms": round(cold_load, 3), "first_query_ms": round(cold_query, 3), "areas": len(s),
               "cached_query": timed(lambda: v.filter_scope(b, "CS100010")),
               "uncached_query": timed(lambda: v._filter_scope_uncached(b, "CS100010")),
               "altair_build_serialize": timed(lambda: v.map_chart(b, s, selected, pal, seoul=s, width=900).to_dict()),
               "plotly_build_serialize": timed(lambda: v.map_plotly(b, s, selected, pal, seoul=s).to_json()),
               "geometry_bytes": (v.STAGE4 / "map_geometry.json").stat().st_size}
    results["measurement"] = "Python 처리와 차트 직렬화. 브라우저 렌더링·네트워크 시간 제외. 동일 환경에서 5회 측정."
    (Path(__file__).resolve().parent / "report/performance.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
