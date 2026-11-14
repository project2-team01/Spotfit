"""검증된 팀 점수표를 브라우저가 읽는 업종별 작은 JSON으로 내보낸다."""
import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "step4_dashboard"
TEAM = SOURCE.parents[1] / "김지영/claude_dashboard/data"
OUT = HERE / "dist"


def main():
    (OUT / "data").mkdir(exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)
    scores = pd.read_parquet(SOURCE / "data/상권_업종_비교점수_2025.parquet")
    quarters = pd.read_parquet(SOURCE / "data/quarter_mart.parquet")
    columns = ["trdar_code", "trdar_name", "gu_name", "trdar_type", "stores", "score_sales", "score_comp", "score_stab",
               "score_dem_avg", "score_dem_floating", "score_dem_worker", "score_dem_resident", "sales_month", "sales_area_status",
               "close_pct_shrunk", "closes", "floating_density", "worker_density", "resident_density", "comp_ratio",
               "franchise_pct", "score_status", "score_total_default", "dem_avg_n"]
    qcols = ["trdar_code", "quarter", "sales_month", "open_count", "close_count", "qoq_raw", "qoq_winsor"]
    for code, group in scores.groupby("industry_code"):
        payload = {"columns": columns, "rows": json.loads(group[columns].to_json(orient="values", force_ascii=False, double_precision=12))}
        q = quarters.loc[quarters.industry_code.eq(code), qcols]
        payload["quarter_columns"] = qcols
        payload["quarters"] = json.loads(q.to_json(orient="values", force_ascii=False, double_precision=12))
        (OUT / "data" / f"{code}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    industries = pd.read_csv(SOURCE / "data/업종별_점수_가능여부.csv", dtype={"업종_코드": str})
    meta = json.loads((SOURCE / "data/stage4_meta.json").read_text(encoding="utf-8"))
    meta["industries"] = json.loads(industries.sort_values("업종명").to_json(orient="records", force_ascii=False))
    meta["districts"] = sorted(scores.gu_name.unique())
    meta["design"] = json.loads(pd.read_csv(SOURCE / "data/점수_설계표.csv").fillna("").to_json(orient="records", force_ascii=False))
    meta["freshness"] = json.loads((TEAM / "meta.json").read_text(encoding="utf-8"))["freshness"]
    (OUT / "data/meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "data/geometry.json").write_bytes((SOURCE / "data/map_geometry.json").read_bytes())
    (OUT / "assets/plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    (OUT / "assets/analysis.md").write_bytes((SOURCE / "report/분석_검증_보고서.md").read_bytes())
    print(f"공유용 데이터 생성: {len(industries)}개 업종, {len(scores):,}개 조합")
    print(f"전체 크기: {sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()) / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()
