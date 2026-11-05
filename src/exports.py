import csv
import json
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd


# REQUIRED COLUMNS
FIELDS = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]
FLOAT_FIELDS = ["lifeExp", "gdpPercap"]


# COMPARE CLEANED DATASETS
def compare_tables(tables: list) -> list:
    """Compare four cleaned datasets and return canonical records."""

    if len(tables) != 4:
        raise ValueError("Exactly four datasets are required.")

    datasets = []

    for table in tables:
        records = {}

        for row in table:
            if any(field not in row for field in FIELDS):
                raise ValueError("A record has missing columns.")

            key = (row["country"], row["year"])

            if key in records:
                raise ValueError(f"Duplicate key: {key}")

            records[key] = row

        datasets.append(records)

    reference = datasets[0]

    for i in range(1, 4):
        current = datasets[i]

        if set(reference) != set(current):
            raise ValueError(f"Dataset {i + 1} has different keys.")

        for key in reference:
            for field in FIELDS:
                value1 = reference[key][field]
                value2 = current[key][field]

                if field in FLOAT_FIELDS:
                    match = np.isclose(value1, value2, rtol=0, atol=1e-8)
                else:
                    match = value1 == value2

                if not match:
                    raise ValueError(f"Dataset {i + 1}: {field} mismatch at {key}")

    canonical = []

    for key in sorted(reference):
        row = {field: reference[key][field] for field in FIELDS}
        canonical.append(row)

    return canonical


# EXPORT CANONICAL DATASET
def export_canonical(canonical: list, output_folder: str) -> None:
    """Export canonical records into four file formats."""

    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(canonical, columns=FIELDS)

    df.to_csv(folder / "canonical.csv", index=False)
    df.to_excel(folder / "canonical.xlsx", index=False)
    df.to_json(
        folder / "canonical.json",
        orient="records",
        double_precision=15)
    df.to_parquet(folder / "canonical.parquet", index=False)


# REAPPLY DATA TYPES
def apply_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Restore the required data types after reloading."""

    if set(df.columns) != set(FIELDS):
        raise ValueError("Export has missing or extra columns.")

    df = df[FIELDS].copy()

    for field in ["country", "continent"]:
        if df[field].isna().any():
            raise ValueError(f"Missing values in {field}")
        df[field] = df[field].astype(str)

    for field in ["year", "pop"]:
        values = pd.to_numeric(df[field], errors="raise")

        if values.isna().any():
            raise ValueError(f"Missing values in {field}")

        if not np.isfinite(values).all():
            raise ValueError(f"Invalid values in {field}")

        if not (values % 1 == 0).all():
            raise ValueError(f"Fractional values in {field}")

        df[field] = values.astype("int64")

    for field in FLOAT_FIELDS:
        values = pd.to_numeric(df[field], errors="raise")

        if values.isna().any():
            raise ValueError(f"Missing values in {field}")

        if not np.isfinite(values).all():
            raise ValueError(f"Invalid values in {field}")

        df[field] = values.astype(float)

    return df


# RELOAD AND CHECK EXPORTED FILES
def reload_and_check(canonical: list, output_folder: str) -> bool:
    """Reload four exports and compare them with canonical records."""

    folder = Path(output_folder)

    original = apply_schema(pd.DataFrame(canonical, columns=FIELDS))
    original = original.sort_values(["country", "year"]).reset_index(drop=True)

    files = {
        "csv": pd.read_csv(folder / "canonical.csv"),
        "xlsx": pd.read_excel(folder / "canonical.xlsx"),
        "json": pd.read_json(folder / "canonical.json"),
        "parquet": pd.read_parquet(folder / "canonical.parquet")}

    for format_name, data in files.items():
        data = apply_schema(data)
        data = data.sort_values(["country", "year"]).reset_index(drop=True)

        if len(data) != len(original):
            raise ValueError(f"{format_name}: row count mismatch")

        for field in FIELDS:
            if field in FLOAT_FIELDS:
                match = np.isclose(
                    original[field].to_numpy(),
                    data[field].to_numpy(),
                    rtol=0,
                    atol=1e-8).all()
            else:
                match = original[field].equals(data[field])

            if not match:
                raise ValueError(f"{format_name}: {field} does not match")

    return True


# AUDIT 
def write_csv_report(filename: str, records: list, columns: list) -> None:
    """Save a list of records as a CSV report."""

    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def write_audit_log(records: list, output_folder: str) -> None:
    """Save audit events."""

    write_csv_report(
        str(Path(output_folder) / "audit_log.csv"),
        records,
        ["step", "status", "details"])


def write_validation_report(records: list, output_folder: str) -> None:
    """Save validation results."""

    write_csv_report(
        str(Path(output_folder) / "validation.csv"),
        records,
        ["check", "status", "details"])


# STAGING
def create_staging_folder(output_folder: str) -> str:
    """Create a temporary folder for new outputs."""

    output_path = Path(output_folder)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = tempfile.mkdtemp(
        prefix="week10_staging_",
        dir=output_path.parent)

    return staging


def finalize_outputs(staging_folder: str, output_folder: str) -> None:
    """Replace old outputs only after all checks succeed."""

    staging = Path(staging_folder)
    output = Path(output_folder)
    backup = output.with_name(output.name + "_backup")

    if not staging.is_dir():
        raise FileNotFoundError("Staging folder does not exist.")

    if backup.exists():
        raise FileExistsError("Backup folder already exists.")

    try:
        if output.exists():
            output.rename(backup)

        staging.rename(output)

    except Exception:
        if backup.exists() and not output.exists():
            backup.rename(output)
        raise

    if backup.exists():
        shutil.rmtree(backup)


# FAILURE REPORT
def write_failure_report(error: Exception, output_folder: str) -> None:
    """Save failure details without replacing successful outputs."""

    path = Path(output_folder)
    path.parent.mkdir(parents=True, exist_ok=True)

    report = path.with_name(path.name + "_failed_validation.csv")

    write_csv_report(
        str(report),
        [{"check": "pipeline", "status": "FAIL", "details": str(error)}],
        ["check", "status", "details"])
