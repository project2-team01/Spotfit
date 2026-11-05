"""기존 STEP 2·3 최종 가공본을 팀원이 바로 열 수 있는 ZIP으로 공유한다.

계산식이나 원본은 바꾸지 않는다. 전체 연도 CSV만 기존 Parquet에서 추가 추출한다.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import shutil
import zipfile


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "seoul-commercial-analysis/data/processed/park_step23"
DEST = HERE / "data"
ARCHIVE = "park_step23_2025_v0.1.zip"
SOURCE_NAMES = [
    "market_industry_features_2025.parquet",
    "market_industry_features_2025q4.csv",
    "market_quarter_context_2025.parquet",
    "market_quarter_context_2025.csv",
    "annual_industry_variability_2025.parquet",
    "annual_industry_variability_2025.csv",
    "semas_native_industry_2025q4.parquet",
    "semas_native_industry_2025q4.csv",
    "semas_all_memberships_industry_2025q4.parquet",
    "semas_all_memberships_industry_2025q4.csv",
    "feature_examples_2025q4.csv",
]
KEYS = {
    "market_industry_features_2025": ["quarter_code", "market_code", "industry_code"],
    "market_industry_features_2025q4": ["quarter_code", "market_code", "industry_code"],
    "market_quarter_context_2025": ["quarter_code", "market_code"],
    "annual_industry_variability_2025": ["market_code", "industry_code"],
    "semas_native_industry_2025q4": ["market_code", "semas_industry_code"],
    "semas_all_memberships_industry_2025q4": ["market_code", "semas_industry_code"],
    "feature_examples_2025q4": ["quarter_code", "market_code", "industry_code"],
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_info(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, sum(1 for _ in reader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    import pandas as pd

    DEST.mkdir(exist_ok=True)
    work = HERE / "outputs/share_package"
    work.mkdir(parents=True, exist_ok=True)
    source_paths = [SOURCE / name for name in SOURCE_NAMES]
    before = {p.name: sha256(p) for p in source_paths}
    tables = {}
    for p in source_paths:
        if p.suffix == ".parquet":
            tables[p.stem] = pd.read_parquet(p)
    panel = tables["market_industry_features_2025"]
    assert len(panel) == 304775 and len(panel.columns) == 84
    assert int(panel["sales_observed"].sum()) == 85732
    assert not panel.duplicated(KEYS["market_industry_features_2025"]).any()
    assert len(tables["market_quarter_context_2025"]) == 6600
    assert len(tables["annual_industry_variability_2025"]) == 77694
    tables["market_industry_features_2025q4"] = panel.loc[
        panel["quarter_code"].eq("20254")
    ].reset_index(drop=True)
    assert len(tables["market_industry_features_2025q4"]) == 75985
    example_keys = pd.read_csv(
        SOURCE / "feature_examples_2025q4.csv",
        usecols=KEYS["feature_examples_2025q4"], dtype="string", encoding="utf-8-sig",
    )
    tables["feature_examples_2025q4"] = example_keys.merge(
        tables["market_industry_features_2025q4"],
        on=KEYS["feature_examples_2025q4"], how="left", validate="one_to_one",
    )[panel.columns]

    full_csv = work / "market_industry_features_2025.csv"
    panel.to_csv(full_csv, index=False, encoding="utf-8-sig")
    paths = source_paths + [full_csv]
    entries = []
    for p in paths:
        if p.suffix == ".parquet":
            frame = tables[p.stem]
            header, rows = frame.columns.tolist(), len(frame)
        else:
            header, rows = csv_info(p)
            if p.stem in tables:
                expected = tables[p.stem]
                assert header == expected.columns.tolist(), p.name
                assert rows == len(expected), p.name
                read_types = {
                    c: expected[c].dtype
                    if pd.api.types.is_numeric_dtype(expected[c]) or pd.api.types.is_bool_dtype(expected[c])
                    else "string" for c in expected.columns
                }
                reread = pd.read_csv(
                    p, encoding="utf-8-sig", dtype=read_types,
                    float_precision="round_trip", low_memory=False,
                )
                expected = expected.reset_index(drop=True)
                pd.testing.assert_frame_equal(reread.isna(), expected.isna())
                for c in expected.columns:
                    valid = expected[c].notna()
                    left, right = reread.loc[valid, c], expected.loc[valid, c]
                    numeric = pd.api.types.is_numeric_dtype(right) or pd.api.types.is_bool_dtype(right)
                    if not numeric:
                        left, right = left.astype("string"), right.astype("string")
                    elif p != full_csv and pd.api.types.is_float_dtype(right):
                        # 원래 csv()의 float_format='%.10g' 출력 규칙과 정확히 대조한다.
                        right = right.map(lambda value: float(format(value, ".10g")))
                    pd.testing.assert_series_equal(
                        left.reset_index(drop=True), right.reset_index(drop=True),
                        check_dtype=False, check_categorical=False,
                        check_exact=True,
                    )
        # 키 이름은 저장된 실제 스키마를 기준으로 확인한다.
        keys = KEYS.get(p.stem, [])
        assert all(c in header for c in keys), p.name
        entries.append({
            "path": "processed/" + p.name,
            "bytes": p.stat().st_size, "sha256": sha256(p),
            "rows": rows, "columns": len(header),
            "column_names": header, "key_columns": keys,
        })

    manifest = {
        "package": ARCHIVE, "version": "v0.1",
        "shared_on": "2026-11-05", "analysis_period": "2025Q1-Q4",
        "analysis_generated_at": json.loads((HERE / "reports/run_summary.json").read_text(encoding="utf-8"))["generated_at"],
        "source_repository": "project2-team01/Spotfit",
        "source_commit": args.source_commit,
        "scope": "Existing final processed tables, plus a full-year CSV exported from the unchanged Parquet. Raw and interim files are not included.",
        "csv_encoding": "utf-8-sig", "csv_missing_values": "empty fields; not zero",
        "csv_precision": "Existing CSVs retain the original float_format='%.10g' export (10 significant digits) and are checked exactly against Parquet values formatted the same way. Integer values are checked exactly without rounding. The new full-year CSV is checked exactly against stored Parquet values without this rounding.",
        "identifier_columns": "Read *_code columns as text. Parquet preserves stored dtypes.",
        "checks": {
            "panel_rows": len(panel), "panel_columns": len(panel.columns),
            "sales_observed_rows": int(panel["sales_observed"].sum()),
            "panel_key_duplicates": int(panel.duplicated(KEYS["market_industry_features_2025"]).sum()),
            "csv_parquet_round_trip": "passed for all source tables, Q4 panel subset and sample, using each CSV's documented export precision",
            "existing_processed_files_unchanged": True,
        },
        "files": entries,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (DEST / "MANIFEST.json").write_text(manifest_text, encoding="utf-8")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=["path", "rows", "columns", "bytes", "sha256"])
    writer.writeheader()
    writer.writerows({k: item[k] for k in writer.fieldnames} for item in entries)
    manifest_csv = out.getvalue().encode("utf-8-sig")
    (DEST / "MANIFEST.csv").write_bytes(manifest_csv)

    # ZIP 내부 시간은 분석 시점으로 고정해 같은 입력의 재포장 결과를 안정화한다.
    def add_file(z, name, path):
        info = zipfile.ZipInfo(name, date_time=(2026, 11, 2, 22, 26, 44))
        info.compress_type = zipfile.ZIP_DEFLATED
        with path.open("rb") as src, z.open(info, "w", force_zip64=True) as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)

    zip_path = DEST / ARCHIVE
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in paths:
            add_file(z, "processed/" + p.name, p)
        for name in ["feature_dictionary.csv", "output_column_dictionary.csv", "input_checksums.csv", "run_summary.json", "analysis_review_evidence.json"]:
            add_file(z, "metadata/" + name, HERE / "reports" / name)
        add_file(z, "metadata/industry_crosswalk.csv", HERE / "config/industry_crosswalk.csv")
        add_file(z, "README.md", DEST / "README.md")
        add_file(z, "MANIFEST.json", DEST / "MANIFEST.json")
        add_file(z, "MANIFEST.csv", DEST / "MANIFEST.csv")
    assert zip_path.stat().st_size < 50 * 1024 * 1024, "Use a release asset if the package grows beyond 50 MiB"
    assert before == {p.name: sha256(p) for p in source_paths}
    (DEST / "checksums.sha256").write_text(sha256(zip_path) + "  " + ARCHIVE + "\n", encoding="utf-8")
    print(json.dumps({"archive": ARCHIVE, "bytes": zip_path.stat().st_size, "table_files": len(entries), "panel_rows": len(panel), "csv_parquet_round_trip": "passed"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
