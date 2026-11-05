from __future__ import annotations

from typing import Any

from src.errors import InputFileError

CANONICAL_COLUMNS: list[str] = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]

MappedRecord = dict[str, Any]


def orient_column_map(column_map: dict[str, str]) -> dict[str, str]:
    """Return the map as {original_name: canonical_name}, inverting it if it was given the other way."""
    canonical = set(CANONICAL_COLUMNS)
    to_canonical = sum(v in canonical for v in column_map.values())
    from_canonical = sum(k in canonical for k in column_map)
    if from_canonical > to_canonical:
        return {original: name for name, original in column_map.items()}
    return dict(column_map)


def map_columns(
    header: list[str],
    records: list[dict[str, Any]],
    column_map: dict[str, str],
    source_name: str = "",
) -> list[MappedRecord]:
    """Rename raw columns to the canonical six and return records keyed by canonical names.

    Columns not in column_map keep their own name (so unrenamed columns still match).
    Extra columns (e.g. metadata) are dropped. A missing required column, or two
    columns mapping to the same name, is a file-level error (InputFileError).
    Original text values are kept untouched under "values".
    """
    rename = orient_column_map(column_map)
    effective = {col: rename.get(col, col) for col in header}
    targets = list(effective.values())

    clashes = {t for t in targets if targets.count(t) > 1 and t in set(CANONICAL_COLUMNS)}
    if clashes:
        raise InputFileError(f"{source_name}: several columns map to {sorted(clashes)}")
    missing = set(CANONICAL_COLUMNS) - set(targets)
    if missing:
        raise InputFileError(f"{source_name}: missing required column(s): {sorted(missing)}")

    original_for = {canon: orig for orig, canon in effective.items() if canon in set(CANONICAL_COLUMNS)}
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