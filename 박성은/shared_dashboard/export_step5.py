"""기존 STEP4 웹 데이터에 확정된 STEP5 분석 산출물을 손실 없이 연결한다."""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "step5_personalization"
OUT = HERE / "dist"


def records(path):
    return json.loads(pd.read_csv(path).to_json(orient="records", force_ascii=False))


def main():
    d = pd.read_parquet(SOURCE / "data/상권업종_유형후보_2025.parquet")
    columns = ["trdar_code", "LV", "EP", "SD", "candidate_type", "known_axes", "type_status",
               "LV_reason", "EP_reason", "SD_reason", "hold_reason", "resident_share_proxy", "ticket",
               "ticket_pct", "sales_month_cv", "floating_cv", "dynamism_index", "ep_peers", "sd_peers",
               "monthly_n", "floating_n", "repeated_sales"]
    for code, group in d.groupby("industry_code"):
        path = OUT / "data" / f"{code}.json"
        p = json.loads(path.read_text(encoding="utf-8"))
        assert set(group.trdar_code) == {r[0] for r in p["rows"]}
        p["step5_columns"] = columns
        p["step5_rows"] = json.loads(group[columns].to_json(orient="values", force_ascii=False, double_precision=12))
        path.write_text(json.dumps(p, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    meta = json.loads((OUT / "data/meta.json").read_text(encoding="utf-8"))
    s = json.loads((SOURCE / "report/summary.json").read_text(encoding="utf-8"))
    s["config"] = json.loads((SOURCE / "types.json").read_text(encoding="utf-8"))
    s["sensitivity"] = records(SOURCE / "data/임계값_민감도.csv")
    s["hold_reasons"] = records(SOURCE / "data/축별_보류사유.csv")
    s["industry_coverage"] = records(SOURCE / "data/업종별_분류가능여부.csv")
    s["source_commit"] = "da58fc59b6fc4498c533c6890c24cee006aa8b72"
    meta["step5"] = s
    (OUT / "data/meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for source, target in [("report/STEP5_분석보고서.md", "step5-analysis.md"),
                           ("data/8유형_정의와_결과.csv", "step5-types.csv"),
                           ("data/임계값_민감도.csv", "step5-sensitivity.csv")]:
        shutil.copyfile(SOURCE / source, OUT / "assets" / target)
    # 기존 Python 탐색기를 기준으로 브라우저의 일치 조건·정렬·수요 연결을 검증한다.
    sys.path.insert(0, str(SOURCE))
    from analyze_step5 import explore
    fixtures = []
    unsupported = next(i["업종_코드"] for i in meta["industries"] if not i["매출_제공_업종"])
    unscored = next(i["업종_코드"] for i in meta["industries"] if not i["점수_생성"])
    for industry in dict.fromkeys(["CS100010", "CS100001", "CS200001", "CS300001", unsupported, unscored]):
        for code in s["types"]:
            for partial in [False, True]:
                for linked in [False, True]:
                    result = explore(d, industry, code, allow_partial=partial, demand_link=linked)
                    fixtures.append({"industry": industry, "code": code, "partial": partial, "linked": linked,
                                     "expected": json.loads(result.to_json(orient="records", force_ascii=False, double_precision=12))})
    (HERE / "step5-fixtures.json").write_text(json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"rows": len(d), "candidates": int(d.candidate_type.notna().sum()), "fixtures": len(fixtures)}))


if __name__ == "__main__":
    main()
