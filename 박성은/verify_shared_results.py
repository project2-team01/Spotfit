"""원본·pandas 없이 공유 ZIP의 해시·CSV 행수·열수·키를 확인한다."""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path(__file__).resolve().parent / "data/park_step23_2025_v0.1.zip")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    path = args.archive
    checksum_path = path.parent / "checksums.sha256"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    assert h.hexdigest() == checksum_path.read_text(encoding="utf-8").split()[0], "ZIP SHA-256 mismatch"
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, "ZIP CRC error"
        manifest = json.loads(z.read("MANIFEST.json"))
        assert json.loads((path.parent / "MANIFEST.json").read_text(encoding="utf-8")) == manifest, "External manifest differs"
        assert len(z.namelist()) == len(set(z.namelist())), "Duplicate ZIP entries"
        csv_tables = 0
        for item in manifest["files"]:
            data = z.read(item["path"])
            assert len(data) == item["bytes"], item["path"]
            assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
            if item["path"].endswith(".csv"):
                reader = csv.reader(io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline=""))
                header = next(reader)
                assert header == item["column_names"]
                key_indexes = [header.index(c) for c in item["key_columns"]]
                keys = set()
                rows = 0
                for row in reader:
                    assert len(row) == item["columns"], item["path"]
                    if key_indexes:
                        key = tuple(row[i] for i in key_indexes)
                        assert all(key) and key not in keys, (item["path"], key)
                        keys.add(key)
                    rows += 1
                assert rows == item["rows"], (item["path"], rows)
                csv_tables += 1
    result = {"archive": path.name, "sha256": h.hexdigest(), "table_files_verified": len(manifest["files"]), "csv_tables_verified": csv_tables, "status": "passed"}
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
