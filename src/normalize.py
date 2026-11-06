"""Column mapping and text normalization shared by all four formats."""
from __future__ import annotations

from typing import Any

from src.errors import InputFileError

CANONICAL_COLUMNS: list[str] = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]

MappedRecord = dict[str, Any]


def map_columns(
    header: list[str],
    records: list[dict[str, Any]],
    column_map: dict[str, str],
    source_name: str = "",
) -> list[MappedRecord]:
    """Rename raw columns to the canonical six and return records keyed by canonical names.

    column_map is the manifest's source_to_canonical: {source_name: canonical_name}.
    Every target must be a canonical name, so a reversed map is a file-level error.
    Columns not in column_map keep their own name (so source columns that already have
    a canonical name still match). Extra columns (e.g. metadata) are dropped. A missing
    required column, or two columns mapping to the same name, is a file-level error
    (InputFileError). Original text values are kept untouched under "values".
    """
    canonical = set(CANONICAL_COLUMNS)
    unknown_targets = set(column_map.values()) - canonical
    if unknown_targets:
        raise InputFileError(
            f"{source_name}: column map must be source name -> canonical name; "
            f"unknown canonical name(s): {sorted(unknown_targets)}"
        )

    effective = {col: column_map.get(col, col) for col in header}
    targets = list(effective.values())

    clashes = {t for t in targets if targets.count(t) > 1 and t in canonical}
    if clashes:
        raise InputFileError(f"{source_name}: several columns map to {sorted(clashes)}")
    missing = canonical - set(targets)
    if missing:
        raise InputFileError(f"{source_name}: missing required column(s): {sorted(missing)}")

    original_for = {canon: orig for orig, canon in effective.items() if canon in canonical}
    mapped: list[MappedRecord] = []
    for rec in records:
        mapped.append(
            {
                "source_file": rec["source_file"],
                "source_record": rec["source_record"],
                "values": {c: rec["values"].get(original_for[c], "") for c in CANONICAL_COLUMNS},
            }
        )
    return mapped


def normalize_records(mapped: list[MappedRecord]) -> list[MappedRecord]:
    """Add a 'clean' dict with surrounding whitespace trimmed; 'values' stays original."""
    return [
        {**rec, "clean": {c: v.strip() for c, v in rec["values"].items()}}
        for rec in mapped
    ]