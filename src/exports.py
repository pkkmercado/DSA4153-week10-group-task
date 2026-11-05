import csv
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd


# REQUIRED COLUMNS
FIELDS = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]
FLOAT_FIELDS = ["lifeExp", "gdpPercap"]


# CHECK AND RESTORE DATA TYPES
def apply_schema(df):
    """Check columns, values, and data types."""

    if len(df.columns) != len(FIELDS) or set(df.columns) != set(FIELDS):
        raise ValueError("Missing or extra columns.")

    df = df[FIELDS].copy()

    for field in ["country", "continent"]:
        if df[field].isna().any():
            raise ValueError(f"Missing {field}")

        df[field] = df[field].astype(str)

        if df[field].str.strip().eq("").any():
            raise ValueError(f"Empty {field}")

    for field in ["year", "pop"]:
        values = pd.to_numeric(df[field], errors="raise")

        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError(f"Invalid {field}")

        if not (values % 1 == 0).all():
            raise ValueError(f"Fractional {field}")

        df[field] = values.astype("int64")

    for field in FLOAT_FIELDS:
        values = pd.to_numeric(df[field], errors="raise")

        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError(f"Invalid {field}")

        df[field] = values.astype(float)

    if df.duplicated(["country", "year"]).any():
        raise ValueError("Duplicate country-year key")

    return df


# COMPARE CLEANED DATASETS
def compare_tables(tables):
    """Compare four datasets and return canonical records."""

    if len(tables) != 4:
        raise ValueError("Exactly four datasets are required.")

    datasets = []

    for table in tables:
        df = apply_schema(pd.DataFrame(table, columns=FIELDS))
        records = {}

        for row in df.to_dict("records"):
            key = (row["country"], row["year"])
            records[key] = row

        datasets.append(records)

    reference = datasets[0]

    for i in range(1, 4):
        current = datasets[i]

        if set(reference) != set(current):
            raise ValueError(f"Dataset {i + 1}: keys do not match")

        for key in reference:
            for field in FIELDS:
                value1 = reference[key][field]
                value2 = current[key][field]

                if field in FLOAT_FIELDS:
                    match = np.isclose(
                        value1, value2, rtol=0, atol=1e-8
                    )
                else:
                    match = value1 == value2

                if not match:
                    raise ValueError(
                        f"Dataset {i + 1}: {field} mismatch at {key}"
                    )

    canonical = []

    for key in sorted(reference):
        canonical.append(reference[key])

    return canonical


# EXPORT CANONICAL DATASET
def export_canonical(canonical, output_folder):
    """Save canonical records in four formats."""

    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)

    df = apply_schema(pd.DataFrame(canonical, columns=FIELDS))

    df.to_csv(folder / "canonical.csv", index=False)
    df.to_excel(folder / "canonical.xlsx", index=False)
    df.to_json(
        folder / "canonical.json",
        orient="records",
        double_precision=15
    )
    df.to_parquet(folder / "canonical.parquet", index=False)


# RELOAD AND CHECK EXPORTS
def reload_and_check(canonical, output_folder):
    """Reload four exports and check against canonical."""

    folder = Path(output_folder)

    original = apply_schema(pd.DataFrame(canonical, columns=FIELDS))
    original = original.sort_values(["country", "year"]).reset_index(drop=True)

    files = {
        "csv": pd.read_csv(folder / "canonical.csv"),
        "xlsx": pd.read_excel(folder / "canonical.xlsx"),
        "json": pd.read_json(folder / "canonical.json", precise_float=True),
        "parquet": pd.read_parquet(folder / "canonical.parquet")
    }

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
                    atol=1e-8
                ).all()
            else:
                match = original[field].equals(data[field])

            if not match:
                raise ValueError(f"{format_name}: {field} mismatch")

    return True


# SAVE CSV REPORT
def write_csv_report(filename, records, columns):
    """Save audit or validation records."""

    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file, fieldnames=columns, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(records)


# AUDIT LOG
def write_audit_log(records, output_folder):
    write_csv_report(
        str(Path(output_folder) / "audit_log.csv"),
        records,
        ["step", "status", "details"]
    )


# VALIDATION REPORT
def write_validation_report(records, output_folder):
    write_csv_report(
        str(Path(output_folder) / "validation.csv"),
        records,
        ["check", "status", "details"]
    )


# CREATE STAGING FOLDER
def create_staging_folder(output_folder):
    """Create a temporary folder beside the final output."""

    output = Path(output_folder)
    output.parent.mkdir(parents=True, exist_ok=True)

    return tempfile.mkdtemp(
        prefix="week10_staging_",
        dir=output.parent
    )


# FINALIZE OUTPUTS
def finalize_outputs(staging_folder, output_folder):
    """Replace outputs after successful validation."""

    staging = Path(staging_folder)
    output = Path(output_folder)
    backup = output.with_name(output.name + "_backup")

    if not staging.is_dir():
        raise FileNotFoundError("Staging folder does not exist.")

    if backup.exists():
        raise FileExistsError("Backup folder already exists.")

    if output.exists() and not output.is_dir():
        raise ValueError("Output path is not a folder.")

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
def write_failure_report(error, output_folder):
    """Save failure details outside the final output folder."""

    output = Path(output_folder)
    output.parent.mkdir(parents=True, exist_ok=True)

    report = output.with_name(output.name + "_failed_validation.csv")

    write_csv_report(
        str(report),
        [{"check": "pipeline", "status": "FAIL", "details": str(error)}],
        ["check", "status", "details"]
    )
