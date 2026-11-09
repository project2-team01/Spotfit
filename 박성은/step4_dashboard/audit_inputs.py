"""공통 입력의 행 수와 분모를 확인한다. 입력 파일은 변경하지 않는다."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STEP = REPO / "김지영/step2_3/data"
DATA = REPO / "김지영/claude_dashboard/data"


def audit():
    ids = {"quarter": str, "trdar_code": str, "industry_code": str}
    fact = pd.read_csv(STEP / "fact_trdar_industry_quarter.csv.gz", dtype=ids,
                       usecols=[*ids, "store_count", "close_count", "main_analysis_eligible"])
    annual = pd.read_csv(STEP / "annual_features.csv.gz", dtype=ids)
    context = pd.read_csv(STEP / "trdar_quarter_context.csv.gz", dtype=ids)
    dim = pd.read_csv(STEP / "dim_trdar.csv.gz", dtype=ids)
    counts = dict(fact=len(fact), annual=len(annual), context=len(context), dim=len(dim))
    assert counts == dict(fact=304775, annual=77694, context=6600, dim=1650), counts
    assert set(fact.quarter) == {"20251", "20252", "20253", "20254"}
    assert fact.industry_code.nunique() == 100
    assert not fact.duplicated(list(ids)).any()
    f = fact.loc[fact.main_analysis_eligible]
    g = f.groupby(["trdar_code", "industry_code"]).agg(
        stock=("store_count", "sum"), closes=("close_count", "sum"))
    g["stores"] = g.stock / 4
    g = g.loc[g.stores > 0].copy()
    rate = g.groupby(level="industry_code").closes.transform("sum") / g.groupby(level="industry_code").stores.transform("sum")
    expected = g.stores * rate
    alpha = float((expected ** 2).sum() / ((g.closes - expected) ** 2 - expected).sum())
    g["shrunk"] = (g.closes + alpha) / (g.stores + alpha / rate.replace(0, np.nan)) * 100
    cells = pd.read_parquet(DATA / "cells.parquet").set_index(["trdar_code", "industry_code"])
    check = g.join(cells[["stores", "close_pct", "close_pct_shrunk"]].rename(columns={"stores": "stores_cached"}), validate="one_to_one")
    assert len(check) == len(cells) and check.stores_cached.notna().all()
    errors = {
        "stores": float((check.stores - check.stores_cached).abs().max()),
        "close_pct": float((check.closes / check.stores * 100 - check.close_pct).abs().max()),
        "shrunk": float((check.shrunk - check.close_pct_shrunk).abs().max()),
    }
    assert max(errors.values()) < 1e-8, errors
    fixed = {}
    for col in ["worker_population", "resident_population", "facility_count"]:
        assert col in context, col
        fixed[col] = int(context.groupby("trdar_code")[col].nunique().gt(1).sum())
        assert fixed[col] == 0, (col, fixed[col])
    return {"rows": counts, "quarters": sorted(fact.quarter.unique()), "industries": 100,
            "tourist_areas": int(dim.is_tourist.sum()), "comparison_areas": int((~dim.is_tourist).sum()),
            "checked_annual_cells": len(check), "shrinkage_alpha": alpha,
            "max_absolute_difference": errors, "static_context_changed_areas": fixed,
            "conclusion": "분기 패널에서 재계산한 4분기 평균 점포·폐업률·축소 추정이 공통 cells와 일치. 검증 후 재사용."}


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
