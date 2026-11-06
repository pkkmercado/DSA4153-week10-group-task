"""Command-line entry point for four-format recovery and validation."""
import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
import pandas as pd

from src.csv_excel_readers import read_csv_records, read_excel_records
from src.json_parquet_readers import read_json_records, read_parquet_records
from src.normalize import map_columns, normalize_records
from src.validation import ValidationRun, process_reader_records, deduplicate_and_check_conflicts
from src.analysis import run_analysis, write_analysis_outputs
from src.exports import (compare_tables, export_canonical, reload_and_check,
                         create_staging_folder, finalize_outputs,
                         write_audit_log, write_validation_report, write_failure_report)

READERS = {"csv": read_csv_records, "xlsx": read_excel_records,
           "json": read_json_records, "parquet": read_parquet_records}


def write_rows(path, rows, columns):
    """Write reports with stable column order, including when no rows exist."""
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(data_dir="data", output_dir="outputs", manifest_path=None):
    data_dir = Path(data_dir).resolve()
    output_dir = Path(output_dir).resolve()
    manifest_path = Path(manifest_path).resolve() if manifest_path else data_dir / "manifest.json"
    staging = None

    try:
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)

        validator = ValidationRun(
            allowed_continents=set(manifest["allowed_continents"]),
            allowed_years=set(manifest["allowed_years"]),
        )
        expected = manifest["expected_per_file"]
        cleaned_tables, quarantine, duplicate_log = [], [], []
        audit, checks = [], []

        for spec in manifest["files"]:
            fmt = spec["format"]
            if fmt not in READERS:
                raise ValueError(f"Unsupported format: {fmt}")
            settings = {}
            if fmt == "csv":
                settings = {"encoding": spec.get("encoding", "cp1252"),
                            "delimiter": spec.get("separator", ";"),
                            "comment_prefix": spec.get("comment_prefix")}
            elif fmt == "xlsx":
                settings = {"sheet": spec.get("sheet_name", "observations")}
            elif fmt == "json":
                settings = {"record_path": spec.get("record_path", "records"),
                            "encoding": spec.get("encoding", "utf-8")}

            path = data_dir / spec["file"]
            header, raw = READERS[fmt](path, settings)
            mapped = map_columns(header, raw, spec["source_to_canonical"], path.name)
            normalized = normalize_records(mapped)
            valid, rejected = process_reader_records(normalized, validator, path.name)
            cleaned, duplicates = deduplicate_and_check_conflicts(valid)
            cleaned_tables.append(cleaned)
            quarantine.extend(rejected)
            duplicate_log.extend(duplicates)

            counts = {"raw_rows": len(raw), "rejected_rows": len(rejected),
                      "valid_before_deduplication": len(valid),
                      "exact_duplicates_removed": len(duplicates),
                      "canonical_rows": len(cleaned)}
            for name, actual in counts.items():
                target = expected[name]
                passed = actual == target
                checks.append({"check": f"{fmt}.{name}",
                               "status": "PASS" if passed else "FAIL",
                               "details": f"expected={target}; actual={actual}"})
                if not passed:
                    raise ValueError(f"{path.name}: {name}: expected {target}, got {actual}")
            audit.append({"step": f"read_validate_{fmt}", "status": "PASS",
                          "details": str(counts)})

        canonical = compare_tables(cleaned_tables)
        if len(canonical) != expected["canonical_rows"]:
            raise ValueError("Canonical record count does not match manifest")
        checks.append({"check": "four_format_comparison", "status": "PASS",
                       "details": f"{len(canonical)} matching canonical rows"})
        audit.append({"step": "compare_four_formats", "status": "PASS",
                      "details": f"{len(canonical)} matching rows"})

        analysis = run_analysis(pd.DataFrame(canonical), controls=manifest.get("controls"))
        for item in analysis["checks"]:
            passed = bool(item["pass"])
            checks.append({"check": item["check"],
                           "status": "PASS" if passed else "FAIL",
                           "details": f"expected={item['expected']}; actual={item['actual']}"})
            if not passed:
                raise ValueError(f"Analysis check failed: {item['check']}")
        audit.append({"step": "analysis", "status": "PASS",
                      "details": "All analysis checks passed"})

        staging = Path(create_staging_folder(output_dir))
        export_canonical(canonical, staging)
        write_analysis_outputs(analysis, staging)
        write_rows(staging / "quarantine.csv", quarantine,
                   ["source_file", "source_record", "reason", "country", "continent",
                    "year", "lifeExp", "pop", "gdpPercap"])
        write_rows(staging / "duplicate_log.csv", duplicate_log,
                   ["source_file", "source_record", "country", "year"])
        reload_and_check(canonical, staging)
        checks.append({"check": "export_reload", "status": "PASS",
                       "details": "All four exported files match canonical data"})
        audit.append({"step": "export_reload", "status": "PASS",
                      "details": "CSV, XLSX, JSON, and Parquet reloaded successfully"})
        write_validation_report(checks, staging)
        write_audit_log(audit, staging)
        finalize_outputs(staging, output_dir)
        staging = None
        print(f"SUCCESS: {len(canonical)} canonical records. Outputs: {output_dir}")
        return True

    except Exception as error:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        write_failure_report(error, output_dir)
        print(f"FAILED: {error}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="Four-format data recovery and validation")
    parser.add_argument("--data", default="data", help="Input data directory")
    parser.add_argument("--output", default="outputs", help="Final output directory")
    parser.add_argument("--manifest", default=None, help="Manifest JSON path")
    args = parser.parse_args()
    try:
        run_pipeline(args.data, args.output, args.manifest)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
